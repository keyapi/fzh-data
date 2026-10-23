#!/usr/bin/env python
# -*- coding: utf-8 -*-
"""Forward net demand from the 2026-10-22 snapshot — SC02 repair v2 (OFFLINE).

Fixes merged from the 301 forward review + the coordinator follow-up:

  1. SO / stock: `availableStockQuantity` and `waitingShipmentStockQuantity` are
     NOT proven semantics (DECISIONS.md:682-683). The row keeps
     `inventory_basis=unknown`, and the SO overlap is a SCENARIO
     (overlap=0 vs overlap=min(forecast, SO)), never a silent deduction.
  2. Same-batch: `suspected_same_batch_as_po` is NOT upgraded to proven. Both
     `same_batch` and `different_batch` scenarios are emitted side by side.
  3. Per-bucket ledger: every SKU x warehouse x bucket x scenario stores
     opening / forecast / included_SO / overlap / total_demand / receipts /
     allocated_supply / fulfilled / unserved / closing, and the two identities
     are asserted: opening+receipts-fulfilled=closing and
     total_demand-fulfilled=unserved; unserved is carried into the next bucket.
  4. Demand source: the rate comes from the T5 column (`新预测等效率(T5)`,
     AutoETS with an MA3 fallback, statsforecast 2.1.1) — NOT from
     `decision_v2.月需求率`, which is the T3 three-month mean. The source,
     method, version and fallback reason are stored on every row.
  5. Work orders: `wo_qty=null`, `wo_status=not_observed` — an unknown WO is not
     zero supply, so such rows never reach a proven readiness.
  6. Anchor: snapshot-anchored (bucket 1 starts at the snapshot and keeps ALL
     subsequent demand). The elapsed-day deduction is NOT applied on top; the
     alternative anchor is available as `stock_after_elapsed` but unused here.

Naming (Codex2): `scenario_id` labels the demand/supply assumption, `readiness`
is 研究 / 条件 / 已确认 / 执行已授权 with HOLD for missing evidence. Old A/B/C
stay in `old_status` and map B->条件, A->已确认 (after review), C->HOLD.

Outputs (row level stays local):
  out/business_phase/forward_net.json
  out/business_phase/forward_net_rows.csv
  out/business_phase/forward_net_buckets.csv
"""
from __future__ import annotations

import csv
import json
from collections import Counter, defaultdict
from datetime import date
from pathlib import Path

BP = Path(__file__).resolve().parents[2] / "out" / "business_phase"
SNAPSHOT = date(2026, 10, 22)
RUN_DATE = date(2026, 10, 23)
BASE_DAYS = 31


# ---------------------------------------------------------------------------
# Pure helpers (asserted by test_forward_net.py)
# ---------------------------------------------------------------------------

def days_inclusive(a: date, b: date) -> int:
    return (b - a).days + 1


def horizon_demand(monthly_rate: float, start: date, end: date) -> float:
    return float(monthly_rate) * days_inclusive(start, end) / BASE_DAYS


def bucket_bounds():
    return [("2026-10 剩余", SNAPSHOT, date(2026, 10, 31)),
            ("2026-11", date(2026, 11, 1), date(2026, 11, 30)),
            ("2026-12", date(2026, 12, 1), date(2026, 12, 31))]


def stock_after_elapsed(stock: float, daily: float, days: int) -> float:
    """Alternative anchor (rolling to the run date). NOT used in the main path."""
    return float(stock) - float(daily) * int(days)


def gap_after_so(demand, so_in_forecast, so_extra, stock, stock_net_of_so=False):
    """SO inside the forecast window is part of demand -> never deducted twice."""
    return max(0.0, float(demand) + float(so_extra) - float(stock))


def batch_supply(po, transit, dedupe_state):
    """Same-batch is UNPROVEN: return both scenarios, never collapse them."""
    po, transit = float(po or 0), float(transit or 0)
    if dedupe_state == "suspected_same_batch_as_po":
        return dict(same_batch=max(po, transit), different_batch=po + transit,
                    dedupe_state="unknown_suspected")
    return dict(same_batch=po + transit, different_batch=po + transit,
                dedupe_state=dedupe_state or "none_recorded")


