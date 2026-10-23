#!/usr/bin/env python
# -*- coding: utf-8 -*-
"""Hand-computed service-metric assertions for the SC08 policy evaluator.

Every expected value below is computed by hand and asserted to 1e-9.
Definitions follow DECISIONS D40:
  beta  (fill rate) = units fulfilled / units demanded
  alpha (CSL)       = share of DEMAND-BEARING cycles with no stockout
  zero-demand cycles are counted separately and never inflate alpha
  a zero denominator is NOT reported as 100%

Run either way:
  uv run python docs/research/supply-chain/2026-10-20/claude/experiments/business_phase/test_inventory_policy.py
  uv run python -m pytest docs/research/supply-chain/2026-10-20/claude/experiments/business_phase/test_inventory_policy.py -q
"""
from __future__ import annotations

import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))
import inventory_policy as ip  # noqa: E402

TOL = 1e-9


def close(a, b):
    return a is not None and b is not None and abs(a - b) <= TOL


class _Results:
    def __init__(self):
        self.rows = []

    def record(self, name, fnc):
        try:
            fnc()
            self.rows.append(("PASS", name, ""))
        except AssertionError as exc:
            self.rows.append(("FAIL", name, str(exc)))

    def report(self):
        counts = {"PASS": 0, "FAIL": 0}
        for st, name, msg in self.rows:
            counts[st] += 1
            print(f"{st:4s} {name}" + (f"  ← {msg}" if msg else ""))
        print(f"\nsummary: PASS {counts['PASS']} / FAIL {counts['FAIL']} / total {len(self.rows)}")
        return counts


# ---------------------------------------------------------------------------
# 1. single period, deterministic
# ---------------------------------------------------------------------------

def test_single_period_deterministic_full_service():
    p = ip.simulate_flow([10.0], opening=10.0)
    m = ip.metrics(p)
    assert close(m["beta"], 1.0) and close(m["alpha"], 1.0)
    assert close(p[0]["closing"], 0.0) and close(p[0]["lost"], 0.0)


def test_single_period_deterministic_shortage_lost_sales():
    p = ip.simulate_flow([10.0], opening=4.0, semantics="lost_sales")
    m = ip.metrics(p)
    assert close(m["beta"], 0.4), f"beta {m['beta']}"
    assert close(m["alpha"], 0.0)
    assert close(p[0]["lost"], 6.0) and close(p[0]["closing"], 0.0)


# ---------------------------------------------------------------------------
# 2. single period, stochastic with a known distribution
# ---------------------------------------------------------------------------

def test_single_period_stochastic_known_distribution():
    """Demand is 10 or 20 equiprobable; stock 15 in both cycles.
    E[fulfilled] = (10 + 15) / 2 = 12.5 ; E[demand] = 15 -> beta = 25/30.
    alpha = 1 of 2 cycles served = 1/2."""
    p1 = ip.simulate_flow([10.0], opening=15.0)
    p2 = ip.simulate_flow([20.0], opening=15.0)
    fulfilled = p1[0]["fulfilled"] + p2[0]["fulfilled"]
    demand = p1[0]["demand"] + p2[0]["demand"]
    assert close(fulfilled / demand, 25.0 / 30.0)
    assert close(len([p for p in (p1[0], p2[0]) if p["fulfilled"] >= p["demand"]]) / 2, 0.5)


# ---------------------------------------------------------------------------
# 3. two periods, backlog (lost-sales vs backorder)
# ---------------------------------------------------------------------------

def test_two_period_lost_sales_vs_backorder():
    """demand [10, 10], receipts [0, 15], opening 5:
       lost-sales : p1 serves 5 (5 lost), p2 serves 10  -> beta = 15/20 = 0.75
       backorder  : p1 serves 5 (backlog 5), p2 need 15, serves 15 -> beta = 1.0
    """
    lost = ip.metrics(ip.simulate_flow([10.0, 10.0], receipts=[0.0, 15.0],
                                       opening=5.0, semantics="lost_sales"))
    back = ip.metrics(ip.simulate_flow([10.0, 10.0], receipts=[0.0, 15.0],
                                       opening=5.0, semantics="backorder"))
    assert close(lost["beta"], 0.75), f"lost-sales beta {lost['beta']}"
    assert close(back["beta"], 1.0), f"backorder beta {back['beta']}"
    assert close(lost["total_lost"], 5.0)
    assert close(back["total_lost"], 0.0)
    assert close(back["end_backlog"], 0.0)


