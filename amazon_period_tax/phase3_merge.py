# -*- coding: utf-8 -*-
"""Colab「钉钉OA收款费用…」Phase3：OA 定稿 + 汇率 + 渠道账号 + 附加费/Tax → GSheet。"""
from __future__ import annotations

import re
from dataclasses import dataclass, field
from pathlib import Path

import numpy as np
import pandas as pd

from exchange_rate import load_exchange_rate_table
from gsheet_tax import (
    additional_fee_worksheet_name_from_yyyymm,
    open_additional_fee_tax_spreadsheet,
    tax_worksheet_name,
)
from phase3_constants import (
    ADDITIONAL_FEE_COLS,
    APRIL_2026_ALREADY_PROCESSED_APPROVAL_IDS,
    COL_TOTAL_COST,
    COL_TOTAL_COST_RMB,
    LS_COL_COST,
    LS_COL_NEED_NUMERIC,
    OPS_CHANNEL_WS_TITLE,
    OPS_SPREADSHEET_ID,
)
from phase3_gsheet import phase3_spreadsheet_available, read_worksheet_df, write_worksheet_df


def set2after1(ls_cols: list, first_element: str, second_element: str) -> None:
    index_1 = ls_cols.index(first_element)
    index_2 = ls_cols.index(second_element)
    if index_1 < index_2:
        ls_cols.insert(index_1 + 1, ls_cols.pop(index_2))
    else:
        ls_cols.insert(index_1, ls_cols.pop(index_2))


def period_range_from_bucket(bucket: str) -> str:
    m = re.search(r"账期(\d{8}-\d{8})", bucket)
    if not m:
        raise ValueError(f"桶名须含 账期YYYYMMDD-YYYYMMDD: {bucket!r}")
    return m.group(1)


def accounting_yyyymm_from_bucket(bucket: str) -> str:
    return period_range_from_bucket(bucket)[:6]


def load_channel_accounts(gc, exchange_month: str) -> tuple[pd.DataFrame, pd.DataFrame]:
    sh = gc.open_by_key(OPS_SPREADSHEET_ID)
    ws = None
    for w in sh.worksheets():
        if w.title == OPS_CHANNEL_WS_TITLE or ("渠道账号" in w.title and "20260521" in w.title):
            ws = w
            break
    if ws is None:
        raise FileNotFoundError(f"未找到运营渠道账号 ws: {OPS_CHANNEL_WS_TITLE!r}")
    rows = ws.get_all_values()
    df_account = pd.DataFrame(rows[1:], columns=rows[0]).replace("", pd.NA)
    if "渠道账号" not in df_account.columns:
        # 20260521 表头第 3 列常为样例账号名而非「渠道账号」
        if len(df_account.columns) >= 3 and "渠道" in df_account.columns:
            df_account = df_account.rename(columns={df_account.columns[2]: "渠道账号"})
    if "渠道账号" not in df_account.columns:
        raise KeyError(f"渠道账号表无法识别账号列: {list(df_account.columns)[:8]!r}")
    if "渠道账号别名" not in df_account.columns:
        df_account["渠道账号别名"] = ""
    staff_col = f"运营人员{exchange_month}"
    if staff_col not in df_account.columns:
        raise KeyError(f"渠道账号表无列 {staff_col!r}")
    df_account = df_account.copy()
    df_account["运营人员"] = df_account[staff_col].astype(str)
    df_account["渠道账号"] = df_account["渠道账号"].astype(str)
    df_account["渠道账号别名"] = df_account["渠道账号别名"].fillna("").astype(str).str.replace("，", ",", regex=False)
    df_account["渠道账号别名"] = df_account["渠道账号"] + "," + df_account["渠道账号别名"]
    df_account["渠道账号别名"] = df_account["渠道账号别名"].str.split(",").apply(
        lambda x: [e.strip() for e in x if e.strip()]
    )
    df_explode = df_account.explode("渠道账号别名")
    df_explode["渠道账号别名"] = df_explode["渠道账号别名"].str.strip()
    df_explode = df_explode[["渠道", "渠道账号", "渠道账号别名", "运营人员"]].drop_duplicates(
        subset=["渠道账号别名"], keep="first"
    )
    if df_explode["渠道账号别名"].duplicated().any():
        dup = df_explode.loc[df_explode["渠道账号别名"].duplicated(), "渠道账号别名"].unique()
        raise ValueError(f"渠道账号别名重复: {dup[:5]!r}")
    return df_account[["渠道", "渠道账号", "运营人员"]].drop_duplicates("渠道账号"), df_explode


