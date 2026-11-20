# -*- coding: utf-8 -*-
"""账期管道硬关卡：Tax / Phase3 对账检查（只读，不写任何表）。

用法见 ``scripts/verify_period.py``。所有检查返回 ``Check``；任一项 FAIL → 脚本非 0 退出。
"""
from __future__ import annotations

import math
import re
from dataclasses import dataclass
from pathlib import Path

import pandas as pd

from bucket_meta import bucket_yyyymm, resolve_exchange_month
from gsheet_tax import (
    additional_fee_worksheet_name_from_yyyymm,
    open_additional_fee_tax_spreadsheet,
    tax_worksheet_name,
)
from phase3_constants import ADDITIONAL_FEE_COLS, LS_COL_COST
from phase3_merge import FBA_DELTA_RMB, FBA_STAFF_SUFFIX, FBA_SUMMARY_SUFFIX

TOL = 0.01
MONEY_COLS = ["应收金额", "销售额", *LS_COL_COST]

# 每张表必须具备的核心列（缺列直接 FAIL，不能靠 sum 空列=0 蒙混）。
REQUIRED_COLUMNS = {
    "原始": ["账期日期", "审批状态", "审批结果", "渠道账号", "汇率", "应收金额", "销售额"],
    "人民币": ["渠道账号", "应收金额_人民币", "销售额_人民币", "Tax amount人民币", "附加费累加人民币"],
    "主表(分组)": ["渠道账号", "应收金额_人民币", "销售额_人民币"],
    "收款比例收款归属": ["收款归属", "应收金额_人民币", "销售额_人民币", "平均收款比例"],
    "收款比例运营人员": ["运营人员", "销售额_人民币", "应收金额_人民币"],
}


@dataclass
class Check:
    name: str
    ok: bool
    detail: str = ""

    def line(self) -> str:
        return f"[{'PASS' if self.ok else 'FAIL'}] {self.name}: {self.detail}"


def parse_number(value) -> float | None:
    """GSheet 单元格 → float。兼容千分位、百分号、空串、括号负数。"""
    if value is None:
        return None
    s = str(value).strip().replace(",", "").replace(" ", "")
    if s in {"", "-", "nan", "None"}:
        return None
    pct = s.endswith("%")
    if pct:
        s = s[:-1]
    neg = s.startswith("(") and s.endswith(")")
    if neg:
        s = s[1:-1]
    try:
        v = float(s)
    except ValueError:
        return None
    if pct:
        v /= 100.0
    return -v if neg else v


def _num_series(df: pd.DataFrame, col: str) -> pd.Series:
    if col not in df.columns:
        return pd.Series(dtype=float)
    return df[col].map(parse_number).astype(float)


def cell_blank(value) -> bool:
    """GSheet 单元格是否为空（哨兵含空串/nan/None/连字符）。"""
    if value is None:
        return True
    try:
        if pd.isna(value):
            return True
    except (TypeError, ValueError):
        pass
    return str(value).strip() in {"", "-", "nan", "None", "N/A", "NA"}


def is_finite(value) -> bool:
    try:
        return math.isfinite(float(value))
    except (TypeError, ValueError):
        return False


def finite_close(a, b, tol: float = TOL) -> bool:
    """两侧都必须是有限数才可能 PASS；NaN/Inf 一律 False，不能当作「差为 0」。"""
    return is_finite(a) and is_finite(b) and abs(float(a) - float(b)) <= tol


def numeric_cell_errors(df: pd.DataFrame, cols, *, table: str, limit: int = 6) -> list[str]:
    """非空单元格必须能解析成**有限**数；空单元格允许（费用列本就允许空）。"""
    problems: list[str] = []
    for col in cols:
        if col not in df.columns:
            continue
        series = df[col]
        for pos, raw in series.items():
            if cell_blank(raw):
                continue
            val = parse_number(raw)
            if val is None:
                problems.append(f"{table}.{col}[行{pos}] 非空非法值 {raw!r}")
            elif not is_finite(val):
                problems.append(f"{table}.{col}[行{pos}] 非有限值 {raw!r}（NaN/Inf 不能当通过）")
            if len(problems) >= limit:
                return problems
    return problems


def rmb_columns(df: pd.DataFrame) -> list[str]:
    return [c for c in df.columns if str(c).endswith("_人民币")]


def missing_columns(df: pd.DataFrame, required) -> list[str]:
    return [c for c in required if c not in df.columns]


