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
           "source_status": "known", "inventory_time_status": "known",
           "inventory_time_proven": True, "inventory_freshness": "fresh"}
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
        self.assertEqual(len(facts), 1)
        fact = facts[0]
        self.assertTrue(fact["payload_conflict"])
        self.assertIsNone(fact["qty"])
        self.assertEqual(fact["qty_status"], "unknown")
        self.assertFalse(fact["counted_as_supply"])
        self.assertEqual(len(fact["payload_hashes"]), 2)
        self.assertIn("source_payload_conflict", fact["conflicts"])

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

    def test_unknown_inventory_time_does_not_supersede_receipt(self):
        full = self._full(None)
        received = stage_rows(full, "received")[0]
        on_hand = stage_rows(full, "on_hand")[0]
        self.assertEqual(received["inventory_inclusion_status"], "unknown")
        self.assertTrue(received["counted_as_supply"])
        self.assertIn("inventory_inclusion_unknown",
                      received["unknown_reasons"])
        self.assertFalse(on_hand["counted_as_supply"])
        self.assertIn("on_hand_not_current", on_hand["unknown_reasons"])
        self.assertEqual(on_hand["inventory_inclusion_status"], "unknown")


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


class ReviewIdentityAndInclusionTests(unittest.TestCase):
    def test_document_identities_without_common_batch_do_not_accumulate(self):
        tranches = [{"delivery_note": "DN-1", "dn_item": "D1", "qty": 5,
                     "bucket": "po_completed_assumed_qty"}]
        full = build_full_supply_facts(
            position(tranches=tranches, dn_net_qty=5,
                     po_completed_assumed_qty=5),
            production=[production(batch_id=None, qty=5)],
            receipts=[receipt(batch_id=None, qty=5)],
            inventory=[inventory(batch_id=None, qty=5)])
        stages = {fact["stage"] for fact in full["stage_rows"]}
        self.assertTrue({"in_transit", "waiting_shipment", "received",
                         "on_hand"}.issubset(stages))
        self.assertTrue(all(fact["lineage_status"] == "unproven"
                            for fact in full["stage_rows"]))
        self.assertFalse(any(fact["counted_as_supply"]
                             for fact in full["stage_rows"]))
        self.assertEqual(full["stage_summary"]["counted_stage_counts"], {})
        self.assertEqual(full["stage_summary"]["counted_qty_by_stage"], {})

    def test_different_batch_receipt_and_inventory_are_not_included(self):
        full = build_full_supply_facts(
            {"rows": []},
            receipts=[receipt(batch_id="A",
                              received_at="2026-11-01T00:00:00+00:00",
                              signed_at="2026-10-31T00:00:00+00:00")],
            inventory=[inventory(batch_id="B",
                                 as_of="2026-11-06T00:00:00+00:00")])
        received = stage_rows(full, "received", "A")[0]
        on_hand = stage_rows(full, "on_hand", "B")[0]
        self.assertEqual(received["inventory_inclusion_status"], "unknown")
        self.assertEqual(on_hand["inventory_inclusion_status"], "included")
        self.assertTrue(received["counted_as_supply"])
        self.assertTrue(on_hand["counted_as_supply"])

    def test_receipt_before_signed_is_a_conflict(self):
        full = build_full_supply_facts({"rows": []}, receipts=[receipt(
            signed_at="2026-08-11T00:00:00+00:00",
            received_at="2026-07-10T00:00:00+00:00")])
        fact = stage_rows(full, "received")[0]
        self.assertIn("receipt_before_signed", fact["conflicts"])
        self.assertEqual(fact["qty_status"], "unknown")
        self.assertEqual(fact["confidence"], "conflict")
        self.assertFalse(fact["counted_as_supply"])
        self.assertIsNone(full["rows"][0]["received_qty"])
        self.assertEqual(fact["received_at"], "2026-07-10T00:00:00+00:00")
        self.assertEqual(fact["signed_at"], "2026-08-11T00:00:00+00:00")

    def test_received_before_actual_transit_is_time_order_conflict(self):
        full = build_full_supply_facts({"rows": []}, receipts=[
            receipt(source_ref="RC-A", receipt_id="RC-A", batch_id="B1",
                    signed_at="2026-10-31T00:00:00+00:00",
                    received_at="2026-11-01T00:00:00+00:00"),
            receipt(source_ref="RC-B", receipt_id="RC-B", batch_id="B1",
                    signed_at="2026-11-05T00:00:00+00:00",
                    received_at=None)])
        self.assertTrue(all("time_order_conflict" in fact["conflicts"]
                            or "receipt_before_signed" in fact["conflicts"]
                            for fact in full["stage_rows"]))
        self.assertFalse(any(fact["counted_as_supply"]
                             for fact in full["stage_rows"]))

    def test_waiting_eta_does_not_regress_actual_transit(self):
        full = build_full_supply_facts(
            {"rows": []},
            production=[production(batch_id="B1", qty=5,
                                  available_date="2026-12-01T00:00:00+00:00")],
            receipts=[receipt(batch_id="B1", qty=5,
                              signed_at="2026-11-01T00:00:00+00:00",
                              received_at=None)])
        transit = stage_rows(full, "in_transit")[0]
        waiting = stage_rows(full, "waiting_shipment")[0]
        self.assertTrue(transit["counted_as_supply"])
        self.assertFalse(waiting["counted_as_supply"])

    def test_waiting_actual_after_transit_is_stage_regression(self):
        full = build_full_supply_facts(
            {"rows": []},
            production=[production(batch_id="B1", qty=5,
                                  actual_at="2026-11-05T00:00:00+00:00")],
            receipts=[receipt(batch_id="B1", qty=5,
                              signed_at="2026-11-01T00:00:00+00:00",
                              received_at=None)])
        waiting = stage_rows(full, "waiting_shipment")[0]
        transit = stage_rows(full, "in_transit")[0]
        self.assertIn("stage_regression", waiting["conflicts"])
        self.assertIn("stage_regression", transit["conflicts"])
        self.assertFalse(waiting["counted_as_supply"])
        self.assertFalse(transit["counted_as_supply"])

    def test_real_zmt26071090_is_negative_receipt_conflict(self):
        # Real Tongtool fragment: signed 2026-08-11, receipt 2026-07-10.
        # No common PO/batch, so it stays a negative sample, never a closure.
        full = build_full_supply_facts({"rows": []}, receipts=[receipt(
            source_ref="ZMT26071090", receipt_id="ZMT26071090",
            batch_id=None, signed_at="2026-08-11T00:00:00+00:00",
            received_at="2026-07-10T00:00:00+00:00")])
        fact = stage_rows(full, "received")[0]
        self.assertIn("receipt_before_signed", fact["conflicts"])
        self.assertFalse(fact["physical_lineage_id"])
        self.assertEqual(fact["lineage_status"], "unproven")
        self.assertFalse(fact["counted_as_supply"])
        self.assertIsNone(full["rows"][0]["received_qty"])

    def test_observed_at_does_not_change_business_stage(self):
        def build(observed):
            return build_full_supply_facts({"rows": []}, receipts=[receipt(
                batch_id="B1", signed_at="2026-11-05T00:00:00+00:00",
                received_at=None, observed_at=observed)])
        first = build("2026-11-01T00:00:00+00:00")
        second = build("2026-11-02T00:00:00+00:00")
        fact_first = stage_rows(first, "in_transit")[0]
        fact_second = stage_rows(second, "in_transit")[0]
        self.assertEqual(fact_first["stage_fact_id"],
                         fact_second["stage_fact_id"])
        self.assertTrue(fact_first["counted_as_supply"])
        self.assertTrue(fact_second["counted_as_supply"])
        self.assertNotEqual(fact_first["payload_hash"],
                            fact_second["payload_hash"])

    def test_actual_is_preferred_over_estimate(self):
        full = build_full_supply_facts({"rows": []}, production=[
            production(source_ref="WO-1", batch_id="B1", qty=3,
                       evidence_status="proven"),
            production(source_ref="WO-2", batch_id="B2", qty=4,
                       evidence_status="estimated")])
        counted = [fact for fact in stage_rows(full, "waiting_shipment")
                   if fact["counted_as_supply"]]
        self.assertEqual(len(counted), 1)
        self.assertEqual(counted[0]["batch_id"], "B1")
        self.assertEqual(counted[0]["qty"], "3")
        self.assertEqual(counted[0]["confidence"], "proven")


