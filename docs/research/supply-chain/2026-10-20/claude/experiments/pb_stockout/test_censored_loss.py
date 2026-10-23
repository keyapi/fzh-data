#!/usr/bin/env python
# -*- coding: utf-8 -*-
"""Regression tests for the M01 lower-bound loss fix (no third-party deps).

Run:  uv run python docs/research/supply-chain/2026-10-20/claude/experiments/pb_stockout/test_censored_loss.py

Tests
  T1  301's minimal counterexample y=[0,0,10] (third row a lower bound):
      old implementation -> 0.0 ; corrected -> >= raw (3.333333) and far from 0.
  T2  the upper side stays free: y=[10,10,0] with the third row a lower bound of 0
      -> corrected fit equals the fit WITHOUT that row (10.0), no extra penalty.
  T3  penalty function: below the bound costs, at/above it costs nothing.
  T4  no lower-bound rows -> byte-identical to plain ridge.
  T5  same direction holds on the log1p scale actually used by the experiment.
"""
from __future__ import annotations

import sys
from pathlib import Path

import numpy as np

sys.path.insert(0, str(Path(__file__).resolve().parent))

import censored_compare as legacy        # noqa: E402  (old, buggy fit_route)
import censored_r2 as r2                 # noqa: E402

ok = []


def check(name, cond, detail):
    if not cond:
        raise AssertionError(f"{name} FAILED: {detail}")
    ok.append(f"PASS {name}: {detail}")


def t1_counterexample():
    X = np.ones((3, 1))
    y = np.array([0.0, 0.0, 10.0])
    cens = np.array([False, False, True])          # row 3 is a LOWER bound
    raw = float(legacy.fit_ridge(X, y, np.ones(3))[0])
    old = float(legacy.fit_route(y, X, cens, "censored")[0])
    new = float(r2.fit_lower(y, X, cens)[0])
    check("T1.raw", abs(raw - 10.0 / 3.0) < 1e-9, f"raw={raw:.6f} (expect 3.333333)")
    check("T1.old_bug", abs(old) < 1e-9, f"OLD censored={old:.6f} (301 reproduced: collapses to 0)")
    check("T1.new_ge_raw", new >= raw - 1e-9, f"NEW censored={new:.6f} >= raw={raw:.6f}")
    check("T1.new_away_from_zero", new > 1.0, f"NEW censored={new:.6f} (> 1, not 0)")
    check("T1.new_beats_old", new > old + 1.0, f"NEW {new:.6f} > OLD {old:.6f}")
    return dict(raw=round(raw, 6), old=round(old, 6), new=round(new, 6))


def t2_upper_side_free():
    X = np.ones((3, 1))
    y = np.array([10.0, 10.0, 0.0])
    cens = np.array([False, False, True])          # row 3: demand >= 0, so 10 is fine
    raw = float(legacy.fit_ridge(X, y, np.ones(3))[0])
    new = float(r2.fit_lower(y, X, cens)[0])
    check("T2.raw", abs(raw - 20.0 / 3.0) < 1e-9, f"raw={raw:.6f}")
    check("T2.no_extra_penalty", abs(new - 10.0) < 1e-9,
          f"NEW={new:.6f} == fit without the lower-bound row (10.0)")
    check("T2.penalty_zero", r2.lower_bound_penalty(new, 0.0, True) == 0.0,
          f"penalty at pred={new:.6f}, y=0 is 0")
    return dict(raw=round(raw, 6), new=round(new, 6))


def t3_penalty_shape():
    below = r2.lower_bound_penalty(np.array([8.0]), np.array([10.0]), np.array([True]))
    at = r2.lower_bound_penalty(np.array([10.0]), np.array([10.0]), np.array([True]))
    above = r2.lower_bound_penalty(np.array([12.0]), np.array([10.0]), np.array([True]))
    obs = r2.lower_bound_penalty(np.array([8.0]), np.array([10.0]), np.array([False]))
    check("T3.below", abs(below - 4.0) < 1e-12, f"pred=8,y=10 -> {below} (=4)")
    check("T3.at", at == 0.0, f"pred=10,y=10 -> {at} (=0)")
    check("T3.above", above == 0.0, f"pred=12,y=10 -> {above} (=0, upper side free)")
    check("T3.observed", abs(obs - 4.0) < 1e-12, f"uncensored still pays ({obs})")
    return dict(below=below, at=at, above=above)


def t4_no_censored_is_raw():
    rng = np.random.default_rng(7)
    X = rng.normal(size=(24, 4))
    y = rng.normal(size=24)
    a = legacy.fit_ridge(X, y, np.ones(24))
    b = r2.fit_lower(y, X, np.zeros(24, dtype=bool))
    check("T4.identical", np.allclose(a, b, atol=0, rtol=0),
          f"max |diff| = {float(np.max(np.abs(a - b))):.3e}")
    return dict(max_abs_diff=0.0)


def t5_log_scale_direction():
    X = np.ones((3, 1))
    y = np.log1p(np.array([0.0, 0.0, 10.0]))
    cens = np.array([False, False, True])
    raw = float(legacy.fit_ridge(X, y, np.ones(3))[0])
    old = float(legacy.fit_route(y, X, cens, "censored")[0])
    new = float(r2.fit_lower(y, X, cens)[0])
    check("T5.new_ge_raw", new >= raw - 1e-12, f"log1p scale: new={new:.6f} >= raw={raw:.6f}")
    check("T5.new_gt_old", new > old + 1e-6, f"log1p scale: new={new:.6f} > old={old:.6f}")
    return dict(raw=round(raw, 6), old=round(old, 6), new=round(new, 6))


def main() -> int:
    print("== M01 lower-bound loss regression ==")
    t1_counterexample()
    t2_upper_side_free()
    t3_penalty_shape()
    t4_no_censored_is_raw()
    t5_log_scale_direction()
    for line in ok:
        print(line)
    print(f"ALL PASS ({len(ok)} assertions)")
    return 0


if __name__ == "__main__":
    try:
        sys.exit(main())
    except AssertionError as exc:
        print(str(exc))
        sys.exit(1)
