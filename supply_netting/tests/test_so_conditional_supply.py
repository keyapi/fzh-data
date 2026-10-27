# -*- coding: utf-8 -*-
"""SO 工厂条件供给层：日期规则、守恒门槛、FBA/分公司映射、缺口含/不含对比。"""

from __future__ import annotations

import unittest

import pandas as pd

from supply_netting.scripts.so_conditional_supply import (build_by_key, build_tranches,
                                                          plan_dates)

AUDIT = "2026-10-27"


def payload(so, lines, balances, as_of=AUDIT):
    return {"so": so, "payload": {"schema_version": "supply-facts/v1",
                                  "rule_version": "test", "as_of": as_of,
                                  "lines": lines, "stage_balances": balances}}


def line(so, line_id, customer, item, qty=10.0, uom="个"):
    return dict(so=so, so_line=line_id, item_code=item, customer=customer, qty=qty,
                delivered_qty=0.0, uom=uom, warehouse="成品仓 - FZH", scope="in_house",
                role="finished")


def balance(so, line_id, item, stage, qty=10.0, scope="in_house", exclusion="",
            qty_status="known", batch_key=None):
    return dict(so=so, so_line_id=line_id, item_code=item, warehouse="成品仓 - FZH",
                uom="个", stage=stage, stage_detail="", qty=qty, qty_status=qty_status,
                qty_basis="", cumulative_excess_qty=None, batch_key=batch_key,
                source_record="DN-1" if batch_key else None, exclusion_reason=exclusion,
                included_in_stock="unknown", demand_status="active", scope=scope,
                role="finished")


class DateRuleTests(unittest.TestCase):
    def test_finished_pending_uses_ship_plus_sea(self):
        centrade = plan_dates("produced_pending_dn", pd.Timestamp(AUDIT).date(),
                              "美东-CENTRADE")
        self.assertEqual(centrade["eta_earliest"], "2026-12-08")   # +7+35
        self.assertEqual(centrade["eta_latest"], "2026-12-08")     # 不跨春节
        poland = plan_dates("produced_pending_dn", pd.Timestamp(AUDIT).date(),
                            "波兰-FZHPoland-covers")
        self.assertEqual(poland["eta_earliest"], "2026-12-13")     # +7+40

    def test_in_production_adds_60_days_and_spring_buffer(self):
        result = plan_dates("in_production", pd.Timestamp(AUDIT).date(), "美东-CENTRADE")
        self.assertEqual(result["eta_earliest"], "2027-02-06")     # +60+7+35
        self.assertTrue(result["spring_crossing"])
        self.assertEqual(result["spring_buffer_days"], 60)
        self.assertEqual(result["eta_latest"], "2027-04-07")
        self.assertEqual(result["confidence"], "assumed")

    def test_in_transit_has_no_date(self):
        result = plan_dates("shipped_in_transit", pd.Timestamp(AUDIT).date(), "美东-CENTRADE")
        self.assertIsNone(result["eta_earliest"])
        self.assertEqual(result["confidence"], "unknown")

    def test_unknown_stage_has_no_date(self):
        result = plan_dates("unknown", pd.Timestamp(AUDIT).date(), "美东-CENTRADE")
        self.assertIsNone(result["eta_latest"])


