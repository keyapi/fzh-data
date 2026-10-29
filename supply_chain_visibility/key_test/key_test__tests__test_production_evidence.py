"""Acceptance tests for the step-3 production evidence layer (pure, no Frappe)."""
import math
import unittest

from key_test.production_evidence import (
    aggregate_wo_evidence, build_wo_evidence, rollup_line_evidence,
)


def op(name, operation, seq, corrective=0, **extra):
    row = {"name": name, "operation": operation, "sequence_id": seq,
           "is_corrective_operation": corrective}
    row.update(extra)
    return row


def jc(operation_id, tn="", qty=1, status="Completed", docstatus=1,
       start=None, end=None, operation=None, name=None, **extra):
    row = {
        "name": name or "JC-%s-%s-%s" % (operation_id, tn or "batch", qty),
        "operation_id": operation_id,
        "operation": operation or "",
        "tracking_number": tn,
        "total_completed_qty": qty,
        "status": status,
        "docstatus": docstatus,
        "actual_start_date": start,
        "actual_end_date": end,
    }
    row.update(extra)
    return row


def tn(name, qty, **extra):
    row = {"name": name, "qty": qty}
    row.update(extra)
    return row


def finished(qty, item="FG", uom="个", **extra):
    row = {"is_finished_item": 1, "item_code": item, "qty": qty, "uom": uom,
           "stock_uom": uom, "t_warehouse": "WH"}
    row.update(extra)
    return row


def se(name, items, docstatus=1, is_return=0, posting_date="2026-01-01",
       posting_time="10:00:00", work_order="WO-1", **extra):
    row = {"name": name, "work_order": work_order, "purpose": "Manufacture",
           "stock_entry_type": "Manufacture", "docstatus": docstatus,
           "is_return": is_return, "posting_date": posting_date,
           "posting_time": posting_time, "items": items}
    row.update(extra)
    return row


def qi(name, status="Accepted", docstatus=1, ref_type="Job Card", ref_name="JC-1",
       item="FG", coverage=None, report_date="2026-01-01", **extra):
    row = {"name": name, "status": status, "docstatus": docstatus,
           "reference_type": ref_type, "reference_name": ref_name,
           "item_code": item, "report_date": report_date,
           "coverage_qty": coverage}
    row.update(extra)
    return row


def build(ops, jcs, tns=None, ses=None, qis=None, qty=10, stock_uom="个",
          order_uom=None, availability=None, docstatus=1, observed_at=None):
    wo = {"name": "WO-1", "qty": qty, "stock_uom": stock_uom,
          "production_item": "FG", "docstatus": docstatus}
    return build_wo_evidence(
        wo, ops, jcs, tracking_numbers=tns or [], stock_entries=ses or [],
        quality_inspections=qis or [], order_uom=order_uom,
        availability=availability, observed_at=observed_at)


class FirstProcessTests(unittest.TestCase):
    def test_first_process_done_but_later_ops_not_complete(self):
        ops = [op("OP-CUT", "裁剪", 1), op("OP-SEW", "缝制", 2), op("OP-QC", "质检", 3)]
        result = build(ops, [jc("OP-CUT", "T1", 8)], [tn("T1", 8)], qty=8)
        self.assertEqual(result["first_process_done"]["qty_proven"], 8)
        self.assertEqual(result["all_process_done"]["qty_proven"], 0)
        self.assertEqual(result["qc_performed"]["qty_proven"], 0)

    def test_partial_all_process_counts_only_complete_tracking_units(self):
        ops = [op("OP-CUT", "裁剪", 1), op("OP-SEW", "缝制", 2), op("OP-QC", "质检", 3)]
        jcs, tns = [], []
        for idx in range(4):
            name = "T%d" % (idx + 1)
            tns.append(tn(name, 1))
            for oid in ("OP-CUT", "OP-SEW", "OP-QC"):
                jcs.append(jc(oid, name, 1))
        for idx in range(4, 8):
            name = "T%d" % (idx + 1)
            tns.append(tn(name, 2))
            jcs.append(jc("OP-CUT", name, 2))
        result = build(ops, jcs, tns, qty=12)
        self.assertEqual(result["first_process_done"]["qty_proven"], 12)
        self.assertEqual(result["all_process_done"]["qty_proven"], 4)

    def test_qc_can_run_ahead_of_all_process(self):
        ops = [op("OP-CUT", "裁剪", 1), op("OP-SEW", "缝制", 2), op("OP-QC", "质检", 3)]
        jcs, tns = [], []
        for idx in range(11):
            name = "T%d" % (idx + 1)
            tns.append(tn(name, 1))
            for oid in ("OP-CUT", "OP-SEW", "OP-QC"):
                jcs.append(jc(oid, name, 1))
        for idx in range(11, 16):
            name = "T%d" % (idx + 1)
            tns.append(tn(name, 1))
            jcs.append(jc("OP-QC", name, 1))
        result = build(ops, jcs, tns, qty=36)
        self.assertEqual(result["all_process_done"]["qty_proven"], 11)
        self.assertEqual(result["qc_performed"]["qty_proven"], 16)

    def test_qc_wip_is_not_performed_or_passed(self):
        ops = [op("OP-CUT", "裁剪", 1), op("OP-SEW", "缝制", 2), op("OP-QC", "质检", 3)]
        jcs, tns = [], []
        for idx in range(10):
            name = "T%d" % (idx + 1)
            tns.append(tn(name, 1))
            jcs.append(jc("OP-CUT", name, 1))
            jcs.append(jc("OP-SEW", name, 1))
            jcs.append(jc("OP-QC", name, 1, status="Work In Progress"))
        result = build(ops, jcs, tns, qty=10,
                       ses=[se("SE-1", [finished(6)])])
        self.assertEqual(result["all_process_done"]["qty_proven"], 0)
        self.assertEqual(result["qc_performed"]["qty_proven"], 0)
        self.assertIsNone(result["qc_passed"]["qty_proven"])
        self.assertEqual(result["stock_in_posted"]["qty_proven"], 6)


