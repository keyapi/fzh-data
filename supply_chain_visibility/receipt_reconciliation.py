"""Pure reconciliation of receipt events against per-warehouse stock snapshots.

This classifies receipt deltas around a collection window; it is not a stock
replay or an available-inventory calculation.
"""

from collections import defaultdict
from dataclasses import dataclass
from datetime import datetime, timezone
from decimal import Decimal, InvalidOperation
from typing import Iterable, Mapping, Optional, Union


Timestamp = Union[str, datetime]


@dataclass(frozen=True)
class ReceiptEvent:
    receipt_id: Optional[str]
    line_id: Optional[str]
    po_code: Optional[str]
    sku: Optional[str]
    warehouse: Optional[str]
    uom: Optional[str]
    quantity: object
    stock_effective_at: Optional[Timestamp]


@dataclass(frozen=True)
class SnapshotWindow:
    start: Timestamp
    end: Timestamp


@dataclass(frozen=True)
class ReconciledEvent:
    input_index: int
    receipt_id: Optional[str]
    line_id: Optional[str]
    po_code: Optional[str]
    sku: Optional[str]
    warehouse: Optional[str]
    uom: Optional[str]
    quantity: Optional[Decimal]
    stock_effective_at: Optional[datetime]
    disposition: str
    reason: Optional[str]
    duplicate_of: Optional[int] = None
    po_association_unknown: bool = False
    receipt_delta_candidate: bool = False


@dataclass(frozen=True)
class Aggregate:
    sku: str
    warehouse: str
    uom: str
    before: Decimal
    after: Decimal
    uncertain: Decimal


@dataclass(frozen=True)
class ReconciliationSummary:
    """Input-row partition: input = unique + duplicate + conflict + unknown."""

    input_count: int
    # Successfully classified, unique event rows (before/after/uncertain).
    unique_count: int
    duplicate_count: int
    conflict_count: int
    unknown_count: int


@dataclass(frozen=True)
class ReconciliationResult:
    events: tuple[ReconciledEvent, ...]
    aggregates: tuple[Aggregate, ...]
    summary: ReconciliationSummary


def _timestamp(value: Optional[Timestamp]) -> Optional[datetime]:
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
    return parsed.astimezone(timezone.utc)


def _time_issue(value: Optional[Timestamp]) -> str:
    if value is None or value == "":
        return "missing_effective_time"
    if isinstance(value, datetime):
        return "timezone_missing" if value.tzinfo is None or value.utcoffset() is None else "invalid_effective_time"
    if isinstance(value, str):
        try:
            parsed = datetime.fromisoformat(value.replace("Z", "+00:00"))
        except ValueError:
            return "invalid_effective_time"
        if parsed.tzinfo is None or parsed.utcoffset() is None:
            return "timezone_missing"
    return "invalid_effective_time"


def _decimal(value: object) -> Optional[Decimal]:
    """Accept finite nonnegative quantities; zero is a valid no-op receipt line."""
    if value is None or isinstance(value, bool):
        return None
    try:
        number = Decimal(str(value).strip())
    except (InvalidOperation, ValueError, AttributeError):
        return None
    if not number.is_finite() or number < 0:
        return None
    return number


def _identity(event: ReceiptEvent) -> tuple:
    """Normalize payload for exact replay detection without masking conflicts."""
    effective = _timestamp(event.stock_effective_at)
    quantity = _decimal(event.quantity)
    raw_quantity = quantity if quantity is not None else str(event.quantity)
    timestamp_value = effective if effective is not None else str(event.stock_effective_at)
    return (
        event.po_code, event.sku, event.warehouse, event.uom,
        raw_quantity, timestamp_value,
    )


def _has_stable_id(event: ReceiptEvent) -> bool:
    return bool(event.receipt_id and event.receipt_id.strip() and event.line_id and event.line_id.strip())


