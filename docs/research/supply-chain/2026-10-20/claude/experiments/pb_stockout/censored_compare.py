#!/usr/bin/env python
# -*- coding: utf-8 -*-
"""Raw vs censored-aware training for the PB stockout SKUs (OFFLINE, READ-ONLY).

Labels (from T42, `out/pb_stockout/stockout_intervals.csv`)
  A month is RESTRICTED when a conservative interval [start, end] overlaps it.
  The loose bound [start, loose_until] is used as the sensitivity label.
  Sales in a restricted month are a LOWER-BOUND observation, not true demand.

Two training routes (same SKUs, same cut points, same outer level)
  a) raw        : every month enters the ridge regression as observed.
  b) censored   : restricted months enter a one-sided (lower-censored) loss —
                  a prediction BELOW the observed value costs nothing, a
                  prediction ABOVE it is penalised. Solved by IRLS.
  Both use the same feature set (trend + month-of-year dummies) on log1p(y),
  so the only difference is how restricted months are treated.

Evaluation uses observable quantities only:
  1. WAPE / Bias on NON-restricted target months;
  2. stockout exposure on RESTRICTED target months: did the model predict more
     than what actually shipped (share of cells). This is a hit-rate against
     shipping, never a demand truth;
  3. backlog proxy: distribution of forecast / actual shipments (>1.2 = high).

No imputed demand is ever used as ground truth.

Budget: offline, < 600 s. Ends in seconds.
Outputs: out/pb_stockout/censored_compare.md / .json
"""
from __future__ import annotations

import argparse
import json
from collections import Counter, defaultdict
from datetime import date
from pathlib import Path

import duckdb
import numpy as np

HERE = Path(__file__).resolve()
CLAUDE_DIR = HERE.parents[2]
OUT = CLAUDE_DIR / "out" / "pb_stockout"
INTERVALS = OUT / "stockout_intervals.csv"
DB_PATH = Path("D:/Work/fzh-order-store/order_store.duckdb")
ORIGINS = ["2026-05", "2026-06", "2026-07"]
HORIZON = 3
MIN_TRAIN = 12
RIDGE = 1.0
IRLS_ITERS = 6
OVER_RATIO = 1.2


def ym_i(s: str) -> int:
    return int(s[:4]) * 12 + int(s[5:7]) - 1


def i_ym(i: int) -> str:
    y, m = divmod(i, 12)
    return f"{y:04d}-{m + 1:02d}"