class QcTests(unittest.TestCase):
    def test_completed_qc_card_without_qi_is_performed_not_passed(self):
        ops = [op("OP-CUT", "裁剪", 1), op("OP-QC", "质检", 2)]
        jcs, tns = [], []
        for idx in range(10):
            name = "T%d" % (idx + 1)
            tns.append(tn(name, 1))
            jcs.append(jc("OP-CUT", name, 1))
            jcs.append(jc("OP-QC", name, 1))
        result = build(ops, jcs, tns, qty=10)
        self.assertEqual(result["qc_performed"]["qty_proven"], 10)
        self.assertIsNone(result["qc_passed"]["qty_proven"])
        self.assertIn("qc_result_not_recorded", result["qc_passed"]["reasons"])

    def test_qi_accepted_without_coverage_quantity_is_unknown(self):
        ops = [op("OP-CUT", "裁剪", 1), op("OP-QC", "质检", 2)]
        jcs, tns = [], []
        for idx in range(10):
            name = "T%d" % (idx + 1)
            tns.append(tn(name, 1))
            jcs.append(jc("OP-CUT", name, 1))
            jcs.append(jc("OP-QC", name, 1))
        qis = [qi("QI-1", status="Accepted", coverage=None,
                  sample_size=5, ref_name=jcs[0]["name"])]
        result = build(ops, jcs, tns, qty=10, qis=qis)
        self.assertEqual(result["qc_passed"]["status"], "Accepted")
        self.assertIsNone(result["qc_passed"]["qty_proven"])
        self.assertIn("coverage_qty_not_available", result["qc_passed"]["reasons"])

    def test_qi_work_order_reference_is_rejected(self):
        ops = [op("OP-CUT", "裁剪", 1), op("OP-QC", "质检", 2)]
        jcs = [jc("OP-CUT", "T1", 1), jc("OP-QC", "T1", 1)]
        result = build(ops, jcs, [tn("T1", 1)], qty=1,
                       qis=[qi("QI-1", ref_type="Work Order", ref_name="WO-1")])
        self.assertIsNone(result["qc_passed"]["qty_proven"])
        self.assertIn("qi_reference_type_invalid", [c["code"] for c in result["qc_passed"]["conflicts"]])


class StockInTests(unittest.TestCase):
    def test_draft_stock_entry_is_not_posted(self):
        ops = [op("OP-CUT", "裁剪", 1), op("OP-QC", "质检", 2)]
        jcs = [jc("OP-CUT", "T1", 36), jc("OP-QC", "T1", 36)]
        result = build(ops, jcs, [tn("T1", 36)], qty=36,
                       ses=[se("SE-DRAFT", [finished(36)], docstatus=0)])
        self.assertEqual(result["stock_in_posted"]["qty_proven"], 0)

    def test_submitted_stock_entry_net_quantity(self):
        ops = [op("OP-CUT", "裁剪", 1)]
        jcs = [jc("OP-CUT", "T1", 4.5)]
        result = build(ops, jcs, [tn("T1", 4.5)], qty=4.5,
                       ses=[se("SE-1", [finished(4.5)], docstatus=1)])
        self.assertEqual(result["stock_in_posted"]["qty_proven"], 4.5)

    def test_cancelled_stock_entry_is_excluded(self):
        ops = [op("OP-CUT", "裁剪", 1)]
        jcs = [jc("OP-CUT", "T1", 3)]
        result = build(ops, jcs, [tn("T1", 3)], qty=3, ses=[
            se("SE-OK", [finished(3)], docstatus=1),
            se("SE-DRAFT", [finished(2)], docstatus=0),
            se("SE-CANCELLED", [finished(1)], docstatus=2),
        ])
        self.assertEqual(result["stock_in_posted"]["qty_proven"], 3)

    def test_stock_return_sign_is_normalized(self):
        for raw_return in (10, -10):
            with self.subTest(raw_return=raw_return):
                ops = [op("OP-CUT", "裁剪", 1)]
                result = build(
                    ops, [], [], qty=100,
                    ses=[se("SE-GROSS", [finished(100)]),
                         se("SE-RET", [finished(raw_return)], is_return=1)])
                stock = result["stock_in_posted"]
                self.assertEqual(stock["components"]["gross_qty"], 100)
                self.assertEqual(stock["components"]["return_qty"], 10)
                self.assertEqual(stock["qty_proven"], 90)

    def test_return_with_mismatched_item_is_conflict(self):
        ops = [op("OP-CUT", "裁剪", 1)]
        result = build(ops, [], [], qty=100, ses=[
            se("SE-GROSS", [finished(100)]),
            se("SE-RET", [finished(10, item="OTHER")], is_return=1),
        ])
        self.assertIsNone(result["stock_in_posted"]["qty_proven"])
        self.assertIn("return_unallocated", [c["code"] for c in result["stock_in_posted"]["conflicts"]])

    def test_stock_entry_does_not_prove_process_or_qc(self):
        ops = [op("OP-CUT", "裁剪", 1), op("OP-QC", "质检", 2)]
        result = build(ops, [], [], qty=10, ses=[se("SE-1", [finished(6)])])
        self.assertEqual(result["all_process_done"]["qty_proven"], 0)
        self.assertEqual(result["qc_passed"]["qty_proven"] is None, True)
        self.assertEqual(result["stock_in_posted"]["qty_proven"], 6)


