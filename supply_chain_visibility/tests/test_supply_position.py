"""Consumer contract: PO completion must only close audited included DN rows."""
import copy
import hashlib
import importlib.util
import json
import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch

from supply_chain_visibility.supply_position import (
    assemble_input, build_position, publish_position, read_position, main,
)


def sample():
    scope = {"status": "provided", "source": "approved-local-scope",
             "version": "v1", "items": ["ITEM"]}
    canonical = {k: scope[k] for k in ("source", "version", "items")}
    scope["hash"] = hashlib.sha256(json.dumps(
        canonical, sort_keys=True, ensure_ascii=False).encode()).hexdigest()
    return {
        "schema_version": "supply-position-input/v1",
        "as_of": "2026-10-30T18:00:00+08:00",
        "mapping_version": "approved-B-v1",
        "delivery": {
            "schema_version": "supply-facts/v3", "rule_version": "2026-10-30.3",
            "observed_at": "2026-10-30T18:00:00+08:00",
            "implementation_version": "fixture", "scope": scope,
            "pagination": {"exhausted": True, "partial": False, "total": 1},
            "delivery_lines": [{"delivery_note": "DN1", "delivery_note_item": "L1",
                                "item_code": "ITEM", "uom": "个", "docstatus": 1,
                                "actual_qty": 10, "qty": 10,
                                "quantity_status": "known", "relevance_status": "in_scope",
                                "posting_date": "2026-10-20"}]},
        "mappings": [{"delivery_note": "DN1", "dn_item": "L1", "item_code": "ITEM",
                      "tt_sku": "SKU", "warehouse": "W1", "uom": "个",
                      "purpose": "branch", "evidence": "approved-B-row-1"}],
        "creations": [{"name": "C1", "delivery_note": "DN1", "status": "confirmed",
                       "purchase_order_code": "PO1", "lines": [
                           {"dn_item": "L1", "item_code": "ITEM", "qty": 10,
                            "uom": "个", "tt_sku": "SKU", "outcome": "included",
                            "contribution_qty": 10}]}],
        "po_statuses": {"observed_at": "2026-10-30T17:59:00+08:00", "results": {
            "PO1": {"found": True, "status": "3", "identity": {
                "purchaseOrderCode": "PO1"}}}},
    }


