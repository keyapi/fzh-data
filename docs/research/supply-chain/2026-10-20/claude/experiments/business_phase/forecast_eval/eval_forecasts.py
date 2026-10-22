#!/usr/bin/env python
# -*- coding: utf-8 -*-
"""T2: forecast evaluation against statsforecast (v2, after T2-REVIEW).

Fixes vs the first version
--------------------------
1. Zero-actual cells are RETAINED in aggregate WAPE (only an all-zero actual
   total makes it undefined). Both variants are reported: keep-zero and
   exclude-zero, so a ranking change is visible instead of hidden.
2. Validation and test are compared on the COMMON SUBSET of cells where every
   candidate produced a forecast; per-candidate availability and failure reasons
   are reported. Per-model (own-availability) numbers are kept only as context.
3. The combination candidate is named `combo_dynamic_ew`: per cell it is the
   equal-weight mean of whichever simple models were available in that cell, and
   its composition per split is reported. It is NOT a fixed five-model combo.
4. Model selection uses the validation set ONLY (common subset, keep-zero WAPE);
   the test set is reported, never used to override the selection. Uncertainty
   comes from a SKU bootstrap on the validation cells.
5. Stratification (tier / warehouse / intermittent) is labelled POST-HOC with
   its basis stated; it is not treated as information available at the origin.

Read-only inputs: order_store.duckdb, destinations.json.
Outputs: forecast_eval_results.json, report.md
"""
from __future__ import annotations

import argparse
import hashlib
import json
import math
import random
import warnings
from collections import Counter, defaultdict
from datetime import date, timedelta
from pathlib import Path

import duckdb
import numpy as np

DB_PATH = Path("D:/Work/fzh-order-store/order_store.duckdb")
HERE = Path(__file__).resolve()
CLAUDE_DIR = HERE.parents[3]
OUT_DIR = HERE.parent
DEST = CLAUDE_DIR / "out" / "business_phase" / "destinations.json"

VAL_ORIGINS = ["2025-01", "2025-02", "2025-03", "2025-04", "2025-05", "2025-06"]
TEST_ORIGINS = ["2025-10", "2025-11", "2025-12", "2026-01", "2026-02", "2026-03"]
MIN_TRAIN = 24
WINDOW_DAYS = 90
SIMPLE = ["naive", "seasonal_naive", "ma3", "ma6", "ma12"]
MODELS = SIMPLE + ["tsb", "croston", "autoets", "combo_dynamic_ew"]
BOOTSTRAP = 300
warnings.filterwarnings("ignore")


def ym_i(ym: str) -> int:
    return int(ym[:4]) * 12 + int(ym[5:7]) - 1


def i_ym(i: int) -> str:
    y, m = divmod(i, 12)
    return f"{y:04d}-{m + 1:02d}"


