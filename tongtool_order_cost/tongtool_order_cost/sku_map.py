# -*- coding: utf-8 -*-
"""Confirmed June 2026 AMZBAINAUS FBA Tongtool SKU remap (old export name → current master)."""
from __future__ import annotations

import pandas as pd

# 井只维护新名。订单 Google Sheet / 1.4 导出仍可能是改名前的旧名。
# 不要把规则表改回旧名。
OLD_TO_NEW: dict[str, str] = {
    "BNFBAvelvetblack-100": "BNUSFBA-Velvet-Black-100",
    "BNFBAvelvetgray-100": "BNUSFBA-Velvet-Grey-100",
    "BNUSFBA-vel-grey153": "BNUSFBA-Velvet-Grey-153",
    "BNvelvetblack-153fba": "BNUSFBA-Velvet-Black-153",
}

# 通途主档里真实存在，不是 100CM 的笔误。替换订单时不要动。
DO_NOT_TOUCH: frozenset[str] = frozenset({"BNFBAvelvetgray60"})

# 规则表笔误：Foam FBA 只有 BLACK-100。不要把订单 100 改成 97。
RULE_TYPO_FOAM97 = "FoamFBAKZ159410287-BLACK-97"
RULE_CANON_FOAM100 = "FoamFBAKZ159410287-BLACK-100"
CEN_BLACK97 = "CENKZ159410287-BLACK-97"

SKU_COL_CANDIDATES = ("通途SKU", "SKU", "商品SKU", "货品SKU")
QTY_COL_CANDIDATES = ("发货数量", "产品数量", "销量", "订单数量", "数量", "销售数量")


def sku_col(df: pd.DataFrame) -> str:
    names = [str(c).strip() for c in df.columns]
    for want in SKU_COL_CANDIDATES:
        if want in names:
            return str(df.columns[names.index(want)])
    raise KeyError(f"no SKU column in {list(df.columns)[:20]}")


def qty_col(df: pd.DataFrame) -> str | None:
    for c in QTY_COL_CANDIDATES:
        if c in df.columns:
            return c
    return None