OA_HEADER_ANCHOR_COLS = ("新平台销售账户", "选择平台", "账期日期")


def _dingtalk_oa_has_header_row(df: pd.DataFrame) -> bool:
    col_set = {str(c).strip() for c in df.columns}
    return any(a in col_set for a in OA_HEADER_ANCHOR_COLS)


def read_dingtalk_oa_sheet(path: Path, sheet_name: str, dtype: dict) -> tuple[pd.DataFrame, int]:
    df0 = pd.read_excel(path, sheet_name=sheet_name, header=0, dtype=dtype)
    if _dingtalk_oa_has_header_row(df0):
        return df0, 0
    df1 = pd.read_excel(path, sheet_name=sheet_name, header=1, dtype=dtype)
    if _dingtalk_oa_has_header_row(df1):
        return df1, 1
    preview = pd.read_excel(path, sheet_name=sheet_name, header=None, nrows=25)
    for i in range(len(preview)):
        for v in preview.iloc[i].tolist():
            if isinstance(v, str) and v.strip() == "新平台销售账户":
                df = pd.read_excel(path, sheet_name=sheet_name, header=i, dtype=dtype)
                if _dingtalk_oa_has_header_row(df):
                    return df, i
                break
    return df0, 0


def load_oa_dataframe(path: Path) -> pd.DataFrame:
    dtype = {"发起人工号": str, "关联审批单": str, "审批编号": str}
    xp = pd.ExcelFile(path)
    if "核算行" in xp.sheet_names:
        df = pd.read_excel(path, sheet_name="核算行", dtype=dtype)
        return df
    frames = []
    for sn in xp.sheet_names:
        try:
            df_s, _hdr = read_dingtalk_oa_sheet(path, sn, dtype)
        except Exception:
            continue
        if not _dingtalk_oa_has_header_row(df_s):
            continue
        frames.append(df_s)
    if not frames:
        raise ValueError(f"无法读取 OA Excel: {path}")
    return pd.concat(frames, ignore_index=True)


def normalize_receipt_columns(df: pd.DataFrame) -> pd.DataFrame:
    out = df.copy()
    if "账期收款额" in out.columns:
        if "应收金额" in out.columns:
            out["应收金额"] = out["应收金额"].fillna(out["账期收款额"])
            out = out.drop(columns=["账期收款额"])
        else:
            out = out.rename(columns={"账期收款额": "应收金额"})
    return out


def drop_april_resubmit_rows(df: pd.DataFrame, accounting_yyyymm: str) -> tuple[pd.DataFrame, int]:
    if "审批编号" not in df.columns:
        return df, 0
    out = df.copy()
    out["审批编号"] = out["审批编号"].astype(str).str.strip().replace({"nan": "", "None": ""})
    mask = out["审批编号"].isin(APRIL_2026_ALREADY_PROCESSED_APPROVAL_IDS) & (out["审批编号"] != "")
    n = int(mask.sum())
    if n and accounting_yyyymm >= "202605":
        out = out.loc[~mask].reset_index(drop=True)
    return out, n


def _resolve_sales_accounts(df: pd.DataFrame) -> pd.DataFrame:
    out = df.copy()
    col_amz = "亚马逊销售账户"
    col_new = "新平台销售账户"
    if col_amz not in out.columns:
        out[col_amz] = None
    if col_new not in out.columns:
        out[col_new] = None
    amz_cols = [c for c in out.columns if str(c).startswith("AMZ") and str(c).endswith("账户")]

    def extract_amz_account(filename: str) -> str | None:
        m = re.match(r"^(AMZ[^-]*)-", str(filename or ""))
        return m.group(1) if m else None

    out["提取账期明细中AMZ账号"] = out.get("账期明细", pd.Series(dtype=object)).fillna("").astype(str).apply(
        extract_amz_account
    )

    def update_sales_account(row: pd.Series) -> str:
        prefix = row.get(col_new)
        if isinstance(prefix, str) and prefix.strip():
            matched = next((c for c in out.columns if str(c).startswith(prefix)), None)
            if matched:
                new_value = row.get(matched)
                if isinstance(new_value, str) and len(new_value) > len(prefix):
                    return new_value
        return row.get(col_new)

    if amz_cols:
        for c in amz_cols:
            out[col_amz] = out[col_amz].fillna(out[c])
    out[col_amz] = out[col_amz].fillna(out["提取账期明细中AMZ账号"])
    out[col_new] = out.apply(update_sales_account, axis=1)
    out["销售账户"] = out[col_amz].fillna(out[col_new])
    if "独立站账户" in out.columns:
        out["销售账户"] = out["销售账户"].fillna(out["独立站账户"])
    return out


