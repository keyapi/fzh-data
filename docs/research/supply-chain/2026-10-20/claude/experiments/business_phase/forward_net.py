#!/usr/bin/env python
# -*- coding: utf-8 -*-
"""Forward net demand from the 2026-10-22 snapshot — SC02 R3 repair (OFFLINE).

The 301 review of 73f66437 found that the previous repair lived only in helper
functions: the MAIN flow still used `available - waiting` unconditionally and
still added the SO through a forecast-dependent share (forecast = 0 -> the SO
was wiped). R3 moves the real per-row flow into `compute_row()` and fixes it:

  M01 stock / demand basis — three explicit branches, one per scenario:
      physics   : `available` IS physical on-hand            -> opening = available
      net       : `available` already nets the occupancy      -> opening = available + waiting
      unknown   : both branches are emitted (gap range)
    Demand keeps the SO inside the forecast (overlap scenario) or outside it
    (extra-demand scenario); the SO is NEVER subtracted from stock as well.

  M01 SO allocation — `allocate_so()` with an explicit mode:
      "earliest"     : the whole SO lands in the first bucket (assumption)
      "proportional" : split by forecast share, falling back to "earliest" when
                       the forecast is zero (so a zero/negative forecast can
                       never wipe the SO)

  M02 source provenance — per row: actual method (AutoETS vs MA3), library
      version, fallback reason, and the sha256 of the source artifact; the raw
      and clamped rates are both kept with a counter.

Outputs (row level stays local):
  out/business_phase/forward_net.json
  out/business_phase/forward_net_rows.csv
  out/business_phase/forward_net_buckets.csv
  out/business_phase/forward_net_frozen.json   (hashes + input manifest)
"""
from __future__ import annotations

import csv
import hashlib
import json
from collections import Counter, defaultdict
from datetime import date
from pathlib import Path

BP = Path(__file__).resolve().parents[2] / "out" / "business_phase"
SNAPSHOT = date(2026, 10, 22)
RUN_DATE = date(2026, 10, 23)
BASE_DAYS = 31

# scenario: (id, stock_basis, overlap_ratio, supply_kind)
SCENARIOS = [
    ("S_phys_overlap0_onhand", "physical", 0.0, "on_hand"),
    ("S_net_overlap0_onhand", "net", 0.0, "on_hand"),
    ("S_phys_overlap_proven_onhand", "physical", 1.0, "on_hand"),
    ("S_net_overlap_proven_onhand", "net", 1.0, "on_hand"),
    ("S_phys_overlap0_same_batch", "physical", 0.0, "same_batch"),
    ("S_phys_overlap0_diff_batch", "physical", 0.0, "diff_batch"),
]


# ---------------------------------------------------------------------------
# Pure helpers
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


def opening_for_basis(basis, available, waiting):
    """Physical on-hand under an explicit inventory basis.

    physics   : available is physical on-hand
    net       : available already nets the occupancy -> add it back
    unknown   : return both ends (the caller turns them into a gap range)
    """
    available, waiting = float(available or 0), float(max(0.0, waiting or 0))
    if basis == "physical":
        return available
    if basis == "net":
        return available + waiting
    if basis == "unknown":
        return (available, available + waiting)
    raise ValueError(f"unknown inventory basis: {basis}")


def allocate_so(so_total, forecast_b, mode="earliest"):
    """Allocate the outstanding SO into buckets WITHOUT depending on a non-zero
    forecast. `proportional` falls back to `earliest` when the forecast is 0."""
    n = len(forecast_b)
    so_total = float(max(0.0, so_total or 0))
    if n == 0 or so_total == 0:
        return [0.0] * n
    total = float(sum(forecast_b))
    if mode == "earliest" or total <= 0:
        out = [0.0] * n
        out[0] = so_total
        return out
    if mode == "proportional":
        return [so_total * (f / total) for f in forecast_b]
    raise ValueError(f"unknown SO allocation mode: {mode}")


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
    lhs = bucket_row["opening"] + bucket_row["receipts"] - bucket_row["fulfilled"]
    assert abs(lhs - bucket_row["closing"]) <= tol, "opening+receipts-fulfilled != closing"
    rhs = bucket_row["demand"] - bucket_row["fulfilled"]
    assert abs(rhs - bucket_row["unserved"]) <= tol, "total_demand-fulfilled != unserved"


