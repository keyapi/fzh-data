# -*- coding: utf-8 -*-
"""目录覆盖后续动作：原因分类、动作表对账、64 项优先清单、落盘只写 out。"""

from __future__ import annotations

import json
import tempfile
import unittest
from pathlib import Path

import pandas as pd

from supply_netting.scripts import catalog_next as cn

COLUMNS = ["item", "role", "group", "name", "in_catalog", "mapped_tt_count", "stock_qty",
           "stock_warehouses", "sales_total", "sales_recent6", "in_pack", "pack_keys",
           "reason", "reason_detail"]


def row(item, reason, stock=0.0, group="三角靠枕", mapped=1, sales=0.0, warehouses=""):
    return dict(item=item, role="finished", group=group, name=f"{group}-{item}",
                in_catalog=True, mapped_tt_count=mapped, stock_qty=stock,
                stock_warehouses=warehouses, sales_total=sales, sales_recent6=sales,
                in_pack=False, pack_keys=0, reason=reason, reason_detail="test")


def fixture(tmp: Path, rows=None) -> tuple[Path, Path]:
    rows = rows or [
        row("KS-UOM-1", "stock_without_uom_evidence", 30.0, warehouses="美东-CENTRADE"),
        row("KS-UOM-2", "stock_without_uom_evidence", 20.0, warehouses="波兰-FZHPoland-covers"),
        row("KS-UOM-3", "stock_without_uom_evidence", 5.0, warehouses="美中-FZH-DANEEY"),
        row("KS-UNMAP-1", "unmapped_no_evidence", mapped=0),
        row("KS-NS-1", "mapped_no_stock_no_sales"),
        row("PK#KS1-X", "component_or_cover"),
        row("ND#KS1-Y", "component_or_cover"),
    ]
    uncovered = tmp / "uncovered_items.csv"
    pd.DataFrame(rows, columns=COLUMNS).to_csv(uncovered, index=False, encoding="utf-8-sig")
    summary = tmp / "catalog_coverage_summary.json"
    summary.write_text(json.dumps(dict(
        keys_in_pack=4014, items_in_pack=1627, catalog_items=6573,
        catalog_uncovered=len(rows), stock_uncovered=3, stock_uncovered_qty=55.0,
        reasons={r: sum(1 for x in rows if x["reason"] == r) for r in cn.REASONS},
    ), ensure_ascii=False), encoding="utf-8")
    return uncovered, summary


class CoverageActionTests(unittest.TestCase):
    def test_actions_cover_every_reason_and_reconcile(self):
        with tempfile.TemporaryDirectory() as tmp:
            uncovered_path, summary_path = fixture(Path(tmp))
            uncovered = cn.load_uncovered(uncovered_path)
            summary = cn.load_summary(summary_path)
            actions = cn.coverage_actions(uncovered, summary)
            self.assertEqual(set(actions["reason"]), set(cn.REASONS))
            self.assertEqual(int(actions["items"].sum()), summary["catalog_uncovered"])
            self.assertEqual(int(actions["stock_items"].sum()), summary["stock_uncovered"])
            self.assertEqual(float(actions["stock_qty"].sum()), summary["stock_uncovered_qty"])
            # 有库存那类必须是 P0 且由本层负责
            uom_row = actions[actions["reason"] == "stock_without_uom_evidence"].iloc[0]
            self.assertEqual(uom_row["priority"], "P0")
            self.assertEqual(uom_row["owner"], cn.ROLE_SUPPLY)
            # 组件/皮壳属业务口径，不由本层建 SKU
            cover = actions[actions["reason"] == "component_or_cover"].iloc[0]
            self.assertEqual(cover["owner"], cn.ROLE_BIZ)
            self.assertIn("不建独立", cover["action"])

    def test_unknown_reason_fails_loudly(self):
        with tempfile.TemporaryDirectory() as tmp:
            tmp = Path(tmp)
            rows = [row("KS-X", "brand_new_reason")]
            uncovered, summary = fixture(tmp, rows)
            with self.assertRaises(cn.InputError):
                cn.load_uncovered(uncovered)

    def test_mismatched_summary_fails(self):
        with tempfile.TemporaryDirectory() as tmp:
            uncovered_path, summary_path = fixture(Path(tmp))
            summary = cn.load_summary(summary_path)
            summary["stock_uncovered"] = 99
            with self.assertRaises(cn.InputError):
                cn.coverage_actions(cn.load_uncovered(uncovered_path), summary)

    def test_missing_columns_fail(self):
        with tempfile.TemporaryDirectory() as tmp:
            path = Path(tmp) / "bad.csv"
            pd.DataFrame([{"item": "KS1", "reason": "unmapped_no_evidence"}]).to_csv(
                path, index=False)
            with self.assertRaises(cn.InputError):
                cn.load_uncovered(path)


