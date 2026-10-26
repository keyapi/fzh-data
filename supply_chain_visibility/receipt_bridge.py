"""Bridge PO remaining, inventory snapshot, and receipt events without auto-adjusting.

The bridge exposes three numbers and their differences. It never adds a receipt
to available stock and never deducts it from in-transit.
"""
from __future__ import annotations

from collections import defaultdict
from dataclasses import dataclass
from datetime import datetime
from decimal import Decimal, InvalidOperation
from typing import Iterable, Optional, Union

from supply_chain_visibility.receipt_reconciliation import ReceiptEvent, SnapshotWindow


Timestamp = Union[str, datetime]


@dataclass(frozen=True)
class PoOpenRow:
    po_code: str
    sku: str
    warehouse: str
    qty: object
    uom: Optional[str]
    as_of: Optional[Timestamp] = None
    status: Optional[str] = None


@dataclass(frozen=True)
class InventoryRow:
    sku: str
    warehouse: str
    available: object
    uom: Optional[str]
    as_of: Optional[Timestamp] = None
    window_start: Optional[Timestamp] = None
    window_end: Optional[Timestamp] = None


@dataclass(frozen=True)
class TransitRow:
    sku: str
    warehouse: str
    qty: object
    uom: Optional[str]
    as_of: Optional[Timestamp] = None


def _decimal(value: object) -> Optional[Decimal]:
    if value is None or isinstance(value, bool):
        return None
    try:
        number = Decimal(str(value).strip())
    except (InvalidOperation, ValueError, AttributeError):
        return None
    if not number.is_finite() or number < 0:
        return None
    return number


def _aware(value: Optional[Timestamp]) -> Optional[datetime]:
    if value is None or value == "":
        return None
    if isinstance(value, datetime):
        parsed = value
    elif isinstance(value, str):
        try:
            parsed = datetime.fromisoformat(value.replace("Z", "+00:00"))
        except ValueError:
            return None
    else:
        return None
    if parsed.tzinfo is None or parsed.utcoffset() is None:
        return None
    return parsed


def _out(value: Optional[Decimal]) -> Optional[str]:
    return None if value is None else str(value)


def _window_bounds(windows: Optional[Iterable[SnapshotWindow]]):
    bounds = []
    for window in windows or ():
        start, end = _aware(window.start), _aware(window.end)
        if start and end and start <= end:
            bounds.append((start, end))
    return bounds


