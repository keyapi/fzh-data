# -*- coding: utf-8 -*-
"""账期桶名 → 日期窗口 / 账期月 + 汇率月一致性校验。"""
from __future__ import annotations

import pytest

from bucket_meta import bucket_period_range, bucket_yyyymm, resolve_exchange_month


def test_bucket_period_range_parses_window():
    rng = bucket_period_range("账期20260704-20260803")
    assert rng is not None
    assert (rng[0].isoformat(), rng[1].isoformat()) == ("2026-07-04", "2026-08-03")


def test_bucket_period_range_accepts_plain_range_and_custom_dir():
    assert bucket_period_range("20261004-20261103") is not None
    assert bucket_period_range("我的同步目录") is None


def test_bucket_yyyymm():
    assert bucket_yyyymm("账期20260804-20260903") == "202608"
    assert bucket_yyyymm("random") is None


def test_resolve_exchange_month_derives_from_bucket():
    assert resolve_exchange_month("账期20260804-20260903") == "202608"


def test_resolve_exchange_month_explicit_mismatch_raises():
    with pytest.raises(ValueError, match="不一致"):
        resolve_exchange_month("账期20260804-20260903", "202607")


def test_resolve_exchange_month_force_allows_mismatch():
    assert resolve_exchange_month("账期20260804-20260903", "202607", force=True) == "202607"


def test_resolve_exchange_month_requires_derivable_when_blank():
    with pytest.raises(ValueError, match="无法从桶名推导"):
        resolve_exchange_month("自定义目录", "")


def test_resolve_exchange_month_validates_format():
    with pytest.raises(ValueError, match="YYYYMM"):
        resolve_exchange_month("账期20260804-20260903", "2026-08")
