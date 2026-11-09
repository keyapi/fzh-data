# -*- coding: utf-8 -*-
"""Tax 汇总（Colab df6）及辅助透视。"""
from __future__ import annotations

import pandas as pd


def enrich_with_fx(df: pd.DataFrame, df_exchange_rate: pd.DataFrame) -> pd.DataFrame:
    out = df.copy()
    out = out.merge(
        df_exchange_rate[["收款币种", "汇率"]],
        how="left",
        left_on="currency",
        right_on="收款币种",
    )
    out["amount"] = pd.to_numeric(out["amount"], errors="coerce")
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
