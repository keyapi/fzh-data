# -*- coding: utf-8 -*-
"""Executable offline pipeline: saved responses -> position/full/timeline."""

import hashlib
import importlib.util
import json
import os
import subprocess
import sys
import tempfile
import unittest
from unittest.mock import patch
from pathlib import Path

from supply_chain_visibility.supply_pipeline import main
from supply_chain_visibility.publication import read_publication
from warehouse_restock.delivery_facts_adapter import _scope_hash

AS_OF = "2026-11-02T10:00:00+00:00"


def _scope():
    scope = {"status": "provided", "source": "approved_b",
             "version": "Bv6r10", "items": [{"item_code": "SKU-1"}]}
    scope["hash"] = _scope_hash(scope)
    return scope


def _delivery():
    scope = _scope()
    return {"schema_version": "supply-facts/v3", "rule_version": "2026-10-30.5",
            "implementation_version": "key_test.delivery_facts@2026-10-30.5",
            "scope": scope, "coverage": {"scope": scope}, "snapshot_id": "snap-1",
            "pagination": {"exhausted": True, "partial": False, "total": 1},
            "delivery_lines": [{
                "delivery_note": "DN-1", "delivery_note_item": "DNI-1",
                "item_code": "SKU-1", "uom": "个", "qty": 5, "actual_qty": 5,
                "is_return": 0, "docstatus": 1, "customer": "C1",
                "quantity_status": "known", "relevance_status": "in_scope",
                "warehouse": "WH-1", "target_warehouse": "WH-1"}]}


def _mappings():
    return {"source": "approved_b", "version": "Bv6r10", "rows": [{
        "delivery_note": "DN-1", "dn_item": "DNI-1", "item_code": "SKU-1",
        "tt_sku": "S1", "warehouse": "WH-1", "uom": "个",
        "purpose": "branch", "evidence": "Bv6r10"}]}


def _audit(lines=True):
    return {"delivery_note": "DN-1",
            "pagination": {"limit": 50, "offset": 0, "returned": 1, "total": 1,
                           "exhausted": True, "partial": False, "next_offset": None},
            "creations": [{"name": "TPO-1", "delivery_note": "DN-1",
                           "status": "confirmed",
                           "confirmed_at": AS_OF,
                           "purchase_order_code": "PO-1",
                           "lines": ([{"dn_item": "DNI-1", "item_code": "SKU-1",
                                       "qty": 5, "uom": "个", "tt_sku": "S1",
                                       "outcome": "included",
                                       "contribution_qty": 5}] if lines else [])}]}


def _status(raw="3"):
    # Shape produced by po_status_refresh (statuses) as well as API batch.
    return {"observed_at": AS_OF, "statuses": {"PO-1": {
        "found": True, "status": raw, "raw_status": raw, "is_voided": raw == "4",
        "observed_at": AS_OF, "cached": False,
        "identity": {"purchaseOrderCode": "PO-1"}}}}


