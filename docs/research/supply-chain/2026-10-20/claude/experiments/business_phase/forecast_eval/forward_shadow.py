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

  # synthetic counterexample for the zero-demand rule (no DB, no files)
  uv run python forward_shadow.py --mode selftest

  # entry-path regression: missing last target month returns labels_incomplete
  # (structured reasons, retry date) instead of exiting; no DB, temp dir only
  uv run python forward_shadow.py --mode entrytest

Scoring mother set
  The presaved `sample.skus` is the mother set. Once every target month has
  labels, a sampled SKU with no order rows is a zero-demand cell: its |forecast|
  enters the WAPE numerator, it contributes 0 to the denominator. If any target
  month lacks labels the whole window is `labels_incomplete` and every excluded
  SKU is listed with its reason (nothing disappears silently).

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
import math
import sys
import tempfile
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
    ap.add_argument("--mode", choices=["presave", "score", "selftest", "entrytest"],
                    default="presave")
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


def build_score(pre: dict, actual: dict, months_present: set,
                db_hash: str | None, presave_name: str) -> dict:
    """Score a pre-registered file on its OWN sample (M03, T14).

    The mother set is the presaved sample, never "SKUs that happen to have order
    rows in the target window". Once label coverage is complete, a sampled SKU
    with no order rows is a genuine zero-demand cell: its |forecast| enters the
    WAPE numerator and it contributes 0 to the denominator. If coverage is
    incomplete the whole window is marked unknown with explicit exclusions — a
    SKU never disappears silently.
    """
    origin = pre["origin"]
    targets = pre["target_months"]
    required = ("selected", "naive", "ma3")     # top-level comparators (kept for continuity)
    # T25: fixed candidate set reported per candidate. A cell enters the common
    # evaluable subset only if EVERY candidate has a presaved forecast there, so
    # all candidates are scored on the same (SKU, origin) cells.
    candidates = ["selected", "naive", "ma3", "ma6", "seasonal_naive",
                  "autoets", "combo_ew"]
    sample_skus = [r["sku"] for r in pre["sample"]["skus"]]
    missing_months = [t for t in targets if t not in months_present]
    excluded, included = [], {}
    if missing_months:
        excluded = [dict(sku=s, reason="missing_labels:" + ",".join(missing_months))
                    for s in sample_skus]
    else:
        for sku in sample_skus:
            fc = pre["forecasts"].get(sku)
            if not fc:
                excluded.append(dict(sku=sku, reason="missing_presaved_forecast"))
                continue
            miss = [m for m in required if m not in fc]
            if miss:
                excluded.append(dict(sku=sku, reason="incomplete_forecast:" + ",".join(miss)))
                continue
            # actual defaults to 0.0: no order rows in a fully covered window
            included[sku] = float(actual.get(sku, 0.0))
    # common evaluable subset: same cells for every candidate
    common = [sku for sku in included
              if all(c in pre["forecasts"][sku] for c in candidates)]
    unavailable = {}
    for c in candidates:
        missing_skus = [sku for sku in included if c not in pre["forecasts"][sku]]
        if missing_skus:
            unavailable[c] = dict(
                n=len(missing_skus), examples=sorted(missing_skus)[:5],
                reason=("该候选在该块不可评：预存文件缺少该 SKU 的候选预测"
                        "（例如历史过短时该候选未拟合）"))

    def cand_stats(c: str) -> dict:
        """Per-candidate metrics on the COMMON (SKU, origin) subset."""
        cells = [(float(np.sum(pre["forecasts"][sku][c])), included[sku])
                 for sku in common]
        n = len(cells)
        if n == 0:
            return dict(n_cells=0, wape_with_zero=None, wape_excluding_zero=None,
                        bias=None, upper_coverage=None, zero_count=0, zero_share=None)
        den_c = sum(a for _, a in cells)
        zero_cells = [(f, a) for f, a in cells if abs(a) < 1e-9]
        nz_cells = [(f, a) for f, a in cells if abs(a) >= 1e-9]
        den_nz = sum(a for _, a in nz_cells)
        return dict(
            n_cells=n,
            # 与零需求口径一致：零实际量单元格的 |F| 保留在分子，分母贡献 0
            wape_with_zero=(round(sum(abs(f - a) for f, a in cells) / den_c, 4)
                            if den_c > 1e-9 else None),
            # 仅非零实际量单元格（分子分母都排除）——对照口径，不替代主口径
            wape_excluding_zero=(round(sum(abs(f - a) for f, a in nz_cells) / den_nz, 4)
                                 if den_nz > 1e-9 else None),
            # Bias = Σ(F−A)/ΣA；读作方向，不读作准确率
            bias=round(sum(f - a for f, a in cells) / den_c, 4) if den_c > 1e-9 else None,
            # 上限区间覆盖率：单边上界（点预测）的实测覆盖，只作观察、不构成保证
            upper_coverage=round(sum(1 for f, a in cells if a <= f + 1e-9) / n, 4),
            zero_count=len(zero_cells),
            zero_share=round(len(zero_cells) / n, 4))

    candidate_metrics = {c: cand_stats(c) for c in candidates}
    # all candidates must share the same common-subset size by construction
    _sizes = {m["n_cells"] for m in candidate_metrics.values()}
    assert len(_sizes) <= 1, f"candidates not on one common subset: {_sizes}"
    by_sku = {sku: dict(actual=included[sku],
                        **{m: float(np.sum(pre["forecasts"][sku][m])) for m in required})
              for sku in common}
    den = sum(included[s] for s in common)
    zero = sum(1 for s in common if abs(included[s]) < 1e-9)
    # 零分母：数量与占比（占比 = 零分母格数 / 该块共同可评单元格数）
    zero_share = round(zero / len(common), 4) if common else None
    status = ("labels_incomplete" if missing_months else
              "no_common_subset" if not common else
              "undefined_denominator" if den <= 1e-9 else "scored")
    wape = {m: candidate_metrics[m]["wape_with_zero"] for m in required}
    bias = {c: candidate_metrics[c]["bias"] for c in candidates}
    bootstrap = None
    if den > 1e-9:
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
        bootstrap = dict(iterations=300,
                         **{k: dict(mean=round(float(np.mean(v)), 4),
                                    p5=round(float(np.percentile(v, 5)), 4),
                                    p95=round(float(np.percentile(v, 95)), 4))
                            for k, v in diffs.items()})
    return dict(
        schema_version="t10_forward_shadow_score/4",
        scored_at=datetime.now(timezone.utc).astimezone().isoformat(timespec="seconds"),
        presave_file=presave_name, generated_at=pre["generated_at"],
        origin=origin, target_months=targets, status=status,
        inputs=dict(db_sha256=db_hash,
                    presave_db_sha256=pre["inputs"]["db_sha256"],
                    destinations_sha256=pre["inputs"]["destinations_sha256"]),
        coverage=dict(months_present=sorted(set(targets) & set(months_present)),
                      missing_months=missing_months,
                      labels_complete=not missing_months),
        scoring_due=pre.get("scoring_due"),
        labels_needed_through=targets[-1],
        mother_set=dict(kind="presaved sample", n=len(sample_skus),
                        rule=("shadow_<origin>.json → sample.skus；不按目标窗订单记录收缩；"
                              "标签完整时无订单 = 零需求")),
        n_sample=len(sample_skus), n_scored=len(common),
        n_included=len(included), n_common=len(common),
        n_zero_demand_retained=zero,
        zero_demand_share=zero_share,
        n_excluded=len(excluded), excluded=excluded,
        unavailable_candidates=unavailable,
        common_subset_rule=("共同可评分子集 = 预存样本中 selected/naive/ma3/ma6/"
                            "seasonal_naive/autoets/combo_ew 七个候选均有预测的同一批 "
                            "(SKU, origin) 单元格；所有候选指标都在该交集上计算"),
        extra_forecasts_not_in_sample=sorted(set(pre["forecasts"]) - set(sample_skus)),
        denominator=round(den, 2), wape=wape, bias=bias,
        candidate_metrics=candidate_metrics,
        upper_coverage={c: candidate_metrics[c]["upper_coverage"] for c in candidates},
        bootstrap=bootstrap,
        metric_definition=dict(
            wape="Σ|F−A| / ΣA over the common subset (zero-demand cells retained in the numerator)",
            wape_excluding_zero="仅非零实际量单元格的 Σ|F−A| / ΣA（对照口径，不替代主口径）",
            bias="Σ(F−A) / ΣA；读作方向，不读作准确率",
            upper_coverage=("上限区间覆盖率：实际 ≤ 点预测（单边上界）的单元格占比；"
                            "只作观察，不构成保证"),
            zero_demand="零需求单元格的 |F| 进入分子，对分母贡献 0",
            zero_demand_share="零分母单元格占比 = 零分母格数 / 该块共同可评单元格数",
            denominator_zero="仅当聚合总实际量为 0 时该聚合无定义（status=undefined_denominator）",
            missing_labels="任一目标月无标签则整窗 unknown，逐 SKU 列出排除原因",
            candidates=("参与候选：selected / naive / ma3 / ma6 / seasonal_naive / "
                        "autoets / combo_ew；每候选输出 wape_with_zero / "
                        "wape_excluding_zero / bias / upper_coverage / n_cells / "
                        "zero_count / zero_share")),
        note=("一次月度结果不构成改默认的依据；区间跨 0 时只能说方向不稳定；"
              "选择结果来自预存文件，评分阶段未重新选模。"),
    )