class IdentityAndDedupTests(unittest.TestCase):
    def test_batch_and_tracking_cards_are_not_summed(self):
        ops = [op("OP-CUT", "裁剪", 1), op("OP-SEW", "缝制", 2), op("OP-QC", "质检", 3)]
        jcs = [jc("OP-CUT", "T1", 36), jc("OP-SEW", "T1", 36), jc("OP-QC", "T1", 36)]
        jcs += [jc("OP-CUT", "", 36), jc("OP-SEW", "", 36), jc("OP-QC", "", 36)]
        result = build(ops, jcs, [tn("T1", 36)], qty=36)
        self.assertEqual(result["first_process_done"]["qty_proven"], 36)
        self.assertEqual(result["first_process_done"]["qty_estimated"], 36)
        self.assertIsNone(result["all_process_done"]["qty_proven"])
        self.assertEqual(result["all_process_done"]["qty_estimated"], 36)
        self.assertNotEqual(result["all_process_done"]["qty_proven"], 72)

    def test_batch_pool_without_identity_is_estimated_not_proven(self):
        ops = [op("OP-CUT", "裁剪", 1), op("OP-SEW", "缝制", 2), op("OP-QC", "质检", 3)]
        jcs = [jc("OP-CUT", "", 36), jc("OP-SEW", "", 36), jc("OP-QC", "", 36)]
        jcs.append(jc("OP-CUT", "T1", 36))
        result = build(ops, jcs, [tn("T1", 36)], qty=36)
        self.assertEqual(result["first_process_done"]["qty_proven"], 36)
        self.assertEqual(result["first_process_done"]["qty_estimated"], 36)
        self.assertIsNone(result["all_process_done"]["qty_proven"])
        self.assertEqual(result["all_process_done"]["qty_estimated"], 36)

    def test_different_units_complete_different_ops_do_not_use_min(self):
        ops = [op("OP-CUT", "裁剪", 1), op("OP-SEW", "缝制", 2), op("OP-QC", "质检", 3)]
        result = build(ops, [jc("OP-CUT", "T1", 1), jc("OP-SEW", "T2", 1)],
                       [tn("T1", 1), tn("T2", 1)], qty=2)
        self.assertEqual(result["all_process_done"]["qty_proven"], 0)
        self.assertNotEqual(result["all_process_done"]["qty_proven"], 1)

    def test_corrective_operations_are_excluded_from_required_set(self):
        ops = [op("OP-CUT", "裁剪", 1), op("OP-SEW", "缝制", 2),
               op("OP-QC", "质检", 3), op("OP-REWORK", "缝制返工", 4, corrective=1)]
        jcs = [jc("OP-CUT", "T1", 5), jc("OP-SEW", "T1", 5),
               jc("OP-QC", "T1", 5), jc("OP-REWORK", "T1", 5)]
        result = build(ops, jcs, [tn("T1", 5)], qty=5)
        self.assertEqual(result["all_process_done"]["qty_proven"], 5)
        self.assertEqual([o["operation"] for o in result["required_operations"]],
                         ["裁剪", "缝制", "质检"])

    def test_multiple_work_orders_are_not_collapsed(self):
        ops = [op("OP-CUT", "裁剪", 1)]
        r1 = build(ops, [jc("OP-CUT", "T1", 3)], [tn("T1", 3)], qty=3)
        r2 = build(ops, [jc("OP-CUT", "T2", 4)], [tn("T2", 4)], qty=4)
        rollup = aggregate_wo_evidence([r1, r2])
        self.assertEqual(len(rollup["work_orders"]), 2)
        self.assertIsNone(rollup["qty_proven"])
        self.assertEqual([w["wo"] for w in rollup["work_orders"]], ["WO-1", "WO-1"])

    def test_duplicate_operation_names_without_operation_id_are_ambiguous(self):
        ops = [op("OP-A", "缝制", 1), op("OP-B", "缝制", 2)]
        bad = jc("", "T1", 1, operation="缝制")
        bad["operation_id"] = None
        result = build(ops, [bad], [tn("T1", 1)], qty=1)
        self.assertIsNone(result["all_process_done"]["qty_proven"])
        self.assertEqual(result["all_process_done"]["confidence"], "unknown")
        self.assertIn("ambiguous_operation_name",
                      [c["code"] for c in result["all_process_done"]["conflicts"]])

    def test_operation_id_not_found_does_not_fall_back_to_name(self):
        ops = [op("OP-CUT", "裁剪", 1)]
        result = build(ops, [jc("OP-MISSING", "T1", 1, operation="裁剪")],
                       [tn("T1", 1)], qty=1)
        self.assertIsNone(result["all_process_done"]["qty_proven"])
        self.assertEqual(result["all_process_done"]["confidence"], "unknown")
        self.assertIn("operation_id_not_found",
                      [c["code"] for c in result["all_process_done"]["conflicts"]])


