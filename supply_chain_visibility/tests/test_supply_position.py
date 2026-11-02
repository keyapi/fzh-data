# -*- coding: utf-8 -*-
"""Supply position rules: closure, partial, legacy, dedupe, net."""

import unittest

from supply_chain_visibility.supply_position import (
    DemandPosition,
    InventoryPosition,
    ManifestLine,
    PoManifest,
    PoStatus,
    build_supply_position,
    filter_positions,
)


def line(item="SKU-1", outcome="included", qty=10, uom="个", dn_item="I-1",
         reason=""):
    return ManifestLine(dn_item=dn_item, item_code=item, outcome=outcome,
                        qty=qty, uom=uom, contribution_qty=qty, reason=reason)


def manifest(lines=None, po="PO-1", source="audit", status="0",
             completed_at=None, warehouse="WH-1", scope="in_house",
             branch="CENTRADE"):
    return PoManifest(po_code=po, dn_name="DN-1", source=source, status=status,
                      completed_at=completed_at, lines=tuple(lines or []),
                      warehouse=warehouse, scope=scope, branch=branch)


def status(po="PO-1", raw="0", found=True, source_status="known",
           is_voided=False):
    return PoStatus(po_code=po, found=found, raw_status=raw, is_voided=is_voided,
                    source_status=source_status)


def rows_of(result, stage=None):
    return [row for row in result["rows"]
            if stage is None or row["stage"] == stage]


class ClosureTests(unittest.TestCase):
    def test_completed_closes_only_included_lines(self):
        result = build_supply_position(
            [manifest([line(), line(item="SKU-2", outcome="mapping_failed")])],
            [status(raw="3")])
        completed = rows_of(result, "po_completed")
        self.assertEqual([row["item_code"] for row in completed], ["SKU-1"])
        self.assertEqual(completed[0]["qty"], "0")
        uncovered = rows_of(result, "dn_goods_unclosed")
        self.assertEqual([row["item_code"] for row in uncovered], ["SKU-2"])
        self.assertIsNone(uncovered[0]["qty"])
        self.assertEqual(uncovered[0]["qty_status"], "unknown")
        self.assertIn("dn_goods_not_closed", uncovered[0]["flags"])

    def test_open_po_contributes_known_qty(self):
        result = build_supply_position([manifest([line(qty=7)])], [status(raw="0")])
        row = rows_of(result, "po_open")[0]
        self.assertEqual(row["qty"], "7")
        self.assertEqual(row["qty_status"], "known")

    def test_partial_arrival_does_not_allocate(self):
        result = build_supply_position([manifest([line(qty=7)])], [status(raw="1")])
        row = rows_of(result, "po_partial_allocation_unknown")[0]
        self.assertIsNone(row["qty"])
        self.assertEqual(row["qty_status"], "unknown")
        self.assertIn("allocation_unknown", row["flags"])

    def test_voided_contributes_zero(self):
        result = build_supply_position([manifest([line(qty=7)])],
                                       [status(raw="4", is_voided=True)])
        row = rows_of(result, "po_voided")[0]
        self.assertEqual(row["qty"], "0")

    def test_unknown_status_stays_unknown(self):
        result = build_supply_position([manifest([line(qty=7)])],
                                       [status(raw="9")])
        row = rows_of(result, "po_status_unknown")[0]
        self.assertIsNone(row["qty"])
        self.assertEqual(row["qty_status"], "unknown")

    def test_source_error_stays_unknown(self):
        result = build_supply_position(
            [manifest([line(qty=7)])],
            [status(found=False, raw=None, source_status="source_error")])
        row = rows_of(result, "po_status_unknown")[0]
        self.assertEqual(row["reason"], "status_source_error")

    def test_rule_excluded_is_not_supply_or_demand(self):
        result = build_supply_position(
            [manifest([line(outcome="rule_excluded")])], [status(raw="0")])
        self.assertEqual(result["rows"], [])
        self.assertEqual(result["summary"]["outcomes"]["rule_excluded"], 1)


