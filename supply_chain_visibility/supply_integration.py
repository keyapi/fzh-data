"""Data-layer assembly for PO / inventory / transit / receipt supply integration.

The report can call this module without changing its existing entry point. All
row-level inputs stay here; ``report_only`` returns aggregates and flags only.
"""
from __future__ import annotations

from collections import Counter, defaultdict
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
from supply_chain_visibility.receipt_reconciliation import ReceiptEvent, SnapshotWindow
from supply_chain_visibility.supply_row import SupplyRow, to_dict, validate_supply_row


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


def _uom_proven(uom: Optional[str]) -> bool:
    return bool(uom and str(uom).strip())


def _po_supply_rows(rows: Iterable[PoOpenRow]) -> list[SupplyRow]:
    out = []
    for row in rows:
        qty = _decimal(row.qty)
        out.append(SupplyRow(
            sku=row.sku, warehouse=row.warehouse, stage="po_open", source_layer="po_open",
            qty=qty, qty_status="known" if qty is not None else "unknown",
            uom=row.uom, uom_proven=_uom_proven(row.uom),
            event_date=None, available_date=None, date_confidence="unknown",
            timezone_status="unverified", identity_confidence="proven",
            source_as_of=_date_string(row.as_of),
            b_min_eligible=qty is not None, b_max_eligible=qty is not None,
        ))
    return out


def _inventory_supply_rows(rows: Iterable[InventoryRow]) -> list[SupplyRow]:
    out = []
    for row in rows:
        qty = _decimal(row.available)
        aware = _aware(row.window_start) or _aware(row.as_of)
        date = _date_string(row.as_of) or _date_string(row.window_start)
        out.append(SupplyRow(
            sku=row.sku, warehouse=row.warehouse, stage="on_hand", source_layer="inventory_snapshot",
            qty=qty, qty_status="known" if qty is not None else "unknown",
            uom=row.uom, uom_proven=_uom_proven(row.uom),
            event_date=date, available_date=date if aware else None,
            date_confidence="confirmed" if aware else "unknown",
            timezone_status="verified" if aware else "unverified",
            identity_confidence="proven", source_as_of=date,
            snapshot_window_start=_date_string(row.window_start),
            snapshot_window_end=_date_string(row.window_end),
            b_min_eligible=qty is not None, b_max_eligible=qty is not None,
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
            uom=row.uom, uom_proven=_uom_proven(row.uom),
            event_date=_date_string(row.as_of), available_date=None,
            date_confidence="unknown",
            timezone_status="verified" if _aware(row.as_of) else "unverified",
            identity_confidence="proven", source_as_of=_date_string(row.as_of),
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
        not_collected = bool(aware and windows and not any(
            start <= aware <= end for start, end in windows
        ))
        reason = "not_collected" if not_collected else (
            "timezone_unverified" if aware is None else "missing_stable_id"
        )
        out.append(SupplyRow(
            sku=event.sku or "", warehouse=event.warehouse or "", stage="received",
            source_layer="receipt_event", qty=qty,
            qty_status="known" if qty is not None else "unknown",
            uom=event.uom, uom_proven=_uom_proven(event.uom),
            event_date=_date_string(event.stock_effective_at), available_date=None,
            date_confidence="unknown",
            timezone_status="verified" if aware is not None else "unverified",
            identity_confidence="weak_identity", not_collected=not_collected,
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
        if eligible(row) and row.qty is not None:
            totals[row.uom or "(unknown)"] += row.qty
    return {uom: str(qty) for uom, qty in sorted(totals.items())}


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
    gated = apply_overlap_gates(rows)
    bridge = build_receipt_bridge(
        po, receipts, inventory,
        collection_windows=collection, transit_rows=transit,
    )
    errors = [error for row in gated for error in validate_supply_row(row)]
    summary = {
        "rows": len(gated),
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
        "validation_errors": len(errors),
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
                or row.timezone_status == "unverified" or row.identity_confidence == "weak_identity"
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
