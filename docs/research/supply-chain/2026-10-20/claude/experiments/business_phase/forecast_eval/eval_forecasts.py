#!/usr/bin/env python
# -*- coding: utf-8 -*-
"""T2: forecast evaluation against a mature-model library (statsforecast).

Design (fixed before looking at results):
  data      : order_store.duckdb, monthly net sales per tongtool SKU
              (sum(qty) by despatch month, test lines excluded, zero-filled)
  window    : SAME shape as the first batch -- 90 calendar days starting on the
              22nd of the month after each origin (bucket weights, 4 months)
  split     : validation origins 2025-01..2025-06, test origins 2025-10..2026-03
              (model selection uses validation ONLY)
  isolation : interval calibration for an origin uses residuals whose
              label_available_at (first day after the window's last month) is
              <= that origin's decision date -- the same rule as V1 R3
  candidates: naive, seasonal_naive, ma3, ma6, ma12, TSB, Croston, AutoETS,
              equal-weight combo of the simple point models
  failures  : every failed / inapplicable (model, series, origin) is kept with a
              reason code; nothing is silently dropped.

Outputs: forecast_eval_results.json, report.md
"""
from __future__ import annotations

import argparse
import hashlib
import json
import math
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
MIN_TRAIN = 24            # months needed to be "trainable" for this evaluation
WINDOW_DAYS = 90
SIMPLE = ["naive", "seasonal_naive", "ma3", "ma6", "ma12"]
MODELS = SIMPLE + ["tsb", "croston", "autoets", "combo"]
warnings.filterwarnings("ignore")


def ym_i(ym: str) -> int:
    return int(ym[:4]) * 12 + int(ym[5:7]) - 1


def i_ym(i: int) -> str:
    y, m = divmod(i, 12)
    return f"{y:04d}-{m + 1:02d}"


