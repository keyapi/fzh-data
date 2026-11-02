# -*- coding: utf-8 -*-
"""Full supply facts: demand vs supply, unknown, POD, waybills, timeline."""

import unittest

from supply_chain_visibility.full_supply_facts import (
    assess_freshness,
    build_full_supply_facts,
    build_timeline,
    collapse_waybills,
    filter_rows,
)


def position(**over):
    row = {
        "item_code": "SKU-1", "tt_sku": "S1", "warehouse": "WH-1",
        "purpose": "branch", "uom": "个", "branch": "CENTRADE",
        "dn_net_qty": 5.0, "po_completed_assumed_qty": 0.0,
        "open_po_qty": 4.0, "unresolved_qty": 0.0, "as_of": "2026-11-02T00:00:00+00:00",
    }
    row.update(over)
    return {"rows": [row]}


def row_of(result, item="SKU-1"):
    return next(r for r in result["rows"] if r["item_code"] == item)


class DemandSupplyTests(unittest.TestCase):
    def test_so_balance_is_demand_not_production(self):
        result = build_full_supply_facts(
            position(), so_balances=[{
                "item_code": "SKU-1", "uom": "个", "warehouse": "WH-1",
                "branch": "CENTRADE", "so_open_qty": 6,
                "source_status": "known"}])
        row = row_of(result)
        self.assertEqual(row["so_open_qty"], "6")
        self.assertIsNone(row["in_production_qty"])

    def test_estimated_production_is_not_proven(self):
        result = build_full_supply_facts(position(), production=[
            {"item_code": "SKU-1", "uom": "个", "warehouse": "WH-1",
             "branch": "CENTRADE", "qty": 3, "evidence_status": "proven"},
            {"item_code": "SKU-1", "uom": "个", "warehouse": "WH-1",
             "branch": "CENTRADE", "qty": 2, "evidence_status": "estimated"}])
        row = row_of(result)
        self.assertEqual(row["in_production_qty"], "3")
        self.assertEqual(row["in_production_estimated_qty"], "2")

    def test_unavailable_inventory_is_unknown_not_zero(self):
        result = build_full_supply_facts(position(), inventory=[{
            "item_code": "SKU-1", "uom": "个", "warehouse": "WH-1",
            "branch": "CENTRADE", "qty": None, "source_status": "unavailable"}])
        row = row_of(result)
        self.assertIsNone(row["inventory_qty"])
        self.assertIn("inventory_source_unavailable", row["unknown_reasons"])

    def test_independent_dn_row_is_preserved(self):
        result = build_full_supply_facts(position(
            dn_net_qty=7.0, open_po_qty=0.0, po_completed_assumed_qty=0.0))
        row = row_of(result)
        self.assertEqual(row["dn_net_qty"], 7.0)

    def test_approved_item_without_evidence_is_listed(self):
        result = build_full_supply_facts({"rows": []},
                                         approved_items=["SKU-EMPTY"])
        row = row_of(result, "SKU-EMPTY")
        self.assertEqual(row["coverage"], "approved_item_without_evidence")
        self.assertIn("no_observed_supply_or_demand", row["unknown_reasons"])
        self.assertIsNone(row["inventory_qty"])


class ReceiptTests(unittest.TestCase):
    def test_pod_upload_is_not_receipt(self):
        result = build_full_supply_facts(position(), receipts=[{
            "item_code": "SKU-1", "uom": "个", "warehouse": "WH-1",
            "branch": "CENTRADE", "qty": 5,
            "pod_uploaded_at": "2026-11-01T00:00:00+00:00"}])
        row = row_of(result)
        self.assertIsNone(row["received_qty"])
        self.assertIn("receipt_pod_only", row["unknown_reasons"])

    def test_signed_receipt_is_proven(self):
        result = build_full_supply_facts(position(), receipts=[{
            "item_code": "SKU-1", "uom": "个", "warehouse": "WH-1",
            "branch": "CENTRADE", "qty": 5,
            "signed_at": "2026-11-01T00:00:00+00:00",
            "pod_uploaded_at": "2026-11-02T00:00:00+00:00"}])
        row = row_of(result)
        self.assertEqual(row["received_qty"], "5")
        self.assertEqual(row["available_date"], "2026-11-01T00:00:00+00:00")


