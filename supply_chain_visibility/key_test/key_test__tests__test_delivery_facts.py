# -*- coding: utf-8 -*-
"""Counterexample tests for DN-anchored delivery facts (pure builder)."""
import hashlib
import importlib.util
import json
import sys
import types
import unittest
from pathlib import Path

_saved = {name: sys.modules.get(name) for name in ("frappe", "frappe.utils")}
_frappe = types.ModuleType("frappe")
_frappe.whitelist = lambda *a, **k: (lambda fn: fn)
_frappe.ValidationError = ValueError
_frappe.PermissionError = PermissionError
_frappe.local = types.SimpleNamespace(site="test")
_frappe.throw = lambda message, exc=None: (_ for _ in ()).throw(exc or Exception(message))
_frappe.utils = types.SimpleNamespace(now_datetime=lambda: "2026-10-30 10:00:00")
sys.modules["frappe"] = _frappe
sys.modules["frappe.utils"] = _frappe.utils
_spec = importlib.util.spec_from_file_location(
    "key_test_delivery_facts_test",
    Path(__file__).resolve().parents[1] / "delivery_facts.py")
df = importlib.util.module_from_spec(_spec)
_spec.loader.exec_module(df)
for name, module in _saved.items():
    if module is None:
        sys.modules.pop(name, None)
    else:
        sys.modules[name] = module

TARGET = "PK#KS0001-DM-100-GREY"
OTHER = "COTTON-ROLL-1"


def scope_obj(codes=(TARGET,)):
    payload = {"source": "warehouse_restock", "version": "test-scope-v1",
               "items": [{"item_code": code} for code in codes]}
    canonical = json.dumps({"source": payload["source"],
                            "version": payload["version"],
                            "items": sorted(codes)}, sort_keys=True)
    payload["hash"] = hashlib.sha256(canonical.encode("utf-8")).hexdigest()
    return payload


def header(name, customer="C1", docstatus=1, is_return=0, **over):
    row = {"name": name, "customer": customer, "company": "FZH",
           "posting_date": "2026-10-20", "posting_time": "10:00:00",
           "docstatus": docstatus, "is_return": is_return,
           "return_against": None, "amended_from": None,
           "set_warehouse": "SRC", "set_target_warehouse": None,
           "custom_tongtool_purchase_order": "PO-1",
           "modified": "2026-10-20 10:00:00", "status": "To Bill"}
    row.update(over)
    return row


def item(name, parent, item_code=TARGET, qty=10, uom="个", stock_uom="个",
         so_detail=None, against=None, dn_detail=None, idx=1,
         warehouse="SRC", **over):
    row = {"name": name, "parent": parent, "idx": idx, "item_code": item_code,
           "item_name": item_code, "customer_item_code": "", "qty": qty,
           "uom": uom, "stock_qty": qty, "stock_uom": stock_uom,
           "conversion_factor": 1, "warehouse": warehouse, "target_warehouse": None,
           "against_sales_order": against, "so_detail": so_detail,
           "dn_detail": dn_detail, "is_return": 0}
    row.update(over)
    return row


def so_item(name, parent, item_code=TARGET, qty=100, uom="个"):
    return {"name": name, "parent": parent, "item_code": item_code,
            "qty": qty, "uom": uom, "stock_uom": uom}


def so_header(name, customer="C1", docstatus=1):
    return {"name": name, "customer": customer, "docstatus": docstatus}


def build(headers, items, so_headers=None, so_items=None, permitted=None,
          candidates=None, logistics=None, scope=None, **kwargs):
    return df.build_delivery_facts(
        headers, items, so_headers or {}, so_items or [],
        permitted if permitted is not None else set(so_headers or {}),
        candidates or {}, logistics or {},
        scope=scope if scope is not None else scope_obj(),
        observed_at="2026-10-30T10:00:00", as_of="2026-10-30", **kwargs)


