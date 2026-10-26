"""Overlap and unit gates for PO / in-transit / DN trace / FBA supply rows."""
from __future__ import annotations

from collections import Counter, defaultdict
from dataclasses import replace
from decimal import Decimal
from typing import Iterable

from supply_chain_visibility.supply_row import SupplyRow


def _qty(row: SupplyRow) -> Decimal:
    return row.qty if row.qty is not None else Decimal(0)


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
        po_qty = sum(_qty(row) for row in items if row.source_layer == "po_open")
        transit_qty = sum(_qty(row) for row in items if row.source_layer == "in_transit")
        suspected = po_qty > 0 and transit_qty > 0 and abs(po_qty - transit_qty) < Decimal("0.000001")
        if suspected:
            status = "same_batch_suspected"
        elif po_qty > 0 and transit_qty > 0:
            status = "distinct"
        else:
            status = "unknown"

        for row in items:
            b_min, b_max = row.b_min_eligible, row.b_max_eligible
            reason = row.exclusion_reason
            if row.scope == "external_fba":
                b_min = b_max = False
                reason = "external_fba"
            elif row.warehouse_confidence == "unmapped":
                b_min = b_max = False
                reason = "unmapped"
            elif row.source_layer == "dn_trace":
                b_min = b_max = False
                reason = "trace_only"
            elif row.qty is None:
                b_min = b_max = False
                reason = "qty_unknown"
            elif not row.uom_proven:
                b_min = False
                reason = "uom_unproven"
            elif row.role == "cover":
                b_min = False
                reason = "cover_conversion_unproven"
            elif suspected and row.source_layer == "po_open":
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
