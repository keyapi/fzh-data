"""Verified publication: explicit schema, cross-format readback, atomic latest."""
import hashlib
import importlib.util
import json
import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch

from supply_chain_visibility.full_supply_facts import (
    SCHEMA_VERSION,
    build_full_supply_facts,
)
from supply_chain_visibility.publication import (
    CorruptedPublication,
    full_schema,
    publish,
    read_publication,
)

AS_OF = "2026-11-02T00:00:00+00:00"


def position(over=None):
    row = {
        "item_code": "I", "uom": "个", "warehouse": "WH", "purpose": "branch",
        "tt_sku": "S1", "branch": "B1", "dn_net_qty": 5.0,
        "po_completed_assumed_qty": 0.0, "open_po_qty": 0.0,
        "unresolved_qty": 0.0, "known_dn_net_qty": 5.0,
        "unknown_quantity_lines": 0, "line_count": 1,
        "return_review_lines": 0, "reasons": [], "tranches": [],
        "as_of": AS_OF, "mapping_version": "m1",
        "available_stock_qty": None, "open_order_qty": None,
        "in_production_qty": None, "inventory_inclusion_status": "unknown",
        "netting_ready": False, "auto_order": False,
        "action": "manual_review", "coverage": "dn_po_only",
    }
    row.update(over or {})
    return {"rows": [row],
            "report": {"source_versions": {"observed_at": AS_OF}}}


def abc(**over):
    row = {
        "item_code": "I", "uom": "个", "warehouse": "WH", "purpose": "branch",
        "tt_sku": "S1", "branch": "B1", "inventory_qty": "0",
        "inventory_observed_qty": "0",
        "inventory_current_available_qty": "0",
        "inventory_as_of": AS_OF, "inventory_as_of_raw": AS_OF,
        "inventory_time_status": "known", "inventory_freshness": "fresh",
        "attribution_status": "attributed", "abc_identity_source": "B",
        "source_status": "known", "reasons": [], "coverage": "abc_inventory",
    }
    row.update(over)
    return row


def inputs(*extra):
    base = [{
        "role": "mapping", "source": "approved_b", "path": "m.json",
        "sha256": "a" * 64, "rows": 1, "version": "Bv6r10", "as_of": None,
        "observed_at": None, "status": "provided",
        "required_for_closure": False, "reason": None,
    }]
    return base + list(extra)


def dataset_sha(root, name):
    return hashlib.sha256((Path(root) / name).read_bytes()).hexdigest()


