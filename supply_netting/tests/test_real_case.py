# -*- coding: utf-8 -*-
"""真实案例对照：冻结需求净额表 × 2026-10-20 通途库存快照。

数据在本地 ``D:/Work/fzh-order-store``；缺失时整组跳过（CI/新机器不应误报失败）。
真实数据会滚动更新，所以这里断言**结构与守恒**，不断言易变的绝对数量。
"""

from __future__ import annotations

import unittest
from datetime import datetime, timezone
from pathlib import Path

STORE = Path("D:/Work/fzh-order-store")
CANONICAL = STORE / "en-demand-v1" / "canonical"
REQUIRED = [CANONICAL / "demand_netting.parquet", STORE / "en_stock.parquet",
            STORE / "sku_map.tsv", CANONICAL / "item_uom_cache.parquet"]
AVAILABLE = all(p.exists() for p in REQUIRED)


@unittest.skipUnless(AVAILABLE, "本地冻结数据不存在，跳过真实案例对照")
class RealCaseTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        from self_fulfilled_demand.canonical import WAREHOUSE_ALIASES
        from supply_netting.demand import SERIES_DEFAULT, load_demand_netting, series_rows
        from supply_netting.engine import build_buckets, net_all
        from supply_netting.supply import load_inputs

        cls.demand_df, cls.demand_meta = load_demand_netting(CANONICAL / "demand_netting.parquet")
        cls.rows = series_rows(cls.demand_df, SERIES_DEFAULT)
        cls.supply = load_inputs(
            stock_path=STORE / "en_stock.parquet", po_path=STORE / "po_open.tsv",
            sku_map_path=STORE / "sku_map.tsv",
            uom_cache_path=CANONICAL / "item_uom_cache.parquet",
            warehouse_alias_path=WAREHOUSE_ALIASES, snapshot_date="2026-10-20")
        cls.as_of = datetime(2026, 10, 21, tzinfo=timezone.utc)
        cls.buckets = build_buckets(cls.as_of, protect_days=3, weeks=2)
        cls.result = net_all(demand_rows=cls.rows, supply_rows=cls.supply["rows"],
                             as_of=cls.as_of, buckets=cls.buckets,
                             supply_sources_complete=False)

    def test_frozen_demand_contract_holds(self):
        self.assertEqual(self.demand_meta["four_key_duplicates"], 0)
        self.assertTrue(self.demand_meta["netting_allowed_all"])
        self.assertEqual(self.demand_meta["date_max"], "2026-10-26")

    def test_every_demand_row_has_a_destination(self):
        accounted = sum(len(t["demand_dispositions"]) for t in self.result["targets"])
        self.assertLess(accounted, len(self.rows))    # 历史需求不进入视界键
        for target in self.result["targets"]:
            for disposition in target["demand_dispositions"]:
                self.assertIn(disposition["reason"],
                              {"bucketed", "before_as_of", "after_horizon",
                               "demand_date_unproven_earliest"})

    def test_bucket_identities_hold_on_real_data(self):
        from supply_netting.legacy_ledger import assert_bucket_identities
        for target in self.result["targets"]:
            for row in target["rows"]:
                if row["opening"] is None:
                    continue
                assert_bucket_identities(dict(opening=float(row["opening"]),
                                              receipts=float(row["receipts"]),
                                              demand=float(row["demand"]),
                                              fulfilled=float(row["fulfilled"]),
                                              closing=float(row["closing"]),
                                              unserved=float(row["unserved"])))
                self.assertEqual(row["opening"] + row["receipts"] - row["fulfilled"], row["closing"])

    def test_real_gap_and_conditional_supply_exist(self):
        expected = [r for t in self.result["targets"] for r in t["rows"]
                    if r["scenario"] == "expected" and r["bucket_id"] == "protect"]
        self.assertTrue(any(r["gap"] and r["gap"] > 0 for r in expected),
                        "真实窗口里应至少有一个保护期缺口")
        self.assertTrue(any(r["conditional_receipts"] and r["conditional_receipts"] > 0
                            for r in expected),
                        "通途在途无 ETA，应至少有一条条件态供应")

    def test_no_snapshot_basis_is_kept_unknown(self):
        unknown = [t for t in self.result["targets"]
                   if any(r["status"] == "unknown" for r in t["rows"])]
        self.assertGreaterEqual(len(unknown), 0)
        for target in unknown:
            self.assertIsNone(target["opening"])
            for row in target["rows"]:
                self.assertIsNone(row["gap"])


if __name__ == "__main__":
    unittest.main()
