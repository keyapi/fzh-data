#!/usr/bin/env python
# -*- coding: utf-8 -*-
"""SC05 equal-investment comparison (OFFLINE) — resolves the "each tier sizes its own stock" confound.

Two contrasts on the SAME frozen units and the SAME policy (R=1 month, L=2 months,
lost-sales, opening = 0):

  (A) same beta target (95%): for every tier, size the order-up-to level S so that
      the tier's own forecast-implied demand distribution reaches beta=95%
      (Monte-Carlo calibration on the forecast, never on the actuals), then score
      against the ACTUAL demand. Answer: at the same nominal service level, which
      tier holds less stock / has less excess?
  (B) same inventory budget: fix the aggregate average inventory at the T5 level
      (12.55 for the 790 universe, 13.54 for the 239 universe, as recorded in the
      previous round), scale each tier's S by one global factor to hit that budget,
      then compare the achieved beta. Answer: with the same capital, who serves more?

Units are read from the frozen list (hashes e977e8311a69c428 / 066150d3bf4fb22d).
Bootstrap: SKU-cluster, 2,000 draws, fixed predictions -> no retrain/selection
variance (stated in the report).

No production access, no replenishment quantity, no commit.
Outputs:
  out/business_phase/sc05_equal_investment.json
"""
from __future__ import annotations

import csv
import hashlib
import json
import statistics
import sys
from collections import defaultdict
from pathlib import Path

import duckdb
import numpy as np

HERE = Path(__file__).resolve()
BP = HERE.parents[2] / "out" / "business_phase"
sys.path.insert(0, str(HERE.parent))
import inventory_policy as ip  # noqa: E402
import sc05_integrate as sc  # noqa: E402  (reuse unit/forecast helpers)

CUT = sc.CUT
ACTUAL = sc.ACTUAL_MONTHS
LEAD, REVIEW = 2, 1
BETA_TARGET = 0.95
BOOT = 2000
SEED = 20261023
T5_INVENTORY_TARGET = dict(scored790=12.55, verifiable239=13.54)


def unit_seed(uid):
    return int(hashlib.sha256(uid.encode("utf-8")).hexdigest()[:8], 16)


def beta_paths(S, paths, lead=LEAD, review=REVIEW):
    """Vectorised monthly order-up-to simulation; returns aggregate beta."""
    n, m = paths.shape
    stock = np.zeros(n)
    backlog = np.zeros(n)
    on_order = np.zeros(n)
    arrivals = np.zeros((n, m + lead + 2))
    fulfilled = np.zeros(n)
    total = np.zeros(n)
    for t in range(m):
        arr = arrivals[:, t]
        stock += arr
        on_order -= arr
        need = paths[:, t] + backlog
        f = np.minimum(need, stock)
        stock -= f
        backlog = need - f
        fulfilled += f
        total += paths[:, t]
        if review > 0 and t % review == review - 1:
            qty = np.maximum(0.0, S - (stock + on_order))
            on_order += qty
            arrivals[:, t + lead] += qty
    return float(fulfilled.sum() / total.sum()) if total.sum() else None


def calibrate_S(forecast_mean, cv, uid, target=BETA_TARGET, paths_n=200, grid=40):
    """Order-up-to level that reaches the beta target on the FORECAST-implied
    demand (forecast mean x noise), never on the actual demand."""
    if forecast_mean <= 0:
        return 0.0
    rng = np.random.default_rng(unit_seed(uid))
    paths = np.maximum(0.0, forecast_mean * (1 + cv * rng.standard_normal((paths_n, len(ACTUAL)))))
    hi = forecast_mean * (LEAD + REVIEW) * 4
    best = hi
    for s in np.linspace(0.0, hi, grid):
        b = beta_paths(s, paths)
        if b is not None and b >= target:
            best = float(s)
            break
    return best


