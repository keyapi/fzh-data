#!/usr/bin/env python3
"""把月度成品 xlsx 的指定列写回固定 Google Sheet 里的月度 ws（不整表 clear）。

背景/取舍见 docs/reference/gsheet-monthly-sheet-upload.md。
默认行为（patch 模式，推荐）：
  1. 打开「通途订单YYYYMM」的 ws「YYYY年M月订单」（表头与 xlsx 校验一致）
  2. 复制该 ws（服务端瞬时，保留格式与人工改动）插入到原索引；旧 ws 改名归档 弃用…<日期>
  3. 只把 xlsx 中指定列（默认「物流商运费」）整列覆盖写回新 ws（单/少列，远低于 API 体积上限）
  4. 回读校验（行数/表头/数值列合计）并打印摘要

为什么不 `clear()` + 整表 update：整表 ~87 万格会超请求体积上限，且 clear 后是空表窗口，
中途失败即丢数据；只写变化列不触碰其它列与人工编辑。

用法：
  GSPREAD_SERVICE_ACCOUNT_FILE=<父仓库>/secrets/gsheets-service-account.json \
  uv run python tongtool_order_cost/scripts/upload_monthly_order_sheet.py \
      --xlsx "GS再次上传 …20260911.xlsx" --month 202607            # 直接执行
      ... --dry-run                                               # 只看计划，不写入
      ... --sheet 通途订单202607 --ws 2026年7月订单 --columns 物流商运费
"""
from __future__ import annotations

import argparse
import datetime as dt
import sys
import time

import pandas as pd


def column_letter(n: int) -> str:
    """1-based 列号 → A/Z/AA…"""
    s = ""
    while n > 0:
        n, r = divmod(n - 1, 26)
        s = chr(65 + r) + s
    return s


def derive_names(month: str) -> tuple[str, str]:
    """'202607' → (spreadsheet='通途订单202607', worksheet='2026年7月订单')"""
    y, m = int(month[:4]), int(month[4:6])
    if not (1 <= m <= 12):
        raise ValueError(f"月份非法: {month}")
    return f"通途订单{month}", f"{y}年{m}月订单"


def default_archive_name(ws: str, today: dt.date | None = None) -> str:
    today = today or dt.date.today()
    return f"弃用{ws} {today:%Y%m%d}"


def unique_title(taken: set[str], base: str) -> str:
    if base not in taken:
        return base
    i = 2
    while f"{base} ({i})" in taken:
        i += 1
    return f"{base} ({i})"


def norm(v) -> tuple:
    """归一化单元格值用于比较：''/None 视为空；去千分位后能转数则按数值比。"""
    if v is None:
        return ("empty",)
    s = str(v).strip()
    if s == "":
        return ("empty",)
    try:
        return ("num", round(float(s.replace(",", "")), 6))
    except ValueError:
        return ("str", s)


def open_spreadsheet(gc, title: str, attempts: int = 5):
    for i in range(attempts):
        try:
            return gc.open(title)
        except Exception as e:  # 503 等瞬时错误
            if i == attempts - 1:
                raise
            print(f"  [重试 {i+1}] open({title}) {type(e).__name__}: {str(e)[:60]}")
            time.sleep(5)


def load_column_values(xlsx_path: str, column: str) -> list:
    """读 xlsx 指定列 → 值列表（NaN→''），不含表头。"""
    df = pd.read_excel(xlsx_path)
    if column not in df.columns:
        raise SystemExit(f"xlsx 缺少列: {column}（现有列示例: {list(df.columns)[:6]}…）")
    return df[column].astype(object).where(pd.notna(df[column]), "").tolist()


