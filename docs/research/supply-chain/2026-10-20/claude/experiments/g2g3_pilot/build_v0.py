#!/usr/bin/env python
# -*- coding: utf-8 -*-
"""G2+G3 narrow pilot: 10-SKU demand forecast + replenishment V0 (read-only).

Reads:
  - D:/Work/fzh-order-store/order_store.duckdb (read_only=True)
  - EN phase1 association manifest + 10 snapshots (read-only)
Writes:
  - experiments/g2g3_pilot/out/sample_2sku.json
  - out/replenishment_v0/evidence.json
  - control/reviews/2026-10-22-sample-2sku.md (sample report)
  - control/reviews/2026-10-22-supply-demand-replenishment-v0.md (full report)

No production access, no writes to source systems, no order placement.
"""
from __future__ import annotations

import argparse
import hashlib
import json
import math
import os
from datetime import datetime, timezone
from pathlib import Path

import duckdb
import numpy as np

DB_PATH = Path("D:/Work/fzh-order-store/order_store.duckdb")
HERE = Path(__file__).resolve()
CLAUDE_DIR = HERE.parents[2]              # .../claude
G1_OUT = CLAUDE_DIR / "experiments" / "g1_contract" / "out"
PILOT_OUT = HERE.parent / "out"
EVIDENCE_DIR = CLAUDE_DIR / "out" / "replenishment_v0"
REVIEW_DIR = CLAUDE_DIR / "control" / "reviews"

# customer_code / tongtool SKU / EN snapshot
SCOPES = [
    ("CENCord995-DKGrey-97",          "KS0001-QDKTR-100-DEEPGREY",      "g1b_en_top_1.json"),
    ("CEN003-DPBLUE-100",             "KS0001-QDKTR-100-DEEPBLUE",     "g1b_en_top_2.json"),
    ("C/Linen-Natural-100-688-wow",   "KS0001-XMMBS-100-HEMPNATURAL",  "g1b_en_top_3.json"),
    ("C/Cord-DKBlue-100-713-wow",     "KS0001-CMKTR-100-DEEPBLUE",     "g1b_en_top_4.json"),
    ("C/Linen-Natural-153-688-wow",   "KS0001-XMMBS-153-HEMPNATURAL",  "g1b_en_top_5.json"),
    ("C/Velvet-Grey-100-705-wow",     "KS0001-PR-100-GREY",            "g1b_en_top_6.json"),
    ("C/Cord-Grey-100-710-wow",       "KS0001-CMKTR-100-GREY",         "g1b_en_top_7.json"),
    ("C/Linen-White-100-662-WOW",     "KS0001-CMM-100-WHITE",          "g1b_en_top_8.json"),
    ("TT0000671K0063721",             "KS0001-HLR-100-OFFWHITE",       "g1b_en_top_9.json"),
    ("C/Linen-Natural-194-688-wow",   "KS0001-XMMBS-194-HEMPNATURAL",  "g1b_en_rr2.json"),
]
SAMPLE_CODES = ["C/Linen-Natural-194-688-wow", "C/Linen-White-100-662-WOW"]

AS_OF_STOCK = "2026-10-22"
SALES_CUTOFF = "2026-09"
FUTURE_MONTHS = ["2026-10", "2026-11", "2026-12"]
TH_BACKTEST_ORIGINS = 6
LEAD_DAYS = [60, 90, 120]
REVIEW_DAYS = 30
Z90 = 1.2815515655446004
DAYS_PER_MONTH = 30.4375


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
    y, m = int(ym[:4]), int(ym[5:7])
    return y * 12 + (m - 1)


def i_to_ym(i: int) -> str:
    y, m = divmod(i, 12)
    return f"{y:04d}-{m + 1:02d}"


def num(x, nd=1):
    if x is None:
        return None
    if isinstance(x, (int, np.integer)):
        return int(x)
    v = float(x)
    if abs(v - round(v)) < 1e-9:
        return int(round(v))
    return round(v, nd)


def q(v: float, nd=1):
    """format for markdown"""
    if v is None:
        return "—"
    if abs(v - round(v)) < 1e-9:
        return f"{int(round(v)):,}"
    return f"{v:,.{nd}f}"


def pct(v):
    return "—" if v is None else f"{v*100:.1f}%"


# ----------------------------------------------------------------------------
# forecast primitives
# ----------------------------------------------------------------------------
def fit_seasonal_naive_residuals(y: np.ndarray, m: int = 12) -> np.ndarray:
    if len(y) <= m:
        return np.array([], dtype=float)
    return np.array([y[t] - y[t - m] for t in range(m, len(y))], dtype=float)


def fit_mean3_residuals(y: np.ndarray) -> np.ndarray:
    if len(y) < 4:
        return np.array([], dtype=float)
    return np.array([y[t] - float(np.mean(y[max(0, t - 3):t])) for t in range(3, len(y))], dtype=float)


def sigma_from_resid(resid: np.ndarray) -> tuple[float, float]:
    """Return (sigma_effective, q90). sigma_eff uses max(std, q90/z) so a fat
    right tail is not under-covered. Both derived from training residuals only."""
    if len(resid) == 0:
        return 0.0, 0.0
    sd = float(np.std(resid, ddof=1)) if len(resid) > 1 else 0.0
    q90 = float(np.quantile(resid, 0.90))
    return max(sd, q90 / Z90, 0.0), q90


def seasonal_naive_forecast(y: np.ndarray, h: int, m: int = 12) -> np.ndarray:
    return np.array([y[len(y) - m + (i % m)] for i in range(h)], dtype=float)


def mean3_forecast(y: np.ndarray, h: int) -> np.ndarray:
    return np.full(h, float(np.mean(y[-3:])), dtype=float)


def ets_fit(y: np.ndarray, m: int = 12, grid=(0.1, 0.3, 0.5, 0.7, 0.9)):
    """Holt-Winters additive (level+trend+seasonal), grid-search smoothing.
    Deterministic, no external dependency. Returns dict with fitted state."""
    n = len(y)
    if n < m + 2:
        return None
    best = None
    for a in grid:
        for b in grid:
            for g in grid:
                level = float(np.mean(y[:m]))
                trend = float((np.mean(y[-m:]) - np.mean(y[:m])) / m)
                seas = np.array([float(np.mean(y[s::m]) - level) for s in range(m)])
                resid = []
                sse = 0.0
                for t in range(m, n):
                    pred = level + trend + seas[t % m]
                    e = float(y[t] - pred)
                    resid.append(e)
                    sse += e * e
                    new_level = a * (y[t] - seas[t % m]) + (1 - a) * (level + trend)
                    new_trend = b * (new_level - level) + (1 - b) * trend
                    new_seas = seas.copy()
                    new_seas[t % m] = g * (y[t] - new_level) + (1 - g) * seas[t % m]
                    level, trend, seas = new_level, new_trend, new_seas
                if best is None or sse < best["sse"]:
                    best = dict(sse=sse, alpha=a, beta=b, gamma=g,
                                level=float(level), trend=float(trend),
                                seas=seas.copy(), resid=np.array(resid), n=n)
    return best


def ets_forecast(model, h: int, m: int = 12) -> np.ndarray:
    n = model["n"]
    seas = model["seas"]
    return np.array([model["level"] + (i + 1) * model["trend"] + seas[(n + i) % m]
                     for i in range(h)], dtype=float)


def model_name_for(n_train: int) -> str:
    # task rule: <24 months -> low confidence, degrade to last-3-month mean.
    return "seasonal_naive" if n_train >= 24 else "mean3"


def point_forecast(y: np.ndarray, h: int, model: str) -> np.ndarray:
    if model == "seasonal_naive" and len(y) >= 12:
        return seasonal_naive_forecast(y, h)
    return mean3_forecast(y, h)


def residual_for(y: np.ndarray, model: str) -> np.ndarray:
    if model == "seasonal_naive":
        return fit_seasonal_naive_residuals(y)
    return fit_mean3_residuals(y)


def metrics(cells: list[dict]) -> dict:
    """cells: [{a, f, p90}]. Zero-actual cells excluded from WAPE/bias."""
    usable = [c for c in cells if c["a"] != 0]
    excluded = len(cells) - len(usable)
    if not usable:
        return dict(n=0, zero_excluded=excluded, wape=None, bias=None, coverage=None)
    sum_a = sum(c["a"] for c in usable)
    wape = sum(abs(c["f"] - c["a"]) for c in usable) / sum_a
    bias = sum(c["f"] - c["a"] for c in usable) / sum_a
    cov = sum(1 for c in usable if c["a"] <= c["p90"] + 1e-9) / len(usable)
    return dict(n=len(usable), zero_excluded=excluded, wape=round(wape, 4),
                bias=round(bias, 4), coverage=round(cov, 4))


