# -*- coding: utf-8 -*-
"""FBA 特例规则过滤：只能命中规则里的 SKU，不能退化成整账号。"""
from __future__ import annotations

import pandas as pd

from fba_adjust import process_fba_orders


def _fba_df() -> pd.DataFrame:
    return pd.DataFrame(
        {
            "渠道账号": ["AMZAUS", "AMZAUS", "AMZAUS", "AMZBUS", "AMZBUS"],
            "sku": ["SKU1", "SKU2", "SKU3", "SKU1", "SKU9"],
            "amount-description": ["FBAPerUnitFulfillmentFee"] * 5,
            "amount": [10.0, 20.0, 30.0, 40.0, 50.0],
            "汇率": [7.0] * 5,
        }
    )


def test_rule_matches_only_listed_sku():
    rules = pd.DataFrame({"渠道账号": ["AMZAUS"], "平台SKU": ["SKU1"], "当月是否执行": ["是"]})
    out = process_fba_orders(rules, _fba_df())
    by = {(a, s): v for a, s, v in zip(out["渠道账号"], out["sku"], out["amount"])}
    assert by[("AMZAUS", "SKU1")] == 0.0  # 命中规则
    assert by[("AMZAUS", "SKU2")] == 20.0  # 同账号其它 SKU 不受影响
    assert by[("AMZAUS", "SKU3")] == 30.0
    assert by[("AMZBUS", "SKU9")] == 50.0
    assert (out["调整前-后amount"] > 0).sum() == 1


def test_account_level_rule_matches_all_of_that_account():
    """规则 SKU 为空（NaN）→ 账号级规则，命中该账号全部行。"""
    rules = pd.DataFrame({"渠道账号": ["AMZBUS"], "平台SKU": [None], "当月是否执行": ["是"]})
    out = process_fba_orders(rules, _fba_df())
    b = out[out["渠道账号"] == "AMZBUS"]
    assert (b["amount"] == 0).all()
    assert (out[out["渠道账号"] == "AMZAUS"]["amount"] > 0).all()


def test_rule_sku_whitespace_insensitive():
    rules = pd.DataFrame({"渠道账号": ["AMZAUS"], "平台SKU": ["SKU 2"], "当月是否执行": ["是"]})
    out = process_fba_orders(rules, _fba_df())
    by = {(a, s): v for a, s, v in zip(out["渠道账号"], out["sku"], out["amount"])}
    assert by[("AMZAUS", "SKU2")] == 0.0
    assert by[("AMZAUS", "SKU1")] == 10.0