def harvest_total(rows):
    """Drafts excluded; one row counted once even with many tracking numbers; the
    same tracking on several DNs counted once; returns/cancellations subtract."""
    seen_tracking = set()
    total = 0.0
    for r in rows:
        if r.get("docstatus") != 1:
            continue
        tr = r.get("tracking")
        if tr:
            if tr in seen_tracking:
                continue
            seen_tracking.add(tr)
        q = float(r.get("qty") or 0)
        kind = r.get("kind")
        total += -abs(q) if kind in ("return", "cancel") else q
    return total


def split_by_eta(rows):
    dated = [r for r in rows if r.get("eta_ok")]
    undated = [r for r in rows if not r.get("eta_ok")]
    return dict(dated_total=harvest_total(dated), undated_total=harvest_total(undated),
                dated_rows=len(dated), undated_rows=len(undated))


def require_evidence(row):
    missing = []
    for field, label in (("stock", "库存"), ("uom", "单位"), ("item", "物料")):
        if row.get(field) in (None, ""):
            missing.append(label)
    if row.get("supply_expected") and not row.get("eta_ok"):
        missing.append("ETA")
    return missing


def gap_or_unknown(stock, demand):
    return None if stock is None else max(0.0, float(demand) - float(stock))


def warehouse_gaps(rows):
    return [dict(warehouse=r["warehouse"], gap=gap_or_unknown(r.get("stock"), r.get("demand")))
            for r in rows]


def aggregate_with_unknown(values):
    known = [v for v in values if v is not None]
    return dict(total=sum(known), known=len(known), unknown=len(values) - len(known))


def shared_allocation(total, skus, rule=None):
    if rule is None:
        return None
    return [float(total) * rule.get(s, 0.0) for s in skus]


def bucket_gaps(buckets):
    """Per-bucket conservation with carried unserved demand."""
    out = []
    prev_closing = 0.0
    carried = 0.0
    for b in buckets:
        opening = float(b["opening"]) if b.get("opening") is not None else prev_closing
        receipts = float(b.get("receipts") or 0.0)
        demand = float(b.get("demand") or 0.0) + carried
        fulfilled = min(demand, opening + receipts)
        closing = opening + receipts - fulfilled
        unserved = demand - fulfilled
        out.append(dict(name=b.get("name", ""), opening=opening, receipts=receipts,
                        demand=demand, fulfilled=fulfilled, closing=closing,
                        unserved=unserved, gap=max(0.0, unserved)))
        prev_closing = closing
        carried = unserved
    return out


def assert_bucket_identities(bucket_row, tol=1e-9):
    """opening+receipts-fulfilled=closing and total_demand-fulfilled=unserved."""
    lhs = bucket_row["opening"] + bucket_row["receipts"] - bucket_row["fulfilled"]
    assert abs(lhs - bucket_row["closing"]) <= tol, "opening+receipts-fulfilled != closing"
    rhs = bucket_row["demand"] - bucket_row["fulfilled"]
    assert abs(rhs - bucket_row["unserved"]) <= tol, "total_demand-fulfilled != unserved"


def choose_rate(t5, t3):
    """Demand source is T5 (AutoETS eq-rate); T3 is a labelled fallback only."""
    if t5 not in (None, ""):
        return float(t5), "T5_AutoETS_eq_rate"
    if t3 not in (None, ""):
        return float(t3), "T3_3month_mean_fallback"
    return None, "missing"


def demand_rate(raw):
    """A negative forecast rate is an artifact, not negative demand: clamp to 0."""
    return max(0.0, float(raw))


def readiness_of(old_status: str, wo_observed: bool) -> str:
    """Old A/B/C -> readiness. An unobserved WO caps the row at 条件."""
    base = {"A": "已确认", "B": "条件", "B_pending_inventory": "条件",
            "C": "HOLD"}.get(old_status, "研究")
    if not wo_observed and base == "已确认":
        return "条件"          # never promote a row whose WO is unknown
    return base


# ---------------------------------------------------------------------------
# Row pipeline
# ---------------------------------------------------------------------------

def num(x):
    try:
        return float(x)
    except Exception:
        return None


SCENARIOS = [
    ("S_overlap0_onhand", 0.0, "on_hand"),
    ("S_overlap_proven_onhand", 1.0, "on_hand"),
    ("S_overlap0_same_batch", 0.0, "same_batch"),
    ("S_overlap0_diff_batch", 0.0, "diff_batch"),
]