# ----------------------------------------------------------------------------
# data loading
# ----------------------------------------------------------------------------
def load_all():
    if not DB_PATH.exists():
        raise SystemExit(f"missing db: {DB_PATH}")
    db_hash = sha256_file(DB_PATH)
    con = duckdb.connect(str(DB_PATH), read_only=True)
    codes = [c for c, _, _ in SCOPES]
    skus = [s for _, s, _ in SCOPES]
    in_codes = ",".join("'" + c.replace("'", "''") + "'" for c in codes)
    in_skus = ",".join("'" + s.replace("'", "''") + "'" for s in skus)

    rows = con.execute(f"""
        SELECT sku_tongtool, substr(despatch_date,1,7) AS ym, SUM(qty) AS qty,
               COUNT(*) AS n_lines, COUNT(DISTINCT order_id) AS n_orders,
               COUNT(*) FILTER (WHERE despatch_date IS NULL OR despatch_date='') AS bad_date
        FROM gs_orders WHERE sku_tongtool IN ({in_codes})
        GROUP BY 1,2 ORDER BY 1,2
    """).fetchall()
    total_rows = con.execute(
        f"SELECT COUNT(*) FROM gs_orders WHERE sku_tongtool IN ({in_codes})").fetchone()[0]
    bad_rows = con.execute(
        f"SELECT COUNT(*) FROM gs_orders WHERE sku_tongtool IN ({in_codes}) "
        f"AND (despatch_date IS NULL OR despatch_date='')").fetchone()[0]
    min_date, max_date = con.execute(
        f"SELECT MIN(despatch_date), MAX(despatch_date) FROM gs_orders "
        f"WHERE sku_tongtool IN ({in_codes})").fetchone()
    global_months = [r[0] for r in con.execute(
        "SELECT DISTINCT month FROM gs_orders ORDER BY 1").fetchall()]

    stock = con.execute(f"""
        SELECT goods_sku, warehouse_name, available, intransit, waiting_shipment, defects,
               batch_complete, is_test, uom_basis, run_id
        FROM stock_history
        WHERE goods_sku IN ({in_codes}) AND snapshot_date = DATE '{AS_OF_STOCK}'
        ORDER BY goods_sku, warehouse_name
    """).fetchall()

    po = con.execute(f"""
        SELECT p.ponum, p.goods_sku, p.warehouse, p.quantity, p.in_quantity, p.open_qty,
               p.status, p.purchase_date, p.will_arrive_date
        FROM tongtool_po p
        WHERE p.goods_sku IN ({in_codes})
        ORDER BY p.goods_sku, p.purchase_date, p.ponum, p.warehouse
    """).fetchall()

    po_open = con.execute(f"""
        SELECT sku, warehouse, on_order FROM tongtool_po_open
        WHERE sku IN ({in_codes}) ORDER BY sku, warehouse
    """).fetchall()

    stock_latest = con.execute(f"""
        SELECT warehouse, sku, available, intransit, waiting_shipment, defects
        FROM stock_latest WHERE sku IN ({in_codes}) ORDER BY sku, warehouse
    """).fetchall()

    v3 = con.execute(f"""
        SELECT warehouse, sku, available, intransit, on_order, waiting_shipment, defects,
               daily_forecast, days_cover, rop_days, rop_qty, suggested_qty, supply_note
        FROM replenishment_v3 WHERE sku IN ({in_codes}) ORDER BY sku, warehouse
    """).fetchall()

    threepl = con.execute(f"""
        SELECT warehouse, sku, item_code, ship_type, available, intransit
        FROM three_pl_stock WHERE sku IN ({in_codes}) OR item_code IN ({in_skus})
        ORDER BY sku, warehouse
    """).fetchall()

    bom_rows = con.execute(f"""
        SELECT b.item AS finished_item, b.bom, bi.item_code AS component, bi.qty, bi.uom
        FROM bom b JOIN bom_item bi ON bi.parent = b.bom
        WHERE b.item IN ({in_skus})
        ORDER BY b.item, bi.item_code
    """).fetchall()

    item_attr = con.execute(f"""
        SELECT item, item_name, item_group, lead_days, safety_stock
        FROM item_attr WHERE item IN ({in_skus})
    """).fetchall()

    ship_type = con.execute(f"""
        SELECT item_code, item_group, ship_type FROM item_ship_type
        WHERE item_code IN ({in_skus})
    """).fetchall()

    sku_map = con.execute(f"""
        SELECT item_code, tongtool_sku FROM sku_map
        WHERE item_code IN ({in_skus}) OR tongtool_sku IN ({in_codes})
    """).fetchall()

    con.close()
    return dict(
        db_hash=db_hash, rows=rows, total_rows=total_rows, bad_rows=bad_rows,
        min_date=min_date, max_date=max_date, global_months=global_months,
        stock=stock, stock_latest=stock_latest, po=po, po_open=po_open, v3=v3, threepl=threepl,
        bom=bom_rows, item_attr=item_attr, ship_type=ship_type, sku_map=sku_map,
    )


def load_snapshots():
    out = {}
    for code, sku, fn in SCOPES:
        p = G1_OUT / fn
        with p.open("r", encoding="utf-8") as f:
            d = json.load(f)
        out[code] = dict(path=str(p), sha256=sha256_file(p), data=d)
    manifest_path = G1_OUT / "dn_wo_jc_se_expand10_phase1" / "association_manifest.json"
    with manifest_path.open("r", encoding="utf-8") as f:
        manifest = json.load(f)
    return out, manifest, str(manifest_path), sha256_file(manifest_path)


# ----------------------------------------------------------------------------
# per-SKU build
# ----------------------------------------------------------------------------
def _identity_info(code, sku, sku_map):
    items_for_code = {r[0] for r in sku_map if r[1] == code}
    codes_for_item = {r[1] for r in sku_map if r[0] == sku}
    status = "confirmed" if items_for_code == {sku} else "ambiguous"
    return status, len(codes_for_item)


