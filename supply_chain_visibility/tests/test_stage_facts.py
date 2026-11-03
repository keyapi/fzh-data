"""D6 stage-detail contract: one current stage per batch, split times, CG."""
import hashlib
import importlib.util
import json
import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch

from supply_chain_visibility.full_supply_facts import build_full_supply_facts
from supply_chain_visibility.publication import (
    STAGE_KEY,
    CorruptedPublication,
    full_schema,
    publish,
    read_publication,
    target_summary_schema,
)

AS_OF = "2026-11-02T00:00:00+00:00"
BASE = {"item_code": "SKU-1", "uom": "个", "warehouse": "WH-1",
        "purpose": "branch", "branch": "B1", "tt_sku": "S1",
        "market": "US", "product_form": "finished"}


def position(**over):
    row = {**BASE, "dn_net_qty": 0, "po_completed_assumed_qty": 0,
           "open_po_qty": 0, "unresolved_qty": 0, "as_of": AS_OF,
           "known_dn_net_qty": 0, "available_stock_qty": None,
           "open_order_qty": None, "in_production_qty": None,
           "line_count": 1, "unknown_quantity_lines": 0,
           "return_review_lines": 0, "mapping_version": "m1",
           "inventory_inclusion_status": "unknown",
           "action": "manual_review", "coverage": "dn_po_only",
           "netting_ready": False, "auto_order": False,
           "reasons": [], "tranches": []}
    row.update(over)
    return {"rows": [row],
            "report": {"source_versions": {"observed_at": AS_OF}}}


def production(**over):
    row = {**BASE, "source_ref": "WO-1", "work_order": "WO-1",
           "batch_id": "B1", "qty": 5, "evidence_status": "proven",
           "available_date": AS_OF, "observed_at": AS_OF}
    row.update(over)
    return row


def transit(**over):
    row = {**BASE, "delivery_note": "DN-1", "waybill": "W1",
           "batch_id": "B1", "qty": 5, "source_status": "known",
           "available_date": AS_OF, "observed_at": AS_OF}
    row.update(over)
    return row


def receipt(**over):
    row = {**BASE, "source_ref": "RC-1", "receipt_id": "RC-1",
           "batch_id": "B1", "qty": 5, "signed_at": AS_OF,
           "received_at": AS_OF, "observed_at": AS_OF}
    row.update(over)
    return row


def inventory(**over):
    row = {**BASE, "source_ref": "ST-1", "snapshot_id": "S1",
           "batch_id": "B1", "qty": 5, "as_of": AS_OF,
           "source_status": "known"}
    row.update(over)
    return row


def abc_row(**over):
    row = {**BASE, "purpose": "cg", "branch": "", "batch_id": "B-CG",
           "pool": "WH-1", "inventory_qty": "5",
           "inventory_observed_qty": "5",
           "inventory_current_available_qty": "5",
           "inventory_as_of": AS_OF, "inventory_as_of_raw": AS_OF,
           "inventory_time_status": "known", "inventory_time_proven": True,
           "inventory_freshness": "fresh",
           "attribution_status": "attributed", "source_status": "known",
           "reasons": [], "coverage": "abc_inventory", "source_ref": "ST-1"}
    row.update(over)
    return row


def stage_rows(full, stage=None, batch_id=None):
    rows = full["stage_rows"]
    if stage:
        rows = [row for row in rows if row["stage"] == stage]
    if batch_id:
        rows = [row for row in rows if row["batch_id"] == batch_id]
    return rows