class ReviewSameStageAndOnHandTests(unittest.TestCase):
    def test_duplicate_in_transit_chains_count_once(self):
        full = build_full_supply_facts(
            {"rows": []},
            transit=[transit(batch_id="B1", qty=5)],
            receipts=[receipt(batch_id="B1", qty=5,
                              signed_at="2026-11-01T00:00:00+00:00",
                              received_at=None)])
        facts = stage_rows(full, "in_transit", "B1")
        self.assertEqual(len(facts), 2)
        self.assertEqual({fact["same_stage_reconciliation_status"]
                          for fact in facts}, {"duplicate_evidence"})
        self.assertEqual(sum(1 for fact in facts if fact["evidence_only"]), 1)
        self.assertEqual(
            full["stage_summary"]["counted_qty_by_stage"],
            {"in_transit": "5"})

    def test_duplicate_chain_across_targets_counts_once(self):
        full = build_full_supply_facts({"rows": []}, transit=[
            transit(batch_id="B1", warehouse="WH-1", qty=5,
                    delivery_note="DN-1", waybill="W1"),
            transit(batch_id="B1", warehouse="WH-2", qty=5,
                    delivery_note="DN-2", waybill="W2")])
        facts = stage_rows(full, "in_transit", "B1")
        self.assertEqual(len(facts), 2)
        self.assertEqual(sum(1 for fact in facts if fact["evidence_only"]), 1)
        self.assertEqual(
            full["stage_summary"]["counted_qty_by_stage"],
            {"in_transit": "5"})

    def test_same_stage_different_quantity_without_allocation_conflicts(self):
        full = build_full_supply_facts(
            {"rows": []},
            transit=[transit(batch_id="B1", qty=5)],
            receipts=[receipt(batch_id="B1", qty=6,
                              signed_at="2026-11-01T00:00:00+00:00",
                              received_at=None)])
        facts = stage_rows(full, "in_transit", "B1")
        self.assertTrue(all("same_stage_quantity_conflict" in fact["conflicts"]
                            for fact in facts))
        self.assertTrue(all(fact["same_stage_reconciliation_status"]
                            == "quantity_conflict" for fact in facts))
        self.assertFalse(any(fact["counted_as_supply"] for fact in facts))
        self.assertEqual(full["stage_summary"]["counted_qty_by_stage"], {})

    def test_valid_allocation_sums_within_same_stage(self):
        full = build_full_supply_facts({"rows": []}, production=[
            production(source_ref="WO-1", batch_id="B1", qty=2,
                       allocation_id="AL-1", allocated_qty=2,
                       source_qty=5),
            production(source_ref="WO-1", batch_id="B1", qty=3,
                       allocation_id="AL-2", allocated_qty=3,
                       source_qty=5)])
        facts = stage_rows(full, "waiting_shipment", "B1")
        self.assertEqual(len(facts), 2)
        self.assertEqual({fact["same_stage_reconciliation_status"]
                          for fact in facts}, {"allocated_sum"})
        self.assertEqual({fact["stage_measured_qty"] for fact in facts},
                         {"5"})
        self.assertTrue(all(fact["counted_as_supply"] for fact in facts))
        self.assertEqual(
            full["stage_summary"]["counted_qty_by_stage"],
            {"waiting_shipment": "5"})

    def test_missing_on_hand_time_does_not_supersede_receipt(self):
        full = build_full_supply_facts(
            {"rows": []},
            receipts=[receipt(batch_id="B1", qty=5,
                              signed_at="2026-10-31T00:00:00+00:00",
                              received_at="2026-11-01T00:00:00+00:00")],
            inventory=[inventory(batch_id="B1", qty=5, as_of=None,
                                 inventory_time_status="missing",
                                 inventory_time_proven=False,
                                 inventory_freshness="unknown_time")])
        received = stage_rows(full, "received", "B1")[0]
        on_hand = stage_rows(full, "on_hand", "B1")[0]
        self.assertTrue(received["counted_as_supply"])
        self.assertFalse(on_hand["counted_as_supply"])
        self.assertIn("on_hand_not_current", on_hand["unknown_reasons"])
        self.assertEqual(on_hand["inventory_inclusion_status"], "unknown")

    def test_unusable_on_hand_time_never_supersedes_receipt(self):
        cases = {
            "stale": {
                "as_of": "2026-10-01T00:00:00+00:00",
                "inventory_freshness": "stale"},
            "future": {
                "as_of": "2026-12-01T00:00:00+00:00",
                "inventory_freshness": "future"},
            "date_only": {
                "as_of": "2026-11-01",
                "inventory_freshness": "unknown_time",
                "inventory_time_status": "date_only",
                "inventory_time_proven": False},
            "naive": {
                "as_of": "2026-11-01T00:00:00",
                "inventory_freshness": "unknown_time",
                "inventory_time_status": "naive",
                "inventory_time_proven": False},
        }
        for name, over in cases.items():
            with self.subTest(case=name):
                full = build_full_supply_facts(
                    {"rows": []},
                    receipts=[receipt(
                        batch_id="B1", qty=5,
                        signed_at="2026-10-31T00:00:00+00:00",
                        received_at="2026-11-01T00:00:00+00:00")],
                    inventory=[inventory(batch_id="B1", qty=5, **over)])
                received = stage_rows(full, "received", "B1")[0]
                on_hand = stage_rows(full, "on_hand", "B1")[0]
                self.assertTrue(received["counted_as_supply"], name)
                self.assertFalse(on_hand["counted_as_supply"], name)
                self.assertEqual(
                    on_hand["inventory_inclusion_status"], "unknown", name)


