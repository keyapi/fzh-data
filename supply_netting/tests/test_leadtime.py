# -*- coding: utf-8 -*-
"""版本化交期配置：默认值冻结、缺文件/缺字段失败、消费方接线（A4）。"""

from __future__ import annotations

import copy
import hashlib
import importlib
import json
import tempfile
import unittest
from datetime import date, timedelta
from pathlib import Path

import pandas as pd

import supply_netting.leadtime as leadtime
import supply_netting.so_backlog as so_backlog
from supply_netting.leadtime import (ConfigAmbiguous, ConfigNotFound, ConfigSchemaError,
                                     ConfigVersionError, UnknownRoute, load_config,
                                     load_default_config)

AUDIT = date(2026, 10, 27)


def _raw() -> dict:
    return json.loads(leadtime.DEFAULT_CONFIG_PATH.read_text(encoding="utf-8"))


def _write(tmp, doc: dict) -> Path:
    path = Path(tmp) / "leadtime_config.json"
    path.write_text(json.dumps(doc, ensure_ascii=False), encoding="utf-8")
    return path


class FrozenValuesTests(unittest.TestCase):
    """接入只换来源、不改数字：默认配置必须与改造前的硬编码一致。"""

    def setUp(self):
        self.cfg = load_default_config()

    def test_pipeline_and_festival_values(self):
        pipeline, festival = self.cfg.so_pipeline, self.cfg.spring_festival
        self.assertEqual(pipeline.order_to_branch_days, 90)
        self.assertEqual(tuple(pipeline.order_to_branch_range_days), (75, 90))
        self.assertEqual(pipeline.stage_eta_assumption_days, 14)
        self.assertEqual(festival.anchor, date(2027, 2, 6))
        self.assertEqual((festival.shutdown_days, festival.recovery_days), (30, 30))
        self.assertEqual(festival.buffer_days, 60)
        self.assertEqual(festival.window_days, 30)

    def test_routes_keep_ship_production_sea(self):
        by_warehouse = {r.warehouse: r for r in self.cfg.routes}
        self.assertEqual(set(by_warehouse), {"美东-CENTRADE", "美中-FZH-DANEEY",
                                             "波兰-FZHPoland-covers"})
        self.assertEqual(by_warehouse["美东-CENTRADE"].segments,
                         dict(production=60, shipping=7, ocean=35))
        self.assertEqual(by_warehouse["波兰-FZHPoland-covers"].ocean_days, 40)
        self.assertEqual(self.cfg.shared_days("shipping"), 7)
        self.assertEqual(self.cfg.shared_days("production"), 60)

    def test_every_assumption_self_reports_provenance(self):
        blocks = [self.cfg.so_pipeline, self.cfg.spring_festival, *self.cfg.routes]
        for block in blocks:
            self.assertEqual(block.source, "assumed")
            self.assertEqual(block.sample_size, 0)

    def test_manifest_records_version_and_sources(self):
        manifest = self.cfg.to_manifest()
        self.assertEqual(manifest["version"], self.cfg.version)
        self.assertTrue(manifest["version"].startswith("2026-10-28"))
        self.assertEqual(manifest["effective_from"], "2026-10-27")
        self.assertEqual(manifest["config"], "supply_netting/config/leadtime_config.json")
        self.assertEqual(manifest["sha256"],
                         hashlib.sha256(leadtime.DEFAULT_CONFIG_PATH.read_bytes()).hexdigest())
        self.assertEqual(len(manifest["sha256"]), 64)
        self.assertEqual(manifest["sources"], ["assumed"])
        self.assertEqual(manifest["so_pipeline"]["source"], "assumed")
        self.assertEqual(manifest["so_pipeline"]["sample_size"], 0)
        self.assertEqual(len(manifest["routes"]), 3)
        self.assertEqual(manifest["routes"][0]["segments"],
                         dict(production=60, shipping=7, ocean=35))
        self.assertEqual(manifest["spring_festival"]["buffer_days"], 60)


