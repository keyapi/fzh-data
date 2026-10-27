"""Data-layer assembly for PO / inventory / transit / receipt supply integration.

The report can call this module without changing its existing entry point. All
row-level inputs stay here; ``report_only`` returns aggregates and flags only.
"""
from __future__ import annotations

from collections import Counter, defaultdict
from dataclasses import replace
from datetime import datetime
from decimal import Decimal, InvalidOperation
from typing import Iterable, Optional

from supply_chain_visibility.overlap_gates import apply_overlap_gates
from supply_chain_visibility.receipt_bridge import (
    InventoryRow,
    PoOpenRow,
    TransitRow,
    build_receipt_bridge,
)
from supply_chain_visibility.receipt_reconciliation import ReceiptEvent, SnapshotWindow, _has_stable_id
from supply_chain_visibility.supply_row import SupplyRow, to_dict, require_valid


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


def _parse_aware(value) -> Optional[datetime]:
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


def _aware(value) -> bool:
    return _parse_aware(value) is not None


def _date_string(value) -> Optional[str]:
    if value is None or value == "":
        return None
    if isinstance(value, datetime):
        return value.isoformat()
    return str(value)


def _proof_fields(row) -> dict:
    proof = row.proof
    if any(not isinstance(getattr(proof, name), bool) for name in
           ("uom_proven", "identity_proven", "complete", "batch_proven")):
        raise ValueError("source proof flags must be boolean")
    return dict(
        uom_proven=proof.uom_proven,
        identity_confidence="proven" if proof.identity_proven else "unproven",
        source_key=proof.source_key, source_complete=proof.complete,
        scope=proof.scope, warehouse_confidence=proof.warehouse_confidence,
        role=proof.role, batch_key=proof.batch_key, batch_proven=proof.batch_proven,
    )


def _po_supply_rows(rows: Iterable[PoOpenRow]) -> list[SupplyRow]:
    out = []
    for row in rows:
        if row.status_semantics not in ("open", "closed", "cancelled", "unproven"):
            raise ValueError("invalid PO status semantics")
        qty = _decimal(row.qty)
        closed = row.status_semantics in ("closed", "cancelled")
        out.append(SupplyRow(
            sku=row.sku, warehouse=row.warehouse, stage="po_open", source_layer="po_open",
            qty=qty, qty_status="known" if qty is not None else "unknown",
            uom=row.uom, **_proof_fields(row),
            event_date=None, available_date=None, date_confidence="unknown",
            timezone_status="verified" if _aware(row.as_of) else "unverified",
            source_as_of=_date_string(row.as_of),
            document_key=row.po_code,
            b_min_eligible=qty is not None and row.status_semantics == "open" and str(row.status) != "4",
            b_max_eligible=qty is not None and not closed,
            exclusion_reason=("po_closed" if closed else "po_status_unproven"
                              if row.status_semantics != "open" or str(row.status) == "4" else ""),
        ))
    return out


def _inventory_supply_rows(rows: Iterable[InventoryRow]) -> list[SupplyRow]:
    out = []
    for row in rows:
        qty = _decimal(row.available)
        start, end = _parse_aware(row.window_start), _parse_aware(row.window_end)
        instant = _parse_aware(row.as_of)
        aware = bool(start and end and instant and start <= instant <= end)
        date = _date_string(row.as_of) or _date_string(row.window_start)
        out.append(SupplyRow(
            sku=row.sku, warehouse=row.warehouse, stage="on_hand", source_layer="inventory_snapshot",
            qty=qty, qty_status="known" if qty is not None else "unknown",
            uom=row.uom, **_proof_fields(row),
            event_date=date, available_date=date if aware else None,
            date_confidence="confirmed" if aware else "unknown",
            timezone_status="verified" if aware else "unverified",
            source_as_of=date,
            snapshot_window_start=_date_string(row.window_start),
            snapshot_window_end=_date_string(row.window_end),
            b_min_eligible=qty is not None and aware, b_max_eligible=qty is not None and aware,
            exclusion_reason="invalid_snapshot_window" if not aware else "",
        ))
    return out


