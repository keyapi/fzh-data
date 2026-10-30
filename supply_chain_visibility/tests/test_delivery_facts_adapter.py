# -*- coding: utf-8 -*-
"""Tests for the warehouse_restock delivery-facts adapter (v2)."""
import hashlib
import json
import unittest

from warehouse_restock.delivery_facts_adapter import (
    build_restock_delivery_view,
)

TARGET = "PK#KS0001-DM-100-GREY"
OTHER = "PK#KS0001-DM-194-IVORY"


def scope(codes=(TARGET, OTHER)):
    payload = {"status": "provided", "source": "warehouse_restock",
               "version": "scope-v2", "items": sorted(codes)}
    canonical = json.dumps({"source": payload["source"],
                            "version": payload["version"],
                            "items": sorted(codes)}, sort_keys=True)
    payload["hash"] = hashlib.sha256(canonical.encode("utf-8")).hexdigest()
    return payload


def delivery(lines, *, scope_obj=None, partial=False):
    return {
        "schema_version": "supply-facts/v3", "rule_version": "2026-10-30.2",
        "implementation_version": "key_test.delivery_facts@2026-10-30.2",
        "scope": scope_obj if scope_obj is not None else scope(),
        "coverage": {"scope": scope_obj if scope_obj is not None else scope()},
        "pagination": {"exhausted": not partial, "partial": partial},
        "delivery_lines": lines, "ambiguity_pools": [],
    }


def line(item=TARGET, qty=10, uom="个", channel=None, destination="WH-1",
         association="linked", line_id="L1", status=1):
    return {
        "delivery_note": "DN-1", "delivery_note_item": line_id,
        "item_code": item, "uom": uom, "docstatus": status,
        "actual_qty": qty, "association_status": association,
        "target_warehouse": destination, "warehouse": destination,
        "channel": channel, "relevance_status": "in_scope",
    }


class GatesTests(unittest.TestCase):
    def test_missing_scope_keeps_e_pending(self):
        result = build_restock_delivery_view(
            delivery([line()], scope_obj={"status": "pending"}))
        self.assertEqual(result["status"], "scope_pending")
        self.assertEqual(result["rows"], [])

    def test_partial_snapshot_is_rejected(self):
        with self.assertRaises(ValueError):
            build_restock_delivery_view(delivery([line()], partial=True))

    def test_scope_hash_mismatch_is_rejected(self):
        bad = scope()
        bad["hash"] = "0" * 64
        with self.assertRaises(ValueError):
            build_restock_delivery_view(delivery([line()], scope_obj=bad))

    def test_missing_version_is_rejected(self):
        payload = delivery([line()])
        del payload["implementation_version"]
        with self.assertRaises(ValueError):
            build_restock_delivery_view(payload)


class GroupingTests(unittest.TestCase):
    def test_item_uom_channel_destination_are_separate_rows(self):
        lines = [
            line(line_id="L1", channel=None),
            line(line_id="L2", channel="in_house"),
            line(line_id="L3", uom="箱", qty=2),
            line(line_id="L4", destination="WH-2", qty=1),
        ]
        result = build_restock_delivery_view(
            delivery(lines), fba_item_codes={TARGET},
            channel_by_item={TARGET: "in_house"})
        target_rows = [r for r in result["rows"] if r["item_code"] == TARGET]
        keys = {(r["uom"], r["channel"], r["destination"]) for r in target_rows}
        self.assertEqual(len(target_rows), 3)  # 个/in_house/WH-1, 箱/in_house/WH-1, 个/in_house/WH-2
        self.assertIn(("箱", "in_house", "WH-1"), keys)
        self.assertIn(("个", "in_house", "WH-2"), keys)
        # No cross-UOM sum: the two UOM rows stay separate.
        for row in target_rows:
            self.assertFalse(row["auto_order"])

    def test_fba_and_in_house_are_not_summed(self):
        lines = [line(line_id="L1", qty=4, channel="fba"),
                 line(line_id="L2", qty=6, channel="in_house")]
        result = build_restock_delivery_view(delivery(lines))
        rows = [r for r in result["rows"] if r["item_code"] == TARGET]
        self.assertEqual({r["channel"] for r in rows}, {"fba", "in_house"})
        self.assertEqual(len(rows), 2)
        self.assertEqual(sorted(r["actual_delivery_qty"] for r in rows), [4.0, 6.0])

    def test_unknown_quantity_is_not_zero(self):
        lines = [line(line_id="L1", qty=None)]
        result = build_restock_delivery_view(delivery(lines))
        row = next(r for r in result["rows"] if r["item_code"] == TARGET)
        self.assertIsNone(row["actual_delivery_qty"])
        self.assertEqual(row["qty_status"], "unknown")

    def test_item_without_delivery_is_not_zero(self):
        result = build_restock_delivery_view(delivery([]))
        row = next(r for r in result["rows"] if r["item_code"] == OTHER)
        self.assertIsNone(row["actual_delivery_qty"])
        self.assertEqual(row["qty_status"], "no_observed_delivery")

    def test_duplicate_identity_is_flagged(self):
        result = build_restock_delivery_view(
            delivery([line(line_id="L1"), line(line_id="L1", qty=2)]))
        self.assertFalse(result["summary"]["duplicate_free"])


if __name__ == "__main__":
    unittest.main()
