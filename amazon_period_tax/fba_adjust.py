# -*- coding: utf-8 -*-
"""FBA 费用特例：读 gsheet 规则 + Colab process_fba_orders。"""
from __future__ import annotations

from datetime import datetime

import pandas as pd

FBA_DESCRIPTIONS = (
    "FBAPerUnitFulfillmentFee",
    "Storage Fee",
    "StorageRenewalBilling",
    "FBA Inbound Placement Service Fee",
)

COL_AMOUNT_RMB = "amount人民币"
COL_FBA_RATE = "调整比例amount"
COL_AMOUNT_CHANGE = "调整前-后amount"
COL_AMOUNT_CHANGE_RMB = "调整前-后amount人民币"


def load_fba_rules(gc, *, bucket_name: str, sheet: str = "和财务部共享", ws: str = "账期FBA费用特例") -> pd.DataFrame:
    from amazon_period_tax.exchange_rate import CFO_SPREADSHEET_ID

    sh = gc.open_by_key(CFO_SPREADSHEET_ID)
    ws_obj = sh.worksheet(ws)
    rows = ws_obj.get_all_values()
    if not rows:
        return pd.DataFrame()
    df = pd.DataFrame(rows[1:], columns=rows[0]).replace("", pd.NA)
    ym = datetime.strptime(bucket_name[2:8], "%Y%m")
    df["当月是否执行"] = "否"

    def _parse_ym(raw) -> datetime | None:
        s = str(raw or "").strip()
        if not s or s.lower() == "nan":
            return None
        try:
            return datetime.strptime(s[:7], "%Y-%m")
        except ValueError:
            return None

    for index, row in df.iterrows():
        start_ym = _parse_ym(row.get("执行开始时间"))
        end_ym = _parse_ym(row.get("执行结束时间"))
        if start_ym is None and end_ym is None:
            df.at[index, "当月是否执行"] = "是"
        elif start_ym is None and end_ym is not None:
            if ym <= end_ym:
                df.at[index, "当月是否执行"] = "是"
        elif start_ym is not None and end_ym is None:
            if ym >= start_ym:
                df.at[index, "当月是否执行"] = "是"
        else:
            if start_ym <= ym <= end_ym:
                df.at[index, "当月是否执行"] = "是"
    if "平台SKU" in df.columns:
        df["平台SKU"] = df["平台SKU"].astype(str).str.replace(r"\s+", "", regex=True)
    return df.drop_duplicates(subset=["渠道账号", "平台SKU", "当月是否执行"], keep="first")


def filter_fba_order(df_rule: pd.DataFrame, df_fba: pd.DataFrame, filter_columns: list[str]) -> pd.DataFrame:
    filter_condition = pd.Series([False] * len(df_fba), index=df_fba.index)
    for _, rule in df_rule.iterrows():
        single = pd.Series([True] * len(df_fba), index=df_fba.index)
        for column in filter_columns:
            if column not in df_fba.columns:
                continue
            rule_value = str(rule.get(column if column != "sku" else "平台SKU", "") or "").strip()
            if rule_value:
                single &= df_fba[column].astype(str) == rule_value
        filter_condition |= single
    return df_fba.loc[filter_condition].copy()


def adj_fba_orders_cost(df_fba_orig: pd.DataFrame, filtered: pd.DataFrame) -> pd.DataFrame:
    df = df_fba_orig.copy()
    df["amount"] = pd.to_numeric(df["amount"], errors="coerce")
    df["汇率"] = pd.to_numeric(df["汇率"], errors="coerce")
    df[COL_FBA_RATE] = 1.0
    df["调整前amount"] = df["amount"]
    df.loc[filtered.index, COL_FBA_RATE] = 0.0
    df.loc[filtered.index, "amount"] = 0.0
    cond1 = df["amount-description"].isin(["FBAPerUnitFulfillmentFee"])
    parts = []
    for _, group in df.groupby("渠道账号"):
        group = group.copy()
        cond2 = group["amount-description"].isin(
            ["Storage Fee", "StorageRenewalBilling", "FBA Inbound Placement Service Fee"]
        )
        orig = group.loc[cond1, "调整前amount"].sum()
        mod = group.loc[cond1, "amount"].sum()
        rate = mod / orig if orig else 1.0
        group.loc[cond2, COL_FBA_RATE] = rate
        group.loc[cond2, "amount"] = group.loc[cond2, "amount"] * rate
        parts.append(group)
    result = pd.concat(parts, axis=0)
    result[COL_AMOUNT_CHANGE] = result["调整前amount"] - result["amount"]
    result[COL_AMOUNT_CHANGE_RMB] = result[COL_AMOUNT_CHANGE] * result["汇率"]
    result[COL_AMOUNT_RMB] = result["amount"] * result["汇率"]
    return result


def process_fba_orders(df_rule_exec: pd.DataFrame, df_fba_orig: pd.DataFrame) -> pd.DataFrame:
    rules = df_rule_exec.rename(columns={"平台SKU": "sku"})
    filtered = filter_fba_order(rules, df_fba_orig, ["渠道账号", "sku"])
    return adj_fba_orders_cost(df_fba_orig, filtered)


def fba_summary_df12(processed: pd.DataFrame) -> pd.DataFrame:
    return (
        processed.groupby(["父文件夹名", "子文件夹名", "渠道账号", "currency", "汇率"], dropna=False)[
            ["amount", COL_AMOUNT_RMB, COL_AMOUNT_CHANGE, COL_AMOUNT_CHANGE_RMB]
        ]
        .sum()
        .reset_index()
    )
