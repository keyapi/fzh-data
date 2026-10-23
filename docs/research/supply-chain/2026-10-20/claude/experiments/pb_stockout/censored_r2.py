#!/usr/bin/env python
# -*- coding: utf-8 -*-
"""R2: corrected lower-bound training for the PB signal cohort (OFFLINE, READ-ONLY).

SUPERSEDES experiments/pb_stockout/censored_compare.py (commit e1b9b5d7).

Why the old script must not be used: its "censored" route zero-weights exactly the
rows a lower bound obliges us to penalise. `censored_compare.py:111-119` sets
w=0 when `pred < y_log`, i.e. it drops the row precisely when the model predicts
BELOW the observed (lower-bound) value. The direction is inverted: a prediction
below the bound is the violation, a prediction above it is unremarkable.

This script implements the fix and the four structural repairs the independent
review (#301) demanded:

  M01  one-sided LOWER bound loss   : penalty = max(0, y - pred)^2 on lower-bound
                                      months, 0 above the bound. Active-set IRLS.
  M02  span is not a stockout length: `signal_cluster_span_days`; the widened
                                      window is a HYPOTHETICAL extension; actual
                                      signal days kept; duration / recovery = unknown.
                                      Labels no longer come from the span.
  M03  ratio is descriptive only   : `forecast_above_shipment_ratio`, zero-owner
                                      cells listed separately, no business ranking.
  M04  per-cut freeze              : what was knowable at each cut, per-cut roster,
                                      and a negative test that appending future
                                      evidence changes neither labels nor forecasts.
  M05  set difference closed       : 26 / 27 / 28 with four categories.
  N01  counts and horizon wording  : 208 / 202 + 6; horizon 3/3/2; month counts.

Red lines: DB read_only=True; no production access; no writes outside out/; no new
dependencies; no imputed demand as ground truth; no business ranking from ratios.

Outputs (all new files):
  out/pb_stockout/censored_r2.json
  out/pb_stockout/stockout_intervals_v2.csv
  out/pb_stockout/sku_set_diff.csv
  out/pb_stockout/ratio_zero_denominator_cells.csv
"""
from __future__ import annotations

import argparse
import csv
import json
import sys
import time
from collections import Counter, defaultdict
from datetime import date, timedelta
from pathlib import Path

import numpy as np

HERE = Path(__file__).resolve()
EXP_DIR = HERE.parent
CLAUDE_DIR = HERE.parents[2]
OUT = CLAUDE_DIR / "out" / "pb_stockout"
sys.path.insert(0, str(EXP_DIR))

import censored_compare as legacy       # design()/fit_ridge()/fit_route() — OLD loss, demo only
import audit_pb_censored as audit       # source loaders + cluster helper (reused)

ORIGINS = legacy.ORIGINS
HORIZON = legacy.HORIZON
MIN_TRAIN = legacy.MIN_TRAIN
RIDGE = legacy.RIDGE
OVER_RATIO = 1.2
MAX_ROSTER = 30
IRLS_ITERS = 60


# --------------------------------------------------------------------------- #
# M01 — the corrected loss
# --------------------------------------------------------------------------- #
def lower_bound_penalty(pred, y, censored):
    """One-sided lower-bound squared loss.

    y is a LOWER bound on demand (true >= y). Therefore:
      pred <  y  -> violation, cost (y - pred)^2
      pred >= y  -> consistent with the bound, cost 0
    Uncensored rows always pay the usual squared error.
    """
    pred = np.asarray(pred, float)
    y = np.asarray(y, float)
    censored = np.asarray(censored, bool)
    r_low = np.where(censored & (y > pred), y - pred, 0.0)
    r_obs = np.where(censored, 0.0, pred - y)
    return float((r_low ** 2).sum() + (r_obs ** 2).sum())