def load_score_inputs(db: str, targets: list[str]) -> tuple[dict, set]:
    """Read-only actuals and month coverage for the target window."""
    ph = ",".join("?" * len(targets))
    con = duckdb.connect(db, read_only=True)
    try:
        rows = con.execute(f"""
            SELECT sku_tongtool, substr(despatch_date,1,7), SUM(qty)
            FROM gs_orders
            WHERE substr(despatch_date,1,7) IN ({ph})
              AND NOT regexp_matches(lower(platform_sku), '(^|[-_])test([-_]|$)')
            GROUP BY 1,2""", targets).fetchall()
        present = {r[0] for r in con.execute(f"""
            SELECT DISTINCT substr(despatch_date,1,7)
            FROM gs_orders
            WHERE substr(despatch_date,1,7) IN ({ph})
              AND NOT regexp_matches(lower(platform_sku), '(^|[-_])test([-_]|$)')""",
            targets).fetchall()}
    finally:
        con.close()
    actual = defaultdict(float)
    for sku, _ym, q in rows:
        actual[sku] += float(q)
    return actual, present


def score(args, fetch=None) -> dict:
    """Entry point for scoring. NEVER exits early on missing labels (T15).

    Missing target months are a normal outcome of the monthly job, not a crash:
    the window is scored as `labels_incomplete` with the missing months, every
    affected SKU and its reason, plus the date to retry. Only a missing
    --pred-file is an argument error.
    """
    if not args.pred_file:
        raise SystemExit("--mode score requires --pred-file shadow_YYYY-MM.json")
    path = Path(args.pred_file)
    pre = json.loads(path.read_text(encoding="utf-8"))
    origin = pre["origin"]
    targets = pre["target_months"]
    actual, present = (fetch or load_score_inputs)(args.db, targets)
    # db hash is only meaningful for the real reader; injected readers (the
    # entry regression test) pass None and build_score records it as such.
    db_hash = (hashlib.sha256(Path(args.db).read_bytes()).hexdigest()
               if fetch is None else None)

    payload = build_score(pre, actual, present, db_hash, path.name)
    out_path = Path(args.out_dir) / f"shadow_{origin}_score.json"
    out_path.write_text(json.dumps(payload, ensure_ascii=False, indent=1) + "\n",
                        encoding="utf-8")
    print(f"wrote {out_path}")
    print("status", payload["status"], "sample", payload["n_sample"],
          "scored", payload["n_scored"], "zero", payload["n_zero_demand_retained"],
          "excluded", payload["n_excluded"], "wape", payload["wape"])
    if payload["coverage"]["missing_months"]:
        print("missing_months", payload["coverage"]["missing_months"],
              "retry_after", payload["scoring_due"])
    print("bootstrap", payload["bootstrap"])
    return payload