def period_sheet_names(bucket: str) -> dict[str, str]:
    """``账期20260804-20260903`` → 五张主表 worksheet 名。"""
    period = period_range_from_bucket(bucket_name(bucket))
    return {
        "主表(分组)": period,
        "原始": f"{period}原始",
        "人民币": f"人民币{period}",
        "收款比例收款归属": f"{period}收款比例收款归属",
        "收款比例运营人员": f"{period}收款比例运营人员",
    }


_MONTH_PATTERNS = (
    re.compile(r"^\s*(\d{4})[-/.](\d{1,2})"),
    re.compile(r"^\s*(\d{4})(\d{2})(\d{2})"),
)


def month_of(value) -> str | None:
    """账期日期单元格（2026-07-04 / 2026/7/4 / 20260704）→ ``YYYY-MM``。"""
    if value is None:
        return None
    try:
        if pd.isna(value):
            return None
    except (TypeError, ValueError):
        pass
    s = str(value).strip()
    if not s or s.lower() in {"nan", "none", "nat"}:
        return None
    for pat in _MONTH_PATTERNS:
        m = pat.match(s)
        if m:
            year, month = int(m.group(1)), int(m.group(2))
            if 1 <= month <= 12:
                return f"{year:04d}-{month:02d}"
    return None


def approval_in_progress_summary(
    df: pd.DataFrame,
    *,
    date_col: str = "账期日期",
    status_col: str = "审批状态",
    result_col: str = "审批结果",
) -> pd.DataFrame:
    """按月统计「审批中」行数/应收/销售及其占本表比例（只报告，不判 FAIL）。"""
    cols = ["月份", "行数", "应收金额", "销售额", "行数占比", "应收占比", "销售占比"]
    if df.empty or status_col not in df.columns:
        return pd.DataFrame(columns=cols)
    status = df[status_col].astype(str).str.strip()
    result = (
        df[result_col].astype(str).str.strip()
        if result_col in df.columns
        else pd.Series("", index=df.index)
    )
    pending = (status == "审批中") & (result != "拒绝")
    months = df[date_col].map(month_of) if date_col in df.columns else pd.Series(index=df.index, dtype=object)
    months = months.fillna("未知")

    recv = _num_series(df, "应收金额")
    sales = _num_series(df, "销售额")
    total_rows = len(df)
    total_recv = float(recv.sum())
    total_sales = float(sales.sum())
    rows = []
    for month in sorted(months.unique()):
        idx = months == month
        p = pending & idx
        n = int(p.sum())
        r = float(recv[p].sum())
        s = float(sales[p].sum())
        rows.append(
            {
                "月份": month,
                "行数": n,
                "应收金额": r,
                "销售额": s,
                "行数占比": (n / total_rows) if total_rows else 0.0,
                "应收占比": (r / total_recv) if total_recv else 0.0,
                "销售占比": (s / total_sales) if total_sales else 0.0,
            }
        )
    return pd.DataFrame(rows, columns=cols)


def format_approval_summary(summary: pd.DataFrame) -> str:
    if summary.empty:
        return "无审批中行"
    return "; ".join(
        f"{r['月份']}: 行{r['行数']}({r['行数占比']:.1%}) "
        f"应收{r['应收金额']:.2f}({r['应收占比']:.1%}) 销售{r['销售额']:.2f}({r['销售占比']:.1%})"
        for _, r in summary.iterrows()
    )


def period_range_from_bucket(bucket: str) -> str:
    m = re.search(r"\d{8}-\d{8}", bucket)
    if not m:
        raise ValueError(f"桶名无日期区间: {bucket!r}")
    return m.group(0)


def read_sheet_df(gc, spreadsheet, name: str) -> pd.DataFrame:
    import gspread

    try:
        ws = spreadsheet.worksheet(name)
    except gspread.exceptions.WorksheetNotFound:
        return pd.DataFrame()
    rows = ws.get_all_values()
    if not rows:
        return pd.DataFrame()
    return pd.DataFrame(rows[1:], columns=rows[0])


