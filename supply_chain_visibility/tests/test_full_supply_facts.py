# -*- coding: utf-8 -*-
"""Full supply facts: purpose strictness, stage dates, unknown, POD, waybills."""

import itertools
import unittest

from supply_chain_visibility.full_supply_facts import (
    assess_freshness,
    build_full_supply_facts,
    collapse_waybills,
    filter_rows,
)

BASE = {"item_code": "SKU-1", "uom": "个", "warehouse": "WH-1",
        "purpose": "branch", "branch": "CENTRADE", "tt_sku": "S1"}
_COUNTER = itertools.count(1)


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
    row.setdefault("source_ref", "SRC-%d" % next(_COUNTER))
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

    def test_different_source_identities_keep_both_fragments(self):
        result = build_full_supply_facts(position(), production=[
            layer(qty=3, evidence_status="proven",
                  available_date="2026-11-10T00:00:00+00:00", source_ref="WO-1"),
            layer(qty=3, evidence_status="proven",
                  available_date="2026-11-10T00:00:00+00:00", source_ref="WO-2")])
        row = row_of(result)
        self.assertEqual(row["in_production_qty"], "6")
        fragments = [frag for frag in row["stage_quantities"]
                     if frag["stage"] == "in_production"]
        self.assertEqual(len(fragments), 2)

    def test_same_source_replay_is_counted_once(self):
        result = build_full_supply_facts(position(), production=[
            layer(qty=3, evidence_status="proven", source_ref="WO-1"),
            layer(qty=3, evidence_status="proven", source_ref="WO-1")])
        row = row_of(result)
        self.assertEqual(row["in_production_qty"], "3")
        fragments = [frag for frag in row["stage_quantities"]
                     if frag["stage"] == "in_production"]
        self.assertEqual(len(fragments), 1)
        self.assertTrue(fragments[0]["replay"])

    def test_same_source_different_payload_is_conflict(self):
        result = build_full_supply_facts(position(), production=[
            layer(qty=3, evidence_status="proven", source_ref="WO-1"),
            layer(qty=4, evidence_status="proven", source_ref="WO-1")])
        row = row_of(result)
        self.assertIsNone(row["in_production_qty"])
        self.assertIn("source_payload_conflict", row["unknown_reasons"])

    def test_missing_source_identity_is_not_summed_as_known(self):
        result = build_full_supply_facts(position(), production=[
            {"item_code": "SKU-1", "uom": "个", "warehouse": "WH-1",
             "purpose": "branch", "branch": "CENTRADE", "tt_sku": "S1",
             "qty": 5, "evidence_status": "proven"}])
        row = row_of(result)
        self.assertIsNone(row["in_production_qty"])
        self.assertIn("source_identity_missing", row["unknown_reasons"])

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
        self.assertEqual(row["receipt_basis"], "signed_assumed")


