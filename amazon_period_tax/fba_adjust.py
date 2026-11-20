# -*- coding: utf-8 -*-
"""FBA 费用特例：读 gsheet 规则 + Colab process_fba_orders。

门禁（gate_audit_20261120 F01/F02，整改计划 U-B B1）：

- 规则必须同时有 ``渠道账号`` + ``平台SKU``；空 SKU **不再**隐式变成「整账号」。
  账号级规则必须显式 ``规则范围=account`` 且经财务批准（``approve_account_scope=True``），
  账号仍然必填；空账号绝不按全账号匹配。
- 非空非法日期 / 起止倒置 FAIL；同账号同 SKU 的当期规则先查冲突再去重。
- 明细缺筛选列直接 FAIL（不再 ``continue`` 静默当通配）。
- 每条规则的命中行数/金额写进 ``processed.attrs['rule_hits']``，
  0 命中由上层要求财务审定（本模块只报数，不替业务判断）。
"""
from __future__ import annotations

import re
from datetime import datetime

import numpy as np
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

RULE_ACCOUNT_COL = "渠道账号"
RULE_SKU_COL = "平台SKU"
RULE_SCOPE_COL = "规则范围"
RULE_EXEC_COL = "当月是否执行"

SCOPE_SKU = "sku"
SCOPE_ACCOUNT = "account"
_SCOPE_ALIASES = {
    "sku": SCOPE_SKU,
    "单品": SCOPE_SKU,
    "sku级": SCOPE_SKU,
    "account": SCOPE_ACCOUNT,
    "账号": SCOPE_ACCOUNT,
    "账号级": SCOPE_ACCOUNT,
    "整账号": SCOPE_ACCOUNT,
}

_MONTH_RE = re.compile(r"^(\d{4})[-/.年](\d{1,2})(?:[-/.月](\d{1,2})日?)?$")
_WS_RE = re.compile(r"\s+")


class FbaRuleError(ValueError):
    """FBA 规则/明细不满足门禁。调用方必须转成写前错误，不得 catch 后继续写。"""


def _is_blank(value) -> bool:
    """None / NaN / 空白串 / 'nan' 都算空（GSheet 读回的空单元格是 '' 或 NaN）。"""
    if value is None:
        return True
    try:
        if pd.isna(value):
            return True
    except (TypeError, ValueError):
        pass
    return str(value).strip() in {"", "nan", "NaN", "NaT", "None"}


def _norm(value) -> str:
    """过滤匹配用的规范化：去空白，空值统一成空串（不能变成 'nan'）。"""
    return "" if _is_blank(value) else _WS_RE.sub("", str(value))


def parse_rule_month(raw, *, column: str = "执行时间") -> datetime | None:
    """空 → None（不限）；非空但非法 → :class:`FbaRuleError`（不许静默变「长期有效」）。"""
    if _is_blank(raw):
        return None
    text = str(raw).strip()
    match = _MONTH_RE.match(text)
    if not match:
        raise FbaRuleError(
            f"{column} 非空但不是合法年月: {text!r}（空=不限；请填 YYYY-MM 或 YYYY-MM-DD）"
        )
    year, month = int(match.group(1)), int(match.group(2))
    if not 1 <= month <= 12:
        raise FbaRuleError(f"{column} 月份非法: {text!r}")
    return datetime(year, month, 1)


def _scope_of(value) -> str:
    """规则范围 → 'sku' / 'account'；非法值原样返回（由校验拦下）。"""
    if _is_blank(value):
        return SCOPE_SKU
    return _SCOPE_ALIASES.get(str(value).strip().lower(), str(value).strip())


def _sku_col(df_rule: pd.DataFrame) -> str | None:
    """规则表的 SKU 列名：原表 ``平台SKU``，``process_fba_orders`` 内改名后是 ``sku``。"""
    if RULE_SKU_COL in df_rule.columns:
        return RULE_SKU_COL
    if "sku" in df_rule.columns:
        return "sku"
    return None