class TrancheTests(unittest.TestCase):
    def _w1(self, conserved=True):
        rows = [payload("SO-1",
                        [line("SO-1", "L1", "美东公司（CENTADE）", "PK#KS0001-X")],
                        [balance("SO-1", "L1", "PK#KS0001-X", "produced_pending_dn", 12.0),
                         balance("SO-1", "L1", "PK#KS0001-X", "shipped_in_transit", 5.0)])]
        return rows

    def test_conversion_and_branch_mapping(self):
        frame = build_tranches(self._w1(), {"SO-1": True})
        row = frame.iloc[0]
        self.assertEqual(row["canonical_sku"], "KS0001-X")
        self.assertTrue(bool(row["conversion_assumed"]))
        self.assertEqual(row["branch_warehouse"], "美东-CENTRADE")

    def test_conserved_rows_can_be_authoritative(self):
        frame = build_tranches(self._w1(), {"SO-1": True})
        pending = frame[frame["stage"] == "produced_pending_dn"].iloc[0]
        self.assertTrue(bool(pending["authoritative_offset"]))
        transit = frame[frame["stage"] == "shipped_in_transit"].iloc[0]
        self.assertFalse(bool(transit["authoritative_offset"]))   # 无日期
        self.assertTrue(transit["dedup_status"].startswith("po_in_transit_unproven"))

    def test_non_conserved_rows_are_not_authoritative(self):
        frame = build_tranches(self._w1(), {"SO-1": False})
        pending = frame[frame["stage"] == "produced_pending_dn"].iloc[0]
        self.assertFalse(bool(pending["authoritative_offset"]))
        self.assertFalse(bool(pending["so_conserved"]))

    def test_missing_dn_is_still_conditional(self):
        rows = [payload("SO-1", [line("SO-1", "L1", "美中公司（DANEEY）", "KS2")],
                        [balance("SO-1", "L1", "KS2", "produced_pending_dn", 9.0,
                                 exclusion="缺出库单")])]
        frame = build_tranches(rows, {"SO-1": True})
        row = frame.iloc[0]
        self.assertTrue(bool(row["authoritative_offset"]))
        self.assertEqual(row["exclusion_reason"], "缺出库单")
        self.assertEqual(row["confidence"], "assumed")

    def test_fba_rows_have_no_branch(self):
        rows = [payload("SO-9", [line("SO-9", "L1", "美国FBA仓", "KS3")],
                        [balance("SO-9", "L1", "KS3", "produced_pending_dn", 4.0,
                                 scope="external_fba")])]
        frame = build_tranches(rows, {"SO-9": True})
        row = frame.iloc[0]
        self.assertIsNone(row["branch_warehouse"])
        self.assertFalse(bool(row["authoritative_offset"]))

    def test_layer_overlap_is_flagged(self):
        rows = [payload("SO-1", [line("SO-1", "L1", "美东公司（CENTADE）", "KS1")],
                        [balance("SO-1", "L1", "KS1", "produced_pending_dn", 5.0),
                         balance("SO-1", "L1", "KS1", "in_production", 5.0)])]
        frame = build_tranches(rows, {"SO-1": True})
        self.assertTrue(frame["layer_overlap_unproven"].all())


class KeyAggregationTests(unittest.TestCase):
    def _inputs(self, conserved=True):
        rows = [payload("SO-1", [line("SO-1", "L1", "美东公司（CENTADE）", "KS1")],
                        [balance("SO-1", "L1", "KS1", "produced_pending_dn", 30.0),
                         balance("SO-1", "L1", "KS1", "shipped_in_transit", 100.0)])]
        frame = build_tranches(rows, {"SO-1": conserved})
        windows = pd.DataFrame([
            dict(window_days=90, canonical_sku="KS1", canonical_warehouse="美东-CENTRADE",
                 canonical_uom="个", cum_unserved=100.0, bucket_end="2027-01-25T05:17:34+08:00"),
            dict(window_days=150, canonical_sku="KS1", canonical_warehouse="美东-CENTRADE",
                 canonical_uom="个", cum_unserved=100.0, bucket_end="2027-03-29T05:17:34+08:00"),
        ])
        return frame, windows

    def test_gap_reduced_by_conserved_dated_qty(self):
        frame, windows = self._inputs(conserved=True)
        by_key = build_by_key(frame, windows)
        row = by_key.iloc[0]
        self.assertEqual(row["canonical_sku"], "KS1")
        self.assertEqual(row["conditional_dated_qty"], 30.0)
        self.assertEqual(row["in_transit_qty_no_eta"], 100.0)
        self.assertEqual(row["gap90_base"], 100.0)
        self.assertEqual(row["gap90_with"], 70.0)      # 12-08 ETA ≤ 2027-01-25
        self.assertEqual(row["gap150_with"], 70.0)
        self.assertFalse(row["netting_key_present"] is False)   # 有净额键

    def test_non_conserved_does_not_reduce_gap(self):
        frame, windows = self._inputs(conserved=False)
        by_key = build_by_key(frame, windows)
        row = by_key.iloc[0]
        self.assertEqual(row["conditional_dated_qty"], 0.0)
        self.assertEqual(row["conditional_dated_qty_all"], 30.0)
        self.assertEqual(row["gap90_with"], 100.0)

    def test_key_without_netting_row_keeps_null_gap(self):
        frame, _ = self._inputs(conserved=True)
        by_key = build_by_key(frame, None)
        row = by_key.iloc[0]
        self.assertTrue(pd.isna(row["gap90_base"]))
        self.assertTrue(pd.isna(row["gap90_with"]))
        self.assertEqual(row["conditional_dated_qty"], 30.0)


if __name__ == "__main__":
    unittest.main()