class DemandSupplyTests(unittest.TestCase):
    def test_position_unresolved_reasons_and_source_time_survive(self):
        p = position(unresolved_qty=5, reasons=["creation_lines_not_exported"])
        p["report"] = {"source_versions": {"observed_at": "2026-10-30T00:00:00+00:00"}}
        result = build_full_supply_facts(p, as_of="2026-11-02T00:00:00+00:00", max_age_seconds=900)
        row = row_of(result)
        self.assertIn("creation_lines_not_exported", row["unknown_reasons"])
        self.assertEqual(row["source_status"]["dn_po"], "partial")
        self.assertEqual(row["unresolved_qty"], "5")
        self.assertEqual(row["next_node"], "manual_review_unknown")
        self.assertFalse(result["freshness"]["rows"][0]["fresh"])

    def test_explicit_conflicting_sku_is_not_attached(self):
        result = build_full_supply_facts(position(), inventory=[{
            "item_code": "SKU-1", "uom": "个", "warehouse": "WH-1",
            "purpose": "branch", "branch": "CENTRADE", "tt_sku": "OTHER", "qty": 8}])
        self.assertEqual(len(result["rows"]), 2)
        base = next(r for r in result["rows"] if r["tt_sku"] == "S1")
        self.assertIsNone(base["inventory_qty"])

    def test_filled_branch_key_is_not_reused_for_other_branch(self):
        result = build_full_supply_facts(
            position(branch=""),
            production=[{"item_code": "SKU-1", "uom": "个",
                         "warehouse": "WH-1", "purpose": "branch",
                         "branch": "CENTRADE", "qty": 3,
                         "evidence_status": "proven", "source_ref": "WO-1"}],
            inventory=[{"item_code": "SKU-1", "uom": "个",
                        "warehouse": "WH-1", "purpose": "branch",
                        "branch": "DANEEY", "qty": 8,
                        "source_ref": "ST-1"}])
        self.assertEqual(len(result["rows"]), 3)
        centrade = next(r for r in result["rows"] if r["branch"] == "CENTRADE")
        daney = next(r for r in result["rows"] if r["branch"] == "DANEEY")
        self.assertIsNone(centrade["inventory_qty"])
        self.assertEqual(centrade["in_production_qty"], "3")
        self.assertIsNone(daney["in_production_qty"])
        self.assertEqual(daney["inventory_qty"], "8")
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
        self.assertEqual(row_of(result)["dn_net_qty"], "7")

    def test_approved_item_without_evidence_is_listed(self):
        result = build_full_supply_facts({"rows": []},
                                         approved_items=["SKU-EMPTY"])
        row = row_of(result, "SKU-EMPTY")
        self.assertEqual(row["coverage"], "approved_item_without_evidence")
        self.assertIn("no_observed_supply_or_demand", row["unknown_reasons"])

    def test_non_authoritative_source_does_not_fill_blank_branch(self):
        result = build_full_supply_facts(
            position(branch=""),
            inventory=[layer(qty=5, as_of="2026-11-02T00:00:00+00:00")])
        self.assertEqual(len(result["rows"]), 2)
        blank = next(r for r in result["rows"] if r["branch"] == "")
        explicit = next(r for r in result["rows"] if r["branch"] == "CENTRADE")
        self.assertEqual(blank["dn_net_qty"], "5")
        self.assertIsNone(blank["inventory_qty"])
        self.assertIsNone(explicit["dn_net_qty"])
        self.assertEqual(explicit["inventory_qty"], "5")

    def test_source_without_tt_sku_does_not_attach_to_position_row(self):
        result = build_full_supply_facts(
            position(), inventory=[{"item_code": "SKU-1", "uom": "个",
                                    "warehouse": "WH-1", "purpose": "branch",
                                    "branch": "CENTRADE", "qty": 5,
                                    "source_ref": "ST-1",
                                    "as_of": "2026-11-02T00:00:00+00:00"}])
        self.assertEqual(len(result["rows"]), 2)
        position_row = next(r for r in result["rows"] if r["tt_sku"] == "S1")
        self.assertIsNone(position_row["inventory_qty"])
        unassigned = next(r for r in result["rows"]
                          if r["tt_sku"] is None and r["inventory_qty"] == "5")
        self.assertIn("tt_sku_unknown", unassigned["unknown_reasons"])


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
        self.assertIsNone(result["summary"]["cross_layer_total"])


