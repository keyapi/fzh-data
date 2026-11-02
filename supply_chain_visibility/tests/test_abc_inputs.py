"""Frozen A/B/C attribution: strict identity, stale/zero, CG pools, versions."""
import importlib.util
import tempfile
import unittest
from pathlib import Path

from supply_chain_visibility.abc_inputs import attribute_readiness, load_frozen_abc


def base(**over):
    row = {
        "item_code": "I", "pool": "美东USNJ", "canonical_uom": "个",
        "a_active": True, "a_role": "成品",
        "b_attribution_available": True, "b_evidence_rows": 1,
        "b_warehouse": "WH", "b_branch": "B1", "b_purpose": "branch",
        "b_tt_sku": "S1", "b_identity_conflict": False,
        "b_units": ["个"],
        "b_target_identities": [{"warehouse": "WH", "branch": "B1",
                                 "purpose": "branch", "tt_sku": "S1"}],
        "c_join_class": "join_full", "c_source_ref": "ST:1",
        "inventory_qty_raw": 10, "inventory_observed_qty": 10,
        "inventory_as_of": "2026-11-02",
        "inventory_as_of_raw": "2026-11-02T08:00:00+08:00",
        "inventory_age_days": 0, "inventory_refresh_needed": False,
        "reasons": [],
    }
    row.update(over)
    return row


def attribute(rows, max_stock_age_days=1):
    return attribute_readiness(
        {"rows": rows}, as_of="2026-11-02",
        max_stock_age_days=max_stock_age_days,
        as_of_time="2026-11-02T00:00:00+00:00")