class WaybillTests(unittest.TestCase):
    def test_multi_waybill_does_not_copy_quantity(self):
        events = [
            {"delivery_note": "DN-1", "item_code": "SKU-1", "uom": "个",
             "warehouse": "WH-1", "branch": "CENTRADE", "qty": 10,
             "waybill": "W1"},
            {"delivery_note": "DN-1", "item_code": "SKU-1", "uom": "个",
             "warehouse": "WH-1", "branch": "CENTRADE", "qty": 10,
             "waybill": "W2"},
        ]
        collapsed = collapse_waybills(events)
        self.assertEqual(len(collapsed), 1)
        self.assertIsNone(collapsed[0]["qty"])
        self.assertEqual(collapsed[0]["reason"],
                         "multi_waybill_allocation_unknown")
        result = build_full_supply_facts(position(), transit=events)
        row = row_of(result)
        self.assertIsNone(row["in_transit_qty"])
        self.assertIn("multi_waybill_allocation_unknown",
                      row["unknown_reasons"])


class StrictUnknownTests(unittest.TestCase):
    def test_known_plus_unknown_so_nulls_total(self):
        result = build_full_supply_facts(position(), so_balances=[
            {"item_code": "SKU-1", "uom": "个", "warehouse": "WH-1",
             "branch": "CENTRADE", "so_open_qty": 5, "source_status": "known"},
            {"item_code": "SKU-1", "uom": "个", "warehouse": "WH-1",
             "branch": "CENTRADE", "so_open_qty": None,
             "source_status": "unavailable"}])
        row = row_of(result)
        self.assertIsNone(row["so_open_qty"])
        self.assertIn("so_open_unknown", row["unknown_reasons"])

    def test_multiple_inventory_snapshots_are_not_summed(self):
        result = build_full_supply_facts(position(), inventory=[
            {"item_code": "SKU-1", "uom": "个", "warehouse": "WH-1",
             "branch": "CENTRADE", "qty": 8,
             "as_of": "2026-11-01T00:00:00+00:00"},
            {"item_code": "SKU-1", "uom": "个", "warehouse": "WH-1",
             "branch": "CENTRADE", "qty": 6,
             "as_of": "2026-11-02T00:00:00+00:00"}])
        row = row_of(result)
        self.assertIsNone(row["inventory_qty"])
        self.assertIn("multiple_inventory_snapshots", row["unknown_reasons"])

    def test_conflicting_dates_are_marked_unknown(self):
        result = build_full_supply_facts(position(), production=[
            {"item_code": "SKU-1", "uom": "个", "warehouse": "WH-1",
             "branch": "CENTRADE", "qty": 1, "evidence_status": "proven",
             "available_date": "2026-11-01T00:00:00+00:00"},
            {"item_code": "SKU-1", "uom": "个", "warehouse": "WH-1",
             "branch": "CENTRADE", "qty": 1, "evidence_status": "proven",
             "available_date": "2026-11-03T00:00:00+00:00"}])
        row = row_of(result)
        self.assertIsNone(row["available_date"])
        self.assertEqual(row["date_confidence"], "unknown")
        self.assertIn("date_conflict", row["unknown_reasons"])

    def test_duplicate_waybill_same_qty_is_replay(self):
        events = [
            {"delivery_note": "DN-1", "item_code": "SKU-1", "uom": "个",
             "warehouse": "WH-1", "branch": "CENTRADE", "qty": 10,
             "waybill": "W1"},
            {"delivery_note": "DN-1", "item_code": "SKU-1", "uom": "个",
             "warehouse": "WH-1", "branch": "CENTRADE", "qty": 10,
             "waybill": "W1"}]
        collapsed = collapse_waybills(events)
        self.assertEqual(len(collapsed), 1)
        self.assertEqual(collapsed[0]["qty"], 10)

    def test_duplicate_waybill_different_qty_is_unknown(self):
        events = [
            {"delivery_note": "DN-1", "item_code": "SKU-1", "uom": "个",
             "warehouse": "WH-1", "branch": "CENTRADE", "qty": 10,
             "waybill": "W1"},
            {"delivery_note": "DN-1", "item_code": "SKU-1", "uom": "个",
             "warehouse": "WH-1", "branch": "CENTRADE", "qty": 12,
             "waybill": "W1"}]
        collapsed = collapse_waybills(events)
        self.assertIsNone(collapsed[0]["qty"])
        self.assertEqual(collapsed[0]["reason"],
                         "duplicate_waybill_quantity_conflict")

    def test_invalid_timeline_as_of_does_not_crash(self):
        result = build_full_supply_facts(position(), as_of="not-a-time",
                                         max_age_seconds=None)
        self.assertIn("timeline", result)