def check_tax(
    gc,
    *,
    bucket: str,
    bucket_dir: Path,
    exchange_month: str,
    repair_dir: Path | None = None,
) -> list[Check]:
    """Tax：合计 == 本地重算；账号集合一致；输出行数 == 账号数；读文件无 FAIL。"""
    from exchange_rate import load_exchange_rate_table
    from read_amz_txt import read_bucket_amz_txts
    from tax_aggregate import enrich_with_fx, tax_summary_df6, tax_summary_for_gsheet

    checks: list[Check] = []
    yyyymm = str(exchange_month).strip()
    stats: dict = {}
    df_raw, _reports = read_bucket_amz_txts(
        bucket_dir, repair_dir=repair_dir, stats_out=stats, write_repairs=False
    )
    checks.append(
        Check(
            "Tax: 源文件读取失败=0",
            int(stats.get("files_failed", 0)) == 0 and int(stats.get("rows_mismatch", 0)) == 0,
            f"files={stats.get('files_total')} used={stats.get('files_used')} "
            f"failed={stats.get('files_failed')} rows_mismatch={stats.get('rows_mismatch')}",
        )
    )
    checks.append(
        Check(
            "Tax: 无待人工复核文件",
            int(stats.get("files_needs_review", 0)) == 0,
            f"NEEDS-REVIEW={stats.get('files_needs_review', 0)}"
            "（疑似误名/同结算多版本/同内容不同账号，必须人工裁定）",
        )
    )
    checks.append(
        Check(
            "Tax: 同内容文件去重",
            True,
            f"SKIP-DUP={stats.get('files_dup', 0)}（已排除，不计入合计；>0 说明桶里有重复上传）",
        )
    )
    out_n = int(stats.get("files_out_of_period", 0))
    checks.append(
        Check(
            "Tax: 桶内无跨期 txt",
            out_n == 0,
            f"OUT-OF-PERIOD={out_n}（窗口外副本默认已排除，>0 说明有错放文件）",
        )
    )
    nodate = int(stats.get("files_no_period_date", 0))
    if nodate:
        checks.append(
            Check("Tax: 结算日可校验（报告）", True, f"NO-PERIOD-DATE={nodate} 份 txt 无内部结束日")
        )
    if df_raw.empty:
        checks.append(Check("Tax: 有数据", False, "桶内没有可用 AMZ txt"))
        return checks

    df_fx, _ = load_exchange_rate_table(gc, month_col=yyyymm)
    df1 = enrich_with_fx(df_raw, df_fx)
    missing = df1[df1["汇率"].isna()]["currency"].dropna().unique()
    checks.append(Check("Tax: 币种全部匹配汇率", len(missing) == 0, f"未匹配={list(missing)[:10]}"))

    detail = tax_summary_df6(df1)
    expected = tax_summary_for_gsheet(detail, all_accounts=df1["渠道账号"].dropna().unique())
    sheet = read_sheet_df(gc, open_additional_fee_tax_spreadsheet(gc), tax_worksheet_name(bucket_name(bucket)))
    if sheet.empty:
        checks.append(Check("Tax: 工作表存在", False, f"未找到 {tax_worksheet_name(bucket_name(bucket))}"))
        return checks

    miss_cols = missing_columns(sheet, ["渠道账号", "Tax amount人民币"])
    checks.append(Check("Tax: 源表列齐全", not miss_cols, f"缺列={miss_cols}"))
    invalid = numeric_cell_errors(sheet, ["Tax amount人民币"], table="Tax")
    checks.append(Check("Tax: 无非空非法/非有限金额", not invalid, "; ".join(invalid[:6]) or "全部有限"))

    sheet_total = _num_series(sheet, "Tax amount人民币").sum()
    expected_total = float(expected["Tax amount人民币"].sum())
    diff = abs(sheet_total - expected_total)
    checks.append(
        Check(
            "Tax: Σ(Tax amount人民币) == 本地重算",
            finite_close(sheet_total, expected_total),
            f"sheet={sheet_total:.2f} expected={expected_total:.2f} diff={diff:.4f}",
        )
    )

    sheet_accounts = {str(a).strip() for a in sheet.get("渠道账号", []) if str(a).strip()}
    expected_accounts = {str(a).strip() for a in expected["渠道账号"]}
    checks.append(
        Check(
            "Tax: 账号集合一致",
            sheet_accounts == expected_accounts,
            f"仅表内={sorted(sheet_accounts - expected_accounts)[:5]} "
            f"仅重算={sorted(expected_accounts - sheet_accounts)[:5]}",
        )
    )
    checks.append(
        Check(
            "Tax: 输出行数 == 账号数",
            len(sheet) == len(sheet_accounts),
            f"rows={len(sheet)} accounts={len(sheet_accounts)}",
        )
    )

    # 每账号金额级核对（容差 0.01）
    exp_map = {
        str(r["渠道账号"]).strip(): float(r["Tax amount人民币"]) for _, r in expected.iterrows()
    }
    sheet_map = {
        str(a).strip(): v
        for a, v in zip(sheet.get("渠道账号", []), _num_series(sheet, "Tax amount人民币"))
    }
    bad = [
        f"{acct}: sheet={sheet_map.get(acct)} exp={exp_map.get(acct)}"
        for acct in sorted(set(exp_map) | set(sheet_map))
        if not finite_close(sheet_map.get(acct), exp_map.get(acct))
    ]
    checks.append(Check("Tax: 每账号金额一致", not bad, "; ".join(bad[:8]) or "全部一致"))
    return checks


