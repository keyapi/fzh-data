#!/usr/bin/env python
# -*- coding: utf-8 -*-
"""239 verifiable-SKU shadow comparison — executes the registered plan (OFFLINE).

The plan is pre-registered in control/reviews/2026-10-23-monthcell-audit.md §⑤:
  * scope  : 239 SKUs with tier=可验证(>=12) and mapped=yes;
  * methods: naive, ma3, tsb (intermittent candidate only), combo (equal weight);
             seasonal_naive excluded (all series <= 23 usable months, D36);
  * windows: per SKU 6 training months + two NON-overlapping 3-month windows
             (w1 = usable months 7-9, w2 = usable months 10-12);
  * metrics: WAPE / bias / MAE per window, reported SEPARATELY;
  * fallback: algorithm failure -> naive, with a trace; insufficient observation
             must not pass through fallback.

Nothing here is a new design. Results are a SHADOW candidate only: the default
model is not replaced and no order quantity is produced.

Bootstrap: SKU-cluster resampling (>= 2000) for the WAPE delta 95% CI. It covers
the sampling noise of FIXED predictions only — it does NOT include retraining or
model-selection variance (D35).

Outputs (row-level stays local):
  out/business_phase/shadow_239.json
"""
from __future__ import annotations

import csv
import json
from collections import Counter, defaultdict
from pathlib import Path

import numpy as np

BP = Path(__file__).resolve().parents[3] / "out" / "business_phase"
N_BOOT = 2000
SEED = 20261023
METHODS = ["naive", "ma3", "tsb", "combo"]


def wape_bias(sums):
    ae, tot, bias = sums
    if not tot:
        return dict(n=None, wape=None, bias=None)
    return dict(n=None, wape=ae / tot, bias=bias / tot)


def forecast(model, y, h=6):
    """6-step forecast from the single 6-month training block (registered plan).

    w1 takes steps 1-3, w2 takes steps 4-6 — the plan registers ONE 6-month
    training block and two non-overlapping 3-month validation windows, so the
    prediction level is the same in both windows; only the actuals differ.
    """
    if model == "naive":
        return np.repeat(y[-1], h)
    if model == "ma3":
        return np.repeat(float(np.mean(y[-3:])), h)
    if model == "tsb":
        from statsforecast import models as sfm
        m = sfm.TSB(alpha_d=0.3, alpha_p=0.3)
        m.fit(np.asarray(y, dtype=np.float32))
        return np.asarray(m.predict(h=h)["mean"], dtype=float)
    if model == "combo":
        parts = [forecast(m, y, h) for m in ("naive", "ma3", "tsb")]
        return np.mean(np.vstack(parts), axis=0)
    raise ValueError(model)