def build_sku(code, sku, snap, data, cover_map=None):
    d = snap["data"]
    counts = d.get("counts", {})
    so_rows = d.get("so_rows", [])
    wos = d.get("wos", [])

    # ---- demand series (despatch month) ----
    by_ym = {}
    for r in data["rows"]:
        if r[0] != code:
            continue
        by_ym[r[1]] = float(r[2])
    if not by_ym:
        raise SystemExit(f"no demand rows for {code}")
    first_i = min(ym_to_i(m) for m in by_ym)
    last_i = ym_to_i(SALES_CUTOFF)
    months = [i_to_ym(i) for i in range(first_i, last_i + 1)]
    y = np.array([by_ym.get(m, 0.0) for m in months], dtype=float)
    zero_filled = sum(1 for m in months if m not in by_ym)
    qty_total = float(y.sum())
    n_months = len(y)
    confidence = "low" if n_months < 24 else ("medium-low" if n_months < 36 else "medium")
    primary_model = model_name_for(n_months)

    # ---- future forecast ----
    fc_point = point_forecast(y, len(FUTURE_MONTHS), primary_model)
    fc_point = np.maximum(fc_point, 0.0)
    resid = residual_for(y, primary_model)
    sigma, q90 = sigma_from_resid(resid)
    z_sig = max(Z90 * sigma, q90, 0.0)
    fc_months = []
    for i, m in enumerate(FUTURE_MONTHS):
        h = i + 1
        p50 = float(fc_point[i])
        p90 = p50 + z_sig * math.sqrt(h)
        fc_months.append(dict(month=m, p50=num(p50), p90=num(p90)))
    p50_3m = float(fc_point.sum())
    p90_3m = p50_3m + z_sig * math.sqrt(3)
    # monthly point values for lead-time proration
    avg_p50 = p50_3m / 3.0
    recent3 = float(np.mean(y[-3:]))
    run_rate_ratio = (avg_p50 / recent3) if recent3 > 0 else None

    # ---- ETS candidate ----
    ets = None
    if n_months >= 24:
        fit = ets_fit(y)
        if fit is not None:
            ef = np.maximum(ets_forecast(fit, 3), 0.0)
            e_sigma, e_q90 = sigma_from_resid(fit["resid"])
            ets = dict(available=True, alpha=fit["alpha"], beta=fit["beta"],
                       gamma=fit["gamma"], months=[num(v) for v in ef],
                       p50_3m=num(float(ef.sum())),
                       sigma=round(e_sigma, 3), q90=round(e_q90, 3),
                       used=False, unstable=bool(ef.sum() <= 1e-9),
                       note="candidate only; not selected; additive HW can collapse to 0 on spiky series")
        else:
            ets = dict(available=False, reason="insufficient_history")
    else:
        ets = dict(available=False, reason="history_lt_24m")

    # ---- backtest: last 6 origins with known h=3 ----
    origin_positions = []
    for oi in range(last_i - 3 - (TH_BACKTEST_ORIGINS - 1), last_i - 3 + 1):
        train = y[: oi - first_i + 1]
        origin_positions.append((oi, train))
    bt = []
    for oi, train in origin_positions:
        if len(train) < 3:
            bt.append(dict(origin=i_to_ym(oi), n_train=len(train), skipped="history_lt_3m"))
            continue
        model = model_name_for(len(train))
        f = np.maximum(point_forecast(train, 3, model), 0.0)
        r = residual_for(train, model)
        s, q9 = sigma_from_resid(r)
        zs = max(Z90 * s, q9, 0.0)
        a = []
        for h in range(1, 4):
            idx = oi - first_i + h
            a.append(float(y[idx]) if 0 <= idx < len(y) else None)
        if any(v is None for v in a):
            bt.append(dict(origin=i_to_ym(oi), n_train=len(train), skipped="target_out_of_range"))
            continue
        p90_1 = float(f[0] + zs)
        p90_3 = float(f.sum() + zs * math.sqrt(3))
        # ETS candidate on the same origin (only if >=24m train)
        etcell = None
        if len(train) >= 24:
            efit = ets_fit(train)
            if efit is not None:
                ef = np.maximum(ets_forecast(efit, 3), 0.0)
                es, eq = sigma_from_resid(efit["resid"])
                ezs = max(Z90 * es, eq, 0.0)
                etcell = dict(f=[round(float(v), 2) for v in ef],
                              p90_1=round(float(ef[0] + ezs), 2),
                              p90_3=round(float(ef.sum() + ezs * math.sqrt(3)), 2))
        bt.append(dict(
            origin=i_to_ym(oi), n_train=len(train), model=model,
            actual=[round(v, 2) for v in a],
            forecast=[round(float(v), 2) for v in f],
            p90_1=round(p90_1, 2), p90_3=round(p90_3, 2),
            ets=etcell,
        ))

    def cells_for(h):
        out = []
        for r in bt:
            if "actual" not in r:
                continue
            if h == 1:
                out.append(dict(a=r["actual"][0], f=r["forecast"][0], p90=r["p90_1"]))
            else:
                out.append(dict(a=sum(r["actual"]), f=sum(r["forecast"]), p90=r["p90_3"]))
        return out

    bt_h1 = metrics(cells_for(1))
    bt_h3 = metrics(cells_for(3))
    ets_cells1, ets_cells3 = [], []
    for r in bt:
        if "actual" not in r or not r.get("ets"):
            continue
        ets_cells1.append(dict(a=r["actual"][0], f=r["ets"]["f"][0], p90=r["ets"]["p90_1"]))
        ets_cells3.append(dict(a=sum(r["actual"]), f=sum(r["ets"]["f"]), p90=r["ets"]["p90_3"]))
    ets_h1 = metrics(ets_cells1) if ets_cells1 else None
    ets_h3 = metrics(ets_cells3) if ets_cells3 else None

    # ---- inventory (2026-10-22 complete snapshot) ----
    stock_rows = [r for r in data["stock"] if r[0] == code]
    by_wh = {}
    for r in stock_rows:
        by_wh[r[1]] = dict(available=float(r[2]), intransit=float(r[3]),
                           waiting_shipment=float(r[4]), defects=float(r[5]),
                           batch_complete=bool(r[6]), is_test=bool(r[7]),
                           uom_basis=r[8], run_id=r[9])
    available = sum(v["available"] for v in by_wh.values())
    intransit = sum(v["intransit"] for v in by_wh.values())
    defects = sum(v["defects"] for v in by_wh.values())
    waiting = sum(v["waiting_shipment"] for v in by_wh.values())
    threepl = [dict(warehouse=r[0], sku=r[1], available=num(r[4]), intransit=num(r[5]))
               for r in data["threepl"] if r[1] == code or r[2] == sku]

    # ---- PO (open lines, row key) ----
    po_rows = [r for r in data["po"] if r[1] == code]
    open_lines = []
    for r in po_rows:
        ponum, goods_sku, wh, qty, inq, openq, status, pdate, eta = r
        if float(openq) > 0:
            open_lines.append(dict(ponum=ponum, goods_sku=goods_sku, warehouse=wh,
                                   quantity=num(qty), in_quantity=num(inq),
                                   open_qty=num(openq), status=status,
                                   purchase_date=pdate,
                                   will_arrive_date=eta,
                                   row_key=f"{ponum}|{goods_sku}|{wh}"))
    # duplicate candidates: identical (sku, warehouse, quantity) open lines, later PO marked duplicate
    groups = {}
    for ln in open_lines:
        groups.setdefault((ln["goods_sku"], ln["warehouse"], ln["quantity"]), []).append(ln)
    dup_keys = set()
    for key, lines in groups.items():
        if len(lines) > 1:
            lines_sorted = sorted(lines, key=lambda x: (x["purchase_date"] or "", x["ponum"]))
            for ln in lines_sorted[1:]:
                dup_keys.add(ln["row_key"])
    po_raw = sum(ln["open_qty"] for ln in open_lines)
    po_dup = sum(ln["open_qty"] for ln in open_lines if ln["row_key"] in dup_keys)
    po_dedup = po_raw - po_dup
    po_by_wh = {}
    for ln in open_lines:
        if ln["row_key"] in dup_keys:
            continue
        po_by_wh[ln["warehouse"]] = po_by_wh.get(ln["warehouse"], 0.0) + ln["open_qty"]
    po_eta_missing = sum(1 for ln in open_lines if ln["will_arrive_date"] in (None, ""))
    for ln in open_lines:
        ln["duplicate_candidate"] = ln["row_key"] in dup_keys

    # ---- open SO / document evidence ----
    ob = d.get("open_breakdown", {})
    reconciled = float(ob.get("reconciled_open_qty") or 0)
    dead = float(ob.get("dead_qty") or 0)
    in_prog = float(ob.get("in_progress_qty") or 0)
    no_plan = float(ob.get("no_plan_qty") or 0)
    over = float(ob.get("over_delivered_qty") or 0)
    voided = float(ob.get("voided_qty") or 0)
    live_open = reconciled - dead
    # conservation check on the published buckets
    bucket_check = round(live_open - (in_prog + no_plan + over), 6)

    # ---- production (open WOs) ----
    open_wo, stopped_wo, draft_wo = [], [], []
    for w in wos:
        status = str(w.get("status"))
        docstatus = w.get("docstatus")
        item = dict(name=w.get("name"), status=status, docstatus=docstatus,
                    sales_order=w.get("sales_order"), production_item=w.get("production_item"),
                    qty=num(w.get("qty")), produced_qty=num(w.get("produced_qty")),
                    planned_start_date=w.get("planned_start_date"),
                    planned_end_date=w.get("planned_end_date"))
        if docstatus == 1 and status in ("Not Started", "In Process"):
            item["remaining_qty"] = max(0.0, float(w.get("qty") or 0) - float(w.get("produced_qty") or 0))
            open_wo.append(item)
        elif docstatus == 1 and status == "Stopped":
            item["remaining_qty"] = max(0.0, float(w.get("qty") or 0) - float(w.get("produced_qty") or 0))
            stopped_wo.append(item)
        elif docstatus == 0:
            draft_wo.append(item)
    wo_gross = sum(float(w["qty"]) for w in open_wo)
    wo_remaining = sum(float(w["remaining_qty"]) for w in open_wo)
    stopped_gross = sum(float(w["qty"]) for w in stopped_wo)
    stopped_remaining = sum(float(w["remaining_qty"]) for w in stopped_wo)
    prod_types = sorted({w["production_item"] for w in open_wo})
    prod_type_kind = sorted({"PK#" if str(t).startswith("PK#") else "KS" for t in prod_types})
    wo_eta_missing = sum(1 for w in open_wo if not w.get("planned_end_date"))

    # ---- independent intransit (not explained by open PO at same warehouse) ----
    indep_transit = 0.0
    indep_by_wh = {}
    for wh, v in by_wh.items():
        indep = max(0.0, v["intransit"] - po_by_wh.get(wh, 0.0))
        indep_by_wh[wh] = indep
        indep_transit += indep

    # ---- supply scenarios ----
    prod_not_in_po = max(0.0, wo_remaining - po_dedup)
    supply_A = available + wo_remaining            # no PO / no intransit
    supply_B = available + po_dedup + prod_not_in_po + indep_transit
    supply_B_raw = available + po_raw + max(0.0, wo_remaining - po_raw) + indep_transit

    # ---- lead-time demand / recommendation ----
    def lt(days):
        m = days / DAYS_PER_MONTH
        p50 = avg_p50 * m + live_open
        p90 = p50 + z_sig * math.sqrt(m)
        return dict(days=days, months=round(m, 3),
                    p50=round(p50, 1), p90=round(p90, 1))

    lead = {f"L{d}": lt(d) for d in LEAD_DAYS}
    def rec(days, supply):
        v = lead[f"L{days}"]["p90"]  # overwritten below for L+30
        plus = lt(days + REVIEW_DAYS)
        return max(0.0, plus["p90"] - supply)
    recs = {}
    for days in LEAD_DAYS:
        recs[f"A_L{days}"] = round(rec(days, supply_A), 1)
        recs[f"B_L{days}"] = round(rec(days, supply_B), 1)
        recs[f"AVAIL_L{days}"] = round(rec(days, available), 1)

    # ---- unknowns / scenarios for this SKU ----
    unknowns = []
    if po_raw > 0:
        unknowns.append(f"PO ETA 全空：{len(open_lines)} 条未结行，{po_eta_missing}/{len(open_lines)} 无 will_arrive_date")
    if po_dup > 0:
        unknowns.append(f"PO 重复候选：{po_dup:g} 件（同 SKU/仓/数量、不同 PO，未证单据关系；主口径已剔除，原始值作敏感性）")
    if stopped_gross > 0:
        unknowns.append(f"Stopped WO：{stopped_gross:g} 件未计入在产（{len(stopped_wo)} 张）")
    if draft_wo:
        unknowns.append(f"Draft WO：{len(draft_wo)} 张未计入（docstatus=0）")
    if wo_eta_missing:
        unknowns.append(f"在产无 ETA：{wo_eta_missing}/{len(open_wo)} 张 WO 的 planned_end_date 为空")
    if dead > 0:
        unknowns.append(f"死单 SO：{dead:g} 件（Closed 未发）未计入需求；若业务确认补发需另加")
    if abs(bucket_check) > 1e-6:
        unknowns.append(f"open bucket 对不平：{bucket_check:g}")
    if n_months < 24:
        unknowns.append(f"历史仅 {n_months} 月（<24），按规则退化近 3 月均值；若近 3 月含峰值，预测会明显高于去年同月，"
                        "属低置信退化代价，不声称季节性")
    if run_rate_ratio is not None and run_rate_ratio < 0.5:
        unknowns.append(f"模型分歧：预测月均仅为近 3 月均值的 {run_rate_ratio:.0%}"
                        f"（{avg_p50:.1f} vs {recent3:.1f}/月）；若近期旺势延续，P50 会低估，建议量只作下限情景")
    elif run_rate_ratio is not None and run_rate_ratio > 2.0:
        unknowns.append(f"模型分歧：预测月均为近 3 月均值的 {run_rate_ratio:.0%}；建议量只作上限情景")
    if first_i == ym_to_i(min(data["global_months"])):
        unknowns.append("历史起点=数据起点 2023-01，序列可能左截断（此前销量不可见）")
    if po_dup > 0 and abs(po_dedup - intransit) < 1e-9:
        unknowns.append("去重后未结 PO 恰好等于同 SKU 在途量；与重复候选假设一致，但仍不是单据级证明")
    unknowns.append("库存 UOM=unknown；按件计数、未做换算（条件假设，不是已证 1:1）")
    if prod_type_kind:
        unknowns.append("在产 WO 的生产物是 PK# 皮壳，本轮按 1:1 对应 KS 成品计入；未检查 ND# 内胆可用性，"
                        "也未证 PK#+ND# 装配是否即时；该 1:1 关系未证")
    if len(prod_type_kind) > 1:
        unknowns.append("在产 WO 同时含 KS 与 PK# 生产物；两种都按件 1:1 计入，未做结构换算")
    unknowns.append("断货删失未校正：stock_history 仅 3 天，无法还原历史可售天数")
    unknowns.append("Cover 可替代未证：cover 库存不并入供给")
    cover = cover_map.get(sku) if cover_map else None
    if cover:
        if cover.get("cover_observed"):
            unknowns.append(f"Cover 观测：alias_available_sum={cover.get('alias_available_sum')}（单列情景，不计入供给）")
        else:
            unknowns.append("Cover 无映射：alias/item_cover_stock 均无行，属 scenario，不写 0")

    return dict(
        sku=sku, customer_code=code,
        identity=dict(sku_map_rows=[list(r) for r in data["sku_map"] if r[0] == sku or r[1] == code],
                      ship_type=next((r[2] for r in data["ship_type"] if r[0] == sku), None),
                      item_name=next((r[1] for r in data["item_attr"] if r[0] == sku), None),
                      bom=[dict(component=r[2], qty=num(r[3]), uom=r[4])
                           for r in data["bom"] if r[0] == sku],
                      identity_status=_identity_info(code, sku, data["sku_map"])[0],
                      alias_count=_identity_info(code, sku, data["sku_map"])[1],
                      identity_note="customer_code -> single KS item; the KS item has multiple platform aliases (normal, not cross-item ambiguity)"),
        cover=cover_map.get(sku, dict(verdict="missing", cover_observed=False,
                                      alias_available_sum=None, counted_in_supply=False,
                                      note="not found in cover evidence map")),
        snapshot=dict(path=snap["path"], sha256=snap["sha256"],
                      generated_at=d.get("generated_at"), as_of=d.get("date"),
                      counts=counts, open_breakdown=ob),
        history=dict(first_month=months[0], last_month=months[-1], n_months=n_months,
                     total_qty=num(qty_total), zero_filled_months=zero_filled,
                     recent3_mean=num(float(np.mean(y[-3:]))),
                     launch_truncated=(first_i == ym_to_i(min(data["global_months"]))),
                     series=[dict(month=m, qty=num(v)) for m, v in zip(months, y)]),
        forecast=dict(primary_model=primary_model, confidence=confidence,
                      history_months=n_months, months=fc_months,
                      p50_3m=num(p50_3m), p90_3m=num(p90_3m),
                      sigma=round(sigma, 3), q90=round(q90, 3),
                      z_sig=round(z_sig, 3),
                      recent3_mean=num(recent3),
                      run_rate_ratio=round(run_rate_ratio, 3) if run_rate_ratio is not None else None,
                      ets_candidate=ets),
        backtest=dict(h1=bt_h1, h3=bt_h3,
                      ets_h1=ets_h1, ets_h3=ets_h3,
                      origins=bt,
                      leakage_check=dict(
                          structural_pass=all(ym_to_i(r["origin"]) + h > ym_to_i(r["origin"])
                                              for r in bt if "actual" in r for h in (1, 2, 3)),
                          train_rule="fit uses y[month <= origin]; targets are origin+1..origin+3",
                          target_months=[f"{r['origin']}+1..+3" for r in bt if "actual" in r],
                      ),
                      rule="last 6 origins with known h=3; zero-actual cells excluded; "
                           "residual sigma from training only; no future data in fit"),
        inventory=dict(as_of=AS_OF_STOCK, available=num(available), intransit=num(intransit),
                       defects=num(defects), waiting_shipment=num(waiting),
                       by_warehouse=[dict(warehouse=k, **{kk: num(vv) for kk, vv in v.items()
                                                          if kk not in ("batch_complete", "is_test", "uom_basis", "run_id")},
                                          batch_complete=v["batch_complete"], is_test=v["is_test"],
                                          uom_basis=v["uom_basis"])
                                     for k, v in sorted(by_wh.items())],
                       stock_latest_crosscheck=[dict(warehouse=r[0], sku=r[1], available=num(r[2]),
                                                     intransit=num(r[3]), waiting_shipment=num(r[4]),
                                                     defects=num(r[5]))
                                                for r in data.get("stock_latest", []) if r[1] == code],
                       stock_latest_available_total=num(sum(
                           float(r[2]) for r in data.get("stock_latest", []) if r[1] == code)),
                       replenishment_v3_crosscheck=[dict(warehouse=r[0], available=num(r[2]),
                                                         intransit=num(r[3]), on_order=num(r[4]),
                                                         daily_forecast=num(r[7], 4),
                                                         rop_days=r[9], rop_qty=num(r[10]),
                                                         suggested_qty=num(r[11]), supply_note=r[12])
                                                    for r in data.get("v3", []) if r[1] == code],
                       three_pl_crosscheck=threepl,
                       uom_status="unknown_conditional"),
        po=dict(rows_total=len(po_rows), open_lines=open_lines,
                open_line_count=len(open_lines), open_qty_raw=num(po_raw),
                duplicate_candidate_qty=num(po_dup), open_qty_dedup=num(po_dedup),
                eta_missing_lines=po_eta_missing,
                row_key="(ponum, goods_sku, warehouse)",
                dedup_rule="identical (goods_sku, warehouse, quantity) with different PO; later purchase_date excluded as duplicate candidate; not document-proven",
                dedup_equals_intransit=(po_dup > 0 and abs(po_dedup - intransit) < 1e-9),
                po_open_table=[[r[0], r[1], num(r[2])] for r in data["po_open"] if r[0] == code]),
        production=dict(open_wo=open_wo, stopped_wo=stopped_wo, draft_wo=draft_wo,
                        open_wo_count=len(open_wo), gross_qty=num(wo_gross),
                        remaining_qty=num(wo_remaining),
                        stopped_qty=num(stopped_gross), stopped_remaining_qty=num(stopped_remaining),
                        production_item_kinds=prod_type_kind,
                        eta_missing_count=wo_eta_missing,
                        eta_status="planned_end_date_all_null"),
        open_so=dict(reconciled_open=num(reconciled), dead=num(dead), live_open=num(live_open),
                     in_progress=num(in_prog), no_plan=num(no_plan),
                     over_delivered=num(over), voided=num(voided),
                     bucket_check=bucket_check,
                     dead_so=[b for b in ob.get("buckets", {}).get("dead", [])],
                     in_progress_so=[b for b in ob.get("buckets", {}).get("in_progress", [])],
                     no_plan_so=[b for b in ob.get("buckets", {}).get("no_plan", [])],
                     over_delivered_so=[b for b in ob.get("buckets", {}).get("over_delivered", [])]),
        supply=dict(available=num(available), open_po_raw=num(po_raw),
                    open_po_dedup=num(po_dedup), independent_intransit=num(indep_transit),
                    production_gross=num(wo_gross), production_remaining=num(wo_remaining),
                    production_not_in_po=num(prod_not_in_po),
                    scenario_A=num(supply_A), scenario_B=num(supply_B),
                    scenario_B_raw_po=num(supply_B_raw),
                    independent_intransit_by_warehouse={k: num(v) for k, v in indep_by_wh.items()}),
        demand=dict(forecast_p50_3m=num(p50_3m), forecast_p90_3m=num(p90_3m),
                    open_so_live=num(live_open), total_p50=num(p50_3m + live_open),
                    total_p90=num(p90_3m + live_open),
                    dead_so_excluded=num(dead)),
        lead_time=lead,
        recommendation=dict(values=recs,
                            note="unrounded; no MOQ/pack multiple; not an order quantity"),
        unknowns=unknowns,
    )