def main(argv=None) -> int:
    ap = argparse.ArgumentParser(description="月度成品 xlsx → 固定 gsheet 月度 ws（patch 模式）")
    ap.add_argument("--xlsx", required=True)
    ap.add_argument("--month", help="YYYYMM；用于推导 --sheet/--ws 默认值")
    ap.add_argument("--sheet", help="电子表格名，如 通途订单202607")
    ap.add_argument("--ws", dest="ws", help="目标工作表名，如 2026年7月订单")
    ap.add_argument("--columns", default="物流商运费", help="要写回的列（逗号分隔），默认 物流商运费")
    ap.add_argument("--archive", help="旧 ws 归档名，默认 弃用<ws> <YYYYMMDD>")
    ap.add_argument("--chunk", type=int, default=5000, help="单次写入行数（默认 5000）")
    ap.add_argument("--in-place", action="store_true",
                    help="直接覆盖目标 ws 的指定列（不复制旧 ws、不归档）；用于纯列更新")
    ap.add_argument("--dry-run", action="store_true", help="只打印计划与差异，不写入")
    args = ap.parse_args(argv)

    if not args.sheet or not args.ws:
        if not args.month:
            raise SystemExit("需给 --month YYYYMM，或显式 --sheet/--ws")
        sheet_name, ws_name = derive_names(args.month)
        sheet_name = args.sheet or sheet_name
        ws_name = args.ws or ws_name
    else:
        sheet_name, ws_name = args.sheet, args.ws
    columns = [c.strip() for c in args.columns.split(",") if c.strip()]

    if ws_name.startswith("写回"):
        raise SystemExit(f"拒绝操作「写回*」表: {ws_name}（该表由后续 Colab 处理）")

    from tongtool_order_cost.gsheets import client  # 延迟导入，便于纯函数测试

    gc = client()
    sp = open_spreadsheet(gc, sheet_name)
    old = sp.worksheet(ws_name)
    hdr = old.row_values(1)
    df_cols = [str(c) for c in pd.read_excel(args.xlsx, nrows=0).columns]
    if hdr != df_cols:
        raise SystemExit(f"表头不一致，拒绝写入。\n  gsheet: {hdr[:6]}…\n  xlsx  : {df_cols[:6]}…")

    plans = []
    for col in columns:
        idx = hdr.index(col) + 1
        new_vals = load_column_values(args.xlsx, col)
        old_vals = old.col_values(idx)[1:]
        n = min(len(new_vals), len(old_vals))
        changed = sum(1 for i in range(n) if norm(new_vals[i]) != norm(old_vals[i]))
        plans.append((col, idx, new_vals, changed))

    print(f"表: {sp.title} | ws: {ws_name} (index={old.index})")
    print(f"xlsx 行数: {len(plans[0][2])} | 现有 ws 行数: {old.row_count} | 归档为: {args.archive or default_archive_name(ws_name)}")
    for col, idx, vals, changed in plans:
        print(f"  列 {col}（{column_letter(idx)}）: 变化 {changed} 行")
    if args.dry_run:
        print("[dry-run] 未做任何写入。")
        return 0

    if args.in_place:
        print(f"in-place 模式：直接覆盖 {ws_name} 的指定列（不复制、不归档）")
    else:
        # 复制旧 ws 到原索引（保留格式/人工改动），随后旧 ws 归档
        taken = {w.title for w in sp.worksheets()}
        dup_title = unique_title(taken, f"{ws_name}__new")
        dup = sp.duplicate_sheet(old.id, insert_sheet_index=old.index, new_sheet_name=dup_title)
        arch = args.archive or default_archive_name(ws_name)
        old.update_title(unique_title(taken - {ws_name}, arch))
        dup.update_title(ws_name)
        print(f"已复制并归档: 新 {ws_name}（原索引） / 旧 {arch}")

    # 2) 只覆盖指定列
    ws_new = sp.worksheet(ws_name)
    for col, idx, vals, _ in plans:
        L = column_letter(idx)
        for s in range(0, len(vals), args.chunk):
            chunk = [[v] for v in vals[s:s + args.chunk]]
            ws_new.update(values=chunk, range_name=f"{L}{s + 2}", value_input_option="RAW")
            print(f"  {col}: 写入 {min(s + args.chunk, len(vals))}/{len(vals)}")

    # 3) 回读校验
    ws_new = sp.worksheet(ws_name)
    ok = True
    for col, idx, vals, _ in plans:
        back = ws_new.col_values(idx)[1:]
        same = len(back) == len(vals) and all(norm(a) == norm(b) for a, b in zip(back, vals))
        print(f"  校验 {col}: 行数 {len(back)} {'一致' if same else '不一致!'}")
        ok = ok and same
    print("完成。" if ok else "完成（有校验不一致，请人工核对）。")
    return 0 if ok else 1


if __name__ == "__main__":
    sys.exit(main())
