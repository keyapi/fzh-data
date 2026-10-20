#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""E1 预测基线回测：PB 楔形枕 8 SKU（2026-10-20 修正版，含 R01/R02）。

历史修正（上一轮）：
1. TSB：概率 z 与需求规模 d 分开平滑；零需求期只衰减 z，d 保持不变。
2. 缺失 ≠ 0：按月表拉取状态 + SKU launch 月，给每个 SKU-月打
   observed / zero_confirmed / pre_launch / missing 标签；missing 不进训练。
3. 日期归属：解析 发货日期（YYYY-MM-DD、YYYY/M/D、datetime 等），
   按发货日期的月份聚合，不再用月表名或 date[:7]。
4. 最小训练长度：默认 ≥18 个已确认月；不足的 origin 丢弃并记录。
5. 验证/测试隔离：验证期选择方法，测试期只报告、不参与选择。
6. Croston classic：仅在非零需求期更新需求规模与间隔。

本轮 R01（label knowability）：
- `--label-lag`（月，默认 1）：月份 m 的标签在 m + label_lag 的 1 日可用。
- origin t 的决策时点 = t + label_lag（1 日）。
- 验证/测试按「目标月不重叠」切分：val_end ≤ test_start − H（默认 2025-04）。
- 评估只使用标签已可用的目标月（h 仍为 3；不足时只评可用部分）。
- 结果 JSON 写入 label_overlap_check（交集必须为空，
  且验证期最晚目标可用时点 ≤ 最早测试决策时点）。
- TSB 初始化：z0 = 非零期占比，d0 = 非零期均值（全训练历史），
  然后按 α 平滑；零需求期 d 不变。附 golden 自测（--self-test）。

本轮 R02（数据质量）：
- 读取 pull_data 的 qty_status/qty_reason；qty 为空或 bad 的行跳过，
  不转 0；若某 SKU-月存在任何 bad 行，则该 SKU-月标记 bad_data，
  从训练与评估中剔除。
- data_status.json 与结果 JSON 均写入 data_quality（bad 行数、
  SKU-月清单、逐月 source_rows/extracted_rows、完整性 caveat）。

