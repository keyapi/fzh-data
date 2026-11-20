# -*- coding: utf-8 -*-
"""FBA 多组分摊守恒（F05/F06，整改 U-B B3）。

账号级差额是**账号总量**：同账号在组表多行、或源里有差额但组表没该账号，
都不能靠"逐行各加一份"或"静默丢弃"过关。``build_fba_staff`` 与
``apply_fba_to_group`` 共用同一套检查。
"""
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


def _staff_group() -> pd.DataFrame:
    return _group(
        [
            {
                "渠道账号": "AMZA",
                "运营人员": "甲",
                "收款归属": "平台",
                "应收金额_人民币": 100.0,
                "销售额_人民币": 200.0,
                "佣金_人民币": 10.0,
            },
            {
                "渠道账号": "AMZB",
                "运营人员": "乙",
                "收款归属": "平台",
                "应收金额_人民币": 40.0,
                "销售额_人民币": 80.0,
                "佣金_人民币": 4.0,
            },
        ]
    )


# ------------------------------------------------------------ 分组表（F05）


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


def test_multi_row_account_with_negative_delta_raises(monkeypatch):
    """审计原例：A 两组、差额 -5，不得产生 +10。"""
    df_group = _group(
        [
            {"渠道账号": "AMZA", "收款归属": "平台", "应收金额_人民币": 100.0, "佣金_人民币": 10.0},
            {"渠道账号": "AMZA", "收款归属": "我司", "应收金额_人民币": 50.0, "佣金_人民币": 5.0},
        ]
    )
    phase3_merge = _patch(monkeypatch, _fba([{"渠道账号": "AMZA", "调整前-后amount人民币": -5.0}]))
    with pytest.raises(ValueError, match="无法唯一挂"):
        phase3_merge.apply_fba_to_group(df_group, None, "20260804-20260903")


def test_single_row_account_applied_once(monkeypatch):
    df_group = _group(
        [
            {"渠道账号": "AMZA", "收款归属": "平台", "应收金额_人民币": 100.0, "佣金_人民币": 10.0},
            {"渠道账号": "AMZB", "收款归属": "平台", "应收金额_人民币": 40.0, "佣金_人民币": 4.0},
        ]
    )
    phase3_merge = _patch(monkeypatch, _fba([{"渠道账号": "AMZA", "调整前-后amount人民币": 100.0}]))
    out, ok = phase3_merge.apply_fba_to_group(df_group, None, "20260804-20260903")
    assert ok is True
    row_a = out[out["渠道账号"] == "AMZA"].iloc[0]
    assert row_a["FBA费用_人民币"] == pytest.approx(-100.0)
    assert row_a["加上FBA费用_应收金额_人民币"] == pytest.approx(0.0)
    assert row_a["扣减FBA费用_佣金_人民币"] == pytest.approx(110.0)
    assert out["FBA费用_人民币"].sum() == pytest.approx(-100.0)


def test_orphan_account_nonzero_delta_raises(monkeypatch):
    """源里有非零差额但组表没这账号：不能静默丢（F05 孤儿）。"""
    df_group = _group([{"渠道账号": "AMZA", "应收金额_人民币": 100.0, "佣金_人民币": 10.0}])
    phase3_merge = _patch(
        monkeypatch,
        _fba(
            [
                {"渠道账号": "AMZA", "调整前-后amount人民币": 100.0},
                {"渠道账号": "AMZZZ", "调整前-后amount人民币": -3.0},
            ]
        ),
    )
    with pytest.raises(ValueError, match="孤儿"):
        phase3_merge.apply_fba_to_group(df_group, None, "20260804-20260903")


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


def test_blank_account_in_summary_fails(monkeypatch):
    df_group = _group([{"渠道账号": "AMZA", "应收金额_人民币": 10.0, "佣金_人民币": 1.0}])
    phase3_merge = _patch(monkeypatch, _fba([{"渠道账号": "", "调整前-后amount人民币": 1.0}]))
    with pytest.raises(ValueError, match="渠道账号为空"):
        phase3_merge.apply_fba_to_group(df_group, None, "20260804-20260903")