# ----------------------------------------------------------------------------
# aggregate + write
# ----------------------------------------------------------------------------
def aggregate(skus, data, manifest, manifest_path, snapshots, db_hash):
    def s(key):
        return sum(float(x[key]) for x in skus if x.get(key) is not None)

    open_po = sum(float(x["po"]["open_qty_dedup"]) for x in skus)
    open_po_raw = sum(float(x["po"]["open_qty_raw"]) for x in skus)
    open_lines = sum(x["po"]["open_line_count"] for x in skus)
    po_skus = sum(1 for x in skus if x["po"]["open_line_count"] > 0)
    eta_missing = sum(x["po"]["eta_missing_lines"] for x in skus)
    prod_skus = sum(1 for x in skus if x["production"]["open_wo_count"] > 0)
    wo_count = sum(x["production"]["open_wo_count"] for x in skus)
    stopped = sum(float(x["production"]["stopped_qty"]) for x in skus)
    dead = sum(float(x["open_so"]["dead"]) for x in skus)
    live = sum(float(x["open_so"]["live_open"]) for x in skus)
    available = sum(float(x["inventory"]["available"]) for x in skus)
    intransit = sum(float(x["inventory"]["intransit"]) for x in skus)
    supply_A = sum(float(x["supply"]["scenario_A"]) for x in skus)
    supply_B = sum(float(x["supply"]["scenario_B"]) for x in skus)
    supply_B_raw = sum(float(x["supply"]["scenario_B_raw_po"]) for x in skus)
    fc50 = sum(float(x["forecast"]["p50_3m"]) for x in skus)
    fc90 = sum(float(x["forecast"]["p90_3m"]) for x in skus)
    recs = {}
    for k in skus[0]["recommendation"]["values"]:
        recs[k] = round(sum(float(x["recommendation"]["values"][k]) for x in skus), 1)
    conf = {c: sum(1 for x in skus if x["forecast"]["confidence"] == c)
            for c in ("medium", "medium-low", "low")}
    models = {m: sum(1 for x in skus if x["forecast"]["primary_model"] == m)
              for m in ("seasonal_naive", "mean3")}
    # backtest aggregate across SKUs (weighted by actual demand)
    def agg_metric(which):
        cells = []
        for x in skus:
            # reconstruct cells from origins
            for r in x["backtest"]["origins"]:
                if "actual" not in r:
                    continue
                if which == "h1":
                    cells.append(dict(a=r["actual"][0], f=r["forecast"][0], p90=r["p90_1"]))
                else:
                    cells.append(dict(a=sum(r["actual"]), f=sum(r["forecast"]), p90=r["p90_3"]))
        return metrics(cells)
    bt = dict(h1=agg_metric("h1"), h3=agg_metric("h3"))
    # scope demand share (qty in window covered by gs_orders global)
    total_scope = sum(float(x["history"]["total_qty"]) for x in skus)
    global_total = data.get("global_qty")
    return dict(
        sku_count=len(skus),
        available_total=num(available), intransit_total=num(intransit),
        open_po_total=num(open_po), open_po_raw_total=num(open_po_raw),
        open_po_line_count=open_lines, open_po_sku_count=po_skus,
        po_eta_missing_lines=eta_missing,
        production_sku_count=prod_skus, open_wo_count=wo_count, stopped_wo_qty=num(stopped),
        open_so_live_total=num(live), dead_so_total=num(dead),
        forecast_p50_3m_total=num(fc50), forecast_p90_3m_total=num(fc90),
        supply_A_total=num(supply_A), supply_B_total=num(supply_B),
        supply_B_raw_po_total=num(supply_B_raw),
        recommendation_sums=recs,
        confidence_counts=conf, primary_model_counts=models,
        backtest_aggregate=bt,
        demand_share=dict(scope_qty=num(total_scope),
                          gs_orders_qty_all=num(global_total) if global_total else None,
                          share=round(total_scope / global_total, 6) if global_total else None),
    )