def build_row_level_df(
    df_orig: pd.DataFrame,
    *,
    df_exchange_rate: pd.DataFrame,
    df_explode: pd.DataFrame,
    df_rate_explode: pd.DataFrame,
) -> tuple[pd.DataFrame, pd.DataFrame]:
    df = normalize_receipt_columns(df_orig.copy())
    df = _resolve_sales_accounts(df)
    if "币种" in df.columns:
        df = df.rename(columns={"币种": "货币中文名"})
    df.drop(columns=["收款币种", "汇率"], inplace=True, errors="ignore")
    df = df.merge(df_rate_explode[["货币中文名", "收款币种", "汇率"]], how="left", on="货币中文名")
    df.loc[df["销售账户"] == "DLZ", "销售账户"] = "DLZPPL"
    df.loc[df["销售账户"] == "PPL", "销售账户"] = "DLZPPL"
    df["销售账户"] = df["销售账户"].astype(str).str.strip()
    df = df.merge(
        df_explode[["渠道账号", "渠道账号别名", "运营人员"]],
        how="left",
        left_on="销售账户",
        right_on="渠道账号别名",
    )
    numeric_cols = [c for c in LS_COL_NEED_NUMERIC if c in df.columns]
    df[numeric_cols] = df[numeric_cols].replace(",", "", regex=True).apply(pd.to_numeric, errors="coerce")
    df[numeric_cols] = df[numeric_cols].fillna(0)
    cost_cols = [c for c in LS_COL_COST if c in df.columns]
    df[COL_TOTAL_COST] = df[cost_cols].sum(axis=1)
    df[COL_TOTAL_COST_RMB] = df[COL_TOTAL_COST] * df["汇率"]
    rmb_cols = [f"{x}_人民币" for x in numeric_cols]
    df[rmb_cols] = df[numeric_cols].multiply(df["汇率"], axis="index")
    if "销售额" in df.columns and "销售额_人民币" in df.columns and "应收金额_人民币" in df.columns:
        sales_index = df.columns.get_loc("销售额")
        df.insert(
            sales_index + 1,
            "收款比例",
            np.where(
                df["销售额_人民币"] == 0,
                0.0,
                df["应收金额_人民币"] / df["销售额_人民币"],
            ),
        )
    approval_filter = (df["审批状态"].isin(["完成", "审批中"])) & (df["审批结果"] != "拒绝")
    return df, approval_filter


