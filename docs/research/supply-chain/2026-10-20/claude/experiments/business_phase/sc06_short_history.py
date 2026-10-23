#!/usr/bin/env python
# -*- coding: utf-8 -*-
"""SC06: short-history / intermittent batch — does cross-SKU or category borrowing help? (OFFLINE)

Scope: the 155 mapped "shadow" SKUs (6-11 usable months) and the 87 mapped
"insufficient" SKUs (<6 months); the 57 unmapped SKUs are untouched.

Shadow tier (155): rolling cuts inside each SKU's own history — cut k = 6 months,
plus k = 7 when at least one month remains. Every cut uses ONLY the months before
it; four method families are scored on the SAME (unit, cut) cells against the
months that follow:

    simple   : naive, ma3
    TSB      : intermittent count model
    category : shrinkage of the unit's own level toward its item_group peers,
               peers' levels computed from THEIR first k months only
               (training-window category data, never the full period)
    tree     : MLForecast + LightGBM fitted on all shadow units at the same cut

Insufficient tier (87): an eligibility-gap list (missing usable months / missing
mapping), not a forced run.

Bootstrap: SKU-cluster, 2,000 draws. No default replacement, no quantity, no commit.

Outputs:
  out/business_phase/sc06_short_history.json
  out/business_phase/sc06_gap_list.csv   (local)
"""
from __future__ import annotations

import csv
import hashlib
import json
import statistics
import sys
from collections import Counter, defaultdict
from pathlib import Path

import duckdb
import numpy as np
import pandas as pd

HERE = Path(__file__).resolve()
BP = HERE.parents[2] / "out" / "business_phase"
sys.path.insert(0, str(HERE.parent))
import inventory_policy as ip  # noqa: E402
import sc05_integrate as sc  # noqa: E402

CUTS = (6, 7)
HORIZON = 3
BOOT = 2000
SEED = 20261023
K_SHRINK = 6.0


def load_series():
    con = duckdb.connect(str(sc.DB), read_only=True)
    try:
        rows = con.execute(
            "SELECT sku, warehouse, substr(month,1,7), SUM(qty) FROM monthly_series "
            "GROUP BY 1,2,3").fetchall()
        groups = {r[0]: r[1] for r in con.execute(
            "SELECT item, item_group FROM item_attr").fetchall()}
    finally:
        con.close()
    raw = defaultdict(dict)
    for s, w, m, q in rows:
        raw[(s, w)][m] = float(q or 0)
    return {k: sc.reindex_unit(v) for k, v in raw.items()}, groups


def tsb_forecast(train):
    from statsforecast import models as sfm
    m = sfm.TSB(alpha_d=0.3, alpha_p=0.3)
    m.fit(np.asarray(train, dtype=np.float32))
    return float(m.predict(h=1)["mean"][0])


def tree_predict(series, units, k):
    rows = []
    for (s, w) in units:
        months = sorted(series[(s, w)])[:k]
        for m in months:
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
    pr = fc.predict(h=HORIZON)
    pr["mi"] = pr["ds"].apply(lambda d: d.year * 12 + d.month - 1)
    return {uid: g.sort_values("mi")["LGBMRegressor"].to_numpy(dtype=float)
            for uid, g in pr.groupby("unique_id")}


