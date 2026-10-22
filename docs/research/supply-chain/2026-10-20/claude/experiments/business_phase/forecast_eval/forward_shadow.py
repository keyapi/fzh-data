#!/usr/bin/env python
# -*- coding: utf-8 -*-
"""T10 forward shadow: pre-register predictions, score them after labels exist.

Why this script exists
----------------------
The current label coverage has NO clean hold-out block (T2's 2026-03 origin
already reaches July 2026 with its 90-day target window). The only clean
evidence is a real forward shadow: save the sample, the inner selection, every
candidate's forecast and the generation time BEFORE the target months are
labelled, then score that saved file once the labels arrive.

Parameterisation (T12 audit fix)
--------------------------------
Nothing about the cut-off or the outer origin is hard-coded:
  --data-cutoff   last month with labels (default: max month found in the DB)
  --origin        last month of the training window (default: = data cutoff);
                  forecasts cover origin+1 .. origin+--h
  --inner-offsets inner cut points relative to the origin (default 3,6,9)
  --h             horizon in months (default 3)
Target months, the scoring due date (day 4 of the month after the last target
month) and the file name are all derived from those parameters.

Usage
  # presave (run before the target months have labels; refuses to overwrite)
  uv run python forward_shadow.py
  uv run python forward_shadow.py --data-cutoff 2026-09 --origin 2026-09

  # score (run when labels are available; never re-selects a model)
  uv run python forward_shadow.py --mode score --pred-file shadow_2026-09.json

Outputs
  shadow_<origin>.json         pre-registered predictions (immutable evidence)
  shadow_<origin>_score.json   scores, only in --mode score

Metric matches nested_eval.py: WAPE = Σ|F−A| / ΣA on the common evaluable
subset, zero-demand cells retained in the numerator, missing predictions null.
"""
from __future__ import annotations

import argparse
import hashlib
import json
import sys
import time
from collections import Counter, defaultdict
from datetime import datetime, timezone
from pathlib import Path

import duckdb
import numpy as np

HERE = Path(__file__).resolve()
sys.path.insert(0, str(HERE.parent))
from nested_eval import forecast, i_ym, ym_i   # noqa: E402  (shared model code)

CLAUDE_DIR = HERE.parents[3]
DEFAULT_DB = Path("D:/Work/fzh-order-store/order_store.duckdb")
DEST = CLAUDE_DIR / "out" / "business_phase" / "destinations.json"
OUT_DIR = HERE.parent

CANDIDATES = ["naive", "ma3", "ma6", "seasonal_naive", "autoets", "combo_ew"]


