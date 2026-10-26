"""Map collected receipt rows into the pure reconciliation core and summarize coverage.

The Tongtool response has no stable receipt/line ID, no UOM, and no timezone
offset. This layer keeps those gaps visible: rows stay unknown and no quantity
is added to available stock or deducted from in-transit.
"""
from __future__ import annotations

from collections import Counter
from datetime import datetime
from typing import Iterable, Mapping, Optional

from supply_chain_visibility.receipt_reconciliation import (
    ReceiptEvent,
    SnapshotWindow,
    reconcile_receipts,
)
from tongtool_api.receipt_collector import CollectionResult


def _first(row: dict, *names: str):
    for name in names:
        value = row.get(name)
        if value not in (None, ""):
            return value
    return None


def _has_explicit_offset(value) -> bool:
    if isinstance(value, datetime):
        return value.tzinfo is not None and value.utcoffset() is not None
    if isinstance(value, str):
        try:
            parsed = datetime.fromisoformat(value.replace("Z", "+00:00"))
        except ValueError:
            return False
        return parsed.tzinfo is not None and parsed.utcoffset() is not None
    return False


def events_from_collection(result: CollectionResult) -> list[ReceiptEvent]:
    """Keep one event per non-overlap row; overlap replays stay in the audit count."""
    events = []
    for collected in result.rows:
        if collected.overlap_duplicate:
            continue
        row = collected.row
        events.append(ReceiptEvent(
            receipt_id=_first(row, "receiptId", "receipt_id"),
            line_id=_first(row, "lineId", "line_id"),
            po_code=_first(row, "purchaseOrderCode", "purchase_order_code"),
            sku=_first(row, "sku"),
            warehouse=_first(row, "warehouseName", "warehouse_name"),
            uom=_first(row, "uom"),
            quantity=_first(row, "warehousingNum", "warehousing_num"),
            stock_effective_at=_first(row, "warehousingDate", "warehousing_date"),
            weak_event_key=collected.weak_event_key,
            possible_duplicate=collected.possible_duplicate,
            dedup_assumed=False,
        ))
    return events


def build_coverage_report(
    result: CollectionResult,
    *,
    warehouse_windows: Optional[Mapping[str, SnapshotWindow]] = None,
    run_window: Optional[SnapshotWindow] = None,
    collection_windows: Optional[Iterable[SnapshotWindow]] = None,
) -> dict:
    """Aggregate-only coverage report; never includes row-level quantities."""
    events = events_from_collection(result)
    reconciliation = reconcile_receipts(
        events,
        warehouse_windows or {},
        run_window=run_window,
        collection_windows=collection_windows,
    )
    dispositions = Counter(row.disposition for row in reconciliation.events)
    unknown_reasons = Counter(row.reason for row in reconciliation.events if row.reason)
    kept = [row for row in result.rows if not row.overlap_duplicate]
    days = Counter((row.row.get("warehousingDate") or "")[:10] for row in kept)
    return {
        "collection": {
            "input_count": result.input_count,
            "unique_count": result.unique_count,
            "overlap_duplicate_count": result.overlap_duplicate_count,
            "possible_duplicate_count": result.possible_duplicate_count,
            "truncated_windows": [
                {"start": w.start.isoformat(), "end": w.end.isoformat()}
                for w in result.truncated_windows
            ],
            "cache_hits": result.cache_hits,
        },
        "reconciliation": {
            "input_count": reconciliation.summary.input_count,
            "unique_count": reconciliation.summary.unique_count,
            "duplicate_count": reconciliation.summary.duplicate_count,
            "conflict_count": reconciliation.summary.conflict_count,
            "unknown_count": reconciliation.summary.unknown_count,
            "not_collected_count": reconciliation.summary.not_collected_count,
            "dispositions": dict(sorted(dispositions.items())),
            "unknown_reasons": dict(sorted(unknown_reasons.items())),
        },
        "coverage": {
            "distinct_po": len({e.po_code for e in events if e.po_code}),
            "distinct_sku": len({e.sku for e in events if e.sku}),
            "day_counts": dict(sorted(days.items())),
            "rows_without_stable_id": sum(1 for e in events if not (e.receipt_id and e.line_id)),
            "rows_without_uom": sum(1 for e in events if not e.uom),
            "rows_with_naive_time": sum(1 for e in events if e.stock_effective_at and not _has_explicit_offset(e.stock_effective_at)),
        },
        "note": (
            "Source rows lack stable receipt/line IDs, UOM, and timezone offsets; "
            "they stay unknown. No quantity is added to available stock or deducted from in-transit."
        ),
    }
