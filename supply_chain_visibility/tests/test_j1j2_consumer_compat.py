# -*- coding: utf-8 -*-
"""J1/J2 API shapes -> #323 consumer, offline end-to-end compatibility."""

import unittest

from supply_chain_visibility.supply_position import assemble_input, build_position
from warehouse_restock.delivery_facts_adapter import _scope_hash

AS_OF = "2026-11-02T10:00:00+00:00"


def _scope():
    scope = {"status": "provided", "source": "approved_b",
             "version": "Bv6r10", "items": [{"item_code": "SKU-1"}]}
    scope["hash"] = _scope_hash(scope)
    return scope


def _delivery():
    scope = _scope()
    return {
        "schema_version": "supply-facts/v3", "rule_version": "2026-10-30.5",
        "implementation_version": "key_test.delivery_facts@2026-10-30.5",
        "scope": scope, "coverage": {"scope": scope},
        "snapshot_id": "snap-1",
        "pagination": {"exhausted": True, "partial": False, "total": 1},
        "delivery_lines": [{
            "delivery_note": "DN-1", "delivery_note_item": "DNI-1",
            "item_code": "SKU-1", "uom": "个", "qty": 5, "actual_qty": 5,
            "is_return": 0, "docstatus": 1, "customer": "C1",
            "quantity_status": "known", "relevance_status": "in_scope",
            "warehouse": "WH-1", "target_warehouse": "WH-1",
            "purpose": "branch",
        }],
    }


def _mappings():
    return {"source": "approved_b", "version": "Bv6r10", "rows": [{
        "delivery_note": "DN-1", "dn_item": "DNI-1", "item_code": "SKU-1",
        "tt_sku": "S1", "warehouse": "WH-1", "uom": "个",
        "purpose": "branch", "evidence": "Bv6r10 approved row"}]}


def _audit():
    # Shape produced by the new delivery_plan get_creation_audit.
    return {"delivery_note": "DN-1", "pagination": {
        "limit": 50, "offset": 0, "returned": 1, "total": 1,
        "exhausted": True, "partial": False, "next_offset": None},
        "creations": [{
            "name": "TPO-1", "delivery_note": "DN-1", "status": "confirmed",
            "purchase_order_code": "PO-1",
            "lines": [{"dn_item": "DNI-1", "item_code": "SKU-1", "qty": 5,
                       "uom": "个", "tt_sku": "S1", "outcome": "included",
                       "contribution_qty": 5,
                       "merged_goods_detail_id": "G1", "reason": ""}]}]}


def _status_batch(raw="3"):
    # Shape produced by the new get_purchase_order_status_many.
    return {"requested": 1, "returned": 1, "queried": 1, "observed_at": AS_OF,
            "exhausted": False, "partial": False, "termination_reason": "completed",
            "results": {"PO-1": {
                "found": True, "status": raw, "is_voided": raw == "4",
                "source_status": "known", "observed_at": AS_OF,
                "cached": False, "cache_generated_at": AS_OF,
                "identity": {"purchaseOrderCode": "PO-1"}}}}


class CompatTests(unittest.TestCase):
    def _build(self, raw="3"):
        payload = assemble_input(delivery=_delivery(), mappings=_mappings(),
                                 audits=[_audit()], statuses=[_status_batch(raw)],
                                 as_of=AS_OF)
        return build_position(payload)

    def test_completed_po_closes_only_included_line(self):
        result = self._build("3")
        row = next(r for r in result["rows"] if r["item_code"] == "SKU-1")
        self.assertEqual(row["po_completed_assumed_qty"], 5.0)
        self.assertEqual(row["open_po_qty"], 0.0)
        self.assertFalse(row["netting_ready"])
        self.assertFalse(row["auto_order"])

    def test_open_po_stays_open(self):
        row = next(r for r in self._build("0")["rows"]
                   if r["item_code"] == "SKU-1")
        self.assertEqual(row["open_po_qty"], 5.0)
        self.assertEqual(row["po_completed_assumed_qty"], 0.0)

    def test_missing_lines_are_not_fabricated(self):
        audit = _audit()
        audit["creations"][0]["lines"] = []
        payload = assemble_input(delivery=_delivery(), mappings=_mappings(),
                                 audits=[audit], statuses=[_status_batch("3")],
                                 as_of=AS_OF)
        result = build_position(payload)
        row = next(r for r in result["rows"] if r["item_code"] == "SKU-1")
        self.assertEqual(row["po_completed_assumed_qty"], 0.0)
        self.assertIsNone(row["unresolved_qty"] if row["unknown_quantity_lines"] else None)


if __name__ == "__main__":
    unittest.main()
