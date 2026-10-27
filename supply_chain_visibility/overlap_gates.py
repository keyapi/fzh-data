"""Overlap and unit gates for PO / in-transit / DN trace / FBA supply rows."""
from __future__ import annotations

from collections import Counter, defaultdict
from dataclasses import replace
from decimal import Decimal
from typing import Iterable

from supply_chain_visibility.supply_row import SupplyRow, aware_timestamp


def _qty(row: SupplyRow) -> Decimal:
    return row.qty if row.qty is not None else Decimal(0)


def classify_batch_overlap(po_qty, transit_qty, po_batches, transit_batches) -> str:
    """Quantities can raise suspicion; only proven batch keys establish lineage."""
    pos, transits = list(po_batches), list(transit_batches)
    if pos and transits and all(proven and key for key, proven in pos + transits):
        po_keys, transit_keys = {key for key, _ in pos}, {key for key, _ in transits}
        if po_keys.isdisjoint(transit_keys):
            return "distinct"
        if len(po_keys | transit_keys) == 1:
            if po_qty is not None and transit_qty is not None and po_qty == transit_qty:
                return "proven"
            return "batch_quantity_conflict"
    if po_qty is not None and transit_qty is not None and po_qty > 0 and transit_qty > 0:
        if abs(po_qty - transit_qty) < Decimal("0.000001"):
            return "same_batch_suspected"
    return "unknown"


def apply_overlap_gates(rows: Iterable[SupplyRow]) -> list[SupplyRow]:
    """Apply the ordered exclusion rules and PO/in-transit overlap detection.

    Precedence: external FBA > unmapped > trace-only > unknown qty > unknown
    UOM > cover conversion > PO side of a suspected same batch. B_max keeps
    both sides of a suspected overlap; B_min keeps one side only.
    """
    source = list(rows)
    groups = defaultdict(list)
    for row in source:
        groups[(row.sku, row.warehouse, row.uom)].append(row)

    gated = []
    for _, items in groups.items():
        active = [row for row in items if row.exclusion_reason not in (
            "exact_replay", "source_identity_conflict", "source_grain_conflict"
        )]
        pos = [row for row in active if row.source_layer == "po_open" and row.scope == "in_house"]
        transits = [row for row in active if row.source_layer == "in_transit" and row.scope == "in_house"]
        po_qty = sum(_qty(row) for row in pos)
        transit_qty = sum(_qty(row) for row in transits)
        supply_sources = [row for row in items if row.source_layer in ("inventory_snapshot", "po_open", "in_transit", "work_order")
                          and row.b_min_eligible]
        source_instants = {aware_timestamp(row.source_as_of) for row in supply_sources}
        mixed_basis = len(source_instants) > 1
        status = classify_batch_overlap(po_qty, transit_qty,
                                        [(row.batch_key, row.batch_proven) for row in pos],
                                        [(row.batch_key, row.batch_proven) for row in transits])
        proven_distinct = status == "distinct"

        for row in items:
            b_min, b_max = row.b_min_eligible, row.b_max_eligible
            reason = row.exclusion_reason
            if reason in ("exact_replay", "source_identity_conflict", "source_grain_conflict"):
                b_min = b_max = False
            elif row.scope == "external_fba":
                b_min = b_max = False
                reason = "external_fba"
            elif row.warehouse_confidence == "unmapped":
                b_min = b_max = False
                reason = "unmapped"
            elif row.source_layer == "dn_trace":
                b_min = b_max = False
                reason = "trace_only"
            elif row.source_layer in ("receipt_event", "demand"):
                b_min = b_max = False
                reason = reason or "evidence_only"
            elif row.not_collected:
                b_min = b_max = False
                reason = "not_collected"
            elif row.qty is None:
                b_min = b_max = False
                reason = "qty_unknown"
            elif not row.uom_proven:
                b_min = b_max = False
                reason = "uom_unproven"
            elif not row.source_complete or not row.source_key or row.identity_confidence != "proven":
                b_min = b_max = False
                reason = "source_unproven"
            elif row.possible_duplicate or row.dedup_assumed:
                b_min = b_max = False
                reason = "duplicate_unproven"
            elif status == "batch_quantity_conflict" and row.source_layer in ("po_open", "in_transit"):
                b_min = b_max = False
                reason = "batch_quantity_conflict"
            elif status == "proven" and row.source_layer == "po_open":
                b_min = b_max = False
                reason = "proven_batch_replay"
            elif row.timezone_status != "verified" or aware_timestamp(row.source_as_of) is None:
                b_min = False
                reason = "source_time_unverified"
            elif row.warehouse_confidence != "confirmed" or row.role == "unknown":
                b_min = False
                reason = "mapping_unproven"
            elif row.role == "cover":
                b_min = False
                reason = "cover_conversion_unproven"
            elif mixed_basis:
                b_min = False
                reason = "source_time_mismatch"
            elif pos and transits and not proven_distinct and row.source_layer == "po_open":
                b_min = False
                reason = "po_not_counted"
            gated.append(replace(
                row,
                overlap_status=status if row.source_layer in ("po_open", "in_transit") else row.overlap_status,
                b_min_eligible=b_min,
                b_max_eligible=b_max,
                exclusion_reason=reason,
            ))
    return sorted(gated, key=lambda row: (row.sku, row.warehouse, row.uom or "", row.source_layer))


def summarize_overlap(rows: Iterable[SupplyRow]) -> dict:
    source = list(rows)
    return {
        "rows": len(source),
        "by_overlap_status": dict(sorted(Counter(
            row.overlap_status for row in source if row.source_layer in ("po_open", "in_transit")
        ).items())),
        "b_min_rows": sum(1 for row in source if row.b_min_eligible),
        "b_max_rows": sum(1 for row in source if row.b_max_eligible),
        "exclusions": dict(sorted(Counter(
            row.exclusion_reason for row in source if row.exclusion_reason
        ).items())),
    }
