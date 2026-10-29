"""Conservative merge tests for the supply facts batch exporter."""
import importlib.util
import json
import tempfile
from pathlib import Path
from unittest import mock
import unittest


def _load_exporter():
    path = Path(__file__).resolve().parents[2] / "EN_API" / "supply_facts_export.py"
    spec = importlib.util.spec_from_file_location("supply_facts_export_test", path)
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


def _empty_target():
    return {"lines": [], "stage_balances": [], "milestones": [],
            "availability_schedule": [], "links": [], "partial": False,
            "counts": {}, "coverage": {}, "sources": {}, "source_timestamps": {},
            "restricted": {}, "external_sources": {},
            "notes": [], "schema_version": "", "rule_version": "",
            "implementation_version": "", "as_of": ""}


def _batch(**coverage):
    return {"lines": [], "stage_balances": [], "milestones": [],
            "availability_schedule": [], "links": [],
            "manifest": {"schema_version": "supply-facts/v1",
                         "implementation_version": "impl-v1",
                         "partial": True, "coverage": coverage,
                         "notes": ["note"], "counts": {"input": 1},
                         "rule_version": "v1", "as_of": "2026-10-27"}}


class MergeSemanticsTest(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.exporter = _load_exporter()

    def test_restricted_is_or_and_sources_is_and(self):
        target = _empty_target()
        self.exporter._merge(target, _batch(
            sources={"delivery_note": True, "work_order": True},
            restricted={"delivery_note": True, "work_order": False}))
        self.exporter._merge(target, _batch(
            sources={"delivery_note": False, "work_order": True},
            restricted={"delivery_note": False, "work_order": False}))
        self.assertTrue(target["restricted"]["delivery_note"])
        self.assertFalse(target["restricted"]["work_order"])
        self.assertFalse(target["sources"]["delivery_note"])
        self.assertTrue(target["sources"]["work_order"])
        self.assertTrue(target["partial"])

    def test_external_sources_and_timestamps_are_conservative(self):
        target = _empty_target()
        self.exporter._merge(target, _batch(
            external_sources={"receipt": "not_integrated"},
            source_timestamps={"delivery_note": "2026-10-27T10:00:00"}))
        self.exporter._merge(target, _batch(
            external_sources={"receipt": "integrated"},
            source_timestamps={"delivery_note": "2026-10-27T09:00:00"}))
        self.assertEqual(target["external_sources"]["receipt"], "not_integrated")
        self.assertEqual(target["source_timestamps"]["delivery_note"],
                         "2026-10-27T09:00:00")

    def test_empty_reason_is_preserved(self):
        target = _empty_target()
        self.exporter._merge(target, _batch(empty_reason="no_matching_lines"))
        self.assertEqual(target["coverage"]["empty_reason"], "no_matching_lines")

    def test_implementation_version_is_carried(self):
        target = _empty_target()
        batch = _batch()
        batch["manifest"]["implementation_version"] = "key_test.supply_facts@2026-10-27.3"
        self.exporter._merge(target, batch)
        self.assertEqual(target["implementation_version"],
                         "key_test.supply_facts@2026-10-27.3")

    def test_mixed_implementation_version_is_rejected(self):
        target = _empty_target()
        self.exporter._merge(target, _batch())
        batch = _batch()
        batch["manifest"]["implementation_version"] = "impl-v2"
        with self.assertRaises(self.exporter.BatchVersionError):
            self.exporter._merge(target, batch)
        self.assertEqual(target["implementation_version"], "impl-v1")
        self.assertEqual(target["lines"], [])

    def test_old_and_new_implementation_versions_are_rejected(self):
        target = _empty_target()
        target["implementation_version"] = "key_test.supply_facts@2026-10-27.7"
        batch = _batch()
        batch["manifest"]["implementation_version"] = "key_test.supply_facts@2026-10-29.1"
        with self.assertRaises(self.exporter.BatchVersionError):
            self.exporter._merge(target, batch)

    def test_mixed_rule_schema_or_as_of_is_rejected(self):
        target = _empty_target()
        self.exporter._merge(target, _batch())
        for key, value in (("rule_version", "v2"), ("schema_version", "supply-facts/v2"),
                           ("as_of", "2026-10-28T00:00:00")):
            bad = _batch()
            bad["manifest"][key] = value
            with self.assertRaises(self.exporter.BatchVersionError):
                self.exporter._merge(target, bad)

    def test_batch_missing_version_is_rejected(self):
        target = _empty_target()
        for key in ("schema_version", "rule_version", "implementation_version", "as_of"):
            bad = _batch()
            del bad["manifest"][key]
            with self.assertRaises(self.exporter.BatchVersionError):
                self.exporter._merge(target, bad)


class ExportPaginationTest(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.exporter = _load_exporter()

    def _batch_page(self, total, offset, limit):
        end = min(offset + limit, total)
        lines = [{"so": "SO-1", "so_line": "SOI-%05d" % i} for i in range(offset, end)]
        return {
            "lines": lines, "stage_balances": [], "milestones": [],
            "availability_schedule": [], "links": [],
            "manifest": {
                "schema_version": "supply-facts/v1",
                "rule_version": "v1",
                "implementation_version": "impl-v1",
                "as_of": "2026-10-29",
                "partial": True,
                "counts": {"input": len(lines)},
                "coverage": {},
                "notes": [],
            },
            "pagination": {
                "limit": limit, "offset": offset, "returned": len(lines), "total": total,
                "next_offset": None if end >= total else end,
                "next_cursor": lines[-1]["so_line"] if lines else None,
                "exhausted": end >= total,
                "partial": end < total,
                "termination_reason": "exhausted" if end >= total else "page_limit",
            },
        }

    def _run_export(self, argv, total=501):
        calls = []

        def fake_call(base, key, secret, filters):
            calls.append(dict(filters))
            return self._batch_page(total, int(filters.get("offset") or 0),
                                    int(filters["limit"]))

        with mock.patch.object(self.exporter.iss, "load_credentials",
                               return_value=("k", "s")), \
             mock.patch.object(self.exporter.iss, "resolve_env_files",
                               return_value=None), \
             mock.patch.object(self.exporter.iss, "ENV_URLS",
                               {"test": "http://test"}), \
             mock.patch.object(self.exporter, "_call", side_effect=fake_call), \
             mock.patch.object(self.exporter, "_resolve_sos",
                               return_value=["SO-1"]):
            with tempfile.TemporaryDirectory() as td:
                rc = self.exporter.main(argv + ["--out", td])
                self.assertEqual(rc, 0)
                runs = list((Path(td) / "runs").glob("run-*"))
                self.assertEqual(len(runs), 1)
                lines = json.loads((runs[0] / "lines.json").read_text(encoding="utf-8"))
                manifest = json.loads((runs[0] / "manifest.json").read_text(encoding="utf-8"))
        return calls, lines, manifest

    def test_single_so_501_rows_paginates_to_exhaustion(self):
        calls, lines, manifest = self._run_export(
            ["--so", "SO-1", "--test", "--page-size", "500", "--no-excel"])
        self.assertEqual(len(lines), 501)
        self.assertEqual([c["offset"] for c in calls], [0, 500])
        self.assertFalse(manifest["truncated"])
        self.assertEqual(manifest["termination_reason"], "exhausted")
        self.assertEqual(manifest["coverage"]["sales_orders"], 1)
        self.assertEqual(manifest["coverage"]["so_lines"], 501)
        self.assertEqual(manifest["coverage"]["so_lines_total"], 501)

    def test_customer_code_501_rows_paginates_to_exhaustion(self):
        calls, lines, manifest = self._run_export(
            ["--codes", "TT0031038K0062927", "--test", "--page-size", "500", "--no-excel"])
        self.assertEqual(len(lines), 501)
        self.assertEqual([c["offset"] for c in calls], [0, 500])
        self.assertFalse(manifest["truncated"])
        self.assertEqual(manifest["termination_reason"], "exhausted")
        self.assertEqual(manifest["coverage"]["sales_orders"], 1)
        self.assertEqual(manifest["coverage"]["so_lines"], 501)
        self.assertEqual(manifest["coverage"]["so_lines_total"], 501)

    def test_paginate_rejects_stalled_offset(self):
        def fake_call(base, key, secret, filters):
            batch = self._batch_page(10, 0, 500)
            batch["pagination"].update({"exhausted": False, "next_offset": 0})
            return batch

        with mock.patch.object(self.exporter, "_call", side_effect=fake_call):
            with self.assertRaises(self.exporter.iss.QueryError):
                self.exporter._paginate("base", "k", "s", {}, 500, max_pages=2)

    def test_paginate_rejects_duplicate_unique_key(self):
        first = self._batch_page(501, 0, 500)
        second = self._batch_page(501, 500, 500)
        second["lines"][0]["so_line"] = first["lines"][0]["so_line"]

        with mock.patch.object(self.exporter, "_call", side_effect=[first, second]):
            with self.assertRaises(self.exporter.iss.QueryError):
                self.exporter._paginate("base", "k", "s", {}, 500, max_pages=2)

    def test_paginate_reports_page_limit(self):
        def fake_call(base, key, secret, filters):
            offset = int(filters.get("offset") or 0)
            batch = self._batch_page(10**9, offset, 500)
            batch["pagination"].update({"exhausted": False, "next_offset": offset + 500})
            return batch

        with mock.patch.object(self.exporter, "_call", side_effect=fake_call):
            batches, term = self.exporter._paginate("base", "k", "s", {}, 500, max_pages=2)
        self.assertEqual(len(batches), 2)
        self.assertEqual(term, "page_limit")


    def test_paginate_rejects_gap_in_next_offset(self):
        first = self._batch_page(501, 0, 500)
        first["pagination"]["next_offset"] = 501  # skips line #500
        with mock.patch.object(self.exporter, "_call", side_effect=[first]):
            with self.assertRaises(self.exporter.iss.QueryError):
                self.exporter._paginate("base", "k", "s", {}, 500)

    def test_paginate_rejects_exhausted_with_missing_rows(self):
        first = self._batch_page(501, 0, 500)
        final = self._batch_page(501, 500, 500)
        final["lines"] = []
        final["pagination"].update({"returned": 0, "next_offset": None, "exhausted": True})
        with mock.patch.object(self.exporter, "_call", side_effect=[first, final]):
            with self.assertRaises(self.exporter.iss.QueryError):
                self.exporter._paginate("base", "k", "s", {}, 500)

    def test_paginate_rejects_total_change(self):
        first = self._batch_page(501, 0, 500)
        second = self._batch_page(501, 500, 500)
        second["pagination"]["total"] = 502
        with mock.patch.object(self.exporter, "_call", side_effect=[first, second]):
            with self.assertRaises(self.exporter.iss.QueryError):
                self.exporter._paginate("base", "k", "s", {}, 500)

    def test_paginate_rejects_returned_mismatch(self):
        first = self._batch_page(501, 0, 500)
        first["pagination"]["returned"] = 499
        with mock.patch.object(self.exporter, "_call", side_effect=[first]):
            with self.assertRaises(self.exporter.iss.QueryError):
                self.exporter._paginate("base", "k", "s", {}, 500)

    def test_merge_coverage_dedupes_entities_by_identity(self):
        target = _empty_target()

        def batch(line_key):
            item = _batch()
            item["lines"] = [{"so": "SO-1", "so_line": line_key}]
            item["links"] = [{
                "source_doctype": "Delivery Note", "source_name": "DN-1",
                "target_doctype": "Shipment", "target_name": "SHIP-1",
            }]
            item["pagination"] = {"total": 2}
            item["manifest"]["coverage"] = {
                "sales_orders": 1, "so_lines": 1, "so_lines_total": 2,
                "delivery_notes": 1, "shipments": 1,
            }
            return item

        self.exporter._merge(target, batch("L1"), scope_key="SO-1")
        self.exporter._merge(target, batch("L2"), scope_key="SO-1")
        self.exporter._finalize_coverage(target)
        self.assertEqual(target["coverage"]["sales_orders"], 1)
        self.assertEqual(target["coverage"]["so_lines"], 2)
        self.assertEqual(target["coverage"]["so_lines_total"], 2)
        self.assertEqual(target["coverage"]["delivery_notes"], 1)
        self.assertEqual(target["coverage"]["shipments"], 1)
        self.assertNotIn("_coverage_state", target)


    def test_failed_pagination_preserves_latest_pointer(self):
        with tempfile.TemporaryDirectory() as td:
            out = Path(td)
            out.mkdir(parents=True, exist_ok=True)
            old_pointer = {"run_id": "previous-success"}
            (out / "latest.json").write_text(json.dumps(old_pointer), encoding="utf-8")
            bad = self._batch_page(501, 0, 500)
            bad["pagination"]["next_offset"] = 501
            with mock.patch.object(self.exporter.iss, "load_credentials",
                                   return_value=("k", "s")), \
                 mock.patch.object(self.exporter.iss, "resolve_env_files",
                                   return_value=None), \
                 mock.patch.object(self.exporter.iss, "ENV_URLS",
                                   {"test": "http://test"}), \
                 mock.patch.object(self.exporter, "_call", return_value=bad):
                rc = self.exporter.main(
                    ["--so", "SO-1", "--test", "--page-size", "500",
                     "--no-excel", "--out", td])
            self.assertEqual(rc, 1)
            self.assertEqual(json.loads((out / "latest.json").read_text(encoding="utf-8")),
                             old_pointer)
            self.assertFalse((out / "runs").exists())


if __name__ == "__main__":
    unittest.main()