@unittest.skipUnless(importlib.util.find_spec("pyarrow"), "requires pyarrow")
class PipelineTests(unittest.TestCase):
    def _write(self, root, name, payload):
        path = Path(root) / name
        path.write_text(json.dumps(payload), encoding="utf-8")
        return str(path)

    def _args(self, root, out, audit=None):
        return [
            "--delivery-json", self._write(root, "delivery.json", _delivery()),
            "--mapping-json", self._write(root, "mapping.json", _mappings()),
            "--audit-json", self._write(root, "audit.json", audit or _audit()),
            "--status-json", self._write(root, "status.json", _status("3")),
            "--inventory-json", self._write(root, "inventory.json",
                                            {"schema_version": "local/v1",
                                             "observed_at": AS_OF,
                                             "inventory": [{
                                                "item_code": "SKU-1", "uom": "个",
                                                "warehouse": "WH-1",
                                                "purpose": "branch",
                                                "branch": "", "tt_sku": "S1",
                                                "source_ref": "ST-1", "qty": 8,
                                                "as_of": AS_OF}]}),
            "--so-json", self._write(root, "so.json",
                                     {"schema_version": "local/v1",
                                      "observed_at": AS_OF,
                                      "balances": [{"item_code": "SKU-1",
                                                    "uom": "个",
                                                    "warehouse": "WH-1",
                                                    "purpose": "branch",
                                                    "branch": "", "tt_sku": "S1",
                                                    "source_ref": "SO-1",
                                                    "so_open_qty": 6}]}),
            "--as-of", AS_OF, "--out", out]

    def test_pipeline_writes_position_full_and_timeline(self):
        with tempfile.TemporaryDirectory() as td:
            root = Path(td) / "in"
            root.mkdir()
            out = Path(td) / "out"
            rc = main(self._args(root, str(out)))
            self.assertEqual(rc, 0)
            latest = json.loads((out / "latest.json").read_text(encoding="utf-8"))
            manifest = json.loads(Path(latest["manifest"]).read_text(encoding="utf-8"))
            self.assertFalse(manifest["netting_ready"])
            self.assertFalse(manifest["auto_order"])
            facts = json.loads((Path(latest["run_dir"]) / "full_supply_facts.json")
                               .read_text(encoding="utf-8"))
            row = next(r for r in facts if r["item_code"] == "SKU-1"
                       and r["tt_sku"] == "S1")
            self.assertEqual(row["po_completed_assumed_qty"], "5")
            self.assertEqual(row["inventory_qty"], "8")
            self.assertEqual(row["so_open_qty"], "6")
            timeline = json.loads((Path(latest["run_dir"]) / "timeline.json")
                                  .read_text(encoding="utf-8"))
            self.assertFalse(timeline[0]["forecast_connected"])
            for name, meta in manifest["datasets"].items():
                digest = hashlib.sha256(
                    (Path(latest["run_dir"]) / meta["file"]).read_bytes()).hexdigest()
                self.assertEqual(digest, meta["sha256"], name)

    def test_failure_keeps_previous_latest(self):
        with tempfile.TemporaryDirectory() as td:
            root = Path(td) / "in"
            root.mkdir()
            out = Path(td) / "out"
            self.assertEqual(main(self._args(root, str(out))), 0)
            before = (out / "latest.json").read_text(encoding="utf-8")
            rc = main(self._args(root, str(out), audit={"bad": True}))
            self.assertEqual(rc, 1)
            self.assertEqual((out / "latest.json").read_text(encoding="utf-8"),
                             before)
            attempt = json.loads((out / "last_attempt.json")
                                 .read_text(encoding="utf-8"))
            self.assertEqual(attempt["status"], "failed")

    def test_missing_lines_do_not_fabricate_completion(self):
        with tempfile.TemporaryDirectory() as td:
            root = Path(td) / "in"
            root.mkdir()
            out = Path(td) / "out"
            rc = main(self._args(root, str(out), audit=_audit(lines=False)))
            self.assertEqual(rc, 0)
            latest = json.loads((out / "latest.json").read_text(encoding="utf-8"))
            facts = json.loads((Path(latest["run_dir"]) / "full_supply_facts.json")
                               .read_text(encoding="utf-8"))
            row = next(r for r in facts if r["item_code"] == "SKU-1"
                       and r["tt_sku"] == "S1")
            self.assertEqual(row["po_completed_assumed_qty"], "0")

    def test_success_after_failure_clears_stale_failure_marker(self):
        with tempfile.TemporaryDirectory() as td:
            root = Path(td) / "in"
            root.mkdir()
            out = Path(td) / "out"
            with patch("builtins.print"):
                self.assertEqual(main(self._args(root, str(out), audit={"bad": True})), 1)
                self.assertEqual(main(self._args(root, str(out))), 0)
            attempt = json.loads((out / "last_attempt.json").read_text(encoding="utf-8"))
            self.assertEqual(attempt["status"], "succeeded")

    def test_missing_audit_status_and_mapping_still_outputs_delivery(self):
        with tempfile.TemporaryDirectory() as td:
            root = Path(td) / "in"
            root.mkdir()
            out = Path(td) / "out"
            args = [
                "--delivery-json", self._write(root, "delivery.json", _delivery()),
                "--as-of", AS_OF, "--out", str(out)]
            with patch("builtins.print"):
                self.assertEqual(main(args), 0)
            latest = json.loads((out / "latest.json").read_text(encoding="utf-8"))
            manifest = json.loads(Path(latest["manifest"]).read_text(encoding="utf-8"))
            self.assertIn("audit", manifest["input_summary"]["not_provided"])
            self.assertIn("po_status", manifest["input_summary"]["not_provided"])
            self.assertIn("mapping", manifest["input_summary"]["not_provided"])
            self.assertTrue(manifest["output_summary"]["partial"])
            facts = json.loads((Path(latest["run_dir"]) / "full_supply_facts.json")
                               .read_text(encoding="utf-8"))
            row = next(r for r in facts if r["item_code"] == "SKU-1")
            self.assertEqual(row["dn_net_qty"], "5")
            self.assertEqual(row["unresolved_qty"], "5")
            self.assertIn("mapping_unknown", row["unknown_reasons"])
            self.assertIn("dn_po_unresolved", row["unknown_reasons"])

    def test_mixed_audit_versions_do_not_publish(self):
        with tempfile.TemporaryDirectory() as td:
            root = Path(td) / "in"
            root.mkdir()
            out = Path(td) / "out"
            first = _audit()
            first["schema_version"] = "supply-facts/v1"
            second = _audit()
            second["schema_version"] = "supply-facts/v2"
            args = [
                "--delivery-json", self._write(root, "delivery.json", _delivery()),
                "--mapping-json", self._write(root, "mapping.json", _mappings()),
                "--audit-json", self._write(root, "audit-a.json", first),
                "--audit-json", self._write(root, "audit-b.json", second),
                "--status-json", self._write(root, "status.json", _status("3")),
                "--as-of", AS_OF, "--out", str(out)]
            with patch("builtins.print"):
                self.assertEqual(main(args), 1)
            self.assertFalse((out / "latest.json").exists())
            attempt = json.loads((out / "last_attempt.json").read_text(encoding="utf-8"))
            self.assertEqual(attempt["status"], "failed")
            self.assertIn("mixed_input_versions", attempt["error"])

    def test_truncated_delivery_does_not_publish(self):
        with tempfile.TemporaryDirectory() as td:
            root = Path(td) / "in"
            root.mkdir()
            out = Path(td) / "out"
            delivery = _delivery()
            delivery["pagination"] = {"exhausted": False, "partial": True,
                                      "total": 1}
            args = [
                "--delivery-json", self._write(root, "delivery.json", delivery),
                "--mapping-json", self._write(root, "mapping.json", _mappings()),
                "--audit-json", self._write(root, "audit.json", _audit()),
                "--status-json", self._write(root, "status.json", _status("3")),
                "--as-of", AS_OF, "--out", str(out)]
            with patch("builtins.print"):
                self.assertEqual(main(args), 1)
            self.assertFalse((out / "latest.json").exists())
            attempt = json.loads((out / "last_attempt.json").read_text(encoding="utf-8"))
            self.assertEqual(attempt["status"], "failed")

    def test_missing_version_page_with_versioned_page_fails(self):
        with tempfile.TemporaryDirectory() as td:
            root = Path(td) / "in"
            root.mkdir()
            out = Path(td) / "out"
            versioned = _audit()
            versioned["schema_version"] = "supply-facts/v1"
            unversioned = _audit()
            args = [
                "--delivery-json", self._write(root, "delivery.json", _delivery()),
                "--mapping-json", self._write(root, "mapping.json", _mappings()),
                "--audit-json", self._write(root, "audit-a.json", versioned),
                "--audit-json", self._write(root, "audit-b.json", unversioned),
                "--status-json", self._write(root, "status.json", _status("3")),
                "--as-of", AS_OF, "--out", str(out)]
            with patch("builtins.print"):
                self.assertEqual(main(args), 1)
            self.assertFalse((out / "latest.json").exists())
            attempt = json.loads((out / "last_attempt.json").read_text(encoding="utf-8"))
            self.assertIn("missing_version", attempt["error"])

    def test_truncated_optional_input_is_rejected(self):
        with tempfile.TemporaryDirectory() as td:
            root = Path(td) / "in"
            root.mkdir()
            out = Path(td) / "out"
            inventory = {"schema_version": "local/v1", "observed_at": AS_OF,
                         "truncated": True,
                         "inventory": [{"item_code": "SKU-1", "uom": "个",
                                        "warehouse": "WH-1",
                                        "purpose": "branch", "tt_sku": "S1",
                                        "source_ref": "ST-1", "qty": 8,
                                        "as_of": AS_OF}]}
            args = [
                "--delivery-json", self._write(root, "delivery.json", _delivery()),
                "--mapping-json", self._write(root, "mapping.json", _mappings()),
                "--audit-json", self._write(root, "audit.json", _audit()),
                "--status-json", self._write(root, "status.json", _status("3")),
                "--inventory-json", self._write(root, "inventory.json", inventory),
                "--as-of", AS_OF, "--out", str(out)]
            with patch("builtins.print"):
                self.assertEqual(main(args), 1)
            attempt = json.loads((out / "last_attempt.json").read_text(encoding="utf-8"))
            self.assertIn("input_truncated:inventory", attempt["error"])

    def test_business_partial_is_not_pagination_truncation(self):
        with tempfile.TemporaryDirectory() as td:
            root = Path(td) / "in"
            root.mkdir()
            out = Path(td) / "out"
            production = {
                "schema_version": "local/v1", "observed_at": AS_OF,
                "partial": True,
                "pagination": {"exhausted": True, "partial": False},
                "production": [{
                    "item_code": "SKU-1", "uom": "个", "warehouse": "WH-1",
                    "purpose": "branch", "branch": "", "tt_sku": "S1",
                    "source_ref": "WO-1", "qty": 4,
                    "evidence_status": "proven", "available_date": AS_OF}]}
            args = self._args(root, str(out))
            self._write(root, "delivery.json",
                        {**_delivery(), "observed_at": AS_OF})
            args += ["--production-json",
                     self._write(root, "production.json", production)]
            with patch("builtins.print"):
                self.assertEqual(main(args), 0)
            latest = json.loads((out / "latest.json").read_text(encoding="utf-8"))
            manifest = json.loads(Path(latest["manifest"]).read_text(encoding="utf-8"))
            self.assertIn("business_partial",
                          manifest["output_summary"]["partial_reason"])
            self.assertEqual(
                manifest["output_summary"]["layer_status"].get("production"),
                "partial")
            facts = json.loads((Path(latest["run_dir"]) / "full_supply_facts.json")
                               .read_text(encoding="utf-8"))
            row = next(item for item in facts if item["tt_sku"] == "S1")
            self.assertIsNone(row["in_production_qty"])
            self.assertEqual(row["dn_net_qty"], "5")
            stages = [fragment for fragment in row["stage_quantities"]
                      if fragment["stage"] == "in_production"]
            self.assertEqual([fragment["qty"] for fragment in stages], ["4"])
            state = read_publication(str(out), as_of=AS_OF,
                                     max_age_seconds=900)
            self.assertIn("manifest_partial", state["warnings"])
            self.assertIn("business_partial", state["partial_reason"])
            allowed = read_publication(str(out), as_of=AS_OF,
                                       max_age_seconds=900, allow_stale=True)
            self.assertTrue(allowed["readable"])
            self.assertIn("business_partial", state["partial_reason"])

    def test_pagination_truncation_still_rejects_and_keeps_latest(self):
        with tempfile.TemporaryDirectory() as td:
            root = Path(td) / "in"
            root.mkdir()
            out = Path(td) / "out"
            with patch("builtins.print"):
                self.assertEqual(main(self._args(root, str(out))), 0)
            before = (out / "latest.json").read_text(encoding="utf-8")
            runs_before = len(list((out / "runs").iterdir()))
            for flag in ({"truncated": True},
                         {"pagination": {"exhausted": False,
                                         "partial": False}}):
                production = {
                    "schema_version": "local/v1", "observed_at": AS_OF,
                    "production": [{
                        "item_code": "SKU-1", "uom": "个",
                        "warehouse": "WH-1", "purpose": "branch",
                        "branch": "", "tt_sku": "S1",
                        "source_ref": "WO-1", "qty": 4,
                        "evidence_status": "proven",
                        "available_date": AS_OF}]}
                production.update(flag)
                args = self._args(root, str(out)) + [
                    "--production-json", self._write(
                        root, "production.json", production)]
                with patch("builtins.print"):
                    self.assertEqual(main(args), 1)
                self.assertEqual((out / "latest.json")
                                 .read_text(encoding="utf-8"), before)
                self.assertEqual(len(list((out / "runs").iterdir())),
                                 runs_before)
                attempt = json.loads((out / "last_attempt.json")
                                     .read_text(encoding="utf-8"))
                self.assertIn("input_truncated:production",
                              attempt["error"])

    def test_incomplete_input_contract_marks_layer_unknown(self):
        with tempfile.TemporaryDirectory() as td:
            root = Path(td) / "in"
            root.mkdir()
            out = Path(td) / "out"
            inventory = {"inventory": [{"item_code": "SKU-1", "uom": "个",
                                        "warehouse": "WH-1",
                                        "purpose": "branch", "tt_sku": "S1",
                                        "source_ref": "ST-1", "qty": 8,
                                        "as_of": AS_OF}]}
            args = [
                "--delivery-json", self._write(root, "delivery.json", _delivery()),
                "--mapping-json", self._write(root, "mapping.json", _mappings()),
                "--audit-json", self._write(root, "audit.json", _audit()),
                "--status-json", self._write(root, "status.json", _status("3")),
                "--inventory-json", self._write(root, "inventory.json", inventory),
                "--as-of", AS_OF, "--out", str(out)]
            with patch("builtins.print"):
                self.assertEqual(main(args), 0)
            latest = json.loads((out / "latest.json").read_text(encoding="utf-8"))
            manifest = json.loads(Path(latest["manifest"]).read_text(encoding="utf-8"))
            self.assertIn("inventory", manifest["input_summary"]["contract_incomplete"])
            self.assertTrue(manifest["output_summary"]["partial"])
            facts = json.loads((Path(latest["run_dir"]) / "full_supply_facts.json")
                               .read_text(encoding="utf-8"))
            row = next(r for r in facts if r["item_code"] == "SKU-1")
            self.assertIsNone(row["inventory_qty"])
            self.assertIn("source_contract_incomplete", row["unknown_reasons"])

    def test_partial_audit_pagination_keeps_dn_facts_partial(self):
        with tempfile.TemporaryDirectory() as td:
            root = Path(td) / "in"
            root.mkdir()
            out = Path(td) / "out"
            audit = _audit()
            audit["pagination"] = {"limit": 50, "offset": 0, "returned": 1,
                                   "total": 2, "exhausted": False,
                                   "partial": True}
            args = [
                "--delivery-json", self._write(root, "delivery.json", _delivery()),
                "--mapping-json", self._write(root, "mapping.json", _mappings()),
                "--audit-json", self._write(root, "audit.json", audit),
                "--status-json", self._write(root, "status.json", _status("3")),
                "--as-of", AS_OF, "--out", str(out)]
            with patch("builtins.print"):
                self.assertEqual(main(args), 0)
            latest = json.loads((out / "latest.json").read_text(encoding="utf-8"))
            manifest = json.loads(Path(latest["manifest"]).read_text(encoding="utf-8"))
            audit_entry = next(item for item in manifest["inputs"]
                               if item["role"].startswith("audit"))
            self.assertTrue(audit_entry["truncated"])
            self.assertEqual(audit_entry["completeness"], "partial")
            self.assertIn("pagination_not_exhausted",
                          audit_entry["partial_reason"])
            self.assertTrue(manifest["output_summary"]["partial"])
            facts = json.loads((Path(latest["run_dir"]) / "full_supply_facts.json")
                               .read_text(encoding="utf-8"))
            row = next(r for r in facts if r["tt_sku"] == "S1")
            self.assertEqual(row["dn_net_qty"], "5")
            self.assertEqual(row["source_status"]["dn_po"], "partial")

    def test_empty_collection_with_contract_is_legal(self):
        with tempfile.TemporaryDirectory() as td:
            root = Path(td) / "in"
            root.mkdir()
            out = Path(td) / "out"
            inventory = {"schema_version": "local/v1", "observed_at": AS_OF,
                         "inventory": []}
            args = [
                "--delivery-json", self._write(root, "delivery.json", _delivery()),
                "--mapping-json", self._write(root, "mapping.json", _mappings()),
                "--audit-json", self._write(root, "audit.json", _audit()),
                "--status-json", self._write(root, "status.json", _status("3")),
                "--inventory-json", self._write(root, "inventory.json", inventory),
                "--as-of", AS_OF, "--out", str(out)]
            with patch("builtins.print"):
                self.assertEqual(main(args), 0)
            latest = json.loads((out / "latest.json").read_text(encoding="utf-8"))
            manifest = json.loads(Path(latest["manifest"]).read_text(encoding="utf-8"))
            self.assertNotIn("inventory",
                             manifest["input_summary"]["contract_incomplete"])

    def test_frozen_replay_with_spaces_and_chinese_paths(self):
        with tempfile.TemporaryDirectory() as td:
            root = Path(td) / "含 空格 目录" / "in"
            root.mkdir(parents=True)
            out = Path(td) / "含 空格 目录" / "out"
            args = self._args(root, str(out))
            with patch("builtins.print"):
                self.assertEqual(main(args), 0)
            latest = json.loads((out / "latest.json").read_text(encoding="utf-8"))
            run_dir = Path(latest["run_dir"])
            manifest = json.loads((run_dir / "manifest.json").read_text(encoding="utf-8"))
            self.assertIn("--replay-run", manifest["rerun"]["command"])
            self.assertEqual(manifest["rerun"]["effective_args"]["as_of"], AS_OF)
            self.assertEqual(
                manifest["rerun"]["effective_args"]["max_age_seconds"], 900)
            self.assertEqual(
                manifest["rerun"]["effective_args"]["max_stock_age_days"], 1)
            frozen = [item for item in manifest["inputs"]
                      if item.get("frozen_path")]
            self.assertTrue(frozen)
            for item in frozen:
                path = run_dir / item["frozen_path"]
                self.assertTrue(path.is_file())
                self.assertEqual(
                    hashlib.sha256(path.read_bytes()).hexdigest(),
                    item["frozen_sha256"])
            original_sha = hashlib.sha256(
                (run_dir / "full_supply_facts.json").read_bytes()).hexdigest()
            # Original inputs disappear; the frozen copies must still replay.
            for item in manifest["inputs"]:
                if item.get("path"):
                    Path(item["path"]).unlink(missing_ok=True)
            replay_out = Path(td) / "含 空格 目录" / "replay"
            with patch("builtins.print"):
                self.assertEqual(main(["--replay-run", str(run_dir),
                                       "--out", str(replay_out)]), 0)
            replay_latest = json.loads((replay_out / "latest.json")
                                       .read_text(encoding="utf-8"))
            replay_sha = hashlib.sha256(
                (Path(replay_latest["run_dir"]) / "full_supply_facts.json")
                .read_bytes()).hexdigest()
            self.assertEqual(original_sha, replay_sha)

    def test_replay_rejects_tampered_frozen_input(self):
        with tempfile.TemporaryDirectory() as td:
            root = Path(td) / "in"
            root.mkdir()
            out = Path(td) / "out"
            with patch("builtins.print"):
                self.assertEqual(main(self._args(root, str(out))), 0)
            latest = json.loads((out / "latest.json").read_text(encoding="utf-8"))
            run_dir = Path(latest["run_dir"])
            manifest = json.loads((run_dir / "manifest.json").read_text(encoding="utf-8"))
            target = next(item for item in manifest["inputs"]
                          if item.get("frozen_path"))
            (run_dir / target["frozen_path"]).write_bytes(b"tampered")
            with patch("builtins.print"):
                self.assertEqual(main(["--replay-run", str(run_dir),
                                       "--out", str(Path(td) / "replay")]), 1)

    def test_inspect_reads_healthy_publication(self):
        with tempfile.TemporaryDirectory() as td:
            root = Path(td) / "in"
            root.mkdir()
            out = Path(td) / "out"
            with patch("builtins.print"):
                self.assertEqual(main(self._args(root, str(out))), 0)
            with patch("builtins.print"):
                self.assertEqual(main(["--inspect", "--out", str(out),
                                       "--as-of", AS_OF,
                                       "--max-age-seconds", "900"]), 0)

    @unittest.skipUnless(importlib.util.find_spec("openpyxl"), "requires openpyxl")
    def test_abc_workbooks_integrate_into_publication(self):
        from openpyxl import Workbook
        with tempfile.TemporaryDirectory() as td:
            root = Path(td) / "in"
            root.mkdir()
            out = Path(td) / "out"
            a = root / "A.xlsx"
            book = Workbook()
            sheet = book.active
            sheet.title = "活跃宇宙"
            sheet.append(["EN物料", "角色", "活跃分类"])
            sheet.append(["SKU-1", "成品", "EN+通途"])
            sheet.append(["A-ONLY", "成品", "EN+通途"])
            book.save(a)
            b = root / "B.xlsx"
            book = Workbook()
            sheet = book.active
            sheet.title = "主表"
            sheet.append(["产品键", "地区", "美国责任方", "UOM_单位",
                          "是否需求行", "可进净额", "限制原因",
                          "目的仓", "branch", "purpose", "tt_sku"])
            sheet.append(["SKU-1", "US", "美东USNJ", "个", "Y", "否", "",
                          "WH-1", "CENTRADE", "branch", "S1"])
            book.save(b)
            c = root / "C.xlsx"
            book = Workbook()
            sheet = book.active
            sheet.title = "19_Top50候选导出"
            sheet.append(["product_id", "pool", "canonical_uom", "可发供给",
                          "join_class", "source_ref", "as_of",
                          "demand_eligibility"])
            sheet.append(["SKU-1", "美东USNJ", "个", 0, "join_full", "ST:1",
                          "2026-10-28", "independent"])
            second = book.create_sheet("19b_Top50观察表")
            second.append(["product_id", "pool", "canonical_uom", "可发供给",
                           "join_class", "source_ref", "as_of",
                           "demand_eligibility"])
            book.save(c)
            args = self._args(root, str(out))
            index = args.index("--inventory-json")
            del args[index:index + 2]
            index = args.index("--so-json")
            del args[index:index + 2]
            args += ["--a-workbook", str(a), "--b-workbook", str(b),
                     "--c-workbook", str(c), "--a-version", "A1",
                     "--b-version", "v6r10", "--c-version", "v14",
                     "--c-declared-b-version", "v6r10"]
            with patch("builtins.print"):
                self.assertEqual(main(args), 0)
            latest = json.loads((out / "latest.json").read_text(encoding="utf-8"))
            manifest = json.loads(Path(latest["manifest"]).read_text(encoding="utf-8"))
            roles = {item["role"] for item in manifest["inputs"]}
            self.assertTrue({"A", "B", "C"}.issubset(roles))
            facts = json.loads((Path(latest["run_dir"]) / "full_supply_facts.json")
                               .read_text(encoding="utf-8"))
            skilled = next(r for r in facts if r["item_code"] == "SKU-1"
                           and r["tt_sku"] == "S1")
            self.assertEqual(skilled["inventory_qty"], "0")
            self.assertEqual(skilled["inventory_freshness"], "stale")
            self.assertIsNone(skilled["inventory_current_available_qty"])
            self.assertTrue(any(r["item_code"] == "A-ONLY" for r in facts))
            abc_versions = manifest["datasets"][
                "full_supply_facts.parquet"]["source_versions"]["ABC"]
            self.assertEqual(abc_versions["B"]["version"], "v6r10")
            self.assertEqual(abc_versions["C"]["version"], "v14")
            self.assertEqual(abc_versions["version_relation"], "match")
            self.assertIn(abc_versions["c_dependency_source"],
                          ("cli", "workbook"))
            # Windows GBK consoles must not fail on the success line.
            out2 = Path(td) / "out2"
            command = list(args)
            command[command.index("--out") + 1] = str(out2)
            env = dict(os.environ, PYTHONIOENCODING="gbk")
            repo_root = Path(__file__).resolve().parents[2]
            completed = subprocess.run(
                [sys.executable, "-m",
                 "supply_chain_visibility.supply_pipeline"] + command,
                cwd=str(repo_root), env=env, capture_output=True, text=True)
            self.assertEqual(completed.returncode, 0,
                             completed.stderr[-500:])
            self.assertIn("OK pipeline", completed.stdout)


if __name__ == "__main__":
    unittest.main()
