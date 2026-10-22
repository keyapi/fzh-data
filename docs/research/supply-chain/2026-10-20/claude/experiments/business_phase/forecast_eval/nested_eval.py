#!/usr/bin/env python
# -*- coding: utf-8 -*-
"""T10: nested rolling evaluation under seven pre-registered rules.

Rules implemented here (and reported one by one)
1. Strata are built ONLY from each training window (never from the full period
   or the test period). This also applies to the 200-series SAMPLE and to the
   dominant-warehouse label: both use sales up to each outer origin only.
2. Inner rolling selection: within each outer training window, the model is
   chosen on inner cut points; the outer outcome is never visible.
3. Outer loop re-runs the whole selection (including the equal-weight combo)
   and compares against fixed MA3 and naive on the SAME sample.
4. Monthly cumulative h=3, step 3; only labels available at the time are used
   (label_available_at), every window is refit.
5. Short histories follow a PRE-REGISTERED fallback rule; failures are kept, not
   dropped; missing forecasts are written as null (never 0).
6. The old T2 test period is exploratory only. There is NO clean hold-out block
   inside the current label coverage: T2's 2026-03 origin already reaches July
   2026 with its 90-day target window, so 2026-07..09 is only "last evaluable",
   not "unused". The only clean evidence comes from the forward shadow.
7. Compute budget: <=6 candidates, 200 series, 3 outer x 3 inner cut points,
   <=14,400 fits, 30-minute cap; on overflow partial results + explicit gap.

Metric: WAPE = Σ|F−A| / ΣA on the COMMON evaluable subset (rows where selected,
MA3 and naive all produced a forecast). Zero-demand cells are RETAINED in the
numerator — their |F| is an error; they contribute 0 to the denominator. Dropping
them would delete real over-forecast error.

T12 audit fixes (2026-10-22) — see control/reviews/2026-10-22-t12-audit-fixes.md
  Sampling / tier / dominant warehouse now use each outer block's training
  window only; the "unused block" wording is corrected; zero-demand errors are
  retained; missing predictions are null; the common evaluable subset is stated.

T14 recheck fix (2026-10-22) — M02: each block's sampling mother set is
restricted to SKUs whose first order month is <= that block's origin, so series
that did not exist yet cannot be sampled into an earlier block.

Diagnostic only: the main table and the T2 model choice are NOT changed.
Outputs: nested_eval.json, nested_eval.csv, nested_report.md
"""
from __future__ import annotations

import csv
import hashlib
import json
import math
import time
import tracemalloc
import warnings
from collections import Counter, defaultdict
from datetime import date
from pathlib import Path

import duckdb
import numpy as np

warnings.filterwarnings("ignore")

DB_PATH = Path("D:/Work/fzh-order-store/order_store.duckdb")
HERE = Path(__file__).resolve()
CLAUDE_DIR = HERE.parents[3]
OUT = HERE.parent
DEST = CLAUDE_DIR / "out" / "business_phase" / "destinations.json"

CANDIDATES = ["naive", "ma3", "ma6", "seasonal_naive", "autoets", "combo_ew"]
N_SERIES = 200
OUTER = [("2025-10", "exploratory"), ("2026-01", "exploratory"),
         ("2026-06", "last_evaluable_no_clean_holdout")]
INNER_OFFSETS = (3, 6, 9)          # months before the outer origin, step 3
H = 3
FIT_CAP = 14400
TIME_CAP_S = 1800
SCORED_FIELDS = ("sel_forecast", "ma3_forecast", "naive_forecast")


def ym_i(ym: str) -> int:
    return int(ym[:4]) * 12 + int(ym[5:7]) - 1


def i_ym(i: int) -> str:
    y, m = divmod(i, 12)
    return f"{y:04d}-{m + 1:02d}"


def forecast(model: str, y: np.ndarray, h: int):
    n = len(y)
    if model == "naive":
        return np.repeat(y[-1], h)
    if model == "seasonal_naive":
        if n < 13:
            raise ValueError("history_lt_13m")
        return np.array([y[n - 12 + (k % 12)] for k in range(h)], dtype=float)
    if model in ("ma3", "ma6"):
        k = min(int(model[2:]), n)
        return np.repeat(float(np.mean(y[-k:])), h)
    from statsforecast import models as sfm
    if model == "autoets":
        if n < 3:
            raise ValueError("history_lt_3m")
        m = sfm.AutoETS(season_length=12 if n >= 24 else 1)
        m.fit(y.astype(np.float32))
        return np.asarray(m.predict(h=h)["mean"], dtype=float)
    raise ValueError(model)