def fit_lower(y, X, censored, ridge=RIDGE, iters=IRLS_ITERS):
    """Fit the one-sided lower-bound objective by active-set IRLS.

    At each iteration the loss is quadratic on {uncensored} u {censored : pred < y}
    and flat on {censored : pred >= y}, so the update is weighted ridge regression
    on the active set. Iterate until the active set stops changing.

    Chosen over a Gaussian Tobit MLE because (a) it needs no scale parameter —
    with 1-3 lower-bound months per SKU a fitted sigma is unstable; (b) it keeps the
    identical ridge penalty so the ONLY difference from the raw route is how
    lower-bound months are treated; (c) the fixed point is deterministic and easy
    to regression-test.
    """
    y = np.asarray(y, float)
    X = np.asarray(X, float)
    censored = np.asarray(censored, bool)
    w = np.ones(len(y))
    beta = legacy.fit_ridge(X, y, w, ridge)
    for _ in range(iters):
        pred = X @ beta
        w_new = np.where(censored & (pred >= y), 0.0, 1.0)
        if np.array_equal(w_new, w):
            break
        if w_new.sum() < 2:
            break            # nothing constrains the model any more; keep current beta
        w = w_new
        beta = legacy.fit_ridge(X, y, w, ridge)
    return beta


# --------------------------------------------------------------------------- #
def signals(events, wx, wx_dates, sku, cut=None):
    """Dates with an observed blocked-order signal, known at `cut` (None = full window)."""
    hi = wx_dates[-1] if cut is None else min(cut, wx_dates[-1])
    sig = {d for d in events.get(sku.upper(), ()) if wx_dates[0] <= d <= hi}
    for d in wx_dates:
        if d > hi:
            continue
        if audit.status_of(wx.get(sku, {}).get(d)) in ("nonpositive", "low_1_3"):
            sig.add(d)
    return sorted(sig)


def month_of(d: date) -> str:
    return f"{d.year:04d}-{d.month:02d}"


# --------------------------------------------------------------------------- #
def run_experiment(series, skus, events, wx, wx_dates, truncate_at_cut):
    """Cells for both routes. truncate_at_cut=True rebuilds labels only from what
    was knowable at the cut (used by the M04 negative test)."""
    last_i = legacy.ym_i("2026-09")
    cells = {r: [] for r in ("raw", "lower_bound")}
    labels, unscored = {}, []
    for sku in skus:
        by = series[sku]
        first = min(legacy.ym_i(m) for m in by)
        months = [legacy.i_ym(i) for i in range(first, last_i + 1)]
        y = np.array([by.get(m, 0.0) for m in months], dtype=float)
        labels[sku] = {}
        for origin in ORIGINS:
            cut = audit.month_end(origin)
            sig = signals(events, wx, wx_dates, sku, cut if truncate_at_cut else None)
            lb_months = {month_of(d) for d in sig}       # M02: label = month has a signal day
            tr = legacy.ym_i(origin) - first + 1
            if tr < MIN_TRAIN:
                unscored.append(dict(sku=sku, origin=origin, reason="history_lt_min_train"))
                continue
            train_months = months[:tr]
            cens = np.array([m in lb_months for m in train_months], dtype=bool)
            labels[sku][origin] = dict(train_lower_bound_months=[m for m, c in zip(train_months, cens) if c])
            X = legacy.design([legacy.ym_i(m) for m in train_months],
                              [int(m[5:7]) for m in train_months], first)
            ylog = np.log1p(y[:tr])
            tgt = [legacy.i_ym(legacy.ym_i(origin) + 1 + k) for k in range(HORIZON)]
            tgt = [m for m in tgt if legacy.ym_i(m) <= last_i]
            Xf = legacy.design([legacy.ym_i(m) for m in tgt],
                               [int(m[5:7]) for m in tgt], first)
            for route in ("raw", "lower_bound"):
                beta = (legacy.fit_ridge(X, ylog, np.ones(len(ylog)), RIDGE)
                        if route == "raw" else fit_lower(ylog, X, cens, RIDGE))
                if route == "raw":
                    beta_raw = beta
                else:
                    # the one-sided objective must be no worse than the raw fit's.
                    # (Note: the bound pred >= y need NOT hold at the optimum — the
                    # loss trades a violation against the uncensored residuals.)
                    def obj(b):
                        return (lower_bound_penalty(X @ b, ylog, cens)
                                + RIDGE * float(b[1:] @ b[1:]))
                    labels[sku][origin]["objective_lb_le_raw"] = bool(obj(beta) <= obj(beta_raw) + 1e-9)
                    labels[sku][origin]["objective_gain"] = float(obj(beta_raw) - obj(beta))
                f = np.maximum(0.0, np.expm1(Xf @ beta))
                for m, fv in zip(tgt, f):
                    cells[route].append(dict(
                        sku=sku, origin=origin, month=m,
                        forecast=round(float(fv), 6),
                        actual=round(float(by.get(m, 0.0)), 6),
                        lower_bound_month=bool(m in lb_months),
                        training_has_lower_bound=bool(cens.any()),
                        knowable_at_cut=legacy.ym_i(m) <= legacy.ym_i(origin),
                    ))
    return cells, labels, unscored