def choose_rate(t5, t3):
    if t5 not in (None, ""):
        return float(t5), "T5"
    if t3 not in (None, ""):
        return float(t3), "T3_fallback"
    return None, "missing"


def demand_rate(raw):
    """A negative forecast rate is an artifact, not negative demand: clamp to 0."""
    return max(0.0, float(raw))


def method_label(replen):
    """Name the ACTUAL method (AutoETS vs MA3 fallback), never a blanket T5."""
    raw = (replen or {}).get("预测方法(实际使用)") or ""
    if "MA3" in raw.upper():
        return "MA3_fallback"
    if "AutoETS" in raw:
        return "AutoETS"
    return raw or "unknown"


def readiness_of(old_status: str, wo_observed: bool) -> str:
    base = {"A": "已确认", "B": "条件", "B_pending_inventory": "条件",
            "C": "HOLD"}.get(old_status, "研究")
    if not wo_observed and base == "已确认":
        return "条件"
    return base


def num(x):
    try:
        return float(x)
    except Exception:
        return None


# ---------------------------------------------------------------------------
# The MAIN flow, extracted so the tests can call it
# ---------------------------------------------------------------------------

def compute_row(row, replen, periods=None, scenarios=None, so_mode="earliest"):
    """Compute one SKU x warehouse row and its per-bucket ledger.

    `row` and `replen` are plain dicts (CSV-shaped) so the tests can build
    synthetic inputs. Returns dict(record=..., buckets=[...], flags=...).
    """
    periods = periods or bucket_bounds()
    scenarios = scenarios or SCENARIOS
    sku, wh = row.get("SKU", ""), row.get("仓", "")
    t5 = (replen or {}).get("新预测等效率(T5)")
    t3 = (replen or {}).get("历史率(T3)")
    rate_raw, src_tag = choose_rate(t5, t3)
    available = num(row.get("可用"))
    waiting_all = num(row.get("已承诺待发"))
    waiting = waiting_all or 0.0
    transit = num(row.get("在途")) or 0.0
    po = num(row.get("PO未结")) or 0.0
    old = row.get("状态", "")
    wo_observed = False
    ready = readiness_of(old, wo_observed)
    method = method_label(replen)
    version = (replen or {}).get("方法版本") or ""
    fallback = (replen or {}).get("fallback理由") or ""
    demand_source = (f"{src_tag}_{method}" if src_tag in ("T5", "T3_fallback")
                     else "missing")

    if rate_raw is None or available is None:
        missing = "需求" if rate_raw is None else "库存"
        rec = dict(sku=sku, warehouse=wh, scenario_id="S0_证据不足",
                   readiness="HOLD", old_status=old, tier="不能算", reason=missing,
                   demand_source="missing", method=method, version=version,
                   fallback_reason=fallback,
                   forecast_rate="", forecast_rate_raw="", rate_clamped="",
                   stock_available="", stock_physical="", inventory_basis="unknown",
                   so_unfulfilled=round(max(0.0, waiting), 6),
                   so_negative=round(min(0.0, waiting), 6), so_allocation=so_mode,
                   overlap_proven="unknown", batch_same="", batch_diff="",
                   dedupe_state="", wo_qty="", wo_status="not_observed",
                   gap_low="", gap_high="",
                   assumptions=f"缺 {missing} → unknown，不填 0")
        return dict(record=rec, buckets=[], gaps={},
                    flags=dict(source=demand_source, clamped=False, missing=missing))

    rate = demand_rate(rate_raw)
    clamped = rate_raw < 0
    stock_avail = available
    stock_phys = available + max(0.0, waiting)
    batches = batch_supply(po, transit, row.get("在途去重状态"))
    forecast_b = [horizon_demand(rate, a, b) for _n, a, b in periods]
    forecast_total = sum(forecast_b)
    so_total = max(0.0, waiting)
    so_negative = min(0.0, waiting)
    so_b = allocate_so(so_total, forecast_b, so_mode)
    names = [p[0] for p in periods]

    buckets, gaps_by_scen = [], {}
    for scen_id, basis, overlap_ratio, supply_kind in scenarios:
        opening = opening_for_basis(basis, stock_avail, so_total)
        if isinstance(opening, tuple):
            opening = opening[0]        # unknown basis handled by caller scenarios
        overlap = min(forecast_total, so_total) * overlap_ratio
        overlap_b = [overlap * (f / forecast_total) if forecast_total else 0.0
                     for f in forecast_b]
        supply_total = (batches["same_batch"] if supply_kind == "same_batch"
                        else batches["different_batch"] if supply_kind == "diff_batch"
                        else 0.0)
        comp = []
        for i in range(len(periods)):
            # SO is allocated by `allocate_so`, never scaled by the forecast share
            # alone; the overlap only removes the *forecasted* duplicate part.
            comp.append(dict(name=names[i],
                             opening=(opening if i == 0 else None),
                             receipts=(supply_total if i == 0 else 0.0),
                             demand=forecast_b[i] - overlap_b[i] + so_b[i]))
        chain = bucket_gaps(comp)
        carried = 0.0
        for i, c in enumerate(chain):
            assert_bucket_identities(c)
            new_demand = forecast_b[i] - overlap_b[i] + so_b[i]
            buckets.append(dict(
                sku=sku, warehouse=wh, scenario_id=scen_id, inventory_basis=basis,
                so_allocation=so_mode, bucket=names[i],
                opening=round(c["opening"], 6), forecast=round(forecast_b[i], 6),
                included_SO=round(so_b[i], 6), overlap=round(overlap_b[i], 6),
                new_demand=round(new_demand, 6), carried_in=round(carried, 6),
                total_demand=round(c["demand"], 6), receipts=round(c["receipts"], 6),
                allocated_supply=round(c["receipts"], 6),
                fulfilled=round(c["fulfilled"], 6), unserved=round(c["unserved"], 6),
                closing=round(c["closing"], 6)))
            carried = c["unserved"]
        gaps_by_scen[scen_id] = chain[-1]["unserved"]

    onhand = [v for k, v in gaps_by_scen.items() if k.endswith("_onhand")]
    gap_low = max(onhand) if onhand else 0.0      # pessimistic end
    gap_high = min(onhand) if onhand else 0.0     # optimistic end

    rec = dict(
        sku=sku, warehouse=wh, scenario_id="S_phys_overlap0_onhand", readiness=ready,
        old_status=old, tier="B", reason="",
        demand_source=demand_source, method=method, version=version,
        fallback_reason=fallback,
        forecast_rate=round(rate, 6), forecast_rate_raw=round(rate_raw, 6),
        rate_clamped=int(clamped),
        stock_available=round(stock_avail, 6), stock_physical=round(stock_phys, 6),
        inventory_basis="unknown", so_unfulfilled=round(so_total, 6),
        so_negative=round(so_negative, 6), so_allocation=so_mode,
        overlap_proven="unknown",
        batch_same=round(batches["same_batch"], 6),
        batch_diff=round(batches["different_batch"], 6),
        dedupe_state=batches["dedupe_state"],
        wo_qty="", wo_status="not_observed",
        gap_low=round(gap_low, 3), gap_high=round(gap_high, 3),
        assumptions=("需求=T5 等效率（实际方法见 method）；snapshot 锚定；"
                     "库存口径 physical/net 并列；SO 按 "
                     f"{so_mode} 分桶（零预测不回退丢单）；"
                     "在途疑似同批→same/diff 并列；WO 未观测→不计且不升级"))
    return dict(record=rec, buckets=buckets, gaps=gaps_by_scen,
                flags=dict(source=demand_source, clamped=clamped, missing=""))