def month_span(ym: str):
    i = ym_i(ym)
    return date(i // 12, i % 12 + 1, 1), date((i + 1) // 12, (i + 1) % 12 + 1, 1)


def read_intervals(path: Path, loose: bool = False):
    import csv
    out = defaultdict(list)
    with path.open(encoding="utf-8-sig", newline="") as fh:
        for r in csv.DictReader(fh):
            end = r["loose_until"] if loose and r.get("loose_until") else r["end"]
            out[r["sku"]].append((date.fromisoformat(r["start"]), date.fromisoformat(end)))
    return out


def is_restricted(sku, ym: str, iv: dict) -> bool:
    ms, me = month_span(ym)
    for a, b in iv.get(sku, ()):
        if a < me and b >= ms:          # overlap of [a,b] with the month
            return True
    return False


def design(months_idx, month_of_year, t0):
    """[1, t, 11 month dummies] — same for both routes."""
    rows = []
    for i, m in zip(months_idx, month_of_year):
        row = [1.0, float(i - t0)]
        for k in range(1, 12):
            row.append(1.0 if m == k else 0.0)
        rows.append(row)
    return np.array(rows, dtype=float)


def fit_ridge(X, y, w, lam=RIDGE):
    W = np.diag(w)
    A = X.T @ W @ X + lam * np.eye(X.shape[1])
    A[0, 0] -= lam                   # do not penalise the intercept
    b = X.T @ W @ y
    return np.linalg.solve(A, b)


def fit_route(y_log, X, censored, route):
    w = np.ones(len(y_log))
    beta = fit_ridge(X, y_log, w)
    if route == "raw":
        return beta
    # one-sided lower-censored loss via IRLS
    for _ in range(IRLS_ITERS):
        pred = X @ beta
        w_new = np.ones(len(y_log))
        for j in range(len(y_log)):
            if censored[j] and pred[j] < y_log[j]:
                w_new[j] = 0.0       # predicting below the lower bound is free
        if np.allclose(w_new, w):
            break
        w = w_new
        if w.sum() < 2:              # keep the fit identifiable
            w = np.maximum(w, 0.05)
        beta = fit_ridge(X, y_log, w)
    return beta


def main() -> None:
    ap = argparse.ArgumentParser()
    ap.add_argument("--db", default=str(DB_PATH))
    ap.add_argument("--intervals", default=str(INTERVALS))
    args = ap.parse_args()

    iv = read_intervals(Path(args.intervals))
    iv_loose = read_intervals(Path(args.intervals), loose=True)

    con = duckdb.connect(args.db, read_only=True)
    try:
        rows = con.execute("""
            SELECT sku_tongtool, substr(despatch_date,1,7), SUM(qty)
            FROM gs_orders WHERE channel='PotteryBarn'
              AND despatch_date <= '2026-09-30'
            GROUP BY 1,2""").fetchall()
    finally:
        con.close()

    series = defaultdict(dict)
    for sku, ym, q in rows:
        series[sku][ym] = float(q or 0)

    skus = sorted({s for s in iv} & set(series))     # frozen list ∩ sales
    last_i = ym_i("2026-09")

    results = {r: dict(cells_non=[], cells_restricted=[], per_sku={}) for r in ("raw", "censored")}
    labels = {}
    unscored = []
    preds_out = []

    for sku in skus:
        by = series[sku]
        first = min(ym_i(m) for m in by)
        months = [i_ym(i) for i in range(first, last_i + 1)]
        y = np.array([by.get(m, 0.0) for m in months], dtype=float)
        labels[sku] = dict(
            restricted_months=[m for m in months if is_restricted(sku, m, iv)],
            restricted_months_loose=[m for m in months if is_restricted(sku, m, iv_loose)])
        per_sku = dict(n_months=len(months), forecasts={})

        for origin in ORIGINS:
            o = ym_i(origin)
            tr = o - first + 1
            if tr < MIN_TRAIN:
                unscored.append(dict(sku=sku, origin=origin, reason="history_lt_min_train"))
                continue
            train_months = months[:tr]
            ytr = y[:tr]
            cens = np.array([is_restricted(sku, m, iv) for m in train_months], dtype=bool)
            X = design([ym_i(m) for m in train_months],
                       [int(m[5:7]) for m in train_months], first)
            ylog = np.log1p(ytr)
            tgt_months = [i_ym(o + 1 + k) for k in range(HORIZON)]
            tgt_months = [m for m in tgt_months if ym_i(m) <= last_i]
            Xf = design([ym_i(m) for m in tgt_months],
                        [int(m[5:7]) for m in tgt_months], first)
            for route in ("raw", "censored"):
                beta = fit_route(ylog, X, cens, route)
                f = np.maximum(0.0, np.expm1(Xf @ beta))
                for m, fv in zip(tgt_months, f):
                    actual = by.get(m, 0.0)
                    restricted = is_restricted(sku, m, iv)
                    cell = dict(sku=sku, origin=origin, month=m, forecast=round(float(fv), 3),
                                actual=round(float(actual), 3), restricted=bool(restricted))
                    (results[route]["cells_restricted"] if restricted
                     else results[route]["cells_non"]).append(cell)
                    preds_out.append(dict(route=route, **cell))
                per_sku["forecasts"].setdefault(origin, {})[route] = [
                    round(float(v), 3) for v in f]
        results["raw"]["per_sku"][sku] = per_sku
        results["censored"]["per_sku"][sku] = per_sku

    # ---- metrics ------------------------------------------------------
    def wape_bias(cells):
        if not cells:
            return dict(n=0, wape=None, bias=None)
        ae = sum(abs(c["forecast"] - c["actual"]) for c in cells)
        tot = sum(c["actual"] for c in cells)
        bias = sum(c["forecast"] - c["actual"] for c in cells)
        return dict(n=len(cells), wape=(ae / tot if tot else None),
                    bias=(bias / tot if tot else None))

    def exposure(cells):
        """Share of restricted-month cells where the forecast exceeds actual
        shipments by > 20% (model thought it could serve more than shipped)."""
        if not cells:
            return dict(n=0, over=0, rate=None)
        over = sum(1 for c in cells if c["actual"] > 0 and c["forecast"] > c["actual"] * OVER_RATIO)
        return dict(n=len(cells), over=over, rate=over / len(cells))

    def backlog(cells):
        ratios = [c["forecast"] / c["actual"] for c in cells if c["actual"] > 0]
        if not ratios:
            return dict(n=0, median=None, over_share=None)
        arr = np.array(ratios)
        return dict(n=len(ratios), median=round(float(np.median(arr)), 3),
                    over_share=round(float((arr > OVER_RATIO).mean()), 4))

    summary = {}
    for route in ("raw", "censored"):
        r = results[route]
        summary[route] = dict(
            non_restricted=wape_bias(r["cells_non"]),
            restricted_exposure=exposure(r["cells_restricted"]),
            backlog_proxy=backlog(r["cells_non"] + r["cells_restricted"]))

    # ---- write --------------------------------------------------------
    payload = dict(
        schema_version="pb_censored_compare/1",
        inputs=dict(intervals=str(INTERVALS), db=str(args.db),
                    origins=ORIGINS, horizon=HORIZON, min_train=MIN_TRAIN,
                    ridge=RIDGE, over_ratio=OVER_RATIO),
        labels=dict(
            rule=("月份与保守区间 [start,end] 有重叠即受限；宽松区间 [start,loose_until] "
                  "作敏感性；受限月销量是下限观测"),
            skus=len(skus),
            restricted_month_counts={s: len(v["restricted_months"]) for s, v in labels.items()},
            loose_month_counts={s: len(v["restricted_months_loose"]) for s, v in labels.items()},
            per_sku=labels),
        routes=dict(
            raw="ridge on log1p(y), all months weighted 1",
            censored=("ridge on log1p(y) with one-sided lower-censored loss: a prediction "
                      "below the observed restricted value costs 0, above it costs the "
                      "usual squared loss (IRLS, 6 iterations)")),
        summary=summary,
        unscored=dict(n=len(unscored), reasons=dict(Counter(u["reason"] for u in unscored))),
        scored_skus=len({c["sku"] for c in results["raw"]["cells_non"]
                         + results["raw"]["cells_restricted"]}),
        per_sku_forecasts=results["raw"]["per_sku"],
        cells=preds_out,
    )
    (OUT / "censored_compare.json").write_text(
        json.dumps(payload, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")

    def p(v):
        return "—" if v is None else (f"{v:.3f}" if isinstance(v, float) else str(v))

    def p(v):
        return "—" if v is None else (f"{v:.3f}" if isinstance(v, float) else str(v))

    def diff(x, y):
        if x is None or y is None:
            return "—"
        return f"{y - x:+.3f}"

    a, b = summary["raw"], summary["censored"]
    L = ["---", "okf: v0.1", "type: Report",
         "title: 原始销量 vs 删失感知训练（PB 三角）",
         "date: 2026-10-23", "owner: claude-worker",
         "status: 只读离线；只用可观测量评估；不用插补需求当真值",
         "artifacts:",
         "  - experiments/pb_stockout/censored_compare.py",
         "  - out/pb_stockout/censored_compare.json",
         "---", "",
         "# 原始销量 vs 删失感知训练", "",
         "> **铁律**：受限月的销量是**下限观测**，不是真实需求。本报告从不用插补需求当 ground truth；"
         "三条评估全部基于可观测量（非受限月实际销量、实际发运、预测/发运比值）。", "",
         "## 1. 标签（来自 T42 区间）", "",
         "- 受限月判定：月份与保守区间 `[start, end]` 重叠 → 受限；宽松 `[start, loose_until]` 作敏感性。",
         f"- 名单 SKU **{len(skus)}**；有受限月的 SKU "
         f"**{sum(1 for v in labels.values() if v['restricted_months'])}**"
         f"（受限月只落在 2026-06 / 2026-07）。",
         f"- 切点：{', '.join(ORIGINS)}；horizon {HORIZON} 个月；最少训练 {MIN_TRAIN} 个月。", "",
         "## 2. 两条训练路线", "",
         "| 路线 | 实现 |", "|---|---|",
         "| raw | `log1p(y)` 上做岭回归（趋势 + 11 个月份哑变量），所有月份权重 1 |",
         "| censored | 同一特征、同一正则；对受限月用**单侧（下删失）损失**："
         "预测低于观测值不计损失，高于观测值才罚（IRLS 6 次迭代） |", "",
         "> 两条路线唯一的差别就是受限月的处理方式，特征与切点完全相同。", "",
         "## 3. 三项评估（只用可观测量）", "",
         "| 指标 | raw | censored | 差异 |", "|---|---:|---:|---|",
         f"| ① 非受限月 WAPE（n={a['non_restricted']['n']}） | "
         f"{p(a['non_restricted']['wape'])} | {p(b['non_restricted']['wape'])} | "
         f"{diff(a['non_restricted']['wape'], b['non_restricted']['wape'])} |",
         f"| ① 非受限月 Bias | {p(a['non_restricted']['bias'])} | "
         f"{p(b['non_restricted']['bias'])} | "
         f"{diff(a['non_restricted']['bias'], b['non_restricted']['bias'])} |",
         f"| ② 受限月「预测>实际发运×1.2」占比（n={a['restricted_exposure']['n']}） | "
         f"{p(a['restricted_exposure']['rate'])} | {p(b['restricted_exposure']['rate'])} | "
         f"{diff(a['restricted_exposure']['rate'], b['restricted_exposure']['rate'])} |",
         f"| ③ 积压代理：预测/发运中位数（n={a['backlog_proxy']['n']}） | "
         f"{p(a['backlog_proxy']['median'])} | {p(b['backlog_proxy']['median'])} | "
         f"{diff(a['backlog_proxy']['median'], b['backlog_proxy']['median'])} |",
         f"| ③ 积压代理：比值 >1.2 占比 | {p(a['backlog_proxy']['over_share'])} | "
         f"{p(b['backlog_proxy']['over_share'])} | "
         f"{diff(a['backlog_proxy']['over_share'], b['backlog_proxy']['over_share'])} |", ""]

    # per-SKU evidence table
    by_sku = defaultdict(lambda: {"raw": {"non": [], "res": []},
                                  "censored": {"non": [], "res": []}})
    for route in ("raw", "censored"):
        for c in results[route]["cells_non"]:
            by_sku[c["sku"]][route]["non"].append(c)
        for c in results[route]["cells_restricted"]:
            by_sku[c["sku"]][route]["res"].append(c)

    L += ["", "### 3b. 逐 SKU 证据", "",
          "| SKU | 非受限单元 | raw WAPE | censored WAPE | 受限单元 | raw 高估% | censored 高估% |",
          "|---|---:|---:|---:|---:|---:|---:|"]
    for sku in sorted(by_sku):
        row = by_sku[sku]
        rn = wape_bias(row["raw"]["non"])["wape"]
        cn = wape_bias(row["censored"]["non"])["wape"]
        rr = exposure(row["raw"]["res"])["rate"]
        cr = exposure(row["censored"]["res"])["rate"]
        L.append(f"| `{sku}` | {len(row['raw']['non'])} | {p(rn)} | {p(cn)} | "
                 f"{len(row['raw']['res'])} | {p(rr)} | {p(cr)} |")
    L += ["", "> 逐 SKU 单元数很小（每个切点 1–3 个月），单 SKU 数字只作证据，不作排名。", ""]

    L += ["", "> ② 是「模型是否高估了可满足量」的命中率，**不是**需求真值比较；"
          "③ 用预测÷实际发运的比值分布作积压代理，>1.2 记高估。", "",
          "## 4. 样本量与未评分覆盖", "",
          f"- 评分 SKU **{payload['scored_skus']}** / 名单 {len(skus)}；"
          f"未评分单元 **{payload['unscored']['n']}**，原因 {payload['unscored']['reasons'] or '无'}",
          f"- 非受限月单元 **{a['non_restricted']['n']}**；受限月单元 **{a['restricted_exposure']['n']}**；"
          f"逐 SKU 预测见 JSON 的 `per_sku_forecasts` 与 `cells`。", "",
          "## 5. 结论（只写观测）", ""]

    def better(x, y, lower_is_better=True):
        if x is None or y is None:
            return "样本不足，无法比较"
        if abs(x - y) < 1e-9:
            return "两者相同"
        win = "raw" if ((x < y) if lower_is_better else (x > y)) else "censored"
        return f"**{win} 更好**（差 {abs(y - x):.3f}）"

    L.append(f"1. **非受限月 WAPE**：raw {p(a['non_restricted']['wape'])}、"
             f"censored {p(b['non_restricted']['wape'])}，n={a['non_restricted']['n']} → "
             f"{better(a['non_restricted']['wape'], b['non_restricted']['wape'])}。")
    L.append(f"2. **受限月缺货暴露**（预测>实际发运×1.2 的占比）：raw {p(a['restricted_exposure']['rate'])}、"
             f"censored {p(b['restricted_exposure']['rate'])}，n={a['restricted_exposure']['n']} → "
             f"{better(a['restricted_exposure']['rate'], b['restricted_exposure']['rate'])}。")
    L.append(f"3. **积压代理**（>1.2 占比）：raw {p(a['backlog_proxy']['over_share'])}、"
             f"censored {p(b['backlog_proxy']['over_share'])}，n={a['backlog_proxy']['n']} → "
             f"{better(a['backlog_proxy']['over_share'], b['backlog_proxy']['over_share'])}。")
    L += ["", "> 以上只说明**在这批 SKU、这几个切点、这些可观测量上**谁更好、差多少；"
          "不构成「删失感知更优」的一般结论，也没有用插补需求评自身。", "",
          "## 6. 已知限制", "",
          "- 受限月只有 2026-06 / 2026-07 两个月，切点因此集中在 2026-05..07，样本小。",
          "- 特征只有趋势与月份哑变量；促销、价格、上新日历本地不可得，未编造。",
          "- 实际发运同时受订单与库存影响，不是纯需求观测量。", ""]

    (OUT / "censored_compare.md").write_text("\n".join(L) + "\n", encoding="utf-8")
    print(json.dumps(summary, ensure_ascii=False))
    print(f"skus={len(skus)} scored={payload['scored_skus']} unscored={len(unscored)}")


if __name__ == "__main__":
    main()