def test_non_numeric_delta_fails(monkeypatch):
    df_group = _group([{"渠道账号": "AMZA", "应收金额_人民币": 10.0, "佣金_人民币": 1.0}])
    phase3_merge = _patch(monkeypatch, _fba([{"渠道账号": "AMZA", "调整前-后amount人民币": "x"}]))
    with pytest.raises(ValueError, match="非数值"):
        phase3_merge.apply_fba_to_group(df_group, None, "20260804-20260903")


# ------------------------------------------------------------ 人员表（F06）


def test_staff_multi_row_account_does_not_double():
    """审计原例：同账号两组、差额 -5，不得变成 +10。"""
    from phase3_merge import build_fba_staff

    group = _group(
        [
            {
                "渠道账号": "AMZA",
                "运营人员": "甲",
                "收款归属": "平台",
                "应收金额_人民币": 100.0,
                "销售额_人民币": 200.0,
                "佣金_人民币": 10.0,
            },
            {
                "渠道账号": "AMZA",
                "运营人员": "甲",
                "收款归属": "我司",
                "应收金额_人民币": 50.0,
                "销售额_人民币": 100.0,
                "佣金_人民币": 5.0,
            },
        ]
    )
    with pytest.raises(ValueError, match="无法唯一挂"):
        build_fba_staff(group, _fba([{"渠道账号": "AMZA", "调整前-后amount人民币": -5.0}]))


def test_staff_single_row_applies_once():
    from phase3_merge import build_fba_staff

    out = build_fba_staff(_staff_group(), _fba([{"渠道账号": "AMZA", "调整前-后amount人民币": -5.0}]))
    row = out[out["运营人员"] == "甲"].iloc[0]
    assert row["FBA费用_人民币"] == pytest.approx(5.0)  # 差额取反
    assert out["FBA费用_人民币"].sum() == pytest.approx(5.0)


def test_staff_zero_delta_multi_row_ok():
    from phase3_merge import build_fba_staff

    group = _group(
        [
            {"渠道账号": "AMZA", "运营人员": "甲", "应收金额_人民币": 10.0, "销售额_人民币": 20.0, "佣金_人民币": 1.0},
            {"渠道账号": "AMZA", "运营人员": "甲", "应收金额_人民币": 30.0, "销售额_人民币": 60.0, "佣金_人民币": 3.0},
        ]
    )
    out = build_fba_staff(group, _fba([{"渠道账号": "AMZA", "调整前-后amount人民币": 0.0}]))
    assert out["FBA费用_人民币"].sum() == pytest.approx(0.0)


def test_staff_orphan_account_fails():
    from phase3_merge import build_fba_staff

    with pytest.raises(ValueError, match="孤儿"):
        build_fba_staff(
            _staff_group(),
            _fba([{"渠道账号": "AMZB", "调整前-后amount人民币": -3.0}, {"渠道账号": "AMZZ", "调整前-后amount人民币": -3.0}]),
        )


def test_staff_none_summary_is_not_zero():
    from phase3_merge import build_fba_staff

    with pytest.raises(ValueError, match="分类汇总缺失"):
        build_fba_staff(_staff_group(), None)


def test_staff_matches_group_and_plain_staff_bases():
    """分类差额取反 = 人员 FBA 合计；人员基数与普通人员表一致。"""
    from phase3_merge import build_fba_staff, collection_rate_by_staff

    summary = _fba(
        [
            {"渠道账号": "AMZA", "调整前-后amount人民币": -5.0},
            {"渠道账号": "AMZB", "调整前-后amount人民币": 2.0},
        ]
    )
    staff = build_fba_staff(_staff_group(), summary).set_index("运营人员")
    plain = collection_rate_by_staff(_staff_group()).set_index("运营人员")
    assert staff["FBA费用_人民币"].sum() == pytest.approx(3.0)  # = -(-5+2)
    for col in ("应收金额_人民币", "销售额_人民币", "佣金_人民币"):
        assert (staff[col].astype(float) - plain[col].astype(float)).abs().max() <= 0.01
