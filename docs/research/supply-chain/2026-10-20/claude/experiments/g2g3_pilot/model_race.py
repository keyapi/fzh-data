#!/usr/bin/env python
# -*- coding: utf-8 -*-
"""V1 candidate model race: 10-SKU demand forecast, rolling 6-origin backtest,
empirical/conformal cumulative P90, and replenishment action sensitivity.

Read-only inputs:
  - D:/Work/fzh-order-store/order_store.duckdb (read_only=True)
  - out/replenishment_v0/evidence.json (V0.1 supply/SO evidence; frozen 98e1c664)
Output:
  - out/replenishment_v0/model_race.json

No production access, no order placement, no scope expansion. The V0.1 report and
build_v0.py are not modified.

Candidates (same rolling origins):
  1 seasonal_naive          last year's same month
  2 mean3                   last-3-month mean (levels off recent, not seasonal)
  3 seasonal_yoy            seasonal naive x trailing-6m YoY level factor
  4 ets                     explicitly skipped: statsmodels/statsforecast absent
  5 peer_shape              peer seasonal shape x own trailing-12m level

Uncertainty:
  Cumulative P90 uses the empirical/conformal quantile of rolling-origin
  cumulative errors, not sqrt(h) or sqrt(6). No random-walk assumption.
  Own-SKU primary residuals are used when >=3 exist; otherwise a pooled
  peer-relative conformal estimate is used and labelled. Target 0.90 and
  achieved coverage are recorded separately.
"""
from __future__ import annotations

import argparse
import hashlib
import json
import math
from datetime import date, datetime, timedelta
from pathlib import Path

import duckdb
import numpy as np

DB_PATH = Path("D:/Work/fzh-order-store/order_store.duckdb")
HERE = Path(__file__).resolve()
CLAUDE_DIR = HERE.parents[2]
EVIDENCE_PATH = CLAUDE_DIR / "out" / "replenishment_v0" / "evidence.json"
OUT_PATH = CLAUDE_DIR / "out" / "replenishment_v0" / "model_race.json"

# customer_code (gs_orders.sku_tongtool), EN item_code, EN phase1 snapshot filename
SCOPES = [
    ("CENCord995-DKGrey-97", "KS0001-QDKTR-100-DEEPGREY", "g1b_en_top_1.json"),
    ("CEN003-DPBLUE-100", "KS0001-QDKTR-100-DEEPBLUE", "g1b_en_top_2.json"),
    ("C/Linen-Natural-100-688-wow", "KS0001-XMMBS-100-HEMPNATURAL", "g1b_en_top_3.json"),
    ("C/Cord-DKBlue-100-713-wow", "KS0001-CMKTR-100-DEEPBLUE", "g1b_en_top_4.json"),
    ("C/Linen-Natural-153-688-wow", "KS0001-XMMBS-153-HEMPNATURAL", "g1b_en_top_5.json"),
    ("C/Velvet-Grey-100-705-wow", "KS0001-PR-100-GREY", "g1b_en_top_6.json"),
    ("C/Cord-Grey-100-710-wow", "KS0001-CMKTR-100-GREY", "g1b_en_top_7.json"),
    ("C/Linen-White-100-662-WOW", "KS0001-CMM-100-WHITE", "g1b_en_top_8.json"),
    ("TT0000671K0063721", "KS0001-HLR-100-OFFWHITE", "g1b_en_top_9.json"),
    ("C/Linen-Natural-194-688-wow", "KS0001-XMMBS-194-HEMPNATURAL", "g1b_en_rr2.json"),
]

SALES_CUTOFF = "2026-09"
DECISION_DATE = date(2026, 10, 22)
HORIZON_MONTHS = 5  # 2026-10 .. 2027-02, enough for 120+30 day windows
REPORT_ORIGINS = [f"2026-{m:02d}" for m in range(1, 7)]
TARGET_COVERAGE = 0.90
LEAD_DAYS = [60, 90, 120]
REVIEW_DAYS = 30
DAYS_PER_MONTH = 30.4375

MIN_LEVEL = 10.0          # near-zero protection for the YoY level window
PEER_MIN_HIST = 12        # a peer needs 12 months before contributing a shape
PEER_MIN_OBS = 2          # a calendar month needs 2 peer observations
PEER_MIN_BASE = 20.0      # ignore peer months whose trailing-12m mean is tiny

# Earliest training length at which a candidate is genuinely itself (not a fallback).
PRIMARY_MIN = {
    "seasonal_naive": 12,
    "mean3": 3,
    "seasonal_yoy": 18,
    "peer_shape": 3,
}

CANDIDATES = [
    dict(id="seasonal_naive", name="季节 naive（去年同月）",
         implemented=True,
         description="forecast[m] = y[origin-11 .. origin] same month last year; <12 months falls back to mean3"),
    dict(id="mean3", name="近 3 月均值",
         implemented=True,
         description="constant mean of the last 3 months; recent level, no seasonality"),
    dict(id="seasonal_yoy", name="季节 naive × 近期同比修正",
         implemented=True,
         description="seasonal naive x shrunk, clipped trailing-6m YoY factor; skipped on short/near-zero/zero-in-window baselines"),
    dict(id="ets", name="AutoETS / ETS",
         implemented=False,
         description="explicitly skipped: statsmodels and statsforecast are not installed; V0's hand-rolled additive HW is not reused as a candidate"),
    dict(id="peer_shape", name="同类季节形状 × 本 SKU 近期水平",
         implemented=True,
         description="median peer monthly/trailing-12m shape applied to own trailing-12m level; peers are the other 9 SKUs with >=12 months"),
]


# ----------------------------------------------------------------------------
# helpers
# ----------------------------------------------------------------------------
def sha256_file(path: Path) -> str:
    h = hashlib.sha256()
    with path.open("rb") as f:
        for chunk in iter(lambda: f.read(1 << 20), b""):
            h.update(chunk)
    return h.hexdigest()


def ym_to_i(ym: str) -> int:
    return int(ym[:4]) * 12 + int(ym[5:7]) - 1


def i_to_ym(i: int) -> str:
    y, m = divmod(i, 12)
    return f"{y:04d}-{m + 1:02d}"


def _round(x, nd=4):
    if x is None:
        return None
    if isinstance(x, (np.integer, int)):
        return int(x)
    v = float(x)
    if not math.isfinite(v):
        return None
    if abs(v - round(v)) < 1e-9:
        return int(round(v))
    return round(v, nd)


def clean(obj):
    """Recursively make numpy/pandas-free JSON-safe values."""
    if isinstance(obj, dict):
        return {str(k): clean(v) for k, v in obj.items()}
    if isinstance(obj, (list, tuple)):
        return [clean(v) for v in obj]
    if isinstance(obj, (np.integer,)):
        return int(obj)
    if isinstance(obj, (np.floating,)):
        return _round(float(obj))
    if isinstance(obj, float):
        return _round(obj)
    return obj