def bucket_name(bucket: str) -> str:
    """归一成 账期YYYYMMDD-YYYYMMDD（允许只传日期区间）。"""
    return bucket if bucket.startswith("账期") else f"账期{bucket}"


def check_phase3(gc, *, bucket: str, require_fba: bool = False) -> list[Check]:
    """Phase3：五张主表 + Tax/附加费源表 + 声明适用的 FBA 两表全覆盖。"""
    from phase3_gsheet import open_phase3_spreadsheet

    checks: list[Check] = []
    bname = bucket_name(bucket)
    period = period_range_from_bucket(bname)
    yyyymm = bucket_yyyymm(bname) or period[:6]
    names = period_sheet_names(bucket)
    sh = open_phase3_spreadsheet(gc)
    add_sh = open_additional_fee_tax_spreadsheet(gc)

    frames: dict[str, pd.DataFrame] = {}
    missing_sheets: list[str] = []
    for label, ws_name in names.items():
        df = read_sheet_df(gc, sh, ws_name)
        frames[label] = df
        if df.empty:
            missing_sheets.append(f"{label}({ws_name})")
    tax = read_sheet_df(gc, add_sh, f"Tax{yyyymm}")
    sep = read_sheet_df(gc, add_sh, additional_fee_worksheet_name_from_yyyymm(yyyymm))
    if tax.empty:
        missing_sheets.append(f"Tax{yyyymm}")
    if sep.empty:
        missing_sheets.append(f"附加费{yyyymm}")
    checks.append(
        Check("Phase3: 五张主表(含两张比例) + Tax/附加费源表存在", not missing_sheets, f"缺失={missing_sheets}")
    )
    if missing_sheets:
        return checks

    orig, rmb, group = frames["原始"], frames["人民币"], frames["主表(分组)"]
    rate_receipt, rate_staff = frames["收款比例收款归属"], frames["收款比例运营人员"]

    # 0) 缺列：不能靠「列不存在 → sum 空 = 0」蒙混通过。
    missing_cols: list[str] = []
    for label, required in REQUIRED_COLUMNS.items():
        miss = missing_columns(frames[label], required)
        if miss:
            missing_cols.append(f"{label}:{miss}")
    miss_tax = missing_columns(tax, ["渠道账号", "Tax amount人民币"])
    if miss_tax:
        missing_cols.append(f"Tax:{miss_tax}")
    sep_miss: list[str] = []
    if "渠道账号" not in sep.columns:
        sep_miss.append("渠道账号")
    if not (set(ADDITIONAL_FEE_COLS) & set(sep.columns)):
        sep_miss.append("附加费金额列")
    if sep_miss:
        missing_cols.append(f"附加费:{sep_miss}")
    checks.append(Check("Phase3: 表列齐全", not missing_cols, "; ".join(missing_cols) or "全部齐"))
    if missing_cols:
        return checks  # 列都不齐，后面的按列计算没有意义

    # 1) 非空非法/非有限：NaN/Inf 单独 FAIL，不能当「差=0」。
    table_frames = {**frames, "Tax": tax, "附加费": sep}
    scan = {
        "原始": [c for c in [*MONEY_COLS, "汇率", *rmb_columns(orig)] if c in orig.columns],
        "人民币": [
            c
            for c in [*rmb_columns(rmb), "Tax amount人民币", "附加费累加人民币", *ADDITIONAL_FEE_COLS]
            if c in rmb.columns
        ],
        "主表(分组)": [c for c in [*rmb_columns(group), "收款费用累加人民币"] if c in group.columns],
        "收款比例收款归属": [
            c for c in ["应收金额_人民币", "销售额_人民币", "平均收款比例"] if c in rate_receipt.columns
        ],
        "收款比例运营人员": rmb_columns(rate_staff),
        "Tax": ["Tax amount人民币"],
        "附加费": [c for c in ADDITIONAL_FEE_COLS if c in sep.columns],
    }
    invalid_problems: list[str] = []
    for label, cols in scan.items():
        invalid_problems.extend(numeric_cell_errors(table_frames[label], cols, table=label))
    checks.append(
        Check("Phase3: 非空非法/非有限金额", not invalid_problems, "; ".join(invalid_problems[:6]) or "全部有限")
    )

    # 2) 审批中占比（只报告，不阻断）。
    approval_summary = approval_in_progress_summary(orig)
    checks.append(Check("Phase3: 审批中占比（只报告）", True, format_approval_summary(approval_summary)))

    # 3) 人民币.Tax == Tax{YYYYMM} 合计（NaN 不能当通过）
    rmb_tax = _num_series(rmb, "Tax amount人民币").sum()
    tax_total = _num_series(tax, "Tax amount人民币").sum()
    checks.append(
        Check(
            "Phase3: Σ(人民币.Tax) == Σ(Tax{YYYYMM})",
            finite_close(rmb_tax, tax_total),
            f"rmb={rmb_tax:.2f} tax_ws={tax_total:.2f} diff={abs(rmb_tax - tax_total):.4f}",
        )
    )

    # 4) 人民币.附加费 == 附加费{YYYYMM}
    rmb_sep = _num_series(rmb, "附加费累加人民币").sum()
    sep_total = _num_series(sep, "附加费累加人民币").sum() if "附加费累加人民币" in sep.columns else 0.0
    checks.append(
        Check(
            "Phase3: Σ(人民币.附加费) == Σ(附加费{YYYYMM})",
            finite_close(rmb_sep, sep_total),
            f"rmb={rmb_sep:.2f} sep_ws={sep_total:.2f} diff={abs(rmb_sep - sep_total):.4f}",
        )
    )

    # 5) 原始：外币>0 且 汇率空 == 0
    fx = _num_series(orig, "汇率")
    foreign = sum(
        (_num_series(orig, c).abs() for c in MONEY_COLS if c in orig.columns),
        pd.Series(0.0, index=orig.index),
    )
    bad_fx = int(((fx.isna() | (fx == 0)) & (foreign > 0)).sum())
    checks.append(Check("Phase3: 原始 外币>0 且汇率空 == 0", bad_fx == 0, f"rows={bad_fx}"))

    # 6) 原始：渠道账号未匹配 == 0
    acct = orig.get("渠道账号", pd.Series(dtype=object)).astype(str).str.strip()
    blank_acct = int(((acct == "") | (acct == "nan")).sum())
    checks.append(Check("Phase3: 渠道账号未匹配 == 0", blank_acct == 0, f"rows={blank_acct}"))

    # 7) 原始：渠道账号正确提交次数 已生成
    has_count = "渠道账号正确提交次数" in orig.columns
    count_filled = int(_num_series(orig, "渠道账号正确提交次数").notna().sum()) if has_count else 0
    checks.append(
        Check(
            "Phase3: 原始 含 渠道账号正确提交次数",
            has_count and count_filled > 0,
            f"column={has_count} filled={count_filled}",
        )
    )

    # 8) 每行账期月：不只校验桶月，逐行日期必须落在桶起始自然月。
    derived = bucket_yyyymm(bname)
    if derived:
        want = f"{derived[:4]}-{derived[4:]}"
        months = orig["账期日期"].map(month_of)
        bad_mask = months != want
        n_bad = int(bad_mask.sum())
        samples = [str(v) for v in orig.loc[bad_mask, "账期日期"].head(5)]
        checks.append(
            Check(
                "Phase3: 原始 每行账期月 == 桶账期月",
                n_bad == 0,
                f"bad={n_bad} want={want} 样例={samples}",
            )
        )

    # 9) 分组合计 == 行级过滤后合计
    status = orig.get("审批状态", pd.Series(dtype=object)).astype(str).str.strip()
    result = orig.get("审批结果", pd.Series(dtype=object)).astype(str).str.strip()
    approved = status.isin(["完成", "审批中"]) & (result != "拒绝")
    bad_cols: list[str] = []
    for col in [c for c in rmb.columns if c.endswith("_人民币")]:
        if col not in orig.columns:
            continue
        row_sum = _num_series(orig, col)[approved].sum()
        group_sum = _num_series(group, col).sum()
        if not finite_close(row_sum, group_sum):
            bad_cols.append(f"{col}: group={group_sum:.2f} rows={row_sum:.2f}")
    checks.append(
        Check("Phase3: 分组表合计 == 行级过滤后合计", not bad_cols, "; ".join(bad_cols[:6]) or "全部一致")
    )

    # 10) 两张比例表与分组表同口径
    rate_bad: list[str] = []
    if "应收金额_人民币" in rate_receipt.columns:
        a, b = _num_series(rate_receipt, "应收金额_人民币").sum(), _num_series(group, "应收金额_人民币").sum()
        if not finite_close(a, b):
            rate_bad.append(f"收款归属.应收 sum={a:.2f} group={b:.2f}")
    if "销售额_人民币" in rate_staff.columns:
        a, b = _num_series(rate_staff, "销售额_人民币").sum(), _num_series(group, "销售额_人民币").sum()
        if not finite_close(a, b):
            rate_bad.append(f"运营人员.销售 sum={a:.2f} group={b:.2f}")
    checks.append(Check("Phase3: 两张比例表与分组表合计一致", not rate_bad, "; ".join(rate_bad) or "一致"))

    # 11) FBA 两表：声明适用则必须成对存在且列/数值完整。
    fba_summary = read_sheet_df(gc, sh, f"{period}{FBA_SUMMARY_SUFFIX}")
    fba_staff = read_sheet_df(gc, sh, f"{period}{FBA_STAFF_SUFFIX}")
    has_summary, has_staff = not fba_summary.empty, not fba_staff.empty
    pair_ok = (has_summary == has_staff) and (has_summary or not require_fba)
    checks.append(
        Check(
            "Phase3: FBA 两表成对（分类+人员）",
            pair_ok,
            f"分类={has_summary} 人员={has_staff} require_fba={require_fba}",
        )
    )
    if has_summary and has_staff:
        fba_problems: list[str] = []
        if "渠道账号" not in fba_summary.columns:
            fba_problems.append("分类缺 渠道账号")
        if FBA_DELTA_RMB not in fba_summary.columns:
            fba_problems.append(f"分类缺 {FBA_DELTA_RMB}")
        if "运营人员" not in fba_staff.columns:
            fba_problems.append("人员缺 运营人员")
        fba_problems.extend(
            numeric_cell_errors(
                fba_summary,
                [c for c in [FBA_DELTA_RMB, *rmb_columns(fba_summary)] if c in fba_summary.columns],
                table="FBA分类",
            )
        )
        fba_problems.extend(
            numeric_cell_errors(
                fba_staff, [c for c in rmb_columns(fba_staff) if c in fba_staff.columns], table="FBA人员"
            )
        )
        checks.append(
            Check("Phase3: FBA 两表列/数值完整", not fba_problems, "; ".join(fba_problems[:6]) or "完整")
        )
    return checks


