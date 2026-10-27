# -*- coding: utf-8 -*-
"""前沿 v2 用例：全局日历、暖机多周期、倍数单调、无前视。"""

from __future__ import annotations

import numpy as np
import pandas as pd
import pytest

from supply_netting.frontier_v2 import (EVAL_END, build, global_series, simulate,
                                       target_from)

KEY = ["canonical_sku", "canonical_warehouse", "canonical_uom"]


def test_global_series_fills_tail_days_with_zero():
    demand = pd.DataFrame([
        dict(canonical_sku="K", canonical_warehouse="W", canonical_uom="个",
             quantity_default=5.0, date=pd.Timestamp("2026-10-20")),
    ])
    series = global_series(demand, ("K", "W", "个"), pd.Timestamp("2026-10-18"),
                           pd.Timestamp("2026-10-26"))
    assert len(series) == 9                     # 全局日历，不是按最后一笔订单截断
    assert series[-1] == 0.0 and series[2] == 5.0


def test_warmup_runs_multiple_cycles_and_seeds_pipeline():
    daily = np.full(400, 3.0)
    # 提前期 90 天 × 3/天 = 270 件在途，目标 350 才够
    result = simulate(daily, target=350.0, sim_start=200, score_start=300, end=395,
                      lead=90, review=7, seed_rate=3.0)
    assert result["cycles"] >= 10               # 95 天 / 7 天 ≈ 13 个复核周期
    assert result["fill_rate"] is not None and result["fill_rate"] > 0.9


def test_higher_target_never_lowers_fill_rate():
    daily = np.random.default_rng(3).poisson(4, size=400).astype(float)
    low = simulate(daily, 40.0, sim_start=200, score_start=300, end=395,
                   lead=90, review=7, seed_rate=4.0)
    high = simulate(daily, 80.0, sim_start=200, score_start=300, end=395,
                    lead=90, review=7, seed_rate=4.0)
    assert high["fill_rate"] >= low["fill_rate"] - 1e-9


def test_target_quantile_monotone():
    history = np.random.default_rng(11).normal(8, 2, size=365).clip(0)
    q90 = target_from(history, 0.90, 97)
    q95 = target_from(history, 0.95, 97)
    q98 = target_from(history, 0.98, 97)
    assert q90 <= q95 <= q98


def _demand_frame(eval_multiplier: float = 1.0):
    rows = []
    days = pd.date_range("2025-07-20", "2026-10-26", freq="D")
    for index, day in enumerate(days):
        in_eval = day > pd.Timestamp("2026-07-23")
        qty = 4.0 if not in_eval else 4.0 * eval_multiplier
        rows.append(dict(canonical_sku="K1", canonical_warehouse="W", canonical_uom="个",
                         quantity_default=qty, demand_date=day.date()))
    rows.append(dict(canonical_sku="K2", canonical_warehouse="W", canonical_uom="个",
                     quantity_default=1.0, demand_date=pd.Timestamp("2025-08-01").date()))
    return pd.DataFrame(rows)


def test_abc_and_eligibility_ignore_future_sales(tmp_path):
    """只改评估期内销量，ABC/资格不能变（禁止前视）。"""
    keys = pd.DataFrame([dict(window_days=90, canonical_sku="K1", canonical_warehouse="W",
                              canonical_uom="个", forecast_demand=1.0, qty_current=0.0),
                         dict(window_days=90, canonical_sku="K2", canonical_warehouse="W",
                              canonical_uom="个", forecast_demand=1.0, qty_current=0.0)])
    keys_path = tmp_path / "keys.csv"
    keys.to_csv(keys_path, index=False)

    outputs = []
    for multiplier in (1.0, 50.0):
        path = tmp_path / f"demand_{multiplier}.parquet"
        _demand_frame(multiplier).to_parquet(path, index=False)
        by_key, coverage = build(path, keys_path)
        replay = by_key[(by_key["lead_days"] == 90) & (by_key["service_level"] == 0.95)
                        & (by_key["target_multiplier"] == 1.0)]
        outputs.append((coverage["eligible_keys"],
                        replay.set_index("SKU")["abc_tier"].to_dict()))
    assert outputs[0] == outputs[1]              # 评估期销量放大 50 倍也不影响资格/分档
