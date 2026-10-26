from datetime import date
import unittest

from supply_chain_visibility.receipt_coverage import (
    build_coverage_report,
    events_from_collection,
)
from tongtool_api.receipt_collector import (
    CollectedRow,
    CollectionResult,
    CollectionWindow,
)


def make_result() -> CollectionResult:
    window = CollectionWindow(date(2026, 10, 1), date(2026, 10, 7))
    rows = (
        CollectedRow(0, window, {
            "purchaseOrderCode": "PO1", "sku": "S1", "warehouseName": "WH-A",
            "warehousingDate": "2026-10-01 08:00:00", "warehousingNum": 2,
        }, ("k1",), False, False),
        CollectedRow(1, window, {
            "purchaseOrderCode": "PO1", "sku": "S2", "warehouseName": "WH-A",
            "warehousingDate": "2026-10-02 09:00:00", "warehousingNum": 3,
        }, ("k2",), False, True),
        CollectedRow(2, window, {
            "purchaseOrderCode": "PO2", "sku": "S1", "warehouseName": "WH-A",
            "warehousingDate": "2026-10-02 10:00:00", "warehousingNum": 4,
        }, ("k3",), True, False),
    )
    return CollectionResult(
        rows=rows, windows=(window,), input_count=3, unique_count=2,
        overlap_duplicate_count=1, possible_duplicate_count=1,
        truncated_windows=(), cache_hits=0,
    )


class ReceiptCoverageTests(unittest.TestCase):
    def test_overlap_rows_are_not_mapped_again(self):
        events = events_from_collection(make_result())
        self.assertEqual(len(events), 2)
        self.assertIsNone(events[0].receipt_id)
        self.assertIsNone(events[0].line_id)
        self.assertIsNone(events[0].uom)
        self.assertEqual(events[0].weak_event_key, ("k1",))
        self.assertTrue(events[1].possible_duplicate)

    def test_report_is_aggregate_only_and_keeps_gaps_visible(self):
        report = build_coverage_report(make_result())
        self.assertEqual(report["collection"]["input_count"], 3)
        self.assertEqual(report["collection"]["unique_count"], 2)
        self.assertEqual(report["reconciliation"]["unknown_count"], 2)
        self.assertEqual(report["reconciliation"]["dispositions"], {"unknown": 2})
        self.assertEqual(report["reconciliation"]["unknown_reasons"], {"missing_stable_id": 2})
        self.assertEqual(report["coverage"]["distinct_po"], 1)
        self.assertEqual(report["coverage"]["distinct_sku"], 2)
        self.assertEqual(report["coverage"]["rows_without_stable_id"], 2)
        self.assertEqual(report["coverage"]["rows_without_uom"], 2)
        self.assertEqual(report["coverage"]["rows_with_naive_time"], 2)
        self.assertEqual(report["coverage"]["day_counts"],
                         {"2026-10-01": 1, "2026-10-02": 1})
        self.assertNotIn("quantities", report)


if __name__ == "__main__":
    unittest.main()
