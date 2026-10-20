#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""E1 预测基线回测：PB 楔形枕 8 SKU。

方法：naive / seasonal_naive / ma3 / ma6 / ma12 / M1 运行率 / M2 同比 /
M3 线性趋势 / M3b 季节平均 / Croston / TSB。
滚动原点（h=3），断货月可选删失。
"""

import argparse
import csv
import json
import math
import statistics
from collections import defaultdict
from pathlib import Path

BASE = Path(__file__).resolve().parent
DATA = BASE / "data" / "wedge_monthly.csv"
CENSORED = {
    "2880": {"2026-03", "2026-04", "2026-05"},
    "2878": {"2026-06", "2026-07"},
    "2876": {"2026-05"},
}
H = 3


def mkey(y, m):
    return f"{y}-{m:02d}"


def madd(key, k):
    y, m = map(int, key.split("-"))
    t = y * 12 + (m - 1) + k
    return mkey(t // 12, t % 12 + 1)


def months_between(a, b):
    out = []
    cur = a
    while cur <= b:
        out.append(cur)
        cur = madd(cur, 1)
    return out


def load(measure):
    series = defaultdict(dict)
    with DATA.open(encoding="utf-8") as f:
        for row in csv.DictReader(f):
            series[row["sku"]][row["month"]] = float(row[measure])
    lo = min(min(s) for s in series.values())
    hi = max(max(s) for s in series.values())
    full = months_between(lo, hi)
    for sku in series:
        series[sku] = {m: series[sku].get(m, 0.0) for m in full}
    return series, full


def clean_hist(series, sku, upto, mode):
    """返回 origin 之前的 [(month, value)]；censored 模式剔除断货月。"""
    out = []
    for m, v in sorted(series[sku].items()):
        if m > upto:
            break
        if mode == "censored" and m in CENSORED.get(sku, set()):
            continue
        out.append((m, v))
    return out


def naive_rate(hist):
    return hist[-1][1] if hist else 0.0


def ma_rate(hist, n):
    vals = [v for _, v in hist[-n:]]
    return sum(vals) / len(vals) if vals else 0.0


def seasonal_naive_month(series, sku, target, hist_map):
    prev = madd(target, -12)
    return hist_map.get(prev, naive_rate(list(hist_map.items())))


def m1_rate(hist):
    return ma_rate(hist, 12)


def m2_month(series, sku, target, hist, origin):
    hist_map = dict(hist)
    prev = madd(target, -12)
    if prev not in hist_map:
        return m1_rate(hist)
    recent = [v for _, v in hist[-6:]]
    prior = [hist_map.get(madd(m, -12), 0.0) for m in months_between(madd(origin, -5), origin)]
    r = sum(recent) / sum(prior) if sum(prior) > 0 else 1.0
    r = max(0.3, min(2.0, r))
    return hist_map[prev] * r


def m3_month(hist, target, origin):
    vals = [v for _, v in hist[-12:]]
    n = len(vals)
    if n < 6:
        return m1_rate(hist)
    xs = list(range(n))
    mx = sum(xs) / n
    my = sum(vals) / n
    den = sum((x - mx) ** 2 for x in xs)
    slope = sum((x - mx) * (y - my) for x, y in zip(xs, vals)) / den if den else 0.0
    step = months_between(origin, target)
    k = len(step) - 1
    return max(0.0, my + slope * (n - 1 - mx + k))


def m3b_month(series, sku, target, origin, hist):
    mm = target[5:7]
    vals = [
        v for m, v in series[sku].items()
        if m[5:7] == mm and m <= origin and m not in CENSORED.get(sku, set())
    ]
    return statistics.mean(vals) if vals else m1_rate(hist)


def croston_tsb(hist, alpha=0.3, beta=0.3):
    """TSB：概率 × 需求规模。返回月需求率。"""
    if not hist:
        return 0.0
    nz = [v for _, v in hist if v > 0]
    z = len(nz) / len(hist)
    d = sum(nz) / len(nz) if nz else 0.0
    for _, v in hist:
        if v > 0:
            z = alpha * 1.0 + (1 - alpha) * z
            d = alpha * v + (1 - alpha) * d
        else:
            z = (1 - alpha) * z
            d = beta * 0 + (1 - beta) * d
    return z * d


def croston_classic(hist, alpha=0.3):
    if not hist:
        return 0.0
    # 简化 Croston：非零间隔与规模分别指数平滑
    p, d = None, None
    gap = 0
    for _, v in hist:
        gap += 1
        if v > 0:
            p = gap if p is None else alpha * gap + (1 - alpha) * p
            d = v if d is None else alpha * v + (1 - alpha) * d
            gap = 0
    return (d / p) if p and d else 0.0


def forecast(series, sku, origin, method, mode):
    hist = clean_hist(series, sku, origin, mode)
    hist_map = dict(hist)
    targets = [madd(origin, k) for k in range(1, H + 1)]
    if method == "naive":
        r = naive_rate(hist)
        return [r] * H
    if method == "seasonal_naive":
        return [seasonal_naive_month(series, sku, t, hist_map) for t in targets]
    if method.startswith("ma"):
        r = ma_rate(hist, int(method[2:]))
        return [r] * H
    if method == "M1":
        r = m1_rate(hist)
        return [r] * H
    if method == "M2":
        return [m2_month(series, sku, t, hist, origin) for t in targets]
    if method == "M3":
        return [m3_month(hist, t, origin) for t in targets]
    if method == "M3b":
        return [m3b_month(series, sku, t, origin, hist) for t in targets]
    if method == "croston":
        r = croston_classic(hist)
        return [r] * H
    if method == "tsb":
        r = croston_tsb(hist)
        return [r] * H
    if method in ("ens3", "ens5"):
        comps = ["ma6", "croston", "tsb"] if method == "ens3" else ["ma3", "ma6", "ma12", "croston", "tsb"]
        lists = [forecast(series, sku, origin, c, mode) for c in comps]
        return [statistics.median(l[k] for l in lists) for k in range(H)]
    raise ValueError(method)


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--measure", default="qty_daneey", choices=["qty_daneey", "qty_all"])
    ap.add_argument("--mode", default="censored", choices=["raw", "censored"])
    ap.add_argument("--start", default="2024-06")
    ap.add_argument("--end", default="2026-04")
    args = ap.parse_args()

    series, full = load(args.measure)
    methods = ["naive", "seasonal_naive", "ma3", "ma6", "ma12", "M1", "M2", "M3", "M3b", "croston", "tsb", "ens3", "ens5"]
    origins = [m for m in months_between(args.start, args.end)]
    cells = []
    for origin in origins:
        for sku in sorted(series):
            hist = clean_hist(series, sku, origin, args.mode)
            if len(hist) < 6:
                continue
            targets = [madd(origin, k) for k in range(1, H + 1)]
            if args.mode == "censored" and any(t in CENSORED.get(sku, set()) for t in targets):
                continue
            actual = sum(series[sku].get(t, 0.0) for t in targets)
            for method in methods:
                pred = sum(forecast(series, sku, origin, method, args.mode))
                cells.append({
                    "origin": origin, "sku": sku, "method": method,
                    "actual": actual, "pred": pred, "abs": abs(pred - actual),
                })

    # 指标
    summary = {}
    for method in methods:
        rows = [c for c in cells if c["method"] == method]
        if not rows:
            continue
        sum_a = sum(c["actual"] for c in rows)
        sum_abs = sum(c["abs"] for c in rows)
        bias = (sum(c["pred"] for c in rows) - sum_a) / sum_a if sum_a else 0.0
        # 按 origin 聚合 WAPE，用于排名稳定性
        by_origin = defaultdict(lambda: [0.0, 0.0])
        for c in rows:
            by_origin[c["origin"]][0] += c["abs"]
            by_origin[c["origin"]][1] += c["actual"]
        origin_wapes = {o: (a / t) for o, (a, t) in by_origin.items() if t > 0}
        ranks = []
        # 每个 origin 内排名
        for o in origin_wapes:
            ordered = sorted(
                [(m, (sum(c["abs"] for c in cells if c["method"] == m and c["origin"] == o)
                     / max(1e-9, sum(c["actual"] for c in cells if c["method"] == m and c["origin"] == o))))
                 for m in methods if any(c["method"] == m and c["origin"] == o for c in cells)],
                key=lambda x: x[1],
            )
            for i, (m, _) in enumerate(ordered, 1):
                if m == method:
                    ranks.append(i)
        summary[method] = {
            "wape": sum_abs / sum_a if sum_a else None,
            "bias": bias,
            "n_cells": len(rows),
            "n_origins": len(origin_wapes),
            "top1": sum(1 for r in ranks if r == 1) / len(ranks) if ranks else None,
            "top3": sum(1 for r in ranks if r <= 3) / len(ranks) if ranks else None,
            "rank_std": statistics.pstdev(ranks) if len(ranks) > 1 else 0.0,
            "per_sku": {
                sku: {
                    "wape": (sum(c["abs"] for c in rows if c["sku"] == sku)
                             / max(1e-9, sum(c["actual"] for c in rows if c["sku"] == sku))),
                    "bias": ((sum(c["pred"] for c in rows if c["sku"] == sku)
                              - sum(c["actual"] for c in rows if c["sku"] == sku))
                             / max(1e-9, sum(c["actual"] for c in rows if c["sku"] == sku))),
                }
                for sku in sorted(series)
            },
        }

    out = {
        "measure": args.measure, "mode": args.mode,
        "origins": len(origins), "h": H,
        "cells": len(cells),
        "summary": summary,
    }
    (BASE / f"results_{args.measure}_{args.mode}.json").write_text(
        json.dumps(out, ensure_ascii=False, indent=2), encoding="utf-8")

    print(f"\n== {args.measure} / {args.mode} | origins={len(origins)} cells={len(cells)} ==")
    print(f"{'method':16} {'WAPE':>8} {'bias':>8} {'top1':>7} {'top3':>7} {'rank_sd':>8}")
    for m, s in sorted(summary.items(), key=lambda kv: kv[1]["wape"] if kv[1]["wape"] is not None else 9):
        print(f"{m:16} {s['wape']:8.3f} {s['bias']:8.3f} "
              f"{(s['top1'] or 0):7.2f} {(s['top3'] or 0):7.2f} {s['rank_std']:8.2f}")


if __name__ == "__main__":
    main()
