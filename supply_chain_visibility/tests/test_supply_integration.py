from decimal import Decimal
import unittest

from supply_chain_visibility.receipt_bridge import InventoryRow, PoOpenRow, TransitRow
from supply_chain_visibility.receipt_reconciliation import ReceiptEvent, SnapshotWindow
from supply_chain_visibility.supply_integration import build_supply_integration, report_only


def inputs(uom="Nos", receipt_when="2026-10-14T07:25:00+08:00", collection_windows=None):
    po = PoOpenRow("PO1", "S1", "WH-A", Decimal("10"), uom,
                   as_of="2026-10-14T00:00:00+08:00")
    inventory = InventoryRow(
        "S1", "WH-A", Decimal("5"), uom, as_of="2026-10-14T05:17:00+08:00",
        window_start="2026-10-14T05:17:00+08:00", window_end="2026-10-14T05:31:00+08:00",
    )
    transit = TransitRow("S1", "WH-A", Decimal("10"), uom, as_of="2026-10-14T05:17:00+08:00")
    receipt = ReceiptEvent(
        None, None, "PO1", "S1", "WH-A", uom, Decimal("10"), receipt_when,
        weak_event_key=("PO1", "S1", "WH-A", "2026-10-14T07:25:00+08:00", "10"),
    )
    return [po], [inventory], [transit], [receipt]


class SupplyIntegrationTests(unittest.TestCase):
    def test_same_batch_keeps_bmin_single_sided_and_bmax_both(self):
        po, inventory, transit, receipts = inputs()
        integration = build_supply_integration(po, inventory, transit, receipts)
        summary = integration["summary"]
        self.assertEqual(summary["rows"], 4)
        self.assertEqual(summary["by_source_layer"], {
            "inventory_snapshot": 1, "in_transit": 1, "po_open": 1, "receipt_event": 1,
        })
        self.assertEqual(summary["b_min_by_uom"], {"Nos": "15"})
        self.assertEqual(summary["b_max_by_uom"], {"Nos": "25"})
        self.assertEqual(summary["by_overlap_status"], {"same_batch_suspected": 2})
        self.assertEqual(summary["validation_errors"], 0)
        self.assertEqual(summary["bridge"]["same_batch_suspected"], 1)
        self.assertTrue(summary["flags"]["same_batch_suspected"])
        self.assertGreaterEqual(summary["flags"]["unknown_rows"], 1)

    def test_unknown_uom_blocks_bmin_but_stays_in_bmax_bucket(self):
        po, inventory, transit, receipts = inputs(uom=None)
        summary = build_supply_integration(po, inventory, transit, receipts)["summary"]
        self.assertEqual(summary["b_min_by_uom"], {})
        self.assertEqual(summary["b_max_by_uom"], {"(unknown)": "25"})
        self.assertTrue(summary["flags"]["uom_unknown"])
        self.assertEqual(summary["validation_errors"], 0)

    def test_not_collected_receipt_is_flagged(self):
        po, inventory, transit, receipts = inputs()
        summary = build_supply_integration(
            po, inventory, transit, receipts,
            collection_windows=[SnapshotWindow(
                "2026-10-14T00:00:00+08:00", "2026-10-14T06:00:00+08:00"
            )],
        )["summary"]
        self.assertTrue(summary["flags"]["not_collected"])
        self.assertEqual(summary["bridge"]["not_collected"], 1)

    def test_naive_receipt_time_is_unknown_and_not_adjusted(self):
        po, inventory, transit, receipts = inputs(receipt_when="2026-10-14 07:25:00")
        integration = build_supply_integration(po, inventory, transit, receipts)
        summary = integration["summary"]
        self.assertTrue(summary["flags"]["timezone_unverified"])
        self.assertEqual(summary["b_min_by_uom"], {"Nos": "15"})
        receipt_rows = [row for row in integration["rows"] if row["source_layer"] == "receipt_event"]
        self.assertEqual(receipt_rows[0]["exclusion_reason"], "timezone_unverified")
        self.assertFalse(receipt_rows[0]["b_min_eligible"])
        self.assertFalse(receipt_rows[0]["b_max_eligible"])

    def test_report_only_has_no_row_details(self):
        po, inventory, transit, receipts = inputs()
        report = report_only(build_supply_integration(po, inventory, transit, receipts))
        self.assertIn("summary", report)
        self.assertNotIn("rows", report)
        self.assertNotIn("bridge_rows", report)


if __name__ == "__main__":
    unittest.main()
