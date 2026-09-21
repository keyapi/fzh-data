#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""步骤 3：SPS 订单 CSV -> 通途导入 xlsx。

流程（照搬 Colab notebook 步骤 3，仅修 pandas 3.0 不兼容点）：
1. 读 CSV（PO Number / Zip 等强制为字符串，日期列 parse_dates）
2. 按 PO Number 分组组内前向填充（订单头 H 行的地址等字段下发给 D 行）
3. 只保留 Record Type == 'D' 的订单行
4. 按 (PO Number, PO Line # 倒序) 排序
5. 若 Qty Ordered > 1，拆成多行（每行 1 件），便于一页一包裹
6. 派生 Line # / Line Count / PO Number-Line / x Qty Ordered / SKUxQTY
7. 删掉通途不认的固定列，再按需从右往左删空列，保证不超过 100 列
8. 无货 SKU（--no-stock）从可导入集合中剔除，并单独出「无库存」文件

输出（与历史文件命名一致，产物落当天文件夹）：
    无 no-stock：  PB_0_导入_原始_{csv_stem}_on_{ts}.xlsx
    有 no-stock：  PB_0_不可导入_原始_... + PB_1_不可导入_无库存_... + PB_2_导入_库存有货_...

用法：
    uv run python pb_tongtu_excel.py "checked0stock order x40 20260921_0159_334423.csv"
"""

import argparse
import os
import sys
from datetime import datetime
from pathlib import Path

import numpy as np
import pandas as pd

# 通途导入列数上限（超出会导入失败）
MAX_COLS = 100

# 强制为字符串的列：PO Number / Zip 等若被 pandas 推断成数字会丢前导 0 或变成科学计数法
DTYPE_STR = {
    "PO Number": str,
    "PO Line #": str,
    "Retailers PO": str,
    "Customer Order #": str,
    "Buyers Catalog or Stock Keeping #": str,
    "Contact Phone": str,
    "Ship to Zip": str,
    "Ship To Zip": str,
    "Ship To Contact": str,
    "Bill To Zip": str,
    "Buying Party Zip": str,
}
DATE_COLS = ["PO Date", "Requested Delivery Date", "Ship Dates"]

# 固定删除的 31 列（通途导入模板不需要；原始 130 列 -> 99 列）
COLS_TO_DROP = [
    "Payment Terms %", "Payment Terms Disc Due Date", "Payment Terms Disc Days Due",
    "Payment Terms Net Due Date", "Payment Terms Net Days", "Payment Terms Disc Amt",
    "Payment Terms Desc", "PO Total Weight ", "PO Total UOM ", "Shipping account number",
    "Mark for Name", "Mark for Address 1", "Mark for Address 2", "Mark for City",
    "Mark for State", "Mark for Postal", "Mark for Country", "Shipping Container Code",
    "National Drug Code", "Expiration Date", "Dist", "Scheduled Quantity",
    "Scheduled Qty UOM", "Required By Date", "Must Arrive By", "Entire Shipment",
    "Agreement Number", "Additional Vendor Part #", "Buyer Part Number",
    "Carrier Details Special Handling", "Restrictions/Conditions",
]

COL_PO = "PO Number"
COL_RECORD_TYPE = "Record Type"
COL_QTY = "Qty Ordered"
COL_VENDOR_STYLE = "Vendor Style"
COL_SKUxQTY = "SKUxQTY"


def _timestamp(fmt="%Y-%m-%d_%H-%M-%S"):
    return datetime.now().strftime(fmt)


def load_order_csv(path):
    """读订单 CSV：dtype / parse_dates 只对实际存在的列生效。"""
    header = pd.read_csv(path, nrows=0).columns
    dtype = {k: v for k, v in DTYPE_STR.items() if k in header}
    usecols_dates = [c for c in DATE_COLS if c in header]
    return pd.read_csv(path, dtype=dtype, parse_dates=usecols_dates or None)


def drop_extra_empty_columns(df, max_cols=MAX_COLS):
    """列数 > max_cols 时，从右往左删整列空值列，直到 <= max_cols。"""
    if df.shape[1] <= max_cols:
        return df
    d = df.replace("", np.nan)
    empty = [c for c in list(d.columns)[::-1] if d[c].isna().all()]
    return df.drop(columns=empty[: df.shape[1] - max_cols])


def build_order_df(path):
    """订单 CSV -> 通途导入用 DataFrame（拆行后）。"""
    df = load_order_csv(path)

    # 组内前向填充：pandas 3.0 的 groupby.ffill() 会丢掉分组键，且 include_groups=True 已禁用
    # 用 concat 把 PO Number 拼回首位（直接赋值会往碎片化的宽表里 insert，触发 PerformanceWarning）
    po_keys = df[COL_PO]
    ffilled = df.groupby(COL_PO, group_keys=False).ffill()
    df = pd.concat([po_keys, ffilled], axis=1)

    df = df.loc[df[COL_RECORD_TYPE] == "D"].copy()

    # 按 (PO Number, PO Line # 倒序) 排序。PO Line # 保持 CSV 读进来的字符串类型、
    # 按字典序比较 —— 与 notebook 一致；转成数字会改变导出列的值（'1' -> 1）。
    df = df.sort_values(
        by=[COL_PO, "PO Line #"], ascending=[True, False], ignore_index=True
    )

    # 数量 > 1 的拆成多行，每行 1 件（PDF 一页一包裹）
    qty = pd.to_numeric(df[COL_QTY], errors="coerce")
    if qty.isna().any():
        bad = df.loc[qty.isna(), COL_PO].tolist()
        raise ValueError(f"{COL_QTY} 存在空值/非数字，无法拆行。PO: {bad[:5]}")
    df = df.loc[df.index.repeat(qty.astype(int))].reset_index(drop=True)
    df.loc[pd.to_numeric(df[COL_QTY]) > 1, COL_QTY] = 1

    df["Line #"] = (df.groupby(COL_PO).cumcount(ascending=False) + 1).astype(str)
    df["Line Count"] = df.groupby(COL_PO)[COL_PO].transform("count")
    df["PO Number-Line"] = np.where(
        df["Line Count"] == 1, df[COL_PO], df[COL_PO] + "-" + df["Line #"]
    )

    if "PO Date" in df.columns:
        df["PO Date"] = df["PO Date"].dt.strftime("%Y-%m-%d %H:%M:%S")
    df["Ship To Country"] = df["Ship To Country"].str.replace("USA", "US")

    df["Unit Price x Qty Ordered"] = df["Unit Price"] * df[COL_QTY]

    df["x Qty Ordered"] = df[COL_QTY].astype("Int64").astype(str)
    multi = df["x Qty Ordered"] != "1"
    df.loc[multi, "x Qty Ordered"] = df.loc[multi, "x Qty Ordered"] + " ! ! !"
    df[COL_SKUxQTY] = df[COL_VENDOR_STYLE] + " x" + df["x Qty Ordered"]

    df = df.drop(columns=COLS_TO_DROP, errors="ignore")
    return drop_extra_empty_columns(df).reset_index(drop=True)


def split_no_stock(df, no_stock_skus):
    """按无货 SKU 拆分（大小写不敏感）。no_stock_skus 为空则全部可导入。

    注：Colab 里这段是死代码（参数是字符串，for 遍历的是单个字符，isin 永不命中），
    本版做成真正可用；默认不传 = 不过滤，与当前 Colab 行为等价。
    """
    if not no_stock_skus:
        return df, df.iloc[0:0].copy()
    wanted = {s.strip().lower() for s in no_stock_skus if s.strip()}
    mask = df[COL_VENDOR_STYLE].astype(str).str.strip().str.lower().isin(wanted)
    return df.loc[~mask].copy(), df.loc[mask].copy()


def export(df_all, df_importable, df_no_stock, out_dir, csv_stem, ts=None):
    """写导入文件，返回 {标签: 路径}。无 no-stock 命中时只写 PB_0。"""
    ts = ts or _timestamp()
    out_dir = Path(out_dir)
    out_dir.mkdir(parents=True, exist_ok=True)
    written = {}

    def _write(prefix, df):
        name = f"{prefix}_{csv_stem}_on_{ts}.xlsx"
        p = out_dir / name
        df.to_excel(p, index=False)
        written[prefix] = p
        return p

    if df_no_stock.empty:
        _write("PB_0_导入_原始", df_all)
    else:
        _write("PB_0_不可导入_原始", df_all)
        _write("PB_1_不可导入_无库存", df_no_stock)
        _write("PB_2_导入_库存有货", df_importable)
    return written


def main():
    ap = argparse.ArgumentParser(description="步骤 3：SPS 订单 CSV -> 通途导入 xlsx")
    ap.add_argument("csv", help="checked0stock order CSV 路径")
    ap.add_argument("--out", default=None, help="输出目录，默认与 CSV 同目录")
    ap.add_argument("--no-stock", default="", help="无货 SKU，逗号分隔")
    args = ap.parse_args()

    src = Path(args.csv).resolve()
    if not src.is_file():
        sys.exit(f"文件不存在: {src}")
    out = Path(args.out).resolve() if args.out else src.parent

    df = build_order_df(src)
    skus = [s for s in args.no_stock.split(",") if s.strip()]
    importable, no_stock = split_no_stock(df, skus)

    print(f"拆行后总行数: {len(df)} | 列数: {df.shape[1]}")
    print(f"可导入: {len(importable)} | 无库存: {len(no_stock)}")
    if df.shape[1] > MAX_COLS:
        print(f"警告：列数 {df.shape[1]} 超过通途上限 {MAX_COLS}")
    written = export(df, importable, no_stock, out, src.stem)
    for k, v in written.items():
        print(f"  {k}: {os.path.relpath(v, out)}")


if __name__ == "__main__":
    main()
