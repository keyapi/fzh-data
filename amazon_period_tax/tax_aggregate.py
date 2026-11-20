# -*- coding: utf-8 -*-
"""Tax 汇总（Colab df6）及辅助透视。"""
from __future__ import annotations

import pandas as pd

from amounts import is_blank, parse_amounts_frame
from exchange_rate import normalize_currency_label, unique_rates_by_key


def enrich_with_fx(df: pd.DataFrame, df_exchange_rate: pd.DataFrame) -> pd.DataFrame:
    """按收款币种补汇率。两侧都先走 normalize_currency_label 再 join。

    结算 txt 里的 currency 与汇率表的「收款币种」都是 3 位代码，但可能带零宽字符/全角字符
    （见 docs/solutions/integration-issues/amazon-period-fx-currency-label-invisible-chars.md），
    不归一化会出现静默的无汇率 → amount人民币 全 0。

    门禁（T01）：空币种键禁止连接；汇率表同币种多汇率报错；被用到的汇率必须有限且 >0；
    join 用 ``validate="many_to_one"``；amount 严格解析，非空非法不再静默变 NaN。
    """
    out = df.copy()
    if "currency" not in out.columns:
        raise ValueError("enrich_with_fx: 数据缺 currency 列，无法补汇率")
    out["currency"] = out["currency"].map(normalize_currency_label)
    blank = is_blank(out["currency"])
    if blank.any():
        raise ValueError(f"enrich_with_fx: {int(blank.sum())} 行币种为空，禁止连接汇率（空币种键）")

    if "amount" not in out.columns:
        raise ValueError("enrich_with_fx: 数据缺 amount 列")
    out["amount"] = parse_amounts_frame(
        out, ["amount"], label="enrich_with_fx", row_key="settlement-id" if "settlement-id" in out.columns else "文件名"
    )["amount"]

    rates = (
        unique_rates_by_key(
            df_exchange_rate,
            key="收款币种",
            used_keys=set(out["currency"]),
            label="汇率表",
        )[["收款币种", "汇率"]]
        .rename(columns={"收款币种": "currency"})
    )
    out = out.merge(rates, how="left", on="currency", validate="many_to_one")
    out["amount人民币"] = out["amount"] * out["汇率"]
    return out


def tax_summary_df6(df1: pd.DataFrame) -> pd.DataFrame:
    """Colab「账号Tax汇总」：description 含 Tax 且 amount-type ∈ ItemPrice/Promotion。"""
    mask = df1["amount-description"].astype(str).str.contains("Tax", na=False) & df1[
        "amount-type"
    ].isin(["ItemPrice", "Promotion"])
    df6 = (
        df1.loc[mask]
        .groupby(["父文件夹名", "子文件夹名", "渠道账号", "currency", "汇率"], dropna=False)[
            ["amount", "amount人民币"]
        ]
        .sum()
        .reset_index()
    )
    df6 = df6.rename(columns={"amount人民币": "Tax amount人民币"})
    return df6


def tax_summary_for_gsheet(
    df6_detail: pd.DataFrame,
    *,
    all_accounts: pd.Series | None = None,
) -> pd.DataFrame:
    """每个渠道账号一行（供 GSheet / Phase 3 合并）。可选补全无 Tax 行的账号（amount=0）。"""
    if df6_detail.empty and all_accounts is None:
        return df6_detail.copy()
    g = (
        df6_detail.groupby("渠道账号", as_index=False)
        .agg(amount=("amount", "sum"), **{"Tax amount人民币": ("Tax amount人民币", "sum")})
        .sort_values("渠道账号")
    )
    if all_accounts is not None:
        base = pd.DataFrame({"渠道账号": pd.Series(all_accounts).dropna().astype(str).unique()})
        g = base.merge(g, on="渠道账号", how="left")
        g["amount"] = g["amount"].fillna(0)
        g["Tax amount人民币"] = g["Tax amount人民币"].fillna(0)
        g = g.sort_values("渠道账号")
    if g["渠道账号"].duplicated().any():
        raise ValueError("Tax 汇总存在重复渠道账号")
    return g


def file_count_by_person(df: pd.DataFrame) -> pd.DataFrame:
    if df.empty:
        return pd.DataFrame(columns=["子文件夹名", "不同文件数"])
    return (
        df.groupby(["子文件夹名"])["文件名"].nunique().reset_index().rename(columns={"文件名": "不同文件数"})
    )
