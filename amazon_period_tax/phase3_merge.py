# -*- coding: utf-8 -*-
"""Colab「钉钉OA收款费用…」Phase3：OA 定稿 + 汇率 + 渠道账号 + 附加费/Tax → GSheet。"""
from __future__ import annotations

import re
import sys
from dataclasses import dataclass, field
from pathlib import Path

import numpy as np
import pandas as pd

from exchange_rate import load_exchange_rate_table, normalize_currency_label
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

_DING = Path(__file__).resolve().parents[1] / "dingtalk" / "dingtalk_oa_approval"
if str(_DING) not in sys.path:
    sys.path.insert(0, str(_DING))


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

    acct_view = df_account[["渠道", "渠道账号", "运营人员"]]
    dup_mask = acct_view["渠道账号"].duplicated(keep=False)
    if dup_mask.any():
        conflicts = acct_view.loc[dup_mask].groupby("渠道账号")[["渠道", "运营人员"]].nunique()
        bad = conflicts.loc[(conflicts > 1).any(axis=1)].index.tolist()
        if bad:
            raise ValueError(f"渠道账号表重复账号且渠道/运营人员不一致（无法唯一合并）: {bad[:5]!r}")
        acct_view = acct_view.drop_duplicates("渠道账号", keep="first")
    return acct_view, df_explode


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