方法：naive / seasonal_naive / ma3 / ma6 / ma12 / M1 / M2 / M3 / M3b /
croston / tsb / ens3 / ens5。
"""

import argparse
import csv
import json
import math
import re
import statistics
from collections import Counter, defaultdict
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
DEFAULT_LABEL_LAG = 1
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


def label_available_month(month, lag):
    """月份 month 的标签可用时点（该月 1 日）：month + lag。"""
    return madd(month, lag)


def decision_at(origin, lag):
    """origin t 的决策时点（该月 1 日）：t + lag。"""
    return madd(origin, lag)


def _pick_int(rest, name):
    m = re.search(rf"(?:^|\s){name}=(\d+)", rest)
    return int(m.group(1)) if m else None


def load_sheet_status():
    """从 pull_log 解析每月月表拉取状态与逐月读取计数。

    ok 判定：行内有 source_rows=<int>（本次格式）；旧格式 rows=<int> 兼容。
    未列出的月份视为 missing。
    """
    status = {}
    counts = {}
    if not PULL_LOG.exists():
        return status, [], counts
    lines = PULL_LOG.read_text(encoding="utf-8").splitlines()
    for line in lines:
        m = re.match(r"^通途订单(\d{4})(\d{2}):\s*(.*)$", line.strip())
        if not m:
            continue
        month = mkey(int(m.group(1)), int(m.group(2)))
        rest = m.group(3)
        source_rows = _pick_int(rest, "source_rows")
        if source_rows is not None or re.search(r"\brows=\d+", rest):
            status[month] = "ok"
        else:
            status[month] = "failed"
        mismatch = re.search(r"col_mismatch=(yes|no)", rest)
        reasons = re.search(r"bad_reasons=([^\s]+)", rest)
        counts[month] = {
            "source_rows": source_rows,
            "extracted_rows": _pick_int(rest, "extracted_rows"),
            "blank_tail": _pick_int(rest, "blank_tail"),
            "hits": _pick_int(rest, "hits"),
            "empty_date": _pick_int(rest, "empty_date"),
            "bad_qty": _pick_int(rest, "bad_qty"),
            "bad_date": _pick_int(rest, "bad_date"),
            "bad_reasons": reasons.group(1) if reasons else None,
            "column_length_mismatch": (mismatch.group(1) == "yes") if mismatch else None,
        }
    return status, lines, counts


def load_raw():
    """按 发货日期 重新聚合到 SKU × 月。

    返回 values, parse_errors, bad_rows, bad_months。
    - qty_status=bad 或 qty 为空：跳过该行（不转 0），记入 bad_rows，
      并把对应 SKU-月加入 bad_months（日期可解析时）。
    - 日期解析失败：记入 parse_errors，不进入聚合。
    """
    values = {"qty_all": defaultdict(float), "qty_daneey": defaultdict(float)}
    parse_errors = []
    bad_rows = []
    bad_months = set()
    with RAW.open(encoding="utf-8") as f:
        for row in csv.DictReader(f):
            date = row.get("date")
            sku_raw = str(row.get("sku") or "").strip()
            if not sku_raw:
                continue
            sku = sku_raw[-4:]
            month = parse_month(date)
            qraw = row.get("qty")
            qstatus = str(row.get("qty_status") or "").strip().lower()
            qtxt = "" if qraw is None else str(qraw).strip()
            qty = None
            reason = ""
            if qstatus == "bad" or qtxt == "":
                reason = str(row.get("qty_reason") or "").strip() or (
                    "bad" if qstatus == "bad" else "blank")
            else:
                try:
                    qty = float(qtxt)
                except ValueError:
                    reason = "non_numeric"
                else:
                    if not math.isfinite(qty):
                        reason = "non_finite"
                        qty = None
                    elif qty < 0:
                        reason = "negative"
                        qty = None
                    elif qty != int(qty):
                        reason = "non_integer_pieces"
                        qty = None
            if qty is None:
                bad_rows.append({"date": date, "sku": sku,
                                 "month": month or "", "reason": reason})
                if month:
                    bad_months.add((sku, month))
                continue
            if month is None:
                parse_errors.append({"date": date, "sku": sku})
                continue
            values["qty_all"][(sku, month)] += qty
            if "DANEEY" in str(row.get("warehouse", "")).upper():
                values["qty_daneey"][(sku, month)] += qty
    return values, parse_errors, bad_rows, bad_months


def load_monthly_csv():
    """仅用于交叉校验 raw 重聚合结果；不参与计算。"""
    out = {}
    with MONTHLY.open(encoding="utf-8") as f:
        for row in csv.DictReader(f):
            out[(row["sku"], row["month"])] = (
                float(row["qty_all"]), float(row["qty_daneey"]))
    return out


def build_series(values):
    series = {"qty_all": defaultdict(dict), "qty_daneey": defaultdict(dict)}
    for measure, kv in values.items():
        for (sku, month), qty in kv.items():
            series[measure][sku][month] = qty
    return series


def measure_status(series, sheet_status, all_months, measure, bad_months):
    """每个 SKU-月：missing / bad_data / pre_launch / observed / zero_confirmed。

    - missing: 月表 OPEN_FAILED / BATCH_FAILED / 缺列 / 未拉取。
    - bad_data: 该 SKU-月存在任一非法数量行；数量不可信，训练与评估都剔除。
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
            elif (sku, month) in bad_months:
                st = "bad_data"
            elif launch[sku] is None or month < launch[sku]:
                st = "pre_launch"
            elif series[measure][sku].get(month, 0.0) > 0:
                st = "observed"
            else:
                st = "zero_confirmed"
            status[sku][month] = st
    return status, launch


