# -*- coding: utf-8 -*-
"""供应决策契约 §7 的 8 个合成验收案例（stage_balances / availability_schedule）。"""

from __future__ import annotations

import tempfile
import unittest
from datetime import datetime, timezone
from decimal import Decimal
from pathlib import Path

import pandas as pd

from supply_netting.engine import build_buckets, net_target
from supply_netting.facts import (
    StageBalance, build_availability_schedule, milestones_frame, split_balance,
    summarize_stage_balances, tranches_frame, tranches_to_supply_rows,
    validate_stage_balances,
)

UOM = "件"


def balance(stage, qty, *, order="SO-1", sku="S", warehouse="W", uom=UOM,
            balance_id=None, **changes):
    values = dict(
        balance_id=balance_id or f"{order}:{sku}:{uom}:{stage}",
        order_key=order, sku=sku, warehouse=warehouse, uom=uom, stage=stage,
        qty=Decimal(str(qty)) if qty is not None else None,
        qty_status="known" if qty is not None else "unknown",
        order_qty=Decimal("100"),
        allocation_status="free",
        sellable_at="2026-11-01T00:00:00+00:00",
        date_confidence="confirmed",
        observed_at="2026-10-27T00:00:00+00:00",
        source="synthetic",
    )
    values.update(changes)
    return StageBalance(**values)


def schedule(results):
    return {tranche.balance_id: tranche for tranche in results}


def snapshot(qty=0):
    from supply_chain_visibility.supply_row import SupplyRow
    return SupplyRow(
        sku="S", warehouse="W", stage="on_hand", source_layer="inventory_snapshot",
        qty=Decimal(str(qty)), qty_status="known", uom=UOM, uom_proven=True,
        event_date="2026-11-01", available_date=None, date_confidence="unknown",
        timezone_status="unverified", identity_confidence="proven",
        scope="in_house", warehouse_confidence="confirmed", role="finished",
        b_min_eligible=False, b_max_eligible=True, source_key="snapshot", source_complete=True,
    )


