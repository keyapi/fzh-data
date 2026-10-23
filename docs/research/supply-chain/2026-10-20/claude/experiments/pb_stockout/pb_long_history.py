#!/usr/bin/env python
# -*- coding: utf-8 -*-
"""PB 多年长史 / 促销 / 断货验证（只读离线）—— SC07 下一批。

接 b2217e4d（R2 损失方向修正）与 9acec3db（零分母表）。按 INVENTORY_EVALUATION §7：

  (1) 固定 28 名单 + 26/27/28 差集（复用 sku_set_diff.csv，不重算）；
      把 2024/25 促销窗口切成 正常 / 促销 / 疑似受限 / 恢复期 四段。
  (2) 分开「下单需求/接单时间」与「履约发运量/时间」（sale_date vs despatch_date）。
  (3) ★主验收：在可靠未受限片段做人工截断，保留原真实需求作真值，
      验证损失方向与恢复方法能不能真的还原；报告截断比例/还原误差/失败条件。
  (4) 真实缺货段只报需求范围与敏感性，不造假真值。

复用而非重写：`censored_r2.fit_lower`（单侧下限 IRLS）、`censored_compare.design/fit_ridge`
（同一套岭回归设计）、`out/pb_stockout/sku_set_diff.csv`、`stockout_intervals_v2.csv`。

红线：只读；无预测交付、无补货量；行级数据留本地；报告只放聚合与样例。

输出（本地）：
  out/pb_stockout/pb_long_segments.csv      28 SKU × 月份 × 段标签
  out/pb_stockout/pb_long_demand_ship.csv   下单/发运 双口径
  out/pb_stockout/pb_long_truncation.csv    人工截断逐次结果
  out/pb_stockout/pb_long_ranges.csv        真实受限段需求范围（情景）
  out/pb_stockout/pb_long_history.json      聚合
"""
from __future__ import annotations

import csv
import json
import sys
import time
from collections import Counter, defaultdict
from datetime import date
from pathlib import Path

import duckdb
import numpy as np

HERE = Path(__file__).resolve()
EXP_DIR = HERE.parent
CLAUDE_DIR = HERE.parents[2]
OUT = CLAUDE_DIR / "out" / "pb_stockout"
sys.path.insert(0, str(EXP_DIR))

import censored_compare as legacy          # noqa: E402  (design / fit_ridge)
import censored_r2 as r2                   # noqa: E402  (fit_lower，R2 修正后的单侧下限损失)

DB_PATH = Path("D:/Work/fzh-order-store/order_store.duckdb")
COHORT = Path("D:/Work/fzh-order-store/pb_forecast_cohort.json")
SET_DIFF = OUT / "sku_set_diff.csv"
INTERVALS_V2 = OUT / "stockout_intervals_v2.csv"

LAST_I = 2026 * 12 + 9 - 1          # 2026-09 是最后一个完整月
MIN_HISTORY = 18                    # 拟合至少需要 18 个月（既有限制，非新门槛）
CUTS = ["2025-09", "2025-12", "2026-03"]   # 三个截断点，均在信号窗（2026-06）之前
WINDOW_LENS = [1, 3]                # 人为受限段的长度（月）
RATIOS = [0.0, 0.2, 0.4, 0.6, 0.8]  # 残留可观测比例（0.0 = 完全截断）
METHODS = ["raw", "lower_bound", "neighbor", "seasonal_naive"]


# --------------------------------------------------------------------------- #
def ym_i(s: str) -> int:
    return int(s[:4]) * 12 + int(s[5:7]) - 1


def i_ym(i: int) -> str:
    y, m = divmod(i, 12)
    return f"{y:04d}-{m + 1:02d}"


def month_set(a: str, b: str):
    return {i_ym(i) for i in range(ym_i(a), ym_i(b) + 1)}