class FailLoudTests(unittest.TestCase):
    def test_missing_file_raises(self):
        with tempfile.TemporaryDirectory() as tmp:
            with self.assertRaises(ConfigNotFound):
                load_config(Path(tmp) / "nope.json")

    def test_invalid_json_raises(self):
        with tempfile.TemporaryDirectory() as tmp:
            path = Path(tmp) / "x.json"
            path.write_text("{not json", encoding="utf-8")
            with self.assertRaises(leadtime.ConfigParseError):
                load_config(path)

    def test_missing_top_level_field_raises(self):
        with tempfile.TemporaryDirectory() as tmp:
            for key in ("version", "effective_from", "so_pipeline", "spring_festival",
                        "routes"):
                doc = _raw()
                del doc[key]
                with self.subTest(key=key), self.assertRaises(ConfigSchemaError) as ctx:
                    load_config(_write(tmp, doc))
                self.assertIn(key, ctx.exception.field)

    def test_missing_nested_field_raises(self):
        with tempfile.TemporaryDirectory() as tmp:
            cases = [
                ("so_pipeline", "order_to_branch_days"),
                ("so_pipeline", "order_to_branch_range_days"),
                ("so_pipeline", "stage_eta_assumption_days"),
                ("so_pipeline", "source"),
                ("so_pipeline", "sample_size"),
                ("so_pipeline", "notes"),
                ("spring_festival", "anchor"),
                ("spring_festival", "shutdown_days"),
                ("spring_festival", "recovery_days"),
                ("spring_festival", "window_days"),
                ("spring_festival", "source"),
                ("spring_festival", "sample_size"),
                ("spring_festival", "notes"),
            ]
            for block, key in cases:
                doc = _raw()
                del doc[block][key]
                with self.subTest(block=block, key=key), \
                        self.assertRaises(ConfigSchemaError) as ctx:
                    load_config(_write(tmp, doc))
                self.assertIn(key, ctx.exception.field)

    def test_missing_route_fields_raise(self):
        with tempfile.TemporaryDirectory() as tmp:
            for key in ("route_id", "warehouse", "mode", "segments", "source",
                        "sample_size", "notes"):
                doc = _raw()
                del doc["routes"][0][key]
                with self.subTest(key=key), self.assertRaises(ConfigSchemaError) as ctx:
                    load_config(_write(tmp, doc))
                self.assertIn(key, ctx.exception.field)
            for key in ("production", "shipping", "ocean"):
                doc = _raw()
                del doc["routes"][0]["segments"][key]
                with self.subTest(segment=key), self.assertRaises(ConfigSchemaError):
                    load_config(_write(tmp, doc))

    def test_measured_without_samples_is_rejected(self):
        with tempfile.TemporaryDirectory() as tmp:
            doc = _raw()
            doc["routes"][0]["source"] = "measured"
            doc["routes"][0]["sample_size"] = 0
            with self.assertRaises(ConfigSchemaError) as ctx:
                load_config(_write(tmp, doc))
            self.assertEqual(ctx.exception.field, "routes[0].sample_size")

    def test_range_must_contain_baseline(self):
        with tempfile.TemporaryDirectory() as tmp:
            doc = _raw()
            doc["so_pipeline"]["order_to_branch_range_days"] = [60, 80]
            with self.assertRaises(ConfigSchemaError):
                load_config(_write(tmp, doc))

    def test_duplicate_route_conflicts(self):
        with tempfile.TemporaryDirectory() as tmp:
            doc = _raw()
            doc["routes"].append(copy.deepcopy(doc["routes"][0]))
            with self.assertRaises(ConfigSchemaError) as ctx:
                load_config(_write(tmp, doc))
            self.assertEqual(ctx.exception.field, "routes[3]")

    def test_unknown_mode_rejected(self):
        with tempfile.TemporaryDirectory() as tmp:
            doc = _raw()
            doc["routes"][0]["mode"] = "teleport"
            with self.assertRaises(ConfigSchemaError):
                load_config(_write(tmp, doc))

    def test_version_format_and_pin(self):
        with tempfile.TemporaryDirectory() as tmp:
            doc = _raw()
            doc["version"] = "v1"
            with self.assertRaises(ConfigVersionError):
                load_config(_write(tmp, doc))
            doc = _raw()
            path = _write(tmp, doc)
            with self.assertRaises(ConfigVersionError):
                load_config(path, expected_version="1999-01-01.1")

    def test_unknown_fields_warn_but_load(self):
        with tempfile.TemporaryDirectory() as tmp:
            doc = _raw()
            doc["future_flag"] = True
            doc["routes"][0]["leadtime_p95"] = 45
            cfg = load_config(_write(tmp, doc))
            joined = "\n".join(cfg.warnings)
            self.assertIn("future_flag", joined)
            self.assertIn("leadtime_p95", joined)


