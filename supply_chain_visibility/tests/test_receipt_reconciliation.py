from datetime import datetime, timezone
from decimal import Decimal
import unittest

from supply_chain_visibility.receipt_reconciliation import (
    ReceiptEvent,
    SnapshotWindow,
    reconcile_receipts,
)


def event(receipt_id="R1", line_id="1", **changes):
    values = {
        "receipt_id": receipt_id,
        "line_id": line_id,
        "po_code": "PO-1",
        "sku": "SKU-A",
        "warehouse": "WH-A",
        "uom": "Nos",
        "quantity": "2.5",
        "stock_effective_at": "2026-10-26T09:00:00+08:00",
    }
    values.update(changes)
    return ReceiptEvent(**values)


class ReceiptReconciliationTests(unittest.TestCase):
    def setUp(self):
        self.window = SnapshotWindow(
            "2026-10-26T10:00:00+08:00", "2026-10-26T10:14:00+08:00"
        )

    def test_classifies_before_after_and_uncertain_boundary_and_collection(self):
        result = reconcile_receipts(
            [
                event("before", stock_effective_at="2026-10-26T09:00:00+08:00"),
                event("at-start", stock_effective_at="2026-10-26T10:00:00+08:00"),
                event("during", stock_effective_at="2026-10-26T10:07:00+08:00"),
                event("at-end", stock_effective_at="2026-10-26T10:14:00+08:00"),
                event("after", stock_effective_at="2026-10-26T10:15:00+08:00"),
            ],
            {"WH-A": self.window},
        )
        self.assertEqual(
            [row.disposition for row in result.events],
            ["before", "uncertain", "uncertain", "uncertain", "after"],
        )
        self.assertEqual(result.aggregates[0].before, Decimal("2.5"))
        self.assertEqual(result.aggregates[0].after, Decimal("2.5"))
        self.assertEqual(result.aggregates[0].uncertain, Decimal("7.5"))
        self.assertTrue(result.events[-1].receipt_delta_candidate)

    def test_0517_run_window_separates_0900_from_0510(self):
        result = reconcile_receipts(
            [
                event("nine", stock_effective_at="2026-10-26T09:00:00+08:00"),
                event("five-ten", stock_effective_at="2026-10-26T05:10:00+08:00"),
            ],
            {},
            run_window=SnapshotWindow(
                "2026-10-26T05:17:00+08:00", "2026-10-26T05:31:00+08:00"
            ),
        )
        self.assertEqual([row.disposition for row in result.events], ["after", "before"])

    def test_partial_receipts_are_distinct_and_exact_replay_is_deduplicated(self):
        first = event("R1", "1", quantity="2", stock_effective_at="2026-10-26T10:15:00+08:00")
        second = event("R1", "2", quantity="3", stock_effective_at="2026-10-26T10:15:00+08:00")
        result = reconcile_receipts(
            [first, second, first], {"WH-A": self.window}
        )
        self.assertEqual([row.disposition for row in result.events], ["after", "after", "duplicate"])
        self.assertEqual(result.summary.input_count, 3)
        self.assertEqual(result.summary.unique_count, 2)
        self.assertEqual(result.summary.duplicate_count, 1)
        self.assertEqual(result.aggregates[0].after, Decimal("5"))

    def test_conflicting_identity_isolated_instead_of_picking_one_version(self):
        result = reconcile_receipts(
            [event(quantity="2"), event(quantity="9"), event(quantity="4")], {"WH-A": self.window}
        )
        self.assertEqual([row.disposition for row in result.events], ["conflict"] * 3)
        self.assertEqual(result.summary.conflict_count, 3)
        self.assertEqual(result.aggregates, ())

    def test_unknown_identity_time_uom_and_po_are_preserved(self):
        result = reconcile_receipts(
            [
                event(receipt_id=None),
                event("missing-time", stock_effective_at=None),
                event("missing-uom", uom=None),
                event("no-po", po_code=None),
            ],
            {"WH-A": self.window},
        )
        self.assertEqual([row.disposition for row in result.events], ["unknown", "unknown", "unknown", "before"])
        self.assertEqual(result.summary.unknown_count, 3)
        self.assertEqual(result.events[0].reason, "missing_stable_id")
        self.assertEqual(result.events[1].reason, "missing_effective_time")
        self.assertEqual(result.events[2].reason, "unknown_uom")
        self.assertTrue(result.events[3].po_association_unknown)

    def test_invalid_quantities_are_unknown(self):
        result = reconcile_receipts(
            [
                event("negative", quantity="-1"),
                event("nan", quantity="NaN"),
                event("infinity", quantity="Infinity"),
                event("blank", quantity=""),
                event("none", quantity=None),
                event("bool", quantity=True),
            ],
            {"WH-A": self.window},
        )
        self.assertEqual([row.disposition for row in result.events], ["unknown"] * 6)
        self.assertEqual([row.reason for row in result.events], ["invalid_quantity"] * 6)

    def test_zero_quantity_is_valid_and_stably_classified(self):
        result = reconcile_receipts(
            [event("zero", quantity="0", stock_effective_at="2026-10-26T10:15:00+08:00")],
            {"WH-A": self.window},
        )
        self.assertEqual(result.events[0].disposition, "after")
        self.assertEqual(result.aggregates[0].after, Decimal("0"))
        self.assertEqual(result.summary.unique_count, 1)

    def test_invalid_snapshot_windows_make_events_unknown(self):
        for window in (
            SnapshotWindow("2026-10-26T10:00:00", "2026-10-26T10:30:00+08:00"),
            SnapshotWindow("2026-10-26T10:30:00+08:00", "2026-10-26T10:00:00+08:00"),
        ):
            with self.subTest(window=window):
                result = reconcile_receipts([event()], {"WH-A": window})
                self.assertEqual(result.events[0].disposition, "unknown")
                self.assertEqual(result.events[0].reason, "invalid_snapshot_window")

    def test_blank_stable_ids_remain_unknown(self):
        result = reconcile_receipts(
            [event(receipt_id="  "), event("R2", line_id="\t")],
            {"WH-A": self.window},
        )
        self.assertEqual([row.reason for row in result.events], ["missing_stable_id"] * 2)
        self.assertEqual(result.summary.unique_count, 0)

    def test_summary_counts_partition_every_input_row(self):
        unknown = event("unknown-time", stock_effective_at=None)
        result = reconcile_receipts(
            [
                event("before"),
                event("after", stock_effective_at="2026-10-26T10:15:00+08:00"),
                unknown,
                unknown,
                event("conflict", quantity="1"),
                event("conflict", quantity="2"),
                event("conflict", quantity="3"),
                event(receipt_id=None),
            ],
            {"WH-A": self.window},
        )
        summary = result.summary
        self.assertEqual(
            summary.input_count,
            summary.unique_count + summary.duplicate_count + summary.conflict_count + summary.unknown_count,
        )
        self.assertEqual((summary.unique_count, summary.duplicate_count, summary.conflict_count, summary.unknown_count), (2, 1, 3, 2))

    def test_naive_timestamps_and_missing_warehouse_window_are_unknown(self):
        result = reconcile_receipts(
            [
                event("naive", stock_effective_at="2026-10-26T09:00:00"),
                event("no-window", warehouse="WH-B"),
            ],
            {"WH-A": self.window},
        )
        self.assertEqual([row.reason for row in result.events], ["timezone_missing", "missing_snapshot_window"])

    def test_run_window_is_conservative_fallback_and_offset_times_compare_by_instant(self):
        result = reconcile_receipts(
            [event(stock_effective_at="2026-10-26T01:45:00Z")],
            {},
            run_window=SnapshotWindow(
                "2026-10-26T09:00:00+08:00", "2026-10-26T09:30:00+08:00"
            ),
        )
        self.assertEqual(result.events[0].disposition, "after")

    def test_aggregation_keeps_warehouses_and_units_separate(self):
        result = reconcile_receipts(
            [
                event("a", warehouse="WH-A", uom="Nos", quantity="1", stock_effective_at="2026-10-26T10:15:00+08:00"),
                event("b", warehouse="WH-B", uom="Nos", quantity="2", stock_effective_at="2026-10-26T10:15:00+08:00"),
                event("c", warehouse="WH-A", uom="Box", quantity="3", stock_effective_at="2026-10-26T10:15:00+08:00"),
            ],
            {"WH-A": self.window, "WH-B": self.window},
        )
        self.assertEqual(len(result.aggregates), 3)
        self.assertEqual(
            {(a.sku, a.warehouse, a.uom, a.after) for a in result.aggregates},
            {("SKU-A", "WH-A", "Nos", Decimal("1")), ("SKU-A", "WH-B", "Nos", Decimal("2")), ("SKU-A", "WH-A", "Box", Decimal("3"))},
        )


    def test_collection_window_marks_uncollected_instead_of_after(self):
        result = reconcile_receipts(
            [event("late", stock_effective_at="2026-10-27T09:00:00+08:00")],
            {"WH-A": self.window},
            collection_windows=[
                SnapshotWindow("2026-10-26T00:00:00+08:00", "2026-10-26T23:59:59+08:00")
            ],
        )
        self.assertEqual(result.events[0].disposition, "not_collected")
        self.assertEqual(result.events[0].reason, "outside_collection_window")
        self.assertEqual(result.summary.not_collected_count, 1)
        summary = result.summary
        self.assertEqual(
            summary.input_count,
            summary.unique_count + summary.duplicate_count + summary.conflict_count
            + summary.unknown_count + summary.not_collected_count,
        )

    def test_weak_identity_flags_are_preserved(self):
        result = reconcile_receipts(
            [event(
                "weak",
                weak_event_key=("PO", "1", "G", "S", "W", "T", "N"),
                possible_duplicate=True,
                dedup_assumed=True,
            )],
            {"WH-A": self.window},
        )
        row = result.events[0]
        self.assertEqual(row.weak_event_key, ("PO", "1", "G", "S", "W", "T", "N"))
        self.assertTrue(row.possible_duplicate)
        self.assertTrue(row.dedup_assumed)


if __name__ == "__main__":
    unittest.main()
