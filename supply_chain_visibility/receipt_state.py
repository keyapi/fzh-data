"""Signed Shipment -> Tongtool purchase receipt reconciliation (pure).

The only accepted association is an already-proven chain:
Shipment -> Delivery Note -> DN.custom_tongtool_purchase_order -> Tongtool PO
-> receipt line (same SKU / warehouse / UOM).

No quantity equality, date proximity, or same-SKU guess is ever used. A
receipt that cannot be allocated to exactly one link stays unknown and is not
counted; duplicate payloads are counted once, conflicting payloads are unknown.
"""
from __future__ import annotations

from collections import defaultdict
from dataclasses import dataclass, field
from datetime import datetime
from decimal import Decimal, InvalidOperation
from typing import Iterable, Optional

STAGE_IN_TRANSIT = "in_transit"
STAGE_PENDING = "signed_pending_tongtool_receipt"
STAGE_RECEIVED = "tongtool_received"
STAGE_UNKNOWN = "unknown"


@dataclass(frozen=True)
class ShipmentLink:
    shipment: str
    dn: Optional[str]
    po_codes: tuple = ()
    signed_at: Optional[str] = None
    qty: object = None
    uom: Optional[str] = None
    sku: Optional[str] = None
    warehouse: Optional[str] = None
    identity_confidence: str = "unproven"
    status_semantics: str = "unproven"


@dataclass(frozen=True)
class ReceiptLine:
    receipt_id: Optional[str]
    line_id: Optional[str]
    po_code: Optional[str]
    sku: Optional[str]
    warehouse: Optional[str]
    uom: Optional[str]
    qty: object
    effective_at: Optional[str]
    quantity_semantics: str = "unknown"
    uom_proven: bool = False
    identity_proven: bool = False
    raw: dict = field(default_factory=dict)


def _decimal(value) -> Optional[Decimal]:
    if value is None or isinstance(value, bool):
        return None
    try:
        number = Decimal(str(value).strip())
    except (InvalidOperation, ValueError, AttributeError):
        return None
    if not number.is_finite() or number < 0:
        return None
    return number


def _parse(value) -> Optional[datetime]:
    text = "" if value is None else str(value).strip()
    if not text:
        return None
    try:
        parsed = datetime.fromisoformat(text.replace("Z", "+00:00"))
    except ValueError:
        return None
    return parsed


def _out(value: Optional[Decimal]) -> Optional[str]:
    return None if value is None else str(value)


def _identity(line: ReceiptLine):
    return (line.receipt_id, line.line_id)


def _payload(line: ReceiptLine):
    return (line.po_code, line.sku, line.warehouse, line.uom,
            str(line.qty), line.effective_at, line.quantity_semantics,
            bool(line.uom_proven), bool(line.identity_proven))


def _dedupe(receipts: list[ReceiptLine]):
    """Exact replays count once; same identity with different payload conflicts."""
    by_identity = defaultdict(list)
    passthrough = []
    for line in receipts:
        if line.receipt_id and line.line_id:
            by_identity[_identity(line)].append(line)
        else:
            passthrough.append(line)
    unique, duplicates, conflicts = [], 0, set()
    for key, rows in by_identity.items():
        payloads = {_payload(row) for row in rows}
        if len(payloads) > 1:
            conflicts.update(key for key in [key])
            continue
        unique.append(rows[0])
        duplicates += len(rows) - 1
    return unique + passthrough, duplicates, conflicts


def _link_matches(line: ReceiptLine, link: ShipmentLink) -> bool:
    return (line.po_code in link.po_codes
            and line.sku == link.sku
            and line.warehouse == link.warehouse
            and line.uom == link.uom)