# ---------------------------------------------------------------------------
# main
# ---------------------------------------------------------------------------

def sha256(path: Path) -> str:
    h = hashlib.sha256()
    with path.open("rb") as fh:
        for chunk in iter(lambda: fh.read(1 << 20), b""):
            h.update(chunk)
    return h.hexdigest()


def main() -> None:
    dec_path = BP / "decision_v2.csv"
    rep_path = BP / "replenishment_v2.csv"
    dec = list(csv.DictReader(dec_path.open(encoding="utf-8-sig")))
    rep = {(r["SKU"], r["仓"]): r for r in csv.DictReader(rep_path.open(encoding="utf-8-sig"))}

    rows_out, buckets_out = [], []
    tiers = Counter()
    readiness = Counter()
    reasons = Counter()
    sources = Counter()
    methods = Counter()
    fallbacks = Counter()
    clamped_rows = 0
    parts = bucket_bounds()
    scen_totals = defaultdict(lambda: dict(demand=0.0, receipts=0.0, fulfilled=0.0,
                                           unserved_end=0.0))

    for r in dec:
        out = compute_row(r, rep.get((r["SKU"], r["仓"]), {}), parts)
        rec = out["record"]
        rows_out.append(rec)
        buckets_out.extend(out["buckets"])
        for scen, gap in out["gaps"].items():
            scen_totals[scen]["unserved_end"] += gap
        tiers[rec["tier"]] += 1
        readiness[rec["readiness"]] += 1
        if rec["reason"]:
            reasons[rec["reason"]] += 1
        if out["flags"]["source"] != "missing":
            sources[out["flags"]["source"]] += 1
            methods[rec["method"]] += 1
            if rec["fallback_reason"]:
                fallbacks[rec["fallback_reason"][:40]] += 1
            clamped_rows += int(rec["rate_clamped"] or 0)

    with (BP / "forward_net_rows.csv").open("w", encoding="utf-8-sig", newline="") as fh:
        w = csv.DictWriter(fh, fieldnames=list(rows_out[0].keys()))
        w.writeheader()
        w.writerows(rows_out)
    with (BP / "forward_net_buckets.csv").open("w", encoding="utf-8-sig", newline="") as fh:
        w = csv.DictWriter(fh, fieldnames=list(buckets_out[0].keys()))
        w.writeheader()
        w.writerows(buckets_out)

    for b in buckets_out:
        t = scen_totals[b["scenario_id"]]
        t["demand"] += b["new_demand"]
        t["receipts"] += b["receipts"]
        t["fulfilled"] += b["fulfilled"]

    manifest = dict(
        schema_version="forward_net/4",
        snapshot=dict(as_of=SNAPSHOT.isoformat(), run_date=RUN_DATE.isoformat(),
                      anchor="snapshot_anchored"),
        inputs=dict(decision_v2=dict(path=str(dec_path), sha256=sha256(dec_path)),
                    replenishment_v2=dict(path=str(rep_path), sha256=sha256(rep_path))),
        outputs=dict(rows=dict(path=str(BP / "forward_net_rows.csv"),
                               sha256=sha256(BP / "forward_net_rows.csv")),
                     buckets=dict(path=str(BP / "forward_net_buckets.csv"),
                                  sha256=sha256(BP / "forward_net_buckets.csv"))),
        demand_source=dict(counts=dict(sources), methods=dict(methods),
                           fallbacks=dict(fallbacks), clamps=clamped_rows,
                           note="逐行保存实际方法/版本/回退原因；AutoETS 与 MA3 回退可分辨"),
        inventory_basis=dict(branches=["physical", "net", "unknown"],
                             note="physical: opening=available；net: opening=available+waiting；"
                                  "unknown: 两个分支并列成缺口区间"),
        so_allocation=dict(modes=["earliest", "proportional"],
                           note="零预测时 proportional 回退 earliest，不会抹掉 SO"),
        wo=dict(wo_qty=None, wo_status="not_observed"),
        rows=len(rows_out), row_tiers=dict(tiers), readiness=dict(readiness),
        reasons=dict(reasons), buckets=len(buckets_out),
        scenario_totals={k: {kk: round(vv, 1) for kk, vv in v.items()}
                         for k, v in scen_totals.items()},
        naming=dict(B="条件", A="已确认（复核后）", C="HOLD"),
        model_interface=dict(current="T5 等效率（AutoETS / MA3 回退逐行标注）",
                             switch="待 Codex2 裁定"),
    )
    (BP / "forward_net.json").write_text(
        json.dumps(manifest, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    (BP / "forward_net_frozen.json").write_text(
        json.dumps(dict(schema_version="forward_net_frozen/1",
                        inputs=manifest["inputs"], outputs=manifest["outputs"],
                        generated_for="逐行复核：用 inputs + 脚本即可复算 outputs 的 sha256"),
                   ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    print(json.dumps(dict(rows=manifest["rows"], tiers=manifest["row_tiers"],
                          readiness=manifest["readiness"], sources=sources,
                          methods=dict(methods), clamps=clamped_rows,
                          buckets=manifest["buckets"],
                          scen=manifest["scenario_totals"]), ensure_ascii=False))


if __name__ == "__main__":
    main()