class TimeAndBoundaryTests(unittest.TestCase):
    def test_first_process_uses_completion_end_time(self):
        ops = [op("OP-CUT", "裁剪", 1)]
        result = build(ops, [jc("OP-CUT", "T1", 1,
                                start="2026-01-01 08:00:00",
                                end="2026-01-01 17:00:00")],
                       [tn("T1", 1)], qty=1)
        ev = result["first_process_done"]
        self.assertEqual(ev["started_at"], "2026-01-01 08:00:00")
        self.assertEqual(ev["completed_at"], "2026-01-01 17:00:00")

    def test_partial_missing_completion_time_is_not_faked_by_other_max(self):
        ops = [op("OP-CUT", "裁剪", 1)]
        jcs = [
            jc("OP-CUT", "T1", 1, start="2026-01-01 08:00:00", end="2026-01-01 09:00:00"),
            jc("OP-CUT", "T2", 1, start="2026-01-01 10:00:00", end=None),
        ]
        result = build(ops, jcs, [tn("T1", 1), tn("T2", 1)], qty=2)
        ev = result["first_process_done"]
        self.assertEqual(ev["qty_proven"], 2)
        self.assertIsNone(ev["completed_at"])
        self.assertEqual(ev["time_status"], "partial_missing")

    def test_unit_mismatch_is_unknown(self):
        ops = [op("OP-CUT", "裁剪", 1)]
        result = build(ops, [jc("OP-CUT", "T1", 1)], [tn("T1", 1)],
                       qty=1, stock_uom="个", order_uom="箱")
        ev = result["all_process_done"]
        self.assertIsNone(ev["qty_proven"])
        self.assertEqual(ev["confidence"], "unknown")
        self.assertIn("unit_mismatch", ev["reasons"])

    def test_permission_restricted_is_unknown_not_zero(self):
        ops = [op("OP-CUT", "裁剪", 1)]
        result = build(ops, [jc("OP-CUT", "T1", 1)], [tn("T1", 1)], qty=1,
                       availability={"job_cards": False})
        ev = result["all_process_done"]
        self.assertIsNone(ev["qty_proven"])
        self.assertEqual(ev["confidence"], "unknown")
        self.assertIn("permission", ev["reasons"])

    def test_cancelled_job_card_is_not_completion(self):
        ops = [op("OP-CUT", "裁剪", 1)]
        result = build(ops, [jc("OP-CUT", "T1", 1, docstatus=2)],
                       [tn("T1", 1)], qty=1)
        self.assertEqual(result["all_process_done"]["qty_proven"], 0)

    def test_tracking_qty_missing_is_unknown_not_zero(self):
        ops = [op("OP-CUT", "裁剪", 1)]
        result = build(ops, [jc("OP-CUT", "T1", 1)], [tn("T1", None)], qty=1)
        ev = result["all_process_done"]
        self.assertIsNone(ev["qty_proven"])
        self.assertIn("tracking_qty_missing", ev["reasons"])

    def test_cancelled_work_order_with_valid_stock_entry_keeps_stock_fact(self):
        ops = [op("OP-CUT", "裁剪", 1)]
        result = build(ops, [], [], qty=10, docstatus=2,
                       ses=[se("SE-1", [finished(10)])])
        self.assertEqual(result["stock_in_posted"]["qty_proven"], 10)
        self.assertIn("wo_cancelled_with_valid_stock_in",
                      [c["code"] for c in result["conflicts"]])
        self.assertIsNone(result["all_process_done"]["qty_proven"])

    def test_stock_in_and_process_can_differ(self):
        ops = [op("OP-CUT", "裁剪", 1)]
        result = build(ops, [jc("OP-CUT", "T1", 3)], [tn("T1", 3)], qty=3,
                       ses=[se("SE-1", [finished(5)])])
        self.assertEqual(result["all_process_done"]["qty_proven"], 3)
        self.assertEqual(result["stock_in_posted"]["qty_proven"], 5)


class AdditionalEdgeTests(unittest.TestCase):
    def test_no_routing_is_not_applicable_not_zero(self):
        result = build([], [], [], qty=5, ses=[se("SE-1", [finished(5)])])
        self.assertIsNone(result["first_process_done"]["qty_proven"])
        self.assertIsNone(result["all_process_done"]["qty_proven"])
        self.assertIn("no_routing", result["all_process_done"]["reasons"])
        self.assertEqual(result["stock_in_posted"]["qty_proven"], 5)

    def test_batch_only_is_estimated_not_proven(self):
        ops = [op("OP-CUT", "裁剪", 1), op("OP-SEW", "缝制", 2), op("OP-QC", "质检", 3)]
        jcs = [jc("OP-CUT", "", 36), jc("OP-SEW", "", 36), jc("OP-QC", "", 36)]
        result = build(ops, jcs, [], qty=36)
        self.assertIsNone(result["first_process_done"]["qty_proven"])
        self.assertEqual(result["first_process_done"]["qty_estimated"], 36)
        self.assertIsNone(result["all_process_done"]["qty_proven"])
        self.assertEqual(result["all_process_done"]["qty_estimated"], 36)
        self.assertEqual(result["all_process_done"]["confidence"], "estimated")

    def test_stock_entry_permission_is_unknown(self):
        ops = [op("OP-CUT", "裁剪", 1)]
        result = build(ops, [], [], qty=1, ses=[se("SE-1", [finished(1)])],
                       availability={"stock_entries": False})
        ev = result["stock_in_posted"]
        self.assertIsNone(ev["qty_proven"])
        self.assertEqual(ev["confidence"], "unknown")
        self.assertIn("permission", ev["reasons"])

    def test_qi_reference_not_found_is_unallocated(self):
        ops = [op("OP-CUT", "裁剪", 1), op("OP-QC", "质检", 2)]
        jcs = [jc("OP-CUT", "T1", 1), jc("OP-QC", "T1", 1)]
        result = build(ops, jcs, [tn("T1", 1)], qty=1,
                       qis=[qi("QI-1", ref_type="Job Card", ref_name="MISSING")])
        self.assertIsNone(result["qc_passed"]["qty_proven"])
        self.assertIn("qi_reference_unallocated",
                      [c["code"] for c in result["qc_passed"]["conflicts"]])

    def test_gross_stock_entry_item_mismatch_is_conflict(self):
        ops = [op("OP-CUT", "裁剪", 1)]
        result = build(ops, [], [], qty=10,
                       ses=[se("SE-1", [finished(10, item="OTHER")])])
        self.assertIsNone(result["stock_in_posted"]["qty_proven"])
        self.assertIn("stock_in_item_mismatch",
                      [c["code"] for c in result["stock_in_posted"]["conflicts"]])

    def test_partial_tracking_qty_missing_marks_unknown(self):
        ops = [op("OP-CUT", "裁剪", 1)]
        result = build(ops, [jc("OP-CUT", "T1", 1), jc("OP-CUT", "T2", 1)],
                       [tn("T1", 1), tn("T2", None)], qty=2)
        ev = result["all_process_done"]
        self.assertEqual(ev["qty_proven"], 1)
        self.assertEqual(ev["confidence"], "unknown")
        self.assertIn("tracking_qty_missing", ev["reasons"])