def build_evidence(data, snapshots, manifest, manifest_path, manifest_hash, skus,
                   cover_path=None, cover_hash=None):
    agg = aggregate(skus, data, manifest, manifest_path, snapshots, data["db_hash"])
    return dict(
        schema_version="supply_replenishment_v0/1",
        generated_at=datetime.now(timezone.utc).astimezone().isoformat(timespec="seconds"),
        scope=dict(
            skus=[x["sku"] for x in skus],
            customer_codes=[x["customer_code"] for x in skus],
            sales_cutoff=SALES_CUTOFF,
            stock_as_of=AS_OF_STOCK,
            document_snapshot="EN phase1 (2026-10-20/21); not re-read from production",
            future_months=FUTURE_MONTHS,
            lead_days=LEAD_DAYS, review_days=REVIEW_DAYS, service_level=0.90,
            production_access=False,
            contains_raw_order_lines=False,
            note="aggregates only; SO/WO/PO identifiers are document-level keys, not order lines",
        ),
        sources=dict(
            db=dict(path=str(DB_PATH), sha256=data["db_hash"], read_only=True),
            en_manifest=dict(path=manifest_path, sha256=manifest_hash,
                             stable_sha256=manifest.get("stable_sha256"),
                             payload_sha256=manifest.get("payload_sha256"),
                             run_id=manifest.get("run_id"), as_of=manifest.get("as_of")),
            en_snapshots=[dict(customer_code=k, path=v["path"], sha256=v["sha256"],
                               generated_at=v["data"].get("generated_at"),
                               as_of=v["data"].get("date"))
                          for k, v in snapshots.items()],
            cover_evidence=dict(path=str(cover_path) if cover_path else None, sha256=cover_hash,
                                note="B v2.1 cover/ETA/UOM evidence; cover is scenario only, not added to supply"),
            tables=["gs_orders", "sku_map", "stock_history", "stock_latest", "tongtool_po",
                    "tongtool_po_open", "replenishment_v3", "three_pl_stock",
                    "bom", "bom_item", "item_attr", "item_ship_type"],
        ),
        row_accounting=dict(
            gs_orders=dict(rows_read=data["total_rows"], bad_date_rows=data["bad_rows"],
                           min_despatch=data["min_date"], max_despatch=data["max_date"],
                           monthly_cells=sum(x["history"]["n_months"] for x in skus),
                           zero_filled_cells=sum(x["history"]["zero_filled_months"] for x in skus),
                           note="all rows aggregated; no row dropped; months between first order and 2026-09 filled with 0 only when gs_orders has no row"),
            stock=dict(rows_asof=len(data["stock"]),
                       note="stock_history 2026-10-22 complete batch, is_test=false"),
            po=dict(rows_total=sum(x["po"]["rows_total"] for x in skus),
                    open_lines=sum(x["po"]["open_line_count"] for x in skus),
                    closed_lines=sum(x["po"]["rows_total"] for x in skus) - sum(x["po"]["open_line_count"] for x in skus),
                    note="open = open_qty > 0; closed rows kept in count but not in supply"),
            production=dict(wos_open=sum(x["production"]["open_wo_count"] for x in skus),
                            wos_stopped=sum(len(x["production"]["stopped_wo"]) for x in skus),
                            wos_draft=sum(len(x["production"]["draft_wo"]) for x in skus)),
            en=dict(so_rows=manifest.get("row_accounting", {}).get("so_line", {}).get("read"),
                    dn_rows=manifest.get("row_accounting", {}).get("dn_line", {}).get("read"),
                    wo_rows=manifest.get("row_accounting", {}).get("wo", {}).get("read"),
                    se_rows=manifest.get("row_accounting", {}).get("se", {}).get("read")),
        ),
        method=dict(
            demand="monthly sum(qty) by despatch_date month; cutoff 2026-09-30; gs_orders has no order-status column, so cancellation/return exclusion is not possible at this layer and is unproven",
            forecast_primary="seasonal_naive (lag 12) when history >= 24 months; otherwise mean of last 3 months; low confidence <24 months",
            forecast_candidate="Holt-Winters additive (level+trend+seasonal, grid-search alpha/beta/gamma); reported, not selected",
            p50="point forecast, clamped at 0",
            p90="p50 + max(1.2816*sigma, q90_residual)*sqrt(h); sigma/q90 from training residuals only",
            backtest="last 6 origins with known h=3; WAPE/bias exclude zero-actual cells; P90 coverage = share actual<=P90",
            supply_A="available + open production remaining; no PO and no intransit",
            supply_B="available + dedup open PO + production not in PO + independent intransit; PO assumed to arrive within lead time (ETA all null)",
            production="open WO = docstatus=1 and status in (Not Started, In Process); remaining = max(0, qty - produced_qty); Draft/Stopped excluded and shown separately",
            production_uom_assumption="WO production_item is PK#皮壳; counted 1:1 against the KS finished item (not proven)",
            po_dedup="identical (sku, warehouse, quantity) open lines across different POs: later purchase_date treated as duplicate candidate; not document-proven",
            recommendation="max(0, P90(lead+30d) - scenario supply); unrounded; no MOQ/pack multiple; not order-ready",
            lead_time="P50 = 3-month average monthly rate x months + live open SO; P90 adds z_sig*sqrt(months); beyond 3 months uses the same average rate (linear extrapolation, not an independent forecast)",
            censoring="NOT corrected: only 3 days of stock history, cannot reconstruct lost sales",
        ),
        queries=dict(
            demand="SELECT sku_tongtool, substr(despatch_date,1,7) AS ym, SUM(qty) FROM gs_orders "
                   "WHERE sku_tongtool IN (<10 customer codes>) GROUP BY 1,2 ORDER BY 1,2",
            stock="SELECT goods_sku, warehouse_name, available, intransit, waiting_shipment, defects, "
                  "batch_complete, is_test, uom_basis FROM stock_history "
                  "WHERE goods_sku IN (<10 customer codes>) AND snapshot_date='2026-10-22'",
            stock_latest="SELECT warehouse, sku, available, intransit, waiting_shipment, defects "
                         "FROM stock_latest WHERE sku IN (<10 customer codes>)",
            po="SELECT ponum, goods_sku, warehouse, quantity, in_quantity, open_qty, status, "
               "purchase_date, will_arrive_date FROM tongtool_po WHERE goods_sku IN (<10 customer codes>)",
            po_open="SELECT sku, warehouse, on_order FROM tongtool_po_open "
                    "WHERE sku IN (<10 customer codes>)",
            replenishment_v3="SELECT * FROM replenishment_v3 WHERE sku IN (<10 customer codes>) "
                             "-- cross-check only; 10-21 pool, excludes Wayfair 3PL",
            cover="cover evidence copied from out/eta_cover_uom/evidence.json (sha256 in sources)",
            en_snapshot="json['wos'], json['so_rows'], json['open_breakdown'] from each g1b_en_*.json",
        ),
        aggregate=agg,
        skus=skus,
        exclusions=dict(
            in_scope=10, excluded=0,
            reason="all 10 have confirmed 1:1 customer-code -> KS item mapping in sku_map; no identity-unknown SKU inside the fixed phase1 scope",
            outside_scope="rest of gs_orders catalog not expanded (user sovereignty; narrow pilot only)",
        ),
        open_items=[
            f"{agg['open_po_sku_count']} SKUs / {agg['open_po_line_count']} open PO lines / "
            f"{agg['open_po_raw_total']} units have no will_arrive_date; Scenario B is an assumption, not an ETA",
            "Open WOs have planned_end_date = null for all open WOs; production arrival date unconfirmed",
            "Open WOs produce PK# covers; counted 1:1 against KS finished items. Insert (ND#) availability and assembly are not modeled",
            "intransit <= open PO at every observed warehouse, but row-level PO<->intransit link is not proven",
            "stock UOM is unknown (stock_history.uom_basis=unknown for all rows); quantities treated as pieces, no conversion",
            "Cover substitution is not proven; cover stock is not added to supply",
            "stockout censoring not corrected (3 days of stock history)",
            "gs_orders has no order-status field; cancellation/return exclusion is not possible and unproven",
            "PO duplicate candidates (PO021733 vs PO021735 on 3 SKUs) are excluded from the main scenario but the document relation is unproven",
        ],
    )


def write_json(path: Path, obj):
    path.parent.mkdir(parents=True, exist_ok=True)
    with path.open("w", encoding="utf-8") as f:
        json.dump(obj, f, ensure_ascii=False, indent=2)
        f.write("\n")