class StageIdentityTests(unittest.TestCase):
    def test_same_target_same_stage_two_documents_are_not_merged(self):
        full = build_full_supply_facts({"rows": []}, production=[
            production(source_ref="WO-1", work_order="WO-1",
                       batch_id="B1", qty=3),
            production(source_ref="WO-2", work_order="WO-2",
                       batch_id="B2", qty=4)])
        facts = stage_rows(full, "waiting_shipment")
        self.assertEqual(len(facts), 2)
        self.assertEqual(sorted(fact["qty"] for fact in facts), ["3", "4"])
        self.assertTrue(all(fact["counted_as_supply"] for fact in facts))

    def test_same_identity_replay_is_one_fact(self):
        record = production(source_ref="WO-1", batch_id="B1", qty=3)
        full = build_full_supply_facts({"rows": []},
                                       production=[record, dict(record)])
        facts = stage_rows(full, "waiting_shipment")
        self.assertEqual(len(facts), 1)
        self.assertEqual(facts[0]["qty"], "3")

    def test_same_identity_different_payload_is_conflict(self):
        full = build_full_supply_facts({"rows": []}, production=[
            production(source_ref="WO-1", batch_id="B1", qty=3),
            production(source_ref="WO-1", batch_id="B1", qty=4)])
        facts = stage_rows(full, "waiting_shipment")
        self.assertEqual(len(facts), 2)
        self.assertTrue(all(not fact["counted_as_supply"] for fact in facts))
        self.assertTrue(all("source_payload_conflict"
                            in fact["conflicts"] for fact in facts))

    def test_one_batch_five_stages_has_one_counted_current_stage(self):
        tranches = [
            {"delivery_note": "DN-1", "dn_item": "D1", "qty": 5,
             "bucket": "po_completed_assumed_qty", "batch_id": "B1"},
            {"delivery_note": "DN-2", "dn_item": "D2", "qty": 5,
             "bucket": "open_po_qty", "batch_id": "B1"}]
        full = build_full_supply_facts(
            position(tranches=tranches, dn_net_qty=10,
                     po_completed_assumed_qty=5, open_po_qty=5),
            production=[production(batch_id="B1", qty=5)],
            transit=[transit(batch_id="B1", qty=5)],
            receipts=[receipt(batch_id="B1", qty=5)],
            inventory=[inventory(batch_id="B1", qty=5)])
        facts = stage_rows(full, batch_id="B1")
        stages = {fact["stage"] for fact in facts}
        self.assertTrue({"open_po", "waiting_shipment", "in_transit",
                         "received", "on_hand"}.issubset(stages))
        counted = [fact for fact in facts if fact["counted_as_supply"]]
        self.assertEqual(len(counted), 1)
        self.assertEqual(counted[0]["stage"], "on_hand")
        open_po = next(fact for fact in facts if fact["stage"] == "open_po")
        self.assertFalse(open_po["counted_as_supply"])
        self.assertEqual(open_po["counted_reason"],
                         "open_po_reconciliation_only")

    def test_open_po_is_never_added_to_transit_or_on_hand(self):
        full = build_full_supply_facts(
            position(open_po_qty=5, dn_net_qty=5,
                     tranches=[{"delivery_note": "DN-1", "dn_item": "D1",
                                "qty": 5, "bucket": "open_po_qty",
                                "batch_id": "B1"}]),
            transit=[transit(batch_id="B2", qty=7)])
        summary = full["stage_summary"]
        self.assertEqual(summary["counted_qty_by_stage"].get("open_po"),
                         None)
        self.assertEqual(summary["counted_qty_by_stage"]["in_transit"], "12")
        self.assertFalse(any(fact["stage"] == "open_po"
                             and fact["counted_as_supply"]
                             for fact in full["stage_rows"]))

    def test_signed_without_receipt_is_in_transit(self):
        full = build_full_supply_facts({"rows": []}, receipts=[
            receipt(received_at=None, signed_at="2026-11-05T00:00:00+00:00")])
        fact = stage_rows(full, "in_transit")[0]
        self.assertEqual(fact["signed_at"], "2026-11-05T00:00:00+00:00")
        self.assertIsNone(fact["received_at"])
        self.assertEqual(stage_rows(full, "received"), [])
        target = full["rows"][0]
        self.assertEqual(target["signed_pending_qty"], "5")
        self.assertIsNone(target["received_qty"])


