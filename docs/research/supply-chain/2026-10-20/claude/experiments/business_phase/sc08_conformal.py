#!/usr/bin/env python
# -*- coding: utf-8 -*-
"""SC08: empirical / pooled-conformal quantiles instead of normal + CV (OFFLINE).

The previous round showed that a nominal 95% target only realized 0.5439-0.6980
out of sample, because the forecast-error tail is far heavier than the normal
assumption (actual/forecast q95 = 2.0-4.7, q99 = 13-47). This script replaces the
normal-CV sizing rule with a TRAINING-SIDE empirical quantile of the same ratio
distribution, and evaluates it on two windows:

    inner cut 2025-09 : calibration 2025-10..2025-12, inner scoring 2026-01..2026-03
    outer cut 2026-03 : outer scoring 2026-07..2026-09   (evaluated, NEVER tuned)

Sizing rules compared side by side (same policy: lost_sales, R=1 month, L=2
months, warm-up L+R = 3 months):
    CV      : S = f x (L+R) x (1 + z_tau x CV / sqrt(L+R))          (current)
    EMP     : S = f x (L+R) x q_tau                                  (conformal)
    EMP3x   : same as EMP with the ratio winsorised at 3x             (sensitivity)
`q_tau` is pooled across the units of a universe/tier over the CALIBRATION months
only — the scoring-period actuals never enter the multiplier.

No production default is replaced and no replenishment quantity is produced.

Output: out/business_phase/sc08_conformal.json
"""
from __future__ import annotations

import csv
import json
import statistics
import sys
from collections import defaultdict
from pathlib import Path

import duckdb
import numpy as np
import pandas as pd

HERE = Path(__file__).resolve()
BP = HERE.parents[2] / "out" / "business_phase"
sys.path.insert(0, str(HERE.parent))
import inventory_policy as ip  # noqa: E402
import sc05_integrate as sc  # noqa: E402
import sc05_equal_investment_r2 as r2  # noqa: E402

INNER_CUT, OUTER_CUT = "2025-09", "2026-03"
CAL_MONTHS = ["2025-10", "2025-11", "2025-12"]
INNER_EVAL = ["2026-01", "2026-02", "2026-03"]
OUTER_EVAL = ["2026-04", "2026-05", "2026-06", "2026-07", "2026-08", "2026-09"]
LEAD, REVIEW = 2, 1
WARMUP = LEAD + REVIEW
Z = {"0.90": 1.2815515655446004, "0.95": 1.6448536269514722, "0.99": 2.3263478740408408}


def share_window(cut):
    i = int(cut[:4]) * 12 + int(cut[5:7]) - 1
    return [f"{(i - k) // 12:04d}-{(i - k) % 12 + 1:02d}" for k in (3, 2, 1)]