class ReviewStableKeyTests(unittest.TestCase):
    def test_same_stable_identity_same_payload_replays_once(self):
        record = production(source_ref="WO-1", batch_id="B1", qty=3)
        full = build_full_supply_facts({"rows": []},
                                       production=[record, dict(record)])
        facts = stage_rows(full, "waiting_shipment")
        self.assertEqual(len(facts), 1)
        self.assertFalse(facts[0]["payload_conflict"])
        self.assertEqual(facts[0]["payload_hashes"],
                         [facts[0]["payload_hash"]])
        self.assertEqual(facts[0]["qty"], "3")

    def test_stage_fact_id_is_stable_across_qty_and_time_changes(self):
        first = build_full_supply_facts({"rows": []}, production=[
            production(source_ref="WO-1", batch_id="B1", qty=3,
                       observed_at="2026-11-01T00:00:00+00:00")])
        second = build_full_supply_facts({"rows": []}, production=[
            production(source_ref="WO-1", batch_id="B1", qty=4,
                       observed_at="2026-11-02T00:00:00+00:00")])
        fact_first = stage_rows(first, "waiting_shipment")[0]
        fact_second = stage_rows(second, "waiting_shipment")[0]
        self.assertEqual(fact_first["stage_fact_id"],
                         fact_second["stage_fact_id"])
        self.assertNotEqual(fact_first["payload_hash"],
                            fact_second["payload_hash"])

    def test_cross_snapshot_same_fact_keeps_stage_fact_id(self):
        first = build_full_supply_facts({"rows": []}, inventory=[
            inventory(snapshot_id="S1", batch_id="B1", qty=5,
                      as_of="2026-11-01T00:00:00+00:00")])
        second = build_full_supply_facts({"rows": []}, inventory=[
            inventory(snapshot_id="S1", batch_id="B1", qty=5,
                      as_of="2026-11-02T00:00:00+00:00")])
        fact_first = stage_rows(first, "on_hand")[0]
        fact_second = stage_rows(second, "on_hand")[0]
        self.assertEqual(fact_first["stage_fact_id"],
                         fact_second["stage_fact_id"])
        self.assertNotEqual(fact_first["payload_hash"],
                            fact_second["payload_hash"])

    @unittest.skipUnless(importlib.util.find_spec("pyarrow"),
                         "requires pyarrow")
    def test_payload_conflict_publishes_as_partial(self):
        pos, valid = StagePublicationTests._full()
        conflict = build_full_supply_facts({"rows": []}, production=[
            production(source_ref="WO-1", batch_id="B1", qty=3),
            production(source_ref="WO-1", batch_id="B1", qty=4)])
        with tempfile.TemporaryDirectory() as tmp:
            publish(tmp, full_result=valid, position_result=pos,
                    inputs=[], pipeline_as_of=AS_OF)
            before = (Path(tmp) / "latest.json").read_text(encoding="utf-8")
            published = publish(tmp, full_result=conflict, position_result=pos,
                                inputs=[], pipeline_as_of=AS_OF)
            self.assertEqual(published["status"], "ok")
            after = (Path(tmp) / "latest.json").read_text(encoding="utf-8")
            self.assertNotEqual(after, before)
            manifest = published["manifest"]
            self.assertTrue(manifest["output_summary"]["partial"])
            self.assertEqual(
                manifest["output_summary"]["business_conflict_rows"], 1)
            self.assertIn("source_payload_conflict",
                          manifest["output_summary"]
                          ["business_conflict_reasons"])
            state = read_publication(tmp, as_of=AS_OF,
                                     max_age_seconds=900)
            self.assertEqual(state["status"], "partial")
            self.assertTrue(state["readable"])
            self.assertEqual(state["business_conflict_rows"], 1)

    @unittest.skipUnless(importlib.util.find_spec("pyarrow"),
                         "requires pyarrow")
    def test_receipt_conflict_publishes_as_partial(self):
        pos, valid = StagePublicationTests._full()
        conflict = build_full_supply_facts({"rows": []}, receipts=[receipt(
            signed_at="2026-08-11T00:00:00+00:00",
            received_at="2026-07-10T00:00:00+00:00")])
        with tempfile.TemporaryDirectory() as tmp:
            publish(tmp, full_result=valid, position_result=pos,
                    inputs=[], pipeline_as_of=AS_OF)
            before = (Path(tmp) / "latest.json").read_text(encoding="utf-8")
            published = publish(tmp, full_result=conflict, position_result=pos,
                                inputs=[], pipeline_as_of=AS_OF)
            after = (Path(tmp) / "latest.json").read_text(encoding="utf-8")
            self.assertNotEqual(after, before)
            self.assertTrue(
                published["manifest"]["output_summary"]["partial"])
            self.assertIn("receipt_before_signed",
                          published["manifest"]["output_summary"]
                          ["business_conflict_reasons"])
            state = read_publication(tmp, as_of=AS_OF,
                                     max_age_seconds=900)
            self.assertEqual(state["status"], "partial")
            self.assertTrue(state["readable"])
            self.assertIn("business_conflicts:1", state["warnings"])

    @unittest.skipUnless(importlib.util.find_spec("pyarrow"),
                         "requires pyarrow")
    def test_stage_regression_and_time_order_publish_as_partial(self):
        pos = StagePublicationTests._full()[0]
        cases = {
            "stage_regression": build_full_supply_facts(
                {"rows": []},
                production=[production(
                    batch_id="B1", qty=5,
                    actual_at="2026-11-05T00:00:00+00:00")],
                receipts=[receipt(
                    batch_id="B1", qty=5,
                    signed_at="2026-11-01T00:00:00+00:00",
                    received_at=None)]),
            "time_order_conflict": build_full_supply_facts(
                {"rows": []}, receipts=[
                    receipt(source_ref="RC-A", receipt_id="RC-A",
                            batch_id="B1", qty=5,
                            signed_at="2026-10-31T00:00:00+00:00",
                            received_at="2026-11-01T00:00:00+00:00"),
                    receipt(source_ref="RC-B", receipt_id="RC-B",
                            batch_id="B1", qty=5,
                            signed_at="2026-11-05T00:00:00+00:00",
                            received_at=None)]),
        }
        for reason, full in cases.items():
            with self.subTest(reason=reason):
                with tempfile.TemporaryDirectory() as tmp:
                    published = publish(
                        tmp, full_result=full, position_result=pos,
                        inputs=[], pipeline_as_of=AS_OF)
                    manifest = published["manifest"]
                    self.assertTrue(manifest["output_summary"]["partial"])
                    self.assertIn(reason, manifest["output_summary"]
                                  ["business_conflict_reasons"])
                    state = read_publication(tmp, as_of=AS_OF,
                                             max_age_seconds=900)
                    self.assertEqual(state["status"], "partial")
                    self.assertTrue(state["readable"])
                    self.assertGreaterEqual(
                        state["business_conflict_rows"], 1)