def validate_fba_rules(
    df_rule: pd.DataFrame,
    *,
    approve_account_scope: bool = False,
    allowed_overlaps: frozenset | set = frozenset(),
) -> list[str]:
    """规则结构校验（不修改输入）。返回问题清单，空表示通过。

    - 缺 ``渠道账号`` / ``平台SKU`` 列 → 问题。
    - 当期执行规则：空账号 FAIL；``scope=sku`` 且空 SKU FAIL；``scope=account``
      无财务批准 FAIL；非法 ``规则范围`` 值 FAIL。
    - 同账号同 SKU 的当期规则内容不同 → 冲突 FAIL（相同可安全去重）。
    - 同账号同时有账号级与 SKU 级规则 → 重叠 FAIL（除非在 ``allowed_overlaps`` 白名单）。
    - 任何行的日期非空但非法 / 起止倒置 → FAIL（空表示不限，合法）。
    """
    problems: list[str] = []
    if df_rule is None or len(df_rule) == 0:
        return problems
    sku_col = _sku_col(df_rule)
    missing = [c for c in (RULE_ACCOUNT_COL,) if c not in df_rule.columns]
    if sku_col is None:
        missing.append(f"{RULE_SKU_COL}/sku")
    if missing:
        return [f"FBA 规则缺列 {missing}（必须能按 渠道账号+平台SKU 限定范围）"]

    # 日期：全表校验。非法日期会把规则悄悄变成"长期有效"，不能只在当期行查。
    if "执行开始时间" in df_rule.columns or "执行结束时间" in df_rule.columns:
        for _, row in df_rule.iterrows():
            start = parse_rule_month(row.get("执行开始时间"), column="执行开始时间")
            end = parse_rule_month(row.get("执行结束时间"), column="执行结束时间")
            if start is not None and end is not None and start > end:
                problems.append(
                    f"FBA 规则 {RULE_ACCOUNT_COL}={row.get(RULE_ACCOUNT_COL)!r} "
                    f"执行开始时间 {start:%Y-%m} 晚于 执行结束时间 {end:%Y-%m}"
                )

    executed = (
        df_rule[RULE_EXEC_COL].astype(str).eq("是")
        if RULE_EXEC_COL in df_rule.columns
        else pd.Series(True, index=df_rule.index)
    )
    work = df_rule.loc[executed]
    if work.empty:
        return problems

    blank_account = [idx for idx, v in work[RULE_ACCOUNT_COL].items() if _is_blank(v)]
    if blank_account:
        problems.append(
            f"FBA 规则有 {len(blank_account)} 条当期规则 {RULE_ACCOUNT_COL} 为空"
            "（空账号不得按全账号匹配）"
        )

    key_rows: dict[tuple[str, str], list] = {}
    for idx, row in work.iterrows():
        scope = _scope_of(row.get(RULE_SCOPE_COL))
        sku = _norm(row.get(sku_col))
        account = "" if _is_blank(row.get(RULE_ACCOUNT_COL)) else str(row.get(RULE_ACCOUNT_COL)).strip()
        if scope not in (SCOPE_SKU, SCOPE_ACCOUNT):
            problems.append(f"FBA 规则 规则范围={row.get(RULE_SCOPE_COL)!r} 非法（只允许 sku / account）")
            continue
        if scope == SCOPE_SKU and not sku:
            problems.append(
                f"FBA 规则 {account or '<空账号>'} 的当期规则 SKU 为空："
                "空 SKU 不得隐式按账号匹配；如需账号级请显式 规则范围=account 并经财务批准"
            )
        if scope == SCOPE_ACCOUNT:
            if sku:
                problems.append(
                    f"FBA 规则 {account} 声明 规则范围=account 却填了 SKU={sku!r}"
                    "（账号级规则不能带 SKU，请改成 sku 规则）"
                )
            if not approve_account_scope:
                problems.append(
                    f"FBA 规则 {account} 为账号级规则但未获财务批准"
                    "（需 approve_account_scope=True 且范围已确认）"
                )
        if account:
            key_rows.setdefault((account, sku), []).append(idx)

    # 先查冲突，再去重：内容不同的同键规则不能 keep-first 静默吞掉。
    for (account, sku), idxs in key_rows.items():
        if len(idxs) < 2:
            continue
        rows = df_rule.loc[idxs].fillna("").astype(str).drop_duplicates()
        if len(rows) > 1:
            problems.append(
                f"FBA 规则冲突：账号={account!r} SKU={sku or '<账号级>'!r} 有 {len(idxs)} 条"
                "当期规则内容不同（先查后去重，禁止 keep-first）"
            )

    account_scope = {account for account, sku in key_rows if not sku}
    for account, sku in sorted(key_rows):
        if not sku or account not in account_scope:
            continue
        if (account, sku) not in allowed_overlaps:
            problems.append(
                f"FBA 规则重叠：账号 {account!r} 同时有账号级规则和 SKU={sku!r} 规则"
                "（未在批准白名单内，重复扣减口径不明）"
            )
    return problems