def line(result, name):
    return next(row for row in result["delivery_lines"]
                if row["delivery_note_item"] == name)


class AssociationTests(unittest.TestCase):
    def test_linked_70_plus_unlinked_10_is_pool_overlap_not_confirmed(self):
        headers = [header("DN-L"), header("DN-U")]
        items = [item("I-L", "DN-L", qty=70, so_detail="SOI-1", against="SO-1"),
                 item("I-U", "DN-U", qty=10)]
        result = build(headers, items,
                       so_headers={"SO-1": so_header("SO-1")},
                       so_items=[so_item("SOI-1", "SO-1", qty=100)])
        fulfillment = result["so_fulfillment"][0]
        self.assertEqual(fulfillment["linked_delivered_qty"], 70.0)
        self.assertEqual(fulfillment["so_open_qty"], 30.0)
        self.assertEqual(fulfillment["unresolved_demand_qty"], 30.0)
        self.assertIsNone(fulfillment["potential_overlap_qty"])
        self.assertIsNone(fulfillment["confirmed_additional_supply_qty"])
        pool = result["ambiguity_pools"][0]
        self.assertEqual(pool["potential_overlap_qty"], 10.0)
        self.assertEqual(pool["unresolved_demand_qty"], 20.0)
        self.assertEqual(sum(row["actual_qty"] for row in result["delivery_lines"]), 80.0)

    def test_dn_without_so_is_preserved(self):
        result = build([header("DN-U")], [item("I-U", "DN-U", qty=12)],
                       logistics={"numbers_by_dn": {}, "shipment_by_number": {}})
        row = line(result, "I-U")
        self.assertEqual(row["association_status"], "unlinked")
        self.assertEqual(row["actual_qty"], 12.0)
        stages = [r["stage"] for r in result["physical_chain"]]
        self.assertIn("receipt", stages)

    def test_same_so_multiple_lines_same_item_is_ambiguous(self):
        result = build(
            [header("DN-A")], [item("I-A", "DN-A", qty=5, against="SO-1")],
            so_headers={"SO-1": so_header("SO-1")},
            so_items=[so_item("SOI-1", "SO-1"), so_item("SOI-2", "SO-1")])
        row = line(result, "I-A")
        self.assertEqual(row["association_status"], "ambiguous")
        self.assertEqual(len(row["candidate_so_lines"]), 2)

    def test_scope_requires_authoritative_input(self):
        pending = build([header("DN-S")], [item("I-S", "DN-S")], scope={})
        self.assertEqual(line(pending, "I-S")["relevance_status"], "unknown")
        self.assertEqual(pending["coverage"]["scope"]["status"], "pending")
        invalid = scope_obj()
        invalid["hash"] = "0" * 64
        bad = build([header("DN-S")], [item("I-S", "DN-S")], scope=invalid)
        self.assertEqual(bad["coverage"]["scope"]["status"], "invalid")
        good = build([header("DN-S")],
                     [item("I-IN", "DN-S"), item("I-OUT", "DN-S", item_code=OTHER)])
        self.assertEqual(line(good, "I-IN")["relevance_status"], "in_scope")
        self.assertEqual(line(good, "I-OUT")["relevance_status"], "out_of_scope")

    def test_linked_requires_header_and_all_identity_fields(self):
        cases = [
            (item("I-1", "DN", qty=5, so_detail="SOI-1"), "so_header_missing"),
            (item("I-1", "DN", qty=5, so_detail="SOI-1", against="SO-2"),
             "so_detail_parent_mismatch"),
            (item("I-1", "DN", qty=5, so_detail="SOI-1", against="SO-1", uom="箱"),
             "so_uom_mismatch"),
            (item("I-1", "DN", qty=5, so_detail="SOI-1", against="SO-1",
                  item_code=OTHER), "so_item_code_mismatch"),
        ]
        for row_item, reason in cases:
            result = build(
                [header("DN")], [row_item],
                so_headers={"SO-1": so_header("SO-1")},
                so_items=[so_item("SOI-1", "SO-1")])
            row = line(result, "I-1")
            self.assertEqual(row["association_status"], "conflict", reason)
            self.assertIn(reason, row["conflicts"])

    def test_multi_so_ambiguity_is_order_invariant(self):
        headers = [header("DN-L1"), header("DN-L2"), header("DN-U")]
        items = [item("I-L1", "DN-L1", qty=40, so_detail="SOI-1", against="SO-1"),
                 item("I-L2", "DN-L2", qty=30, so_detail="SOI-2", against="SO-2"),
                 item("I-U", "DN-U", qty=10, against=None)]
        so_headers = {"SO-1": so_header("SO-1"), "SO-2": so_header("SO-2")}
        so_items = [so_item("SOI-1", "SO-1", qty=100),
                    so_item("SOI-2", "SO-2", qty=100)]
        forward = build(headers, items, so_headers=so_headers, so_items=so_items)
        reverse = build(headers, list(reversed(items)),
                        so_headers=so_headers, so_items=so_items)
        self.assertEqual(forward["ambiguity_pools"], reverse["ambiguity_pools"])
        pool = forward["ambiguity_pools"][0]
        self.assertEqual(pool["so_open_total_qty"], 130.0)
        self.assertEqual(pool["potential_overlap_qty"], 10.0)
        self.assertEqual(pool["unresolved_demand_qty"], 120.0)

    def test_restricted_association_does_not_leak_so_name(self):
        result = build([header("DN-R")],
                       [item("I-R", "DN-R", so_detail="SOI-1", against="SO-1")],
                       so_headers={}, so_items=[], permitted=set())
        row = line(result, "I-R")
        self.assertEqual(row["association_status"], "restricted")
        self.assertIsNone(row["so"])
        self.assertIsNone(row["so_line"])


