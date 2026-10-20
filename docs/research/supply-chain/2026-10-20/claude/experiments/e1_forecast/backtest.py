#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""E1 预测基线回测：PB 楔形枕 8 SKU（2026-10-20 修正版）。

修正要点（对应 review）：
1. TSB：概率 z 与需求规模 d 分开平滑；零需求期只衰减 z，d 保持不变。
2. 缺失 ≠ 0：按月表拉取状态 + SKU launch 月，给每个 SKU-月打
   observed / zero_confirmed / pre_launch / missing 标签；missing 不进训练。
3. 日期归属：解析 发货日期（YYYY-MM-DD、YYYY/M/D、datetime 等），
   按发货日期的月份聚合，不再用月表名或 date[:7]。
4. 最小训练长度：默认 ≥18 个已确认月；不足的 origin 丢弃并记录。
5. 验证/测试隔离：验证期选择方法，测试期只报告、不参与选择。
6. Croston classic：仅在非零需求期更新需求规模与间隔。

方法：naive / seasonal_naive / ma3 / ma6 / ma12 / M1 / M2 / M3 / M3b /
croston / tsb / ens3 / ens5。
"""

import argparse
import csv
import json
import re
import statistics
from collections import defaultdict
from datetime import datetime
from pathlib import Path

BASE = Path(__file__).resolve().parent
RAW = BASE / "data" / "wedge_raw.csv"
MONTHLY = BASE / "data" / "wedge_monthly.csv"
PULL_LOG = BASE / "data" / "pull_log.txt"
DATA_STATUS_OUT = BASE / "data_status.json"

CENSORED = {
    "2880": {"2026-03", "2026-04", "2026-05"},
    "2878": {"2026-06", "2026-07"},
    "2876": {"2026-05"},
}
H = 3
ALPHA = 0.3
DEFAULT_MIN_TRAIN = 18
CONFIRMED = {"observed", "zero_confirmed"}

DATE_PATTERNS = [
    re.compile(r"^(\d{4})-(\d{1,2})-(\d{1,2})(?:[ T].*)?$"),
    re.compile(r"^(\d{4})/(\d{1,2})/(\d{1,2})(?:[ T].*)?$"),
    re.compile(r"^(\d{4})\.(\d{1,2})\.(\d{1,2})(?:[ T].*)?$"),
    re.compile(r"^(\d{4})年(\d{1,2})月(\d{1,2})日?(?:[ T].*)?$"),
    re.compile(r"^(\d{4})-(\d{1,2})$"),
]


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


def parse_month(value):
    """把 发货日期 解析为 YYYY-MM；支持 ISO / YYYY/M/D / 点号 / datetime / 中文日期。

    解析失败返回 None（调用方记 parse_error，不得当作 0 需求）。
    """
    if value is None:
        return None
    if isinstance(value, datetime):
        return value.strftime("%Y-%m")
    s = str(value).strip()
    if not s:
        return None
    for pat in DATE_PATTERNS:
        m = pat.match(s)
        if m:
            y, mo = int(m.group(1)), int(m.group(2))
            if 1 <= mo <= 12:
                return mkey(y, mo)
            return None
    try:  # 兜底：Python datetime.fromisoformat 可吃 "2023-07-13 00:00:00"
        return datetime.fromisoformat(s.replace("/", "-")).strftime("%Y-%m")
    except ValueError:
        return None


def load_sheet_status():
    """从 pull_log 解析每月月表拉取状态；未列出的月份视为 missing。"""
    status = {}
    if not PULL_LOG.exists():
        return status, []
    lines = PULL_LOG.read_text(encoding="utf-8").splitlines()
    for line in lines:
        m = re.match(r"^通途订单(\d{4})(\d{2}):\s*(.*)$", line.strip())
        if not m:
            continue
        month = mkey(int(m.group(1)), int(m.group(2)))
        status[month] = "ok" if re.search(r"rows=\d+", line) else "failed"
    return status, lines


def load_raw():
    """按 发货日期 重新聚合到 SKU × 月；同时保留每月拉取状态。"""
    values = {"qty_all": defaultdict(float), "qty_daneey": defaultdict(float)}
    parse_errors = []
    with RAW.open(encoding="utf-8") as f:
        for row in csv.DictReader(f):
            month = parse_month(row.get("date"))
            if month is None:
                parse_errors.append({"date": row.get("date"), "sku": row.get("sku")})
                continue
            sku = str(row.get("sku", "")).strip()[-4:]
            try:
                qty = float(row.get("qty") or 0)
            except ValueError:
                qty = 0.0
            values["qty_all"][(sku, month)] += qty
            if "DANEEY" in str(row.get("warehouse", "")).upper():
                values["qty_daneey"][(sku, month)] += qty
    return values, parse_errors


def load_monthly_csv():
    """仅用于交叉校验 raw 重聚合结果；不参与计算。"""
    out = {}
    with MONTHLY.open(encoding="utf-8") as f:
        for row in csv.DictReader(f):
            out[(row["sku"], row["month"])] = (float(row["qty_all"]), float(row["qty_daneey"]))
    return out


def build_series(values):
    series = {"qty_all": defaultdict(dict), "qty_daneey": defaultdict(dict)}
    for measure, kv in values.items():
        for (sku, month), qty in kv.items():
            series[measure][sku][month] = qty
    return series


def measure_status(series, sheet_status, all_months, measure):
    """每个 SKU-月：missing / pre_launch / observed / zero_confirmed。

    - missing: 月表 OPEN_FAILED / BATCH_FAILED / 缺列 / 未拉取。
    - pre_launch: 早于该 SKU 首次发货月（用 qty_all 判定）；确认无需求，但不代表
      正常需求状态，训练时剔除。
    - observed: 该口径当月发货量 > 0。
    - zero_confirmed: 月表成功拉取、SKU 已上市、该口径当月为 0（含无行）。
    """
    launch = {}
    for sku in series["qty_all"]:
        months = [m for m, v in series["qty_all"][sku].items() if v > 0]
        launch[sku] = min(months) if months else None
    status = {}
    for sku in sorted(series["qty_all"]):
        status[sku] = {}
        for month in all_months:
            if sheet_status.get(month) != "ok":
                st = "missing"
            elif launch[sku] is None or month < launch[sku]:
                st = "pre_launch"
            elif series[measure][sku].get(month, 0.0) > 0:
                st = "observed"
            else:
                st = "zero_confirmed"
            status[sku][month] = st
    return status, launch


def clean_hist(series, status, sku, upto, mode):
    """origin 及以前、已确认（非 missing/pre_launch）的 [(month, value)]。"""
    out = []
    for month in sorted(series[sku]):
        if month > upto:
            break
        if status[sku].get(month) not in CONFIRMED:
            continue
        if mode == "censored" and month in CENSORED.get(sku, set()):
            continue
        out.append((month, series[sku][month]))
    return out


def naive_rate(hist):
    return hist[-1][1] if hist else 0.0


def ma_rate(hist, n):
    vals = [v for _, v in hist[-n:]]
    return sum(vals) / len(vals) if vals else 0.0


def seasonal_naive_month(target, hist_map, hist):
    return hist_map.get(madd(target, -12), naive_rate(hist))


def m2_month(target, hist, origin):
    hist_map = dict(hist)
    prev = madd(target, -12)
    if prev not in hist_map:
        return ma_rate(hist, 12)
    recent_months = months_between(madd(origin, -5), origin)
    prior_months = [madd(m, -12) for m in recent_months]
    recent = sum(hist_map.get(m, 0.0) for m in recent_months)
    prior = sum(hist_map.get(m, 0.0) for m in prior_months)
    r = recent / prior if prior > 0 else 1.0
    r = max(0.3, min(2.0, r))
    return hist_map[prev] * r


def m3_month(hist, target, origin):
    vals = [v for _, v in hist[-12:]]
    n = len(vals)
    if n < 6:
        return ma_rate(hist, 12)
    xs = list(range(n))
    mx = sum(xs) / n
    my = sum(vals) / n
    den = sum((x - mx) ** 2 for x in xs)
    slope = sum((x - mx) * (y - my) for x, y in zip(xs, vals)) / den if den else 0.0
    k = len(months_between(origin, target)) - 1
    return max(0.0, my + slope * (n - 1 - mx + k))


def m3b_month(target, hist):
    mm = target[5:7]
    vals = [v for m, v in hist if m[5:7] == mm]
    return statistics.mean(vals) if vals else ma_rate(hist, 12)


def croston_classic(hist, alpha=ALPHA):
    """经典 Croston（修正版）。

    变体：间隔 p 与需求规模 d 都只在非零需求期更新；p 为距上次非零需求的
    已确认月数（含零需求月，不含 missing/pre_launch 月）。首次非零时
    p=首次出现的间隔、d=首次需求量。预测 = d / p（每月需求率）。
    """
    if not hist:
        return 0.0
    size = None
    interval = None
    gap = 0
    for _, v in hist:
        gap += 1
        if v > 0:
            if size is None:
                size = v
                interval = gap
            else:
                size = alpha * v + (1 - alpha) * size
                interval = alpha * gap + (1 - alpha) * interval
            gap = 0
    if size is None or not interval:
        return 0.0
    return size / interval


def tsb(hist, alpha=ALPHA):
    """TSB（修正版）。

    z = 需求发生概率，初始化为非零期占比；d = 非零需求均值。
    非零期：z = α + (1-α)z, d = α·demand + (1-α)d。
    零需求期：z = (1-α)z，d 保持不变（不衰减到 0）。
    预测 = z·d。α = 0.3。
    """
    if not hist:
        return 0.0
    nz = [v for _, v in hist if v > 0]
    if not nz:
        return 0.0
    z = len(nz) / len(hist)
    d = sum(nz) / len(nz)
    for _, v in hist:
        if v > 0:
            z = alpha * 1.0 + (1 - alpha) * z
            d = alpha * v + (1 - alpha) * d
        else:
            z = (1 - alpha) * z  # d 不变
    return z * d


def forecast(hist, method, origin=None):
    hist_map = dict(hist)
    if not hist:
        return [0.0] * H
    if origin is None:
        origin = hist[-1][0]
    targets = [madd(origin, k) for k in range(1, H + 1)]
    if method == "naive":
        r = naive_rate(hist)
        return [r] * H
    if method == "seasonal_naive":
        return [seasonal_naive_month(t, hist_map, hist) for t in targets]
    if method.startswith("ma"):
        r = ma_rate(hist, int(method[2:]))
        return [r] * H
    if method == "M1":
        r = ma_rate(hist, 12)
        return [r] * H
    if method == "M2":
        return [m2_month(t, hist, origin) for t in targets]
    if method == "M3":
        return [m3_month(hist, t, origin) for t in targets]
    if method == "M3b":
        return [m3b_month(t, hist) for t in targets]
    if method == "croston":
        return [croston_classic(hist)] * H
    if method == "tsb":
        return [tsb(hist)] * H
    if method in ("ens3", "ens5"):
        comps = ["ma6", "croston", "tsb"] if method == "ens3" else [
            "ma3", "ma6", "ma12", "croston", "tsb"]
        lists = [forecast(hist, c, origin) for c in comps]
        return [statistics.median(l[k] for l in lists) for k in range(H)]
    raise ValueError(method)


def summarize(cells, methods):
    summary = {}
    for method in methods:
        rows = [c for c in cells if c["method"] == method]
        if not rows:
            continue
        sum_a = sum(c["actual"] for c in rows)
        sum_abs = sum(c["abs"] for c in rows)
        sum_pred = sum(c["pred"] for c in rows)
        by_origin = defaultdict(lambda: [0.0, 0.0])
        for c in rows:
            by_origin[c["origin"]][0] += c["abs"]
            by_origin[c["origin"]][1] += c["actual"]
        ranks = []
        for o in by_origin:
            ordered = sorted(
                [(m, _wape_for(cells, m, o)) for m in methods
                 if any(c["method"] == m and c["origin"] == o for c in cells)],
                key=lambda x: x[1],
            )
            for i, (m, _) in enumerate(ordered, 1):
                if m == method:
                    ranks.append(i)
        summary[method] = {
            "wape": sum_abs / sum_a if sum_a else None,
            "bias": (sum_pred - sum_a) / sum_a if sum_a else None,
            "n_cells": len(rows),
            "n_origins": len(by_origin),
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
                for sku in sorted({c["sku"] for c in rows})
            },
        }
    return summary


def _wape_for(cells, method, origin):
    rows = [c for c in cells if c["method"] == method and c["origin"] == origin]
    total = sum(c["actual"] for c in rows)
    return sum(c["abs"] for c in rows) / total if total else 9.99


def main():
    ap = argparse.ArgumentParser(description="E1 forecast backtest (corrected)")
    ap.add_argument("--measure", default="qty_daneey", choices=["qty_daneey", "qty_all"])
    ap.add_argument("--mode", default="censored", choices=["raw", "censored"])
    ap.add_argument("--start", default="2024-06")
    ap.add_argument("--end", default="2026-02")
    ap.add_argument("--val-start", default="2024-12")
    ap.add_argument("--val-end", default="2025-06")
    ap.add_argument("--test-start", default="2025-07")
    ap.add_argument("--test-end", default="2026-02")
    ap.add_argument("--min-train", type=int, default=DEFAULT_MIN_TRAIN)
    args = ap.parse_args()

    methods = ["naive", "seasonal_naive", "ma3", "ma6", "ma12", "M1", "M2",
               "M3", "M3b", "croston", "tsb", "ens3", "ens5"]
    singles = ["naive", "seasonal_naive", "ma3", "ma6", "ma12", "M1", "M2",
               "M3", "M3b", "croston", "tsb"]

    values, parse_errors = load_raw()
    series = build_series(values)
    monthly_csv = load_monthly_csv()
    sheet_status, pull_lines = load_sheet_status()
    all_months = sorted(sheet_status) if sheet_status else sorted(
        {m for kv in values["qty_all"].values() for m in kv})
    status, launch = measure_status(series, sheet_status, all_months, args.measure)
    # 已确认月显式落 0：zero_confirmed 是真实观测到的 0，missing/pre_launch 不进序列。
    series_m = {
        sku: {
            month: values[args.measure].get((sku, month), 0.0)
            for month in all_months
            if status[sku][month] in CONFIRMED
        }
        for sku in series[args.measure]
    }

    # 交叉校验：raw 按发货日期重聚合 vs 既有 wedge_monthly.csv
    mismatches = []
    for sku in sorted(series["qty_all"]):
        for month in all_months:
            raw_key = (sku, month)
            got = (series["qty_all"][sku].get(month, 0.0),
                   series["qty_daneey"][sku].get(month, 0.0))
            if raw_key in monthly_csv:
                exp = monthly_csv[raw_key]
                if abs(got[0] - exp[0]) > 1e-9 or abs(got[1] - exp[1]) > 1e-9:
                    mismatches.append({"sku": sku, "month": month,
                                       "raw": got, "monthly_csv": exp})

    origins = months_between(args.start, args.end)
    val_origins = set(months_between(args.val_start, args.val_end))
    test_origins = set(months_between(args.test_start, args.test_end))
    cells = []
    dropped = {"origin_no_sku": [], "sku_origin_insufficient_history": [],
               "sku_origin_missing_target": [], "sku_origin_censored": []}
    per_origin_sku = defaultdict(int)

    for origin in origins:
        for sku in sorted(series_m):
            hist = clean_hist(series_m, status, sku, origin, args.mode)
            if len(hist) < args.min_train:
                dropped["sku_origin_insufficient_history"].append(
                    {"origin": origin, "sku": sku, "n_hist": len(hist)})
                continue
            targets = [madd(origin, k) for k in range(1, H + 1)]
            if any(status[sku].get(t) not in CONFIRMED for t in targets):
                dropped["sku_origin_missing_target"].append({"origin": origin, "sku": sku})
                continue
            if args.mode == "censored" and any(t in CENSORED.get(sku, set()) for t in targets):
                dropped["sku_origin_censored"].append({"origin": origin, "sku": sku})
                continue
            actual = sum(series_m[sku].get(t, 0.0) for t in targets)
            per_origin_sku[origin] += 1
            for method in methods:
                pred = sum(forecast(hist, method, origin))
                cells.append({
                    "origin": origin, "sku": sku, "method": method,
                    "actual": actual, "pred": pred, "abs": abs(pred - actual),
                    "n_hist": len(hist),
                })

    for origin in origins:
        if per_origin_sku.get(origin, 0) == 0:
            dropped["origin_no_sku"].append(origin)

    val_cells = [c for c in cells if c["origin"] in val_origins]
    test_cells = [c for c in cells if c["origin"] in test_origins]
    combined_cells = val_cells + test_cells

    val_summary = summarize(val_cells, methods)
    test_summary = summarize(test_cells, methods)
    combined_summary = summarize(combined_cells, methods)
    if not val_summary:
        raise SystemExit("validation split has no cells; check dates/min-train")

    # 只在验证期选择；测试期不参与选择
    selected = min(val_summary, key=lambda m: val_summary[m]["wape"])
    val_singles_ranked = sorted(
        [m for m in singles if m in val_summary],
        key=lambda m: val_summary[m]["wape"])
    test_singles_ranked = sorted(
        [m for m in singles if m in test_summary],
        key=lambda m: test_summary[m]["wape"])
    report_methods = []
    for m in [selected, "ens5", "naive", *val_singles_ranked[:3]]:
        if m in test_summary and m not in report_methods:
            report_methods.append(m)
    test_report = {m: test_summary[m] for m in report_methods}
    oracle = (test_singles_ranked[0] if test_singles_ranked else None)

    # 数据状态汇总（两种口径都落盘，避免结果依赖最后一次运行的 measure）
    status_by_measure = {
        m: measure_status(series, sheet_status, all_months, m)[0]
        for m in ("qty_all", "qty_daneey")
    }
    status_counts = defaultdict(lambda: defaultdict(int))
    for measure, per_sku in status_by_measure.items():
        for months in per_sku.values():
            for st in months.values():
                status_counts[measure][st] += 1
    data_status = {
        "source": "data/wedge_raw.csv, aggregated by parsed 发货日期",
        "parse_errors": parse_errors[:50],
        "parse_error_count": len(parse_errors),
        "pull_log": {"months": all_months, "status": sheet_status},
        "monthly_csv_mismatches": mismatches,
        "classification": {
            "missing": "月表未拉取/打开失败/批量读取失败/缺列；不进训练，也不当 0",
            "pre_launch": "早于 SKU 首次发货月（按 qty_all 判定）；确认无货可发，但不代表正常需求，训练时剔除",
            "observed": "该口径当月发货量 > 0",
            "zero_confirmed": "月表成功拉取且 SKU 已上市、该口径当月为 0（含无行）",
        },
        "sku_month": {
            sku: {
                month: {
                    "status_qty_all": status_by_measure["qty_all"][sku][month],
                    "status_qty_daneey": status_by_measure["qty_daneey"][sku][month],
                    "qty_all": series["qty_all"][sku].get(month, 0.0),
                    "qty_daneey": series["qty_daneey"][sku].get(month, 0.0),
                    "censored": month in CENSORED.get(sku, set()),
                }
                for month in all_months
            }
            for sku in sorted(status)
        },
    }
    DATA_STATUS_OUT.write_text(json.dumps(data_status, ensure_ascii=False, indent=2),
                               encoding="utf-8")

    out = {
        "design": {
            "measure": args.measure, "mode": args.mode, "h": H,
            "min_train_months": args.min_train,
            "alpha_tsb": ALPHA, "alpha_croston": ALPHA,
            "origins": origins,
            "validation_origins": sorted(val_origins),
            "test_origins": sorted(test_origins),
            "selection": "fixed split: choose by validation WAPE, report on test",
            "dropped": dropped,
            "origins_with_cells": dict(sorted(per_origin_sku.items())),
        },
        "data_status_summary": {k: dict(v) for k, v in status_counts.items()},
        "launch_month": launch,
        "cells": len(cells),
        "validation": {
            "n_cells": len(val_cells),
            "n_origins": len({c["origin"] for c in val_cells}),
            "summary": val_summary,
        },
        "test": {
            "n_cells": len(test_cells),
            "n_origins": len({c["origin"] for c in test_cells}),
            "summary": test_summary,
        },
        "combined_reported": {
            "n_cells": len(combined_cells),
            "n_origins": len({c["origin"] for c in combined_cells}),
            "summary": combined_summary,
        },
        "selection": {
            "selected_by_validation": selected,
            "validation_wape": val_summary[selected]["wape"],
            "oracle_best_single_on_test": oracle,
            "oracle_test_wape": test_summary[oracle]["wape"] if oracle else None,
        },
        "test_report": test_report,
    }
    (BASE / f"results_{args.measure}_{args.mode}.json").write_text(
        json.dumps(out, ensure_ascii=False, indent=2), encoding="utf-8")

    print(f"\n== {args.measure} / {args.mode} | min_train={args.min_train} "
          f"| cells={len(cells)} ==")
    print(f"status: {dict(status_counts[args.measure])} | "
          f"parse_errors={len(parse_errors)} raw_vs_csv_mismatches={len(mismatches)}")
    print(f"origins: {len(origins)}; dropped no-SKU origins: {dropped['origin_no_sku']}")
    print(f"validation: origins={sorted(val_origins)} cells={len(val_cells)}")
    print(f"test:       origins={sorted(test_origins)} cells={len(test_cells)}")
    print(f"\n-- validation WAPE (method selection) --")
    print(f"{'method':16} {'WAPE':>8} {'bias':>8} {'n':>5}")
    for m, s in sorted(val_summary.items(), key=lambda kv: kv[1]["wape"]):
        print(f"{m:16} {s['wape']:8.3f} {s['bias']:8.3f} {s['n_cells']:5d}")
    print(f"\nselected by validation: {selected}")
    print(f"\n-- test report (held out) --")
    print(f"{'method':16} {'WAPE':>8} {'bias':>8} {'n':>5}")
    for m, s in sorted(test_report.items(), key=lambda kv: kv[1]["wape"]):
        print(f"{m:16} {s['wape']:8.3f} {s['bias']:8.3f} {s['n_cells']:5d}")
    if oracle:
        print(f"oracle best single on test (not selectable): {oracle} "
              f"WAPE={test_summary[oracle]['wape']:.3f}")
    print(f"\n-- combined reported origins (validation+test) --")
    print(f"{'method':16} {'WAPE':>8} {'bias':>8} {'n':>5}")
    for m in ["ens5", "ens3", "tsb", "croston", selected, "naive"]:
        if m in combined_summary:
            s = combined_summary[m]
            print(f"{m:16} {s['wape']:8.3f} {s['bias']:8.3f} {s['n_cells']:5d}")


if __name__ == "__main__":
    main()