def load_oa_dataframe(path: Path, failures_out: list[str] | None = None) -> pd.DataFrame:
    """读 OA 导出 Excel。

    sheet 读取异常不再静默 ``continue``：记录到 ``failures_out``（默认由调用方转 warnings，
    ``--strict`` 时据此非 0），全部 sheet 都读不出才 raise。
    """
    dtype = {"发起人工号": str, "关联审批单": str, "审批编号": str}
    xp = pd.ExcelFile(path)
    if "核算行" in xp.sheet_names:
        df = pd.read_excel(path, sheet_name="核算行", dtype=dtype)
        return df
    frames = []
    failures: list[str] = []
    for sn in xp.sheet_names:
        try:
            df_s, _hdr = read_dingtalk_oa_sheet(path, sn, dtype)
        except Exception as e:
            failures.append(f"FAIL-SHEET {sn}: {e}")
            continue
        if not _dingtalk_oa_has_header_row(df_s):
            continue
        frames.append(df_s)
    if failures_out is not None:
        failures_out.extend(failures)
    if not frames:
        raise ValueError(f"无法读取 OA Excel: {path}；sheet 读取失败: {failures or '无可用表头'}")
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
    if "货币中文名" in df.columns:
        df["货币中文名"] = df["货币中文名"].map(normalize_currency_label)
    df.drop(columns=["收款币种", "汇率"], inplace=True, errors="ignore")
    df = df.merge(
        df_rate_explode[["货币中文名", "收款币种", "汇率"]],
        how="left",
        on="货币中文名",
        validate="many_to_one",
    )
    df.loc[df["销售账户"] == "DLZ", "销售账户"] = "DLZPPL"
    df.loc[df["销售账户"] == "PPL", "销售账户"] = "DLZPPL"
    df["销售账户"] = df["销售账户"].astype(str).str.strip()
    df = df.merge(
        df_explode[["渠道账号", "渠道账号别名", "运营人员"]],
        how="left",
        left_on="销售账户",
        right_on="渠道账号别名",
        validate="many_to_one",
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
    # Colab cell 8：只统计「完成/审批中且非拒绝」的单据，按渠道账号计数；未通过的行留空
    df["渠道账号正确提交次数"] = np.nan
    approved = df.loc[approval_filter]
    if not approved.empty and "渠道账号" in approved.columns:
        counts = approved.groupby("渠道账号")["渠道账号"].transform("count")
        df.loc[approval_filter, "渠道账号正确提交次数"] = counts
    return df, approval_filter


def find_unmatched_currency(df: pd.DataFrame) -> pd.DataFrame:
    """币种没能从汇率表匹配到、但金额不为 0 的行（静默变 0 的根因兜底）。"""
    amount_cols = [c for c in ["应收金额", "销售额", *LS_COL_COST] if c in df.columns]
    if "汇率" not in df.columns or not amount_cols:
        return pd.DataFrame()
    amounts = df[amount_cols].apply(pd.to_numeric, errors="coerce").fillna(0).abs().sum(axis=1)
    mask = df["汇率"].isna() & (amounts > 0)
    cols = [c for c in ["审批编号", "销售账户", "渠道账号", "货币中文名", "应收金额", "销售额"] if c in df.columns]
    out = df.loc[mask, cols].copy()
    out["外币金额合计"] = amounts[mask]
    return out


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
    g = g.merge(fx, how="left", on="收款币种", validate="many_to_one")
    g = g.merge(
        df_account[["渠道", "渠道账号", "运营人员"]],
        how="left",
        on="渠道账号",
        validate="many_to_one",
    )
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


def _alias_resolver(df_explode: pd.DataFrame | None):
    """返回 (resolve, known)：把附加费/Tax 表里的渠道账号别名归一到规范账号。"""
    from channel_canonical import canonical_account

    alias_map: dict[str, str] = {}
    if df_explode is not None and not df_explode.empty:
        for canon, alias in zip(df_explode["渠道账号"], df_explode["渠道账号别名"]):
            alias_map[str(alias).strip().upper()] = str(canon).strip()
    known = {str(a).strip() for a in (df_explode["渠道账号"] if df_explode is not None else [])}

    def resolve(value) -> str:
        key = str(value).strip()
        hit = alias_map.get(key.upper())
        if hit:
            return hit
        canon = canonical_account(key)
        return canon or key

    return resolve, known


def _read_fee_worksheet(gc, ws_name: str, *, allow_empty: bool) -> pd.DataFrame | None:
    """读附加费&Tax 表某 ws；不存在时 allow_empty 返回 None，否则抛错。"""
    sh = open_additional_fee_tax_spreadsheet(gc)
    try:
        rows = sh.worksheet(ws_name).get_all_values()
    except Exception:
        if allow_empty:
            return None
        raise
    if not rows:
        if allow_empty:
            return None
        raise ValueError(f"工作表 {ws_name} 为空")
    return pd.DataFrame(rows[1:], columns=rows[0]).replace("", pd.NA)


def load_additional_fee_grouped(
    gc,
    exchange_month: str,
    df_explode: pd.DataFrame,
    *,
    allow_empty: bool = False,
) -> tuple[pd.DataFrame, list[str]]:
    """读「附加费{YYYYMM}」并按别名归一化渠道账号后求和。

    必需列：``渠道账号`` + 至少一列附加费金额（``附加费累加人民币`` 缺失时用各分量列求和）。
    缺必需列默认 ``raise``（不再静默返回空表让 Phase3 少算）；``allow_empty=True`` 才允许空。
    返回 (df, 未匹配别名列表)；未匹配账号进 Phase3 warnings。
    """
    ws_name = additional_fee_worksheet_name_from_yyyymm(exchange_month)
    raw = _read_fee_worksheet(gc, ws_name, allow_empty=allow_empty)
    empty_cols = ["渠道账号", "附加费累加人民币"]
    if raw is None:
        return pd.DataFrame(columns=empty_cols), []
    amount_cols = [c for c in ADDITIONAL_FEE_COLS if c in raw.columns]
    if "渠道账号" not in raw.columns or not amount_cols:
        detail = []
        if "渠道账号" not in raw.columns:
            detail.append("渠道账号")
        if not amount_cols:
            detail.append("附加费金额列（附加费累加人民币或分量列）")
        if allow_empty:
            return pd.DataFrame(columns=empty_cols), []
        raise ValueError(
            f"附加费工作表 {ws_name} 缺必需列 {detail}；现有列={list(raw.columns)[:12]}"
        )

    raw = raw[["渠道账号"] + amount_cols].copy()
    for c in amount_cols:
        raw[c] = pd.to_numeric(
            raw[c].astype(str).str.replace(",", "", regex=False), errors="coerce"
        ).fillna(0)
    comp_cols = [c for c in amount_cols if c != "附加费累加人民币"]
    if "附加费累加人民币" not in raw.columns:
        raw["附加费累加人民币"] = raw[comp_cols].sum(axis=1) if comp_cols else 0.0
    sum_cols = ["附加费累加人民币", *comp_cols]

    resolve, known = _alias_resolver(df_explode)
    raw["渠道账号"] = raw["渠道账号"].astype(str).str.strip()
    raw = raw.loc[~raw["渠道账号"].isin(["", "nan", "None", "NaN"])]
    raw["渠道账号"] = raw["渠道账号"].map(resolve)
    unmatched = sorted({a for a in raw["渠道账号"] if known and a not in known})
    out = raw.groupby("渠道账号", as_index=False)[sum_cols].sum()
    return out, unmatched


def load_tax_grouped(
    gc,
    bucket: str,
    df_explode: pd.DataFrame | None = None,
    *,
    allow_empty: bool = False,
) -> tuple[pd.DataFrame, list[str]]:
    """读 Tax{YYYYMM} 并按别名归一化渠道账号后求和。

    与 Colab cell 31-32 一致：Tax 表的「渠道账号」可能是别名，先按（大写化后的）别名映射回
    规范渠道账号；映射不到的再用 ``channel_canonical`` 静态快照兜底。返回 (df, 未匹配别名列表)。
    缺 ``渠道账号`` / ``Tax amount人民币`` 列默认 ``raise``（不再静默变空表），
    只有 ``allow_empty=True`` 才允许。
    """
    ws_name = tax_worksheet_name(bucket)
    raw = _read_fee_worksheet(gc, ws_name, allow_empty=allow_empty)
    empty_cols = ["渠道账号", "Tax amount人民币"]
    if raw is None:
        return pd.DataFrame(columns=empty_cols), []
    missing = [c for c in empty_cols if c not in raw.columns]
    if missing:
        if allow_empty:
            return pd.DataFrame(columns=empty_cols), []
        raise ValueError(f"Tax 工作表 {ws_name} 缺必需列 {missing}；现有列={list(raw.columns)[:12]}")
    raw["Tax amount人民币"] = pd.to_numeric(
        raw["Tax amount人民币"].astype(str).str.replace(",", "", regex=False),
        errors="coerce",
    ).fillna(0)
    raw["渠道账号"] = raw["渠道账号"].astype(str).str.strip()
    raw = raw.loc[~raw["渠道账号"].isin(["", "nan", "None", "NaN"])]
    resolve, known = _alias_resolver(df_explode)
    raw["渠道账号"] = raw["渠道账号"].map(resolve)
    unmatched = sorted({a for a in raw["渠道账号"] if known and a not in known})
    return raw.groupby("渠道账号")["Tax amount人民币"].sum().reset_index(), unmatched


def merge_rmb_tax_additional(
    df_rmb: pd.DataFrame,
    *,
    df_sep: pd.DataFrame,
    df_tax: pd.DataFrame,
    df_account: pd.DataFrame,
    stats_out: dict | None = None,
) -> pd.DataFrame:
    """按渠道账号外连接人民币/附加费/Tax/账号表。

    连接前断言各表 ``渠道账号`` 唯一；外连接新增的账号（只存在于附加费/Tax/账号表）
    收集进 ``stats_out['outer_only_accounts']``，作为行数差异的明确清单。
    """
    stats = {"outer_only_accounts": []}

    def _assert_unique(df: pd.DataFrame, label: str) -> None:
        if "渠道账号" not in df.columns:
            raise ValueError(f"{label} 缺渠道账号列")
        dup = df.loc[df["渠道账号"].duplicated(keep=False), "渠道账号"]
        if not dup.empty:
            raise ValueError(f"{label} 渠道账号重复，无法唯一合并: {sorted(set(dup))[:5]!r}")

    base = df_rmb.drop(columns=["渠道", "运营人员"], errors="ignore")
    _assert_unique(base, "人民币按账号表")
    out = base
    for other, label in ((df_sep, "附加费"), (df_tax, "Tax")):
        if other is None or other.empty:
            continue
        _assert_unique(other, label)
        before = set(out["渠道账号"])
        out = out.merge(other, how="outer", on="渠道账号", validate="one_to_one")
        added = sorted(set(out["渠道账号"]) - before)
        stats["outer_only_accounts"].extend([f"{label}:{a}" for a in added])
    _assert_unique(df_account, "渠道账号表")
    before = set(out["渠道账号"])
    out = out.merge(
        df_account[["渠道", "渠道账号", "运营人员"]],
        how="outer",
        on="渠道账号",
        validate="one_to_one",
    )
    added = sorted(set(out["渠道账号"]) - before)
    stats["outer_only_accounts"].extend([f"账号表:{a}" for a in added])
    if out["渠道账号"].duplicated().any():
        raise ValueError("合并后渠道账号重复（外连接产生了重复账号）")
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
    if stats_out is not None:
        stats_out.update(stats)
    return out[cols]


def collection_rate_by_receipt(df_group: pd.DataFrame) -> pd.DataFrame:
    g = df_group.groupby("收款归属").agg({"应收金额_人民币": "sum", "销售额_人民币": "sum"})
    g["平均收款比例"] = g["应收金额_人民币"] / g["销售额_人民币"]
    g = g.replace([np.inf, -np.inf], np.nan)
    return g.reset_index()


def collection_rate_by_staff(df_group: pd.DataFrame) -> pd.DataFrame:
    """Colab cell 17：按运营人员汇总人民币列，比例列插在其源列右侧。

    列序（202608 实表）：运营人员, 销售额_人民币, 应收金额_人民币, 应收金额_比例,
    客户退货至平台运费_人民币, … 每个 ``_人民币`` 后面紧跟 ``_比例``；最后把
    销售额_人民币 挪到运营人员右侧。旧实现把比例列全追加到末尾，与 notebook 不一致。
    """
    rmb_cols = [f"{c}_人民币" for c in LS_COL_NEED_NUMERIC if f"{c}_人民币" in df_group.columns]
    g = df_group.groupby("运营人员")[rmb_cols].sum()
    if "销售额_人民币" in g.columns:
        for col in rmb_cols:
            if col == "销售额_人民币":
                continue
            new_name = col.replace("_人民币", "_比例")
            ratio = (g[col] / g["销售额_人民币"]).replace([np.inf, -np.inf], np.nan).fillna(1.0)
            g.insert(g.columns.get_loc(col) + 1, new_name, ratio)
    g = g.reset_index()
    if "销售额_人民币" in g.columns:
        sales_rmb = g.pop("销售额_人民币")
        g.insert(g.columns.get_loc("运营人员") + 1, "销售额_人民币", sales_rmb)
    return g


FBA_COL = "FBA费用_人民币"
FBA_ADD_RECEIVE = "加上FBA费用_应收金额_人民币"
FBA_MINUS_COMMISSION = "扣减FBA费用_佣金_人民币"
FBA_SUMMARY_SUFFIX = "FBA费用扣减后分类汇总"
FBA_STAFF_SUFFIX = "FBA费用扣减后收款比例运营人员"


def build_fba_summary(
    gc,
    *,
    bucket: str,
    bucket_dir: Path,
    df_exchange_rate: pd.DataFrame,
    repair_dir: Path | None = None,
) -> tuple[pd.DataFrame, dict]:
    """用本地 FBA 管道生成 ``{期}FBA费用扣减后分类汇总``（只算不写）。

    与 Colab 分类汇总同口径：结算 txt 中的 FBA 费用行 → 特例规则 → 扣减后按
    父文件夹/子文件夹/渠道账号/币种/汇率汇总。返回 (summary, 统计信息)。
    """
    from fba_adjust import FBA_DESCRIPTIONS, fba_summary_df12, load_fba_rules, process_fba_orders
    from read_amz_txt import read_bucket_amz_txts
    from tax_aggregate import enrich_with_fx

    info: dict = {"bucket_dir": str(bucket_dir), "read_stats": {}, "rule_rows": 0, "fba_rows": 0}
    df_raw, reports = read_bucket_amz_txts(bucket_dir, repair_dir=repair_dir, stats_out=info["read_stats"])
    info["read_reports"] = reports
    if df_raw.empty:
        return pd.DataFrame(), info
    df = enrich_with_fx(df_raw, df_exchange_rate)
    df_fba = df[df["amount-description"].isin(FBA_DESCRIPTIONS)].copy()
    info["fba_rows"] = int(len(df_fba))
    if df_fba.empty:
        return pd.DataFrame(), info
    rules = load_fba_rules(gc, bucket_name=bucket)
    rules_exec = rules.loc[rules["当月是否执行"] == "是"].copy()
    info["rule_rows"] = int(len(rules_exec))
    if rules_exec.empty:
        return pd.DataFrame(), info
    processed = process_fba_orders(rules_exec, df_fba)
    summary = fba_summary_df12(processed)
    info["summary_rows"] = int(len(summary))
    return summary, info


def build_fba_staff(
    df_group: pd.DataFrame,
    fba_summary: pd.DataFrame,
) -> pd.DataFrame:
    """Colab cell 45-47：``{期}FBA费用扣减后收款比例运营人员``（只算不写）。"""
    if df_group.empty:
        return pd.DataFrame()
    if fba_summary is None or fba_summary.empty:
        fb = pd.DataFrame({"渠道账号": [], "调整前-后amount人民币": []})
    else:
        df_fba = fba_summary.copy()
        for c in ("amount", "amount人民币", "调整前-后amount", "调整前-后amount人民币"):
            if c in df_fba.columns:
                df_fba[c] = pd.to_numeric(
                    df_fba[c].astype(str).str.replace(",", "", regex=False), errors="coerce"
                ).fillna(0)
        fb = df_fba.groupby("渠道账号")["调整前-后amount人民币"].sum().reset_index()

    merged = df_group.merge(fb, how="left", on="渠道账号")
    merged["调整前-后amount人民币"] = merged["调整前-后amount人民币"].fillna(0.0)
    merged = merged.rename(columns={"调整前-后amount人民币": FBA_COL})
    merged[FBA_COL] = merged[FBA_COL] * -1
    merged[FBA_ADD_RECEIVE] = merged["应收金额_人民币"] + merged[FBA_COL]
    merged[FBA_MINUS_COMMISSION] = merged["佣金_人民币"] - merged[FBA_COL]

    cols = [f"{c}_人民币" for c in LS_COL_NEED_NUMERIC if f"{c}_人民币" in merged.columns]
    cols += [FBA_COL, FBA_ADD_RECEIVE, FBA_MINUS_COMMISSION]
    g = merged.groupby("运营人员")[cols].sum()
    for col in cols:
        if col == "销售额_人民币":
            continue
        new_name = col.replace("_人民币", "_比例")
        ratio = (g[col] / g["销售额_人民币"]).replace([np.inf, -np.inf], np.nan).fillna(1.0)
        g.insert(g.columns.get_loc(col) + 1, new_name, ratio)

    g = g.reset_index()
    if "销售额_人民币" in g.columns:
        sales_rmb = g.pop("销售额_人民币")
        g.insert(g.columns.get_loc("运营人员") + 1, "销售额_人民币", sales_rmb)
    move = [
        FBA_COL,
        FBA_COL.replace("_人民币", "_比例"),
        FBA_ADD_RECEIVE,
        FBA_ADD_RECEIVE.replace("_人民币", "_比例"),
    ]
    move = [c for c in move if c in g.columns]
    anchor = "应收金额_比例"
    if anchor in g.columns and move:
        order = [c for c in g.columns if c not in move]
        pos = order.index(anchor) + 1
        order[pos:pos] = move
        g = g[order]
    return g


def apply_fba_to_group(
    df_group: pd.DataFrame,
    gc,
    period_range: str,
) -> tuple[pd.DataFrame, bool]:
    """把 ``{期}FBA费用扣减后分类汇总`` 按渠道账号挂到分组表。

    账号级 FBA 是**账号总量**；若同一 ``渠道账号`` 在分组表有多行（不同收款归属/币种），
    逐行各加一份会把 FBA 放大成本（N 行 × 账号差额）。这里默认断言
    ``Σ(组表 FBA费用_人民币) == -Σ(账号级 FBA)``，不平直接 raise —— 宁可暴露，
    也不静默把差额复制 N 份。
    """
    ws_name = f"{period_range}FBA费用扣减后分类汇总"
    df_fba = read_worksheet_df(gc, ws_name)
    if df_fba.empty or "渠道账号" not in df_fba.columns:
        return df_group, False
    for c in ("amount", "amount人民币", "调整前-后amount", "调整前-后amount人民币"):
        if c in df_fba.columns:
            df_fba[c] = pd.to_numeric(df_fba[c], errors="coerce").fillna(0)
    fb = df_fba.groupby("渠道账号").agg({"调整前-后amount人民币": "sum"}).reset_index()
    col_fba = "FBA费用_人民币"

    # 账号级差额只能挂一次：多行账号必须先被识别出来。
    multi = df_group.loc[df_group["渠道账号"].duplicated(keep=False), "渠道账号"].unique()
    hit = fb.loc[fb["渠道账号"].isin(multi) & fb["调整前-后amount人民币"].ne(0)]
    if not hit.empty:
        raise ValueError(
            "FBA 账号级差额无法唯一挂到分组表：以下渠道账号在分组表有多行且 FBA≠0，"
            "逐行相加会放大金额（需先确定按行分摊口径）: "
            f"{sorted(hit['渠道账号'].tolist())[:5]!r}"
        )

    merged = df_group.merge(fb, how="left", on="渠道账号", validate="many_to_one")
    merged["调整前-后amount人民币"] = merged["调整前-后amount人民币"].fillna(0.0)
    merged = merged.rename(columns={"调整前-后amount人民币": col_fba})
    merged[col_fba] = merged[col_fba] * -1

    account_total = float(
        -fb.loc[fb["渠道账号"].isin(set(df_group["渠道账号"])), "调整前-后amount人民币"].sum()
    )
    group_total = float(merged[col_fba].sum())
    if abs(account_total - group_total) > 0.01:
        raise ValueError(
            f"FBA 守恒失败：账号级合计={account_total:.2f} 组表合计={group_total:.2f}"
        )
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
    tax_unmatched_accounts: list[str] = field(default_factory=list)
    additional_fee_unmatched_accounts: list[str] = field(default_factory=list)
    outer_only_accounts: list[str] = field(default_factory=list)
    oa_sheet_failures: list[str] = field(default_factory=list)
    allow_empty_tax: bool = False
    fba_summary_rows: int | None = None
    fba_staff_rows: int | None = None
    fba_source: str = ""
    warnings: list[str] = field(default_factory=list)
    worksheets_written: list[str] = field(default_factory=list)


def run_phase3(
    *,
    gc,
    input_xlsx: Path,
    bucket: str,
    exchange_month: str,
    bucket_dir: Path | None = None,
    repair_dir: Path | None = None,
    write_gsheet: bool = False,
    write_gsheet_fba: bool = False,
    allow_empty_tax: bool = False,
) -> tuple[Phase3Report, dict[str, pd.DataFrame]]:
    period_range = period_range_from_bucket(bucket)
    yyyymm = exchange_month.strip()
    if yyyymm != accounting_yyyymm_from_bucket(bucket):
        raise ValueError(f"--exchange-month {yyyymm} 与桶 {bucket} 不一致")

    oa_failures: list[str] = []
    df_orig = load_oa_dataframe(input_xlsx, failures_out=oa_failures)
    df_orig, april_n = drop_april_resubmit_rows(df_orig, yyyymm)
    df_rate, df_rate_explode = load_exchange_rate_table(gc, month_col=yyyymm)
    df_account, df_explode = load_channel_accounts(gc, yyyymm)

    df, approval_filter = build_row_level_df(
        df_orig, df_exchange_rate=df_rate, df_explode=df_explode, df_rate_explode=df_rate_explode
    )
    unmatched = int(((df["渠道账号"].isna()) | (df["渠道账号"] == "")).sum())
    fx_missing = find_unmatched_currency(df)
    df_group = build_group_account_cost(
        df, approval_filter, df_rate_explode=df_rate_explode, df_account=df_account
    )
    df_rmb = build_rmb_by_account(df_group)
    df_sep, sep_unmatched = load_additional_fee_grouped(
        gc, yyyymm, df_explode, allow_empty=allow_empty_tax
    )
    df_tax, tax_unmatched = load_tax_grouped(
        gc, bucket, df_explode, allow_empty=allow_empty_tax
    )
    merge_stats: dict = {}
    df_merged = merge_rmb_tax_additional(
        df_rmb, df_sep=df_sep, df_tax=df_tax, df_account=df_account, stats_out=merge_stats
    )

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
        tax_unmatched_accounts=tax_unmatched,
        additional_fee_unmatched_accounts=sep_unmatched,
        outer_only_accounts=list(merge_stats.get("outer_only_accounts", [])),
        oa_sheet_failures=oa_failures,
        allow_empty_tax=allow_empty_tax,
    )
    for f in oa_failures:
        rep.warnings.append(f"OA sheet 读取失败: {f}")
    if unmatched:
        rep.warnings.append(f"渠道账号未匹配 {unmatched} 行（销售账户→别名表）")
    if tax_unmatched:
        rep.warnings.append(f"Tax 有 {len(tax_unmatched)} 个渠道账号未在别名表/快照中: {tax_unmatched[:5]}")
    if sep_unmatched:
        rep.warnings.append(
            f"附加费有 {len(sep_unmatched)} 个渠道账号未在别名表/快照中: {sep_unmatched[:5]}"
        )
    if rep.outer_only_accounts:
        print("[INFO] 外连接新增账号（仅附加费/Tax/账号表）:", rep.outer_only_accounts[:10], file=sys.stderr)
    if allow_empty_tax and df_tax.empty:
        rep.warnings.append("Tax 表为空（显式 --allow-empty-tax，人民币 Tax 将按 0 处理）")
    if allow_empty_tax and df_sep.empty:
        rep.warnings.append("附加费表为空（显式 --allow-empty-tax）")
    if not fx_missing.empty:
        labels = sorted({str(x) for x in fx_missing["货币中文名"].dropna().unique()})
        rep.warnings.append(
            f"币种未匹配汇率 {len(fx_missing)} 行（币种={labels}），这些行的人民币会是 0/空"
        )
        print("[WARN] 币种未匹配汇率，检查汇率表别名或不可见字符：", file=sys.stderr)
        print(fx_missing.to_string(index=False), file=sys.stderr)
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

    # Colab 39-47：FBA 分类汇总 + FBA 扣减后收款比例运营人员（本地生成，只算不写）
    fba_summary = pd.DataFrame()
    if bucket_dir is not None:
        try:
            fba_summary, fba_info = build_fba_summary(
                gc,
                bucket=bucket,
                bucket_dir=Path(bucket_dir),
                df_exchange_rate=df_rate,
                repair_dir=repair_dir,
            )
            frames["fba_summary"] = fba_summary
            frames["fba_staff"] = build_fba_staff(df_group, fba_summary)
            rep.fba_summary_rows = int(len(fba_summary))
            rep.fba_staff_rows = int(len(frames["fba_staff"]))
            rep.fba_source = "local-txt"
            bad = int(fba_info["read_stats"].get("files_failed", 0)) + int(
                fba_info["read_stats"].get("rows_mismatch", 0)
            )
            if bad:
                rep.warnings.append(f"FBA 源 txt 读取异常 {bad} 处（见 fba read_reports）")
        except Exception as e:  # 生成失败不能影响五张主表
            rep.warnings.append(f"FBA 表生成失败: {e}")
    else:
        # 不给桶目录时退回读现有分类汇总（Colab 手工复制的场景）
        existing = read_worksheet_df(gc, f"{period_range}{FBA_SUMMARY_SUFFIX}")
        frames["fba_summary"] = existing
        frames["fba_staff"] = build_fba_staff(df_group, existing)
        rep.fba_summary_rows = int(len(existing))
        rep.fba_staff_rows = int(len(frames["fba_staff"]))
        rep.fba_source = "existing-sheet" if not existing.empty else ""

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

    if write_gsheet_fba:
        if not phase3_spreadsheet_available(gc):
            raise PermissionError("Phase3 表不可读，无法写 FBA 工作表")
        if frames.get("fba_summary") is not None and not frames["fba_summary"].empty:
            ws_fba_summary = f"{period_range}{FBA_SUMMARY_SUFFIX}"
            write_worksheet_df(gc, frames["fba_summary"], worksheet=ws_fba_summary)
            rep.worksheets_written.append(ws_fba_summary)
        if frames.get("fba_staff") is not None and not frames["fba_staff"].empty:
            ws_fba_staff = f"{period_range}{FBA_STAFF_SUFFIX}"
            write_worksheet_df(gc, frames["fba_staff"], worksheet=ws_fba_staff)
            rep.worksheets_written.append(ws_fba_staff)
        from phase3_gsheet import sort_phase3_tabs

        sort_phase3_tabs(gc, pin_worksheet=period_range)

    return rep, frames
