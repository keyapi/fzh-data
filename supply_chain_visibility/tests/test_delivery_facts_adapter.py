# -*- coding: utf-8 -*-
"""Tests for the warehouse_restock delivery-facts adapter."""
import unittest

from warehouse_restock.delivery_facts_adapter import (
    APPROVED_TARGET_ITEMS, build_restock_delivery_view,
)

TARGET = "PK#KS0001-DM-100-GREY"
OTHER_TARGET = "PK#KS0001-DM-194-IVORY"
OUT = "COTTON-ROLL-1"


def line(item, qty, association="linked", docstatus=1, uom_status="known",
         line_id=None, relevance="in_scope"):
    return {
        "delivery_note": "DN-1", "delivery_note_item": line_id or item,
        "item_code": item, "actual_qty": qty, "qty": qty, "uom": "个",
        "docstatus": docstatus, "association_status": association,
        "relevance_status": relevance, "uom_status": uom_status,
    }


class AdapterTests(unittest.TestCase):
    def test_linked_and_unlinked_stay_visible_without_double_count(self):
        delivery = {
            "delivery_lines": [
                line(TARGET, 70, "linked", line_id="L1"),
                line(TARGET, 10, "unlinked", line_id="L2"),
                line(OUT, 5, "unlinked", line_id="L3", relevance="out_of_scope"),
            ],
            "coverage": {"conservation": {"actual_delivery_qty": 85}},
        }
        result = build_restock_delivery_view(
            delivery, channel_by_item={TARGET: "in_house"})
        row = next(r for r in result["rows"] if r["item_code"] == TARGET)
        self.assertEqual(row["actual_delivery_qty"], 80.0)
        self.assertEqual(row["linked_delivery_qty"], 70.0)
        self.assertEqual(row["unlinked_delivery_qty"], 10.0)
        self.assertEqual(row["suggested_action"],
                         "manual_review_unlinked_delivery")
        self.assertFalse(row["eligible_for_restock"])
        self.assertFalse(row["auto_order"])
        self.assertEqual(result["summary"]["out_of_scope_actual_delivery_qty"], 5.0)

    def test_unknown_uom_is_not_zero(self):
        delivery = {"delivery_lines": [
            line(TARGET, 12, "linked", uom_status="unknown", line_id="L1")]}
        row = next(r for r in build_restock_delivery_view(
            delivery, channel_by_item={TARGET: "in_house"})["rows"]
                   if r["item_code"] == TARGET)
        self.assertIsNone(row["actual_delivery_qty"])
        self.assertEqual(row["qty_status"], "unknown_uom")
        self.assertEqual(row["suggested_action"],
                         "manual_review_delivery_unknown")

    def test_items_without_observed_delivery_are_not_zero(self):
        row = next(r for r in build_restock_delivery_view(
            {"delivery_lines": []}, channel_by_item={
                OTHER_TARGET: "in_house"})["rows"]
                   if r["item_code"] == OTHER_TARGET)
        self.assertIsNone(row["actual_delivery_qty"])
        self.assertEqual(row["qty_status"], "no_observed_delivery")

    def test_fba_and_in_house_are_separate_rows(self):
        delivery = {"delivery_lines": [
            line(TARGET, 4, "linked", line_id="L1"),
            line(OTHER_TARGET, 6, "linked", line_id="L2"),
        ]}
        result = build_restock_delivery_view(
            delivery, fba_item_codes={TARGET},
            channel_by_item={OTHER_TARGET: "in_house"})
        channels = {r["item_code"]: r["channel"] for r in result["rows"]}
        self.assertEqual(channels[TARGET], "fba")
        self.assertEqual(channels[OTHER_TARGET], "in_house")

    def test_duplicate_delivery_identity_is_flagged(self):
        delivery = {"delivery_lines": [
            line(TARGET, 1, line_id="L1"), line(TARGET, 2, line_id="L1")]}
        result = build_restock_delivery_view(delivery)
        self.assertFalse(result["summary"]["duplicate_free"])
        self.assertEqual(result["summary"]["duplicate_line_ids"], ["L1"])

    def test_every_approved_item_has_a_row(self):
        result = build_restock_delivery_view({"delivery_lines": []})
        self.assertEqual(len(result["rows"]), len(APPROVED_TARGET_ITEMS))
        self.assertTrue(all(r["auto_order"] is False for r in result["rows"]))


if __name__ == "__main__":
    unittest.main()
