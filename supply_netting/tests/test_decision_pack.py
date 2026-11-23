# -*- coding: utf-8 -*-
"""广范围补货决策包：去向对账、UOM 隔离、两档情景、可追溯性。"""

from __future__ import annotations

import json
import tempfile
import unittest
from pathlib import Path

import pandas as pd

from supply_netting.decision_pack import (DEST_NONE, DEST_SUGGEST, DEST_UNKNOWN,
                                          DEST_VERIFY, Inputs, build_pack, manifest,
                                          write_outputs)

KEY = ["canonical_sku", "canonical_warehouse", "canonical_uom"]


def netting_row(sku="S1", wh="W", uom="个", bucket="protect", *, demand=10.0, receipts=0.0,
                opening=0.0, unserved=None, gap=None, status="conditional", reason=None,
                conditional=0.0):
    if unserved is None:
        unserved = None if opening is None else demand - min(demand, opening + receipts)
    if gap is None:
        gap = None if unserved is None else max(0.0, unserved)
    return dict(canonical_sku=sku, canonical_warehouse=wh, canonical_uom=uom,
                scenario="expected", bucket_id=bucket, period_demand=demand,
                receipts=receipts, unserved=unserved, gap=gap, opening=opening,
                opening_lower_bound=opening, conditional_receipts=conditional,
                status=status, unknown_reason=reason)


def make_inputs(netting, review, facts=None, forecast=None, sku_map=None, history=None) -> Inputs:
    review = pd.DataFrame(review)
    facts = pd.DataFrame(facts or [], columns=["disposition_reason", "source_layer",
                                               "canonical_sku", "canonical_warehouse",
                                               "canonical_uom", "qty"])
    forecast = pd.DataFrame(forecast or [], columns=["tongtool_sku", "canonical_warehouse",
                                                     "canonical_uom", "lead_days",
                                                     "netting_eligible",
                                                     "netting_block_reason"])
    sku_map = pd.DataFrame(sku_map or [], columns=["tongtool_sku", "item_codes", "n_items",
                                                   "mapping_status", "mapping_evidence"])
    buckets = {"protect": {"start": "2026-10-26T05:17:34+08:00",
                           "end": "2026-11-02T05:17:34+08:00", "granularity": "bucket"}}
    doc = dict(run_id="run-test", as_of="2026-10-26T05:17:34+08:00",
               buckets=[dict(bucket_id="protect", **buckets["protect"])],
               forecast=dict(run_id="forecast-test", lead_days=60, window_start="2026-10-29",
                             window_end="2026-12-28", manifest_sha256="a" * 64,
                             windows_sha256="b" * 64, code_git_head="d6f63fd3"),
               inputs=dict(demand_netting=dict(date_max="2026-10-26")),
               partial=True, partial_reasons=["test"], checks={})
    sources = dict(forecast_rows_in=len(forecast), horizon_end="2026-11-30T05:17:34+08:00",
                   history=dict(path="x", sha256="h" * 64, matches_r5=True),
                   sku_map=dict(path="y", sha256="s" * 64),
                   r5=dict(supply_netting=dict(sha256="1" * 64),
                           replenishment_review=dict(sha256="2" * 64),
                           supply_facts=dict(sha256="3" * 64)))
    return Inputs(run_dir=Path("."), manifest=doc, netting=pd.DataFrame(netting),
                  review=review, facts=facts, forecast_windows=forecast,
                  forecast_meta=dict(doc["forecast"]), sku_map=sku_map,
                  history=history if history is not None else pd.DataFrame(
                      columns=["canonical_sku", "canonical_warehouse", "canonical_uom",
                               "demand_date", "quantity"]),
                  buckets=buckets, sources=sources)


def review_row(sku="S1", wh="W", uom="个", *, demand=10.0, gap=10.0, unserved=10.0):
    return dict(canonical_sku=sku, canonical_warehouse=wh, canonical_uom=uom,
                protect_demand=demand, protect_gap=gap, horizon_unserved=unserved,
                needs_review="")


