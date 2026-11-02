"""Read-only collection validation and adapters (no network in tests)."""
import unittest

from supply_chain_visibility.en_collect import (
    CollectionError,
    build_mappings,
    build_production,
    build_receipts,
    build_so_balances,
    build_transit,
    merge_delivery,
    merge_supply,
    validate_delivery_batches,
    validate_supply_batches,
)

AS_OF = "2026-11-02T00:00:00+00:00"
B_ROWS = [{
    "item_code": "ITEM-1", "uom": "PCS", "warehouse": "WH-1",
    "branch": "B1", "purpose": "branch", "tt_sku": "TT-1",
    "market": "US", "product_form": "finished",
}]


def batch(*, lines=None, offset=0, total=1, exhausted=True, next_offset=None,
          observed_at=AS_OF, schema="supply-facts/v3", rule="r3",
          implementation="impl3", snapshot_id="SNAP-1", **manifest_extra):
    lines = lines if lines is not None else [{"so": "SO-1", "so_line": "L1"}]
    coverage = {"observed_at": observed_at, "source_status": {
        "sales_order": {"available": True, "restricted": False, "reason": ""},
        "tongtool_po": {"available": False, "restricted": False,
                        "reason": "not_integrated"},
    }}
    coverage.update(manifest_extra.pop("coverage", {}))
    return {
        "schema_version": schema, "rule_version": rule,
        "implementation_version": implementation, "as_of": "2026-11-02",
        "snapshot_id": snapshot_id,
        "lines": lines,
        "pagination": {"limit": len(lines), "offset": offset,
                       "returned": len(lines), "total": total,
                       "next_offset": next_offset, "exhausted": exhausted},
        "manifest": {"coverage": coverage, "truncated": False,
                     "partial_reasons": []},
    }


class CollectionValidationTests(unittest.TestCase):
    def test_accepts_exhausted_and_not_integrated_as_business_unknown(self):
        signature, unknown = validate_supply_batches([batch()], "exhausted")
        self.assertEqual(signature["as_of"], "2026-11-02")
        self.assertEqual(unknown, [{"source": "tongtool_po",
                                    "status": "not_integrated"}])

    def test_rejects_page_limit(self):
        with self.assertRaises(CollectionError):
            validate_supply_batches([batch(exhausted=False)], "page_limit")

    def test_rejects_version_drift(self):
        first = batch(total=2, exhausted=False, next_offset=1)
        second = batch(lines=[{"so": "SO-1", "so_line": "L2"}], offset=1,
                       total=2, rule="r4")
        with self.assertRaises(CollectionError) as ctx:
            validate_supply_batches([first, second], "exhausted")
        self.assertIn("drift", str(ctx.exception))

    def test_accepts_observed_at_drift_when_snapshot_is_stable(self):
        first = batch(total=2, exhausted=False, next_offset=1)
        second = batch(lines=[{"so": "SO-1", "so_line": "L2"}], offset=1,
                       total=2, observed_at="2026-11-03T00:00:00+00:00",
                       exhausted=True)
        signature, _ = validate_supply_batches([first, second], "exhausted")
        self.assertEqual(signature["snapshot_id"], "SNAP-1")

    def test_rejects_pagination_gap_and_total_drift(self):
        first = batch(total=2, exhausted=False, next_offset=2)
        second = batch(lines=[{"so": "SO-1", "so_line": "L2"}], offset=1,
                       total=3, exhausted=True)
        with self.assertRaises(CollectionError):
            validate_supply_batches([first, second], "exhausted")

    def test_rejects_permission_or_query_error(self):
        payload = batch(coverage={"source_status": {
            "job_card": {"available": False, "restricted": False,
                         "reason": "query_error"}}})
        with self.assertRaises(CollectionError) as ctx:
            validate_supply_batches([payload], "exhausted")
        self.assertIn("job_card", str(ctx.exception))

    def test_rejects_restricted_true(self):
        payload = batch(coverage={"restricted": {"delivery_note": True}})
        with self.assertRaises(CollectionError):
            validate_supply_batches([payload], "exhausted")

    def test_rejects_duplicate_line_across_pages(self):
        first = batch(lines=[{"so": "SO-1", "so_line": "L1"}], total=2)
        second = batch(lines=[{"so": "SO-1", "so_line": "L1"}], offset=1,
                       total=2)
        with self.assertRaises(CollectionError):
            validate_supply_batches([first, second], "exhausted")

    def test_rejects_exhausted_with_missing_rows(self):
        with self.assertRaises(CollectionError):
            validate_supply_batches([batch(total=2)], "exhausted")

    def test_delivery_rejects_snapshot_drift(self):
        first = {"schema_version": "v3", "rule_version": "r",
                 "implementation_version": "i", "snapshot_id": "S1",
                 "coverage": {"as_of": AS_OF}, "delivery_lines": [],
                 "pagination": {"exhausted": True, "total": 0}}
        second = dict(first, snapshot_id="S2")
        with self.assertRaises(CollectionError):
            validate_delivery_batches([first, second], "exhausted")


