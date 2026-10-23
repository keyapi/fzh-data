#!/usr/bin/env python
# -*- coding: utf-8 -*-
"""Minimal service / inventory policy evaluator (SC08 phase 1, OFFLINE).

Scope (DECISIONS D40):
  * beta (fill rate) is the primary metric, alpha (CSL) secondary;
  * the unit denominator, the effective cycles and the zero-demand cycles are
    reported separately; alpha is NOT computable when no cycle has demand;
  * review is L+R; order-up-to is a REFERENCE policy, not an optimisation;
  * lost-sales or backorder is a single explicit parameter, never mixed;
  * the exploration grid (L = 60/90/120, R = 7/30, beta 90/95/99%) is a
    frontier SAMPLE and is explicitly **not an approved value**;
  * no real SKU, no model input, no replenishment quantity.

Identity enforced on every simulated period:
    opening + receipts - fulfilled = closing

Outputs (local):
  out/business_phase/sc08_frontier.csv
"""
from __future__ import annotations

import csv
import json
from pathlib import Path

BP = Path(__file__).resolve().parents[2] / "out" / "business_phase"


# ---------------------------------------------------------------------------
# Core simulator
# ---------------------------------------------------------------------------

def simulate_flow(demand, receipts=None, opening=0.0, semantics="lost_sales"):
    """Period-by-period flow with EXPLICIT receipts.

    opening + receipts - fulfilled = closing  (asserted)
    lost_sales: unmet demand disappears; backorder: it is carried and served
    later (never counted twice as a new loss).
    """
    if semantics not in ("lost_sales", "backorder"):
        raise ValueError("semantics must be 'lost_sales' or 'backorder'")
    receipts = list(receipts or [0.0] * len(demand))
    periods = []
    stock = float(opening)
    backlog = 0.0
    for t, (d, r) in enumerate(zip(demand, receipts)):
        d, r = float(d), float(r)
        available = stock + r
        need = d + (backlog if semantics == "backorder" else 0.0)
        fulfilled = min(need, available)
        if semantics == "backorder":
            backlog_new = need - fulfilled
            lost = 0.0
        else:
            backlog_new = 0.0
            lost = d - fulfilled
        closing = available - fulfilled
        assert abs((stock + r) - fulfilled - closing) < 1e-9, "conservation broken"
        periods.append(dict(t=t, opening=stock, receipts=r, demand=d, need=need,
                            fulfilled=fulfilled, lost=lost, backlog=backlog_new,
                            closing=closing))
        stock = closing
        backlog = backlog_new
    return periods


def simulate_policy(demand, lead, review, order_up_to, opening=0.0,
                    semantics="lost_sales"):
    """Order-up-to reference policy.

    Orders are placed every `review` periods for `order_up_to - inventory_position`
    and arrive `lead` periods later. This is a REFERENCE, not an optimum.
    """
    n = len(demand)
    arrivals = [0.0] * n
    pipeline = []          # (arrival_index, qty)
    on_order = 0.0
    stock = float(opening)
    backlog = 0.0
    periods = []
    for t, d in enumerate(demand):
        d = float(d)
        for idx, qty in list(pipeline):
            if idx == t:
                arrivals[t] += qty
                on_order -= qty
                pipeline.remove((idx, qty))
        available = stock + arrivals[t]
        need = d + (backlog if semantics == "backorder" else 0.0)
        fulfilled = min(need, available)
        if semantics == "backorder":
            backlog_new = need - fulfilled
            lost = 0.0
        else:
            backlog_new = 0.0
            lost = d - fulfilled
        closing = available - fulfilled
        assert abs((stock + arrivals[t]) - fulfilled - closing) < 1e-9, "conservation broken"
        periods.append(dict(t=t, opening=stock, receipts=arrivals[t], demand=d, need=need,
                            fulfilled=fulfilled, lost=lost, backlog=backlog_new,
                            closing=closing, order=0.0))
        stock = closing
        backlog = backlog_new
        # review at the END of period t (or before t % review == 0)
        if review > 0 and t % review == review - 1:
            position = stock + on_order
            qty = max(0.0, float(order_up_to) - position)
            if qty > 0:
                periods[-1]["order"] = qty
                on_order += qty
                pipeline.append((t + max(1, int(lead)), qty))
    return periods


# ---------------------------------------------------------------------------
# Metrics (D40 definitions)
# ---------------------------------------------------------------------------