class UomPriorityTests(unittest.TestCase):
    def _priority(self):
        with tempfile.TemporaryDirectory() as tmp:
            uncovered_path, _ = fixture(Path(tmp))
            uncovered = cn.load_uncovered(uncovered_path)
        en = {"KS-UOM-1": dict(stock_uom="个", disabled=0),
              "KS-UOM-2": dict(stock_uom="个", disabled=1),
              "KS-UOM-3": dict(stock_uom=None, disabled=0)}
        return cn.uom_priority(uncovered, en, {"KS-UOM-3"})

    def test_only_stock_rows_sorted_by_qty(self):
        priority = self._priority()
        self.assertEqual(priority["item"].tolist(), ["KS-UOM-1", "KS-UOM-2", "KS-UOM-3"])
        self.assertEqual(priority["rank"].tolist(), [1, 2, 3])
        self.assertEqual(priority["cum_stock_qty"].tolist(), [30.0, 50.0, 55.0])

    def test_status_and_action_per_evidence(self):
        priority = self._priority().set_index("item")
        self.assertEqual(priority.loc["KS-UOM-1", "status"], "en_has_uom_cache_missing")
        self.assertIn("刷新 UOM 缓存", priority.loc["KS-UOM-1", "action"])
        self.assertEqual(priority.loc["KS-UOM-2", "status"], "en_item_disabled")
        self.assertIn("停售确认", priority.loc["KS-UOM-2", "action"])
        self.assertEqual(priority.loc["KS-UOM-3", "status"], "cache_hit")

    def test_missing_en_uom_goes_to_master_data(self):
        priority = cn.uom_priority(
            pd.DataFrame([row("KS-NO-EN", "stock_without_uom_evidence", 3.0)],
                         columns=COLUMNS), {}, set())
        self.assertEqual(priority.iloc[0]["status"], "en_uom_missing")
        self.assertIn("补 stock_uom", priority.iloc[0]["action"])


class BuildTests(unittest.TestCase):
    def test_build_writes_only_into_out_dir(self):
        with tempfile.TemporaryDirectory() as tmp:
            tmp = Path(tmp)
            uncovered_path, summary_path = fixture(tmp)
            en_items = tmp / "en.json"
            en_items.write_text(json.dumps({
                "KS-UOM-1": dict(stock_uom="个", disabled=0),
                "KS-UOM-2": dict(stock_uom="个", disabled=0),
                "KS-UOM-3": dict(stock_uom="个", disabled=1),
            }, ensure_ascii=False), encoding="utf-8")
            cache = tmp / "uom.parquet"
            pd.DataFrame([dict(item_code="OTHER", stock_uom="个")]).to_parquet(cache, index=False)
            out = tmp / "out"
            manifest = cn.build(uncovered_path, summary_path, en_items, cache, out)

            for name in ("coverage_actions.csv", "uom_unproven_priority.csv",
                         "report.md", "manifest.json"):
                self.assertTrue((out / name).is_file(), name)
            self.assertEqual(manifest["counts"]["uom_unproven_items"], 3)
            self.assertEqual(manifest["counts"]["uom_unproven_qty"], 55.0)
            self.assertEqual(manifest["counts"]["keys_in_pack"], 4014)
            self.assertEqual(set(manifest["inputs"]),
                             {str(uncovered_path), str(summary_path), str(en_items), str(cache)})
            text = (out / "report.md").read_text(encoding="utf-8")
            self.assertIn("不是公司全目录", text)
            self.assertIn("未覆盖 ≠ 零需求", text)
            self.assertIn("不改净额", text)
            self.assertEqual(sorted(p.name for p in tmp.iterdir()),
                             ["catalog_coverage_summary.json", "en.json", "out",
                              "uncovered_items.csv", "uom.parquet"])


if __name__ == "__main__":
    unittest.main()
