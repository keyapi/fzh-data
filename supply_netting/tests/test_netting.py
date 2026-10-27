# -*- coding: utf-8 -*-
"""供给净额层的 8 条必测场景（全部合成数据，不读生产/business fixture）。"""

from __future__ import annotations

import unittest
from datetime import datetime, timezone
from decimal import Decimal

from supply_chain_visibility.supply_row import SupplyRow

from supply_netting.engine import (
    ALWAYS_DEDUPED, build_buckets, net_all, net_target,
)
from supply_netting.legacy_ledger import assert_bucket_identities

UOM = "个"


def t(day, hour=0):
    return datetime(2026, 10, day, hour, tzinfo=timezone.utc)


AS_OF = t(27)
BUCKETS = build_buckets(AS_OF, protect_days=3, weeks=2)   # protect 27–30, w1 30–11/06, w2 11/06–11/13


def demand(quantity, day="2026-10-28", sku="S", warehouse="W", row_id=None):
    return dict(demand_row_id=row_id or f"d-{day}-{quantity}",
                demand_date=day, canonical_sku=sku, canonical_warehouse=warehouse,
                canonical_uom=UOM, quantity=Decimal(str(quantity)))


def srow(qty, *, sku="S", warehouse="W", layer="in_transit", stage="shipped_in_transit",
         available="2026-10-28T00:00:00+00:00", scope="in_house", b_min=True, b_max=True,
         batch_key=None, batch_proven=False, document_key=None, source_key=None,
         date_confidence=None, exclusion=""):
    return SupplyRow(
        sku=sku, warehouse=warehouse, stage=stage, source_layer=layer,
        qty=Decimal(str(qty)) if qty is not None else None,
        qty_status="known" if qty is not None else "unknown",
        uom=UOM, uom_proven=True,
        event_date="2026-10-28",
        available_date=available,
        date_confidence=date_confidence or ("confirmed" if available else "unknown"),
        timezone_status="verified" if available else "unverified",
        identity_confidence="proven",
        source_as_of="2026-10-27T00:00:00+00:00" if b_min else None,
        scope=scope, warehouse_confidence="confirmed", role="finished",
        b_min_eligible=b_min, b_max_eligible=b_max,
        source_key=source_key or f"{layer}:{sku}:{warehouse}:{qty}",
        source_complete=True, batch_key=batch_key, batch_proven=batch_proven,
        document_key=document_key,
    )


def snapshot(qty, *, sku="S", warehouse="W"):
    return srow(qty, sku=sku, warehouse=warehouse, layer="inventory_snapshot",
                stage="on_hand", available=None, b_min=False, b_max=True)


def run(demand_rows, supply_rows, *, backlog=Decimal("0"), complete=True):
    return net_target(sku="S", warehouse="W", uom=UOM, as_of=AS_OF, buckets=BUCKETS,
                      demand_rows=demand_rows, supply_rows=supply_rows,
                      backlog_qty=backlog, supply_sources_complete=complete)


def buckets_of(result, scenario="expected"):
    return {row["bucket_id"]: row for row in result["rows"] if row["scenario"] == scenario}