class ReviewRegressionTests(unittest.TestCase):
    def test_invalid_batch_cards_do_not_create_estimate(self):
        ops = [op("OP-CUT", "裁剪", 1), op("OP-SEW", "缝制", 2)]
        jcs = [jc("OP-CUT", "", 5, status="Open", docstatus=0),
               jc("OP-SEW", "", 5, status="Open", docstatus=0)]
        result = build(ops, jcs, [], qty=5)
        self.assertEqual(result["all_process_done"]["qty_proven"], 0)
        self.assertIn(result["all_process_done"]["qty_estimated"], (None, 0))
        self.assertNotEqual(result["all_process_done"]["qty_estimated"], 5)

    def test_cancelled_batch_cards_do_not_create_estimate(self):
        ops = [op("OP-CUT", "裁剪", 1), op("OP-SEW", "缝制", 2)]
        jcs = [jc("OP-CUT", "", 5, docstatus=2), jc("OP-SEW", "", 5, docstatus=2)]
        result = build(ops, jcs, [], qty=5)
        self.assertEqual(result["all_process_done"]["qty_proven"], 0)
        self.assertIn(result["all_process_done"]["qty_estimated"], (None, 0))

    def test_missing_job_card_qty_is_unknown_not_proven(self):
        ops = [op("OP-CUT", "裁剪", 1)]
        result = build(ops, [jc("OP-CUT", "T1", None)], [tn("T1", 1)], qty=1)
        ev = result["all_process_done"]
        self.assertIsNone(ev["qty_proven"])
        self.assertEqual(ev["confidence"], "unknown")
        self.assertIn("qty_missing", [c["code"] for c in ev["conflicts"]])

    def test_duplicate_completed_job_cards_are_unknown_not_proven(self):
        ops = [op("OP-CUT", "裁剪", 1)]
        jcs = [jc("OP-CUT", "T1", 1, name="JC-A"),
               jc("OP-CUT", "T1", 2, name="JC-B")]
        result = build(ops, jcs, [tn("T1", 1)], qty=1)
        ev = result["all_process_done"]
        self.assertIsNone(ev["qty_proven"])
        self.assertEqual(ev["confidence"], "unknown")
        self.assertIn("duplicate_job_card",
                      [c["code"] for c in ev["conflicts"]])

    def test_duplicate_stock_entry_payload_is_deduped(self):
        ops = [op("OP-CUT", "裁剪", 1)]
        entry = se("SE-1", [finished(10)])
        result = build(ops, [], [], qty=10, ses=[entry, dict(entry)])
        self.assertEqual(result["stock_in_posted"]["qty_proven"], 10)
        self.assertNotIn("duplicate_stock_entry_payload",
                         [c["code"] for c in result["stock_in_posted"]["conflicts"]])

    def test_duplicate_stock_entry_with_different_payload_is_conflict(self):
        ops = [op("OP-CUT", "裁剪", 1)]
        result = build(ops, [], [], qty=10, ses=[
            se("SE-1", [finished(10)]),
            se("SE-1", [finished(20)]),
        ])
        self.assertIsNone(result["stock_in_posted"]["qty_proven"])
        self.assertIn("duplicate_stock_entry_payload",
                      [c["code"] for c in result["stock_in_posted"]["conflicts"]])

    def test_return_with_invalid_reference_is_not_deducted(self):
        ops = [op("OP-CUT", "裁剪", 1)]
        result = build(ops, [], [], qty=100, ses=[
            se("SE-GROSS", [finished(100)]),
            se("SE-RET", [finished(10)], is_return=1,
               outgoing_stock_entry="SE-MISSING"),
        ])
        ev = result["stock_in_posted"]
        self.assertIsNone(ev["qty_proven"])
        self.assertIn("return_reference_invalid", [c["code"] for c in ev["conflicts"]])
        self.assertEqual(ev["components"]["return_qty"], 0)

    def test_missing_work_order_uom_is_unknown(self):
        ops = [op("OP-CUT", "裁剪", 1)]
        result = build(ops, [jc("OP-CUT", "T1", 5)], [tn("T1", 5)], qty=5,
                       stock_uom="", ses=[se("SE-1", [finished(5, uom="")])])
        for ev in (result["first_process_done"], result["all_process_done"],
                   result["stock_in_posted"]):
            self.assertIsNone(ev["qty_proven"])
            self.assertEqual(ev["confidence"], "unknown")
            self.assertIn("unit_missing", ev["reasons"])

    def test_duplicate_accepted_qi_coverage_is_conflict_not_sum(self):
        ops = [op("OP-CUT", "裁剪", 1), op("OP-QC", "质检", 2)]
        jcs = [jc("OP-CUT", "T1", 1, name="JC-CUT"),
               jc("OP-QC", "T1", 1, name="JC-QC")]
        qis = [qi("QI-1", ref_name="JC-QC", coverage=5),
               qi("QI-2", ref_name="JC-QC", coverage=5)]
        result = build(ops, jcs, [tn("T1", 1)], qty=1, qis=qis)
        ev = result["qc_passed"]
        self.assertIsNone(ev["qty_proven"])
        self.assertIn("qi_coverage_conflict", [c["code"] for c in ev["conflicts"]])

    def test_qi_accepted_and_rejected_same_reference_is_conflict(self):
        ops = [op("OP-CUT", "裁剪", 1), op("OP-QC", "质检", 2)]
        jcs = [jc("OP-CUT", "T1", 1, name="JC-CUT"),
               jc("OP-QC", "T1", 1, name="JC-QC")]
        qis = [qi("QI-1", ref_name="JC-QC", coverage=5),
               qi("QI-2", ref_name="JC-QC", coverage=None, status="Rejected")]
        result = build(ops, jcs, [tn("T1", 1)], qty=1, qis=qis)
        ev = result["qc_passed"]
        self.assertIsNone(ev["qty_proven"])
        self.assertIn("qi_result_conflict", [c["code"] for c in ev["conflicts"]])

    def test_permission_restricted_hides_completion_time(self):
        ops = [op("OP-CUT", "裁剪", 1)]
        result = build(ops, [jc("OP-CUT", "T1", 1,
                                start="2026-01-01 08:00:00",
                                end="2026-01-01 17:00:00")],
                       [tn("T1", 1)], qty=1,
                       availability={"job_cards": False})
        for ev in (result["first_process_done"], result["all_process_done"]):
            self.assertIsNone(ev["qty_proven"])
            self.assertIsNone(ev["started_at"])
            self.assertIsNone(ev["completed_at"])

    def test_all_process_zero_has_no_completion_time(self):
        ops = [op("OP-CUT", "裁剪", 1), op("OP-SEW", "缝制", 2)]
        result = build(ops, [jc("OP-CUT", "T1", 1,
                                start="2026-01-01 08:00:00",
                                end="2026-01-01 09:00:00")],
                       [tn("T1", 1)], qty=1)
        self.assertEqual(result["first_process_done"]["qty_proven"], 1)
        self.assertEqual(result["all_process_done"]["qty_proven"], 0)
        self.assertIsNone(result["all_process_done"]["completed_at"])

    def test_evidence_has_sources_and_observed_at(self):
        ops = [op("OP-CUT", "裁剪", 1), op("OP-QC", "质检", 2)]
        jcs = [jc("OP-CUT", "T1", 1, name="JC-CUT"),
               jc("OP-QC", "T1", 1, name="JC-QC")]
        result = build(ops, jcs, [tn("T1", 1)], qty=1,
                       ses=[se("SE-1", [finished(1)])],
                       qis=[qi("QI-1", ref_name="JC-QC")],
                       observed_at="2026-01-02T00:00:00")
        self.assertEqual(result["first_process_done"]["observed_at"],
                         "2026-01-02T00:00:00")
        self.assertTrue(any(r.get("doctype") == "Job Card" and r.get("name") == "JC-CUT"
                            for r in result["first_process_done"]["source_records"]))
        self.assertTrue(any(r.get("doctype") == "Stock Entry" and r.get("name") == "SE-1"
                            for r in result["stock_in_posted"]["source_records"]))
        self.assertTrue(any(r.get("doctype") == "Quality Inspection" and r.get("name") == "QI-1"
                            for r in result["qc_passed"]["source_records"]))


