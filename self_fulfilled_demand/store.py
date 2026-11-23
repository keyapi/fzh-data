# -*- coding: utf-8 -*-
"""en-demand-v1 的本地 Parquet 存储（快照 + 最后提交指针）。

一致性设计
- 所有表写入 ``snapshots/<commit_id>/``，五张表全部写成功后写 ``commit.json``，
  最后用原子替换更新根目录 ``CURRENT`` 指针。
- 读取只看 ``CURRENT`` 指向的快照；快照缺文件 / 缺 ``commit.json`` → 直接报
  ``IncompleteSnapshotError``，绝不拿根目录里残留的旧文件拼一个「看起来成功」的快照。
- 一次采集用 ``begin(run_id)`` 开快照，逐页写同一快照，最后 ``commit(status)``。
  写文件失败 → ``abort()``，``CURRENT`` 不变（失败的批次不会冒充成功）。
- 兼容旧版本：根目录直接有 parquet 且没有 ``CURRENT`` 时，读取走旧布局；
  ``adopt_legacy()`` 可把旧布局收编成一个正式快照。

表
- en_orders.parquet / en_order_lines.parquet / en_order_packages.parquet
- en_order_events.parquet / raw/en_orders_raw.parquet
"""

from __future__ import annotations

import hashlib
import json
import os
import shutil
from contextlib import contextmanager
from datetime import datetime
from pathlib import Path
from typing import Iterable, Sequence

import pandas as pd

from . import SCHEMA_VERSION, config

ORDER_COLUMNS = [
    "en_doc_name",
    "en_order_id_code",
    "platform_order_id",
    "base_order_id",
    "platform_base_order_id",
    "split_suffix",
    "split_index",
    "split_basis",
    "order_type",
    "order_status",
    "invalid",
    "invalid_raw",
    "suspended",
    "refunded_flag",
    "refunded_time",
    "lifecycle_state",
    "sale_time",
    "sale_date",
    "paid_time",
    "despatch_complete_time",
    "despatch_date",
    "updated_time",
    "last_sync_time",
    "modified",
    "creation",
    "warehouse_name",
    "package_id",
    "tracking_number",
    "carrier",
    "channel",
    "account",
    "sale_account",
    "platform_code",
    "channel_account_en",
    "order_amount",
    "order_amount_currency",
    "fulfillment_scope",
    "scope_evidence",
    "scope_conflict",
    "line_count",
    "line_qty_total",
    "line_count_missing_qty",
    "line_count_embedded_component",
    "package_count",
    "first_seen_at",
    "last_seen_at",
    "first_run_id",
    "last_run_id",
    "ingest_scope",
    "coverage_status",
    "source",
    "state_hash",
]

LINE_COLUMNS = [
    "line_key",
    "en_doc_name",
    "base_order_id",
    "idx",
    "source_line_id",
    "line_identity_basis",
    "platform_sku",
    "tongtool_sku",
    "erp_item_code",
    "quantity",
    "quantity_missing",
    "is_deliver_good",
    "shipping_method",
    "demand_kind",
    "demand_kind_basis",
    "match_status",
    "asin",
    "web_store_item_id",
    "transaction_price",
    "calc_price_rmb",
    "item_cost",
]

PACKAGE_COLUMNS = [
    "en_doc_name",
    "package",
    "tracking_number",
    "allocated_fee",
    "currency",
    "allocated_carrier_fee",
    "carrier_currency",
    "package_index",
    "package_source",
]

EVENT_COLUMNS = [
    "en_doc_name",
    "observed_at",
    "run_id",
    "event_types",
    "old_state_hash",
    "new_state_hash",
    "changes_json",
]

RAW_COLUMNS = [
    "en_doc_name",
    "modified",
    "sale_time",
    "payload",
    "payload_hash",
    "captured_at",
    "run_id",
]

TABLE_FILES = {
    "orders": "en_orders.parquet",
    "lines": "en_order_lines.parquet",
    "packages": "en_order_packages.parquet",
    "events": "en_order_events.parquet",
    "raw": "raw/en_orders_raw.parquet",
}

