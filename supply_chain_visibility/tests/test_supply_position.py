"""Consumer contract: PO completion must only close audited included DN rows."""
import copy
import hashlib
import importlib.util
import json
import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch

from supply_chain_visibility.supply_position import build_position, publish_position


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


if __name__ == "__main__":
    unittest.main()