class DecisionPackTests(unittest.TestCase):
    def test_every_key_has_exactly_one_destination_and_counts_reconcile(self):
        netting = [netting_row("SUG"), netting_row("NONE", opening=50.0, demand=10.0),
                   netting_row("UNK", opening=None, demand=5.0, unserved=None, gap=None,
                               status="unknown", reason="no_snapshot_basis")]
        review = [review_row("SUG"), review_row("NONE", gap=0.0, unserved=0.0),
                  review_row("UNK", gap=None, unserved=None)]
        facts = [dict(disposition_reason="outside_demand_scope",
                      source_layer="inventory_snapshot", canonical_sku="STOCKONLY",
                      canonical_warehouse="W", canonical_uom="个", qty=7.0)]
        forecast = [dict(tongtool_sku="TT1", canonical_warehouse="W", canonical_uom="个",
                         lead_days=60, netting_eligible=False,
                         netting_block_reason="subwarehouse_identity_unproven")]
        sku_map = [dict(tongtool_sku="TT1", item_codes=("FORECAST_ONLY",), n_items=1,
                        mapping_status="mapped", mapping_evidence="t")]
        inputs = make_inputs(netting, review, facts, forecast, sku_map)
        result, stats = build_pack(inputs)

        self.assertEqual(len(result), stats["universe_keys"])
        self.assertTrue(stats["reconciliation_ok"])
        self.assertEqual(sum(stats["destinations"].values()), stats["universe_keys"])
        self.assertEqual(set(result["destination"]), {DEST_SUGGEST, DEST_NONE, DEST_UNKNOWN,
                                                      DEST_VERIFY})
        self.assertEqual(result.loc[result.canonical_sku == "SUG", "destination"].iloc[0],
                         DEST_SUGGEST)
        self.assertEqual(result.loc[result.canonical_sku == "UNK", "destination"].iloc[0],
                         DEST_UNKNOWN)
        self.assertEqual(result.loc[result.canonical_sku == "STOCKONLY", "destination"].iloc[0],
                         DEST_VERIFY)
        self.assertEqual(result.loc[result.canonical_sku == "FORECAST_ONLY", "destination"].iloc[0],
                         DEST_VERIFY)

    def test_uom_groups_never_merge(self):
        netting = [netting_row("S1", uom="个", demand=10.0),
                   netting_row("S1", uom="套", demand=3.0, opening=5.0)]
        review = [review_row("S1", uom="个"), review_row("S1", uom="套", gap=0.0, unserved=0.0)]
        result, stats = build_pack(make_inputs(netting, review))
        self.assertEqual(len(result), 2)
        by_uom = {row["uom"]: row for row in stats["scenarios_by_uom"]}
        self.assertEqual(by_uom["个"]["qty_current"], 10.0)
        self.assertNotIn("套", by_uom)          # 套没有建议键，不产生情景标量
        self.assertEqual(stats["single_uom"], "个")
        self.assertIn("跨 UOM 不相加", stats["uom_note"])

    def test_two_service_tiers_and_extra_holding(self):
        netting = [netting_row("S1", demand=100.0, opening=0.0)]
        review = [review_row("S1", demand=100.0, gap=100.0, unserved=100.0)]
        result, stats = build_pack(make_inputs(netting, review))
        row = result.iloc[0]
        self.assertEqual(row["qty_current"], 100.0)
        self.assertGreaterEqual(row["qty_higher"], row["qty_current"])
        self.assertEqual(stats["scenarios"][0]["scenario"], "current_policy")
        self.assertEqual(stats["scenarios"][1]["scenario"], "higher_service_flat95")
        self.assertIn("不是覆盖率承诺", stats["scenarios"][1]["note"])

    def test_conditional_supply_creates_a_counterfactual_low_end(self):
        netting = [netting_row("S1", demand=40.0, opening=0.0, conditional=30.0)]
        review = [review_row("S1", demand=40.0, gap=40.0, unserved=40.0)]
        result, _ = build_pack(make_inputs(netting, review))
        row = result.iloc[0]
        self.assertEqual(row["qty_high"], 40.0)
        self.assertEqual(row["qty_low_counterfactual"], 10.0)
        self.assertIn("条件供应", row["to_verify"])
        self.assertIn("反事实", row["qty_low_semantics"])

    def test_unknown_opening_is_not_given_quantities(self):
        netting = [netting_row("S1", demand=5.0, opening=None, status="unknown",
                               reason="opening_partially_unproven")]
        review = [review_row("S1", demand=5.0, gap=None, unserved=None)]
        result, _ = build_pack(make_inputs(netting, review))
        row = result.iloc[0]
        self.assertEqual(row["destination"], DEST_UNKNOWN)
        for column in ("gap_today", "horizon_demand", "protect_gap", "qty_current",
                       "qty_high", "qty_low_counterfactual"):
            self.assertTrue(pd.isna(row[column]), column)

    def test_every_row_is_traceable_to_runs(self):
        netting = [netting_row("S1")]
        review = [review_row("S1")]
        result, _ = build_pack(make_inputs(netting, review))
        row = result.iloc[0]
        self.assertEqual(row["forecast_run_id"], "forecast-test")
        self.assertEqual(row["netting_run_id"], "run-test")
        self.assertIn("forecast forecast-test", row["basis_forecast"])
        self.assertEqual(row["data_cutoff"], "2026-10-26")

    def test_outputs_round_trip_and_manifest_marks_limits(self):
        netting = [netting_row("S1"), netting_row("S2", opening=50.0, demand=10.0)]
        review = [review_row("S1"), review_row("S2", gap=0.0, unserved=0.0)]
        inputs = make_inputs(netting, review)
        result, stats = build_pack(inputs)
        doc = manifest(inputs, stats, out_dir=Path("."), data_cutoff="2026-10-26",
                       code=dict(git_head="deadbeef", git_dirty=False))
        with tempfile.TemporaryDirectory() as tmp:
            outputs = write_outputs(result, stats, doc, Path(tmp))
            back = pd.read_parquet(outputs["parquet"])
            excel = pd.read_excel(outputs["xlsx"], sheet_name="决策清单")
            with pd.ExcelFile(outputs["xlsx"]) as excel_file:
                sheet_names = excel_file.sheet_names
            manifest_json = json.loads(Path(outputs["manifest"]).read_text(encoding="utf-8"))
        self.assertEqual(len(back), len(result))
        self.assertEqual(len(excel), len(result))
        for name in ("决策清单", "去向对账", "源行对账", "情景对照", "数据与限制",
                     "预测源行排除", "Manifest"):
            self.assertIn(name, sheet_names)
        self.assertEqual(manifest_json["decision_date"], "2026-10-29")
        self.assertTrue(manifest_json["limits"])
        self.assertEqual(manifest_json["coverage"]["destinations"], stats["destinations"])


if __name__ == "__main__":
    unittest.main()