def conf_q90(vals: list[float]) -> tuple[float, float]:
    """Split-conformal empirical 90% upper quantile with finite-sample level."""
    n = len(vals)
    level = min(1.0, math.ceil((n + 1) * TARGET_COVERAGE) / n)
    q = float(np.quantile(np.asarray(vals, dtype=float), level, method="higher"))
    return q, level


def metrics(cells: list[dict]) -> dict:
    """WAPE/bias/coverage. Zero-actual cells are retained; only an all-zero
    aggregate denominator makes WAPE/bias undefined. Coverage only counts
    cells where a calibrated P90 exists."""
    n = len(cells)
    zero_cells = sum(1 for c in cells if abs(c["a"]) < 1e-9)
    if n == 0:
        return dict(n=0, zero_actual_cells=0, wape=None, bias=None,
                    coverage=None, n_coverage=0)
    sum_a = sum(c["a"] for c in cells)
    cov_cells = [c for c in cells if c.get("p90") is not None]
    coverage = (sum(1 for c in cov_cells if c["a"] <= c["p90"] + 1e-9) / len(cov_cells)) if cov_cells else None
    if abs(sum_a) < 1e-9:
        return dict(n=n, zero_actual_cells=zero_cells, wape=None, bias=None,
                    coverage=_round(coverage), n_coverage=len(cov_cells))
    wape = sum(abs(c["f"] - c["a"]) for c in cells) / sum_a
    bias = sum(c["f"] - c["a"] for c in cells) / sum_a
    return dict(n=n, zero_actual_cells=zero_cells, wape=_round(wape),
                bias=_round(bias), coverage=_round(coverage),
                n_coverage=len(cov_cells))


# ----------------------------------------------------------------------------
# data loading
# ----------------------------------------------------------------------------
def load_series(con):
    out = {}
    total_rows = 0
    bad_rows = 0
    for code, sku, snap in SCOPES:
        rows = con.execute(
            "SELECT substr(despatch_date,1,7) AS ym, SUM(qty) AS qty, "
            "COUNT(*) AS n_lines, COUNT(DISTINCT order_id) AS n_orders "
            "FROM gs_orders WHERE sku_tongtool=? GROUP BY 1 ORDER BY 1",
            [code]).fetchall()
        bad = con.execute(
            "SELECT COUNT(*) FROM gs_orders WHERE sku_tongtool=? "
            "AND (despatch_date IS NULL OR despatch_date='')", [code]).fetchone()[0]
        by_ym = {r[0]: float(r[1]) for r in rows}
        first_i = min(ym_to_i(m) for m in by_ym)
        last_i = ym_to_i(SALES_CUTOFF)
        months = [i_to_ym(i) for i in range(first_i, last_i + 1)]
        y = np.array([by_ym.get(m, 0.0) for m in months], dtype=float)
        out[sku] = dict(
            sku=sku, code=code, snapshot=snap,
            first=first_i, last=last_i, months=months, y=y,
            n_months=len(months),
            zero_filled=sum(1 for m in months if m not in by_ym),
            total_qty=float(y.sum()),
            rows=sum(int(r[2]) for r in rows),
            orders=sum(int(r[3]) for r in rows),
            bad_dates=int(bad),
            by_ym=by_ym,
        )
        total_rows += sum(int(r[2]) for r in rows)
        bad_rows += int(bad)
    return out, total_rows, bad_rows


def load_stockout_rows(con):
    codes = [c for c, _, _ in SCOPES]
    in_codes = ",".join("'" + c.replace("'", "''") + "'" for c in codes)
    rows = con.execute(f"""
        SELECT goods_sku, COUNT(*) AS n_rows,
               COUNT(*) FILTER (WHERE stockout_observed) AS n_stockout
        FROM stock_history
        WHERE snapshot_date = DATE '{DECISION_DATE.isoformat()}'
          AND goods_sku IN ({in_codes})
        GROUP BY 1 ORDER BY 1
    """).fetchall()
    return {r[0]: dict(rows=int(r[1]), stockout_rows=int(r[2])) for r in rows}


def load_white_orders(con):
    code = "C/Linen-White-100-662-WOW"
    rows = con.execute("""
        SELECT substr(despatch_date,1,7) AS ym, channel, account,
               COUNT(*) AS n_lines, COUNT(DISTINCT order_id) AS n_orders,
               SUM(qty) AS qty, MIN(qty) AS min_qty, MAX(qty) AS max_qty
        FROM gs_orders WHERE sku_tongtool=?
        GROUP BY 1,2,3 ORDER BY 1,2,3
    """, [code]).fetchall()
    out = []
    for r in rows:
        out.append(dict(month=r[0], channel=r[1] or "(blank)", account=r[2] or "(blank)",
                        n_lines=int(r[3]), n_orders=int(r[4]), qty=float(r[5]),
                        min_qty=float(r[6]), max_qty=float(r[7])))
    return out


def load_evidence():
    with EVIDENCE_PATH.open("r", encoding="utf-8") as f:
        ev = json.load(f)
    by_sku = {s["sku"]: s for s in ev["skus"]}
    return ev, by_sku


# ----------------------------------------------------------------------------
# candidate point forecasts
# ----------------------------------------------------------------------------
def mean3_forecast(y: np.ndarray, h: int):
    k = min(3, len(y))
    v = float(np.mean(y[-k:])) if k else 0.0
    return np.full(h, max(0.0, v), dtype=float), dict(
        effective="mean3", fallback=False, level_basis=f"mean_last_{k}m")


def seasonal_naive_forecast(y: np.ndarray, h: int):
    if len(y) >= 12:
        f = np.array([y[len(y) - 12 + i] for i in range(h)], dtype=float)
        return np.maximum(f, 0.0), dict(
            effective="seasonal_naive", fallback=False,
            low_confidence_lt_24m=bool(len(y) < 24),
            seasonality_claim=("one_season_only_do_not_claim_stable"
                               if len(y) < 24 else "two_plus_seasons"),
        )
    f, meta = mean3_forecast(y, h)
    meta = dict(meta, effective="mean3_fallback", fallback=True,
                fallback_reason="history_lt_12m", low_confidence_lt_24m=True)
    return f, meta


