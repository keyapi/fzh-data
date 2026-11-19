# -*- coding: utf-8 -*-
"""FBA 多组分摊守恒：账号级差额不能给同账号的每行各加一份。"""
from __future__ import annotations

import pandas as pd
import pytest


def _group(rows: list[dict]) -> pd.DataFrame:
    return pd.DataFrame(rows)


def _fba(rows: list[dict]) -> pd.DataFrame:
    return pd.DataFrame(rows)


def _patch(monkeypatch, fba_df):
    import phase3_merge

    monkeypatch.setattr(phase3_merge, "read_worksheet_df", lambda gc, name: fba_df)
    # 避免测试依赖真实 GSheet 可读性
    monkeypatch.setattr(phase3_merge, "phase3_spreadsheet_available", lambda gc: True)
    return phase3_merge


def test_multi_row_account_with_fba_raises(monkeypatch):
    df_group = _group(
        [
            {"渠道账号": "AMZA", "收款归属": "平台", "应收金额_人民币": 100.0, "佣金_人民币": 10.0},
            {"渠道账号": "AMZA", "收款归属": "我司", "应收金额_人民币": 50.0, "佣金_人民币": 5.0},
        ]
    )
    phase3_merge = _patch(monkeypatch, _fba([{"渠道账号": "AMZA", "调整前-后amount人民币": 100.0}]))
    with pytest.raises(ValueError, match="无法唯一挂"):
        phase3_merge.apply_fba_to_group(df_group, None, "20260804-20260903")


def test_single_row_account_applied_once(monkeypatch):
    df_group = _group(
        [
            {"渠道账号": "AMZA", "收款归属": "平台", "应收金额_人民币": 100.0, "佣金_人民币": 10.0},
            {"渠道账号": "AMZB", "收款归属": "平台", "应收金额_人民币": 40.0, "佣金_人民币": 4.0},
        ]
    )
    phase3_merge = _patch(
        monkeypatch,
        _fba(
            [
                {"渠道账号": "AMZA", "调整前-后amount人民币": 100.0},
                # 不在分组表的账号：不参与守恒断言
                {"渠道账号": "AMZZZ", "调整前-后amount人民币": 999.0},
            ]
        ),
    )
    out, ok = phase3_merge.apply_fba_to_group(df_group, None, "20260804-20260903")
    assert ok is True
    row_a = out[out["渠道账号"] == "AMZA"].iloc[0]
    assert row_a["FBA费用_人民币"] == pytest.approx(-100.0)
    assert row_a["加上FBA费用_应收金额_人民币"] == pytest.approx(0.0)
    assert row_a["扣减FBA费用_佣金_人民币"] == pytest.approx(110.0)
    assert out["FBA费用_人民币"].sum() == pytest.approx(-100.0)


def test_multi_row_account_with_zero_fba_is_allowed(monkeypatch):
    df_group = _group(
        [
            {"渠道账号": "AMZA", "收款归属": "平台", "应收金额_人民币": 10.0, "佣金_人民币": 1.0},
            {"渠道账号": "AMZA", "收款归属": "我司", "应收金额_人民币": 20.0, "佣金_人民币": 2.0},
        ]
    )
    phase3_merge = _patch(monkeypatch, _fba([{"渠道账号": "AMZA", "调整前-后amount人民币": 0.0}]))
    out, ok = phase3_merge.apply_fba_to_group(df_group, None, "20260804-20260903")
    assert ok is True
    assert out["FBA费用_人民币"].sum() == pytest.approx(0.0)


def test_empty_fba_sheet_returns_unchanged(monkeypatch):
    df_group = _group([{"渠道账号": "AMZA", "应收金额_人民币": 10.0, "佣金_人民币": 1.0}])
    phase3_merge = _patch(monkeypatch, pd.DataFrame())
    out, ok = phase3_merge.apply_fba_to_group(df_group, None, "20260804-20260903")
    assert ok is False
    assert out is df_group
