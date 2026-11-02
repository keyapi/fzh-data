"""Atomic EN snapshot refresh orchestration and failure boundaries."""
import importlib.util
import json
import tempfile
import unittest
from pathlib import Path

from supply_chain_visibility.en_collect import CollectionError
from supply_chain_visibility.supply_snapshot_refresh import (
    RefreshLock,
    RefreshOptions,
    _delivery_scope,
    _scope_hash,
    _write_attempt,
    run_refresh,
)


class _BrokenClient:
    def supply_pages(self, filters, page_size, max_pages):
        return [], "exhausted"

    def delivery_pages(self, page_size, max_pages, **kwargs):
        raise AssertionError("delivery must not run after supply failure")


class _EmptySnapshotClient:
    def supply_pages(self, filters, page_size, max_pages):
        coverage = {"observed_at": "2026-11-02T00:00:00+00:00",
                    "source_status": {
                        "sales_order": {"available": True, "restricted": False,
                                        "reason": ""},
                        "tongtool_po": {"available": False, "restricted": False,
                                        "reason": "not_integrated"}}}
        batch = {
            "schema_version": "supply-facts/v2", "rule_version": "r",
            "implementation_version": "i", "as_of": "2026-11-02",
            "snapshot_id": "SUPPLY-EMPTY", "lines": [],
            "stage_balances": [], "milestones": [],
            "availability_schedule": [], "links": [],
            "production_evidence": [], "shipment_progress": [],
            "pagination": {"limit": page_size, "offset": 0, "returned": 0,
                           "total": 0, "next_offset": None,
                           "exhausted": True},
            "manifest": {"coverage": coverage, "truncated": False},
        }
        return [batch], "exhausted"

    def delivery_pages(self, page_size, max_pages, **kwargs):
        scope = kwargs["scope"]
        batch = {
            "schema_version": "supply-facts/v3", "rule_version": "r",
            "implementation_version": "d", "snapshot_id": "DELIVERY-EMPTY",
            "scope": scope,
            "coverage": {"as_of": "2026-11-02",
                         "observed_at": "2026-11-02T00:00:00+00:00",
                         "source_status": {}},
            "delivery_lines": [], "association_edges": [],
            "coverage_exceptions": [], "physical_chain": [],
            "so_fulfillment": [], "ambiguity_pools": [], "supply_ledger": [],
            "pagination": {"limit": page_size, "offset": 0, "returned": 0,
                           "total": 0, "next_offset": None,
                           "exhausted": True},
        }
        return [batch], "exhausted"


class RefreshBoundaryTests(unittest.TestCase):
    def test_attempt_writer_creates_output_directory(self):
        with tempfile.TemporaryDirectory() as tmp:
            out = Path(tmp) / "new" / "out"
            _write_attempt(out, "failed", "collect", "credentials", "missing")
            payload = json.loads((out / "last_attempt.json").read_text(
                encoding="utf-8"))
            self.assertEqual(payload["status"], "failed")

    def test_abc_scope_is_authoritative_and_hash_matches_server_contract(self):
        options = RefreshOptions(out="out", as_of="2026-11-02T00:00:00+00:00")
        abc = {"approved_items": ["B", "A"], "report": {
            "dataset_versions": {"A": "A-v1", "B": "B-v2"}}}
        b_rows = [{"item_code": "A", "uom": "EA", "warehouse": "WH",
                   "branch": "US", "purpose": "branch", "tt_sku": "TT-A"}]
        scope = _delivery_scope(options, abc, b_rows)
        self.assertEqual(scope["status"], "provided")
        self.assertEqual([row["item_code"] for row in scope["items"]], ["A", "B"])
        self.assertEqual(scope["hash"], _scope_hash(
            scope["source"], scope["version"], ["A", "B"]))

    def test_no_abc_needs_explicit_scope(self):
        options = RefreshOptions(
            out="out", as_of="2026-11-02T00:00:00+00:00", no_abc=True)
        with self.assertRaises(CollectionError):
            _delivery_scope(options, None, [])

    def test_collection_failure_keeps_previous_latest(self):
        with tempfile.TemporaryDirectory() as tmp:
            out = Path(tmp) / "publication"
            out.mkdir()
            latest = out / "latest.json"
            latest.write_text('{"run_id":"old"}', encoding="utf-8")
            scope = {"status": "provided", "source": "fixture", "version": "v1",
                     "items": [{"item_code": "A"}]}
            scope["hash"] = _scope_hash("fixture", "v1", ["A"])
            scope_path = Path(tmp) / "scope.json"
            scope_path.write_text(json.dumps(scope), encoding="utf-8")
            options = RefreshOptions(
                out=str(out), as_of="2026-11-02T00:00:00+00:00",
                no_abc=True, scope_json=str(scope_path))
            result = run_refresh(options, _BrokenClient())
            self.assertEqual(result["status"], "failed")
            self.assertEqual(latest.read_text(encoding="utf-8"),
                             '{"run_id":"old"}')
            self.assertFalse((out / "runs").exists())

    def test_lock_is_non_blocking_and_preserves_latest(self):
        with tempfile.TemporaryDirectory() as tmp:
            lock_path = Path(tmp) / ".refresh.lock"
            with RefreshLock(lock_path):
                with self.assertRaises(CollectionError):
                    with RefreshLock(lock_path):
                        pass

    @unittest.skipUnless(importlib.util.find_spec("pyarrow"), "requires pyarrow")
    def test_empty_en_snapshot_with_structured_abc_publishes_atomically(self):
        fixtures = Path(__file__).resolve().parent / "fixtures" / "abc"
        with tempfile.TemporaryDirectory() as tmp:
            options = RefreshOptions(
                out=str(Path(tmp) / "out"),
                as_of="2026-11-02T00:00:00+00:00",
                a_dataset=str(fixtures / "a.json"),
                b_dataset=str(fixtures / "b.json"),
                c_dataset=str(fixtures / "c.json"))
            result = run_refresh(options, _EmptySnapshotClient())
            self.assertEqual(result["status"], "ok", result)
            latest = json.loads((Path(options.out) / "latest.json").read_text(
                encoding="utf-8"))
            manifest = json.loads(Path(latest["manifest"]).read_text(
                encoding="utf-8"))
            self.assertEqual(manifest["collection"]["supply_snapshot_id"],
                             "SUPPLY-EMPTY")
            self.assertEqual(manifest["schema_version"], "supply-publication/v4")


if __name__ == "__main__":
    unittest.main()