class ReceiptInventoryOverlapTests(unittest.TestCase):
    def _full(self, inventory_as_of):
        return build_full_supply_facts(
            {"rows": []},
            receipts=[receipt(received_at="2026-11-05T00:00:00+00:00",
                              signed_at="2026-11-04T00:00:00+00:00")],
            inventory=[inventory(as_of=inventory_as_of)])

    def test_receipt_included_in_later_inventory_is_not_counted(self):
        full = self._full("2026-11-06T00:00:00+00:00")
        received = stage_rows(full, "received")[0]
        on_hand = stage_rows(full, "on_hand")[0]
        self.assertEqual(received["inventory_inclusion_status"], "included")
        self.assertFalse(received["counted_as_supply"])
        self.assertTrue(on_hand["counted_as_supply"])

    def test_receipt_after_inventory_is_post_snapshot_and_counted(self):
        full = self._full("2026-11-02T00:00:00+00:00")
        received = stage_rows(full, "received")[0]
        on_hand = stage_rows(full, "on_hand")[0]
        self.assertEqual(received["inventory_inclusion_status"],
                         "post_snapshot")
        self.assertTrue(received["counted_as_supply"])
        self.assertFalse(on_hand["counted_as_supply"])

    def test_unknown_inventory_time_keeps_on_hand_and_flags_unknown(self):
        full = self._full(None)
        received = stage_rows(full, "received")[0]
        on_hand = stage_rows(full, "on_hand")[0]
        self.assertEqual(received["inventory_inclusion_status"], "unknown")
        self.assertFalse(received["counted_as_supply"])
        self.assertIn("inventory_inclusion_unknown",
                      received["unknown_reasons"])
        self.assertTrue(on_hand["counted_as_supply"])


class TimeSeparationTests(unittest.TestCase):
    def test_observed_eta_signed_received_are_distinct(self):
        full = build_full_supply_facts({"rows": []},
            production=[production(observed_at="2026-11-01T00:00:00+00:00",
                                  available_date="2026-11-10T00:00:00+00:00")])
        fact = stage_rows(full, "waiting_shipment")[0]
        self.assertEqual(fact["observed_at"], "2026-11-01T00:00:00+00:00")
        self.assertEqual(fact["eta"], "2026-11-10T00:00:00+00:00")
        self.assertIsNone(fact["actual_at"])
        self.assertIsNone(fact["signed_at"])
        self.assertIsNone(fact["received_at"])
        self.assertIsNone(fact["available_at"])

        full = build_full_supply_facts({"rows": []}, receipts=[receipt(
            observed_at="2026-11-04T00:00:00+00:00",
            signed_at="2026-11-05T00:00:00+00:00",
            received_at="2026-11-06T00:00:00+00:00")])
        fact = stage_rows(full, "received")[0]
        self.assertEqual(fact["observed_at"], "2026-11-04T00:00:00+00:00")
        self.assertEqual(fact["signed_at"], "2026-11-05T00:00:00+00:00")
        self.assertEqual(fact["received_at"], "2026-11-06T00:00:00+00:00")
        self.assertEqual(fact["available_at"], "2026-11-06T00:00:00+00:00")
        self.assertIsNone(fact["eta"])

    def test_signed_time_never_becomes_received_time(self):
        full = build_full_supply_facts({"rows": []}, receipts=[receipt(
            signed_at="2026-11-05T00:00:00+00:00", received_at=None)])
        fact = stage_rows(full, "in_transit")[0]
        self.assertEqual(fact["signed_at"], "2026-11-05T00:00:00+00:00")
        self.assertIsNone(fact["received_at"])
        self.assertIsNone(fact["available_at"])

    def test_naive_observed_time_is_not_assumed_utc(self):
        full = build_full_supply_facts({"rows": []}, production=[
            production(observed_at="2026-11-01T10:00:00")])
        fact = stage_rows(full, "waiting_shipment")[0]
        self.assertIsNone(fact["observed_at"])
        self.assertEqual(fact["observed_at_raw"], "2026-11-01T10:00:00")
        self.assertEqual(fact["observed_at_time_status"], "naive")


