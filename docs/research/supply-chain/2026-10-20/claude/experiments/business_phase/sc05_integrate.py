#!/usr/bin/env python
# -*- coding: utf-8 -*-
"""SC05: plug the evaluated forecast tiers into the SC08 policy evaluator (OFFLINE).

Same-policy comparison of three FORECAST TIERS on frozen unit sets:

  tiers  : T5 (AutoETS eq-rate, T3 fallback) / combo (naive+ma3+tsb equal weight)
           / tree (MLForecast + LightGBM trained on the same units)
  units  : SKU x warehouse with >=12 months before the cut (2026-03). The 239
           verifiable set and the 790 scored set are DISJOINT (intersection 0),
           so each universe is frozen and run on its own — no merging, no
           extrapolation.
  policy : D40 reference shape — review R=1 month, lead L=2 months, order-up-to,
           beta target 95%; protection L+R = 3 months equals the forecast horizon
           (covered; a longer protection would be marked 未覆盖).
  sizing : one transparent rule for every tier
           S = mean_f x (L+R) x (1 + 1.645 x CV / sqrt(L+R))
           (reference rule, NOT a D40 grid value and NOT a P90 conversion)
  scoring: the fixed policy runs against ACTUAL monthly demand Apr-Sep 2026;
           the L+R warm-up months are excluded.

No production access, no replenishment quantity, no commit.

Outputs (local):
  out/business_phase/sc05_integration.json
  out/business_phase/sc05_units.csv
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
import pandas as pd

HERE = Path(__file__).resolve()
BP = HERE.parents[2] / "out" / "business_phase"
sys.path.insert(0, str(HERE.parent))
import inventory_policy as ip  # noqa: E402

DB = Path("D:/Work/fzh-order-store/order_store.duckdb")
CUT = "2026-03"
ACTUAL_MONTHS = ["2026-04", "2026-05", "2026-06", "2026-07", "2026-08", "2026-09"]
LEAD, REVIEW = 2, 1
BETA_TARGET = 0.95
Z = 1.6448536269514722
BOOT = 2000
SEED = 20261023


def unit_key(s, w):
    return f"{s}|{w}"


def reindex_unit(bym, upto="2026-09"):
    """Make the monthly series contiguous from its first month, filling absent
    months with 0 (absence = no order lines that month, per the monthcell audit)."""
    if not bym:
        return {}
    first = min(bym)
    fi = int(first[:4]) * 12 + int(first[5:7]) - 1
    li = int(upto[:4]) * 12 + int(upto[5:7]) - 1
    out = {}
    for i in range(fi, li + 1):
        m = f"{i // 12:04d}-{i % 12 + 1:02d}"
        out[m] = float(bym.get(m, 0.0))
    return out


def build_units(series, universe):
    return sorted([k for k, bym in series.items()
                   if k[0] in universe and len([m for m in bym if m <= CUT]) >= 12])


def combo_forecast(train):
    from statsforecast import models as sfm
    parts = [float(train[-1]), float(np.mean(train[-3:]))]
    try:
        m = sfm.TSB(alpha_d=0.3, alpha_p=0.3)
        m.fit(np.asarray(train, dtype=np.float32))
        parts.append(float(m.predict(h=1)["mean"][0]))
    except Exception:
        parts.append(float(train[-1]))
    return float(np.mean(parts))


def tree_forecasts(series, units):
    """MLForecast + LightGBM trained on the given units, 3 monthly steps."""
    rows = []
    for (s, w) in units:
        bym = series[(s, w)]
        for m in sorted(x for x in bym if x <= CUT):
            i = int(m[:4]) * 12 + int(m[5:7]) - 1
            rows.append((unit_key(s, w),
                         pd.Timestamp(year=i // 12, month=i % 12 + 1, day=1), bym[m]))
    df = pd.DataFrame(rows, columns=["unique_id", "ds", "y"])
    df["ds"] = pd.to_datetime(df["ds"])
    df["y"] = df["y"].astype(float)
    from lightgbm import LGBMRegressor
    from mlforecast import MLForecast
    fc = MLForecast(models=LGBMRegressor(n_estimators=200, learning_rate=0.05, num_leaves=31,
                                         verbose=-1, random_state=0),
                    freq="MS", lags=[1, 2, 3, 6, 12], date_features=["month"])
    fc.fit(df)
    pr = fc.predict(h=3)
    pr["mi"] = pr["ds"].apply(lambda d: d.year * 12 + d.month - 1)
    out = {}
    for uid, grp in pr.groupby("unique_id"):
        out[uid] = float(grp.sort_values("mi")["LGBMRegressor"].mean())
    return out


def run_universe(name, units, series, repl):
    tree = tree_forecasts(series, units)
    results = defaultdict(list)
    for (s, w) in units:
        bym = series[(s, w)]
        train = [bym[m] for m in sorted(m for m in bym if m <= CUT)]
        actual = [bym.get(m, 0.0) for m in ACTUAL_MONTHS]
        mean_tr = statistics.mean(train)
        cv = (statistics.pstdev(train) / mean_tr) if mean_tr > 0 else 0.0
        uid = unit_key(s, w)
        t5 = repl.get((s, w), {}).get("新预测等效率(T5)")
        tiers = dict(
            T5=float(t5) if t5 not in (None, "") else float(statistics.fmean(train[-3:])),
            combo=combo_forecast(train),
            tree=tree.get(uid, float(statistics.fmean(train[-3:]))),
        )
        def level_for(fmean):
            fmean = max(0.0, float(fmean))
            return (fmean * (LEAD + REVIEW)
                    * (1 + Z * cv / (LEAD + REVIEW) ** 0.5)) if fmean > 0 else 0.0

        for tier, fmean in tiers.items():
            fmean = max(0.0, float(fmean))
            s_level = level_for(fmean)
            periods = ip.simulate_policy(actual, lead=LEAD, review=REVIEW,
                                         order_up_to=s_level, semantics="lost_sales")
            results[tier].append(dict(unit=uid, forecast=fmean, order_up_to=s_level,
                                      **ip.metrics(periods[LEAD + REVIEW:])))

    def agg(rows_):
        td = sum(r["total_demand"] for r in rows_)
        tf = sum(r["total_fulfilled"] for r in rows_)
        alphas = [r["alpha"] for r in rows_ if r["alpha"] is not None]
        return dict(units=len(rows_), beta=(tf / td if td else None),
                    alpha=(statistics.fmean(alphas) if alphas else None),
                    avg_inventory=round(statistics.fmean([r["avg_closing"] for r in rows_]), 4),
                    excess=round(sum(r["excess_exposure"] for r in rows_), 2))

    summary = {t: agg(results[t]) for t in results}

    rng = np.random.default_rng(SEED)
    n = len(units)
    draws = [rng.integers(0, n, n) for _ in range(BOOT)]

    def beta_of(tier, idx):
        sel = [results[tier][i] for i in idx]
        td = sum(r["total_demand"] for r in sel)
        tf = sum(r["total_fulfilled"] for r in sel)
        return tf / td if td else np.nan

    beta_ci = {}
    for tier in ("T5", "combo", "tree"):
        arr = np.array([beta_of(tier, idx) for idx in draws], dtype=float)
        beta_ci[tier] = [round(float(np.nanpercentile(arr, 2.5)), 4),
                         round(float(np.nanpercentile(arr, 97.5)), 4)]
    deltas = {}
    for tier in ("combo", "tree"):
        arr = np.array([beta_of(tier, idx) - beta_of("T5", idx) for idx in draws], dtype=float)
        lo, hi = float(np.nanpercentile(arr, 2.5)), float(np.nanpercentile(arr, 97.5))
        deltas[tier] = dict(delta=round(summary[tier]["beta"] - summary["T5"]["beta"], 4),
                            ci95=[round(lo, 4), round(hi, 4)],
                            significant=bool(lo > 0 or hi < 0))
    unit_hash = hashlib.sha256("\n".join(unit_key(s, w) for s, w in units)
                               .encode()).hexdigest()[:16]
    return dict(name=name, units=len(units), skus=len({s for s, _ in units}),
                hash=unit_hash,
                frozen=[unit_key(s, w) for s, w in units],
                results=summary, beta_ci=beta_ci, delta_vs_T5=deltas)


def main() -> None:
    rout = list(csv.DictReader((BP / "final_bundle_routing.csv").open(encoding="utf-8-sig")))
    scored = {r["SKU"] for r in rout if r["routing_support"].startswith("曾进入")}
    mc = list(csv.DictReader((BP / "monthcell_sku.csv").open(encoding="utf-8-sig")))
    v239 = {r["sku"] for r in mc if r["tier"] == "可验证(>=12)" and r["mapped"] == "yes"}

    con = duckdb.connect(str(DB), read_only=True)
    try:
        rows = con.execute(
            "SELECT sku, warehouse, substr(month,1,7), SUM(qty) FROM monthly_series "
            "GROUP BY 1,2,3").fetchall()
    finally:
        con.close()
    raw_series = defaultdict(dict)
    for s, w, m, q in rows:
        raw_series[(s, w)][m] = float(q or 0)
    series = {k: reindex_unit(v) for k, v in raw_series.items()}

    repl = {(r["SKU"], r["仓"]): r for r in csv.DictReader(
        (BP / "replenishment_v2.csv").open(encoding="utf-8-sig"))}

    universes = dict(scored790=build_units(series, scored),
                     verifiable239=build_units(series, v239))
    runs = {name: run_universe(name, units, series, repl)
            for name, units in universes.items() if units}

    payload = dict(
        schema_version="sc05_integration/2",
        cut=CUT, actual_months=ACTUAL_MONTHS,
        universes={k: dict(units=v["units"], skus=v["skus"], frozen_hash=v["hash"])
                   for k, v in runs.items()},
        intersection_note=("239 与 790 的交集为 0（239 是可验证短史档、790 是已评分档），"
                           "两套单元各自独立运行、分别报覆盖，不合并不外推"),
        policy=dict(lead_months=LEAD, review_months=REVIEW, beta_target=BETA_TARGET,
                    protection_months=LEAD + REVIEW, forecast_horizon_months=3,
                    coverage_note=("L+R = 3 个月 = 预测窗 3 个月，已覆盖；"
                                   "若保护期更长必须标未覆盖"),
                    sizing=("S = mean_f × (L+R) × (1 + 1.645×CV/√(L+R))"
                            "（参照规则，非 D40 网格值）"),
                    semantics="lost_sales"),
        tiers=dict(T5="T5 AutoETS 等效率（T3 回退）",
                   combo="naive+ma3+tsb 等权",
                   tree="MLForecast+LightGBM（同批单元训练）"),
        runs={k: dict(units=v["units"], hash=v["hash"], results=v["results"],
                      beta_ci=v["beta_ci"], delta_vs_T5=v["delta_vs_T5"]) for k, v in runs.items()},
        bootstrap=dict(resamples=BOOT, seed=SEED, cluster="unit = SKU×仓",
                       includes_retrain_variance=False,
                       note="SKU 整簇重采样；模型与预测固定，不含重训方差"),
        boundaries=["不替换任何生产默认", "不出补货量", "不外推到未入选单元",
                    "790 与 239 分别报覆盖"],
    )
    (BP / "sc05_integration.json").write_text(
        json.dumps(payload, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    with (BP / "sc05_units.csv").open("w", encoding="utf-8-sig", newline="") as fh:
        w = csv.DictWriter(fh, fieldnames=["universe", "sku", "warehouse", "frozen_hash"])
        w.writeheader()
        for name, v in runs.items():
            for uid in v["frozen"]:
                s, wh = uid.split("|", 1)
                w.writerow(dict(universe=name, sku=s, warehouse=wh, frozen_hash=v["hash"]))
    for name, v in runs.items():
        print(json.dumps(dict(universe=name, units=v["units"], hash=v["hash"],
                              results=v["results"], beta_ci=v["beta_ci"],
                              delta=v["delta_vs_T5"]),
                         ensure_ascii=False))


if __name__ == "__main__":
    main()