class LookupTests(unittest.TestCase):
    def setUp(self):
        self.cfg = load_default_config()

    def test_unknown_warehouse_raises_instead_of_guessing(self):
        with self.assertRaises(UnknownRoute):
            self.cfg.route_for("美西-不存在")

    def test_ambiguous_warehouse_requires_mode(self):
        with tempfile.TemporaryDirectory() as tmp:
            doc = _raw()
            twin = copy.deepcopy(doc["routes"][0])
            twin["mode"] = "air"
            doc["routes"].append(twin)
            cfg = load_config(_write(tmp, doc))
            with self.assertRaises(ConfigAmbiguous):
                cfg.route_for("美东-CENTRADE")
            self.assertEqual(cfg.route_for("美东-CENTRADE", mode="air").mode, "air")

    def test_shared_days_refuses_mixed_routes(self):
        with tempfile.TemporaryDirectory() as tmp:
            doc = _raw()
            doc["routes"][2]["segments"]["ocean"] = 45
            cfg = load_config(_write(tmp, doc))
            with self.assertRaises(ConfigSchemaError):
                cfg.shared_days("ocean")


class ConsumerWiringTests(unittest.TestCase):
    """两个消费方都从配置取值，而不是各留一份硬编码。"""

    def setUp(self):
        self.cfg = load_default_config()

    def test_so_backlog_constants_come_from_config(self):
        self.assertEqual(so_backlog.BASELINE_ORDER_TO_BRANCH_DAYS,
                         self.cfg.so_pipeline.order_to_branch_days)
        self.assertEqual(so_backlog.BASELINE_RANGE_DAYS,
                         tuple(self.cfg.so_pipeline.order_to_branch_range_days))
        self.assertEqual(so_backlog.SPRING_FESTIVAL_ANCHOR, self.cfg.spring_festival.anchor)
        self.assertEqual(so_backlog.SPRING_FESTIVAL_BUFFER_DAYS,
                         self.cfg.spring_festival.buffer_days)

    def test_so_backlog_summary_carries_version_and_source(self):
        import pandas as pd
        frame = so_backlog.build_so_backlog(pd.DataFrame(
            [dict(so="SO1", customer="DANEEY", delivery_date="2026-12-01",
                  item_code="KS1", customer_item_code="TT1",
                  warehouse="成品仓 - FZH", open_qty=5)],
            columns=["so", "customer", "delivery_date", "item_code",
                     "customer_item_code", "warehouse", "open_qty"]), as_of=AUDIT)
        summary = so_backlog.summarize_backlog(frame)
        self.assertEqual(summary["leadtime_config"]["version"], self.cfg.version)
        self.assertEqual(summary["leadtime_config"]["sources"], ["assumed"])
        self.assertEqual(summary["order_to_branch_days"],
                         self.cfg.so_pipeline.order_to_branch_days)

    def test_plan_dates_uses_config_segments_and_names_version(self):
        from supply_netting.scripts.so_conditional_supply import plan_dates
        route = self.cfg.route_for("波兰-FZHPoland-covers")
        pending = plan_dates("produced_pending_dn", AUDIT, "波兰-FZHPoland-covers")
        expected = AUDIT + timedelta(days=route.shipping_days + route.ocean_days)
        self.assertEqual(pending["eta_earliest"], expected.isoformat())
        self.assertEqual(pending["confidence"], "assumed")
        self.assertIn(self.cfg.version, pending["eta_basis"])
        in_production = plan_dates("in_production", AUDIT, "波兰-FZHPoland-covers")
        self.assertIn(f"生产{route.production_days}", in_production["eta_basis"])

    def test_consumer_import_fails_without_config(self):
        """配置缺失时消费方 import 即失败（无内置默认值兜底）。"""
        original = leadtime.DEFAULT_CONFIG_PATH
        with tempfile.TemporaryDirectory() as tmp:
            leadtime.DEFAULT_CONFIG_PATH = Path(tmp) / "missing.json"
            try:
                with self.assertRaises(ConfigNotFound):
                    importlib.reload(so_backlog)
            finally:
                leadtime.DEFAULT_CONFIG_PATH = original
                importlib.reload(so_backlog)
        self.assertEqual(so_backlog.BASELINE_ORDER_TO_BRANCH_DAYS, 90)