class ContractSection7(unittest.TestCase):
    def test_1_stage_balances_are_mutually_exclusive_and_cumulative_is_not_supply(self):
        rows = [balance("unreleased", 10), balance("in_production", 30),
                balance("finished_waiting_shipment", 20), balance("shipped_in_transit", 25),
                balance("arrived_waiting_receipt", 5),
                balance("completed_sellable_delivery", 10)]
        self.assertEqual(validate_stage_balances(rows), [])
        summary = summarize_stage_balances(rows)[0]
        self.assertEqual(summary["total"], 100)
        self.assertTrue(summary["balanced"])
        self.assertEqual(summary["supply_qty"], 80)      # 未排产不算供给
        self.assertEqual(summary["terminal_qty"], 10)    # 累计交付不可再加
        tranches = build_availability_schedule(rows)
        counted = [t for t in tranches if not t.exclusion_reason]
        self.assertEqual(sum(t.qty for t in counted), Decimal(80))
        self.assertEqual({t.exclusion_reason for t in tranches if t.exclusion_reason},
                         {"not_released", "already_delivered"})

    def test_2_one_dn_two_shipments_needs_proven_allocation(self):
        unproven = balance("shipped_in_transit", 100, allocation_status="unknown",
                           balance_id="DN-100")
        tranche = schedule(build_availability_schedule([unproven]))["DN-100"]
        self.assertEqual(tranche.exclusion_reason, "allocation_unproven")
        self.assertEqual(tranche.qty, Decimal(100))       # 不得拆成两份 100

        proven = balance("shipped_in_transit", 100, balance_id="DN-100B")
        parts = split_balance(proven, [("A", 60, "2026-11-05T00:00:00+00:00"),
                                       ("B", 40, "2026-11-20T00:00:00+00:00")])
        self.assertEqual([p.qty for p in parts], [Decimal(60), Decimal(40)])
        got = schedule(build_availability_schedule(parts))
        self.assertEqual(got["DN-100B#A1"].available_at, "2026-11-05T00:00:00+00:00")
        self.assertEqual(got["DN-100B#B2"].available_at, "2026-11-20T00:00:00+00:00")

    def test_3_partial_receipt_does_not_create_140_or_double_count_stock(self):
        rows = [balance("unreleased", 60, balance_id="PO-100:open"),
                balance("shipped_in_transit", 30, balance_id="PO-100:transit"),
                balance("arrived_waiting_receipt", 10, balance_id="PO-100:received",
                        included_in_opening=True)]
        summary = summarize_stage_balances(rows)[0]
        self.assertEqual(summary["total"], 100)
        tranches = schedule(build_availability_schedule(rows))
        self.assertEqual(tranches["PO-100:transit"].exclusion_reason, "")
        self.assertEqual(tranches["PO-100:received"].exclusion_reason, "included_in_opening")
        self.assertEqual(tranches["PO-100:open"].exclusion_reason, "not_released")

    def test_4_fba_reservation_excluded_and_units_do_not_mix(self):
        rows = [balance("in_production", 12, allocation_status="free", balance_id="free-12"),
                balance("in_production", 8, allocation_status="fba", balance_id="fba-8"),
                balance("in_production", 2, uom="套", balance_id="sets-2")]
        tranches = schedule(build_availability_schedule(rows))
        self.assertEqual(tranches["free-12"].exclusion_reason, "")
        self.assertEqual(tranches["fba-8"].exclusion_reason, "fba_allocated")
        summary = {row["uom"]: row for row in summarize_stage_balances(rows)}
        self.assertEqual(summary["件"]["total"], 20)     # 12 自由 + 8 FBA
        self.assertEqual(summary["套"]["total"], 2)      # 不并入件

    def test_5_sellable_after_arrival_does_not_clear_earlier_gap(self):
        row = balance("shipped_in_transit", 1, balance_id="ETA-1",
                      expected_at="2026-11-05T00:00:00+00:00",
                      sellable_at="2026-11-08T00:00:00+00:00")
        tranche = schedule(build_availability_schedule([row]))["ETA-1"]
        self.assertEqual(tranche.available_at, "2026-11-08T00:00:00+00:00")
        supply_rows, _ = tranches_to_supply_rows([tranche])
        supply_rows = [snapshot()] + supply_rows
        as_of = datetime(2026, 11, 1, tzinfo=timezone.utc)
        result = net_target(
            sku="S", warehouse="W", uom=UOM, as_of=as_of,
            buckets=build_buckets(as_of, protect_days=6, weeks=1),
            demand_rows=[dict(demand_row_id="d1", demand_date="2026-11-06",
                              quantity=Decimal("1"))],
            supply_rows=supply_rows, supply_sources_complete=True)
        protect = next(r for r in result["rows"]
                       if r["bucket_id"] == "protect" and r["scenario"] == "expected")
        self.assertEqual(protect["gap"], Decimal(1))     # 11/6 的缺口不被 11/8 可售消除

    def test_6_split_tranches_only_fill_their_own_period(self):
        whole = balance("in_production", 100, balance_id="SO-BATCH")
        parts = split_balance(whole, [("now", 20, "2026-11-01T12:00:00+00:00"),
                                      ("mid", 30, "2026-11-05T00:00:00+00:00"),
                                      ("late", 50, "2026-11-20T00:00:00+00:00")])
        self.assertEqual(sum(p.qty for p in parts), Decimal(100))   # 不重复计原 SO 100
        tranches = build_availability_schedule(parts)
        self.assertEqual(len(tranches), 3)
        supply_rows, _ = tranches_to_supply_rows(tranches)
        supply_rows = [snapshot()] + supply_rows
        as_of = datetime(2026, 11, 1, tzinfo=timezone.utc)
        result = net_target(
            sku="S", warehouse="W", uom=UOM, as_of=as_of,
            buckets=build_buckets(as_of, protect_days=7, weeks=3),
            demand_rows=[dict(demand_row_id="d", demand_date="2026-11-01",
                              quantity=Decimal("100"))],
            supply_rows=supply_rows, supply_sources_complete=True)
        rows = {r["bucket_id"]: r for r in result["rows"] if r["scenario"] == "expected"}
        # 保护期只拿到 11/1 与 11/5 两批（20 + 30），11/20 的 50 不能提前用
        self.assertEqual(rows["protect"]["receipts"], Decimal(50))
        self.assertEqual(rows["w1"]["receipts"], Decimal(0))
        self.assertEqual(rows["w2"]["receipts"], Decimal(50))
        self.assertEqual(sum(r["receipts"] for r in rows.values()), Decimal(100))

    def test_7_cancelled_order_keeps_physical_quantity_and_reason(self):
        rows = [balance("cancelled", 100, balance_id="SO-X:cancelled"),
                balance("in_production", 40, allocation_status="unknown",
                        balance_id="SO-X:physical")]
        tranches = schedule(build_availability_schedule(rows))
        self.assertEqual(tranches["SO-X:cancelled"].exclusion_reason, "order_cancelled")
        self.assertEqual(tranches["SO-X:physical"].exclusion_reason, "allocation_unproven")
        self.assertEqual(sum(t.qty for t in tranches.values()), Decimal(140))
        rows_out, evidence = tranches_to_supply_rows(list(tranches.values()))
        self.assertEqual(rows_out, [])                     # 实物未重新分配前不算供给
        self.assertEqual(len(evidence), 2)                 # 但必须留痕

    def test_8_parquet_and_excel_agree_and_rerun_is_stable(self):
        rows = [balance("in_production", 5, balance_id="R:1"),
                balance("shipped_in_transit", 3, balance_id="R:2",
                        date_confidence="unknown", sellable_at=None)]
        first = tranches_frame(build_availability_schedule(rows))
        second = tranches_frame(build_availability_schedule(rows))
        self.assertEqual(first, second)                    # 重跑不重复计数
        frame = pd.DataFrame(first)
        with tempfile.TemporaryDirectory() as tmp:
            pq = Path(tmp) / "schedule.parquet"
            xl = Path(tmp) / "schedule.xlsx"
            frame.to_parquet(pq, index=False)
            frame.to_excel(xl, index=False)
            back_pq = pd.read_parquet(pq)
            back_xl = pd.read_excel(xl)
        self.assertEqual(list(back_pq["tranche_id"]), list(back_xl["tranche_id"]))
        self.assertEqual(list(back_pq["qty"]), list(back_xl["qty"]))
        self.assertEqual(list(back_pq["available_at"].astype(object)),
                         list(back_xl["available_at"].astype(object)))
        self.assertEqual(sorted(back_pq["exclusion_reason"].fillna("")),
                         sorted(back_xl["exclusion_reason"].fillna("")))

    def test_milestone_fields_are_kept_separately(self):
        row = balance("shipped_in_transit", 3, balance_id="M:1",
                      planned_at="2026-11-01T00:00:00+00:00",
                      expected_at="2026-11-05T00:00:00+00:00",
                      actual_at=None)
        frame = milestones_frame([row])
        self.assertEqual(frame[0]["planned_at"], "2026-11-01T00:00:00+00:00")
        self.assertEqual(frame[0]["expected_at"], "2026-11-05T00:00:00+00:00")
        self.assertIsNone(frame[0]["actual_at"])


if __name__ == "__main__":
    unittest.main()