class AdapterTests(unittest.TestCase):
    def _supply(self, **over):
        supply = {
            "lines": [{"so": "SO-1", "so_line": "L1", "item_code": "ITEM-1",
                       "uom": "PCS", "warehouse": "WH-1", "qty": 10}],
            "stage_balances": [{"so_line_id": "L1", "stage": "delivered_sellable",
                                "qty": 4}],
            "production_evidence": [], "shipment_progress": [],
            "observed_at": AS_OF, "as_of": "2026-11-02",
        }
        supply.update(over)
        return supply

    def test_so_demand_subtracts_fulfilled_actuals(self):
        rows = build_so_balances(self._supply(), B_ROWS)
        self.assertEqual(len(rows), 1)
        self.assertEqual(rows[0]["so_open_qty"], 6)
        self.assertEqual(rows[0]["tt_sku"], "TT-1")
        self.assertEqual(rows[0]["branch"], "B1")

    def test_so_demand_unknown_when_fulfilled_qty_unknown(self):
        supply = self._supply(stage_balances=[
            {"so_line_id": "L1", "stage": "shipped_in_transit", "qty": None}])
        row = build_so_balances(supply, B_ROWS)[0]
        self.assertIsNone(row["so_open_qty"])
        self.assertEqual(row["source_status"], "unknown")

    def test_production_takes_proven_primary_not_subassembly(self):
        supply = self._supply(production_evidence=[{
            "so": "SO-1", "so_line": "L1", "line_item_code": "ITEM-1",
            "work_orders": [
                {"wo": "WO-1", "production_item": "ITEM-1",
                 "all_process_done": {"qty_proven": 7, "confidence": "proven",
                                      "completed_at": AS_OF,
                                      "observed_at": AS_OF}},
                {"wo": "WO-2", "production_item": "SUB-1",
                 "all_process_done": {"qty_proven": 9, "confidence": "proven"}},
                {"wo": "WO-3", "production_item": "ITEM-1",
                 "wo_cancelled": True,
                 "all_process_done": {"qty_proven": 5,
                                      "confidence": "proven"}},
            ]}])
        rows = build_production(supply, B_ROWS)
        self.assertEqual([row["work_order"] for row in rows], ["WO-1"])
        self.assertEqual(rows[0]["qty"], 7)
        self.assertEqual(rows[0]["evidence_status"], "proven")

    def test_first_process_only_is_not_supply(self):
        supply = self._supply(production_evidence=[{
            "so": "SO-1", "so_line": "L1", "line_item_code": "ITEM-1",
            "work_orders": [{
                "wo": "WO-1", "production_item": "ITEM-1",
                "first_process_done": {"qty_proven": 10,
                                       "confidence": "proven"},
                "all_process_done": {"qty_proven": None,
                                     "confidence": "unknown"},
            }]}])
        self.assertEqual(build_production(supply, B_ROWS), [])

    def test_transit_and_receipt_adapters_keep_unknown(self):
        supply = self._supply(stage_balances=[
            {"so_line_id": "L1", "stage": "shipped_in_transit", "qty": 3,
             "qty_status": "known", "item_code": "ITEM-1", "uom": "PCS",
             "warehouse": "WH-1", "batch_key": "DN-1", "source_record": "DN-1"},
            {"so_line_id": "L1", "stage": "signed_pending_tongtool_receipt",
             "qty": 2, "qty_status": "known", "item_code": "ITEM-1",
             "uom": "PCS", "warehouse": "WH-1", "batch_key": "DN-2",
             "source_record": "DN-2"},
        ], shipment_progress=[
            {"stage": "shipped_in_transit", "item_code": "ITEM-1",
             "uom": "PCS", "warehouse": "WH-1", "shipment": "SHIP-1",
             "dn": "DN-1", "logistic_number": "TRK-1", "eta": AS_OF,
             "latest_progress_at": AS_OF},
            {"stage": "signed_pending_tongtool_receipt",
             "item_code": "ITEM-1", "uom": "PCS", "warehouse": "WH-1",
             "shipment": "SHIP-2", "dn": "DN-2", "received_qty": 2,
             "shipment_signed_at": AS_OF, "signed_status_proven": False,
             "latest_progress_at": AS_OF},
        ])
        transit = build_transit(supply, B_ROWS)
        self.assertEqual(transit[0]["qty"], 3)
        receipts = build_receipts(supply, B_ROWS)
        self.assertEqual(receipts[0]["qty"], 2)
        self.assertIsNone(receipts[0]["signed_at"])

    def test_mapping_requires_unique_b_identity(self):
        lines = [{"delivery_note": "DN-1", "delivery_note_item": "D1",
                  "item_code": "ITEM-1", "uom": "PCS",
                  "target_warehouse": "WH-1"}]
        mappings = build_mappings(lines, B_ROWS)
        self.assertEqual(len(mappings), 1)
        self.assertEqual(mappings[0]["tt_sku"], "TT-1")
        ambiguous = build_mappings(lines, B_ROWS + B_ROWS)
        self.assertEqual(ambiguous, [])

    def test_merge_supply_recomputes_identity_totals(self):
        merged = merge_supply([batch(lines=[{"so": "SO-1", "so_line": "L1"}])])
        self.assertEqual(merged["coverage"]["so_lines"], 1)
        self.assertEqual(merged["coverage"]["sales_orders"], 1)

    def test_merge_delivery_synthesizes_exhausted_pagination(self):
        first = {"delivery_lines": [{"delivery_note_item": "D1"}],
                 "schema_version": "v3", "rule_version": "r",
                 "implementation_version": "i", "snapshot_id": "S1",
                 "scope": {}, "coverage": {"as_of": AS_OF},
                 "pagination": {"limit": 500, "offset": 0, "returned": 1,
                                "total": 1, "next_offset": None,
                                "exhausted": True}}
        merged = merge_delivery([first])
        self.assertTrue(merged["pagination"]["exhausted"])
        self.assertEqual(merged["pagination"]["total"], 1)


if __name__ == "__main__":
    unittest.main()