class SecondReviewRegressionTests(unittest.TestCase):
    def test_batch_missing_qty_is_unknown_not_proven(self):
        ops = [op("OP-CUT", "裁剪", 1), op("OP-SEW", "缝制", 2)]
        jcs = [jc("OP-CUT", "", None), jc("OP-SEW", "", 5)]
        result = build(ops, jcs, [], qty=5)
        ev = result["all_process_done"]
        self.assertIsNone(ev["qty_proven"])
        self.assertEqual(ev["confidence"], "unknown")
        self.assertIn("qty_missing", [c["code"] for c in ev["conflicts"]])

    def test_return_reference_to_draft_original_is_invalid(self):
        ops = [op("OP-CUT", "裁剪", 1)]
        result = build(ops, [], [], qty=100, ses=[
            se("SE-GROSS", [finished(100)]),
            se("SE-DRAFT", [finished(100)], docstatus=0),
            se("SE-RET", [finished(10)], is_return=1,
               outgoing_stock_entry="SE-DRAFT"),
        ])
        ev = result["stock_in_posted"]
        self.assertIsNone(ev["qty_proven"])
        self.assertEqual(ev["components"]["return_qty"], 0)
        self.assertIn("return_reference_invalid", [c["code"] for c in ev["conflicts"]])

    def test_return_reference_to_self_is_invalid(self):
        ops = [op("OP-CUT", "裁剪", 1)]
        result = build(ops, [], [], qty=100, ses=[
            se("SE-GROSS", [finished(100)]),
            se("SE-RET", [finished(10)], is_return=1,
               outgoing_stock_entry="SE-RET"),
        ])
        ev = result["stock_in_posted"]
        self.assertIsNone(ev["qty_proven"])
        self.assertEqual(ev["components"]["return_qty"], 0)
        self.assertIn("return_reference_invalid", [c["code"] for c in ev["conflicts"]])

    def test_return_original_item_mismatch_is_invalid(self):
        ops = [op("OP-CUT", "裁剪", 1)]
        result = build(ops, [], [], qty=100, ses=[
            se("SE-GROSS", [finished(100)]),
            se("SE-ORIG", [finished(100, item="OTHER")]),
            se("SE-RET", [finished(10)], is_return=1,
               outgoing_stock_entry="SE-ORIG"),
        ])
        ev = result["stock_in_posted"]
        self.assertIsNone(ev["qty_proven"])
        self.assertEqual(ev["components"]["return_qty"], 0)
        self.assertIn("return_reference_invalid", [c["code"] for c in ev["conflicts"]])

    def test_permission_restricted_hides_source_payload(self):
        ops = [op("OP-CUT", "裁剪", 1)]
        result = build(ops, [jc("OP-CUT", "T1", 1, name="JC-CUT",
                                start="2026-01-01 08:00:00",
                                end="2026-01-01 17:00:00")],
                       [tn("T1", 1)], qty=1,
                       availability={"job_cards": False})
        self.assertEqual(result["required_operations"], [])
        for ev in (result["first_process_done"], result["all_process_done"],
                   result["qc_performed"]):
            self.assertEqual(ev["source_records"], [])
            self.assertEqual(ev["components"], {})
            self.assertEqual(ev["conflicts"], [])

    def test_duplicate_tracking_metadata_is_order_independent(self):
        ops = [op("OP-CUT", "裁剪", 1)]
        snapshots = []
        for quantities in ((2, 5), (5, 2)):
            with self.subTest(quantities=quantities):
                result = build(ops, [jc("OP-CUT", "T1", 5)],
                               [tn("T1", q) for q in quantities], qty=5)
                ev = result["all_process_done"]
                self.assertIsNone(ev["qty_proven"])
                self.assertEqual(ev["confidence"], "unknown")
                self.assertIsNone(ev["completed_at"])
                self.assertIn("tracking_qty_conflict",
                              [c["code"] for c in ev["conflicts"]])
                snapshots.append((ev["qty_proven"], ev["completed_at"],
                                  ev["source_records"], ev["confidence"]))
        self.assertEqual(snapshots[0], snapshots[1])

    def test_duplicate_tracking_same_payload_is_deduped(self):
        ops = [op("OP-CUT", "裁剪", 1)]
        result = build(ops, [jc("OP-CUT", "T1", 5)],
                       [tn("T1", 5), tn("T1", 5)], qty=5)
        self.assertEqual(result["all_process_done"]["qty_proven"], 5)
        self.assertNotIn("tracking_qty_conflict",
                         [c["code"] for c in result["all_process_done"]["conflicts"]])

    def test_job_card_references_missing_tracking_number_is_unknown(self):
        ops = [op("OP-CUT", "裁剪", 1)]
        result = build(ops, [jc("OP-CUT", "T1", 1)], [], qty=1)
        ev = result["all_process_done"]
        self.assertIsNone(ev["qty_proven"])
        self.assertEqual(ev["confidence"], "unknown")
        self.assertIn("tracking_reference_missing",
                      [c["code"] for c in ev["conflicts"]])

    def test_different_job_cards_same_op_tn_conflict_order_independent(self):
        ops = [op("OP-CUT", "裁剪", 1)]
        snapshots = []
        for rows in (
            [jc("OP-CUT", "T1", 5, name="JC-A",
                start="2026-01-01 10:00:00", end="2026-01-01 10:30:00"),
             jc("OP-CUT", "T1", 5, name="JC-B",
                start="2026-01-01 17:00:00", end="2026-01-01 17:30:00")],
            [jc("OP-CUT", "T1", 5, name="JC-B",
                start="2026-01-01 17:00:00", end="2026-01-01 17:30:00"),
             jc("OP-CUT", "T1", 5, name="JC-A",
                start="2026-01-01 10:00:00", end="2026-01-01 10:30:00")],
        ):
            result = build(ops, rows, [tn("T1", 5)], qty=5)
            ev = result["all_process_done"]
            self.assertIsNone(ev["qty_proven"])
            self.assertEqual(ev["confidence"], "unknown")
            self.assertIsNone(ev["completed_at"])
            self.assertIn("duplicate_job_card",
                          [c["code"] for c in ev["conflicts"]])
            snapshots.append((ev["qty_proven"], ev["completed_at"],
                              ev["source_records"], ev["confidence"]))
        self.assertEqual(snapshots[0], snapshots[1])

    def test_same_job_card_name_different_payload_is_conflict(self):
        ops = [op("OP-CUT", "裁剪", 1)]
        rows = [jc("OP-CUT", "T1", 5, name="JC-A",
                   start="2026-01-01 10:00:00", end="2026-01-01 10:30:00"),
                jc("OP-CUT", "T1", 5, name="JC-A",
                   start="2026-01-01 17:00:00", end="2026-01-01 17:30:00")]
        result = build(ops, rows, [tn("T1", 5)], qty=5)
        ev = result["all_process_done"]
        self.assertIsNone(ev["qty_proven"])
        self.assertIn("duplicate_job_card_payload",
                      [c["code"] for c in ev["conflicts"]])

    def test_same_job_card_name_identical_payload_is_deduped(self):
        ops = [op("OP-CUT", "裁剪", 1)]
        row = jc("OP-CUT", "T1", 5, name="JC-A",
                 start="2026-01-01 10:00:00", end="2026-01-01 10:30:00")
        result = build(ops, [row, dict(row)], [tn("T1", 5)], qty=5)
        self.assertEqual(result["all_process_done"]["qty_proven"], 5)
        self.assertEqual(len(result["all_process_done"]["source_records"]), 1)

    def test_work_order_permission_hides_routing(self):
        ops = [op("OP-CUT", "裁剪", 1)]
        result = build(ops, [jc("OP-CUT", "T1", 1)], [tn("T1", 1)], qty=1,
                       availability={"work_order": False})
        self.assertEqual(result["required_operations"], [])

    def test_nan_tracking_qty_is_rejected(self):
        ops = [op("OP-CUT", "裁剪", 1)]
        result = build(ops, [jc("OP-CUT", "T1", 1)], [tn("T1", math.nan)], qty=1)
        ev = result["all_process_done"]
        self.assertIsNone(ev["qty_proven"])
        self.assertEqual(ev["confidence"], "unknown")
        self.assertIn("tracking_qty_invalid", ev["reasons"])

    def test_infinite_stock_qty_is_rejected(self):
        ops = [op("OP-CUT", "裁剪", 1)]
        result = build(ops, [], [], qty=1,
                       ses=[se("SE-1", [finished(math.inf)])])
        ev = result["stock_in_posted"]
        self.assertIsNone(ev["qty_proven"])
        self.assertEqual(ev["confidence"], "unknown")
        self.assertIn("stock_in_qty_invalid", [c["code"] for c in ev["conflicts"]])

    def test_nan_job_card_qty_is_rejected(self):
        ops = [op("OP-CUT", "裁剪", 1)]
        result = build(ops, [jc("OP-CUT", "T1", math.nan)], [tn("T1", 1)], qty=1)
        ev = result["all_process_done"]
        self.assertIsNone(ev["qty_proven"])
        self.assertEqual(ev["confidence"], "unknown")
        self.assertIn("qty_invalid", [c["code"] for c in ev["conflicts"]])


