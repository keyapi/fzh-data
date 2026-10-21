#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""en_variant_evidence 的离线单测（不联网、不调用 main()）。"""

from __future__ import annotations

import unittest
from datetime import date

import en_family_poc as fp
import en_variant_evidence as ev

BASE = "KS0001-A"
CODE = "PK#KS0001-A"
AS_OF = "2026-10-21"


def item_docs():
    return {
        CODE: {"name": CODE, "item_code": CODE, "stock_uom": "个", "disabled": 0,
               "modified": "2026-01-01", "uoms": [{"uom": "个", "conversion_factor": 1}]},
        BASE: {"name": BASE, "item_code": BASE, "stock_uom": "个", "disabled": 0,
               "modified": "2026-01-01", "uoms": [{"uom": "个", "conversion_factor": 1}]},
    }


def bom(output=10, component=10, active=1, default=1):
    return {
        "name": "BOM-A", "item": BASE, "quantity": output, "uom": "个",
        "docstatus": 1, "is_active": active, "is_default": default,
        "modified": "2026-01-01",
        "items": [{"item_code": CODE, "qty": component, "uom": "个",
                   "stock_qty": component, "stock_uom": "个"}],
    }


class FlagTest(unittest.TestCase):
    def test_strict_flag_parsing(self):
        self.assertIs(ev.flag("0"), False)
        self.assertIs(ev.flag("1"), True)
        self.assertIs(ev.flag("false"), False)
        self.assertIs(ev.flag("true"), True)
        self.assertIs(ev.flag(0), False)
        self.assertIs(ev.flag(1), True)
        self.assertIsNone(ev.flag("maybe"))

    def test_float_zero_one_are_equivalent(self):
        self.assertIs(ev.flag(0.0), False)
        self.assertIs(ev.flag(1.0), True)

    def test_other_numbers_and_nan_inf_are_invalid(self):
        for value in (2, -1, 0.5, float("nan"), float("inf"), float("-inf")):
            self.assertIsNone(ev.flag(value), value)

    def test_item_disabled_string_zero(self):
        self.assertIs(ev.item_meta({"disabled": "0"})["disabled"], False)
        self.assertIs(ev.item_meta({"disabled": "1"})["disabled"], True)
        self.assertIsNone(ev.item_meta({"disabled": 2})["disabled"])


class AnalyzeBomTest(unittest.TestCase):
    def test_integer_flags_are_normalized(self):
        cand, reason = ev.analyze_bom(bom(), CODE, BASE, item_docs())
        self.assertEqual(reason, "")
        self.assertTrue(cand["is_active"])
        self.assertTrue(cand["eligible_at_evidence"])
        self.assertEqual(cand["ratio"], 1.0)

    def test_string_zero_flag_is_inactive(self):
        cand, reason = ev.analyze_bom(bom(active="0"), CODE, BASE, item_docs())
        self.assertEqual(reason, "")
        self.assertFalse(cand["is_active"])
        self.assertFalse(cand["eligible_at_evidence"])

    def test_unknown_flag_is_invalid(self):
        cand, reason = ev.analyze_bom(bom(active="maybe"), CODE, BASE, item_docs())
        self.assertIsNone(cand)
        self.assertEqual(reason, "bom_flag_invalid")

    def test_numeric_non_binary_flag_is_invalid(self):
        for value in (2, -1, 0.5, float("nan"), float("inf")):
            cand, reason = ev.analyze_bom(bom(active=value), CODE, BASE, item_docs())
            self.assertIsNone(cand, value)
            self.assertEqual(reason, "bom_flag_invalid")

    def test_float_one_flag_is_eligible(self):
        cand, reason = ev.analyze_bom(bom(active=1.0, default=0.0), CODE, BASE,
                                      item_docs())
        self.assertEqual(reason, "")
        self.assertTrue(cand["eligible_at_evidence"])
        self.assertFalse(cand["is_default"])

    def test_inactive_bom_not_eligible(self):
        cand, _ = ev.analyze_bom(bom(active=0), CODE, BASE, item_docs())
        self.assertFalse(cand["is_active"])
        self.assertFalse(cand["eligible_at_evidence"])

    def test_ratio_uses_stock_quantities(self):
        cand, _ = ev.analyze_bom(bom(output=2, component=1), CODE, BASE, item_docs())
        self.assertEqual(cand["ratio"], 0.5)

    def test_reversed_direction_is_recorded_not_swapped(self):
        reversed_bom = bom()
        reversed_bom["item"] = CODE
        reversed_bom["items"][0]["item_code"] = BASE
        cand, _ = ev.analyze_bom(reversed_bom, CODE, BASE, item_docs())
        self.assertEqual(cand["direction"], "variant_parent_ks_component")


