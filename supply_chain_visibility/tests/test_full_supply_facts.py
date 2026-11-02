# -*- coding: utf-8 -*-
"""Full supply facts: purpose strictness, stage dates, unknown, POD, waybills."""

import unittest

from supply_chain_visibility.full_supply_facts import (
    assess_freshness,
    build_full_supply_facts,
    collapse_waybills,
    filter_rows,
)

BASE = {"item_code": "SKU-1", "uom": "个", "warehouse": "WH-1",
        "purpose": "branch", "branch": "CENTRADE", "tt_sku": "S1"}


def position(**over):
    row = {
        "item_code": "SKU-1", "tt_sku": "S1", "warehouse": "WH-1",
        "purpose": "branch", "uom": "个", "branch": "CENTRADE",
        "dn_net_qty": 5.0, "po_completed_assumed_qty": 0.0,
        "open_po_qty": 4.0, "unresolved_qty": 0.0,
        "as_of": "2026-11-02T00:00:00+00:00",
    }
    row.update(over)
    return {"rows": [row]}


def layer(**over):
    row = dict(BASE)
    row.update(over)
    return row


def row_of(result, item="SKU-1"):
    return next(r for r in result["rows"] if r["item_code"] == item)


class PurposeTests(unittest.TestCase):
    def test_missing_purpose_is_unknown_not_branch(self):
        result = build_full_supply_facts({"rows": []}, inventory=[{
            "item_code": "SKU-1", "uom": "个", "warehouse": "WH-1",
            "qty": 5, "as_of": "2026-11-02T00:00:00+00:00"}])
        row = row_of(result)
        self.assertEqual(row["purpose"], "unknown")
        self.assertEqual(row["scope"], "unknown")
        self.assertIn("purpose_unknown", row["unknown_reasons"])
        self.assertEqual(row["next_node"], "manual_review_unknown")
        self.assertEqual(result["summary"]["unknown_purpose_rows"], 1)

    def test_explicit_unknown_and_invalid_stay_unknown(self):
        for purpose in ("unknown", "weird", ""):
            result = build_full_supply_facts({"rows": []}, inventory=[{
                **BASE, "purpose": purpose, "qty": 5,
                "as_of": "2026-11-02T00:00:00+00:00"}])
            row = row_of(result)
            self.assertEqual(row["purpose"], "unknown", purpose)
            self.assertIn("purpose_unknown", row["unknown_reasons"])

    def test_branch_and_fba_are_isolated(self):
        result = build_full_supply_facts({"rows": [
            {"item_code": "SKU-1", "uom": "个", "warehouse": "WH-1",
             "purpose": "branch", "branch": "CENTRADE"},
            {"item_code": "SKU-1", "uom": "个", "warehouse": "WH-1",
             "purpose": "fba", "branch": ""},
        ]})
        self.assertEqual(len(filter_rows(result["rows"], scope="in_house")), 1)
        self.assertEqual(len(filter_rows(result["rows"], scope="external_fba")), 1)
        self.assertEqual(filter_rows(result["rows"], scope="unknown"), [])
        self.assertEqual([r["purpose"] for r in filter_rows(
            result["rows"], purpose="fba")], ["fba"])


