#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""stock_history_ingest.py 的验收测试（方案 v4，14 条验收 + 补充用例）。

真实两天数据的用例只在 D:/Work/库存备份 存在时运行（直接只读，不复制、不提交）；
其余全部使用临时目录里的合成小样本。

运行：
  cd docs/research/supply-chain/2026-10-20/claude/experiments/g1_contract
  uv run python -m unittest -v test_stock_history_ingest.py
"""

from __future__ import annotations

import json
import os
import shutil
import subprocess
import sys
import tempfile
import time
import unittest
from datetime import date, datetime, timedelta, timezone
from pathlib import Path

import duckdb

import stock_history_ingest as ing

HERE = Path(__file__).resolve().parent
SCRIPT = HERE / "stock_history_ingest.py"
REAL_ROOT = Path(os.environ.get("STOCK_BACKUP_ROOT", r"D:/Work/库存备份"))
DAY_20 = REAL_ROOT / "2026-10-20"
DAY_21 = REAL_ROOT / "2026-10-21"

# 固定 SHA256 基线（2026-10-21 首次记录；与 docs 中的基线表一致）。
REAL_MANIFEST_SHA = {
    "2026-10-20": "186498757a79b1325edff8314d90208ca616a9955393317366b4d52e81f57828",
    "2026-10-21": "4dd9bbfde0ffdcb6df64e3dc1c8761a7226a8053d931d29dad62aa77274b2ed7",
}

_MISSING = object()


# --------------------------------------------------------------------------- #
# 合成样本
# --------------------------------------------------------------------------- #


def row(
    sku: str,
    goods_id: str,
    warehouse_id: str,
    *,
    available: float = 0,
    intransit: float = 0,
    defects: float = 0,
    waiting: float = 0,
    warehouse_name: str = "",
) -> dict:
    return {
        "goodsSku": sku,
        "warehouseName": warehouse_name,
        "availableStockQuantity": available,
        "intransitStockQuantity": intransit,
        "defectsStockQuantity": defects,
        "waitingShipmentStockQuantity": waiting,
        "goodsIdKey": goods_id,
        "warehouseIdKey": warehouse_id,
    }


def warehouse(
    warehouse_id: str,
    name: str,
    rows: list[dict],
    *,
    complete: bool = True,
    manifest_rows=_MISSING,
    include_file: bool = True,
    error: str | None = None,
    truncated: bool = False,
    file_hint: str | None = None,
) -> dict:
    for item in rows:
        if not item.get("warehouseName"):
            item["warehouseName"] = name
    return {
        "id": warehouse_id,
        "name": name,
        "rows": rows,
        "complete": complete,
        "manifest_rows": len(rows) if manifest_rows is _MISSING else manifest_rows,
        "include_file": include_file,
        "error": error,
        "truncated": truncated,
        "file_hint": file_hint,
    }


def _file_name(warehouse_id: str, name: str) -> str:
    return f"warehouse={warehouse_id}_{name}.jsonl"


def make_run(
    root: Path,
    dirname: str,
    snapshot_at: str,
    warehouses: list[dict],
    *,
    complete: bool = True,
    run_id: str | None = None,
    seal: bool = True,
    manifest_date: str | None = None,
    started_at: str | None = None,
    ended_at: str | None = None,
    exit_code: int = 0,
    trigger: str = "test",
) -> Path:
    """生成一个 run 目录：JSONL + manifest +（可选）run_meta + .sealed。"""
    run_dir = root / dirname
    run_dir.mkdir(parents=True, exist_ok=True)

    snapshot_local = ing.parse_local_datetime(snapshot_at)
    entries = []
    for spec in warehouses:
        entry: dict = {
            "warehouseId": spec["id"],
            "warehouseName": spec["name"],
            "pages": 1,
            "bad_rows": 0,
            "complete": spec["complete"],
            "truncated": spec["truncated"],
            "capture_start": snapshot_at,
            "capture_end": snapshot_at,
        }
        if spec["include_file"]:
            name = _file_name(spec["id"], spec["name"])
            path = run_dir / name
            with path.open("w", encoding="utf-8", newline="\n") as fh:
                for item in spec["rows"]:
                    fh.write(json.dumps(item, ensure_ascii=False) + "\n")
            entry["file"] = spec["file_hint"] or str(path)
            entry["rows"] = spec["manifest_rows"]
        if spec["error"]:
            entry["error"] = spec["error"]
        entries.append(entry)

    manifest = {
        "snapshot_date": manifest_date or snapshot_local.date().isoformat(),
        "snapshot_at": snapshot_at,
        "source": "synthetic",
        "requests": 1,
        "warehouses": entries,
        "complete": complete,
    }
    manifest_path = run_dir / "manifest.json"
    manifest_path.write_text(
        json.dumps(manifest, ensure_ascii=False, indent=2) + "\n", encoding="utf-8"
    )

    if run_id is not None:
        files = {"manifest.json": ing.sha256_file(manifest_path)}
        for spec in warehouses:
            if spec["include_file"]:
                path = run_dir / _file_name(spec["id"], spec["name"])
                files[path.name] = ing.sha256_file(path)
        run_meta = {
            "run_id": run_id,
            "snapshot_date": manifest["snapshot_date"],
            "started_at": started_at or snapshot_at,
            "ended_at": ended_at or snapshot_at,
            "exit_code": exit_code,
            "trigger": trigger,
            "manifest_sha256": files["manifest.json"],
            "files": [{"path": name, "sha256": sha} for name, sha in sorted(files.items())],
        }
        (run_dir / "run_meta.json").write_text(
            json.dumps(run_meta, ensure_ascii=False, indent=2) + "\n", encoding="utf-8"
        )

        if seal:
            seal_payload = {
                "run_id": run_id,
                "sealed_at": datetime.now(timezone.utc).isoformat(),
                "manifest_sha256": files["manifest.json"],
                "files": files,
            }
            (run_dir / ".sealed").write_text(
                json.dumps(seal_payload, ensure_ascii=False, indent=2) + "\n", encoding="utf-8"
            )
    return run_dir


def memory_db() -> "duckdb.DuckDBPyConnection":
    conn = duckdb.connect(":memory:")
    ing.migrate(conn)
    return conn


def publish(conn, bundle, now: datetime | None = None) -> dict:
    ing.stage_run(conn, bundle, now=now)
    decision = ing.evaluate_publish(conn, bundle)
    if decision["action"] == "publish":
        ing.materialize(
            conn, bundle.snapshot_date, bundle.run_id, decision.get("previous_run_id")
        )
    else:
        ing.record_decision(conn, bundle, decision)
    return decision


def history_rows(conn):
    return conn.execute(
        "SELECT snapshot_date, run_id, warehouse_id, goods_id, goods_sku, warehouse_name,"
        " available, intransit, defects, waiting_shipment, batch_complete, is_test,"
        " stockout_observed, uom_basis FROM stock_history"
        " ORDER BY snapshot_date, warehouse_id, goods_id"
    ).fetchall()


def expected_rows_from_run(conn, run_id: str):
    return conn.execute(
        "SELECT snapshot_date, run_id, warehouse_id, goods_id, goods_sku, warehouse_name,"
        " available, intransit, defects, waiting_shipment, batch_complete, is_test,"
        " (batch_complete AND available = 0), uom_basis FROM stock_history_run"
        " WHERE run_id = ? ORDER BY snapshot_date, warehouse_id, goods_id",
        [run_id],
    ).fetchall()


def expected_rows_from_bundle(bundle) -> list[tuple]:
    rows = []
    for wh in bundle.warehouses:
        for item in wh.records:
            rows.append(
                (
                    bundle.snapshot_date,
                    bundle.run_id,
                    item["warehouse_id"],
                    item["goods_id"],
                    item["goods_sku"],
                    item["warehouse_name"],
                    item["available"],
                    item["intransit"],
                    item["defects"],
                    item["waiting_shipment"],
                    wh.batch_complete,
                    item["is_test"],
                    bool(wh.batch_complete and item["available"] == 0),
                    item["uom_basis"],
                )
            )
    return sorted(rows, key=lambda r: (r[0], r[2], r[3]))


class TempCase(unittest.TestCase):
    def setUp(self) -> None:
        self._tmp = tempfile.TemporaryDirectory(prefix="stock_ingest_")
        self.tmp = Path(self._tmp.name)

    def tearDown(self) -> None:
        self._tmp.cleanup()

    def simple_run(
        self,
        dirname: str = "2026-10-21",
        snapshot_at: str = "2026-10-21T09:46:23",
        rows_per_warehouse: int = 3,
        *,
        run_id: str | None = "run-20261021T094623-aaaaaa",
        seal: bool = True,
        **kwargs,
    ) -> Path:
        wings = []
        for index, wid in enumerate(("W1", "W2")):
            rows = [
                row(f"SKU-{wid}-{n}", f"G{wid}{n}", wid, available=n, warehouse_name=f"WH-{wid}")
                for n in range(rows_per_warehouse)
            ]
            wings.append(warehouse(wid, f"WH-{wid}", rows))
        return make_run(
            self.tmp,
            dirname,
            snapshot_at,
            wings,
            run_id=run_id,
            seal=seal,
            **kwargs,
        )


# --------------------------------------------------------------------------- #
# 14 条验收
# --------------------------------------------------------------------------- #


class AcceptanceTests(TempCase):
    def test_a01_reimport_same_run_is_idempotent(self) -> None:
        """验收 1：同一 run 重复导入 → 行数/内容不变，published 不变。"""
        run_dir = self.simple_run()
        first = ing.load_run(run_dir, source="scheduled")
        second = ing.load_run(run_dir, source="scheduled")
        self.assertEqual(first.run_id, second.run_id)
        self.assertEqual(first.run_id, "run-20261021T094623-aaaaaa")

        conn = memory_db()
        try:
            now = datetime(2026, 10, 21, 2, 0, 0)
            ing.stage_run(conn, first, now=now)
            ing.materialize(conn, first.snapshot_date, first.run_id, None)
            before_history = history_rows(conn)
            before_run_rows = expected_rows_from_run(conn, first.run_id)
            ingested_before = conn.execute(
                "SELECT ingested_at FROM stock_run WHERE run_id = ?", [first.run_id]
            ).fetchone()[0]

            ing.stage_run(conn, first, now=now + timedelta(hours=1))
            decision = ing.evaluate_publish(conn, first)
            self.assertEqual(decision["action"], "already")

            self.assertEqual(history_rows(conn), before_history)
            self.assertEqual(expected_rows_from_run(conn, first.run_id), before_run_rows)
            self.assertEqual(
                conn.execute("SELECT COUNT(*) FROM stock_run WHERE run_id = ?", [first.run_id]).fetchone()[0],
                1,
            )
            self.assertEqual(
                conn.execute(
                    "SELECT ingested_at FROM stock_run WHERE run_id = ?", [first.run_id]
                ).fetchone()[0],
                ingested_before,
                "重复导入不应刷新 ingested_at",
            )
        finally:
            conn.close()

    @unittest.skipUnless(DAY_20.is_dir(), f"真实数据缺失: {DAY_20}")
    def test_a02_real_2026_10_20_incomplete_day(self) -> None:
        """验收 2：10-20 退货仓 400 行部分批次；13/14 完整；不是完整日。"""
        bundle = ing.load_run(DAY_20, source="legacy")
        self.assertEqual(bundle.snapshot_date, date(2026, 10, 20))
        self.assertEqual(bundle.manifest_sha256, REAL_MANIFEST_SHA["2026-10-20"])
        self.assertTrue(bundle.run_id.startswith("legacy-20261020T181947-"))
        self.assertEqual(len(bundle.warehouses), 14)
        self.assertEqual(bundle.rows_read, 5192)
        self.assertEqual(bundle.rows_ingested, 5192)
        self.assertEqual(bundle.bad_rows, 0)
        self.assertEqual(bundle.duplicate_rows, 0)
        self.assertEqual(bundle.scope_coverage, 13)
        self.assertFalse(bundle.scope_complete)
        self.assertFalse(bundle.run_complete)
        self.assertFalse(bundle.sealed)
        self.assertEqual(bundle.sealing_exemption, "legacy")
        self.assertTrue(bundle.integrity_ok, bundle.integrity_errors)

        failed = [w for w in bundle.warehouses if w.warehouse_id == "6464013595202406110001248096"]
        self.assertEqual(len(failed), 1)
        self.assertEqual(failed[0].warehouse_name, "美中-FZH-DANEEY-退货产品仓")
        self.assertEqual(failed[0].rows_read, 400)
        self.assertEqual(failed[0].unique_rows, 400)
        self.assertFalse(failed[0].batch_complete)
        self.assertEqual(failed[0].manifest_rows, None)
        self.assertIn("URLError", failed[0].manifest_error or "")
        complete = [w for w in bundle.warehouses if w.batch_complete]
        self.assertEqual(len(complete), 13)
        self.assertTrue(all(w.manifest_rows == w.rows_read for w in complete))

        conn = memory_db()
        try:
            decision = publish(conn, bundle)
            self.assertEqual(decision["action"], "publish")
            report = ing.build_report(bundle, decision, dry_run=False)
            self.assertFalse(report["complete_day"], "10-20 不能标记为完整日")
            self.assertEqual(
                conn.execute("SELECT COUNT(*) FROM stock_history").fetchone()[0], 5192
            )
            self.assertEqual(
                conn.execute("SELECT COUNT(*) FROM v_stock_history_analysis").fetchone()[0],
                5190,
                "TEST-1 的 2 行应从分析视图排除",
            )
        finally:
            conn.close()

    @unittest.skipUnless(DAY_21.is_dir(), f"真实数据缺失: {DAY_21}")
    def test_a03_real_2026_10_21_complete_day(self) -> None:
        """验收 3：10-21 → 5,314 行、14 仓 complete、run_complete=true。"""
        bundle = ing.load_run(DAY_21, source="legacy")
        self.assertEqual(bundle.snapshot_date, date(2026, 10, 21))
        self.assertEqual(bundle.manifest_sha256, REAL_MANIFEST_SHA["2026-10-21"])
        self.assertTrue(bundle.run_id.startswith("legacy-20261021T094623-"))
        self.assertEqual(bundle.rows_read, 5314)
        self.assertEqual(bundle.rows_ingested, 5314)
        self.assertEqual(bundle.bad_rows, 0)
        self.assertEqual(bundle.duplicate_rows, 0)
        self.assertEqual(bundle.scope_coverage, 14)
        self.assertTrue(bundle.scope_complete)
        self.assertTrue(bundle.run_complete)
        self.assertTrue(bundle.integrity_ok, bundle.integrity_errors)
        self.assertEqual(bundle.test_sku_rows, 2)
        # manifest 里的绝对路径指向旧目录 D:\Work\fzh-inventory，入库按 basename 解析。
        raw_manifest = json.loads((DAY_21 / "manifest.json").read_text(encoding="utf-8"))
        self.assertIn("fzh-inventory", raw_manifest["warehouses"][0]["file"])
        self.assertTrue(Path(bundle.warehouses[0].file_path).is_relative_to(DAY_21))

        conn = memory_db()
        try:
            decision = publish(conn, bundle)
            self.assertEqual(decision["action"], "publish")
            report = ing.build_report(bundle, decision, dry_run=False)
            self.assertTrue(report["complete_day"])
            self.assertEqual(conn.execute("SELECT COUNT(*) FROM stock_history").fetchone()[0], 5314)
            self.assertEqual(
                conn.execute("SELECT COUNT(*) FROM v_stock_history_analysis").fetchone()[0], 5312
            )
            published = ing.get_publish(conn, bundle.snapshot_date)
            self.assertEqual(published["run_id"], bundle.run_id)
        finally:
            conn.close()

    def test_a04_complete_then_incomplete_keeps_complete(self) -> None:
        """验收 4：完整→不完整、反序导入 → published 仍指向完整 run。"""
        complete_dir = self.simple_run(
            dirname="2026-10-21",
            run_id="run-20261021T090000-aaaaaa",
            ended_at="2026-10-21T09:30:00",
        )
        partial_dir = make_run(
            self.tmp,
            "2026-10-21-partial",
            "2026-10-21T10:00:00",
            [
                warehouse("W1", "WH-W1", [row("SKU-1", "G1", "W1", available=1)]),
                warehouse(
                    "W2",
                    "WH-W2",
                    [],
                    complete=False,
                    include_file=False,
                    manifest_rows=None,
                    error="URLError: boom",
                ),
            ],
            complete=False,
            run_id="run-20261021T100000-bbbbbb",
            ended_at="2026-10-21T12:00:00",
        )
        complete = ing.load_run(complete_dir, source="scheduled")
        partial = ing.load_run(partial_dir, source="scheduled")
        self.assertTrue(complete.run_complete)
        self.assertFalse(partial.run_complete)

        for order in (("complete", "partial"), ("partial", "complete")):
            conn = memory_db()
            try:
                bundles = {"complete": complete, "partial": partial}
                for name in order:
                    publish(conn, bundles[name])
                published = ing.get_publish(conn, date(2026, 10, 21))
                self.assertEqual(
                    published["run_id"], complete.run_id, f"导入顺序 {order} 结果不一致"
                )
                self.assertEqual(history_rows(conn), expected_rows_from_bundle(complete))
            finally:
                conn.close()

    def test_a05_incomplete_then_complete_atomic_switch(self) -> None:
        """验收 5：不完整→完整 → 原子切换；旧行无残留（逐行比对）。"""
        partial_dir = make_run(
            self.tmp,
            "2026-10-21-partial",
            "2026-10-21T08:00:00",
            [
                warehouse("W1", "WH-W1", [row("SKU-P", "GP", "W1", available=9)]),
                warehouse(
                    "W2", "WH-W2", [], complete=False, include_file=False,
                    manifest_rows=None, error="timeout",
                ),
            ],
            complete=False,
            run_id="run-20261021T080000-cccccc",
            ended_at="2026-10-21T08:10:00",
        )
        complete_dir = self.simple_run(
            dirname="2026-10-21",
            run_id="run-20261021T090000-dddddd",
            ended_at="2026-10-21T09:30:00",
        )
        partial = ing.load_run(partial_dir, source="scheduled")
        complete = ing.load_run(complete_dir, source="scheduled")

        conn = memory_db()
        try:
            publish(conn, partial)
            self.assertEqual(ing.get_publish(conn, date(2026, 10, 21))["run_id"], partial.run_id)
            decision = publish(conn, complete)
            self.assertEqual(decision["action"], "publish")
            self.assertEqual(decision["previous_run_id"], partial.run_id)
            self.assertEqual(history_rows(conn), expected_rows_from_bundle(complete))
            leftover = conn.execute(
                "SELECT COUNT(*) FROM stock_history WHERE run_id = ?", [partial.run_id]
            ).fetchone()[0]
            self.assertEqual(leftover, 0, "旧 run 的行不得残留在 published 表")
            published = ing.get_publish(conn, date(2026, 10, 21))
            self.assertEqual(published["run_id"], complete.run_id)
            self.assertEqual(published["previous_run_id"], partial.run_id)
        finally:
            conn.close()

    def test_a06_empty_vs_unknown(self) -> None:
        """验收 6：成功空仓 complete；缺文件 unknown，不写 0。"""
        run_dir = make_run(
            self.tmp,
            "2026-10-21",
            "2026-10-21T09:00:00",
            [
                warehouse("EMPTY", "空仓", []),
                warehouse(
                    "MISSING", "缺文件仓", [], complete=False, include_file=False,
                    manifest_rows=None, error="URLError: 10060",
                ),
            ],
            complete=False,
            run_id="run-20261021T090000-eeeeee",
        )
        bundle = ing.load_run(run_dir, source="scheduled")
        empty, missing = bundle.warehouses
        self.assertTrue(empty.batch_complete)
        self.assertEqual(empty.rows_read, 0)
        self.assertFalse(missing.batch_complete)
        self.assertIsNone(missing.file_sha256)
        self.assertTrue(bundle.integrity_ok, bundle.integrity_errors)

        conn = memory_db()
        try:
            publish(conn, bundle)
            states = conn.execute(
                "SELECT warehouse_id, rows, complete FROM stock_run_warehouse"
                " WHERE run_id = ? ORDER BY warehouse_id",
                [bundle.run_id],
            ).fetchall()
            self.assertEqual(
                states, [("EMPTY", 0, True), ("MISSING", 0, False)],
                "空仓 complete=true；缺文件 complete=false（unknown）",
            )
            self.assertEqual(
                conn.execute("SELECT COUNT(*) FROM stock_history").fetchone()[0], 0,
                "空仓/未知都不得写入 0 行观测",
            )
        finally:
            conn.close()

    def test_a07_multirun_tie_break_is_order_independent(self) -> None:
        """验收 7：同日平局按 run_id 字典序最大，反序导入一致。"""
        dir_a = self.simple_run(
            dirname="2026-10-21-a",
            run_id="run-20261021T090000-aaaaaa",
            ended_at="2026-10-21T09:30:00",
        )
        dir_z = self.simple_run(
            dirname="2026-10-21-z",
            run_id="run-20261021T090000-zzzzzz",
            ended_at="2026-10-21T09:30:00",
            rows_per_warehouse=2,
        )
        a = ing.load_run(dir_a, source="scheduled")
        z = ing.load_run(dir_z, source="scheduled")
        self.assertEqual(a.rank_key()[:3], z.rank_key()[:3])
        self.assertEqual(a.rank_key()[3], z.rank_key()[3])

        outcomes = []
        for order in ((a, z), (z, a)):
            conn = memory_db()
            try:
                for bundle in order:
                    publish(conn, bundle)
                outcomes.append(ing.get_publish(conn, date(2026, 10, 21))["run_id"])
            finally:
                conn.close()
        self.assertEqual(outcomes, [z.run_id, z.run_id])

    def test_a08_alias_and_duplicate_conflicts_rejected_with_evidence(self) -> None:
        """验收 8：别名/重复键数值冲突 → 拒绝发布并保留证据。"""
        alias_dir = make_run(
            self.tmp,
            "alias",
            "2026-10-21T09:00:00",
            [
                warehouse("W1", "WH-1", [row("SAME-SKU", "G1", "W1", available=1)]),
                warehouse("W2", "WH-2", [row("SAME-SKU", "G2", "W2", available=2)]),
            ],
            run_id="run-20261021T090000-aaaaaa",
        )
        alias_bundle = ing.load_run(alias_dir, source="scheduled")
        self.assertTrue(alias_bundle.integrity_ok)
        self.assertEqual(len(ing.alias_conflicts(alias_bundle)), 1)

        conn = memory_db()
        try:
            decision = publish(conn, alias_bundle)
            self.assertEqual(decision["action"], "reject")
            self.assertEqual(decision["reason"], "integrity_or_alias_conflict")
            self.assertEqual(conn.execute("SELECT COUNT(*) FROM stock_history").fetchone()[0], 0)
            self.assertGreater(
                conn.execute("SELECT COUNT(*) FROM stock_ingest_event").fetchone()[0], 0
            )
        finally:
            conn.close()

        conflict_dir = make_run(
            self.tmp,
            "dup-conflict",
            "2026-10-21T09:00:00",
            [
                warehouse(
                    "W1",
                    "WH-1",
                    [
                        row("SKU-A", "G1", "W1", available=1),
                        row("SKU-A", "G1", "W1", available=2),
                    ],
                )
            ],
            run_id="run-20261021T090000-bbbbbb",
        )
        conflict_bundle = ing.load_run(conflict_dir, source="scheduled")
        self.assertFalse(conflict_bundle.integrity_ok)
        self.assertEqual(conflict_bundle.warehouses[0].rows_read, 2)
        self.assertEqual(conflict_bundle.warehouses[0].duplicate_rows, 0)
        conn = memory_db()
        try:
            ing.stage_run(conn, conflict_bundle)
            decision = ing.evaluate_publish(conn, conflict_bundle)
            self.assertEqual(decision["action"], "reject")
            self.assertEqual(
                conn.execute(
                    "SELECT COUNT(*) FROM stock_history_run WHERE run_id = ?",
                    [conflict_bundle.run_id],
                ).fetchone()[0],
                0,
                "冲突 run 不得入库任意一条候选值",
            )
            stored = conn.execute(
                "SELECT integrity_ok FROM stock_run WHERE run_id = ?", [conflict_bundle.run_id]
            ).fetchone()
            self.assertEqual(stored, (False,), "拒绝证据（含哈希）必须保留在 stock_run")
            events = conn.execute(
                "SELECT action, detail FROM stock_ingest_event WHERE run_id = ?",
                [conflict_bundle.run_id],
            ).fetchall()
            self.assertTrue(any(a == "integrity_rejected" for a, _ in events))
            self.assertIn("duplicate_value_conflict", " ".join(d for _, d in events))
        finally:
            conn.close()

        # 数值一致的重复键：允许，去重计数
        dedup_dir = make_run(
            self.tmp,
            "dup-consistent",
            "2026-10-21T09:00:00",
            [
                warehouse(
                    "W1",
                    "WH-1",
                    [
                        row("SKU-A", "G1", "W1", available=1),
                        row("SKU-A", "G1", "W1", available=1),
                    ],
                )
            ],
            run_id="run-20261021T090000-cccccc",
        )
        dedup_bundle = ing.load_run(dedup_dir, source="scheduled")
        self.assertTrue(dedup_bundle.integrity_ok)
        self.assertEqual(dedup_bundle.duplicate_rows, 1)
        conn = memory_db()
        try:
            decision = publish(conn, dedup_bundle)
            self.assertEqual(decision["action"], "publish")
            self.assertEqual(conn.execute("SELECT COUNT(*) FROM stock_history").fetchone()[0], 1)
        finally:
            conn.close()

        # 同一 goods_id 多别名：允许，并进入 stock_id_history
        multi_alias_dir = make_run(
            self.tmp,
            "multi-alias",
            "2026-10-21T09:00:00",
            [
                warehouse(
                    "W1",
                    "WH-1",
                    [
                        row("SKU-OLD", "G1", "W1", available=1),
                        row("SKU-NEW", "G1", "W1", available=1),
                    ],
                )
            ],
            run_id="run-20261021T090000-dddddd",
        )
        multi_alias = ing.load_run(multi_alias_dir, source="scheduled")
        self.assertTrue(multi_alias.integrity_ok)
        self.assertEqual(len(ing.id_aliases(multi_alias)), 1)
        conn = memory_db()
        try:
            publish(conn, multi_alias)
            names = {
                r[0]
                for r in conn.execute(
                    "SELECT name FROM stock_id_history WHERE entity_type='goods' AND entity_id='G1'"
                ).fetchall()
            }
            self.assertEqual(names, {"SKU-OLD", "SKU-NEW"})
        finally:
            conn.close()

    def test_a09_hash_anomaly_rejected(self) -> None:
        """验收 9：哈希异常 → 拒绝发布（封存清单 + 外部基线两种来源）。"""
        run_dir = self.simple_run(run_id="run-20261021T090000-aaaaaa")
        clean = ing.load_run(run_dir, source="scheduled")
        self.assertTrue(clean.integrity_ok)
        self.assertTrue(clean.sealed)

        baseline_path = self.tmp / "baseline.json"
        baseline_path.write_text(json.dumps(clean.baseline), encoding="utf-8")
        self.assertTrue(
            ing.load_run(run_dir, source="scheduled", baseline_in=baseline_path).integrity_ok
        )

        target = run_dir / _file_name("W1", "WH-W1")
        with target.open("a", encoding="utf-8") as fh:
            fh.write(json.dumps(row("TAMPER", "GT", "W1", available=1)) + "\n")

        tampered = ing.load_run(run_dir, source="scheduled")
        self.assertFalse(tampered.integrity_ok)
        codes = {e["code"] for e in tampered.integrity_errors}
        self.assertIn("hash_mismatch", codes)
        with_baseline = ing.load_run(run_dir, source="scheduled", baseline_in=baseline_path)
        self.assertIn(
            "baseline_hash_mismatch", {e["code"] for e in with_baseline.integrity_errors}
        )

        conn = memory_db()
        try:
            ing.stage_run(conn, tampered)
            decision = ing.evaluate_publish(conn, tampered)
            self.assertEqual(decision["action"], "reject")
            self.assertEqual(conn.execute("SELECT COUNT(*) FROM stock_history").fetchone()[0], 0)
            self.assertEqual(
                conn.execute(
                    "SELECT integrity_ok FROM stock_run WHERE run_id = ?", [tampered.run_id]
                ).fetchone(),
                (False,),
            )
        finally:
            conn.close()

    def test_a10_cross_day_attribution(self) -> None:
        """验收 10：按 snapshot_at 的 Asia/Shanghai 日期归属；目录冲突拒绝。"""
        # 目录日期与 snapshot_at 冲突 → 拒绝
        conflict_dir = self.simple_run(
            dirname="2026-10-22",
            snapshot_at="2026-10-21T23:30:00",
            run_id="run-20261022T233000-aaaaaa",
        )
        with self.assertRaises(ing.DateAttributionError):
            ing.load_run(conflict_dir, source="scheduled")

        # UTC 时间跨日：17:30Z = 次日 01:30 +08，归到 10-22
        utc_dir = make_run(
            self.tmp / "utc",
            "2026-10-22",
            "2026-10-21T17:30:00Z",
            [warehouse("W1", "WH-W1", [row("SKU-1", "G1", "W1", available=1)])],
            run_id="run-20261021T173000-aaaaaa",
        )
        utc_bundle = ing.load_run(utc_dir, source="scheduled")
        self.assertEqual(utc_bundle.snapshot_date, date(2026, 10, 22))
        self.assertEqual(utc_bundle.snapshot_at.hour, 1)

        # legacy run_id 也按 +08 本地时间生成
        legacy_dir = make_run(
            self.tmp / "legacy",
            "2026-10-22",
            "2026-10-21T17:30:00Z",
            [warehouse("W1", "WH-W1", [row("SKU-1", "G1", "W1", available=1)])],
            seal=False,
            run_id=None,
        )
        legacy_bundle = ing.load_run(legacy_dir, source="legacy")
        self.assertTrue(legacy_bundle.run_id.startswith("legacy-20261022T013000-"))
        self.assertFalse(legacy_bundle.sealed)
        self.assertEqual(legacy_bundle.sealing_exemption, "legacy")

        # 目录 10-21、UTC 10-20 23:59（=10-21 07:59 +08）→ 允许
        within_dir = make_run(
            self.tmp / "within",
            "2026-10-21",
            "2026-10-20T23:59:00Z",
            [warehouse("W1", "WH-W1", [row("SKU-1", "G1", "W1", available=1)])],
            run_id="run-20261020T235900-aaaaaa",
        )
        within = ing.load_run(within_dir, source="scheduled")
        self.assertEqual(within.snapshot_date, date(2026, 10, 21))

        # manifest.snapshot_date 与 snapshot_at 冲突 → 拒绝
        mismatch_dir = make_run(
            self.tmp / "mismatch",
            "2026-10-21",
            "2026-10-21T09:00:00",
            [warehouse("W1", "WH-W1", [row("SKU-1", "G1", "W1", available=1)])],
            run_id="run-20261021T090000-eeeeee",
            manifest_date="2026-10-20",
        )
        with self.assertRaises(ing.DateAttributionError):
            ing.load_run(mismatch_dir, source="scheduled")

    def test_a11_rollback_replays_previous_run_row_by_row(self) -> None:
        """验收 11：回滚按 previous_run_id 重放，逐行内容一致。"""
        dir_a = self.simple_run(
            dirname="2026-10-21-a",
            run_id="run-20261021T080000-aaaaaa",
            ended_at="2026-10-21T08:30:00",
            rows_per_warehouse=2,
        )
        dir_b = self.simple_run(
            dirname="2026-10-21-b",
            run_id="run-20261021T090000-bbbbbb",
            ended_at="2026-10-21T09:30:00",
            rows_per_warehouse=3,
        )
        a = ing.load_run(dir_a, source="scheduled")
        b = ing.load_run(dir_b, source="scheduled")

        conn = memory_db()
        try:
            publish(conn, a)
            decision = publish(conn, b)
            self.assertEqual(decision["previous_run_id"], a.run_id)
            expected = expected_rows_from_run(conn, a.run_id)
            self.assertGreater(len(expected), 0)

            preview = ing.rollback(conn, date(2026, 10, 21), dry_run=True)
            self.assertEqual(preview["to_run_id"], a.run_id)
            self.assertTrue(preview["dry_run"])
            self.assertEqual(ing.get_publish(conn, date(2026, 10, 21))["run_id"], b.run_id)

            result = ing.rollback(conn, date(2026, 10, 21))
            self.assertEqual(result["to_run_id"], a.run_id)
            self.assertFalse(result["dry_run"])
            self.assertEqual(history_rows(conn), expected, "回滚必须逐行内容一致")
            published = ing.get_publish(conn, date(2026, 10, 21))
            self.assertEqual(published["run_id"], a.run_id)
            self.assertEqual(published["previous_run_id"], b.run_id)
        finally:
            conn.close()

    def test_a12_lock_concurrency_and_crash_recovery(self) -> None:
        """验收 12：并发第二个进程拒绝；活进程超时不被抢锁；崩溃锁随进程释放。"""
        lock_path = self.tmp / "stock_history.lock"
        held = ing.acquire_lock(lock_path, "test")
        try:
            with self.assertRaises(ing.LockHeld):
                ing.acquire_lock(lock_path, "second")

            # 活进程持锁：即使 mtime 很旧、stale 阈值很小，也绝不抢锁
            ancient = time.time() - 10_000
            os.utime(lock_path, (ancient, ancient))
            with self.assertRaises(ing.LockHeld):
                ing.acquire_lock(lock_path, "age", stale_after_seconds=1)

            # 第二个进程走 CLI：锁被占用 → 退出码 3，且不打开 DB
            run_dir = self.simple_run(run_id="run-20261021T090000-aaaaaa")
            db_path = self.tmp / "cli.duckdb"
            proc = subprocess.run(
                [
                    sys.executable,
                    str(SCRIPT),
                    "--run-dir",
                    str(run_dir),
                    "--source",
                    "scheduled",
                    "--db",
                    str(db_path),
                    "--lock-path",
                    str(lock_path),
                ],
                capture_output=True,
                text=True,
                timeout=120,
            )
            self.assertEqual(proc.returncode, 3, proc.stderr)
            self.assertIn("锁被占用", proc.stderr)
            self.assertFalse(db_path.exists(), "持锁失败时不应创建/打开数据库")
        finally:
            held.release()

        # 锁文件保留（删文件会造成 inode 竞态），但 OS 锁已释放，可再次获取
        self.assertTrue(lock_path.exists(), "文件锁不删除锁文件")
        again = ing.acquire_lock(lock_path, "again")
        again.release()

        # 崩溃进程遗留：子进程拿锁后 os._exit（不做任何清理），内核自动释放
        code = (
            "import sys, os; sys.path.insert(0, {here!r});"
            "import stock_history_ingest as ing;"
            "_lock = ing.acquire_lock({lock!r});"
            "os._exit(0)"
        ).format(here=str(HERE), lock=str(lock_path))
        crashed = subprocess.run(
            [sys.executable, "-c", code], capture_output=True, text=True, timeout=120
        )
        self.assertEqual(crashed.returncode, 0, crashed.stderr)
        recovered = ing.acquire_lock(lock_path, "recovery")
        recovered.release()

        # 旧版本遗留的纯文本锁（没有 OS 锁持有者）同样可以直接接管
        legacy = self.tmp / "legacy.lock"
        legacy.write_text(
            json.dumps({"pid": 0, "host": "dead", "token": "old"}), encoding="utf-8"
        )
        legacy_held = ing.acquire_lock(legacy, "legacy")
        legacy_held.release()

    def test_a13_migration_failure_rolls_back(self) -> None:
        """验收 13：schema 迁移失败 → 该版本整版回滚，已成功版本保留。"""
        conn = duckdb.connect(":memory:")
        try:
            with self.assertRaises(ing.MigrationFailure):
                ing.migrate(
                    conn,
                    migrations=[
                        (1, "good", ["CREATE TABLE keep_me (a INTEGER)"]),
                        (
                            2,
                            "bad",
                            [
                                "CREATE TABLE partial_me (a INTEGER)",
                                "SELECT * FROM table_that_does_not_exist",
                            ],
                        ),
                    ],
                )
            tables = {r[0] for r in conn.execute("SELECT table_name FROM duckdb_tables()").fetchall()}
            self.assertIn("keep_me", tables)
            self.assertNotIn("partial_me", tables, "失败版本的 DDL 必须回滚")
            versions = [r[0] for r in conn.execute("SELECT version FROM schema_migrations ORDER BY version").fetchall()]
            self.assertEqual(versions, [1])
        finally:
            conn.close()

        # 全新库上完整迁移两次：幂等
        conn = duckdb.connect(":memory:")
        try:
            self.assertEqual(ing.migrate(conn), [1, 2])
            self.assertEqual(ing.migrate(conn), [], "重复 migrate 应幂等")
        finally:
            conn.close()

    def test_a14_test_sku_excluded_and_no_cross_sku_sum(self) -> None:
        """验收 14：TEST-1 排除；uom_basis=unknown 禁止跨 SKU 求和。"""
        run_dir = make_run(
            self.tmp,
            "2026-10-21",
            "2026-10-21T09:00:00",
            [
                warehouse(
                    "W1",
                    "WH-1",
                    [
                        row("TEST-1", "GTEST", "W1", available=50),
                        row("SKU-A", "GA", "W1", available=3),
                        row("SKU-B", "GB", "W1", available=0),
                    ],
                )
            ],
            run_id="run-20261021T090000-aaaaaa",
        )
        bundle = ing.load_run(run_dir, source="scheduled")
        self.assertEqual(bundle.test_sku_rows, 1)

        conn = memory_db()
        try:
            publish(conn, bundle)
            flags = dict(
                conn.execute("SELECT goods_id, is_test FROM stock_history").fetchall()
            )
            self.assertTrue(flags["GTEST"])
            self.assertFalse(flags["GA"])
            self.assertEqual(
                conn.execute("SELECT COUNT(*) FROM v_stock_history_analysis").fetchone()[0], 2
            )
            bases = {r[0] for r in conn.execute("SELECT DISTINCT uom_basis FROM stock_history").fetchall()}
            self.assertEqual(bases, {"unknown"})
            with self.assertRaises(ing.UomBasisError):
                ing.sum_available(conn)
            views = {
                r[0]
                for r in conn.execute("SELECT view_name FROM duckdb_views() WHERE NOT internal").fetchall()
            }
            self.assertEqual(
                views,
                {"v_stock_history_analysis", "v_stockout_observed", "v_stock_by_sku", "v_stock_run_status"},
            )
            grouped = conn.execute("SELECT COUNT(*) FROM v_stock_by_sku").fetchone()[0]
            self.assertEqual(grouped, 2, "聚合视图必须按 SKU 分组（不含 TEST-1）")
            stockout = conn.execute("SELECT goods_id FROM v_stockout_observed").fetchall()
            self.assertEqual(stockout, [("GB",)])
        finally:
            conn.close()


# --------------------------------------------------------------------------- #
# 补充用例（封存 / 迁移 / 基线 / 兼容性）
# --------------------------------------------------------------------------- #


class SupplementaryTests(TempCase):
    def test_unsealed_scheduled_run_is_rejected(self) -> None:
        run_dir = self.simple_run(run_id="run-20261021T090000-aaaaaa", seal=False)
        bundle = ing.load_run(run_dir, source="scheduled")
        self.assertFalse(bundle.sealed)
        self.assertFalse(bundle.integrity_ok)
        self.assertIn("unsealed_run", {e["code"] for e in bundle.integrity_errors})
        conn = memory_db()
        try:
            ing.stage_run(conn, bundle)
            self.assertEqual(ing.evaluate_publish(conn, bundle)["action"], "reject")
        finally:
            conn.close()

    def test_manifest_rows_mismatch_is_rejected(self) -> None:
        run_dir = make_run(
            self.tmp,
            "2026-10-21",
            "2026-10-21T09:00:00",
            [warehouse("W1", "WH-W1", [row("SKU-1", "G1", "W1")], manifest_rows=99)],
            run_id="run-20261021T090000-aaaaaa",
        )
        bundle = ing.load_run(run_dir, source="scheduled")
        self.assertFalse(bundle.warehouses[0].batch_complete)
        self.assertTrue(bundle.warehouses[0].rows_mismatch)
        self.assertFalse(bundle.integrity_ok)

    def test_legacy_run_id_is_deterministic(self) -> None:
        run_dir = make_run(
            self.tmp,
            "2026-10-21",
            "2026-10-21T09:46:23",
            [warehouse("W1", "WH-W1", [row("SKU-1", "G1", "W1")])],
            seal=False,
            run_id=None,
        )
        first = ing.load_run(run_dir, source="legacy")
        second = ing.load_run(run_dir, source="legacy")
        self.assertEqual(first.run_id, second.run_id)
        self.assertRegex(first.run_id, r"^legacy-20261021T094623-[0-9a-f]{8}$")
        self.assertEqual(
            first.run_id.rsplit("-", 1)[1], ing.sha256_file(run_dir / "manifest.json")[:8]
        )

    def test_baseline_roundtrip_via_cli(self) -> None:
        run_dir = self.simple_run(run_id="run-20261021T090000-aaaaaa")
        baseline_path = self.tmp / "baseline.json"
        proc = subprocess.run(
            [
                sys.executable,
                str(SCRIPT),
                "--run-dir",
                str(run_dir),
                "--source",
                "scheduled",
                "--dry-run",
                "--json",
                "--baseline-out",
                str(baseline_path),
            ],
            capture_output=True,
            text=True,
            timeout=120,
        )
        self.assertEqual(proc.returncode, 0, proc.stderr)
        report = json.loads(proc.stdout)
        self.assertTrue(report["dry_run"])
        self.assertEqual(report["publish"]["action"], "publish")
        self.assertEqual(report["rows_ingested"], 6)
        baseline = json.loads(baseline_path.read_text(encoding="utf-8"))
        self.assertEqual(baseline["manifest_sha256"], report["manifest_sha256"])
        self.assertEqual(len(baseline["files"]), 3, "manifest + 2 个 JSONL")

        ok = subprocess.run(
            [
                sys.executable,
                str(SCRIPT),
                "--run-dir",
                str(run_dir),
                "--source",
                "scheduled",
                "--dry-run",
                "--json",
                "--baseline-in",
                str(baseline_path),
            ],
            capture_output=True,
            text=True,
            timeout=120,
        )
        self.assertEqual(ok.returncode, 0, ok.stderr)
        self.assertTrue(json.loads(ok.stdout)["integrity_ok"])

        with (run_dir / _file_name("W1", "WH-W1")).open("a", encoding="utf-8") as fh:
            fh.write(json.dumps(row("EXTRA", "GX", "W1")) + "\n")
        bad = subprocess.run(
            [
                sys.executable,
                str(SCRIPT),
                "--run-dir",
                str(run_dir),
                "--source",
                "scheduled",
                "--dry-run",
                "--json",
                "--baseline-in",
                str(baseline_path),
            ],
            capture_output=True,
            text=True,
            timeout=120,
        )
        self.assertEqual(bad.returncode, 0, bad.stderr)
        self.assertFalse(json.loads(bad.stdout)["integrity_ok"])

    def test_manifest_absolute_path_hint_is_ignored(self) -> None:
        run_dir = make_run(
            self.tmp,
            "2026-10-21",
            "2026-10-21T09:00:00",
            [
                warehouse(
                    "W1",
                    "WH-W1",
                    [row("SKU-1", "G1", "W1")],
                    file_hint=r"C:\some\old\place\warehouse=W1_WH-W1.jsonl",
                )
            ],
            run_id="run-20261021T090000-aaaaaa",
        )
        bundle = ing.load_run(run_dir, source="scheduled")
        self.assertTrue(bundle.integrity_ok, bundle.integrity_errors)
        self.assertEqual(bundle.warehouses[0].rows_read, 1)
        self.assertTrue((run_dir / "warehouse=W1_WH-W1.jsonl").is_file())

    def test_published_alias_conflict_across_runs_is_resolved_by_rank(self) -> None:
        first_dir = make_run(
            self.tmp,
            "2026-10-21-a",
            "2026-10-21T08:00:00",
            [warehouse("W1", "WH-W1", [row("SKU-X", "G1", "W1", available=1)])],
            run_id="run-20261021T080000-aaaaaa",
        )
        second_dir = make_run(
            self.tmp,
            "2026-10-21-b",
            "2026-10-21T09:00:00",
            [warehouse("W1", "WH-W1", [row("SKU-X", "G2", "W1", available=1)])],
            run_id="run-20261021T090000-bbbbbb",
        )
        first = ing.load_run(first_dir, source="scheduled")
        second = ing.load_run(second_dir, source="scheduled")
        conn = memory_db()
        try:
            publish(conn, first)
            decision = publish(conn, second)
            self.assertEqual(decision["action"], "publish")
            self.assertEqual(
                decision["reason"], "candidate_outranks_published_with_alias_conflict"
            )
            self.assertTrue(decision["alias_conflicts"])
            self.assertEqual(
                ing.get_publish(conn, date(2026, 10, 21))["run_id"], second.run_id
            )
        finally:
            conn.close()


# --------------------------------------------------------------------------- #
# 代码复审（2026-10-22）六项修复的回归用例
# --------------------------------------------------------------------------- #


def clone_run_with_value(
    src_run: Path, dst_root: Path, dirname: str, value: float, *, run_id: str
) -> Path:
    """复制 run 的 manifest（字节不变），只改 JSONL 与 run_meta/.sealed 哈希。

    这样 manifest_sha256 与源 run 完全相同，只有文件哈希变化——正是复审指出的
    "同 run_id、只改数据文件"的绕过场景。
    """
    dst = dst_root / dirname
    dst.mkdir(parents=True, exist_ok=True)
    shutil.copy2(src_run / "manifest.json", dst / "manifest.json")
    name = _file_name("W1", "WH-W1")
    with (dst / name).open("w", encoding="utf-8", newline="\n") as fh:
        fh.write(json.dumps(row("SKU-1", "G1", "W1", available=value)) + "\n")
    files = {
        "manifest.json": ing.sha256_file(dst / "manifest.json"),
        name: ing.sha256_file(dst / name),
    }
    timestamp = "2026-10-21T09:00:00"
    run_meta = {
        "run_id": run_id,
        "snapshot_date": "2026-10-21",
        "started_at": timestamp,
        "ended_at": timestamp,
        "exit_code": 0,
        "trigger": "test",
        "manifest_sha256": files["manifest.json"],
        "files": [{"path": n, "sha256": s} for n, s in sorted(files.items())],
    }
    (dst / "run_meta.json").write_text(
        json.dumps(run_meta, ensure_ascii=False, indent=2) + "\n", encoding="utf-8"
    )
    seal_payload = {
        "run_id": run_id,
        "sealed_at": datetime.now(timezone.utc).isoformat(),
        "manifest_sha256": files["manifest.json"],
        "files": files,
    }
    (dst / ".sealed").write_text(
        json.dumps(seal_payload, ensure_ascii=False, indent=2) + "\n", encoding="utf-8"
    )
    return dst


class CodeReviewFixTests(TempCase):
    """2026-10-22 Codex 复审：六项修复 + ⑦ 回滚漏洞，每一项都有可复现的回归断言。"""

    def test_r1_reimport_with_changed_file_hash_is_rejected(self) -> None:
        """① 同 run_id 重导必须比对旧哈希；文件变了就拒绝，绝不先删后插。"""
        run_id = "run-20261021T090000-aaaaaa"
        original = make_run(
            self.tmp / "orig",
            "2026-10-21",
            "2026-10-21T09:00:00",
            [warehouse("W1", "WH-W1", [row("SKU-1", "G1", "W1", available=95)])],
            run_id=run_id,
        )
        changed = clone_run_with_value(
            original, self.tmp / "changed", "2026-10-21", 123456, run_id=run_id
        )
        good = ing.load_run(original, source="scheduled")
        bad = ing.load_run(changed, source="scheduled")
        self.assertTrue(good.integrity_ok, good.integrity_errors)
        self.assertTrue(bad.integrity_ok, bad.integrity_errors)
        self.assertEqual(good.run_id, bad.run_id)
        self.assertEqual(
            good.manifest_sha256,
            bad.manifest_sha256,
            "本用例刻意保持 manifest 字节不变，只有 JSONL 内容变化",
        )
        self.assertNotEqual(
            good.warehouses[0].file_sha256, bad.warehouses[0].file_sha256
        )

        conn = memory_db()
        try:
            publish(conn, good)
            before_history = history_rows(conn)
            before_rows = expected_rows_from_run(conn, run_id)
            self.assertEqual(before_history[0][6], 95.0)

            with self.assertRaises(ing.DataIntegrityError):
                ing.stage_run(conn, bad)

            self.assertEqual(history_rows(conn), before_history, "已发布行不得被覆盖")
            self.assertEqual(
                expected_rows_from_run(conn, run_id), before_rows, "审计行不得被删改"
            )
            self.assertEqual(
                conn.execute(
                    "SELECT integrity_ok FROM stock_run WHERE run_id = ?", [run_id]
                ).fetchone(),
                (True,),
            )
            events = conn.execute(
                "SELECT action, detail FROM stock_ingest_event WHERE run_id = ?",
                [run_id],
            ).fetchall()
            actions = [action for action, _ in events]
            self.assertIn("reimport_changed_rejected", actions)
            details = " ".join(detail for _, detail in events)
            self.assertIn(good.warehouses[0].file_sha256, details)
            self.assertIn(bad.warehouses[0].file_sha256, details)

            # 完全相同的重导仍然幂等（不能误伤正常重复导入）
            ing.stage_run(conn, ing.load_run(original, source="scheduled"))
            self.assertEqual(history_rows(conn), before_history)
            self.assertEqual(expected_rows_from_run(conn, run_id), before_rows)
        finally:
            conn.close()

        # dry-run 的只读路径（CLI --dry-run --db）也必须看到同样的变更
        db_path = self.tmp / "dryrun.duckdb"
        writer = duckdb.connect(str(db_path))
        try:
            ing.migrate(writer)
            publish(writer, good)
        finally:
            writer.close()
        reader = duckdb.connect(str(db_path), read_only=True)
        try:
            decision = ing.evaluate_publish(reader, bad)
            self.assertEqual(decision["action"], "reject")
            self.assertEqual(decision["reason"], "reimport_changed")
        finally:
            reader.close()

    def test_r2_missing_manifest_complete_flag_is_unknown(self) -> None:
        """② manifest.complete 缺失 → 保守判 unknown，不能冒充完整日。"""
        unknown = ing.load_run(
            self.simple_run(
                dirname="2026-10-21-unknown",
                run_id="run-20261021T090000-aaaaaa",
                complete=None,
            ),
            source="scheduled",
        )
        known = ing.load_run(
            self.simple_run(
                dirname="2026-10-21-known",
                run_id="run-20261021T090000-bbbbbb",
                complete=True,
            ),
            source="scheduled",
        )
        self.assertIsNone(unknown.manifest_complete)
        self.assertTrue(unknown.scope_complete, "仓级批次仍可全部完整")
        self.assertFalse(unknown.run_complete, "缺全仓标志只能判 unknown")
        self.assertFalse(
            ing.build_report(unknown, {"action": "publish"}, dry_run=True)["complete_day"]
        )
        self.assertTrue(known.run_complete)
        self.assertGreater(known.rank_key(), unknown.rank_key())

        conn = memory_db()
        try:
            publish(conn, unknown)
            stored = conn.execute(
                "SELECT manifest_complete, scope_complete, run_complete"
                " FROM stock_run WHERE run_id = ?",
                [unknown.run_id],
            ).fetchone()
            self.assertEqual(stored, (None, True, False))
            self.assertEqual(
                conn.execute("SELECT COUNT(*) FROM stock_history").fetchone()[0], 6
            )
        finally:
            conn.close()

    def test_r3_alias_conflict_is_deterministic_regardless_of_order(self) -> None:
        """③ 跨 run 别名冲突按同一总序裁决：反序导入最终赢家唯一。"""

        def build(dirname: str, run_id: str, goods_id: str):
            return ing.load_run(
                make_run(
                    self.tmp,
                    dirname,
                    "2026-10-21T09:00:00",
                    [
                        warehouse(
                            "W1", "WH-W1", [row("SKU-X", goods_id, "W1", available=1)]
                        )
                    ],
                    run_id=run_id,
                    ended_at="2026-10-21T09:30:00",
                ),
                source="scheduled",
            )

        low = build("low", "run-20261021T090000-aaaaaa", "G1")
        high = build("high", "run-20261021T090000-zzzzzz", "G2")
        self.assertEqual(low.rank_key()[:4], high.rank_key()[:4])

        final: list[str] = []
        second_actions: list[tuple[str, str]] = []
        for order in ((low, high), (high, low)):
            conn = memory_db()
            try:
                decisions = [publish(conn, bundle) for bundle in order]
                second_actions.append((decisions[-1]["action"], decisions[-1]["reason"]))
                final.append(ing.get_publish(conn, date(2026, 10, 21))["run_id"])
                goods_ids = [
                    r[0] for r in conn.execute("SELECT goods_id FROM stock_history").fetchall()
                ]
                self.assertEqual(goods_ids, ["G2"], f"导入顺序 {order} 结果不一致")
            finally:
                conn.close()

        self.assertEqual(final, [high.run_id, high.run_id])
        self.assertEqual(
            second_actions,
            [
                ("publish", "candidate_outranks_published_with_alias_conflict"),
                ("reject", "alias_conflict_with_published"),
            ],
        )

        # 更低序的冲突候选无论在哪个方向都不能赢
        lowest = build("lowest", "run-20261021T090000-000000", "G3")
        for order in ((high, lowest), (lowest, high)):
            conn = memory_db()
            try:
                for bundle in order:
                    publish(conn, bundle)
                self.assertEqual(
                    ing.get_publish(conn, date(2026, 10, 21))["run_id"], high.run_id
                )
            finally:
                conn.close()

    def test_r4_alias_intervals_are_date_rebuilt_and_rollback_restores(self) -> None:
        """④ 按日期重建别名区间：反序导入不得出现 valid_to < valid_from；回滚恢复。"""
        old = ing.load_run(
            make_run(
                self.tmp / "p_old",
                "2026-10-20",
                "2026-10-20T09:00:00",
                [warehouse("W1", "WH-W1", [row("SKU-OLD", "G1", "W1", available=1)])],
                run_id="run-20261020T090000-aaaaaa",
            ),
            source="scheduled",
        )
        new = ing.load_run(
            make_run(
                self.tmp / "p_new",
                "2026-10-21",
                "2026-10-21T09:00:00",
                [warehouse("W1", "WH-W1", [row("SKU-NEW", "G1", "W1", available=1)])],
                run_id="run-20261021T090000-bbbbbb",
                ended_at="2026-10-21T09:30:00",
            ),
            source="scheduled",
        )
        newer = ing.load_run(
            make_run(
                self.tmp / "p_newer",
                "2026-10-21",
                "2026-10-21T10:00:00",
                [warehouse("W1", "WH-W1", [row("SKU-NEW2", "G1", "W1", available=1)])],
                run_id="run-20261021T100000-cccccc",
                ended_at="2026-10-21T10:30:00",
            ),
            source="scheduled",
        )

        def intervals(conn):
            rows = conn.execute(
                "SELECT name, valid_from, valid_to FROM stock_id_history"
                " WHERE entity_type = 'goods' AND entity_id = 'G1' ORDER BY name"
            ).fetchall()
            for _, start, end in rows:
                if end is not None:
                    self.assertGreaterEqual(end, start, f"区间倒挂: {rows}")
            return rows

        conn = memory_db()
        try:
            # 反序导入：先 10-21 再 10-20
            publish(conn, new)
            self.assertEqual(
                intervals(conn), [("SKU-NEW", date(2026, 10, 21), None)]
            )
            publish(conn, old)
            expected = [
                ("SKU-NEW", date(2026, 10, 21), None),
                ("SKU-OLD", date(2026, 10, 20), date(2026, 10, 21)),
            ]
            self.assertEqual(intervals(conn), expected)

            # 同日替换：旧别名不再属于当日发布事实，但区间仍不得倒挂
            decision = publish(conn, newer)
            self.assertEqual(decision["previous_run_id"], new.run_id)
            self.assertEqual(
                intervals(conn),
                [
                    ("SKU-NEW2", date(2026, 10, 21), None),
                    ("SKU-OLD", date(2026, 10, 20), date(2026, 10, 21)),
                ],
            )

            # 回滚到 previous run：别名区间必须一起恢复
            result = ing.rollback(conn, date(2026, 10, 21))
            self.assertEqual(result["to_run_id"], new.run_id)
            self.assertEqual(intervals(conn), expected)
        finally:
            conn.close()

    def test_r5_zero_row_empty_previous_run_is_rollbackable(self) -> None:
        """⑤ 合法零行空仓可按批次有效性回滚；批次不完整的零行仍拒绝。"""
        empty = ing.load_run(
            make_run(
                self.tmp / "empty",
                "2026-10-21",
                "2026-10-21T08:00:00",
                [
                    warehouse("W1", "WH-W1", []),
                    warehouse("W2", "WH-W2", []),
                ],
                complete=True,
                run_id="run-20261021T080000-aaaaaa",
                ended_at="2026-10-21T08:30:00",
            ),
            source="scheduled",
        )
        full = ing.load_run(
            make_run(
                self.tmp / "full",
                "2026-10-21",
                "2026-10-21T09:00:00",
                [
                    warehouse("W1", "WH-W1", [row("SKU-1", "G1", "W1", available=1)]),
                    warehouse("W2", "WH-W2", [row("SKU-2", "G2", "W2", available=1)]),
                ],
                complete=True,
                run_id="run-20261021T090000-bbbbbb",
                ended_at="2026-10-21T09:30:00",
            ),
            source="scheduled",
        )
        self.assertTrue(empty.run_complete)
        self.assertEqual(empty.rows_ingested, 0)

        conn = memory_db()
        try:
            publish(conn, empty)
            decision = publish(conn, full)
            self.assertEqual(decision["previous_run_id"], empty.run_id)
            preview = ing.rollback(conn, date(2026, 10, 21), dry_run=True)
            self.assertEqual(preview["to_run_id"], empty.run_id)
            self.assertEqual(preview["rows"], 0)
            result = ing.rollback(conn, date(2026, 10, 21))
            self.assertEqual(result["rows"], 0)
            self.assertEqual(history_rows(conn), [])
            self.assertEqual(
                ing.get_publish(conn, date(2026, 10, 21))["run_id"], empty.run_id
            )
        finally:
            conn.close()

        # 反例：0 行但有一个仓没抓到（batch_complete=false）→ 无法断言是真空仓
        broken = ing.load_run(
            make_run(
                self.tmp / "broken",
                "2026-10-21",
                "2026-10-21T07:00:00",
                [
                    warehouse("W1", "WH-W1", []),
                    warehouse(
                        "W2",
                        "WH-W2",
                        [],
                        complete=False,
                        include_file=False,
                        manifest_rows=None,
                        error="URLError: boom",
                    ),
                ],
                complete=False,
                run_id="run-20261021T070000-000000",
                ended_at="2026-10-21T07:30:00",
            ),
            source="scheduled",
        )
        self.assertFalse(broken.run_complete)
        conn = memory_db()
        try:
            publish(conn, broken)
            publish(conn, full)
            with self.assertRaises(ing.RollbackUnavailable):
                ing.rollback(conn, date(2026, 10, 21))
            # 拒绝回滚时发布指针不得变动
            self.assertEqual(
                ing.get_publish(conn, date(2026, 10, 21))["run_id"], full.run_id
            )
        finally:
            conn.close()

    def test_r6_live_process_lock_is_not_stolen_after_timeout(self) -> None:
        """⑥ 可靠进程锁：活进程持锁即使超时也不被抢；进程退出后自动可获取。"""
        lock_path = self.tmp / "cross.lock"
        code = (
            "import sys, time; sys.path.insert(0, {here!r});"
            "import stock_history_ingest as ing;"
            "_lock = ing.acquire_lock({lock!r});"
            "print('held', flush=True); time.sleep(60)"
        ).format(here=str(HERE), lock=str(lock_path))
        child = subprocess.Popen(
            [sys.executable, "-c", code],
            stdout=subprocess.PIPE,
            stderr=subprocess.PIPE,
            text=True,
        )
        try:
            self.assertEqual(child.stdout.readline().strip(), "held")
            ancient = time.time() - 10_000
            os.utime(lock_path, (ancient, ancient))
            with self.assertRaises(ing.LockHeld):
                ing.acquire_lock(lock_path, "parent", stale_after_seconds=1)
            self.assertFalse(
                any(p.name.startswith(lock_path.name + ".stale-") for p in self.tmp.iterdir()),
                "不得把活进程的锁改名抢走",
            )
        finally:
            child.terminate()
            child.wait(timeout=30)
            if child.stdout:
                child.stdout.close()
            if child.stderr:
                child.stderr.close()

        # 子进程退出（含崩溃/被终止）后内核释放锁，父进程即可获取。
        # TerminateProcess 与内核释放句柄之间可能有极短延迟，给 10s 上限。
        deadline = time.time() + 10
        while True:
            try:
                held = ing.acquire_lock(lock_path, "parent")
                break
            except ing.LockHeld:
                if time.time() > deadline:
                    raise
                time.sleep(0.1)
        held.release()


class FailedReimportRollbackTests(TempCase):
    """⑦ A 发布 → B 替换 → 重导 A 外部基线失败：A 必须原样保留，回滚仍可用。"""

    def test_r7_failed_reimport_after_supersede_keeps_rollback_target(self) -> None:
        day = date(2026, 10, 21)
        run_a_id = "run-20261021T090000-aaaaaa"
        run_b_id = "run-20261021T100000-bbbbbb"
        a_dir = make_run(
            self.tmp / "a",
            "2026-10-21",
            "2026-10-21T09:00:00",
            [warehouse("W1", "WH-W1", [row("SKU-A", "GA", "W1", available=7)])],
            run_id=run_a_id,
            ended_at="2026-10-21T09:30:00",
        )
        b_dir = make_run(
            self.tmp / "b",
            "2026-10-21",
            "2026-10-21T10:00:00",
            [warehouse("W1", "WH-W1", [row("SKU-B", "GB", "W1", available=11)])],
            run_id=run_b_id,
            ended_at="2026-10-21T10:30:00",
        )
        good_a = ing.load_run(a_dir, source="scheduled")
        good_b = ing.load_run(b_dir, source="scheduled")
        self.assertTrue(good_a.integrity_ok, good_a.integrity_errors)
        self.assertTrue(good_b.integrity_ok, good_b.integrity_errors)

        # 外部基线不一致：内容哈希与 A 完全相同，只有校验结论不同。
        baseline_path = self.tmp / "external_baseline.json"
        baseline_path.write_text(
            json.dumps(
                {
                    "snapshot_date": "2026-10-21",
                    "manifest_sha256": "0" * 64,
                    "files": {"manifest.json": "0" * 64},
                }
            )
            + "\n",
            encoding="utf-8",
        )
        bad_a = ing.load_run(a_dir, source="scheduled", baseline_in=baseline_path)
        self.assertFalse(bad_a.integrity_ok)
        self.assertEqual(bad_a.manifest_sha256, good_a.manifest_sha256)
        self.assertEqual(
            [wh.file_sha256 for wh in bad_a.warehouses],
            [wh.file_sha256 for wh in good_a.warehouses],
            "失败重导必须与首次入库的哈希基线一致，才走失败重导保护而非 reimport_changed",
        )

        conn = memory_db()
        try:
            publish(conn, good_a)
            decision = publish(conn, good_b)
            self.assertEqual(decision["action"], "publish")
            self.assertEqual(decision["previous_run_id"], run_a_id)
            self.assertEqual(ing.get_publish(conn, day)["run_id"], run_b_id)

            b_history = history_rows(conn)
            a_audit_rows = expected_rows_from_run(conn, run_a_id)
            a_run_row = conn.execute(
                "SELECT * FROM stock_run WHERE run_id = ?", [run_a_id]
            ).fetchone()
            self.assertEqual(len(a_audit_rows), 1)

            # A 已不再是当前发布 run，但它仍是回滚目标：失败重导必须整体拒绝。
            with self.assertRaises(ing.DataIntegrityError):
                ing.stage_run(conn, bad_a)

            self.assertEqual(
                expected_rows_from_run(conn, run_a_id), a_audit_rows, "A 的审计原始行不得被删"
            )
            self.assertEqual(history_rows(conn), b_history, "已发布行不得被覆盖")
            self.assertEqual(
                conn.execute(
                    "SELECT * FROM stock_run WHERE run_id = ?", [run_a_id]
                ).fetchone(),
                a_run_row,
                "A 的元数据（含 integrity_ok=true）不得被覆盖",
            )
            self.assertEqual(
                ing.get_publish(conn, day)["run_id"], run_b_id, "发布指针不得被移动"
            )
            actions = [
                action
                for (action,) in conn.execute(
                    "SELECT action FROM stock_ingest_event WHERE run_id = ?",
                    [run_a_id],
                ).fetchall()
            ]
            self.assertIn("reimport_rejected", actions)

            # 无效重导之后，回滚到 A 仍然成功且逐行重放 A 的原始行。
            preview = ing.rollback(conn, day, dry_run=True)
            self.assertEqual(preview["to_run_id"], run_a_id)
            self.assertEqual(preview["rows"], 1)
            result = ing.rollback(conn, day)
            self.assertEqual(result["to_run_id"], run_a_id)
            self.assertEqual(ing.get_publish(conn, day)["run_id"], run_a_id)
            self.assertEqual(history_rows(conn), expected_rows_from_run(conn, run_a_id))
            self.assertEqual(
                conn.execute(
                    "SELECT integrity_ok FROM stock_run WHERE run_id = ?", [run_a_id]
                ).fetchone(),
                (True,),
            )
        finally:
            conn.close()


if __name__ == "__main__":
    unittest.main(verbosity=2)