class HashTests(unittest.TestCase):
    """哈希按被解析的同一份字节算；改了文件哈希就变。"""

    def test_hash_comes_from_parsed_bytes(self):
        cfg = load_default_config()
        self.assertEqual(cfg.to_manifest()["sha256"], cfg.config_sha256)
        self.assertEqual(cfg.config_sha256,
                         hashlib.sha256(leadtime.DEFAULT_CONFIG_PATH.read_bytes()).hexdigest())

    def test_editing_file_changes_hash(self):
        with tempfile.TemporaryDirectory() as tmp:
            doc = _raw()
            before = load_config(_write(tmp, doc)).config_sha256
            doc["routes"][2]["segments"]["ocean"] = 41
            after = load_config(_write(tmp, doc)).config_sha256
            self.assertNotEqual(before, after)


class V3ManifestTests(unittest.TestCase):
    """v3 的日期来自同一份配置，manifest 必须带上版本 + 哈希 + 来源 + 样本量。"""

    def _w1(self, path: Path) -> None:
        payload = {
            "so": "SO-1", "as_of": AUDIT.isoformat(), "links": [],
            "lines": [dict(so="SO-1", so_line="L1", item_code="KS1", customer="美东公司（CENTADE）",
                           qty=100.0, delivered_qty=0.0, uom="个", warehouse="成品仓 - FZH",
                           scope="in_house", role="finished")],
            "stage_balances": [dict(so="SO-1", so_line_id="L1", item_code="KS1",
                                    warehouse="成品仓 - FZH", uom="个", stage="in_production",
                                    stage_detail="", qty=10.0, qty_status="known",
                                    qty_basis="", cumulative_excess_qty=None, batch_key="WO-1",
                                    source_record="WO-1", exclusion_reason="",
                                    included_in_stock="unknown", demand_status="active",
                                    scope="in_house", role="finished")],
        }
        path.write_text(json.dumps({"so": "SO-1", "payload": payload}, ensure_ascii=False) + "\n",
                        encoding="utf-8")

    def test_v3_manifest_records_leadtime_version_hash_source(self):
        from supply_netting.scripts import so_conditional_supply_v3 as v3
        from supply_netting.scripts.so_conditional_supply import plan_dates

        cfg = load_default_config()
        with tempfile.TemporaryDirectory() as tmp:
            tmp = Path(tmp)
            w1, cache, out = tmp / "w1.jsonl", tmp / "uom.parquet", tmp / "out"
            self._w1(w1)
            pd.DataFrame([dict(item_code="KS1", stock_uom="个")]).to_parquet(cache, index=False)
            v3.main(["--w1", str(w1), "--out", str(out), "--uom-cache", str(cache),
                     "--role-csv", "", "--windows", "", "--v2", "", "--conservation-v2", ""])

            manifest = json.loads((out / "so_conditional_supply_v3_manifest.json")
                                  .read_text(encoding="utf-8"))
            block = manifest["leadtime_config"]
            self.assertEqual(block["version"], cfg.version)
            self.assertEqual(block["sha256"], cfg.config_sha256)
            self.assertEqual(block["sources"], ["assumed"])
            self.assertEqual(block["so_pipeline"]["sample_size"], 0)
            self.assertEqual(block["spring_festival"]["source"], "assumed")
            self.assertEqual(manifest["offset_allowed"], False)

            # 日期数值不变：与 plan_dates 逐值一致
            tranches = pd.read_csv(out / "so_supply_tranches_v3.csv", encoding="utf-8-sig")
            dated = tranches[tranches["eta_earliest"].notna()].iloc[0]
            expected = plan_dates("in_production", AUDIT, "美东-CENTRADE")
            self.assertEqual(dated["eta_earliest"], expected["eta_earliest"])
            self.assertEqual(dated["eta_latest"], expected["eta_latest"])
            self.assertEqual(dated["candidate_qty"], 10.0)


if __name__ == "__main__":
    unittest.main()
