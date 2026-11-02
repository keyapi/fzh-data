from datetime import date

import numpy as np

from supply_netting.temporal_demand import (
    available_residuals, choose_model, forecast_cache, nonoverlapping_starts,
    demand_quantiles, calendar_total,
    stratum_key, fast_ets, calibration_pool,
)


def test_calibration_requires_outcome_window_completed():
    rows = [dict(available_at=date(2026, 6, 1), residual=1.0),
            dict(available_at=date(2026, 7, 1), residual=900.0)]
    assert available_residuals(rows, date(2026, 6, 1)) == [1.0]


def test_future_values_cannot_change_earlier_choice_or_prediction():
    funcs = {'naive': lambda y, h: np.repeat(y[-1], h),
             'ma3': lambda y, h: np.repeat(np.mean(y[-3:]), h)}
    a = np.arange(1, 25, dtype=float)
    b = a.copy(); b[15:] = 10000
    ca, cb = forecast_cache(a, funcs), forecast_cache(b, funcs)
    assert choose_model(a, ca, 15) == choose_model(b, cb, 15)
    np.testing.assert_equal(ca[15], cb[15])


def test_zero_error_model_wins_same_validation_windows():
    y = np.ones(20)
    funcs = {'naive': lambda y, h: np.ones(h),
             'ma3': lambda y, h: np.repeat(2., h),
             'sba': lambda y, h: np.repeat(1.5, h)}
    cache = forecast_cache(y, funcs)
    assert choose_model(y, cache, 20)[0] == 'naive'


def test_quantile_unknown_is_not_zero_and_has_single_formula():
    empty = demand_quantiles(10., [], 97)
    assert np.isnan(empty['q95'])
    q = demand_quantiles(10., [1., 2., 3., 4.], 97)
    assert q['q85'] <= q['q90'] <= q['q95']
    assert q['q95'] == 10. + 4. * 97


def test_real_nonoverlap_uses_dates_not_five_month_steps():
    starts = [date(2024, 2, 1), date(2024, 7, 1), date(2024, 8, 1)]
    assert nonoverlapping_starts(starts, 157) == [starts[0], starts[2]]


def test_calendar_total_preserves_month_lengths():
    assert calendar_total([31., 28., 31.], date(2025, 1, 1), 59) == 59.


def test_selection_does_not_use_uncompleted_inner_outcome():
    y = np.arange(1., 25.)
    funcs = {'naive': lambda y, h: np.repeat(y[-1], h)}
    cache = forecast_cache(y, funcs)
    _, info = choose_model(y, cache, 12)
    assert max(info['validation_positions']) < 12


def test_structured_and_saved_stratum_keys_are_identical():
    assert stratum_key(('old', 'finished')) == stratum_key("('old', 'finished')")


def test_fast_ets_preserves_scalar_alpha_search_with_gaps():
    import importlib.util
    from pathlib import Path
    path = Path(__file__).parents[2] / 'scripts/d3b_history_backtest_v3_2_2026-11-02.py'
    spec = importlib.util.spec_from_file_location('d3_ets_reference', path)
    module = importlib.util.module_from_spec(spec); spec.loader.exec_module(module)
    values = np.array([2., 5., np.nan, 0., 8., 3.])
    np.testing.assert_allclose(fast_ets(values, 3), module.f_ets_ann(values, 3))


def test_small_key_samples_use_same_pool_not_noisy_key_quantile():
    assert calibration_pool([1.]*29,[2.]*40) == ([2.]*40,'same_pool_form_uom',40)
    assert calibration_pool([1.]*30,[2.]*40) == ([1.]*30,'key',30)
