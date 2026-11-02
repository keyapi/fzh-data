from __future__ import annotations

import importlib.util
from pathlib import Path

import numpy as np
import pytest


SCRIPT = Path(__file__).resolve().parents[2] / "scripts" / "d3b_history_backtest_v3_2_2026-11-02.py"
SPEC = importlib.util.spec_from_file_location("d3b_history_backtest", SCRIPT)
MODULE = importlib.util.module_from_spec(SPEC)
SPEC.loader.exec_module(MODULE)


def test_zero_mae_baseline_is_still_a_valid_comparator():
    selected = MODULE.select(
        {
            "naive": {"status": "ok", "wape": 0.0, "mae": 0.0, "den": 20.0},
            "croston": {"status": "ok", "wape": 0.2, "mae": 1.0, "den": 20.0},
        },
        "intermittent",
    )

    assert selected["adopted"] == "naive"
    assert selected["baseline"] == "naive"


def test_naive_uses_latest_observed_month_and_training_keeps_gap():
    months = [f"2025{m:02d}" for m in range(1, 13)] + ["202601", "202602", "202603", "202604", "202605"]
    y = np.array([1.0] * 12 + [np.nan, 4.0, 6.0, 2.0, 3.0])
    obs = np.array([True] * 12 + [False, True, True, True, True])

    rows = MODULE.backtest(y, obs, ["naive"], origins=("202602",), h=3, months=months)

    assert rows[0]["status"] == "ok"
    assert rows[0]["n_train"] == 13
    assert rows[0]["n_train_calendar"] == 14
    assert rows[0]["abs_err"] == 5.0  # 4 forecast from latest observed month, not a fabricated zero.


def test_ma3_refuses_a_missing_month_in_its_calendar_window():
    months = [f"2025{m:02d}" for m in range(1, 13)] + ["202601", "202602", "202603", "202604", "202605"]
    y = np.array([1.0] * 12 + [np.nan, 4.0, 6.0, 2.0, 3.0])
    obs = np.array([True] * 12 + [False, True, True, True, True])

    rows = MODULE.backtest(y, obs, ["ma3"], origins=("202602",), h=3, months=months)

    assert rows[0]["status"] == "failed"
    assert "缺观测" in rows[0]["reason"]


def test_snaive_fails_when_exact_t_minus_12_month_is_unobserved():
    months = [f"2025{m:02d}" for m in range(1, 13)] + ["202601", "202602", "202603", "202604", "202605"]
    y = np.array([1.0, 1.0, np.nan] + [1.0] * 9 + [2.0, 4.0, 6.0, 2.0, 3.0])
    obs = np.array([True, True, False] + [True] * 9 + [True, True, True, True, True])

    rows = MODULE.backtest(y, obs, ["snaive"], origins=("202602",), h=3, months=months)

    assert rows[0]["status"] == "failed"
    assert "缺观测" in rows[0]["reason"]


def test_intermittent_models_reject_training_gaps_instead_of_compressing_time():
    months = [f"2025{m:02d}" for m in range(1, 13)] + ["202601", "202602", "202603", "202604", "202605"]
    y = np.array([2.0] * 12 + [np.nan, 4.0, 6.0, 2.0, 3.0])
    obs = np.array([True] * 12 + [False, True, True, True, True])

    rows = MODULE.backtest(y, obs, ["croston", "sba", "tsb"], origins=("202602",), h=3, months=months)

    assert {r["model"] for r in rows} == {"croston", "sba", "tsb"}
    assert all(r["status"] == "failed" and "训练缺观测" in r["reason"] for r in rows)


def test_selection_compares_models_on_their_common_origin_only():
    per_model = {
        "naive": {"status": "ok", "wape": 0.5, "mae": 5.0, "den": 20.0},
        "croston": {"status": "ok", "wape": 0.0, "mae": 0.0, "den": 10.0},
    }
    rows = [
        {"model": "naive", "origin": "202601", "status": "ok", "test_months": "202602", "n_test": 1,
         "abs_err": 10.0, "sum_abs": 10.0},
        {"model": "naive", "origin": "202602", "status": "ok", "test_months": "202603", "n_test": 1,
         "abs_err": 0.0, "sum_abs": 10.0},
        {"model": "croston", "origin": "202602", "status": "ok", "test_months": "202603", "n_test": 1,
         "abs_err": 0.0, "sum_abs": 10.0},
    ]

    selected = MODULE.select(per_model, "intermittent", rows=rows)

    assert selected["adopted"] == "naive"
    assert selected["baseline"] == "naive"
    assert "共同" in selected["reason"]


def test_regular_fully_observed_series_preserves_existing_forecasts():
    assert MODULE.f_naive(np.array([1.0, 2.0, 3.0]), 2).tolist() == [3.0, 3.0]
    assert MODULE.f_ma3(np.array([1.0, 2.0, 6.0]), 1).tolist() == [3.0]
    assert MODULE.f_snaive(np.arange(1.0, 15.0), 2).tolist() == [3.0, 4.0]
    assert np.isfinite(MODULE.f_ets_ann(np.array([1.0, np.nan, 3.0]), 1)[0])


def test_selftest_zero_error_case_expects_valid_perfect_baseline():
    results = {name: (ok, detail) for name, ok, detail in MODULE.run_selftests()}

    assert results["⑦ 有正销的零误差基线仍有效"][0]
    assert "naive" in results["⑦ 有正销的零误差基线仍有效"][1]


def test_d3_uses_sale_date_as_month_and_retains_source_partition():
    frame = MODULE.pd.DataFrame(
        {
            "month": ["202301", "202302", "202303"],
            "sale_date": ["2022-12-29", "2023-01-02", None],
            "qty": [2, 3, 5],
        }
    )

    normalized, report = MODULE.prepare_order_input(frame)

    assert normalized["month"].iloc[:2].tolist() == ["202212", "202301"]
    assert normalized["source_month"].iloc[:2].tolist() == ["202301", "202302"]
    assert normalized["demand_event_date"].iloc[0].isoformat() == "2022-12-29"
    assert report == {
        "event_date_column": "sale_date",
        "source_month_role": "worksheet_partition_only",
        "rows": 3,
        "month_mismatch_rows": 2,
        "unknown_event_dates": 1,
    }


def test_unknown_event_date_routes_to_conservation_bucket():
    frame = MODULE.pd.DataFrame(
        {
            "demand_event_date": [None, MODULE.pd.Timestamp("2023-01-01").date()],
            "pool": ["美东USNJ", "美东USNJ"],
            "status": ["唯一", "唯一"],
            "in_k_fixed": [True, True],
        }
    )

    assert MODULE.assign_order_bucket(frame).tolist() == ["date_unknown", "mapped"]