class StageDateTests(unittest.TestCase):
    def test_inventory_observation_and_future_arrival_both_kept(self):
        result = build_full_supply_facts(position(), inventory=[layer(
            qty=5, as_of="2026-11-02T00:00:00+00:00")], production=[layer(
                qty=10, evidence_status="proven",
                available_date="2026-11-10T00:00:00+00:00")])
        row = row_of(result)
        self.assertEqual(row["inventory_as_of"], "2026-11-02T00:00:00+00:00")
        self.assertEqual(row["available_date"], "2026-11-10T00:00:00+00:00")
        self.assertEqual(row["date_confidence"], "expected")
        self.assertNotIn("date_conflict", row["unknown_reasons"])
        stages = {frag["stage"] for frag in row["stage_quantities"]}
        self.assertIn("inventory", stages)
        self.assertIn("in_production", stages)

    def test_same_stage_batches_are_both_retained(self):
        result = build_full_supply_facts(position(), production=[
            layer(qty=3, evidence_status="proven",
                  available_date="2026-11-10T00:00:00+00:00"),
            layer(qty=7, evidence_status="proven",
                  available_date="2026-11-20T00:00:00+00:00")])
        row = row_of(result)
        self.assertEqual(row["in_production_qty"], "10")
        dates = sorted(frag["date"] for frag in row["stage_quantities"]
                       if frag["stage"] == "in_production")
        self.assertEqual(dates, ["2026-11-10T00:00:00+00:00",
                                 "2026-11-20T00:00:00+00:00"])
        self.assertEqual(row["available_date"], "2026-11-10T00:00:00+00:00")
        self.assertNotIn("date_conflict", row["unknown_reasons"])

    def test_equal_dates_dedupe_to_one_fragment(self):
        result = build_full_supply_facts(position(), production=[
            layer(qty=3, evidence_status="proven",
                  available_date="2026-11-10T00:00:00+00:00"),
            layer(qty=3, evidence_status="proven",
                  available_date="2026-11-10T00:00:00+00:00")])
        fragments = [frag for frag in row_of(result)["stage_quantities"]
                     if frag["stage"] == "in_production"]
        self.assertEqual(len(fragments), 1)

    def test_estimated_date_is_expected_not_actual(self):
        result = build_full_supply_facts(position(), production=[layer(
            qty=4, evidence_status="estimated",
            available_date="2026-11-10T00:00:00+00:00")])
        row = row_of(result)
        self.assertIsNone(row["in_production_qty"])
        self.assertEqual(row["in_production_estimated_qty"], "4")
        fragment = next(frag for frag in row["stage_quantities"]
                        if frag["stage"] == "in_production_estimated")
        self.assertEqual(fragment["date_kind"], "expected")
        self.assertEqual(fragment["date_confidence"], "expected")

    def test_signed_receipt_date_is_actual(self):
        result = build_full_supply_facts(position(), receipts=[layer(
            qty=5, signed_at="2026-11-05T00:00:00+00:00")])
        row = row_of(result)
        self.assertEqual(row["available_date_kind"], "actual")
        self.assertEqual(row["date_confidence"], "confirmed")


class DemandSupplyTests(unittest.TestCase):
    def test_so_balance_is_demand_not_production(self):
        result = build_full_supply_facts(
            position(), so_balances=[layer(so_open_qty=6)])
        row = row_of(result)
        self.assertEqual(row["so_open_qty"], "6")
        self.assertIsNone(row["in_production_qty"])

    def test_estimated_production_is_separate(self):
        result = build_full_supply_facts(position(), production=[
            layer(qty=3, evidence_status="proven"),
            layer(qty=2, evidence_status="estimated")])
        row = row_of(result)
        self.assertEqual(row["in_production_qty"], "3")
        self.assertEqual(row["in_production_estimated_qty"], "2")

    def test_known_plus_unknown_so_nulls_total(self):
        result = build_full_supply_facts(position(), so_balances=[
            layer(so_open_qty=5),
            layer(so_open_qty=None, source_status="unavailable")])
        row = row_of(result)
        self.assertIsNone(row["so_open_qty"])
        self.assertIn("so_open_unknown", row["unknown_reasons"])

    def test_unavailable_inventory_is_unknown_not_zero(self):
        result = build_full_supply_facts(position(), inventory=[layer(
            qty=None, source_status="unavailable")])
        row = row_of(result)
        self.assertIsNone(row["inventory_qty"])
        self.assertIn("inventory_source_unavailable", row["unknown_reasons"])

    def test_multiple_inventory_snapshots_are_not_summed(self):
        result = build_full_supply_facts(position(), inventory=[
            layer(qty=8, as_of="2026-11-01T00:00:00+00:00"),
            layer(qty=6, as_of="2026-11-02T00:00:00+00:00")])
        row = row_of(result)
        self.assertIsNone(row["inventory_qty"])
        self.assertIn("multiple_inventory_snapshots", row["unknown_reasons"])

    def test_independent_dn_row_is_preserved(self):
        result = build_full_supply_facts(position(dn_net_qty=7.0))
        self.assertEqual(row_of(result)["dn_net_qty"], 7.0)

    def test_approved_item_without_evidence_is_listed(self):
        result = build_full_supply_facts({"rows": []},
                                         approved_items=["SKU-EMPTY"])
        row = row_of(result, "SKU-EMPTY")
        self.assertEqual(row["coverage"], "approved_item_without_evidence")
        self.assertIn("no_observed_supply_or_demand", row["unknown_reasons"])

    def test_source_without_tt_sku_attaches_to_position_row(self):
        result = build_full_supply_facts(
            position(), inventory=[{"item_code": "SKU-1", "uom": "个",
                                    "warehouse": "WH-1", "purpose": "branch",
                                    "branch": "CENTRADE", "qty": 5,
                                    "as_of": "2026-11-02T00:00:00+00:00"}])
        self.assertEqual(len(result["rows"]), 1)
        self.assertEqual(row_of(result)["inventory_qty"], "5")


