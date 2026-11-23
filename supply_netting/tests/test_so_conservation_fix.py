# -*- coding: utf-8 -*-
"""不守恒 SO 逐行重分类 v2：逐行封顶、孪生才叫重复、四类去向、97 单零回归。"""

from __future__ import annotations

import unittest
from pathlib import Path

import pandas as pd

from supply_netting.scripts.so_conservation_fix import build, reconcile, summarize

W1_PATH = Path("D:/Work/fzh-order-store/w1_supply_facts_v2/supply_facts_raw.jsonl")


def line(item="KS1", qty=100.0, so_line="L1", customer="美东公司（CENTADE）"):
    return dict(so="SO-1", so_line=so_line, item_code=item, customer=customer, qty=qty,
                delivered_qty=0.0, uom="个", warehouse="成品仓 - FZH", scope="in_house",
                role="finished")


def bal(stage, qty, *, item="KS1", so_line="L1", record="", exclusion="", basis="",
        scope="in_house", status="known"):
    return dict(so="SO-1", so_line_id=so_line, item_code=item, warehouse="成品仓 - FZH",
                uom="个", stage=stage, stage_detail="", qty=qty, qty_status=status,
                qty_basis=basis, cumulative_excess_qty=None, batch_key=record,
                source_record=record, exclusion_reason=exclusion,
                included_in_stock="unknown", demand_status="active", scope=scope,
                role="finished")


def payload(lines, balances):
    return {"so": "SO-1", "lines": lines, "stage_balances": balances, "links": []}


def by_stage(rows):
    return {row["stage"]: row for row in rows}


class PerLineCapTests(unittest.TestCase):
    def test_named_overship_is_capped_at_line_quantity(self):
        rows, so = reconcile(payload([line(qty=40.0)],
                                     [bal("shipped_in_transit", 60.0, record="DN-1")]))
        row = rows[0]
        self.assertEqual(row["attributable_qty"], 40.0)
        self.assertEqual(row["excess_qty"], 20.0)
        self.assertEqual(row["excess_class"], "over_ship")
        self.assertEqual(so["delta_after"], 0.0)
        self.assertEqual(so["status"], "excess_reclassified")

    def test_counter_example_is_overship_plus_placeholder(self):
        # SO-26-00048 形状：在途 60 对订单 40（超发 20）+ 无单号待核 20（异常占位）
        rows, so = reconcile(payload(
            [line(qty=40.0)],
            [bal("shipped_in_transit", 60.0, record="DN-24"),
             bal("unknown", 20.0, exclusion="超发/重复证据或退货无仓级归属，待核实")]))
        classes = {row["stage"]: row["excess_class"] for row in rows}
        self.assertEqual(classes["shipped_in_transit"], "over_ship")
        self.assertEqual(classes["unknown"], "abnormal_placeholder")
        self.assertEqual(so["over_ship_qty"], 20.0)
        self.assertEqual(so["abnormal_placeholder_qty"], 20.0)
        self.assertEqual(so["duplicate_qty"], 0.0)

    def test_duplicate_requires_an_unflagged_twin(self):
        rows, _ = reconcile(payload(
            [line(qty=10.0), line(qty=10.0, so_line="L2")],
            [bal("arrived_not_sellable", 30.0, record="DN-9"),
             bal("unknown", 30.0, record="DN-9",
                 exclusion="重复证据，待核实", so_line="L2")]))
        # 第二行与第一行同 source/item/qty，且第一行未标记 → 第二行可标重复
        classes = [row["excess_class"] for row in rows]
        self.assertIn("duplicate", classes)
        self.assertEqual(rows[1]["excess_class"], "duplicate")

    def test_no_twin_means_not_duplicate(self):
        rows, _ = reconcile(payload(
            [line(qty=10.0), line(qty=10.0, so_line="L2")],
            [bal("arrived_not_sellable", 30.0, record="DN-9"),
             bal("unknown", 20.0, record="",
                 exclusion="重复证据，待核实", so_line="L2")]))
        self.assertNotIn("duplicate", [row["excess_class"] for row in rows])
        self.assertIn("abnormal_placeholder", [row["excess_class"] for row in rows])

    def test_return_reason_without_overship_is_return_pending(self):
        rows, _ = reconcile(payload(
            [line(qty=10.0), line(qty=2.0, so_line="L2")],
            [bal("arrived_not_sellable", 10.0, record="DN-1"),
             bal("unknown", 5.0, exclusion="退货待核，无仓级归属", so_line="L2")]))
        classes = [row["excess_class"] for row in rows]
        self.assertIn("return_pending", classes)

    def test_over_produced_and_fba_are_separate(self):
        rows, so = reconcile(payload(
            [line(qty=10.0), line(item="KS2", qty=5.0, so_line="L2", customer="美国FBA仓")],
            [bal("arrived_not_sellable", 10.0, record="DN-1"),
             bal("over_produced", 4.0, record="WO-1"),
             bal("shipped_in_transit", 5.0, item="KS2", so_line="L2", record="DN-2",
                 scope="external_fba")]))
        classes = {row["stage"]: row["excess_class"] for row in rows}
        self.assertEqual(classes["over_produced"], "over_produced")
        self.assertEqual(classes["shipped_in_transit"], "fba_external")
        self.assertEqual(so["so_total_inhouse"], 10.0)
        self.assertEqual(so["delta_after"], 0.0)

    def test_conserved_so_stays_conserved(self):
        rows, so = reconcile(payload(
            [line(qty=50.0)],
            [bal("arrived_not_sellable", 30.0, record="DN-1"),
             bal("shipped_in_transit", 20.0, record="DN-2")]))
        self.assertEqual(so["status"], "conserved_in_branch_scope")
        self.assertEqual(so["delta_after"], 0.0)
        self.assertEqual(sum(row["attributable_qty"] for row in rows), 50.0)


