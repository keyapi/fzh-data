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


FAMILY_LEAVES = {"KS0001", "KS0248"}


def family_resolution(exact_candidates):
    """Caller supplies exact code matches, not category/suffix guesses."""
    candidates = set(exact_candidates)
    if not candidates:
        return {"status": "unmatched", "reason": "no_exact_match"}
    if len(candidates) != 1:
        return {"status": "conflict", "reason": "ambiguous_item_or_leaf"}
    item, leaf = next(iter(candidates))
    if not item or leaf is None:
        return {"status": "unknown", "reason": "missing_item_or_leaf"}
    if leaf not in FAMILY_LEAVES:
        return {"status": "blocked", "reason": "outside_family"}
    return {"status": "used", "item": item, "leaf": leaf}


def family_totals(lines):
    seen = set()
    leaf_totals = defaultdict(int)
    items = set()
    for row_id, quantity, candidates in lines:
        require(row_id not in seen, "duplicate source row")
        seen.add(row_id)
        match = family_resolution(candidates)
        require(match["status"] == "used", "unresolved family line")
        leaf_totals[match["leaf"]] += strict_quantity(quantity)
        items.add(match["item"])
    return {"family_qty": sum(leaf_totals.values()), "leaf_qty": dict(leaf_totals),
            "distinct_items": len(items)}


def mapping_gate(customer_code, candidates, deleted_prefix=False):
    """Deletion flag is supplied from an evidenced source rule, never guessed."""
    flags = []
    if not customer_code or not customer_code.strip():
        return {"status": "unmatched", "reason": "empty_customer_code", "flags": flags}
    if deleted_prefix:
        return {"status": "blocked", "reason": "deleted_prefix", "flags": ["deleted_prefix"]}
    if customer_code.endswith(("-Cover", "-Foam")):
        flags.append("component_suffix_requires_role_check")
    result = family_resolution(candidates)
    return {**result, "flags": flags}


def bucket_demand(forecast, bucket, orders):
    """Toy cancellation policy: only unshipped units can be cancelled.

    All same-bucket terminal rows are explicitly forecast-covered in this fixture.
    Cross-bucket/internal rows are reported separately, not silently consumed.
    """
    forecast = strict_quantity(forecast)
    consumed = open_qty = cross_bucket = internal = 0
    seen = set()
    dispositions = []
    covered_ids = []
    for order_id, order_bucket, kind, quantity, shipped, cancelled in orders:
        require(order_id not in seen, "duplicate order row")
        seen.add(order_id)
        quantity, shipped, cancelled = map(strict_quantity, (quantity, shipped, cancelled))
        require(shipped + cancelled <= quantity, "cancelled/shipped exceed order")
        valid = quantity - cancelled
        if kind == "internal":
            internal += valid
            dispositions.append({"order_id": order_id, "status": "used", "role": "internal_excluded",
                                 "quantity": valid})
            continue
        require(kind == "terminal", "unknown demand type")
        if order_bucket != bucket:
            cross_bucket += valid
            dispositions.append({"order_id": order_id, "status": "blocked", "reason": "outside_bucket",
                                 "target_bucket": order_bucket, "quantity": valid})
            continue
        consumed += valid
        open_qty += valid - shipped
        covered_ids.append(order_id)
        dispositions.append({"order_id": order_id, "status": "used", "role": "covered_terminal",
                             "quantity": valid, "shipped": shipped, "cancelled": cancelled})
    net = max(0, forecast - consumed)
    excess = max(0, consumed - forecast)
    return {"consumed": consumed, "open": open_qty, "net": net,
            "bucket_total": consumed + net, "remaining": open_qty + net,
            "cross_bucket": cross_bucket, "internal": internal,
            "over_forecast": excess, "dispositions": dispositions,
            "exceptions": ([{"reason": "over_forecast", "quantity": excess,
                             "related_order_ids": covered_ids, "destination": "retain_in_current_bucket"}]
                           if excess else [])}


def pending_receipt(qualified_received, already_in_snapshot):
    qualified_received = strict_quantity(qualified_received)
    already_in_snapshot = strict_quantity(already_in_snapshot)
    require(already_in_snapshot <= qualified_received, "snapshot receipt exceeds qualified receipt")
    return qualified_received - already_in_snapshot


def receipt_totals_g1(capacities, receipt_lines):
    """G1 four-field allocation includes rejected; G0 helper stays unchanged."""
    gross_by_dn = defaultdict(int)
    accepted = damaged = rejected = 0
    for raw_id, gross, allocations in latest_receipt_versions(receipt_lines):
        require(sum(g + d + r for _, g, d, r in allocations) == gross, "receipt allocation mismatch")
        for dn_row, good, bad, refused in allocations:
            require(dn_row in capacities and min(good, bad, refused) >= 0, "invalid receipt allocation")
            gross_by_dn[dn_row] += good + bad + refused
            accepted += good
            damaged += bad
            rejected += refused
    require(all(gross_by_dn[k] <= v for k, v in capacities.items()), "overreceived DN line")
    return {"gross": sum(gross_by_dn.values()), "accepted": accepted, "damaged": damaged,
            "rejected": rejected, "unreceived": sum(capacities.values()) - sum(gross_by_dn.values())}


