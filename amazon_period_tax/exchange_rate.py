# -*- coding: utf-8 -*-
"""和财务部共享 / 汇率 — 与 Colab cell 1.1x 一致。"""
from __future__ import annotations

import re
import unicodedata

import pandas as pd

# 和财务部共享 — 避免 Drive 按标题搜索（易 SSL/限流）
CFO_SPREADSHEET_ID = "1UhFiMF9tLmndoOaz7PaEP_Fz1ZGYK9GVT6hiIYLM8Go"

# 零宽 / 格式化字符（OA 表单下拉值里混进过 U+200C，肉眼不可见）
_INVISIBLE = re.compile(r"[\u00ad\u200b-\u200f\u202a-\u202e\u2060-\u2064\ufeff]")


def normalize_currency_label(value) -> str:
    """统一币种写法：去零宽字符，全角转半角（NFKC），去首尾空白。

    例：'\\u200c匈牙利福林（HUF）' → '匈牙利福林(HUF)'，才能和汇率表别名对上。
    """
    if value is None:
        return ""
    try:
        if pd.isna(value):
            return ""
    except (TypeError, ValueError):
        pass
    s = _INVISIBLE.sub("", str(value))
    s = unicodedata.normalize("NFKC", s)
    return s.strip()


def load_exchange_rate_table(
    gc,
    *,
    sheet_name: str = "和财务部共享",
    worksheet: str = "汇率",
    month_col: str,
) -> tuple[pd.DataFrame, pd.DataFrame]:
    """返回 (df_exchange_rate 含列 收款币种+汇率, df_explode 用于 merge on currency)。"""
    sh = gc.open_by_key(CFO_SPREADSHEET_ID)
    ws = sh.worksheet(worksheet)
    rows = ws.get_all_values()
    if not rows:
        raise ValueError(f"汇率 worksheet 为空: {worksheet}")
    raw = pd.DataFrame(rows[1:], columns=rows[0]).replace("", pd.NA)
    if month_col not in raw.columns:
        raise KeyError(f"汇率表无列 {month_col!r}，现有: {list(raw.columns)[-6:]}")
    df = raw.copy()
    df["汇率"] = pd.to_numeric(df[month_col], errors="coerce")
    df["货币中文名"] = df["货币中文名"].map(normalize_currency_label)
    df["货币别名"] = df["货币别名"].map(normalize_currency_label)

    # 同一收款币种只能有一行：否则 merge(validate="many_to_one") 会把 Tax 乘多遍。
    code = df["收款币种"].map(normalize_currency_label)
    dup_code = df.loc[code.ne("") & code.duplicated(keep=False), "收款币种"]
    if not dup_code.empty:
        raise ValueError(f"汇率表 收款币种 重复（必须唯一）: {sorted(set(dup_code.astype(str)))[:10]!r}")

    df["货币别名"] = df["货币中文名"] + "," + df["货币别名"]
    df["货币别名"] = df["货币别名"].str.split(",").apply(lambda x: [e.strip() for e in x if e.strip()])
    exploded = df.explode("货币别名")
    exploded["货币别名"] = exploded["货币别名"].str.strip()
    exploded = exploded.drop(columns=["货币中文名"], errors="ignore")
    exploded = exploded.rename(columns={"货币别名": "货币中文名"})
    exploded = exploded.loc[exploded["货币中文名"].astype(str).str.strip().ne("")]

    # 同一中文名/别名映射到不同币种或不同汇率 → 歧义，直接报错（不再静默 keep-first）。
    dup_name = exploded.loc[exploded["货币中文名"].duplicated(keep=False)]
    if not dup_name.empty:
        conflicts = dup_name.groupby("货币中文名").agg(
            币种数=("收款币种", "nunique"), 汇率数=("汇率", "nunique")
        )
        bad = conflicts[(conflicts["币种数"] > 1) | (conflicts["汇率数"] > 1)].index.tolist()
        if bad:
            raise ValueError(f"汇率表 货币中文名/别名 指向不同币种或汇率: {bad[:10]!r}")
        exploded = exploded.drop_duplicates(subset=["货币中文名"], keep="first")
    return df[["收款币种", "汇率"]].copy(), exploded
