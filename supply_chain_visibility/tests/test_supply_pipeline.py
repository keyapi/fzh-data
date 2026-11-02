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
                           "status": "confirmed", "purchase_order_code": "PO-1",
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
                                            {"inventory": [{
                                                "item_code": "SKU-1", "uom": "个",
                                                "warehouse": "WH-1",
                                                "purpose": "branch",
                                                "branch": "CENTRADE", "qty": 8,
                                                "as_of": AS_OF}]}),
            "--so-json", self._write(root, "so.json",
                                     {"balances": [{"item_code": "SKU-1",
                                                    "uom": "个",
                                                    "warehouse": "WH-1",
                                                    "purpose": "branch",
                                                    "branch": "CENTRADE",
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
            row = next(r for r in facts if r["item_code"] == "SKU-1")
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
            row = next(r for r in facts if r["item_code"] == "SKU-1")
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
            skilled = next(r for r in facts if r["item_code"] == "SKU-1")
            self.assertEqual(skilled["inventory_qty"], "0")
            self.assertEqual(skilled["inventory_freshness"], "stale")
            self.assertIsNone(skilled["inventory_current_available_qty"])
            self.assertTrue(any(r["item_code"] == "A-ONLY" for r in facts))
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