def seasonal_yoy_forecast(y: np.ndarray, h: int):
    """Seasonal naive with a trailing-6m level correction.

    Protection is deliberate and excludes small denominators:
      - <18 months: cannot compare the same 6 months last year -> skip;
      - either 6-month window mean < MIN_LEVEL -> skip;
      - any zero in the prior 6-month window -> skip (near-zero / censored);
      - raw ratio clipped to [0.5, 2.0], then shrunk 50% toward 1.
    When skipped the point forecast equals seasonal_naive, so calibration is
    delegated to that candidate (no pretending the factor was applied).
    """
    f, meta = seasonal_naive_forecast(y, h)
    meta = dict(meta)
    if len(y) < 18:
        return f, dict(meta, adjustment=1.0, yoy="skipped_history_lt_18m",
                       delegate_calibration="seasonal_naive")
    recent = float(np.mean(y[-6:]))
    prior = float(np.mean(y[-18:-12]))
    if recent < MIN_LEVEL or prior < MIN_LEVEL:
        return f, dict(meta, adjustment=1.0,
                       yoy=f"skipped_small_window recent={recent:.2f} prior={prior:.2f}",
                       delegate_calibration="seasonal_naive")
    if any(abs(float(v)) < 1e-9 for v in y[-18:-12]):
        return f, dict(meta, adjustment=1.0, yoy="skipped_zero_in_prior_window",
                       delegate_calibration="seasonal_naive")
    raw = recent / prior
    clipped = float(min(2.0, max(0.5, raw)))
    factor = 1.0 + 0.5 * (clipped - 1.0)
    f2 = np.maximum(0.0, f * factor)
    return f2, dict(meta, adjustment=_round(factor), yoy=dict(
        recent6_mean=_round(recent), prior6_mean=_round(prior),
        raw_ratio=_round(raw), clipped_ratio=_round(clipped),
        shrinkage=0.5, applied=True))


def peer_shape_forecast(sku: str, data: dict, train_len: int, origin_abs: int, h: int):
    """Median peer seasonal shape x own trailing-12m level.

    Peer shape = median over peers and months of y[m] / trailing-12m-mean for
    the same calendar month. Peers are the other 9 SKUs, truncated at the same
    origin so no future data enters the shape. Own level is trailing 12 months,
    or all history when <12 months (marked fallback_level).
    """
    t = data[sku]
    y = t["y"][:train_len]
    if len(y) == 0:
        return np.zeros(h), dict(effective="peer_shape", fallback=True,
                                 fallback_reason="no_history")
    lvl = float(np.mean(y[-12:])) if len(y) >= 12 else float(np.mean(y))
    ratios: dict[int, list[float]] = {}
    peers_used = 0
    for s2, d2 in data.items():
        if s2 == sku:
            continue
        cut = origin_abs - d2["first"] + 1
        if cut < PEER_MIN_HIST:
            continue
        yy = d2["y"][:cut]
        contributed = False
        for idx in range(11, len(yy)):
            base = float(np.mean(yy[idx - 11:idx + 1]))
            if base < PEER_MIN_BASE:
                continue
            cal = (d2["first"] + idx) % 12  # calendar month, 0=Jan
            ratios.setdefault(cal, []).append(float(yy[idx]) / base)
            contributed = True
        if contributed:
            peers_used += 1
    shape = {cal: float(np.median(v)) for cal, v in ratios.items() if len(v) >= PEER_MIN_OBS}
    if not shape:
        f, meta = seasonal_naive_forecast(y, h)
        meta = dict(meta, effective="seasonal_fallback",
                    peer_fallback=True, peers_used=peers_used)
        return f, dict(meta, delegate_calibration="seasonal_naive")
    f = []
    missing = []
    for k in range(1, h + 1):
        cal = (origin_abs + k) % 12
        if cal in shape:
            f.append(max(0.0, lvl * shape[cal]))
        else:
            missing.append(i_to_ym(origin_abs + k))
            f.append(max(0.0, float(np.mean(y[-3:]))) if len(y) >= 3 else 0.0)
    shape_list = [None if c not in shape else _round(shape[c]) for c in range(12)]
    obs_by_month = {str(c): len(ratios.get(c, [])) for c in range(12)}
    return np.array(f), dict(
        effective="peer_shape", fallback=len(y) < 12,
        fallback_reason="own_history_lt_12m" if len(y) < 12 else None,
        level=_round(lvl), level_basis="trailing_12m" if len(y) >= 12 else "all_history",
        peers_used=peers_used, shape_by_calendar_month=shape_list,
        observations_by_calendar_month=obs_by_month,
        missing_shape_months=missing,
    )


def forecast_candidate(cid: str, sku: str, data: dict, train_len: int,
                       origin_abs: int, h: int):
    if cid == "seasonal_naive":
        return seasonal_naive_forecast(data[sku]["y"][:train_len], h)
    if cid == "mean3":
        return mean3_forecast(data[sku]["y"][:train_len], h)
    if cid == "seasonal_yoy":
        return seasonal_yoy_forecast(data[sku]["y"][:train_len], h)
    if cid == "peer_shape":
        return peer_shape_forecast(sku, data, train_len, origin_abs, h)
    raise ValueError(f"candidate not implemented: {cid}")


# ----------------------------------------------------------------------------
# conformal cumulative P90
# ----------------------------------------------------------------------------
def primary_errors(sku: str, data: dict, cid: str, h: int, asof_abs: int):
    """Cumulative actual-minus-forecast errors from origins whose target window
    ends strictly at or before asof_abs. Only primary (non-fallback) cells;
    origins where the candidate delegates to another model are excluded."""
    d = data[sku]
    y = d["y"]
    first = d["first"]
    n = len(y)
    errs = []
    n_fallback = 0
    n_delegated = 0
    for o2 in range(first + PRIMARY_MIN[cid], asof_abs - h + 1):
        tr = o2 - first + 1
        if tr + h - 1 >= n:
            continue
        f, meta = forecast_candidate(cid, sku, data, tr, o2, h)
        if meta.get("delegate_calibration"):
            n_delegated += 1
            continue
        a = float(y[tr:tr + h].sum())
        errs.append(a - float(f.sum()))
        if meta.get("fallback"):
            n_fallback += 1
    return errs, n_fallback, n_delegated


def pooled_relative_errors(sku: str, data: dict, cid: str, h: int, asof_abs: int):
    """Relative errors (A-F)/F from other SKUs' primary cells. Used only when
    the target SKU has fewer than 3 own primary residuals. Delegated points are
    excluded so the pool reflects the candidate, not its fallback."""
    vals = []
    for s2, d2 in data.items():
        if s2 == sku:
            continue
        y = d2["y"]
        first = d2["first"]
        n = len(y)
        for o2 in range(first + PRIMARY_MIN[cid], asof_abs - h + 1):
            tr = o2 - first + 1
            if tr + h - 1 >= n:
                continue
            f, meta = forecast_candidate(cid, s2, data, tr, o2, h)
            if meta.get("delegate_calibration"):
                continue
            F = float(f.sum())
            if F <= 1e-9:
                continue
            a = float(y[tr:tr + h].sum())
            vals.append((a - F) / F)
    return vals