class AttributionTests(unittest.TestCase):
    def test_a_item_without_b_is_still_listed_unknown(self):
        row = base(b_attribution_available=False, b_warehouse=None,
                   b_branch=None, b_purpose=None, b_tt_sku=None,
                   b_target_identities=[], c_join_class=None,
                   c_source_ref=None, inventory_qty_raw=None,
                   inventory_observed_qty=None, inventory_as_of=None,
                   inventory_as_of_raw=None, inventory_age_days=None,
                   reasons=["a_missing_or_inactive"])
        result = attribute([row])
        self.assertEqual(result["approved_items"], ["I"])
        out = result["rows"][0]
        self.assertIsNone(out["inventory_qty"])
        self.assertEqual(out["attribution_status"], "unattributed")
        self.assertEqual(out["coverage"], "abc_approved_without_identity")
        self.assertIn("b_missing_same_product_pool", out["reasons"])

    def test_a_plus_b_without_c_keeps_inventory_unknown(self):
        row = base(c_join_class=None, c_source_ref=None,
                   inventory_qty_raw=None, inventory_observed_qty=None,
                   inventory_as_of=None, inventory_as_of_raw=None,
                   inventory_age_days=None)
        out = attribute([row])["rows"][0]
        self.assertIsNone(out["inventory_qty"])
        self.assertIsNone(out["inventory_observed_qty"])
        self.assertEqual(out["attribution_status"], "partial_identity")
        self.assertIn("c_uncovered_not_zero", out["reasons"])

    def test_c_without_b_keeps_observed_but_does_not_guess(self):
        row = base(b_attribution_available=False, b_warehouse=None,
                   b_branch=None, b_purpose=None, b_tt_sku=None,
                   b_target_identities=[], inventory_qty_raw=7,
                   inventory_observed_qty=7)
        out = attribute([row])["rows"][0]
        self.assertEqual(out["inventory_observed_qty"], "7")
        self.assertIsNone(out["inventory_qty"])
        self.assertEqual(out["attribution_status"], "unattributed")
        self.assertIn("c_without_b_attribution", out["reasons"])

    def test_true_zero_is_preserved_not_null(self):
        row = base(inventory_qty_raw=0, inventory_observed_qty=0)
        out = attribute([row])["rows"][0]
        self.assertEqual(out["inventory_qty"], "0")
        self.assertEqual(out["inventory_observed_qty"], "0")
        self.assertEqual(out["inventory_current_available_qty"], "0")

    def test_stale_inventory_keeps_observation_but_not_current(self):
        row = base(inventory_qty_raw=5, inventory_observed_qty=5,
                   inventory_as_of="2026-10-28",
                   inventory_as_of_raw="2026-10-28", inventory_age_days=5,
                   inventory_refresh_needed=True)
        out = attribute([row])["rows"][0]
        self.assertEqual(out["inventory_qty"], "5")
        self.assertEqual(out["inventory_freshness"], "stale")
        self.assertIsNone(out["inventory_current_available_qty"])
        self.assertIn("inventory_stale", out["reasons"])
        self.assertEqual(out["inventory_time_status"], "date_only")

    def test_version_conflict_blocks_trust(self):
        row = base(reasons=["c_declared_b_version_mismatch"])
        out = attribute([row])["rows"][0]
        self.assertEqual(out["attribution_status"], "version_conflict")
        self.assertIsNone(out["inventory_qty"])
        self.assertEqual(out["inventory_observed_qty"], "10")
        self.assertFalse(out["inventory_trusted"])

    def test_cg_pool_is_not_copied_into_each_branch(self):
        row = base(b_identity_conflict=False, b_warehouse=None,
                   b_branch=None, b_purpose=None, b_tt_sku=None,
                   b_target_identities=[
                       {"warehouse": "WH", "branch": "B1",
                        "purpose": "branch", "tt_sku": "S1"},
                       {"warehouse": "WH", "branch": "B2",
                        "purpose": "branch", "tt_sku": "S2"}])
        rows = attribute([row])["rows"]
        self.assertEqual(len(rows), 3)
        identities = [r for r in rows if r["coverage"] == "abc_cg_pool_identity"]
        pooled = [r for r in rows if r["coverage"] == "abc_cg_pool_unattributed"]
        self.assertEqual(len(identities), 2)
        self.assertEqual(len(pooled), 1)
        self.assertTrue(all(r["inventory_qty"] is None for r in identities))
        self.assertTrue(all(r["inventory_observed_qty"] is None for r in identities))
        self.assertEqual(pooled[0]["inventory_observed_qty"], "10")
        self.assertIsNone(pooled[0]["inventory_qty"])
        self.assertIn("cg_pool_shared_by_multiple_attributions",
                      pooled[0]["reasons"])

    def test_b_identity_conflict_does_not_attribute(self):
        row = base(b_identity_conflict=True,
                   reasons=["b_identity_conflict"])
        rows = attribute([row])["rows"]
        pooled = next(r for r in rows
                      if r["coverage"] == "abc_conflict_unattributed")
        self.assertEqual(pooled["attribution_status"], "b_identity_conflict")
        self.assertIsNone(pooled["inventory_qty"])
        self.assertIsNone(pooled["inventory_current_available_qty"])
        self.assertEqual(pooled["inventory_observed_qty"], "10")

    def test_each_dimension_is_a_separate_key(self):
        rows = [
            base(),
            base(canonical_uom="套"),
            base(b_branch="B2", b_target_identities=[
                {"warehouse": "WH", "branch": "B2",
                 "purpose": "branch", "tt_sku": "S1"}]),
            base(b_purpose="fba", b_branch=None, b_target_identities=[
                {"warehouse": "WH", "branch": None,
                 "purpose": "fba", "tt_sku": "S1"}]),
            base(b_tt_sku="S2", b_target_identities=[
                {"warehouse": "WH", "branch": "B1",
                 "purpose": "branch", "tt_sku": "S2"}]),
        ]
        out = attribute(rows)["rows"]
        keys = {(r["item_code"], r["uom"], r["warehouse"], r["purpose"],
                 r["tt_sku"], r["branch"]) for r in out}
        self.assertEqual(len(keys), 5)
        self.assertEqual(len(out), 5)

    def test_duplicate_target_key_with_different_payload_is_rejected(self):
        with self.assertRaises(ValueError) as ctx:
            attribute([base(inventory_qty_raw=5), base(inventory_qty_raw=6)])
        self.assertIn("duplicate_target_key", str(ctx.exception))

    def test_unit_mismatch_keeps_observation_but_not_attribution(self):
        row = base(canonical_uom="EA", b_units=["BOX"],
                   reasons=["b_c_uom_missing_or_mismatch"])
        out = attribute([row])["rows"][0]
        self.assertEqual(out["attribution_status"], "uom_mismatch")
        self.assertEqual(out["inventory_observed_qty"], "10")
        self.assertEqual(out["inventory_observed_uom"], "EA")
        self.assertEqual(out["b_units"], ["BOX"])
        self.assertIsNone(out["inventory_qty"])
        self.assertIsNone(out["inventory_current_available_qty"])
        self.assertIn("uom_mismatch", out["reasons"])

    def test_naive_time_is_not_current_available(self):
        row = base(inventory_as_of_raw="2026-11-02T23:59:00",
                   inventory_as_of=None, inventory_age_days=0)
        out = attribute([row])["rows"][0]
        self.assertEqual(out["inventory_time_status"], "naive")
        self.assertFalse(out["inventory_time_proven"])
        self.assertEqual(out["inventory_freshness"], "unknown_time")
        self.assertIsNone(out["inventory_current_available_qty"])
        self.assertIn("inventory_time_unknown", out["reasons"])

    def test_same_day_future_is_future_and_not_current(self):
        row = base(inventory_as_of_raw="2026-11-02T23:59:00+00:00",
                   inventory_as_of="2026-11-02T23:59:00+00:00",
                   inventory_age_days=0)
        out = attribute([row])["rows"][0]
        self.assertEqual(out["inventory_freshness"], "future")
        self.assertTrue(out["inventory_time_proven"])
        self.assertIsNone(out["inventory_current_available_qty"])

    def test_inactive_a_is_not_attributed(self):
        row = base(a_active=False, reasons=["a_missing_or_inactive"])
        out = attribute([row])["rows"][0]
        self.assertEqual(out["attribution_status"], "a_inactive")
        self.assertEqual(out["inventory_observed_qty"], "10")
        self.assertIsNone(out["inventory_qty"])
        self.assertIsNone(out["inventory_current_available_qty"])

    def test_multiple_b_units_keep_each_destination(self):
        row = base(canonical_uom="EA", b_units=["BOX", "EA"])
        rows = attribute([row])["rows"]
        self.assertEqual(len(rows), 2)
        self.assertEqual(sorted(r["uom"] for r in rows), ["BOX", "EA"])
        self.assertTrue(all(r["inventory_qty"] is None for r in rows))
        self.assertTrue(all(r["attribution_status"] == "b_multi_uom_ambiguous"
                            for r in rows))
        observed = [r for r in rows if r["inventory_observed_qty"] is not None]
        self.assertEqual(len(observed), 1)
        self.assertEqual(observed[0]["uom"], "EA")
        self.assertEqual(observed[0]["inventory_observed_qty"], "10")
        self.assertEqual(observed[0]["inventory_observed_uom"], "EA")

    def test_current_available_and_order_eligibility_are_separate(self):
        row = base(reasons=["b_existing_netting_gate_closed"])
        out = attribute([row])["rows"][0]
        self.assertEqual(out["inventory_current_available_qty"], "10")
        self.assertEqual(out["order_eligibility"], "blocked")
        self.assertIn("b_netting_gate_closed", out["order_blockers"])

    def test_partial_identity_keeps_observation_but_not_current(self):
        row = base(b_tt_sku=None, b_target_identities=[
            {"warehouse": "WH", "branch": "B1", "purpose": "branch",
             "tt_sku": None}], reasons=["b_missing_tt_sku"])
        out = attribute([row])["rows"][0]
        self.assertEqual(out["attribution_status"], "partial_identity")
        self.assertIsNone(out["inventory_qty"])
        self.assertEqual(out["inventory_observed_qty"], "10")
        self.assertIsNone(out["inventory_current_available_qty"])
        self.assertIn("identity_partial", out["reasons"])