def main() -> None:
    mc = list(csv.DictReader((BP / "monthcell_sku.csv").open(encoding="utf-8-sig")))
    shadow = [r for r in mc if r["tier"] == "仅影子(6-11)" and r["mapped"] == "yes"]
    insuff = [r for r in mc if r["tier"] == "不足(<6)"]
    dest = {r["sku"]: r for r in json.loads(
        (BP / "destinations.json").read_text(encoding="utf-8"))["rows"]}
    series, groups = load_series()

    def group_of(sku):
        return groups.get(dest.get(sku, {}).get("mapped_item_code"))

    shadow_units = [(r["sku"], w) for r in shadow for w in
                    {w for (s, w) in series if s == r["sku"]}]
    cells = []          # (unit, cut, method, wape, demand)
    fallback = defaultdict(int)
    for k in CUTS:
        units_k = [(s, w) for (s, w) in shadow_units if len(series[(s, w)]) >= k + 1]
        if not units_k:
            continue
        tree = tree_predict(series, units_k, k)
        # category level per (sku, k): mean of peers' first-k-month levels
        cat_level = {}
        for (s, w) in units_k:
            g = group_of(s)
            peers = [statistics.mean(list(series[(p, q)].values())[:k])
                     for (p, q) in units_k if p != s and group_of(p) == g and g]
            cat_level[(s, w)] = statistics.mean(peers) if peers else None
        for (s, w) in units_k:
            uid = f"{s}|{w}"
            bym = series[(s, w)]
            months = sorted(bym)
            train = [bym[m] for m in months[:k]]
            actuals = [bym[m] for m in months[k:k + HORIZON]]
            if not actuals:
                continue
            own = statistics.mean(train)
            cat = cat_level[(s, w)]
            wgt = k / (k + K_SHRINK)
            cat_f = own if cat is None else wgt * own + (1 - wgt) * cat
            methods = dict(
                naive=train[-1],
                ma3=statistics.mean(train[-3:]),
                tsb=tsb_forecast(train),
                category=cat_f,
            )
            tp = tree.get(uid)
            if tp is not None and len(tp):
                methods["tree"] = float(np.mean(tp[:len(actuals)]))
            for m, f in methods.items():
                f = max(0.0, float(f))
                # direct forecast-vs-actual: a flat forecast f serves min(actual, f)
                cells.append(dict(unit=uid, sku=s, cut=k, method=m,
                                  demand=sum(actuals),
                                  fulfilled=sum(min(a, f) for a in actuals)))

    methods = ["naive", "ma3", "tsb", "category", "tree"]
    common = set.intersection(*[{(c["unit"], c["cut"]) for c in cells if c["method"] == m}
                                for m in methods])
    common_cells = [c for c in cells if (c["unit"], c["cut"]) in common]

    def wape_of(method):
        sel = [c for c in common_cells if c["method"] == method]
        td = sum(c["demand"] for c in sel)
        tf = sum(c["fulfilled"] for c in sel)
        return (tf / td if td else None), len(sel)

    summary = {m: dict(wape=round(wape_of(m)[0], 4) if wape_of(m)[0] else None,
                       cells=wape_of(m)[1]) for m in methods}

    # SKU-cluster bootstrap on WAPE differences vs naive
    skus = sorted({c["sku"] for c in common_cells})
    idx_of_sku = {s: i for i, s in enumerate(skus)}
    per = defaultdict(lambda: defaultdict(lambda: [0.0, 0.0]))   # method -> sku -> [ful, dem]
    for c in common_cells:
        a = per[c["method"]][c["sku"]]
        a[0] += c["fulfilled"]
        a[1] += c["demand"]
    rng = np.random.default_rng(SEED)
    draws = [rng.integers(0, len(skus), len(skus)) for _ in range(BOOT)]

    def wape_boot(method, idx):
        f = sum(per[method][skus[i]][0] for i in idx)
        d = sum(per[method][skus[i]][1] for i in idx)
        return f / d if d else np.nan

    ci = {}
    for m in methods:
        arr = np.array([wape_boot(m, idx) for idx in draws], dtype=float)
        ci[m] = [round(float(np.nanpercentile(arr, 2.5)), 4),
                 round(float(np.nanpercentile(arr, 97.5)), 4)]
    delta = {}
    for m in methods:
        if m == "naive":
            continue
        arr = np.array([wape_boot(m, idx) - wape_boot("naive", idx) for idx in draws], dtype=float)
        lo, hi = float(np.nanpercentile(arr, 2.5)), float(np.nanpercentile(arr, 97.5))
        delta[m] = dict(ci95=[round(lo, 4), round(hi, 4)],
                        significant=bool(lo > 0 or hi < 0))

    # ---- 87 tier gap list -------------------------------------------
    gap_rows = []
    for r in insuff:
        n = int(r["usable_months"])
        gap_rows.append(dict(sku_hash=hashlib.sha256(r["sku"].encode()).hexdigest()[:12],
                             sku=r["sku"], mapped=r["mapped"], usable_months=n,
                             months_short=max(0, 6 - n),
                             reason=("未映射：无物料码，无法借力品类" if r["mapped"] == "no"
                                     else f"可用历史仅 {n} 个月（<6）")))
    with (BP / "sc06_gap_list.csv").open("w", encoding="utf-8-sig", newline="") as fh:
        w = csv.DictWriter(fh, fieldnames=list(gap_rows[0].keys()))
        w.writeheader()
        w.writerows(gap_rows)

    payload = dict(
        schema_version="sc06_short_history/1",
        scope=dict(shadow_skus=len(shadow), shadow_units=len(shadow_units),
                   insufficient_skus=len(insuff),
                   insufficient_mapped=sum(1 for r in insuff if r["mapped"] == "yes"),
                   unmapped_untouched=sum(1 for r in mc if r["mapped"] == "no")),
        cuts=list(CUTS), horizon=HORIZON,
        common_cells=len(common), sku_clusters=len(skus),
        methods={m: "见脚本；category 只用同品类 peer 的前 k 月水平" for m in methods},
        wape=summary, beta_ci=ci, delta_wape_vs_naive=delta,
        bootstrap=dict(resamples=BOOT, seed=SEED, unit="SKU 整簇",
                       includes_retrain_variance=False,
                       note="每个切点独立重训（只用切点前信息），CI 仍只覆盖固定预测下的重采样"),
        gap_tier=dict(rows=len(gap_rows),
                      months_short_distribution=dict(
                          Counter(g["months_short"] for g in gap_rows)),
                      unmapped_rows=sum(1 for g in gap_rows if g["mapped"] == "no")),
        boundaries=["239 只用于可验证档结论，不外推到 155/87",
                    "品类借力只用训练窗内品类数据",
                    "不替换默认、不出量"])
    (BP / "sc06_short_history.json").write_text(
        json.dumps(payload, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    print(json.dumps(dict(scope=payload["scope"], common=len(common), skus=len(skus),
                          wape=summary, delta=delta, gap=payload["gap_tier"]),
                     ensure_ascii=False))


if __name__ == "__main__":
    main()
