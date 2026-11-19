# -*- coding: utf-8 -*-
"""审批中占比（按月，只报告）。"""
from __future__ import annotations

import pandas as pd

from verify_period import approval_in_progress_summary, format_approval_summary, month_of


def test_month_of_variants():
    assert month_of("2026-07-04") == "2026-07"
    assert month_of("2026/7/4") == "2026-07"
    assert month_of("20260704") == "2026-07"
    assert month_of("2026-07-04 00:00:00") == "2026-07"
    assert month_of(None) is None
    assert month_of("") is None
    assert month_of("nan") is None
    assert month_of("2026-13-01") is None


def _df() -> pd.DataFrame:
    return pd.DataFrame(
        {
            "账期日期": ["2026-07-04", "2026-07-10", "2026-07-15", "2026-08-02"],
            "审批状态": ["完成", "审批中", "审批中", "审批中"],
            "审批结果": ["同意", "", "拒绝", ""],
            "应收金额": [100.0, 50.0, 30.0, 25.0],
            "销售额": [1000.0, 500.0, 300.0, 250.0],
        }
    )


def test_approval_in_progress_summary_excludes_rejected():
    out = approval_in_progress_summary(_df())
    assert list(out["月份"]) == ["2026-07", "2026-08"]
    july = out[out["月份"] == "2026-07"].iloc[0]
    assert july["行数"] == 1
    assert july["应收金额"] == 50.0
    assert july["销售额"] == 500.0
    assert july["行数占比"] == 0.25
    assert july["应收占比"] == 50.0 / 205.0
    assert july["销售占比"] == 500.0 / 2050.0
    aug = out[out["月份"] == "2026-08"].iloc[0]
    assert aug["行数"] == 1
    assert aug["应收金额"] == 25.0


def test_approval_summary_is_report_only_no_fail_flag():
    # 返回结构里只有统计值，没有 ok/FAIL 语义；format 不抛异常即可
    text = format_approval_summary(approval_in_progress_summary(_df()))
    assert "2026-07" in text and "2026-08" in text


def test_empty_or_missing_column():
    assert approval_in_progress_summary(pd.DataFrame()).empty
    assert approval_in_progress_summary(pd.DataFrame({"应收金额": [1.0]})).empty
