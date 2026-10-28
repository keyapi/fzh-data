# -*- coding: utf-8 -*-
"""MOQ / 补货频率政策：解析、仓/渠道证据、分档、MOQ 取整、落盘（不改主表）。"""

from __future__ import annotations

import json
import tempfile
import unittest
from pathlib import Path

import pandas as pd

from supply_netting.scripts import moq_replenish_policy as policy

ATTR_HEADER = "\t".join(policy.ATTR_COLUMNS)


def attr_rows(rows) -> str:
    """把 (code, name, group, is_stock, moq, ss, lt) 拼成 10 列无表头 TSV 文本。"""
    lines = []
    for code, name, group, is_stock, moq, safety, lead in rows:
        lines.append("\t".join([code, name, group, str(is_stock), f"{moq:.9f}", "0",
                                f"{safety:.9f}", str(lead), "0.000000000", "0"]))
    return "\n".join(lines) + "\n"


def snapshot_row(stock_uom="千克", default_warehouse="包材仓 - FZH", bins=None,
                 purchase=1, manufacturing=1):
    return dict(stock_uom=stock_uom, default_warehouse=default_warehouse,
                bins=bins or [], is_purchase_item=purchase,
                include_item_in_manufacturing=manufacturing)


class ItemAttrTests(unittest.TestCase):
    def _write(self, tmp, rows) -> Path:
        path = Path(tmp) / "items_attr.tsv"
        path.write_text(attr_rows(rows), encoding="utf-8")
        return path

    def test_parses_moq_column_and_keeps_zero_rows(self):
        with tempfile.TemporaryDirectory() as tmp:
            rows = [("A1", "物料A", "辅材", 1, 48, 0, 7), ("B1", "物料B", "成品", 1, 0, 0, 5)]
            frame = policy.load_item_attr(self._write(tmp, rows))
            self.assertEqual(len(frame), 2)
            self.assertEqual(frame.loc[frame["item_code"] == "A1", "min_order_qty"].iloc[0], 48)
            selected = policy.moq_items(frame)
            self.assertEqual(selected["item_code"].tolist(), ["A1"])

    def test_wrong_column_count_fails(self):
        with tempfile.TemporaryDirectory() as tmp:
            path = Path(tmp) / "bad.tsv"
            path.write_text("A1\t物料A\t辅材\n", encoding="utf-8")
            with self.assertRaises(policy.InputError):
                policy.load_item_attr(path)

    def test_duplicate_item_code_fails(self):
        with tempfile.TemporaryDirectory() as tmp:
            rows = [("A1", "物料A", "辅材", 1, 10, 0, 5), ("A1", "物料A2", "辅材", 1, 0, 0, 5)]
            with self.assertRaises(policy.InputError):
                policy.load_item_attr(self._write(tmp, rows))

    def test_non_numeric_moq_fails(self):
        with tempfile.TemporaryDirectory() as tmp:
            path = Path(tmp) / "x.tsv"
            path.write_text("A1\t物料A\t辅材\t1\tN/A\t0\t0\t5\t0\t0\n", encoding="utf-8")
            with self.assertRaises(policy.InputError):
                policy.load_item_attr(path)


