#!/usr/bin/env python3
"""Local synthetic benchmark for the supply integration data layer (no production calls)."""
from __future__ import annotations

import argparse
import json
import sys
import time
import tracemalloc
from decimal import Decimal
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from supply_chain_visibility.receipt_bridge import (
    InventoryRow,
    PoOpenRow,
    TransitRow,
    build_receipt_bridge,
)
from supply_chain_visibility.receipt_reconciliation import ReceiptEvent
from supply_chain_visibility.supply_integration import build_supply_integration, report_only

AS_OF = "2026-10-14T05:17:00+08:00"
WINDOW_END = "2026-10-14T05:31:00+08:00"
RECEIPT_AT = "2026-10-14T07:25:00+08:00"


def make_inputs(rows_per_source: int):
    po_rows, inventory_rows, transit_rows, receipts = [], [], [], []
    for index in range(rows_per_source):
        sku = f"TEST-SKU-{index:06d}"
        warehouse = f"TEST-WH-{index % 5}"
        po_code = f"TEST-PO-{index:06d}"
        po_rows.append(PoOpenRow(po_code, sku, warehouse, Decimal("10"), "Nos", as_of=AS_OF))
        inventory_rows.append(InventoryRow(
            sku, warehouse, Decimal("5"), "Nos", as_of=AS_OF,
            window_start=AS_OF, window_end=WINDOW_END,
        ))
        transit_rows.append(TransitRow(sku, warehouse, Decimal("10"), "Nos", as_of=AS_OF))
        receipts.append(ReceiptEvent(
            None, None, po_code, sku, warehouse, "Nos", Decimal("3"), RECEIPT_AT,
            weak_event_key=(po_code, sku, warehouse, RECEIPT_AT, "3"),
        ))
    return po_rows, inventory_rows, transit_rows, receipts


def timed(function, repeat: int = 2) -> float:
    best = float("inf")
    for _ in range(repeat):
        started = time.perf_counter()
        function()
        best = min(best, time.perf_counter() - started)
    return best


def main() -> int:
    parser = argparse.ArgumentParser(description="Synthetic local benchmark (no production calls)")
    parser.add_argument("--sizes", default="1000,5000,10000")
    parser.add_argument("--repeat", type=int, default=2)
    args = parser.parse_args()
    sizes = [int(value) for value in args.sizes.split(",") if value.strip()]

    results = []
    for size in sizes:
        data = make_inputs(size)
        build_supply_integration(*data)  # warm-up
        tracemalloc.start()
        started = time.perf_counter()
        integration = build_supply_integration(*data)
        elapsed = time.perf_counter() - started
        _, peak = tracemalloc.get_traced_memory()
        tracemalloc.stop()
        bridge_seconds = timed(lambda: build_receipt_bridge(data[0], data[3], data[1], transit_rows=data[2]), args.repeat)
        report_seconds = timed(lambda: report_only(integration), args.repeat)
        result = {
            "rows_per_source": size,
            "total_rows": size * 4,
            "build_seconds": round(elapsed, 4),
            "bridge_seconds": round(bridge_seconds, 4),
            "report_only_seconds": round(report_seconds, 6),
            "peak_mb": round(peak / 1024 / 1024, 2),
            "bridge_rows": integration["summary"]["bridge"]["rows"],
            "b_min_uom_keys": list(integration["summary"]["b_min_by_uom"].keys()),
        }
        results.append(result)
        print(json.dumps(result, ensure_ascii=False))
    print("RESULTS", json.dumps(results, ensure_ascii=False))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