def parse_args() -> argparse.Namespace:
    ap = argparse.ArgumentParser(description=__doc__,
                                 formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("--db", default=str(DEFAULT_DB))
    ap.add_argument("--dest", default=str(DEST))
    ap.add_argument("--data-cutoff", help="last labelled month YYYY-MM (default: DB max)")
    ap.add_argument("--origin", help="training-window end YYYY-MM (default: data cutoff)")
    ap.add_argument("--h", type=int, default=3)
    ap.add_argument("--inner-offsets", default="3,6,9")
    ap.add_argument("--n-series", type=int, default=200)
    ap.add_argument("--mode", choices=["presave", "score"], default="presave")
    ap.add_argument("--pred-file", help="pre-registered file to score (score mode)")
    ap.add_argument("--out-dir", default=str(OUT_DIR))
    ap.add_argument("--force", action="store_true",
                    help="overwrite an existing presave file (breaks pre-registration)")
    return ap.parse_args()


def db_months(db: str) -> tuple[str, str]:
    con = duckdb.connect(db, read_only=True)
    try:
        lo, hi = con.execute(
            "SELECT min(substr(despatch_date,1,7)), max(substr(despatch_date,1,7)) "
            "FROM gs_orders").fetchone()
    finally:
        con.close()
    return lo, hi


def load_series(db: str, dest_path: str, cutoff: str) -> tuple[dict, str, set]:
    """Monthly SKU series strictly up to and including `cutoff`."""
    cutoff_end = f"{i_ym(ym_i(cutoff) + 1)}-01"          # first day after cutoff
    db_hash = hashlib.sha256(Path(db).read_bytes()).hexdigest()
    dest = {r["sku"]: r for r in
            json.loads(Path(dest_path).read_text(encoding="utf-8"))["rows"]}
    eligible = {s for s, r in dest.items() if r["destination"] == "mapped_eligible"}
    con = duckdb.connect(db, read_only=True)
    try:
        rows = con.execute("""
            SELECT sku_tongtool, substr(despatch_date,1,7), warehouse, SUM(qty)
            FROM gs_orders
            WHERE despatch_date < ?
              AND NOT regexp_matches(lower(platform_sku), '(^|[-_])test([-_]|$)')
            GROUP BY 1,2,3""", [cutoff_end]).fetchall()
    finally:
        con.close()
    if hashlib.sha256(Path(db).read_bytes()).hexdigest() != db_hash:
        raise SystemExit("DB changed during read")
    month = defaultdict(dict)
    for sku, ym, _wh, q in rows:
        if sku in eligible:
            month[sku][ym] = month[sku].get(ym, 0.0) + float(q)
    last_i = ym_i(cutoff)
    series = {}
    for sku, by in month.items():
        first = min(ym_i(m) for m in by)
        months = [i_ym(i) for i in range(first, last_i + 1)]
        series[sku] = dict(first=first,
                           y=np.array([by.get(m, 0.0) for m in months], dtype=float))
    return series, db_hash, eligible


def fallback_rule(n: int) -> dict:
    if n < 3:
        return dict(allowed=["naive"], reason="n<3: only naive is defined")
    if n < 13:
        return dict(allowed=["naive", "ma3", "ma6", "autoets"],
                    reason="n<13: seasonal_naive needs 12 lags; autoets season_length=1")
    if n < 24:
        return dict(allowed=CANDIDATES,
                    reason="13<=n<24: autoets season_length=1; one-season low-confidence flag")
    return dict(allowed=CANDIDATES, reason="n>=24")


def combo(got: dict):
    parts = [got[m] for m in ("naive", "ma3", "ma6", "seasonal_naive") if m in got]
    return np.mean(np.vstack(parts), axis=0) if parts else None


def presave(args) -> None:
    _, db_hi = db_months(args.db)
    cutoff = args.data_cutoff or db_hi
    origin = args.origin or cutoff
    if ym_i(origin) != ym_i(cutoff):
        raise SystemExit(f"presave requires origin == data cutoff ({cutoff}); got {origin}. "
                         "The shadow forecasts must start after the last labelled month.")
    offsets = tuple(int(x) for x in args.inner_offsets.split(",") if x.strip())
    O = ym_i(origin)
    targets = [i_ym(O + k) for k in range(1, args.h + 1)]
    due = f"{i_ym(O + args.h + 1)}-04"       # labels for the last target close on day 4

    series, db_hash, _ = load_series(args.db, args.dest, cutoff)
    keys = sorted(series, key=lambda s: (-float(series[s]["y"].sum()), s))
    step = max(1, len(keys) // args.n_series)
    sample = keys[::step][:args.n_series]

    fits = Counter()
    failures = Counter()
    selected, forecasts, reasons = {}, {}, {}
    for sku in sample:
        s = series[sku]
        n_tr = O - s["first"] + 1
        rule = fallback_rule(n_tr)
        scores = {c: [] for c in CANDIDATES}
        for k in offsets:
            i_o = O - k
            tr = i_o - s["first"] + 1
            if tr < 2 or i_o + args.h > O:     # inner target must end <= origin
                continue
            A = float(np.sum(s["y"][i_o + 1 - s["first"]: i_o + 1 - s["first"] + args.h]))
            got = {}
            for c in rule["allowed"]:
                if c == "combo_ew":
                    continue
                try:
                    got[c] = forecast(c, s["y"][:tr], args.h)
                    fits[c] += 1
                except Exception as exc:
                    failures[f"{c}:{type(exc).__name__}"] += 1
            cb = combo(got)
            if cb is not None:
                got["combo_ew"] = cb
            for c, f in got.items():
                F = float(np.sum(f))
                scores[c].append(abs(F - A) / A if A > 1e-9 else None)
        chosen, best = "naive", None
        for c in ["autoets", "seasonal_naive", "ma6", "ma3", "combo_ew", "naive"]:
            vals = [v for v in scores.get(c, []) if v is not None]
            if not vals:
                continue
            m = float(np.mean(vals))
            if best is None or m < best - 1e-12:
                best, chosen = m, c
        reasons[sku] = (f"inner mean |err|/A = {best:.4f}" if best is not None
                        else "no feasible candidate -> naive")
        ytr = s["y"][:max(n_tr, 0)]
        if n_tr < 2:
            failures["outer:insufficient_history"] += 1
            selected[sku] = None
            continue
        out = {}
        for c in ["naive", "ma3", "ma6", "seasonal_naive", "autoets"]:
            if c not in rule["allowed"] and c != "naive":
                continue
            try:
                out[c] = forecast(c, ytr, args.h)
                fits[f"outer:{c}"] += 1
            except Exception as exc:
                failures[f"outer:{c}:{type(exc).__name__}"] += 1
        cb = combo(out)
        if cb is not None:
            out["combo_ew"] = cb
        sel_f = out.get(chosen)
        if sel_f is None:
            sel_f, chosen = out.get("naive"), "naive"
            reasons[sku] += " | outer refit fell back to naive"
        selected[sku] = chosen
        forecasts[sku] = {c: [round(float(v), 4) for v in f] for c, f in out.items()}
        forecasts[sku]["selected"] = [round(float(v), 4) for v in sel_f]

    payload = dict(
        schema_version="t10_forward_shadow/1",
        generated_at=datetime.now(timezone.utc).astimezone().isoformat(timespec="seconds"),
        data_cutoff=cutoff,
        origin=origin,
        target_months=targets,
        scoring_due=due,
        params=dict(h=args.h, inner_offsets=list(offsets), n_series=args.n_series,
                    candidates=CANDIDATES),
        inputs=dict(db_sha256=db_hash,
                    destinations_sha256=hashlib.sha256(
                        Path(args.dest).read_bytes()).hexdigest()),
        sample=dict(n=len(sample),
                    rule=("ranked by training-window qty only (first .. origin), "
                          "every k-th, first n_series"),
                    skus=[dict(sku=s, n_train=O - series[s]["first"] + 1,
                               train_total=round(float(series[s]["y"].sum()), 2))
                          for s in sample]),
        selection=reasons,
        forecasts=forecasts,
        selection_distribution=dict(Counter(v for v in selected.values() if v).most_common()),
        fits=dict(fits),
        failures=dict(failures.most_common()),
        metric_definition=dict(
            wape="Σ|F−A| / ΣA on the common evaluable subset",
            zero_demand="零需求单元格保留在分子；对分母贡献 0",
            common_subset="所有候选预测均非 null 的 SKU×目标窗",
            missing_forecast="缺失预测写 null，不写 0"),
        presave_checklist=[
            "sample (SKU list + training totals) saved before labels exist",
            "inner-selection result and reason per SKU saved",
            "every candidate's monthly forecast and the selected forecast saved",
            "generation timestamp, data cutoff, origin, target months saved",
            "file is written once; --force is required to overwrite",
        ],
        wording_note=("只记录在未见样本上的差异与不确定性；这不是准确率，也没有通用阈值；"
                      "评分前不得改选模型，评分后一次结果也不得改默认。"),
        status="presaved; waiting for labels",
    )
    out_path = Path(args.out_dir) / f"shadow_{origin}.json"
    if out_path.exists() and not args.force:
        raise SystemExit(f"{out_path} already exists — pre-registered predictions are "
                         "immutable; use --force only if you really mean to overwrite")
    out_path.write_text(json.dumps(payload, ensure_ascii=False, indent=1) + "\n",
                        encoding="utf-8")
    print(f"wrote {out_path}")
    print(f"cutoff {cutoff} origin {origin} targets {targets} scoring_due {due}")
    print("selection", payload["selection_distribution"], "failures", dict(failures))


def score(args) -> None:
    if not args.pred_file:
        raise SystemExit("--mode score requires --pred-file shadow_YYYY-MM.json")
    path = Path(args.pred_file)
    pre = json.loads(path.read_text(encoding="utf-8"))
    origin = pre["origin"]
    targets = pre["target_months"]
    _, db_hi = db_months(args.db)
    if ym_i(db_hi) < ym_i(targets[-1]):
        raise SystemExit(f"labels missing: need through {targets[-1]}, DB has {db_hi}; "
                         f"score again after {pre['scoring_due']}")
    db_hash = hashlib.sha256(Path(args.db).read_bytes()).hexdigest()
    con = duckdb.connect(args.db, read_only=True)
    try:
        rows = con.execute("""
            SELECT sku_tongtool, substr(despatch_date,1,7), SUM(qty)
            FROM gs_orders
            WHERE substr(despatch_date,1,7) IN ({})
              AND NOT regexp_matches(lower(platform_sku), '(^|[-_])test([-_]|$)')
            GROUP BY 1,2""".format(",".join("?" * len(targets))), targets).fetchall()
    finally:
        con.close()
    actual = defaultdict(float)
    for sku, _ym, q in rows:
        actual[sku] += float(q)

    methods = ["selected", "naive", "ma3"]
    by_sku = {}
    for sku, fc in pre["forecasts"].items():
        if sku not in actual:
            continue
        if not all(m in fc for m in methods):
            continue
        by_sku[sku] = dict(actual=actual[sku],
                           **{m: float(np.sum(fc[m])) for m in methods})
    if not by_sku:
        raise SystemExit("no common evaluable SKU between presave file and labels")
    den = sum(v["actual"] for v in by_sku.values())
    zero = sum(1 for v in by_sku.values() if abs(v["actual"]) < 1e-9)
    wape = {m: (round(sum(abs(v[m] - v["actual"]) for v in by_sku.values()) / den, 4)
                if den > 1e-9 else None) for m in methods}
    rng = np.random.default_rng(ym_i(origin) * 100 + 4)   # deterministic, origin-derived
    skus = sorted(by_sku)
    diffs = {"selected_minus_ma3": [], "selected_minus_naive": []}
    for _ in range(300):
        pick = [skus[rng.integers(0, len(skus))] for _ in range(len(skus))]
        sden = sum(by_sku[s]["actual"] for s in pick)
        if sden < 1e-9:
            continue
        sel = sum(abs(by_sku[s]["selected"] - by_sku[s]["actual"]) for s in pick) / sden
        ma3 = sum(abs(by_sku[s]["ma3"] - by_sku[s]["actual"]) for s in pick) / sden
        nai = sum(abs(by_sku[s]["naive"] - by_sku[s]["actual"]) for s in pick) / sden
        diffs["selected_minus_ma3"].append(sel - ma3)
        diffs["selected_minus_naive"].append(sel - nai)
    payload = dict(
        schema_version="t10_forward_shadow_score/1",
        scored_at=datetime.now(timezone.utc).astimezone().isoformat(timespec="seconds"),
        presave_file=str(path.name), generated_at=pre["generated_at"],
        origin=origin, target_months=targets,
        inputs=dict(db_sha256=db_hash,
                    presave_db_sha256=pre["inputs"]["db_sha256"],
                    destinations_sha256=pre["inputs"]["destinations_sha256"]),
        n_scored=len(by_sku), n_zero_demand_retained=zero,
        denominator=round(den, 2),
        wape=wape,
        bootstrap=dict(iterations=300,
                       **{k: dict(mean=round(float(np.mean(v)), 4),
                                  p5=round(float(np.percentile(v, 5)), 4),
                                  p95=round(float(np.percentile(v, 95)), 4))
                          for k, v in diffs.items()}),
        note=("一次月度结果不构成改默认的依据；区间跨 0 时只能说方向不稳定；"
              "选择结果来自预存文件，评分阶段未重新选模。"),
    )
    out_path = Path(args.out_dir) / f"shadow_{origin}_score.json"
    out_path.write_text(json.dumps(payload, ensure_ascii=False, indent=1) + "\n",
                        encoding="utf-8")
    print(f"wrote {out_path}")
    print("n", len(by_sku), "zero", zero, "wape", wape)
    print("bootstrap", payload["bootstrap"])


def main() -> None:
    t0 = time.time()
    args = parse_args()
    (presave if args.mode == "presave" else score)(args)
    print(f"done in {time.time() - t0:.1f} s")


if __name__ == "__main__":
    main()
