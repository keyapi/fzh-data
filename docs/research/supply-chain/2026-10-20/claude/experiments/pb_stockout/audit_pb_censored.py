#!/usr/bin/env python
# -*- coding: utf-8 -*-
"""Audit of the PB "raw vs censored-aware" comparison (OFFLINE, READ-ONLY).

This script does NOT modify any artifact committed by e1b9b5d7 / 458642cf.
It re-reads them, re-derives the underlying signal dates from the same offline
sources, and answers the four defects raised by the coordinator:

  1. roster / promotion basis   — 27-SKU list vs the 28-row external cohort,
                                  vendorSKU mapping status, promotion usage;
  2. "14-day merge" != "consecutive stockout days"
                                — observed_signal_days / merged_window_days /
                                  unknown_gap_days, stored separately, no imputation;
  3. "forecast/shipment" is neither a stockout rate nor a backlog gauge
                                — renamed to forecast_above_shipment_ratio, with
                                  both denominators spelled out;
  4. future-restricted-label leakage
                                — point-in-time rebuild per cut date, training vs
                                  evaluation partition compared separately.

Red lines honoured here:
  * DuckDB is opened read_only=True; no writes, no production access.
  * the manual wide table (warehouse_scope != 'source_warehouse') is counted and
    never merged;
  * no daily inventory is fabricated — only observed signal dates and gaps;
  * no imputed demand is used as ground truth;
  * the ridge / IRLS implementation is imported from the committed
    `censored_compare.py` so the numbers are comparable, not re-invented.

Outputs (new files, nothing overwritten):
  out/pb_stockout/stockout_intervals_decomposed.csv
  out/pb_stockout/censored_audit.json
"""
from __future__ import annotations

import argparse
import csv
import hashlib
import json
import re
import sys
import time
from collections import Counter, defaultdict
from datetime import date, timedelta
from pathlib import Path

import duckdb
import numpy as np

HERE = Path(__file__).resolve()
EXP_DIR = HERE.parent
CLAUDE_DIR = HERE.parents[2]
OUT = CLAUDE_DIR / "out" / "pb_stockout"
DB_PATH = Path("D:/Work/fzh-order-store/order_store.duckdb")
PB_ROOT = Path("D:/Work/美国/Tracy Miller/PB orders")
COHORT = Path("D:/Work/fzh-order-store/pb_forecast_cohort.json")

sys.path.insert(0, str(EXP_DIR))
import censored_compare as cc          # noqa: E402  (reuse fit_route/design/is_restricted)

LOW_THRESHOLD = 3.0
MERGE_DAYS = 14
OVER_RATIO = cc.OVER_RATIO


# --------------------------------------------------------------------------- #
# helpers
# --------------------------------------------------------------------------- #
def parse_date_from_name(name: str):
    m = re.search(r"(20\d{2})(\d{2})(\d{2})", name)
    if m:
        try:
            return date(int(m.group(1)), int(m.group(2)), int(m.group(3)))
        except ValueError:
            return None
    return None


def status_of(total):
    if total is None:
        return "unknown"
    if total <= 0:
        return "nonpositive"
    if total <= LOW_THRESHOLD:
        return "low_1_3"
    return "positive"


def runs_of(dates, merge_days=MERGE_DAYS):
    runs, cur = [], []
    for d in sorted(dates):
        if cur and (d - cur[-1]).days <= merge_days:
            cur.append(d)
            continue
        if cur:
            runs.append(cur)
        cur = [d]
    if cur:
        runs.append(cur)
    return runs


def month_end(ym: str) -> date:
    _, me = cc.month_span(ym)
    return me - timedelta(days=1)