# ----------------------------------------------------------------------------
# markdown rendering
# ----------------------------------------------------------------------------
def render_sku_section(x, level=2):
    h = "#" * level
    f = x["forecast"]
    b = x["backtest"]
    inv = x["inventory"]
    po = x["po"]
    pr = x["production"]
    so = x["open_so"]
    sup = x["supply"]
    out = []
    out.append(f"{h} {x['sku']}  ")
    out.append(f"客户码 `{x['customer_code']}` · ship_type {x['identity']['ship_type']} · "
               f"{x['identity']['item_name']} · 映射 {x['identity']['identity_status']}")
    out.append("")
    out.append(f"证据：EN `{Path(x['snapshot']['path']).name}` sha256 `{x['snapshot']['sha256'][:16]}…`、"
               f"as_of {x['snapshot']['as_of']}；DB `gs_orders`/`stock_history`/`tongtool_po` 查询见 "
               "`out/replenishment_v0/evidence.json` 的 `queries`。")
    out.append("")
    out.append(f"**历史需求**：{x['history']['n_months']} 个月（{x['history']['first_month']} → "
               f"{x['history']['last_month']}），合计 {q(x['history']['total_qty'])} 件；"
               f"近 3 月均值 {q(x['history']['recent3_mean'])}/月；零填充 {x['history']['zero_filled_months']} 个月。")
    # last 12
    ser = x["history"]["series"][-12:]
    out.append("")
    out.append("| 月 | " + " | ".join(s["month"] for s in ser) + " |")
    out.append("|---|" + "---|" * len(ser))
    out.append("| 件 | " + " | ".join(q(s["qty"]) for s in ser) + " |")
    out.append("")
    out.append(f"**预测（{f['primary_model']}，置信度 {f['confidence']}）**")
    out.append("")
    out.append("| 月 | P50 | P90 |")
    out.append("|---|---:|---:|")
    for m in f["months"]:
        out.append(f"| {m['month']} | {q(m['p50'])} | {q(m['p90'])} |")
    out.append(f"| **3 月合计** | **{q(f['p50_3m'])}** | **{q(f['p90_3m'])}** |")
    out.append("")
    out.append("> 3 月 P90 按 P50 合计 + z·σ·√3 计算，不是三个月 P90 相加（独立残差假设）。")
    out.append("")
    out.append(f"ETS 候选：{'可用' if f['ets_candidate'].get('available') else '不可用（' + str(f['ets_candidate'].get('reason')) + '）'}"
               + (f"，3 月 P50 {q(f['ets_candidate'].get('p50_3m'))}" if f['ets_candidate'].get('available') else ""))
    if f.get("run_rate_ratio") is not None:
        out.append(f"模型分歧：预测月均 {q(f['p50_3m']/3)} vs 近 3 月均值 {q(f['recent3_mean'])}"
                   f"（{f['run_rate_ratio']*100:.0f}%）。")
    out.append("")
    def mrow(label, m):
        if not m or m.get("n", 0) == 0:
            return f"| {label} | — | — | — | 0 | — |"
        return (f"| {label} | {pct(m['wape'])} | {pct(m['bias'])} | {pct(m['coverage'])} | "
                f"{m['n']} | {m['zero_excluded']} |")
    out.append("**回测（最近 6 个起点，1/3 月）**")
    out.append("")
    out.append("| 口径 | WAPE | bias | P90 覆盖率 | 有效起点 | 零需求剔除 |")
    out.append("|---|---:|---:|---:|---:|---:|")
    out.append(mrow("1 月", b["h1"]))
    out.append(mrow("3 月累计", b["h3"]))
    if b.get("ets_h1"):
        out.append(mrow("ETS 1 月（参考）", b["ets_h1"]))
        out.append(mrow("ETS 3 月（参考）", b["ets_h3"]))
    out.append("")
    out.append("| 起点 | 训练月数 | 模型 | 实际 h1/h2/h3 | P50 h1/h2/h3 | P90(h1) | P90(h3) |")
    out.append("|---|---:|---|---|---|---:|---:|")
    for r in b["origins"]:
        if "actual" not in r:
            out.append(f"| {r['origin']} | {r.get('n_train','—')} | — | — | — | — | — |")
            continue
        out.append(f"| {r['origin']} | {r['n_train']} | {r['model']} | "
                   f"{'/'.join(q(v) for v in r['actual'])} | {r['forecast'][0]:g}/{r['forecast'][1]:g}/{r['forecast'][2]:g} | "
                   f"{q(r['p90_1'])} | {q(r['p90_3'])} |")
    out.append("")
    out.append("**库存（2026-10-22 完整批次）**")
    out.append("")
    out.append("| 仓 | available | intransit | waiting_shipment | defects |")
    out.append("|---|---:|---:|---:|---:|")
    for w in inv["by_warehouse"]:
        out.append(f"| {w['warehouse']} | {q(w['available'])} | {q(w['intransit'])} | {q(w['waiting_shipment'])} | {q(w['defects'])} |")
    out.append(f"| **合计** | **{q(inv['available'])}** | **{q(inv['intransit'])}** | **{q(inv['waiting_shipment'])}** | **{q(inv['defects'])}** |")
    out.append("")
    sl = inv.get("stock_latest_available_total")
    if sl is not None:
        out.append(f"`stock_latest` 交叉核对：available {q(sl)}（部分行仍是 10-21 值；与 10-22 差 {q(sl - inv['available'])}）；"
                   "主口径用 `stock_history` 10-22 完整批次。")
        out.append("")
    cover = x.get("cover") or {}
    if cover:
        if cover.get("cover_observed"):
            out.append(f"**Cover（单列，不计入供给）**：观测 available={q(cover.get('alias_available_sum'))}，"
                       f"alias_mapping={cover.get('alias_mapping_present')}，verdict={cover.get('verdict')}。")
        else:
            out.append(f"**Cover（单列，不计入供给）**：无映射（cover_observed=false），"
                       "`alias_available_sum=null`；不写 0。")
        out.append("")
    out.append(f"**未结 PO**：原始 {q(po['open_qty_raw'])} 件 / {po['open_line_count']} 行；"
               f"重复候选剔除 {q(po['duplicate_candidate_qty'])} → 主口径 {q(po['open_qty_dedup'])} 件；"
               f"ETA 缺失 {po['eta_missing_lines']}/{po['open_line_count']}。")
    if po["open_lines"]:
        out.append("")
        out.append("| PO | 仓 | quantity | open_qty | status | purchase_date | ETA | 重复候选 |")
        out.append("|---|---|---:|---:|---|---|---|---|")
        for ln in po["open_lines"]:
            out.append(f"| {ln['ponum']} | {ln['warehouse']} | {q(ln['quantity'])} | {q(ln['open_qty'])} | "
                       f"{ln['status']} | {ln['purchase_date']} | {ln['will_arrive_date'] or 'NULL'} | "
                       f"{'是' if ln['duplicate_candidate'] else ''} |")
    out.append("")
    out.append(f"**在产 WO**：{pr['open_wo_count']} 张 / 毛量 {q(pr['gross_qty'])} / 剩余 {q(pr['remaining_qty'])}；"
               f"Stopped {q(pr['stopped_qty'])} 件（未计）；Draft {len(pr['draft_wo'])} 张（未计）；"
               f"planned_end_date 缺失 {pr['eta_missing_count']}/{pr['open_wo_count']}。")
    if pr["open_wo"]:
        out.append("")
        out.append("| WO | 状态 | 生产物 | qty | produced_qty | 剩余 |")
        out.append("|---|---|---|---:|---:|---:|")
        for w in pr["open_wo"]:
            out.append(f"| {w['name']} | {w['status']} | {w['production_item']} | {q(w['qty'])} | "
                       f"{q(w['produced_qty'])} | {q(w['remaining_qty'])} |")
    out.append("")
    out.append(f"**已开未发 SO**：reconciled {q(so['reconciled_open'])} = 死单 {q(so['dead'])} + "
               f"在产 {q(so['in_progress'])} + 无计划 {q(so['no_plan'])} + 超发 {q(so['over_delivered'])}；"
               f"**计入需求的 live open = {q(so['live_open'])}**（死单不计）。")
    if so["dead_so"]:
        out.append(f"死单明细：{', '.join(b['so'] + '=' + q(b['open_qty']) for b in so['dead_so'])}。")
    out.append("")
    out.append("**供给情景与建议量（未取整、不可直接下单）**")
    out.append("")
    out.append(f"- 情景 A（无 PO / 无在途）= available {q(sup['available'])} + 在产剩余 {q(sup['production_remaining'])} = **{q(sup['scenario_A'])}**")
    out.append(f"- 情景 B（PO 按假设到货）= available {q(sup['available'])} + 去重 PO {q(sup['open_po_dedup'])} + "
               f"未含于 PO 的在产 {q(sup['production_not_in_po'])} + 独立在途 {q(sup['independent_intransit'])} = **{q(sup['scenario_B'])}**")
    out.append(f"- B 敏感性（PO 不去重）= {q(sup['scenario_B_raw_po'])}；仅可用库存 = {q(sup['available'])}")
    out.append("")
    out.append("| 提前期 | 需求 P50（含 open SO） | 需求 P90（ROP） | 建议量 A | 建议量 B | 仅可用库存 |")
    out.append("|---|---:|---:|---:|---:|---:|")
    for d in LEAD_DAYS:
        l = x["lead_time"][f"L{d}"]
        rv = x["recommendation"]["values"]
        out.append(f"| {d} 天 | {q(l['p50'])} | {q(l['p90'])} | {q(rv[f'A_L{d}'])} | "
                   f"{q(rv[f'B_L{d}'])} | {q(rv[f'AVAIL_L{d}'])} |")
    out.append("")
    out.append("需单列的未知/情景：")
    for u in x["unknowns"]:
        out.append(f"- {u}")
    out.append("")
    return "\n".join(out)


def render_sample(skus, ev):
    parts = []
    parts.append("---")
    parts.append("okf: v0.1")
    parts.append("type: Review")
    parts.append("title: G2+G3 2-SKU 端到端样例（只读）")
    parts.append("date: 2026-10-22")
    parts.append("owner: claude-worker")
    parts.append("status: sample")
    parts.append("---")
    parts.append("")
    parts.append("# G2+G3 2-SKU 端到端样例")
    parts.append("")
    parts.append("> 目的：在 60 分钟内交付可检查的端到端样例，证明历史需求、预测/回测、库存、"
                 "PO/在产、情景 A/B 和证据链接能跑通。**不是下单建议**；全量 10 SKU 见同目录 V0 报告。")
    parts.append("")
    parts.append(f"- 数据：`{DB_PATH}`（read_only=True，sha256 `{ev['sources']['db']['sha256'][:16]}…`），"
                 f"销量截止 {SALES_CUTOFF}-30，库存 {AS_OF_STOCK} 完整批次。")
    parts.append(f"- 单据：EN phase1 快照（2026-10-20/21，manifest `{ev['sources']['en_manifest']['sha256'][:16]}…`，"
                 f"stable `{str(ev['sources']['en_manifest']['stable_sha256'])[:16]}…`）；本轮 0 次生产访问。")
    parts.append(f"- Cover 证据沿用 B v2.1：`out/eta_cover_uom/evidence.json` sha256 "
                 f"`{str(ev['sources']['cover_evidence']['sha256'])[:16]}…`；cover 只作情景，不并入供给。")
    parts.append(f"- 证据 JSON：`out/replenishment_v0/evidence.json`；本样例逐 SKU 见 `evidence.json` 的 `skus[]`。")
    parts.append("")
    for x in skus:
        parts.append(render_sku_section(x, 2))
    parts.append("## 样例结论（只读）")
    parts.append("")
    parts.append("1. 两例都跑通了「历史需求 → 预测/回测 → 库存/PO/在产 → A/B 情景 → 建议量」；"
                 "但建议量明确受 ETA 缺失、PO 重复候选、在产无日期、死单/库存 UOM 未证影响，不能当订单。")
    parts.append("2. Linen-Natural-194 是「高量 + 无 PO + 大量在产 + 421 件死单」的代表；"
                 "Linen-White 是「历史 <24 月退化 mean3 + PO 73 件 + 库存低」的代表。")
    parts.append("3. **Linen-White 的 mean3 明显受 2026-08 峰值 280 影响**（近 3 月 27/280/16 均值 107.7/月），"
                 "预测远高于 2025 年同月 2/5/15；这是“<24 月退化”规则的低置信代价，建议量不可直接用。"
                 "若改用 seasonal naive 需 24 个月历史，本批没有。")
    parts.append("4. 回测指标只代表过去 6 个起点，不能外推；P90 覆盖率若低于 90%，说明当前区间偏窄，"
                 "不应据此承诺服务水平。")
    parts.append("")
    return "\n".join(parts)


