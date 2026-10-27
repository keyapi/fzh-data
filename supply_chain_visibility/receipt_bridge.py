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

from supply_chain_visibility.receipt_reconciliation import ReceiptEvent, SnapshotWindow, _has_stable_id, _identity
from supply_chain_visibility.supply_row import SourceProof
from supply_chain_visibility.overlap_gates import classify_batch_overlap


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
    proof: SourceProof = SourceProof()
    status_semantics: str = "unproven"


@dataclass(frozen=True)
class InventoryRow:
    sku: str
    warehouse: str
    available: object
    uom: Optional[str]
    as_of: Optional[Timestamp] = None
    window_start: Optional[Timestamp] = None
    window_end: Optional[Timestamp] = None
    proof: SourceProof = SourceProof()


@dataclass(frozen=True)
class TransitRow:
    sku: str
    warehouse: str
    qty: object
    uom: Optional[str]
    as_of: Optional[Timestamp] = None
    proof: SourceProof = SourceProof()


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
    receipt_versions = defaultdict(set)
    for event in receipt_events:
        receipt_groups[(event.sku, event.warehouse, event.uom)].append(event)
        if _has_stable_id(event):
            receipt_versions[(event.receipt_id, event.line_id)].add(_identity(event))
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
        po_value = None if not pos or po_qty_unknown else po_qty
        transit_value = None if (not transits or transit_qty_unknown) else transit_qty
        overlap_status = classify_batch_overlap(po_value, transit_value,
            [(row.proof.batch_key, row.proof.batch_proven) for row in pos],
            [(row.proof.batch_key, row.proof.batch_proven) for row in transits])

        group_po_as_of = effective_po_as_of if pos else None
        if group_po_as_of is None:
            candidates = [_aware(row.as_of) for row in pos]
            candidates = [value for value in candidates if value is not None]
            group_po_as_of = candidates[0] if candidates and len(candidates) == len(pos) and len(set(candidates)) == 1 else None
        po_instants = defaultdict(list)
        for row in pos:
            po_instants[row.po_code].append(_aware(row.as_of))

        snapshot_bounds = []
        for row in inventories:
            start = _aware(row.window_start)
            end = _aware(row.window_end)
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
                "po_as_of_unknown", "gap_candidate", "overlap_candidate",
            )
        }
        receipt_qty = Decimal(0)
        receipt_qty_known = bool(receipts)
        unproven_buckets = set()
        seen_receipts = set()
        duplicate_receipts = conflict_receipts = 0

        for event in receipts:
            if _has_stable_id(event):
                event_key = (event.receipt_id, event.line_id)
                if len(receipt_versions[event_key]) > 1:
                    conflict_receipts += 1
                    receipt_qty_known = False
                    continue
                if event_key in seen_receipts:
                    duplicate_receipts += 1
                    continue
                seen_receipts.add(event_key)
            quantity = _decimal(event.quantity)
            proven_quantity = bool(
                _has_stable_id(event) and event.uom and event.uom_proven
                and event.quantity_semantics_proven and not event.possible_duplicate
                and not event.dedup_assumed
            )
            if not proven_quantity:
                receipt_qty_known = False
            if quantity is None:
                buckets["invalid_qty"]["rows"] += 1
                unproven_buckets.add("invalid_qty")
                receipt_qty_known = False
                continue
            receipt_qty += quantity
            aware = _aware(event.stock_effective_at)
            before_counts = {name: bucket["rows"] for name, bucket in buckets.items()}
            if aware is None:
                buckets["unknown_time"]["rows"] += 1
                buckets["unknown_time"]["qty"] += quantity
                if not proven_quantity:
                    unproven_buckets.add("unknown_time")
                continue
            if collection_windows is not None and not any(start <= aware <= end for start, end in collected):
                buckets["not_collected"]["rows"] += 1
                buckets["not_collected"]["qty"] += quantity
                if not proven_quantity:
                    unproven_buckets.add("not_collected")
                continue
            candidates = po_instants.get(event.po_code, [])
            receipt_po_as_of = effective_po_as_of if candidates else None
            if receipt_po_as_of is None and candidates and all(candidates) and len(set(candidates)) == 1:
                receipt_po_as_of = candidates[0]
            if receipt_po_as_of is not None:
                bucket = "after_po_as_of" if aware > receipt_po_as_of else "before_or_at_po_as_of"
                buckets[bucket]["rows"] += 1
                buckets[bucket]["qty"] += quantity
            else:
                buckets["po_as_of_unknown"]["rows"] += 1
                buckets["po_as_of_unknown"]["qty"] += quantity
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
            risk_bucket = None
            if receipt_po_as_of is not None and snapshot_start is not None and snapshot_end is not None:
                if snapshot_end < aware <= receipt_po_as_of:
                    risk_bucket = "gap_candidate"
                elif receipt_po_as_of < aware < snapshot_start:
                    risk_bucket = "overlap_candidate"
            if risk_bucket:
                buckets[risk_bucket]["rows"] += 1
                buckets[risk_bucket]["qty"] += quantity
            if not proven_quantity:
                unproven_buckets.update(name for name, bucket in buckets.items() if bucket["rows"] > before_counts[name])

        flags = {
            "po_remaining_may_reflect_receipts": buckets["before_or_at_po_as_of"]["rows"] > 0,
            "receipt_gap_risk": buckets["gap_candidate"]["rows"] > 0,
            "receipt_overlap_risk": buckets["overlap_candidate"]["rows"] > 0,
            "receipts_may_be_in_inventory": buckets["before_snapshot"]["rows"] > 0,
            "timezone_unverified": buckets["unknown_time"]["rows"] > 0,
            "not_collected": buckets["not_collected"]["rows"] > 0,
            "uom_unknown": uom in (None, ""),
            "po_qty_unknown": not pos or po_qty_unknown,
            "inventory_qty_unknown": len(inventories) != 1 or inventory_qty_unknown,
            "transit_qty_unknown": not transits or transit_qty_unknown,
            "same_batch_suspected": overlap_status == "same_batch_suspected",
            "po_as_of_unverified": group_po_as_of is None,
            "snapshot_window_missing": snapshot_start is None or snapshot_end is None,
            "collection_coverage_unknown": collection_windows is None,
            "mixed_po_as_of": len({_aware(row.as_of) for row in pos}) > 1,
            "receipt_quantity_unproven": not receipt_qty_known,
            "receipt_identity_conflict": bool(conflict_receipts),
            "po_grain_conflict": len({row.po_code for row in pos}) != len(pos),
        }
        out.append({
            "sku": sku,
            "warehouse": warehouse,
            "uom": uom,
            "po_rows": len(pos),
            "po_open_qty": None if not pos or po_qty_unknown or flags["mixed_po_as_of"] or flags["po_grain_conflict"] else _out(po_qty),
            "inventory_rows": len(inventories),
            "inventory_qty": None if not inventories or inventory_qty_unknown or len(inventories) != 1 else _out(inventory_qty),
            "transit_rows": len(transits),
            "transit_qty": None if (not transits or transit_qty_unknown) else _out(transit_qty),
            "overlap_status": overlap_status,
            "po_as_of": group_po_as_of.isoformat() if group_po_as_of else None,
            "snapshot_start": snapshot_start.isoformat() if snapshot_start else None,
            "snapshot_end": snapshot_end.isoformat() if snapshot_end else None,
            "receipt_rows": len(receipts),
            "receipt_duplicates": duplicate_receipts,
            "receipt_conflicts": conflict_receipts,
            "receipt_qty": _out(receipt_qty) if receipt_qty_known else None,
            **{f"{name}_rows": value["rows"] for name, value in buckets.items()},
            **{f"{name}_qty": None if name in unproven_buckets else _out(value["qty"]) for name, value in buckets.items()},
            "flags": flags,
            "note": "Bridge only; no receipt is added to available or deducted from in-transit.",
        })
    return out
