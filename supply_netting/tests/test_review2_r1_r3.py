# -*- coding: utf-8 -*-
"""第二轮复审 R1–R3 回归（supply-review2-36453827）。"""

from __future__ import annotations

import unittest
from datetime import datetime, timezone
from decimal import Decimal

from supply_chain_visibility.supply_row import SupplyRow

from supply_netting.engine import build_buckets, net_target
from supply_netting.facts import (StageBalance, build_availability_schedule, split_balance,
                                  tranches_to_supply_rows, validate_stage_balances)

UOM = "个"
AS_OF = datetime(2026, 10, 27, tzinfo=timezone.utc)
BUCKETS = build_buckets(AS_OF, protect_days=3, weeks=2)
SELLABLE_A = "2026-10-28T00:00:00+00:00"
SELLABLE_B = "2026-10-29T00:00:00+00:00"


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


def balance(qty=10, *, stage="in_production", batch=None, proven=True, **changes):
    values = dict(
        balance_id="BAL-1", order_key="SO-1", sku="S", warehouse="W", uom=UOM,
        stage=stage, qty=Decimal(str(qty)), order_qty=Decimal("100"),
        allocation_status="free", sellable_at=SELLABLE_A, date_confidence="confirmed",
        observed_at="2026-10-27T00:00:00+00:00", source="synthetic",
        identity_confidence="proven", warehouse_confidence="confirmed", source_complete=True,
        batch_key=batch, batch_proven=proven,
    )
    values.update(changes)
    return StageBalance(**values)


def demand(qty, day="2026-10-28"):
    return dict(demand_row_id=f"d-{day}", demand_date=day, canonical_sku="S",
                canonical_warehouse="W", canonical_uom=UOM, quantity=Decimal(str(qty)))


def run(demand_rows, supply_rows):
    return net_target(sku="S", warehouse="W", uom=UOM, as_of=AS_OF, buckets=BUCKETS,
                      demand_rows=demand_rows, supply_rows=supply_rows,
                      supply_sources_complete=True)


def protect(result):
    return next(r for r in result["rows"]
                if r["bucket_id"] == "protect" and r["scenario"] == "expected")


class R1SplitLineage(unittest.TestCase):
    def test_proven_batch_split_6_plus_4_counts_ten(self):
        parent = balance(10, batch="B-SPLIT", proven=True)
        parts = split_balance(parent, [("a", 6, SELLABLE_A), ("b", 4, SELLABLE_B)])
        self.assertEqual(validate_stage_balances(parts), [])
        rows, evidence = tranches_to_supply_rows(build_availability_schedule(parts))
        self.assertEqual(len(rows), 2)
        self.assertEqual(evidence, [])
        result = run([demand(10)], [snapshot(0)] + rows)
        self.assertEqual(protect(result)["receipts"], Decimal(10))
        self.assertEqual(protect(result)["gap"], Decimal(0))

    def test_split_children_keep_their_own_dates(self):
        parent = balance(10, batch="B-DATES", proven=True)
        parts = split_balance(parent, [("a", 6, SELLABLE_A), ("b", 4, SELLABLE_B)])
        rows, _ = tranches_to_supply_rows(build_availability_schedule(parts))
        self.assertEqual(sorted(row.available_date for row in rows), [SELLABLE_A, SELLABLE_B])

    def test_split_total_mismatch_is_rejected(self):
        parts = split_balance(balance(10, batch="B-X"), [("a", 6, SELLABLE_A), ("b", 4, SELLABLE_B)])
        tampered = [parts[0], parts[1].__class__(**{**parts[1].__dict__, "split_total": Decimal("99")})]
        self.assertTrue(any("父余额" in e for e in validate_stage_balances(tampered)))

    def test_cross_stage_replay_of_same_quota_still_dedupes(self):
        # 没有拆分谱系的同批跨阶段仍是同一额度 → 只计一次
        from supply_netting.tests.test_review_f1_f4 import tranche_row
        work = tranche_row(10, stage="in_production", batch="B-REPLAY", proven=True)
        transit = tranche_row(10, stage="shipped_in_transit", batch="B-REPLAY", proven=True)
        result = run([demand(20)], [snapshot(0), work, transit])
        self.assertEqual(protect(result)["receipts"], Decimal(10))

    def test_split_and_whole_batch_conflict_is_reported(self):
        from supply_netting.tests.test_review_f1_f4 import tranche_row
        parent = balance(10, batch="B-MIX", proven=True)
        parts = split_balance(parent, [("a", 6, SELLABLE_A), ("b", 4, SELLABLE_B)])
        split_rows, _ = tranches_to_supply_rows(build_availability_schedule(parts))
        whole = tranche_row(10, stage="shipped_in_transit", batch="B-MIX", proven=True)
        result = run([demand(30)], [snapshot(0)] + split_rows + [whole])
        self.assertEqual(result["batch_split_conflicts"], 1)
        # 谱系未证时两侧都保留（不静默丢弃已证数量），但冲突已显式上报
        self.assertEqual(protect(result)["receipts"], Decimal(20))


class R2MixedOpening(unittest.TestCase):
    def test_known_plus_unknown_opening_is_not_precise(self):
        known = snapshot(10, source_key="stock:known")
        unknown = snapshot(None, source_key="stock:unknown")
        result = run([demand(20)], [known, unknown])
        self.assertIsNone(result["opening"])
        self.assertEqual(result["opening_reason"], "opening_partially_unproven")
        self.assertEqual(result["opening_lower_bound"], Decimal(10))
        row = protect(result)
        self.assertIsNone(row["gap"])                 # 不用精确缺口掩盖未知
        self.assertEqual(row["status"], "unknown")
        self.assertEqual(row["opening_lower_bound"], Decimal(10))

    def test_unknown_only_opening_has_zero_lower_bound(self):
        result = run([demand(5)], [snapshot(None, source_key="stock:unknown")])
        self.assertIsNone(result["opening"])
        self.assertEqual(result["opening_lower_bound"], Decimal(0))

    def test_definitive_exclusion_plus_known_opening_stays_precise(self):
        known = snapshot(10, source_key="stock:known")
        fba = snapshot(4, source_key="stock:fba", scope="external_fba")
        result = run([demand(6)], [known, fba])
        self.assertEqual(result["opening"], Decimal(10))
        self.assertEqual(protect(result)["gap"], Decimal(0))


class R3ForecastHash(unittest.TestCase):
    """R3 的哈希拒绝主回归在 test_forecast.py；这里锁 CLI 参数接线。"""

    def test_cli_exposes_manifest_sha_flag(self):
        from supply_netting.__main__ import build_parser
        args = build_parser().parse_args([
            "--demand", "x", "--stock", "x", "--sku-map", "x", "--uom-cache", "x",
            "--as-of", "2026-10-27T00:00:00+08:00", "--out", "x",
            "--forecast-manifest-sha256", "7a41"])
        self.assertEqual(args.forecast_manifest_sha256, "7a41")


if __name__ == "__main__":
    unittest.main()