def clean_hist(series, status, sku, upto, mode):
    """origin 及以前、已确认（非 missing/bad_data/pre_launch）的 [(month, value)]。"""
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
    """TSB（修正版，初始化沿用既有实现，未确认与成熟库存在 bug）。

    初始化（全训练历史，一次）：
      z0 = 非零需求期数 / 已确认期数
      d0 = 非零需求量之和 / 非零期数
    随后逐期平滑：
      非零期：z = α + (1−α)z, d = α·v + (1−α)d
      零需求：z = (1−α)z, d 保持不变
    预测 = z·d，α = 0.3。

    golden（见 self_test）：
      [0, 5, 0, 10] → 4.38046125
      [3]          → 3.0
      [0, 0]       → 0.0
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


def self_test():
    """TSB / Croston 的 golden 短序列自测；返回可写入 JSON 的用例列表。"""
    cases = []

    def check(name, got, want, tol=1e-6):
        cases.append({"case": name, "got": got, "expected": want,
                      "pass": abs(got - want) <= tol})

    seq = [("2023-01", 0.0), ("2023-02", 5.0), ("2023-03", 0.0), ("2023-04", 10.0)]
    check("tsb [0,5,0,10]", tsb(seq), 4.38046125)
    check("tsb [3]", tsb([("2023-01", 3.0)]), 3.0)
    check("tsb [0,0]", tsb([("2023-01", 0.0), ("2023-02", 0.0)]), 0.0)
    check("croston [0,5,0,10]", croston_classic(seq), 3.25)
    return cases


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
    ap = argparse.ArgumentParser(description="E1 forecast backtest (corrected R01/R02)")
    ap.add_argument("--measure", default="qty_daneey", choices=["qty_daneey", "qty_all"])
    ap.add_argument("--mode", default="censored", choices=["raw", "censored"])
    ap.add_argument("--start", default="2024-06")
    ap.add_argument("--end", default="2026-02")
    ap.add_argument("--val-start", default="2024-12")
    ap.add_argument("--val-end", default="2025-04")
    ap.add_argument("--test-start", default="2025-07")
    ap.add_argument("--test-end", default="2026-02")
    ap.add_argument("--min-train", type=int, default=DEFAULT_MIN_TRAIN)
    ap.add_argument("--label-lag", type=int, default=DEFAULT_LABEL_LAG,
                    help="label for month m is available at m+lag (first day)")
    ap.add_argument("--data-end", default=None,
                    help="last pulled month (YYYY-MM); default = max month in pull_log")
    ap.add_argument("--self-test", action="store_true")
    args = ap.parse_args()

    st_cases = self_test()
    if args.self_test:
        for c in st_cases:
            print(f"{'PASS' if c['pass'] else 'FAIL'} {c['case']}: "
                  f"got={c['got']!r} expected={c['expected']!r}")
        raise SystemExit(0 if all(c["pass"] for c in st_cases) else 1)
    if not all(c["pass"] for c in st_cases):
        raise SystemExit(f"self-test failed: {st_cases}")

    methods = ["naive", "seasonal_naive", "ma3", "ma6", "ma12", "M1", "M2",
               "M3", "M3b", "croston", "tsb", "ens3", "ens5"]
    singles = ["naive", "seasonal_naive", "ma3", "ma6", "ma12", "M1", "M2",
               "M3", "M3b", "croston", "tsb"]

    values, parse_errors, bad_rows, bad_months = load_raw()
    series = build_series(values)
    monthly_csv = load_monthly_csv()
    sheet_status, pull_lines, sheet_counts = load_sheet_status()
    all_months = sorted(sheet_status) if sheet_status else sorted(
        {m for kv in values["qty_all"].values() for m in kv})
    data_end = args.data_end or (all_months[-1] if all_months else None)
    if data_end is None:
        raise SystemExit("cannot determine data end month")
    # 拉取时点：最后一张月表所属月结束后的次月 1 日
    now_month = madd(data_end, 1)
    latest_label_month = madd(data_end, 1 - args.label_lag)

    status, launch = measure_status(
        series, sheet_status, all_months, args.measure, bad_months)
    # 已确认月显式落 0：zero_confirmed 是真实观测到的 0，
    # missing/bad_data/pre_launch 不进序列。
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

    # ---- R01: split with label knowability ----
    max_val_end = madd(args.test_start, -H)
    val_end = args.val_end
    split_adjustment = None
    if val_end > max_val_end:
        split_adjustment = {
            "requested_val_end": val_end,
            "applied_val_end": max_val_end,
            "reason": "val_end must be <= test_start - H so validation targets "
                      "do not overlap test targets",
        }
        val_end = max_val_end
    if args.val_start > val_end:
        raise SystemExit(
            f"invalid split: val_start {args.val_start} > val_end {val_end}")
    if args.test_start > args.test_end:
        raise SystemExit("invalid split: test_start > test_end")

    origins = months_between(args.start, args.end)
    val_origins = set(months_between(args.val_start, val_end))
    test_origins = set(months_between(args.test_start, args.test_end))

    def window_targets(origin_set):
        return sorted({madd(o, k) for o in origin_set for k in range(1, H + 1)})

    val_target_months = window_targets(val_origins)
    test_target_months = window_targets(test_origins)
    target_intersection = sorted(set(val_target_months) & set(test_target_months))
    max_val_target = val_target_months[-1] if val_target_months else None
    max_val_available = (label_available_month(max_val_target, args.label_lag)
                         if max_val_target else None)
    min_test_decision = (decision_at(min(test_origins), args.label_lag)
                         if test_origins else None)
    overlap_pass = (
        not target_intersection
        and max_val_available is not None
        and min_test_decision is not None
        and max_val_available <= min_test_decision
    )
    label_overlap_check = {
        "label_lag_months": args.label_lag,
        "data_end_month": data_end,
        "pull_as_of_month": now_month,
        "labels_available_through": latest_label_month,
        "validation_origins": sorted(val_origins),
        "validation_target_months": val_target_months,
        "test_origins": sorted(test_origins),
        "test_target_months": test_target_months,
        "target_month_intersection": target_intersection,
        "max_validation_target": max_val_target,
        "max_validation_available_at": max_val_available,
        "min_test_decision_at": min_test_decision,
        "definition": "label for month m available at m+label_lag (first day); "
                      "decision for origin t at t+label_lag (first day)",
        "pass": overlap_pass,
    }
    if not overlap_pass:
        raise SystemExit(
            "label_overlap_check failed: " +
            json.dumps(label_overlap_check, ensure_ascii=False))

    cells = []
    dropped = {"origin_no_sku": [], "sku_origin_insufficient_history": [],
               "sku_origin_missing_target": [], "sku_origin_bad_target": [],
               "sku_origin_no_available_label": [], "sku_origin_censored": []}
    per_origin_sku = defaultdict(int)

    for origin in origins:
        for sku in sorted(series_m):
            hist = clean_hist(series_m, status, sku, origin, args.mode)
            if len(hist) < args.min_train:
                dropped["sku_origin_insufficient_history"].append(
                    {"origin": origin, "sku": sku, "n_hist": len(hist)})
                continue
            targets = [(k, madd(origin, k)) for k in range(1, H + 1)]
            scored = [
                (k, t) for k, t in targets
                if label_available_month(t, args.label_lag) <= now_month
            ]
            if not scored:
                dropped["sku_origin_no_available_label"].append(
                    {"origin": origin, "sku": sku})
                continue
            if any(status[sku].get(t) == "bad_data" for _, t in scored):
                dropped["sku_origin_bad_target"].append({"origin": origin, "sku": sku})
                continue
            if any(status[sku].get(t) not in CONFIRMED for _, t in scored):
                dropped["sku_origin_missing_target"].append({"origin": origin, "sku": sku})
                continue
            if args.mode == "censored" and any(
                    t in CENSORED.get(sku, set()) for _, t in scored):
                dropped["sku_origin_censored"].append({"origin": origin, "sku": sku})
                continue
            actual = sum(series_m[sku].get(t, 0.0) for _, t in scored)
            per_origin_sku[origin] += 1
            for method in methods:
                full = forecast(hist, method, origin)
                pred = sum(full[k - 1] for k, _ in scored)
                cells.append({
                    "origin": origin, "sku": sku, "method": method,
                    "actual": actual, "pred": pred, "abs": abs(pred - actual),
                    "n_hist": len(hist), "n_scored_h": len(scored),
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
        m: measure_status(series, sheet_status, all_months, m, bad_months)[0]
        for m in ("qty_all", "qty_daneey")
    }
    status_counts = defaultdict(lambda: defaultdict(int))
    for measure, per_sku in status_by_measure.items():
        for months in per_sku.values():
            for st in months.values():
                status_counts[measure][st] += 1
    data_quality = {
        "bad_rows_count": len(bad_rows),
        "bad_sku_month_count": len(bad_months),
        "bad_sku_months": sorted(f"{s}@{m}" for s, m in bad_months),
        "bad_rows_sample": bad_rows[:200],
        "gate_exercised": bool(bad_rows),
        "gate": "row kept in raw with qty blank + qty_status=bad; "
                "any bad row marks the SKU-month bad_data and excludes it "
                "from training/evaluation; never converted to 0",
        "sheet_counts": sheet_counts,
        "source_rows_note": "source_rows = sheet row_count including header; "
                            "extracted_rows = aligned data rows read (row 2..N). "
                            "A successful sheet read does not prove all cross-month "
                            "shipment rows exist; counts are logged per month for audit.",
        "completeness_caveat": "月表读取成功 ≠ 跨月发货行完整；本实验不声称数据完整，"
                               "仅逐月记录 source_rows/extracted_rows/blank_tail 供核对。",
    }
    data_status = {
        "source": "data/wedge_raw.csv, aggregated by parsed 发货日期",
        "parse_errors": parse_errors[:50],
        "parse_error_count": len(parse_errors),
        "pull_log": {"months": all_months, "status": sheet_status},
        "monthly_csv_mismatches": mismatches,
        "data_quality": data_quality,
        "classification": {
            "missing": "月表未拉取/打开失败/批量读取失败/缺列；不进训练，也不当 0",
            "bad_data": "该 SKU-月存在非法数量行（空/非数字/负数/非有限/非整数件）；"
                        "数量不可信，训练与评估都剔除，不转 0",
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

    def scored_hist(cell_list):
        return {str(k): v for k, v in sorted(
            Counter(c["n_scored_h"] for c in cell_list).items())}

    out = {
        "design": {
            "measure": args.measure, "mode": args.mode, "h": H,
            "label_lag_months": args.label_lag,
            "data_end_month": data_end,
            "pull_as_of_month": now_month,
            "labels_available_through": latest_label_month,
            "min_train_months": args.min_train,
            "alpha_tsb": ALPHA, "alpha_croston": ALPHA,
            "origins": origins,
            "validation_origins": sorted(val_origins),
            "test_origins": sorted(test_origins),
            "split_rule": "val_end <= test_start - H; at run time val_end is "
                          "clamped to test_start - H if needed",
            "split_adjustment": split_adjustment,
            "selection": "fixed split: choose by validation WAPE, report on test",
            "scoring": "h=3 forecast window; only target months with "
                       "m+label_lag <= pull_as_of are scored",
            "tsb_init": "z0=nonzero fraction, d0=mean of nonzero demands over "
                        "full training history, then smooth; d unchanged on zeros",
            "dropped": dropped,
            "origins_with_cells": dict(sorted(per_origin_sku.items())),
        },
        "label_overlap_check": label_overlap_check,
        "self_test": {
            "passed": all(c["pass"] for c in st_cases),
            "cases": st_cases,
        },
        "data_quality": data_quality,
        "data_status_summary": {k: dict(v) for k, v in status_counts.items()},
        "launch_month": launch,
        "cells": len(cells),
        "validation": {
            "n_cells": len(val_cells),
            "n_origins": len({c["origin"] for c in val_cells}),
            "scored_h_hist": scored_hist(val_cells),
            "summary": val_summary,
        },
        "test": {
            "n_cells": len(test_cells),
            "n_origins": len({c["origin"] for c in test_cells}),
            "scored_h_hist": scored_hist(test_cells),
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
          f"| label_lag={args.label_lag} | cells={len(cells)} ==")
    print(f"status: {dict(status_counts[args.measure])} | "
          f"parse_errors={len(parse_errors)} raw_vs_csv_mismatches={len(mismatches)} "
          f"bad_rows={len(bad_rows)} bad_sku_months={len(bad_months)}")
    print(f"label_overlap_check: pass={overlap_pass} "
          f"val_targets={val_target_months[0]}..{val_target_months[-1]} "
          f"test_targets={test_target_months[0]}..{test_target_months[-1]} "
          f"intersection={target_intersection} "
          f"max_val_available={max_val_available} min_test_decision={min_test_decision}")
    print(f"origins: {len(origins)}; dropped no-SKU origins: {dropped['origin_no_sku']}")
    print(f"validation: origins={sorted(val_origins)} cells={len(val_cells)} "
          f"scored_h={scored_hist(val_cells)}")
    print(f"test:       origins={sorted(test_origins)} cells={len(test_cells)} "
          f"scored_h={scored_hist(test_cells)}")
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
    combined_print = []
    for m in ["ens5", "ens3", "tsb", "croston", selected, "naive"]:
        if m in combined_summary and m not in combined_print:
            combined_print.append(m)
    for m in combined_print:
        if m in combined_summary:
            s = combined_summary[m]
            print(f"{m:16} {s['wape']:8.3f} {s['bias']:8.3f} {s['n_cells']:5d}")


if __name__ == "__main__":
    main()