class V2ContractTests(unittest.TestCase):
    def test_duplicate_position_target_key_is_rejected(self):
        row = {"item_code": "SKU-1", "uom": "个", "warehouse": "WH-1",
               "purpose": "branch", "tt_sku": "S1", "branch": "CENTRADE",
               "dn_net_qty": 5, "po_completed_assumed_qty": 0,
               "open_po_qty": 0, "unresolved_qty": 0}
        with self.assertRaises(ValueError) as ctx:
            build_full_supply_facts({"rows": [row, dict(row, dn_net_qty=6)]})
        self.assertIn("duplicate_target_key", str(ctx.exception))
        replay = build_full_supply_facts({"rows": [row, dict(row)]})
        self.assertEqual(len(replay["rows"]), 1)

    def test_uom_purpose_and_tt_sku_are_separate_keys(self):
        rows = [
            {"item_code": "SKU-1", "uom": "个", "warehouse": "WH-1",
             "purpose": "branch", "tt_sku": "S1", "branch": "B1"},
            {"item_code": "SKU-1", "uom": "套", "warehouse": "WH-1",
             "purpose": "branch", "tt_sku": "S1", "branch": "B1"},
            {"item_code": "SKU-1", "uom": "个", "warehouse": "WH-1",
             "purpose": "fba", "tt_sku": "S1", "branch": "B1"},
            {"item_code": "SKU-1", "uom": "个", "warehouse": "WH-1",
             "purpose": "branch", "tt_sku": "S2", "branch": "B1"},
        ]
        result = build_full_supply_facts({"rows": rows})
        self.assertEqual(len(result["rows"]), 4)
        self.assertEqual(result["summary"]["duplicate_keys"], 0)

    def test_missing_audit_and_status_still_emit_supply_facts(self):
        result = build_full_supply_facts(
            {"rows": []},
            so_balances=[layer(so_open_qty=6)],
            inventory=[layer(qty=8, as_of="2026-11-02T00:00:00+00:00")])
        row = row_of(result)
        self.assertEqual(row["so_open_qty"], "6")
        self.assertEqual(row["inventory_qty"], "8")
        self.assertIsNone(row["po_completed_assumed_qty"])

    def test_layers_are_never_summed_and_overlap_is_flagged(self):
        result = build_full_supply_facts(
            position(po_completed_assumed_qty=5.0, dn_net_qty=5.0),
            inventory=[layer(qty=8, as_of="2026-11-02T00:00:00+00:00")])
        row = row_of(result)
        self.assertEqual(row["po_completed_assumed_qty"], "5")
        self.assertEqual(row["inventory_qty"], "8")
        self.assertIn("possible_po_inventory_overlap", row["unknown_reasons"])
        self.assertIsNone(result["summary"]["global_qty_total"])
        self.assertIsNone(result["summary"]["cross_layer_total"])

    def test_abc_explicit_branch_enriches_blank_position_branch(self):
        abc_row = {**BASE, "inventory_qty": "0",
                   "inventory_observed_qty": "0",
                   "inventory_current_available_qty": "0",
                   "inventory_as_of": "2026-11-02T00:00:00+00:00",
                   "inventory_as_of_raw": "2026-11-02T00:00:00+00:00",
                   "inventory_time_status": "known",
                   "inventory_freshness": "fresh",
                   "attribution_status": "attributed",
                   "abc_identity_source": "B", "source_status": "known",
                   "reasons": [], "coverage": "abc_inventory"}
        result = build_full_supply_facts(position(branch=""),
                                         abc_inventory=[abc_row])
        self.assertEqual(len(result["rows"]), 1)
        row = row_of(result)
        self.assertEqual(row["branch"], "CENTRADE")
        self.assertEqual(row["inventory_qty"], "0")

    def test_conflicting_abc_branch_claims_do_not_enrich_blank_row(self):
        def abc_row(branch, qty):
            return {**BASE, "branch": branch, "inventory_qty": qty,
                    "inventory_observed_qty": qty,
                    "inventory_current_available_qty": None,
                    "inventory_as_of": "2026-11-02T00:00:00+00:00",
                    "inventory_as_of_raw": "2026-11-02T00:00:00+00:00",
                    "inventory_time_status": "known",
                    "inventory_freshness": "fresh",
                    "attribution_status": "attributed",
                    "abc_identity_source": "B", "source_status": "known",
                    "reasons": [], "coverage": "abc_inventory"}
        result = build_full_supply_facts(
            position(branch=""), abc_inventory=[
                abc_row("B1", "1"), abc_row("B2", "2")])
        self.assertEqual(len(result["rows"]), 3)
        blank = next(row for row in result["rows"] if row["branch"] == "")
        self.assertIn("branch_unknown", blank["unknown_reasons"])
        self.assertIn("target_key_ambiguous", blank["unknown_reasons"])
        self.assertEqual(
            sorted(row["branch"] for row in result["rows"]
                   if row["inventory_qty"] is not None), ["B1", "B2"])

    def test_abc_inventory_attaches_only_to_exact_key(self):
        result = build_full_supply_facts(
            position(), abc_inventory=[{
                **BASE, "inventory_qty": "0",
                "inventory_observed_qty": "0",
                "inventory_current_available_qty": "0",
                "inventory_as_of": "2026-11-02T00:00:00+00:00",
                "inventory_as_of_raw": "2026-11-02T00:00:00+00:00",
                "inventory_time_status": "known",
                "inventory_freshness": "fresh",
                "attribution_status": "attributed",
                "abc_identity_source": "B", "source_status": "known",
                "reasons": [], "coverage": "abc_inventory"}])
        self.assertEqual(len(result["rows"]), 1)
        self.assertEqual(row_of(result)["inventory_qty"], "0")
        self.assertTrue(row_of(result)["inventory_current_available"])
        other = build_full_supply_facts(
            position(), abc_inventory=[{
                **BASE, "tt_sku": "OTHER", "inventory_qty": "0",
                "inventory_observed_qty": "0",
                "inventory_current_available_qty": None,
                "inventory_as_of": None,
                "inventory_as_of_raw": "2026-10-28",
                "inventory_time_status": "date_only",
                "inventory_freshness": "stale",
                "attribution_status": "attributed",
                "abc_identity_source": "B", "source_status": "known",
                "reasons": [], "coverage": "abc_inventory"}])
        self.assertEqual(len(other["rows"]), 2)
        base_row = next(row for row in other["rows"] if row["tt_sku"] == "S1")
        self.assertIsNone(base_row["inventory_qty"])

    def test_cg_pool_rows_are_not_double_counted(self):
        first = {**BASE, "branch": "B1", "inventory_qty": None,
                 "inventory_observed_qty": None,
                 "inventory_current_available_qty": None,
                 "inventory_as_of": None, "inventory_as_of_raw": "2026-10-28",
                 "inventory_time_status": "date_only",
                 "inventory_freshness": "stale",
                 "attribution_status": "cg_pool_ambiguous",
                 "abc_identity_source": "B", "source_status": "known",
                 "reasons": ["cg_pool_allocation_unknown"],
                 "coverage": "abc_cg_pool_identity"}
        second = {**first, "branch": "B2"}
        pooled = {**first, "branch": "", "tt_sku": None,
                  "inventory_observed_qty": "9",
                  "reasons": ["cg_pool_allocation_unknown",
                              "cg_pool_shared_by_multiple_attributions"],
                  "coverage": "abc_cg_pool_unattributed"}
        result = build_full_supply_facts({"rows": []},
                                         abc_inventory=[first, second, pooled])
        observed = [row for row in result["rows"]
                    if row["inventory_observed_qty"] is not None]
        self.assertEqual(len(observed), 1)
        self.assertEqual(observed[0]["inventory_observed_qty"], "9")
        self.assertTrue(all(row["inventory_qty"] is None
                            for row in result["rows"]))


