"""D-independent A/B/C readiness: preserve keys, evidence and unknown stock."""
import unittest
import importlib.util
import tempfile

from supply_chain_visibility.preforecast_readiness import assess_readiness, publish_readiness


def inputs():
    return ([{"item_code": "I", "active": True, "role": "成品"}],
            [{"item_code": "I", "pool": "美东USNJ", "uom": "个", "demand_row": True,
              "netting_gate": "否", "blockers": "仍需库存/在途/交期证据"}],
            [{"item_code": "I", "pool": "美东USNJ", "uom": "个", "qty": 0,
              "join_class": "join_full", "demand_eligibility": "independent",
              "source_ref": "ST:1", "as_of": "2026-10-28"}])


class ReadinessTests(unittest.TestCase):
    def run_case(self, data):
        return assess_readiness(*data, as_of="2026-11-02", max_stock_age_days=1)

    def test_zero_is_valid_but_stale_stock_cannot_be_current(self):
        result = self.run_case(inputs())
        row = result["rows"][0]
        self.assertTrue(row["abc_contract_compatible"])
        self.assertEqual(row["inventory_qty"], 0)
        self.assertTrue(row["inventory_refresh_needed"])
        self.assertFalse(row["current_abc_ready"])
        self.assertFalse(row["netting_ready"])
        self.assertIn("b_existing_netting_gate_closed", row["reasons"])

    def test_stock_on_other_side_is_not_reassigned(self):
        a, b, c = inputs()
        c[0]["pool"] = "美中USTX"
        result = self.run_case((a, b, c))
        self.assertEqual(len(result["rows"]), 2)
        east = next(r for r in result["rows"] if r["pool"] == "美东USNJ")
        west = next(r for r in result["rows"] if r["pool"] == "美中USTX")
        self.assertIsNone(east["inventory_qty"])
        self.assertFalse(west["b_attribution_available"])
        self.assertFalse(any(r["abc_contract_compatible"] for r in result["rows"]))

    def test_partial_missing_and_no_proof_never_fill_zero(self):
        for change in ("no_stock", "partial", "missing_proof", "unknown_qty"):
            a, b, c = inputs()
            if change == "no_stock":
                c = []
            elif change == "partial":
                c[0]["join_class"] = "join_partial"
            elif change == "missing_proof":
                c[0]["source_ref"] = None
            else:
                c[0]["qty"] = None
            row = self.run_case((a, b, c))["rows"][0]
            self.assertFalse(row["abc_contract_compatible"])
            self.assertIsNone(row["inventory_qty"])

    def test_b_duplicates_are_evidence_not_duplicate_stock(self):
        a, b, c = inputs()
        b *= 3
        result = self.run_case((a, b, c))
        self.assertEqual(len(result["rows"]), 1)
        self.assertEqual(result["rows"][0]["b_evidence_rows"], 3)
        self.assertEqual(result["rows"][0]["inventory_qty"], 0)

    def test_components_and_no_pool_active_goods_are_retained(self):
        a, b, c = inputs()
        a.append({"item_code": "ND#I", "active": True, "role": "内胆"})
        c[0]["demand_eligibility"] = "component"
        result = self.run_case((a, b, c))
        self.assertEqual(len(result["rows"]), 2)
        self.assertFalse(any(r["independent_demand_candidate"] for r in result["rows"]))
        self.assertTrue(any(r["pool"] is None for r in result["rows"]))

    def test_duplicate_stock_and_conflicting_a_identity_are_rejected(self):
        a, b, c = inputs()
        with self.assertRaises(ValueError):
            self.run_case((a, b, c * 2))
        with self.assertRaises(ValueError):
            self.run_case((a + [dict(a[0], active=False)], b, c))

    def test_unit_conflict_and_inactive_item_do_not_pass(self):
        a, b, c = inputs()
        b[0]["uom"] = "套"
        row = self.run_case((a, b, c))["rows"][0]
        self.assertFalse(row["abc_contract_compatible"])
        self.assertIn("b_c_uom_missing_or_mismatch", row["reasons"])
        a[0]["active"] = False
        self.assertFalse(self.run_case((a, b, c))["rows"][0]["a_active"])

    def test_corrupt_source_time_is_not_accepted_by_date_prefix(self):
        for value in ("2026-11-02corrupt", "2026-11-02T99:99:00", "2026-02-30"):
            a, b, c = inputs()
            c[0]["as_of"] = value
            row = self.run_case((a, b, c))["rows"][0]
            self.assertTrue(row["inventory_refresh_needed"])
            self.assertIsNone(row["inventory_age_days"])
            self.assertFalse(row["current_abc_ready"])

    def test_complete_iso_timestamp_can_supply_day_level_freshness(self):
        a, b, c = inputs()
        c[0]["as_of"] = "2026-11-02T08:00:00+08:00"
        row = self.run_case((a, b, c))["rows"][0]
        self.assertEqual(row["inventory_age_days"], 0)
        self.assertFalse(row["inventory_refresh_needed"])

    @unittest.skipUnless(importlib.util.find_spec("pyarrow"), "requires pyarrow")
    def test_empty_result_keeps_schema_and_zero_is_preserved(self):
        import pyarrow.parquet as pq
        with tempfile.TemporaryDirectory() as tmp:
            empty = self.run_case(([], [], []))
            root = publish_readiness(empty, tmp)
            table = pq.read_table(root / "preforecast_readiness.parquet")
            self.assertEqual(table.num_rows, 0)
            self.assertIn("inventory_qty", table.column_names)
            root = publish_readiness(self.run_case(inputs()), tmp)
            self.assertEqual(pq.read_table(root / "preforecast_readiness.parquet")["inventory_qty"][0].as_py(), 0)


if __name__ == "__main__":
    unittest.main()