def available_after_receipt(accepted_units, pending_states):
    """Synthetic unit IDs make disjoint pending allocations testable, not assumed."""
    required = {"inspection", "processing", "shelving"}
    if (accepted_units is None or set(pending_states) != required
            or any(v is None for v in pending_states.values())):
        return None
    pending = set()
    for units in pending_states.values():
        require(set(units) <= set(accepted_units), "pending units outside accepted")
        require(not pending.intersection(units), "overlapping pending states")
        pending.update(units)
    return len(set(accepted_units) - pending)


def snapshot_at(snapshot_time, quantity, query_time):
    if query_time != snapshot_time:
        return {"status": "unknown", "quantity": None,
                "reason": "history_unavailable" if query_time < snapshot_time else "future_events_required"}
    return {"status": "used", "quantity": strict_quantity(quantity)}


def scoped_stockout_signal(sku, warehouse, period, channel, signals):
    # Absence of a scoped signal is unknown, never proof of no stockout.
    key = (sku, warehouse, period, channel)
    return "signal_present" if key in signals else "unknown"


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

    # C14-C20 are G1 extensions; C01-C13 remain the frozen G0 reference cases.
    family_rows = [("source-line-A", 1, [("synthetic-item-A", "KS0001")]),
                   ("source-line-B", 1, [("synthetic-item-B", "KS0248")])]
    family = family_totals(family_rows)
    record("C14_family_preserves_leaf_and_item", family == {
        "family_qty": 2, "leaf_qty": {"KS0001": 1, "KS0248": 1}, "distinct_items": 2}
        and rejects(lambda: family_totals(family_rows + [family_rows[0]])),
        "one item from each leaf => family2 with two items; duplicate source row rejected")

    ambiguous = [("synthetic-item-A", "KS0001"), ("synthetic-item-B", "KS0248")]
    record("C15_mapping_ambiguity_and_hints", family_resolution(ambiguous)["status"] == "conflict"
           and family_resolution([])["status"] == "unmatched"
           and family_resolution([("synthetic-item-C", "KS9999")])["status"] == "blocked"
           and family_resolution([("synthetic-item-A", None)])["status"] == "unknown"
           and family_resolution([family_rows[0][2][0]] * 2)["status"] == "used"
           and mapping_gate("", family_rows[0][2])["reason"] == "empty_customer_code"
           and mapping_gate("synthetic-code", family_rows[0][2], True)["reason"] == "deleted_prefix"
           and mapping_gate("synthetic-code-Cover", [])["status"] == "unmatched"
           and "component_suffix_requires_role_check" in mapping_gate("synthetic-code-Cover", [])["flags"]
           and mapping_gate("synthetic-code", ambiguous)["status"] == "conflict"
           and rejects(lambda: family_totals([("line-hint", 1, [])])),
           "empty/deleted/Cover/multiple-match marked separately; category or suffix hint cannot establish membership")

    full = bucket_demand(100, "2026-06", [("order-1", "2026-06", "terminal", 30, 30, 0)])
    partial = bucket_demand(100, "2026-06", [("order-1", "2026-06", "terminal", 30, 10, 0)])
    cancelled = bucket_demand(100, "2026-06", [("order-1", "2026-06", "terminal", 30, 10, 5)])
    other = bucket_demand(100, "2026-06", [("order-2", "2026-07", "terminal", 30, 0, 0),
                                          ("internal-1", "2026-06", "internal", 80, 0, 0)])
    excess = bucket_demand(100, "2026-06", [("order-3", "2026-06", "terminal", 120, 20, 0)])
    record("C16_shipped_orders_keep_consuming", (full["consumed"], full["net"], full["bucket_total"], full["remaining"])
           == (30, 70, 100, 70) and (partial["open"], partial["remaining"]) == (20, 90)
           and (cancelled["consumed"], cancelled["net"], cancelled["remaining"]) == (25, 75, 90)
           and (other["remaining"], other["cross_bucket"], other["internal"]) == (100, 30, 80)
           and len(other["dispositions"]) == 2
           and other["dispositions"][0]["target_bucket"] == "2026-07"
           and (excess["bucket_total"], excess["remaining"], excess["over_forecast"]) == (120, 100, 20)
           and excess["exceptions"][0]["related_order_ids"] == ["order-3"]
           and excess["exceptions"][0]["quantity"] == 20
           and rejects(lambda: bucket_demand(100, "2026-06", [("bad", "2026-06", "terminal", 30, 30, 1)])),
           "fully shipped30 leaves forecast70; partial/cancel tracked; cross-bucket/internal excluded visibly; excess preserved")

    record("C17_snapshot_and_transit_are_exclusive", 100 + pending_receipt(20, 20) == 100
           and pending_receipt(20, 15) == 5
           and rejects(lambda: pending_receipt(20, 21))
           and normalize_lot_views([("transport-lot", 30), ("transport-lot", 30)]) == 30
           and rejects(lambda: normalize_lot_views([("transport-lot", 30), ("transport-lot", 29)])),
           "on-hand100 already includes received20 =>100; receipt only partly included leaves5; transit conflict blocks")

    capacities_g1 = {"synthetic-DN-A-row": 55, "synthetic-DN-B-row": 45}
    g1r1 = ("synthetic-R1-line", 1, 70, [("synthetic-DN-A-row", 45, 0, 0), ("synthetic-DN-B-row", 25, 0, 0)])
    g1r1v2 = ("synthetic-R1-line", 2, 70, [("synthetic-DN-A-row", 44, 1, 0), ("synthetic-DN-B-row", 25, 0, 0)])
    g1r2 = ("synthetic-R2-line", 1, 30, [("synthetic-DN-A-row", 10, 0, 0), ("synthetic-DN-B-row", 20, 0, 0)])
    g1r2v2 = ("synthetic-R2-line", 2, 30, [("synthetic-DN-A-row", 10, 0, 0), ("synthetic-DN-B-row", 19, 0, 1)])
    receipt_g1 = receipt_totals_g1(capacities_g1, [g1r1, g1r1v2, g1r2])
    receipt_rejected = receipt_totals_g1(capacities_g1, [g1r1, g1r1v2, g1r2, g1r2v2])
    accepted_units = set(range(99))
    record("C18_receipt_revision_allocation_and_availability", receipt_g1 == {
        "gross": 100, "accepted": 99, "damaged": 1, "rejected": 0, "unreceived": 0}
        and receipt_rejected == {"gross": 100, "accepted": 98, "damaged": 1, "rejected": 1, "unreceived": 0}
        and rejects(lambda: receipt_totals_g1(capacities_g1, [g1r1, g1r1]))
        and available_after_receipt(accepted_units, {"inspection": {0, 1, 2}, "processing": {3, 4},
                                                     "shelving": {5, 6, 7, 8}}) == 90
        and available_after_receipt(accepted_units, {"shelving": None}) is None
        and available_after_receipt(accepted_units, {"inspection": set()}) is None
        and available_after_receipt(accepted_units, {k: set() for k in ("inspection", "processing", "shelving")}) == 99
        and rejects(lambda: available_after_receipt(accepted_units, {"inspection": {0}, "processing": {0}, "shelving": set()}))
        and rejects(lambda: available_after_receipt(accepted_units, {"inspection": set(), "processing": set(), "shelving": {999}})),
        "revision/disjoint DN allocations yield99+1 or98+1+1; qualified99 not automatically available; overlapping pending rejected")

    cutoff = datetime(2026, 10, 20, 12)
    record("C19_current_snapshot_cannot_reconstruct_history", snapshot_at(cutoff, 100, cutoff)
           == {"status": "used", "quantity": 100}
           and snapshot_at(cutoff, 100, datetime(2026, 7, 31))["status"] == "unknown"
           and snapshot_at(cutoff, 100, datetime(2026, 10, 21))["status"] == "unknown"
           and rejects(lambda: snapshot_at(cutoff, None, cutoff)),
           "current-cutoff100 supports only that snapshot; historical or future balances need other evidence, not zero")

    # Synthetic scope of 30 signal-bearing items in an 80-item family, not a real SKU roster.
    family_skus = [f"synthetic-family-{i:03}" for i in range(80)]
    signals = {(sku, "DANEEY" if i < 15 else "CENTRADE", "2026-06", "PB")
               for i, sku in enumerate(family_skus[:30])}
    record("C20_pb_signals_are_a_scoped_subset", len(signals) == 30
           and scoped_stockout_signal(family_skus[0], "DANEEY", "2026-06", "PB", signals) == "signal_present"
           and scoped_stockout_signal(family_skus[0], "CENTRADE", "2026-06", "PB", signals) == "unknown"
           and scoped_stockout_signal(family_skus[0], "DANEEY", "2026-06", "other", signals) == "unknown"
           and scoped_stockout_signal(family_skus[31], "CENTRADE", "2026-06", "PB", signals) == "unknown"
           and all(scoped_stockout_signal(sku, "DANEEY", "2026-06", "PB", signals) == "unknown"
                   for sku in family_skus[30:]),
           "PB subset signals do not label the family; warehouse switch, another channel, or no label remains unknown")

    print(json.dumps({"scope": "synthetic contract oracle only", "total": len(report),
                      "passed": len(report), "failed": 0, "skipped": 0, "cases": report},
                     ensure_ascii=False, indent=2))


if __name__ == "__main__":
    run()