def metrics(periods):
    total_demand = sum(p["demand"] for p in periods)
    total_fulfilled = sum(p["fulfilled"] for p in periods)
    total_lost = sum(p["lost"] for p in periods)
    demand_cycles = [p for p in periods if p["demand"] > 0]
    zero_cycles = [p for p in periods if p["demand"] == 0]
    stockout_cycles = [p for p in demand_cycles if p["fulfilled"] < p["demand"] - 1e-12]
    beta = (total_fulfilled / total_demand) if total_demand > 0 else None
    alpha = (1.0 - len(stockout_cycles) / len(demand_cycles)) if demand_cycles else None
    avg_closing = sum(p["closing"] for p in periods) / len(periods) if periods else None
    # excess exposure: closing units beyond the NEXT period's demand
    excess = 0.0
    for i, p in enumerate(periods[:-1]):
        nxt = periods[i + 1]["demand"]
        excess += max(0.0, p["closing"] - nxt)
    return dict(total_demand=total_demand, total_fulfilled=total_fulfilled,
                total_lost=total_lost,
                end_backlog=periods[-1]["backlog"] if periods else 0.0,
                beta=beta, alpha=alpha,
                demand_cycles=len(demand_cycles), zero_cycles=len(zero_cycles),
                stockout_cycles=len(stockout_cycles),
                avg_closing=avg_closing, excess_exposure=excess)


# ---------------------------------------------------------------------------
# Frontier exploration (NOT approved values)
# ---------------------------------------------------------------------------

def synthetic_demand(n=900, mean=5.0, seed=42):
    """Fixed synthetic daily demand (Poisson-like), reproducible; no real SKU."""
    import random
    rng = random.Random(seed)
    out = []
    for t in range(n):
        lam = mean * (1.25 if t % 7 in (5, 6) else 1.0)      # mild weekly shape
        # simple Poisson draw via Knuth (no third-party dependency)
        L, k, p = 2.718281828459045 ** (-lam), 0, 1.0
        while True:
            p *= rng.random()
            if p <= L:
                break
            k += 1
        out.append(float(k))
    return out


def bisect_order_up_to(demand, lead, review, target_beta, semantics="lost_sales",
                       lo=0.0, hi=None, iters=45, warmup=None):
    """Find the order-up-to level whose simulated beta >= target (bisection).

    The first `lead + review` periods are a warm-up (the pipeline is empty at
    t=0) and are discarded from the measured beta.
    """
    warmup = (lead + review) if warmup is None else int(warmup)
    if hi is None:
        hi = max(1.0, sum(demand) / len(demand) * (lead + review) * 4)
    best = hi
    for _ in range(iters):
        mid = (lo + hi) / 2.0
        m = metrics(simulate_policy(demand, lead, review, mid, semantics=semantics)[warmup:])
        beta = m["beta"] or 0.0
        if beta >= target_beta:
            best = mid
            hi = mid
        else:
            lo = mid
    return best


def main() -> None:
    demand = synthetic_demand()
    rows = []
    failures = 0
    for lead in (60, 90, 120):
        for review in (7, 30):
            for target in (0.90, 0.95, 0.99):
                s = bisect_order_up_to(demand, lead, review, target)
                periods = simulate_policy(demand, lead, review, s)
                warmup = lead + review
                for p in periods:
                    try:
                        assert abs(p["opening"] + p["receipts"] - p["fulfilled"]
                                   - p["closing"]) < 1e-9
                    except AssertionError:
                        failures += 1
                m = metrics(periods[warmup:])
                rows.append(dict(lead_days=lead, review_days=review, beta_target=target,
                                 order_up_to=round(s, 3),
                                 beta_achieved=round(m["beta"], 4) if m["beta"] else None,
                                 alpha_achieved=round(m["alpha"], 4) if m["alpha"] else None,
                                 avg_closing=round(m["avg_closing"], 2),
                                 excess_exposure=round(m["excess_exposure"], 1),
                                 demand_cycles=m["demand_cycles"],
                                 zero_cycles=m["zero_cycles"]))

    with (BP / "sc08_frontier.csv").open("w", encoding="utf-8-sig", newline="") as fh:
        w = csv.DictWriter(fh, fieldnames=list(rows[0].keys()))
        w.writeheader()
        w.writerows(rows)
    summary = dict(schema_version="sc08_p1/1", demand_days=len(demand),
                   demand_total=sum(demand), rows=rows, identity_failures=failures,
                   warning="L=60/90/120、R=7/30、beta=90/95/99% 是探索网格，非批准值；"
                           "order-up-to 只是参照政策，不是最优解；未接真实 SKU、未接模型、不出补货量")
    (BP / "sc08_frontier.json").write_text(
        json.dumps(summary, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    print(f"{'L':>4} {'R':>4} {'β目标':>7} {'S':>10} {'β实得':>8} {'α实得':>8} "
          f"{'均库存':>8} {'超额暴露':>9}")
    for r in rows:
        print(f"{r['lead_days']:>4} {r['review_days']:>4} {r['beta_target']:>7.2f} "
              f"{r['order_up_to']:>10.1f} {r['beta_achieved']:>8.4f} "
              f"{(r['alpha_achieved'] if r['alpha_achieved'] is not None else 0):>8.4f} "
              f"{r['avg_closing']:>8.2f} {r['excess_exposure']:>9.1f}")
    print(f"identity_failures={failures}")


if __name__ == "__main__":
    main()