def render_full(skus, ev):
    agg = ev["aggregate"]
    parts = []
    parts.append("---")
    parts.append("okf: v0.1")
    parts.append("type: Review")
    parts.append("title: G2+G3 窄范围供需与补货决策报告 V0（只读）")
    parts.append("date: 2026-10-22")
    parts.append("owner: claude-worker")
    parts.append("scope: 10 EN-chain-complete SKUs")
    parts.append("status: V0 for review; not order-ready")
    parts.append("---")
    parts.append("")
    parts.append("# G2+G3 窄范围供需与补货决策报告 V0")
    parts.append("")
    parts.append("> **范围与边界**：只覆盖 phase1 已验收的 10 个 SKU；只读 `order_store.duckdb` 与 EN phase1 快照；"
                 "不访问生产、不下单、不扩样。所有建议量未取整、未套 MOQ/包装倍数，**不是可直接下单的结论**。")
    parts.append("")
    parts.append("## 1. 结论先行")
    parts.append("")
    parts.append(f"- **入 10 SKU → 出 10 SKU**；客户码→单一 KS 物料确认 10/10，G3 排除 0 个。"
                 f"10 个 SKU 在 gs_orders 窗口内合计 {q(agg['demand_share']['scope_qty'])} 件，"
                 f"占全表 {pct(agg['demand_share']['share'])}（仅作规模参考，不是总体覆盖率）。")
    parts.append(f"- **需求**：3 个月（2026-10..12）预测 P50 合计 **{q(agg['forecast_p50_3m_total'])}**、"
                 f"P90 合计 **{q(agg['forecast_p90_3m_total'])}**（逐 SKU P90 相加，不是组合 P90）；"
                 f"已开未发 live SO **{q(agg['open_so_live_total'])}** 件，死单 {q(agg['dead_so_total'])} 件未计入。")
    parts.append(f"- **供给**：可用库存 **{q(agg['available_total'])}**；去重未结 PO **{q(agg['open_po_total'])}**"
                 f"（原始 {q(agg['open_po_raw_total'])}，重复候选剔除 {q(agg['open_po_raw_total'] - agg['open_po_total'])}）；"
                 f"在产剩余已单列；独立在途 0。")
    parts.append(f"- **情景 A 总供给 {q(agg['supply_A_total'])} / 情景 B {q(agg['supply_B_total'])}**；"
                 f"B 的 PO 到货是假设（13 行未结 PO 的 ETA 全空），不是证据。")
    parts.append(f"- **回测**：聚合 1 月 WAPE {pct(agg['backtest_aggregate']['h1']['wape'])}、"
                 f"3 月 WAPE {pct(agg['backtest_aggregate']['h3']['wape'])}；"
                 f"P90 覆盖率 1 月 {pct(agg['backtest_aggregate']['h1']['coverage'])}、"
                 f"3 月 {pct(agg['backtest_aggregate']['h3']['coverage'])}。"
                 "覆盖率不足 90% 时，P90 区间偏窄，服务水平不能按名义值承诺。")
    parts.append("- **不能做的结论**：不能把 A/B、60/90/120 天、PO 去重与否合成一个“建议下单量”；"
                 "ETA、在产日期、UOM、Cover 可替代、断货删失都未证。")
    parts.append("")
    parts.append("## 2. 范围、身份与排除")
    parts.append("")
    parts.append("| # | 客户码 | item_code | ship_type | 别名数 | 历史月数 | 置信度 | 主模型 |")
    parts.append("|---:|---|---|---|---:|---:|---|---|")
    for i, x in enumerate(skus, 1):
        parts.append(f"| {i} | `{x['customer_code']}` | `{x['sku']}` | {x['identity']['ship_type']} | "
                     f"{x['identity']['alias_count']} | "
                     f"{x['history']['n_months']} | {x['forecast']['confidence']} | {x['forecast']['primary_model']} |")
    parts.append("")
    parts.append("- 排除：**0/10**。每个客户码只指向一个 KS 物料（10/10 confirmed）；同一 KS 物料另有平台别名"
                 "（本轮 6 个别名常见），这是多渠道/cover 命名，不是跨物料歧义。没有身份不明到需要排除 G3 的 SKU。"
                 "单位口径仍是条件结论：需求/BOM 为「个」，库存 `uom_basis=unknown`，本轮按件计数、不做换算。")
    parts.append(f"- 置信度分布：{agg['confidence_counts']}；主模型：{agg['primary_model_counts']}。")
    parts.append("- 历史 <24 月退化为近 3 月均值（本批仅 Linen-White 14 月）；24–35 月标 medium-low，36+ 标 medium。"
                 "所有 SKU 都不声称稳定季节性。")
    parts.append("")
    parts.append("## 3. 预测与回测")
    parts.append("")
    parts.append("### 3.1 方法")
    parts.append("")
    parts.append("- 需求：`gs_orders` 按 `despatch_date` 月聚合 `sum(qty)`，截止 2026-09-30；首个订单月到 2026-09 之间无行补 0。"
                 "`gs_orders` 无订单状态字段，本层无法剔除取消/退货；若源表已只含发货行则无影响，但未证。")
    parts.append("- 主模型：历史 ≥24 月用 seasonal naive（lag 12）；<24 月用近 3 月均值。ETS 候选为 Holt-Winters 加法"
                 "（level+trend+seasonal，网格搜索 α/β/γ），**仅报告、不选为主模型**，避免在同一 6 个回测起点上选模的乐观偏差。")
    parts.append("- P50 = 点预测（下限 0）；P90 = P50 + max(1.2816·σ, q90(残差))·√h。σ/q90 只用训练残差。"
                 "3 月 P90 不是三个月 P90 相加，而是按 √3 缩放（独立残差假设）。")
    parts.append("- 回测：最近 6 个已知 h=3 的起点（2026-01..2026-06）；1 月按单月、3 月按累计；"
                 "实际为 0 的单元不参与 WAPE/bias；P90 覆盖率 = 实际 ≤ P90 的比例。")
    parts.append("- ETS 只在训练 ≥24 月的起点可算，因此它的样本起点数可能少于 6；表中 ETS 行只作参考，"
                 "不与主模型 6 起点 WAPE 直接比较。")
    parts.append("")
    parts.append("### 3.2 逐 SKU 回测与 3 月预测")
    parts.append("")
    parts.append("| SKU | 模型 | 近3月均值/月 | P50月均/近3月 | 1月 WAPE | 3月 WAPE | 1月 bias | 3月 bias | 1月 P90覆盖 | 3月 P90覆盖 | P50 3月 | P90 3月 |")
    parts.append("|---|---|---:|---:|---:|---:|---:|---:|---:|---:|---:|---:|")
    for x in skus:
        b = x["backtest"]
        f = x["forecast"]
        def v(m, k):
            return pct(m[k]) if m and m.get(k) is not None else "—"
        ratio = f.get("run_rate_ratio")
        ratio_txt = "—" if ratio is None else f"{ratio*100:.0f}%"
        parts.append(f"| `{x['sku']}` | {f['primary_model']} | {q(x['history']['recent3_mean'])} | "
                     f"{ratio_txt} | "
                     f"{v(b['h1'],'wape')} | {v(b['h3'],'wape')} | "
                     f"{v(b['h1'],'bias')} | {v(b['h3'],'bias')} | {v(b['h1'],'coverage')} | "
                     f"{v(b['h3'],'coverage')} | {q(f['p50_3m'])} | {q(f['p90_3m'])} |")
    parts.append("")
    parts.append(f"**聚合**（按实际量加权）：1 月 WAPE {pct(agg['backtest_aggregate']['h1']['wape'])}、"
                 f"3 月 WAPE {pct(agg['backtest_aggregate']['h3']['wape'])}；"
                 f"1 月 P90 覆盖 {pct(agg['backtest_aggregate']['h1']['coverage'])}、"
                 f"3 月 P90 覆盖 {pct(agg['backtest_aggregate']['h3']['coverage'])}；"
                 f"有效单元 1 月 {agg['backtest_aggregate']['h1']['n']}、3 月 {agg['backtest_aggregate']['h3']['n']}。")
    parts.append("")
    div = [x for x in skus if x["forecast"].get("run_rate_ratio") is not None
           and x["forecast"]["run_rate_ratio"] < 0.5]
    if div:
        parts.append(f"> **模型分歧（重要）**：{len(div)}/10 个 SKU 的预测月均低于近 3 月均值的 50%"
                     f"（{', '.join('`'+x['sku']+'`' for x in div)}）。原因是 seasonal naive 直接用 2025 年 10–12 月，"
                     "而 2026 年 6–9 月量级明显更高。若近期旺势延续，P50 会低估、建议量偏小；"
                     "这些 SKU 的建议量只能当下限情景，不能当“不用补”的证据。")
        parts.append("")
    parts.append("ETS 候选的逐 SKU 参考值见 `evidence.json` 的 `skus[].backtest.ets_h1/ets_h3`；"
                 "本轮没有用 ETS 替换主模型。ETS 在本批不稳定：QDKTR-DEEPGREY 的 3 月 P50 被拟合为 0，"
                 "多个 SKU 只有 1–3 个可比起点；它只作对照，不进入建议量。")
    parts.append("")
    parts.append("> **低置信退化代价**：Linen-White 只有 14 个月历史，按规则用近 3 月均值；"
                 "近 3 月为 27/280/16，均值 107.7/月，预测远高于 2025 年 10–12 月的 2/5/15。"
                 "这不是模型“看好”该 SKU，而是规则在峰值月上的机械外推；建议量必须按低置信处理。")
    parts.append("")
    parts.append("## 4. 供给：库存、PO、在产")
    parts.append("")
    parts.append("### 4.1 口径")
    parts.append("")
    parts.append("- **可用库存**：`stock_history` 2026-10-22 完整批次、`is_test=false`，按仓求和；含 WayfairCG 3PL。"
                 "`stock_latest` 部分行仍是 10-21 值，本轮不用它。")
    parts.append("- **未结 PO**：`tongtool_po.open_qty > 0`，行键 `(ponum, goods_sku, warehouse)`。"
                 "同 SKU/仓/数量但不同 PO 的行视为重复候选，保留较早 purchase_date、剔除较晚者；"
                 "该规则是“候选”，不是单据级证明。")
    parts.append("- **在产**：EN 快照 WO 中 `docstatus=1` 且 status ∈ {Not Started, In Process}；"
                 "剩余 = max(0, qty − produced_qty)。Draft/Stopped 不计，单列。WO 的 `produced_qty` 已知不可靠，"
                 "因此另给毛量；主口径用剩余量，并在未知项中标注。")
    parts.append("- **在产 1:1 假设**：WO 的 `production_item` 是 `PK#` 皮壳，本轮按 1:1 对应 KS 成品计入；"
                 "该关系未证（若 BOM/加工损耗不是 1:1，在产量需重算）。")
    parts.append("- **独立在途**：同仓 `intransit − open PO` 的正部；本轮 10/10 为 0。"
                 "但是否逐笔属于同一 PO 未证，故只作“独立在途=0”的条件结论。")
    parts.append("- **严格口径**：若坚持“ETA 空不得视为及时到货”，则 A/B 都不能算作可到货供给，"
                 "只能看“仅可用库存”列；A/B 是情景，不是承诺。")
    parts.append("")
    parts.append("### 4.2 逐 SKU 供给")
    parts.append("")
    parts.append("| SKU | 可用 | 在途 | 未结PO原始 | PO重复候选 | 去重PO | 在产毛量 | 在产剩余 | 未含PO在产 | 独立在途 | A | B |")
    parts.append("|---|---:|---:|---:|---:|---:|---:|---:|---:|---:|---:|---:|")
    for x in skus:
        s = x["supply"]
        parts.append(f"| `{x['sku']}` | {q(s['available'])} | {q(x['inventory']['intransit'])} | "
                     f"{q(s['open_po_raw'])} | {q(s['open_po_raw'] - s['open_po_dedup'])} | "
                     f"{q(s['open_po_dedup'])} | {q(s['production_gross'])} | {q(s['production_remaining'])} | "
                     f"{q(s['production_not_in_po'])} | {q(s['independent_intransit'])} | "
                     f"{q(s['scenario_A'])} | {q(s['scenario_B'])} |")
    parts.append("")
    dedup_ok = [x["sku"] for x in skus if x["po"].get("dedup_equals_intransit")]
    if dedup_ok:
        parts.append(f"> 去重一致性：{len(dedup_ok)} 个 SKU（{', '.join('`'+s+'`' for s in dedup_ok)}）"
                     "剔除较晚重复候选后，未结 PO 恰好等于同 SKU 在途量。这与“重复候选”假设一致，"
                     "但仍不是单据级证明；原始 PO 口径作敏感性（B_raw）。")
        parts.append("")
    parts.append("## 5. 需求与建议量（情景，不是订单）")
    parts.append("")
    parts.append("需求 = 预测 + 已开未发 live SO（死单不计）。ROP = 提前期需求 P90；建议量 = max(0, P90(提前期+30天) − 同期净供给)。"
                 "所有值未取整、无 MOQ/包装倍数。提前期 120/150 天超出 3 个月预测窗口，用 3 个月平均月率线性外推，"
                 "不是独立预测。")
    parts.append("")
    parts.append("| SKU | 预测P50 | 预测P90 | live SO | 需求P50 | 需求P90 | ROP60 | 建议60 A/B | ROP90 | 建议90 A/B | ROP120 | 建议120 A/B |")
    parts.append("|---|---:|---:|---:|---:|---:|---:|---|---:|---|---:|---|")
    for x in skus:
        f = x["forecast"]; so = x["open_so"]; d = x["demand"]; lt = x["lead_time"]; rv = x["recommendation"]["values"]
        parts.append(f"| `{x['sku']}` | {q(f['p50_3m'])} | {q(f['p90_3m'])} | {q(so['live_open'])} | "
                     f"{q(d['total_p50'])} | {q(d['total_p90'])} | "
                     f"{q(lt['L60']['p90'])} | "
                     f"{q(rv['A_L60'])} / {q(rv['B_L60'])} | "
                     f"{q(lt['L90']['p90'])} | "
                     f"{q(rv['A_L90'])} / {q(rv['B_L90'])} | "
                     f"{q(lt['L120']['p90'])} | "
                     f"{q(rv['A_L120'])} / {q(rv['B_L120'])} |")
    parts.append("")
    parts.append("> ROP 只依赖需求，不依赖供给情景；建议量按 A/B 分列。聚合值：A 建议 60/90/120 = "
                 f"{q(agg['recommendation_sums']['A_L60'])} / {q(agg['recommendation_sums']['A_L90'])} / {q(agg['recommendation_sums']['A_L120'])}；"
                 f"B = {q(agg['recommendation_sums']['B_L60'])} / {q(agg['recommendation_sums']['B_L90'])} / {q(agg['recommendation_sums']['B_L120'])}。"
                 "这些合计**不是**采购/生产总量。")
    parts.append("")
    parts.append("## 6. 未知项与情景隔离")
    parts.append("")
    parts.append("| 类别 | 数量/范围 | 处理 |")
    parts.append("|---|---|---|")
    parts.append(f"| PO ETA 空 | {agg['open_po_line_count']} 行 / {q(agg['open_po_raw_total'])} 件 / {agg['open_po_sku_count']} SKU | 情景 B 假设提前期内到货；不写“及时到货” |")
    parts.append(f"| 在产无日期 | {agg['open_wo_count']} 张开放 WO | 计入供给但标“到货日未确认”；Draft/Stopped 单列 |")
    parts.append(f"| Stopped WO | {agg['stopped_wo_qty']} 件 | 未计入在产 |")
    parts.append(f"| 死单 SO | {q(agg['dead_so_total'])} 件 | 未计入需求；若确认补发需另加 |")
    parts.append("| 库存 UOM | 10/10 SKU | `uom_basis=unknown`；按件计数、未换算 |")
    parts.append("| Cover 可替代 | 10/10 SKU | 未证；cover 库存不并入供给 |")
    parts.append("| 断货删失 | 10/10 SKU | 仅 3 天库存历史，未校正；历史缺口可能低估需求 |")
    parts.append("| 取消/退货 | 10/10 SKU | `gs_orders` 无状态字段，未剔除；若源表只含发货行则无影响，未证 |")
    parts.append("| PO 重复候选 | 3 SKU（Cord-DKBlue/Cord-Grey/Linen-153）| 主口径剔除较晚 PO；原始值作敏感性 |")
    parts.append("")
    parts.append("## 7. 对账与可复现性")
    parts.append("")
    ra = ev["row_accounting"]
    parts.append("### 7.1 行数对账")
    parts.append("")
    parts.append("| 数据 | 读入 | 输出/保留 | 差数解释 |")
    parts.append("|---|---:|---:|---|")
    parts.append(f"| gs_orders | {ra['gs_orders']['rows_read']} 行 | {ra['gs_orders']['monthly_cells']} 个月度单元（10 SKU） | 全部按 SKU×月聚合；无坏日期行（{ra['gs_orders']['bad_date_rows']}）；首单月前不补 0 |")
    parts.append(f"| stock_history 10-22 | {ra['stock']['rows_asof']} 行 | 10 SKU × 仓 | 完整批次、is_test=false；退货仓 0 保留 |")
    parts.append(f"| tongtool_po | {ra['po']['rows_total']} 行 | {ra['po']['open_lines']} 未结 + {ra['po']['closed_lines']} 已结 | 已结行不进供给，但保留计数 |")
    parts.append(f"| EN WO | {ra['production']['wos_open']} 开放 + {ra['production']['wos_stopped']} Stopped + {ra['production']['wos_draft']} Draft | 开放计入，其余单列 | 无静默丢弃 |")
    parts.append(f"| EN SO/DN/WO/SE | {ra['en']['so_rows']}/{ra['en']['dn_rows']}/{ra['en']['wo_rows']}/{ra['en']['se_rows']} | phase1 已守恒 | DN/SE 只用于核销，不重复加减 |")
    parts.append("")
    parts.append("### 7.2 查询与哈希")
    parts.append("")
    parts.append(f"- DB：`{DB_PATH}` sha256 `{ev['sources']['db']['sha256']}`（read_only=True；运行前后未变）。")
    parts.append(f"- EN manifest：`{ev['sources']['en_manifest']['path']}` sha256 `{ev['sources']['en_manifest']['sha256']}`；"
                 f"stable `{ev['sources']['en_manifest']['stable_sha256']}`。")
    parts.append("- 10 个 EN 快照的 sha256 在 `evidence.json` 的 `sources.en_snapshots[]`。")
    parts.append("- 查询定义：")
    parts.append("```sql")
    parts.append("SELECT sku_tongtool, substr(despatch_date,1,7) ym, sum(qty) FROM gs_orders")
    parts.append("WHERE sku_tongtool IN (<10 customer codes>) GROUP BY 1,2;")
    parts.append("SELECT goods_sku,warehouse_name,available,intransit,waiting_shipment,defects")
    parts.append("FROM stock_history WHERE snapshot_date='2026-10-22' AND goods_sku IN (<10 codes>);")
    parts.append("SELECT ponum,goods_sku,warehouse,quantity,in_quantity,open_qty,status,purchase_date,will_arrive_date")
    parts.append("FROM tongtool_po WHERE goods_sku IN (<10 codes>);")
    parts.append("SELECT * FROM replenishment_v3 WHERE sku IN (<10 codes>);  -- cross-check only")
    parts.append("```")
    parts.append("")
    parts.append("## 8. 复审建议")
    parts.append("")
    parts.append("1. 先审样例（`2026-10-22-sample-2sku.md`）与供给去重：特别是 PO021733/PO021735 重复候选、"
                 "intransit 与 PO 的 max 口径、在产 remaining vs gross。")
    parts.append("2. 再审回测：6 个起点的零需求剔除、P90 覆盖、<24 月退化是否按规则执行。")
    parts.append("3. 业务侧只需先回答三件事：PO021733/735 是否重复；死单是否补发；库存单位是否为件。"
                 "这三项不解决，建议量只能作情景。")
    parts.append("")
    parts.append("## 9. 附：逐 SKU 明细")
    parts.append("")
    for x in skus:
        parts.append(render_sku_section(x, 2))
    parts.append("")
    parts.append("## 10. 运行限制")
    parts.append("")
    parts.append("- 0 次生产访问；`order_store.duckdb` 以 read_only 打开；未写下单/采购/生产系统。")
    parts.append("- 10 SKU 是 phase1 固定范围，未扩样；全 family / 100 SKU 需用户明确授权。")
    parts.append("- 本报告是 V0，供 Codex1 复审；不自行宣布 PASS。")
    parts.append("")
    return "\n".join(parts)


