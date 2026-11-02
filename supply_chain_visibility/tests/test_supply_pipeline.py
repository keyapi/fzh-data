# -*- coding: utf-8 -*-
"""Executable offline pipeline: saved responses -> position/full/timeline."""

import hashlib
import json
import tempfile
import unittest
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
            self.assertEqual(row["po_completed_assumed_qty"], 5.0)
            self.assertEqual(row["inventory_qty"], "8")
            self.assertEqual(row["so_open_qty"], "6")
            timeline = json.loads((Path(latest["run_dir"]) / "timeline.json")
                                  .read_text(encoding="utf-8"))
            self.assertFalse(timeline[0]["forecast_connected"])
            for name, meta in manifest["datasets"].items():
                digest = hashlib.sha256(
                    (Path(latest["run_dir"]) / meta["path"]).read_bytes()).hexdigest()
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
            self.assertEqual(row["po_completed_assumed_qty"], 0.0)


if __name__ == "__main__":
    unittest.main()
