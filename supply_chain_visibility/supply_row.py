"""Canonical supply row for PO / inventory / in-transit / receipt integration."""
from __future__ import annotations

from dataclasses import asdict, dataclass
from decimal import Decimal
from datetime import datetime
from typing import Optional

STAGES = (
    "on_hand", "po_open", "in_production", "shipped_in_transit",
    "received", "partially_received", "unknown",
)
QTY_STATUSES = ("known", "estimated", "unknown")
DATE_CONFIDENCES = ("confirmed", "estimated", "unknown")
IDENTITY_CONFIDENCES = ("proven", "weak_identity", "unproven")
TIMEZONE_STATUSES = ("verified", "unverified")
SCOPES = ("in_house", "external_fba")
WAREHOUSE_CONFIDENCES = ("confirmed", "assumed", "unmapped")
ROLES = ("finished", "component", "cover", "unknown")
SOURCE_LAYERS = ("inventory_snapshot", "po_open", "in_transit", "receipt_event", "work_order",
                 "dn_trace", "demand", "uncovered_chain", "not_reported", "warehouse_scope_unknown")


@dataclass(frozen=True)
class SourceProof:
    """Caller-supplied evidence; a nonempty UOM or a timestamp is not proof."""

    source_key: Optional[str] = None
    uom_proven: bool = False
    identity_proven: bool = False
    complete: bool = False
    scope: str = "in_house"
    warehouse_confidence: str = "unmapped"
    role: str = "unknown"
    batch_key: Optional[str] = None
    batch_proven: bool = False


def aware_timestamp(value):
    if isinstance(value, datetime):
        parsed = value
    elif isinstance(value, str):
        try:
            parsed = datetime.fromisoformat(value.replace("Z", "+00:00"))
        except ValueError:
            return None
    else:
        return None
    return parsed if parsed.tzinfo is not None and parsed.utcoffset() is not None else None


@dataclass(frozen=True)
class SupplyRow:
    sku: str
    warehouse: str
    stage: str
    source_layer: str
    qty: Optional[Decimal]
    qty_status: str
    uom: Optional[str]
    uom_proven: bool
    event_date: Optional[str]
    available_date: Optional[str]
    date_confidence: str
    timezone_status: str
    identity_confidence: str
    source_as_of: Optional[str] = None
    scope: str = "in_house"
    warehouse_confidence: str = "assumed"
    role: str = "unknown"
    snapshot_window_start: Optional[str] = None
    snapshot_window_end: Optional[str] = None
    collection_window_start: Optional[str] = None
    collection_window_end: Optional[str] = None
    not_collected: bool = False
    overlap_status: str = "unknown"
    weak_event_key: Optional[tuple] = None
    possible_duplicate: bool = False
    dedup_assumed: bool = False
    b_min_eligible: bool = False
    b_max_eligible: bool = False
    exclusion_reason: str = ""
    source_key: Optional[str] = None
    source_complete: bool = False
    batch_key: Optional[str] = None
    batch_proven: bool = False
    document_key: Optional[str] = None


