# -*- coding: utf-8 -*-
"""独立复审 F1–F4 回归（supply-review-6614403）。

F1 期初库存绕过排除 gate
F2 阶段转 tranche 丢失身份/仓库证明
F3 跨阶段同批只计一次 + 重复输入失败关闭 + 校验先于写产物
F4 到仓待上架已有 confirmed 可售日仍被排除
"""

from __future__ import annotations

import tempfile
import unittest
from datetime import datetime, timezone
from decimal import Decimal
from pathlib import Path
from unittest import mock

import pandas as pd

from supply_chain_visibility.supply_row import SupplyRow
from supply_netting.engine import build_buckets, net_target
from supply_netting.facts import (
    DuplicateBalanceError, StageBalance, build_availability_schedule,
    tranches_to_supply_rows, validate_stage_balances,
)

UOM = "个"
AS_OF = datetime(2026, 10, 27, tzinfo=timezone.utc)
BUCKETS = build_buckets(AS_OF, protect_days=3, weeks=2)
SELLABLE = "2026-10-28T00:00:00+00:00"


def snapshot(qty=0, **changes):
    values = dict(
        sku="S", warehouse="W", stage="on_hand", source_layer="inventory_snapshot",
        qty=Decimal(str(qty)) if qty is not None else None,
        qty_status="known" if qty is not None else "unknown",
        uom=UOM, uom_proven=True, event_date="2026-10-27", available_date=None,
        date_confidence="unknown", timezone_status="unverified",
        identity_confidence="proven", scope="in_house", warehouse_confidence="confirmed",
        role="finished", b_min_eligible=False, b_max_eligible=True,
        source_key=f"stock:{qty}", source_complete=True,
    )
    values.update(changes)
    return SupplyRow(**values)


def tranche_row(qty=10, *, stage="in_production", batch=None, proven=False, **changes):
    values = dict(
        sku="S", warehouse="W", stage=stage,
        source_layer="work_order" if stage in ("in_production", "finished_waiting_shipment") else "in_transit",
        qty=Decimal(str(qty)), qty_status="known", uom=UOM, uom_proven=True,
        event_date=None, available_date=SELLABLE, date_confidence="confirmed",
        timezone_status="verified", identity_confidence="proven",
        source_as_of=SELLABLE, scope="in_house", warehouse_confidence="confirmed",
        role="finished", b_min_eligible=False, b_max_eligible=True,
        source_key=f"tranche:{stage}:{qty}:{batch}", source_complete=True,
        batch_key=batch, batch_proven=proven,
    )
    values.update(changes)
    return SupplyRow(**values)


def stage(qty=10, *, stage="in_production", **changes):
    values = dict(
        balance_id="BAL-1", order_key="SO-1", sku="S", warehouse="W", uom=UOM,
        stage=stage, qty=Decimal(str(qty)), order_qty=Decimal(str(qty)),
        allocation_status="free", sellable_at=SELLABLE, date_confidence="confirmed",
        observed_at="2026-10-27T00:00:00+00:00", source="synthetic",
        identity_confidence="proven", warehouse_confidence="confirmed", source_complete=True,
    )
    values.update(changes)
    return StageBalance(**values)


def run(demand_rows, supply_rows, complete=True):
    return net_target(sku="S", warehouse="W", uom=UOM, as_of=AS_OF, buckets=BUCKETS,
                      demand_rows=demand_rows, supply_rows=supply_rows,
                      supply_sources_complete=complete)


def demand(qty, day="2026-10-28"):
    return dict(demand_row_id=f"d-{day}", demand_date=day, canonical_sku="S",
                canonical_warehouse="W", canonical_uom=UOM, quantity=Decimal(str(qty)))


def protect(result, scenario="expected"):
    return next(r for r in result["rows"]
                if r["bucket_id"] == "protect" and r["scenario"] == scenario)


