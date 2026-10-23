#!/usr/bin/env python
# -*- coding: utf-8 -*-
"""SC05 calibration gap: nominal service target -> out-of-sample achievable (OFFLINE).

Training-side only. The mapping is estimated by an INNER backtest that sits
entirely before the outer cut (2026-03):

    inner cut    : 2025-09
    inner actuals: 2025-10 .. 2026-03   (all <= outer cut, so no scoring-period data)
    sizing rule  : S = f x (L+R) x (1 + z_tau x CV / sqrt(L+R))   (same rule as production)
    policy       : lost_sales, R=1 month, L=2 months, warm-up L+R

For every nominal target tau in {90, 95, 99}% we report the beta actually achieved
on the inner window, plus the empirical correction from the forecast-error ratio
quantiles (actual / forecast on the inner months). Everything is reported per
universe (scored790 / verifiable239) and per tier (T5* / combo / tree).

This is a diagnostic correction for sizing, not a model-selection verdict and not
a production default. No replenishment quantity; no commit.

Output: out/business_phase/sc05_calibration_gap.json
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

HERE = Path(__file__).resolve()
BP = HERE.parents[2] / "out" / "business_phase"
sys.path.insert(0, str(HERE.parent))
import inventory_policy as ip  # noqa: E402
import sc05_integrate as sc  # noqa: E402
import sc05_equal_investment_r2 as r2  # noqa: E402

INNER_CUT = "2025-09"
INNER_ACTUAL = ["2025-10", "2025-11", "2025-12", "2026-01", "2026-02", "2026-03"]
SHARE_MONTHS = ("2025-07", "2025-08", "2025-09")
LEAD, REVIEW = 2, 1
WARMUP = LEAD + REVIEW
Z = {"0.90": 1.2815515655446004, "0.95": 1.6448536269514722, "0.99": 2.3263478740408408}


def tree_forecasts_inner(series, pairs):
    """Tree at the INNER cut with a short-lag set (lags 12 would empty the frame
    because the inner window is shorter). Disclosed as a limitation."""
    import pandas as pd
    rows = []
    for (s, w) in pairs:
        for m in sorted(x for x in series[(s, w)] if x <= INNER_CUT):
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
                    freq="MS", lags=[1, 2, 3], date_features=["month"])
    fc.fit(df)
    pr = fc.predict(h=3)
    pr["mi"] = pr["ds"].apply(lambda d: d.year * 12 + d.month - 1)
    return {uid: float(g.sort_values("mi")["LGBMRegressor"].mean())
            for uid, g in pr.groupby("unique_id")}


def aggregate(rows):
    td = sum(r["total_demand"] for r in rows)
    tf = sum(r["total_fulfilled"] for r in rows)
    return round(tf / td, 4) if td else None


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

    old_cut = sc.CUT
    sc.CUT = INNER_CUT
    out = {}
    try:
        for universe, pairs in units_by_universe.items():
            tree = tree_forecasts_inner(series, pairs)
            share_den, share_num = defaultdict(float), defaultdict(float)
            for (s, w), bym in series.items():
                share_den[s] += sum(bym.get(m, 0.0) for m in SHARE_MONTHS)
                share_num[(s, w)] = sum(bym.get(m, 0.0) for m in SHARE_MONTHS)
            sku_rate = {}
            for s in {s for s, _ in pairs}:
                bym = defaultdict(float)
                for (ss, w), v in series.items():
                    if ss == s:
                        for m, q in v.items():
                            if m <= INNER_CUT:
                                bym[m] += q
                train = [bym[m] for m in sorted(bym)]
                sku_rate[s] = r2.t5_star_rate(train)[0] if train else 0.0

            per_tau = defaultdict(lambda: defaultdict(list))
            ratios = defaultdict(list)
            for (s, w) in pairs:
                uid = f"{s}|{w}"
                bym = series[(s, w)]
                train = [bym[m] for m in sorted(bym) if m <= INNER_CUT]
                if len(train) < 6:
                    continue      # inner window needs >=6 months; the 239 tier is short-history by design
                mean_tr = statistics.mean(train)
                cv = (statistics.pstdev(train) / mean_tr) if mean_tr > 0 else 0.0
                share = (share_num[(s, w)] / share_den[s]) if share_den[s] > 1e-9 else 0.0
                tiers = dict(
                    T5_star=max(0.0, sku_rate[s] * share),
                    combo=max(0.0, sc.combo_forecast(train)),
                    tree=max(0.0, tree.get(uid, statistics.fmean(train[-3:]))))
                actual = [bym.get(m, 0.0) for m in INNER_ACTUAL]
                for tier, f in tiers.items():
                    if f <= 0:
                        continue
                    for m, a in zip(INNER_ACTUAL, actual):
                        ratios[tier].append(a / f)
                    for tau, z in Z.items():
                        S = f * (LEAD + REVIEW) * (1 + z * cv / (LEAD + REVIEW) ** 0.5)
                        periods = ip.simulate_policy(actual, lead=LEAD, review=REVIEW,
                                                     order_up_to=S, semantics="lost_sales")
                        per_tau[tau][tier].append(ip.metrics(periods[WARMUP:]))

            result = {}
            for tau in Z:
                result[tau] = {tier: aggregate(rows) for tier, rows in per_tau[tau].items()}
            mapping = {}
            for tier in ("T5_star", "combo", "tree"):
                pts = [(float(t), result[t].get(tier)) for t in Z
                       if result[t].get(tier) is not None]
                # nominal target needed to realize 90/95/99 out-of-sample
                need = {}
                for want in (0.90, 0.95, 0.99):
                    hit = next((t for t, b in pts if b >= want), None)
                    need[f"{want:.2f}"] = (hit if hit is not None else ">0.99")
                q = {f"{p:.2f}": round(float(np.quantile(ratios[tier], p)), 4)
                     for p in (0.90, 0.95, 0.99)} if ratios[tier] else {}
                capped = [min(3.0, r) for r in ratios[tier]]
                qc = {f"{p:.2f}": round(float(np.quantile(capped, p)), 4)
                      for p in (0.90, 0.95, 0.99)} if capped else {}
                mapping[tier] = dict(achieved=mapping_pts(pts), required_nominal=need,
                                     ratio_quantiles=q, ratio_quantiles_capped_3x=qc,
                                     suggested_multiplier_capped=qc.get("0.95"))
            out[universe] = dict(units=len(pairs), inner_cut=INNER_CUT,
                                 inner_actual=INNER_ACTUAL, by_nominal=result,
                                 mapping=mapping)
    finally:
        sc.CUT = old_cut

    payload = dict(
        schema_version="sc05_calibration_gap/1",
        method=("training-side inner backtest：inner cut 2025-09，评估 2025-10..2026-03；"
                "同一 sizing 规则与同一 lost_sales 政策；不使用评分期 actual"),
        universes=out,
        recommendation=("名义目标按内层回测映射后使用；若要在样本外实现 95%，"
                        "取映射表中 achieved≥0.95 的最小名义档（或按 ratio 0.95 分位乘 S）"),
        limitations=[
            "只反映内层窗口（2025-10..2026-03）的预测误差结构，不能外推到促销/断货/换品",
            "预测模型或训练窗改变时须重估",
            "内层训练下限取 6 个月（239 档本身是短史档）；短于 6 个月的单元已跳过",
            "239 宇宙的内层树模型用 lags[1,2,3]（lags 12 会让短窗变空帧），与其他档不完全同构",
            "不是选模结论、不是生产默认、不出补货量"],
    )
    (BP / "sc05_calibration_gap.json").write_text(
        json.dumps(payload, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    for u, v in out.items():
        print(json.dumps(dict(universe=u, units=v["units"], by_nominal=v["by_nominal"],
                              mapping={t: dict(achieved=m["achieved"],
                                               need=m["required_nominal"],
                                               q=m["ratio_quantiles"])
                                       for t, m in v["mapping"].items()}),
                         ensure_ascii=False))


def mapping_pts(pts):
    return {t: b for t, b in pts}


if __name__ == "__main__":
    main()