class EvidenceTests(unittest.TestCase):
    def _attr(self):
        return pd.DataFrame([dict(item_code="PPM1500", item_name="PP棉", item_group="PP棉",
                                  is_stock_item="1", min_order_qty=350.0, safety_stock=0.0,
                                  lead_time_days=5.0)])

    def test_missing_evidence_is_kept_and_marked(self):
        frame = policy.attach_en_evidence(self._attr(), {})
        self.assertEqual(frame.iloc[0]["en_evidence"], "missing")
        self.assertIsNone(frame.iloc[0]["stock_uom"])
        self.assertEqual(policy.supply_channel(frame.iloc[0].to_dict()), "unknown")

    def test_bins_and_warehouses_are_passed_through(self):
        snapshot = {"PPM1500": snapshot_row(bins=[
            dict(warehouse="包材仓 - FZH", actual_qty=120.0),
            dict(warehouse="辅材仓 - FZH", actual_qty=0.0)])}
        frame = policy.attach_en_evidence(self._attr(), snapshot)
        row = frame.iloc[0]
        self.assertEqual(row["default_warehouse"], "包材仓 - FZH")
        self.assertEqual(row["stock_warehouses"], "包材仓 - FZH")   # 0 库存的仓不算“有库存”
        self.assertEqual(row["stock_qty_total"], 120.0)
        self.assertEqual(row["supply_channel"], "外购辅料→绍兴工厂生产")

    def test_channel_never_invents_moq(self):
        snapshot = {"PPM1500": snapshot_row(purchase=1, manufacturing=0)}
        row = policy.attach_en_evidence(self._attr(), snapshot).iloc[0]
        self.assertEqual(row["supply_channel"], "外购")
        self.assertNotIn("MOQ", row["supply_channel"])

    def test_decision_membership(self):
        decisions = pd.DataFrame([
            dict(canonical_sku="PPM1500", canonical_warehouse="包材仓 - FZH",
                 canonical_uom="千克", qty_current=10.0, value_status="measured"),
            dict(canonical_sku="KS1", canonical_warehouse="美东-CENTRADE",
                 canonical_uom="个", qty_current=1.0, value_status="measured")])
        frame = policy.annotate_decision_membership(self._attr(), decisions)
        self.assertTrue(bool(frame.iloc[0]["in_decision_keys"]))
        self.assertEqual(frame.iloc[0]["decision_key_count"], 1)


def tier_frames():
    decisions = pd.DataFrame([
        dict(canonical_sku="S1", canonical_warehouse="W", canonical_uom="个",
             qty_current=1.0, status="conditional"),      # < 1 周（周需求 4）
        dict(canonical_sku="S2", canonical_warehouse="W", canonical_uom="个",
             qty_current=10.0, status="conditional"),     # 2 周
        dict(canonical_sku="S3", canonical_warehouse="W", canonical_uom="个",
             qty_current=50.0, status="conditional"),     # 10 周
        dict(canonical_sku="S4", canonical_warehouse="W", canonical_uom="个",
             qty_current=0.0, status="no_gap"),           # 0 → 不参与
        dict(canonical_sku="S5", canonical_warehouse="W", canonical_uom="个",
             qty_current=None, status="to_verify"),       # null → 不参与
        dict(canonical_sku="S6", canonical_warehouse="W", canonical_uom="套",
             qty_current=3.0, status="conditional"),      # 无预测
    ])
    weekly = pd.DataFrame([
        dict(canonical_sku="S1", canonical_warehouse="W", canonical_uom="个",
             p50=34.28, weekly_p50=4.0),
        dict(canonical_sku="S2", canonical_warehouse="W", canonical_uom="个",
             p50=42.86, weekly_p50=5.0),
        dict(canonical_sku="S3", canonical_warehouse="W", canonical_uom="个",
             p50=42.86, weekly_p50=5.0),
    ])
    return decisions, weekly


class OrderTierTests(unittest.TestCase):

    def test_tiers_and_exclusions(self):
        decisions, weekly = tier_frames()
        frame = policy.classify_orders(decisions, weekly).set_index("canonical_sku")
        self.assertEqual(frame.loc["S1", "tier"], "观察（<1 周需求）")
        self.assertEqual(frame.loc["S2", "tier"], "正常（1–4 周需求）")
        self.assertEqual(frame.loc["S3", "tier"], "批量（>4 周需求）")
        self.assertEqual(frame.loc["S6", "tier"], "无需求证据")
        self.assertNotIn("S4", frame.index)
        self.assertNotIn("S5", frame.index)
        self.assertAlmostEqual(frame.loc["S3", "weeks_of_cover"], 10.0)

    def test_summary_never_totals_across_uom(self):
        decisions, weekly = tier_frames()
        stats = policy.tier_summary(policy.classify_orders(decisions, weekly))
        self.assertEqual(set(stats), {"个", "套"})
        self.assertEqual(stats["个"]["tiers"]["观察（<1 周需求）"]["keys"], 1)
        self.assertEqual(stats["套"]["tiers"]["无需求证据"]["keys"], 1)
        self.assertNotIn("合计", json.dumps(stats, ensure_ascii=False))

    def test_cycle_stock_formula(self):
        decisions, weekly = tier_frames()
        effect = policy.cycle_stock_effect(policy.classify_orders(decisions, weekly))
        # 个：已知 S1 4 + S2 5 + S3 5 = 14/周 → 14 × (30-7)/2/7 = 23
        self.assertAlmostEqual(effect["个"]["delta_cycle_stock"], 23.0)
        self.assertEqual(effect["套"]["delta_cycle_stock"], 0.0)   # 无周需求证据不计