def build_group_account_cost(
    df: pd.DataFrame,
    approval_filter: pd.Series,
    *,
    df_rate_explode: pd.DataFrame,
    df_account: pd.DataFrame,
) -> pd.DataFrame:
    numeric_cols = [c for c in LS_COL_NEED_NUMERIC if c in df.columns]
    rmb_cols = [f"{x}_人民币" for x in numeric_cols]
    g = (
        df.loc[approval_filter]
        .groupby(by=["选择平台", "渠道账号", "收款归属", "收款币种"], dropna=False)[numeric_cols + rmb_cols]
        .sum()
        .reset_index()
    )
    sales_rmb_index = g.columns.get_loc("销售额_人民币")
    g.insert(
        sales_rmb_index + 1,
        "平均收款比例",
        np.where(
            g["销售额_人民币"] == 0,
            0.0,
            g["应收金额_人民币"] / g["销售额_人民币"],
        ),
    )
    cost_cols = [c for c in LS_COL_COST if c in g.columns]
    g[COL_TOTAL_COST] = g[cost_cols].sum(axis=1)
    fx = df_rate_explode.drop_duplicates(subset=["收款币种"], keep="first")[
        ["货币中文名", "收款币种", "汇率"]
    ]
    g = g.merge(fx, how="left", on="收款币种")
    g = g.merge(df_account[["渠道", "渠道账号", "运营人员"]], how="left", on="渠道账号")
    g[COL_TOTAL_COST_RMB] = g[COL_TOTAL_COST] * g["汇率"]
    cols = g.columns.tolist()
    cols.insert(0, cols.pop(cols.index("选择平台")))
    for a, b in [
        ("选择平台", "渠道"),
        ("渠道", "渠道账号"),
        ("渠道账号", "运营人员"),
        ("运营人员", "货币中文名"),
        ("货币中文名", "收款币种"),
        ("收款币种", "汇率"),
        ("汇率", "收款归属"),
        ("收款归属", "应收金额"),
        ("应收金额", "销售额"),
        ("销售额", "应收金额_人民币"),
        ("应收金额_人民币", "销售额_人民币"),
        ("销售额_人民币", "平均收款比例"),
        ("平均收款比例", COL_TOTAL_COST),
        (COL_TOTAL_COST, COL_TOTAL_COST_RMB),
    ]:
        if a in cols and b in cols:
            set2after1(cols, a, b)
    return g[cols]


def build_rmb_by_account(df_group: pd.DataFrame) -> pd.DataFrame:
    cost_rmb = [f"{x}_人民币" for x in LS_COL_COST if f"{x}_人民币" in df_group.columns]
    insert_cols = [COL_TOTAL_COST_RMB] + [c for c in cost_rmb if c != COL_TOTAL_COST_RMB]
    return (
        df_group.groupby(by=["渠道", "渠道账号", "运营人员"], dropna=False)[insert_cols]
        .sum()
        .reset_index()
    )


def load_additional_fee_grouped(gc, exchange_month: str, df_explode: pd.DataFrame) -> pd.DataFrame:
    ws_name = additional_fee_worksheet_name_from_yyyymm(exchange_month)
    sh = open_additional_fee_tax_spreadsheet(gc)
    rows = sh.worksheet(ws_name).get_all_values()
    raw = pd.DataFrame(rows[1:], columns=rows[0]).replace("", pd.NA)
    if "运营人员" in raw.columns:
        raw["运营人员"] = raw["运营人员"].fillna("")
    keep_cols = ["渠道账号"] + [c for c in ADDITIONAL_FEE_COLS if c in raw.columns]
    raw = raw[[c for c in keep_cols if c in raw.columns]]
    fee_cols = [c for c in ADDITIONAL_FEE_COLS if c in raw.columns and c != "附加费累加人民币"]
    for c in raw.columns:
        if c == "渠道账号":
            continue
        raw[c] = raw[c].astype(str).str.replace(",", "", regex=False)
        raw[c] = pd.to_numeric(raw[c], errors="coerce").fillna(0)
    if fee_cols and "附加费累加人民币" not in raw.columns:
        raw["附加费累加人民币"] = raw[fee_cols].sum(axis=1)
    sum_cols = ["附加费累加人民币"] + fee_cols
    if "渠道账号" in raw.columns:
        return raw.groupby("渠道账号")[sum_cols].sum().reset_index()
    raw = raw.rename(columns={"渠道账号": "渠道账号别名"})
    raw = raw.merge(df_explode[["渠道账号", "渠道账号别名"]], how="left", on="渠道账号别名")
    raw = raw.drop(columns=["渠道账号别名"], errors="ignore")
    return raw.groupby("渠道账号")[sum_cols].sum().reset_index()


def load_tax_grouped(gc, bucket: str) -> pd.DataFrame:
    ws_name = tax_worksheet_name(bucket)
    sh = open_additional_fee_tax_spreadsheet(gc)
    rows = sh.worksheet(ws_name).get_all_values()
    raw = pd.DataFrame(rows[1:], columns=rows[0]).replace("", pd.NA)
    if "渠道账号" not in raw.columns or "Tax amount人民币" not in raw.columns:
        return pd.DataFrame(columns=["渠道账号", "Tax amount人民币"])
    raw["Tax amount人民币"] = pd.to_numeric(
        raw["Tax amount人民币"].astype(str).str.replace(",", "", regex=False),
        errors="coerce",
    ).fillna(0)
    return raw.groupby("渠道账号")["Tax amount人民币"].sum().reset_index()