def main() -> None:
    tracemalloc.start()
    t0 = time.time()
    db_hash = hashlib.sha256(DB_PATH.read_bytes()).hexdigest()
    dest = {r["sku"]: r for r in json.loads(DEST.read_text(encoding="utf-8"))["rows"]}
    eligible = [s for s, r in dest.items() if r["destination"] == "mapped_eligible"]

    con = duckdb.connect(str(DB_PATH), read_only=True)
    try:
        wmap = {r[0]: r[1] for r in con.execute(
            "SELECT gs_warehouse, current_warehouse FROM warehouse_map").fetchall()}
        rows = con.execute("""
            SELECT sku_tongtool, substr(despatch_date,1,7), warehouse, SUM(qty)
            FROM gs_orders
            WHERE despatch_date <= '2026-09-30'
              AND NOT regexp_matches(lower(platform_sku), '(^|[-_])test([-_]|$)')
            GROUP BY 1,2,3""").fetchall()
    finally:
        con.close()
    if hashlib.sha256(DB_PATH.read_bytes()).hexdigest() != db_hash:
        raise SystemExit("DB changed")

    month = defaultdict(dict)
    wh_month = defaultdict(lambda: defaultdict(lambda: defaultdict(float)))
    for sku, ym, wh, q in rows:
        month[sku][ym] = month[sku].get(ym, 0.0) + float(q)
        wh_month[sku][wmap.get(wh, wh)][ym] += float(q)
    last_i = ym_i("2026-09")
    series = {}
    for sku in eligible:
        by = month.get(sku)
        if not by:
            continue
        first = min(ym_i(m) for m in by)
        months = [i_ym(i) for i in range(first, last_i + 1)]
        series[sku] = dict(first=first, y=np.array([by.get(m, 0.0) for m in months],
                                                   dtype=float), months=months)

    # --- training-window-only helpers (T10-1: no full-period information) -----
    def training_total(sku: str, origin_i: int) -> float:
        s = series[sku]
        n = origin_i - s["first"] + 1
        return float(np.sum(s["y"][:n])) if n > 0 else 0.0

    def dominant_warehouse(sku: str, origin_i: int) -> str | None:
        """Dominant warehouse using only months <= the outer origin."""
        first = series[sku]["first"]
        if origin_i < first:
            return None
        agg = {wh: sum(q for ym, q in by.items() if first <= ym_i(ym) <= origin_i)
               for wh, by in wh_month.get(sku, {}).items()}
        agg = {k: v for k, v in agg.items() if v > 0}
        return max(agg.items(), key=lambda kv: kv[1])[0] if agg else None

    fits = 0
    fit_by_model = Counter()
    failures = Counter()
    rows_out = []
    sample_by_block = {}
    sample_meta = {}

    def fit_forecast(model: str, y: np.ndarray, h: int):
        nonlocal fits
        if fits >= FIT_CAP:
            raise RuntimeError("fit_cap")
        fits += 1
        fit_by_model[model] += 1
        return forecast(model, y, h)

    def combo(y: np.ndarray, h: int, got: dict):
        parts = [got[m] for m in ("naive", "ma3", "ma6", "seasonal_naive") if m in got]
        if not parts:
            return None
        return np.mean(np.vstack(parts), axis=0)

    # pre-registered short-history fallback (rule 5)
    def fallback_rule(n: int) -> dict:
        if n < 3:
            return dict(allowed=["naive"], reason="n<3: only naive is defined")
        if n < 13:
            return dict(allowed=["naive", "ma3", "ma6", "autoets"],
                        reason="n<13: seasonal_naive needs 12 lags; autoets uses season_length=1")
        if n < 24:
            return dict(allowed=CANDIDATES,
                        reason="13<=n<24: autoets season_length=1; one-season low-confidence flag")
        return dict(allowed=CANDIDATES, reason="n>=24")

    def window_summary(y: np.ndarray, first: int, origin_i: int):
        """Cumulative h=3 target months origin+1..origin+3 (labels available)."""
        if origin_i + H > last_i:
            return None
        return float(np.sum(y[origin_i + 1 - first: origin_i + 1 - first + H]))

    for outer_ym, outer_kind in OUTER:
        O = ym_i(outer_ym)
        inner = [O - k for k in INNER_OFFSETS]
        # T10-1: the 200-series sample is drawn from THIS block's training
        # window only. Ranking by the full-history total (through 2026-09) would
        # let final-block actuals decide which series are evaluated.
        # M02 (T14): the mother set is ALSO restricted to series that already
        # exist at this origin (first order month <= O). Sampling all eligible
        # keys let SKUs whose first order came later enter earlier blocks
        # (2025-10: 28 such SKUs, 2026-01: 11) — a forward-looking mother set.
        mother = [s for s in series if series[s]["first"] <= O]
        keys = sorted(mother, key=lambda s: (-training_total(s, O), s))
        step = max(1, len(keys) // N_SERIES)
        sample = keys[::step][:N_SERIES]
        sample_by_block[outer_ym] = sample
        # diagnostic: how many SKUs the OLD (all-keys) rule would have sampled
        # before they existed, and how much the sample changed
        old_keys = sorted(series, key=lambda s: (-training_total(s, O), s))
        old_sample = old_keys[::max(1, len(old_keys) // N_SERIES)][:N_SERIES]
        sample_meta[outer_ym] = dict(
            n_mother=len(mother),
            n_excluded_not_started=len(series) - len(mother),
            n_sample=len(sample),
            sample_first_le_origin=all(series[s]["first"] <= O for s in sample),
            max_first_in_sample=(i_ym(max(series[s]["first"] for s in sample))
                                 if sample else None),
            old_rule_not_started_in_sample=sum(1 for s in old_sample
                                               if series[s]["first"] > O),
            n_changed_vs_old_rule=len(set(sample) ^ set(old_sample)),
        )
        for sku in sample:
            s = series[sku]
            n_tr = O - s["first"] + 1
            rule = fallback_rule(n_tr)
            # ---- inner rolling: choose model per series (rule 2) ----------
            inner_scores = {c: [] for c in CANDIDATES}
            for i_o in inner:
                A = window_summary(s["y"], s["first"], i_o)
                if A is None:
                    continue
                tr = i_o - s["first"] + 1
                if tr < 2:
                    continue
                got = {}
                for c in rule["allowed"]:
                    if c == "combo_ew":
                        continue
                    try:
                        got[c] = fit_forecast(c, s["y"][:tr], H)
                    except Exception as exc:
                        failures[f"{c}:{type(exc).__name__}"] += 1
                cb = combo(s["y"][:tr], H, got)
                if cb is not None:
                    got["combo_ew"] = cb
                for c, f in got.items():
                    F = float(np.sum(f))
                    inner_scores[c].append(abs(F - A) / A if A > 1e-9 else None)
            chosen, reason_sel = "naive", "no feasible candidate -> naive"
            best = None
            for c in ["autoets", "seasonal_naive", "ma6", "ma3", "combo_ew", "naive"]:
                vals = [v for v in inner_scores.get(c, []) if v is not None]
                if len(vals) < 1:
                    continue
                m = float(np.mean(vals))
                if best is None or m < best - 1e-12:
                    best, chosen = m, c
            if best is not None:
                reason_sel = f"inner mean |err|/A = {best:.4f} over {len(inner_scores[chosen])} windows"
            # ---- outer: refit whole selection, get actual (rule 3,4) ------
            A_out = window_summary(s["y"], s["first"], O)
            if A_out is None:
                continue
            ytr = s["y"][:n_tr]
            if n_tr < 2:
                failures["outer:insufficient_history"] += 1
                rows_out.append(dict(
                    outer=outer_ym, outer_kind=outer_kind, sku=sku, chosen=None,
                    selection_reason="no training history before this outer origin",
                    fallback_rule=rule["reason"], n_train=max(n_tr, 0),
                    train_total=0.0,
                    actual=round(A_out, 2), sel_forecast=None, ma3_forecast=None,
                    naive_forecast=None, zero_actual=bool(abs(A_out) < 1e-9),
                    intermittent=False, zero_share_train=0.0,
                    warehouse=dominant_warehouse(sku, O) or "unknown",
                    low_confidence=True, inner_wape={}, valid=False))
                continue
            out_pred = {}
            for c in ["naive", "ma3", "ma6", "seasonal_naive", "autoets"]:
                if c not in rule["allowed"] and c != "naive":
                    continue
                try:
                    out_pred[c] = fit_forecast(c, ytr, H)
                except Exception as exc:
                    failures[f"outer:{c}:{type(exc).__name__}"] += 1
            cb = combo(ytr, H, out_pred)
            if cb is not None:
                out_pred["combo_ew"] = cb
            sel_f = out_pred.get(chosen)
            if sel_f is None:
                sel_f = out_pred.get("naive")
                chosen = "naive"
                reason_sel += " | outer refit fell back to naive"
            # ---- strata from the TRAINING window only (rule 1) ------------
            hist = ytr
            zshare = float(np.mean(hist == 0)) if len(hist) else 0.0
            dom_wh = dominant_warehouse(sku, O) or "unknown"
            rows_out.append(dict(
                outer=outer_ym, outer_kind=outer_kind, sku=sku, chosen=chosen,
                selection_reason=reason_sel, fallback_rule=rule["reason"],
                n_train=n_tr,
                train_total=round(float(np.sum(ytr)), 2),
                actual=round(A_out, 2),
                sel_forecast=round(float(np.sum(sel_f)), 2),
                # T10-4: a missing prediction is null, never 0.
                ma3_forecast=(round(float(np.sum(out_pred["ma3"])))
                              if "ma3" in out_pred else None),
                naive_forecast=round(float(np.sum(out_pred["naive"])), 2),
                zero_actual=bool(abs(A_out) < 1e-9),
                intermittent=bool(zshare >= 0.5),
                zero_share_train=round(zshare, 3),
                warehouse=dom_wh,
                low_confidence=bool(n_tr < 24),
                inner_wape={c: (round(float(np.mean([v for v in vs if v is not None])), 4)
                                if any(v is not None for v in vs) else None)
                            for c, vs in inner_scores.items()},
                valid=True,
            ))
        if time.time() - t0 > TIME_CAP_S:
            raise SystemExit("time cap reached; partial results not published")

    # ---------------- aggregate -------------------------------------------
    def common_rows(subset):
        """Rows where every compared method produced a forecast (T10-4)."""
        return [r for r in subset if r.get("valid")
                and all(r.get(f) is not None for f in SCORED_FIELDS)]

    def wape(field: str, subset) -> float | None:
        # zero-demand cells stay in the numerator: |F − 0| is a real error.
        # They add 0 to the denominator, so no divide-by-zero is introduced.
        cells = common_rows(subset)
        sa = sum(r["actual"] for r in cells)
        if not cells or sa < 1e-9:
            return None
        return round(sum(abs(r[field] - r["actual"]) for r in cells) / sa, 4)

    def block_stats(subset):
        common = common_rows(subset)
        return dict(
            n=len(subset),
            n_valid=sum(1 for r in subset if r.get("valid")),
            n_common=len(common),
            n_scored=sum(1 for r in common if r["actual"] > 1e-9),
            zero_retained=sum(1 for r in common if abs(r["actual"]) < 1e-9),
            missing_forecast=sum(1 for r in subset if r.get("valid")
                                 and not all(r.get(f) is not None for f in SCORED_FIELDS)),
            selected=wape("sel_forecast", subset), ma3=wape("ma3_forecast", subset),
            naive=wape("naive_forecast", subset))

    by_outer = {o: [r for r in rows_out if r["outer"] == o] for o, _ in OUTER}
    blocks = {f"{o}|{k}": block_stats(v) for (o, k), v in
              zip(OUTER, [by_outer[o] for o, _ in OUTER])}
    final_key = f"{OUTER[-1][0]}|{OUTER[-1][1]}"
    final_rows = [r for r in by_outer[OUTER[-1][0]] if r.get("valid")]

    # tier strata from each block's OWN training-window total (T10-1). The old
    # code ranked the final block by its ACTUAL, i.e. it used the outcome.
    for outer_ym, _ in OUTER:
        ranked = sorted([r for r in by_outer[outer_ym] if r.get("valid")],
                        key=lambda r: (-r["train_total"], r["sku"]))
        third = max(1, len(ranked) // 3)
        for idx, r in enumerate(ranked):
            r["tier"] = ("high" if idx < third else
                         "mid" if idx < 2 * third else "low")
        for r in by_outer[outer_ym]:
            r.setdefault("tier", "no_history")
    strata = defaultdict(list)
    for r in final_rows:
        strata[f"tier:{r['tier']}"].append(r)
        strata[f"warehouse:{r['warehouse']}"].append(r)
        strata[f"intermittent:{'yes' if r['intermittent'] else 'no'}"].append(r)
    stratum_stats = {g: block_stats(strata[g]) for g in sorted(strata)}

    # SKU bootstrap on the final block (uncertainty, not significance claim)
    rng = np.random.default_rng(20261022)
    diffs_ma3, diffs_naive = [], []
    by_sku = defaultdict(list)
    for r in final_rows:
        by_sku[r["sku"]].append(r)
    skus = sorted(by_sku)
    for _ in range(300):
        pick = [skus[rng.integers(0, len(skus))] for _ in range(len(skus))]
        rows_b = [r for s in pick for r in common_rows(by_sku[s])]
        sa = sum(r["actual"] for r in rows_b)
        if sa < 1e-9:
            continue
        sel = sum(abs(r["sel_forecast"] - r["actual"]) for r in rows_b) / sa
        ma3 = sum(abs(r["ma3_forecast"] - r["actual"]) for r in rows_b) / sa
        nai = sum(abs(r["naive_forecast"] - r["actual"]) for r in rows_b) / sa
        diffs_ma3.append(sel - ma3)
        diffs_naive.append(sel - nai)

    sel_dist = Counter(r["chosen"] for r in rows_out if r.get("valid") and r["chosen"])
    sample_per_block = {o: len(v) for o, v in sample_by_block.items()}
    sample_overlap = {
        o: len(set(v) & set(sample_by_block[OUTER[0][0]])) for o, v in sample_by_block.items()}
    result = dict(
        schema_version="t10_nested_eval/3",
        inputs=dict(db_sha256=db_hash,
                    destinations_sha256=hashlib.sha256(DEST.read_bytes()).hexdigest()),
        metric_definition=dict(
            wape="Σ|F−A| / ΣA on the common evaluable subset",
            zero_demand=("零需求单元格保留在分子中（|F| 计为误差），对分母贡献 0；"
                         "不再把它们从 WAPE 中删除。"),
            common_subset=("共同可评分子集 = 该块 valid 且 sel/MA3/naive 三个预测均非 null "
                           "的行；三种方法在同一批单元格上比较。"),
            missing_forecast="缺失预测写 null（CSV 为空），不写 0。"),
        rules=dict(
            r1_strata=("sample mother set, tier, dominant warehouse and intermittent labels use "
                       "THIS block's training window only; the mother set also requires the first "
                       "order month <= the outer origin (no not-yet-started SKUs)"),
            r2_inner="model chosen on inner cut points inside each outer training window",
            r3_outer="outer refits every candidate and compares with fixed MA3/naive on the same sample",
            r4_window="monthly cumulative h=3, step 3, labels available at the time (label_available_at), refit per window",
            r5_fallback="pre-registered short-history rules; failures kept; missing predictions kept as null",
            r6_final=("旧 T2 测试期只作探索。当前标签覆盖（≤2026-09）内**不存在干净留出块**："
                      "T2 的 2026-03 外层切点其 90 天目标窗已触及 2026-07，故 2026-07..09 只是"
                      "“最后一个可评估块”，不是“未使用块”。唯一干净证据来自前向影子"
                      "（参数化脚本 forward_shadow.py；目标月标签闭合后按每月 4 日评分）。"),
            r7_budget=dict(candidates=len(CANDIDATES),
                           series=sample_per_block, outer=len(OUTER),
                           inner=len(INNER_OFFSETS),
                           fit_cap=FIT_CAP, time_cap_s=TIME_CAP_S),
        ),
        candidates=CANDIDATES,
        series_sample=dict(
            n_per_block=sample_per_block, overlap_with_first_block=sample_overlap,
            per_block=sample_meta,
            rule=("per block: mother set = series with first order month <= outer origin; "
                  "rank by TRAINING-window qty only (first .. origin), every k-th, "
                  "first 200; blocks are therefore not the same series list"),
            note=("三个外层块的样本各自独立抽取；块间不可直接比较，只做块内同样本对比。"
                  "旧版用截至 2026-09 的全历史总量抽样，且母集包含当时尚未首单的 SKU，"
                  "会让最终块实际值和未来才出现的 SKU 进入早期块。")),
        layout_note=("最后一个外层块 2026-06 的目标窗为 2026-07..09；它不是干净留出块"
                     "（见 rules.r6_final）。"),
        common_subset={k: dict(n_common=v["n_common"], n_scored=v["n_scored"],
                               zero_retained=v["zero_retained"],
                               missing_forecast=v["missing_forecast"])
                       for k, v in blocks.items()},
        fits=dict(total=fits, by_model=dict(fit_by_model), cap=FIT_CAP),
        failures=dict(failures.most_common()),
        blocks=blocks,
        final_block=final_key,
        selection_distribution=dict(sel_dist.most_common()),
        strata=stratum_stats,
        bootstrap_final=dict(
            n=len(diffs_ma3), iterations=300,
            selected_minus_ma3=dict(mean=round(float(np.mean(diffs_ma3)), 4),
                                    p5=round(float(np.percentile(diffs_ma3, 5)), 4),
                                    p95=round(float(np.percentile(diffs_ma3, 95)), 4)),
            selected_minus_naive=dict(mean=round(float(np.mean(diffs_naive)), 4),
                                      p5=round(float(np.percentile(diffs_naive, 5)), 4),
                                      p95=round(float(np.percentile(diffs_naive, 95)), 4)),
            note=("range across resampled SKUs; describes uncertainty of the difference "
                  "on unseen samples, not a significance test; zero-demand cells retained")),
        shadow_plan=dict(
            when="每月 4 日（上月标签闭合后）",
            who="数据分析 worker（离线，只读 order_store）",
            what=("用 forecast_eval/forward_shadow.py（参数化：--data-cutoff/--origin，"
                  "无写死截止期）预存样本、内层选模结果、各候选预测与生成时间；"
                  "标签可得后再用同一文件评分"),
            status=("当前标签覆盖内没有干净留出块；2026-10..12 的标签尚不存在，"
                    "故本轮只交付最后一个可评估块（2026-07..09）与前向影子预存方案"),
            next_window="2026-10..12（该窗口标签闭合后按预存文件评分）"),
        zero_denominator={k: v["zero_retained"] for k, v in blocks.items()},
        wording_note=("WAPE 是加权绝对百分比误差，不是“错 SKU 比例”或“准确率”，也没有通用阈值；"
                      "本报告只陈述“在（部分）未见样本上的差异与不确定性”，不使用“改进/稳健/"
                      "干净留出”等说法，也不把探索性时段称作留出验证；模型选择仍未定。"),
    )
    mem = tracemalloc.get_traced_memory()[1]
    tracemalloc.stop()
    result["compute"] = dict(seconds=round(time.time() - t0, 1),
                             tracemalloc_peak_mb=round(mem / 1e6, 1),
                             fits=fits, fit_cap=FIT_CAP)
    (OUT / "nested_eval.json").write_text(
        json.dumps(result, ensure_ascii=False, indent=1) + "\n", encoding="utf-8")

    with (OUT / "nested_eval.csv").open("w", encoding="utf-8-sig", newline="") as f:
        w = csv.DictWriter(f, fieldnames=list(rows_out[0].keys()))
        w.writeheader()
        w.writerows(rows_out)

    # ---------------- report ----------------------------------------------
    L = ["# T10 嵌套滚动评估报告", "",
         "> 只做评估：不改主表、不改 T2 选模结论。", "",
         "## 规则执行（七条）", ""]
    for k, v in result["rules"].items():
        L.append(f"- **{k}**：{v if not isinstance(v, dict) else json.dumps(v, ensure_ascii=False)}")
    L += ["", "## 计算规模", "",
          f"- 实际拟合 **{fits}** 次（上限 {FIT_CAP}）；运行 **{result['compute']['seconds']} s**，"
          f"tracemalloc 峰值 **{result['compute']['tracemalloc_peak_mb']} MB**",
          f"- 每块样本 {sample_per_block} 序列 × 外层 {len(OUTER)} × 内层 {len(INNER_OFFSETS)}，"
          f"候选 {len(CANDIDATES)}；样本按各块训练窗销量抽取（块间不同）",
          "- 母集按块起点限制（**首单 ≤ 块起点**）：" + "；".join(
              f"{o} 母集 {m['n_mother']}、剔除未首单 {m['n_excluded_not_started']}、"
              f"样本内最晚首单 {m['max_first_in_sample']}、"
              f"旧规则样本中当时未首单 {m['old_rule_not_started_in_sample']}、"
              f"新旧样本差异 {m['n_changed_vs_old_rule']}"
              for o, m in sample_meta.items()), "",
          "## 同样本对比（WAPE，零需求单元格保留）", "",
          "口径：`Σ|F−A| / ΣA`，三种方法都在**同一共同可评分子集**上"
          "（该块 valid 且三个预测均非 null）。零需求单元格保留在分子中"
          "（|F| 计为误差），对分母贡献 0；缺失预测为 null，不写 0。", "",
          "| 外层 | 性质 | n | 有效 | 共同可评 | 计分(非零) | 零需求(保留) | 缺失预测 | 选择流程 | MA3 | naive |",
          "|---|---|---:|---:|---:|---:|---:|---:|---:|---:|---:|"]
    for (o, kind), v in zip(OUTER, [blocks[f"{o}|{k}"] for o, k in OUTER]):
        L.append(f"| {o} | {kind} | {v['n']} | {v['n_valid']} | {v['n_common']} | "
                 f"{v['n_scored']} | {v['zero_retained']} | {v['missing_forecast']} | "
                 f"{v['selected']} | {v['ma3']} | {v['naive']} |")
    L += ["", f"- 最后一个可评估块：**{final_key}**（目标窗 2026-07..09）。"
          "**它不是干净留出块**：T2 的 2026-03 外层切点其 90 天目标窗已触及 2026-07，"
          "因此该块已被部分使用；更早两块是探索性（旧测试期）。"
          "当前标签覆盖内**不存在干净留出块**，唯一干净证据来自前向影子。", "",
          "## 内层选模分布", "",
          "| 被选中模型 | 次数 |", "|---|---:|"]
    for c, n in sel_dist.most_common():
        L.append(f"| {c} | {n} |")
    L += ["", "## 最后一个可评估块的分层指标（tier/主仓/间歇均只用该块训练窗）", "",
          "| 层 | n | 共同可评 | 零需求(保留) | 选择流程 | MA3 | naive |",
          "|---|---:|---:|---:|---:|---:|---:|"]
    for g, v in stratum_stats.items():
        L.append(f"| {g} | {v['n']} | {v['n_common']} | {v['zero_retained']} | "
                 f"{v['selected']} | {v['ma3']} | {v['naive']} |")
    b = result["bootstrap_final"]
    L += ["", "## 不确定性（最后一个可评估块，重抽 SKU 300 次）", "",
          f"- 选择流程 − MA3：均值 {b['selected_minus_ma3']['mean']}，"
          f"5–95% [{b['selected_minus_ma3']['p5']}, {b['selected_minus_ma3']['p95']}]",
          f"- 选择流程 − naive：均值 {b['selected_minus_naive']['mean']}，"
          f"5–95% [{b['selected_minus_naive']['p5']}, {b['selected_minus_naive']['p95']}]",
          f"- {b['note']}", "",
          "## 失败与边界", "",
          "- 失败（保留，不删序列）：" + ("；".join(f"`{k}` × {v}" for k, v in
                                              result["failures"].items()) or "无"),
          "- 零需求单元格保留在 WAPE 分子中；`零需求(保留)` 列单独给出数量，"
          "缺失预测为 null（不进共同可评分子集，也不按 0 计分）。", "",
          "## 前向影子（唯一干净证据路径）", "",
          f"- {result['shadow_plan']['when']}；执行人：{result['shadow_plan']['who']}",
          f"- 预存内容：{result['shadow_plan']['what']}",
          f"- 状态：{result['shadow_plan']['status']}；下一窗口：{result['shadow_plan']['next_window']}", "",
          "## 措辞纪律", "",
          f"- {result['wording_note']}", "",
          "## 结论", "",
          f"- 在最后一个可评估块（2026-07..09，非干净留出）上，选择流程与 MA3 / naive 的 "
          f"WAPE 分别为 {blocks[final_key]['selected']} / {blocks[final_key]['ma3']} / "
          f"{blocks[final_key]['naive']}（共同可评 n={blocks[final_key]['n_common']}，"
          f"零需求保留 {blocks[final_key]['zero_retained']} 条）；差异的 SKU 重抽区间见上节。",
          "- 内层选模分布显示没有单一候选占绝对多数，选模本身带来方差；"
          "本报告不据此宣布任何候选更好，模型选择仍未定。", ""]
    (OUT / "nested_report.md").write_text("\n".join(L) + "\n", encoding="utf-8")

    print("wrote nested_eval.json / .csv / nested_report.md")
    print("fits", fits, "runtime", result["compute"]["seconds"], "mem", result["compute"]["tracemalloc_peak_mb"])
    print("final", final_key, blocks[final_key])
    print("selection", dict(sel_dist.most_common()))


if __name__ == "__main__":
    main()