def simulate_units(units, s_levels, actual_by_unit):
    rows = []
    for uid in units:
        s, w = uid.split("|", 1)
        periods = ip.simulate_policy(actual_by_unit[uid], lead=LEAD, review=REVIEW,
                                     order_up_to=s_levels[uid], semantics="lost_sales")
        m = ip.metrics(periods[LEAD + REVIEW:])
        rows.append(dict(unit=uid, **m))
    return rows


def agg(rows):
    td = sum(r["total_demand"] for r in rows)
    tf = sum(r["total_fulfilled"] for r in rows)
    alphas = [r["alpha"] for r in rows if r["alpha"] is not None]
    return dict(units=len(rows), beta=(tf / td if td else None),
                alpha=(statistics.fmean(alphas) if alphas else None),
                avg_inventory=round(statistics.fmean([r["avg_closing"] for r in rows]), 4),
                excess=round(sum(r["excess_exposure"] for r in rows), 2))


def bootstrap(rows_by_tier, n_units):
    rng = np.random.default_rng(SEED)
    draws = [rng.integers(0, n_units, n_units) for _ in range(BOOT)]

    def beta_of(tier, idx):
        sel = [rows_by_tier[tier][i] for i in idx]
        td = sum(r["total_demand"] for r in sel)
        tf = sum(r["total_fulfilled"] for r in sel)
        return tf / td if td else np.nan

    ci, delta = {}, {}
    for t in rows_by_tier:
        arr = np.array([beta_of(t, idx) for idx in draws], dtype=float)
        ci[t] = [round(float(np.nanpercentile(arr, 2.5)), 4),
                 round(float(np.nanpercentile(arr, 97.5)), 4)]
    for t in ("combo", "tree"):
        if t not in rows_by_tier or "T5" not in rows_by_tier:
            continue
        arr = np.array([beta_of(t, idx) - beta_of("T5", idx) for idx in draws], dtype=float)
        lo, hi = float(np.nanpercentile(arr, 2.5)), float(np.nanpercentile(arr, 97.5))
        delta[t] = dict(ci95=[round(lo, 4), round(hi, 4)],
                        significant=bool(lo > 0 or hi < 0))
    return ci, delta


