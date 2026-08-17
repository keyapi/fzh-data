#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""PB 佣金结算表（To Tracy Miller）生成。

从给财务对账表过滤账期（每月 19 号 - 下月 18 号）内的付款 + 按天截止的发票，
生成 TM 佣金表（全英文 Notes、5% 佣金）。可复用每月跑。

用法：
    python tm_commission.py --dry-run   # 只读+报告+校验，不写文件
    python tm_commission.py --write     # 生成 To Tracy Miller 目录下的账期文件

下月复用：改顶部 FINANCE_FILE / PERIODS / EXPECTED / PREV_SOURCE 后重跑。
"""

import datetime
import os
import sys
from copy import copy

import openpyxl
from openpyxl.styles import PatternFill

# ================= 本月参数（下月复用只改这里） =================
FINANCE_FILE = r"D:\Work\美国\Tracy Miller\PB orders\payment advice\给财务\PB Remittance Advice Payment Date 20240430-20260813_差5单未付 20260814_171350.xlsx"
OUT_DIR = r"D:\Work\美国\Tracy Miller\PB orders\payment advice\To Tracy Miller"
# 账期列表：(start, end) 格式 YYYYMMDD。默认每月两个独立账期；
# 如需一次合并结算（如 2026-08 付 05/19-07/18 两期），可临时改为 [("20260519","20260718")]
PERIODS = [("20260519", "20260618"), ("20260619", "20260718")]
# 各账期预计付款总额（硬校验，来自财务确认）
EXPECTED = {"20260519-20260618": 14185.71, "20260619-20260718": 8842.75,
            # "20260519-20260718": 23028.46  # 合并账期（一次性）
            }
# 上轮账期 TM 文件（供 P1 的"上轮未付本轮已付"）；未列出的账期自动衔接上一期的未付清单
PREV_SOURCE = {
    "20260519": r"D:\Work\美国\Tracy Miller\PB orders\payment advice\To Tracy Miller\PB Remittance Advice Payment Date 20260419-20260518.xlsx",
}
COMMISSION_RATE = 0.05
K2_NOTE = (
    "Pottery Barn (PB) Commission To Tracy Miller. \n"
    "1) PB payment date: 30 days after shipment. \n"
    "2) Settlement cycle: PB Payment Start Date 19th of the previous month - PB Payment End Date 18th of the current month, US central time. \n"
    "3) Commission payout time: 14 days after a Settlement cycle.\n"
    "4) Worksheet \"Invoice to PB\" downloaded from PB, for invoice and order item details.\n"
    "In column X \"Record Type\": \n"
    "Choose \"H\" (Header) for order level data e.g. Date, Invoice Total etc.;\n"
    "Choose \"D\" (Details) for order item level details, Invoice Total with \"Record Type\":\"D\" are duplicates and should not be counted. \n"
    "e.g. Cell:G2 uses formula =SUMIF('Invoice to PB'!X:X, \"H\", 'Invoice to PB'!CA:CA) to pick only \"Record Type\":\"H\" and accumulates their Invoice Total"
)
# ==============================================================

PB_SHEET = "PB Remittance Advice"
INV_SHEET = "Invoice to PB"
NOTES_SHEET = "Notes"

CA_COL = 79
CG_COL = 85
CH_COL = 86
X_COL = 24  # Record Type


def to_date(v):
    if isinstance(v, datetime.datetime):
        return v.date()
    if isinstance(v, datetime.date):
        return v
    if isinstance(v, str):
        return datetime.datetime.strptime(v.strip(), "%m/%d/%Y").date()
    return None


def copy_style(dst, src):
    dst.font = copy(src.font)
    dst.fill = copy(src.fill)
    dst.border = copy(src.border)
    dst.number_format = src.number_format
    dst.alignment = copy(src.alignment)


def read_prev_unpaid(file):
    """从上一账期 TM 文件读取 'Unpaid in this period' 发票清单。"""
    wb = openpyxl.load_workbook(file, data_only=True)
    nws = wb[NOTES_SHEET]
    invs = {}
    in_section = False
    for r in range(1, nws.max_row + 1):
        v = nws.cell(r, 11).value
        if v == "Unpaid in this period":
            in_section = True
            continue
        if in_section and isinstance(v, str) and v.startswith("INV"):
            invs[str(v).strip()] = (nws.cell(r, 12).value, nws.cell(r, 13).value)
        elif in_section and v == "Total:":
            break
    return invs


def build_notes(nws, period_start, period_end, inv_start, inv_end, pay_start, pay_end,
                actual_pay_start, actual_pay_end, unpaid_last_paid, unpaid_this):
    """写 Notes sheet（结构对照示例 20260419-20260518）。"""
    from openpyxl.styles import Font
    bold = Font(bold=True)
    no_fill = PatternFill(fill_type=None)

    def put(r, c, val, font=None, numfmt=None):
        cell = nws.cell(r, c)
        cell.value = val
        cell.font = copy(font) if font else Font()
        cell.fill = no_fill
        cell.border = copy(nws["A1"].border)
        cell.number_format = numfmt if numfmt else "General"
        cell.alignment = copy(nws["A1"].alignment)
        return cell

    # Row 1 headers
    for c, h in [(1, "Invoice To PB Start Date"), (2, "Invoice To PB End Date"),
                 (3, "PB Invoice Start Date"), (4, "PB Invoice End Date"),
                 (5, "PB Payment Start Date"), (6, "PB Payment End Date"),
                 (7, "Invoice Amount"), (8, "Payment Amount"), (9, "Commission Rate"),
                 (10, "Commission Amount"), (11, "Notes")]:
        put(1, c, h, bold)

    # Row 2 dates + formulas
    def dt(v):
        return datetime.datetime(v.year, v.month, v.day)
    put(2, 1, dt(inv_start))
    put(2, 2, dt(inv_end))
    put(2, 3, dt(inv_start))
    put(2, 4, dt(inv_end))
    put(2, 5, dt(pay_start))
    put(2, 6, dt(pay_end))
    put(2, 7, f"=SUMIF('{INV_SHEET}'!X:X,\"H\",'{INV_SHEET}'!CA:CA)")
    put(2, 8, f"=SUM('{PB_SHEET}'!I:I)")
    put(2, 9, COMMISSION_RATE)
    put(2, 10, "=H2*I2")
    put(2, 11, K2_NOTE)

    # Row 3 actual dates（实际首末付款日，非账期边界）
    put(3, 5, f"Actual PB Payment Start Date: {actual_pay_start.month}/{actual_pay_start.day}/{actual_pay_start.year}")
    put(3, 6, f"Actual PB Payment End Date: {actual_pay_end.month}/{actual_pay_end.day}/{actual_pay_end.year}")

    # Unpaid in last period, paid in this period
    r = 5
    put(r, 11, "Unpaid in last period, paid in this period", bold)
    put(r, 12, "Invoice Date", bold)
    put(r, 13, "Invoice Total", bold)
    r += 1
    for inv, (d, amt) in sorted(unpaid_last_paid.items()):
        put(r, 11, inv)
        if d:
            put(r, 12, d)
        if amt is not None:
            put(r, 13, amt)
        r += 1
    last_total_row = r
    put(last_total_row, 11, "Total:", bold)
    if unpaid_last_paid:
        put(last_total_row, 13, f"=SUM(M6:M{last_total_row - 1})")
    else:
        put(last_total_row, 13, 0)

    # Unpaid in this period
    hu = last_total_row + 3  # 隔 2 行
    put(hu, 11, "Unpaid in this period", bold)
    put(hu, 12, "Invoice Date", bold)
    put(hu, 13, "Invoice Total", bold)
    r = hu + 1
    for inv, (d, amt) in sorted(unpaid_this.items()):
        put(r, 11, inv)
        if d:
            put(r, 12, d)
        if amt is not None:
            put(r, 13, amt)
        r += 1
    this_total_row = r
    put(this_total_row, 11, "Total:", bold)
    if unpaid_this:
        put(this_total_row, 13, f"=SUM(M{hu + 1}:M{this_total_row - 1})")
    else:
        put(this_total_row, 13, 0)

    # Difference
    put(this_total_row, 7, "Difference", bold)
    put(this_total_row, 8, f"=G2-H2")
    return this_total_row


def build_tm_file(fin_wb_values, fin_wb_styles, period, prev_unpaid):
    start_s, end_s = period
    start = datetime.datetime.strptime(start_s, "%Y%m%d").date()
    end = datetime.datetime.strptime(end_s, "%Y%m%d").date()

    fp = fin_wb_values[PB_SHEET]
    fi = fin_wb_values[INV_SHEET]

    # 1) 过滤付款
    pay_rows = []
    paid_inv = set()
    for r in range(2, fp.max_row + 1):
        b = fp.cell(r, 2).value
        if b and start <= to_date(b) <= end:
            vals = [fp.cell(r, c).value for c in range(1, 11)]  # A..J
            pay_rows.append(vals)
            paid_inv.add(str(vals[2]).strip())
    pay_dates = sorted({to_date(p[1]) for p in pay_rows})

    # 2) 发票日范围 = [首个有付款的发票日, 最后]
    inv_days = sorted({to_date(p[4]) for p in pay_rows if p[4]})
    inv_start, inv_end = inv_days[0], inv_days[-1]

    # 3) 过滤发票：先取范围内 H 行的发票号集合，再复制这些发票的全部 H/D 行
    included_inv = set()
    for r in range(2, fi.max_row + 1):
        if fi.cell(r, X_COL).value == "H" and fi.cell(r, 1).value:
            d = to_date(fi.cell(r, 2).value) if fi.cell(r, 2).value else None
            if d and inv_start <= d <= inv_end:
                included_inv.add(str(fi.cell(r, 1).value).strip())
    inv_rows = []
    for r in range(2, fi.max_row + 1):
        a = fi.cell(r, 1).value
        if a and str(a).strip() in included_inv:
            vals = [fi.cell(r, c).value for c in range(1, 85)]  # A..CF
            inv_rows.append(vals)

    # 4) 未付清单
    unpaid_this = {}
    for inv in sorted(included_inv - paid_inv):
        d = amt = None
        for v in inv_rows:
            if str(v[0]).strip() == inv and v[X_COL - 1] == "H":
                d, amt = v[1], v[CA_COL - 1]
                break
        unpaid_this[inv] = (d, amt)
    unpaid_last_paid = {inv: info for inv, info in prev_unpaid.items() if inv in paid_inv}

    # ---- 构建 workbook（sheet 顺序：Notes / PB Remittance Advice / Invoice to PB） ----
    tpl_p = fin_wb_styles[PB_SHEET]
    tpl_i = fin_wb_styles[INV_SHEET]
    wb = openpyxl.Workbook()
    ws_n = wb.active
    ws_n.title = NOTES_SHEET
    ws_p = wb.create_sheet(PB_SHEET)
    ws_i = wb.create_sheet(INV_SHEET)

    # PB Remittance Advice: header + filtered rows
    for c in range(1, 12):
        copy_style(ws_p.cell(1, c), tpl_p.cell(1, c))
        ws_p.cell(1, c).value = tpl_p.cell(1, c).value
    for idx, vals in enumerate(pay_rows):
        r = 2 + idx
        for c in range(1, 11):
            cell = ws_p.cell(r, c)
            cell.value = vals[c - 1]
            copy_style(cell, tpl_p.cell(2, c))
        cell = ws_p.cell(r, 11)
        cell.value = f"=VLOOKUP(C{r},'{INV_SHEET}'!A:H,2,FALSE)"
        copy_style(cell, tpl_p.cell(2, 11))

    # Invoice to PB: header + filtered rows
    for c in range(1, 87):
        copy_style(ws_i.cell(1, c), tpl_i.cell(1, c))
        ws_i.cell(1, c).value = tpl_i.cell(1, c).value
    for idx, vals in enumerate(inv_rows):
        r = 2 + idx
        for c, v in enumerate(vals, start=1):
            if v not in (None, ""):
                cell = ws_i.cell(r, c)
                cell.value = v
                copy_style(cell, tpl_i.cell(2, c))
        cell = ws_i.cell(r, CG_COL)
        cell.value = f"=_xlfn.IFNA(VLOOKUP(A{r},'{PB_SHEET}'!C:I,7,FALSE),0)"
        copy_style(cell, tpl_i.cell(2, CG_COL))
        cell = ws_i.cell(r, CH_COL)
        cell.value = f"=CA{r}-CG{r}"
        copy_style(cell, tpl_i.cell(2, CH_COL))

    # Notes
    build_notes(ws_n, start, end, inv_start, inv_end, start, end,
                pay_dates[0], pay_dates[-1], unpaid_last_paid, unpaid_this)

    wb.calculation.fullCalcOnLoad = True
    return wb, pay_rows, unpaid_this, inv_start, inv_end


def main():
    mode = "--write" if "--write" in sys.argv else "--dry-run"
    fin_values = openpyxl.load_workbook(FINANCE_FILE, data_only=True)
    fin_styles = openpyxl.load_workbook(FINANCE_FILE, data_only=False)

    prev_unpaid = {}
    for i, period in enumerate(PERIODS):
        start_s = period[0]
        # 上轮未付：P1 用 PREV_SOURCE 文件；后续用上一期输出
        if start_s in PREV_SOURCE:
            prev_unpaid = read_prev_unpaid(PREV_SOURCE[start_s])
            print(f"[{period[0]}-{period[1]}] 上轮未付来自 {os.path.basename(PREV_SOURCE[start_s])}: {len(prev_unpaid)} 张")
        elif i > 0:
            prev_unpaid = prev_unpaid_this
            print(f"[{period[0]}-{period[1]}] 上轮未付衔接上一期: {len(prev_unpaid)} 张")

        wb, pay_rows, unpaid_this, inv_start, inv_end = build_tm_file(fin_values, fin_styles, period, prev_unpaid)
        pay_total = round(sum(p[8] for p in pay_rows), 2)
        key = f"{period[0]}-{period[1]}"
        print(f"[{key}] 付款 {len(pay_rows)} 行, 总额 {pay_total}")
        print(f"   发票范围 {inv_start}..{inv_end}，未付本账期 {len(unpaid_this)} 张")

        # 硬校验
        exp = EXPECTED.get(key)
        if exp is not None and abs(pay_total - exp) > 0.01:
            print(f"   !! 付款总额 {pay_total} 与预期 {exp} 不符，跳过")
            return 1

        if mode == "--write":
            out = os.path.join(OUT_DIR, f"PB Remittance Advice Payment Date {key}.xlsx")
            wb.save(out)
            print(f"   已保存: {out}")
        prev_unpaid_this = unpaid_this

    if mode == "--dry-run":
        print("\n[dry-run] 未写文件。确认后用 --write 输出。")
    else:
        print("\n完成。请在 Excel 打开确认公式已重算。")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