def _write_workbooks(tmp, *, with_target=True, conflict_alias=False,
                     c_dependency="v6r9", c_dependency2=None):
    from openpyxl import Workbook
    tmp = Path(tmp)
    a = tmp / "A.xlsx"
    book = Workbook()
    sheet = book.active
    sheet.title = "活跃宇宙"
    sheet.append(["EN物料", "角色", "活跃分类"])
    sheet.append(["I", "成品", "EN+通途"])
    book.save(a)

    b = tmp / "B.xlsx"
    book = Workbook()
    sheet = book.active
    sheet.title = "主表"
    headers = ["产品键", "地区", "美国责任方", "UOM_单位", "是否需求行",
               "可进净额", "限制原因"]
    values = ["I", "US", "美东USNJ", "个", "Y", "否", ""]
    if with_target:
        headers += ["目的仓", "branch", "purpose", "tt_sku"]
        values += ["WH", "B1", "branch", "S1"]
        if conflict_alias:
            headers += ["warehouse"]
            values += ["OTHER"]
    sheet.append(headers)
    sheet.append(values)
    book.save(b)

    c = tmp / "C.xlsx"
    book = Workbook()
    sheet = book.active
    sheet.title = "19_Top50候选导出"
    c_headers = ["product_id", "pool", "canonical_uom", "可发供给",
                 "join_class", "source_ref", "as_of",
                 "demand_eligibility", "依赖B版本"]
    c_values = ["I", "美东USNJ", "个", 4, "join_full", "ST:1",
                "2026-10-28", "independent", c_dependency]
    if c_dependency2 is not None:
        c_headers.append("依赖B版本2")
        c_values.append(c_dependency2)
    sheet.append(c_headers)
    sheet.append(c_values)
    second = book.create_sheet("19b_Top50观察表")
    second.append(c_headers)
    book.save(c)
    return a, b, c