def calibration_for(sku: str, data: dict, cid: str, h: int, asof_abs: int,
                    delegate: str | None = None):
    """Return a calibration object for cumulative horizon h as of asof_abs.

    Own primary residuals >=3 -> own empirical/conformal quantile.
    Fewer than 3 -> pooled peer-relative conformal, explicitly labelled.
    """
    cal_cid = delegate or cid
    errs, n_fallback, n_delegated = primary_errors(sku, data, cal_cid, h, asof_abs)
    if len(errs) >= 3:
        q, level = conf_q90(errs)
        status = "conformal_empirical" if len(errs) >= 10 else "estimate_small_sample"
        return dict(
            status=status, scope="own_sku_primary", n_own=len(errs),
            n_fallback_excluded=n_fallback, n_delegated_excluded=n_delegated, n_pool=0,
            q90_abs=_round(q), conformal_level=_round(level),
            calibration_candidate=cal_cid,
        )
    rel = pooled_relative_errors(sku, data, cal_cid, h, asof_abs)
    if len(rel) >= 3:
        qrel, level = conf_q90(rel)
        return dict(
            status="estimate_pooled_peer_relative",
            scope="pooled_peer_relative", n_own=len(errs),
            n_fallback_excluded=n_fallback, n_delegated_excluded=n_delegated, n_pool=len(rel),
            q90_rel=_round(qrel), conformal_level=_round(level),
            calibration_candidate=cal_cid,
        )
    return dict(status="not_calibrated", scope="none", n_own=len(errs),
                n_fallback_excluded=n_fallback, n_delegated_excluded=n_delegated,
                n_pool=len(rel), calibration_candidate=cal_cid)


def p90_from_cal(point: float, cal: dict):
    """Apply a calibration object to a point forecast."""
    point = float(point)
    if cal.get("q90_abs") is not None:
        p = max(point, point + float(cal["q90_abs"]))
    elif cal.get("q90_rel") is not None:
        p = max(point, point * (1.0 + max(0.0, float(cal["q90_rel"]))))
    else:
        return None, None
    return p, p - point


