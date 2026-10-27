# -*- coding: utf-8 -*-
"""终审 F1–F7 回归（final-review-e1ea2bbb）。"""

from __future__ import annotations

import json
import tempfile
import unittest
from pathlib import Path

import pandas as pd

from supply_netting import decision_pack as dp
from supply_netting.decision_pack import (FROZEN_SKU_MAP_SHA256, _reconcile, _strict_json,
                                          _verify_r5_outputs, build_pack, load_inputs,
                                          manifest, write_outputs)
from supply_netting.tests.test_decision_pack import (KEY, make_inputs, netting_row,
                                                     review_row)

NULL_COLUMNS = ("gap_today", "horizon_demand", "protect_gap", "qty_current", "qty_high",
                "qty_low_counterfactual", "qty_higher", "extra_holding")


def _three_outputs(result, stats, inputs):
    doc = manifest(inputs, stats, out_dir=Path("."), data_cutoff="2026-10-26",
                   code=dict(git_head="deadbeef", git_dirty=False))
    tmp = tempfile.TemporaryDirectory()
    outputs = write_outputs(result, stats, doc, Path(tmp.name))
    return tmp, outputs


class F1NullSemantics(unittest.TestCase):
    def _pack(self):
        netting = [netting_row("SUG", demand=10.0),
                   netting_row("UNK", opening=None, demand=5.0, unserved=None, gap=None,
                               status="unknown", reason="no_snapshot_basis")]
        review = [review_row("SUG"), review_row("UNK", gap=None, unserved=None)]
        facts = [dict(disposition_reason="outside_demand_scope",
                      source_layer="inventory_snapshot", canonical_sku="VERIFY",
                      canonical_warehouse="W", canonical_uom="个", qty=7.0)]
        return make_inputs(netting, review, facts=facts)

    def test_unknown_and_not_covered_are_null_in_all_three_outputs(self):
        inputs = self._pack()
        result, stats = build_pack(inputs)
        unknown = result[result["destination"] == "不可算"].iloc[0]
        verify = result[result["destination"] == "待核"].iloc[0]
        for column in NULL_COLUMNS:
            self.assertTrue(pd.isna(unknown[column]), f"unknown {column}")
            self.assertTrue(pd.isna(verify[column]), f"verify {column}")

        tmp, outputs = _three_outputs(result, stats, inputs)
        self.addCleanup(tmp.cleanup)
        parquet = pd.read_parquet(outputs["parquet"]).set_index("canonical_sku")
        records = {row["canonical_sku"]: row
                   for row in json.loads(Path(outputs["json"]).read_text(encoding="utf-8"))}
        excel = pd.read_excel(outputs["xlsx"], sheet_name="决策清单").set_index("canonical_sku")
        for sku in ("UNK", "VERIFY"):
            for column in NULL_COLUMNS:
                self.assertTrue(pd.isna(parquet.loc[sku, column]), (sku, column, "parquet"))
                self.assertIsNone(records[sku][column], (sku, column, "json"))
                self.assertTrue(pd.isna(excel.loc[sku, column]), (sku, column, "xlsx"))

    def test_evidence_status_columns(self):
        inputs = self._pack()
        result, _ = build_pack(inputs)
        by_sku = result.set_index("canonical_sku")
        self.assertEqual(by_sku.loc["UNK", "demand_evidence_status"], "unknown")
        self.assertEqual(by_sku.loc["UNK", "gap_evidence_status"], "unknown")
        self.assertEqual(by_sku.loc["VERIFY", "demand_evidence_status"], "not_covered")
        self.assertEqual(by_sku.loc["VERIFY", "gap_evidence_status"], "not_covered")
        self.assertEqual(by_sku.loc["SUG", "demand_evidence_status"], "known")
        self.assertEqual(by_sku.loc["SUG", "gap_evidence_status"], "known")

    def test_measured_zero_is_not_confused_with_null(self):
        netting = [netting_row("ZERO", demand=0.0, opening=10.0, unserved=0.0, gap=0.0)]
        review = [review_row("ZERO", demand=0.0, gap=0.0, unserved=0.0)]
        result, _ = build_pack(make_inputs(netting, review))
        row = result.iloc[0]
        self.assertEqual(row["value_status"], "measured_zero")
        self.assertEqual(row["gap_today"], 0.0)
        self.assertEqual(row["horizon_demand"], 0.0)


