"""Pure chronological model selection and empirical demand quantiles.

All cutoffs are exclusive. Residuals become visible only after their full
outcome window has ended. Empirical intervals are not a service guarantee.
"""
from __future__ import annotations

from datetime import date, timedelta
import math
import ast

import numpy as np

BASELINES = ('naive', 'ma3', 'snaive', 'ets_ann')


def stratum_key(value):
    if isinstance(value, (tuple, list)) and len(value) == 2:
        return tuple(str(x) for x in value)
    try:
        parsed = ast.literal_eval(str(value))
    except (ValueError, SyntaxError):
        parsed = str(value).split('|', 1)
    if not isinstance(parsed, (tuple, list)) or len(parsed) != 2:
        raise ValueError('invalid stratum identity')
    return tuple(str(x) for x in parsed)


def forecast_cache(values, functions, horizon=6, min_observed=3):
    values = np.asarray(values, dtype=float)
    cache = {}
    for cutoff in range(len(values) + 1):
        train = values[:cutoff]
        finite = np.flatnonzero(np.isfinite(train))
        result = {}
        if len(finite) >= min_observed:
            train = train[finite[0]:]  # retain internal calendar gaps
            for name, fn in functions.items():
                try:
                    pred = np.asarray(fn(train.copy(), horizon), dtype=float)
                    if len(pred) == horizon and np.isfinite(pred).all():
                        result[name] = np.maximum(pred, 0.)
                except (ValueError, ArithmeticError, IndexError):
                    continue
        cache[cutoff] = result
    return cache


def choose_model(values, cache, cutoff, lookback=6, min_validation=3, gain=.05):
    """Use only one-step forecasts and outcomes strictly before cutoff."""
    values = np.asarray(values, dtype=float)
    if not 0 <= cutoff <= len(values):
        raise ValueError('cutoff outside history')
    positions = [i for i in range(max(0, cutoff-lookback), cutoff)
                 if np.isfinite(values[i]) and cache.get(i)]
    valid = cache.get(cutoff, {})
    candidates = {name for name in valid
                  if all(name in cache[i] for i in positions)}
    if len(positions) < min_validation or not candidates:
        fallback = next((name for name in ('snaive', 'ets_ann', 'naive', 'ma3')
                         if name in valid), 'none')
        return fallback, dict(basis='insufficient_inner_validation',
                              validation_positions=positions, scores={})
    scores = {name: float(np.mean([abs(values[i]-cache[i][name][0])
                                  for i in positions])) for name in candidates}
    base = [name for name in BASELINES if name in candidates]
    if not base:
        return 'none', dict(basis='no_comparable_baseline',
                            validation_positions=positions, scores=scores)
    best = min(base, key=lambda name: (scores[name], BASELINES.index(name)))
    challengers = [name for name in candidates if name not in BASELINES]
    if challengers:
        challenger = min(challengers, key=lambda name: (scores[name], name))
        # A perfect baseline cannot be improved by a positive-error challenger.
        if scores[best] > 0 and scores[challenger] <= scores[best]*(1-gain):
            best = challenger
    return best, dict(basis='past_common_one_step_validation',
                      validation_positions=positions, scores=scores)


def available_residuals(records, as_of):
    return [float(r['residual']) for r in records
            if r['available_at'] <= as_of and np.isfinite(r['residual'])]


def calibration_pool(own, pooled, min_key=30, min_pool=30):
    if len(own) >= min_key:
        return own, 'key', len(own)
    if len(pooled) >= min_pool:
        return pooled, 'same_pool_form_uom', len(pooled)
    return [], 'none', len(pooled)


def demand_quantiles(point, residuals_daily, days):
    """Single formula used by evaluation, export, and downstream consumption."""
    if not np.isfinite(point) or days <= 0:
        return {f'q{level}': float('nan') for level in (10, 50, 85, 90, 95)}
    residuals = np.asarray(residuals_daily, dtype=float)
    residuals = residuals[np.isfinite(residuals)]
    return {f'q{level}': max(0., float(point + np.quantile(
        residuals, level/100., method='higher')*days)) if len(residuals)
        else float('nan') for level in (10, 50, 85, 90, 95)}


def next_month(start):
    return date(start.year+(start.month == 12), 1 if start.month == 12 else start.month+1, 1)


def calendar_total(monthly_predictions, start, days):
    end, cur, index, total = start+timedelta(days=days), start, 0, 0.
    while cur < end:
        nxt = next_month(cur)
        month_start = date(cur.year, cur.month, 1)
        if index >= len(monthly_predictions):
            raise ValueError('forecast shorter than requested calendar window')
        stop = min(nxt, end)
        total += float(monthly_predictions[index])*(stop-cur).days/(nxt-month_start).days
        cur, index = stop, index+1
    return total


def nonoverlapping_starts(starts, days):
    selected, end = [], date.min
    for start in sorted(set(starts)):
        if start >= end:
            selected.append(start); end = start+timedelta(days=days)
    return selected


def fast_ets(values, horizon, alphas=None):
    """Vectorize the existing ETS(A,N,N) alpha search without dropping months."""
    y = np.asarray(values, dtype=float)
    finite = np.flatnonzero(np.isfinite(y))
    if not len(finite):
        raise ValueError('no observed training values')
    y = y[finite[0]:]
    alphas = np.asarray(alphas if alphas is not None else np.arange(.01, 1., .01))
    levels, losses = np.full(len(alphas), y[0]), np.zeros(len(alphas))
    for value in y[1:]:
        if not np.isfinite(value):
            continue  # skip measurement, retain calendar location
        losses += (value-levels)**2
        levels = alphas*value+(1-alphas)*levels
    return np.repeat(levels[int(np.argmin(losses))], horizon)
