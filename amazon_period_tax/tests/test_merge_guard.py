# -*- coding: utf-8 -*-
"""合并唯一性 / 缺列报错 / 附加费别名归一（Codex 复核 BLOCK 项）。"""
from __future__ import annotations

import pandas as pd
import pytest

from phase3_merge import (
    load_additional_fee_grouped,
    load_tax_grouped,
    merge_rmb_tax_additional,
)


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


@pytest.fixture(autouse=True)
def _identity_canonical(monkeypatch):
    """不依赖本机 gitignored 渠道账号快照。"""
    import channel_canonical

    monkeypatch.setattr(channel_canonical, "canonical_account", lambda s: s)


def test_exchange_rate_duplicate_currency_raises():
    from exchange_rate import load_exchange_rate_table

    rows = [
        ["收款币种", "货币中文名", "货币别名", "202608"],
        ["USD", "美元", "US Dollar", "7.10"],
        ["USD", "美元副本", "US2", "7.20"],
    ]
    with pytest.raises(ValueError, match="收款币种 重复"):
        load_exchange_rate_table(_FakeGc(rows), month_col="202608")


def test_exchange_rate_alias_conflict_raises():
    from exchange_rate import load_exchange_rate_table

    rows = [
        ["收款币种", "货币中文名", "货币别名", "202608"],
        ["USD", "美元", "美元,US Dollar", "7.10"],
        ["EUR", "欧元", "欧元,US Dollar", "7.80"],
    ]
    with pytest.raises(ValueError, match="不同币种或汇率"):
        load_exchange_rate_table(_FakeGc(rows), month_col="202608")


def test_exchange_rate_ok_returns_unique_codes():
    from exchange_rate import load_exchange_rate_table

    rows = [
        ["收款币种", "货币中文名", "货币别名", "202608"],
        ["USD", "美元", "美元,US Dollar", "7.10"],
        ["EUR", "欧元", "欧元,Euro", "7.80"],
    ]
    df, exploded = load_exchange_rate_table(_FakeGc(rows), month_col="202608")
    assert sorted(df["收款币种"]) == ["EUR", "USD"]
    assert exploded["货币中文名"].is_unique


def _df_explode() -> pd.DataFrame:
    return pd.DataFrame(
        {
            "渠道账号": ["BASEPPPL", "AMZOTHER"],
            "渠道账号别名": ["BasePPPL", "other-acct"],
            "运营人员": ["甲", "乙"],
        }
    )


def test_tax_missing_columns_raises():
    rows = [["渠道账号", "其他列"], ["AMZOTHER", "1"]]
    with pytest.raises(ValueError, match="缺必需列"):
        load_tax_grouped(_FakeGc(rows), "账期20260804-20260903", _df_explode())


def test_tax_missing_columns_allowed_when_explicit():
    rows = [["渠道账号", "其他列"], ["AMZOTHER", "1"]]
    out, unmatched = load_tax_grouped(
        _FakeGc(rows), "账期20260804-20260903", _df_explode(), allow_empty=True
    )
    assert out.empty
    assert list(out.columns) == ["渠道账号", "Tax amount人民币"]
    assert unmatched == []


def test_additional_fee_alias_mapped_and_unmatched_collected():
    rows = [
        ["渠道账号", "附加费累加人民币", "账号单独费用"],
        ["BasePPPL", "6428.80", "1.5"],
        ["mystery-acc", "2", "3"],
    ]
    out, unmatched = load_additional_fee_grouped(_FakeGc(rows), "202607", _df_explode())
    got = dict(zip(out["渠道账号"], out["附加费累加人民币"]))
    assert got["BASEPPPL"] == pytest.approx(6428.80)
    assert "mystery-acc" in unmatched
    assert "BasePPPL" not in set(out["渠道账号"])  # 不再以别名单独成行


def test_additional_fee_missing_amount_columns_raises():
    rows = [["渠道账号", "运营人员"], ["AMZOTHER", "乙"]]
    with pytest.raises(ValueError, match="缺必需列"):
        load_additional_fee_grouped(_FakeGc(rows), "202607", _df_explode())


def test_merge_counts_and_outer_only_accounts_reported():
    df_rmb = pd.DataFrame({"渠道账号": ["A", "B"], "应收金额_人民币": [10.0, 20.0]})
    df_sep = pd.DataFrame({"渠道账号": ["A", "C"], "附加费累加人民币": [1.0, 5.0]})
    df_tax = pd.DataFrame({"渠道账号": ["B"], "Tax amount人民币": [100.0]})
    df_account = pd.DataFrame(
        {
            "渠道": ["Amazon"] * 4,
            "渠道账号": ["A", "B", "C", "D"],
            "运营人员": ["甲", "乙", "丙", "丁"],
        }
    )
    stats: dict = {}
    out = merge_rmb_tax_additional(
        df_rmb, df_sep=df_sep, df_tax=df_tax, df_account=df_account, stats_out=stats
    )
    assert len(out) == 4
    assert out["渠道账号"].is_unique
    assert "附加费:C" in stats["outer_only_accounts"]
    assert "账号表:D" in stats["outer_only_accounts"]


def test_merge_duplicate_account_raises():
    df_rmb = pd.DataFrame({"渠道账号": ["A"], "应收金额_人民币": [10.0]})
    df_sep = pd.DataFrame({"渠道账号": ["A", "A"], "附加费累加人民币": [1.0, 2.0]})
    df_account = pd.DataFrame({"渠道": ["Amazon"], "渠道账号": ["A"], "运营人员": ["甲"]})
    with pytest.raises(ValueError, match="重复"):
        merge_rmb_tax_additional(df_rmb, df_sep=df_sep, df_tax=pd.DataFrame(), df_account=df_account)