def selftest() -> None:
    """Synthetic counterexample for M03: a presaved 15 with no order rows.

    Two SKUs: A forecast 15 / actual 0 (no order rows), B forecast 100 / actual 100.
    The zero-demand SKU must contribute 15 to the numerator:
    WAPE = (15 + 0) / 100 = 0.15. Dropping it would give 0.0.
    """
    pre = dict(origin="2026-09", target_months=["2026-10", "2026-11", "2026-12"],
               generated_at="synthetic", inputs=dict(db_sha256="x", destinations_sha256="x"),
               sample=dict(skus=[dict(sku="A"), dict(sku="B")]),
               forecasts={
                   "A": {"selected": [5, 5, 5], "naive": [5, 5, 5], "ma3": [4, 4, 4],
                         "ma6": [5, 5, 5], "seasonal_naive": [5, 5, 5],
                         "autoets": [5, 5, 5], "combo_ew": [5, 5, 5]},
                   "B": {"selected": [40, 30, 30], "naive": [40, 30, 30],
                         "ma3": [40, 30, 30], "ma6": [40, 30, 30],
                         "seasonal_naive": [40, 30, 30], "autoets": [40, 30, 30],
                         "combo_ew": [40, 30, 30]}})
    out = build_score(pre, {"B": 100.0}, set(pre["target_months"]), None, "synthetic")
    assert out["status"] == "scored"
    assert out["n_scored"] == 2 and out["n_common"] == 2
    assert out["n_zero_demand_retained"] == 1
    assert out["zero_demand_share"] == 0.5
    assert out["wape"]["selected"] == 0.15
    assert out["unavailable_candidates"] == {}
    for c in ("selected", "naive", "ma3", "ma6", "seasonal_naive",
              "autoets", "combo_ew"):
        assert c in out["candidate_metrics"], c
        m = out["candidate_metrics"][c]
        for k in ("wape_with_zero", "wape_excluding_zero", "bias", "upper_coverage"):
            assert m[k] is not None and math.isfinite(m[k]), (c, k, m[k])
        assert m["n_cells"] == 2, (c, m["n_cells"])
        assert m["zero_count"] == 1 and m["zero_share"] == 0.5
    assert set(out["candidate_metrics"]) == {
        "selected", "naive", "ma3", "ma6", "seasonal_naive", "autoets", "combo_ew"}
    assert len({m["n_cells"] for m in out["candidate_metrics"].values()}) == 1
    assert out["candidate_metrics"]["selected"]["wape_excluding_zero"] == 0.0
    assert out["bias"]["selected"] == 0.15
    assert out["upper_coverage"]["selected"] == 1.0
    excluded_variant = out["wape"]["selected"] - 15.0 / out["denominator"]
    assert abs(excluded_variant - 0.0) < 1e-12
    missing = build_score(pre, {}, set(), None, "synthetic")
    assert missing["status"] == "labels_incomplete"
    assert missing["n_excluded"] == 2 and missing["n_scored"] == 0
    assert missing["n_common"] == 0
    assert missing["zero_demand_share"] is None
    assert set(missing["candidate_metrics"]) == {
        "selected", "naive", "ma3", "ma6", "seasonal_naive", "autoets", "combo_ew"}
    assert all(m["n_cells"] == 0 for m in missing["candidate_metrics"].values())
    print(json.dumps(dict(status=out["status"], denominator=out["denominator"],
                          wape_with_zero=out["wape"]["selected"],
                          wape_excluding_zero=out["candidate_metrics"]["selected"]["wape_excluding_zero"],
                          bias_selected=out["bias"]["selected"],
                          upper_coverage_selected=out["upper_coverage"]["selected"],
                          zero_demand_retained=out["n_zero_demand_retained"],
                          zero_demand_share=out["zero_demand_share"],
                          n_common=out["n_common"],
                          candidates=sorted(out["candidate_metrics"]),
                          per_candidate={c: dict(n_cells=m["n_cells"],
                                                 wape_with_zero=m["wape_with_zero"],
                                                 bias=m["bias"],
                                                 upper_coverage=m["upper_coverage"])
                                         for c, m in out["candidate_metrics"].items()},
                          labels_incomplete_status=missing["status"]),
                     ensure_ascii=False, indent=1))