def _transit_supply_rows(rows: Iterable[TransitRow]) -> list[SupplyRow]:
    out = []
    for row in rows:
        qty = _decimal(row.qty)
        out.append(SupplyRow(
            sku=row.sku, warehouse=row.warehouse, stage="shipped_in_transit",
            source_layer="in_transit", qty=qty,
            qty_status="known" if qty is not None else "unknown",
            uom=row.uom, **_proof_fields(row),
            event_date=_date_string(row.as_of), available_date=None,
            date_confidence="unknown",
            timezone_status="verified" if _aware(row.as_of) else "unverified",
            source_as_of=_date_string(row.as_of),
            b_min_eligible=qty is not None, b_max_eligible=qty is not None,
        ))
    return out


def _receipt_supply_rows(
    events: Iterable[ReceiptEvent],
    collection_windows: Optional[Iterable[SnapshotWindow]],
) -> list[SupplyRow]:
    windows = []
    for window in collection_windows or ():
        start, end = _parse_aware(window.start), _parse_aware(window.end)
        if start and end and start <= end:
            windows.append((start, end))
    out = []
    for event in events:
        qty = _decimal(event.quantity)
        aware = _parse_aware(event.stock_effective_at)
        not_collected = bool(collection_windows is not None and aware and not any(
            start <= aware <= end for start, end in windows
        ))
        if not event.sku or not event.warehouse:
            reason = "missing_sku_or_warehouse"
        elif not_collected:
            reason = "not_collected"
        elif aware is None:
            reason = "timezone_unverified"
        elif not _has_stable_id(event):
            reason = "missing_stable_id"
        elif not event.uom_proven:
            reason = "uom_unproven"
        elif not event.quantity_semantics_proven:
            reason = "quantity_semantics_unproven"
        else:
            reason = "receipt_evidence_only"
        out.append(SupplyRow(
            sku=event.sku or "", warehouse=event.warehouse or "", stage="received",
            source_layer="receipt_event", qty=qty,
            qty_status="known" if qty is not None else "unknown",
            uom=event.uom, uom_proven=event.uom_proven,
            event_date=_date_string(event.stock_effective_at), available_date=None,
            date_confidence="unknown",
            timezone_status="verified" if aware is not None else "unverified",
            identity_confidence="proven" if _has_stable_id(event) else "weak_identity", not_collected=not_collected,
            weak_event_key=event.weak_event_key,
            possible_duplicate=event.possible_duplicate,
            dedup_assumed=event.dedup_assumed,
            b_min_eligible=False, b_max_eligible=False,
            exclusion_reason=reason,
        ))
    return out


def _sum_by_uom(rows: Iterable[SupplyRow], eligible) -> dict:
    totals = defaultdict(Decimal)
    for row in rows:
        if eligible(row) and row.qty is not None and row.uom_proven and row.uom:
            totals[row.uom] += row.qty
    return {uom: str(qty) for uom, qty in sorted(totals.items())}


def _source_identity_gates(rows: list[SupplyRow]) -> list[SupplyRow]:
    by_key = defaultdict(list)
    for index, row in enumerate(rows):
        if row.source_key:
            by_key[row.source_key].append(index)
    output = list(rows)
    for indexes in by_key.values():
        if len(indexes) < 2:
            continue
        original = rows[indexes[0]]
        conflict = any(rows[index] != original for index in indexes[1:])
        for index in indexes if conflict else indexes[1:]:
            output[index] = replace(rows[index], b_min_eligible=False, b_max_eligible=False,
                                    exclusion_reason="source_identity_conflict" if conflict else "exact_replay")
    inventories = defaultdict(list)
    for index, row in enumerate(output):
        if row.source_layer in ("inventory_snapshot", "po_open") and (row.b_min_eligible or row.b_max_eligible):
            inventories[(row.source_layer, row.sku, row.warehouse, row.uom, row.document_key)].append(index)
    for indexes in inventories.values():
        if len(indexes) > 1:
            for index in indexes:
                output[index] = replace(output[index], b_min_eligible=False, b_max_eligible=False,
                                        exclusion_reason="source_grain_conflict")
    return output