class F2StrictJson(unittest.TestCase):
    def test_strict_json_rejects_nan_and_emits_null(self):
        with self.assertRaises(ValueError):
            _strict_json([{"value": float("nan")}])
        text = _strict_json([{"value": None, "other": 1}])
        self.assertIn("null", text)
        self.assertNotIn("NaN", text)
        self.assertEqual(json.loads(text, parse_constant=lambda t: (_ for _ in ()).throw(
            ValueError(t)))[0]["value"], None)

    def test_exported_json_has_no_nan_tokens_and_parses_strictly(self):
        netting = [netting_row("SUG"), netting_row("UNK", opening=None, demand=5.0,
                                                  unserved=None, gap=None, status="unknown",
                                                  reason="no_snapshot_basis")]
        review = [review_row("SUG"), review_row("UNK", gap=None, unserved=None)]
        inputs = make_inputs(netting, review)
        result, stats = build_pack(inputs)
        tmp, outputs = _three_outputs(result, stats, inputs)
        self.addCleanup(tmp.cleanup)
        text = Path(outputs["json"]).read_text(encoding="utf-8")
        self.assertNotIn("NaN", text)
        self.assertNotIn("Infinity", text)

        def reject(token):
            raise ValueError(f"non-strict constant {token}")

        payload = json.loads(text, parse_constant=reject)
        self.assertEqual(len(payload), len(result))


class F3UomAggregation(unittest.TestCase):
    def test_mixed_uom_has_no_unscaled_scalar(self):
        netting = [netting_row("S1", uom="个", demand=10.0),
                   netting_row("S1", uom="套", demand=3.0)]
        review = [review_row("S1", uom="个"), review_row("S1", uom="套", gap=3.0, unserved=3.0)]
        result, stats = build_pack(make_inputs(netting, review))
        self.assertIsNone(stats["single_uom"])
        for scenario in stats["scenarios"]:
            self.assertIsNone(scenario["suggest_qty"], scenario)
            self.assertIsNone(scenario["uom"])
        by_uom = {row["uom"]: row for row in stats["scenarios_by_uom"]}
        self.assertEqual(by_uom["个"]["qty_current"], 10.0)
        self.assertEqual(by_uom["套"]["qty_current"], 3.0)
        # 顶层不产生跨 UOM 的无单位合计
        self.assertNotIn("suggest_qty_current", stats)
        self.assertNotIn("gap_today_total", stats)

    def test_abc_tiers_are_computed_within_each_uom(self):
        netting = [netting_row("A1", uom="个", demand=100.0),
                   netting_row("A2", uom="个", demand=10.0),
                   netting_row("B1", uom="套", demand=5.0)]
        review = [review_row("A1", uom="个"), review_row("A2", uom="个", gap=10.0, unserved=10.0),
                  review_row("B1", uom="套", gap=5.0, unserved=5.0)]
        result, _ = build_pack(make_inputs(netting, review))
        tiers = result.set_index("canonical_sku")["service_tier"]
        self.assertEqual(tiers.loc["B1"], "A")      # 套组内第一名，不是跨 UOM 的 C
        self.assertEqual(tiers.loc["A1"], "A")


class F4IndependentReconciliation(unittest.TestCase):
    def test_missing_input_key_fails_reconciliation(self):
        netting = [netting_row("S1"), netting_row("S2")]
        review = [review_row("S1"), review_row("S2")]
        inputs = make_inputs(netting, review)
        result, stats = build_pack(inputs)
        input_keys = pd.DataFrame([{"canonical_sku": "S1", "canonical_warehouse": "W",
                                    "canonical_uom": "个"},
                                   {"canonical_sku": "S2", "canonical_warehouse": "W",
                                    "canonical_uom": "个"}])
        with self.assertRaises(ValueError):
            _reconcile(result[result["canonical_sku"] == "S1"], input_keys, inputs, [])

    def test_forecast_source_rows_are_fully_accounted(self):
        forecast = [dict(tongtool_sku="TT1", canonical_warehouse="W", canonical_uom="个",
                         lead_days=60, netting_eligible=True, netting_block_reason=None),
                    dict(tongtool_sku="TT-UNMAPPED", canonical_warehouse="W",
                         canonical_uom="个", lead_days=60, netting_eligible=False,
                         netting_block_reason="sku_mapping_missing"),
                    dict(tongtool_sku="TT2", canonical_warehouse="W", canonical_uom="unknown",
                         lead_days=60, netting_eligible=False,
                         netting_block_reason="uom_missing")]
        sku_map = [dict(tongtool_sku="TT1", item_codes=("S1",), n_items=1,
                        mapping_status="mapped", mapping_evidence="t"),
                   dict(tongtool_sku="TT2", item_codes=("S2",), n_items=1,
                        mapping_status="mapped", mapping_evidence="t")]
        netting = [netting_row("S1")]
        review = [review_row("S1")]
        inputs = make_inputs(netting, review, forecast=forecast, sku_map=sku_map)
        _, stats = build_pack(inputs)
        ledger = stats["source_ledger"]
        self.assertEqual(ledger["forecast_rows_in"], 3)
        self.assertEqual(ledger["forecast_rows_excluded"], 2)
        self.assertEqual(ledger["forecast_rows_normalized"], 1)
        reasons = ledger["forecast_excluded_reasons"]
        self.assertEqual(reasons.get("sku_mapping_missing_or_ambiguous"), 1)
        self.assertEqual(reasons.get("uom_missing"), 1)
        self.assertEqual({row["raw_sku"] for row in ledger["forecast_excluded_rows"]},
                         {"TT-UNMAPPED", "TT2"})