def test_backorder_does_not_double_count_the_loss():
    """A backlog carried into the next period is served once, not counted again."""
    p = ip.simulate_flow([10.0, 5.0], receipts=[0.0, 20.0], opening=0.0,
                         semantics="backorder")
    m = ip.metrics(p)
    assert close(m["total_fulfilled"], 15.0)
    assert close(m["beta"], 1.0)
    assert close(m["total_lost"], 0.0)


# ---------------------------------------------------------------------------
# 4. zero-demand cycles
# ---------------------------------------------------------------------------

def test_zero_demand_cycle_is_excluded_from_alpha():
    p = ip.simulate_flow([0.0, 10.0], opening=10.0)
    m = ip.metrics(p)
    assert close(m["beta"], 1.0)
    assert m["demand_cycles"] == 1 and m["zero_cycles"] == 1
    assert close(m["alpha"], 1.0), "zero-demand cycle must not be counted in alpha"


def test_zero_denominator_is_not_100_percent():
    m = ip.metrics(ip.simulate_flow([0.0, 0.0], opening=0.0))
    assert m["beta"] is None and m["alpha"] is None, "零分母不得填 100%"


# ---------------------------------------------------------------------------
# 5. beta != alpha, and P90 != fill-rate 90%
# ---------------------------------------------------------------------------

def test_beta_differs_from_alpha_concrete_counterexample():
    """demand 10, stock 8 -> beta = 0.8 but alpha = 0 (the cycle is a stockout)."""
    m = ip.metrics(ip.simulate_flow([10.0], opening=8.0))
    assert close(m["beta"], 0.8)
    assert close(m["alpha"], 0.0)
    assert not close(m["beta"], m["alpha"])


def test_p90_is_not_fill_rate_90():
    """Demand uniform on {0..10}: P90 = 9 (P(D<=9)=10/11=0.909).
    Stocking to P90 gives beta = E[min(D,9)]/E[D] = (54/11)/5 = 54/55 = 0.981818...,
    NOT 0.90."""
    xs = list(range(0, 11))
    import math
    p90 = xs[min(len(xs) - 1, math.ceil(0.9 * (len(xs) - 1)))]
    assert p90 == 9
    e_min = (sum(xs[:10]) + 9.0) / 11.0          # 54/11
    beta = e_min / (sum(xs) / 11.0)              # 54/55
    assert close(beta, 54.0 / 55.0)
    assert not close(beta, 0.90)


# ---------------------------------------------------------------------------
# 6. policy simulator: identity + review/lead behaviour
# ---------------------------------------------------------------------------

def test_policy_identity_and_no_negative_stock():
    demand = [5.0] * 30
    periods = ip.simulate_policy(demand, lead=2, review=1, order_up_to=15.0,
                                 opening=0.0)
    for p in periods:
        assert abs(p["opening"] + p["receipts"] - p["fulfilled"] - p["closing"]) <= TOL
        assert p["closing"] >= -TOL
    m = ip.metrics(periods)
    assert m["beta"] is not None and 0.0 <= m["beta"] <= 1.0


def test_policy_more_stock_never_lowers_fill_rate():
    demand = [5.0, 3.0, 8.0, 2.0, 6.0] * 6
    low = ip.metrics(ip.simulate_policy(demand, lead=2, review=1, order_up_to=10.0))
    high = ip.metrics(ip.simulate_policy(demand, lead=2, review=1, order_up_to=20.0))
    assert high["beta"] >= low["beta"] - TOL


TESTS = [
    test_single_period_deterministic_full_service,
    test_single_period_deterministic_shortage_lost_sales,
    test_single_period_stochastic_known_distribution,
    test_two_period_lost_sales_vs_backorder,
    test_backorder_does_not_double_count_the_loss,
    test_zero_demand_cycle_is_excluded_from_alpha,
    test_zero_denominator_is_not_100_percent,
    test_beta_differs_from_alpha_concrete_counterexample,
    test_p90_is_not_fill_rate_90,
    test_policy_identity_and_no_negative_stock,
    test_policy_more_stock_never_lowers_fill_rate,
]


def main() -> int:
    res = _Results()
    for fnc in TESTS:
        res.record(fnc.__name__, fnc)
    counts = res.report()
    return 0 if counts["FAIL"] == 0 else 1


def test_suite_runs():
    res = _Results()
    for fnc in TESTS:
        res.record(fnc.__name__, fnc)
    counts = res.report()
    assert counts["FAIL"] == 0, f"failures: {counts['FAIL']}"


if __name__ == "__main__":
    sys.exit(main())
