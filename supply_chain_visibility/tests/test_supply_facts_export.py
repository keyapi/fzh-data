"""Conservative merge tests for the supply facts batch exporter."""
import importlib.util
import json
import hashlib
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
            "availability_schedule": [], "links": [], "production_evidence": [],
            "partial": False,
            "counts": {}, "coverage": {}, "sources": {}, "source_timestamps": {},
            "restricted": {}, "external_sources": {},
            "notes": [], "schema_version": "", "rule_version": "",
            "implementation_version": "", "as_of": ""}


def _batch(**coverage):
    return {"lines": [], "stage_balances": [], "milestones": [],
            "availability_schedule": [], "links": [], "production_evidence": [],
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
                "target_is_record": True,
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


    def test_merge_coverage_waybill_only_is_not_a_shipment(self):
        target = _empty_target()
        batch = _batch()
        batch["lines"] = [{"so": "SO-1", "so_line": "L1"}]
        batch["links"] = [{
            "source_doctype": "Delivery Note", "source_name": "DN-1",
            "target_doctype": "Shipment", "target_name": "WAYBILL-1",
            "target_is_record": False,
        }]
        batch["pagination"] = {"total": 1}
        batch["manifest"]["coverage"] = {
            "sales_orders": 1, "so_lines": 1, "so_lines_total": 1,
            "delivery_notes": 1, "shipments": 0,
        }
        self.exporter._merge(target, batch, scope_key="SO-1")
        self.exporter._finalize_coverage(target)
        self.assertEqual(target["coverage"]["shipments"], 0)
        self.assertEqual(target["coverage"]["delivery_notes"], 1)

    def test_merge_coverage_matches_only_real_shipments_and_dedupes(self):
        target = _empty_target()
        batch = _batch()
        batch["lines"] = [{"so": "SO-1", "so_line": "L1"}]

        def link(dn, ship, is_record):
            return {
                "source_doctype": "Delivery Note", "source_name": dn,
                "target_doctype": "Shipment", "target_name": ship,
                "target_is_record": is_record,
            }

        batch["links"] = [
            link("DN-1", "SHIP-1", False),  # waybill placeholder, not a record
            link("DN-1", "SHIP-1", True),   # real record
            link("DN-2", "SHIP-1", True),   # duplicate real record
            link("DN-2", "SHIP-2", True),
        ]
        batch["pagination"] = {"total": 1}
        batch["manifest"]["coverage"] = {
            "sales_orders": 1, "so_lines": 1, "so_lines_total": 1,
            "delivery_notes": 2, "shipments": 0,
        }
        self.exporter._merge(target, batch, scope_key="SO-1")
        self.exporter._finalize_coverage(target)
        self.assertEqual(target["coverage"]["shipments"], 2)
        self.assertEqual(target["coverage"]["delivery_notes"], 2)
        self.assertEqual(target["coverage"]["sales_orders"], 1)
        self.assertEqual(target["coverage"]["so_lines"], 1)
        self.assertEqual(target["coverage"]["so_lines_total"], 1)


class ProductionEvidenceExportTest(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.exporter = _load_exporter()

    def _evidence(self, qty=10):
        return {"qty_proven": qty, "qty_estimated": None, "confidence": "proven",
                "started_at": "2026-10-20 08:00:00",
                "completed_at": "2026-10-20 17:00:00",
                "time_status": "complete", "reasons": [], "conflicts": [],
                "components": {}, "source_records": []}

    def _pe_line(self, so_line):
        stock = self._evidence()
        stock["components"] = {"gross_qty": 10.0, "return_qty": 0.0,
                               "net_qty": 10.0, "unallocated_return_qty": 0.0}
        return {
            "so": "SO-1", "so_line": so_line, "line_item_code": "KS0001",
            "work_orders": [{
                "wo": "WO-1", "production_item": "KS0001", "qty": 10.0,
                "uom": "个", "docstatus": 1, "wo_cancelled": False,
                "first_process_done": self._evidence(),
                "all_process_done": self._evidence(),
                "qc_performed": self._evidence(),
                "qc_passed": {"class": "qc_passed", "status": "Accepted",
                              "confidence": "unknown", "qty_proven": None,
                              "qty_estimated": None, "started_at": None,
                              "completed_at": None, "time_status": "not_applicable",
                              "reasons": [], "conflicts": [],
                              "components": {}, "source_records": []},
                "stock_in_posted": stock,
                "conflicts": [], "reasons": [],
            }],
        }

    def _page(self, total, offset, limit):
        end = min(offset + limit, total)
        lines = [{"so": "SO-1", "so_line": "SOI-%05d" % i} for i in range(offset, end)]
        return {
            "lines": lines, "stage_balances": [], "milestones": [],
            "availability_schedule": [], "links": [],
            "production_evidence": [self._pe_line("SOI-%05d" % i)
                                    for i in range(offset, end)],
            "manifest": {
                "schema_version": "supply-facts/v1", "rule_version": "v1",
                "implementation_version": "impl-v1", "as_of": "2026-10-29",
                "partial": True, "counts": {"input": len(lines)},
                "coverage": {}, "notes": [],
            },
            "pagination": {
                "limit": limit, "offset": offset, "returned": len(lines),
                "total": total,
                "next_offset": None if end >= total else end,
                "next_cursor": lines[-1]["so_line"] if lines else None,
                "exhausted": end >= total, "partial": end < total,
                "termination_reason": "exhausted" if end >= total else "page_limit",
            },
        }

    def _run(self, total=2, excel=False):
        def fake_call(base, key, secret, filters):
            return self._page(total, int(filters.get("offset") or 0),
                              int(filters["limit"]))

        argv = ["--so", "SO-1", "--test", "--page-size", "1"]
        if not excel:
            argv.append("--no-excel")
        with mock.patch.object(self.exporter.iss, "load_credentials",
                               return_value=("k", "s")), \
             mock.patch.object(self.exporter.iss, "resolve_env_files",
                               return_value=None), \
             mock.patch.object(self.exporter.iss, "ENV_URLS",
                               {"test": "http://test"}), \
             mock.patch.object(self.exporter, "_call", side_effect=fake_call):
            with tempfile.TemporaryDirectory() as td:
                rc = self.exporter.main(argv + ["--out", td])
                self.assertEqual(rc, 0)
                run = list((Path(td) / "runs").glob("run-*"))[0]
                payload = json.loads((run / "production_evidence.json")
                                     .read_text(encoding="utf-8"))
                manifest = json.loads((run / "manifest.json")
                                      .read_text(encoding="utf-8"))
                digest = hashlib.sha256(
                    (run / "production_evidence.json").read_bytes()).hexdigest()
                xlsx_rows = None
                if excel:
                    from openpyxl import load_workbook
                    wb = load_workbook(run / "supply_facts.xlsx", read_only=True)
                    xlsx_rows = list(wb["production_evidence"].iter_rows(
                        values_only=True))
                    wb.close()
                return payload, manifest, digest, xlsx_rows

    def test_production_evidence_is_exported_with_checksum_and_rows(self):
        payload, manifest, digest, _ = self._run(total=2)
        self.assertEqual(len(payload), 2)
        entry = manifest["files"]["production_evidence.json"]
        self.assertEqual(entry["rows"], 2)
        self.assertEqual(entry["sha256"], digest)
        flat = self.exporter._flatten_production_evidence(payload)
        self.assertEqual(manifest["datasets"]["production_evidence"]["rows"],
                         len(flat))
        self.assertEqual(manifest["datasets"]["production_evidence"]["lines"], 2)

    def test_flatten_is_one_row_per_wo_and_evidence_class(self):
        flat = self.exporter._flatten_production_evidence([self._pe_line("SOI-1")])
        self.assertEqual(len(flat), 5)
        classes = {row["evidence_class"] for row in flat}
        self.assertEqual(classes, {"first_process_done", "all_process_done",
                                   "qc_performed", "qc_passed", "stock_in_posted"})
        stock = next(row for row in flat if row["evidence_class"] == "stock_in_posted")
        self.assertEqual(stock["gross_qty"], 10.0)
        self.assertEqual(stock["net_qty"], 10.0)
        self.assertEqual(stock["line_role"], "primary")

    def test_excel_sheet_matches_json_row_count(self):
        payload, manifest, _, xlsx_rows = self._run(total=2, excel=True)
        self.assertEqual(len(xlsx_rows) - 1,
                         manifest["datasets"]["production_evidence"]["rows"])
        self.assertEqual(len(xlsx_rows) - 1,
                         len(self.exporter._flatten_production_evidence(payload)))

    def test_write_failure_does_not_switch_latest_pointer(self):
        with tempfile.TemporaryDirectory() as td:
            out = Path(td)
            old = {"run_id": "previous-success"}
            (out / "latest.json").write_text(json.dumps(old), encoding="utf-8")

            def fake_call(base, key, secret, filters):
                return self._page(2, int(filters.get("offset") or 0),
                                  int(filters["limit"]))

            with mock.patch.object(self.exporter.iss, "load_credentials",
                                   return_value=("k", "s")), \
                 mock.patch.object(self.exporter.iss, "resolve_env_files",
                                   return_value=None), \
                 mock.patch.object(self.exporter.iss, "ENV_URLS",
                                   {"test": "http://test"}), \
                 mock.patch.object(self.exporter, "_call", side_effect=fake_call), \
                 mock.patch.object(self.exporter, "_write_xlsx",
                                   side_effect=RuntimeError("boom")):
                rc = self.exporter.main(
                    ["--so", "SO-1", "--test", "--page-size", "1", "--out", td])
            self.assertEqual(rc, 1)
            self.assertEqual(json.loads((out / "latest.json").read_text(encoding="utf-8")),
                             old)
            self.assertEqual(list((out / "runs").glob("run-*")), [])


if __name__ == "__main__":
    unittest.main()