def main() -> None:
    dec = list(csv.DictReader((BP / "decision_v2.csv").open(encoding="utf-8-sig")))
    rep = {(r["SKU"], r["仓"]): r for r in csv.DictReader(
        (BP / "replenishment_v2.csv").open(encoding="utf-8-sig"))}

    rows_out, buckets_out = [], []
    tiers = Counter()
    readiness = Counter()
    reasons = Counter()
    sources = Counter()
    identity_fail = 0
    scen_totals = defaultdict(lambda: dict(demand=0.0, receipts=0.0, fulfilled=0.0,
                                           unserved_sum=0.0, unserved_end=0.0,
                                           closing_end=0.0))
    periods = bucket_bounds()
    names = [p[0] for p in periods]

    for r in dec:
        sku, wh = r["SKU"], r["仓"]
        rr = rep.get((sku, wh), {})
        rate, source = choose_rate(rr.get("新预测等效率(T5)"), rr.get("历史率(T3)"))
        available = num(r.get("可用"))
        waiting = num(r.get("已承诺待发")) or 0.0
        transit = num(r.get("在途")) or 0.0
        po = num(r.get("PO未结")) or 0.0
        old = r.get("状态", "")
        wo_observed = False          # every row: work_order_not_in_snapshot
        ready = readiness_of(old, wo_observed)

        if rate is None or available is None:
            missing = "需求" if rate is None else "库存"
            tiers["不能算"] += 1
            reasons[missing] += 1
            readiness["HOLD"] += 1
            rows_out.append(dict(sku=sku, warehouse=wh, scenario_id="S0_证据不足",
                                 readiness="HOLD", old_status=old, tier="不能算",
                                 reason=missing, demand_source="missing",
                                 forecast_rate="", stock_net="", stock_gross="",
                                 inventory_basis="unknown", so_unfulfilled="",
                                 so_negative="", overlap_proven="unknown",
                                 batch_same="", batch_diff="",
                                 dedupe_state="", wo_qty="", wo_status="not_observed",
                                 gap_low="", gap_high="",
                                 assumptions=f"缺 {missing} → unknown，不填 0"))
            continue

        sources[source] += 1
        rate_raw = rate
        if rate < 0:
            sources["negative_rate_clamped"] = sources.get("negative_rate_clamped", 0) + 1
        rate = demand_rate(rate)
        stock_net = max(0.0, available - waiting)
        batches = batch_supply(po, transit, r.get("在途去重状态"))
        forecast_b = [horizon_demand(rate, a, b) for _n, a, b in periods]
        forecast_total = sum(forecast_b)
        # a negative "committed" value is a return/credit, not demand: never
        # subtract it from demand (it is recorded separately)
        so_total = max(0.0, waiting)
        so_negative = min(0.0, waiting)
        share = [f / forecast_total if forecast_total else 0.0 for f in forecast_b]

        low = high = None
        for scen_id, overlap_ratio, supply_kind in SCENARIOS:
            overlap = min(forecast_total, so_total) * overlap_ratio
            supply_total = (batches["same_batch"] if supply_kind == "same_batch"
                            else batches["different_batch"] if supply_kind == "diff_batch"
                            else 0.0)
            comp = []
            for i, (name, a, b) in enumerate(periods):
                overlap_b = overlap * share[i]
                included_so_b = so_total * share[i]
                comp.append(dict(name=name,
                                 opening=(stock_net if i == 0 else None),
                                 receipts=(supply_total if i == 0 else 0.0),
                                 demand=forecast_b[i] - overlap_b + included_so_b))
            chain = bucket_gaps(comp)
            prev_unserved = 0.0
            for i, c in enumerate(chain):
                try:
                    assert_bucket_identities(c)
                except AssertionError:
                    identity_fail += 1
                new_demand = forecast_b[i] - overlap * share[i] + so_total * share[i]
                buckets_out.append(dict(
                    sku=sku, warehouse=wh, scenario_id=scen_id, bucket=names[i],
                    opening=round(c["opening"], 6),
                    forecast=round(forecast_b[i], 6),
                    included_SO=round(so_total * share[i], 6),
                    overlap=round(overlap * share[i], 6),
                    new_demand=round(new_demand, 6),
                    carried_in=round(prev_unserved, 6),
                    total_demand=round(c["demand"], 6),
                    receipts=round(c["receipts"], 6),
                    allocated_supply=round(c["receipts"], 6),
                    fulfilled=round(c["fulfilled"], 6),
                    unserved=round(c["unserved"], 6),
                    closing=round(c["closing"], 6)))
                prev_unserved = c["unserved"]
            t = scen_totals[scen_id]
            for i, c in enumerate(chain):
                t["demand"] += (forecast_b[i] - overlap * share[i] + so_total * share[i])
                t["receipts"] += c["receipts"]
                t["fulfilled"] += c["fulfilled"]
                t["unserved_sum"] += c["unserved"]
            t["unserved_end"] += chain[-1]["unserved"]
            t["closing_end"] += chain[-1]["closing"]
            if scen_id == "S_overlap0_onhand":
                low = chain[-1]["unserved"]
            if scen_id == "S_overlap_proven_onhand":
                high = chain[-1]["unserved"]

        tiers["B"] += 1
        readiness[ready] += 1
        rows_out.append(dict(
            sku=sku, warehouse=wh, scenario_id="S_overlap0_onhand", readiness=ready,
            old_status=old, tier="B", reason="",
            demand_source=source, forecast_rate=round(rate, 6),
            forecast_rate_raw=round(rate_raw, 6),
            stock_net=round(stock_net, 6), stock_gross=round(available, 6),
            inventory_basis="unknown", so_unfulfilled=round(so_total, 6),
            so_negative=round(so_negative, 6), overlap_proven="unknown",
            batch_same=round(batches["same_batch"], 6),
            batch_diff=round(batches["different_batch"], 6),
            dedupe_state=batches["dedupe_state"],
            wo_qty="", wo_status="not_observed",
            gap_low=round(low, 3) if low is not None else "",
            gap_high=round(high, 3) if high is not None else "",
            assumptions=("需求=T5 等效率（含失败回退）；snapshot 锚定，未另扣运行日消耗；"
                         "available/SO 语义未证→overlap 情景；在途疑似同批→same/diff 并列；"
                         "WO 未观测→不计且不升级为已确认")))

    with (BP / "forward_net_rows.csv").open("w", encoding="utf-8-sig", newline="") as fh:
        w = csv.DictWriter(fh, fieldnames=list(rows_out[0].keys()))
        w.writeheader()
        w.writerows(rows_out)
    with (BP / "forward_net_buckets.csv").open("w", encoding="utf-8-sig", newline="") as fh:
        w = csv.DictWriter(fh, fieldnames=list(buckets_out[0].keys()))
        w.writeheader()
        w.writerows(buckets_out)

    summary = dict(
        schema_version="forward_net/3",
        snapshot=dict(as_of=SNAPSHOT.isoformat(), run_date=RUN_DATE.isoformat(),
                      anchor="snapshot_anchored（桶 1 从快照日起，完整保留后续需求；不另扣已过天数）"),
        demand_source=dict(counts=dict(sources),
                           note=("T5 = 新预测等效率（AutoETS，失败回退 MA3，statsforecast 2.1.1）；"
                                 "decision_v2.月需求率 是 T3 三月均值，本口径不使用")),
        field_semantics=dict(inventory_basis="unknown", overlap="scenario",
                             same_batch="unknown_suspected → same/diff 并列"),
        wo=dict(wo_qty=None, wo_status="not_observed",
                note="不计未知 WO ≠ 供应完整；不得因此升级已确认"),
        rows=len(rows_out), row_tiers=dict(tiers),
        reconcile=f"{tiers.get('B',0)} + {tiers.get('不能算',0)} = {len(rows_out)}",
        reconcile_ok=(sum(tiers.values()) == len(rows_out)),
        readiness=dict(readiness), reasons=dict(reasons),
        buckets=len(buckets_out), identity_failures=identity_fail,
        scenario_totals={k: {kk: round(vv, 1) for kk, vv in v.items()}
                         for k, v in scen_totals.items()},
        naming=dict(B="条件", A="已确认（复核后）", C="HOLD"),
        model_interface=dict(current="T5 AutoETS 等效率（MA3 回退）", switch="待 Codex2 裁定"),
    )
    (BP / "forward_net.json").write_text(
        json.dumps(summary, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    print(json.dumps(dict(rows=summary["rows"], tiers=summary["row_tiers"],
                          readiness=summary["readiness"],
                          sources=summary["demand_source"]["counts"],
                          buckets=summary["buckets"], identity_failures=identity_fail,
                          scen=summary["scenario_totals"],
                          reconcile_ok=summary["reconcile_ok"]), ensure_ascii=False))


if __name__ == "__main__":
    main()
