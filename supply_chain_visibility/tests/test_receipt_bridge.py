from datetime import datetime, timezone
from decimal import Decimal
import unittest

from supply_chain_visibility.receipt_bridge import (
    InventoryRow,
    PoOpenRow,
    TransitRow,
    build_receipt_bridge,
)
from supply_chain_visibility.receipt_reconciliation import ReceiptEvent, SnapshotWindow


def po(**changes):
    values = {
        "po_code": "PO1", "sku": "S1", "warehouse": "WH-A",
        "qty": Decimal("10"), "uom": "Nos",
        "as_of": "2026-10-14T00:00:00+08:00", "status": "3",
    }
    values.update(changes)
    return PoOpenRow(**values)


def inventory(**changes):
    values = {
        "sku": "S1", "warehouse": "WH-A", "available": Decimal("0"), "uom": "Nos",
        "as_of": "2026-10-14T05:17:00+08:00",
        "window_start": "2026-10-14T05:17:00+08:00",
        "window_end": "2026-10-14T05:31:00+08:00",
    }
    values.update(changes)
    return InventoryRow(**values)


def event(when="2026-10-14T07:25:00+08:00", quantity="5", uom="Nos", **changes):
    values = {
        "receipt_id": None, "line_id": None, "po_code": "PO1", "sku": "S1",
        "warehouse": "WH-A", "uom": uom, "quantity": quantity,
        "stock_effective_at": when,
    }
    values.update(changes)
    return ReceiptEvent(**values)


class ReceiptBridgeTests(unittest.TestCase):
    def test_after_snapshot_is_not_added_to_available(self):
        rows = build_receipt_bridge([po()], [event()], [inventory()])
        self.assertEqual(len(rows), 1)
        row = rows[0]
        self.assertEqual(row["po_open_qty"], "10")
        self.assertEqual(row["inventory_qty"], "0")
        self.assertEqual(row["after_snapshot_rows"], 1)
        self.assertEqual(row["after_snapshot_qty"], "5")
        self.assertFalse(row["flags"]["receipts_may_be_in_inventory"])
        self.assertNotIn("adjusted_available", row)

    def test_before_snapshot_flags_inventory_double_count(self):
        row = build_receipt_bridge([po()], [event(when="2026-10-14T05:10:00+08:00")], [inventory()])[0]
        self.assertEqual(row["before_snapshot_rows"], 1)
        self.assertEqual(row["before_snapshot_qty"], "5")
        self.assertTrue(row["flags"]["receipts_may_be_in_inventory"])

    def test_before_po_as_of_flags_possible_double_deduction(self):
        row = build_receipt_bridge(
            [po(as_of="2026-10-14T08:00:00+08:00")], [event()], [inventory()]
        )[0]
        self.assertEqual(row["before_or_at_po_as_of_rows"], 1)
        self.assertTrue(row["flags"]["po_remaining_may_include_receipts"])

    def test_naive_time_is_unknown_and_not_compared(self):
        row = build_receipt_bridge([po()], [event(when="2026-10-14 07:25:00")], [inventory()])[0]
        self.assertEqual(row["unknown_time_rows"], 1)
        self.assertEqual(row["unknown_time_qty"], "5")
        self.assertEqual(row["before_snapshot_rows"], 0)
        self.assertEqual(row["after_snapshot_rows"], 0)
        self.assertTrue(row["flags"]["timezone_unverified"])

    def test_uom_groups_stay_separate(self):
        rows = build_receipt_bridge(
            [po(), po(uom="Box")], [event()], [inventory()]
        )
        self.assertEqual(len(rows), 2)
        self.assertEqual({row["uom"] for row in rows}, {"Nos", "Box"})

    def test_not_collected_event_is_flagged(self):
        row = build_receipt_bridge(
            [po()], [event()], [inventory()],
            collection_windows=[SnapshotWindow(
                "2026-10-14T00:00:00+08:00", "2026-10-14T06:00:00+08:00"
            )],
        )[0]
        self.assertEqual(row["not_collected_rows"], 1)
        self.assertEqual(row["not_collected_qty"], "5")
        self.assertTrue(row["flags"]["not_collected"])

    def test_receipt_uom_unknown_stays_separate(self):
        rows = build_receipt_bridge([po()], [event(uom=None)], [inventory()])
        self.assertEqual(len(rows), 2)
        receipt_row = [row for row in rows if row["uom"] is None][0]
        self.assertTrue(receipt_row["flags"]["uom_unknown"])

    def test_same_batch_transit_is_flagged(self):
        row = build_receipt_bridge(
            [po()], [event()], [inventory()],
            transit_rows=[TransitRow("S1", "WH-A", Decimal("10"), "Nos")],
        )[0]
        self.assertEqual(row["transit_qty"], "10")
        self.assertEqual(row["overlap_status"], "same_batch_suspected")
        self.assertTrue(row["flags"]["same_batch_suspected"])

    def test_unequal_transit_is_distinct(self):
        row = build_receipt_bridge(
            [po()], [event()], [inventory()],
            transit_rows=[TransitRow("S1", "WH-A", Decimal("7"), "Nos")],
        )[0]
        self.assertEqual(row["overlap_status"], "distinct")
        self.assertFalse(row["flags"]["same_batch_suspected"])


if __name__ == "__main__":
    unittest.main()