class ReturnTests(unittest.TestCase):
    def test_negative_return_is_magnitude_and_single_deduction(self):
        headers = [header("DN-O"), header("DN-R", is_return=1,
                                          return_against="DN-O")]
        items = [item("I-O", "DN-O", qty=8),
                 item("I-R", "DN-R", qty=-3, dn_detail="I-O")]
        result = build(headers, items)
        original, ret = line(result, "I-O"), line(result, "I-R")
        self.assertEqual(original["actual_qty"], 8.0)   # gross stays once
        self.assertEqual(ret["raw_signed_qty"], -3.0)
        self.assertEqual(ret["qty_magnitude"], 3.0)
        self.assertEqual(ret["actual_qty"], -3.0)
        self.assertEqual(sum(r["actual_qty"] for r in result["delivery_lines"]), 5.0)
        self.assertEqual(original["returned_qty"], 3.0)

    def test_positive_return_is_equivalent(self):
        headers = [header("DN-O"), header("DN-R", is_return=1,
                                          return_against="DN-O")]
        items = [item("I-O", "DN-O", qty=8),
                 item("I-R", "DN-R", qty=3, dn_detail="I-O")]
        result = build(headers, items)
        self.assertEqual(line(result, "I-R")["actual_qty"], -3.0)
        self.assertEqual(sum(r["actual_qty"] for r in result["delivery_lines"]), 5.0)

    def test_over_return_and_wrong_reference(self):
        headers = [header("DN-O"), header("DN-R", is_return=1,
                                          return_against="DN-O"),
                   header("DN-X", is_return=1)]
        items = [item("I-O", "DN-O", qty=2),
                 item("I-R", "DN-R", qty=-5, dn_detail="I-O"),
                 item("I-X", "DN-X", qty=-4, dn_detail="MISSING")]
        result = build(headers, items)
        self.assertEqual(line(result, "I-R")["excess_return_qty"], 3.0)
        self.assertEqual(line(result, "I-X")["return_status"],
                         "return_reference_missing")
        self.assertEqual(line(result, "I-X")["actual_qty"], 0.0)

    def test_cross_identity_and_draft_original_are_rejected(self):
        headers = [header("DN-O"), header("DN-R", is_return=1,
                                          return_against="DN-O"),
                   header("DN-D", docstatus=0), header("DN-RD", is_return=1,
                                                       return_against="DN-D")]
        items = [item("I-O", "DN-O", qty=8),
                 item("I-R", "DN-R", qty=-3, dn_detail="I-O", warehouse="OTHER"),
                 item("I-D", "DN-D", qty=8),
                 item("I-RD", "DN-RD", qty=-3, dn_detail="I-D")]
        result = build(headers, items)
        self.assertEqual(line(result, "I-R")["return_status"],
                         "return_identity_mismatch")
        self.assertEqual(line(result, "I-RD")["return_status"],
                         "return_reference_not_submitted")

    def test_inactive_lines_never_accumulate(self):
        headers = [header("DN-1"), header("DN-0", docstatus=0),
                   header("DN-2", docstatus=2, amended_from="DN-OLD")]
        items = [item("I-1", "DN-1", qty=8), item("I-0", "DN-0", qty=10),
                 item("I-2", "DN-2", qty=7)]
        result = build(headers, items)
        self.assertEqual(line(result, "I-1")["actual_qty"], 8.0)
        self.assertEqual(line(result, "I-0")["actual_qty"], 0.0)
        self.assertEqual(line(result, "I-2")["actual_qty"], 0.0)
        counts = result["coverage"]["conservation"]["row_counts"]
        self.assertEqual(counts["unknown_quantity"], 0)