def main() -> None:
    sku_rows = list(csv.DictReader((BP / "monthcell_sku.csv").open(encoding="utf-8-sig")))
    selected = [r for r in sku_rows
                if r["tier"] == "可验证(>=12)" and r["mapped"] == "yes"]
    cells = defaultdict(list)
    for c in csv.DictReader((BP / "monthcell_cells.csv").open(encoding="utf-8-sig")):
        cells[c["sku"]].append(c)
    for s in cells:
        cells[s].sort(key=lambda c: c["month"])

    excluded = Counter()
    usable = {}
    for r in selected:
        s = r["sku"]
        u = [c for c in cells.get(s, []) if c["state"] != "unknown"]
        if len(u) < 12:
            excluded["usable_lt_12"] += 1
            continue
        usable[s] = u

    # ---- forecasts and per-window errors ------------------------------
    cells_out = []          # (sku, window, method, forecast_sum, actual_sum, abs_err)
    fallbacks = Counter()
    intermittent = {}
    for sku, u in usable.items():
        y = np.array([float(c["qty_observed"] or 0) for c in u])
        train, w1, w2 = y[:6], u[6:9], u[9:12]
        a1 = np.array([float(c["qty_observed"] or 0) for c in w1])
        a2 = np.array([float(c["qty_observed"] or 0) for c in w2])
        nz = train[train > 0]
        zero_share = float((train <= 0).mean())
        adi = len(train) / len(nz) if len(nz) else float("inf")
        intermittent[sku] = bool(zero_share >= 0.4 or adi >= 2.0)
        for m in METHODS:
            try:
                f = forecast(m, train, 6)
            except Exception:
                f = forecast("naive", train, 6)
                fallbacks[m] += 1
            for win, a, off in (("w1", a1, 0), ("w2", a2, 3)):
                k = min(len(a), len(f) - off)
                for j in range(k):
                    fv = float(f[off + j]); av = float(a[j])
                    cells_out.append((sku, win, m, fv, av, abs(fv - av)))

    # ---- metrics per window (common subset = SKUs with every method) --
    by_win_method = defaultdict(lambda: defaultdict(list))
    for sku, win, m, fv, av, ae in cells_out:
        by_win_method[win][m].append((sku, fv, av, ae))

    metrics = {}
    for win in ("w1", "w2"):
        metrics[win] = {}
        for m in METHODS:
            rows = by_win_method[win][m]
            ae = sum(r[3] for r in rows)
            tot = sum(r[2] for r in rows)
            bias = sum(r[1] - r[2] for r in rows)
            metrics[win][m] = dict(cells=len(rows),
                                   wape=(ae / tot if tot else None),
                                   bias=(bias / tot if tot else None),
                                   mae=(ae / len(rows) if rows else None))

    # ---- SKU-cluster bootstrap on WAPE delta --------------------------
    rng = np.random.default_rng(SEED)
    boot = {}
    for win in ("w1", "w2"):
        # per-SKU per-method aggregates
        per = defaultdict(lambda: defaultdict(lambda: [0.0, 0.0, 0.0]))  # ae, tot, bias
        for sku, w, m, fv, av, ae in cells_out:
            if w != win:
                continue
            per[m][sku][0] += ae
            per[m][sku][1] += av
            per[m][sku][2] += fv - av
        skus = sorted({s for m in METHODS for s in per[m]})
        idx = {s: i for i, s in enumerate(skus)}
        arrs = {}
        for m in METHODS:
            ae = np.zeros(len(skus)); tot = np.zeros(len(skus))
            for s, (a_, t_, b_) in per[m].items():
                ae[idx[s]] = a_; tot[idx[s]] = t_
            arrs[m] = (ae, tot)
        samples = {m: np.empty(N_BOOT) for m in METHODS}
        for b in range(N_BOOT):
            counts = np.bincount(rng.integers(0, len(skus), len(skus)),
                                 minlength=len(skus)).astype(float)
            for m in METHODS:
                ae, tot = arrs[m]
                t = float(np.dot(counts, tot))
                samples[m][b] = float(np.dot(counts, ae) / t) if t else np.nan
        boot[win] = {}
        for m in METHODS:
            lo, hi = np.nanpercentile(samples[m], [2.5, 97.5])
            d = samples[m] - samples["naive"]
            dlo, dhi = np.nanpercentile(d, [2.5, 97.5])
            boot[win][m] = dict(wape=metrics[win][m]["wape"],
                                ci95=[float(lo), float(hi)],
                                delta_vs_naive=metrics[win][m]["wape"] - metrics[win]["naive"]["wape"],
                                delta_ci95=[float(dlo), float(dhi)],
                                significant=bool(dlo > 0 or dhi < 0))

    inter_skus = [s for s in usable if intermittent[s]]
    inter_set = set(inter_skus)
    metrics_inter = {}
    for win in ("w1", "w2"):
        metrics_inter[win] = {}
        for m in METHODS:
            rows = [r for r in by_win_method[win][m] if r[0] in inter_set]
            ae = sum(r[3] for r in rows)
            tot = sum(r[2] for r in rows)
            bias = sum(r[1] - r[2] for r in rows)
            metrics_inter[win][m] = dict(cells=len(rows),
                                         wape=(ae / tot if tot else None),
                                         bias=(bias / tot if tot else None),
                                         mae=(ae / len(rows) if rows else None))
    summary = dict(
        schema_version="shadow_239/1",
        registered_plan="control/reviews/2026-10-23-monthcell-audit.md §⑤",
        selected=len(selected), included=len(usable), excluded=dict(excluded),
        reconcile=f"{len(usable)} + {sum(excluded.values())} = {len(usable)+sum(excluded.values())}"
                  f" == {len(selected)}",
        reconcile_ok=(len(usable) + sum(excluded.values()) == len(selected)),
        windows=dict(w1="usable months 7-9", w2="usable months 10-12"),
        methods=METHODS,
        fallbacks=dict(fallbacks),
        intermittent_skus=dict(total=len(inter_skus), of_included=len(usable)),
        metrics=metrics, metrics_intermittent=metrics_inter,
        bootstrap=boot, n_boot=N_BOOT, seed=SEED,
        bootstrap_scope=("SKU 整簇重采样；只覆盖固定预测下的重采样方差，"
                         "不含重训/选模方差（D35）"),
    )
    (BP / "shadow_239.json").write_text(
        json.dumps(summary, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    print(json.dumps(dict(selected=len(selected), included=len(usable),
                          reconcile_ok=summary["reconcile_ok"],
                          fallbacks=dict(fallbacks),
                          intermittent=len(inter_skus),
                          metrics={w: {m: dict(n=v["cells"], wape=round(v["wape"], 4) if v["wape"] else None,
                                               bias=round(v["bias"], 4) if v["bias"] is not None else None,
                                               mae=round(v["mae"], 3) if v["mae"] else None)
                                        for m, v in metrics[w].items()} for w in metrics},
                          boot={w: {m: (round(b["wape"], 4), [round(x, 4) for x in b["delta_ci95"]], b["significant"])
                                    for m, b in boot[w].items()} for w in boot}), ensure_ascii=False))


if __name__ == "__main__":
    main()
