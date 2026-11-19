# -*- coding: utf-8 -*-
"""Phase3 合并：列序、提交次数、Tax 别名归一、RAW 写表单元格。"""
from __future__ import annotations

import pandas as pd

from phase3_gsheet import df_to_gsheet_rows


def _group_df() -> pd.DataFrame:
    return pd.DataFrame(
        {
            "选择平台": ["亚马逊", "亚马逊"],
            "渠道": ["Amazon", "Amazon"],
            "渠道账号": ["AMZAUS", "AMZBUS"],
            "运营人员": ["甲", "乙"],
            "应收金额_人民币": [100.0, 0.0],
            "销售额_人民币": [200.0, 0.0],
            "佣金_人民币": [20.0, 0.0],
        }
    )


def test_collection_rate_staff_column_order():
    from phase3_merge import collection_rate_by_staff

    out = collection_rate_by_staff(_group_df())
    cols = list(out.columns)
    assert cols == [
        "运营人员",
        "销售额_人民币",
        "应收金额_人民币",
        "应收金额_比例",
        "佣金_人民币",
        "佣金_比例",
    ]
    # 销售额为 0 → 比例按 notebook 填 1.0；0/200 = 0
    row = out[out["运营人员"] == "甲"].iloc[0]
    assert row["应收金额_比例"] == 0.5
    assert row["佣金_比例"] == 0.1
    row_b = out[out["运营人员"] == "乙"].iloc[0]
    assert row_b["佣金_比例"] == 1.0


def test_submission_count_only_approved():
    from phase3_merge import build_row_level_df

    df = pd.DataFrame(
        {
            "亚马逊销售账户": ["A", "A", "B", "C"],
            "审批状态": ["完成", "审批中", "已撤销", "完成"],
            "审批结果": ["同意", "", "", "拒绝"],
            "币种": ["USD"] * 4,
            "应收金额": [1, 1, 1, 1],
            "销售额": [10, 10, 10, 10],
        }
    )
    df_rate_explode = pd.DataFrame({"货币中文名": ["USD"], "收款币种": ["USD"], "汇率": [7.0]})
    df_explode = pd.DataFrame(
        {
            "渠道账号": ["AMZA", "AMZB", "AMZC"],
            "渠道账号别名": ["A", "B", "C"],
            "运营人员": ["甲", "乙", "丙"],
        }
    )
    out, _filter = build_row_level_df(
        df, df_exchange_rate=None, df_explode=df_explode, df_rate_explode=df_rate_explode
    )
    assert "渠道账号正确提交次数" in out.columns
    assert out.loc[0, "渠道账号正确提交次数"] == 2
    assert out.loc[1, "渠道账号正确提交次数"] == 2
    assert pd.isna(out.loc[2, "渠道账号正确提交次数"])  # 已撤销
    assert pd.isna(out.loc[3, "渠道账号正确提交次数"])  # 拒绝


class _FakeWS:
    def __init__(self, rows):
        self._rows = rows

    def get_all_values(self):
        return self._rows


class _FakeSh:
    def __init__(self, rows):
        self._rows = rows

    def worksheet(self, name):
        return _FakeWS(self._rows)


class _FakeGc:
    def __init__(self, rows):
        self._rows = rows

    def open_by_key(self, _id):
        return _FakeSh(self._rows)


def test_tax_alias_normalized(monkeypatch):
    import channel_canonical

    monkeypatch.setattr(channel_canonical, "canonical_account", lambda s: s)
    rows = [
        ["渠道账号", "Tax amount人民币"],
        ["amz-accA", "100"],
        ["AMZACCB", "50"],
    ]
    df_explode = pd.DataFrame(
        {
            "渠道账号": ["AMZACCA", "AMZACCB"],
            "渠道账号别名": ["amz-accA", "AMZACCB"],
            "运营人员": ["甲", "乙"],
        }
    )
    from phase3_merge import load_tax_grouped

    out, unmatched = load_tax_grouped(_FakeGc(rows), "账期20261004-20261103", df_explode)
    got = dict(zip(out["渠道账号"], out["Tax amount人民币"]))
    assert got == {"AMZACCA": 100.0, "AMZACCB": 50.0}
    assert unmatched == []


def test_raw_gsheet_rows_keep_id_text_and_numbers():
    df = pd.DataFrame(
        {
            "审批编号": ["202608101804000200960"],
            "金额": [1234.5],
            "空值": [None],
        }
    )
    header, row = df_to_gsheet_rows(df)
    assert header == ["审批编号", "金额", "空值"]
    assert row[0] == "202608101804000200960"  # 21 位编号保持文本
    assert isinstance(row[1], float) and row[1] == 1234.5  # 数字不转字符串
    assert row[2] == ""
