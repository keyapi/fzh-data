"""Tests for signed Shipment -> Tongtool purchase receipt state machine."""
import unittest

from supply_chain_visibility.receipt_state import (
    ReceiptLine,
    ShipmentLink,
    reconcile_signed_receipts,
)


def link(shipment="SHIP-1", dn="DN-1", po=("PO-1",), signed="2026-10-20T10:00:00+08:00",
         qty=10, uom="个", sku="SKU-1", warehouse="WH-1", confidence="proven"):
    return ShipmentLink(shipment=shipment, dn=dn, po_codes=tuple(po or ()),
                        signed_at=signed, qty=qty, uom=uom, sku=sku,
                        warehouse=warehouse, identity_confidence=confidence)


def receipt(line_id="L1", po="PO-1", qty=10, at="2026-10-25T10:00:00+08:00",
            sku="SKU-1", warehouse="WH-1", uom="个", receipt_id="R1",
            semantics="increment", uom_proven=True, identity_proven=True):
    return ReceiptLine(receipt_id=receipt_id, line_id=line_id, po_code=po,
                       sku=sku, warehouse=warehouse, uom=uom, qty=qty,
                       effective_at=at, quantity_semantics=semantics,
                       uom_proven=uom_proven, identity_proven=identity_proven)


class AssociationTests(unittest.TestCase):
    def test_no_po_link_is_unknown(self):
        row = reconcile_signed_receipts([link(po=())], [])[0]
        self.assertEqual(row["status"], "unknown")
        self.assertEqual(row["exclusion_reason"], "no_po_link")

    def test_receipt_for_other_po_is_not_counted(self):
        row = reconcile_signed_receipts([link()], [receipt(po="PO-OTHER")])[0]
        self.assertEqual(row["status"], "signed_pending_tongtool_receipt")
        self.assertEqual(row["received_qty"], "0")
        self.assertEqual(row["unmatched_receipt_rows"], 1)

    def test_sku_uom_warehouse_mismatch_is_unknown(self):
        for bad in (receipt(sku="SKU-2"), receipt(uom="箱"), receipt(warehouse="WH-2")):
            row = reconcile_signed_receipts([link()], [bad])[0]
            self.assertEqual(row["status"], "unknown")
            self.assertEqual(row["exclusion_reason"], "receipt_identity_mismatch")


class StateMachineTests(unittest.TestCase):
    def test_signed_without_receipt_is_pending(self):
        row = reconcile_signed_receipts([link()], [])[0]
        self.assertEqual(row["status"], "signed_pending_tongtool_receipt")
        self.assertEqual(row["receipt_completion"], "pending")
        self.assertEqual(row["received_qty"], "0")
        self.assertEqual(row["pending_qty"], "10")
        self.assertEqual(row["received_evidence_status"], "known")
        self.assertIsNone(row["tongtool_receipt_at"])
        self.assertEqual(row["receipt_basis"], "signed_assumed")

    def test_partial_receipt_stays_pending(self):
        row = reconcile_signed_receipts(
            [link()], [receipt(qty=4, at="2026-10-25T10:00:00+08:00")])[0]
        self.assertEqual(row["status"], "signed_pending_tongtool_receipt")
        self.assertEqual(row["receipt_completion"], "partial")
        self.assertEqual(row["received_qty"], "4")
        self.assertEqual(row["pending_qty"], "6")
        self.assertEqual(row["tongtool_first_receipt_at"], "2026-10-25T10:00:00+08:00")
        self.assertIsNone(row["tongtool_receipt_at"])

    def test_full_receipt_closes_with_last_receipt_time(self):
        row = reconcile_signed_receipts(
            [link()],
            [receipt(line_id="L1", qty=4, at="2026-10-25T10:00:00+08:00"),
             receipt(line_id="L2", qty=6, at="2026-10-28T10:00:00+08:00")])[0]
        self.assertEqual(row["status"], "tongtool_received")
        self.assertEqual(row["receipt_completion"], "complete")
        self.assertEqual(row["received_qty"], "10")
        self.assertEqual(row["pending_qty"], "0")
        self.assertEqual(row["tongtool_first_receipt_at"], "2026-10-25T10:00:00+08:00")
        self.assertEqual(row["tongtool_last_receipt_at"], "2026-10-28T10:00:00+08:00")
        self.assertEqual(row["tongtool_receipt_at"], "2026-10-28T10:00:00+08:00")
        self.assertEqual(row["receipt_lag_days"], 8)

    def test_unknown_quantity_semantics_keeps_pending_unknown(self):
        row = reconcile_signed_receipts(
            [link()], [receipt(semantics="cumulative")])[0]
        self.assertEqual(row["status"], "unknown")
        self.assertEqual(row["exclusion_reason"], "quantity_semantics_unproven")
        self.assertIsNone(row["received_qty"])


class ConflictTests(unittest.TestCase):
    def test_duplicate_receipt_is_counted_once(self):
        rows = [receipt(line_id="L1", qty=4), receipt(line_id="L1", qty=4)]
        row = reconcile_signed_receipts([link()], rows)[0]
        self.assertEqual(row["received_qty"], "4")
        self.assertEqual(row["receipt_duplicates"], 1)

    def test_conflicting_receipt_payload_is_unknown(self):
        rows = [receipt(line_id="L1", qty=4), receipt(line_id="L1", qty=6)]
        row = reconcile_signed_receipts([link()], rows)[0]
        self.assertEqual(row["status"], "unknown")
        self.assertEqual(row["exclusion_reason"], "receipt_payload_conflict")

    def test_multi_link_same_receipt_group_is_allocation_unknown(self):
        rows = reconcile_signed_receipts(
            [link(shipment="S1", dn="DN-1"), link(shipment="S2", dn="DN-2")],
            [receipt(qty=10)])[0]
        self.assertEqual(rows["status"], "unknown")
        self.assertEqual(rows["exclusion_reason"], "receipt_allocation_unknown")

    def test_order_invariance_and_idempotency(self):
        rows = [receipt(line_id="L1", qty=4), receipt(line_id="L2", qty=6)]
        forward = reconcile_signed_receipts([link()], rows)[0]
        reverse = reconcile_signed_receipts([link()], list(reversed(rows)))[0]
        self.assertEqual(forward, reverse)


if __name__ == "__main__":
    unittest.main()
