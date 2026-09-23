#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""步骤 1-2：从 SPS 合并 PDF（打包单 + UPS 标签同页）抽取 PO Number 与 Item Number。

PDF 每页结构固定（SPS 导出，A4 竖版）：
    Customer Order Number: 362632154021
    Purchase Order Number 137943090      <- PO（9 位以上）
    ...
    Item Number                          <- 表头，取其下方第一个 7-10 位数字行
    Component / Item Ratio / Description / Ship Qty / Unit Price
    1069914                              <- Item Number 值
    Inventive Sleep: ...

一页 = 一个包裹 = 一个 Item，页序与订单 CSV 拆行后的行序一致（1:1）。
同 PO 多件时，PO 会出现多次，故派生 `Line` / `Line Count` / `PO Number-Line`。

用法：
    uv run python sps_pb_pdf.py "Packslip 美中 x50 20260921.pdf"
"""

import argparse
import re
import sys
from pathlib import Path

import fitz  # PyMuPDF
import numpy as np
import pandas as pd

RE_ITEM_HEADER = "Item Number"
RE_PO = re.compile(r"Purchase Order Number (\d{9,})")
RE_ITEM_VALUE = re.compile(r"\d{7,10}")

COL_PO = "PO Number"
COL_ITEM = "Item Number"
COL_LINE_COUNT = "Line Count"
COL_LINE = "Line"
COL_PO_LINE = "PO Number-Line"
COL_VENDOR_STYLE = "Vendor Style"


def _page_lines(page):
    """返回 [(行文本, bbox), ...]；bbox = (x0, y0, x1, y1)，PyMuPDF 原点在左上、y 向下。"""
    out = []
    for block in page.get_text("dict").get("blocks", []):
        for line in block.get("lines", []):
            text = "".join(span["text"] for span in line["spans"]).strip()
            if text:
                out.append((text, line["bbox"]))
    return out


def extract_po_number(page):
    """取第一个 `Purchase Order Number <9+位数字>`；找不到返回 None。"""
    found = RE_PO.findall(page.get_text())
    return found[0] if found else None


def extract_item_number(page):
    """定位第一个 "Item Number" 表头，取表头下方第一个纯 7-10 位数字行。

    注意：PyMuPDF 的 y 轴向下，所以"在表头下方"= 该行 bbox 上沿 > 表头 bbox 下沿。
    （原 notebook 用 pdfminer，y 轴向上，判据为 bbox[3] < 表头 bbox[1] - 10，方向相反。）
    """
    lines = _page_lines(page)
    header_bbox = next((bbox for text, bbox in lines if RE_ITEM_HEADER in text), None)
    if header_bbox is None:
        return None
    for text, bbox in lines:
        if bbox[1] < header_bbox[3] - 1:  # 在表头上方，跳过
            continue
        if RE_ITEM_HEADER in text:  # 表头本身
            continue
        if RE_ITEM_VALUE.fullmatch(text):
            return text
    return None


def build_page_df(pdf_path):
    """PDF -> 每页一行的 DataFrame（PO Number / Item Number + 派生列）。"""
    with fitz.open(pdf_path) as doc:
        pos = [extract_po_number(page) for page in doc]
        items = [extract_item_number(page) for page in doc]

    df = pd.DataFrame({COL_PO: pos, COL_ITEM: items})
    df[COL_LINE_COUNT] = df.groupby(COL_PO)[COL_PO].transform("count")
    df[COL_LINE] = (df.groupby(COL_PO).cumcount() + 1).astype(str)
    df[COL_PO_LINE] = np.where(
        df[COL_LINE_COUNT] == 1,
        df[COL_PO],
        df[COL_PO] + "-" + df[COL_LINE],
    )
    return df


COL_CATALOG = "Buyers Catalog or Stock Keeping #"
JOIN_COLS = [COL_PO, COL_CATALOG, "SKUxQTY", "Line #", COL_VENDOR_STYLE, "Qty Ordered"]


def join_pages_with_orders(df_pdf, df_order):
    """把 PDF 页（PO + Item Number）与订单行按 (PO, Item Number = Buyer Catalog #) 关联。

    订单侧 PO 可能被人工加过 '-2' 之类后缀，先按 '-' 截断只取主体再匹配。
    返回 (df, 未匹配的 PO Number-Line 列表)。
    """
    missing_cols = [c for c in JOIN_COLS if c not in df_order.columns]
    if missing_cols:
        raise KeyError(f"订单表缺少列: {missing_cols}")

    orders = df_order.copy()
    orders[COL_PO] = orders[COL_PO].astype(str).str.split("-").str[0]
    right = orders[JOIN_COLS].drop_duplicates(
        subset=[COL_PO, COL_CATALOG], keep="last"
    )
    out = df_pdf.merge(
        right,
        how="left",
        left_on=[COL_PO, COL_ITEM],
        right_on=[COL_PO, COL_CATALOG],
    )
    unmatched = out.loc[out["SKUxQTY"].isna(), COL_PO_LINE].tolist()
    return out, unmatched


def _selftest(path):
    df = build_page_df(path)
    print(f"总页数: {len(df)}")
    print(f"PO 抽取失败: {int(df[COL_PO].isna().sum())} 页")
    print(f"Item Number 抽取失败: {int(df[COL_ITEM].isna().sum())} 页")
    print(f"唯一 PO: {df[COL_PO].nunique()}")
    print(df.head(10).to_string())


def main():
    ap = argparse.ArgumentParser(description="步骤 1-2：SPS PDF 抽取 PO / Item Number")
    ap.add_argument("pdf", help="Packslip PDF 路径")
    args = ap.parse_args()
    path = Path(args.pdf).resolve()
    if not path.is_file():
        sys.exit(f"文件不存在: {path}")
    _selftest(path)


if __name__ == "__main__":
    main()
