# -*- coding: utf-8 -*-
"""Tax 汇率合并：币种写法归一化；汇率表别名行不能把金额乘多遍。"""
from __future__ import annotations

import pandas as pd

from tax_aggregate import enrich_with_fx


def test_currency_normalized_both_sides():
    df = pd.DataFrame(
        {
            "currency": ["USD​", "ＥＵＲ", "GBP"],
            "amount": [10.0, 5.0, 2.0],
        }
    )
    rates = pd.DataFrame(
        {
            "收款币种": ["USD", "EUR", "GBP"],
            "汇率": [7.0, 8.0, 9.0],
        }
    )
    out = enrich_with_fx(df, rates)
    assert out["汇率"].tolist() == [7.0, 8.0, 9.0]
    assert out["amount人民币"].tolist() == [70.0, 40.0, 18.0]


def test_duplicate_rate_rows_do_not_multiply():
    df = pd.DataFrame({"currency": ["USD"], "amount": [10.0]})
    rates = pd.DataFrame({"收款币种": ["USD", "USD"], "汇率": [7.0, 7.0]})
    out = enrich_with_fx(df, rates)
    assert len(out) == 1
    assert out["amount人民币"].iloc[0] == 70.0
