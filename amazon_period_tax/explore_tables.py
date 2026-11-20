# -*- coding: utf-8 -*-
"""Colab §2.2 探索用透视表（科目/FBA/订单/退款）— 供 Excel 多 sheet，Tax 主线外仅供参考。"""
from __future__ import annotations

import numpy as np
import pandas as pd

from fba_adjust import (
    COL_AMOUNT_RMB,
    fba_summary_df12,
    load_fba_rules,
    process_fba_orders,
)
from tax_aggregate import tax_summary_df6, tax_summary_for_gsheet


def build_exploration_tables(
    df1: pd.DataFrame,
    gc,
    *,
    bucket_name: str,
) -> dict[str, pd.DataFrame]:
    """返回与 Colab cell 17 同名的 sheet 字典（探索用）。"""
    col_rmb = COL_AMOUNT_RMB
    out: dict[str, pd.DataFrame] = {}

    out["数据"] = df1
    out["提交文件数"] = (
        df1.groupby(["子文件夹名"])["文件名"].nunique().reset_index().rename(columns={"文件名": "不同文件数"})
    )
    out["金额分类汇总"] = (
        df1.groupby(["transaction-type", "amount-type", "amount-description", "currency"])[[ "amount", col_rmb]]
        .sum()
        .reset_index()
    )
    out["账号金额分类汇总"] = (
        df1.groupby(["渠道账号", "amount-description", "currency"])[["amount", col_rmb]].sum().reset_index()
    )
    df5 = (
        df1.loc[df1["amount-description"] == "Tax"]
        .groupby(["父文件夹名", "子文件夹名", "渠道账号", "amount-description", "currency", "汇率"])[
            ["amount", col_rmb]
        ]
        .sum()
        .reset_index()
    )
    df5 = df5.rename(columns={col_rmb: f"Tax {col_rmb}"})
    out["账号Tax汇总老算法不对截至202312"] = df5

    df6 = tax_summary_df6(df1)
    out["账号Tax汇总"] = df6
    out["账号Tax汇总_按渠道账号单行"] = tax_summary_for_gsheet(
        df6, all_accounts=df1["渠道账号"].dropna().unique()
    )

    order_rev = df1.loc[
        (df1["transaction-type"] == "Order") & (df1["amount-type"].isin(["ItemPrice", "Promotion"]))
    ].copy()
    order_qty = df1.loc[
        (df1["transaction-type"] == "Order")
        & (df1["amount-type"] == "ItemPrice")
        & (df1["amount-description"] == "Principal")
    ].copy()
    g_no_sku = ["渠道账号", "transaction-type", "order-id", "currency", "汇率", "fulfillment-id"]
    g_sku = ["渠道账号", "transaction-type", "order-id", "sku", "currency", "汇率", "fulfillment-id"]
    agg = ["amount", col_rmb]
    out["订单号销售额"] = order_rev.groupby(g_no_sku)[agg].sum().reset_index()
    df8_qty = order_qty.groupby(g_sku)[["quantity-purchased"]].sum().reset_index()
    df8_rev = order_rev.groupby(g_sku)[agg].sum().reset_index()
    order_qty["quantity-purchased"] = order_qty["quantity-purchased"].fillna(0).astype(int)
    out["订单号SKU数量销售额"] = df8_qty.merge(df8_rev, on=g_sku, how="left")

    ref_rev = df1.loc[
        (df1["transaction-type"].isin(["Refund", "A-to-z Guarantee Refund"]))
        & (df1["amount-type"].isin(["ItemPrice", "Promotion"]))
    ].copy()
    ref_qty = df1.loc[
        (df1["transaction-type"].isin(["Refund", "A-to-z Guarantee Refund"]))
        & (df1["amount-type"] == "ItemPrice")
        & (df1["amount-description"] == "Principal")
    ].copy()
    ref_qty["quantity-purchased"] = ref_qty["quantity-purchased"].fillna(1).astype(int)
    out["订单号退款额"] = ref_rev.groupby(g_no_sku)[agg].sum().reset_index()
    df10_qty = ref_qty.groupby(g_sku)[["quantity-purchased"]].sum().reset_index()
    df10_rev = ref_rev.groupby(g_sku)[agg].sum().reset_index()
    out["订单号SKU数量退款额"] = df10_qty.merge(df10_rev, on=g_sku, how="right")

    merged = pd.merge(
        df10_qty.merge(df10_rev, on=g_sku, how="right", suffixes=("_q", "_r")),
        out["订单号SKU数量销售额"],
        on=["渠道账号", "order-id", "sku", "currency", "汇率"],
        how="left",
        suffixes=("_refund", "_sale"),
    )
    if not merged.empty and "amount_refund" in merged.columns:
        merged["ratio"] = np.abs(merged["amount_refund"]) / merged["amount_sale"].replace(0, np.nan)
        merged["ratio"] = merged["ratio"].replace([np.inf, -np.inf], 1).fillna(1)
        merged["quantity-purchased-updated"] = np.ceil(
            merged.get("quantity-purchased_sale", 0) * merged["ratio"]
        ).fillna(1)
    out["订单号SKU借用数量退款额"] = merged

    df_fba = df1[df1["amount-description"].isin(
        [
            "FBAPerUnitFulfillmentFee",
            "Storage Fee",
            "StorageRenewalBilling",
            "FBA Inbound Placement Service Fee",
        ]
    )].copy()
    out["FBA费用原始"] = df_fba
    rules = load_fba_rules(gc, bucket_name=bucket_name)
    rules_exec = rules.loc[rules["当月是否执行"] == "是"].copy()
    if not df_fba.empty and not rules_exec.empty:
        rules_exec = rules_exec.rename(columns={"平台SKU": "sku"})
        processed = process_fba_orders(rules_exec, df_fba)
        out["FBA费用扣减后"] = processed
        out["FBA费用扣减后分类汇总"] = fba_summary_df12(processed)
    else:
        out["FBA费用扣减后"] = df_fba.iloc[0:0].copy()
        out["FBA费用扣减后分类汇总"] = pd.DataFrame()

    return out