def _fake_run(tmp: Path, history_sha: str, *, corrupt_r5: bool = False) -> tuple[Path, Path]:
    """构造一个最小 r5 run + forecast root，供 load_inputs 的哈希校验测试。"""
    run_dir = tmp / "run"
    run_dir.mkdir(parents=True)
    netting = pd.DataFrame([netting_row("S1")])
    review = pd.DataFrame([review_row("S1")])
    facts = pd.DataFrame(columns=["disposition_reason", "source_layer", "canonical_sku",
                                  "canonical_warehouse", "canonical_uom", "qty"])
    for name, frame in (("supply_netting", netting), ("replenishment_review", review),
                        ("supply_facts", facts)):
        frame.to_parquet(run_dir / f"{name}.parquet", index=False)
    forecast_root = tmp / "forecast"
    fx = forecast_root / "fx"
    fx.mkdir(parents=True)
    (forecast_root / "CURRENT").write_text("fx", encoding="utf-8")
    windows = pd.DataFrame([dict(tongtool_sku="TT1", canonical_warehouse="W",
                                 canonical_uom="个", lead_days=60, netting_eligible=True,
                                 netting_block_reason=None, window_start="2026-10-29",
                                 window_end="2026-12-28", p50=1.0)])
    windows.to_parquet(fx / "forecast_sku_warehouse_windows.parquet", index=False)
    (fx / "forecast_manifest.json").write_text(json.dumps({
        "schema_version": "en-demand-forecast-v1", "run_id": "fx",
        "run": {"decision_date": "2026-10-29", "data_cutoff": "2026-10-26"},
        "code": {"git_head": "d6f63fd3"},
        "outputs": [{"file": "forecast_sku_warehouse_windows.parquet", "rows": 1,
                     "sha256": dp._sha(fx / "forecast_sku_warehouse_windows.parquet")}],
    }), encoding="utf-8")
    outputs = {f"{name}_sha256": dp._sha(run_dir / f"{name}.parquet")
               for name in ("supply_netting", "replenishment_review", "supply_facts")}
    if corrupt_r5:
        outputs["supply_netting_sha256"] = "0" * 64
    manifest_doc = dict(
        run_id="run-test", as_of="2026-10-26T05:17:34+08:00",
        buckets=[dict(bucket_id="protect", start="2026-10-26T05:17:34+08:00",
                      end="2026-11-02T05:17:34+08:00")],
        forecast=dict(run_id="fx", lead_days=60, window_start="2026-10-29",
                      window_end="2026-12-28",
                      manifest_sha256=dp._sha(fx / "forecast_manifest.json"),
                      windows_sha256=dp._sha(fx / "forecast_sku_warehouse_windows.parquet")),
        inputs=dict(demand_netting=dict(date_max="2026-10-26", sha256=history_sha)),
        partial=True, partial_reasons=["test"], checks={}, outputs=outputs,
    )
    (run_dir / "supply_netting_manifest.json").write_text(json.dumps(manifest_doc),
                                                          encoding="utf-8")
    return run_dir, forecast_root


