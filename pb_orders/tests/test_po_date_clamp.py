#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""通途导入：超过 3 个月的 PO Date 要改成导入日（付款时间）。"""

from __future__ import annotations

from datetime import date

import pandas as pd

import pb_tongtu_excel as t


def test_old_po_date_is_clamped_and_new_is_untouched():
    df = pd.DataFrame(
        {
            "PO Number": ["137682252", "138280979", "137682252"],
            "PO Date": [
                "2026-08-12 00:00:00",
                "2026-11-09 00:00:00",
                "2026-08-12 00:00:00",
            ],
        }
    )
    out, adjustments = t.clamp_old_po_dates(df, today=date(2026, 11, 16))
    assert out["PO Date"].tolist() == [
        "2026-11-16 00:00:00",
        "2026-11-09 00:00:00",
        "2026-11-16 00:00:00",
    ]
    # 同一 PO 多行只报一次
    assert adjustments == [{"po": "137682252", "old": "2026-08-12", "new": "2026-11-16"}]
    # 原 df 不被修改（只改导出用的副本）
    assert df["PO Date"].iloc[0] == "2026-08-12 00:00:00"


def test_date_exactly_on_cutoff_is_untouched():
    df = pd.DataFrame({"PO Number": ["A"], "PO Date": ["2026-08-18 00:00:00"]})
    out, adjustments = t.clamp_old_po_dates(df, today=date(2026, 11, 16))
    assert out["PO Date"].tolist() == ["2026-08-18 00:00:00"]
    assert adjustments == []


def test_missing_or_bad_dates_are_ignored():
    df = pd.DataFrame(
        {"PO Number": ["A", "B"], "PO Date": [None, "not-a-date"]}
    )
    out, adjustments = t.clamp_old_po_dates(df, today=date(2026, 11, 16))
    assert adjustments == []
    assert out["PO Date"].isna().sum() == 1
    assert out["PO Date"].tolist()[1] == "not-a-date"


def test_no_po_date_column_is_a_noop():
    df = pd.DataFrame({"PO Number": ["A"]})
    out, adjustments = t.clamp_old_po_dates(df)
    assert adjustments == []
    assert out.equals(df)