class QuantityAndPhysicalTests(unittest.TestCase):
    def test_nan_infinity_and_none_stay_unknown(self):
        for bad in (float("nan"), float("inf"), None, "not-a-number"):
            result = build([header("DN-B")], [item("I-B", "DN-B", qty=bad)])
            row = line(result, "I-B")
            self.assertIsNone(row["qty"])
            self.assertIsNone(row["actual_qty"], bad)
            self.assertEqual(row["quantity_status"], "unknown")
            groups = result["coverage"]["conservation"]["groups"]
            self.assertEqual(groups[0]["unknown_quantity_rows"], 1)
            self.assertFalse(groups[0]["ok"])

    def test_multi_waybill_never_copies_line_qty(self):
        logistics = {"numbers_by_dn": {"DN-M": [{"number": "A"}, {"number": "B"}]},
                     "shipment_by_number": {}}
        result = build([header("DN-M")], [item("I-M", "DN-M", qty=60)],
                       logistics=logistics)
        rows = [r for r in result["physical_chain"] if r["stage"] == "shipment"]
        self.assertEqual(len(rows), 2)
        self.assertTrue(all(r["qty"] is None for r in rows))
        self.assertTrue(all(r["allocation"] == "allocation_unknown" for r in rows))

    def test_unknown_target_and_uom_mismatch_stay_unknown(self):
        result = build([header("DN-U")],
                       [item("I-U", "DN-U", qty=5, uom="箱", stock_uom="个",
                             stock_qty=5, conversion_factor=0)])
        row = line(result, "I-U")
        self.assertEqual(row["uom_status"], "unknown")
        self.assertEqual(row["destination_status"], "unknown")

    def test_conservation_is_group_scoped(self):
        headers = [header("DN-1"), header("DN-2")]
        items = [item("I-1", "DN-1", item_code=TARGET, qty=7, uom="个"),
                 item("I-2", "DN-2", item_code=OTHER, qty=3, uom="箱")]
        result = build(headers, items)
        groups = result["coverage"]["conservation"]["groups"]
        self.assertEqual(len(groups), 2)
        self.assertNotIn("actual_delivery_qty",
                         result["coverage"]["conservation"])
        self.assertTrue(all(row["ok"] for row in groups))


if __name__ == "__main__":
    unittest.main()