def main() -> None:
    units_by_universe = defaultdict(list)
    hashes = {}
    for r in csv.DictReader((BP / "sc05_units.csv").open(encoding="utf-8-sig")):
        units_by_universe[r["universe"]].append(f"{r['sku']}|{r['warehouse']}")
        hashes[r["universe"]] = r["frozen_hash"]

    raw = defaultdict(dict)
    con = duckdb.connect(str(sc.DB), read_only=True)
    try:
        rows = con.execute("SELECT sku, warehouse, substr(month,1,7), SUM(qty) "
                           "FROM monthly_series GROUP BY 1,2,3").fetchall()
    finally:
        con.close()
    for s, w, m, q in rows:
        raw[(s, w)][m] = float(q or 0)
    series = {k: sc.reindex_unit(v) for k, v in raw.items()}
    repl = {(r["SKU"], r["仓"]): r for r in csv.DictReader(
        (BP / "replenishment_v2.csv").open(encoding="utf-8-sig"))}

    out = {}
    for universe, unit_keys in units_by_universe.items():
        pairs = [tuple(u.split("|", 1)) for u in unit_keys]
        tree = sc.tree_forecasts(series, pairs)
        actual = {u: [series[(u.split("|")[0], u.split("|")[1])].get(m, 0.0)
                      for m in ACTUAL] for u in unit_keys}
        s_A = defaultdict(dict)
        base = {}
        for (s, w), uid in zip(pairs, unit_keys):
            train = [series[(s, w)][m] for m in sorted(series[(s, w)]) if m <= CUT]
            mean_tr = statistics.mean(train)
            cv = (statistics.pstdev(train) / mean_tr) if mean_tr > 0 else 0.0
            t5 = repl.get((s, w), {}).get("新预测等效率(T5)")
            tiers = dict(
                T5=max(0.0, float(t5)) if t5 not in (None, "") else max(0.0, statistics.fmean(train[-3:])),
                combo=max(0.0, sc.combo_forecast(train)),
                tree=max(0.0, tree.get(uid, statistics.fmean(train[-3:]))))
            base[uid] = dict(cv=cv, tiers=tiers)
            for tier, f in tiers.items():
                s_A[tier][uid] = calibrate_S(f, cv, uid)

        # (A) same beta target
        rows_A = {}
        for tier in ("T5", "combo", "tree"):
            rows_A[tier] = simulate_units(unit_keys, s_A[tier], actual)
        summary_A = {t: agg(rows_A[t]) for t in rows_A}
        ci_A, delta_A = bootstrap(rows_A, len(unit_keys))

        # (B) same inventory budget = the T5 average inventory recorded in the
        #     previous round (790: 12.55, 239: 13.54) — the task's fixed number
        target_inv = float(T5_INVENTORY_TARGET[universe])
        rows_B, summary_B, k_used = {}, {}, {}
        for tier in ("T5", "combo", "tree"):
            lo, hi = 0.0, 3.0
            for _ in range(24):
                mid = (lo + hi) / 2
                levels = {u: s_A[tier][u] * mid for u in unit_keys}
                rows_try = simulate_units(unit_keys, levels, actual)
                inv = statistics.fmean([r["avg_closing"] for r in rows_try])
                if inv < target_inv:
                    lo = mid
                else:
                    hi = mid
            k_used[tier] = round((lo + hi) / 2, 4)
            rows_B[tier] = simulate_units(unit_keys,
                                          {u: s_A[tier][u] * ((lo + hi) / 2) for u in unit_keys},
                                          actual)
            summary_B[tier] = agg(rows_B[tier])
        ci_B, delta_B = bootstrap(rows_B, len(unit_keys))

        out[universe] = dict(
            units=len(unit_keys), frozen_hash=hashes[universe],
            policy=dict(lead=LEAD, review=REVIEW, semantics="lost_sales", beta_target=BETA_TARGET,
                        opening=0.0),
            A_same_beta_target=dict(results=summary_A, beta_ci=ci_A, delta_vs_T5=delta_A,
                                    note="S 由各档『预测+历史CV』的蒙特卡洛标定到 β=95%，"
                                         "再用实际需求评分（标定不看实际值）"),
            B_same_inventory_budget=dict(results=summary_B, beta_ci=ci_B, delta_vs_T5=delta_B,
                                         inventory_target=round(target_inv, 4),
                                         t5_A_inventory=round(summary_A["T5"]["avg_inventory"], 4),
                                         scale_k=k_used,
                                         note="把各档 S 统一乘 k，使平均库存等于 T5 在 (A) 的水平"))

    payload = dict(schema_version="sc05_equal_investment/1",
                   bootstrap=dict(resamples=BOOT, seed=SEED, cluster="unit = SKU×仓",
                                  includes_retrain_variance=False,
                                  note="固定预测下的抽样方差；不含重训/选模方差"),
                   universes=out,
                   boundaries=["不替换默认", "不出补货量", "790 与 239 分别报、不外推",
                               "标定不使用实际需求"])
    (BP / "sc05_equal_investment.json").write_text(
        json.dumps(payload, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    for u, v in out.items():
        print(json.dumps(dict(universe=u, units=v["units"],
                              A=v["A_same_beta_target"]["results"],
                              B=v["B_same_inventory_budget"]["results"],
                              budget=v["B_same_inventory_budget"]["inventory_target"],
                              k=v["B_same_inventory_budget"]["scale_k"],
                              deltaA=v["A_same_beta_target"]["delta_vs_T5"],
                              deltaB=v["B_same_inventory_budget"]["delta_vs_T5"]),
                         ensure_ascii=False))


if __name__ == "__main__":
    main()