class OwnerAndCgTests(unittest.TestCase):
    def test_two_branch_owners_conflict(self):
        full = build_full_supply_facts({"rows": []}, production=[
            production(branch="A", source_ref="WO-A", work_order="WO-A",
                       batch_id="B1", qty=5),
            production(branch="B", source_ref="WO-B", work_order="WO-B",
                       batch_id="B1", qty=5)])
        facts = stage_rows(full, "waiting_shipment", "B1")
        self.assertTrue(all(fact["owner_status"] == "branch_conflict"
                            for fact in facts))
        self.assertTrue(all(not fact["counted_as_supply"] for fact in facts))

    def test_fba_must_not_bind_branch(self):
        full = build_full_supply_facts({"rows": []}, production=[
            production(purpose="fba", branch="B1", batch_id="B1", qty=5)])
        fact = stage_rows(full, "waiting_shipment")[0]
        self.assertEqual(fact["owner_status"], "fba_branch_conflict")
        self.assertFalse(fact["counted_as_supply"])

    def test_cg_fresh_stale_unknown(self):
        fresh = build_full_supply_facts({"rows": []},
                                        abc_inventory=[abc_row()])
        fact = stage_rows(fresh, "on_hand")[0]
        self.assertEqual(fact["purpose"], "cg")
        self.assertFalse(fact["cg_stale"])
        self.assertTrue(fact["cg_eligible"])
        self.assertTrue(fact["counted_as_supply"])

        stale = build_full_supply_facts({"rows": []}, abc_inventory=[
            abc_row(inventory_freshness="stale",
                    inventory_current_available_qty=None)])
        fact = stage_rows(stale, "on_hand")[0]
        self.assertTrue(fact["cg_stale"])
        self.assertFalse(fact["cg_eligible"])
        self.assertFalse(fact["counted_as_supply"])
        self.assertIn("cg_stale", fact["cg_blocking_reasons"])
        self.assertEqual(stale["stage_summary"]["cg_stale"], 1)

        unknown = build_full_supply_facts({"rows": []}, abc_inventory=[
            abc_row(inventory_freshness="unknown_time",
                    inventory_time_proven=False,
                    inventory_current_available_qty=None)])
        fact = stage_rows(unknown, "on_hand")[0]
        self.assertFalse(fact["cg_stale"])
        self.assertFalse(fact["cg_eligible"])
        self.assertFalse(fact["counted_as_supply"])
        self.assertEqual(unknown["stage_summary"]["cg_unknown"], 1)


