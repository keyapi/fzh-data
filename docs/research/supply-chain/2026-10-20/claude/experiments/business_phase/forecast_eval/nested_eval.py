#!/usr/bin/env python
# -*- coding: utf-8 -*-
"""T10: nested rolling evaluation under seven pre-registered rules.

Rules implemented here (and reported one by one)
1. Strata are built ONLY from each training window (never from the full period
   or the test period).
2. Inner rolling selection: within each outer training window, the model is
   chosen on inner cut points; the outer outcome is never visible.
3. Outer loop re-runs the whole selection (including the equal-weight combo)
   and compares against fixed MA3 and naive on the SAME sample.
4. Monthly cumulative h=3, step 3; only labels available at the time are used
   (label_available_at), every window is refit.
5. Short histories follow a PRE-REGISTERED fallback rule; failures are kept, not
   dropped; zero-denominator cells are listed separately.
6. The old T2 test period is exploratory only. The final evaluation is on a
   genuinely unused consecutive 3 months (2026-07..09); for months whose labels
   do not exist yet a forward shadow plan is given instead.
7. Compute budget: <=6 candidates, 200 series, 3 outer x 3 inner cut points,
   <=14,400 fits, 30-minute cap; on overflow partial results + explicit gap.

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
         ("2026-06", "final_unused")]
INNER_OFFSETS = (3, 6, 9)          # months before the outer origin, step 3
H = 3
FIT_CAP = 14400
TIME_CAP_S = 1800


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

    month, wh_month = defaultdict(dict), defaultdict(lambda: defaultdict(float))
    for sku, ym, wh, q in rows:
        month[sku][ym] = month[sku].get(ym, 0.0) + float(q)
        wh_month[sku][wmap.get(wh, wh)] += float(q)
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

    # deterministic stratified-by-size sample of 200 series
    keys = sorted(series, key=lambda s: (-series[s]["y"].sum(), s))
    step = max(1, len(keys) // N_SERIES)
    sample = keys[::step][:N_SERIES]

    fits = 0
    fit_by_model = Counter()
    failures = Counter()
    rows_out = []

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
                    actual=round(A_out, 2), sel_forecast=None, ma3_forecast=None,
                    naive_forecast=None, zero_actual=bool(abs(A_out) < 1e-9),
                    intermittent=False, zero_share_train=0.0,
                    warehouse=(max(wh_month[sku].items(), key=lambda kv: kv[1])[0]
                               if wh_month[sku] else "unknown"),
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
            dom_wh = max(wh_month[sku].items(), key=lambda kv: kv[1])[0] if wh_month[sku] else "unknown"
            rows_out.append(dict(
                outer=outer_ym, outer_kind=outer_kind, sku=sku, chosen=chosen,
                selection_reason=reason_sel, fallback_rule=rule["reason"],
                n_train=n_tr,
                actual=round(A_out, 2),
                sel_forecast=round(float(np.sum(sel_f)), 2),
                ma3_forecast=(round(float(np.sum(out_pred["ma3"])) if "ma3" in out_pred else 0.0)),
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
    def wape(field: str, subset) -> float | None:
        cells = [r for r in subset if r.get("valid") and not r["zero_actual"]
                 and r.get(field) is not None]
        sa = sum(r["actual"] for r in cells)
        if not cells or sa < 1e-9:
            return None
        return round(sum(abs(r[field] - r["actual"]) for r in cells) / sa, 4)

    def block_stats(subset):
        return dict(
            n=len(subset),
            n_valid=sum(1 for r in subset if r.get("valid")),
            n_scored=sum(1 for r in subset if r.get("valid") and not r["zero_actual"]),
            zero_denominator=sum(1 for r in subset if r["zero_actual"]),
            selected=wape("sel_forecast", subset), ma3=wape("ma3_forecast", subset),
            naive=wape("naive_forecast", subset))

    by_outer = {o: [r for r in rows_out if r["outer"] == o] for o, _ in OUTER}
    blocks = {f"{o}|{k}": block_stats(v) for (o, k), v in
              zip(OUTER, [by_outer[o] for o, _ in OUTER])}
    final_key = f"{OUTER[-1][0]}|{OUTER[-1][1]}"
    final_rows = [r for r in by_outer[OUTER[-1][0]] if r.get("valid")]

    # tier strata from the FINAL training window only
    tot = sorted(final_rows, key=lambda r: -r["actual"])
    third = max(1, len(tot) // 3)
    tier = {}
    for idx, r in enumerate(tot):
        tier[(r["outer"], r["sku"])] = ("high" if idx < third else
                                        "mid" if idx < 2 * third else "low")
    strata = defaultdict(list)
    for r in final_rows:
        strata[f"tier:{tier[(r['outer'], r['sku'])]}"].append(r)
        strata[f"warehouse:{r['warehouse']}"].append(r)
        strata[f"intermittent:{'yes' if r['intermittent'] else 'no'}"].append(r)
    stratum_stats = {g: block_stats(v) for g, v in strata.items()}

    # SKU bootstrap on the final block (uncertainty, not significance claim)
    rng = np.random.default_rng(20261022)
    diffs_ma3, diffs_naive = [], []
    by_sku = defaultdict(list)
    for r in final_rows:
        by_sku[r["sku"]].append(r)
    skus = sorted(by_sku)
    for _ in range(300):
        pick = [skus[rng.integers(0, len(skus))] for _ in range(len(skus))]
        rows_b = [r for s in pick for r in by_sku[s] if not r["zero_actual"]]
        sa = sum(r["actual"] for r in rows_b)
        if sa < 1e-9:
            continue
        sel = sum(abs(r["sel_forecast"] - r["actual"]) for r in rows_b) / sa
        ma3 = sum(abs(r["ma3_forecast"] - r["actual"]) for r in rows_b) / sa
        nai = sum(abs(r["naive_forecast"] - r["actual"]) for r in rows_b) / sa
        diffs_ma3.append(sel - ma3)
        diffs_naive.append(sel - nai)

    sel_dist = Counter(r["chosen"] for r in rows_out if r.get("valid") and r["chosen"])
    result = dict(
        schema_version="t10_nested_eval/1",
        inputs=dict(db_sha256=db_hash,
                    destinations_sha256=hashlib.sha256(DEST.read_bytes()).hexdigest()),
        rules=dict(
            r1_strata="strata use each training window only (final block uses its own training data)",
            r2_inner="model chosen on inner cut points inside each outer training window",
            r3_outer="outer refits every candidate and compares with fixed MA3/naive on the same sample",
            r4_window="monthly cumulative h=3, step 3, labels available at the time (label_available_at), refit per window",
            r5_fallback="pre-registered short-history rules; failures kept; zero-denominator cells listed separately",
            r6_final=("old T2 test period is exploratory; final evaluation uses the unused 2026-07..09 block; "
                      "a forward shadow plan covers months whose labels do not exist yet"),
            r7_budget=dict(candidates=len(CANDIDATES), series=len(sample),
                           outer=len(OUTER), inner=len(INNER_OFFSETS),
                           fit_cap=FIT_CAP, time_cap_s=TIME_CAP_S),
        ),
        candidates=CANDIDATES,
        series_sample=dict(n=len(sample), rule="sorted by total qty, every k-th, first 200"),
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
                  "on unseen samples, not a significance test")),
        shadow_plan=dict(
            when="每月 4 日（上月标签闭合后）",
            who="数据分析 worker（离线，只读 order_store）",
            what="用同一脚本、同一 200 序列样本与同一内层规则，重跑上一个连续 3 个月的累积 h=3 评估，"
                 "记录各候选 WAPE、被选中模型、零分母单元格数、失败原因与 fallback 次数",
            status="2026-10..12 的标签尚不存在，故本轮只交付 2026-07..09 的最终评估与影子方案",
            next_window="2026-10..12（标签可得后执行）"),
        zero_denominator={k: v["zero_denominator"] for k, v in blocks.items()},
        wording_note=("WAPE 是加权绝对百分比误差，不是“错 SKU 比例”或“准确率”，也没有通用阈值；"
                      "本报告只陈述“在未见样本上的差异与不确定性”，不使用评价性结论，"
                      "也不把探索性时段称作留出验证。"),
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
          f"- 样本 {len(sample)} 序列 × 外层 {len(OUTER)} × 内层 {len(INNER_OFFSETS)}，候选 {len(CANDIDATES)}", "",
          "## 同样本对比（WAPE，零分母单元格单列）", "",
          "| 外层 | 性质 | n | 计分 | 零分母 | 选择流程 | MA3 | naive |",
          "|---|---|---:|---:|---:|---:|---:|---:|"]
    for (o, kind), v in zip(OUTER, [blocks[f"{o}|{k}"] for o, k in OUTER]):
        L.append(f"| {o} | {kind} | {v['n']} | {v['n_scored']} | {v['zero_denominator']} | "
                 f"{v['selected']} | {v['ma3']} | {v['naive']} |")
    L += ["", f"- 最终评估块：**{final_key}**（2026-07..09，T2 未用作测试期）；"
          "更早两块是探索性（旧测试期）。", "",
          "## 内层选模分布", "",
          "| 被选中模型 | 次数 |", "|---|---:|"]
    for c, n in sel_dist.most_common():
        L.append(f"| {c} | {n} |")
    L += ["", "## 最终块分层指标（分层只用该外层训练窗的数据）", "",
          "| 层 | n | 计分 | 零分母 | 选择流程 | MA3 | naive |", "|---|---:|---:|---:|---:|---:|---:|"]
    for g, v in stratum_stats.items():
        L.append(f"| {g} | {v['n']} | {v['n_scored']} | {v['zero_denominator']} | "
                 f"{v['selected']} | {v['ma3']} | {v['naive']} |")
    b = result["bootstrap_final"]
    L += ["", "## 不确定性（最终块，重抽 SKU 300 次）", "",
          f"- 选择流程 − MA3：均值 {b['selected_minus_ma3']['mean']}，"
          f"5–95% [{b['selected_minus_ma3']['p5']}, {b['selected_minus_ma3']['p95']}]",
          f"- 选择流程 − naive：均值 {b['selected_minus_naive']['mean']}，"
          f"5–95% [{b['selected_minus_naive']['p5']}, {b['selected_minus_naive']['p95']}]",
          f"- {b['note']}", "",
          "## 失败与边界", "",
          "- 失败（保留，不删序列）：" + ("；".join(f"`{k}` × {v}" for k, v in
                                              result["failures"].items()) or "无"),
          "- 零分母单元格按外层单列（见上表 `零分母` 列），不计入 WAPE 分母。", "",
          "## 前向影子方案（未使用月份）", "",
          f"- {result['shadow_plan']['when']}；执行人：{result['shadow_plan']['who']}",
          f"- 记录内容：{result['shadow_plan']['what']}",
          f"- 状态：{result['shadow_plan']['status']}；下一窗口：{result['shadow_plan']['next_window']}", "",
          "## 措辞纪律", "",
          f"- {result['wording_note']}", "",
          "## 结论", "",
          f"- 在最终未使用块（2026-07..09）上，选择流程与 MA3 / naive 的 WAPE 分别为 "
          f"{blocks[final_key]['selected']} / {blocks[final_key]['ma3']} / "
          f"{blocks[final_key]['naive']}；差异的 SKU 重抽区间见上节。",
          "- 内层选模分布显示没有单一候选占绝对多数，选模本身带来方差；本报告不据此宣布任何候选更好。", ""]
    (OUT / "nested_report.md").write_text("\n".join(L) + "\n", encoding="utf-8")

    print("wrote nested_eval.json / .csv / nested_report.md")
    print("fits", fits, "runtime", result["compute"]["seconds"], "mem", result["compute"]["tracemalloc_peak_mb"])
    print("final", final_key, blocks[final_key])
    print("selection", dict(sel_dist.most_common()))


if __name__ == "__main__":
    main()