@unittest.skipUnless(importlib.util.find_spec("pyarrow"), "requires pyarrow")
class PublicationTests(unittest.TestCase):
    def test_roundtrip_manifest_and_reader(self):
        import pyarrow.parquet as pq
        with tempfile.TemporaryDirectory() as tmp:
            pos = position()
            full = build_full_supply_facts(pos, abc_inventory=[abc()],
                                           as_of=AS_OF, max_age_seconds=900)
            published = publish(tmp, full_result=full, position_result=pos,
                                inputs=inputs(), pipeline_as_of=AS_OF,
                                rerun_argv=["python", "-m", "supply_chain_visibility.supply_pipeline",
                                            "--delivery-json", "d.json",
                                            "--out", tmp],
                                max_age_seconds=900)
            self.assertEqual(published["status"], "ok")
            latest = json.loads((Path(tmp) / "latest.json").read_text(encoding="utf-8"))
            manifest = json.loads(Path(latest["manifest"]).read_text(encoding="utf-8"))
            self.assertEqual(manifest["schema_version"], "supply-publication/v1")
            self.assertEqual(manifest["versions"]["full_supply_facts"], SCHEMA_VERSION)
            self.assertFalse(manifest["netting_ready"])
            self.assertFalse(manifest["auto_order"])
            self.assertIsNone(manifest["output_summary"]["cross_layer_total"])
            self.assertEqual(set(manifest["datasets"]), {
                "full_supply_facts.parquet", "full_supply_facts.json",
                "supply_position.parquet", "supply_position.json",
                "timeline.json"})
            for name, entry in manifest["datasets"].items():
                for key in ("file", "format", "schema_version", "rule_version",
                            "implementation_version", "grain", "unique_key",
                            "rows", "sha256", "freshness", "stats",
                            "relations"):
                    self.assertIn(key, entry, name)
                self.assertEqual(dataset_sha(latest["run_dir"], name),
                                 entry["sha256"], name)
            self.assertIn("--delivery-json", manifest["rerun"]["command"])
            table = pq.read_table(Path(latest["run_dir"]) / "full_supply_facts.parquet")
            self.assertTrue(table.schema.equals(full_schema()))
            self.assertEqual(table.num_rows, 1)
            state = read_publication(tmp, as_of=AS_OF, max_age_seconds=900)
            self.assertEqual(state["status"], "healthy", state["warnings"])
            self.assertFalse(state["full_chain_ready"])

    def test_empty_result_keeps_full_fixed_schema(self):
        import pyarrow.parquet as pq
        with tempfile.TemporaryDirectory() as tmp:
            pos = {"rows": [], "report": {}}
            full = build_full_supply_facts({"rows": []})
            publish(tmp, full_result=full, position_result=pos,
                    inputs=inputs(), pipeline_as_of=AS_OF)
            latest = json.loads((Path(tmp) / "latest.json").read_text(encoding="utf-8"))
            table = pq.read_table(Path(latest["run_dir"]) / "full_supply_facts.parquet")
            self.assertTrue(table.schema.equals(full_schema()))
            self.assertEqual(table.num_rows, 0)
            data = json.loads((Path(latest["run_dir"]) / "full_supply_facts.json")
                              .read_text(encoding="utf-8"))
            self.assertEqual(data, [])
            self.assertEqual(read_publication(tmp, as_of=AS_OF,
                                              max_age_seconds=900)["status"],
                             "healthy")

    def test_null_zero_decimal_and_timezone_are_stable(self):
        with tempfile.TemporaryDirectory() as tmp:
            rows = [
                abc(item_code="I", inventory_qty="0",
                    inventory_observed_qty="0",
                    inventory_current_available_qty="0",
                    inventory_as_of="2026-11-02T08:00:00+08:00",
                    inventory_as_of_raw="2026-11-02T08:00:00+08:00"),
                abc(item_code="J", tt_sku="S2", inventory_qty=None,
                    inventory_observed_qty=None,
                    inventory_current_available_qty=None,
                    inventory_as_of=None,
                    inventory_as_of_raw="2026-10-28",
                    inventory_time_status="date_only",
                    inventory_freshness="stale",
                    attribution_status="unattributed",
                    reasons=["c_without_b_attribution"]),
            ]
            pos = position()
            full = build_full_supply_facts(pos, abc_inventory=rows,
                                           as_of=AS_OF, max_age_seconds=900)
            publish(tmp, full_result=full, position_result=pos,
                    inputs=inputs(), pipeline_as_of=AS_OF)
            latest = json.loads((Path(tmp) / "latest.json").read_text(encoding="utf-8"))
            data = json.loads((Path(latest["run_dir"]) / "full_supply_facts.json")
                              .read_text(encoding="utf-8"))
            first = next(row for row in data if row["item_code"] == "I")
            second = next(row for row in data if row["item_code"] == "J")
            self.assertEqual(first["inventory_qty"], "0")
            self.assertEqual(first["inventory_as_of"],
                             "2026-11-02T00:00:00+00:00")
            self.assertEqual(first["inventory_as_of_raw"],
                             "2026-11-02T08:00:00+08:00")
            self.assertIsNone(second["inventory_qty"])
            self.assertIsNone(second["inventory_as_of"])
            self.assertEqual(second["inventory_as_of_raw"], "2026-10-28")
            self.assertEqual(second["inventory_time_status"], "date_only")
            state = read_publication(tmp, as_of=AS_OF, max_age_seconds=900)
            self.assertNotIn(state["status"], ("corrupted", "incompatible_version"))

    def test_duplicate_target_key_is_rejected_without_switching_latest(self):
        with tempfile.TemporaryDirectory() as tmp:
            pos = position()
            full = build_full_supply_facts(pos, abc_inventory=[abc()],
                                           as_of=AS_OF, max_age_seconds=900)
            publish(tmp, full_result=full, position_result=pos,
                    inputs=inputs(), pipeline_as_of=AS_OF)
            before = (Path(tmp) / "latest.json").read_text(encoding="utf-8")
            duplicate = dict(full["rows"][0])
            duplicate["dn_net_qty"] = "9"
            bad = {"rows": full["rows"] + [duplicate],
                   "summary": full["summary"], "timeline": full["timeline"]}
            with self.assertRaises(CorruptedPublication):
                publish(tmp, full_result=bad, position_result=pos,
                        inputs=inputs(), pipeline_as_of=AS_OF)
            self.assertEqual((Path(tmp) / "latest.json").read_text(encoding="utf-8"),
                             before)
            attempt = json.loads((Path(tmp) / "last_attempt.json")
                                 .read_text(encoding="utf-8"))
            self.assertEqual(attempt["status"], "failed")
            self.assertIn("duplicate", attempt["error"].lower())

    def test_writeback_failure_keeps_previous_latest(self):
        with tempfile.TemporaryDirectory() as tmp:
            pos = position()
            full = build_full_supply_facts(pos, abc_inventory=[abc()],
                                           as_of=AS_OF, max_age_seconds=900)
            publish(tmp, full_result=full, position_result=pos,
                    inputs=inputs(), pipeline_as_of=AS_OF)
            before = (Path(tmp) / "latest.json").read_text(encoding="utf-8")
            runs_before = len(list((Path(tmp) / "runs").iterdir()))
            changed = build_full_supply_facts(
                position({"item_code": "K", "tt_sku": "S9"}),
                abc_inventory=[], as_of=AS_OF, max_age_seconds=900)
            with patch("supply_chain_visibility.publication._verify_full",
                       side_effect=CorruptedPublication("injected readback failure")):
                with self.assertRaises(CorruptedPublication):
                    publish(tmp, full_result=changed, position_result=pos,
                            inputs=inputs(), pipeline_as_of=AS_OF)
            self.assertEqual((Path(tmp) / "latest.json").read_text(encoding="utf-8"),
                             before)
            self.assertEqual(len(list((Path(tmp) / "runs").iterdir())), runs_before)
            attempt = json.loads((Path(tmp) / "last_attempt.json")
                                 .read_text(encoding="utf-8"))
            self.assertEqual(attempt["status"], "failed")
            self.assertIn("injected", attempt["error"])

    def test_disk_write_failure_keeps_previous_latest(self):
        with tempfile.TemporaryDirectory() as tmp:
            pos = position()
            full = build_full_supply_facts(pos, abc_inventory=[abc()],
                                           as_of=AS_OF, max_age_seconds=900)
            publish(tmp, full_result=full, position_result=pos,
                    inputs=inputs(), pipeline_as_of=AS_OF)
            before = (Path(tmp) / "latest.json").read_text(encoding="utf-8")
            runs_before = len(list((Path(tmp) / "runs").iterdir()))
            with patch("pyarrow.parquet.write_table",
                       side_effect=OSError("disk full")):
                with self.assertRaises(OSError):
                    publish(tmp, full_result=full, position_result=pos,
                            inputs=inputs(), pipeline_as_of=AS_OF)
            self.assertEqual((Path(tmp) / "latest.json").read_text(encoding="utf-8"),
                             before)
            self.assertEqual(len(list((Path(tmp) / "runs").iterdir())), runs_before)
            attempt = json.loads((Path(tmp) / "last_attempt.json")
                                 .read_text(encoding="utf-8"))
            self.assertEqual(attempt["status"], "failed")
            self.assertIn("disk full", attempt["error"])

    def test_reader_states(self):
        def make(tmp, **kwargs):
            pos = kwargs.pop("pos", position())
            full = kwargs.pop("full", build_full_supply_facts(
                pos, abc_inventory=[abc()], as_of=AS_OF, max_age_seconds=900))
            publish(tmp, full_result=full, position_result=pos,
                    inputs=kwargs.pop("inputs", inputs()), pipeline_as_of=AS_OF,
                    max_age_seconds=kwargs.pop("max_age_seconds", 900))

        with tempfile.TemporaryDirectory() as tmp:
            make(tmp)
            self.assertEqual(read_publication(tmp, as_of=AS_OF,
                                              max_age_seconds=900)["status"],
                             "healthy")
        with tempfile.TemporaryDirectory() as tmp:
            make(tmp, inputs=inputs({
                "role": "inventory", "path": "i.json", "sha256": "b" * 64,
                "rows": 1, "version": "v1",
                "as_of": "2026-10-01T00:00:00+00:00", "status": "provided",
                "required_for_closure": False}))
            self.assertEqual(read_publication(tmp, as_of=AS_OF,
                                              max_age_seconds=60)["status"],
                             "stale")
        with tempfile.TemporaryDirectory() as tmp:
            make(tmp, inputs=inputs({
                "role": "inventory", "path": "i.json", "sha256": "b" * 64,
                "rows": 1, "version": "v1", "as_of": "2026-10-28",
                "status": "provided", "required_for_closure": False}))
            self.assertEqual(read_publication(tmp, as_of=AS_OF,
                                              max_age_seconds=60)["status"],
                             "stale")
        with tempfile.TemporaryDirectory() as tmp:
            pos = position()
            full = build_full_supply_facts(
                pos, abc_inventory=[abc(reasons=["c_without_b_attribution"],
                                        attribution_status="unattributed")],
                as_of=AS_OF, max_age_seconds=900)
            make(tmp, pos=pos, full=full)
            self.assertEqual(read_publication(tmp, as_of=AS_OF,
                                              max_age_seconds=900)["status"],
                             "partial")
        with tempfile.TemporaryDirectory() as tmp:
            make(tmp)
            (Path(tmp) / "last_attempt.json").write_text(json.dumps({
                "status": "failed", "error": "boom"}), encoding="utf-8")
            self.assertEqual(read_publication(tmp, as_of=AS_OF,
                                              max_age_seconds=900)["status"],
                             "refresh_failed_using_previous")
        with tempfile.TemporaryDirectory() as tmp:
            make(tmp)
            latest = json.loads((Path(tmp) / "latest.json").read_text(encoding="utf-8"))
            path = Path(latest["run_dir"]) / "full_supply_facts.parquet"
            path.write_bytes(path.read_bytes() + b"x")
            self.assertEqual(read_publication(tmp, as_of=AS_OF,
                                              max_age_seconds=900)["status"],
                             "corrupted")
        with tempfile.TemporaryDirectory() as tmp:
            make(tmp)
            latest_path = Path(tmp) / "latest.json"
            latest = json.loads(latest_path.read_text(encoding="utf-8"))
            manifest_path = Path(latest["manifest"])
            manifest = json.loads(manifest_path.read_text(encoding="utf-8"))
            manifest["schema_version"] = "supply-publication/999"
            manifest_path.write_text(json.dumps(manifest), encoding="utf-8")
            latest["manifest_sha256"] = hashlib.sha256(
                manifest_path.read_bytes()).hexdigest()
            latest_path.write_text(json.dumps(latest), encoding="utf-8")
            self.assertEqual(read_publication(tmp, as_of=AS_OF,
                                              max_age_seconds=900)["status"],
                             "incompatible_version")

    def test_saved_inputs_rerun_stable(self):
        with tempfile.TemporaryDirectory() as tmp:
            pos = position()
            full = build_full_supply_facts(pos, abc_inventory=[abc()],
                                           as_of=AS_OF, max_age_seconds=900)
            first = publish(tmp, full_result=full, position_result=pos,
                            inputs=inputs(), pipeline_as_of=AS_OF)
            second = publish(tmp, full_result=full, position_result=pos,
                             inputs=inputs(), pipeline_as_of=AS_OF)
            self.assertNotEqual(first["run_dir"], second["run_dir"])
            for name in ("full_supply_facts.json", "supply_position.json",
                         "timeline.json"):
                self.assertEqual(
                    dataset_sha(first["run_dir"], name),
                    dataset_sha(second["run_dir"], name), name)
            rows_first = json.loads((Path(first["run_dir"])
                                     / "full_supply_facts.json")
                                    .read_text(encoding="utf-8"))
            rows_second = json.loads((Path(second["run_dir"])
                                      / "full_supply_facts.json")
                                     .read_text(encoding="utf-8"))
            self.assertEqual(rows_first, rows_second)

    def test_position_dataset_keeps_its_own_schema_and_grain(self):
        with tempfile.TemporaryDirectory() as tmp:
            pos = position()
            full = build_full_supply_facts(pos, abc_inventory=[abc()],
                                           as_of=AS_OF, max_age_seconds=900)
            published = publish(tmp, full_result=full, position_result=pos,
                                inputs=inputs(), pipeline_as_of=AS_OF)
            datasets = published["manifest"]["datasets"]
            position_entry = datasets["supply_position.parquet"]
            full_entry = datasets["full_supply_facts.parquet"]
            self.assertEqual(position_entry["schema_version"], "supply-position/v1")
            self.assertNotEqual(position_entry["grain"], full_entry["grain"])
            self.assertNotIn("branch", position_entry["unique_key"])

    def test_2000_synthetic_keys_have_no_cross_totals(self):
        rows = [abc(item_code="I-%04d" % i, tt_sku="S-%04d" % i,
                    branch="B-%04d" % i) for i in range(2000)]
        full = build_full_supply_facts({"rows": []}, abc_inventory=rows)
        self.assertEqual(len(full["rows"]), 2000)
        self.assertIsNone(full["summary"]["global_qty_total"])
        self.assertIsNone(full["summary"]["cross_layer_total"])
        with tempfile.TemporaryDirectory() as tmp:
            published = publish(tmp, full_result=full,
                                position_result={"rows": [], "report": {}},
                                inputs=inputs(), pipeline_as_of=AS_OF)
            self.assertEqual(
                published["manifest"]["output_summary"]["full_supply_facts_rows"],
                2000)


if __name__ == "__main__":
    unittest.main()
