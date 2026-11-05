# -*- coding: utf-8 -*-
"""Regression tests for external-review F1/F3 fixes (2026-11-05)."""
from __future__ import annotations

import importlib.util
from datetime import date
from pathlib import Path

import numpy as np
import pandas as pd

ROOT = Path(__file__).resolve().parents[2]


def load(name: str, filename: str):
    spec = importlib.util.spec_from_file_location(name, ROOT / "scripts" / filename)
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


def test_us_total_inputs_sum_both_pools():
    d5 = load("d5_v64", "d5_time_validated_v6_4_20261105.py")
    keys = [("P1", "美东USNJ", "成品", "个"), ("P1", "美中USTX", "成品", "个"),
            ("P2", "波兰", "成品", "个")]
    monthly = {
        (keys[0], 202601): 3.0, (keys[1], 202601): 4.0,
        (keys[2], 202601): 9.0,
        (keys[0], 202602): 1.0, (keys[1], 202602): 2.0,
    }
    daily = {
        keys[0]: pd.Series({date(2026, 1, 1): 3.0}),
        keys[1]: pd.Series({date(2026, 1, 1): 4.0, date(2026, 1, 2): 1.0}),
        keys[2]: pd.Series({date(2026, 1, 1): 9.0}),
    }
    total_keys, total_monthly, total_daily = d5.us_total_inputs(keys, monthly, daily)
    assert total_keys == [("P1", "US_total", "成品", "个")]
    assert total_monthly[(("P1", "US_total", "成品", "个"), 202601)] == 7.0
    assert total_monthly[(("P1", "US_total", "成品", "个"), 202602)] == 3.0
    series = total_daily[("P1", "US_total", "成品", "个")]
    assert float(series.sum()) == 8.0
    assert "P2" not in {k[0] for k in total_keys}


def test_simulate_never_stockout_with_abundant_stock():
    s2 = load("s2_9", "s2_9_daily_service_validation_20261105.py")
    rng = np.random.default_rng(1)
    res = s2.simulate(10, 30, on_hand=10_000, receipts=[], qty=0,
                      prod=np.zeros(50), head=np.zeros(50),
                      order_delay=0, need_days=97, rng=rng)
    assert res["no_stockout"] == 1.0
    assert res["fill_rate"] > 0.99


def test_simulate_stockout_without_stock_or_order():
    s2 = load("s2_9", "s2_9_daily_service_validation_20261105.py")
    rng = np.random.default_rng(2)
    res = s2.simulate(10, 30, on_hand=0, receipts=[], qty=0,
                      prod=np.zeros(50), head=np.zeros(50),
                      order_delay=0, need_days=97, rng=rng)
    assert res["no_stockout"] < 0.05
    assert res["fill_rate"] < 0.05


def test_simulate_long_lead_fails_arrival():
    s2 = load("s2_9", "s2_9_daily_service_validation_20261105.py")
    rng = np.random.default_rng(3)
    res = s2.simulate(10, 30, on_hand=10_000, receipts=[], qty=10,
                      prod=np.full(50, 200.0), head=np.zeros(50),
                      order_delay=0, need_days=97, rng=rng)
    assert res["arrival_prob"] == 0.0