def build_supply_integration(
    po_rows: Iterable[PoOpenRow],
    inventory_rows: Iterable[InventoryRow],
    transit_rows: Iterable[TransitRow],
    receipt_events: Iterable[ReceiptEvent],
    *,
    collection_windows: Optional[Iterable[SnapshotWindow]] = None,
    extra_rows: Iterable[SupplyRow] = (),
) -> dict:
    """Assemble canonical rows, gates, bridge, and aggregates for a report."""
    po = list(po_rows)
    inventory = list(inventory_rows)
    transit = list(transit_rows)
    receipts = list(receipt_events)
    collection = list(collection_windows) if collection_windows is not None else None
    rows = (
        _po_supply_rows(po)
        + _inventory_supply_rows(inventory)
        + _transit_supply_rows(transit)
        + _receipt_supply_rows(receipts, collection)
        + list(extra_rows)
    )
    # Validate values before any arithmetic. Eligibility is revalidated after
    # gates; input evidence must not be made valid by silently dropping a flag.
    for row in rows:
        if not isinstance(row.b_min_eligible, bool) or not isinstance(row.b_max_eligible, bool):
            raise ValueError("bound eligibility flags must be boolean")
        require_valid(replace(row, b_min_eligible=False, b_max_eligible=False))
    gated = apply_overlap_gates(_source_identity_gates(rows))
    bridge = build_receipt_bridge(
        po, receipts, inventory,
        collection_windows=collection, transit_rows=transit,
    )
    for row in gated:
        require_valid(row)
    summary = {
        "input_rows": len(rows),
        "rows": len(gated),
        "partition": {
            "b_min": sum(row.b_min_eligible for row in gated),
            "b_max_only": sum(row.b_max_eligible and not row.b_min_eligible for row in gated),
            "excluded": sum(not row.b_min_eligible and not row.b_max_eligible for row in gated),
        },
        "by_source_layer": dict(sorted(Counter(row.source_layer for row in gated).items())),
        "by_stage": dict(sorted(Counter(row.stage for row in gated).items())),
        "by_overlap_status": dict(sorted(Counter(
            row.overlap_status for row in gated if row.source_layer in ("po_open", "in_transit")
        ).items())),
        "by_exclusion_reason": dict(sorted(Counter(
            row.exclusion_reason for row in gated if row.exclusion_reason
        ).items())),
        "b_min_by_uom": _sum_by_uom(gated, lambda row: row.b_min_eligible),
        "b_max_by_uom": _sum_by_uom(gated, lambda row: row.b_max_eligible),
        "validation_errors": 0,
        # This assembler does not prove coverage of the entire supply chain.
        "bounds_complete": False,
        "committable": False,
        "coverage_status": "unverified",
        "bridge": {
            "rows": len(bridge),
            "same_batch_suspected": sum(1 for row in bridge if row["overlap_status"] == "same_batch_suspected"),
            "timezone_unverified": sum(1 for row in bridge if row["flags"]["timezone_unverified"]),
            "not_collected": sum(1 for row in bridge if row["flags"]["not_collected"]),
        },
        "flags": {
            "timezone_unverified": any(row.timezone_status == "unverified" for row in gated),
            "uom_unknown": any(not row.uom_proven for row in gated),
            "not_collected": any(row.not_collected for row in gated),
            "same_batch_suspected": any(row.overlap_status == "same_batch_suspected" for row in gated),
            "unknown_rows": sum(
                1 for row in gated
                if row.qty is None or not row.uom_proven or row.not_collected
                or row.timezone_status == "unverified" or row.identity_confidence != "proven"
                or not row.source_complete
            ),
        },
    }
    return {
        "rows": [to_dict(row) for row in gated],
        "bridge_rows": bridge,
        "summary": summary,
    }


def report_only(integration: dict) -> dict:
    """Return aggregate-only output for a report surface (no row details)."""
    return {
        "summary": integration["summary"],
        "note": "Aggregate only; row-level quantities stay local and unknown rows are not adjusted.",
    }