def load_fba_rules(
    gc,
    *,
    bucket_name: str,
    sheet: str = "和财务部共享",
    ws: str = "账期FBA费用特例",
    approve_account_scope: bool = False,
) -> pd.DataFrame:
    """读规则表并算 ``当月是否执行``；非法日期/冲突规则直接抛 :class:`FbaRuleError`。"""
    from amazon_period_tax.exchange_rate import CFO_SPREADSHEET_ID

    sh = gc.open_by_key(CFO_SPREADSHEET_ID)
    ws_obj = sh.worksheet(ws)
    rows = ws_obj.get_all_values()
    if not rows:
        return pd.DataFrame()
    df = pd.DataFrame(rows[1:], columns=rows[0]).replace("", pd.NA)
    ym = datetime.strptime(bucket_name[2:8], "%Y%m")
    df[RULE_EXEC_COL] = "否"

    for index, row in df.iterrows():
        start_ym = parse_rule_month(row.get("执行开始时间"), column="执行开始时间")
        end_ym = parse_rule_month(row.get("执行结束时间"), column="执行结束时间")
        if start_ym is None and end_ym is None:
            df.at[index, RULE_EXEC_COL] = "是"
        elif start_ym is None:
            if ym <= end_ym:
                df.at[index, RULE_EXEC_COL] = "是"
        elif end_ym is None:
            if ym >= start_ym:
                df.at[index, RULE_EXEC_COL] = "是"
        elif start_ym <= ym <= end_ym:
            df.at[index, RULE_EXEC_COL] = "是"
    if RULE_SKU_COL in df.columns:
        # 空 SKU 必须保持"空"，不能 astype(str) 变成 'nan' 冒充真实 SKU。
        df[RULE_SKU_COL] = df[RULE_SKU_COL].map(_norm)
    problems = validate_fba_rules(df, approve_account_scope=approve_account_scope)
    if problems:
        raise FbaRuleError("FBA 规则校验失败: " + "; ".join(problems))
    before = len(df)
    df = df.drop_duplicates(subset=[RULE_ACCOUNT_COL, RULE_SKU_COL, RULE_EXEC_COL], keep="first")
    df.attrs["deduped"] = before - len(df)
    return df


def _match_mask(df_fba: pd.DataFrame, rule: pd.Series, filter_columns: list[str]) -> pd.Series:
    """单条规则命中的明细行：非空列等值匹配；空列=该列不限（账号级规则只有 SKU 为空）。"""
    mask = pd.Series(True, index=df_fba.index)
    for column in filter_columns:
        rule_value = _norm(rule.get(column))
        if not rule_value:
            continue
        mask &= df_fba[column].map(_norm) == rule_value
    return mask


def filter_fba_order(df_rule: pd.DataFrame, df_fba: pd.DataFrame, filter_columns: list[str]) -> pd.DataFrame:
    """规则行命中明细行：规则里的列值在明细里等值匹配。

    ``df_rule`` 必须已被 ``process_fba_orders`` 改名（``平台SKU`` → ``sku``）。
    **缺筛选列直接 FAIL**；空账号 FAIL；空 SKU 只表示"该账号全部 SKU"
    （账号级规则已在校验阶段要求财务批准）。
    """
    if df_fba is None or df_fba.empty:
        return df_fba.copy() if df_fba is not None else pd.DataFrame()
    missing_detail = [c for c in filter_columns if c not in df_fba.columns]
    if missing_detail:
        raise FbaRuleError(f"FBA 明细缺筛选列 {missing_detail}（不能把缺列当通配）")
    if df_rule is None or df_rule.empty:
        return df_fba.iloc[0:0].copy()
    missing_rule = [c for c in filter_columns if c not in df_rule.columns]
    if missing_rule:
        raise FbaRuleError(f"FBA 规则缺筛选列 {missing_rule}")

    matched = pd.Series([False] * len(df_fba), index=df_fba.index)
    for _, rule in df_rule.iterrows():
        if _is_blank(rule.get(RULE_ACCOUNT_COL)):
            raise FbaRuleError("FBA 规则 渠道账号 为空：不得按全账号匹配")
        matched |= _match_mask(df_fba, rule, filter_columns)
    return df_fba.loc[matched].copy()


def rule_hits_frame(
    df_rule: pd.DataFrame,
    df_fba: pd.DataFrame,
    filter_columns: list[str],
) -> pd.DataFrame:
    """每条规则的命中行数与金额（0 命中须财务审定，见 F02）。"""
    columns = ["rule_row", RULE_ACCOUNT_COL, "sku", "hit_rows", "hit_amount"]
    if df_rule is None or df_rule.empty or df_fba is None or df_fba.empty:
        return pd.DataFrame(columns=columns)
    missing_detail = [c for c in filter_columns if c not in df_fba.columns]
    if missing_detail:
        raise FbaRuleError(f"FBA 明细缺筛选列 {missing_detail}（无法统计命中）")
    amounts = pd.to_numeric(df_fba["amount"], errors="coerce") if "amount" in df_fba.columns else None
    out: list[dict] = []
    for pos, (_, rule) in enumerate(df_rule.iterrows()):
        mask = _match_mask(df_fba, rule, filter_columns)
        hit_amount = float(amounts.loc[mask].fillna(0).sum()) if amounts is not None else 0.0
        out.append(
            {
                "rule_row": pos,
                RULE_ACCOUNT_COL: rule.get(RULE_ACCOUNT_COL),
                "sku": rule.get("sku", rule.get(RULE_SKU_COL)),
                "hit_rows": int(mask.sum()),
                "hit_amount": hit_amount,
            }
        )
    return pd.DataFrame(out, columns=columns)