def validate_supply_row(row: SupplyRow) -> list[str]:
    errors = []
    if any(not isinstance(value, str) or (not value.strip() and row.source_layer != "receipt_event")
           for value in (row.sku, row.warehouse)):
        errors.append("sku and warehouse must be nonempty")
    for field in ("uom_proven", "source_complete", "batch_proven", "not_collected", "possible_duplicate",
                  "dedup_assumed", "b_min_eligible", "b_max_eligible"):
        if not isinstance(getattr(row, field), bool):
            errors.append(f"{field} must be boolean")
    if row.source_key is not None and (not isinstance(row.source_key, str) or not row.source_key.strip()):
        errors.append("source_key must be a nonempty string or null")
    if row.document_key is not None and (not isinstance(row.document_key, str) or not row.document_key.strip()):
        errors.append("document_key must be a nonempty string or null")
    if row.batch_proven and (not isinstance(row.batch_key, str) or not row.batch_key.strip()):
        errors.append("proven batch requires a nonempty key")
    if row.qty is not None and (
        not isinstance(row.qty, Decimal) or not row.qty.is_finite() or row.qty < 0
    ):
        errors.append("qty must be a finite nonnegative Decimal or null")
    if row.uom_proven and (not isinstance(row.uom, str) or not row.uom.strip()):
        errors.append("proven UOM requires a nonempty unit")
    if row.stage not in STAGES:
        errors.append(f"invalid stage: {row.stage}")
    if row.source_layer not in SOURCE_LAYERS:
        errors.append(f"invalid source_layer: {row.source_layer}")
    if row.b_min_eligible and not row.b_max_eligible:
        errors.append("B_min eligibility requires B_max eligibility")
    if row.qty_status not in QTY_STATUSES:
        errors.append(f"invalid qty_status: {row.qty_status}")
    if row.date_confidence not in DATE_CONFIDENCES:
        errors.append(f"invalid date_confidence: {row.date_confidence}")
    if row.identity_confidence not in IDENTITY_CONFIDENCES:
        errors.append(f"invalid identity_confidence: {row.identity_confidence}")
    if row.timezone_status not in TIMEZONE_STATUSES:
        errors.append(f"invalid timezone_status: {row.timezone_status}")
    if row.scope not in SCOPES:
        errors.append(f"invalid scope: {row.scope}")
    if row.warehouse_confidence not in WAREHOUSE_CONFIDENCES:
        errors.append(f"invalid warehouse_confidence: {row.warehouse_confidence}")
    if row.role not in ROLES:
        errors.append(f"invalid role: {row.role}")
    if row.qty is None and row.qty_status != "unknown":
        errors.append("qty=null requires qty_status=unknown")
    if row.qty is not None and row.qty_status == "unknown":
        errors.append("qty_status=unknown requires qty=null")
    if row.date_confidence == "unknown" and row.available_date is not None:
        errors.append("date_confidence=unknown requires available_date=null")
    if row.not_collected and (row.b_min_eligible or row.b_max_eligible):
        errors.append("not_collected rows cannot enter B_min/B_max")
    if row.qty_status == "unknown" and (row.b_min_eligible or row.b_max_eligible):
        errors.append("unknown quantity cannot enter B_min/B_max")
    if not row.uom_proven and row.b_min_eligible:
        errors.append("B_min requires a proven UOM")
    if not row.uom_proven and row.b_max_eligible:
        errors.append("B_max requires a proven UOM")
    if row.b_min_eligible or row.b_max_eligible:
        if row.source_layer == "po_open" and not row.document_key:
            errors.append("identified PO bounds require a document key")
        if not row.source_complete or not row.source_key or row.identity_confidence != "proven":
            errors.append("bounds require complete, identified source evidence")
        if row.possible_duplicate or row.dedup_assumed:
            errors.append("ambiguous duplicates cannot enter bounds")
    if row.b_min_eligible:
        if row.timezone_status != "verified" or aware_timestamp(row.source_as_of) is None:
            errors.append("B_min requires a verified source instant")
        if row.warehouse_confidence != "confirmed" or row.role not in ("finished", "component"):
            errors.append("B_min requires a confirmed warehouse and material role")
    if row.scope == "external_fba" and (row.b_min_eligible or row.b_max_eligible):
        errors.append("external_fba rows cannot enter B_min/B_max")
    if row.warehouse_confidence == "unmapped" and (row.b_min_eligible or row.b_max_eligible):
        errors.append("unmapped rows cannot enter B_min/B_max")
    if row.role == "cover" and row.b_min_eligible:
        errors.append("cover conversion is unproven; cannot enter B_min")
    return errors


def require_valid(row: SupplyRow) -> SupplyRow:
    errors = validate_supply_row(row)
    if errors:
        raise ValueError("; ".join(errors))
    return row


def to_dict(row: SupplyRow) -> dict:
    data = asdict(row)
    data["qty"] = None if row.qty is None else str(row.qty)
    return data
