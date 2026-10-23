#!/usr/bin/env python
# -*- coding: utf-8 -*-
"""SC05 equal-investment R2 (OFFLINE) — time-point fairness, policy consistency,
ex-ante vs ex-post inventory alignment, SKU-cluster bootstrap.

301 (commit 60c352c5) found three majors + one minor; this run fixes them:

  1. TIME POINT — the production T5 rate was built with data through 2026-09
     (and Jul-Sep warehouse shares), while combo/tree trained up to 2026-03, so
     future scoring months leaked into T5. Here every tier is rebuilt at the SAME
     as_of (2026-03): `T5*` re-implements the production method at that cut
     (AutoETS on the SKU series <= 2026-03, MA3 fallback, Jan-Mar warehouse
     shares). The production T5 artifact (as_of 2026-09) is NOT comparable and is
     excluded from the comparison — it is not mixed in.
  2. POLICY — calibration and scoring now use the SAME policy (lost_sales), the
     SAME warm-up (L+R months) and the SAME scored window.
  3. k-INVERSION — the "same actual inventory" run is kept only as an EX-POST
     diagnostic (oracle), never as selection evidence. The ex-ante counterpart
     aligns each tier's FORECAST-implied average inventory (no actuals).
  4. RESAMPLING — bootstrap draws SKUs, not SKU x warehouse rows (all warehouses
     of a drawn SKU share the draw).

D40 protocol split:
  MODEL_ONLY : only the forecast changes; S comes from one fixed rule for every
               tier (no per-tier tuning).
  FULL_FLOW  : the policy is tuned INSIDE each tier (calibrated to beta=95% on
               that tier's forecast) and the whole flow is evaluated outside.

No production access, no replenishment quantity, no commit.
Outputs:
  out/business_phase/sc05_equal_investment_r2.json
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
import sc05_integrate as sc  # noqa: E402

CUT = "2026-03"
SHARE_MONTHS = ("2026-01", "2026-02", "2026-03")
ACTUAL = sc.ACTUAL_MONTHS                 # 2026-04 .. 2026-09
LEAD, REVIEW = 2, 1
WARMUP = LEAD + REVIEW                    # first 3 months are warm-up on BOTH sides
Z = 1.6448536269514722
BETA_TARGET = 0.95
BOOT = 2000
SEED = 20261023


# ---------------------------------------------------------------------------
# Policy simulation (lost_sales, identical in calibration and scoring)
# ---------------------------------------------------------------------------

def beta_paths(S, paths, lead=LEAD, review=REVIEW, warmup=WARMUP):
    """Vectorised monthly order-up-to, LOST-SALES, scored only after warm-up."""
    n, m = paths.shape
    stock = np.zeros(n)
    on_order = np.zeros(n)
    arrivals = np.zeros((n, m + lead + 2))
    fulfilled = np.zeros(n)
    total = np.zeros(n)
    for t in range(m):
        arr = arrivals[:, t]
        stock += arr
        on_order -= arr
        need = paths[:, t]
        f = np.minimum(need, stock)          # lost-sales: no backlog carry
        stock -= f
        if t >= warmup:
            fulfilled += f
            total += need
        if review > 0 and t % review == review - 1:
            qty = np.maximum(0.0, S - (stock + on_order))
            on_order += qty
            arrivals[:, t + lead] += qty
    return float(fulfilled.sum() / total.sum()) if total.sum() else None


def mean_closing_paths(S, paths, lead=LEAD, review=REVIEW, warmup=WARMUP):
    n, m = paths.shape
    stock = np.zeros(n)
    on_order = np.zeros(n)
    arrivals = np.zeros((n, m + lead + 2))
    closes = []
    for t in range(m):
        arr = arrivals[:, t]
        stock += arr
        on_order -= arr
        f = np.minimum(paths[:, t], stock)
        stock -= f
        if t >= warmup:
            closes.append(stock.copy())
        if review > 0 and t % review == review - 1:
            qty = np.maximum(0.0, S - (stock + on_order))
            on_order += qty
            arrivals[:, t + lead] += qty
    return float(np.mean([c.mean() for c in closes])) if closes else 0.0


def calibrate_S(forecast_mean, cv, uid, target=BETA_TARGET, paths_n=200, grid=40):
    """S reaching the beta target on the forecast-implied demand, same policy and
    same warm-up as the evaluation."""
    if forecast_mean <= 0:
        return 0.0
    seed = int(hashlib.sha256(uid.encode()).hexdigest()[:8], 16)
    rng = np.random.default_rng(seed)
    paths = np.maximum(0.0, forecast_mean * (1 + cv * rng.standard_normal((paths_n, len(ACTUAL)))))
    hi = forecast_mean * (LEAD + REVIEW) * 4
    for s in np.linspace(0.0, hi, grid):
        b = beta_paths(s, paths)
        if b is not None and b >= target:
            return float(s)
    return float(hi)


# ---------------------------------------------------------------------------
# Tiers at the same as_of
# ---------------------------------------------------------------------------

def t5_star_rate(train):
    """Re-implementation of the production T5 method AT THE CUT (AutoETS, MA3 fallback)."""
    from statsforecast import models as sfm
    y = np.asarray(train, dtype=np.float32)
    try:
        m = sfm.AutoETS(season_length=12 if len(y) >= 24 else 1)
        m.fit(y)
        f = np.asarray(m.predict(h=3)["mean"], dtype=float)
        return float(np.mean(f)), "AutoETS"
    except Exception:
        return float(np.mean(y[-3:])), "MA3_fallback"


def build_units(series, universe):
    return sorted([k for k, bym in series.items()
                   if k[0] in universe and len([m for m in bym if m <= CUT]) >= 12])


def sku_cluster_bootstrap(sku_of_unit, rows_by_tier, draws=BOOT, seed=SEED):
    skus = sorted(set(sku_of_unit))
    idx_of_sku = defaultdict(list)
    for i, s in enumerate(sku_of_unit):
        idx_of_sku[s].append(i)
    rng = np.random.default_rng(seed)
    sampled = [[i for s in rng.choice(skus, size=len(skus), replace=True)
                for i in idx_of_sku[s]] for _ in range(draws)]

    def beta_of(tier, idx):
        sel = [rows_by_tier[tier][i] for i in idx]
        td = sum(r["total_demand"] for r in sel)
        tf = sum(r["total_fulfilled"] for r in sel)
        return tf / td if td else np.nan

    ci, delta = {}, {}
    for t in rows_by_tier:
        arr = np.array([beta_of(t, idx) for idx in sampled], dtype=float)
        ci[t] = [round(float(np.nanpercentile(arr, 2.5)), 4),
                 round(float(np.nanpercentile(arr, 97.5)), 4)]
    for t in ("combo", "tree", "T5_star"):
        if t == "T5_star" or t not in rows_by_tier or "T5_star" not in rows_by_tier:
            continue
        arr = np.array([beta_of(t, idx) - beta_of("T5_star", idx) for idx in sampled], dtype=float)
        lo, hi = float(np.nanpercentile(arr, 2.5)), float(np.nanpercentile(arr, 97.5))
        delta[t] = dict(ci95=[round(lo, 4), round(hi, 4)],
                        significant=bool(lo > 0 or hi < 0))
    return ci, delta


def agg(rows):
    td = sum(r["total_demand"] for r in rows)
    tf = sum(r["total_fulfilled"] for r in rows)
    alphas = [r["alpha"] for r in rows if r["alpha"] is not None]
    return dict(units=len(rows), beta=(tf / td if td else None),
                alpha=(statistics.fmean(alphas) if alphas else None),
                avg_inventory=round(statistics.fmean([r["avg_closing"] for r in rows]), 4),
                excess=round(sum(r["excess_exposure"] for r in rows), 2))


def simulate(units, levels, actual):
    rows = []
    for uid in units:
        periods = ip.simulate_policy(actual[uid], lead=LEAD, review=REVIEW,
                                     order_up_to=levels[uid], semantics="lost_sales")
        rows.append(dict(unit=uid, **ip.metrics(periods[WARMUP:])))
    return rows


def main() -> None:
    units_by_universe = defaultdict(list)
    hashes = {}
    for r in csv.DictReader((BP / "sc05_units.csv").open(encoding="utf-8-sig")):
        units_by_universe[r["universe"]].append(f"{r['sku']}|{r['warehouse']}")
        hashes[r["universe"]] = r["frozen_hash"]

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

    out = {}
    for universe, keys in units_by_universe.items():
        pairs = [tuple(u.split("|", 1)) for u in keys]
        actual = {u: [series[(u.split("|")[0], u.split("|")[1])].get(m, 0.0) for m in ACTUAL]
                  for u in keys}
        tree = sc.tree_forecasts(series, pairs)
        # Jan-Mar warehouse share per SKU (for the T5* reconstruction)
        share_den, share_num = defaultdict(float), defaultdict(float)
        for (s, w), bym in series.items():
            share_den[s] += sum(bym.get(m, 0.0) for m in SHARE_MONTHS)
            share_num[(s, w)] = sum(bym.get(m, 0.0) for m in SHARE_MONTHS)
        sku_rate = {}
        for s in {s for s, _ in pairs}:
            train = [series[(s, w)][m] for (ss, w) in series if ss == s
                     for m in sorted(series[(s, w)]) if m <= CUT]
            # SKU-level series: sum across warehouses
            bym = defaultdict(float)
            for (ss, w), v in series.items():
                if ss == s:
                    for m, q in v.items():
                        if m <= CUT:
                            bym[m] += q
            train = [bym[m] for m in sorted(bym)]
            sku_rate[s] = t5_star_rate(train)[0] if train else 0.0

        tiers, cv_of = {}, {}
        for (s, w), uid in zip(pairs, keys):
            bym = series[(s, w)]
            train = [bym[m] for m in sorted(bym) if m <= CUT]
            mean_tr = statistics.mean(train)
            cv = (statistics.pstdev(train) / mean_tr) if mean_tr > 0 else 0.0
            share = (share_num[(s, w)] / share_den[s]) if share_den[s] > 1e-9 else 0.0
            t5s = max(0.0, sku_rate[s] * share)
            tiers[uid] = dict(
                T5_star=t5s,
                combo=max(0.0, sc.combo_forecast(train)),
                tree=max(0.0, tree.get(uid, statistics.fmean(train[-3:]))))
            cv_of[uid] = cv

        # ---- MODEL_ONLY: one fixed S rule, only the forecast changes --------
        model_only_levels = {}
        for tier in ("T5_star", "combo", "tree"):
            model_only_levels[tier] = {
                uid: (tiers[uid][tier] * (LEAD + REVIEW)
                      * (1 + Z * cv_of[uid] / (LEAD + REVIEW) ** 0.5))
                if tiers[uid][tier] > 0 else 0.0 for uid in keys}
        rows_mo = {t: simulate(keys, model_only_levels[t], actual) for t in model_only_levels}

        # ---- FULL_FLOW: policy calibrated inside each tier -------------------
        levels_ff = {t: {uid: calibrate_S(tiers[uid][t], cv_of[uid], uid) for uid in keys}
                     for t in ("T5_star", "combo", "tree")}
        rows_ff = {t: simulate(keys, levels_ff[t], actual) for t in levels_ff}

        # ---- ex-ante equal FORECAST-implied inventory (no actuals) ----------
        implied = {}
        for t in levels_ff:
            vals = []
            for uid in keys:
                seed = int(hashlib.sha256(uid.encode()).hexdigest()[:8], 16)
                rng = np.random.default_rng(seed)
                paths = np.maximum(0.0, tiers[uid][t] * (
                    1 + cv_of[uid] * rng.standard_normal((100, len(ACTUAL)))))
                vals.append(mean_closing_paths(levels_ff[t][uid], paths))
            implied[t] = statistics.fmean(vals)
        target = implied["T5_star"]
        rows_ea, k_ea = {}, {}
        for t in levels_ff:
            lo, hi = 0.0, 4.0
            for _ in range(22):
                mid = (lo + hi) / 2
                lv = {uid: levels_ff[t][uid] * mid for uid in keys}
                # bisect on the FORECAST-implied inventory, not the actual one
                vals = []
                for uid in keys:
                    seed = int(hashlib.sha256(uid.encode()).hexdigest()[:8], 16)
                    rng = np.random.default_rng(seed)
                    paths = np.maximum(0.0, tiers[uid][t] * (
                        1 + cv_of[uid] * rng.standard_normal((100, len(ACTUAL)))))
                    vals.append(mean_closing_paths(lv[uid], paths))
                if statistics.fmean(vals) < target:
                    lo = mid
                else:
                    hi = mid
            k_ea[t] = round((lo + hi) / 2, 4)
            rows_ea[t] = simulate(keys, {uid: levels_ff[t][uid] * k_ea[t] for uid in keys}, actual)

        # ---- EX-POST diagnostic (oracle): same ACTUAL inventory -------------
        target_act = statistics.fmean([r["avg_closing"] for r in rows_ff["T5_star"]])
        rows_ex, k_ex = {}, {}
        for t in levels_ff:
            lo, hi = 0.0, 4.0
            for _ in range(22):
                mid = (lo + hi) / 2
                rows_try = simulate(keys, {uid: levels_ff[t][uid] * mid for uid in keys}, actual)
                inv = statistics.fmean([r["avg_closing"] for r in rows_try])
                if inv < target_act:
                    lo = mid
                else:
                    hi = mid
            k_ex[t] = round((lo + hi) / 2, 4)
            rows_ex[t] = simulate(keys, {uid: levels_ff[t][uid] * k_ex[t] for uid in keys}, actual)

        sku_of_unit = [u.split("|")[0] for u in keys]
        out[universe] = dict(
            units=len(keys), sku_clusters=len(set(sku_of_unit)),
            frozen_hash=hashes[universe],
            as_of=CUT, warmup_months=WARMUP, scored_months=len(ACTUAL) - WARMUP,
            tiers_note="三档均在 as_of=2026-03 重建；生产 T5 产物（as_of 2026-09）不可比，已排除",
            MODEL_ONLY=dict(results={t: agg(r) for t, r in rows_mo.items()},
                            method="固定 S 规则，只换预测（D40 MODEL_ONLY）"),
            FULL_FLOW=dict(results={t: agg(r) for t, r in rows_ff.items()},
                           method="政策在档内标定到 β=95%，外层评整个流程（D40 FULL_FLOW）"),
            ex_ante_equal_inventory=dict(results={t: agg(r) for t, r in rows_ea.items()},
                                         k=k_ea, target_implied=round(target, 4),
                                         note="按预测隐含库存对齐（事前），不使用实际需求"),
            ex_post_diagnostic=dict(results={t: agg(r) for t, r in rows_ex.items()},
                                    k=k_ex, target_actual=round(target_act, 4),
                                    note="按实际平均库存对齐——仅事后诊断，不作选模证据"),
            bootstrap=dict(ci_full_flow=sku_cluster_bootstrap(sku_of_unit, rows_ff),
                           ci_model_only=sku_cluster_bootstrap(sku_of_unit, rows_mo),
                           resamples=BOOT, seed=SEED, unit="SKU 整簇（同 SKU 跨仓共享抽样权重）",
                           includes_retrain_variance=False))

    payload = dict(schema_version="sc05_equal_investment/2",
                   protocol="D40：MODEL_ONLY 与 FULL_FLOW 分表，不混成一张",
                   universes=out,
                   retraction=("撤回上一轮『T5 显著最好』的结论：旧比较中 T5 用了 2026-09 信息"
                               "（评分月进入输入），combo/tree 只到 2026-03；本轮按同 as_of 重建后，"
                               "任何跨档差异都只能作为固定单元上的观测，不能当选模结论"),
                   boundaries=["不替换默认", "不出补货量", "790 与 239 分别报、不外推",
                               "不含重训/选模方差"])
    (BP / "sc05_equal_investment_r2.json").write_text(
        json.dumps(payload, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    for u, v in out.items():
        print(json.dumps(dict(universe=u, units=v["units"], skus=v["sku_clusters"],
                              MODEL_ONLY=v["MODEL_ONLY"]["results"],
                              FULL_FLOW=v["FULL_FLOW"]["results"],
                              ex_ante=v["ex_ante_equal_inventory"]["results"],
                              ex_post=v["ex_post_diagnostic"]["results"]),
                         ensure_ascii=False))


if __name__ == "__main__":
    main()
