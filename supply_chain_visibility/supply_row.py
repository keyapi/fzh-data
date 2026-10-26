"""Canonical supply row for PO / inventory / in-transit / receipt integration."""
from __future__ import annotations

from dataclasses import asdict, dataclass
from decimal import Decimal
from typing import Optional

STAGES = (
    "on_hand", "po_open", "in_production", "shipped_in_transit",
    "received", "partially_received", "unknown",
)
QTY_STATUSES = ("known", "estimated", "unknown")
DATE_CONFIDENCES = ("confirmed", "estimated", "unknown")
IDENTITY_CONFIDENCES = ("proven", "weak_identity", "unproven")
TIMEZONE_STATUSES = ("verified", "unverified")


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


def validate_supply_row(row: SupplyRow) -> list[str]:
    errors = []
    if row.stage not in STAGES:
        errors.append(f"invalid stage: {row.stage}")
    if row.qty_status not in QTY_STATUSES:
        errors.append(f"invalid qty_status: {row.qty_status}")
    if row.date_confidence not in DATE_CONFIDENCES:
        errors.append(f"invalid date_confidence: {row.date_confidence}")
    if row.identity_confidence not in IDENTITY_CONFIDENCES:
        errors.append(f"invalid identity_confidence: {row.identity_confidence}")
    if row.timezone_status not in TIMEZONE_STATUSES:
        errors.append(f"invalid timezone_status: {row.timezone_status}")
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
