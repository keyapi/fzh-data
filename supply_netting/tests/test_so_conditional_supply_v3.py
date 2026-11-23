# -*- coding: utf-8 -*-
"""SO 条件供给 v3：逐行封顶、首工序/FBA 剔除、按 UOM、缺口含/不含、v2 差异。"""

from __future__ import annotations

import tempfile
import unittest
from pathlib import Path

import pandas as pd

from supply_netting.scripts.so_conditional_supply_v3 import (build_by_key, build_diff,
                                                             build_tranches, resolve_uom,
                                                             summarize)

AS_OF = "2026-10-27"


def line(item="KS1", qty=100.0, so_line="L1", customer="美东公司（CENTADE）", uom="个"):
    return dict(so="SO-1", so_line=so_line, item_code=item, customer=customer, qty=qty,
                delivered_qty=0.0, uom=uom, warehouse="成品仓 - FZH", scope="in_house",
                role="finished")


def bal(stage, qty, *, item="KS1", so_line="L1", record="", exclusion="", basis="",
        scope="in_house", status="known", uom="个"):
    return dict(so="SO-1", so_line_id=so_line, item_code=item, warehouse="成品仓 - FZH",
                uom=uom, stage=stage, stage_detail="", qty=qty, qty_status=status,
                qty_basis=basis, cumulative_excess_qty=None, batch_key=record,
                source_record=record, exclusion_reason=exclusion,
                included_in_stock="unknown", demand_status="active", scope=scope,
                role="finished")


def payload(lines, balances):
    return {"so": "SO-1", "as_of": AS_OF, "lines": lines,
            "stage_balances": balances, "links": []}


def run(lines, balances):
    tranches, excluded = build_tranches([{"so": "SO-1", "payload": payload(lines, balances)}])
    return tranches, excluded


class V3FilterTests(unittest.TestCase):
    def test_first_op_and_fba_are_excluded(self):
        tranches, excluded = run(
            [line(qty=100.0)],
            [bal("in_production", 40.0, record="WO-1"),
             bal("produced_pending_dn", 30.0, basis="job_card_first_op"),
             bal("shipped_in_transit", 10.0, record="DN-1"),
             bal("shipped_in_transit", 10.0, record="DN-2", scope="external_fba")])
        self.assertEqual(sorted(tranches["stage"]), ["in_production", "shipped_in_transit"])
        self.assertEqual(tranches["candidate_qty"].sum(), 50.0)
        # 剔除量按「原因 → 来源单位标签 → 数量」记账，不再跨单位相加
        self.assertEqual(excluded["first_op_basis"]["个"], 30.0)
        self.assertEqual(excluded["excess:fba_external"]["个"], 10.0)

    def test_over_ship_excess_not_counted(self):
        tranches, _ = run([line(qty=50.0)],
                          [bal("shipped_in_transit", 80.0, record="DN-1")])
        row = tranches.iloc[0]
        self.assertEqual(row["candidate_qty"], 50.0)    # 封顶到订单行
        self.assertEqual(row["excess_class"], "over_ship")

    def test_uom_kept_separate(self):
        tranches, _ = run(
            [line(qty=10.0), line(item="KS2", qty=3.0, so_line="L2", uom="件")],
            [bal("in_production", 10.0, record="WO-1"),
             bal("in_production", 3.0, item="KS2", so_line="L2", record="WO-2", uom="件")])
        by_uom = tranches.groupby("uom")["candidate_qty"].sum().to_dict()
        self.assertEqual(by_uom, {"个": 10.0, "件": 3.0})

    def test_offset_allowed_is_false(self):
        tranches, _ = run([line(qty=10.0)], [bal("in_production", 10.0, record="WO-1")])
        self.assertTrue((tranches["offset_allowed"] == False).all())  # noqa: E712


class UomCanonicalTests(unittest.TestCase):
    def test_uom_comes_from_en_stock_uom(self):
        self.assertEqual(resolve_uom("KS1", "KS1", "件", {"KS1": "个"})[0], "个")
        uom, source, proven, _ = resolve_uom("KS1", "KS1", "个", {})
        self.assertIsNone(uom)
        self.assertEqual(source, "unproven")
        self.assertFalse(proven)

    def test_tj_bundle_is_forced_to_set(self):
        uom, source, proven, note = resolve_uom(
            "TJ#KS1x1_KS2x1-001", "TJ#KS1x1_KS2x1-001", "个", {})
        self.assertEqual(uom, "套")
        self.assertEqual(source, "tj_bundle_rule")
        self.assertTrue(proven)

    def test_pk_cover_uses_ks_uom_one_to_one(self):
        # PK# -> KS x1：按 KS 的「个」，不是套
        self.assertEqual(resolve_uom("PK#KS1", "KS1", "个", {"KS1": "个"})[0], "个")

    def test_unproven_uom_is_excluded_from_totals(self):
        tranches, excluded = build_tranches(
            [{"so": "SO-1", "payload": payload(
                [line(qty=100.0)],
                [bal("in_production", 40.0, record="WO-1", item="KS1"),
                 bal("in_production", 30.0, record="WO-2", item="ND#KS1")])}],
            {"KS1": "个"})
        included = tranches[tranches["included"]]
        self.assertEqual(float(included["candidate_qty"].sum()), 40.0)
        unproven = tranches[~tranches["included"]]
        self.assertEqual(float(unproven["candidate_qty"].sum()), 30.0)
        self.assertTrue(unproven["uom"].isna().all())
        self.assertEqual(excluded["uom_unproven"]["个"], 30.0)   # 只按来源标签记账

    def test_ge_and_tao_are_never_summed(self):
        tranches, _ = build_tranches(
            [{"so": "SO-1", "payload": payload(
                [line(qty=10.0), line(item="TJ#KS2x1-001", qty=2.0, so_line="L2", uom="套")],
                [bal("in_production", 10.0, record="WO-1", item="KS1"),
                 bal("in_production", 2.0, record="WO-2", item="TJ#KS2x1-001",
                     so_line="L2", uom="套")])}],
            {"KS1": "个", "TJ#KS2x1-001": "套"})
        by_uom = tranches[tranches["included"]].groupby("uom")["candidate_qty"].sum().to_dict()
        self.assertEqual(by_uom, {"个": 10.0, "套": 2.0})