INT_COLUMNS = {
    "split_index",
    "invalid",
    "invalid_raw",
    "suspended",
    "refunded_flag",
    "line_count",
    "line_qty_total",
    "line_count_missing_qty",
    "line_count_embedded_component",
    "package_count",
    "idx",
    "quantity",
    "is_deliver_good",
    "package_index",
}
FLOAT_COLUMNS = {
    "order_amount",
    "transaction_price",
    "calc_price_rmb",
    "item_cost",
    "allocated_fee",
    "allocated_carrier_fee",
}
BOOL_COLUMNS = {"quantity_missing"}

TRACKED_FIELDS = {
    "order_status": "status_changed",
    "invalid": "invalid_changed",
    "suspended": "suspended_changed",
    "despatch_complete_time": "despatch_changed",
    "paid_time": "paid_changed",
    "warehouse_name": "warehouse_changed",
    "tracking_number": "tracking_changed",
    "lifecycle_state": "lifecycle_changed",
    "fulfillment_scope": "scope_changed",
    "line_count": "lines_changed",
    "line_qty_total": "lines_changed",
    "package_count": "packages_changed",
}

CURRENT_FILE = "CURRENT"
COMMIT_FILE = "commit.json"


class IncompleteSnapshotError(RuntimeError):
    """快照缺少文件或提交标记，拒绝读取。"""


def now_iso() -> str:
    return datetime.now().astimezone().isoformat(timespec="seconds")


def _cast(df: pd.DataFrame, columns: Sequence[str]) -> pd.DataFrame:
    for col in columns:
        if col not in df.columns:
            df[col] = None
    df = df[list(columns)]
    for col in columns:
        if col in INT_COLUMNS:
            df[col] = pd.to_numeric(df[col], errors="coerce").astype("Int64")
        elif col in FLOAT_COLUMNS:
            df[col] = pd.to_numeric(df[col], errors="coerce").astype("Float64")
        elif col in BOOL_COLUMNS:
            df[col] = df[col].astype("boolean")
        else:
            df[col] = df[col].astype("string")
    return df


