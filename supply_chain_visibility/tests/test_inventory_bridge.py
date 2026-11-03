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


def proof(receipt_id="R1", line_id="L1", snapshot_id="SNAP-1",
          as_of="2026-10-05T00:00:00+00:00"):
    return {
        "proof_type": "snapshot_row_match",
        "source_record": "%s#%s" % (snapshot_id, receipt_id),
        "receipt_identity": {"receipt_id": receipt_id, "line_id": line_id},
        "snapshot_id": snapshot_id,
        "source_as_of": as_of,
    }


def receipt(line_id="L1", at="2026-10-10T10:00:00+00:00", qty=10,
            sku="SKU-1", warehouse="WH-1", uom="个", proof_record=None):
    return ReceiptEvent(receipt_id="R1", line_id=line_id, po_code="PO-1",
                        sku=sku, warehouse=warehouse, uom=uom, quantity=qty,
                        stock_effective_at=at, uom_proven=True,
                        quantity_semantics_proven=True,
                        inclusion_proof_record=proof_record)


class InclusionStatusTests(unittest.TestCase):
    def test_after_snapshot_is_conditional_delta(self):
        result = build_inventory_bridge([snapshot()], [receipt()])
        row = result["rows"][0]
        self.assertEqual(row["receipt_inclusion_status"], "after_snapshot")
        self.assertEqual(row["post_snapshot_delta_qty"], "10")
        self.assertFalse(row["count_in_inventory"])
        self.assertFalse(result["summary"]["eligible"])

    def test_before_snapshot_with_structured_proof_is_included(self):
        row = build_inventory_bridge(
            [snapshot()],
            [receipt(at="2026-09-20T10:00:00+00:00",
                     proof_record=proof())]
        )["rows"][0]
        self.assertEqual(row["receipt_inclusion_status"], "included")
        self.assertEqual(row["inclusion_proof"]["proof_type"], "snapshot_row_match")
        self.assertTrue(row["count_in_inventory"])
        self.assertIsNone(row["post_snapshot_delta_qty"])

    def test_before_snapshot_without_proof_is_uncertain(self):
        row = build_inventory_bridge(
            [snapshot()], [receipt(at="2026-09-20T10:00:00+00:00")]
        )["rows"][0]
        self.assertEqual(row["receipt_inclusion_status"], "uncertain")
        self.assertEqual(row["exclusion_reason"], "inclusion_proof_missing")
        self.assertFalse(row["count_in_inventory"])

    def test_before_snapshot_with_legacy_boolean_is_not_included(self):
        event = receipt(at="2026-09-20T10:00:00+00:00")
        event = ReceiptEvent(**{**event.__dict__, "inclusion_proof": True})
        row = build_inventory_bridge([snapshot()], [event])["rows"][0]
        self.assertEqual(row["receipt_inclusion_status"], "uncertain")
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


class SnapshotBindingTests(unittest.TestCase):
    def test_multiple_snapshot_versions_conflict_without_splicing(self):
        second = snapshot(inventory_snapshot_id="SNAP-2",
                          as_of="2026-10-06T00:00:00+00:00",
                          window_start="2026-10-02T00:00:00+00:00",
                          window_end="2026-10-06T23:59:59+00:00")
        result = build_inventory_bridge([snapshot(), second], [receipt()])
        row = result["rows"][0]
        self.assertEqual(row["receipt_inclusion_status"], "conflict")
        self.assertEqual(row["exclusion_reason"], "multiple_snapshot_versions")
        self.assertIsNone(row["inventory_snapshot_id"])
        self.assertEqual(len(row["snapshot_candidates"]), 2)
        self.assertEqual(result["summary"]["snapshot_identity_count"], 2)
        self.assertIsNone(result["summary"]["snapshot_binding"])

    def test_same_snapshot_duplicate_rows_collapse(self):
        result = build_inventory_bridge([snapshot(), snapshot()], [receipt()])
        row = result["rows"][0]
        self.assertEqual(row["receipt_inclusion_status"], "after_snapshot")
        self.assertEqual(row["inventory_snapshot_id"], "SNAP-1")

    def test_proof_receipt_identity_mismatch_is_conflict(self):
        row = build_inventory_bridge(
            [snapshot()],
            [receipt(at="2026-09-20T10:00:00+00:00",
                     proof_record=proof(receipt_id="R-OTHER"))]
        )["rows"][0]
        self.assertEqual(row["receipt_inclusion_status"], "conflict")
        self.assertEqual(row["exclusion_reason"],
                         "inclusion_proof_identity_mismatch")

    def test_proof_snapshot_or_as_of_mismatch_is_conflict(self):
        for bad in (proof(snapshot_id="SNAP-OTHER"),
                    proof(as_of="2026-10-04T00:00:00+00:00")):
            row = build_inventory_bridge(
                [snapshot()],
                [receipt(at="2026-09-20T10:00:00+00:00", proof_record=bad)]
            )["rows"][0]
            self.assertEqual(row["receipt_inclusion_status"], "conflict")
            self.assertEqual(row["exclusion_reason"],
                             "inclusion_proof_identity_mismatch")

    def test_incomplete_proof_is_conflict(self):
        bad = proof()
        del bad["source_record"]
        row = build_inventory_bridge(
            [snapshot()],
            [receipt(at="2026-09-20T10:00:00+00:00", proof_record=bad)]
        )["rows"][0]
        self.assertEqual(row["receipt_inclusion_status"], "conflict")
        self.assertEqual(row["exclusion_reason"], "inclusion_proof_incomplete")


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
            receipt(line_id="L2", at="2026-09-20T10:00:00+00:00",
                    proof_record=proof(line_id="L2")),
            receipt(line_id="L3", at="2026-09-21T10:00:00+00:00"),
            receipt(line_id="L4", at="2026-10-03T10:00:00+00:00"),
            receipt(line_id="L5", sku="SKU-2"),
        ]
        result = build_inventory_bridge([snapshot()], events)
        self.assertEqual(result["summary"]["partition_total"], len(events))
        self.assertEqual(sum(result["summary"]["partition"].values()), len(events))

    def test_order_invariance(self):
        events = [receipt(line_id="L1", qty=10),
                  receipt(line_id="L2", at="2026-09-20T10:00:00+00:00",
                          proof_record=proof(line_id="L2"))]
        forward = build_inventory_bridge([snapshot()], events)
        reverse = build_inventory_bridge([snapshot()], list(reversed(events)))
        self.assertEqual(forward, reverse)

    def test_post_snapshot_delta_is_grouped_by_uom(self):
        snapshots = [
            snapshot(),
            snapshot(sku="SKU-2", uom="箱", available=5),
        ]
        events = [
            receipt(line_id="L1", sku="SKU-1", uom="个", qty=10),
            receipt(line_id="L2", sku="SKU-2", uom="箱", qty=2),
        ]
        summary = build_inventory_bridge(snapshots, events)["summary"]
        groups = {(g["sku"], g["uom"]): g["qty"]
                  for g in summary["post_snapshot_delta"]}
        self.assertEqual(groups[("SKU-1", "个")], "10")
        self.assertEqual(groups[("SKU-2", "箱")], "2")
        self.assertNotIn("post_snapshot_delta_qty", summary)


if __name__ == "__main__":
    unittest.main()