class ReceiptAndWaybillTests(unittest.TestCase):
    def test_pod_upload_is_not_receipt(self):
        result = build_full_supply_facts(position(), receipts=[layer(
            qty=5, pod_uploaded_at="2026-11-01T00:00:00+00:00")])
        row = row_of(result)
        self.assertIsNone(row["received_qty"])
        self.assertIn("receipt_pod_only", row["unknown_reasons"])

    def test_multi_waybill_does_not_copy_quantity(self):
        events = [
            {**BASE, "delivery_note": "DN-1", "qty": 10, "waybill": "W1"},
            {**BASE, "delivery_note": "DN-1", "qty": 10, "waybill": "W2"},
        ]
        collapsed = collapse_waybills(events)
        self.assertEqual(len(collapsed), 1)
        self.assertIsNone(collapsed[0]["qty"])
        result = build_full_supply_facts(position(), transit=events)
        self.assertIsNone(row_of(result)["in_transit_qty"])
        self.assertIn("multi_waybill_allocation_unknown",
                      row_of(result)["unknown_reasons"])

    def test_duplicate_waybill_same_qty_is_replay(self):
        events = [{**BASE, "delivery_note": "DN-1", "qty": 10, "waybill": "W1"},
                  {**BASE, "delivery_note": "DN-1", "qty": 10, "waybill": "W1"}]
        self.assertEqual(len(collapse_waybills(events)), 1)

    def test_duplicate_waybill_different_qty_is_unknown(self):
        events = [{**BASE, "delivery_note": "DN-1", "qty": 10, "waybill": "W1"},
                  {**BASE, "delivery_note": "DN-1", "qty": 12, "waybill": "W1"}]
        collapsed = collapse_waybills(events)
        self.assertIsNone(collapsed[0]["qty"])
        self.assertEqual(collapsed[0]["reason"],
                         "duplicate_waybill_quantity_conflict")


class TimelineFreshnessTests(unittest.TestCase):
    def test_timeline_marks_forecast_not_connected(self):
        result = build_full_supply_facts(position(), inventory=[layer(
            qty=8, as_of="2026-10-01T00:00:00+00:00")],
            as_of="2026-11-02T00:00:00+00:00")
        timeline = result["timeline"]
        self.assertFalse(timeline["forecast_connected"])
        self.assertIn("date_in_past", timeline["rows"][0]["alerts"])

    def test_freshness_flags_stale_and_unknown(self):
        result = build_full_supply_facts(position(), inventory=[layer(
            qty=8, as_of="2026-10-01T00:00:00+00:00")],
            so_balances=[layer(so_open_qty=2)],
            as_of="2026-11-02T00:00:00+00:00", max_age_seconds=86400)
        summary = result["freshness"]["summary"]
        self.assertEqual(summary["stale"], 1)
        self.assertGreaterEqual(summary["unknown"], 1)

    def test_invalid_timeline_as_of_does_not_crash(self):
        result = build_full_supply_facts(position(), as_of="not-a-time")
        self.assertIn("timeline", result)

    def test_scale_2000_items_has_no_cross_totals(self):
        rows = [{"item_code": "SKU-%04d" % i, "uom": "个",
                 "warehouse": "WH-1", "purpose": "branch",
                 "branch": "CENTRADE", "dn_net_qty": 1,
                 "po_completed_assumed_qty": 0, "open_po_qty": 0,
                 "unresolved_qty": 0} for i in range(2000)]
        result = build_full_supply_facts({"rows": rows})
        self.assertEqual(len(result["rows"]), 2000)
        self.assertIsNone(result["summary"]["global_qty_total"])


if __name__ == "__main__":
    unittest.main()
