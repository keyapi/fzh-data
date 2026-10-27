"""Synthetic receipt timing; never reads production or business fixtures."""
from datetime import datetime, timezone
from decimal import Decimal
import unittest

from supply_chain_visibility.receipt_buckets import bucket_receipts


def t(day):
    return datetime(2026, 10, day, tzinfo=timezone.utc)


def event(key="a", **changes):
    row = dict(event_id=key, sku="S", warehouse="W", uom="个", qty="10",
               available_at=t(28), date_confidence="confirmed", b_min_eligible=True,
               scope="in_house", allocation_status="free")
    return dict(row, **changes)


class ReceiptBucketsTests(unittest.TestCase):
    def calc(self, rows, buckets=None):
        return bucket_receipts(rows, target=("S", "W", "个"), as_of=t(27),
                               buckets=buckets or [("early", t(27), t(29)),
                                                   ("late", t(29), t(31))])

    def test_boundary_only_enters_later_bucket(self):
        got = self.calc([event(available_at=t(29))])
        self.assertEqual(got["receipts"], {"early": Decimal(0), "late": Decimal(10)})

    def test_future_receipt_does_not_remove_earlier_shortage(self):
        got = self.calc([event(available_at=t(30))])
        self.assertEqual(max(Decimal(0), Decimal(8)-got["receipts"]["early"]), 8)

    def test_each_input_has_one_destination_and_units_do_not_mix(self):
        rows = [event(), event("wh", warehouse="OTHER"), event("unit", uom="套"),
                event("past", available_at=t(26)), event("future", available_at=t(31)),
                event("fba", scope="external_fba"), event("allocated", allocation_status="fba"),
                event("unknown", available_at=None), event("proof", b_min_eligible=None)]
        got = self.calc(rows)
        self.assertEqual(len(got["dispositions"]), len(rows))
        self.assertEqual(got["receipts"]["early"], 10)
        self.assertEqual(got["counts"], dict(counted=1, target_mismatch=2, pre_asof_inclusion_unproven=1,
                                          after_horizon=1, fba_allocated=2, date_unproven=1,
                                          eligibility_unproven=1))
        self.assertEqual(got["quantity_ledger"][("S", "W", "个")]["input_known"], 70)
        self.assertTrue(got["has_unresolved"])

    def test_unknown_and_invalid_quantities_are_not_zero(self):
        rows = [event(str(i), qty=q) for i, q in enumerate([None, "NaN", "Infinity", -1, True])]
        got = self.calc(rows)
        self.assertEqual(got["counts"], {"quantity_unproven": 5})
        self.assertTrue(all(r["qty"] is None for r in got["dispositions"]))
        self.assertEqual(got["receipts"]["early"], 0)
        self.assertTrue(got["has_unresolved"])

    def test_gaps_and_ambiguous_date_remain_unresolved(self):
        got = self.calc([event(available_at=t(28)), event("date", available_at="2026-10-28")],
                        [("early", t(27), t(28)), ("late", t(29), t(31))])
        self.assertEqual(got["counts"], {"outside_buckets": 1, "date_unproven": 1})
        self.assertTrue(got["has_unresolved"])

    def test_unknown_identity_allocation_and_opening_stock(self):
        got = self.calc([event("unit", uom=None), event("allocation", allocation_status=None),
                         event("stock", source_layer="inventory_snapshot")])
        self.assertEqual(got["counts"], dict(identity_unproven=1, allocation_unproven=1,
                                             opening_stock=1))
        self.assertTrue(got["has_unresolved"])
        self.assertEqual(got["counted_rows"], 0)

    def test_canonical_available_date_and_timezone_equivalence(self):
        row = event()
        del row["available_at"]
        row["available_date"] = "2026-10-29T08:00:00+08:00"
        got = self.calc([row])
        self.assertEqual(got["receipts"]["late"], 10)

    def test_pre_asof_non_snapshot_without_inclusion_proof_is_unresolved(self):
        got = self.calc([event(available_at=t(26))])
        self.assertEqual(got["counts"], {"pre_asof_inclusion_unproven": 1})
        self.assertTrue(got["has_unresolved"])
        self.assertEqual(got["counted_rows"], 0)

    def test_pre_asof_with_explicit_opening_inclusion_proof_is_excluded(self):
        got = self.calc([event(available_at=t(26), included_in_opening_snapshot=True)])
        self.assertEqual(got["counts"], {"at_or_before_as_of": 1})
        self.assertFalse(got["has_unresolved"])
        self.assertEqual(got["counted_rows"], 0)

    def test_inventory_snapshot_is_excluded_without_requiring_extra_proof(self):
        got = self.calc([event(available_at=t(26), source_layer="inventory_snapshot")])
        self.assertEqual(got["counts"], {"opening_stock": 1})
        self.assertFalse(got["has_unresolved"])
        self.assertEqual(got["counted_rows"], 0)

    def test_overlap_duplicate_ids_and_naive_boundaries_rejected(self):
        with self.assertRaises(ValueError):
            self.calc([event(), event()])
        with self.assertRaises(ValueError):
            self.calc([], [("a", t(27), t(30)), ("b", t(29), t(31))])
        with self.assertRaises(ValueError):
            self.calc([], [("a", datetime(2026, 10, 27), t(31))])


if __name__ == "__main__":
    unittest.main()