class F1OpeningGate(unittest.TestCase):
    def test_fba_opening_is_excluded_and_gap_kept(self):
        result = run([demand(5)], [snapshot(10, scope="external_fba")])
        row = protect(result)
        self.assertEqual(result["opening"], Decimal(0))
        self.assertEqual(row["gap"], Decimal(5))
        reasons = [f["disposition_reason"] for f in result["opening_facts"]]
        self.assertTrue(any(r.startswith("opening_excluded") for r in reasons), reasons)

    def test_replay_opening_is_excluded(self):
        result = run([demand(4)], [snapshot(10, exclusion_reason="exact_replay")])
        self.assertEqual(result["opening"], Decimal(0))
        self.assertEqual(protect(result)["gap"], Decimal(4))

    def test_duplicate_opening_rows_count_once(self):
        result = run([demand(3)], [snapshot(10), snapshot(10)])
        self.assertEqual(result["opening"], Decimal(10))
        self.assertEqual(protect(result)["gap"], Decimal(0))

    def test_zero_stock_remains_valid_evidence(self):
        result = run([demand(1)], [snapshot(0)])
        self.assertEqual(result["opening"], Decimal(0))
        self.assertEqual(protect(result)["gap"], Decimal(1))
        self.assertTrue(any(f["disposition_reason"] == "opening_basis"
                            for f in result["opening_facts"]))

    def test_unknown_opening_is_not_zero(self):
        result = run([demand(1)], [snapshot(None)])
        self.assertIsNone(result["opening"])
        self.assertIsNone(protect(result)["gap"])


class F2TrancheProvenance(unittest.TestCase):
    def _counted(self, balance):
        tranches = build_availability_schedule([balance])
        rows, _ = tranches_to_supply_rows(tranches)
        return rows

    def test_unproven_identity_is_not_upgraded(self):
        rows = self._counted(stage(identity_confidence="unproven"))
        self.assertEqual(rows[0].identity_confidence, "unproven")
        result = run([demand(5)], [snapshot(0)] + rows)
        self.assertEqual(protect(result)["receipts"], Decimal(0))
        reasons = [f["disposition_reason"] for f in result["scenarios"]["expected"]["facts"]]
        self.assertIn("source_unproven", reasons)

    def test_unmapped_warehouse_is_not_upgraded(self):
        rows = self._counted(stage(warehouse_confidence="unmapped"))
        self.assertEqual(rows[0].warehouse_confidence, "unmapped")
        result = run([demand(5)], [snapshot(0)] + rows)
        self.assertEqual(protect(result)["receipts"], Decimal(0))
        reasons = [f["disposition_reason"] for f in result["scenarios"]["expected"]["facts"]]
        self.assertIn("warehouse_unmapped", reasons)

    def test_source_complete_false_is_preserved(self):
        rows = self._counted(stage(source_complete=False))
        self.assertFalse(rows[0].source_complete)
        result = run([demand(5)], [snapshot(0)] + rows)
        self.assertEqual(protect(result)["receipts"], Decimal(0))

    def test_proven_stage_still_counts(self):
        result = run([demand(5)], [snapshot(0)] + self._counted(stage(10)))
        self.assertEqual(protect(result)["receipts"], Decimal(10))