def tree_at(series, pairs, cut, lags):
    rows = []
    for (s, w) in pairs:
        for m in sorted(x for x in series[(s, w)] if x <= cut):
            i = int(m[:4]) * 12 + int(m[5:7]) - 1
            rows.append((f"{s}|{w}", pd.Timestamp(year=i // 12, month=i % 12 + 1, day=1),
                         series[(s, w)][m]))
    df = pd.DataFrame(rows, columns=["unique_id", "ds", "y"])
    df["ds"] = pd.to_datetime(df["ds"])
    df["y"] = df["y"].astype(float)
    from lightgbm import LGBMRegressor
    from mlforecast import MLForecast
    fc = MLForecast(models=LGBMRegressor(n_estimators=200, learning_rate=0.05, num_leaves=31,
                                         verbose=-1, random_state=0),
                    freq="MS", lags=lags, date_features=["month"])
    fc.fit(df)
    pr = fc.predict(h=3)
    pr["mi"] = pr["ds"].apply(lambda d: d.year * 12 + d.month - 1)
    return {uid: float(g.sort_values("mi")["LGBMRegressor"].mean())
            for uid, g in pr.groupby("unique_id")}


def tiers_at(series, pairs, cut, tree):
    sw = share_window(cut)
    share_den, share_num = defaultdict(float), defaultdict(float)
    for (s, w), bym in series.items():
        share_den[s] += sum(bym.get(m, 0.0) for m in sw)
        share_num[(s, w)] = sum(bym.get(m, 0.0) for m in sw)
    sku_rate = {}
    for s in {s for s, _ in pairs}:
        bym = defaultdict(float)
        for (ss, w), v in series.items():
            if ss == s:
                for m, q in v.items():
                    if m <= cut:
                        bym[m] += q
        train = [bym[m] for m in sorted(bym)]
        sku_rate[s] = r2.t5_star_rate(train)[0] if train else 0.0
    out = {}
    for (s, w) in pairs:
        uid = f"{s}|{w}"
        bym = series[(s, w)]
        train = [bym[m] for m in sorted(bym) if m <= cut]
        if len(train) < 6:
            continue
        mean_tr = statistics.mean(train)
        cv = (statistics.pstdev(train) / mean_tr) if mean_tr > 0 else 0.0
        share = (share_num[(s, w)] / share_den[s]) if share_den[s] > 1e-9 else 0.0
        out[uid] = dict(
            cv=cv,
            T5_star=max(0.0, sku_rate[s] * share),
            combo=max(0.0, sc.combo_forecast(train)),
            tree=max(0.0, tree.get(uid, statistics.fmean(train[-3:]))))
    return out


def simulate(units, levels, actual):
    rows = []
    for uid in levels:
        periods = ip.simulate_policy(actual[uid], lead=LEAD, review=REVIEW,
                                     order_up_to=levels[uid], semantics="lost_sales")
        rows.append(dict(unit=uid, **ip.metrics(periods[WARMUP:])))
    return rows


def agg(rows):
    rows = [r for r in rows if r.get("avg_closing") is not None]
    if not rows:
        return dict(units=0, units_with_demand=0, demand_covered_pct=None,
                    beta=None, alpha=None, avg_inventory=None, excess=None)
    td = sum(r["total_demand"] for r in rows)
    tf = sum(r["total_fulfilled"] for r in rows)
    alphas = [r["alpha"] for r in rows if r["alpha"] is not None]
    with_demand = sum(1 for r in rows if r["total_demand"] > 0)
    return dict(units=len(rows), units_with_demand=with_demand,
                demand_covered_pct=round(100 * with_demand / len(rows), 1) if rows else None,
                beta=(round(tf / td, 4) if td else None),
                alpha=(round(statistics.fmean(alphas), 4) if alphas else None),
                avg_inventory=round(statistics.fmean([r["avg_closing"] for r in rows]), 4),
                excess=round(sum(r["excess_exposure"] for r in rows), 2))


def main() -> None:
    units_by_universe = defaultdict(list)
    for r in csv.DictReader((BP / "sc05_units.csv").open(encoding="utf-8-sig")):
        units_by_universe[r["universe"]].append((r["sku"], r["warehouse"]))

    raw = defaultdict(dict)
    con = duckdb.connect(str(sc.DB), read_only=True)
    try:
        for s, w, m, q in con.execute(
                "SELECT sku, warehouse, substr(month,1,7), SUM(qty) FROM monthly_series "
                "GROUP BY 1,2,3").fetchall():
            raw[(s, w)][m] = float(q or 0)
    finally:
        con.close()
    series = {k: sc.reindex_unit(v) for k, v in raw.items()}

    results = {}
    for universe, pairs in units_by_universe.items():
        tree_in = tree_at(series, pairs, INNER_CUT, [1, 2, 3])
        tree_out = tree_at(series, pairs, OUTER_CUT, [1, 2, 3, 6, 12])
        tin = tiers_at(series, pairs, INNER_CUT, tree_in)
        tout = tiers_at(series, pairs, OUTER_CUT, tree_out)

        # the inner policy runs over the full calibration+eval window so that the
        # warm-up (L+R months) is inside the simulation, then scores the last 3
        INNER_FULL = CAL_MONTHS + INNER_EVAL
        actual_inner = {u: [series[tuple(u.split("|"))].get(m, 0.0) for m in INNER_FULL]
                        for u in tin}
        actual_outer = {u: [series[tuple(u.split("|"))].get(m, 0.0) for m in OUTER_EVAL]
                        for u in tout}
        # ratios on the CALIBRATION months only (inner cut, 2025-10..12)
        ratios = defaultdict(list)
        for uid, tt in tin.items():
            bym = series[tuple(uid.split("|"))]
            for m in CAL_MONTHS:
                for tier in ("T5_star", "combo", "tree"):
                    f = tt[tier]
                    if f > 0:
                        ratios[tier].append(bym.get(m, 0.0) / f)

        res = {}
        for tier in ("T5_star", "combo", "tree"):
            q_raw = {tau: float(np.quantile(ratios[tier], float(tau))) for tau in Z}
            q_cap = {tau: float(np.quantile(np.minimum(ratios[tier], 3.0), float(tau)))
                     for tau in Z}
            per = {}
            for tau, z in Z.items():
                def levels(tiers, mult):
                    return {u: max(0.0, t[tier] * (LEAD + REVIEW) * mult) for u, t in tiers.items()}
                cv_in = {u: (t[tier] * (LEAD + REVIEW) *
                             (1 + z * t["cv"] / (LEAD + REVIEW) ** 0.5)) if t[tier] > 0 else 0.0
                         for u, t in tin.items()}
                cv_out = {u: (t[tier] * (LEAD + REVIEW) *
                              (1 + z * t["cv"] / (LEAD + REVIEW) ** 0.5)) if t[tier] > 0 else 0.0
                          for u, t in tout.items()}
                per[tau] = dict(
                    multiplier=dict(conformal_raw=round(q_raw[tau], 4),
                                    conformal_capped3=round(q_cap[tau], 4),
                                    cv_z=round(z, 4)),
                    inner=dict(cv=agg(simulate(tin, cv_in, actual_inner)),
                               conformal=agg(simulate(tin, levels(tin, q_raw[tau]), actual_inner)),
                               conformal_capped3=agg(simulate(tin, levels(tin, q_cap[tau]),
                                                              actual_inner))),
                    outer=dict(cv=agg(simulate(tout, cv_out, actual_outer)),
                               conformal=agg(simulate(tout, levels(tout, q_raw[tau]), actual_outer)),
                               conformal_capped3=agg(simulate(tout, levels(tout, q_cap[tau]),
                                                              actual_outer))))
            res[tier] = dict(ratio_n=len(ratios[tier]), by_tau=per)
        results[universe] = dict(units=len(pairs), calibration=CAL_MONTHS,
                                 inner_eval=INNER_EVAL, outer_eval=OUTER_EVAL[3:],
                                 tiers=res)

    payload = dict(
        schema_version="sc08_conformal/1",
        protocol=("乘数只用内层校准窗 2025-10..12 的『实际/预测』比值（池化到 tier×universe）；"
                  "内层评分 2026-01..03、外层评分 2026-07..09，外层只评不调"),
        policy=dict(lead=LEAD, review=REVIEW, semantics="lost_sales", warmup=WARMUP),
        universes=results,
        limitations=[
            "比值在近零预测上会放大：raw 分位可能给出夸张乘数，capped3 只是敏感性",
            "共形迁移假设误差分布平稳：换模型/重训、促销、断货删失、短史都会破坏",
            "不含重训/选模方差；不替换默认、不出补货量"])
    (BP / "sc08_conformal.json").write_text(
        json.dumps(payload, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    for u, v in results.items():
        print("==", u, v["units"])
        for tier, t in v["tiers"].items():
            for tau, p in t["by_tau"].items():
                print(f"  {tier} tau={tau} mult(raw {p['multiplier']['conformal_raw']:.2f} / "
                      f"cap3 {p['multiplier']['conformal_capped3']:.2f}) "
                      f"inner cv {p['inner']['cv']['beta']} conf {p['inner']['conformal']['beta']} "
                      f"outer cv {p['outer']['cv']['beta']} conf {p['outer']['conformal']['beta']}")


if __name__ == "__main__":
    main()
