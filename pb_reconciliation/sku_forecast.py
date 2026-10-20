#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""PB 商品 SKU 销量预估（基于 Invoice to PB 的 PO 下单量）。

从给财务对账表 "Invoice to PB" 提取指定 Vendor Style 的月度 PO 下单量（销量代理），
用 3 种方法预估未来 N 个月的销量并对比：
  M1 运行率     最近 12 个月平均月量 × 月份数，附 ±25% 区间
  M2 同比窗口   去年同期同月份窗口 × 近期同比调整系数（体现下滑趋势）
  M3 线性趋势   对月度序列做线性回归外推（附低销量过拟合提示）

用法：
    uv run python pb_reconciliation/sku_forecast.py --sku CENKZ1325-YELLOW-97
    uv run python pb_reconciliation/sku_forecast.py --sku CENKZ1325-YELLOW-97 --write
    uv run python pb_reconciliation/sku_forecast.py --sku A,B --months 6 --include-family --write
    uv run python pb_reconciliation/sku_forecast.py --sku CENKZ1325-YELLOW-97 --start 2026-09

SKU 匹配大小写不敏感（数据里为全大写，如 CENKZ1325-YELLOW-97）。
输出到 OUT_DIR：xlsx（历史月度 + 三方法对比 + 方法说明）+ md（中文说明，可转发补货同事）。
"""

import argparse
import datetime
import glob
import os

import numpy as np
import openpyxl
from openpyxl.styles import Alignment, Font, PatternFill

# ================= 参数（下次数据换文件时改这里） =================
BASE_DIR = r"D:\Work\美国\Tracy Miller\PB orders"
PAYMENT_SUBDIR = "给财务"
# 定位给财务目录下的主对账文件（时间戳后缀），排除"验证"副本
PB_WB_GLOB = os.path.join(BASE_DIR, "payment advice", PAYMENT_SUBDIR, "*20260814_171350.xlsx")
OUT_DIR = os.path.join(BASE_DIR, "sales_forecast")
DEFAULT_MONTHS = 6
# ==============================================================

INV_SHEET = "Invoice to PB"
COL_INVOICE = 0
COL_PO_DATE = 4      # 列 E：PO Date（H 行）
COL_QTY = 12         # 列 M：Qty Ordered（D 行）
COL_STYLE = 17       # 列 R：Vendor Style（D 行）
COL_RECORD_TYPE = 23  # 列 X：Record Type = H / D

BOLD = Font(bold=True)
CENTER = Alignment(horizontal="center")
HDR_FILL = PatternFill(start_color="FFDDEBF7", end_color="FFDDEBF7", fill_type="solid")


def add_months(y, m, k):
    t = y * 12 + (m - 1) + k
    return t // 12, t % 12 + 1


def parse_po_date(v):
    """PO Date 为 MM/DD/YYYY 文本或 datetime，返回 (year, month)；无法解析返回 (None, None)。"""
    if isinstance(v, datetime.datetime):
        return v.year, v.month
    if isinstance(v, (int, float)):
        return None, None
    s = str(v).strip()
    parts = s.split("/")
    if len(parts) == 3:
        try:
            return int(parts[2]), int(parts[0])
        except ValueError:
            pass
    return None, None


def to_int(v):
    try:
        return int(float(v))
    except (TypeError, ValueError):
        return 0


def find_workbook():
    cands = [f for f in glob.glob(PB_WB_GLOB) if not os.path.basename(f).startswith("验证")]
    if not cands:
        raise SystemExit(f"未找到对账文件: {PB_WB_GLOB}")
    return sorted(cands)[-1]


def scan_rows(path):
    """遍历 Invoice to PB，产出 (record_type, invoice, po_date, style, qty)。跳过全空行。"""
    wb = openpyxl.load_workbook(path, data_only=True, read_only=True)
    try:
        ws = wb[INV_SHEET]
        for row in ws.iter_rows(values_only=True):
            if row is None or len(row) <= COL_RECORD_TYPE:
                continue
            rt = row[COL_RECORD_TYPE]
            if rt == "H":
                yield "H", row[COL_INVOICE], row[COL_PO_DATE], None, None
            elif rt == "D":
                style = row[COL_STYLE] if len(row) > COL_STYLE else None
                qty = to_int(row[COL_QTY]) if len(row) > COL_QTY else 0
                yield "D", row[COL_INVOICE], None, style, qty
    finally:
        wb.close()


def load_series(path, sku_upper):
    """返回 {(year, month): qty}。记录行数同时返回。"""
    series = {}
    inv_po = {}
    n_rows = 0
    for rt, inv, pod, style, qty in scan_rows(path):
        if rt == "H":
            inv_po[inv] = pod
        elif style is not None and str(style).strip().upper() == sku_upper:
            y, m = parse_po_date(inv_po.get(inv))
            if y is not None:
                series[(y, m)] = series.get((y, m), 0) + qty
                n_rows += 1
    return series, n_rows


def load_family(path, prefix_upper):
    """返回 {style_upper: {(y,m): qty}}，匹配前缀（用于同族尺寸对照）。"""
    family = {}
    inv_po = {}
    for rt, inv, pod, style, qty in scan_rows(path):
        if rt == "H":
            inv_po[inv] = pod
        elif style is not None:
            s = str(style).strip().upper()
            if s.startswith(prefix_upper):
                y, m = parse_po_date(inv_po.get(inv))
                if y is not None:
                    fam = family.setdefault(s, {})
                    fam[(y, m)] = fam.get((y, m), 0) + qty
    return family


def dense_months(series):
    ks = sorted(series)
    if not ks:
        return []
    out = []
    y, m = ks[0]
    while (y, m) <= ks[-1]:
        out.append(((y, m), series.get((y, m), 0)))
        y, m = add_months(y, m, 1)
    return out


def yearly_totals(series):
    tot = {}
    for (y, m), q in series.items():
        tot[y] = tot.get(y, 0) + q
    return tot


def method_runrate(series, n):
    """M1 运行率：最近 12 个月平均月量 × n，±25% 区间。"""
    d = dense_months(series)
    if len(d) < 6:
        return None
    last = d[-12:]
    rate = sum(q for _, q in last) / len(last)
    mid = rate * n
    return {"name": "M1 运行率", "mid": mid, "low": mid * 0.75, "high": mid * 1.25,
            "detail": {"rate12": rate, "last12_sum": sum(q for _, q in last)}}


def method_yoy(series, window):
    """M2 同比窗口：去年同期同月份窗口量 × 近期同比调整系数。"""
    wlast = [(y - 1, m) for y, m in window]
    wprev = [(y - 2, m) for y, m in window]
    anchor = sum(series.get(k, 0) for k in wlast)
    prevwin = sum(series.get(k, 0) for k in wprev)
    y = window[0][0]
    common = list(range(1, 7))  # 1-6 月两年均完整
    cur_ytd = sum(series.get((y, m), 0) for m in common)
    last_ytd = sum(series.get((y - 1, m), 0) for m in common)
    r_win = (anchor / prevwin) if prevwin else 1.0
    r_ytd = (cur_ytd / last_ytd) if last_ytd else 1.0
    adj = (r_win + r_ytd) / 2
    mid = anchor * adj
    return {"name": "M2 同比窗口", "mid": mid, "low": mid * 0.75, "high": mid * 1.25,
            "detail": {"anchor_last_year": anchor, "prev_window": prevwin,
                       "r_window": r_win, "r_ytd": r_ytd, "adj": adj}}


def method_trend(series, window):
    """M3 线性趋势：对月度序列做一次线性回归外推。低销量下易过拟合。"""
    d = dense_months(series)
    if len(d) < 3:
        return None
    xs = np.arange(len(d))
    ys = np.array([q for _, q in d], dtype=float)
    slope, intercept = np.polyfit(xs, ys, 1)
    preds = [max(0.0, slope * (len(d) + i) + intercept) for i in range(len(window))]
    mid = float(sum(preds))
    return {"name": "M3 线性趋势", "mid": mid, "low": mid * 0.75, "high": mid * 1.25,
            "detail": {"slope_per_month": slope, "intercept": intercept, "preds": preds}}


def method_seasonal_avg(series, window):
    """M3b 季节平均：窗口内各月用历年同月平均（仅作为交叉参考）。"""
    total = 0.0
    nz = 0
    for y, m in window:
        vals = [series.get((yy, m), 0) for yy in range(y - 2, y + 1)]
        vals = [v for v in vals if v > 0]
        if vals:
            total += sum(vals) / len(vals)
            nz += 1
    return {"name": "M3b 季节平均", "mid": total, "low": total * 0.75, "high": total * 1.25,
            "detail": {"months_with_data": nz}}


def fmt(v):
    return f"{v:.0f}"


def build_xlsx(path, sku, window, monthly, years, methods, rec, family=None):
    wb = openpyxl.Workbook()

    # sheet1 历史月度
    ws = wb.active
    ws.title = "历史月度"
    ws.append(["年月", "PO 下单量(件)", "年度小计", "备注"])
    for c in ws[1]:
        c.font = BOLD
        c.fill = HDR_FILL
        c.alignment = CENTER
    last_key = sorted(monthly)[-1][0] if monthly else None
    for (y, m), q in monthly:
        row = [f"{y}-{m:02d}", q]
        if m == 12:
            row += [years.get(y, 0), "年度小计" if m == 12 else ""]
        else:
            row += ["", ""]
        if (y, m) == last_key:
            row[3] = "部分月(数据截止当期)"
        ws.append(row)
        for c in ws[ws.max_row]:
            c.alignment = Alignment(horizontal="center")
    ws.append(["合计", "", sum(years.values()), ""])
    ws.append([])
    ws.append(["按年合计"])
    for y in sorted(years):
        ws.append([f"{y}", "", years[y]])

    # sheet2 三方法对比
    ws2 = wb.create_sheet("三方法对比")
    ws2.append(["方法", "中间值(件)", "低(件)", "高(件)", "说明/口径"])
    for c in ws2[1]:
        c.font = BOLD
        c.fill = HDR_FILL
    ws2.append(["预估窗口", f"{window[0][0]}-{window[0][1]:02d} ~ {window[-1][0]}-{window[-1][1]:02d}",
                "", "", f"共 {len(window)} 个月"])
    for m in methods:
        if m is None:
            continue
        ws2.append([m["name"], round(m["mid"], 1), round(m["low"], 1), round(m["high"], 1),
                    _method_note(m)])
    ws2.append([])
    ws2.append(["推荐值", rec["mid"], rec["low"], rec["high"],
                "M1/M2 折中，区间覆盖各方法低高"])
    ws2.append(["建议备货量(含缓冲)", rec["rec"], "", "",
                "按推荐值上浮约20%覆盖断货/波动风险"])
    for r in ws2.iter_rows(min_row=2):
        for c in r:
            if c.column in (2, 3, 4) and c.value is not None:
                c.alignment = Alignment(horizontal="center")

    # sheet3 方法说明
    ws3 = wb.create_sheet("方法说明")
    notes = [
        ("M1 运行率", "最近 12 个月平均月量 × 窗口月数，附 ±25% 区间。最直白，反映当前节奏。"),
        ("M2 同比窗口", "去年同期同月份窗口的销量 × 近期同比调整系数。调整系数 = (2026 上半年/2025 上半年) 与 (上次窗口/上上次窗口) 的平均，体现下滑趋势。"),
        ("M3 线性趋势", "对月度序列做一次线性回归并外推。样本小、波动大时容易过拟合，结果仅供参考。"),
        ("M3b 季节平均", "窗口内各月取历年同月平均。季节规律在此销量级别不明显，仅作交叉参考。"),
        ("推荐值", "M1 与 M2 中间值取平均；区间取各方法低点与高点。"),
        ("局限-断货", "PO 下单量是已开票/已发货的量；若期间断货，未满足的订单不入账，真实需求可能高于预估。当前无库存备份数据可量化。"),
        ("局限-滞后", "近期 PO（数据截止月前后）可能尚未开票入表，最近月量略被低估。"),
        ("局限-样本小", "月量 0-13 件、数据仅约两年多，预估仅供备货参考，建议留缓冲并定期复核。"),
        ("未来增强", "通途订单 API（tongtool_order_cost 项目）可交叉核对/辅助预测；脚本序列读取已独立成函数，后续可加数据源。"),
    ]
    for a, b in notes:
        ws3.append([a, b])
        ws3.cell(ws3.max_row, 1).font = BOLD

    if family:
        wsf = wb.create_sheet("家族对照")
        wsf.append(["Style", "2024 合计", "2025 合计", "2026 YTD", "近12月速率/月", "6个月预估(运行率)"])
        for c in wsf[1]:
            c.font = BOLD
            c.fill = HDR_FILL
        for sty, s in sorted(family.items()):
            yt = yearly_totals(s)
            d = dense_months(s)
            last12 = d[-12:]
            rate = sum(q for _, q in last12) / len(last12) if len(last12) else 0
            wsf.append([sty, yt.get(2024, 0), yt.get(2025, 0),
                        sum(q for (yy, _), q in s.items() if yy == 2026),
                        round(rate, 1), round(rate * len(window), 1)])

    wb.save(path)


def _method_note(m):
    d = m["detail"]
    if m["name"] == "M1 运行率":
        return f"近12月合计 {d['last12_sum']:.0f}，速率 {d['rate12']:.2f} 件/月"
    if m["name"] == "M2 同比窗口":
        return (f"去年同期 {d['anchor_last_year']:.0f} 件；窗口同比 {d['r_window']:.2f}，"
                f"YTD 同比 {d['r_ytd']:.2f}，调整 {d['adj']:.2f}")
    if m["name"] == "M3 线性趋势":
        return f"月度斜率 {d['slope_per_month']:+.2f} 件/月（负值=下滑，警惕过拟合）"
    if m["name"] == "M3b 季节平均":
        return "含2024年较高水平，偏乐观，仅作参考"
    return ""


def build_md(sku, window, monthly, years, methods, rec, source):
    lines = []
    ap = lines.append
    ap(f"# {sku} 销量预估（未来 {len(window)} 个月）")
    ap("")
    ap(f"> 生成时间：{datetime.datetime.now():%Y-%m-%d %H:%M}")
    ap(f"> 数据来源：PB `{os.path.basename(source)}` 工作表 Invoice to PB（PO Date / Qty Ordered / Vendor Style）")
    ap(f"> 预估窗口：{window[0][0]}-{window[0][1]:02d} ~ {window[-1][0]}-{window[-1][1]:02d}")
    ap("")
    ap("## 历史销量（PO 下单量，件/月）")
    ap("")
    ap("| 年 | 合计 | 月均 |")
    ap("|---|---|---|")
    for y in sorted(years):
        n_months = 12 if y < window[0][0] else sum(1 for (yy, _), _ in monthly if yy == y)
        ap(f"| {y} | {years[y]} | {years[y] / max(n_months, 1):.1f} |")
    ap("")
    ap("| 月份 | 2025 | 2026 |")
    ap("|---|---|---|")
    mv25 = {mm: q for (yy, mm), q in monthly if yy == 2025}
    mv26 = {mm: q for (yy, mm), q in monthly if yy == 2026}
    for m in range(1, 13):
        ap(f"| {m}月 | {mv25.get(m, '')} | {mv26.get(m, '')} |")
    ap("")
    ap("## 三种方法对比")
    ap("")
    ap("| 方法 | 中间值(件) | 区间(件) | 口径 |")
    ap("|---|---|---|---|")
    for m in methods:
        if m is None:
            continue
        ap(f"| {m['name']} | {fmt(m['mid'])} | {fmt(m['low'])}-{fmt(m['high'])} | {_method_note(m)} |")
    ap("")
    ap(f"## 结论")
    ap("")
    ap(f"- **预估中间值：约 {fmt(rec['mid'])} 件**（{len(window)} 个月），区间 {fmt(rec['low'])}-{fmt(rec['high'])} 件。")
    ap(f"- **建议备货：约 {fmt(rec['rec'])} 件**（在中间值上浮约 20%，覆盖断货/波动风险）。")
    ap("")
    ap("## 重要说明（补货时请留意）")
    ap("")
    ap("1. **断货可能低估需求**：此处销量 = PO 下单量 = 已开票/已发货量。若期间断货，未满足的订单不会出现在数据里，真实需求可能高于预估。")
    ap("2. **数据滞后**：近期 PO 可能尚未全部开票入表，最近 1-2 个月数字略偏低。")
    ap("3. **销量小、波动大**：月量 0-13 件，仅两年多数据，预估仅供参考，建议留缓冲并每月复核。")
    ap("4. 数据源为给财务对账表 `Invoice to PB`；该表用于对账，PO 下单量仅作销量代理。")
    ap("")
    ap("---")
    ap("*由 pb_reconciliation/sku_forecast.py 生成*")
    return "\n".join(lines)


def main():
    ap = argparse.ArgumentParser(description="PB SKU 销量预估")
    ap.add_argument("--sku", action="append", default=[], help="Vendor Style（可多次/逗号分隔）")
    ap.add_argument("--months", type=int, default=DEFAULT_MONTHS, help=f"预估月数，默认 {DEFAULT_MONTHS}")
    ap.add_argument("--start", default=None, help="窗口起始 YYYY-MM；默认下个月")
    ap.add_argument("--write", action="store_true", help="写 xlsx + md 到 OUT_DIR")
    ap.add_argument("--out", default=OUT_DIR, help="输出目录")
    ap.add_argument("--include-family", action="store_true", help="附加同族尺寸对照（去掉尺寸后缀的前缀匹配）")
    args = ap.parse_args()

    skus = []
    for s in args.sku:
        skus += [x.strip() for x in s.split(",") if x.strip()]
    if not skus:
        print("请用 --sku 指定 SKU，如 --sku CENKZ1325-YELLOW-97")
        return 1
    skus = list(dict.fromkeys(skus))  # 去重保序

    src = find_workbook()
    print(f"数据源: {src}")

    # 预估窗口
    if args.start:
        y0, m0 = [int(x) for x in args.start.split("-")]
    else:
        today = datetime.date.today()
        y0, m0 = today.year, today.month
        y0, m0 = add_months(y0, m0, 1)
    window = []
    y, m = y0, m0
    for _ in range(args.months):
        window.append((y, m))
        y, m = add_months(y, m, 1)
    print(f"预估窗口: {window[0][0]}-{window[0][1]:02d} ~ {window[-1][0]}-{window[-1][1]:02d}（{len(window)} 个月）")

    family = None
    if args.include_family:
        prefix = skus[0].rsplit("-", 1)[0] + "-"
        family = load_family(src, prefix)
        print(f"同族前缀: {prefix} -> {len(family)} 个尺寸")

    for sku in skus:
        sku_upper = sku.strip().upper()
        print(f"\n===== {sku_upper} =====")
        series, n_rows = load_series(src, sku_upper)
        if not series:
            print("  无数据（检查 SKU 写法；数据里为全大写）")
            continue
        years = yearly_totals(series)
        monthly = dense_months(series)
        print(f"  明细行 {n_rows}，月度跨度 {monthly[0][0][0]}-{monthly[0][0][1]:02d} ~ "
              f"{monthly[-1][0][0]}-{monthly[-1][0][1]:02d}")
        print("  按年合计: " + ", ".join(f"{y}={years[y]}" for y in sorted(years)))

        m1 = method_runrate(series, len(window))
        m2 = method_yoy(series, window)
        m3 = method_trend(series, window)
        m3b = method_seasonal_avg(series, window)
        methods = [m1, m2, m3, m3b]
        for m in methods:
            if m is None:
                continue
            print(f"  {m['name']}: 中间值 {m['mid']:.1f}  区间 {m['low']:.1f}-{m['high']:.1f}  {_method_note(m)}")

        # 推荐区间只看三种主方法（M3b 季节平均含 2024 年较高水平，偏乐观，仅作参考）
        primary = [m for m in (m1, m2, m3) if m is not None]
        base = [m for m in (m1, m2) if m is not None]
        if not base:
            print("  M1/M2 数据不足（<6 个月），仅打印历史，不做推荐。")
            continue
        rec_mid = sum(m["mid"] for m in base) / len(base)
        rec_low = min(m["low"] for m in primary)
        rec_high = max(m["high"] for m in primary)
        rec_rec = math_ceil(rec_mid * 1.2)
        rec = {"mid": rec_mid, "low": rec_low, "high": rec_high, "rec": rec_rec}
        print(f"  推荐值: {rec_mid:.0f} 件（区间 {rec_low:.0f}-{rec_high:.0f}），建议备货 {rec_rec} 件")

        if not args.write:
            print("  [dry-run] 未写文件；加 --write 输出 xlsx + md。")
            continue

        os.makedirs(args.out, exist_ok=True)
        stamp = datetime.datetime.now().strftime("%Y%m%d_%H%M%S")
        base = os.path.join(args.out, f"sales_forecast_{sku_upper}_{stamp}")
        xlsx_path = base + ".xlsx"
        md_path = base + ".md"
        build_xlsx(xlsx_path, sku_upper, window, monthly, years, methods, rec,
                   family if args.include_family and sku == skus[0] else None)
        with open(md_path, "w", encoding="utf-8") as fh:
            fh.write(build_md(sku_upper, window, monthly, years, methods, rec, src))
        print(f"  已写: {xlsx_path}")
        print(f"  已写: {md_path}")
    return 0


def math_ceil(x):
    return int(x) + (1 if x > int(x) else 0)


if __name__ == "__main__":
    raise SystemExit(main())