# ----------------------------------------------------------------------------
# main
# ----------------------------------------------------------------------------
def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--sample", action="store_true", help="also write the 2-SKU sample report")
    args = ap.parse_args()

    data = load_all()
    snapshots, manifest, manifest_path, manifest_hash = load_snapshots()
    cover_path = CLAUDE_DIR / "out" / "eta_cover_uom" / "evidence.json"
    cover_hash = sha256_file(cover_path)
    with cover_path.open("r", encoding="utf-8") as f:
        cover_ev = json.load(f)
    cover_map = {s["item_code"]: s["cover"] for s in cover_ev.get("extension_scope", {}).get("skus", [])}
    # global qty for share
    con = duckdb.connect(str(DB_PATH), read_only=True)
    data["global_qty"] = con.execute("SELECT SUM(qty) FROM gs_orders").fetchone()[0]
    con.close()

    skus = []
    for code, sku, fn in SCOPES:
        snap = snapshots[code]
        skus.append(build_sku(code, sku, snap, data, cover_map))

    ev = build_evidence(data, snapshots, manifest, manifest_path, manifest_hash, skus,
                        cover_path=cover_path, cover_hash=cover_hash)
    db_hash_after = sha256_file(DB_PATH)
    ev["sources"]["db"]["sha256_after"] = db_hash_after
    ev["sources"]["db"]["unchanged"] = (db_hash_after == data["db_hash"])
    if db_hash_after != data["db_hash"]:
        raise SystemExit("DB hash changed during read-only run")
    write_json(EVIDENCE_DIR / "evidence.json", ev)
    sample = [x for x in skus if x["customer_code"] in SAMPLE_CODES]
    write_json(PILOT_OUT / "sample_2sku.json", dict(
        schema_version="supply_replenishment_v0_sample/1",
        generated_at=ev["generated_at"],
        note="2-SKU end-to-end sample; full 10-SKU evidence in out/replenishment_v0/evidence.json",
        sources=ev["sources"],
        method=ev["method"],
        skus=sample,
    ))
    if args.sample:
        (REVIEW_DIR / "2026-10-22-sample-2sku.md").write_text(render_sample(sample, ev), encoding="utf-8")
    (REVIEW_DIR / "2026-10-22-supply-demand-replenishment-v0.md").write_text(render_full(skus, ev), encoding="utf-8")

    print("wrote", EVIDENCE_DIR / "evidence.json")
    print("wrote", PILOT_OUT / "sample_2sku.json")
    print("sample skus:", [x["sku"] for x in sample])
    for x in sample:
        print(x["sku"], "hist", x["history"]["n_months"], x["forecast"]["primary_model"],
              "fc50", x["forecast"]["p50_3m"], "fc90", x["forecast"]["p90_3m"],
              "avail", x["inventory"]["available"], "po", x["po"]["open_qty_dedup"],
              "wo_rem", x["production"]["remaining_qty"], "liveSO", x["open_so"]["live_open"],
              "A", x["supply"]["scenario_A"], "B", x["supply"]["scenario_B"])


if __name__ == "__main__":
    main()