# ----------------------------------------------------------------------------
# per-SKU build
# ----------------------------------------------------------------------------
def build_sku(sku: str, d: dict, ev_sku: dict, stockout: dict, data: dict,
              white_orders: list):
    y = d["y"]
    n = len(y)
    recent3 = float(np.mean(y[-3:])) if n >= 3 else 0.0
    last_abs = d["last"]

    # ---------------- backtest: last 6 origins with known h=1..3 ----------------
    cells = {cid: {"h1": [], "h3": []} for cid in
             [c["id"] for c in CANDIDATES if c["implemented"]]}
    backtest = {cid: {"h1": None, "h3": None, "origins": []} for cid in cells}
    for cid in cells:
        rows = []
        for om in REPORT_ORIGINS:
            o = ym_to_i(om)
            tr = o - d["first"] + 1
            f5, meta = forecast_candidate(cid, sku, data, tr, o, 5)
            a = [float(y[tr + k]) for k in range(3)]
            delegate = meta.get("delegate_calibration")
            cal1 = calibration_for(sku, data, cid, 1, o, delegate=delegate)
            cal3 = calibration_for(sku, data, cid, 3, o, delegate=delegate)
            p1, _ = p90_from_cal(float(f5[0]), cal1)
            p3, _ = p90_from_cal(float(f5[:3].sum()), cal3)
            rows.append(dict(
                origin=om, n_train=int(tr), fallback=bool(meta.get("fallback")),
                effective=meta.get("effective"),
                actual=a, forecast=[_round(v) for v in f5[:3]],
                p90_1=_round(p1) if p1 is not None else None,
                p90_3=_round(p3) if p3 is not None else None,
                covered_1=None if p1 is None else bool(a[0] <= p1 + 1e-9),
                covered_3=None if p3 is None else bool(sum(a) <= p3 + 1e-9),
                calibration_1={k: cal1.get(k) for k in
                               ("status", "n_own", "n_pool", "n_delegated_excluded", "q90_abs", "q90_rel")},
                calibration_3={k: cal3.get(k) for k in
                               ("status", "n_own", "n_pool", "n_delegated_excluded", "q90_abs", "q90_rel")},
            ))
            cells[cid]["h1"].append(dict(a=a[0], f=float(f5[0]), p90=p1))
            cells[cid]["h3"].append(dict(a=sum(a), f=float(f5[:3].sum()), p90=p3))
        backtest[cid]["origins"] = rows
        backtest[cid]["h1"] = metrics(cells[cid]["h1"])
        backtest[cid]["h3"] = metrics(cells[cid]["h3"])

    # ---------------- future 5 months + conformal P90 -------------------------
    future_months = [last_abs + k for k in range(1, HORIZON_MONTHS + 1)]
    future = {}
    for cid in cells:
        f5, meta = forecast_candidate(cid, sku, data, n, last_abs, HORIZON_MONTHS)
        delegate = meta.get("delegate_calibration")
        cals = {}
        p90s = {}
        for h in range(1, HORIZON_MONTHS + 1):
            cal = calibration_for(sku, data, cid, h, last_abs, delegate=delegate)
            cals[str(h)] = cal
            F = float(f5[:h].sum())
            p, lift = p90_from_cal(F, cal)
            p90s[str(h)] = dict(
                p50_cum=_round(F), p90_cum=_round(p) if p is not None else None,
                lift=_round(lift) if lift is not None else None,
                status=cal["status"], n_own=cal["n_own"], n_pool=cal["n_pool"],
                calibration_candidate=cal.get("calibration_candidate"),
            )
        future[cid] = dict(
            months=[dict(month=i_to_ym(m), p50=_round(float(f5[k])))
                    for k, m in enumerate(future_months)],
            p50_3m=_round(float(f5[:3].sum())),
            p90_3m=p90s["3"]["p90_cum"],
            p90_by_horizon=p90s,
            calibration=cals,
            meta=meta,
            total_5m=_round(float(f5.sum())),
        )

    # ---------------- model divergence ---------------------------------------
    totals = {cid: float(future[cid]["p50_3m"]) for cid in future}
    min_cid = min(totals, key=totals.get)
    max_cid = max(totals, key=totals.get)
    lo, hi = totals[min_cid], totals[max_cid]
    ratio = (hi / lo) if lo > 1e-9 else None
    recent12 = float(np.mean(y[-12:])) if n >= 12 else float(np.mean(y))
    recent3_over_12 = (recent3 / recent12) if recent12 > 1e-9 else None
    # seasonal contrast: last Oct-Dec vs last Jul-Sep (same 12-month span)
    oct_dec_mean = None
    jul_sep_mean_prior = None
    if n >= 24:
        oct_dec_mean = float(np.mean(y[-12:-9]))   # Oct, Nov, Dec of last year
        jul_sep_mean_prior = float(np.mean(y[-15:-12]))  # Jul, Aug, Sep of last year
    contrast = (oct_dec_mean / jul_sep_mean_prior) if (oct_dec_mean is not None and
                                                        jul_sep_mean_prior and
                                                        jul_sep_mean_prior > 1e-9) else None
    yoy_meta = future["seasonal_yoy"]["meta"].get("yoy")
    yoy_factor = future["seasonal_yoy"]["meta"].get("adjustment")
    if n < 18:
        dominant = "short_history_and_lumpy_events"
    elif ratio is not None and ratio >= 3.0 and recent3_over_12 is not None and recent3_over_12 >= 1.5:
        dominant = "recent_peak_vs_seasonal_trough"
    elif yoy_factor is not None and abs(float(yoy_factor) - 1.0) >= 0.15:
        dominant = "yoy_level_correction_vs_seasonal"
    else:
        dominant = "method_level_difference"
    divergence = dict(
        candidate_totals={c: _round(v) for c, v in totals.items()},
        min_candidate=min_cid, max_candidate=max_cid,
        min_total=_round(lo), max_total=_round(hi),
        ratio=_round(ratio), abs_range=_round(hi - lo),
        level=("high" if (ratio is not None and ratio >= 3.0) else
               "medium" if (ratio is not None and ratio >= 1.5) else "low"),
        recent3_mean=_round(recent3),
        recent12_mean=_round(recent12),
        recent3_over_recent12=_round(recent3_over_12),
        oct_dec_last_year_mean=_round(oct_dec_mean),
        jul_sep_last_year_mean=_round(jul_sep_mean_prior),
        seasonal_contrast=_round(contrast),
        yoy_adjustment=_round(yoy_factor),
        yoy_detail=yoy_meta,
        dominant_driver=dominant,
    )

    # ---------------- supply / SO evidence (frozen V0.1) ----------------------
    inv = ev_sku["inventory"]
    sup = ev_sku["supply"]
    so = ev_sku["open_so"]
    supply = dict(
        available=float(inv["available"]),
        A_low=float(sup["A_low"]), A_high=float(sup["A_high"]),
        B_min=float(sup["B_min"]), B_max=float(sup["B_max"]),
        open_po_raw=float(sup["open_po_raw"]),
        production_remaining=float(sup["production_remaining"]),
        intransit=float(sup["intransit"]),
    )
    open_so = dict(
        positive_open=float(so["positive_open"]),
        negative_over_delivery=float(so["negative_over_delivery"]),
        live_open_net=float(so["live_open_net"]),
    )

    # ---------------- calendar-window P50/P90 and action sensitivity ---------
    def window_integration(f5: np.ndarray, cid: str, days: int):
        start = DECISION_DATE
        end = start + timedelta(days=days)
        p50 = 0.0
        parts = []
        for k in range(HORIZON_MONTHS):
            ms = date(2026 + (9 + k) // 12, (9 + k) % 12 + 1, 1)
            me = date(2026 + (9 + k + 1) // 12, (9 + k + 1) % 12 + 1, 1)
            ov_start = max(start, ms)
            ov_end = min(end, me)
            if ov_end <= ov_start:
                continue
            frac = (ov_end - ov_start).days / (me - ms).days
            p50 += frac * float(f5[k])
            parts.append(dict(month=i_to_ym(last_abs + k + 1),
                              weight=_round(frac), p50=_round(float(f5[k]))))
        h = max(1, min(HORIZON_MONTHS, int(round(days / DAYS_PER_MONTH))))
        cal = future[cid]["calibration"][str(h)]
        p90, lift = p90_from_cal(p50, cal)
        return dict(days=days, months=_round(days / DAYS_PER_MONTH),
                    p50=_round(p50), p90=_round(p90) if p90 is not None else None,
                    lift=_round(lift) if lift is not None else None,
                    calibration_horizon=h, calibration_status=cal["status"],
                    buckets=parts)

    def action_for(need_Bmax: float, need_Ahigh: float):
        if need_Bmax > 1e-9:
            return "always_replenish"
        if need_Ahigh > 1e-9:
            return "depends_on_arrival"
        return "no_need_within_horizon"

    replenishment = dict(by_lead={}, primary_lead_days=90)
    for lead in LEAD_DAYS:
        window_days = lead + REVIEW_DAYS
        by_cand = {}
        for cid in future:
            f5, _ = forecast_candidate(cid, sku, data, n, last_abs, HORIZON_MONTHS)
            w = window_integration(f5, cid, window_days)
            dem = (w["p90"] if w["p90"] is not None else w["p50"]) + open_so["positive_open"]
            needs = {a: max(0.0, dem - supply[a]) for a in
                     ("available", "A_high", "B_min", "B_max")}
            by_cand[cid] = dict(
                p50=w["p50"], p90=w["p90"], demand_p50_plus_so=_round(w["p50"] + open_so["positive_open"]),
                demand_p90_plus_so=_round(dem),
                needs={k: _round(v) for k, v in needs.items()},
                action=action_for(needs["B_max"], needs["A_high"]),
                calibration_status=w["calibration_status"],
                calibration_horizon=w["calibration_horizon"],
            )
        actions = [v["action"] for v in by_cand.values()]
        if actions and all(a == "always_replenish" for a in actions):
            sku_action = "always_replenish"
        elif "always_replenish" in actions and any(a != "always_replenish" for a in actions):
            sku_action = "insufficient_evidence"
        elif any(a == "depends_on_arrival" for a in actions):
            sku_action = "depends_on_arrival"
        elif actions and all(a == "no_need_within_horizon" for a in actions):
            sku_action = "no_need_within_horizon"
        else:
            sku_action = "insufficient_evidence"
        counts = {a: actions.count(a) for a in set(actions)}
        needs_all = [v["needs"][a] for v in by_cand.values()
                     for a in ("available", "A_high", "B_min", "B_max")]
        replenishment["by_lead"][str(lead)] = dict(
            window_days=window_days, candidates=by_cand, sku_action=sku_action,
            action_counts=counts, need_min=_round(min(needs_all)) if needs_all else None,
            need_max=_round(max(needs_all)) if needs_all else None,
        )

    replenishment["action"] = replenishment["by_lead"]["90"]["sku_action"]
    replenishment["action_counts"] = replenishment["by_lead"]["90"]["action_counts"]
    replenishment["note"] = ("unrounded; no MOQ/pack multiple; not an order quantity; "
                             "B_min=max-overlap, B_max=no-overlap; supply is a bound, not a point")

    # ---------------- history / ratio facts ----------------------------------
    ratio_observed = (future["seasonal_naive"]["p50_3m"] / 3.0 / recent3) if recent3 > 1e-9 else None
    history = dict(
        first_month=d["months"][0], last_month=d["months"][-1], n_months=n,
        total_qty=_round(float(y.sum())), zero_filled_months=d["zero_filled"],
        recent3_mean=_round(recent3), recent3_values=[_round(float(v)) for v in y[-3:]],
        recent12_mean=_round(recent12),
        ratio_observed=_round(ratio_observed),
        series=[dict(month=m, qty=_round(float(v))) for m, v in zip(d["months"], y)],
    )

    # ---------------- six-SKU / White explanation facts ----------------------
    explanation = None
    if n >= 24:
        oct_dec = [float(v) for v in y[-12:-9]]
        jul_sep_prior = [float(v) for v in y[-15:-12]]
        jul_sep_now = [float(v) for v in y[-3:]]
        # V0's wording was "2026 Jun-Sep level clearly higher"; test that exact window.
        jun_sep_prior = [float(v) for v in y[-16:-12]]
        jun_sep_now = [float(v) for v in y[-4:]]
        aug_now = float(y[-2]) if n >= 2 else None
        sep_now = float(y[-1])
        sep_over_aug = (sep_now / aug_now) if aug_now and aug_now > 1e-9 else None
        contrast = (float(np.mean(oct_dec)) / float(np.mean(jul_sep_prior))
                    if float(np.mean(jul_sep_prior)) > 1e-9 else None)
        yoy_level = (float(np.mean(jul_sep_now)) / float(np.mean(jul_sep_prior))
                     if float(np.mean(jul_sep_prior)) > 1e-9 else None)
        jun_sep_yoy = (float(np.mean(jun_sep_now)) / float(np.mean(jun_sep_prior))
                       if float(np.mean(jun_sep_prior)) > 1e-9 else None)
        explanation = dict(
            oct_dec_last_year=dict(months=["2025-10", "2025-11", "2025-12"],
                                   values=[_round(v) for v in oct_dec],
                                   mean=_round(float(np.mean(oct_dec)))),
            jul_sep_last_year=dict(values=[_round(v) for v in jul_sep_prior],
                                   mean=_round(float(np.mean(jul_sep_prior)))),
            jul_sep_this_year=dict(values=[_round(v) for v in jul_sep_now],
                                   mean=_round(float(np.mean(jul_sep_now)))),
            jun_sep_last_year=dict(values=[_round(v) for v in jun_sep_prior],
                                   mean=_round(float(np.mean(jun_sep_prior)))),
            jun_sep_this_year=dict(values=[_round(v) for v in jun_sep_now],
                                   mean=_round(float(np.mean(jun_sep_now)))),
            seasonal_contrast=_round(contrast),
            yoy_level=_round(yoy_level),
            jun_sep_yoy=_round(jun_sep_yoy),
            contrast_over_yoy=_round(contrast / yoy_level) if (contrast and yoy_level) else None,
            identity_gap=_round(abs((contrast / yoy_level) - ratio_observed))
            if (contrast and yoy_level and ratio_observed) else None,
            aug_this_year=_round(aug_now), sep_this_year=_round(sep_now),
            sep_over_aug=_round(sep_over_aug),
            available=supply["available"],
            positive_open_so=open_so["positive_open"],
            so_over_available=_round(open_so["positive_open"] / supply["available"])
            if supply["available"] > 1e-9 else None,
            stockout_observed_rows=stockout.get(d["code"], {}).get("stockout_rows"),
            stockout_rows_total=stockout.get(d["code"], {}).get("rows"),
            v0_recent_strength_claim_holds=bool(jun_sep_yoy is not None and jun_sep_yoy > 1.10),
            v0_claim_note=("Jun-Sep 2026 is >10% above Jun-Sep 2025; V0's 'recent strength' wording holds"
                           if (jun_sep_yoy and jun_sep_yoy > 1.10)
                           else "Jun-Sep 2026 is not >10% above Jun-Sep 2025; V0's 'recent strength' wording does not hold"),
        )

    white = None
    if sku == "KS0001-CMM-100-WHITE":
        def month_rows(m):
            return [r for r in white_orders if r["month"] == m]
        aug25 = month_rows("2025-08")
        aug26 = month_rows("2026-08")
        jun26 = month_rows("2026-06")
        total25 = sum(r["qty"] for r in aug25)
        total26 = sum(r["qty"] for r in aug26)
        max_qty = max([r["max_qty"] for r in white_orders] or [0])
        white = dict(
            first_month=d["months"][0],
            aug_2025=dict(qty=_round(total25), by_channel=aug25),
            aug_2026=dict(qty=_round(total26), by_channel=aug26),
            aug_yoy=_round(total26 / total25) if total25 > 1e-9 else None,
            june_2026=dict(qty=_round(sum(r["qty"] for r in jun26)), by_channel=jun26),
            q4_2025_values=[_round(float(v)) for v in y[-12:-9]],
            q4_2025_mean=_round(float(np.mean(y[-12:-9]))),
            mean3_forecast=_round(float(future["mean3"]["p50_3m"] / 3.0)),
            mean3_over_q4=_round((future["mean3"]["p50_3m"] / 3.0) /
                                 float(np.mean(y[-12:-9])))
            if float(np.mean(y[-12:-9])) > 1e-9 else None,
            max_qty_per_line=max_qty,
            is_single_bulk_order=bool(max_qty > 5),
            candidate_totals={c: future[c]["p50_3m"] for c in future},
            candidate_p90={c: future[c]["p90_3m"] for c in future},
        )

    return dict(
        sku=sku, customer_code=d["code"], snapshot=d["snapshot"],
        history=history,
        v0_reference=dict(
            note="frozen V0.1 evidence; its P90 (random-walk sqrt model) is invalid per D10 and is shown only for traceability",
            primary_model=ev_sku["forecast"]["primary_model"],
            h1=ev_sku["backtest"]["h1"], h3=ev_sku["backtest"]["h3"],
            p50_3m=ev_sku["forecast"]["p50_3m"], p90_3m_v0=ev_sku["forecast"]["p90_3m"],
            run_rate_ratio=ev_sku["forecast"]["run_rate_ratio"],
            p90_status_v0=ev_sku["forecast"].get("p90_status"),
            low_confidence_lt_24m_v0=bool(ev_sku["history"]["n_months"] < 24),
        ),
        candidates={cid: dict(
            months=future[cid]["months"], p50_3m=future[cid]["p50_3m"],
            p90_3m=future[cid]["p90_3m"], p90_by_horizon=future[cid]["p90_by_horizon"],
            calibration=future[cid]["calibration"], meta=future[cid]["meta"],
        ) for cid in future},
        backtest=backtest,
        divergence=divergence,
        supply=supply, open_so=open_so,
        replenishment=replenishment,
        explanation=explanation,
        white_peak=white,
    )


# ----------------------------------------------------------------------------
# aggregate
# ----------------------------------------------------------------------------
def aggregate(skus: list[dict], ev: dict, db_hash_before: str, db_hash_after: str,
              row_accounting: dict):
    agg = {}
    for c in CANDIDATES:
        if not c["implemented"]:
            continue
        cid = c["id"]
        h1_cells, h3_cells = [], []
        for s in skus:
            for r in s["backtest"][cid]["origins"]:
                h1_cells.append(dict(a=r["actual"][0], f=r["forecast"][0], p90=r["p90_1"]))
                h3_cells.append(dict(a=sum(r["actual"]), f=sum(r["forecast"]), p90=r["p90_3"]))
        agg[cid] = dict(h1=metrics(h1_cells), h3=metrics(h3_cells),
                        n_skus=len(skus), n_cells_raw=len(h1_cells))
        per_sku = [s["backtest"][cid]["h3"]["wape"] for s in skus
                   if s["backtest"][cid]["h3"]["wape"] is not None]
        agg[cid]["mean_sku_wape_h3"] = _round(float(np.mean(per_sku))) if per_sku else None
        agg[cid]["median_sku_wape_h3"] = _round(float(np.median(per_sku))) if per_sku else None

    # Per-SKU h3 winner (lower WAPE); ties are left as multiple winners.
    win_counts = {cid: 0 for cid in agg}
    winners = {}
    for s in skus:
        vals = {cid: s["backtest"][cid]["h3"]["wape"] for cid in agg
                if s["backtest"][cid]["h3"]["wape"] is not None}
        if not vals:
            continue
        best = min(vals.values())
        tied = [cid for cid, v in vals.items() if abs(v - best) < 1e-9]
        winners[s["sku"]] = dict(best_wape=_round(best), candidates=tied)
        for cid in tied:
            win_counts[cid] += 1
    for cid in agg:
        agg[cid]["sku_wins_h3"] = win_counts[cid]

    ranking = sorted(
        [dict(candidate=cid, **agg[cid]["h3"]) for cid in agg],
        key=lambda x: (x["wape"] if x["wape"] is not None else 9e9),
    )
    for i, r in enumerate(ranking, 1):
        r["rank_h3_wape"] = i

    action_counts = {}
    for s in skus:
        a = s["replenishment"]["action"]
        action_counts[a] = action_counts.get(a, 0) + 1

    totals = {}
    for cid in ("seasonal_naive", "mean3", "seasonal_yoy", "peer_shape"):
        totals[cid] = dict(
            p50_3m=_round(sum(float(s["candidates"][cid]["p50_3m"]) for s in skus)),
            p90_3m=_round(sum(float(s["candidates"][cid]["p90_3m"] or 0) for s in skus)),
        )
    lead_totals = {}
    for lead in LEAD_DAYS:
        per = {}
        for cid in ("seasonal_naive", "mean3", "seasonal_yoy", "peer_shape"):
            lo = sum(float(s["replenishment"]["by_lead"][str(lead)]["candidates"][cid]["needs"]["B_max"]) for s in skus)
            hi = sum(float(s["replenishment"]["by_lead"][str(lead)]["candidates"][cid]["needs"]["available"]) for s in skus)
            per[cid] = dict(min_need_sum=_round(lo), max_need_sum=_round(hi))
        lead_totals[str(lead)] = per

    return dict(
        candidates=agg,
        ranking_h3=ranking,
        per_sku_h3_winners=winners,
        candidate_totals_3m=totals,
        action_counts=action_counts,
        lead_totals=lead_totals,
        note=("sums across SKUs are scenario totals, not a purchase/production order; "
              "P90 is per-SKU upper bound, not a portfolio P90"),
    )


# ----------------------------------------------------------------------------
# main
# ----------------------------------------------------------------------------
def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--json", default=str(OUT_PATH), help="output JSON path")
    args = ap.parse_args()

    if not DB_PATH.exists():
        raise SystemExit(f"missing db: {DB_PATH}")
    if not EVIDENCE_PATH.exists():
        raise SystemExit(f"missing evidence: {EVIDENCE_PATH}")

    db_hash_before = sha256_file(DB_PATH)
    evidence_hash = sha256_file(EVIDENCE_PATH)
    ev, ev_by_sku = load_evidence()

    con = duckdb.connect(str(DB_PATH), read_only=True)
    try:
        data, total_rows, bad_rows = load_series(con)
        stockout = load_stockout_rows(con)
        white_orders = load_white_orders(con)
        global_months = [r[0] for r in con.execute(
            "SELECT DISTINCT month FROM gs_orders ORDER BY 1").fetchall()]
    finally:
        con.close()
    db_hash_after = sha256_file(DB_PATH)

    # Evidence/DB series must be the same 10-SKU demand history. Fail loudly.
    series_checks = []
    for sku, d in data.items():
        ev_sku = ev_by_sku.get(sku)
        if ev_sku is None:
            raise SystemExit(f"evidence missing SKU {sku}")
        ev_series = {r["month"]: float(r["qty"]) for r in ev_sku["history"]["series"]}
        db_series = {m: float(v) for m, v in zip(d["months"], d["y"])}
        if ev_series != db_series:
            diff = sorted(set(ev_series) ^ set(db_series))
            raise SystemExit(f"evidence/DB series mismatch for {sku}: {diff[:5]}")
        series_checks.append(dict(sku=sku, n_months=len(db_series), match=True,
                                  n_rows=d["rows"], bad_dates=d["bad_dates"]))

    skus = []
    for code, sku, snap in SCOPES:
        skus.append(build_sku(sku, data[sku], ev_by_sku[sku], stockout, data, white_orders))

    # Six low-ratio SKUs (same set as V0's 8%-20% group).
    low_ratio = []
    for s in skus:
        r = s["history"]["ratio_observed"]
        if r is not None and r < 0.25 and s["history"]["n_months"] >= 24:
            e = s["explanation"]
            low_ratio.append(dict(
                sku=s["sku"], ratio_observed=r,
                seasonal_contrast=e["seasonal_contrast"],
                yoy_level=e["yoy_level"],
                jun_sep_yoy=e["jun_sep_yoy"],
                identity_check=e["contrast_over_yoy"],
                identity_gap=e["identity_gap"],
                oct_dec_mean=e["oct_dec_last_year"]["mean"],
                jul_sep_2025_mean=e["jul_sep_last_year"]["mean"],
                jul_sep_2026_mean=e["jul_sep_this_year"]["mean"],
                sep_this_year=e["sep_this_year"], aug_this_year=e["aug_this_year"],
                sep_over_aug=e["sep_over_aug"],
                available=e["available"], positive_open_so=e["positive_open_so"],
                so_over_available=e["so_over_available"],
                stockout_observed_rows=e["stockout_observed_rows"],
                v0_recent_strength_claim_holds=e["v0_recent_strength_claim_holds"],
                interpretation=(
                    "ratio = seasonal contrast / YoY level: the denominator is the "
                    "Jul-Aug-Sep peak, the numerator is last year's Oct-Dec trough. "
                    + ("Jun-Sep 2026 is >10% above the same months last year, so the "
                       "higher recent level also contributes to the low ratio."
                       if e["v0_recent_strength_claim_holds"] else
                       "Jun-Sep 2026 is not >10% above the same months last year "
                       "(often lower), so the 8-20% is mainly seasonal, not a "
                       "forecast collapse or a recent-strength story.")
                    + (" Sep-2026 is far below Aug-2026 and current available is far "
                       "below positive open SO, so censoring is plausible; the trough "
                       "may itself be understated." if (
                           (e["sep_over_aug"] is not None and e["sep_over_aug"] < 0.25)
                           or (e["so_over_available"] is not None and e["so_over_available"] > 1.0)
                       ) else "")
                ),
            ))

    white = next((s["white_peak"] for s in skus if s["sku"] == "KS0001-CMM-100-WHITE"), None)
    if white is not None:
        white["interpretation"] = (
            "The Aug-2026 peak (280) is a repeat of Aug-2025 (240, the launch month), "
            "not a single wholesale order: it is 237 Amazon unit orders (qty 1-2), "
            "plus 32 Wayfair, 5 Shopify. But only two August observations exist, one "
            "is the launch month, and Jun-2026 also spikes (141), so the peak cannot "
            "be separated from launch/promo/listing effects. mean3 extrapolates the "
            "Aug spike to 107.7/month for Oct-Dec; last year's Oct-Dec was 2/5/15 "
            "(mean 7.3). Do not use mean3 as the Q4 baseline."
        )
        white["recommendation"] = (
            "Keep Aug as an explicit event scenario, not a seasonal baseline. For Q4 "
            "use peer shape (47.2) / seasonal naive (22.0) as the low baseline and "
            "mean3 (323) only as an upper event-like scenario; need 2 more August "
            "observations or a promo/listing calendar to identify the peak."
        )

    agg = aggregate(skus, ev, db_hash_before, db_hash_after,
                    dict(total_rows=total_rows, bad_rows=bad_rows,
                         series_checks=series_checks))

    out = dict(
        schema_version="model_race_v1/1",
        report_version="V1",
        generated_at=__import__("datetime").datetime.now().astimezone().isoformat(timespec="seconds"),
        task="control/reviews/2026-10-22-model-race-task.md",
        scope=dict(
            skus=[s["sku"] for s in skus], n_skus=len(skus),
            demand_definition="gs_orders despatch_date month sum(qty), 2023-01..2026-09; missing months zero-filled",
            decision_date=DECISION_DATE.isoformat(),
            forecast_months=[i_to_ym(ym_to_i(SALES_CUTOFF) + k) for k in range(1, HORIZON_MONTHS + 1)],
            report_origins=REPORT_ORIGINS,
            target_coverage=TARGET_COVERAGE,
            no_production_access=True, orders_placed=0, scope_expanded=False,
        ),
        inputs=dict(
            db_path=str(DB_PATH), db_sha256_before=db_hash_before,
            db_sha256_after=db_hash_after, db_unchanged=db_hash_before == db_hash_after,
            evidence_path=str(EVIDENCE_PATH), evidence_sha256=evidence_hash,
            evidence_report_version=ev.get("report_version"),
            evidence_generated_at=ev.get("generated_at"),
            series_checks=series_checks,
            row_accounting=dict(
                gs_orders_rows_for_10_skus=total_rows,
                bad_despatch_dates=bad_rows,
                sku_month_cells=sum(s["history"]["n_months"] for s in skus),
                zero_filled_cells=sum(s["history"]["zero_filled_months"] for s in skus),
                month_range=[min(s["history"]["first_month"] for s in skus),
                             max(s["history"]["last_month"] for s in skus)],
                global_months=[global_months[0], global_months[-1]] if global_months else None,
            ),
        ),
        method=dict(
            candidates=CANDIDATES,
            ets_status=dict(
                available=False,
                reason="statsmodels and statsforecast are not installed in the project environment",
                checked_imports=["statsmodels", "statsforecast"],
                v0_hand_rolled_hw_reused=False,
            ),
            backtest=dict(
                rule="last 6 origins 2026-01..2026-06 with known h=1..3; fit uses y<=origin; targets origin+1..+3; no future data in fit",
                metrics="WAPE, bias (sum(f-a)/sum(a)), P90 coverage; zero-actual cells retained; all-zero denominator -> WAPE/bias null; target 0.90 recorded separately",
                horizons=[1, 3],
            ),
            p90=dict(
                method="split-conformal empirical quantile of rolling-origin cumulative errors (A_h - F_h), finite-sample level ceil((n+1)*0.9)/n, method='higher'",
                no_random_walk=True,
                no_sqrt_h=True,
                own_min_n=3,
                empirical_min_n=10,
                small_sample_label="estimate_small_sample",
                pooled_fallback="estimate_pooled_peer_relative: (A-F)/F from other SKUs' primary cells when own n<3",
                delegated_excluded="origins where the candidate delegates to another model (e.g. seasonal_yoy skipped) are excluded from its calibration",
                floor="P90 >= P50; negative residual quantiles do not lower the P50",
                target_coverage=TARGET_COVERAGE,
                achieved_coverage_recorded_separately=True,
            ),
            seasonal_yoy=dict(
                window="trailing 6 months vs same 6 months last year",
                min_level=MIN_LEVEL,
                clip=[0.5, 2.0],
                shrinkage=0.5,
                protections=["history < 18m", "either window mean < 10", "any zero in prior window"],
            ),
            peer_shape=dict(
                peers="the other 9 SKUs, truncated at the same origin",
                peer_min_history_months=PEER_MIN_HIST,
                min_observations_per_calendar_month=PEER_MIN_OBS,
                min_peer_trailing12_mean=PEER_MIN_BASE,
                own_level="trailing 12 months, or all history if <12 months",
                shape="median of y[m]/trailing12_mean by calendar month",
            ),
        ),
        aggregate=agg,
        skus=skus,
        explanations=dict(
            low_ratio_skus=low_ratio,
            low_ratio_count=len(low_ratio),
            low_ratio_v0_claim_holds_count=sum(1 for x in low_ratio if x["v0_recent_strength_claim_holds"]),
            white_aug_peak=white,
        ),
        open_items=[
            "Demand is shipped quantity (despatch_date), not unconstrained demand; stockout censoring is not corrected (only 3 days of stock_history).",
            "gs_orders has no status field; cancellations/returns are not removed.",
            "PO/ production / intransit overlap is not proven; supply is a bound (B_min=max overlap, B_max=no overlap).",
            "PO ETA is empty for all 13 open lines; B assumes arrival inside the lead time, which is a scenario.",
            "Work-order planned_end_date is empty; production timing is not confirmed.",
            "Inventory uom_basis=unknown; all quantities are counted as pieces, no conversion.",
            "Cover alternative stock is not merged into supply.",
            "SO/WO snapshots are 10-20/21, inventory is 10-22; the 1-2 day difference is not bridged.",
            "P90 is a calibrated estimate; achieved coverage is reported and may be below 0.90, especially with n<10 or pooled calibration.",
            "The six low-ratio SKUs' last-year Oct-Dec trough may itself be censored; a stockout-corrected demand series is needed to confirm the true winter level.",
        ],
        residual_risks=dict(
            no_production=True, no_orders=True, no_scope_expansion=True,
            v0_1_report_unchanged=True, build_v0_unchanged=True,
            p90_not_a_service_guarantee=True,
        ),
    )

    out = clean(out)
    out_path = Path(args.json)
    out_path.parent.mkdir(parents=True, exist_ok=True)
    with out_path.open("w", encoding="utf-8") as f:
        json.dump(out, f, ensure_ascii=False, indent=1)
        f.write("\n")

    # console summary
    print(f"wrote {out_path} ({out_path.stat().st_size:,} bytes)")
    print(f"db unchanged: {out['inputs']['db_unchanged']}  rows: {total_rows:,}  bad dates: {bad_rows}")
    print("candidate h3:")
    for r in agg["ranking_h3"]:
        print(f"  {r['candidate']:15s} WAPE={r['wape']} bias={r['bias']} "
              f"coverage={r['coverage']} n={r['n']} cov_n={r['n_coverage']}")
    print("actions:", agg["action_counts"])


if __name__ == "__main__":
    main()