class GapScenarioTests(unittest.TestCase):
    def _windows(self, bucket_end):
        return pd.DataFrame([dict(window_days=150, canonical_sku="KS1",
                                  canonical_warehouse="美东-CENTRADE",
                                  canonical_uom="个", cum_unserved=100.0,
                                  bucket_end=bucket_end)])

    def test_spring_buffer_decides_whether_candidate_arrives_in_time(self):
        tranches, _ = run([line(qty=100.0)],
                          [bal("in_production", 40.0, record="WO-1")])
        by_key = build_by_key(tranches, self._windows("2027-03-29T05:17:34+08:00"))
        row = by_key.iloc[0]
        self.assertEqual(row["gap150_base"], 100.0)
        # 最晚 ETA 含春节 +60 天 = 2027-04-07 > 2027-03-29 → 保守情景不抵减
        self.assertEqual(row["gap150_with"], 100.0)
        # 最早 ETA 2027-02-06 ≤ 2027-03-29 → 乐观情景可抵减到 60
        self.assertEqual(row["gap150_with_optimistic"], 60.0)

    def test_candidate_after_bucket_end_does_not_reduce_gap(self):
        tranches, _ = run([line(qty=100.0)],
                          [bal("in_production", 40.0, record="WO-1")])
        by_key = build_by_key(tranches, self._windows("2027-01-25T05:17:34+08:00"))
        row = by_key.iloc[0]
        self.assertEqual(row["gap150_with"], 100.0)

    def test_transit_has_no_eta_and_never_offsets(self):
        tranches, _ = run([line(qty=100.0)],
                          [bal("shipped_in_transit", 60.0, record="DN-1")])
        by_key = build_by_key(tranches, self._windows("2027-12-31T00:00:00+08:00"))
        row = by_key.iloc[0]
        self.assertEqual(row["transit_qty_no_eta"], 60.0)
        self.assertEqual(row["candidate_dated_qty"], 0.0)
        self.assertEqual(row["gap150_with"], 100.0)

    def test_gap_matches_uom(self):
        tranches, _ = run([line(qty=100.0, uom="件")],
                          [bal("in_production", 40.0, record="WO-1", uom="件")])
        by_key = build_by_key(tranches, self._windows("2027-03-29T05:17:34+08:00"))
        row = by_key.iloc[0]
        self.assertEqual(row["uom"], "件")
        self.assertTrue(pd.isna(row["gap150_base"]))   # 个的缺口不能被子键抵减


class DiffTests(unittest.TestCase):
    def test_diff_reports_per_key_delta(self):
        tranches, _ = run([line(qty=100.0)],
                          [bal("in_production", 40.0, record="WO-1")])
        by_key = build_by_key(tranches, pd.DataFrame())
        with tempfile.TemporaryDirectory() as tmp:
            path = Path(tmp) / "v2.csv"
            pd.DataFrame([dict(canonical_sku="KS1", branch_warehouse="美东-CENTRADE",
                               uom="个", conditional_dated_qty=10.0,
                               gap90_base=0.0, gap90_with=0.0,
                               gap150_base=0.0, gap150_with=0.0)]).to_csv(
                path, index=False, encoding="utf-8-sig")
            diff = build_diff(by_key, path)
        row = diff[diff["canonical_sku"] == "KS1"].iloc[0]
        self.assertEqual(row["v2_candidate_qty"], 10.0)
        self.assertEqual(row["candidate_dated_qty"], 40.0)
        self.assertEqual(row["delta_qty"], 30.0)


if __name__ == "__main__":
    unittest.main()


class DisclosureFixTests(unittest.TestCase):
    """复审返修：不跨未知单位合计、FBA 超量按单位拆、报告不再自相矛盾。"""

    def test_uom_unproven_is_not_totalled_across_units(self):
        tranches, excluded = build_tranches(
            [{"so": "SO-1", "payload": payload(
                [line(qty=100.0)],
                [bal("in_production", 40.0, record="WO-1", item="KS1"),
                 bal("in_production", 30.0, record="WO-2", item="ND#KS1"),
                 bal("in_production", 12.0, record="WO-3", item="ND#KS2")])}],
            {"KS1": "个"})
        labels = excluded["uom_unproven"]
        self.assertEqual(sorted(labels), ["个"])      # 只有来源标签，没有求和
        stats = summarize(tranches, build_by_key(tranches, None), excluded)
        self.assertNotIn("uom_unproven_qty", stats)
        self.assertEqual(stats["uom_unproven_rows"], 2)
        self.assertIn("不是已证单位", stats["uom_unproven_note"])

    def test_fba_excess_is_split_by_unit(self):
        tranches, excluded = build_tranches(
            [{"so": "SO-1", "payload": payload(
                [line(qty=100.0)],
                [bal("in_production", 40.0, record="WO-1", item="KS1"),
                 bal("shipped_in_transit", 20.0, record="DN-1", scope="external_fba",
                     uom="个"),
                 bal("shipped_in_transit", 5.0, record="DN-2", scope="external_fba",
                     uom="套")])}],
            {"KS1": "个"})
        fba = excluded.get("excess:fba_external") or {}
        self.assertEqual(fba.get("个"), 20.0)
        self.assertEqual(fba.get("套"), 5.0)
