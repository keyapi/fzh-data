# -*- coding: utf-8 -*-
"""Counterexample tests for DN-anchored delivery facts (pure builder)."""
import importlib.util
import sys
import types
import unittest
from pathlib import Path

# Load the module against a temporary frappe stub, then restore sys.modules so
# later test modules keep their own fake/real frappe.
_saved = {name: sys.modules.get(name)
          for name in ("frappe", "frappe.utils")}
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
         so_detail=None, against=None, dn_detail=None, idx=1, **over):
    row = {"name": name, "parent": parent, "idx": idx, "item_code": item_code,
           "item_name": item_code, "customer_item_code": "", "qty": qty,
           "uom": uom, "stock_qty": qty, "stock_uom": stock_uom,
           "conversion_factor": 1, "warehouse": "SRC", "target_warehouse": None,
           "against_sales_order": against, "so_detail": so_detail,
           "dn_detail": dn_detail}
    row.update(over)
    return row


def so_item(name, parent, item_code=TARGET, qty=100, uom="个"):
    return {"name": name, "parent": parent, "item_code": item_code,
            "qty": qty, "uom": uom, "stock_uom": uom}


def so_header(name, customer="C1", docstatus=1):
    return {"name": name, "customer": customer, "docstatus": docstatus}


def build(headers, items, so_headers=None, so_items=None, permitted=None,
          candidates=None, logistics=None, **kwargs):
    return df.build_delivery_facts(
        headers, items, so_headers or {}, so_items or [],
        permitted if permitted is not None else {h["name"] for h in (so_headers or {}).values()},
        candidates or {}, logistics or {}, observed_at="2026-10-30T10:00:00", **kwargs)


def line(result, name):
    return next(row for row in result["delivery_lines"]
                if row["delivery_note_item"] == name)


class AssociationAndLedgerTests(unittest.TestCase):
    def test_linked_70_plus_unlinked_10_keeps_overlap_unresolved(self):
        headers = [header("DN-L"), header("DN-U")]
        items = [item("I-L", "DN-L", qty=70, so_detail="SOI-1", against="SO-1"),
                 item("I-U", "DN-U", qty=10)]
        result = build(headers, items,
                       so_headers={"SO-1": so_header("SO-1")},
                       so_items=[so_item("SOI-1", "SO-1", qty=100)])
        fulfillment = result["so_fulfillment"][0]
        self.assertEqual(fulfillment["linked_delivered_qty"], 70.0)
        self.assertEqual(fulfillment["so_open_qty"], 30.0)
        self.assertEqual(fulfillment["potential_overlap_qty"], 10.0)
        self.assertEqual(fulfillment["confirmed_additional_supply_qty"], 20.0)
        actual = sum(row["actual_qty"] for row in result["delivery_lines"])
        self.assertEqual(actual, 80.0)

    def test_dn_without_so_is_preserved_with_physical_chain(self):
        result = build([header("DN-U")], [item("I-U", "DN-U", qty=12)],
                       logistics={"numbers_by_dn": {}, "shipment_by_number": {}})
        row = line(result, "I-U")
        self.assertEqual(row["association_status"], "unlinked")
        self.assertEqual(row["actual_qty"], 12.0)
        stages = [r["stage"] for r in result["physical_chain"]]
        self.assertIn("receipt", stages)
        self.assertIn("inventory", stages)

    def test_same_so_multiple_lines_same_item_is_ambiguous(self):
        result = build(
            [header("DN-A")],
            [item("I-A", "DN-A", qty=5, against="SO-1")],
            so_headers={"SO-1": so_header("SO-1")},
            so_items=[so_item("SOI-1", "SO-1"), so_item("SOI-2", "SO-1")])
        self.assertEqual(line(result, "I-A")["association_status"], "ambiguous")
        self.assertEqual(len(line(result, "I-A")["candidate_so_lines"]), 2)

    def test_scope_in_out_and_unknown(self):
        result = build(
            [header("DN-S")],
            [item("I-IN", "DN-S", item_code=TARGET),
             item("I-OUT", "DN-S", item_code=OTHER),
             item("I-UNK", "DN-S", item_code="")])
        self.assertEqual(line(result, "I-IN")["relevance_status"], "in_scope")
        self.assertEqual(line(result, "I-OUT")["relevance_status"], "out_of_scope")
        self.assertEqual(line(result, "I-UNK")["relevance_status"], "unknown")

    def test_so_item_a_but_dn_item_b_is_conflict(self):
        result = build(
            [header("DN-C")],
            [item("I-C", "DN-C", item_code=TARGET, qty=5,
                  so_detail="SOI-1", against="SO-1")],
            so_headers={"SO-1": so_header("SO-1")},
            so_items=[so_item("SOI-1", "SO-1", item_code=OTHER, qty=5)])
        row = line(result, "I-C")
        self.assertEqual(row["association_status"], "conflict")
        self.assertIn("so_item_code_mismatch", row["conflicts"])