def run_checks(
    gc,
    *,
    bucket: str,
    bucket_dir: Path | None = None,
    exchange_month: str = "",
    repair_dir: Path | None = None,
    do_tax: bool = True,
    do_phase3: bool = True,
    require_fba: bool = False,
) -> list[Check]:
    checks: list[Check] = []
    if not do_tax and not do_phase3:
        return [Check("Verify: 至少执行 Tax 或 Phase3 之一", False, "tax-only 与 phase3-only 不能同时给出")]
    bname = bucket_name(bucket)
    try:
        month = resolve_exchange_month(bname, exchange_month)
    except ValueError as exc:
        checks.append(Check("Verify: --exchange-month 与桶账期月一致", False, str(exc)))
        return checks
    checks.append(Check("Verify: --exchange-month 与桶账期月一致", True, f"exchange_month={month}"))
    if do_tax:
        if bucket_dir is None or not Path(bucket_dir).is_dir():
            checks.append(Check("Tax: 源目录存在", False, str(bucket_dir)))
        else:
            checks.extend(
                check_tax(gc, bucket=bucket, bucket_dir=Path(bucket_dir), exchange_month=month, repair_dir=repair_dir)
            )
    if do_phase3:
        checks.extend(check_phase3(gc, bucket=bucket, require_fba=require_fba))
    return checks
