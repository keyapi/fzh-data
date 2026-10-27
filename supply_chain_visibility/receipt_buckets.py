"""Place upstream-approved free supply into half-open, timezone-aware buckets.

This module does not prove identity, UOM, allocation, completeness or deduplicate
batches. Call it after Jack's supply gates, not on raw PO/DN/Shipment quantities.
"""
from collections import Counter
from datetime import datetime
from decimal import Decimal, InvalidOperation


def _instant(value):
    if isinstance(value, str):
        try:
            value = datetime.fromisoformat(value.replace("Z", "+00:00"))
        except ValueError:
            return None
    if not isinstance(value, datetime) or value.utcoffset() is None:
        return None
    return value


def _quantity(value):
    if value is None or isinstance(value, bool):
        return None
    try:
        number = Decimal(str(value))
    except (InvalidOperation, ValueError, TypeError):
        return None
    return number if number.is_finite() and number >= 0 else None


def bucket_receipts(events, *, target, as_of, buckets):
    """Return Decimal receipts, one disposition per event and a per-unit ledger.

    ``target`` is (sku, warehouse, uom). Buckets are (id, start, end), [start,end).
    Events are mappings, typically ``dataclasses.asdict(SupplyRow)`` augmented
    with stable ``event_id`` and upstream ``allocation_status`` (free/fba/unknown).
    ``available_at`` or canonical ``available_date`` must be an aware instant.
    Day-only dates cannot locate same-day arrivals relative to a stock snapshot;
    they are unresolved here, never silently assumed to arrive at midnight.

    ``has_unresolved=False`` only describes these supplied events. It does not
    establish that upstream sources cover the full supply universe.
    """
    if len(target) != 3 or any(not isinstance(v, str) or not v.strip() for v in target):
        raise ValueError("target requires nonempty sku, warehouse and uom")
    target = tuple(target)
    as_of = _instant(as_of)
    if as_of is None:
        raise ValueError("as_of must be timezone-aware")
    windows, labels = [], set()
    for label, start, end in buckets:
        start, end = _instant(start), _instant(end)
        if (not isinstance(label, str) or not label or label in labels or
                start is None or end is None or start < as_of or start >= end):
            raise ValueError("invalid or duplicate bucket")
        labels.add(label)
        windows.append((label, start, end))
    windows.sort(key=lambda b: b[1])
    if not windows or any(a[2] > b[1] for a, b in zip(windows, windows[1:])):
        raise ValueError("buckets must be nonempty and nonoverlapping")

    receipts = {label: Decimal(0) for label, _, _ in windows}
    dispositions, ledger, ids, counts = [], {}, set(), Counter()
    unresolved = False
    unresolved_reasons = {"quantity_unproven", "identity_unproven", "date_unproven", "eligibility_unproven",
                          "allocation_unproven", "outside_buckets", "pre_asof_inclusion_unproven"}
    for event in events:
        key = event.get("event_id")
        if not isinstance(key, str) or not key.strip() or key in ids:
            raise ValueError("event_id must be nonempty and unique; upstream dedup required")
        ids.add(key)
        identity = tuple(event.get(k) for k in ("sku", "warehouse", "uom"))
        if any(v is not None and not isinstance(v, str) for v in identity):
            raise ValueError("event identity must contain strings or null")
        qty = _quantity(event.get("qty"))
        instant = _instant(event.get("available_at", event.get("available_date")))
        bucket = None
        if qty is None:
            reason = "quantity_unproven"
        elif any(v is None or not v.strip() for v in identity):
            reason = "identity_unproven"
        elif identity != target:
            reason = "target_mismatch"
        elif event.get("scope") == "external_fba" or event.get("allocation_status") == "fba":
            reason = "fba_allocated"
        elif event.get("b_min_eligible") is not True or event.get("scope") != "in_house":
            reason = "eligibility_unproven"
        elif event.get("allocation_status") != "free":
            reason = "allocation_unproven"
        elif event.get("source_layer") == "inventory_snapshot":
            reason = "opening_stock"
        elif instant is None or event.get("date_confidence") != "confirmed":
            reason = "date_unproven"
        elif instant <= as_of:
            reason = ("at_or_before_as_of" if event.get("included_in_opening_snapshot") is True
                      else "pre_asof_inclusion_unproven")
        elif instant >= windows[-1][2]:
            reason = "after_horizon"
        else:
            bucket = next((label for label, start, end in windows if start <= instant < end), None)
            reason = "counted" if bucket else "outside_buckets"
        if qty is not None:
            account = ledger.setdefault(identity, dict(input_known=Decimal(0),
                                                       counted=Decimal(0), excluded_known=Decimal(0)))
            account["input_known"] += qty
            account["counted" if bucket else "excluded_known"] += qty
        if bucket:
            receipts[bucket] += qty
        counts[reason] += 1
        unresolved |= reason in unresolved_reasons
        dispositions.append(dict(event_id=key, identity=identity, qty=qty,
                                 reason=reason, bucket=bucket))
    assert all(v["input_known"] == v["counted"] + v["excluded_known"] for v in ledger.values())
    return dict(receipts=receipts, dispositions=dispositions, counts=dict(counts),
                quantity_ledger=ledger, has_unresolved=unresolved,
                input_rows=len(dispositions), counted_rows=counts["counted"],
                excluded_rows=len(dispositions) - counts["counted"])
