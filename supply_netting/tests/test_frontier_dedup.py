# -*- coding: utf-8 -*-
"""FRONTIER-DEDUP 检查：核心回放等价、管道差异、α≠CSL、frontier_v2 冻结面。"""

from __future__ import annotations

import json
import subprocess
import tempfile
import unittest
from pathlib import Path

from supply_netting import frontier_v2
from supply_netting.scripts import frontier_dedup_check as check

ASSET_OK = subprocess.run(
    ["git", "cat-file", "-e", f"{check.ASSET_COMMIT}:{check.ASSET_PATH}"],
    capture_output=True).returncode == 0
REASON = f"git 里取不到 {check.ASSET_COMMIT}:{check.ASSET_PATH}（浅克隆/归档副本）"


class FrozenSurfaceTests(unittest.TestCase):
    """frontier_v2 冻结：不再新增模拟/评估入口。"""

    def test_public_surface_is_frozen(self):
        drift = check.surface_drift()
        self.assertEqual(drift["new_since_freeze"], [],
                         "frontier_v2 出现冻结面之外的新函数：按 A1/A3 结论不得再扩写")
        self.assertTrue(drift["frozen_is_subset"])

    def test_simulate_has_no_backorder_semantics(self):
        import inspect
        parameters = set(inspect.signature(frontier_v2.simulate).parameters)
        self.assertNotIn("semantics", parameters,
                         "frontier_v2 只支持 lost_sales；要 backorder 必须走既有评估器")

    def test_simulate_keeps_fill_rate_definition(self):
        import numpy as np
        demand = np.array([0, 3, 0, 5, 0, 2, 1, 4], dtype=float)
        result = frontier_v2.simulate(demand, 2.0, sim_start=0, score_start=0, end=len(demand),
                                      lead=2, review=1, seed_rate=0.0)
        self.assertAlmostEqual(result["served"] + result["lost"], result["demand"])
        self.assertAlmostEqual(result["fill_rate"], result["served"] / result["demand"])


@unittest.skipUnless(ASSET_OK, REASON)
class AssetComparisonTests(unittest.TestCase):
    """与既有评估器（e3727683 inventory_policy.py）的实测差异。"""

    @classmethod
    def setUpClass(cls):
        cls.asset = check.load_asset()

    def test_daily_review_is_identical(self):
        cores = check.compare_cores(self.asset, days=200, seed=7)
        daily = [row for row in cores["cases"] if row["review"] == 1]
        self.assertTrue(daily)
        for row in daily:
            self.assertEqual(row["served_delta"], 0.0,
                             f"R=1 L={row['lead']} 应完全相等，实际差 {row['served_delta']}")
        self.assertTrue(cores["daily_review_all_identical"])

    def test_weekly_review_differs_only_by_phase(self):
        cores = check.compare_cores(self.asset, days=200, seed=7)
        weekly = [row for row in cores["cases"] if row["review"] == 7]
        self.assertTrue(any(row["served_delta"] != 0 for row in weekly),
                        "周复核应与既有评估器有相位差，不应被当成等价实现")

    def test_beta_definition_same_but_alpha_is_not_csl(self):
        metric = check.compare_metrics(self.asset, days=200)
        self.assertTrue(metric["same_definition"])      # β ≡ fill_rate（满足量/需求量）
        self.assertFalse(metric["alpha_equals_csl"])    # α（有需求期间）≠ CSL（复核周期）
        self.assertGreater(metric["demand_cycles"], metric["frontier_cycles"])

    def test_backorder_only_exists_in_asset(self):
        backorder = check.compare_backorder(self.asset, days=200)
        self.assertTrue(backorder["asset_has_semantics"])
        self.assertFalse(backorder["frontier_v2_supports_backorder"])
        self.assertGreater(backorder["asset_lost_sales"]["lost"], 0)
        self.assertEqual(backorder["asset_lost_sales"]["end_backlog"], 0)
        self.assertEqual(backorder["asset_backorder"]["lost"], 0)
        self.assertGreater(backorder["asset_backorder"]["end_backlog"], 0)


class CheckPlumbingTests(unittest.TestCase):
    def test_missing_asset_fails_loudly(self):
        with self.assertRaises(check.AssetUnavailable):
            check.git_show("0000000", check.ASSET_PATH)

    @unittest.skipUnless(ASSET_OK, REASON)
    def test_run_check_writes_report_and_manifest_only_in_out(self):
        with tempfile.TemporaryDirectory() as tmp:
            tmp = Path(tmp)
            out = tmp / "out"
            out.mkdir()
            result = check.run_check(None, check.ASSET_COMMIT, check.ASSET_PATH, 120, 7)
            check.write_report(result, out)
            (out / "comparison.json").write_text(
                json.dumps(result, ensure_ascii=False), encoding="utf-8")
            text = (out / "report.md").read_text(encoding="utf-8")
            for phrase in ("核心语义是同一套", "不能直接替换", "α ≠ CSL", "不再扩写 frontier_v2",
                           "backorder"):
                self.assertIn(phrase, text)
            self.assertEqual(sorted(p.name for p in out.iterdir()),
                             ["comparison.json", "report.md"])
            self.assertEqual(sorted(p.name for p in tmp.iterdir()), ["out"])


if __name__ == "__main__":
    unittest.main()