def main() -> None:
    t0 = time.time()
    ap = argparse.ArgumentParser()
    ap.add_argument("--db", default=str(audit.DB_PATH))
    ap.add_argument("--pb-root", default=str(audit.PB_ROOT))
    ap.add_argument("--cohort", default=str(audit.COHORT))
    ap.add_argument("--intervals", default=str(OUT / "stockout_intervals.csv"))
    ap.add_argument("--list", default=str(OUT / "pb_30sku_list.csv"))
    args = ap.parse_args()

    wx_dates, wx, wide_rows = audit.load_wx(args.db)
    n_files, n_uniq, events, wedge, export_dates = audit.load_events(Path(args.pb_root))
    series, sales_total, pb_pairs = audit.load_sales(args.db)
    cohort = json.loads(Path(args.cohort).read_text(encoding="utf-8"))
    roster = list(csv.DictReader(Path(args.list).open(encoding="utf-8-sig", newline="")))
    roster_skus = [r["sku"] for r in roster]
    iv_old = legacy.read_intervals(Path(args.intervals))      # OLD span-overlap labels
    export_in_window = sorted(d for d in export_dates if wx_dates[0] <= d <= wx_dates[-1])
    max_snap_gap = max((b - a).days for a, b in zip(wx_dates, wx_dates[1:]))

    skus = sorted(set(iv_old) & set(series))                  # frozen 26, same scope
    frozen = set(skus)

    # ------------------------------------------------ M02: interval table v2
    v2_rows = []
    for sku in roster_skus:
        sig = signals(events, wx, wx_dates, sku)
        for i, run in enumerate(audit.runs_of(sig), start=1):
            start, end = run[0], run[-1]
            gap_no_obs = gap_pos = 0
            for k in range((end - start).days + 1):
                d = start + timedelta(days=k)
                if d in run:
                    continue
                if audit.status_of(wx.get(sku, {}).get(d)) == "positive":
                    gap_pos += 1
                else:
                    gap_no_obs += 1
            ext = min(end + timedelta(days=max_snap_gap), wx_dates[-1])
            opp = [d for d in export_in_window if start <= d <= end]
            v2_rows.append(dict(
                sku=sku, cluster_index=i,
                first_signal_date=start.isoformat(), last_signal_date=end.isoformat(),
                signal_dates=";".join(d.isoformat() for d in run),
                signal_cluster_span_days=(end - start).days,
                observed_signal_days=len(set(run)),
                unknown_gap_days=(end - start).days + 1 - len(set(run)),
                gap_days_without_any_observation=gap_no_obs,
                gap_days_with_positive_snapshot=gap_pos,
                export_dates_in_window=len(opp),
                export_dates_without_signal=sum(1 for d in opp if d not in run),
                hypothetical_extension_until=(ext.isoformat() if ext > end else ""),
                hypothetical_window_days=(ext - start).days,
                continuous_duration_days="unknown",
                recovery_date="unknown",
                evidence_grade="signal_days_only",
                note=("信号簇跨度不是连续受阻时长；连续时长与恢复日期为 unknown；"
                      "扩展窗口是假设值，不用于打标签"),
            ))
    with (OUT / "stockout_intervals_v2.csv").open("w", encoding="utf-8-sig", newline="") as fh:
        w = csv.DictWriter(fh, fieldnames=list(v2_rows[0].keys()))
        w.writeheader()
        w.writerows(v2_rows)

    # ------------------------------------------------ experiment (both routes)
    cells, labels, unscored = run_experiment(series, skus, events, wx, wx_dates, False)
    cells_pit, labels_pit, _ = run_experiment(series, skus, events, wx, wx_dates, True)

    # ------------------------------------------------ M04 negative test
    neg_mismatch_labels = neg_mismatch_forecast = 0
    for sku in skus:
        for origin in ORIGINS:
            if origin not in labels.get(sku, {}):
                continue
            if labels[sku][origin] != labels_pit[sku][origin]:
                neg_mismatch_labels += 1
    for route in cells:
        full = {(c["sku"], c["origin"], c["month"]): c["forecast"] for c in cells[route]}
        pit = {(c["sku"], c["origin"], c["month"]): c["forecast"] for c in cells_pit[route]}
        for k in full:
            if k in pit and abs(full[k] - pit[k]) > 1e-12:
                neg_mismatch_forecast += 1

    # ------------------------------------------------ per-cut freeze
    freeze = []
    for origin in ORIGINS:
        cut = audit.month_end(origin)
        ev_avail = sorted(d for d in export_dates if d <= cut)
        wx_avail = sorted(d for d in wx_dates if d <= cut)
        sales_cut = {}
        for s in roster_skus:
            n = 0.0
            for m, q in series.get(s, {}).items():
                if m <= origin:
                    n += q
            sales_cut[s] = n
        eligible = [s for s in roster_skus
                    if sales_cut[s] > 0 and signals(events, wx, wx_dates, s, cut)]
        eligible.sort(key=lambda s: (-sales_cut[s], s))
        eligible_set = set(eligible[:MAX_ROSTER])
        freeze.append(dict(
            origin=origin, cut=cut.isoformat(),
            available_checked0stock_dates=[d.isoformat() for d in ev_avail],
            n_available_checked0stock_dates=len(ev_avail),
            available_wx_snapshot_dates=[d.isoformat() for d in wx_avail],
            sales_known_through=origin,
            roster_rule="PB 销量>0 且窗口内至少 1 个信号日，按销量降序取前 30",
            n_roster_eligible_at_cut=len(eligible),
            roster_at_cut_top30=eligible[:MAX_ROSTER],
            overlap_with_frozen=len(eligible_set & frozen),
            frozen_not_eligible=sorted(frozen - set(eligible)),
            eligible_not_in_frozen=sorted(set(eligible) - frozen)[:40],
            note=("名单在 2026-05 切点不可评估：信号只来自 2026-06-09..07-31 的 WX 窗口，"
                  "5 月末尚无任何窗口内信号"),
        ))

    # ------------------------------------------------ metrics (neutral wording)
    def wape_bias(cells_):
        if not cells_:
            return dict(n=0, wape=None, bias=None, actual_sum=0.0)
        tot = sum(c["actual"] for c in cells_)
        return dict(
            n=len(cells_),
            wape=(sum(abs(c["forecast"] - c["actual"]) for c in cells_) / tot if tot else None),
            bias=(sum(c["forecast"] - c["actual"] for c in cells_) / tot if tot else None),
            actual_sum=round(tot, 3),
        )

    def above_shipment(cells_):
        """Descriptive: share of lower-bound months whose forecast exceeds observed
        shipments by >20%. NOT a stockout rate, NOT backlog, NOT service level."""
        obs = [c for c in cells_ if c["actual"] > 0]
        over = [c for c in obs if c["forecast"] > c["actual"] * OVER_RATIO]
        return dict(
            cells=len(cells_), cells_with_actual_zero=len(cells_) - len(obs),
            denominator_all_cells=len(cells_), denominator_observed_cells=len(obs),
            over=len(over),
            ratio_over_all_cells=(len(over) / len(cells_) if cells_ else None),
            ratio_over_observed_cells=(len(over) / len(obs) if obs else None),
        )

    def ratio_dist(cells_):
        r = [c["forecast"] / c["actual"] for c in cells_ if c["actual"] > 0]
        if not r:
            return dict(n=0, median=None, share_above_1_2=None)
        a = np.array(r)
        return dict(n=len(r), median=round(float(np.median(a)), 4),
                    share_above_1_2=round(float((a > OVER_RATIO).mean()), 4))

    metrics = {}
    for route, cs in cells.items():
        lb = [c for c in cs if c["lower_bound_month"]]
        free = [c for c in cs if not c["lower_bound_month"]]
        metrics[route] = dict(
            wape_bias_signal_free_months=wape_bias(free),
            wape_bias_all_cells=wape_bias(cs),
            forecast_above_shipment_ratio_lower_bound_months=above_shipment(lb),
            forecast_to_shipment_ratio_signal_free_months=ratio_dist(free),
            forecast_to_shipment_ratio_all_observed=ratio_dist(cs),
        )

    # zero-denominator cells (M03: listed, never folded into a ratio)
    # NOTE: both routes are reported per cell. The first version of this table took
    # `cells["raw"]` only but labelled every row route="both", which is false for
    # cells where the two routes disagree (301 窄复审 minor).
    lb_by_key = {(c["sku"], c["origin"], c["month"]): c for c in cells["lower_bound"]}
    zero_cells = [dict(
        sku=c["sku"], origin=c["origin"], month=c["month"],
        forecast_raw=c["forecast"],
        forecast_lower_bound=lb_by_key[(c["sku"], c["origin"], c["month"])]["forecast"],
        forecast_delta=round(lb_by_key[(c["sku"], c["origin"], c["month"])]["forecast"]
                             - c["forecast"], 6),
        actual=c["actual"],
        note="actual=0 -> 比值无定义；单列，不并入任何分母；两路线预测分别列出",
    ) for c in cells["raw"] if c["actual"] == 0]
    with (OUT / "ratio_zero_denominator_cells.csv").open("w", encoding="utf-8-sig", newline="") as fh:
        w = csv.DictWriter(fh, fieldnames=list(zero_cells[0].keys()))
        w.writeheader()
        w.writerows(zero_cells)

    # ------------------------------------------------ per-SKU evidence + direction
    idx = {r: {(c["sku"], c["origin"], c["month"]): c for c in cells[r]}
           for r in ("raw", "lower_bound")}
    per_sku, lb_deltas, affected, unaffected = {}, [], [], []
    n_fits = sum(len(v) for v in labels.values())
    for sku in skus:
        free = [k for k in idx["raw"] if k[0] == sku and not idx["raw"][k]["lower_bound_month"]]
        lb = [k for k in idx["raw"] if k[0] == sku and idx["raw"][k]["lower_bound_month"]]
        for k in lb:
            d = idx["lower_bound"][k]["forecast"] - idx["raw"][k]["forecast"]
            lb_deltas.append(d)
            (affected if idx["raw"][k]["training_has_lower_bound"] else unaffected).append(d)
        per_sku[sku] = dict(
            n_signal_free_cells=len(free), n_lower_bound_cells=len(lb),
            wape_signal_free_raw=wape_bias([idx["raw"][k] for k in free])["wape"],
            wape_signal_free_lower_bound=wape_bias([idx["lower_bound"][k] for k in free])["wape"],
            lb_affected_target_cells=sum(1 for k in lb if idx["raw"][k]["training_has_lower_bound"]),
            lb_affected_forecast_delta_median=(
                round(float(np.median([idx["lower_bound"][k]["forecast"] - idx["raw"][k]["forecast"]
                                       for k in lb if idx["raw"][k]["training_has_lower_bound"]])), 4)
                if any(idx["raw"][k]["training_has_lower_bound"] for k in lb) else None),
        )
    direction = dict(
        n_lower_bound_target_cells=len(lb_deltas),
        split_note=("origin=2026-05 的训练集不含任何下限月（信号始于 06-15），两条路线必然相同；"
                    "只有 origin=06/07 的训练集含下限月，修正才会生效"),
        affected=dict(
            n=len(affected),
            forecast_increase_share=(round(float(np.mean([d > 0 for d in affected])), 4)
                                     if affected else None),
            forecast_decrease_share=(round(float(np.mean([d < 0 for d in affected])), 4)
                                     if affected else None),
            median_delta=(round(float(np.median(affected)), 4) if affected else None),
        ),
        unaffected=dict(
            n=len(unaffected),
            max_abs_delta=(round(float(max((abs(d) for d in unaffected), default=0.0)), 6)),
        ),
    )
    objs = [v for s in labels for o, v in labels[s].items() if "objective_lb_le_raw" in v]
    lb_fit_ok = dict(
        fits=n_fits,
        objective_lb_le_raw=sum(1 for v in objs if v["objective_lb_le_raw"]),
        median_objective_gain=round(float(np.median([v["objective_gain"] for v in objs])), 6),
        note=("单侧目标在修正路线上的取值必须不高于 raw 解在同一目标上的取值；"
              "下限 pred>=y 不必在最优解成立（损失会用未删失残差交换违规）"),
    )

    # ------------------------------------------------ bootstrap (SKU clusters)
    rng = np.random.default_rng(20261023)
    BOOT = 2000

    def stat_wape(cs):
        tot = sum(c["actual"] for c in cs)
        return None if not cs or not tot else sum(abs(c["forecast"] - c["actual"]) for c in cs) / tot

    def stat_share_above(cs):
        obs = [c for c in cs if c["actual"] > 0]
        return None if not obs else sum(1 for c in obs if c["forecast"] > c["actual"] * OVER_RATIO) / len(obs)

    def boot_delta(pick_fn, stat, b=BOOT):
        by_sku = {s: {r: pick_fn([c for c in cells[r] if c["sku"] == s])
                      for r in ("raw", "lower_bound")} for s in skus}
        raw_all = [c for s in skus for c in by_sku[s]["raw"]]
        lb_all = [c for s in skus for c in by_sku[s]["lower_bound"]]
        point = stat(lb_all) - stat(raw_all)
        deltas = []
        for _ in range(b):
            idx = rng.integers(0, len(skus), size=len(skus))
            r = [c for i in idx for c in by_sku[skus[i]]["raw"]]
            l = [c for i in idx for c in by_sku[skus[i]]["lower_bound"]]
            a, bb = stat(r), stat(l)
            if a is not None and bb is not None:
                deltas.append(bb - a)
        q = lambda a, p: round(float(np.quantile(a, p)), 4)          # noqa: E731
        return dict(delta_point=round(point, 4),
                    delta_ci95=[q(deltas, 0.025), q(deltas, 0.975)],
                    excludes_zero=bool(q(deltas, 0.025) * q(deltas, 0.975) > 0),
                    bootstrap=b, skus=len(skus))

    bootstrap = dict(
        wape_signal_free= boot_delta(lambda cs: [c for c in cs if not c["lower_bound_month"]], stat_wape),
        wape_all_cells=boot_delta(lambda cs: cs, stat_wape),
        share_forecast_above_1_2=boot_delta(lambda cs: [c for c in cs if c["actual"] > 0],
                                            stat_share_above),
        note="按 SKU 整簇重采样 2000 次，seed 20261023；delta = lower_bound − raw",
    )

    # ------------------------------------------------ M05: set difference
    cohort_rows = cohort["rows"]
    cohort_skus = {r["vendor_sku"] for r in cohort_rows}
    vendor_to_tong = defaultdict(set)
    for psk, tong in pb_pairs:
        vendor_to_tong[psk].add(tong)
    sig_all = {s: signals(events, wx, wx_dates, s) for s in roster_skus}
    diff_rows = []

    def add(sku, in_cohort, category, reason, effect):
        s = series.get(sku, {})
        diff_rows.append(dict(
            sku=sku, in_cohort="yes" if in_cohort else "no",
            in_roster27="yes" if sku in set(roster_skus) else "no",
            in_frozen26="yes" if sku in frozen else "no",
            pb_sales_qty=(round(sales_total[sku]) if sku in sales_total else ""),
            window_signal_dates=len(sig_all.get(sku, [])),
            vendor_to_tongtool=("proven_exact_string"
                                if vendor_to_tong.get(sku.upper()) == {sku}
                                else ("mapping_unproven" if sku not in series else "conflict")),
            category=category, reason=reason, effect_on_frozen26=effect,
        ))

    for r in cohort_rows:
        v = r["vendor_sku"]
        if v in frozen:
            add(v, True, "已纳入", "cohort 内、有销量、窗口内有信号", "参与对照")
        elif v in set(roster_skus):
            add(v, True, "未纳入·无窗口标签", "名册内但 WX 窗口内事件 0 且无非正快照 → 无区间",
                "27→26 被排除；不等于无断货历史")
        else:
            add(v, True, "未纳入·无销量", "PB 渠道 gs_orders 零行，无法进入销量序列",
                "不进 27/26；其 vendor→通途映射亦无法证实")
    for s in roster_skus:
        if s not in cohort_skus:
            add(s, False, "仅在本方·cohort外", "不在外部 28 名单；家族身份仅由 checked0stock 描述文本支撑",
                "计入 27/26，但不得与 cohort 内 23 个混称同源")
    # mapping ambiguity is cohort-wide: PB numeric SKU -> vendor has no local evidence
    for r in cohort_rows:
        diff_rows.append(dict(
            sku=r["vendor_sku"], in_cohort="yes",
            in_roster27="yes" if r["vendor_sku"] in set(roster_skus) else "no",
            in_frozen26="yes" if r["vendor_sku"] in frozen else "no",
            pb_sales_qty=(round(sales_total[r["vendor_sku"]])
                          if r["vendor_sku"] in sales_total else ""),
            window_signal_dates=len(sig_all.get(r["vendor_sku"], [])),
            vendor_to_tongtool=("proven_exact_string"
                                if vendor_to_tong.get(r["vendor_sku"].upper()) == {r["vendor_sku"]}
                                else "mapping_unproven"),
            category="映射歧义", reason=f"PB 数字码 {r['pb_sku']} 在本地任何表均无记录",
            effect_on_frozen26="不改变 26 集合；限制与 PB 官方对账",
        ))
    with (OUT / "sku_set_diff.csv").open("w", encoding="utf-8-sig", newline="") as fh:
        w = csv.DictWriter(fh, fieldnames=list(diff_rows[0].keys()))
        w.writeheader()
        w.writerows(diff_rows)

    # ------------------------------------------------ N01 counts
    lb_month_counts = {s: len({m for o in v for m in v[o]["train_lower_bound_months"]})
                       for s, v in labels.items()}
    horizon_by_origin = {o: len({c["month"] for c in cells["raw"] if c["origin"] == o})
                         for o in ORIGINS}
    # labels that would have come from the OLD span-overlap rule, for the change log
    old_span_labels = defaultdict(set)
    for sku, ivs in iv_old.items():
        for a, b in ivs:
            m = date(a.year, a.month, 1)
            while m <= b:
                old_span_labels[sku].add(f"{m.year:04d}-{m.month:02d}")
                m = date(m.year + (m.month // 12), (m.month % 12) + 1, 1)
    changed = []
    for sku in skus:
        new = {m for o in labels[sku] for m in labels[sku][o]["train_lower_bound_months"]}
        if new != old_span_labels[sku]:
            changed.append(dict(sku=sku, new=sorted(new), old=sorted(old_span_labels[sku])))

    payload = dict(
        schema_version="pb_censored_r2/1",
        supersedes=dict(script="experiments/pb_stockout/censored_compare.py",
                        commit="e1b9b5d7",
                        reason="M01：单侧下限损失方向相反；M02：跨度被当成连续受阻并直接转成标签"),
        inputs=dict(db=str(args.db), pb_root=str(args.pb_root), cohort=str(args.cohort),
                    origins=ORIGINS, horizon=HORIZON, ridge=RIDGE, over_ratio=OVER_RATIO,
                    max_roster=MAX_ROSTER, db_read_only=True),
        loss=dict(
            route_raw="ridge on log1p(y), all months weight 1",
            route_lower_bound=("one-sided lower-bound squared loss: cost (y-pred)^2 when pred<y, "
                               "0 when pred>=y, on months containing >=1 observed signal day; "
                               "active-set IRLS; same ridge penalty as raw"),
            label_rule=("lower_bound_month = 该月至少有 1 个已观测信号日；"
                        "跨度/假设扩展窗口不参与打标签"),
            label_assumption=("把含信号月的销量视作需求下限，是一个**假设**：单次受阻不证明整月受限，"
                              "但它是本批能最小限度辩护的标签"),
        ),
        metrics=metrics,
        bootstrap=bootstrap,
        freeze=freeze,
        negative_test=dict(
            description="追加未来证据不改变历史可用训练标签与预测",
            label_mismatches=neg_mismatch_labels,
            forecast_mismatches=neg_mismatch_forecast,
            passed=bool(neg_mismatch_labels == 0 and neg_mismatch_forecast == 0),
        ),
        counts=dict(
            cells_per_route={r: len(c) for r, c in cells.items()},
            lower_bound_cells=sum(1 for c in cells["raw"] if c["lower_bound_month"]),
            signal_free_cells=sum(1 for c in cells["raw"] if not c["lower_bound_month"]),
            ratio_evaluable_cells=sum(1 for c in cells["raw"] if c["actual"] > 0),
            ratio_zero_denominator_cells=len(zero_cells),
            lower_bound_months_per_sku=dict(Counter(lb_month_counts.values())),
            lower_bound_months_detail=lb_month_counts,
            horizon_by_origin=horizon_by_origin,
            unscored=unscored,
        ),
        labels=dict(per_sku=labels, label_changes_vs_old_span_rule=changed),
        per_sku_metrics=per_sku,
        direction_check=direction,
        lower_bound_fit_check=lb_fit_ok,
        zero_denominator_cells=zero_cells,
        set_diff=diff_rows,
        intervals_v2=v2_rows,
        source_counts=dict(checked0stock_files=n_files, dedup_files=n_uniq,
                           export_dates_in_window=len(export_in_window),
                           wx_source_dates=len(wx_dates), wx_wide_rows_excluded=wide_rows,
                           max_snapshot_gap_days=max_snap_gap),
        reconciliation=dict(
            roster27=len(roster_skus), frozen26=len(skus),
            excluded_no_window_label=sorted(set(roster_skus) - frozen),
            cohort28=len(cohort_rows),
            cohort_not_in_frozen=sorted(cohort_skus - frozen),
            cells={r: len(c) for r, c in cells.items()},
        ),
        elapsed_s=round(time.time() - t0, 2),
    )
    (OUT / "censored_r2.json").write_text(
        json.dumps(payload, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")

    # ------------------------------------------------ console
    print(json.dumps(dict(
        frozen=len(skus), lb_months=dict(Counter(lb_month_counts.values())),
        label_changes_vs_old=len(changed),
        cells={r: len(c) for r, c in cells.items()},
        horizon=horizon_by_origin,
        negative_test=payload["negative_test"],
        elapsed_s=payload["elapsed_s"],
    ), ensure_ascii=False))
    for route in ("raw", "lower_bound"):
        m = metrics[route]
        print(route,
              json.dumps(m["wape_bias_signal_free_months"]),
              json.dumps(m["wape_bias_all_cells"]),
              json.dumps(m["forecast_above_shipment_ratio_lower_bound_months"]),
              json.dumps(m["forecast_to_shipment_ratio_all_observed"]))
    print(json.dumps(bootstrap, ensure_ascii=False, indent=1))
    print(json.dumps([{k: v[k] for k in ("origin", "cut", "n_roster_eligible_at_cut",
                                         "overlap_with_frozen", "n_available_checked0stock_dates")}
                      for v in freeze], ensure_ascii=False))


if __name__ == "__main__":
    main()