def main() -> None:
    t0 = time.time()
    cohort = json.loads(COHORT.read_text(encoding="utf-8"))
    cohort_rows = cohort["rows"]
    cohort_skus = [r["vendor_sku"] for r in cohort_rows]
    set_diff = list(csv.DictReader(SET_DIFF.open(encoding="utf-8-sig", newline="")))
    frozen = sorted({r["sku"] for r in set_diff if r["in_frozen26"] == "yes"})
    roster27 = sorted({r["sku"] for r in set_diff if r["in_roster27"] == "yes"})
    v2 = list(csv.DictReader(INTERVALS_V2.open(encoding="utf-8-sig", newline="")))

    con = duckdb.connect(str(DB_PATH), read_only=True)
    try:
        order_rows = con.execute("""
            SELECT sku_tongtool, substr(sale_date,1,7) ym, sum(qty)
            FROM gs_orders WHERE channel='PotteryBarn' AND sale_date<>''
            GROUP BY 1,2""").fetchall()
        ship_rows = con.execute("""
            SELECT sku_tongtool, substr(despatch_date,1,7) ym, sum(qty)
            FROM gs_orders WHERE channel='PotteryBarn' AND despatch_date<>''
            GROUP BY 1,2""").fetchall()
        lag_rows = con.execute("""
            SELECT sku_tongtool,
                   CASE WHEN d<=3 THEN '0-3' WHEN d<=7 THEN '4-7'
                        WHEN d<=14 THEN '8-14' WHEN d<=30 THEN '15-30' ELSE '>30' END b,
                   count(*), sum(qty)
            FROM (SELECT sku_tongtool, qty,
                         date_diff('day', CAST(sale_date AS DATE), CAST(despatch_date AS DATE)) d
                  FROM gs_orders WHERE channel='PotteryBarn'
                    AND sale_date<>'' AND despatch_date<>'') GROUP BY 1,2""").fetchall()
        cross_month = con.execute("""
            SELECT count(*), sum(qty) FROM gs_orders
            WHERE channel='PotteryBarn' AND sale_date<>'' AND despatch_date<>''
              AND substr(sale_date,1,7) <> substr(despatch_date,1,7)""").fetchone()
        total_lines, total_qty = con.execute("""
            SELECT count(*), sum(qty) FROM gs_orders WHERE channel='PotteryBarn'""").fetchone()
    finally:
        con.close()

    dem = defaultdict(dict)     # sku -> ym -> qty（下单/接单）
    shp = defaultdict(dict)     # sku -> ym -> qty（发运）
    for sku, ym, q in order_rows:
        dem[sku][ym] = float(q or 0)
    for sku, ym, q in ship_rows:
        shp[sku][ym] = float(q or 0)

    # ---------------------------------------------------------------- (1) 分段
    promo_windows = []
    for e in cohort.get("events", []):
        a, b = e["start"], e["end_inclusive"]
        promo_windows.append(dict(event=e["event"], start=a, end=b, basis=e.get("basis"),
                                  months=sorted(month_set(a, b))))
    # 恢复期 = 促销窗结束后的下一个自然月（本轮定义，非来源门槛）
    for w in promo_windows:
        end_i = ym_i(w["months"][-1])
        w["recovery_month"] = i_ym(end_i + 1)

    signal_months = defaultdict(set)
    for r in v2:
        for d in r["signal_dates"].split(";"):
            if d:
                signal_months[r["sku"]].add(d[:7])

    seg_rows = []
    for sku in cohort_skus:
        first = min((ym_i(m) for m in dem.get(sku, {}) if dem[sku][m] > 0), default=None)
        if first is None:
            continue
        for i in range(first, LAST_I + 1):
            m = i_ym(i)
            if m in signal_months.get(sku, ()):
                seg = "疑似受限"
            elif any(m in w["months"] for w in promo_windows):
                seg = "促销"
            elif any(m == w["recovery_month"] for w in promo_windows):
                seg = "恢复期"
            else:
                seg = "正常"
            seg_rows.append(dict(sku=sku, month=m,
                                 qty_order=round(dem.get(sku, {}).get(m, 0.0), 2),
                                 qty_ship=round(shp.get(sku, {}).get(m, 0.0), 2),
                                 segment=seg,
                                 in_frozen26=("yes" if sku in frozen else "no"),
                                 in_roster27=("yes" if sku in roster27 else "no")))
    with (OUT / "pb_long_segments.csv").open("w", encoding="utf-8-sig", newline="") as fh:
        w = csv.DictWriter(fh, fieldnames=list(seg_rows[0].keys()))
        w.writeheader()
        w.writerows(seg_rows)

    seg_counts = Counter(r["segment"] for r in seg_rows)
    # (2) 下单 vs 发运：逐月差 + 跨月顺延
    ds_rows = []
    for sku in cohort_skus:
        months = sorted(set(dem.get(sku, {})) | set(shp.get(sku, {})))
        for m in months:
            ds_rows.append(dict(sku=sku, month=m,
                                qty_order=round(dem.get(sku, {}).get(m, 0.0), 2),
                                qty_ship=round(shp.get(sku, {}).get(m, 0.0), 2),
                                diff_ship_minus_order=round(
                                    shp.get(sku, {}).get(m, 0.0) - dem.get(sku, {}).get(m, 0.0), 2)))
    with (OUT / "pb_long_demand_ship.csv").open("w", encoding="utf-8-sig", newline="") as fh:
        w = csv.DictWriter(fh, fieldnames=list(ds_rows[0].keys()))
        w.writeheader()
        w.writerows(ds_rows)

    lag_by_bucket = defaultdict(lambda: [0, 0.0])
    for sku, b, n, q in lag_rows:
        lag_by_bucket[b][0] += n
        lag_by_bucket[b][1] += float(q or 0)

    # ------------------------------------------------- (3) 人工截断（主验收）
    # 两种设置，目的不同：
    #   interior（背景回填）：受限段两侧都还有观测 -> 考"插补/恢复"能力
    #   terminal（到切点为止）：受限段就在数据末端 -> 考"预测"能力
    def series_of(sku):
        by = dem.get(sku, {})
        pos = [m for m, q in by.items() if q > 0]
        if not pos:
            return None
        first = ym_i(min(pos))
        months = [i_ym(i) for i in range(first, LAST_I + 1)]
        return months, np.array([by.get(m, 0.0) for m in months], dtype=float)

    trunc_rows = []
    for sku in frozen:
        s = series_of(sku)
        if not s:
            continue
        months, y_true = s
        n = len(months)
        if n < MIN_HISTORY:
            continue
        sig_idx = {i for i, m in enumerate(months) if m in signal_months.get(sku, ())}
        for setting, tail in (("interior", 3), ("terminal", 0)):
            for end_i in (n - 4, n - 10, n - 16):
                for L in WINDOW_LENS:
                    w_end = end_i + 1
                    w_start = w_end - L
                    cut_i = w_end + tail
                    if w_start < 6 or cut_i > n or w_end <= w_start:
                        continue
                    if any(i in sig_idx for i in range(w_start, cut_i)):
                        continue                     # 不与真实信号月混在一起
                    train_months = months[:cut_i]
                    for ratio in RATIOS:
                        y_c = y_true[:cut_i].copy()
                        y_c[w_start:w_end] = ratio * y_true[w_start:w_end]
                        cens = np.zeros(cut_i, dtype=bool)
                        cens[w_start:w_end] = True
                        X = legacy.design([ym_i(m) for m in train_months],
                                          [int(m[5:7]) for m in train_months], ym_i(months[0]))
                        ylog = np.log1p(y_c)
                        beta_raw = legacy.fit_ridge(X, ylog, np.ones(len(ylog)))
                        beta_lb = r2.fit_lower(ylog, X, cens)
                        preds = {
                            "raw": np.maximum(0.0, np.expm1(X[w_start:w_end] @ beta_raw)),
                            "lower_bound": np.maximum(0.0, np.expm1(X[w_start:w_end] @ beta_lb)),
                        }
                        neigh = []
                        for k in range(max(0, w_start - 3), w_start):
                            neigh.append(y_c[k])
                        for k in range(w_end, min(cut_i, w_end + 3)):
                            neigh.append(y_c[k])
                        neigh_val = float(np.median(neigh)) if neigh else float(np.median(y_c))
                        preds["neighbor"] = np.full(w_end - w_start, neigh_val)
                        sea = []
                        for k in range(w_start, w_end):
                            prev = k - 12
                            sea.append(y_c[prev] if 0 <= prev < cut_i and not cens[prev] else neigh_val)
                        preds["seasonal_naive"] = np.array(sea)

                        truth = y_true[w_start:w_end]
                        for meth, pr in preds.items():
                            for j, (p, t) in enumerate(zip(pr, truth)):
                                trunc_rows.append(dict(
                                    setting=setting, sku=sku, cut=months[cut_i - 1],
                                    window_len=L, ratio=ratio,
                                    month=months[w_start + j], method=meth,
                                    true=round(float(t), 4), pred=round(float(p), 4),
                                    abs_err=round(abs(float(p) - float(t)), 4),
                                    rel_err=(round((float(p) - float(t)) / float(t), 4) if t else ""),
                                    free_wape="",
                                ))
                        mask_free = np.ones(cut_i, dtype=bool)
                        mask_free[w_start:w_end] = False
                        free = np.where(mask_free)[0]
                        tot = float(y_c[free].sum())
                        for meth, beta in (("raw", beta_raw), ("lower_bound", beta_lb)):
                            p = np.maximum(0.0, np.expm1(X[free] @ beta))
                            wape = float(np.abs(p - y_c[free]).sum() / tot) if tot else None
                            trunc_rows.append(dict(
                                setting=setting, sku=sku, cut=months[cut_i - 1],
                                window_len=L, ratio=ratio, month="__free__", method=meth,
                                true=round(tot, 4), pred=round(float(p.sum()), 4),
                                abs_err="", rel_err="",
                                free_wape=(round(wape, 4) if wape is not None else ""),
                            ))

    fields = ["setting", "sku", "cut", "window_len", "ratio", "month", "method",
              "true", "pred", "abs_err", "rel_err", "free_wape"]
    with (OUT / "pb_long_truncation.csv").open("w", encoding="utf-8-sig", newline="") as fh:
        w = csv.DictWriter(fh, fieldnames=fields)
        w.writeheader()
        w.writerows(trunc_rows)

    cells = [r for r in trunc_rows if r["month"] != "__free__"]
    summary = {}
    for setting in ("interior", "terminal"):
        for ratio in RATIOS:
            for L in WINDOW_LENS:
                for meth in METHODS:
                    sub = [r for r in cells if r["setting"] == setting and r["ratio"] == ratio
                           and r["window_len"] == L and r["method"] == meth]
                    if not sub:
                        continue
                    rel = [r["rel_err"] for r in sub if r["rel_err"] != ""]
                    summary[f"{setting}_r{ratio}_L{L}_{meth}"] = dict(
                        n=len(sub),
                        median_abs_err=round(float(np.median([r["abs_err"] for r in sub])), 4),
                        median_rel_bias=(round(float(np.median(rel)), 4) if rel else None),
                        share_within_20pct=(round(float(np.mean([abs(x) <= 0.20 for x in rel])), 4)
                                            if rel else None),
                    )
    free_wape = {}
    for setting in ("interior", "terminal"):
        for L in WINDOW_LENS:
            for meth in ("raw", "lower_bound"):
                sub = [r for r in trunc_rows if r.get("setting") == setting
                       and r["month"] == "__free__" and r["window_len"] == L
                       and r["method"] == meth and r["free_wape"] != ""]
                if sub:
                    free_wape[f"{setting}_L{L}_{meth}"] = round(
                        float(np.median([float(x["free_wape"]) for x in sub])), 4)

    # --------------------------------------------- (4) 真实受限段：范围与敏感性
    range_rows = []
    for sku in frozen:
        by = dem.get(sku, {})
        series = series_of(sku)
        if not series:
            continue
        months, y = series
        idx = {m: i for i, m in enumerate(months)}
        for r in v2:
            if r["sku"] != sku:
                continue
            for month in month_set(r["first_signal_date"], r["last_signal_date"]):
                if month not in idx:
                    continue
                k = idx[month]
                obs = float(y[k])
                # 参照水平：同 SKU 未受限月的同月型中位数（不看信号月）
                sig = signal_months.get(sku, set())
                ref = [float(y[j]) for j, m2 in enumerate(months)
                       if m2 not in sig and int(m2[5:7]) == int(month[5:7]) and y[j] > 0]
                if not ref:
                    ref = [float(v) for j, v in enumerate(y) if y[j] > 0]
                base_med = float(np.median(ref)) if ref else obs
                base_p75 = float(np.quantile(ref, 0.75)) if ref else obs
                range_rows.append(dict(
                    sku=sku, month=month, observed=round(obs, 2),
                    ref_n=len(ref),
                    demand_low=round(obs, 2),
                    demand_mid=round(max(obs, base_med), 2),
                    demand_high=round(max(obs, base_p75), 2),
                    note="范围=情景敏感性，不是需求真值；obs 是已发运/已下单的下限",
                ))
    if range_rows:
        with (OUT / "pb_long_ranges.csv").open("w", encoding="utf-8-sig", newline="") as fh:
            w = csv.DictWriter(fh, fieldnames=list(range_rows[0].keys()))
            w.writeheader()
            w.writerows(range_rows)

    payload = dict(
        schema_version="pb_long_history/1",
        inputs=dict(db=str(DB_PATH), cohort=str(COHORT), set_diff=str(SET_DIFF),
                    intervals=str(INTERVALS_V2), settings=["interior", "terminal"],
                    window_lens=WINDOW_LENS,
                    ratios=RATIOS, methods=METHODS, min_history=MIN_HISTORY),
        roster=dict(cohort28=len(cohort_skus), frozen26=len(frozen), roster27=len(roster27),
                    set_diff_categories=dict(Counter(r["category"] for r in set_diff))),
        promo=dict(windows=promo_windows,
                   basis_note=("促销日期来自 cohort.json 的 events；basis 是供应商成本恢复口径的邮件/备忘，"
                               "**不是客户零售促销**；两者不可等同（cohort caveat）")),
        segments=dict(counts=dict(seg_counts), total_cells=len(seg_rows)),
        demand_vs_ship=dict(
            lag_buckets={b: dict(lines=v[0], qty=round(v[1], 2)) for b, v in sorted(lag_by_bucket.items())},
            cross_month_lines=cross_month[0], cross_month_qty=round(float(cross_month[1] or 0), 2),
            total_lines=total_lines, total_qty=round(float(total_qty or 0), 2),
            cross_month_share_lines=round(cross_month[0] / total_lines, 4) if total_lines else None,
            cross_month_share_qty=(round(float(cross_month[1] or 0) / float(total_qty), 4)
                                   if total_qty else None),
        ),
        truncation=dict(summary=summary, free_wape=free_wape,
                        n_cells=len(cells), n_runs=len({(r["setting"], r["sku"], r["cut"], r["window_len"], r["ratio"])
                                                        for r in cells})),
        ranges=dict(n=len(range_rows), note="真实受限段只给范围与敏感性，不造假真值"),
        elapsed_s=round(time.time() - t0, 2),
    )
    (OUT / "pb_long_history.json").write_text(
        json.dumps(payload, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")

    print(json.dumps({k: payload[k] for k in ("roster", "segments", "demand_vs_ship")},
                     ensure_ascii=False, indent=1))
    print(json.dumps({"truncation_cells": len(cells), "runs": payload["truncation"]["n_runs"],
                      "ranges": len(range_rows), "elapsed_s": payload["elapsed_s"]}, ensure_ascii=False))
    # 关键格子
    for key in ("interior_r0.0_L1_raw", "interior_r0.0_L1_lower_bound",
                "interior_r0.0_L1_neighbor", "terminal_r0.0_L1_raw", "terminal_r0.0_L1_lower_bound",
                "terminal_r0.0_L3_lower_bound", "terminal_r0.8_L3_lower_bound"):
        if key in summary:
            print(key, json.dumps(summary[key], ensure_ascii=False))


if __name__ == "__main__":
    main()