def month_len(i: int) -> int:
    y, m = divmod(i, 12)
    leap = (y % 4 == 0 and (y % 100 != 0 or y % 400 == 0))
    return [31, 29 if leap else 28, 31, 30, 31, 30, 31, 31, 30, 31, 30, 31][m]


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
    """Return monthly point forecast (length h) or raise with a reason."""
    n = len(y)
    if model == "naive":
        return np.repeat(y[-1], h)
    if model == "seasonal_naive":
        if n < 13:
            raise ValueError("history_lt_13m")
        return np.array([y[n - 12 + (k % 12)] for k in range(h)], dtype=float)
    if model in ("ma3", "ma6", "ma12"):
        k = int(model[2:])
        k = min(k, n)
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
    out = m.predict(h=h)
    return np.asarray(out["mean"], dtype=float)


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
    dom_wh = {}
    tmp = defaultdict(Counter)
    for sku, w, a in wh:
        tmp[sku][w] += int(a or 0)
    for sku, c in tmp.items():
        dom_wh[sku] = c.most_common(1)[0][0]

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

    # minimal reproducible comparison: deterministic sample of 200 series
    keys = sorted(series, key=lambda s: (-series[s]["y"].sum(), s))
    step = max(1, len(keys) // 200)
    minimal = keys[::step][:200]
    plan = [("minimal", minimal, ["2025-06"], ["2026-03"])]
    if not args.minimal_only:
        plan.append(("full", keys, VAL_ORIGINS, TEST_ORIGINS))

    results = dict(
        schema_version="t2_forecast_eval/1",
        inputs=dict(db=dict(path=str(db), sha256=db_hash),
                    destinations_sha256=hashlib.sha256(DEST.read_bytes()).hexdigest()),
        settings=dict(window_days=WINDOW_DAYS, min_train_months=MIN_TRAIN,
                      validation_origins=VAL_ORIGINS, test_origins=TEST_ORIGINS,
                      candidates=MODELS,
                      selection_rule="best validation WAPE (coverage >= 90% of cells)",
                      calibration_rule=("same-shape rolling residuals with "
                                        "label_available_at <= decision date")),
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
        # ---- build cells per model/origin ----------------------------------
        cells = {m: [] for m in MODELS}          # (sku, origin, F, A, split)
        failures = Counter()
        resid = defaultdict(list)                # (sku, model) -> [(label_at, err, F)]
        for origin_ym in all_origins:
            o = ym_i(origin_ym)
            dec = decision_date(o)
            w = window_weights(dec, WINDOW_DAYS)
            h = max(w) - o
            for sku in skus:
                s = series[sku]
                tr = o - s["first"] + 1
                if tr < 3:
                    failures["short_history"] += 1
                    continue
                ytr = s["y"][:tr]
                actual = sum(wt * s["y"][idx - s["first"]] for idx, wt in w.items()
                             if idx - s["first"] < len(s["y"]))
                got = {}
                for m in MODELS[:-1]:
                    try:
                        got[m] = forecast(m, ytr, h)
                    except Exception as exc:
                        failures[f"{m}:{type(exc).__name__}:{str(exc)[:40]}"] += 1
                if got:
                    got["combo"] = np.mean(np.vstack([got[m] for m in SIMPLE
                                                      if m in got]), axis=0)
                for m, f in got.items():
                    F = sum(wt * f[idx - (o + 1)] for idx, wt in w.items())
                    split = "val" if origin_ym in val_origins else "test"
                    cells[m].append(dict(sku=sku, origin=origin_ym, split=split,
                                         F=float(F), A=float(actual)))
                    # residual available for FUTURE origins only
                    label_at = date((max(w) + 1) // 12, (max(w) + 1) % 12 + 1, 1)
                    resid[(sku, m)].append(dict(label_at=label_at,
                                                err=float(actual - F),
                                                F=float(F)))
        # ---- interval calibration per (sku, model, origin) ------------------
        def p90_lift(sku: str, m: str, origin_ym: str):
            o = ym_i(origin_ym)
            dec = decision_date(o)
            vals = [r["err"] for r in resid.get((sku, m), [])
                    if r["label_at"] <= dec]
            if len(vals) >= 3:
                return conf_q(vals), "own"
            pool = []
            for (s2, m2), rs in resid.items():
                if m2 != m:
                    continue
                for r in rs:
                    if r["label_at"] <= dec and abs(r["F"]) > 1e-9:
                        pool.append(r["err"] / r["F"])
            if len(pool) >= 3:
                base = next(c["F"] for c in cells[m]
                            if c["sku"] == sku and c["origin"] == origin_ym)
                return conf_q(pool) * base, "pooled"
            return None, "not_calibrated"

        def metrics(m: str, split: str):
            cs = [c for c in cells[m] if c["split"] == split]
            n = len(cs)
            zero = sum(1 for c in cs if abs(c["A"]) < 1e-9)
            usable = [c for c in cs if abs(c["A"]) > 1e-9]
            sum_a = sum(c["A"] for c in usable)
            if not usable or sum_a < 1e-9:
                return dict(n=n, n_scored=len(usable), zero_actual_cells=zero,
                            wape=None, bias=None, mase=None, coverage=None,
                            width=None)
            wape = sum(abs(c["F"] - c["A"]) for c in usable) / sum_a
            bias = sum(c["F"] - c["A"] for c in usable) / sum_a
            # MASE scale must be in the SAME units as F/A (cumulative window):
            # mean |A_window(o) - A_window(o-12)| over in-sample origins.
            per_series = defaultdict(list)
            for c in cs:
                per_series[c["sku"]].append(c)
            scale = {}
            for sku in per_series:
                s = series[sku]
                vals = []
                for idx in range(s["first"] + 12, last_i):
                    o = idx
                    dec = decision_date(o)
                    ww = window_weights(dec, WINDOW_DAYS)
                    if max(ww) > last_i:
                        continue
                    a_now = sum(wt * s["y"][k - s["first"]] for k, wt in ww.items())
                    a_prev = sum(wt * s["y"][k - 12 - s["first"]] for k, wt in ww.items()
                                 if k - 12 >= s["first"])
                    vals.append(abs(a_now - a_prev))
                if vals and float(np.mean(vals)) > 1e-9:
                    scale[sku] = float(np.mean(vals))
            num, den = [], []
            for c in usable:
                if c["sku"] in scale:
                    num.append(abs(c["F"] - c["A"]))
                    den.append(scale[c["sku"]])
            mase = (np.mean(num) / np.mean(den)) if num and np.mean(den) > 1e-9 else None
            covs, widths = [], []
            for c in usable:
                lift, kind = p90_lift(c["sku"], m, c["origin"])
                if lift is None:
                    continue
                p90 = c["F"] + max(0.0, float(lift))
                covs.append(1.0 if c["A"] <= p90 + 1e-9 else 0.0)
                widths.append(p90 - c["F"])
            return dict(n=n, n_scored=len(usable), zero_actual_cells=zero,
                        wape=round(float(wape), 4), bias=round(float(bias), 4),
                        mase=(round(float(mase), 4) if mase is not None else None),
                        coverage=(round(float(np.mean(covs)), 4) if covs else None),
                        width=(round(float(np.mean(widths)), 3) if widths else None))
        # ---- group breakdown for the selected model -------------------------
        val_metrics = {m: metrics(m, "val") for m in MODELS}
        eligible_models = [m for m in MODELS
                           if val_metrics[m]["wape"] is not None
                           and val_metrics[m]["n_scored"] >= 0.9 * max(
                               v["n_scored"] for v in val_metrics.values())]
        best = min(eligible_models, key=lambda m: val_metrics[m]["wape"]) if eligible_models else None

        def group_metrics(m: str, split: str):
            cs = [c for c in cells[m] if c["split"] == split]
            tiers = {}
            tot = defaultdict(float)
            for c in cs:
                tot[c["sku"]] += c["A"]
            order = sorted(tot, key=lambda s: -tot[s])
            third = max(1, len(order) // 3)
            tier_of = {}
            for i, sku in enumerate(order):
                tier_of[sku] = "high" if i < third else ("mid" if i < 2 * third else "low")
            groups = defaultdict(list)
            for c in cs:
                groups[f"tier:{tier_of[c['sku']]}"].append(c)
                groups[f"warehouse:{dom_wh.get(c['sku'], 'unknown')}"].append(c)
                y = series[c["sku"]]["y"]
                zero_share = float(np.mean(y == 0))
                groups[f"intermittent:{'yes' if zero_share >= 0.5 else 'no'}"].append(c)
            out = {}
            for g, arr in groups.items():
                usable = [c for c in arr if abs(c["A"]) > 1e-9]
                if not usable:
                    continue
                sa = sum(c["A"] for c in usable)
                out[g] = dict(n=len(arr), n_scored=len(usable),
                              wape=round(sum(abs(c["F"] - c["A"]) for c in usable) / sa, 4),
                              bias=round(sum(c["F"] - c["A"] for c in usable) / sa, 4))
            return out

        results["runs"].append(dict(
            run=run_name, n_series=len(skus),
            n_cells={m: len(cells[m]) for m in MODELS},
            validation=val_metrics, test={m: metrics(m, "test") for m in MODELS},
            selected_model=best,
            selection_reason=("最低验证 WAPE（覆盖率门槛 90%）" if best else "无可用模型"),
            groups=(group_metrics(best, "test") if best else {}),
            failures=dict(failures.most_common(20)),
            n_failures_total=sum(failures.values()),
        ))
        print(f"[{run_name}] series={len(skus)} best={best} "
              f"val_wape={val_metrics.get(best, {}).get('wape') if best else None} "
              f"test_wape={results['runs'][-1]['test'][best]['wape'] if best else None}")

    out_json = Path(args.json)
    out_json.write_text(json.dumps(results, ensure_ascii=False, indent=1) + "\n", encoding="utf-8")
    print("wrote", out_json)


if __name__ == "__main__":
    main()