class HeuristicTests(unittest.TestCase):
    def test_heuristic_excludes_first_op_and_flagged_rows(self):
        rows, so = reconcile(payload(
            [line(qty=100.0)],
            [bal("produced_pending_dn", 60.0, record="DN-1", basis="job_card_first_op"),
             bal("in_production", 40.0, record="WO-1")]))
        # 首工序不进启发式；在产 40 可进（归因后仍为 40）
        self.assertEqual(so["heuristic_candidate_qty"], 40.0)
        self.assertFalse(so["offset_allowed"])
        self.assertEqual(so["isolation_reason"], "heuristic_candidate_only")


class BuildSummaryTests(unittest.TestCase):
    def test_build_counts_statuses(self):
        good = dict(payload([line(qty=50.0)],
                            [bal("arrived_not_sellable", 50.0, record="DN-1")]))
        good["so"] = "SO-A"
        excess = dict(payload([line(qty=10.0)],
                              [bal("shipped_in_transit", 30.0, record="DN-2")]))
        excess["so"] = "SO-B"
        data = [{"so": "SO-A", "payload": good}, {"so": "SO-B", "payload": excess}]
        rows, sos = build(data)
        stats = summarize(sos, rows)
        self.assertEqual(stats["orders"], 2)
        self.assertEqual(stats["conserved_orders"], 1)
        self.assertEqual(stats["excess_orders"], 1)
        self.assertEqual(stats["missing_orders"], 0)
        self.assertFalse(stats["offset_allowed"])
        self.assertEqual(stats["duplicate_rows"], 0)


@unittest.skipUnless(W1_PATH.exists(), "W1 缓存不存在")
class RealDataRegressionTests(unittest.TestCase):
    """全部 97 单统一 in_house 重审：55 单零回归，全部 delta_after=0。"""

    @classmethod
    def setUpClass(cls):
        from supply_netting.scripts.so_conditional_supply import load_w1
        cls.w1 = load_w1(W1_PATH)
        cls.rows, cls.sos = build(cls.w1)

    def test_all_orders_reconcile_after_per_line_cap(self):
        self.assertEqual(len(self.sos), 97)
        self.assertTrue((self.sos["delta_after"].abs() < 1e-6).all())

    def test_original_conserved_orders_have_no_regression(self):
        conserved = self.sos[self.sos["status"] == "conserved_in_branch_scope"]
        self.assertEqual(len(conserved), 55)
        self.assertTrue((conserved["delta_raw"].abs() < 1e-6).all())

    def test_duplicates_are_only_claimed_with_a_twin(self):
        claimed = self.rows[self.rows["excess_class"] == "duplicate"]
        for row in claimed.itertuples(index=False):
            self.assertIn("unflagged twin", str(row.evidence))


if __name__ == "__main__":
    unittest.main()