# --------------------------------------------------------------------------- #
# source loading (identical rules to pb_cross_source.py)
# --------------------------------------------------------------------------- #
def load_wx(db: str):
    """Return (dates, sku->date->total, wide row count). Source warehouse only."""
    con = duckdb.connect(db, read_only=True)
    try:
        rows = con.execute("""
            SELECT snapshot_date, sku, available, warehouse_scope
            FROM wx_inventory.canonical""").fetchall()
    finally:
        con.close()
    wx, dates, wide = defaultdict(dict), set(), 0
    for d_, sku, avail, scope in rows:
        if scope != "source_warehouse":
            wide += 1
            continue
        dates.add(d_)
        wx[sku][d_] = wx[sku].get(d_, 0.0) + float(avail or 0)
    return sorted(dates), wx, wide


def load_events(pb_root: Path):
    files = [p for p in pb_root.rglob("*")
             if p.is_file() and not p.name.startswith("~$")
             and "checked0stock" in p.name.lower()
             and p.suffix.lower() == ".csv"]
    by_hash = {}
    for p in files:
        by_hash.setdefault(hashlib.sha256(p.read_bytes()).hexdigest(), p)
    events, wedge = defaultdict(set), set()
    for p in by_hash.values():
        ev_date = parse_date_from_name(p.name)
        try:
            rs = list(csv.DictReader(p.open(encoding="utf-8-sig", errors="replace")))
        except Exception:
            continue
        for r in rs:
            style = (r.get("Vendor Style") or "").strip()
            if not style:
                continue
            desc = (r.get("Product/Item Description") or "").strip()
            if desc and "Wedge Pillow" in desc:
                wedge.add(style.upper())
            if ev_date:
                events[style.upper()].add(ev_date)
    export_dates = {d for v in events.values() for d in v}
    return len(files), len(by_hash), events, wedge, export_dates


def load_sales(db: str, end="2026-09-30"):
    con = duckdb.connect(db, read_only=True)
    try:
        rows = con.execute("""
            SELECT sku_tongtool, substr(despatch_date,1,7), SUM(qty)
            FROM gs_orders WHERE channel='PotteryBarn' AND despatch_date <= ?
            GROUP BY 1,2""", [end]).fetchall()
        tot = con.execute("""
            SELECT sku_tongtool, SUM(qty) FROM gs_orders WHERE channel='PotteryBarn'
            GROUP BY 1""").fetchall()
        pairs = con.execute("""
            SELECT DISTINCT upper(platform_sku), sku_tongtool
            FROM gs_orders WHERE channel='PotteryBarn'""").fetchall()
    finally:
        con.close()
    series = defaultdict(dict)
    for sku, ym, q in rows:
        series[sku][ym] = float(q or 0)
    return series, {s: float(q or 0) for s, q in tot}, pairs