class ReviewPublicationContractTests(unittest.TestCase):
    @unittest.skipUnless(importlib.util.find_spec("pyarrow"),
                         "requires pyarrow")
    def test_identity_and_payload_fields_survive_json_parquet_manifest(self):
        pos, full = StagePublicationTests._full()
        with tempfile.TemporaryDirectory() as tmp:
            publish(tmp, full_result=full, position_result=pos,
                    inputs=[], pipeline_as_of=AS_OF)
            latest = json.loads((Path(tmp) / "latest.json").read_text(
                encoding="utf-8"))
            run = Path(latest["run_dir"])
            manifest = json.loads(Path(latest["manifest"]).read_text(
                encoding="utf-8"))
            stage = json.loads((run / "full_supply_facts.json").read_text(
                encoding="utf-8"))
            fields = {"fact_identity", "physical_lineage_id",
                      "lineage_status", "payload_hash",
                      "payload_conflict", "payload_hashes",
                      "payload_candidates", "stage_measured_qty",
                      "evidence_only", "same_stage_reconciliation_status",
                      "inventory_freshness", "inventory_time_proven"}
            self.assertTrue(fields.issubset(stage[0]))
            from supply_chain_visibility.publication import _stage_from_parquet
            import pyarrow.parquet as pq
            parquet = [_stage_from_parquet(record) for record in
                       pq.read_table(run / "full_supply_facts.parquet")
                       .to_pylist()]

            def sort_key(row):
                return tuple(str(row.get(name) or "") for name in STAGE_KEY)

            self.assertEqual(sorted(parquet, key=sort_key),
                             sorted(stage, key=sort_key))
            summary = manifest["output_summary"]
            self.assertEqual(summary["stage_unique_key"], list(STAGE_KEY))
            self.assertIn("lineage_status_counts", summary["stage_summary"])
            self.assertEqual(summary["stage_summary"]["payload_conflict_rows"],
                             0)


if __name__ == "__main__":
    unittest.main()