class IdentityAndReplayTests(unittest.TestCase):
    def _three(self, layer_name):
        common = {"item_code": "I", "uom": "个", "warehouse": "WH",
                  "purpose": "branch", "tt_sku": "S1"}
        if layer_name == "so":
            return [
                {**common, "branch": "", "so_open_qty": 10,
                 "source_ref": "SO-0"},
                {**common, "branch": "A", "so_open_qty": 2,
                 "source_ref": "SO-A"},
                {**common, "branch": "B", "so_open_qty": 3,
                 "source_ref": "SO-B"}]
        if layer_name == "inventory":
            return [
                {**common, "branch": "", "qty": 10, "source_ref": "ST-0",
                 "as_of": "2026-11-02T00:00:00+00:00"},
                {**common, "branch": "A", "qty": 2, "source_ref": "ST-A",
                 "as_of": "2026-11-02T00:00:00+00:00"},
                {**common, "branch": "B", "qty": 3, "source_ref": "ST-B",
                 "as_of": "2026-11-02T00:00:00+00:00"}]
        if layer_name == "receipt":
            return [
                {**common, "branch": "", "qty": 10, "source_ref": "RC-0",
                 "signed_at": "2026-11-02T00:00:00+00:00"},
                {**common, "branch": "A", "qty": 2, "source_ref": "RC-A",
                 "signed_at": "2026-11-02T00:00:00+00:00"},
                {**common, "branch": "B", "qty": 3, "source_ref": "RC-B",
                 "signed_at": "2026-11-02T00:00:00+00:00"}]
        return [
            {**common, "branch": "", "qty": 10, "source_ref": "WO-0",
             "evidence_status": "proven"},
            {**common, "branch": "A", "qty": 2, "source_ref": "WO-A",
             "evidence_status": "proven"},
            {**common, "branch": "B", "qty": 3, "source_ref": "WO-B",
             "evidence_status": "proven"}]

    def test_missing_identity_stays_unassigned_in_any_order(self):
        import itertools
        for layer_name in ("so", "inventory", "receipt", "production"):
            for order in itertools.permutations(self._three(layer_name)):
                kwargs = {("so_balances" if layer_name == "so" else layer_name):
                          list(order)}
                if layer_name == "receipt":
                    kwargs = {"receipts": list(order)}
                result = build_full_supply_facts({"rows": []}, **kwargs)
                rows = {row["branch"]: row for row in result["rows"]}
                self.assertEqual(set(rows), {"", "A", "B"}, layer_name)
                field = {"so": "so_open_qty", "inventory": "inventory_qty",
                         "receipt": "received_qty",
                         "production": "in_production_qty"}[layer_name]
                self.assertEqual(rows[""][field], "10", layer_name)
                self.assertEqual(rows["A"][field], "2", layer_name)
                self.assertEqual(rows["B"][field], "3", layer_name)

    def test_authoritative_abc_identity_is_order_independent(self):
        pos = position(branch="")
        abc_rows = [
            {**BASE, "branch": "A", "inventory_qty": "2",
             "inventory_observed_qty": "2",
             "inventory_current_available_qty": None,
             "inventory_as_of": "2026-11-02T00:00:00+00:00",
             "inventory_as_of_raw": "2026-11-02T00:00:00+00:00",
             "inventory_time_status": "known", "inventory_time_proven": True,
             "inventory_freshness": "fresh",
             "attribution_status": "attributed", "abc_identity_source": "B",
             "source_status": "known", "reasons": [],
             "coverage": "abc_inventory"},
            {**BASE, "branch": "B", "inventory_qty": "3",
             "inventory_observed_qty": "3",
             "inventory_current_available_qty": None,
             "inventory_as_of": "2026-11-02T00:00:00+00:00",
             "inventory_as_of_raw": "2026-11-02T00:00:00+00:00",
             "inventory_time_status": "known", "inventory_time_proven": True,
             "inventory_freshness": "fresh",
             "attribution_status": "attributed", "abc_identity_source": "B",
             "source_status": "known", "reasons": [],
             "coverage": "abc_inventory"}]
        outputs = []
        for rows in (abc_rows, list(reversed(abc_rows))):
            result = build_full_supply_facts(pos, abc_inventory=rows)
            outputs.append(sorted(
                (row["branch"], row["inventory_qty"]) for row in result["rows"]))
        self.assertEqual(outputs[0], outputs[1])
        self.assertEqual(outputs[0], [("", None), ("A", "2"), ("B", "3")])

    def test_source_identity_is_traceable(self):
        result = build_full_supply_facts(position(), production=[
            layer(qty=5, evidence_status="proven", source_ref="WO-1")])
        row = row_of(result)
        identities = [source.get("source_identity")
                      for source in row["sources"]
                      if source.get("layer") == "production"]
        self.assertTrue(any(identity.get("source_ref") == "WO-1"
                            and identity.get("item_code") == "SKU-1"
                            for identity in identities))
        fragments = [fragment for fragment in row["stage_quantities"]
                     if fragment["stage"] == "in_production"]
        self.assertEqual(fragments[0]["source_identity"]["source_ref"], "WO-1")
        self.assertEqual(fragments[0]["source_identity"]["item_code"], "SKU-1")

    def test_conservative_status_does_not_let_known_overwrite_unavailable(self):
        result = build_full_supply_facts(position(), so_balances=[
            layer(so_open_qty=None, source_status="unavailable",
                  source_ref="SO-1"),
            layer(so_open_qty=5, source_status="known", source_ref="SO-2")])
        row = row_of(result)
        self.assertEqual(row["source_status"]["so_demand"], "unavailable")
        self.assertIsNone(row["so_open_qty"])

    def test_layer_replay_and_conflict_matrix(self):
        cases = {
            "so": (
                [{"item_code": "I", "uom": "个", "warehouse": "WH",
                  "purpose": "branch", "branch": "A", "tt_sku": "S1",
                  "so_open_qty": 5, "source_ref": "SRC-1"}],
                "so_balances", "so_open_qty"),
            "inventory": (
                [{"item_code": "I", "uom": "个", "warehouse": "WH",
                  "purpose": "branch", "branch": "A", "tt_sku": "S1",
                  "qty": 5, "source_ref": "ST-1",
                  "as_of": "2026-11-02T00:00:00+00:00"}],
                "inventory", "inventory_qty"),
            "receipt": (
                [{"item_code": "I", "uom": "个", "warehouse": "WH",
                  "purpose": "branch", "branch": "A", "tt_sku": "S1",
                  "qty": 5, "receipt_id": "RC-1",
                  "signed_at": "2026-11-02T00:00:00+00:00"}],
                "receipts", "received_qty"),
        }
        for layer, (records, keyword, field) in cases.items():
            with self.subTest(layer=layer):
                replayed = build_full_supply_facts(
                    {"rows": []}, **{keyword: records + records})
                row = replayed["rows"][0]
                self.assertEqual(row[field], "5", layer)
                conflicted = build_full_supply_facts(
                    {"rows": []},
                    **{keyword: [records[0], dict(records[0], **{
                        "so_open_qty" if layer == "so" else "qty": 6})]})
                row = conflicted["rows"][0]
                self.assertIsNone(row[field], layer)
                self.assertIn("source_payload_conflict",
                              row["unknown_reasons"], layer)

    def test_logistics_keeps_same_waybill_with_different_warehouse(self):
        events = [
            {**BASE, "delivery_note": "DN-1", "waybill": "W1", "qty": 5,
             "warehouse": "WH-A"},
            {**BASE, "delivery_note": "DN-1", "waybill": "W1", "qty": 5,
             "warehouse": "WH-B"}]
        out = collapse_waybills(events)
        self.assertEqual(len(out), 2)
        self.assertEqual(sorted(row["warehouse"] for row in out),
                         ["WH-A", "WH-B"])
        self.assertTrue(all(row["qty"] == 5 for row in out))

    def test_logistics_keeps_same_waybill_with_different_branch(self):
        events = [
            {**BASE, "delivery_note": "DN-1", "waybill": "W1", "qty": 5,
             "branch": "A"},
            {**BASE, "delivery_note": "DN-1", "waybill": "W1", "qty": 5,
             "branch": "B"}]
        out = collapse_waybills(events)
        self.assertEqual(len(out), 2)
        self.assertEqual(sorted(row["branch"] for row in out), ["A", "B"])

    def test_logistics_multi_waybill_is_unknown_and_order_independent(self):
        events = [
            {**BASE, "delivery_note": "DN-1", "waybill": "W1", "qty": 5},
            {**BASE, "delivery_note": "DN-1", "waybill": "W2", "qty": 5}]
        first = collapse_waybills(events)
        second = collapse_waybills(list(reversed(events)))
        self.assertEqual(first, second)
        self.assertEqual(len(first), 1)
        self.assertIsNone(first[0]["qty"])
        self.assertEqual(first[0]["reason"],
                         "multi_waybill_allocation_unknown")

    def test_logistics_replay_and_conflict(self):
        replay = [
            {**BASE, "delivery_note": "DN-1", "waybill": "W1", "qty": 5},
            {**BASE, "delivery_note": "DN-1", "waybill": "W1", "qty": 5}]
        self.assertEqual(len(collapse_waybills(replay)), 1)
        conflict = [
            {**BASE, "delivery_note": "DN-1", "waybill": "W1", "qty": 5},
            {**BASE, "delivery_note": "DN-1", "waybill": "W1", "qty": 6}]
        out = collapse_waybills(conflict)
        self.assertEqual(len(out), 1)
        self.assertIsNone(out[0]["qty"])
        self.assertEqual(out[0]["reason"],
                         "duplicate_waybill_quantity_conflict")

    def test_logistics_same_waybill_two_dn_lines_is_kept(self):
        events = [
            {**BASE, "delivery_note": "DN-1", "delivery_note_item": "L1",
             "waybill": "W1", "qty": 5, "warehouse": "WH-A"},
            {**BASE, "delivery_note": "DN-1", "delivery_note_item": "L2",
             "waybill": "W1", "qty": 5, "warehouse": "WH-B"}]
        out = collapse_waybills(events)
        self.assertEqual(len(out), 2)

    def test_logistics_unallocated_waybill_over_two_warehouses_is_unknown(self):
        events = [
            {**BASE, "delivery_note": "DN-1", "waybill": "W1", "qty": 5,
             "warehouse": ""},
            {**BASE, "delivery_note": "DN-1", "waybill": "W1", "qty": 5,
             "warehouse": "WH-A"},
            {**BASE, "delivery_note": "DN-1", "waybill": "W1", "qty": 5,
             "warehouse": "WH-B"}]
        out = collapse_waybills(events)
        ambiguous = [row for row in out
                     if row.get("reason") == "multi_assignment_allocation_unknown"]
        self.assertEqual(len(ambiguous), 1)
        self.assertIsNone(ambiguous[0]["qty"])
        self.assertEqual(len(ambiguous[0]["candidates"]), 2)


if __name__ == "__main__":
    unittest.main()