class NettingScenarios(unittest.TestCase):
    def test_1_same_sku_two_warehouses_do_not_offset(self):
        rows = [snapshot(100, warehouse="W1"), snapshot(0, warehouse="W2"),
                srow(40, warehouse="W1")]
        out = net_all(demand_rows=[demand(1, warehouse="W1"), demand(5, warehouse="W2")],
                      supply_rows=rows, as_of=AS_OF, buckets=BUCKETS,
                      supply_sources_complete=True)
        by_wh = {target["key"][1]: target for target in out["targets"]}
        w2 = buckets_of(by_wh["W2"])
        w1 = buckets_of(by_wh["W1"])
        self.assertEqual(w2["protect"]["gap"], Decimal(5))   # W1 的余量不能补 W2
        self.assertEqual(w1["protect"]["gap"], Decimal(0))
        self.assertEqual(w1["protect"]["closing"], Decimal(139))  # 期初 100 + 本仓到货 40 − 需求 1
        self.assertEqual(w1["w1"]["closing"], Decimal(139))       # 结余留在 W1，不外溢到 W2

    def test_2_zero_forecast_still_keeps_unfulfilled_so(self):
        result = run([], [snapshot(0)], backlog=Decimal("8"))
        buckets = buckets_of(result)
        self.assertEqual(buckets["protect"]["demand"], Decimal(8))
        self.assertEqual(buckets["protect"]["gap"], Decimal(8))
        # 未履约量按 bucket_gaps 的结转规则后移，不丢也不重复计入到货
        self.assertEqual(buckets["w1"]["demand"], Decimal(8))
        self.assertEqual(buckets["w1"]["gap"], Decimal(8))

    def test_3_gap_moves_when_demand_increases(self):
        low = buckets_of(run([demand(3)], [snapshot(5)]))
        high = buckets_of(run([demand(8)], [snapshot(5)]))
        self.assertEqual(low["protect"]["gap"], Decimal(0))
        self.assertEqual(high["protect"]["gap"], Decimal(3))

    def test_4_later_supply_cannot_cover_earlier_gap(self):
        rows = [snapshot(0), srow(10, available="2026-11-01T00:00:00+00:00")]
        buckets = buckets_of(run([demand(8, day="2026-10-28")], rows))
        self.assertEqual(buckets["protect"]["gap"], Decimal(8))
        self.assertEqual(buckets["protect"]["receipts"], Decimal(0))
        self.assertEqual(buckets["w1"]["receipts"], Decimal(10))

    def test_5_fba_allocated_supply_is_excluded(self):
        rows = [snapshot(0), srow(10, scope="external_fba")]
        result = run([demand(4)], rows)
        buckets = buckets_of(result)
        self.assertEqual(buckets["protect"]["receipts"], Decimal(0))
        self.assertEqual(buckets["protect"]["gap"], Decimal(4))
        reasons = [f["disposition_reason"] for f in result["scenarios"]["expected"]["facts"]]
        self.assertIn("fba_allocated", reasons)

    def test_6_same_batch_across_stages_counts_once(self):
        po = srow(10, layer="po_open", stage="po_open", available="2026-10-29T00:00:00+00:00",
                  batch_key="BATCH-1", batch_proven=True, document_key="PO-1")
        transit = srow(10, layer="in_transit", batch_key="BATCH-1", batch_proven=True)
        result = run([demand(15)], [snapshot(0), po, transit])
        buckets = buckets_of(result)
        self.assertEqual(buckets["protect"]["receipts"], Decimal(10))  # 只计一次
        reasons = [f["disposition_reason"] for f in result["scenarios"]["expected"]["facts"]]
        self.assertIn("same_batch_counted_once", reasons)
        self.assertEqual(ALWAYS_DEDUPED & {"proven_batch_replay"}, {"proven_batch_replay"})

    def test_7_unknown_eta_stays_conditional(self):
        result = run([demand(6)], [snapshot(1), srow(9, available=None)])
        buckets = buckets_of(result)
        self.assertEqual(buckets["protect"]["receipts"], Decimal(0))
        self.assertEqual(buckets["protect"]["conditional_receipts"], Decimal(9))
        self.assertEqual(buckets["protect"]["status"], "conditional")
        self.assertTrue(buckets["protect"]["has_unresolved"])
        reasons = [f["disposition_reason"] for f in result["scenarios"]["expected"]["facts"]]
        self.assertIn("date_unproven", reasons)

    def test_8_every_bucket_identity_holds(self):
        rows = [snapshot(5), srow(3, available="2026-10-29T00:00:00+00:00"),
                srow(2, available=None), srow(4, scope="external_fba")]
        result = run([demand(7, day="2026-10-28"), demand(2, day="2026-11-02")], rows)
        for row in result["rows"]:
            if row["opening"] is None:
                continue
            assert_bucket_identities(dict(opening=float(row["opening"]), receipts=float(row["receipts"]),
                                          demand=float(row["demand"]), fulfilled=float(row["fulfilled"]),
                                          closing=float(row["closing"]), unserved=float(row["unserved"])))
            self.assertEqual(row["opening"] + row["receipts"] - row["fulfilled"], row["closing"])
        # 供应侧数量账守恒：输入已证量 = 计入量 + 明确排除量
        for scenario in result["scenarios"].values():
            for account in scenario["ledger"].values():
                self.assertEqual(account["input_known"], account["counted"] + account["excluded_known"])


class NettingContractEdges(unittest.TestCase):
    def test_missing_snapshot_is_unknown_not_zero(self):
        result = run([demand(4)], [])
        row = buckets_of(result)["protect"]
        self.assertEqual(row["status"], "unknown")
        self.assertIsNone(row["opening"])
        self.assertIsNone(row["gap"])

    def test_supply_without_evidence_is_conditional_not_zero(self):
        result = run([demand(4)], [snapshot(0)])
        row = buckets_of(result)["protect"]
        self.assertEqual(row["status"], "conditional")
        self.assertEqual(row["receipts"], Decimal(0))

    def test_before_as_of_demand_is_reported_not_netted(self):
        result = run([demand(9, day="2026-10-01")], [snapshot(0)])
        self.assertEqual(result["demand_hidden_qty"], Decimal(9))
        reasons = [d["reason"] for d in result["demand_dispositions"]]
        self.assertEqual(reasons, ["before_as_of"])

    def test_undated_demand_falls_into_earliest_bucket(self):
        result = run([demand(3, day=None)], [snapshot(0)])
        self.assertEqual(buckets_of(result)["protect"]["demand"], Decimal(3))

    def test_conservative_and_expected_differ_only_on_proof(self):
        loose = srow(10, b_min=False, b_max=True)
        result = run([demand(4)], [snapshot(0), loose])
        self.assertEqual(buckets_of(result, "conservative")["protect"]["receipts"], Decimal(0))
        self.assertEqual(buckets_of(result, "expected")["protect"]["receipts"], Decimal(10))

    def test_backlog_without_any_demand_rows_still_gets_a_target(self):
        out = net_all(demand_rows=[], supply_rows=[snapshot(0)],
                      backlog={("S", "W", UOM): 4.0}, as_of=AS_OF, buckets=BUCKETS)
        self.assertEqual(len(out["targets"]), 1)
        rows = buckets_of(out["targets"][0])
        self.assertEqual(rows["protect"]["gap"], Decimal(4))


if __name__ == "__main__":
    unittest.main()