class ReturnTests(unittest.TestCase):
    def test_unlinked_original_return_keeps_unlinked_and_nets(self):
        headers = [header("DN-O"), header("DN-R", is_return=1,
                                          return_against="DN-O")]
        items = [item("I-O", "DN-O", qty=8),
                 item("I-R", "DN-R", qty=3, dn_detail="I-O")]
        result = build(headers, items)
        original, ret = line(result, "I-O"), line(result, "I-R")
        self.assertEqual(original["returned_qty"], 3.0)
        self.assertEqual(original["actual_qty"], 5.0)
        self.assertEqual(ret["actual_qty"], -3.0)
        self.assertEqual(ret["association_status"], "unlinked")
        self.assertEqual(ret["return_status"], "return_matched")

    def test_over_return_and_wrong_reference_are_excess_or_missing(self):
        headers = [header("DN-O"), header("DN-R", is_return=1),
                   header("DN-X", is_return=1)]
        items = [item("I-O", "DN-O", qty=2),
                 item("I-R", "DN-R", qty=5, dn_detail="I-O"),
                 item("I-X", "DN-X", qty=4, dn_detail="MISSING")]
        result = build(headers, items)
        self.assertEqual(line(result, "I-R")["excess_return_qty"], 3.0)
        self.assertEqual(line(result, "I-X")["return_status"],
                         "return_reference_missing")
        self.assertEqual(line(result, "I-X")["actual_qty"], 0.0)

    def test_draft_and_cancelled_never_accumulate(self):
        headers = [header("DN-1"), header("DN-0", docstatus=0),
                   header("DN-2", docstatus=2, amended_from="DN-OLD")]
        items = [item("I-1", "DN-1", qty=8), item("I-0", "DN-0", qty=10),
                 item("I-2", "DN-2", qty=7)]
        result = build(headers, items)
        self.assertEqual(line(result, "I-1")["actual_qty"], 8.0)
        self.assertEqual(line(result, "I-0")["actual_qty"], 0.0)
        self.assertEqual(line(result, "I-2")["actual_qty"], 0.0)
        self.assertEqual(result["coverage"]["conservation"]["actual_delivery_qty"], 8.0)
        self.assertEqual(line(result, "I-2")["amended_from"], "DN-OLD")


class PhysicalAndUomTests(unittest.TestCase):
    def test_multi_waybill_never_copies_line_qty(self):
        logistics = {"numbers_by_dn": {"DN-M": [{"number": "A"}, {"number": "B"}]},
                     "shipment_by_number": {}}
        result = build([header("DN-M")], [item("I-M", "DN-M", qty=60)],
                       logistics=logistics)
        shipment_rows = [r for r in result["physical_chain"] if r["stage"] == "shipment"]
        self.assertEqual(len(shipment_rows), 2)
        self.assertTrue(all(r["qty"] is None for r in shipment_rows))
        self.assertTrue(all(r["allocation"] == "allocation_unknown"
                            for r in shipment_rows))

    def test_unknown_target_and_uom_mismatch_stay_unknown(self):
        result = build(
            [header("DN-U")],
            [item("I-U", "DN-U", qty=5, uom="箱", stock_uom="个",
                  stock_qty=5, conversion_factor=0)])
        row = line(result, "I-U")
        self.assertEqual(row["uom_status"], "unknown")
        self.assertEqual(row["destination_status"], "unknown")
        self.assertIn("conversion_unproven", row["unknown_reasons"])

    def test_restricted_flag_reaches_coverage(self):
        result = build([header("DN-R")], [item("I-R", "DN-R")], restricted=True)
        self.assertTrue(result["coverage"]["restricted"])

    def test_reversal_keeps_conservation_and_totals(self):
        headers = [header("DN-1"), header("DN-2")]
        items = [item("I-1", "DN-1", qty=7), item("I-2", "DN-2", qty=3)]
        forward = build(headers, items)
        reverse = build(headers, list(reversed(items)))
        self.assertEqual(forward["coverage"]["conservation"],
                         reverse["coverage"]["conservation"])
        self.assertEqual(sum(r["actual_qty"] for r in forward["delivery_lines"]),
                         sum(r["actual_qty"] for r in reverse["delivery_lines"]))


if __name__ == "__main__":
    unittest.main()