class FinalInputBoundaryTests(unittest.TestCase):
    def test_cross_work_order_job_card_blocks_proven(self):
        ops = [op("OP-CUT", "裁剪", 1)]
        jcs = [jc("OP-CUT", "T1", 5, work_order="WO-OTHER")]
        result = build(ops, jcs, [tn("T1", 5, work_order="WO-1")], qty=5)
        ev = result["all_process_done"]
        self.assertIsNone(ev["qty_proven"])
        self.assertEqual(ev["confidence"], "unknown")
        self.assertIn("job_card_work_order_mismatch",
                      [c["code"] for c in ev["conflicts"]])

    def test_cross_work_order_tracking_blocks_proven(self):
        ops = [op("OP-CUT", "裁剪", 1)]
        jcs = [jc("OP-CUT", "T1", 5, work_order="WO-1")]
        result = build(ops, jcs, [tn("T1", 5, work_order="WO-OTHER")], qty=5)
        ev = result["all_process_done"]
        self.assertIsNone(ev["qty_proven"])
        self.assertEqual(ev["confidence"], "unknown")
        self.assertIn("tracking_work_order_mismatch",
                      [c["code"] for c in ev["conflicts"]])

    def test_cross_work_order_routing_blocks_proven(self):
        ops = [op("OP-CUT", "裁剪", 1, parent="WO-OTHER")]
        jcs = [jc("OP-CUT", "T1", 5, work_order="WO-1")]
        result = build(ops, jcs, [tn("T1", 5, work_order="WO-1")], qty=5)
        ev = result["all_process_done"]
        self.assertIsNone(ev["qty_proven"])
        self.assertEqual(ev["confidence"], "unknown")
        self.assertIn("routing_work_order_mismatch",
                      [c["code"] for c in ev["conflicts"]])

    def test_batch_duplicate_replay_is_idempotent(self):
        ops = [op("OP-CUT", "裁剪", 1), op("OP-SEW", "缝制", 2)]
        rows = [
            jc("OP-CUT", "", 5, name="JC-B1",
               start="2026-01-01 08:00:00", end="2026-01-01 09:00:00"),
            jc("OP-SEW", "", 5, name="JC-B2",
               start="2026-01-01 09:00:00", end="2026-01-01 10:00:00"),
        ]
        once = build(ops, rows, [], qty=5)
        twice = build(ops, rows + rows, [], qty=5)
        for field in ("first_process_done", "all_process_done"):
            self.assertEqual(once[field]["qty_estimated"], 5)
            self.assertEqual(twice[field]["qty_estimated"], 5)
            self.assertEqual(once[field]["completed_at"],
                             twice[field]["completed_at"])
            self.assertEqual(once[field]["source_records"],
                             twice[field]["source_records"])


