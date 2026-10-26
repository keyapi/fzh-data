from decimal import Decimal
import unittest

from supply_chain_visibility.overlap_gates import apply_overlap_gates, summarize_overlap
from supply_chain_visibility.supply_row import SupplyRow


def row(**changes):
    values = {
        "sku": "S1", "warehouse": "WH-A", "stage": "po_open",
        "source_layer": "po_open", "qty": Decimal("10"), "qty_status": "known",
        "uom": "Nos", "uom_proven": True, "event_date": "2026-10-14",
        "available_date": "2026-10-14", "date_confidence": "estimated",
        "timezone_status": "verified", "identity_confidence": "proven",
        "b_min_eligible": True, "b_max_eligible": True,
    }
    values.update(changes)
    return SupplyRow(**values)


class OverlapGateTests(unittest.TestCase):
    def test_same_batch_keeps_transit_in_bmin_and_both_in_bmax(self):
        rows = apply_overlap_gates([
            row(),
            row(source_layer="in_transit", stage="shipped_in_transit"),
        ])
        po = [r for r in rows if r.source_layer == "po_open"][0]
        transit = [r for r in rows if r.source_layer == "in_transit"][0]
        self.assertEqual(po.overlap_status, "same_batch_suspected")
        self.assertEqual(transit.overlap_status, "same_batch_suspected")
        self.assertFalse(po.b_min_eligible)
        self.assertEqual(po.exclusion_reason, "po_not_counted")
        self.assertTrue(transit.b_min_eligible)
        self.assertTrue(po.b_max_eligible)
        self.assertTrue(transit.b_max_eligible)

    def test_unequal_po_and_transit_are_distinct(self):
        rows = apply_overlap_gates([
            row(qty=Decimal("10")),
            row(qty=Decimal("7"), source_layer="in_transit", stage="shipped_in_transit"),
        ])
        self.assertEqual({r.overlap_status for r in rows}, {"distinct"})
        self.assertTrue(all(r.b_min_eligible for r in rows))

    def test_dn_trace_and_external_fba_are_excluded(self):
        rows = apply_overlap_gates([
            row(source_layer="dn_trace", stage="shipped_in_transit"),
            row(source_layer="in_transit", stage="shipped_in_transit", scope="external_fba"),
        ])
        by_layer = {r.source_layer: r for r in rows}
        self.assertEqual(by_layer["dn_trace"].exclusion_reason, "trace_only")
        self.assertFalse(by_layer["dn_trace"].b_min_eligible)
        self.assertFalse(by_layer["dn_trace"].b_max_eligible)
        self.assertEqual(by_layer["in_transit"].exclusion_reason, "external_fba")
        self.assertFalse(by_layer["in_transit"].b_min_eligible)
        self.assertFalse(by_layer["in_transit"].b_max_eligible)

    def test_unknown_uom_and_cover_block_bmin_only(self):
        rows = apply_overlap_gates([
            row(uom=None, uom_proven=False),
            row(sku="S2", role="cover"),
        ])
        unknown_uom = [r for r in rows if r.sku == "S1"][0]
        cover = [r for r in rows if r.sku == "S2"][0]
        self.assertFalse(unknown_uom.b_min_eligible)
        self.assertEqual(unknown_uom.exclusion_reason, "uom_unproven")
        self.assertTrue(unknown_uom.b_max_eligible)
        self.assertFalse(cover.b_min_eligible)
        self.assertEqual(cover.exclusion_reason, "cover_conversion_unproven")
        self.assertTrue(cover.b_max_eligible)

    def test_unknown_qty_and_unmapped_are_excluded_from_both(self):
        rows = apply_overlap_gates([
            row(qty=None, qty_status="unknown"),
            row(sku="S2", warehouse_confidence="unmapped"),
        ])
        by_sku = {r.sku: r for r in rows}
        self.assertEqual(by_sku["S1"].exclusion_reason, "qty_unknown")
        self.assertFalse(by_sku["S1"].b_min_eligible)
        self.assertFalse(by_sku["S1"].b_max_eligible)
        self.assertEqual(by_sku["S2"].exclusion_reason, "unmapped")
        self.assertFalse(by_sku["S2"].b_max_eligible)

    def test_summary_counts_statuses_and_exclusions(self):
        rows = apply_overlap_gates([
            row(),
            row(source_layer="in_transit", stage="shipped_in_transit"),
            row(sku="S2", source_layer="dn_trace", stage="shipped_in_transit"),
        ])
        summary = summarize_overlap(rows)
        self.assertEqual(summary["rows"], 3)
        self.assertEqual(summary["by_overlap_status"], {"same_batch_suspected": 2})
        self.assertEqual(summary["exclusions"], {"po_not_counted": 1, "trace_only": 1})


if __name__ == "__main__":
    unittest.main()
