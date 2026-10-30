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


@dataclass(frozen=True)
class SnapshotRow:
    inventory_snapshot_id: Optional[str]
    sku: str
    warehouse: str
    uom: Optional[str]
    available: object
    as_of: Optional[Timestamp] = None
    window_start: Optional[Timestamp] = None
    window_end: Optional[Timestamp] = None
    proof: SourceProof = SourceProof()


PROOF_FIELDS = ("proof_type", "source_record", "receipt_identity",
                "snapshot_id", "source_as_of")


def _snapshot_identity(row: SnapshotRow):
    return (row.inventory_snapshot_id, str(row.as_of), str(row.window_start),
            str(row.window_end))


def _proof_identity(value):
    if isinstance(value, dict):
        return (value.get("receipt_id"), value.get("line_id"))
    if isinstance(value, (list, tuple)) and len(value) == 2:
        return (value[0], value[1])
    return None


def _validate_inclusion_proof(record, event, snapshot: SnapshotRow):
    """Return the structured proof or a conflict reason code."""
    if not isinstance(record, dict):
        return None, "inclusion_proof_missing"
    missing = [name for name in PROOF_FIELDS
               if record.get(name) in (None, "")]
    if missing:
        return record, "inclusion_proof_incomplete"
    if str(record.get("snapshot_id")) != str(snapshot.inventory_snapshot_id):
        return record, "inclusion_proof_identity_mismatch"
    if str(record.get("source_as_of")) != str(snapshot.as_of):
        return record, "inclusion_proof_identity_mismatch"
    if _proof_identity(record.get("receipt_identity")) != (
            event.receipt_id, event.line_id):
        return record, "inclusion_proof_identity_mismatch"
    return record, None


def _receipt_payload(event: ReceiptEvent):
    return (event.po_code, event.sku, event.warehouse, event.uom,
            str(event.quantity), str(event.stock_effective_at),
            event.quantity_semantics_proven, event.uom_proven)