def build_receipt_bridge(
    po_rows: Iterable[PoOpenRow],
    receipt_events: Iterable[ReceiptEvent],
    inventory_rows: Iterable[InventoryRow],
    *,
    po_as_of: Optional[Timestamp] = None,
    collection_windows: Optional[Iterable[SnapshotWindow]] = None,
    transit_rows: Iterable[TransitRow] = (),
) -> list[dict]:
    """Return per SKU×warehouse×UOM bridge rows; quantities stay strings or null."""
    po_groups = defaultdict(list)
    for row in po_rows:
        po_groups[(row.sku, row.warehouse, row.uom)].append(row)
    inventory_groups = defaultdict(list)
    for row in inventory_rows:
        inventory_groups[(row.sku, row.warehouse, row.uom)].append(row)
    receipt_groups = defaultdict(list)
    for event in receipt_events:
        receipt_groups[(event.sku, event.warehouse, event.uom)].append(event)
    transit_groups = defaultdict(list)
    for row in transit_rows:
        transit_groups[(row.sku, row.warehouse, row.uom)].append(row)
    keys = sorted(set(po_groups) | set(inventory_groups) | set(receipt_groups) | set(transit_groups),
                  key=lambda key: tuple("" if value is None else str(value) for value in key))
    collected = _window_bounds(collection_windows)
    effective_po_as_of = _aware(po_as_of)

    out = []
    for key in keys:
        sku, warehouse, uom = key
        pos = po_groups.get(key, [])
        inventories = inventory_groups.get(key, [])
        receipts = receipt_groups.get(key, [])
        transits = transit_groups.get(key, [])

        po_qty = Decimal(0)
        po_qty_unknown = False
        for row in pos:
            quantity = _decimal(row.qty)
            if quantity is None:
                po_qty_unknown = True
            else:
                po_qty += quantity

        inventory_qty = Decimal(0)
        inventory_qty_unknown = False
        for row in inventories:
            quantity = _decimal(row.available)
            if quantity is None:
                inventory_qty_unknown = True
            else:
                inventory_qty += quantity

        transit_qty = Decimal(0)
        transit_qty_unknown = False
        for row in transits:
            quantity = _decimal(row.qty)
            if quantity is None:
                transit_qty_unknown = True
            else:
                transit_qty += quantity
        po_value = None if po_qty_unknown else po_qty
        transit_value = None if (not transits or transit_qty_unknown) else transit_qty
        if po_value and transit_value and abs(po_value - transit_value) < Decimal("0.000001"):
            overlap_status = "same_batch_suspected"
        elif po_value and transit_value:
            overlap_status = "distinct"
        else:
            overlap_status = "unknown"

        group_po_as_of = effective_po_as_of
        if group_po_as_of is None:
            candidates = [_aware(row.as_of) for row in pos]
            candidates = [value for value in candidates if value is not None]
            group_po_as_of = max(candidates) if candidates else None

        snapshot_bounds = []
        for row in inventories:
            start = _aware(row.window_start) or _aware(row.as_of)
            end = _aware(row.window_end) or start
            if start and end and start <= end:
                snapshot_bounds.append((start, end))
        snapshot_start = min((start for start, _ in snapshot_bounds), default=None)
        snapshot_end = max((end for _, end in snapshot_bounds), default=None)

        buckets = {
            name: {"rows": 0, "qty": Decimal(0)}
            for name in (
                "before_snapshot", "after_snapshot", "uncertain_snapshot", "missing_snapshot_window",
                "before_or_at_po_as_of", "after_po_as_of", "unknown_time", "not_collected",
                "invalid_qty",
            )
        }
        receipt_qty = Decimal(0)
        receipt_qty_known = True

        for event in receipts:
            quantity = _decimal(event.quantity)
            if quantity is None:
                buckets["invalid_qty"]["rows"] += 1
                receipt_qty_known = False
                continue
            receipt_qty += quantity
            aware = _aware(event.stock_effective_at)
            if aware is None:
                buckets["unknown_time"]["rows"] += 1
                buckets["unknown_time"]["qty"] += quantity
                continue
            if collected and not any(start <= aware <= end for start, end in collected):
                buckets["not_collected"]["rows"] += 1
                buckets["not_collected"]["qty"] += quantity
                continue
            if group_po_as_of is not None:
                bucket = "after_po_as_of" if aware > group_po_as_of else "before_or_at_po_as_of"
                buckets[bucket]["rows"] += 1
                buckets[bucket]["qty"] += quantity
            if snapshot_start is None or snapshot_end is None:
                buckets["missing_snapshot_window"]["rows"] += 1
                buckets["missing_snapshot_window"]["qty"] += quantity
            elif aware < snapshot_start:
                buckets["before_snapshot"]["rows"] += 1
                buckets["before_snapshot"]["qty"] += quantity
            elif aware > snapshot_end:
                buckets["after_snapshot"]["rows"] += 1
                buckets["after_snapshot"]["qty"] += quantity
            else:
                buckets["uncertain_snapshot"]["rows"] += 1
                buckets["uncertain_snapshot"]["qty"] += quantity

        flags = {
            "po_remaining_may_include_receipts": buckets["before_or_at_po_as_of"]["rows"] > 0,
            "receipts_may_be_in_inventory": buckets["before_snapshot"]["rows"] > 0,
            "timezone_unverified": buckets["unknown_time"]["rows"] > 0,
            "not_collected": buckets["not_collected"]["rows"] > 0,
            "uom_unknown": uom in (None, ""),
            "po_qty_unknown": po_qty_unknown,
            "inventory_qty_unknown": inventory_qty_unknown,
            "transit_qty_unknown": transit_qty_unknown,
            "same_batch_suspected": overlap_status == "same_batch_suspected",
            "po_as_of_unverified": group_po_as_of is None,
            "snapshot_window_missing": snapshot_start is None or snapshot_end is None,
        }
        out.append({
            "sku": sku,
            "warehouse": warehouse,
            "uom": uom,
            "po_rows": len(pos),
            "po_open_qty": None if po_qty_unknown else _out(po_qty),
            "inventory_rows": len(inventories),
            "inventory_qty": None if inventory_qty_unknown else _out(inventory_qty),
            "transit_rows": len(transits),
            "transit_qty": None if (not transits or transit_qty_unknown) else _out(transit_qty),
            "overlap_status": overlap_status,
            "po_as_of": group_po_as_of.isoformat() if group_po_as_of else None,
            "snapshot_start": snapshot_start.isoformat() if snapshot_start else None,
            "snapshot_end": snapshot_end.isoformat() if snapshot_end else None,
            "receipt_rows": len(receipts),
            "receipt_qty": _out(receipt_qty) if receipt_qty_known else None,
            **{f"{name}_rows": value["rows"] for name, value in buckets.items()},
            **{f"{name}_qty": _out(value["qty"]) for name, value in buckets.items()},
            "flags": flags,
            "note": "Bridge only; no receipt is added to available or deducted from in-transit.",
        })
    return out