def adj_fba_orders_cost(df_fba_orig: pd.DataFrame, filtered: pd.DataFrame) -> pd.DataFrame:
    """按命中行把 FBA 费用清零，再按账号用 FBAPerUnitFulfillmentFee 比例调仓储费。

    金额/汇率非数值或缺少一律 :class:`FbaRuleError`（不得按 0 继续，F04）。
    """
    if df_fba_orig is None or df_fba_orig.empty:
        return df_fba_orig.copy() if df_fba_orig is not None else pd.DataFrame()
    df = df_fba_orig.copy()
    amount = pd.to_numeric(df["amount"], errors="coerce")
    bad_amount = amount.isna() | ~np.isfinite(amount)
    if bad_amount.any():
        raise FbaRuleError(f"FBA 明细 amount 有 {int(bad_amount.sum())} 行空/非数值/非有限")
    rate = pd.to_numeric(df["汇率"], errors="coerce")
    bad_rate = rate.isna() | ~np.isfinite(rate)
    if bad_rate.any():
        raise FbaRuleError(f"FBA 明细 汇率 有 {int(bad_rate.sum())} 行缺失/非数值（缺 FX 不得继续）")
    df["amount"] = amount
    df["汇率"] = rate
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
        rate_value = mod / orig if orig else 1.0
        group.loc[cond2, COL_FBA_RATE] = rate_value
        group.loc[cond2, "amount"] = group.loc[cond2, "amount"] * rate_value
        parts.append(group)
    result = pd.concat(parts, axis=0)
    result[COL_AMOUNT_CHANGE] = result["调整前amount"] - result["amount"]
    result[COL_AMOUNT_CHANGE_RMB] = result[COL_AMOUNT_CHANGE] * result["汇率"]
    result[COL_AMOUNT_RMB] = result["amount"] * result["汇率"]
    return result


def process_fba_orders(
    df_rule_exec: pd.DataFrame,
    df_fba_orig: pd.DataFrame,
    *,
    approve_account_scope: bool = False,
    allowed_overlaps: frozenset | set = frozenset(),
) -> pd.DataFrame:
    """规则 + 明细 → 调整后明细；命中统计放在 ``attrs['rule_hits']``。"""
    problems = validate_fba_rules(
        df_rule_exec, approve_account_scope=approve_account_scope, allowed_overlaps=allowed_overlaps
    )
    if problems:
        raise FbaRuleError("FBA 规则校验失败: " + "; ".join(problems))
    rules = df_rule_exec.copy() if df_rule_exec is not None else pd.DataFrame()
    if RULE_SKU_COL in rules.columns:
        rules = rules.rename(columns={RULE_SKU_COL: "sku"})
    filtered = filter_fba_order(rules, df_fba_orig, [RULE_ACCOUNT_COL, "sku"])
    result = adj_fba_orders_cost(df_fba_orig, filtered)
    result.attrs["rule_hits"] = rule_hits_frame(rules, df_fba_orig, [RULE_ACCOUNT_COL, "sku"])
    return result


def fba_summary_df12(processed: pd.DataFrame) -> pd.DataFrame:
    return (
        processed.groupby(["父文件夹名", "子文件夹名", "渠道账号", "currency", "汇率"], dropna=False)[
            ["amount", COL_AMOUNT_RMB, COL_AMOUNT_CHANGE, COL_AMOUNT_CHANGE_RMB]
        ]
        .sum()
        .reset_index()
    )


__all__ = [
    "FBA_DESCRIPTIONS",
    "FbaRuleError",
    "RULE_ACCOUNT_COL",
    "RULE_SCOPE_COL",
    "RULE_SKU_COL",
    "SCOPE_ACCOUNT",
    "SCOPE_SKU",
    "adj_fba_orders_cost",
    "fba_summary_df12",
    "filter_fba_order",
    "load_fba_rules",
    "parse_rule_month",
    "process_fba_orders",
    "rule_hits_frame",
    "validate_fba_rules",
]