def reconcile_receipts(
    events: Iterable[ReceiptEvent],
    warehouse_windows: Mapping[str, SnapshotWindow],
    run_window: Optional[SnapshotWindow] = None,
) -> ReconciliationResult:
    """Classify normalized receipt lines against snapshot fetch intervals.

    Timestamps must carry an explicit UTC offset; naive timestamps remain
    unknown. Strictly earlier than window.start is ``before`` and strictly
    later than window.end is ``after``. Both endpoints and the interval are
    ``uncertain``. A run window is a conservative fallback when a warehouse
    has no dedicated fetch interval.
    """
    source = list(events)
    windows = {}
    for warehouse, window in warehouse_windows.items():
        start, end = _timestamp(window.start), _timestamp(window.end)
        windows[warehouse] = (start, end) if start and end and start <= end else None
    fallback = None
    if run_window is not None:
        start, end = _timestamp(run_window.start), _timestamp(run_window.end)
        fallback = (start, end) if start and end and start <= end else None

    identities = defaultdict(list)
    for index, event in enumerate(source):
        if _has_stable_id(event):
            identities[(event.receipt_id, event.line_id)].append(index)

    conflict_indexes = set()
    duplicates = {}
    for indexes in identities.values():
        fingerprints = {_identity(source[index]) for index in indexes}
        if len(fingerprints) > 1:
            conflict_indexes.update(indexes)
            continue
        duplicates.update({index: indexes[0] for index in indexes[1:]})

    rows = []
    totals = defaultdict(lambda: [Decimal(0), Decimal(0), Decimal(0)])
    unknown_count = 0
    for index, event in enumerate(source):
        quantity = _decimal(event.quantity)
        effective = _timestamp(event.stock_effective_at)
        disposition, reason = "unknown", None
        delta_candidate = False

        if index in conflict_indexes:
            disposition, reason = "conflict", "identity_payload_conflict"
        elif index in duplicates:
            disposition, reason = "duplicate", "exact_replay"
        elif not _has_stable_id(event):
            reason = "missing_stable_id"
        elif quantity is None:
            reason = "invalid_quantity"
        elif not event.uom:
            reason = "unknown_uom"
        elif not effective:
            reason = _time_issue(event.stock_effective_at)
        elif not event.sku or not event.warehouse:
            reason = "missing_sku_or_warehouse"
        else:
            bounds = windows.get(event.warehouse)
            if event.warehouse not in windows:
                bounds = fallback
            if bounds is None:
                reason = "invalid_snapshot_window" if event.warehouse in windows or (run_window is not None and fallback is None) else "missing_snapshot_window"
            elif effective < bounds[0]:
                disposition = "before"
            elif effective > bounds[1]:
                disposition = "after"
                delta_candidate = True
            else:
                disposition = "uncertain"

        if disposition == "unknown":
            unknown_count += 1
        row = ReconciledEvent(
            input_index=index,
            receipt_id=event.receipt_id,
            line_id=event.line_id,
            po_code=event.po_code,
            sku=event.sku,
            warehouse=event.warehouse,
            uom=event.uom,
            quantity=quantity,
            stock_effective_at=effective,
            disposition=disposition,
            reason=reason,
            duplicate_of=duplicates.get(index),
            po_association_unknown=not bool(event.po_code),
            receipt_delta_candidate=delta_candidate,
        )
        rows.append(row)
        if disposition in ("before", "after", "uncertain"):
            key = (event.sku, event.warehouse, event.uom)
            totals[key][{"before": 0, "after": 1, "uncertain": 2}[disposition]] += quantity

    aggregates = tuple(
        Aggregate(*key, before=amounts[0], after=amounts[1], uncertain=amounts[2])
        for key, amounts in sorted(totals.items())
    )
    classified_count = sum(row.disposition in ("before", "after", "uncertain") for row in rows)
    summary = ReconciliationSummary(
        input_count=len(source),
        unique_count=classified_count,
        duplicate_count=len(duplicates),
        conflict_count=len(conflict_indexes),
        unknown_count=unknown_count,
    )
    return ReconciliationResult(tuple(rows), aggregates, summary)