class ParquetStore:
    def __init__(self, root: str | Path, retention: int = 2):
        self.root = Path(root)
        self.retention = retention
        self.snapshots_dir = self.root / "snapshots"
        self.runs_dir = self.root / "runs"
        self.manifest_path = self.root / "manifest.json"
        self.current_path = self.root / CURRENT_FILE
        self._staging: Path | None = None
        self._pinned_dir: Path | None = None

    @contextmanager
    def pinned(self):
        """把读取固定在一个快照目录；期间即使有新提交也不换目录。

        消费一次输出必须 `with store.pinned():` 内读 orders/lines/packages，
        否则两次读取之间发生提交会拼出「旧订单头 + 新行」的混合状态。
        """
        previous = self._pinned_dir
        self._pinned_dir = self._active_dir()
        try:
            yield self._pinned_dir
        finally:
            self._pinned_dir = previous

    # -- 快照解析 -----------------------------------------------------------
    def read_current(self) -> dict:
        if not self.current_path.exists():
            return {}
        return json.loads(self.current_path.read_text(encoding="utf-8"))

    def _legacy_files(self) -> dict[str, Path]:
        return {key: self.root / rel for key, rel in TABLE_FILES.items()}

    def _active_dir(self) -> Path:
        if self._pinned_dir is not None:
            return self._pinned_dir
        if self._staging is not None:
            return self._staging
        current = self.read_current()
        if current:
            return self.snapshots_dir / current["commit_id"]
        return self.root

    def _validate(self, directory: Path, require_commit: bool) -> None:
        files = {key: directory / rel for key, rel in TABLE_FILES.items()}
        existing = {key for key, path in files.items() if path.exists()}
        if require_commit:
            # 指针指向的目录必须存在、有 commit.json、五张表齐全；
            # 即使一个文件都没有，也要报错而不是当成空库。
            if not directory.exists():
                raise IncompleteSnapshotError(f"快照目录不存在: {directory}")
            if not (directory / COMMIT_FILE).exists():
                raise IncompleteSnapshotError(f"快照缺少 {COMMIT_FILE}: {directory}")
            missing = [TABLE_FILES[k] for k in TABLE_FILES if k not in existing]
            if missing:
                raise IncompleteSnapshotError(f"快照缺少表 {missing}: {directory}")
            return
        if not existing:
            return  # 空库（尚未提交过任何快照）
        # 暂存区或旧布局：orders 与 lines 必须同时存在，避免「有头无行」被当成功
        if ("orders" in existing) != ("lines" in existing):
            raise IncompleteSnapshotError(
                f"表不完整（orders={('orders' in existing)}, "
                f"lines={('lines' in existing)}）：{directory}"
            )

    # -- 读取 ---------------------------------------------------------------
    def _read(self, key: str, columns: Sequence[str]) -> pd.DataFrame:
        directory = self._active_dir()
        require_commit = (
            self._staging is None and (self._pinned_dir is not None or bool(self.read_current()))
        )
        self._validate(directory, require_commit=require_commit)
        path = directory / TABLE_FILES[key]
        if not path.exists():
            return _cast(pd.DataFrame(), columns)
        return _cast(pd.read_parquet(path), columns)

    def load_orders(self) -> pd.DataFrame:
        return self._read("orders", ORDER_COLUMNS)

    def load_lines(self) -> pd.DataFrame:
        return self._read("lines", LINE_COLUMNS)

    def load_packages(self) -> pd.DataFrame:
        return self._read("packages", PACKAGE_COLUMNS)

    def load_events(self) -> pd.DataFrame:
        return self._read("events", EVENT_COLUMNS)

    def load_raw(self) -> pd.DataFrame:
        return self._read("raw", RAW_COLUMNS)

    # -- 快照生命周期 -------------------------------------------------------
    def begin(self, commit_id: str) -> Path:
        if self._staging is not None:
            raise RuntimeError("已有未提交的快照，先 commit() 或 abort()")
        staging = self.snapshots_dir / commit_id
        if staging.exists():
            raise RuntimeError(f"快照目录已存在：{staging}")
        staging.mkdir(parents=True)
        # 从当前快照复制已有表，保证逐页合并基于已提交数据
        current = self.read_current()
        source_dir = (self.snapshots_dir / current["commit_id"]) if current else self.root
        if source_dir.exists():
            for key, rel in TABLE_FILES.items():
                src = source_dir / rel
                if src.exists():
                    dest = staging / rel
                    dest.parent.mkdir(parents=True, exist_ok=True)
                    shutil.copy2(src, dest)
        self._staging = staging
        return staging

    def commit(self, status: str = "success", meta: dict | None = None) -> dict:
        if self._staging is None:
            raise RuntimeError("没有打开的暂存快照")
        staging = self._staging
        files = {}
        for key, rel in TABLE_FILES.items():
            path = staging / rel
            if not path.exists():
                path.parent.mkdir(parents=True, exist_ok=True)
                _cast(pd.DataFrame(), _columns_for(key)).to_parquet(path, index=False)
            files[rel] = {
                "bytes": path.stat().st_size,
                "sha256": hashlib.sha256(path.read_bytes()).hexdigest(),
            }
        commit_id = staging.name
        marker = {
            "commit_id": commit_id,
            "schema_version": SCHEMA_VERSION,
            "status": status,
            "committed_at": now_iso(),
            "files": files,
            "meta": meta or {},
        }
        marker_tmp = staging / (COMMIT_FILE + ".tmp")
        marker_tmp.write_text(json.dumps(marker, ensure_ascii=False, indent=2), encoding="utf-8")
        os.replace(marker_tmp, staging / COMMIT_FILE)
        current_tmp = self.root / (CURRENT_FILE + ".tmp")
        current_tmp.write_text(
            json.dumps(
                {
                    "commit_id": commit_id,
                    "schema_version": SCHEMA_VERSION,
                    "status": status,
                    "committed_at": marker["committed_at"],
                },
                ensure_ascii=False,
                indent=2,
            ),
            encoding="utf-8",
        )
        os.replace(current_tmp, self.current_path)
        self._staging = None
        self._prune()
        return marker

    def abort(self, reason: str = "") -> Path | None:
        if self._staging is None:
            return None
        staging = self._staging
        self._staging = None
        failed = staging.with_name(staging.name + ".failed")
        try:
            if failed.exists():
                shutil.rmtree(failed, ignore_errors=True)
            os.replace(staging, failed)
            (failed / "ABORTED").write_text(reason or "aborted", encoding="utf-8")
        except OSError:
            shutil.rmtree(staging, ignore_errors=True)
        return failed

    def _prune(self) -> None:
        if not self.snapshots_dir.exists():
            return
        current = self.read_current().get("commit_id")
        snaps = sorted(
            [p for p in self.snapshots_dir.iterdir() if p.is_dir() and not p.name.endswith(".failed")],
            key=lambda p: p.stat().st_mtime,
            reverse=True,
        )
        keep = set(snaps[: self.retention]) | ({self.snapshots_dir / current} if current else set())
        for path in snaps:
            if path not in keep:
                shutil.rmtree(path, ignore_errors=True)

    def adopt_legacy(self) -> dict | None:
        """把根目录旧布局收编为正式快照（已有 CURRENT 则不做）。"""
        if self.read_current():
            return None
        if not (self.root / TABLE_FILES["orders"]).exists():
            return None
        commit_id = f"legacy-adopt-{datetime.now().strftime('%Y%m%dT%H%M%S')}"
        self.begin(commit_id)
        return self.commit(status="adopted_legacy", meta={"source": "legacy_root_files"})

    # -- 写入（只在暂存快照内） ---------------------------------------------
    def _write(self, key: str, df: pd.DataFrame, columns: Sequence[str]) -> None:
        if self._staging is None:
            raise RuntimeError("写入前必须 begin() 打开快照")
        path = self._staging / TABLE_FILES[key]
        path.parent.mkdir(parents=True, exist_ok=True)
        df = _cast(df, columns)
        tmp = path.with_suffix(path.suffix + ".tmp")
        df.to_parquet(tmp, index=False, compression="zstd")
        os.replace(tmp, path)

    # -- ingest -------------------------------------------------------------
    def ingest(self, records: Iterable[dict], run: dict) -> dict:
        """将一批记录合并进当前暂存快照（调用前需 begin；未 begin 则自动开一个）。"""
        auto_open = self._staging is None
        if auto_open:
            self.begin(run["run_id"])
        try:
            stats = self._merge(records, run)
        except Exception:
            if auto_open:
                self.abort(f"auto-open snapshot failed: run={run.get('run_id')}")
            raise
        if auto_open:
            self.commit(status="success", meta={"auto": True, "run_id": run.get("run_id")})
        return stats

    def _merge(self, records: Iterable[dict], run: dict) -> dict:
        records = list(records)
        old_orders = self.load_orders()
        old_lines = self.load_lines()
        old_packages = self.load_packages()
        old_events = self.load_events()
        old_raw = self.load_raw()

        old_by_doc = (
            {r["en_doc_name"]: r for r in old_orders.to_dict("records")}
            if len(old_orders)
            else {}
        )

        new_orders: list[dict] = []
        new_lines: list[dict] = []
        new_packages: list[dict] = []
        new_raw: list[dict] = []
        events: list[dict] = []
        touched_docs: set[str] = set()
        stats = {
            "input_orders": len(records),
            "new_orders": 0,
            "updated_orders": 0,
            "unchanged_orders": 0,
            "duplicate_lines_collapsed": 0,
            "events_appended": 0,
            "orders_with_conflict": 0,
            "orders_unknown_scope": 0,
            "orders_invalid": 0,
            "orders_fba": 0,
            "lines_written": 0,
            "packages_written": 0,
            "orders_missing_lines": 0,
        }

        for rec in records:
            order = dict(rec["order"])
            doc = order["en_doc_name"]
            touched_docs.add(doc)
            stats["duplicate_lines_collapsed"] += rec.get("duplicates", 0)
            if order["scope_conflict"]:
                stats["orders_with_conflict"] += 1
            if order["fulfillment_scope"] == config.SCOPE_UNKNOWN:
                stats["orders_unknown_scope"] += 1
            if order["lifecycle_state"].startswith("cancelled"):
                stats["orders_invalid"] += 1
            if order["fulfillment_scope"] == config.SCOPE_FBA:
                stats["orders_fba"] += 1
            if order["line_count"] == 0:
                stats["orders_missing_lines"] += 1

            old = old_by_doc.get(doc)
            if old is None:
                stats["new_orders"] += 1
                events.append(
                    self._event(doc, run, ["created"], None, order["state_hash"], {"created": True})
                )
            else:
                order["first_seen_at"] = old.get("first_seen_at") or order["first_seen_at"]
                order["first_run_id"] = old.get("first_run_id") or order["first_run_id"]
                if old.get("state_hash") == order["state_hash"]:
                    stats["unchanged_orders"] += 1
                else:
                    stats["updated_orders"] += 1
                    changes = self._diff(old, order)
                    events.append(
                        self._event(
                            doc,
                            run,
                            self._event_types(changes),
                            old.get("state_hash"),
                            order["state_hash"],
                            changes,
                        )
                    )
            new_orders.append(order)
            new_lines.extend(rec["lines"])
            new_packages.extend(rec["packages"])
            new_raw.append(rec["raw"])

        if touched_docs:
            old_lines = old_lines[~old_lines["en_doc_name"].isin(touched_docs)]
            old_packages = old_packages[~old_packages["en_doc_name"].isin(touched_docs)]
            old_raw = old_raw[~old_raw["en_doc_name"].isin(touched_docs)]

        orders_df = self._merge_orders(old_orders, new_orders, touched_docs)
        lines_df = _cast(
            pd.concat([old_lines, _cast(pd.DataFrame(new_lines), LINE_COLUMNS)], ignore_index=True),
            LINE_COLUMNS,
        )
        packages_df = _cast(
            pd.concat([old_packages, _cast(pd.DataFrame(new_packages), PACKAGE_COLUMNS)], ignore_index=True),
            PACKAGE_COLUMNS,
        )
        raw_df = _cast(
            pd.concat([old_raw, _cast(pd.DataFrame(new_raw), RAW_COLUMNS)], ignore_index=True),
            RAW_COLUMNS,
        )
        events_df = _cast(
            pd.concat([old_events, _cast(pd.DataFrame(events), EVENT_COLUMNS)], ignore_index=True),
            EVENT_COLUMNS,
        )

        orders_df = orders_df.sort_values("en_doc_name", kind="stable").reset_index(drop=True)
        lines_df = lines_df.sort_values(["en_doc_name", "idx", "line_key"], kind="stable").reset_index(drop=True)
        packages_df = packages_df.sort_values(["en_doc_name", "package_index"], kind="stable").reset_index(drop=True)
        raw_df = raw_df.sort_values("en_doc_name", kind="stable").reset_index(drop=True)
        events_df = events_df.sort_values(["observed_at", "en_doc_name"], kind="stable").reset_index(drop=True)

        self._write("orders", orders_df, ORDER_COLUMNS)
        self._write("lines", lines_df, LINE_COLUMNS)
        self._write("packages", packages_df, PACKAGE_COLUMNS)
        self._write("raw", raw_df, RAW_COLUMNS)
        self._write("events", events_df, EVENT_COLUMNS)

        stats["events_appended"] = len(events)
        stats["lines_written"] = len(new_lines)
        stats["packages_written"] = len(new_packages)
        stats["totals_after"] = {
            "orders": len(orders_df),
            "lines": len(lines_df),
            "packages": len(packages_df),
            "events": len(events_df),
        }
        return stats

    def _merge_orders(
        self, old_orders: pd.DataFrame, new_orders: list[dict], touched_docs: set[str]
    ) -> pd.DataFrame:
        if not len(old_orders):
            return _cast(pd.DataFrame(new_orders), ORDER_COLUMNS)
        keep = old_orders[~old_orders["en_doc_name"].isin(touched_docs)]
        return _cast(
            pd.concat([keep, _cast(pd.DataFrame(new_orders), ORDER_COLUMNS)], ignore_index=True),
            ORDER_COLUMNS,
        )

    @staticmethod
    def _diff(old: dict, new: dict) -> dict:
        changes = {}
        for field, event in TRACKED_FIELDS.items():
            before, after = old.get(field), new.get(field)
            if str(before) != str(after):
                changes[field] = {"old": before, "new": after, "event": event}
        if not changes:
            changes["content"] = {
                "old": old.get("state_hash"),
                "new": new.get("state_hash"),
                "event": "other_change",
            }
        return changes

    @staticmethod
    def _event_types(changes: dict) -> list[str]:
        return sorted({v.get("event", "other_change") for v in changes.values()}) or ["other_change"]

    @staticmethod
    def _event(doc: str, run: dict, types: list[str], old_hash, new_hash, changes: dict) -> dict:
        return {
            "en_doc_name": doc,
            "observed_at": run["started_at"],
            "run_id": run["run_id"],
            "event_types": ",".join(types),
            "old_state_hash": old_hash,
            "new_state_hash": new_hash,
            "changes_json": json.dumps(changes, ensure_ascii=False, sort_keys=True),
        }

    # -- manifest -----------------------------------------------------------
    def current_files(self) -> dict[str, Path]:
        directory = self._active_dir()
        return {key: directory / rel for key, rel in TABLE_FILES.items()}

    def write_manifest(self, report: dict) -> None:
        current = self.read_current()
        manifest = {
            "schema_version": SCHEMA_VERSION,
            "updated_at": now_iso(),
            "commit_id": current.get("commit_id"),
            "commit_status": current.get("status"),
            "status": report["status"],
            "last_run_id": report["run_id"],
            "last_run_status": report["status"],
            "data_fetch_status": report.get("data_fetch_status"),
            "validation_status": report.get("validation_status"),
            "partial": report["status"] != "success",
            "watermarks": report.get("watermarks", {}),
            "source_coverage": report.get("source_coverage", {}),
            "config": {
                "warehouse_scope_version": config.WAREHOUSE_SCOPE_VERSION,
                "legacy_cutover": config.DEFAULT_LEGACY_CUTOVER,
            },
            "counts": report.get("store", {}).get("totals_after", {}),
            "files": {},
            "caveats": report.get("caveats", []),
        }
        for key, path in self.current_files().items():
            if path.exists():
                data = path.read_bytes()
                manifest["files"][str(Path(TABLE_FILES[key]))] = {
                    "bytes": len(data),
                    "sha256": hashlib.sha256(data).hexdigest(),
                }
        tmp = self.manifest_path.with_suffix(".json.tmp")
        tmp.write_text(json.dumps(manifest, ensure_ascii=False, indent=2), encoding="utf-8")
        os.replace(tmp, self.manifest_path)

    def read_manifest(self) -> dict:
        if not self.manifest_path.exists():
            return {}
        return json.loads(self.manifest_path.read_text(encoding="utf-8"))

    def write_run_report(self, report: dict) -> Path:
        self.runs_dir.mkdir(parents=True, exist_ok=True)
        path = self.runs_dir / f"{report['run_id']}.json"
        path.write_text(json.dumps(report, ensure_ascii=False, indent=2), encoding="utf-8")
        return path


def _columns_for(key: str) -> Sequence[str]:
    return {
        "orders": ORDER_COLUMNS,
        "lines": LINE_COLUMNS,
        "packages": PACKAGE_COLUMNS,
        "events": EVENT_COLUMNS,
        "raw": RAW_COLUMNS,
    }[key]