# --------------------------------------------------------------------------- #
def main() -> None:
    t0 = time.time()
    ap = argparse.ArgumentParser()
    ap.add_argument("--db", default=str(DB_PATH))
    ap.add_argument("--pb-root", default=str(PB_ROOT))
    ap.add_argument("--cohort", default=str(COHORT))
    ap.add_argument("--intervals", default=str(OUT / "stockout_intervals.csv"))
    ap.add_argument("--list", default=str(OUT / "pb_30sku_list.csv"))
    args = ap.parse_args()

    wx_dates, wx, wide_rows = load_wx(args.db)
    n_files, n_uniq, events, wedge, export_dates = load_events(Path(args.pb_root))
    export_in_window = sorted(d for d in export_dates if wx_dates[0] <= d <= wx_dates[-1])
    series, sales_total, pb_pairs = load_sales(args.db)
    cohort = json.loads(Path(args.cohort).read_text(encoding="utf-8"))

    with Path(args.list).open(encoding="utf-8-sig", newline="") as fh:
        roster = list(csv.DictReader(fh))
    roster_skus = [r["sku"] for r in roster]

    with Path(args.intervals).open(encoding="utf-8-sig", newline="") as fh:
        committed_rows = list(csv.DictReader(fh))

    # ---------------------------------------------------------------- signals
    def signals(upper_sku, sku, cut=None):
        """Signal dates observable with knowledge up to `cut` (None = full period)."""
        hi = wx_dates[-1] if cut is None else min(cut, wx_dates[-1])
        sig = {d for d in events.get(upper_sku, ()) if wx_dates[0] <= d <= hi}
        for d in wx_dates:
            if d > hi:
                continue
            if status_of(wx.get(sku, {}).get(d)) in ("nonpositive", "low_1_3"):
                sig.add(d)
        return sorted(sig)

    # ------------------------------------------------- defect 2: decomposition
    rebuilt, mismatches = [], []
    for r in roster:
        sku, up = r["sku"], r["sku"].upper()
        sig = signals(up, sku)
        for run in runs_of(sig):
            start, end = run[0], run[-1]
            span_days = (end - start).days                     # legacy convention
            observed_signal_days = len(set(run))
            unknown_gap = (end - start).days + 1 - observed_signal_days
            gap_no_obs = gap_pos_snap = 0
            for i in range((end - start).days + 1):
                d = start + timedelta(days=i)
                if d in run:
                    continue
                st = status_of(wx.get(sku, {}).get(d))
                if st == "positive":
                    gap_pos_snap += 1
                else:
                    gap_no_obs += 1
            opp = [d for d in export_in_window if start <= d <= end]
            opp_no_signal = sum(1 for d in opp if d not in run)
            rebuilt.append(dict(
                sku=sku, start=start.isoformat(), end=end.isoformat(),
                observed_signal_days=observed_signal_days,
                merged_window_days=span_days,
                unknown_gap_days=unknown_gap,
                gap_days_with_positive_snapshot=gap_pos_snap,
                gap_days_without_any_observation=gap_no_obs,
                export_dates_in_window=len(opp),
                export_dates_without_signal=opp_no_signal,
                signals_in_run=len(run),
                legacy_days_observed=span_days,
                note=("unknown_gap_days = 窗口内无信号日数（不插值）；"
                      "export_dates_in_window = 窗口内 checked0stock 导出日（可观测机会）；"
                      "merged_window_days 沿用旧口径 (end-start).days，便于对账"),
            ))

    # reconcile against the committed intervals CSV (sku,start,end,signals_in_run)
    def key(row):
        return (row["sku"], row["start"], row["end"], int(row["signals_in_run"]))

    committed_keys = Counter(key(r) for r in committed_rows)
    rebuilt_keys = Counter(key(r) for r in rebuilt)
    for k in sorted(set(committed_keys) | set(rebuilt_keys)):
        if committed_keys.get(k) != rebuilt_keys.get(k):
            mismatches.append(dict(row=k, committed=committed_keys.get(k, 0),
                                   rebuilt=rebuilt_keys.get(k, 0)))

    fields = ["sku", "start", "end", "observed_signal_days", "merged_window_days",
              "unknown_gap_days", "gap_days_with_positive_snapshot",
              "gap_days_without_any_observation", "export_dates_in_window",
              "export_dates_without_signal", "signals_in_run", "legacy_days_observed", "note"]
    with (OUT / "stockout_intervals_decomposed.csv").open("w", encoding="utf-8-sig", newline="") as fh:
        w = csv.DictWriter(fh, fieldnames=fields)
        w.writeheader()
        w.writerows(rebuilt)

    # ------------------------------------------------- defect 1: roster vs cohort
    cohort_rows = cohort["rows"]
    cohort_skus = {r["vendor_sku"] for r in cohort_rows}
    roster_set = set(roster_skus)
    vendor_to_tong = defaultdict(set)
    for psk, tong in pb_pairs:
        vendor_to_tong[psk].add(tong)

    def mapping_status(vendor_sku):
        tongs = vendor_to_tong.get(vendor_sku.upper(), set())
        if vendor_sku in series and vendor_sku.upper() in vendor_to_tong:
            return "proven_exact_string" if tongs == {vendor_sku} else "conflict"
        if tongs:
            return "conflict" if vendor_sku not in tongs else "proven_exact_string"
        return "mapping_unproven_no_sales_record"

    cohort_cmp = []
    for r in cohort_rows:
        v = r["vendor_sku"]
        cohort_cmp.append(dict(
            vendor_sku=v, pb_sku=r["pb_sku"], description=r["description"],
            in_roster=v in roster_set,
            in_gs_sales=(v in series),
            pb_sales_qty=sales_total.get(v),
            mapping_vendor_to_tongtool=mapping_status(v),
            mapping_pb_sku_to_vendor="mapping_unproven (无本地表含 PB 数字 SKU)",
        ))
    roster_extra = [s for s in roster_skus if s not in cohort_skus]
    cohort_missing = [r["vendor_sku"] for r in cohort_rows if r["vendor_sku"] not in roster_set]

    # ------------------------------------------------ defect 4: point-in-time
    origins = cc.ORIGINS
    last_i = cc.ym_i("2026-09")
    # the committed comparison scores roster SKUs that carry at least one interval;
    # keep the identical scope so the numbers are comparable (the leftovers are listed)
    iv_full = cc.read_intervals(Path(args.intervals))
    skus = sorted(set(iv_full) & set(series))
    excluded_no_interval = [s for s in roster_skus if s not in set(iv_full)]
    unscored = []
    train_label_mismatch = []
    pit_label_rows = []

    # intervals_used_by_committed_code (full period) — reuse exactly what cc reads

    for sku in skus:
        by = series[sku]
        first = min(cc.ym_i(m) for m in by)
        months = [cc.i_ym(i) for i in range(first, last_i + 1)]
        up = sku.upper()
        for origin in origins:
            cut = month_end(origin)
            iv_pit = {sku: [(run[0], run[-1]) for run in runs_of(signals(up, sku, cut))]}
            tr = cc.ym_i(origin) - first + 1
            if tr < cc.MIN_TRAIN:
                unscored.append(dict(sku=sku, origin=origin, reason="history_lt_min_train"))
                continue
            for m in months[:tr]:
                full = cc.is_restricted(sku, m, iv_full)
                pit = cc.is_restricted(sku, m, iv_pit)
                if full != pit:
                    train_label_mismatch.append(dict(sku=sku, origin=origin, month=m,
                                                     full_label=full, pit_label=pit))
            for m in months[tr:]:
                if cc.ym_i(m) > last_i:
                    continue
                pit_label_rows.append(dict(
                    sku=sku, origin=origin, month=m,
                    knowable_at_cut=cc.ym_i(m) <= cc.ym_i(origin),
                    full_restricted=cc.is_restricted(sku, m, iv_full),
                    pit_restricted=(cc.is_restricted(sku, m, iv_pit)
                                    if cc.ym_i(m) <= cc.ym_i(origin) else None)))

    # --------------------------------------------- metrics (renamed) + partitions
    def wape_bias(cells):
        if not cells:
            return dict(n=0, wape=None, bias=None, actual_sum=0.0)
        ae = sum(abs(c["forecast"] - c["actual"]) for c in cells)
        tot = sum(c["actual"] for c in cells)
        bias = sum(c["forecast"] - c["actual"] for c in cells)
        return dict(n=len(cells), wape=(ae / tot if tot else None),
                    bias=(bias / tot if tot else None), actual_sum=round(tot, 3))

    def above_shipment(cells):
        """forecast > actual * 1.2. Two denominators spelled out."""
        observed = [c for c in cells if c["actual"] > 0]
        over = [c for c in observed if c["forecast"] > c["actual"] * OVER_RATIO]
        return dict(
            cells=len(cells),
            cells_with_actual_zero=len(cells) - len(observed),
            denominator_all_cells=len(cells),
            denominator_observed_cells=len(observed),
            over=len(over),
            ratio_over_all_cells=(len(over) / len(cells) if cells else None),
            ratio_over_observed_cells=(len(over) / len(observed) if observed else None),
        )

    def ratio_dist(cells):
        ratios = [c["forecast"] / c["actual"] for c in cells if c["actual"] > 0]
        if not ratios:
            return dict(n=0, median=None, share_above_1_2=None)
        arr = np.array(ratios)
        return dict(n=len(ratios), median=round(float(np.median(arr)), 4),
                    share_above_1_2=round(float((arr > OVER_RATIO).mean()), 4))

    cells_by_route = {r: [] for r in ("raw", "censored")}
    for sku in skus:
        by = series[sku]
        first = min(cc.ym_i(m) for m in by)
        months = [cc.i_ym(i) for i in range(first, last_i + 1)]
        y = np.array([by.get(m, 0.0) for m in months], dtype=float)
        for origin in origins:
            tr = cc.ym_i(origin) - first + 1
            if tr < cc.MIN_TRAIN:
                continue
            train_months = months[:tr]
            cens = np.array([cc.is_restricted(sku, m, iv_full) for m in train_months], dtype=bool)
            X = cc.design([cc.ym_i(m) for m in train_months],
                          [int(m[5:7]) for m in train_months], first)
            ylog = np.log1p(y[:tr])
            tgt = [cc.i_ym(cc.ym_i(origin) + 1 + k) for k in range(cc.HORIZON)]
            tgt = [m for m in tgt if cc.ym_i(m) <= last_i]
            Xf = cc.design([cc.ym_i(m) for m in tgt], [int(m[5:7]) for m in tgt], first)
            cut = month_end(origin)
            iv_pit = {sku: [(run[0], run[-1]) for run in runs_of(signals(sku.upper(), sku, cut))]}
            for route in ("raw", "censored"):
                beta = cc.fit_route(ylog, X, cens, route)
                f = np.maximum(0.0, np.expm1(Xf @ beta))
                for m, fv in zip(tgt, f):
                    knowable = cc.ym_i(m) <= cc.ym_i(origin)
                    cells_by_route[route].append(dict(
                        sku=sku, origin=origin, month=m,
                        forecast=round(float(fv), 6),
                        actual=round(float(by.get(m, 0.0)), 6),
                        restricted_full=cc.is_restricted(sku, m, iv_full),
                        restricted_pit=(cc.is_restricted(sku, m, iv_pit) if knowable else False),
                        restricted_knowable_at_cut=knowable,
                    ))

    metrics = {}
    for route, cells in cells_by_route.items():
        non_full = [c for c in cells if not c["restricted_full"]]
        res_full = [c for c in cells if c["restricted_full"]]
        non_pit = [c for c in cells if not c["restricted_pit"]]
        res_pit = [c for c in cells if c["restricted_pit"]]
        metrics[route] = dict(
            wape_bias_non_restricted_full_period=wape_bias(non_full),
            wape_bias_all_cells_point_in_time=wape_bias(non_pit),
            forecast_above_shipment_ratio_full_period=above_shipment(res_full),
            forecast_above_shipment_ratio_point_in_time=above_shipment(res_pit),
            forecast_to_shipment_ratio_non_restricted=ratio_dist(non_full),
            forecast_to_shipment_ratio_all_observed=ratio_dist(
                [c for c in cells if c["actual"] > 0]),
        )

    # ------------------------------------------------ clustered bootstrap (no new deps)
    BOOT = 2000
    rng = np.random.default_rng(20261023)

    def stat_wape(cells):
        tot = sum(c["actual"] for c in cells)
        if not cells or not tot:
            return None
        return sum(abs(c["forecast"] - c["actual"]) for c in cells) / tot

    def stat_share_above(cells):
        obs = [c for c in cells if c["actual"] > 0]
        if not obs:
            return None
        return sum(1 for c in obs if c["forecast"] > c["actual"] * OVER_RATIO) / len(obs)

    def boot_delta(cells_by_sku, stat, b=BOOT):
        """Resample whole SKUs with replacement (cluster bootstrap on the SKU)."""
        skus_u = sorted(cells_by_sku)
        if not skus_u:
            return None
        raw_all = [c for s in skus_u for c in cells_by_sku[s]["raw"]]
        cen_all = [c for s in skus_u for c in cells_by_sku[s]["censored"]]
        point = stat(cen_all) - stat(raw_all)
        deltas, raws, cens = [], [], []
        for _ in range(b):
            pick = rng.integers(0, len(skus_u), size=len(skus_u))
            r = [c for i in pick for c in cells_by_sku[skus_u[i]]["raw"]]
            k = [c for i in pick for c in cells_by_sku[skus_u[i]]["censored"]]
            rv, cv = stat(r), stat(k)
            if rv is None or cv is None:
                continue
            raws.append(rv)
            cens.append(cv)
            deltas.append(cv - rv)
        if not deltas:
            return None
        q = lambda a, p: round(float(np.quantile(a, p)), 4)          # noqa: E731
        return dict(delta_point=round(point, 4),
                    delta_ci95=[q(deltas, 0.025), q(deltas, 0.975)],
                    raw_median=round(float(np.median(raws)), 4),
                    censored_median=round(float(np.median(cens)), 4),
                    excludes_zero=bool(q(deltas, 0.025) * q(deltas, 0.975) > 0),
                    bootstrap=b, skus=len(skus_u))

    by_sku_cells = {s: {r: [c for c in cells_by_route[r] if c["sku"] == s]
                        for r in ("raw", "censored")} for s in skus}
    # ① excluded-cells partition (as committed) vs all-cells (point-in-time safe)
    boot_non = {s: {r: [c for c in by_sku_cells[s][r] if not c["restricted_full"]]
                    for r in ("raw", "censored")} for s in skus}
    boot_all = by_sku_cells
    boot_obs = {s: {r: [c for c in by_sku_cells[s][r] if c["actual"] > 0]
                    for r in ("raw", "censored")} for s in skus}

    bootstrap = dict(
        wape_non_restricted_132=boot_delta(boot_non, stat_wape),
        wape_all_cells_208=boot_delta(boot_all, stat_wape),
        forecast_above_shipment_ratio_all_observed_202=boot_delta(boot_obs, stat_share_above),
        note=("按 SKU 整簇重采样（cluster bootstrap），2000 次，seed 20261023；"
              "delta = censored − raw；excludes_zero = 95% CI 不含 0"),
    )

    # ---------------------------------------------- promotion windows vs months
    promo = [(date.fromisoformat(e["start"]), date.fromisoformat(e["end_inclusive"]))
             for e in cohort.get("events", [])]
    promo_train_rows = 0
    promo_train_detail = Counter()
    promo_target_rows = 0
    for route_cells in cells_by_route.values():
        for c in route_cells:
            ms, me = cc.month_span(c["month"])
            if any(a < me and b >= ms for a, b in promo):
                promo_target_rows += 1
        break
    for sku in skus:
        by = series[sku]
        first = min(cc.ym_i(m) for m in by)
        months = [cc.i_ym(i) for i in range(first, last_i + 1)]
        for origin in origins:
            tr = cc.ym_i(origin) - first + 1
            if tr < cc.MIN_TRAIN:
                continue
            for m in months[:tr]:
                ms, me = cc.month_span(m)
                if any(a < me and b >= ms for a, b in promo):
                    promo_train_rows += 1
                    promo_train_detail[m] += 1

    # ------------------------------------------------------------- reconciliation
    recon = dict(
        roster_skus=len(roster_skus),
        roster_skus_with_interval=len({r["sku"] for r in rebuilt}),
        roster_skus_without_interval=[s for s in roster_skus
                                      if s not in {r["sku"] for r in rebuilt}],
        roster_skus_with_sales=len(set(roster_skus) & set(series)),
        scored_skus=len({c["sku"] for c in cells_by_route["raw"]}),
        excluded_no_interval=excluded_no_interval,
        unscored=dict(n=len(unscored), items=unscored),
        interval_rows_committed=len(committed_rows),
        interval_rows_rebuilt=len(rebuilt),
        interval_key_mismatches=mismatches,
        cells_per_route={r: len(c) for r, c in cells_by_route.items()},
        cells_restricted_full_period={
            r: dict(n=sum(1 for c in cells if c["restricted_full"]),
                    knowable_at_cut=sum(1 for c in cells
                                        if c["restricted_full"] and c["restricted_knowable_at_cut"]),
                    not_knowable_at_cut=sum(1 for c in cells
                                            if c["restricted_full"] and not c["restricted_knowable_at_cut"]))
            for r, cells in cells_by_route.items()},
        cells_restricted_point_in_time={r: sum(1 for c in cells if c["restricted_pit"])
                                        for r, cells in cells_by_route.items()},
        train_label_mismatch_full_vs_pit=dict(n=len(train_label_mismatch),
                                              items=train_label_mismatch[:50]),
        source_counts=dict(checked0stock_files=n_files, dedup_files=n_uniq,
                           independent_events=sum(len(v) for v in events.values()),
                           wedge_styles=len(wedge), wx_source_dates=len(wx_dates),
                           wx_wide_rows_excluded=wide_rows),
    )

    payload = dict(
        schema_version="pb_censored_audit/1",
        inputs=dict(db=str(args.db), pb_root=str(args.pb_root), cohort=str(args.cohort),
                    intervals=str(args.intervals), list=str(args.list),
                    merge_days=MERGE_DAYS, over_ratio=OVER_RATIO,
                    low_threshold=LOW_THRESHOLD, origins=origins),
        coh_port=dict(cohort_count=cohort.get("count"), cohort_rows=len(cohort_rows),
                      roster_count=len(roster_skus),
                      roster_extra_not_in_cohort=roster_extra,
                      cohort_missing_from_roster=cohort_missing,
                      per_sku=cohort_cmp),
        promotion=dict(events=cohort.get("events", []),
                       training_rows_in_promo_months=promo_train_rows,
                       training_rows_in_promo_months_by_month=dict(sorted(promo_train_detail.items())),
                       target_cells_in_promo_months=promo_target_rows),
        intervals_decomposed=rebuilt,
        metrics=metrics,
        bootstrap=bootstrap,
        reconciliation=recon,
        elapsed_s=round(time.time() - t0, 2),
    )
    (OUT / "censored_audit.json").write_text(
        json.dumps(payload, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")

    # --------------------------------------------------------------- console
    print(json.dumps(dict(
        roster=len(roster_skus), cohort=len(cohort_rows),
        roster_extra=roster_extra, cohort_missing=cohort_missing,
        promo_train_rows=promo_train_rows, promo_target_cells=promo_target_rows,
        intervals=len(rebuilt), interval_mismatches=len(mismatches),
        train_label_mismatch=len(train_label_mismatch),
        cells={r: len(c) for r, c in cells_by_route.items()},
        elapsed_s=round(time.time() - t0, 2),
    ), ensure_ascii=False, indent=2))
    for route in ("raw", "censored"):
        m = metrics[route]
        print(route, json.dumps(m["wape_bias_non_restricted_full_period"]), end=" ")
        print(json.dumps(m["wape_bias_all_cells_point_in_time"]), end=" ")
        print(json.dumps(m["forecast_above_shipment_ratio_full_period"]), end=" ")
        print(json.dumps(m["forecast_to_shipment_ratio_non_restricted"]))
    print(json.dumps(bootstrap, ensure_ascii=False, indent=2))
    print(json.dumps(dict(
        export_dates_in_window=len(export_in_window),
        observed_vs_span_days=[sum(r["observed_signal_days"] for r in rebuilt),
                               sum(r["merged_window_days"] for r in rebuilt),
                               sum(r["unknown_gap_days"] for r in rebuilt)],
    ), ensure_ascii=False))


if __name__ == "__main__":
    main()