@unittest.skipUnless(importlib.util.find_spec("pyarrow"), "requires pyarrow")
class StagePublicationTests(unittest.TestCase):
    @staticmethod
    def _full():
        tranches = [
            {"delivery_note": "DN-1", "dn_item": "D1", "qty": 5,
             "bucket": "po_completed_assumed_qty", "batch_id": "B1"},
            {"delivery_note": "DN-2", "dn_item": "D2", "qty": 5,
             "bucket": "open_po_qty", "batch_id": "B1"}]
        pos = position(tranches=tranches, dn_net_qty=10,
                       po_completed_assumed_qty=5, open_po_qty=5)
        full = build_full_supply_facts(
            pos, production=[production(batch_id="B1")],
            transit=[transit(batch_id="B1")],
            receipts=[receipt(batch_id="B1")],
            inventory=[inventory(batch_id="B1")],
            as_of=AS_OF, max_age_seconds=900)
        return pos, full

    def test_stage_and_target_summary_are_published_together(self):
        import pyarrow.parquet as pq
        pos, full = self._full()
        with tempfile.TemporaryDirectory() as tmp:
            published = publish(tmp, full_result=full, position_result=pos,
                                inputs=[], pipeline_as_of=AS_OF,
                                max_age_seconds=900)
            self.assertEqual(published["status"], "ok")
            latest = json.loads((Path(tmp) / "latest.json").read_text(
                encoding="utf-8"))
            run = Path(latest["run_dir"])
            manifest = json.loads(Path(latest["manifest"]).read_text(
                encoding="utf-8"))
            self.assertEqual(set(manifest["datasets"]), {
                "full_supply_facts.parquet", "full_supply_facts.json",
                "supply_target_summary.parquet", "supply_target_summary.json",
                "supply_position.parquet", "supply_position.json",
                "timeline.json"})
            stage = json.loads((run / "full_supply_facts.json").read_text(
                encoding="utf-8"))
            target = json.loads((run / "supply_target_summary.json").read_text(
                encoding="utf-8"))
            self.assertEqual(len(stage), len(full["stage_rows"]))
            self.assertEqual(len(target), len(full["rows"]))
            keys = {tuple(row.get(field) or "" for field in STAGE_KEY)
                    for row in stage}
            self.assertEqual(len(keys), len(stage))
            stage_table = pq.read_table(run / "full_supply_facts.parquet")
            self.assertTrue(stage_table.schema.equals(full_schema()))
            self.assertEqual(stage_table.num_rows, len(stage))
            target_table = pq.read_table(run / "supply_target_summary.parquet")
            self.assertTrue(target_table.schema.equals(target_summary_schema()))
            self.assertEqual(target_table.num_rows, len(target))
            summary = manifest["output_summary"]
            self.assertEqual(summary["full_supply_facts_rows"], len(stage))
            self.assertEqual(summary["supply_target_summary_rows"], len(target))
            self.assertEqual(summary["stage_unique_key"], list(STAGE_KEY))
            self.assertEqual(summary["stage_summary"]["counted_stage_counts"],
                             {"on_hand": 1})
            state = read_publication(tmp, as_of=AS_OF, max_age_seconds=900,
                                     allow_stale=True)
            self.assertTrue(state["readable"], state["warnings"])
            self.assertIn(state["status"], ("healthy", "partial"))
            self.assertEqual(state["rows"], len(stage))
            self.assertEqual(state["target_summary_rows"], len(target))
            self.assertEqual(state["row_level"]["rows"], len(stage))
            self.assertGreaterEqual(state["row_level"]["fresh"], 1)

    def test_mixed_target_summary_version_is_rejected(self):
        pos, full = self._full()
        with tempfile.TemporaryDirectory() as tmp:
            publish(tmp, full_result=full, position_result=pos,
                    inputs=[], pipeline_as_of=AS_OF)
            latest_path = Path(tmp) / "latest.json"
            latest = json.loads(latest_path.read_text(encoding="utf-8"))
            manifest_path = Path(latest["manifest"])
            manifest = json.loads(manifest_path.read_text(encoding="utf-8"))
            manifest["versions"]["supply_target_summary"] = "old/v1"
            manifest_path.write_text(json.dumps(manifest), encoding="utf-8")
            latest["manifest_sha256"] = hashlib.sha256(
                manifest_path.read_bytes()).hexdigest()
            latest_path.write_text(json.dumps(latest), encoding="utf-8")
            state = read_publication(tmp, as_of=AS_OF, max_age_seconds=900)
            self.assertEqual(state["status"], "incompatible_version")

    def test_duplicate_stage_key_keeps_previous_latest(self):
        pos, full = self._full()
        with tempfile.TemporaryDirectory() as tmp:
            publish(tmp, full_result=full, position_result=pos,
                    inputs=[], pipeline_as_of=AS_OF)
            before = (Path(tmp) / "latest.json").read_text(encoding="utf-8")
            broken = dict(full)
            broken["stage_rows"] = list(full["stage_rows"]) + [
                dict(full["stage_rows"][0])]
            with self.assertRaises(CorruptedPublication):
                publish(tmp, full_result=broken, position_result=pos,
                        inputs=[], pipeline_as_of=AS_OF)
            self.assertEqual((Path(tmp) / "latest.json").read_text(
                encoding="utf-8"), before)

    def test_stage_readback_failure_keeps_previous_latest(self):
        pos, full = self._full()
        with tempfile.TemporaryDirectory() as tmp:
            publish(tmp, full_result=full, position_result=pos,
                    inputs=[], pipeline_as_of=AS_OF)
            before = (Path(tmp) / "latest.json").read_text(encoding="utf-8")
            with patch(
                    "supply_chain_visibility.publication._verify_stage",
                    side_effect=CorruptedPublication("injected stage readback")):
                with self.assertRaises(CorruptedPublication):
                    publish(tmp, full_result=full, position_result=pos,
                            inputs=[], pipeline_as_of=AS_OF)
            self.assertEqual((Path(tmp) / "latest.json").read_text(
                encoding="utf-8"), before)


if __name__ == "__main__":
    unittest.main()