class TimelineAndFilterTests(unittest.TestCase):
    def test_timeline_marks_forecast_not_connected_and_past_date(self):
        result = build_full_supply_facts(position(), inventory=[{
            "item_code": "SKU-1", "uom": "个", "warehouse": "WH-1",
            "branch": "CENTRADE", "qty": 8,
            "as_of": "2026-10-01T00:00:00+00:00"}])
        timeline = result["timeline"]
        self.assertFalse(timeline["forecast_connected"])
        event = timeline["rows"][0]
        self.assertIn("date_in_past", event["alerts"])
        self.assertFalse(event["forecast_connected"])

    def test_filter_by_purpose_and_branch(self):
        result = build_full_supply_facts({
            "rows": [
                {"item_code": "A", "uom": "个", "warehouse": "WH-1",
                 "purpose": "branch", "branch": "CENTRADE"},
                {"item_code": "B", "uom": "个", "warehouse": "WH-1",
                 "purpose": "fba", "branch": ""},
            ]})
        self.assertEqual([r["item_code"] for r in filter_rows(
            result["rows"], purpose="branch")], ["A"])
        self.assertEqual([r["item_code"] for r in filter_rows(
            result["rows"], purpose="fba")], ["B"])
        self.assertEqual([r["item_code"] for r in filter_rows(
            result["rows"], scope="external_fba")], ["B"])


class FreshnessAndScaleTests(unittest.TestCase):
    def test_freshness_flags_stale_unknown_and_future(self):
        result = build_full_supply_facts(position(), inventory=[{
            "item_code": "SKU-1", "uom": "个", "warehouse": "WH-1",
            "branch": "CENTRADE", "qty": 8,
            "as_of": "2026-10-01T00:00:00+00:00"}],
            as_of="2026-11-02T00:00:00+00:00", max_age_seconds=86400)
        summary = result["freshness"]["summary"]
        self.assertEqual(summary["stale"], 1)
        row = result["freshness"]["rows"][0]
        self.assertTrue(any(p["status"] == "stale" for p in row["problems"]))

    def test_unknown_source_time_is_not_fresh(self):
        result = build_full_supply_facts(position(), inventory=[{
            "item_code": "SKU-1", "uom": "个", "warehouse": "WH-1",
            "branch": "CENTRADE", "qty": 8, "as_of": None}],
            as_of="2026-11-02T00:00:00+00:00", max_age_seconds=86400)
        self.assertGreaterEqual(result["freshness"]["summary"]["unknown"], 1)

    def test_scale_2000_items_has_no_cross_totals(self):
        rows = [{"item_code": "SKU-%04d" % i, "uom": "个",
                 "warehouse": "WH-1", "purpose": "branch",
                 "branch": "CENTRADE", "dn_net_qty": 1,
                 "po_completed_assumed_qty": 0, "open_po_qty": 0,
                 "unresolved_qty": 0} for i in range(2000)]
        result = build_full_supply_facts({"rows": rows})
        self.assertEqual(len(result["rows"]), 2000)
        self.assertIsNone(result["summary"]["global_qty_total"])
        self.assertFalse(result["summary"]["forecast_connected"])

    def test_invalid_freshness_arguments_are_rejected(self):
        with self.assertRaises(ValueError):
            assess_freshness([], as_of="2026-11-02", max_age_seconds=60)
        with self.assertRaises(ValueError):
            assess_freshness([], as_of="2026-11-02T00:00:00+00:00",
                             max_age_seconds=0)


if __name__ == "__main__":
    unittest.main()