class F3BatchQuotaAndDuplicates(unittest.TestCase):
    def test_same_batch_work_order_and_transit_count_once(self):
        work = tranche_row(10, stage="in_production", batch="B-1", proven=True)
        transit = tranche_row(10, stage="shipped_in_transit", batch="B-1", proven=True)
        result = run([demand(15)], [snapshot(0), work, transit])
        self.assertEqual(protect(result)["receipts"], Decimal(10))
        reasons = [f["disposition_reason"] for f in result["scenarios"]["expected"]["facts"]]
        self.assertIn("same_batch_counted_once", reasons)

    def test_same_batch_across_all_supply_stages(self):
        rows = [snapshot(0)] + [tranche_row(10, stage=st, batch="B-2", proven=True)
                                for st in ("in_production", "finished_waiting_shipment",
                                           "shipped_in_transit", "arrived_waiting_receipt")]
        result = run([demand(50)], rows)
        self.assertEqual(protect(result)["receipts"], Decimal(10))

    def test_quantity_conflict_does_not_sum(self):
        work = tranche_row(10, stage="in_production", batch="B-3", proven=True)
        transit = tranche_row(4, stage="shipped_in_transit", batch="B-3", proven=True)
        result = run([demand(20)], [snapshot(0), work, transit])
        self.assertEqual(protect(result)["receipts"], Decimal(4))
        reasons = [f["disposition_reason"] for f in result["scenarios"]["expected"]["facts"]]
        self.assertIn("batch_quantity_conflict", reasons)

    def test_unproven_batches_are_not_deduplicated(self):
        first = tranche_row(10, stage="in_production")
        second = tranche_row(10, stage="shipped_in_transit")
        result = run([demand(20)], [snapshot(0), first, second])
        self.assertEqual(protect(result)["receipts"], Decimal(20))

    def test_duplicate_balance_fails_closed(self):
        with self.assertRaises(DuplicateBalanceError):
            build_availability_schedule([stage(10), stage(10)])

    def test_validator_rejects_duplicate_stage_rows(self):
        errors = validate_stage_balances([stage(10), stage(10, balance_id="BAL-2")])
        self.assertTrue(any("重复" in e for e in errors), errors)

    def test_validator_accepts_legal_splits(self):
        from supply_netting.facts import split_balance
        parts = split_balance(stage(10), [("a", 6, SELLABLE), ("b", 4, SELLABLE)])
        self.assertEqual(validate_stage_balances(parts), [])

    def test_cli_refuses_to_write_when_validation_fails(self):
        from supply_netting import __main__ as cli

        supply = dict(rows=[], evidence=[],
                      stage_balances=[stage(10), stage(10, balance_id="BAL-2")],
                      schedule=[], stock_meta={}, po_meta={}, po_tongtool_meta={})
        meta = dict(four_key_duplicates=0, rows=0, quantity=0.0, default_rows=0,
                    third_party_rows=0, date_min="", date_max="", netting_allowed_all=True,
                    path="synthetic", sha256="")
        with tempfile.TemporaryDirectory() as tmp:
            out = Path(tmp) / "out"
            with mock.patch.object(cli, "load_demand_netting", return_value=(pd.DataFrame(), meta)), \
                    mock.patch.object(cli, "series_rows", return_value=[]), \
                    mock.patch.object(cli, "load_backlog", return_value=({}, {"source": "none"})), \
                    mock.patch.object(cli, "load_inputs", return_value=supply):
                code = cli.main(["--demand", "x", "--stock", "x", "--sku-map", "x",
                                 "--uom-cache", "x", "--as-of", "2026-10-27T00:00:00+08:00",
                                 "--no-forecast", "--out", str(out)])
            self.assertEqual(code, 2)
            self.assertFalse(out.exists() and any(out.glob("*.parquet")))


class F4ArrivedTranche(unittest.TestCase):
    def test_arrived_with_confirmed_sellable_date_counts(self):
        tranches = build_availability_schedule([stage(10, stage="arrived_waiting_receipt")])
        rows, _ = tranches_to_supply_rows(tranches)
        result = run([demand(6)], [snapshot(0)] + rows)
        self.assertEqual(protect(result)["receipts"], Decimal(10))

    def test_arrived_included_in_opening_is_not_added_again(self):
        tranches = build_availability_schedule(
            [stage(10, stage="arrived_waiting_receipt", included_in_opening=True)])
        rows, evidence = tranches_to_supply_rows(tranches)
        self.assertEqual(rows, [])
        self.assertEqual(evidence[0]["disposition_reason"], "included_in_opening")

    def test_arrived_without_date_stays_conditional(self):
        balance = stage(10, stage="arrived_waiting_receipt", sellable_at=None,
                        date_confidence="unknown")
        rows, _ = tranches_to_supply_rows(build_availability_schedule([balance]))
        result = run([demand(6)], [snapshot(0)] + rows)
        row = protect(result)
        self.assertEqual(row["receipts"], Decimal(0))
        self.assertEqual(row["conditional_receipts"], Decimal(10))

    def test_raw_receipt_event_still_not_counted(self):
        raw = SupplyRow(
            sku="S", warehouse="W", stage="arrived_waiting_receipt", source_layer="receipt_event",
            qty=Decimal("10"), qty_status="known", uom=UOM, uom_proven=True,
            event_date="2026-10-27", available_date=SELLABLE, date_confidence="confirmed",
            timezone_status="verified", identity_confidence="proven", scope="in_house",
            warehouse_confidence="confirmed", role="finished", b_min_eligible=False,
            b_max_eligible=True, source_key="receipt:1", source_complete=True)
        result = run([demand(6)], [snapshot(0), raw])
        self.assertEqual(protect(result)["receipts"], Decimal(0))


if __name__ == "__main__":
    unittest.main()