def window_weights(start: date, days: int) -> dict[int, float]:
    end = start + timedelta(days=days)
    out, cur = {}, start.year * 12 + start.month - 1
    last = end.year * 12 + end.month - 1
    while cur <= last:
        ms = date(cur // 12, cur % 12 + 1, 1)
        nm = date((cur + 1) // 12, (cur + 1) % 12 + 1, 1)
        s, e = max(start, ms), min(end, nm)
        if e > s:
            out[cur] = (e - s).days / (nm - ms).days
        cur += 1
    return out


def decision_date(origin_i: int) -> date:
    return date((origin_i + 1) // 12, (origin_i + 1) % 12 + 1, 22)


def forecast(model: str, y: np.ndarray, h: int):
    n = len(y)
    if model == "naive":
        return np.repeat(y[-1], h)
    if model == "seasonal_naive":
        if n < 13:
            raise ValueError("history_lt_13m")
        return np.array([y[n - 12 + (k % 12)] for k in range(h)], dtype=float)
    if model in ("ma3", "ma6", "ma12"):
        k = min(int(model[2:]), n)
        if k < 1:
            raise ValueError("no_history")
        return np.repeat(float(np.mean(y[-k:])), h)
    from statsforecast import models as sfm
    if model == "tsb":
        m = sfm.TSB(alpha_d=0.3, alpha_p=0.3)
    elif model == "croston":
        m = sfm.CrostonOptimized()
    elif model == "autoets":
        m = sfm.AutoETS(season_length=12 if n >= 24 else 1)
    else:
        raise ValueError(f"unknown_model:{model}")
    m.fit(y.astype(np.float32))
    return np.asarray(m.predict(h=h)["mean"], dtype=float)


def conf_q(vals: list[float]) -> float:
    n = len(vals)
    level = min(1.0, math.ceil((n + 1) * 0.9) / n)
    xs = sorted(vals)
    return xs[min(n - 1, math.ceil(level * (n - 1) - 1e-12))]


def main() -> None:
    ap = argparse.ArgumentParser()
    ap.add_argument("--db", default=str(DB_PATH))
    ap.add_argument("--json", default=str(OUT_DIR / "forecast_eval_results.json"))
    ap.add_argument("--md", default=str(OUT_DIR / "report.md"))
    ap.add_argument("--minimal-only", action="store_true")
    args = ap.parse_args()

    db = Path(args.db)
    db_hash = hashlib.sha256(db.read_bytes()).hexdigest()
    dest = json.loads(DEST.read_text(encoding="utf-8"))
    eligible = [r["sku"] for r in dest["rows"] if r["destination"] == "mapped_eligible"]

    con = duckdb.connect(str(db), read_only=True)
    try:
        rows = con.execute("""
            SELECT sku_tongtool, substr(despatch_date,1,7), SUM(qty)
            FROM gs_orders
            WHERE despatch_date <= '2026-09-30'
              AND NOT regexp_matches(lower(platform_sku), '(^|[-_])test([-_]|$)')
            GROUP BY 1,2""").fetchall()
        wh = con.execute("SELECT sku, warehouse, SUM(available) FROM stock_latest "
                         "GROUP BY 1,2").fetchall()
    finally:
        con.close()
    if hashlib.sha256(db.read_bytes()).hexdigest() != db_hash:
        raise SystemExit("DB changed during the run")

    monthly = defaultdict(dict)
    for sku, ym, qty in rows:
        monthly[sku][ym] = float(qty)
    tmp = defaultdict(Counter)
    for sku, w, a in wh:
        tmp[sku][w] += int(a or 0)
    dom_wh = {s: c.most_common(1)[0][0] for s, c in tmp.items()}

    last_i = ym_i("2026-09")
    series = {}
    for sku in eligible:
        by = monthly.get(sku)
        if not by:
            continue
        first = min(ym_i(m) for m in by)
        months = [i_ym(i) for i in range(first, last_i + 1)]
        y = np.array([by.get(m, 0.0) for m in months], dtype=float)
        if len(y) >= MIN_TRAIN:
            series[sku] = dict(first=first, y=y, months=months)

    keys = sorted(series, key=lambda s: (-series[s]["y"].sum(), s))
    step = max(1, len(keys) // 200)
    plan = [("minimal", keys[::step][:200], ["2025-06"], ["2026-03"])]
    if not args.minimal_only:
        plan.append(("full", keys, VAL_ORIGINS, TEST_ORIGINS))

    results = dict(
        schema_version="t2_forecast_eval/2",
        inputs=dict(db=dict(path=str(db), sha256=db_hash),
                    destinations_sha256=hashlib.sha256(DEST.read_bytes()).hexdigest()),
        settings=dict(
            window_days=WINDOW_DAYS, min_train_months=MIN_TRAIN,
            validation_origins=VAL_ORIGINS, test_origins=TEST_ORIGINS,
            candidates=MODELS,
            combo_definition=("combo_dynamic_ew = per-cell equal-weight mean of the "
                              "SIMPLE candidates that produced a forecast in that "
                              "cell; composition reported per split"),
            zero_rule=("zero-actual cells are KEPT in WAPE; the aggregate is undefined "
                       "only when the actual total is zero"),
            common_subset_rule=("validation and test are compared on cells where EVERY "
                                "candidate produced a forecast"),
            selection_rule=("lowest validation WAPE on the common subset, keep-zero; "
                            "the test set is reported only"),
            calibration_rule=("same-shape rolling residuals with label_available_at "
                              "<= decision date; estimate, not a guarantee"),
        ),
        library_versions={},
        runs=[],
    )
    import importlib.metadata as md
    for pkg in ("statsforecast", "statsmodels", "numpy", "pandas"):
        try:
            results["library_versions"][pkg] = md.version(pkg)
        except Exception:
            pass

    for run_name, skus, val_origins, test_origins in plan:
        all_origins = val_origins + test_origins
        cells = {m: {} for m in MODELS}          # (sku,origin) -> dict(F,A,split,sku,origin)
        attempted = defaultdict(int)
        failures = Counter()
        combo_sizes = defaultdict(Counter)       # split -> size -> count
        resid = defaultdict(list)
        for origin_ym in all_origins:
            o = ym_i(origin_ym)
            dec = decision_date(o)
            w = window_weights(dec, WINDOW_DAYS)
            h = max(w) - o
            split = "val" if origin_ym in val_origins else "test"
            for sku in skus:
                s = series[sku]
                tr = o - s["first"] + 1
                if tr < 3:
                    attempted[("short_history", split)] += 1
                    continue
                ytr = s["y"][:tr]
                actual = sum(wt * s["y"][idx - s["first"]] for idx, wt in w.items())
                got = {}
                for m in SIMPLE + ["tsb", "croston", "autoets"]:
                    attempted[(m, split)] += 1
                    try:
                        got[m] = forecast(m, ytr, h)
                    except Exception as exc:
                        failures[f"{m}:{type(exc).__name__}:{str(exc)[:40]}"] += 1
                if got:
                    simple = [m for m in SIMPLE if m in got]
                    got["combo_dynamic_ew"] = np.mean(np.vstack([got[m] for m in simple]),
                                                      axis=0)
                    combo_sizes[split][len(simple)] += 1
                for m, f in got.items():
                    F = sum(wt * f[idx - (o + 1)] for idx, wt in w.items())
                    cells[m][(sku, origin_ym)] = dict(F=float(F), A=float(actual),
                                                      split=split, sku=sku,
                                                      origin=origin_ym)
                    label_at = date((max(w) + 1) // 12, (max(w) + 1) % 12 + 1, 1)
                    resid[(sku, m)].append(dict(label_at=label_at, err=float(actual - F),
                                                F=float(F)))

        def p90_lift(sku: str, m: str, origin_ym: str):
            dec = decision_date(ym_i(origin_ym))
            vals = [r["err"] for r in resid.get((sku, m), []) if r["label_at"] <= dec]
            if len(vals) >= 3:
                return conf_q(vals)
            pool = []
            for (s2, m2), rs in resid.items():
                if m2 != m:
                    continue
                for r in rs:
                    if r["label_at"] <= dec and abs(r["F"]) > 1e-9:
                        pool.append(r["err"] / r["F"])
            if len(pool) >= 3:
                return conf_q(pool) * cells[m][(sku, origin_ym)]["F"]
            return None

        # common subsets
        common = {}
        for split in ("val", "test"):
            per = [set(k for k, c in cells[m].items() if c["split"] == split)
                   for m in MODELS]
            common[split] = set.intersection(*per) if per else set()

        # MASE scale in window units (in-sample seasonal naive)
        def scale_for(sku: str) -> float | None:
            s = series[sku]
            vals = []
            for idx in range(s["first"] + 12, last_i):
                ww = window_weights(decision_date(idx), WINDOW_DAYS)
                if max(ww) > last_i:
                    continue
                a_now = sum(wt * s["y"][k - s["first"]] for k, wt in ww.items())
                a_prev = sum(wt * s["y"][k - 12 - s["first"]] for k, wt in ww.items()
                             if k - 12 >= s["first"])
                vals.append(abs(a_now - a_prev))
            return float(np.mean(vals)) if vals and np.mean(vals) > 1e-9 else None

        scales = {sku: scale_for(sku) for sku in skus}

        def stats(m: str, split: str, key_filter=None) -> dict:
            cs = [c for k, c in cells[m].items()
                  if c["split"] == split and (key_filter is None or k in key_filter)]
            n = len(cs)
            if n == 0:
                return dict(n=0)
            sum_a = sum(c["A"] for c in cs)
            zero = sum(1 for c in cs if abs(c["A"]) < 1e-9)
            keep = (sum(abs(c["F"] - c["A"]) for c in cs) / sum_a) if sum_a > 1e-9 else None
            bias = (sum(c["F"] - c["A"] for c in cs) / sum_a) if sum_a > 1e-9 else None
            pos = [c for c in cs if abs(c["A"]) > 1e-9]
            sum_ap = sum(c["A"] for c in pos)
            excl = (sum(abs(c["F"] - c["A"]) for c in pos) / sum_ap) if sum_ap > 1e-9 else None
            num, den = [], []
            for c in cs:
                sc = scales.get(c["sku"])
                if sc is not None:
                    num.append(abs(c["F"] - c["A"]))
                    den.append(sc)
            mase = (float(np.mean(num)) / float(np.mean(den))) if num and np.mean(den) > 1e-9 else None
            covs, widths = [], []
            for c in cs:
                lift = p90_lift(c["sku"], m, c["origin"])
                if lift is None:
                    continue
                p90 = c["F"] + max(0.0, float(lift))
                covs.append(1.0 if c["A"] <= p90 + 1e-9 else 0.0)
                widths.append(p90 - c["F"])
            return dict(n=n, zero_actual_cells=zero,
                        wape_keep_zero=(round(keep, 4) if keep is not None else None),
                        wape_exclude_zero=(round(excl, 4) if excl is not None else None),
                        bias=(round(bias, 4) if bias is not None else None),
                        mase=(round(mase, 4) if mase is not None else None),
                        coverage=(round(float(np.mean(covs)), 4) if covs else None),
                        width=(round(float(np.mean(widths)), 3) if widths else None))

        # ---- selection strictly on validation (common subset, keep-zero) ----
        val_stats = {m: stats(m, "val") for m in MODELS}
        val_common = {m: stats(m, "val", common["val"]) for m in MODELS}
        pool = [m for m in MODELS if val_common[m].get("wape_keep_zero") is not None]
        best = min(pool, key=lambda m: val_common[m]["wape_keep_zero"]) if pool else None

        # ---- SKU bootstrap on validation common cells -----------------------
        rng = random.Random(20261022)
        boot_best = Counter()
        boot_wape = defaultdict(list)
        if pool:
            per_sku = {m: defaultdict(lambda: [0.0, 0.0]) for m in MODELS}
            for m in MODELS:
                for k, c in cells[m].items():
                    if k in common["val"]:
                        per_sku[m][c["sku"]][0] += abs(c["F"] - c["A"])
                        per_sku[m][c["sku"]][1] += c["A"]
            sku_list = sorted({c["sku"] for k, c in cells[MODELS[0]].items()
                               if k in common["val"]})
            for _ in range(BOOTSTRAP):
                sample = [sku_list[rng.randrange(len(sku_list))] for _ in range(len(sku_list))]
                vals = {}
                for m in MODELS:
                    num = sum(per_sku[m][s][0] for s in sample)
                    den = sum(per_sku[m][s][1] for s in sample)
                    if den > 1e-9:
                        vals[m] = num / den
                        boot_wape[m].append(vals[m])
                if vals:
                    boot_best[min(vals, key=vals.get)] += 1

        # ---- groups (post-hoc) ---------------------------------------------
        def groups(m: str, split: str):
            cs = [c for c in cells[m].values() if c["split"] == split]
            tot = defaultdict(float)
            for c in cs:
                tot[c["sku"]] += c["A"]
            order = sorted(tot, key=lambda s: -tot[s])
            third = max(1, len(order) // 3)
            tier = {s: ("high" if i < third else "mid" if i < 2 * third else "low")
                    for i, s in enumerate(order)}
            out = defaultdict(list)
            for c in cs:
                out[f"tier:{tier[c['sku']]}"].append(c)
                out[f"warehouse:{dom_wh.get(c['sku'], 'unknown')}"].append(c)
                y = series[c["sku"]]["y"]
                out[f"intermittent:{'yes' if float(np.mean(y == 0)) >= 0.5 else 'no'}"].append(c)
            res = {}
            for g, arr in out.items():
                sa = sum(c["A"] for c in arr)
                if sa < 1e-9:
                    continue
                res[g] = dict(n=len(arr), zero_cells=sum(1 for c in arr if c["A"] == 0),
                              wape=round(sum(abs(c["F"] - c["A"]) for c in arr) / sa, 4),
                              bias=round(sum(c["F"] - c["A"] for c in arr) / sa, 4))
            return res

        results["runs"].append(dict(
            run=run_name, n_series=len(skus),
            availability={
                "attempted": {f"{k[0]}|{k[1]}": v for k, v in attempted.items()},
                "available": {m: {s: sum(1 for c in cells[m].values() if c["split"] == s)
                                  for s in ("val", "test")} for m in MODELS},
                "measured": {m: {s: sum(1 for c in cells[m].values() if c["split"] == s)
                                 for s in ("val", "test")} for m in MODELS},
                "common": {s: len(common[s]) for s in ("val", "test")},
                "failures": dict(failures.most_common(20)),
                "n_failures_total": sum(failures.values()),
            },
            combo_composition={s: dict(combo_sizes[s]) for s in ("val", "test")},
            validation_own=val_stats,
            validation_common=val_common,
            test_own={m: stats(m, "test") for m in MODELS},
            test_common={m: stats(m, "test", common["test"]) for m in MODELS},
            selected_model=best,
            selection_basis=("validation common subset, keep-zero WAPE"),
            selection_uncertainty=dict(
                bootstrap=BOOTSTRAP,
                best_model_frequency=dict(boot_best.most_common()),
                wape_p5_p95={m: [round(float(np.percentile(v, 5)), 4),
                                 round(float(np.percentile(v, 95)), 4)]
                             for m, v in boot_wape.items() if len(v) > 10},
            ),
            groups_post_hoc=(groups(best, "test") if best else {}),
            groups_note=("post-hoc only: tier uses TEST-period sales, intermittent uses "
                         "full-history zero share, warehouse uses the CURRENT primary "
                         "warehouse -- none of these is known at the forecast origin"),
        ))
        print(f"[{run_name}] series={len(skus)} common_val={len(common['val'])} "
              f"common_test={len(common['test'])} selected={best} "
              f"val_keep={val_common.get(best, {}).get('wape_keep_zero')}")

    out_json = Path(args.json)
    out_json.write_text(json.dumps(results, ensure_ascii=False, indent=1) + "\n",
                        encoding="utf-8")
    print("wrote", out_json)


if __name__ == "__main__":
    main()