class F5InputLocking(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.addCleanup(self.tmp.cleanup)
        self.root = Path(self.tmp.name)
        self.history = self.root / "demand_netting.parquet"
        pd.DataFrame([dict(canonical_sku="S1", canonical_warehouse="W", canonical_uom="个",
                           demand_date="2026-10-20", quantity_default=3.0,
                           in_default_series=True)]).to_parquet(self.history, index=False)
        self.sku_map = self.root / "sku_map.tsv"
        self.sku_map.write_text("S1\tTT1\tX\n", encoding="utf-8")

    def test_manifest_records_history_and_sku_map_hashes(self):
        run_dir, forecast_root = _fake_run(self.root, dp._sha(self.history))
        inputs = load_inputs(run_dir, forecast_root=forecast_root,
                             demand_netting=self.history, sku_map_path=self.sku_map,
                             expected_sku_map_sha256=None)
        self.assertEqual(inputs.sources["history"]["sha256"], dp._sha(self.history))
        self.assertEqual(inputs.sources["sku_map"]["sha256"], dp._sha(self.sku_map))
        result, stats = build_pack(inputs)
        doc = manifest(inputs, stats, out_dir=self.root, data_cutoff="2026-10-26",
                       code=dict(git_head="x", git_dirty=False))
        self.assertEqual(doc["inputs"]["demand_netting"], dp._sha(self.history))
        self.assertEqual(doc["inputs"]["sku_map"], dp._sha(self.sku_map))
        self.assertTrue(doc["verification"]["history_matches_r5"])
        self.assertEqual(doc["forecast_generated_by"], "d6f63fd3")
        self.assertEqual(doc["reviewed_commit"], "6a7d56bd")

    def test_history_hash_mismatch_is_refused(self):
        run_dir, forecast_root = _fake_run(self.root, "0" * 64)
        with self.assertRaises(ValueError):
            load_inputs(run_dir, forecast_root=forecast_root,
                        demand_netting=self.history, sku_map_path=self.sku_map,
                        expected_sku_map_sha256=None)

    def test_frozen_sku_map_hash_is_enforced(self):
        run_dir, forecast_root = _fake_run(self.root, dp._sha(self.history))
        # 默认参数就是冻结哈希；临时 sku_map 必然不符 → 拒绝
        with self.assertRaises(ValueError):
            load_inputs(run_dir, forecast_root=forecast_root,
                        demand_netting=self.history, sku_map_path=self.sku_map)
        # 显式关闭（仅调试/测试）时记录为未校验，不冒充已验证
        inputs = load_inputs(run_dir, forecast_root=forecast_root,
                             demand_netting=self.history, sku_map_path=self.sku_map,
                             expected_sku_map_sha256=None)
        self.assertFalse(inputs.sources["sku_map"]["verified"])
        self.assertIsNone(inputs.sources["sku_map"]["expected_sha256"])
        self.assertEqual(FROZEN_SKU_MAP_SHA256,
                         "7da3dfd62969c2c06f5b01ce752ccd1bc8d26c46c693eaca22cacaad4d13d42e")

    def test_r5_output_hash_mismatch_is_refused(self):
        run_dir, forecast_root = _fake_run(self.root, dp._sha(self.history), corrupt_r5=True)
        with self.assertRaises(ValueError):
            load_inputs(run_dir, forecast_root=forecast_root,
                        demand_netting=self.history, sku_map_path=self.sku_map,
                        expected_sku_map_sha256=None)


class F6Counterfactual(unittest.TestCase):
    def test_qty_high_ignores_conditional_and_low_is_marked(self):
        netting = [netting_row("S1", demand=44.0, opening=0.0, conditional=110.0)]
        review = [review_row("S1", demand=44.0, gap=44.0, unserved=44.0)]
        result, _ = build_pack(make_inputs(netting, review))
        row = result.iloc[0]
        self.assertEqual(row["qty_high"], 44.0)          # 不扣条件供应
        self.assertEqual(row["qty_low_counterfactual"], 0.0)
        self.assertIn("不可采用", row["qty_low_semantics"])
        self.assertIn("反事实", row["qty_low_semantics"])


class F7GapBucket(unittest.TestCase):
    def test_bucket_fields_and_notes(self):
        netting = [netting_row("S1", demand=10.0)]
        review = [review_row("S1")]
        result, _ = build_pack(make_inputs(netting, review))
        row = result.iloc[0]
        self.assertEqual(row["first_gap_bucket_start"], "2026-10-26T05:17:34+08:00")
        self.assertEqual(row["first_gap_bucket_end"], "2026-11-02T05:17:34+08:00")
        self.assertIn("桶边界", row["bucket_granularity"])
        self.assertIn("视界末", row["gap_today_note"])
        self.assertIsNone(row["gap_today_note"] if row["destination"] != "建议补货" else None)


if __name__ == "__main__":
    unittest.main()