def build_inventory_bridge(
    snapshots: Iterable[SnapshotRow],
    receipt_events: Iterable[ReceiptEvent],
    *,
    collection_windows: Optional[Iterable[SnapshotWindow]] = None,
) -> dict:
    """Per-receipt inclusion status bound to exactly one snapshot identity.

    One computation can reference only one snapshot. Several snapshot rows are
    acceptable only when they describe the same identity; any second
    id/version makes every receipt conflicted instead of splicing windows.
    """
    snapshot_rows = list(snapshots or [])
    events = list(receipt_events or [])
    snapshot_groups = defaultdict(list)
    for row in snapshot_rows:
        snapshot_groups[(row.sku, row.warehouse, row.uom)].append(row)
    snapshot_identities = sorted({_snapshot_identity(row) for row in snapshot_rows})
    single_snapshot = len(snapshot_identities) == 1
    bound = (sorted(snapshot_rows, key=_snapshot_identity)[0]
             if single_snapshot else None)
    collected = (None if collection_windows is None
                 else _window_bounds(collection_windows))

    identities = defaultdict(list)
    for index, event in enumerate(events):
        if _has_stable_id(event):
            identities[(event.receipt_id, event.line_id)].append(index)
    conflicts, duplicates = set(), {}
    for indexes in identities.values():
        payloads = {_receipt_payload(events[index]) for index in indexes}
        if len(payloads) > 1:
            conflicts.update(indexes)
        else:
            duplicates.update({index: indexes[0] for index in indexes[1:]})

    rows = []
    for index, event in enumerate(events):
        quantity = _decimal(event.quantity)
        effective = _aware(event.stock_effective_at)
        base = {
            "receipt_id": event.receipt_id,
            "line_id": event.line_id,
            "po_code": event.po_code,
            "po_line_id": event.po_line_id,
            "dn_line_id": event.dn_line_id,
            "shipment_id": event.shipment_id,
            "sku": event.sku,
            "warehouse": event.warehouse,
            "uom": event.uom,
            "qty": None if quantity is None else str(quantity),
            "receipt_effective_at": event.stock_effective_at,
            "receipt_inclusion_status": "unknown",
            "inclusion_proof": None,
            "inclusion_proof_type": None,
            "post_snapshot_delta_qty": None,
            "conditional_delta_qty": None,
            "eligible": False,
            "count_in_inventory": False,
            "inventory_snapshot_id": None,
            "source_as_of": None,
            "snapshot_window_start": None,
            "snapshot_window_end": None,
            "snapshot_candidates": [],
            "exclusion_reason": "",
            "duplicate_of": None,
        }
        if index in conflicts:
            base["receipt_inclusion_status"] = "conflict"
            base["exclusion_reason"] = "receipt_payload_conflict"
            rows.append(base)
            continue
        if index in duplicates:
            base["receipt_inclusion_status"] = "conflict"
            base["exclusion_reason"] = "duplicate_replay"
            base["duplicate_of"] = duplicates[index]
            rows.append(base)
            continue
        group = snapshot_groups.get((event.sku, event.warehouse, event.uom)) or []
        if not group:
            base["receipt_inclusion_status"] = "unknown"
            base["exclusion_reason"] = "unmatched_snapshot"
            rows.append(base)
            continue
        if not single_snapshot:
            base["receipt_inclusion_status"] = "conflict"
            base["exclusion_reason"] = "multiple_snapshot_versions"
            base["snapshot_candidates"] = [
                {"inventory_snapshot_id": row.inventory_snapshot_id,
                 "as_of": None if row.as_of is None else str(row.as_of),
                 "window_start": None if row.window_start is None else str(row.window_start),
                 "window_end": None if row.window_end is None else str(row.window_end)}
                for row in sorted(group, key=_snapshot_identity)]
            rows.append(base)
            continue
        snapshot = bound
        start = _aware(snapshot.window_start)
        end = _aware(snapshot.window_end)
        base["inventory_snapshot_id"] = snapshot.inventory_snapshot_id
        base["source_as_of"] = (str(snapshot.as_of)
                                if snapshot.as_of is not None else None)
        base["snapshot_window_start"] = start.isoformat() if start else None
        base["snapshot_window_end"] = end.isoformat() if end else None
        if len({str(row.available) for row in group}) > 1:
            base["receipt_inclusion_status"] = "conflict"
            base["exclusion_reason"] = "snapshot_payload_conflict"
            base["snapshot_candidates"] = [
                {"inventory_snapshot_id": row.inventory_snapshot_id,
                 "available": row.available}
                for row in sorted(group, key=repr)]
            rows.append(base)
            continue
        if not _has_stable_id(event):
            base["exclusion_reason"] = "missing_stable_id"
            rows.append(base)
            continue
        if quantity is None:
            base["exclusion_reason"] = "invalid_quantity"
            rows.append(base)
            continue
        if not event.uom or not event.uom_proven:
            base["exclusion_reason"] = "uom_unproven"
            rows.append(base)
            continue
        if not event.quantity_semantics_proven:
            base["exclusion_reason"] = "quantity_semantics_unproven"
            rows.append(base)
            continue
        if effective is None:
            base["exclusion_reason"] = "missing_effective_time"
            rows.append(base)
            continue
        if collected is not None and not any(
                left <= effective <= right for left, right in collected):
            base["receipt_inclusion_status"] = "unknown"
            base["exclusion_reason"] = "not_collected"
            rows.append(base)
            continue
        if start is None or end is None:
            base["exclusion_reason"] = "missing_snapshot_window"
            rows.append(base)
            continue
        proof, proof_reason = _validate_inclusion_proof(
            event.inclusion_proof_record, event, snapshot)
        base["inclusion_proof"] = proof
        base["inclusion_proof_type"] = (proof or {}).get("proof_type")
        if proof_reason in ("inclusion_proof_identity_mismatch",
                            "inclusion_proof_incomplete"):
            base["receipt_inclusion_status"] = "conflict"
            base["exclusion_reason"] = proof_reason
            rows.append(base)
            continue
        if effective > end:
            base["receipt_inclusion_status"] = "after_snapshot"
            base["post_snapshot_delta_qty"] = str(quantity)
            base["conditional_delta_qty"] = str(quantity)
            base["exclusion_reason"] = "after_snapshot_conditional"
        elif effective < start:
            if proof is not None and proof_reason is None:
                base["receipt_inclusion_status"] = "included"
                base["count_in_inventory"] = True
                base["exclusion_reason"] = "inclusion_proof"
            else:
                base["receipt_inclusion_status"] = "uncertain"
                base["exclusion_reason"] = "inclusion_proof_missing"
        else:
            base["receipt_inclusion_status"] = "uncertain"
            base["exclusion_reason"] = "inside_snapshot_window"
        rows.append(base)

    rows.sort(key=lambda row: (str(row.get("receipt_id") or ""),
                               str(row.get("line_id") or ""),
                               str(row.get("sku") or ""),
                               str(row.get("warehouse") or ""),
                               str(row.get("uom") or "")))
    counts = defaultdict(int)
    for row in rows:
        counts[row["receipt_inclusion_status"]] += 1
    partition = {
        "included": counts.get("included", 0),
        "duplicate": sum(1 for row in rows
                         if row["exclusion_reason"] == "duplicate_replay"),
        "conflict": sum(1 for row in rows
                        if row["receipt_inclusion_status"] == "conflict"
                        and row["exclusion_reason"] != "duplicate_replay"),
        "unmatched": sum(1 for row in rows
                         if row["receipt_inclusion_status"] == "unknown"
                         and row["exclusion_reason"] != "not_collected"),
        "not_collected": sum(1 for row in rows
                             if row["exclusion_reason"] == "not_collected"),
        "after_snapshot": counts.get("after_snapshot", 0),
        "uncertain": counts.get("uncertain", 0),
    }
    deltas = defaultdict(lambda: {"qty": Decimal(0), "rows": 0})
    for row in rows:
        if row["post_snapshot_delta_qty"] is not None:
            key = (row["sku"], row["warehouse"], row["uom"])
            deltas[key]["qty"] += Decimal(row["post_snapshot_delta_qty"])
            deltas[key]["rows"] += 1
    ordered_deltas = [
        {"sku": key[0], "warehouse": key[1], "uom": key[2],
         "qty": str(value["qty"]), "rows": value["rows"]}
        for key, value in sorted(
            deltas.items(),
            key=lambda item: tuple("" if part is None else str(part)
                                   for part in item[0]))
    ]
    return {
        "rows": rows,
        "summary": {
            "input_count": len(rows),
            "partition": partition,
            "partition_total": sum(partition.values()),
            "post_snapshot_delta": ordered_deltas,
            "snapshot_identity_count": len(snapshot_identities),
            "snapshot_binding": (bound.inventory_snapshot_id
                                 if bound is not None else None),
            "eligible": False,
            "note": ("Receipts are not added to inventory. Included rows are already "
                     "inside the bound snapshot; post-snapshot rows stay conditional deltas."),
        },
    }

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
