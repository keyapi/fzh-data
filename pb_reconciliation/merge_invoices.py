#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""PB (Pottery Barn) 月度 invoice CSV 合并。

把一个月内各日文件夹的发票 CSV 拼成**一个**文件，交给财务做收款对账附件。

合并规格（与 2026-08-24 手工产出的 `202607/PB invoice 合并 202607.csv` 逐字节一致）：
- 表头 = 列数最多的那份（SPS 新版 92 列：Invoice Number … Remit To Ctry）
- 数据行 = 各日 `invoice/invoice*.csv` 的**全部**数据行（H 头行 + D 明细行都保留，不筛选不去重），
  按日文件夹日期升序拼接
- 每行右侧补空字段，统一补齐到全局最大列数
- UTF-8 带 BOM + CRLF，字段不加引号
- 输出 `<月份文件夹>/PB invoice 合并 <YYYYMM>.csv`

用法：
    python merge_invoices.py --month 202608 --dry-run   # 只读+报告+校验，不写文件
    python merge_invoices.py --month 202608 --write     # 写出合并文件

报告口径：`Invoice Total`(CA, 第 79 列) 只对 `Record Type`(第 24 列) = H 的行累加
（H+D 都算会重复，见 Pottery Barn 收款附件 invoice csv文件 累加金额操作 202403.docx）。
"""

import argparse
import csv
import datetime
import glob
import os
import re
import sys

# ================= 参数（换月份只改 --month） =================
BASE_DIR = r"D:\Work\美国\Tracy Miller\PB orders"

# 列位（0-based，与 CSV 列 1:1）
RECORD_TYPE_COL = 23  # 第 24 列 Record Type，H=头行 D=明细行
INVOICE_TOTAL_COL = 78  # 第 79 列 Invoice Total
# =============================================================


def read_csv(path):
    """读 CSV，返回全部行（含表头）。"""
    with open(path, encoding="utf-8-sig", errors="replace") as fh:
        return list(csv.reader(fh))


def collect_day_files(month_dir):
    """返回 (按日期升序的 [(day, [csv_path,...])], 未匹配的日文件夹列表)。

    只看 `<日文件夹>/invoice/` 下**一层**的 `invoice*.csv`（不递归，天然排除
    `invoice/截至YYYYMMDD尚未取消/` 之类变体子目录）。"""
    days = []
    unmatched = []
    for day in sorted(os.listdir(month_dir)):
        day_dir = os.path.join(month_dir, day)
        inv_dir = os.path.join(day_dir, "invoice")
        if not os.path.isdir(inv_dir):
            continue
        files = [
            f
            for f in glob.glob(os.path.join(inv_dir, "invoice*.csv"))
            if "NotUsed" not in f
        ]
        if files:
            days.append((day, sorted(files)))
        else:
            others = sorted(
                f for f in os.listdir(inv_dir) if f.lower().endswith(".csv")
            )
            unmatched.append((day, others))
    return days, unmatched


def invoice_total(rows):
    """H 行的 Invoice Total 累加 + 张数。"""
    h = [r for r in rows if len(r) > RECORD_TYPE_COL and r[RECORD_TYPE_COL] == "H"]
    total = 0.0
    for r in h:
        if len(r) > INVOICE_TOTAL_COL:
            try:
                total += float(r[INVOICE_TOTAL_COL])
            except ValueError:
                pass
    return len(h), round(total, 2)


def txt_totals(inv_dir):
    """该日 invoice/ 下 `.txt` 文件名里的小计（人手写的当日合计）。"""
    out = []
    for f in os.listdir(inv_dir):
        if f.lower().endswith(".txt"):
            m = re.match(r"^(\d+(?:\.\d+)?)", f)
            if m:
                out.append(float(m.group(1)))
    return out


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--month", required=True, help="月份，如 202608")
    ap.add_argument("--base", default=BASE_DIR, help="根目录（默认 PB orders，可指向副本做验证）")
    ap.add_argument("--dry-run", action="store_true", help="只读+报告，不写文件")
    ap.add_argument("--write", action="store_true", help="写出合并文件")
    ap.add_argument("--out", help="输出路径（默认 <月份文件夹>/PB invoice 合并 <月份>.csv）")
    ap.add_argument("--force", action="store_true", help="输出已存在时直接覆盖（默认写时间戳副本）")
    args = ap.parse_args()
    if args.dry_run == args.write:
        print("请指定 --dry-run 或 --write 之一")
        return 1
    if not re.fullmatch(r"\d{6}", args.month):
        print(f"月份格式应为 YYYYMM，收到 {args.month}")
        return 1

    month_dir = os.path.join(args.base, args.month)
    if not os.path.isdir(month_dir):
        print(f"月份文件夹不存在：{month_dir}")
        return 1

    # ---- 收集 ----
    print(f"[1/4] 扫描 {month_dir}")
    days, unmatched = collect_day_files(month_dir)
    if not days:
        print("没有找到任何 invoice*.csv，退出")
        return 1
    for day, files in days:
        print(f"      {day}: {len(files)} 个 CSV")
    if unmatched:
        print("\n未匹配到 invoice*.csv 的日文件夹（可能文件名拼错）：")
        for day, others in unmatched:
            print(f"  - {day}: 目录下有 {others or '（无 .csv）'}")
        print("校验失败，不写文件。请修正文件名后重跑。")
        return 1

    # ---- 读入 + 表头 ----
    print("[2/4] 读入并校验表头")
    per_day = []
    headers = {}
    for day, files in days:
        rows_all = []
        for fp in files:
            rows = read_csv(fp)
            if not rows:
                continue
            headers.setdefault((len(rows[0]), tuple(rows[0])), []).append(
                os.path.relpath(fp, args.base)
            )
            rows_all += [r for r in rows[1:] if r and r[0].strip()]
        per_day.append((day, files, rows_all))

    max_cols = max(n for n, _ in headers)
    top = {h for n, h in headers if n == max_cols}
    if len(top) > 1:
        print(f"  列数最多（{max_cols}）的表头有 {len(top)} 种，无法确定用哪个，退出")
        return 1
    header = list(next(iter(top)))
    shared = {h for n, h in headers if n < max_cols}
    print(f"      表头 {max_cols} 列；其他列数的表头 {len(shared)} 种（补空对齐）")

    all_rows = []
    for day, _, rows in per_day:
        all_rows += rows
    width = max(max_cols, max((len(r) for r in all_rows), default=0))

    # ---- 报告 ----
    print("[3/4] 对账报告")
    grand_h = 0
    grand_total = 0.0
    for day, files, rows in per_day:
        n_h, total = invoice_total(rows)
        grand_h += n_h
        grand_total += total
        txts = txt_totals(os.path.join(month_dir, day, "invoice"))
        if not txts:
            mark = "（无 txt 可比）"
        elif any(abs(t - total) < 0.005 for t in txts):
            mark = "txt ✔"
        else:
            mark = f"txt ✘ 目录标注 {txts}"
        print(
            f"      {day}  行 {len(rows):4d}  H {n_h:3d}  合计 {total:>10.2f}  {mark}"
        )
    print(f"      全月：CSV {sum(len(f) for _, f, _ in per_day)} 个 / "
          f"数据行 {len(all_rows)} / H {grand_h} 张 / 合计 {round(grand_total, 2)}")

    # ---- 写出 ----
    out_path = args.out or os.path.join(
        month_dir, f"PB invoice 合并 {args.month}.csv"
    )
    if args.dry_run:
        print(f"\n[dry-run] 未写文件。将输出到：{out_path}")
        print("确认无误后用 --write 输出。")
        return 0

    if os.path.exists(out_path) and not args.force:
        stamp = datetime.datetime.now().strftime("%Y%m%d_%H%M%S")
        root, ext = os.path.splitext(out_path)
        out_path = f"{root}_{stamp}{ext}"
        print(f"      目标已存在，改写带时间戳副本：{out_path}")

    print("[4/4] 写入 ...")
    with open(out_path, "w", encoding="utf-8-sig", newline="") as fh:
        w = csv.writer(fh)
        w.writerow(header + [""] * (width - len(header)))
        for r in all_rows:
            w.writerow(r + [""] * (width - len(r)))
    print(f"      已保存: {out_path}")
    print(f"      1 表头 + {len(all_rows)} 数据行 x {width} 列；"
          f"H 行 Invoice Total 合计 {round(grand_total, 2)}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
