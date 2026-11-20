# -*- coding: utf-8 -*-
"""账期管道硬关卡：Tax / Phase3 对账检查（只读，不写任何表）。

用法见 ``scripts/verify_period.py``。所有检查返回 ``Check``；任一项 FAIL → 脚本非 0 退出。
"""
from __future__ import annotations

import re
from dataclasses import dataclass
from pathlib import Path

import pandas as pd

from gsheet_tax import additional_fee_worksheet_name_from_yyyymm, open_additional_fee_tax_spreadsheet, tax_worksheet_name
from phase3_constants import LS_COL_COST

TOL = 0.01
MONEY_COLS = ["应收金额", "销售额", *LS_COL_COST]


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

    sheet_total = _num_series(sheet, "Tax amount人民币").sum()
    expected_total = float(expected["Tax amount人民币"].sum())
    diff = abs(sheet_total - expected_total)
    checks.append(
        Check(
            "Tax: Σ(Tax amount人民币) == 本地重算",
            diff <= TOL,
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
        if abs((sheet_map.get(acct) or 0.0) - (exp_map.get(acct) or 0.0)) > TOL
    ]
    checks.append(Check("Tax: 每账号金额一致", not bad, "; ".join(bad[:8]) or "全部一致"))
    return checks


def bucket_name(bucket: str) -> str:
    """归一成 账期YYYYMMDD-YYYYMMDD（允许只传日期区间）。"""
    return bucket if bucket.startswith("账期") else f"账期{bucket}"


def check_phase3(gc, *, bucket: str) -> list[Check]:
    """Phase3：Tax/附加费合计、原始缺汇率、渠道账号未匹配、分组合计 == 行级过滤后合计。"""
    from phase3_gsheet import open_phase3_spreadsheet

    checks: list[Check] = []
    period = period_range_from_bucket(bucket)
    yyyymm = period[:6]
    sh = open_phase3_spreadsheet(gc)
    orig = read_sheet_df(gc, sh, f"{period}原始")
    rmb = read_sheet_df(gc, sh, f"人民币{period}")
    group = read_sheet_df(gc, sh, period)
    tax = read_sheet_df(gc, open_additional_fee_tax_spreadsheet(gc), f"Tax{yyyymm}")
    sep = read_sheet_df(gc, open_additional_fee_tax_spreadsheet(gc), additional_fee_worksheet_name_from_yyyymm(yyyymm))

    missing_sheets = [n for n, d in [("原始", orig), ("人民币", rmb), ("分组", group)] if d.empty]
    checks.append(Check("Phase3: 五张主表存在", not missing_sheets, f"缺失={missing_sheets}"))
    if missing_sheets:
        return checks

    # 0) 审批中占比（只报告，不阻断）—— 审批中单据已计入本表金额，按账期月看敞口。
    approval_summary = approval_in_progress_summary(orig)
    checks.append(
        Check("Phase3: 审批中占比（只报告）", True, format_approval_summary(approval_summary))
    )

    # 1) 人民币.Tax == Tax{YYYYMM} 合计
    rmb_tax = _num_series(rmb, "Tax amount人民币").sum()
    tax_total = _num_series(tax, "Tax amount人民币").sum()
    checks.append(
        Check(
            "Phase3: Σ(人民币.Tax) == Σ(Tax{YYYYMM})",
            abs(rmb_tax - tax_total) <= TOL,
            f"rmb={rmb_tax:.2f} tax_ws={tax_total:.2f} diff={abs(rmb_tax - tax_total):.4f}",
        )
    )

    # 2) 人民币.附加费 == 附加费{YYYYMM}
    rmb_sep = _num_series(rmb, "附加费累加人民币").sum()
    sep_total = _num_series(sep, "附加费累加人民币").sum() if "附加费累加人民币" in sep.columns else 0.0
    sep_ok = bool(sep.empty) or abs(rmb_sep - sep_total) <= TOL
    checks.append(
        Check(
            "Phase3: Σ(人民币.附加费) == Σ(附加费{YYYYMM})",
            sep_ok,
            f"rmb={rmb_sep:.2f} sep_ws={sep_total:.2f} diff={abs(rmb_sep - sep_total):.4f}",
        )
    )

    # 3) 原始：外币>0 且 汇率空 == 0
    fx = _num_series(orig, "汇率")
    foreign = sum((_num_series(orig, c).abs() for c in MONEY_COLS if c in orig.columns), pd.Series(0.0, index=orig.index))
    bad_fx = int(((fx.isna() | (fx == 0)) & (foreign > 0)).sum())
    checks.append(Check("Phase3: 原始 外币>0 且汇率空 == 0", bad_fx == 0, f"rows={bad_fx}"))

    # 4) 原始：渠道账号未匹配 == 0
    acct = orig.get("渠道账号", pd.Series(dtype=object)).astype(str).str.strip()
    blank_acct = int(((acct == "") | (acct == "nan")).sum())
    checks.append(Check("Phase3: 渠道账号未匹配 == 0", blank_acct == 0, f"rows={blank_acct}"))

    # 5) 原始：渠道账号正确提交次数 已生成（审计项 7 的落地标志）
    has_count = "渠道账号正确提交次数" in orig.columns
    count_filled = int(_num_series(orig, "渠道账号正确提交次数").notna().sum()) if has_count else 0
    checks.append(
        Check(
            "Phase3: 原始 含 渠道账号正确提交次数",
            has_count and count_filled > 0,
            f"column={has_count} filled={count_filled}",
        )
    )

    # 6) 分组合计 == 行级过滤后合计
    status = orig.get("审批状态", pd.Series(dtype=object)).astype(str).str.strip()
    result = orig.get("审批结果", pd.Series(dtype=object)).astype(str).str.strip()
    approved = status.isin(["完成", "审批中"]) & (result != "拒绝")
    bad_cols: list[str] = []
    for col in [c for c in rmb.columns if c.endswith("_人民币")]:
        if col not in orig.columns:
            continue
        row_sum = _num_series(orig, col)[approved].sum()
        group_sum = _num_series(group, col).sum()
        if abs(row_sum - group_sum) > TOL:
            bad_cols.append(f"{col}: group={group_sum:.2f} rows={row_sum:.2f}")
    checks.append(
        Check("Phase3: 分组表合计 == 行级过滤后合计", not bad_cols, "; ".join(bad_cols[:6]) or "全部一致")
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
) -> list[Check]:
    checks: list[Check] = []
    period = period_range_from_bucket(bucket_name(bucket))
    month = exchange_month or period[:6]
    if do_tax:
        if bucket_dir is None or not Path(bucket_dir).is_dir():
            checks.append(Check("Tax: 源目录存在", False, str(bucket_dir)))
        else:
            checks.extend(
                check_tax(gc, bucket=bucket, bucket_dir=Path(bucket_dir), exchange_month=month, repair_dir=repair_dir)
            )
    if do_phase3:
        checks.extend(check_phase3(gc, bucket=bucket))
    return checks