class LegacyTests(unittest.TestCase):
    def test_legacy_manifest_is_not_fabricated_and_does_not_block(self):
        result = build_supply_position([
            manifest(source="legacy", lines=[], po="PO-OLD"),
            manifest(lines=[line(item="SKU-9")], po="PO-NEW"),
        ], [status(po="PO-NEW", raw="0")])
        self.assertEqual(result["legacy"][0]["po_code"], "PO-OLD")
        self.assertEqual(result["legacy"][0]["reason"],
                         "no_creation_audit_manifest")
        self.assertIsNone(result["legacy"][0]["qty"])
        open_rows = rows_of(result, "po_open")
        self.assertEqual([row["item_code"] for row in open_rows], ["SKU-9"])


class SnapshotDedupeTests(unittest.TestCase):
    def test_inventory_include_declared_prevents_double_count(self):
        result = build_supply_position(
            [manifest([line(qty=5)])], [status(raw="0")],
            [InventoryPosition(sku="SKU-1", warehouse="WH-1", uom="个",
                               available=8, includes_po_codes=("PO-1",))])
        row = rows_of(result, "po_in_snapshot")[0]
        self.assertEqual(row["qty"], "0")
        self.assertIn("inventory_includes_po", row["flags"])
        net = result["net"]["rows"][0]
        self.assertEqual(net["on_hand_qty"], "8")
        self.assertEqual(net["po_open_qty"], "0")

    def test_completion_after_snapshot_is_flagged_not_vanished(self):
        result = build_supply_position(
            [manifest([line()], status="3", completed_at="2026-11-02T12:00:00+00:00")],
            [status(raw="3")],
            [InventoryPosition(sku="SKU-1", warehouse="WH-1", uom="个",
                               available=0, as_of="2026-11-01T00:00:00+00:00",
                               window_start="2026-11-01T00:00:00+00:00",
                               window_end="2026-11-01T23:59:59+00:00")])
        row = rows_of(result, "po_completed")[0]
        self.assertIn("post_snapshot_completion", row["flags"])
        self.assertIn("completed_not_in_snapshot", row["flags"])

    def test_missing_inventory_source_is_not_zero(self):
        result = build_supply_position(
            [manifest([line()])], [status(raw="0")],
            [InventoryPosition(sku="SKU-1", warehouse="WH-1", uom="个",
                               available=None, source_status="unavailable")])
        on_hand = rows_of(result, "on_hand")[0]
        self.assertIsNone(on_hand["qty"])
        self.assertIn("inventory_source_unavailable", on_hand["flags"])
        self.assertTrue(result["summary"]["inventory_snapshot_available"] is False)


class FilterAndNetTests(unittest.TestCase):
    def test_scope_and_branch_filter(self):
        result = build_supply_position([
            manifest([line(item="SKU-1")], po="PO-1", branch="CENTRADE"),
            manifest([line(item="SKU-2")], po="PO-2", scope="external_fba"),
        ], [status(po="PO-1", raw="0"), status(po="PO-2", raw="0")])
        self.assertEqual(len(filter_positions(result["rows"], scope="in_house",
                                              branch="CENTRADE")), 1)
        self.assertEqual(len(filter_positions(result["rows"], scope="external_fba")), 1)

    def test_net_builds_min_and_max_per_key(self):
        result = build_supply_position(
            [manifest([line(qty=4)])], [status(raw="0")],
            [InventoryPosition(sku="SKU-1", warehouse="WH-1", uom="个",
                               available=8, branch="CENTRADE")],
            [DemandPosition(sku="SKU-1", uom="个", open_qty=6,
                            warehouse="WH-1", branch="CENTRADE")])
        net = result["net"]["rows"][0]
        self.assertEqual(net["on_hand_qty"], "8")
        self.assertEqual(net["po_open_qty"], "4")
        self.assertEqual(net["demand_qty"], "6")
        self.assertEqual(net["net_min_qty"], "2")
        self.assertEqual(net["net_max_qty"], "6")

    def test_unknown_input_keeps_group_status_unknown(self):
        result = build_supply_position(
            [], [], [],
            [DemandPosition(sku="SKU-1", uom="个", open_qty=None)])
        net = result["net"]["rows"][0]
        self.assertEqual(net["qty_status"], "unknown")
        self.assertEqual(net["unknown_rows"], 1)

    def test_unknown_demand_does_not_become_zero(self):
        result = build_supply_position(
            [], [], [],
            [DemandPosition(sku="SKU-1", uom="个", open_qty=None)])
        demand = rows_of(result, "demand")[0]
        self.assertIsNone(demand["qty"])


if __name__ == "__main__":
    unittest.main()