class MoqRoundupTests(unittest.TestCase):
    def test_rounds_up_to_moq(self):
        self.assertEqual(policy.moq_roundup(100, 350), (350.0, 250.0))
        self.assertEqual(policy.moq_roundup(350, 350), (350.0, 0.0))
        self.assertEqual(policy.moq_roundup(351, 350), (700.0, 349.0))
        self.assertEqual(policy.moq_roundup(0, 350), (0.0, 0.0))
        self.assertEqual(policy.moq_roundup(10, 0), (10.0, 0.0))   # 无 MOQ 不动


class PolicyTableTests(unittest.TestCase):
    def test_policy_rows_state_hard_facts_and_soft_threshold(self):
        decisions, weekly = tier_frames()
        classified = policy.classify_orders(decisions, weekly)
        rows = policy.policy_rows(classified, policy.tier_summary(classified), 0)
        by_level = {row["层次"]: row for row in rows}
        self.assertEqual(by_level["自有工厂（绍兴）MOQ"]["取值"], "无 MOQ 限制")
        self.assertIn(f"{policy.REVIEW_DAYS} 天", by_level["补货频率"]["取值"])
        self.assertIn("建议", by_level["小额补货阈值"]["约束强度"])
        self.assertIn("1 周", by_level["小额补货阈值"]["取值"])
        self.assertIn("不存在", by_level["渠道级 MOQ"]["取值"])
        self.assertIn("0/21", by_level["外购辅料 MOQ（21 项）"]["对主表"])


class BuildTests(unittest.TestCase):
    def test_build_writes_artifacts_only_into_out_dir(self):
        with tempfile.TemporaryDirectory() as tmp:
            tmp = Path(tmp)
            attr = tmp / "items_attr.tsv"
            attr.write_text(attr_rows([("PPM1500", "PP棉", "PP棉", 1, 350, 0, 5),
                                       ("KS1", "成品", "成品", 1, 0, 0, 14)]),
                            encoding="utf-8")
            snapshot = tmp / "en.json"
            snapshot.write_text(json.dumps({"PPM1500": snapshot_row()}, ensure_ascii=False),
                                encoding="utf-8")
            decisions_path = tmp / "dp.parquet"
            pd.DataFrame([dict(canonical_sku="KS1", canonical_warehouse="W",
                               canonical_uom="个", qty_current=3.0, status="conditional",
                               value_status="measured")]).to_parquet(decisions_path, index=False)
            windows, sku_map = tmp / "w.parquet", tmp / "m.tsv"
            windows.write_bytes(b"")
            sku_map.write_text("", encoding="utf-8")
            out = tmp / "out"

            original = policy.weekly_demand
            policy.weekly_demand = lambda *a, **k: pd.DataFrame([
                dict(canonical_sku="KS1", canonical_warehouse="W", canonical_uom="个",
                     p50=60.0, weekly_p50=7.0)])
            try:
                manifest = policy.build(attr, decisions_path, snapshot, windows, sku_map, out)
            finally:
                policy.weekly_demand = original

            for name in ("moq_items_21.csv", "replenish_policy.csv",
                         "small_order_analysis.csv", "impact_summary.json", "report.md"):
                self.assertTrue((out / name).is_file(), name)
            self.assertEqual(manifest["counts"]["moq_items"], 1)
            self.assertEqual(manifest["impact"]["moq_items_in_decisions"], 0)
            self.assertEqual(manifest["impact"]["decisions_with_positive_qty"], 1)
            self.assertEqual(set(manifest["inputs"]), {str(attr), str(decisions_path),
                                                      str(snapshot), str(windows), str(sku_map)})
            self.assertIn("不改决策包", manifest["note"])
            report = (out / "report.md").read_text(encoding="utf-8")
            self.assertIn("无 MOQ", report)
            self.assertIn("渠道级 MOQ", report)
            # 只写了 out 目录：tmp 根目录没有新增文件
            self.assertEqual(sorted(p.name for p in tmp.iterdir()),
                             ["dp.parquet", "en.json", "items_attr.tsv", "m.tsv", "out",
                              "w.parquet"])


if __name__ == "__main__":
    unittest.main()