def entrytest() -> None:
    """Entry-path regression: missing last target month must NOT SystemExit.

    The old entry raised SystemExit before build_score() could report, so the
    monthly job produced no `labels_incomplete` file and no per-SKU reasons.
    This drives the real `score()` entry with an injected read-only reader
    (no DB, no network) and a temporary presave/out directory.
    """
    with tempfile.TemporaryDirectory() as td:
        pre = dict(origin="2026-09", target_months=["2026-10", "2026-11", "2026-12"],
                   scoring_due="2027-01-04", generated_at="synthetic",
                   inputs=dict(db_sha256="x", destinations_sha256="x"),
                   sample=dict(skus=[dict(sku="A"), dict(sku="B")]),
                   forecasts={
                       "A": {"selected": [5, 5, 5], "naive": [5, 5, 5],
                             "ma3": [4, 4, 4], "ma6": [5, 5, 5],
                             "seasonal_naive": [5, 5, 5], "autoets": [5, 5, 5],
                             "combo_ew": [5, 5, 5]},
                       "B": {"selected": [40, 30, 30], "naive": [40, 30, 30],
                             "ma3": [40, 30, 30], "ma6": [40, 30, 30],
                             "seasonal_naive": [40, 30, 30], "autoets": [40, 30, 30],
                             "combo_ew": [40, 30, 30]}})
        pred = Path(td) / "shadow_2026-09.json"
        pred.write_text(json.dumps(pre, ensure_ascii=False), encoding="utf-8")
        args = argparse.Namespace(pred_file=str(pred), out_dir=td, db="unused")

        # labels stop one month short of the target window
        partial = score(args, fetch=lambda _db, targets: ({}, set(targets[:-1])))
        assert partial["status"] == "labels_incomplete", partial["status"]
        assert partial["coverage"]["missing_months"] == [pre["target_months"][-1]]
        assert partial["coverage"]["labels_complete"] is False
        assert partial["n_scored"] == 0
        assert partial["n_excluded"] == 2
        assert all(e["reason"].startswith("missing_labels:")
                   for e in partial["excluded"])
        assert partial["scoring_due"] == "2027-01-04"
        assert partial["wape"] == {m: None for m in ("selected", "naive", "ma3")}
        assert partial["zero_demand_share"] is None
        assert partial["n_common"] == 0
        assert all(m["n_cells"] == 0 for m in partial["candidate_metrics"].values())
        # the same entry still scores normally once labels are complete
        complete = score(args, fetch=lambda _db, targets: ({"B": 100.0}, set(targets)))
        assert complete["status"] == "scored", complete["status"]
        assert complete["wape"]["selected"] == 0.15
        assert complete["coverage"]["labels_complete"] is True
        assert complete["zero_demand_share"] == 0.5
        assert complete["n_common"] == 2
        for c, m in complete["candidate_metrics"].items():
            for k in ("wape_with_zero", "wape_excluding_zero", "bias", "upper_coverage"):
                assert m[k] is not None and math.isfinite(m[k]), (c, k, m[k])
            assert m["n_cells"] == 2
    print(json.dumps(dict(
        entry_missing_last_month=partial["status"],
        missing_months=partial["coverage"]["missing_months"],
        excluded=partial["n_excluded"],
        per_sku_reasons=sorted({e["reason"] for e in partial["excluded"]}),
        retry_after=partial["scoring_due"],
        entry_complete_labels=complete["status"],
        wape_when_complete=complete["wape"]["selected"],
        bias_when_complete=complete["bias"]["selected"],
        upper_coverage_when_complete=complete["upper_coverage"]["selected"],
        zero_demand_share=complete["zero_demand_share"],
        n_common=complete["n_common"],
        candidates=sorted(complete["candidate_metrics"]),
        per_candidate_n={c: m["n_cells"] for c, m in complete["candidate_metrics"].items()},
    ), ensure_ascii=False, indent=1))


def main() -> None:
    t0 = time.time()
    args = parse_args()
    if args.mode == "selftest":
        selftest()
        return
    if args.mode == "entrytest":
        entrytest()
        return
    (presave if args.mode == "presave" else score)(args)
    print(f"done in {time.time() - t0:.1f} s")


if __name__ == "__main__":
    main()
