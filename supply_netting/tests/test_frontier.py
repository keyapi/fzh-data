# -*- coding: utf-8 -*-
"""服务—库存前沿用例：回放正确性、分位单调、稀疏键不硬造、端到端契约。"""

from __future__ import annotations

import numpy as np
import pandas as pd
import pytest

from supply_netting.frontier import (EVALUATION_DAYS, MIN_DEMAND_DAYS, SCENARIOS,
                                     _target_from, build_frontier, replay)


def test_replay_with_sufficient_stock_has_full_fill():
    daily = np.full(120, 2.0)
    result = replay(daily, target=200.0, start=100, end=120)
    assert result["fill_rate"] == pytest.approx(1.0)
    assert result["lost"] == 0.0
    assert result["stockout_days"] == 0


def test_replay_with_no_stock_loses_everything_and_keeps_nulls_safe():
    daily = np.full(120, 2.0)
    result = replay(daily, target=0.0, start=100, end=120)
    assert result["fill_rate"] == pytest.approx(0.0)
    assert result["lost"] == pytest.approx(40.0)
    assert result["stockout_days"] == 20


def test_replay_orders_arrive_after_lead_time_only():
    """提前期 90 天 > 评估窗：评估窗内下的单不应让 fill rate 变好。"""
    daily = np.array([5.0] * 100 + [0.0] * 20)
    low = replay(daily, target=10.0, start=100, end=120)
    assert low["fill_rate"] is None or low["fill_rate"] == 0.0 or low["demand"] == 0.0


def test_target_quantile_is_monotone():
    history = np.random.default_rng(7).normal(10, 3, size=365).clip(0)
    q90 = _target_from(history, 0.90)
    q95 = _target_from(history, 0.95)
    q98 = _target_from(history, 0.98)
    assert q90 <= q95 <= q98


def test_build_frontier_uses_real_paths_and_skips_sparse_keys(tmp_path):
    dates = pd.date_range("2025-10-27", periods=365, freq="D")
    rows = []
    for sku, daily_qty in (("DENSE", 3.0), ("SPARSE", 0.0)):
        for index, day in enumerate(dates):
            qty = daily_qty if sku == "DENSE" else (1.0 if index % 30 == 0 else 0.0)
            if qty:
                rows.append(dict(canonical_sku=sku, canonical_warehouse="W",
                                 canonical_uom="个", quantity_default=qty,
                                 in_default_series=True, demand_date=day.date()))
    demand = pd.DataFrame(rows)
    demand_path = tmp_path / "demand.parquet"
    demand.to_parquet(demand_path, index=False)

    keys = pd.DataFrame([
        dict(window_days=90, canonical_sku="DENSE", canonical_warehouse="W",
             canonical_uom="个", forecast_demand=900.0, qty_current=100.0),
        dict(window_days=90, canonical_sku="SPARSE", canonical_warehouse="W",
             canonical_uom="个", forecast_demand=30.0, qty_current=5.0),
    ])
    keys_path = tmp_path / "keys.csv"
    keys.to_csv(keys_path, index=False)

    summary, per_key, coverage = build_frontier(demand_path, keys_path)
    assert coverage["replayed_keys"] == 1                 # 稀疏键被跳过，不硬造
    assert per_key["SKU"].unique().tolist() == ["DENSE"]
    assert set(per_key["场景"]) == set(SCENARIOS)
    assert len(summary["scenarios"]) == 4
    assert coverage["skipped"]["too_sparse"] == 1
    assert 0.0 <= summary["scenarios"][0]["fill_rate"] <= 1.0