class BuildRecordTest(unittest.TestCase):
    def test_consistent_record_is_current_structure_only(self):
        cand, _ = ev.analyze_bom(bom(), CODE, BASE, item_docs())
        rec, resolution = ev.build_record(
            CODE, BASE, "PK", item_docs(), [cand], [], AS_OF, {BASE})
        self.assertEqual(resolution, "consistent")
        self.assertEqual(rec["evidence_scope"], "current_structure_only")
        self.assertEqual(rec["ratio"], 1.0)
        self.assertTrue(rec["current_planning_eligible"])

    def test_zero_ratio_is_conflict(self):
        cand, _ = ev.analyze_bom(bom(output=2, component=1), CODE, BASE, item_docs())
        rec, resolution = ev.build_record(
            CODE, BASE, "PK", item_docs(), [cand], [], AS_OF, {BASE})
        self.assertEqual(resolution, "conflict")

    def test_reversed_direction_is_not_consistent(self):
        rev = bom()
        rev["item"] = CODE
        rev["items"][0]["item_code"] = BASE
        cand, _ = ev.analyze_bom(rev, CODE, BASE, item_docs())
        rec, resolution = ev.build_record(
            CODE, BASE, "PK", item_docs(), [cand], [], AS_OF, {BASE})
        self.assertEqual(resolution, "unsupported_direction")
        self.assertEqual(rec["reason_code"], "unsupported_direction")
        self.assertFalse(rec["current_planning_eligible"])

    def test_mixed_valid_and_reverse_is_conflict(self):
        rev = bom()
        rev["item"] = CODE
        rev["items"][0]["item_code"] = BASE
        rev_cand, _ = ev.analyze_bom(rev, CODE, BASE, item_docs())
        valid_cand, _ = ev.analyze_bom(bom(), CODE, BASE, item_docs())
        rec, resolution = ev.build_record(
            CODE, BASE, "PK", item_docs(), [valid_cand, rev_cand], [], AS_OF, {BASE})
        self.assertEqual(resolution, "conflict_mixed_direction")
        self.assertFalse(rec["current_planning_eligible"])
        self.assertTrue(rec["candidate_boms"])
        self.assertTrue(any(e["reason"] == "unsupported_direction"
                            for e in rec["excluded_boms"]))

    def test_shared_component_multiple_parents_is_unresolved(self):
        b1 = bom()
        b2 = bom()
        b2["name"] = "BOM-B"
        b2["item"] = "KS0001-B"
        edges = [ev.shared_edge(b1, CODE), ev.shared_edge(b2, CODE)]
        rec, resolution = ev.build_record(
            CODE, "KS9999-X", "ND", item_docs(), [], [], AS_OF, {BASE},
            shared_edges=edges)
        self.assertEqual(resolution, "unresolved_canonical_mapping")
        self.assertEqual(rec["reason_code"], "shared_component_multiple_parents")
        self.assertEqual(rec["shared_parent_ks"], ["KS0001-A", "KS0001-B"])
        self.assertEqual(len(rec["candidate_boms"]), 2)
        self.assertFalse(rec["current_planning_eligible"])

    def test_base_not_in_family_is_unresolved(self):
        cand, _ = ev.analyze_bom(bom(), CODE, BASE, item_docs())
        edge = ev.shared_edge(bom(), CODE)
        rec, resolution = ev.build_record(
            CODE, "KS9999-X", "PK", item_docs(), [cand], [], AS_OF, {BASE},
            shared_edges=[edge])
        self.assertEqual(resolution, "unresolved_canonical_mapping")
        self.assertEqual(rec["reason_code"], "shared_component_single_parent")

    def test_disabled_item_numeric_non_binary_is_invalid(self):
        items = item_docs()
        items[CODE]["disabled"] = 2
        rec, resolution = ev.build_record(
            CODE, BASE, "PK", items, [], [], AS_OF, {BASE})
        self.assertEqual(resolution, "item_flag_invalid")
        self.assertEqual(rec["reason_code"], "item_flag_invalid")

    def test_consumer_accepts_structure_once_historical_anchor_exists(self):
        cand, _ = ev.analyze_bom(bom(), CODE, BASE, item_docs())
        rec, _ = ev.build_record(
            CODE, BASE, "PK", item_docs(), [cand], [], AS_OF, {BASE})
        rec = dict(rec, evidence_scope="historical_verified",
                   historical_basis="unit-test-only",
                   valid_from="2026-04-01", valid_to="2026-09-30")
        ok, reason, ref, detail = fp.validate_variant_record(
            CODE, BASE, "PK", rec, {BASE}, date(2026, 4, 1), date(2026, 9, 30), "个")
        self.assertTrue(ok, (reason, detail))
        self.assertTrue(ref.startswith("BOM-A@"))


class SelectionTest(unittest.TestCase):
    def test_selection_is_deterministic_and_deduplicated(self):
        rows = [
            {"prefix_role": "PK", "disposition": "pending",
             "disposition_reason": "variant_manifest_absent",
             "item_code": "PK#KS0001-A", "base_item_code": "KS0001-A",
             "qty": 5},
            {"prefix_role": "PK", "disposition": "pending",
             "disposition_reason": "variant_manifest_absent",
             "item_code": "PK#KS0001-A", "base_item_code": "KS0001-A",
             "qty": 5},
            {"prefix_role": "ND", "disposition": "pending",
             "disposition_reason": "variant_manifest_absent",
             "item_code": "ND#KS0001-B", "base_item_code": "KS0001-B",
             "qty": 3},
            {"prefix_role": "PK", "disposition": "pending",
             "disposition_reason": "variant_base_not_family",
             "item_code": "PK#KS9999-C", "base_item_code": "KS9999-C",
             "qty": 1},
        ]
        out = ev.select_variants(rows, {"KS0001-A"}, 4)
        self.assertEqual([r["code"] for r in out],
                         ["PK#KS0001-A", "ND#KS0001-B", "PK#KS9999-C"])
        self.assertEqual(ev.select_variants(rows, {"KS0001-A"}, 4),
                         ev.select_variants(rows, {"KS0001-A"}, 4))


if __name__ == "__main__":
    unittest.main()
