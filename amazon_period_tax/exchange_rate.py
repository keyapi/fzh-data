# -*- coding: utf-8 -*-
"""和财务部共享 / 汇率 — 与 Colab cell 1.1x 一致。"""
from __future__ import annotations

import pandas as pd

# 和财务部共享 — 避免 Drive 按标题搜索（易 SSL/限流）
CFO_SPREADSHEET_ID = "1UhFiMF9tLmndoOaz7PaEP_Fz1ZGYK9GVT6hiIYLM8Go"


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
    df["货币别名"] = df["货币别名"].astype(str).str.replace("，", ",", regex=False)
    df["货币别名"] = df["货币中文名"].astype(str) + "," + df["货币别名"]
    df["货币别名"] = df["货币别名"].str.split(",").apply(lambda x: [e.strip() for e in x if e.strip()])
    exploded = df.explode("货币别名")
    exploded["货币别名"] = exploded["货币别名"].str.strip()
    exploded = exploded.drop(columns=["货币中文名"], errors="ignore")
    exploded = exploded.rename(columns={"货币别名": "货币中文名"})
    exploded = exploded.drop_duplicates(subset=["货币中文名"], keep="first")
    return df[["收款币种", "汇率"]].copy(), exploded
