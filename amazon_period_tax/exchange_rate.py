# -*- coding: utf-8 -*-
"""和财务部共享 / 汇率 — 与 Colab cell 1.1x 一致。"""
from __future__ import annotations

import re
import unicodedata

import numpy as np
import pandas as pd

# 和财务部共享 — 避免 Drive 按标题搜索（易 SSL/限流）
CFO_SPREADSHEET_ID = "1UhFiMF9tLmndoOaz7PaEP_Fz1ZGYK9GVT6hiIYLM8Go"

# 零宽 / 格式化字符（OA 表单下拉值里混进过 U+200C，肉眼不可见）
_INVISIBLE = re.compile(r"[\u00ad\u200b-\u200f\u202a-\u202e\u2060-\u2064\ufeff]")


def normalize_currency_label(value) -> str:
    """统一币种写法：去零宽字符，全角转半角（NFKC），纯 ASCII 统一大写，去首尾空白。

    例：'\\u200c匈牙利福林（HUF）' → '匈牙利福林(HUF)'，才能和汇率表别名对上。
    纯 ASCII 代码 ``usd`` → ``USD``（否则与汇率表 ``USD`` 是两个键，记账会多一行空汇率）。
    中文/混合写法不受大写影响。
    """
    if value is None:
        return ""
    try:
        if pd.isna(value):
            return ""
    except (TypeError, ValueError):
        pass
    s = _INVISIBLE.sub("", str(value))
    s = unicodedata.normalize("NFKC", s).strip()
    if s and s.isascii():
        s = s.upper()
    return s


def unique_rates_by_key(
    df_rates: pd.DataFrame,
    *,
    key: str,
    used_keys: "pd.Series | set | None" = None,
    label: str = "汇率表",
) -> pd.DataFrame:
    """按 ``key`` 归一/校验后返回唯一汇率表（保留原列，``key`` 已归一，``汇率`` 已转数值）。

    门禁（T01）：
    - ``key`` 为空的汇率行不允许参与连接（空币种键禁止连接）；
    - 同一 ``key`` 指向不同汇率 → 报错，不能 ``keep-first`` 掩盖冲突；
    - 被用到的 ``key``：汇率必须存在时有限且 > 0（缺失留给 missing_fx 报告，不在这里吞）。
    """
    if key not in df_rates.columns or "汇率" not in df_rates.columns:
        raise KeyError(f"{label} 缺列 {key!r}/'汇率'")
    rates = df_rates.copy()
    rates[key] = rates[key].map(normalize_currency_label)
    rates["汇率"] = pd.to_numeric(rates["汇率"], errors="coerce")
    blank = rates[key].eq("")
    if (blank & rates["汇率"].notna()).any():
        bad = rates.loc[blank & rates["汇率"].notna(), "汇率"].head(5).tolist()
        raise ValueError(f"{label} 存在空币种键但带汇率的行: {bad!r}")
    rates = rates.loc[~blank]
    numeric = rates.loc[rates["汇率"].notna()]
    conflicts = numeric.groupby(key)["汇率"].nunique()
    bad_keys = conflicts[conflicts > 1].index.tolist()
    if bad_keys:
        raise ValueError(f"{label} 同一 {key} 对应多个汇率（必须唯一）: {bad_keys[:10]!r}")
    rates = numeric.drop_duplicates(subset=[key], keep="first")
    if used_keys is not None:
        used = {normalize_currency_label(x) for x in used_keys if normalize_currency_label(x)}
        hit = rates.loc[rates[key].isin(used)]
        invalid = hit.loc[~np.isfinite(hit["汇率"]) | (hit["汇率"] <= 0)]
        if not invalid.empty:
            raise ValueError(
                f"{label} 汇率必须有限且 >0: "
                f"{invalid[[key, '汇率']].head(10).to_dict('records')!r}"
            )
    return rates


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
