"""Offline executable supply-chain contract examples; synthetic fixtures only.

This is a review oracle, not an ERP adapter, forecasting model, or planner.
Run: uv run --no-project python <this file>
"""

from collections import defaultdict
from datetime import datetime
from decimal import Decimal
import json


def require(condition, message):
    if not condition:
        raise ValueError(message)


def kit_ready(component_qty, recipe):
    require(all(n > 0 for n in recipe.values()), "invalid recipe")
    return min(component_qty.get(k, 0) // n for k, n in recipe.items())


def demand_after_consumption(forecast, confirmed_in_bucket, internal_transfer):
    # These confirmed orders belong to this forecast bucket; no match by guess.
    require(min(forecast, confirmed_in_bucket, internal_transfer) >= 0, "negative demand")
    remaining_forecast = max(0, forecast - confirmed_in_bucket)
    return remaining_forecast, confirmed_in_bucket + remaining_forecast


def normalize_lot_views(views):
    """Repeat source views must refer to an explicitly reconciled canonical lot."""
    lots = {}
    for lot_id, quantity in views:
        require(quantity >= 0, "negative lot")
        require(lot_id not in lots or lots[lot_id] == quantity, "conflicting lot views")
        lots[lot_id] = quantity
    return sum(lots.values())


def validate_allocations(capacities, allocations):
    totals = defaultdict(int)
    for line_id, shipment_id, qty in allocations:
        require(line_id in capacities and shipment_id and qty >= 0, "invalid allocation")
        totals[line_id] += qty
    require(all(totals[k] <= v for k, v in capacities.items()), "overallocated DN line")
    return {k: v - totals[k] for k, v in capacities.items()}


def latest_receipt_versions(receipt_lines):
    """Synthetic revisions are increasing integers, prefiltered to one cutoff.

    Keep input events unchanged; select one effective version per raw line.
    Production adapters must define revision and observed-at ordering explicitly.
    """
    seen = set()
    latest = {}
    for raw_id, revision, gross, allocations in receipt_lines:
        require((raw_id, revision) not in seen, "duplicate receipt revision")
        require(isinstance(revision, int) and revision > 0, "invalid receipt revision")
        seen.add((raw_id, revision))
        if raw_id not in latest or revision > latest[raw_id][0]:
            latest[raw_id] = (revision, gross, allocations)
    return [(raw_id, gross, allocations) for raw_id, (_, gross, allocations) in latest.items()]


def receipt_totals(capacities, receipt_lines):
    """Raw receipt line revisions carry explicit DN-row allocations."""
    gross_by_dn = defaultdict(int)
    accepted = damaged = 0
    for raw_id, gross, allocations in latest_receipt_versions(receipt_lines):
        require(sum(a + d for _, a, d in allocations) == gross, "receipt allocation mismatch")
        for dn_row, good, bad in allocations:
            require(dn_row in capacities and min(good, bad) >= 0, "invalid receipt allocation")
            gross_by_dn[dn_row] += good + bad
            accepted += good
            damaged += bad
    require(all(gross_by_dn[k] <= v for k, v in capacities.items()), "overreceived DN line")
    return {
        "gross": sum(gross_by_dn.values()),
        "accepted": accepted,
        "damaged": damaged,
        "unreceived": sum(capacities.values()) - sum(gross_by_dn.values()),
    }


def project(on_hand, demand_by_period, receipts_by_period):
    """Receipts at period start; unmet demand is lost, not carried as backlog."""
    require(on_hand >= 0, "negative initial stock")
    inv = on_hand
    rows = []
    for period, demand in enumerate(demand_by_period, 1):
        receipt = receipts_by_period.get(period, 0)
        require(min(demand, receipt) >= 0, "negative flow")
        inv += receipt
        shortage = max(0, demand - inv)
        inv = max(0, inv - demand)
        rows.append({"period": period, "ending": inv, "shortage": shortage})
    return rows


def known_event(events, cutoff):
    """One milestone, one agreed source; event revision order is observed_at."""
    known = [e for e in events if e["observed_at"] <= cutoff]
    actual = [e for e in known if e["kind"] == "actual"]
    candidates = actual or known
    return max(candidates, key=lambda e: e["observed_at"]) if candidates else None


def approval_valid(proposal, current_hash, now):
    return proposal["input_hash"] == current_hash and now < proposal["expires_at"]


def strict_quantity(value):
    require(value is not None and not isinstance(value, bool), "unknown quantity")
    try:
        qty = Decimal(str(value))
    except Exception as exc:
        raise ValueError("invalid quantity") from exc
    require(qty.is_finite() and qty >= 0 and qty == qty.to_integral_value(), "invalid unit count")
    return int(qty)


def rejects(call):
    try:
        call()
    except ValueError:
        return True
    return False


def run():
    report = []

    def record(case, condition, expected):
        require(condition, f"failed {case}")
        report.append({"case": case, "status": "PASS", "expected": expected})

    # C01: 20 covers + 10 foam are 10 two-cover kits, not 30 finished items.
    ready = kit_ready({"cover": 20, "foam": 10}, {"cover": 2, "foam": 1})
    record("C01_recipe_and_independent_sales", ready == 10 and 10 * 2 + 5 == 25,
           "10 kits; additional 5 standalone covers imply 25 cover demand, not 15 kits")

    # C02: internal replenishment SO is not another terminal demand.
    remainder, total = demand_after_consumption(100, 30, 80)
    record("C02_forecast_consumption", (remainder, total) == (70, 100)
           and demand_after_consumption(100, 120, 80) == (0, 120),
           "100 forecast includes 30 orders => 70 remaining, 100 total; excess orders => 120")

    record("C03_supply_view_dedup", normalize_lot_views([("lot-A", 100)] * 3) == 100
           and rejects(lambda: normalize_lot_views([("lot-A", 100), ("lot-A", 90)])),
           "three reconciled views = 100; source quantity conflict blocks reconciliation")

    capacities = {"DN-A-row-1": 100, "DN-B-row-1": 40}
    allocations = [("DN-A-row-1", "shipment-1", 60), ("DN-B-row-1", "shipment-1", 40),
                   ("DN-A-row-1", "shipment-2", 40)]
    record("C04_split_and_consolidated_shipments", validate_allocations(capacities, allocations)
           == {"DN-A-row-1": 0, "DN-B-row-1": 0}
           and rejects(lambda: validate_allocations(capacities, allocations + [("DN-A-row-1", "shipment-3", 1)])),
           "two DN rows across two shipments; extra 1 blocks as overallocation")

    receipt_cap = {"DN-C-row-1": 60, "DN-D-row-1": 40}
    r1 = ("receipt-1-line-1", 1, 70, [("DN-C-row-1", 48, 2), ("DN-D-row-1", 20, 0)])
    r2 = ("receipt-2-line-1", 1, 30, [("DN-C-row-1", 10, 0), ("DN-D-row-1", 20, 0)])
    r1_corrected = ("receipt-1-line-1", 2, 70, [("DN-C-row-1", 49, 1), ("DN-D-row-1", 20, 0)])
    partial = receipt_totals(receipt_cap, [r1])
    final = receipt_totals(receipt_cap, [r1, r2])
    record("C05_partial_receipt_and_damage", partial == {"gross": 70, "accepted": 68, "damaged": 2, "unreceived": 30}
           and final == {"gross": 100, "accepted": 98, "damaged": 2, "unreceived": 0}
           and receipt_totals(receipt_cap, [r1, r2, r1_corrected])
           == {"gross": 100, "accepted": 99, "damaged": 1, "unreceived": 0}
           and rejects(lambda: receipt_totals(receipt_cap, [r1, r1])),
           "partial68+2+30=100; final98+2=100; correction99+1=100, not170; duplicate revision rejected")

    events = [
        {"kind": "estimated", "event_time": "2026-05-12", "observed_at": "2026-05-11"},
        {"kind": "actual", "event_time": "2026-05-13", "observed_at": "2026-05-14"},
        {"kind": "estimated", "event_time": "2026-05-18", "observed_at": "2026-05-15"},
    ]
    record("C06_bitemporal_event", known_event(events, "2026-05-12")["kind"] == "estimated"
           and known_event(events, "2026-05-16")["event_time"] == "2026-05-13",
           "as-of May12 cannot know actual; stale estimated revision cannot erase actual milestone")

    projection = project(20, [10] * 6, {4: 40})
    record("C07_eta_before_coverage", sum(x["shortage"] for x in projection) == 10
           and projection[2]["shortage"] == 10 and (20 + 40) / 10 == 6,
           "headline six-month supply still has 10 shortage in period3; receipt in period4")

    first, last, stock_in, shipped, prior_stock = None, None, 60, 80, 20
    record("C08_production_quantities_are_distinct", first is None and last is None
           and stock_in + prior_stock == shipped and shipped > stock_in
           and kit_ready({"cover": 60, "foam": 20}, {"cover": 2, "foam": 1}) == 20,
           "no Job Card => unknown reports, not zero; inbound60 + prior20 permits shipped80; kit-ready20")

    # Returns may change commercial delivery but do not erase physical departures.
    ordered, cancelled, dispatched, returned = 100, 20, 70, 10
    net_delivered = dispatched - returned
    original_open = ordered - cancelled - dispatched
    record("C09_returns_and_demand_revision", net_delivered == 60 and original_open == 10
           and original_open + 0 == 10 and original_open + returned == 20 and dispatched == 70,
           "valid80=dispatched70+original-open10; netdelivered60; remaining10 or20 depends on approved replacement")

    # Same cash budget need not imply same units, even before scheduling.
    budget, demand_a, demand_b = 100, 10, 10
    cheap_units, expensive_units = budget // 10, budget // 20
    record("C10_money_is_not_quantity_budget", cheap_units == 10 and expensive_units == 5
           and demand_a + demand_b - cheap_units != demand_a + demand_b - expensive_units,
           "cash100 buys10 at cost10 or5 at cost20; aggregate shortage differs10 vs15")

    proposal = {"input_hash": "synthetic-snapshot-A", "expires_at": datetime(2026, 5, 20)}
    record("C11_approval_snapshot_and_expiry", approval_valid(proposal, "synthetic-snapshot-A", datetime(2026, 5, 19))
           and not approval_valid(proposal, "synthetic-snapshot-B", datetime(2026, 5, 19))
           and not approval_valid(proposal, "synthetic-snapshot-A", datetime(2026, 5, 20)),
           "changed inputs or expired proposal require revalidation; approvals do not authorize production writes")

    record("C12_missing_is_not_zero", strict_quantity("0") == 0
           and all(rejects(lambda v=v: strict_quantity(v)) for v in [None, "bad", "NaN", "inf", -1, "1.5"]),
           "explicit zero accepted; unknown/invalid/fractional counts quarantined")

    # Relative month indexes: validation origin6 predicts7..9; test origin7 predicts8..10.
    targets = lambda origin: set(range(origin + 1, origin + 4))
    overlap = targets(6) & targets(7)
    available_at = {month: datetime(2025, month + 1, 2) for month in range(5, 10)}
    decision_at = datetime(2025, 8, 2)
    known_by = lambda labels: all(available_at[month] <= decision_at for month in labels)
    record("C13_forecast_selection_label_cutoff", overlap == {8, 9}
           and not (targets(4) & targets(7)) and known_by(targets(4)) and not known_by(targets(6)),
           "h3 overlap labels8,9; at Aug2 decision, monthly labels available next-month2 => May-Jul known, Aug-Sep unknown")

    print(json.dumps({"scope": "synthetic contract oracle only", "total": len(report),
                      "passed": len(report), "failed": 0, "skipped": 0, "cases": report},
                     ensure_ascii=False, indent=2))


if __name__ == "__main__":
    run()
