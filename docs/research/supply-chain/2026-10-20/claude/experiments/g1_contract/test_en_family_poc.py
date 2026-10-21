#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""en_family_poc 的离线契约单测（不联网、不调用 main()）。

运行：
  uv run python -m unittest -v test_en_family_poc.py
"""

from __future__ import annotations

import json
import tempfile
import unittest
from datetime import date
from pathlib import Path

import en_family_poc as fp

BASE = "KS0001-A"
CODE = "PK#KS0001-A"
WIN_FROM, WIN_TO = date(2026, 4, 1), date(2026, 9, 30)


def make_record(**overrides):
    rec = {
        "schema_version": "variant_evidence/1",
        "canonical_ks": BASE,
        "role": "PK",
        "evidence": "structural",
        "evidence_scope": "historical_verified",
        "historical_basis": "Version/BOM/BOM-A@2026-04-01",
        "direction": "ks_parent_variant_component",
        "valid_from": "2026-04-01",
        "valid_to": "2026-09-30",
        "resolution": "consistent",
        "current_planning_eligible": True,
        "ratio": 1,
        "uom": "个",
        "component": {
            "item_code": CODE, "qty": 10, "uom": "个", "stock_qty": 10,
            "stock_uom": "个", "conversion_factor": 1, "line_count": 1,
        },
        "output": {
            "item_code": BASE, "qty": 10, "uom": "个", "stock_qty": 10,
            "stock_uom": "个", "conversion_factor": 1,
        },
        "item": {"name": CODE, "disabled": 0, "stock_uom": "个",
                 "sha256": "i" * 64, "modified": "2026-04-01 00:00:00"},
        "bom": {"name": "BOM-A", "modified": "2026-04-01 00:00:00",
                "sha256": "b" * 64},
        "candidate_boms": [{
            "name": "BOM-A", "modified": "2026-04-01 00:00:00",
            "sha256": "b" * 64, "docstatus": 1, "is_active": True,
            "eligible_at_evidence": True,
            "is_default": True, "direction": "ks_parent_variant_component",
            "parent_item": BASE, "child_item": CODE,
            "component_stock_qty": 10, "output_stock_qty": 10, "uom": "个",
        }],
    }
    rec.update(overrides)
    return rec


def rules(rec=None, *, family_items=None, line_uom="个"):
    return fp.validate_variant_record(
        CODE, BASE, "PK", rec if rec is not None else make_record(),
        family_items if family_items is not None else {BASE},
        WIN_FROM, WIN_TO, line_uom)


class LineKeyTest(unittest.TestCase):
    def test_missing_and_duplicate(self):
        seen = set()
        self.assertEqual(fp.check_line_key("A", "", seen), "invalid_missing")
        self.assertEqual(fp.check_line_key("A", "L1", seen), "ok")
        self.assertEqual(fp.check_line_key("A", "L1", seen), "invalid_duplicate")
        self.assertEqual(fp.check_line_key("B", "L1", seen), "ok")


class VariantRecordContractTest(unittest.TestCase):
    def test_valid_record_is_accepted_and_ref_is_derived(self):
        ok, reason, ref, detail = rules()
        self.assertTrue(ok, (reason, detail))
        self.assertEqual(reason, "variant_structural_1to1")
        self.assertEqual(ref, f"BOM-A@{'b' * 12}")

    def test_label_only_record_is_rejected(self):
        ok, reason, ref, detail = rules({"evidence": "proven",
                                         "evidence_ref": "任意 ref"})
        self.assertFalse(ok)
        self.assertEqual(reason, "variant_schema_missing")
        self.assertEqual(ref, "")

    def test_base_outside_family_is_rejected(self):
        rec = make_record(canonical_ks="KS9999-X")
        ok, reason, _, _ = fp.validate_variant_record(
            CODE, "KS9999-X", "PK", rec, {BASE}, WIN_FROM, WIN_TO)
        self.assertFalse(ok)
        self.assertEqual(reason, "variant_base_not_family")

    def test_role_mismatch(self):
        self.assertEqual(rules(make_record(role="ND"))[1],
                         "variant_role_mismatch")

    def test_ratio_half_is_rejected(self):
        rec = make_record(ratio=0.5)
        rec["output"]["qty"] = rec["output"]["stock_qty"] = 2
        self.assertEqual(rules(rec)[1], "variant_ratio_not_1")

    def test_ratio_field_must_match_computed(self):
        self.assertEqual(rules(make_record(ratio=2))[1],
                         "variant_ratio_mismatch")

    def test_uom_conversion_missing(self):
        rec = make_record()
        rec["component"].update({"uom": "箱", "qty": 1, "stock_qty": 2})
        rec["component"].pop("conversion_factor", None)
        self.assertEqual(rules(rec)[1], "variant_uom_conversion_missing")

    def test_uom_conversion_mismatch(self):
        rec = make_record()
        rec["component"].update({"uom": "箱", "qty": 1, "stock_qty": 3,
                                 "conversion_factor": 2})
        self.assertEqual(rules(rec)[1], "variant_uom_conversion_mismatch")

    def test_expired_validity(self):
        self.assertEqual(rules(make_record(valid_to="2026-05-31"))[1],
                         "variant_out_of_validity")

    def test_current_structure_only_is_pending(self):
        self.assertEqual(
            rules(make_record(evidence_scope="current_structure_only"))[1],
            "variant_current_structure_only")

    def test_historical_without_basis_is_pending(self):
        self.assertEqual(rules(make_record(historical_basis=""))[1],
                         "variant_historical_basis_missing")

    def test_wrong_direction_is_pending(self):
        self.assertEqual(
            rules(make_record(direction="variant_parent_ks_component"))[1],
            "variant_direction_not_cover_consumption")

    def test_line_uom_mismatch(self):
        self.assertEqual(rules(None, line_uom="套")[1],
                         "variant_line_uom_mismatch")

    def test_multiple_bom_conflict(self):
        rec = make_record()
        bad = dict(rec["candidate_boms"][0])
        bad.update({"name": "BOM-B", "sha256": "c" * 64,
                    "component_stock_qty": 20})
        rec["candidate_boms"].append(bad)
        self.assertEqual(rules(rec)[1], "variant_bom_conflict")

    def test_candidate_missing_eligible_at_evidence(self):
        rec = make_record()
        rec["candidate_boms"][0].pop("eligible_at_evidence", None)
        self.assertEqual(rules(rec)[1], "variant_bom_conflict")

    def test_inactive_now_but_eligible_at_evidence_is_accepted(self):
        rec = make_record()
        rec["candidate_boms"][0]["is_active"] = False
        self.assertTrue(rules(rec)[0])

    def test_same_uom_qty_stock_mismatch(self):
        rec = make_record()
        rec["component"].update({"qty": 20, "stock_qty": 10})
        self.assertEqual(rules(rec)[1], "variant_quantity_mismatch")

    def test_same_uom_factor_must_be_one(self):
        rec = make_record()
        rec["component"]["conversion_factor"] = 2
        self.assertEqual(rules(rec)[1], "variant_uom_conversion_mismatch")

    def test_output_side_same_uom_mismatch(self):
        rec = make_record()
        rec["output"].update({"qty": 9, "stock_qty": 10})
        self.assertEqual(rules(rec)[1], "variant_quantity_mismatch")

    def test_unsupported_record_schema(self):
        rec = make_record(schema_version="variant_evidence/999")
        self.assertEqual(rules(rec)[1], "variant_unsupported_record_schema")

    def test_malformed_docstatus_does_not_raise(self):
        rec = make_record()
        rec["candidate_boms"][0]["docstatus"] = "bad"
        ok, reason, _, detail = rules(rec)
        self.assertFalse(ok)
        self.assertEqual(reason, "variant_record_invalid")
        self.assertEqual(detail, "candidate.docstatus:BOM-A")

    def test_missing_line_uom(self):
        self.assertEqual(rules(None, line_uom="")[1], "variant_line_uom_missing")

    def test_disabled_with_current_planning_true_is_conflict(self):
        rec = make_record(current_planning_eligible=True)
        rec["item"]["disabled"] = 1
        self.assertEqual(rules(rec)[1], "variant_planning_eligibility_conflict")

    def test_selected_bom_not_in_candidates(self):
        rec = make_record()
        rec["bom"]["name"] = "BOM-Z"
        self.assertEqual(rules(rec)[1], "variant_selected_bom_not_candidate")

    def test_disabled_item_kept_for_history(self):
        rec = make_record(current_planning_eligible=False)
        rec["item"]["disabled"] = 1
        ok, reason, _, detail = rules(rec)
        self.assertTrue(ok, (reason, detail))
        self.assertFalse(rec["current_planning_eligible"])

    def test_missing_current_planning_flag(self):
        rec = make_record()
        rec.pop("current_planning_eligible", None)
        self.assertEqual(rules(rec)[1],
                         "variant_current_planning_flag_missing")


class ClassifyLineTest(unittest.TestCase):
    def test_bare_ks_still_family(self):
        out = fp.classify_line("KS0001-A", "x", "", [], {BASE}, set(),
                               {}, "none", WIN_FROM, WIN_TO)
        self.assertEqual(out[:3], ("family", "KS", "ks_exact"))

    def test_variant_without_manifest_is_pending(self):
        out = fp.classify_line(CODE, "x", "", [], {BASE}, set(),
                               {}, "none", WIN_FROM, WIN_TO)
        self.assertEqual(out[0], "pending")
        self.assertEqual(out[2], "variant_manifest_absent")

    def test_variant_with_valid_record_is_family(self):
        out = fp.classify_line(CODE, "x", "", [], {BASE}, set(),
                               {CODE: make_record()}, "evidence",
                               WIN_FROM, WIN_TO, "个")
        self.assertEqual(out[0], "family")
        self.assertEqual(out[1], "PK")
        self.assertEqual(out[3], f"BOM-A@{'b' * 12}")
        self.assertEqual(out[4], "")

    def test_variant_with_conflicting_record_is_pending(self):
        out = fp.classify_line(CODE, "x", "", [], {BASE}, set(),
                               {CODE: make_record(canonical_ks="KS0001-B")},
                               "evidence", WIN_FROM, WIN_TO)
        self.assertEqual(out[0], "pending")
        self.assertEqual(out[2], "variant_base_conflict")

    def test_validator_exception_is_contained(self):
        class BadRec(dict):
            def get(self, key, default=None):
                raise RuntimeError("boom")

        out = fp.classify_line(CODE, "x", "", [], {BASE}, set(),
                               {CODE: BadRec()}, "evidence",
                               WIN_FROM, WIN_TO, "个")
        self.assertEqual(out[0], "pending")
        self.assertEqual(out[2], "variant_record_invalid")
        self.assertEqual(out[4], "exception:RuntimeError")


class DemandRoleTest(unittest.TestCase):
    def test_terminal_finished_is_candidate_only(self):
        self.assertEqual(fp.derive_demand("family", "KS", ""),
                         ("ks_finished", "terminal_finished_candidate", 1,
                          "count_cover_1to1_event_unverified"))

    def test_cover_only_customer_is_independent_cover_candidate(self):
        self.assertEqual(fp.derive_demand("family", "KS", "CODE-1-Cover"),
                         ("ks_finished", "independent_cover_candidate", 1,
                          "count_cover_1to1_event_unverified"))

    def test_inner_does_not_create_cover_demand(self):
        self.assertEqual(fp.derive_demand("family", "ND", ""),
                         ("inner", "assembly_component_candidate", 0,
                          "no_cover_demand"))

    def test_pending_has_no_demand_role(self):
        self.assertEqual(fp.derive_demand("pending", "PK", ""),
                         ("cover", "unknown", None, "not_counted"))


class QtyTest(unittest.TestCase):
    def test_missing_and_bad_are_none(self):
        self.assertEqual(fp.parse_qty(None), (None, "missing"))
        self.assertEqual(fp.parse_qty(""), (None, "missing"))
        self.assertEqual(fp.parse_qty("abc"), (None, "bad"))
        self.assertEqual(fp.parse_qty(float("nan")), (None, "bad"))
        self.assertEqual(fp.parse_qty(-1), (None, "bad"))

    def test_zero_is_valid(self):
        self.assertEqual(fp.parse_qty(0), (0.0, "ok"))


class VariantFileContractTest(unittest.TestCase):
    def write(self, doc_text):
        tmp = tempfile.NamedTemporaryFile("w", suffix=".json", delete=False,
                                          encoding="utf-8")
        tmp.write(doc_text)
        tmp.close()
        self.addCleanup(Path(tmp.name).unlink, missing_ok=True)
        return Path(tmp.name)

    @staticmethod
    def payload_hash(doc):
        payload = {k: doc.get(k) for k in
                   ("schema_version", "version", "source", "site", "as_of",
                    "producer", "rule_version", "items")}
        return fp.sha256_bytes(fp._canonical_json(payload))

    def make_doc(self, **overrides):
        doc = {
            "schema_version": "variant_evidence/1",
            "version": "family_variant_manifest/test",
            "source": "erpnext.vilavi.cn",
            "site": fp.EXPECTED_SITE,
            "as_of": "2026-10-21",
            "rule_version": "variant-evidence/1",
            "producer": {"name": "unit-test", "version": "1"},
            "items": {CODE: make_record()},
        }
        doc.update(overrides)
        doc["payload_sha256"] = self.payload_hash(doc)
        return doc

    def test_duplicate_code_rejected(self):
        path = self.write('{"items":{"A":{},"A":{}}}')
        with self.assertRaisesRegex(ValueError, "duplicate JSON key"):
            fp.load_variant_evidence(path)

    def test_payload_hash_mismatch_rejected(self):
        doc = self.make_doc()
        doc["producer"]["version"] = "2"
        with self.assertRaisesRegex(ValueError, "payload_sha256"):
            fp.load_variant_evidence(self.write(json.dumps(doc)))

    def test_missing_producer_rejected(self):
        doc = self.make_doc()
        doc.pop("producer")
        doc["payload_sha256"] = self.payload_hash(doc)
        with self.assertRaisesRegex(ValueError, "producer"):
            fp.load_variant_evidence(self.write(json.dumps(doc)))

    def test_missing_schema_or_site_rejected(self):
        for field in ("schema_version", "version", "source", "site", "as_of"):
            doc = self.make_doc()
            doc.pop(field)
            doc["payload_sha256"] = self.payload_hash(doc)
            with self.assertRaisesRegex(ValueError, field):
                fp.load_variant_evidence(self.write(json.dumps(doc)))

    def test_unsupported_schema_rule_source_site_rejected(self):
        cases = {
            "schema_version": "variant_evidence/999",
            "rule_version": "unknown/999",
            "source": "another-site",
            "site": "https://another.example",
        }
        for field, value in cases.items():
            doc = self.make_doc(**{field: value})
            with self.assertRaises(ValueError):
                fp.load_variant_evidence(self.write(json.dumps(doc)))

    def test_valid_file_loads_with_verified_payload_hash(self):
        doc = self.make_doc()
        loaded = fp.load_variant_evidence(
            self.write(json.dumps(doc, ensure_ascii=False)))
        self.assertEqual(loaded["entries"], 1)
        self.assertEqual(loaded["payload_sha256"], doc["payload_sha256"])
        self.assertEqual(loaded["schema_version"], "variant_evidence/1")


if __name__ == "__main__":
    unittest.main()