class RollupTests(unittest.TestCase):
    def test_rollup_sums_proven_and_estimated_components(self):
        ops = [op("OP-CUT", "裁剪", 1)]
        proven = build(ops, [jc("OP-CUT", "T1", 5)], [tn("T1", 5)], qty=5)
        estimated = build(ops, [jc("OP-CUT", "", 5)], [], qty=5)
        rolled = rollup_line_evidence([proven, estimated])
        self.assertEqual(rolled["all_process_done"]["qty_proven"], 5)
        self.assertEqual(rolled["all_process_done"]["qty_estimated"], 5)
        self.assertEqual(rolled["all_process_done"]["confidence"], "mixed")

    def test_rollup_unknown_does_not_become_zero(self):
        ops = [op("OP-CUT", "裁剪", 1)]
        known = build(ops, [jc("OP-CUT", "T1", 5)], [tn("T1", 5)], qty=5)
        unknown = build(ops, [jc("OP-CUT", "T1", 5)], [tn("T1", 5)], qty=5,
                        availability={"job_cards": False})
        rolled = rollup_line_evidence([known, unknown])
        self.assertIsNone(rolled["all_process_done"]["qty_proven"])
        self.assertEqual(rolled["all_process_done"]["confidence"], "unknown")


if __name__ == "__main__":
    unittest.main()