def merge_rmb_tax_additional(
    df_rmb: pd.DataFrame,
    *,
    df_sep: pd.DataFrame,
    df_tax: pd.DataFrame,
    df_account: pd.DataFrame,
) -> pd.DataFrame:
    base = df_rmb.drop(columns=["渠道", "运营人员"], errors="ignore")
    out = base.merge(df_sep, how="outer", on="渠道账号")
    if not df_tax.empty:
        out = out.merge(df_tax, how="outer", on="渠道账号")
    out = out.merge(df_account[["渠道", "渠道账号", "运营人员"]], how="outer", on="渠道账号")
    cols = out.columns.tolist()
    cols.insert(0, cols.pop(cols.index("渠道")))
    for a, b in [
        ("渠道", "渠道账号"),
        ("渠道账号", "运营人员"),
        ("运营人员", COL_TOTAL_COST_RMB),
        (COL_TOTAL_COST_RMB, "Tax amount人民币"),
    ]:
        if a in cols and b in cols:
            set2after1(cols, a, b)
    return out[cols]


def collection_rate_by_receipt(df_group: pd.DataFrame) -> pd.DataFrame:
    g = df_group.groupby("收款归属").agg({"应收金额_人民币": "sum", "销售额_人民币": "sum"})
    g["平均收款比例"] = g["应收金额_人民币"] / g["销售额_人民币"]
    g = g.replace([np.inf, -np.inf], np.nan)
    return g.reset_index()


def collection_rate_by_staff(df_group: pd.DataFrame) -> pd.DataFrame:
    rmb_cols = [c for c in df_group.columns if c.endswith("_人民币")]
    g = df_group.groupby("运营人员")[rmb_cols].sum()
    out = g.copy()
    if "销售额_人民币" in out.columns:
        for col in rmb_cols:
            if col != "销售额_人民币":
                new_name = col.replace("_人民币", "_比例")
                ratio = out[col] / out["销售额_人民币"]
                ratio = ratio.replace([np.inf, -np.inf], np.nan).fillna(1.0)
                out[new_name] = ratio
    return out.reset_index()


def apply_fba_to_group(
    df_group: pd.DataFrame,
    gc,
    period_range: str,
) -> tuple[pd.DataFrame, bool]:
    ws_name = f"{period_range}FBA费用扣减后分类汇总"
    df_fba = read_worksheet_df(gc, ws_name)
    if df_fba.empty or "渠道账号" not in df_fba.columns:
        return df_group, False
    for c in ("amount", "amount人民币", "调整前-后amount", "调整前-后amount人民币"):
        if c in df_fba.columns:
            df_fba[c] = pd.to_numeric(df_fba[c], errors="coerce").fillna(0)
    fb = df_fba.groupby("渠道账号").agg({"调整前-后amount人民币": "sum"}).reset_index()
    merged = df_group.merge(fb, how="left", on="渠道账号")
    merged["调整前-后amount人民币"] = merged["调整前-后amount人民币"].fillna(0.0)
    col_fba = "FBA费用_人民币"
    merged = merged.rename(columns={"调整前-后amount人民币": col_fba})
    merged[col_fba] = merged[col_fba] * -1
    merged["加上FBA费用_应收金额_人民币"] = merged["应收金额_人民币"] + merged[col_fba]
    merged["扣减FBA费用_佣金_人民币"] = merged["佣金_人民币"] - merged[col_fba]
    return merged, True


@dataclass
class Phase3Report:
    bucket: str
    period_range: str
    exchange_month: str
    input_xlsx: str
    row_level_rows: int = 0
    group_rows: int = 0
    rmb_rows: int = 0
    merged_rows: int = 0
    unmatched_sales_account_rows: int = 0
    april_dropped: int = 0
    tax_sum_rmb: float | None = None
    warnings: list[str] = field(default_factory=list)
    worksheets_written: list[str] = field(default_factory=list)