@unittest.skipUnless(importlib.util.find_spec("openpyxl"), "requires openpyxl")
class WorkbookContractTests(unittest.TestCase):
    def test_positive_workbook_attribution_and_input_contract(self):
        with tempfile.TemporaryDirectory() as tmp:
            a, b, c = _write_workbooks(tmp, c_dependency="v6r10")
            result = load_frozen_abc(
                a, b, c, as_of="2026-11-02", a_version="A1",
                b_version="v6r10", c_version="v14",
                c_declared_b_version="v6r10",
                max_stock_age_days=30)
            self.assertEqual(result["report"]["version_relation"], "match")
            self.assertEqual(result["approved_items"], ["I"])
            self.assertEqual(len(result["inventory"]), 1)
            row = result["inventory"][0]
            self.assertEqual(row["inventory_qty"], "4")
            self.assertEqual(row["attribution_status"], "attributed")
            self.assertIsNone(row["inventory_current_available_qty"])
            self.assertEqual(row["inventory_time_status"], "date_only")
            self.assertFalse(row["inventory_time_proven"])
            self.assertEqual(row["inventory_freshness"], "unknown_time")
            inputs = {item["role"]: item for item in result["report"]["inputs"]}
            self.assertEqual(inputs["C"]["as_of"], "2026-10-28")
            self.assertEqual(inputs["C"]["row_count"], 1)
            self.assertEqual(len(inputs["A"]["sha256"]), 64)

    def test_b_without_target_columns_stays_partial_identity(self):
        with tempfile.TemporaryDirectory() as tmp:
            a, b, c = _write_workbooks(tmp, with_target=False,
                                        c_dependency="v6r10")
            result = load_frozen_abc(
                a, b, c, as_of="2026-11-02", a_version="A1",
                b_version="v6r10", c_version="v14",
                c_declared_b_version="v6r10", max_stock_age_days=30)
            row = result["inventory"][0]
            self.assertEqual(row["attribution_status"], "partial_identity")
            self.assertIsNone(row["inventory_qty"])
            self.assertEqual(row["inventory_observed_qty"], "4")
            self.assertIsNone(row["inventory_current_available_qty"])
            for reason in ("b_missing_warehouse", "b_missing_branch",
                           "b_missing_purpose", "b_missing_tt_sku"):
                self.assertIn(reason, row["reasons"])

    def test_declared_old_b_version_is_explicit_conflict(self):
        with tempfile.TemporaryDirectory() as tmp:
            a, b, c = _write_workbooks(tmp)
            result = load_frozen_abc(
                a, b, c, as_of="2026-11-02", a_version="A1",
                b_version="v6r10", c_version="v14",
                c_declared_b_version="v6r9", max_stock_age_days=30)
            self.assertEqual(result["report"]["version_relation"], "mismatch")
            row = result["inventory"][0]
            self.assertEqual(row["attribution_status"], "version_conflict")
            self.assertIsNone(row["inventory_qty"])
            self.assertIn("c_declared_b_version_mismatch", row["reasons"])

    def test_cli_dependency_conflict_with_workbook_is_rejected(self):
        with tempfile.TemporaryDirectory() as tmp:
            a, b, c = _write_workbooks(tmp, c_dependency="v6r9")
            with self.assertRaises(ValueError) as ctx:
                load_frozen_abc(a, b, c, as_of="2026-11-02",
                                a_version="A1", b_version="v6r10",
                                c_version="v14",
                                c_declared_b_version="v6r10",
                                max_stock_age_days=30)
            self.assertIn("c_dependency_conflict", str(ctx.exception))

    def test_multiple_workbook_dependency_markers_are_rejected(self):
        with tempfile.TemporaryDirectory() as tmp:
            a, b, c = _write_workbooks(tmp, c_dependency="v6r9",
                                        c_dependency2="v6r10")
            with self.assertRaises(ValueError) as ctx:
                load_frozen_abc(a, b, c, as_of="2026-11-02",
                                a_version="A1", b_version="v6r10",
                                c_version="v14", max_stock_age_days=30)
            self.assertIn("c_dependency_ambiguous", str(ctx.exception))

    def test_expected_hash_and_row_count_are_enforced(self):
        with tempfile.TemporaryDirectory() as tmp:
            a, b, c = _write_workbooks(tmp)
            with self.assertRaises(ValueError) as ctx:
                load_frozen_abc(a, b, c, as_of="2026-11-02",
                                a_version="A1", b_version="v6r10",
                                c_version="v14", max_stock_age_days=30,
                                expected={"a": {"sha256": "0" * 64}})
            self.assertIn("input_hash_mismatch:a", str(ctx.exception))
            with self.assertRaises(ValueError) as ctx:
                load_frozen_abc(a, b, c, as_of="2026-11-02",
                                a_version="A1", b_version="v6r10",
                                c_version="v14", max_stock_age_days=30,
                                expected={"b": {"rows": 999}})
            self.assertIn("input_row_count_mismatch:b", str(ctx.exception))

    def test_conflicting_target_alias_columns_fail_closed(self):
        with tempfile.TemporaryDirectory() as tmp:
            a, b, c = _write_workbooks(tmp, conflict_alias=True)
            with self.assertRaises(ValueError) as ctx:
                load_frozen_abc(a, b, c, as_of="2026-11-02",
                                a_version="A1", b_version="v6r10",
                                c_version="v14", max_stock_age_days=30)
            self.assertIn("b_target_alias_conflict", str(ctx.exception))

    def test_versions_are_required(self):
        with tempfile.TemporaryDirectory() as tmp:
            a, b, c = _write_workbooks(tmp)
            with self.assertRaises(ValueError):
                load_frozen_abc(a, b, c, as_of="2026-11-02",
                                a_version=None, b_version="v6r10",
                                c_version="v14", max_stock_age_days=30)


if __name__ == "__main__":
    unittest.main()
