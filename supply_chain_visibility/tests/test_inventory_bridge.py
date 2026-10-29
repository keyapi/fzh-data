"""Tests for inventory snapshot receipt inclusion bridge."""
import unittest

from supply_chain_visibility.receipt_bridge import (
    SnapshotRow,
    build_inventory_bridge,
)
from supply_chain_visibility.receipt_reconciliation import ReceiptEvent


def snapshot(**overrides):
    row = dict(inventory_snapshot_id="SNAP-1", sku="SKU-1", warehouse="WH-1",
               uom="个", available=100,
               as_of="2026-10-05T00:00:00+00:00",
               window_start="2026-10-01T00:00:00+00:00",
               window_end="2026-10-05T23:59:59+00:00")
    row.update(overrides)
    return SnapshotRow(**row)


def receipt(line_id="L1", at="2026-10-10T10:00:00+00:00", qty=10,
            proof=False, sku="SKU-1", warehouse="WH-1", uom="个"):
    return ReceiptEvent(receipt_id="R1", line_id=line_id, po_code="PO-1",
                        sku=sku, warehouse=warehouse, uom=uom, quantity=qty,
                        stock_effective_at=at, uom_proven=True,
                        quantity_semantics_proven=True,
                        inclusion_proof=proof)


class InclusionStatusTests(unittest.TestCase):
    def test_after_snapshot_is_conditional_delta(self):
        result = build_inventory_bridge([snapshot()], [receipt()])
        row = result["rows"][0]
        self.assertEqual(row["receipt_inclusion_status"], "after_snapshot")
        self.assertEqual(row["post_snapshot_delta_qty"], "10")
        self.assertFalse(row["count_in_inventory"])
        self.assertFalse(result["summary"]["eligible"])

    def test_before_snapshot_with_proof_is_included(self):
        row = build_inventory_bridge(
            [snapshot()], [receipt(at="2026-09-20T10:00:00+00:00", proof=True)]
        )["rows"][0]
        self.assertEqual(row["receipt_inclusion_status"], "included")
        self.assertTrue(row["inclusion_proof"])
        self.assertTrue(row["count_in_inventory"])
        self.assertIsNone(row["post_snapshot_delta_qty"])

    def test_before_snapshot_without_proof_is_uncertain(self):
        row = build_inventory_bridge(
            [snapshot()], [receipt(at="2026-09-20T10:00:00+00:00", proof=False)]
        )["rows"][0]
        self.assertEqual(row["receipt_inclusion_status"], "uncertain")
        self.assertEqual(row["exclusion_reason"], "inclusion_proof_missing")
        self.assertFalse(row["count_in_inventory"])

    def test_inside_window_is_uncertain(self):
        row = build_inventory_bridge([snapshot()], [receipt(at="2026-10-03T10:00:00+00:00")])["rows"][0]
        self.assertEqual(row["receipt_inclusion_status"], "uncertain")
        self.assertEqual(row["exclusion_reason"], "inside_snapshot_window")

    def test_unmatched_snapshot_is_unknown(self):
        row = build_inventory_bridge([snapshot()], [receipt(sku="SKU-2")])["rows"][0]
        self.assertEqual(row["receipt_inclusion_status"], "unknown")
        self.assertEqual(row["exclusion_reason"], "unmatched_snapshot")

    def test_missing_time_is_unknown(self):
        row = build_inventory_bridge([snapshot()], [receipt(at=None)])["rows"][0]
        self.assertEqual(row["receipt_inclusion_status"], "unknown")
        self.assertEqual(row["exclusion_reason"], "missing_effective_time")


class DuplicateAndPartitionTests(unittest.TestCase):
    def test_exact_duplicate_counts_once_and_stays_visible(self):
        events = [receipt(line_id="L1"), receipt(line_id="L1")]
        result = build_inventory_bridge([snapshot()], events)
        self.assertEqual(result["summary"]["partition"]["duplicate"], 1)
        self.assertEqual(result["summary"]["partition"]["after_snapshot"], 1)
        self.assertEqual(result["summary"]["partition_total"], 2)

    def test_conflicting_payload_is_conflict(self):
        events = [receipt(line_id="L1", qty=10), receipt(line_id="L1", qty=12)]
        result = build_inventory_bridge([snapshot()], events)
        self.assertEqual(result["summary"]["partition"]["conflict"], 2)
        self.assertEqual(result["summary"]["partition_total"], 2)

    def test_partition_sums_to_input(self):
        events = [
            receipt(line_id="L1", at="2026-10-10T10:00:00+00:00"),
            receipt(line_id="L2", at="2026-09-20T10:00:00+00:00", proof=True),
            receipt(line_id="L3", at="2026-09-21T10:00:00+00:00", proof=False),
            receipt(line_id="L4", at="2026-10-03T10:00:00+00:00"),
            receipt(line_id="L5", sku="SKU-2"),
        ]
        result = build_inventory_bridge([snapshot()], events)
        self.assertEqual(result["summary"]["partition_total"], len(events))
        self.assertEqual(sum(result["summary"]["partition"].values()), len(events))

    def test_order_invariance(self):
        events = [receipt(line_id="L1", qty=10),
                  receipt(line_id="L2", at="2026-09-20T10:00:00+00:00", proof=True)]
        forward = build_inventory_bridge([snapshot()], events)
        reverse = build_inventory_bridge([snapshot()], list(reversed(events)))
        self.assertEqual(forward, reverse)


if __name__ == "__main__":
    unittest.main()