def run_phase3(
    *,
    gc,
    input_xlsx: Path,
    bucket: str,
    exchange_month: str,
    write_gsheet: bool = False,
) -> tuple[Phase3Report, dict[str, pd.DataFrame]]:
    period_range = period_range_from_bucket(bucket)
    yyyymm = exchange_month.strip()
    if yyyymm != accounting_yyyymm_from_bucket(bucket):
        raise ValueError(f"--exchange-month {yyyymm} 与桶 {bucket} 不一致")

    df_orig = load_oa_dataframe(input_xlsx)
    df_orig, april_n = drop_april_resubmit_rows(df_orig, yyyymm)
    df_rate, df_rate_explode = load_exchange_rate_table(gc, month_col=yyyymm)
    df_account, df_explode = load_channel_accounts(gc, yyyymm)

    df, approval_filter = build_row_level_df(
        df_orig, df_exchange_rate=df_rate, df_explode=df_explode, df_rate_explode=df_rate_explode
    )
    unmatched = int(((df["渠道账号"].isna()) | (df["渠道账号"] == "")).sum())
    df_group = build_group_account_cost(
        df, approval_filter, df_rate_explode=df_rate_explode, df_account=df_account
    )
    df_rmb = build_rmb_by_account(df_group)
    df_sep = load_additional_fee_grouped(gc, yyyymm, df_explode)
    df_tax = load_tax_grouped(gc, bucket)
    df_merged = merge_rmb_tax_additional(df_rmb, df_sep=df_sep, df_tax=df_tax, df_account=df_account)

    rep = Phase3Report(
        bucket=bucket,
        period_range=period_range,
        exchange_month=yyyymm,
        input_xlsx=str(input_xlsx),
        row_level_rows=len(df),
        group_rows=len(df_group),
        rmb_rows=len(df_rmb),
        merged_rows=len(df_merged),
        unmatched_sales_account_rows=unmatched,
        april_dropped=april_n,
        tax_sum_rmb=float(df_tax["Tax amount人民币"].sum()) if not df_tax.empty else None,
    )
    if unmatched:
        rep.warnings.append(f"渠道账号未匹配 {unmatched} 行（销售账户→别名表）")
    if df_merged["渠道账号"].duplicated().any():
        rep.warnings.append("合并后渠道账号重复")

    frames = {
        "row_level": df,
        "group_account": df_group,
        "rmb_by_account": df_rmb,
        "merged_rmb": df_merged,
        "collection_rate_receipt": collection_rate_by_receipt(df_group),
        "collection_rate_staff": collection_rate_by_staff(df_group),
    }

    df_group_fba, has_fba = df_group, False
    if phase3_spreadsheet_available(gc):
        df_group_fba, has_fba = apply_fba_to_group(df_group, gc, period_range)
    else:
        rep.warnings.append("Phase3 目标 GSheet 当前不可读，已跳过 FBA 工作表合并")
    if has_fba:
        frames["group_account_fba"] = df_group_fba

    if write_gsheet:
        if not phase3_spreadsheet_available(gc):
            raise PermissionError(
                "无法 open_by_key Phase3 表（钉钉OA收款费用…）。"
                "请把服务账号加入该 Spreadsheet 协作后再 --write-gsheet。"
            )
        ws_main = period_range
        ws_orig = f"{period_range}原始"
        ws_rmb = f"人民币{period_range}"
        ws_rate_receipt = f"{period_range}收款比例收款归属"
        ws_rate_staff = f"{period_range}收款比例运营人员"
        write_worksheet_df(gc, df_group, worksheet=ws_main)
        write_worksheet_df(gc, df, worksheet=ws_orig)
        write_worksheet_df(gc, df_merged, worksheet=ws_rmb)
        write_worksheet_df(gc, frames["collection_rate_receipt"], worksheet=ws_rate_receipt)
        write_worksheet_df(gc, frames["collection_rate_staff"], worksheet=ws_rate_staff)
        rep.worksheets_written = [ws_main, ws_orig, ws_rmb, ws_rate_receipt, ws_rate_staff]
        from phase3_gsheet import sort_phase3_tabs

        sort_phase3_tabs(gc, pin_worksheet=ws_main)

    return rep, frames