class PositionTests(unittest.TestCase):
    def test_assemble_existing_api_wrappers_without_inventing_missing_lines(self):
        p = sample()
        mapping = {"source": "approved-B", "version": p["mapping_version"], "rows": p["mappings"]}
        audit = {"message": {"delivery_note": "DN1", "creations": [p["creations"][0]]}}
        status = {"message": p["po_statuses"]}
        joined = assemble_input(delivery={"message": p["delivery"]}, mappings=mapping,
                                audits=[audit], statuses=[status], as_of=p["as_of"])
        self.assertEqual(build_position(joined)["rows"][0]["po_completed_assumed_qty"], 10)
        del audit["message"]["creations"][0]["lines"]
        joined = assemble_input(delivery=p["delivery"], mappings=mapping,
                                audits=[audit], statuses=[status], as_of=p["as_of"])
        self.assertEqual(build_position(joined)["rows"][0]["unresolved_qty"], 10)

    def test_assembly_retains_each_batches_source_time_and_rejects_conflicts(self):
        p = sample()
        mapping = {"source": "approved-B", "version": "B1", "rows": p["mappings"]}
        joined = assemble_input(delivery=p["delivery"], mappings=mapping,
                                audits=[], statuses=[p["po_statuses"]], as_of=p["as_of"])
        self.assertEqual(joined["po_statuses"]["results"]["PO1"]["observed_at"],
                         p["po_statuses"]["observed_at"])
        conflicting = copy.deepcopy(p["po_statuses"])
        conflicting["results"]["PO1"]["status"] = "0"
        with self.assertRaisesRegex(ValueError, "conflict"):
            assemble_input(delivery=p["delivery"], mappings=mapping, audits=[],
                           statuses=[p["po_statuses"], conflicting], as_of=p["as_of"])
        bad_audit = {"delivery_note": "DN2", "creations": p["creations"]}
        with self.assertRaisesRegex(ValueError, "DN"):
            assemble_input(delivery=p["delivery"], mappings=mapping, audits=[bad_audit],
                           statuses=[], as_of=p["as_of"])

    def test_assembly_never_uses_fetch_time_for_missing_source_observation(self):
        p = sample()
        mapping = {"source": "approved-B", "version": "B1", "rows": p["mappings"]}
        del p["po_statuses"]["observed_at"]
        p["po_statuses"]["received_at"] = p["as_of"]
        joined = assemble_input(delivery=p["delivery"], mappings=mapping,
                                audits=[{"delivery_note": "DN1", "creations": p["creations"]}],
                                statuses=[p["po_statuses"]], as_of=p["as_of"])
        row = build_position(joined)["rows"][0]
        self.assertEqual(row["unresolved_qty"], 10)
        self.assertIn("po_observed_at_unknown", row["reasons"])

    def test_po_refresh_statuses_raw_status_shape_is_consumable(self):
        p = sample()
        status = dict(p["po_statuses"]["results"]["PO1"])
        status["raw_status"] = status.pop("status")
        status["observed_at"] = p["po_statuses"]["observed_at"]
        refreshed = {"statuses": {"PO1": status}, "unqueried": {},
                     "requested": 1, "returned": 1, "partial": False,
                     "termination_reason": "completed"}
        payload = assemble_input(delivery=p["delivery"],
            mappings={"source": "B", "version": "v1", "rows": p["mappings"]},
            audits=[{"delivery_note": "DN1", "creations": p["creations"]}],
            statuses=[refreshed], as_of=p["as_of"])
        self.assertEqual(build_position(payload)["rows"][0]["po_completed_assumed_qty"], 10)

    def test_conflicting_status_aliases_are_rejected(self):
        p = sample()
        mapping = {"source": "B", "version": "v1", "rows": p["mappings"]}
        ambiguous = {"results": p["po_statuses"]["results"], "statuses": {}}
        with self.assertRaisesRegex(ValueError, "conflict"):
            assemble_input(delivery=p["delivery"], mappings=mapping, audits=[],
                           statuses=[ambiguous], as_of=p["as_of"])
        p["po_statuses"]["results"]["PO1"]["raw_status"] = "0"
        with self.assertRaisesRegex(ValueError, "conflict"):
            assemble_input(delivery=p["delivery"], mappings=mapping, audits=[],
                           statuses=[p["po_statuses"]], as_of=p["as_of"])

    def test_build_report_carries_partial_batch_coverage(self):
        p = sample()
        p["input_sources"] = {"po_batches": [{"partial": True, "termination_reason": "rate_limited"}]}
        report = build_position(p)["report"]
        self.assertEqual(report["input_sources"], p["input_sources"])

    def test_2000_goods_are_accounted_once(self):
        p = sample()
        base_line = p["delivery"]["delivery_lines"][0]
        base_creation = p["creations"][0]
        base_mapping = p["mappings"][0]
        codes = ["ITEM-%s" % i for i in range(2000)]
        p["delivery"]["scope"]["items"] = codes
        scope = p["delivery"]["scope"]
        # Scope hash sorts/deduplicates codes lexically.
        scope["hash"] = hashlib.sha256(json.dumps(
            {"source": scope["source"], "version": scope["version"], "items": sorted(codes)},
            sort_keys=True, ensure_ascii=False).encode()).hexdigest()
        p["delivery"]["delivery_lines"], p["mappings"], p["creations"] = [], [], []
        p["po_statuses"]["results"] = {}
        for i, code in enumerate(codes):
            dn, li, po, sku = "DN%s" % i, "L%s" % i, "PO%s" % i, "SKU%s" % i
            p["delivery"]["delivery_lines"].append(dict(base_line, delivery_note=dn,
                                                        delivery_note_item=li, item_code=code))
            p["mappings"].append(dict(base_mapping, delivery_note=dn, dn_item=li,
                                      item_code=code, tt_sku=sku))
            c = dict(base_creation, name="C%s" % i, delivery_note=dn, purchase_order_code=po,
                     lines=[dict(base_creation["lines"][0], dn_item=li, item_code=code, tt_sku=sku)])
            p["creations"].append(c)
            p["po_statuses"]["results"][po] = {"found": True, "status": "3",
                "identity": {"purchaseOrderCode": po}}
        p["delivery"]["pagination"]["total"] = 2000
        result = build_position(p)
        self.assertEqual(len(result["rows"]), 2000)
        self.assertEqual(result["report"]["accounted_lines"], 2000)
        self.assertEqual(sum(r["po_completed_assumed_qty"] for r in result["rows"]), 20000)

    @unittest.skipUnless(importlib.util.find_spec("pyarrow"), "requires pyarrow")
    def test_cli_assembles_separate_saved_exports(self):
        p = sample()
        with tempfile.TemporaryDirectory() as tmp:
            files = {
                "delivery.json": {"message": p["delivery"]},
                "mapping.json": {"source": "approved-B", "version": "v1", "rows": p["mappings"]},
                "audit.json": {"message": {"delivery_note": "DN1", "creations": p["creations"]}},
                "status.json": {"message": p["po_statuses"]}}
            for name, content in files.items():
                Path(tmp, name).write_text(json.dumps(content), encoding="utf-8")
            out = str(Path(tmp, "published"))
            with patch("builtins.print"):
                main(["--delivery-json", str(Path(tmp, "delivery.json")),
                      "--mapping-json", str(Path(tmp, "mapping.json")),
                      "--audit-json", str(Path(tmp, "audit.json")),
                      "--status-json", str(Path(tmp, "status.json")),
                      "--as-of", p["as_of"], "--out", out])
            data = read_position(out, as_of=p["as_of"], max_age_seconds=3600)
            self.assertEqual(data["rows"][0]["po_completed_assumed_qty"], 10)

    def test_complete_po_closes_only_included_goods(self):
        p = sample()
        other = copy.deepcopy(p["delivery"]["delivery_lines"][0])
        other["delivery_note_item"] = "L2"
        p["delivery"]["delivery_lines"].append(other)
        p["delivery"]["pagination"]["total"] = 2
        m = dict(p["mappings"][0], dn_item="L2")
        p["mappings"].append(m)
        p["creations"][0]["lines"].append({
            "dn_item": "L2", "item_code": "ITEM", "qty": 10, "uom": "个",
            "tt_sku": "SKU", "outcome": "mapping_failed"})
        r = build_position(p)
        row = r["rows"][0]
        self.assertEqual(row["dn_net_qty"], 20)
        self.assertEqual(row["po_completed_assumed_qty"], 10)
        self.assertEqual(row["unresolved_qty"], 10)
        self.assertEqual(row["open_po_qty"], 0)
        self.assertEqual(r["report"]["input_lines"], 2)
        self.assertFalse(row["netting_ready"])

    def test_open_partial_and_short_closed_are_distinct(self):
        for status, bucket, reason in [("0", "open_po_qty", "po_open"),
                                       ("1", "unresolved_qty", "partial_item_allocation_unknown"),
                                       ("2", "unresolved_qty", "short_receipt_allocation_unknown")]:
            p = sample()
            p["po_statuses"]["results"]["PO1"]["status"] = status
            row = build_position(p)["rows"][0]
            self.assertEqual(row[bucket], 10)
            self.assertIn(reason, row["reasons"])
            self.assertEqual(row["po_completed_assumed_qty"], 0)

    def test_old_missing_or_duplicate_audit_is_not_invented(self):
        for change in ("missing", "duplicate", "no_lines", "unknown", "superseded"):
            p = sample()
            if change == "missing":
                p["creations"] = []
            elif change == "duplicate":
                p["creations"].append(dict(p["creations"][0], name="C2"))
            elif change == "no_lines":
                del p["creations"][0]["lines"]
            elif change == "unknown":
                p["creations"][0]["status"] = "outcome_unknown"
            else:
                p["creations"][0]["superseded_by"] = "C2"
            row = build_position(p)["rows"][0]
            self.assertEqual(row["unresolved_qty"], 10)
            self.assertEqual(row["po_completed_assumed_qty"], 0)

    def test_raw_query_errors_staleness_and_identity_do_not_close(self):
        for change in ("limited", "mismatch", "stale", "future", "boolean"):
            p = sample()
            if change == "limited":
                p["po_statuses"]["results"]["PO1"] = {
                    "found": False, "status": None, "reason": "rate_limited"}
            elif change == "mismatch":
                p["po_statuses"]["results"]["PO1"]["identity"]["purchaseOrderCode"] = "OTHER"
            elif change == "stale":
                p["po_statuses"]["observed_at"] = "2026-10-28T00:00:00+08:00"
            elif change == "future":
                p["po_statuses"]["observed_at"] = "2026-10-31T00:00:00+08:00"
            else:
                p["po_statuses"]["results"]["PO1"]["status"] = True
            row = build_position(p)["rows"][0]
            self.assertEqual(row["unresolved_qty"], 10)
            self.assertEqual(row["po_completed_assumed_qty"], 0)

    def test_audit_changed_quantity_sku_and_unit_are_preserved_as_unknown(self):
        for field, value in [("qty", 12), ("contribution_qty", 12),
                             ("tt_sku", "OTHER"), ("uom", "套")]:
            p = sample()
            p["creations"][0]["lines"][0][field] = value
            row = build_position(p)["rows"][0]
            self.assertEqual(row["unresolved_qty"], 10)

    def test_actual_quantity_drift_and_failed_conservation_cannot_close_po(self):
        p = sample()
        p["delivery"]["delivery_lines"][0]["actual_qty"] = 12
        row = build_position(p)["rows"][0]
        self.assertEqual(row["po_completed_assumed_qty"], 0)
        self.assertEqual(row["unresolved_qty"], 12)
        p = sample()
        p["creations"][0]["conservation_ok"] = False
        row = build_position(p)["rows"][0]
        self.assertEqual(row["unresolved_qty"], 10)

    def test_string_return_flag_is_rejected_instead_of_truthy(self):
        p = sample()
        p["delivery"]["delivery_lines"][0]["is_return"] = "0"
        with self.assertRaises(ValueError):
            build_position(p)

    def test_unknown_quantity_and_missing_mapping_are_not_zero(self):
        p = sample()
        p["delivery"]["delivery_lines"][0]["actual_qty"] = None
        p["delivery"]["delivery_lines"][0]["quantity_status"] = "unknown"
        p["mappings"] = []
        row = build_position(p)["rows"][0]
        self.assertIsNone(row["dn_net_qty"])
        self.assertIsNone(row["po_completed_assumed_qty"])
        self.assertEqual(row["unknown_quantity_lines"], 1)
        self.assertEqual(row["purpose"], "unknown")

    def test_fba_exclusion_is_fact_specific_not_item_global(self):
        p = sample()
        p["mappings"][0]["purpose"] = "fba"
        row = build_position(p)["rows"][0]
        self.assertEqual(row["po_completed_assumed_qty"], 10)
        self.assertEqual(row["action"], "excluded_fba")
        self.assertFalse(row["netting_ready"])

    def test_completed_qty_is_not_available_stock(self):
        row = build_position(sample())["rows"][0]
        self.assertIsNone(row["available_stock_qty"])
        self.assertIsNone(row["open_order_qty"])
        self.assertEqual(row["inventory_inclusion_status"], "unknown")
        self.assertFalse(row["netting_ready"])

    def test_no_observed_delivery_remains_unknown_not_zero(self):
        p = sample()
        p["delivery"]["delivery_lines"] = []
        p["delivery"]["pagination"]["total"] = 0
        r = build_position(p)
        self.assertEqual(len(r["rows"]), 1)
        self.assertIsNone(r["rows"][0]["dn_net_qty"])
        self.assertIn("no_observed_delivery", r["rows"][0]["reasons"])

    def test_object_scope_entries_use_existing_canonicalization(self):
        p = sample()
        p["delivery"]["scope"]["items"] = [{"item_code": "ITEM", "role": "finished"}]
        self.assertEqual(build_position(p)["rows"][0]["dn_net_qty"], 10)

    def test_returns_do_not_close_gross_quantity_or_block_other_goods(self):
        p = sample()
        ret = dict(p["delivery"]["delivery_lines"][0], delivery_note="RET1",
                   delivery_note_item="RL1", is_return=1, return_against="DN1",
                   actual_qty=-2, qty=-2)
        p["delivery"]["delivery_lines"].append(ret)
        p["delivery"]["pagination"]["total"] = 2
        p["mappings"].append(dict(p["mappings"][0], delivery_note="RET1", dn_item="RL1"))
        row = build_position(p)["rows"][0]
        self.assertEqual(row["known_dn_net_qty"], 8)
        self.assertIsNone(row["po_completed_assumed_qty"])
        self.assertIn("return_requires_review", row["reasons"])

    def test_reject_partial_duplicate_and_bad_numeric_input(self):
        for change in ("partial", "duplicate", "nan", "bool", "negative"):
            p = sample()
            if change == "partial":
                p["delivery"]["pagination"]["partial"] = True
            elif change == "duplicate":
                p["delivery"]["delivery_lines"] *= 2
                p["delivery"]["pagination"]["total"] = 2
            else:
                p["delivery"]["delivery_lines"][0]["actual_qty"] = {
                    "nan": float("nan"), "bool": True, "negative": -1}[change]
            with self.assertRaises(ValueError):
                build_position(p)

    @unittest.skipUnless(importlib.util.find_spec("pyarrow"), "Parquet checks require uv run --with pyarrow")
    def test_publish_readback_and_failure_does_not_replace_latest(self):
        import pyarrow.parquet as pq
        with tempfile.TemporaryDirectory() as tmp:
            result = build_position(sample())
            directory = publish_position(result, tmp)
            rows = pq.read_table(directory / "supply_position.parquet").to_pylist()
            self.assertEqual(rows[0]["po_completed_assumed_qty"], 10)
            latest = Path(tmp, "latest.json").read_bytes()
            broken = copy.deepcopy(result)
            broken["rows"][0]["dn_net_qty"] = float("nan")
            with self.assertRaises(ValueError):
                publish_position(broken, tmp)
            self.assertEqual(Path(tmp, "latest.json").read_bytes(), latest)

    @unittest.skipUnless(importlib.util.find_spec("pyarrow"), "Parquet checks require uv run --with pyarrow")
    def test_io_failure_keeps_latest_and_records_failure(self):
        with tempfile.TemporaryDirectory() as tmp:
            result = build_position(sample())
            publish_position(result, tmp)
            latest = Path(tmp, "latest.json").read_bytes()
            with patch("pyarrow.parquet.write_table", side_effect=OSError("disk full")):
                with self.assertRaises(OSError):
                    publish_position(result, tmp)
            self.assertEqual(Path(tmp, "latest.json").read_bytes(), latest)
            failure = json.loads(Path(tmp, "last_attempt.json").read_text(encoding="utf-8"))
            self.assertEqual(failure["status"], "failed")

    @unittest.skipUnless(importlib.util.find_spec("pyarrow"), "requires pyarrow")
    def test_reader_validates_integrity_and_decodes_evidence(self):
        with tempfile.TemporaryDirectory() as tmp:
            final = publish_position(build_position(sample()), tmp)
            data = read_position(tmp, as_of="2026-10-30T18:01:00+08:00", max_age_seconds=3600)
            self.assertEqual(data["rows"][0]["tranches"][0]["po_code"], "PO1")
            self.assertFalse(data["full_chain_ready"])
            self.assertEqual(data["warnings"], ["dn_po_only_not_replenishment_decisions"])
            with (final / "supply_position.parquet").open("ab") as file:
                file.write(b"corrupt")
            with self.assertRaisesRegex(ValueError, "hash"):
                read_position(tmp, as_of="2026-10-30T18:01:00+08:00", max_age_seconds=3600)

    @unittest.skipUnless(importlib.util.find_spec("pyarrow"), "requires pyarrow")
    def test_reader_blocks_stale_future_or_failed_refresh(self):
        with tempfile.TemporaryDirectory() as tmp:
            publish_position(build_position(sample()), tmp)
            for now in ("2026-11-02T18:00:00+08:00", "2026-10-29T18:00:00+08:00"):
                with self.assertRaisesRegex(ValueError, "stale|future"):
                    read_position(tmp, as_of=now, max_age_seconds=3600)
            with patch("pyarrow.parquet.write_table", side_effect=OSError("disk full")):
                with self.assertRaises(OSError):
                    publish_position(build_position(sample()), tmp)
            with self.assertRaisesRegex(ValueError, "refresh"):
                read_position(tmp, as_of="2026-10-30T18:01:00+08:00", max_age_seconds=3600)
            data = read_position(tmp, as_of="2026-11-02T18:00:00+08:00",
                                 max_age_seconds=3600, allow_stale=True)
            self.assertIn("snapshot_stale", data["warnings"])
            self.assertIn("last_refresh_failed", data["warnings"])

    @unittest.skipUnless(importlib.util.find_spec("pyarrow"), "requires pyarrow")
    def test_recent_publication_does_not_refresh_old_source_timestamps(self):
        p = sample()
        p["delivery"]["observed_at"] = "2026-10-28T18:00:00+08:00"
        with tempfile.TemporaryDirectory() as tmp:
            publish_position(build_position(p), tmp)
            with self.assertRaisesRegex(ValueError, "delivery_source_stale"):
                read_position(tmp, as_of=p["as_of"], max_age_seconds=3600)
        p = sample()
        with tempfile.TemporaryDirectory() as tmp:
            publish_position(build_position(p), tmp)
            with self.assertRaisesRegex(ValueError, "po_source_stale"):
                read_position(tmp, as_of="2026-10-30T18:20:00+08:00", max_age_seconds=3600)

    @unittest.skipUnless(importlib.util.find_spec("pyarrow"), "requires pyarrow")
    def test_reader_rejects_pointer_escape_and_report_tampering(self):
        with tempfile.TemporaryDirectory() as tmp:
            final = publish_position(build_position(sample()), tmp)
            report = final / "report.json"
            report.write_text("{}", encoding="utf-8")
            with self.assertRaisesRegex(ValueError, "hash"):
                read_position(tmp, as_of="2026-10-30T18:01:00+08:00", max_age_seconds=3600)
            Path(tmp, "latest.json").write_text(json.dumps({"directory": "../other",
                                                          "manifest": "manifest.json"}))
            with self.assertRaisesRegex(ValueError, "path|directory"):
                read_position(tmp, as_of="2026-10-30T18:01:00+08:00", max_age_seconds=3600)

    def test_malformed_input_records_failed_refresh(self):
        with tempfile.TemporaryDirectory() as tmp:
            input_file = Path(tmp, "broken.json")
            input_file.write_text("{broken", encoding="utf-8")
            with self.assertRaises(ValueError):
                main(["--input", str(input_file), "--out", tmp])
            failure = json.loads(Path(tmp, "last_attempt.json").read_text(encoding="utf-8"))
            self.assertEqual(failure["status"], "failed")


if __name__ == "__main__":
    unittest.main()