def reconcile_signed_receipts(
    links: Iterable[ShipmentLink],
    receipts: Iterable[ReceiptLine],
) -> list[dict]:
    all_links = list(links or [])
    all_receipts = list(receipts or [])
    unique, duplicates, conflict_keys = _dedupe(all_receipts)

    # A receipt key that could map to more than one link is allocation-unknown.
    link_count = defaultdict(int)
    receipt_keys = {(line.po_code, line.sku, line.warehouse, line.uom)
                    for line in unique}
    for link in all_links:
        for key in receipt_keys:
            if key[0] in link.po_codes and key[1] == link.sku \
                    and key[2] == link.warehouse and key[3] == link.uom:
                link_count[key] += 1
    conflict_pos = {line.po_code for line in all_receipts
                    if _identity(line) in conflict_keys}

    rows = []
    for link in all_links:
        unmatched = sum(1 for line in unique if not _link_matches(line, link))
        if not link.po_codes:
            rows.append(_row(link, STAGE_UNKNOWN, exclusion="no_po_link",
                             duplicates=duplicates, unmatched=unmatched))
            continue
        if link.identity_confidence != "proven":
            rows.append(_row(link, STAGE_UNKNOWN,
                             exclusion="identity_unproven",
                             duplicates=duplicates, unmatched=unmatched))
            continue
        if not link.signed_at:
            rows.append(_row(link, STAGE_IN_TRANSIT, duplicates=duplicates,
                             unmatched=unmatched))
            continue
        if any(po in link.po_codes for po in conflict_pos):
            rows.append(_row(link, STAGE_UNKNOWN,
                             exclusion="receipt_payload_conflict",
                             duplicates=duplicates, unmatched=unmatched))
            continue

        same_po = [line for line in unique if line.po_code in link.po_codes]
        matching = [line for line in same_po if _link_matches(line, link)]
        if same_po and not matching:
            rows.append(_row(link, STAGE_UNKNOWN,
                             exclusion="receipt_identity_mismatch",
                             duplicates=duplicates, unmatched=unmatched))
            continue
        if any(link_count[(line.po_code, line.sku, line.warehouse, line.uom)] > 1
               for line in matching):
            rows.append(_row(link, STAGE_UNKNOWN,
                             exclusion="receipt_allocation_unknown",
                             duplicates=duplicates, unmatched=unmatched))
            continue
        if any(line.quantity_semantics != "increment" for line in matching):
            rows.append(_row(link, STAGE_UNKNOWN,
                             exclusion="quantity_semantics_unproven",
                             duplicates=duplicates, unmatched=unmatched))
            continue
        if any(not line.uom_proven or not line.identity_proven for line in matching):
            rows.append(_row(link, STAGE_UNKNOWN,
                             exclusion="receipt_identity_unproven",
                             duplicates=duplicates, unmatched=unmatched))
            continue

        received = Decimal(0)
        times = []
        for line in matching:
            qty = _decimal(line.qty)
            if qty is None:
                received = None
                break
            received += qty
            parsed = _parse(line.effective_at)
            if parsed is not None:
                times.append((parsed, line.effective_at))
        if received is None:
            rows.append(_row(link, STAGE_UNKNOWN, exclusion="invalid_quantity",
                             duplicates=duplicates, unmatched=unmatched))
            continue

        link_qty = _decimal(link.qty)
        if link_qty is None:
            rows.append(_row(link, STAGE_UNKNOWN, exclusion="signed_qty_unknown",
                             duplicates=duplicates, unmatched=unmatched))
            continue
        pending = link_qty - received
        completion = ("complete" if pending <= 0 else
                      "partial" if received > 0 else "pending")
        status = STAGE_RECEIVED if completion == "complete" else STAGE_PENDING
        first_at = min(times)[1] if times else None
        last_at = max(times)[1] if times else None
        lag = None
        if last_at:
            signed = _parse(link.signed_at)
            last = _parse(last_at)
            if signed is not None and last is not None:
                lag = (last - signed).days
        rows.append(_row(
            link, status,
            received=received, pending=max(Decimal(0), pending),
            completion=completion, first_at=first_at, last_at=last_at,
            receipt_at=last_at if status == STAGE_RECEIVED else None,
            lag=lag, duplicates=duplicates, unmatched=unmatched))
    return rows


def _row(link: ShipmentLink, status: str, *, exclusion=None, received=None,
         pending=None, completion="unknown", first_at=None, last_at=None,
         receipt_at=None, lag=None, duplicates=0, unmatched=0) -> dict:
    return {
        "shipment": link.shipment,
        "dn": link.dn,
        "po_codes": list(link.po_codes),
        "sku": link.sku,
        "warehouse": link.warehouse,
        "uom": link.uom,
        "status": status,
        "status_semantics": link.status_semantics,
        "shipment_signed_at": link.signed_at,
        "tongtool_first_receipt_at": first_at,
        "tongtool_last_receipt_at": last_at,
        "tongtool_receipt_at": receipt_at,
        "receipt_lag_days": lag,
        "receipt_completion": completion if status != STAGE_UNKNOWN else "unknown",
        "received_qty": _out(received) if received is not None else None,
        "pending_qty": _out(pending) if pending is not None else None,
        "received_evidence_status": "known" if received is not None else "unknown",
        "pending_evidence_status": "known" if pending is not None else "unknown",
        "receipt_basis": "signed_assumed",
        "identity_confidence": link.identity_confidence,
        "exclusion_reason": exclusion or "",
        "receipt_duplicates": duplicates,
        "unmatched_receipt_rows": unmatched,
    }
