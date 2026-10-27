# -*- coding: utf-8 -*-
"""不守恒 SO 逐单核对：重复成对修正、FBA 不适用/冲突、不可解释隔离、权威量边界。"""

from __future__ import annotations

import unittest
from datetime import datetime, timezone

import pandas as pd

from supply_netting.scripts.so_conservation_fix import build, diagnose, summarize


def line(customer, item="KS1", qty=100.0, so_line="L1"):
    return dict(so="SO-1", so_line=so_line, item_code=item, customer=customer, qty=qty,
                delivered_qty=0.0, uom="个", warehouse="成品仓 - FZH", scope="in_house",
                role="finished")


def bal(stage, qty, *, item="KS1", exclusion="", basis="", so_line="L1", record=None,
        scope="in_house", status="known"):
    return dict(so="SO-1", so_line_id=so_line, item_code=item, warehouse="成品仓 - FZH",
                uom="个", stage=stage, stage_detail="", qty=qty, qty_status=status,
                qty_basis=basis, cumulative_excess_qty=None,
                batch_key=record or "", source_record=record,
                exclusion_reason=exclusion, included_in_stock="unknown",
                demand_status="active", scope=scope, role="finished")


def payload(lines, balances, links=None):
    return {"so": "SO-1", "lines": lines, "stage_balances": balances, "links": links or []}


class DiagnoseTests(unittest.TestCase):
    def test_duplicate_pair_is_fixable(self):
        # 阶段 100 + 50 = 150；SO 总量 50 → 差额 100 = 2×50（重复标记量）
        rows = [bal("arrived_not_sellable", 100.0, record="DN-1"),
                bal("unknown", 50.0, exclusion="超发/重复证据或退货无仓级归属，待核实",
                    record="DN-1")]
        result = diagnose(payload([line("美东公司（CENTADE）", qty=50.0)], rows))
        self.assertEqual(result["cause_code"], "duplicate_evidence_pair")
        self.assertTrue(result["fixable"])
        self.assertEqual(result["duplicate_pair_qty"], 100.0)
        self.assertEqual(result["delta"], 100.0)
        self.assertEqual(result["residual_after_fix"], 0.0)
        self.assertEqual(result["suggested_correction_qty"], 100.0)
        self.assertEqual(result["corrected_stage_total"], 50.0)

    def test_fba_only_without_inhouse_stage_is_not_applicable(self):
        rows = [bal("shipped_in_transit", 30.0, scope="external_fba")]
        result = diagnose(payload([line("美国FBA仓", qty=30.0)], rows))
        self.assertEqual(result["cause_code"], "fba_external_not_applicable")
        self.assertFalse(result["fixable"])
        self.assertEqual(result["isolation_reason"], "fba_external")

    def test_fba_only_with_inhouse_stage_is_isolated(self):
        rows = [bal("arrived_not_sellable", 80.0)]
        result = diagnose(payload([line("美国FBA仓", qty=80.0)], rows))
        self.assertEqual(result["cause_code"], "fba_so_with_inhouse_stage")
        self.assertFalse(result["fixable"])
        self.assertEqual(result["isolation_reason"], "fba_inhouse_stage_conflict")

    def test_unexplained_delta_is_isolated(self):
        rows = [bal("arrived_not_sellable", 100.0, record="DN-1"),
                bal("unknown", 40.0, exclusion="缺入库/上架证据", record="DN-1")]
        result = diagnose(payload([line("美东公司（CENTADE）", qty=50.0)], rows))
        self.assertEqual(result["cause_code"], "unexplained_delta")
        self.assertFalse(result["fixable"])
        self.assertEqual(result["isolation_reason"], "unexplained_delta")

    def test_inhouse_conserved_while_fba_makes_audit_flag(self):
        rows = [bal("arrived_not_sellable", 50.0, record="DN-1")]
        lines = [line("美东公司（CENTADE）", qty=50.0), line("美国FBA仓", qty=20.0, so_line="L2")]
        result = diagnose(payload(lines, rows))
        self.assertEqual(result["cause_code"], "conserved_in_branch_scope")
        self.assertEqual(result["delta"], 0.0)
        self.assertIsNone(result["isolation_reason"])

    def test_first_op_and_flagged_rows_do_not_count_as_authoritative(self):
        rows = [bal("produced_pending_dn", 60.0, basis="job_card_first_op", record="DN-1"),
                bal("in_production", 40.0, basis="", record="WO-1"),
                bal("unknown", 10.0, exclusion="超发/重复证据", record="DN-2")]
        # 阶段 110，SO 100 → 差额 10 ≠ 2×10，故不可修；权威量应为 0（隔离）
        result = diagnose(payload([line("美东公司（CENTADE）", qty=100.0)], rows))
        self.assertFalse(result["fixable"])
        self.assertEqual(result["corrected_authoritative_offset"], 0.0)

    def test_authoritative_is_capped_by_so_total(self):
        rows = [bal("produced_pending_dn", 100.0, record="DN-1"),
                bal("in_production", 80.0, record="WO-1"),
                bal("unknown", 90.0, exclusion="超发/重复证据", record="DN-2")]
        # 阶段 270，SO 90 → 差额 180 = 2×90 → 可修；权威量 180 但按 SO 90 封顶
        result = diagnose(payload([line("美东公司（CENTADE）", qty=90.0)], rows))
        self.assertTrue(result["fixable"])
        self.assertEqual(result["corrected_authoritative_offset"], 90.0)


class BuildTests(unittest.TestCase):
    def test_build_filters_to_non_conserved_and_summarizes(self):
        p1 = dict(payload([line("美东公司（CENTADE）", qty=50.0)],
                          [bal("arrived_not_sellable", 100.0, record="DN-1"),
                           bal("unknown", 50.0, exclusion="超发/重复证据", record="DN-1")]))
        p1["so"] = "SO-1"
        p2 = dict(payload([line("美国FBA仓", qty=30.0)],
                          [bal("shipped_in_transit", 30.0, scope="external_fba")]))
        p2["so"] = "SO-2"
        audit = pd.DataFrame([{"SO": "SO-1", "守恒": "否"}, {"SO": "SO-2", "守恒": "否"},
                              {"SO": "SO-3", "守恒": "是"}])
        frame = build([{"so": "SO-1", "payload": p1}, {"so": "SO-2", "payload": p2}], audit)
        self.assertEqual(len(frame), 2)
        stats = summarize(frame)
        self.assertEqual(stats["non_conserved_orders"], 2)
        self.assertEqual(stats["fixable_orders"], 1)
        self.assertEqual(stats["suggested_correction_total"], 100.0)
        self.assertEqual(stats["causes"].get("fba_external_not_applicable"), 1)


if __name__ == "__main__":
    unittest.main()
