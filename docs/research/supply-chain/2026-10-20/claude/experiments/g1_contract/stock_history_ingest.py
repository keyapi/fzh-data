#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""通途每日库存快照 —— 离线历史入库 / dry-run（方案 v4 实现）。

只读本地 run 目录（`manifest.json` + `warehouse=*.jsonl`），计算：

- 确定性 run_id（legacy 由 snapshot_at + manifest SHA256 生成）
- manifest 与每个 JSONL 的 SHA256 基线
- 批次完整性（batch_complete / scope_complete / run_complete 三级分离）
- 稳定 ID 去重、别名冲突、跨日归属
- 同日多 run 的确定性发布选择与发布指针 / 回滚

写入 DuckDB（内存或临时文件）。**默认 `:memory:`，绝不隐式写 order_store.duckdb。**

用法：
  uv run python stock_history_ingest.py --run-dir "D:/Work/库存备份/2026-10-21" \
      --source legacy --dry-run
  uv run python stock_history_ingest.py --run-dir <run_dir> --source scheduled --db <tmp.duckdb>
  uv run python stock_history_ingest.py --rollback 2026-10-21 --db <db> [--dry-run]

约束：不访问通途 / EN；不改计划任务；不把原始 JSONL 提交进仓库。
"""

from __future__ import annotations

import argparse
import hashlib
import json
import math
import os
import re
import sys
import uuid
from dataclasses import dataclass, field
from datetime import date, datetime, timedelta, timezone
from pathlib import Path
from typing import Any, Sequence

try:
    import duckdb
except ModuleNotFoundError as exc:  # pragma: no cover - 环境缺失时给出可执行提示
    raise SystemExit(
        "缺少 duckdb：请执行 `uv pip install duckdb`（或 `uv add duckdb`）后重试。"
    ) from exc

# Asia/Shanghai 无夏令时，用固定 +08:00，避免 Windows 缺 tzdata 时 zoneinfo 失败。
SHANGHAI = timezone(timedelta(hours=8), name="Asia/Shanghai")

SOURCES = ("legacy", "scheduled", "manual", "unknown")
TEST_SKU = "TEST-1"
UOM_BASIS = "unknown"
DEFAULT_DB = ":memory:"
DEFAULT_LOCK_STALE_SECONDS = 6 * 3600

# 负数库存是合法的（通途可用量可为负）；只要求有限数值。
NUMERIC_FIELDS = (
    ("availableStockQuantity", "available"),
    ("intransitStockQuantity", "intransit"),
    ("defectsStockQuantity", "defects"),
    ("waitingShipmentStockQuantity", "waiting_shipment"),
)
REQUIRED_ROW_KEYS = tuple(src for src, _ in NUMERIC_FIELDS) + (
    "goodsIdKey",
    "warehouseIdKey",
    "goodsSku",
)
DATE_DIR_RE = re.compile(r"^\d{4}-\d{2}-\d{2}$")


# --------------------------------------------------------------------------- #
# 异常
# --------------------------------------------------------------------------- #


class IngestError(Exception):
    """入库流程可预期的业务错误（CLI 返回非零码）。"""


class DateAttributionError(IngestError):
    """snapshot_at / manifest / 目录日期不一致。"""


class DataIntegrityError(IngestError):
    """哈希、完整性或稳定 ID 校验失败，拒绝发布。"""


class LockHeld(IngestError):
    """另一个进程持有 stock_history.lock。"""


class MigrationFailure(IngestError):
    """schema 迁移失败（已回滚）。"""


class UomBasisError(IngestError):
    """uom_basis=unknown，禁止跨 SKU / 品类求和。"""


class RollbackUnavailable(IngestError):
    """没有 previous_run_id 或前序 run 的行已不可重放。"""


# --------------------------------------------------------------------------- #
# 基础工具
# --------------------------------------------------------------------------- #


def sha256_file(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as fh:
        for chunk in iter(lambda: fh.read(1024 * 1024), b""):
            digest.update(chunk)
    return digest.hexdigest()


def parse_local_datetime(raw: str) -> datetime:
    """把 manifest / run_meta 的时间解析成 Asia/Shanghai aware datetime。

    无时区偏移按 +08:00 解释（诊断文档口径）；`Z` 与 `±HH:MM` 正常换算。
    """
    if not isinstance(raw, str) or not raw.strip():
        raise IngestError(f"时间字段为空或非字符串: {raw!r}")
    text = raw.strip()
    if text.endswith("Z"):
        text = text[:-1] + "+00:00"
    try:
        parsed = datetime.fromisoformat(text)
    except ValueError as exc:
        raise IngestError(f"无法解析时间: {raw!r}") from exc
    if parsed.tzinfo is None:
        parsed = parsed.replace(tzinfo=SHANGHAI)
    return parsed.astimezone(SHANGHAI)


def to_naive_local(dt: datetime | None) -> datetime | None:
    """DuckDB TIMESTAMP 列统一存 naive +08 本地时间。"""
    if dt is None:
        return None
    if dt.tzinfo is None:
        return dt
    return dt.astimezone(SHANGHAI).replace(tzinfo=None)


def to_utc_naive_now() -> datetime:
    return datetime.now(timezone.utc).replace(tzinfo=None)


def json_dumps(obj: Any) -> str:
    return json.dumps(obj, ensure_ascii=False, sort_keys=True, separators=(",", ":"))


def _json_default(value: Any) -> Any:
    if isinstance(value, (date, datetime)):
        return value.isoformat()
    if isinstance(value, Path):
        return str(value)
    if isinstance(value, set):
        return sorted(value)
    raise TypeError(f"not JSON serialisable: {type(value)!r}")


def report_json(report: dict) -> str:
    return json.dumps(report, ensure_ascii=False, indent=2, default=_json_default)


# --------------------------------------------------------------------------- #
# 数据模型
# --------------------------------------------------------------------------- #


@dataclass
class WarehouseResult:
    warehouse_id: str
    warehouse_name: str
    file_name: str | None
    file_path: str | None
    file_sha256: str | None
    manifest_rows: int | None
    rows_read: int
    bad_rows: int
    duplicate_rows: int
    records: list[dict] = field(default_factory=list)
    # 去重前的 (goods_id, goods_sku) 观测；同一 goods_id 多别名靠它保留。
    goods_aliases: set[tuple[str, str]] = field(default_factory=set)
    errors: list[dict] = field(default_factory=list)
    complete_requested: bool = False
    truncated: bool = False
    manifest_error: str | None = None
    rows_mismatch: bool = False
    batch_complete: bool = False

    @property
    def unique_rows(self) -> int:
        return len(self.records)

    def to_report(self) -> dict:
        return {
            "warehouse_id": self.warehouse_id,
            "warehouse_name": self.warehouse_name,
            "file": self.file_name,
            "file_sha256": self.file_sha256,
            "manifest_rows": self.manifest_rows,
            "rows_read": self.rows_read,
            "unique_rows": self.unique_rows,
            "bad_rows": self.bad_rows,
            "duplicate_rows": self.duplicate_rows,
            "complete_requested": self.complete_requested,
            "truncated": self.truncated,
            "batch_complete": self.batch_complete,
            "rows_mismatch": self.rows_mismatch,
            "error": self.manifest_error,
            "validation_errors": self.errors,
        }


@dataclass
class RunBundle:
    run_id: str
    source: str
    run_dir: str
    snapshot_date: date
    snapshot_at_raw: str
    snapshot_at: datetime
    manifest_sha256: str
    manifest_complete: bool | None
    started_at: datetime | None
    ended_at: datetime | None
    exit_code: int | None
    trigger: str | None
    sealed: bool
    sealing_exemption: str | None
    warehouses: list[WarehouseResult] = field(default_factory=list)
    integrity_errors: list[dict] = field(default_factory=list)
    baseline: dict = field(default_factory=dict)
    run_meta: dict = field(default_factory=dict)

    @property
    def warehouse_scope(self) -> list[str]:
        return [w.warehouse_id for w in self.warehouses]

    @property
    def rows_read(self) -> int:
        return sum(w.rows_read for w in self.warehouses)

    @property
    def rows_ingested(self) -> int:
        return sum(w.unique_rows for w in self.warehouses)

    @property
    def bad_rows(self) -> int:
        return sum(w.bad_rows for w in self.warehouses)

    @property
    def duplicate_rows(self) -> int:
        return sum(w.duplicate_rows for w in self.warehouses)

    @property
    def scope_coverage(self) -> int:
        return sum(1 for w in self.warehouses if w.batch_complete)

    @property
    def scope_complete(self) -> bool:
        return bool(self.warehouses) and all(w.batch_complete for w in self.warehouses)

    @property
    def run_complete(self) -> bool:
        # manifest.complete 是"全量启用仓"的权威标志。缺失只能判 unknown（false），
        # 绝不能用 scope_complete 冒充：manifest 没写就不知道是否漏了仓。
        if self.manifest_complete is None:
            return False
        return self.scope_complete and bool(self.manifest_complete)

    @property
    def integrity_ok(self) -> bool:
        return not self.integrity_errors

    @property
    def test_sku_rows(self) -> int:
        return sum(1 for w in self.warehouses for r in w.records if r["is_test"])

    def rank_key(self) -> tuple:
        """同日多 run 的确定性偏好：完整 > 范围完整 > 覆盖仓数 > ended_at > run_id。"""
        ended = to_naive_local(self.ended_at) or datetime.min
        return (
            int(self.run_complete),
            int(self.scope_complete),
            int(self.scope_coverage),
            ended,
            self.run_id,
        )

    def to_report(self) -> dict:
        return {
            "run_id": self.run_id,
            "source": self.source,
            "run_dir": self.run_dir,
            "snapshot_date": self.snapshot_date.isoformat(),
            "snapshot_at_raw": self.snapshot_at_raw,
            "snapshot_at_local": self.snapshot_at.isoformat(),
            "manifest_sha256": self.manifest_sha256,
            "sealed": self.sealed,
            "sealing_exemption": self.sealing_exemption,
            "started_at": self.started_at.isoformat() if self.started_at else None,
            "ended_at": self.ended_at.isoformat() if self.ended_at else None,
            "exit_code": self.exit_code,
            "trigger": self.trigger,
            "manifest_complete": self.manifest_complete,
            "warehouse_scope": self.warehouse_scope,
            "warehouses_total": len(self.warehouses),
            "warehouses_complete": self.scope_coverage,
            "scope_complete": self.scope_complete,
            "run_complete": self.run_complete,
            "rows_read": self.rows_read,
            "rows_ingested": self.rows_ingested,
            "duplicate_rows": self.duplicate_rows,
            "bad_rows": self.bad_rows,
            "test_sku_rows": self.test_sku_rows,
            "uom_basis": UOM_BASIS,
            "integrity_ok": self.integrity_ok,
            "integrity_errors": self.integrity_errors,
            "baseline": self.baseline,
            "warehouses": [w.to_report() for w in self.warehouses],
        }


# --------------------------------------------------------------------------- #
# 读取 run 目录
# --------------------------------------------------------------------------- #


def _expected_file_name(warehouse_id: str, warehouse_name: str) -> str:
    return f"warehouse={warehouse_id}_{warehouse_name}.jsonl"


def _resolve_warehouse_file(
    run_dir: Path, entry: dict, warehouse_id: str, warehouse_name: str
) -> Path | None:
    """manifest 里的绝对路径只是提示（历史备份有指向旧目录的），以 basename 为准。"""
    candidates: list[str] = []
    raw = entry.get("file")
    if isinstance(raw, str) and raw.strip():
        candidates.append(Path(raw).name)
    candidates.append(_expected_file_name(warehouse_id, warehouse_name))
    for name in dict.fromkeys(candidates):
        path = run_dir / name
        if path.is_file():
            return path
    return None


def _is_number(value: Any) -> bool:
    return isinstance(value, (int, float)) and not isinstance(value, bool) and math.isfinite(value)


def _normalise_row(raw: dict, fallback_warehouse: str) -> tuple[dict | None, str | None]:
    missing = [k for k in REQUIRED_ROW_KEYS if k not in raw]
    if missing:
        return None, f"missing_keys:{','.join(sorted(missing))}"
    goods_id = str(raw.get("goodsIdKey") or "").strip()
    warehouse_id = str(raw.get("warehouseIdKey") or "").strip()
    if not goods_id:
        return None, "empty_goods_id"
    if not warehouse_id:
        return None, "empty_warehouse_id"
    sku = raw.get("goodsSku")
    sku = "" if sku is None else str(sku).strip()
    values: dict[str, Any] = {}
    for src, dst in NUMERIC_FIELDS:
        value = raw[src]
        if not _is_number(value):
            return None, f"bad_number:{src}"
        values[dst] = float(value)
    warehouse_name = str(raw.get("warehouseName") or fallback_warehouse).strip()
    return {
        "warehouse_id": warehouse_id,
        "goods_id": goods_id,
        "goods_sku": sku,
        "warehouse_name": warehouse_name,
        "available": values["available"],
        "intransit": values["intransit"],
        "defects": values["defects"],
        "waiting_shipment": values["waiting_shipment"],
        "is_test": sku == TEST_SKU,
        "uom_basis": UOM_BASIS,
    }, None


def _dedupe_records(
    rows: list[dict],
) -> tuple[list[dict], int, list[dict]]:
    """按 (warehouse_id, goods_id) 去重；数值一致去重计数，数值冲突则整 run 拒绝。"""
    grouped: dict[tuple[str, str], tuple[tuple, dict]] = {}
    duplicates = 0
    conflicts: list[dict] = []
    for row in rows:
        key = (row["warehouse_id"], row["goods_id"])
        signature = (
            row["available"],
            row["intransit"],
            row["defects"],
            row["waiting_shipment"],
        )
        if key not in grouped:
            grouped[key] = (signature, row)
            continue
        seen_signature, _ = grouped[key]
        if seen_signature == signature:
            duplicates += 1
            continue
        conflicts.append(
            {
                "warehouse_id": key[0],
                "goods_id": key[1],
                "first": list(seen_signature),
                "second": list(signature),
            }
        )
        # 保留第一条，冲突本身会让 integrity_ok=False，行不会入库。
    return [row for _, row in grouped.values()], duplicates, conflicts


def _load_warehouse(
    run_dir: Path, entry: dict, index: int
) -> WarehouseResult:
    warehouse_id = str(entry.get("warehouseId") or "").strip()
    warehouse_name = str(entry.get("warehouseName") or "").strip()
    if not warehouse_id:
        return WarehouseResult(
            warehouse_id=f"<missing-{index}>",
            warehouse_name=warehouse_name or "<missing>",
            file_name=None,
            file_path=None,
            file_sha256=None,
            manifest_rows=entry.get("rows") if isinstance(entry.get("rows"), int) else None,
            rows_read=0,
            bad_rows=0,
            duplicate_rows=0,
            errors=[{"code": "missing_warehouse_id", "message": "manifest 仓库项缺 warehouseId"}],
            complete_requested=entry.get("complete") is True,
            truncated=entry.get("truncated") is True,
            manifest_error=entry.get("error"),
        )

    file_path = _resolve_warehouse_file(run_dir, entry, warehouse_id, warehouse_name)
    manifest_error = entry.get("error")
    manifest_rows = entry.get("rows") if isinstance(entry.get("rows"), int) else None
    complete_requested = entry.get("complete") is True
    truncated = entry.get("truncated") is True

    result = WarehouseResult(
        warehouse_id=warehouse_id,
        warehouse_name=warehouse_name,
        file_name=file_path.name if file_path else None,
        file_path=str(file_path) if file_path else None,
        file_sha256=sha256_file(file_path) if file_path else None,
        manifest_rows=manifest_rows,
        rows_read=0,
        bad_rows=0,
        duplicate_rows=0,
        complete_requested=complete_requested,
        truncated=truncated,
        manifest_error=manifest_error if isinstance(manifest_error, str) else None,
    )

    errors = result.errors

    if file_path is None:
        errors.append(
            {
                "code": "missing_file",
                "message": f"仓库文件不存在: {_expected_file_name(warehouse_id, warehouse_name)}",
            }
        )
        if complete_requested:
            errors.append(
                {
                    "code": "complete_without_file",
                    "message": "manifest 标记 complete=true 但文件缺失，按 unknown 处理",
                }
            )
        return result

    raw_rows: list[dict] = []
    with file_path.open("r", encoding="utf-8") as fh:
        for lineno, line in enumerate(fh, start=1):
            if not line.strip():
                continue
            result.rows_read += 1
            try:
                raw = json.loads(line)
            except json.JSONDecodeError as exc:
                result.bad_rows += 1
                errors.append(
                    {"code": "bad_json", "line": lineno, "message": str(exc)}
                )
                continue
            if not isinstance(raw, dict):
                result.bad_rows += 1
                errors.append({"code": "bad_row_type", "line": lineno, "message": "not an object"})
                continue
            normalised, problem = _normalise_row(raw, warehouse_name)
            if normalised is None:
                result.bad_rows += 1
                errors.append({"code": "bad_row", "line": lineno, "message": problem})
                continue
            if normalised["warehouse_id"] != warehouse_id:
                errors.append(
                    {
                        "code": "warehouse_id_mismatch",
                        "line": lineno,
                        "message": f"行内 {normalised['warehouse_id']} != manifest {warehouse_id}",
                    }
                )
            raw_rows.append(normalised)

    records, duplicates, conflicts = _dedupe_records(raw_rows)
    result.records = records
    result.duplicate_rows = duplicates
    result.goods_aliases = {
        (item["goods_id"], item["goods_sku"]) for item in raw_rows if item["goods_sku"]
    }
    for conflict in conflicts:
        errors.append({"code": "duplicate_value_conflict", **conflict})

    if manifest_rows is not None and complete_requested and manifest_rows != result.rows_read:
        result.rows_mismatch = True
        errors.append(
            {
                "code": "manifest_rows_mismatch",
                "message": f"manifest rows={manifest_rows} 文件行={result.rows_read}",
            }
        )

    result.batch_complete = (
        complete_requested
        and not truncated
        and not result.manifest_error
        and result.bad_rows == 0
        and not result.rows_mismatch
        and not conflicts
        and not any(e["code"] == "warehouse_id_mismatch" for e in errors)
    )
    return result


def _read_json_file(path: Path, label: str) -> dict:
    try:
        with path.open("r", encoding="utf-8") as fh:
            data = json.load(fh)
    except (OSError, json.JSONDecodeError) as exc:
        raise IngestError(f"{label} 读取失败: {path}: {exc}") from exc
    if not isinstance(data, dict):
        raise IngestError(f"{label} 不是 JSON 对象: {path}")
    return data


def _normalise_hash_map(entries: Any) -> dict[str, str]:
    """接受 {name: sha} 或 [{path/file: ..., sha256: ...}] 两种封存格式。"""
    result: dict[str, str] = {}
    if isinstance(entries, dict):
        for name, sha in entries.items():
            if isinstance(sha, str):
                result[Path(str(name)).name] = sha
    elif isinstance(entries, list):
        for item in entries:
            if not isinstance(item, dict):
                continue
            name = item.get("path") or item.get("file") or item.get("name")
            sha = item.get("sha256")
            if isinstance(name, str) and isinstance(sha, str):
                result[Path(name).name] = sha
    return result


def _verify_hash_manifest(
    label: str,
    payload: dict,
    manifest_sha: str,
    actual_files: dict[str, str],
    require_complete: bool,
) -> list[dict]:
    errors: list[dict] = []
    expected_manifest = payload.get("manifest_sha256")
    if require_complete and not isinstance(expected_manifest, str):
        errors.append(
            {"code": "missing_manifest_sha256", "source": label,
             "message": "封存清单缺少 manifest_sha256"}
        )
    if expected_manifest is not None and expected_manifest != manifest_sha:
        errors.append(
            {
                "code": "hash_mismatch",
                "source": label,
                "file": "manifest.json",
                "expected": expected_manifest,
                "actual": manifest_sha,
            }
        )
    listed = _normalise_hash_map(payload.get("files"))
    for name, expected in listed.items():
        actual = actual_files.get(name)
        if actual is None:
            errors.append(
                {"code": "sealed_file_missing", "source": label, "file": name}
            )
        elif actual != expected:
            errors.append(
                {
                    "code": "hash_mismatch",
                    "source": label,
                    "file": name,
                    "expected": expected,
                    "actual": actual,
                }
            )
    if require_complete:
        missing = sorted(set(actual_files) - set(listed))
        if missing:
            errors.append(
                {
                    "code": "seal_incomplete",
                    "source": label,
                    "missing": missing,
                    "message": "封存清单未覆盖全部 manifest/JSONL 文件",
                }
            )
    return errors


def _load_baseline(path: Path) -> dict:
    return _read_json_file(path, "baseline")


def _compare_baseline(
    baseline: dict, manifest_sha: str, actual_files: dict[str, str]
) -> list[dict]:
    errors: list[dict] = []
    expected_manifest = baseline.get("manifest_sha256")
    if expected_manifest and expected_manifest != manifest_sha:
        errors.append(
            {
                "code": "baseline_manifest_mismatch",
                "expected": expected_manifest,
                "actual": manifest_sha,
            }
        )
    expected_files = _normalise_hash_map(baseline.get("files"))
    for name, expected in expected_files.items():
        actual = actual_files.get(name)
        if actual is None:
            errors.append({"code": "baseline_file_missing", "file": name})
        elif actual != expected:
            errors.append(
                {
                    "code": "baseline_hash_mismatch",
                    "file": name,
                    "expected": expected,
                    "actual": actual,
                }
            )
    for name in sorted(set(actual_files) - set(expected_files)):
        errors.append({"code": "baseline_file_unlisted", "file": name})
    return errors


def _derive_legacy_run_id(snapshot_at: datetime, manifest_sha: str) -> str:
    return f"legacy-{snapshot_at.strftime('%Y%m%dT%H%M%S')}-{manifest_sha[:8]}"


def _dir_date_hint(run_dir: Path) -> date | None:
    name = run_dir.name
    if DATE_DIR_RE.match(name):
        try:
            return date.fromisoformat(name)
        except ValueError:
            return None
    return None


def load_run(
    run_dir: str | Path,
    source: str = "unknown",
    run_id: str | None = None,
    baseline_in: str | Path | None = None,
) -> RunBundle:
    """只读加载并校验一个 run 目录，返回完整 RunBundle（无 DB 写入）。"""
    if source not in SOURCES:
        raise IngestError(f"source 必须是 {SOURCES} 之一，收到 {source!r}")
    root = Path(run_dir)
    if not root.is_dir():
        raise IngestError(f"run 目录不存在: {root}")
    manifest_path = root / "manifest.json"
    if not manifest_path.is_file():
        subdirs = [p for p in root.iterdir() if p.is_dir() and (p / "manifest.json").is_file()]
        hint = f"；发现子目录 {[p.name for p in subdirs]}，请直接指向 run 目录" if subdirs else ""
        raise IngestError(f"缺少 manifest.json: {root}{hint}")

    manifest_sha = sha256_file(manifest_path)
    manifest = _read_json_file(manifest_path, "manifest")

    snapshot_raw = manifest.get("snapshot_at")
    snapshot_at = parse_local_datetime(snapshot_raw)
    attributed_date = snapshot_at.date()

    manifest_date_raw = manifest.get("snapshot_date")
    if isinstance(manifest_date_raw, str) and manifest_date_raw.strip():
        try:
            manifest_date = date.fromisoformat(manifest_date_raw.strip())
        except ValueError as exc:
            raise DateAttributionError(
                f"manifest snapshot_date 非法: {manifest_date_raw!r}"
            ) from exc
        if manifest_date != attributed_date:
            raise DateAttributionError(
                "snapshot_at 的 Asia/Shanghai 日期与 manifest.snapshot_date 冲突: "
                f"{attributed_date} vs {manifest_date}"
            )
    else:
        manifest_date = attributed_date

    dir_date = _dir_date_hint(root)
    if dir_date is not None and dir_date != attributed_date:
        raise DateAttributionError(
            f"目录日期 {dir_date} 与 snapshot_at 归属日期 {attributed_date} 冲突；"
            "拒绝导入（跨日补跑必须落在 snapshot_at 所属日期目录）"
        )

    run_meta: dict = {}
    meta_path = root / "run_meta.json"
    if meta_path.is_file():
        run_meta = _read_json_file(meta_path, "run_meta")
        meta_date = run_meta.get("snapshot_date")
        if isinstance(meta_date, str) and meta_date.strip():
            try:
                meta_day = date.fromisoformat(meta_date.strip())
            except ValueError as exc:
                raise DateAttributionError(
                    f"run_meta.snapshot_date 非法: {meta_date!r}"
                ) from exc
            if meta_day != attributed_date:
                raise DateAttributionError(
                    "run_meta.snapshot_date 与 snapshot_at 归属日期冲突: "
                    f"{meta_day} vs {attributed_date}"
                )

    if source == "legacy":
        derived_id = _derive_legacy_run_id(snapshot_at, manifest_sha)
    else:
        derived_id = run_meta.get("run_id")
        if not isinstance(derived_id, str) or not derived_id.strip():
            name = root.name
            if name.startswith("run="):
                derived_id = name[4:]
            else:
                derived_id = None
    effective_run_id = (run_id or derived_id or "").strip()
    if not effective_run_id:
        raise IngestError(
            "非 legacy run 必须提供 run_meta.json 的 run_id、目录名 run=<id> 或 --run-id"
        )

    warehouses: list[WarehouseResult] = []
    entries = manifest.get("warehouses")
    if not isinstance(entries, list):
        raise IngestError("manifest.warehouses 必须是数组")
    for index, entry in enumerate(entries):
        if not isinstance(entry, dict):
            raise IngestError(f"manifest.warehouses[{index}] 不是对象")
        warehouses.append(_load_warehouse(root, entry, index))

    if not warehouses:
        raise IngestError("manifest.warehouses 为空，无法定义目标仓集合")

    actual_files = {"manifest.json": manifest_sha}
    for wh in warehouses:
        if wh.file_name and wh.file_sha256:
            actual_files[wh.file_name] = wh.file_sha256

    started_candidates = [
        parse_local_datetime(e["capture_start"])
        for e in entries
        if isinstance(e, dict) and isinstance(e.get("capture_start"), str)
    ]
    ended_candidates = [
        parse_local_datetime(e["capture_end"])
        for e in entries
        if isinstance(e, dict) and isinstance(e.get("capture_end"), str)
    ]
    started_at = parse_local_datetime(run_meta["started_at"]) if isinstance(run_meta.get("started_at"), str) else (min(started_candidates) if started_candidates else None)
    ended_at = parse_local_datetime(run_meta["ended_at"]) if isinstance(run_meta.get("ended_at"), str) else (max(ended_candidates) if ended_candidates else snapshot_at)
    exit_code = run_meta.get("exit_code") if isinstance(run_meta.get("exit_code"), int) else None
    trigger = run_meta.get("trigger") if isinstance(run_meta.get("trigger"), str) else None

    seal_path = root / ".sealed"
    sealed = seal_path.is_file()
    integrity_errors: list[dict] = []
    sealing_exemption: str | None = None

    if sealed:
        seal = _read_json_file(seal_path, ".sealed")
        integrity_errors.extend(
            _verify_hash_manifest(".sealed", seal, manifest_sha, actual_files, require_complete=True)
        )
    elif source == "legacy":
        sealing_exemption = "legacy"
    else:
        integrity_errors.append(
            {
                "code": "unsealed_run",
                "message": "非 legacy run 缺少 .sealed，按方案禁止进入发布流程",
            }
        )

    if run_meta:
        integrity_errors.extend(
            _verify_hash_manifest(
                "run_meta.json", run_meta, manifest_sha, actual_files, require_complete=False
            )
        )

    baseline = {
        "run_dir": str(root),
        "snapshot_date": attributed_date.isoformat(),
        "manifest_sha256": manifest_sha,
        "files": dict(sorted(actual_files.items())),
    }
    if baseline_in is not None:
        integrity_errors.extend(
            _compare_baseline(_load_baseline(Path(baseline_in)), manifest_sha, actual_files)
        )

    for wh in warehouses:
        for issue in wh.errors:
            # 显式失败/缺文件的仓是合法 `unknown`，不算整 run 的完整性错误；
            # 只有"声称完整却缺文件"或数据本身损坏才拒绝发布。
            if issue["code"] in {
                "missing_warehouse_id",
                "complete_without_file",
                "bad_json",
                "bad_row",
                "bad_row_type",
                "duplicate_value_conflict",
                "manifest_rows_mismatch",
                "warehouse_id_mismatch",
            }:
                integrity_errors.append(
                    {
                        "code": issue["code"],
                        "warehouse_id": wh.warehouse_id,
                        "message": issue.get("message", ""),
                    }
                )

    manifest_complete = manifest.get("complete") if isinstance(manifest.get("complete"), bool) else None

    return RunBundle(
        run_id=effective_run_id,
        source=source,
        run_dir=str(root.resolve()),
        snapshot_date=attributed_date,
        snapshot_at_raw=str(snapshot_raw),
        snapshot_at=snapshot_at,
        manifest_sha256=manifest_sha,
        manifest_complete=manifest_complete,
        started_at=started_at,
        ended_at=ended_at,
        exit_code=exit_code,
        trigger=trigger,
        sealed=sealed,
        sealing_exemption=sealing_exemption,
        warehouses=warehouses,
        integrity_errors=integrity_errors,
        baseline=baseline,
        run_meta=run_meta,
    )


# --------------------------------------------------------------------------- #
# schema 迁移
# --------------------------------------------------------------------------- #

CORE_DDL = [
    """
    CREATE TABLE stock_run (
      run_id VARCHAR PRIMARY KEY,
      snapshot_date DATE NOT NULL,
      snapshot_at_raw VARCHAR,
      snapshot_at TIMESTAMP,
      started_at TIMESTAMP,
      ended_at TIMESTAMP,
      exit_code INTEGER,
      trigger VARCHAR,
      manifest_sha256 VARCHAR,
      manifest_complete BOOLEAN,
      scope_complete BOOLEAN,
      run_complete BOOLEAN,
      scope_coverage INTEGER,
      source VARCHAR,
      sealed BOOLEAN,
      sealing_exemption VARCHAR,
      warehouse_scope VARCHAR,
      run_dir VARCHAR,
      rows_read INTEGER,
      rows_ingested INTEGER,
      duplicate_rows INTEGER,
      bad_rows INTEGER,
      integrity_ok BOOLEAN,
      integrity_errors VARCHAR,
      ingested_at TIMESTAMP
    )
    """,
    """
    CREATE TABLE stock_run_warehouse (
      run_id VARCHAR,
      warehouse_id VARCHAR,
      warehouse_name VARCHAR,
      rows INTEGER,
      rows_unique INTEGER,
      bad_rows INTEGER,
      duplicate_rows INTEGER,
      complete BOOLEAN,
      error VARCHAR,
      file VARCHAR,
      file_sha256 VARCHAR,
      manifest_rows INTEGER,
      batch_complete BOOLEAN,
      PRIMARY KEY (run_id, warehouse_id)
    )
    """,
    # 每个 run 的原始行（审计 + 回滚重放）；stock_history 只存已发布日期的物化行。
    """
    CREATE TABLE stock_history_run (
      run_id VARCHAR,
      snapshot_date DATE,
      warehouse_id VARCHAR,
      goods_id VARCHAR,
      goods_sku VARCHAR,
      warehouse_name VARCHAR,
      available DOUBLE,
      intransit DOUBLE,
      defects DOUBLE,
      waiting_shipment DOUBLE,
      batch_complete BOOLEAN,
      is_test BOOLEAN,
      uom_basis VARCHAR,
      ingested_at TIMESTAMP,
      PRIMARY KEY (run_id, warehouse_id, goods_id)
    )
    """,
    """
    CREATE TABLE stock_history (
      snapshot_date DATE,
      run_id VARCHAR,
      warehouse_id VARCHAR,
      goods_id VARCHAR,
      goods_sku VARCHAR,
      warehouse_name VARCHAR,
      available DOUBLE,
      intransit DOUBLE,
      defects DOUBLE,
      waiting_shipment DOUBLE,
      batch_complete BOOLEAN,
      is_test BOOLEAN,
      stockout_observed BOOLEAN,
      uom_basis VARCHAR,
      ingested_at TIMESTAMP,
      PRIMARY KEY (snapshot_date, warehouse_id, goods_id)
    )
    """,
    """
    CREATE TABLE stock_id_observation (
      run_id VARCHAR,
      entity_type VARCHAR,
      entity_id VARCHAR,
      name VARCHAR,
      PRIMARY KEY (run_id, entity_type, entity_id, name)
    )
    """,
    """
    CREATE TABLE stock_id_history (
      entity_type VARCHAR,
      entity_id VARCHAR,
      name VARCHAR,
      valid_from DATE,
      valid_to DATE,
      source_run VARCHAR,
      PRIMARY KEY (entity_type, entity_id, name, valid_from)
    )
    """,
    """
    CREATE TABLE stock_publish (
      snapshot_date DATE PRIMARY KEY,
      run_id VARCHAR,
      published_at TIMESTAMP,
      previous_run_id VARCHAR
    )
    """,
    """
    CREATE TABLE stock_ingest_event (
      event_id VARCHAR PRIMARY KEY,
      run_id VARCHAR,
      snapshot_date DATE,
      action VARCHAR,
      detail VARCHAR,
      created_at TIMESTAMP
    )
    """,
]

VIEW_DDL = [
    # 默认分析视图：排除 TEST-1；不提供跨 SKU 求和。
    """
    CREATE VIEW v_stock_history_analysis AS
    SELECT snapshot_date, run_id, warehouse_id, goods_id, goods_sku, warehouse_name,
           available, intransit, defects, waiting_shipment,
           batch_complete, uom_basis
    FROM stock_history
    WHERE is_test = FALSE
    """,
    """
    CREATE VIEW v_stockout_observed AS
    SELECT snapshot_date, run_id, warehouse_id, goods_id, goods_sku, available
    FROM stock_history
    WHERE stockout_observed = TRUE
    """,
    # 唯一允许的聚合口径：按 SKU（goods_id）分组，绝不跨 SKU 相加。
    """
    CREATE VIEW v_stock_by_sku AS
    SELECT snapshot_date, warehouse_id, goods_id, goods_sku,
           SUM(available) AS available,
           SUM(intransit) AS intransit,
           SUM(defects) AS defects,
           SUM(waiting_shipment) AS waiting_shipment,
           MIN(uom_basis) AS uom_basis
    FROM stock_history
    WHERE is_test = FALSE
    GROUP BY snapshot_date, warehouse_id, goods_id, goods_sku
    """,
    """
    CREATE VIEW v_stock_run_status AS
    SELECT r.run_id, r.snapshot_date, r.source, r.sealed, r.sealing_exemption,
           r.scope_complete, r.run_complete, r.scope_coverage,
           r.integrity_ok, p.run_id AS published_run_id,
           (p.run_id = r.run_id) AS is_published
    FROM stock_run r
    LEFT JOIN stock_publish p ON p.snapshot_date = r.snapshot_date
    """,
]

MIGRATIONS: list[tuple[int, str, Sequence[str]]] = [
    (1, "core tables (runs / history / publish / events)", CORE_DDL),
    (2, "analysis views (test excluded, per-SKU aggregation only)", VIEW_DDL),
]


def migrate(
    conn: "duckdb.DuckDBPyConnection",
    migrations: Sequence[tuple[int, str, Sequence[str]]] | None = None,
) -> list[int]:
    """按版本应用迁移；任一版本失败则整版回滚（DuckDB 支持事务性 DDL）。"""
    plan = list(migrations if migrations is not None else MIGRATIONS)
    conn.execute(
        "CREATE TABLE IF NOT EXISTS schema_migrations ("
        "version INTEGER PRIMARY KEY, description VARCHAR, applied_at TIMESTAMP)"
    )
    applied = {row[0] for row in conn.execute("SELECT version FROM schema_migrations").fetchall()}
    newly_applied: list[int] = []
    for version, description, statements in sorted(plan, key=lambda item: item[0]):
        if version in applied:
            continue
        conn.execute("BEGIN TRANSACTION")
        try:
            for statement in statements:
                conn.execute(statement)
            conn.execute(
                "INSERT INTO schema_migrations VALUES (?, ?, ?)",
                [version, description, to_utc_naive_now()],
            )
            conn.execute("COMMIT")
        except Exception as exc:
            conn.execute("ROLLBACK")
            raise MigrationFailure(f"迁移 v{version} ({description}) 失败并回滚: {exc}") from exc
        newly_applied.append(version)
    return newly_applied


# --------------------------------------------------------------------------- #
# 锁
# --------------------------------------------------------------------------- #


def _hostname() -> str:
    if os.name == "nt":
        return os.environ.get("COMPUTERNAME", "")
    return os.uname().nodename


def _lock_payload(run_dir: str | None) -> dict:
    return {
        "pid": os.getpid(),
        "host": _hostname(),
        "created_at": datetime.now(timezone.utc).isoformat(),
        "run_dir": run_dir,
        "token": uuid.uuid4().hex,
    }


def _try_lock_handle(handle) -> bool:
    """对已打开的文件句柄尝试非阻塞独占锁（成功返回 True）。

    用 OS 文件锁而不是 PID/mtime 判断：进程崩溃时内核自动释放，活进程即使
    持有很久也不会因为超时被别人抢走。
    """
    fd = handle.fileno()
    try:
        if os.name == "nt":
            import msvcrt

            handle.seek(0)
            msvcrt.locking(fd, msvcrt.LK_NBLCK, 1)
        else:
            import fcntl

            fcntl.flock(fd, fcntl.LOCK_EX | fcntl.LOCK_NB)
    except OSError:
        return False
    return True


def _unlock_handle(handle) -> None:
    fd = handle.fileno()
    if os.name == "nt":
        import msvcrt

        handle.seek(0)
        msvcrt.locking(fd, msvcrt.LK_UNLCK, 1)
    else:
        import fcntl

        fcntl.flock(fd, fcntl.LOCK_UN)


class HistoryLock:
    def __init__(self, path: Path, payload: dict, handle=None):
        self.path = path
        self.payload = payload
        self._handle = handle

    def release(self) -> None:
        handle, self._handle = self._handle, None
        if handle is None:
            return
        try:
            _unlock_handle(handle)
        except OSError:
            pass  # 关闭句柄本身也会释放锁
        finally:
            handle.close()


def acquire_lock(
    lock_path: str | Path,
    run_dir: str | None = None,
    stale_after_seconds: int = DEFAULT_LOCK_STALE_SECONDS,
    pid_alive=None,
) -> HistoryLock:
    """用 OS 文件锁独占锁文件（Windows LockFile / POSIX flock）。

    锁随持有进程退出（含崩溃）由内核释放，因此不再按 mtime 抢锁——活进程
    持有再久也不会被 `--lock-stale-seconds` 抢走。锁文件不删除（删除会带来
    "两个进程各锁一个 inode"的竞态），内容只作诊断信息。

    `stale_after_seconds` / `pid_alive` 参数仅为兼容旧调用保留，不再参与判定。
    """
    del stale_after_seconds, pid_alive
    path = Path(lock_path)
    path.parent.mkdir(parents=True, exist_ok=True)
    payload = _lock_payload(run_dir)
    handle = open(path, "a+b")
    if not _try_lock_handle(handle):
        holder: dict = {}
        try:
            handle.seek(0)
            raw = handle.read()
            holder = json.loads(raw.decode("utf-8") or "{}")
        except (OSError, UnicodeDecodeError, json.JSONDecodeError):
            holder = {}
        handle.close()
        pid = holder.get("pid") if isinstance(holder.get("pid"), int) else -1
        raise LockHeld(
            f"锁被占用: {path} (pid={pid}, host={holder.get('host')}); "
            "OS 文件锁由持有进程在内核中保持，确认该进程后再重试；"
            "不要手工删除锁文件来绕过"
        )
    try:
        data = json.dumps(payload).encode("utf-8")
        handle.seek(0)
        handle.truncate(0)
        handle.write(data)
        handle.flush()
        os.fsync(handle.fileno())
    except Exception:
        try:
            _unlock_handle(handle)
        finally:
            handle.close()
        raise
    return HistoryLock(path, payload, handle)


# --------------------------------------------------------------------------- #
# 入库 / 发布 / 回滚
# --------------------------------------------------------------------------- #


def _fetch_run_row(conn: "duckdb.DuckDBPyConnection", run_id: str) -> dict | None:
    rows = conn.execute(
        "SELECT run_id, snapshot_date, run_complete, scope_complete, scope_coverage,"
        " ended_at, integrity_ok FROM stock_run WHERE run_id = ?",
        [run_id],
    ).fetchall()
    if not rows:
        return None
    row = rows[0]
    return {
        "run_id": row[0],
        "snapshot_date": row[1],
        "run_complete": bool(row[2]),
        "scope_complete": bool(row[3]),
        "scope_coverage": int(row[4] or 0),
        "ended_at": row[5],
        "integrity_ok": bool(row[6]),
    }


def get_publish(conn: "duckdb.DuckDBPyConnection", snapshot_date: date) -> dict | None:
    try:
        rows = conn.execute(
            "SELECT snapshot_date, run_id, published_at, previous_run_id"
            " FROM stock_publish WHERE snapshot_date = ?",
            [snapshot_date],
        ).fetchall()
    except duckdb.CatalogException:
        return None
    if not rows:
        return None
    row = rows[0]
    return {
        "snapshot_date": row[0],
        "run_id": row[1],
        "published_at": row[2],
        "previous_run_id": row[3],
    }


def _record_event(
    conn: "duckdb.DuckDBPyConnection",
    run_id: str,
    snapshot_date: date,
    action: str,
    detail: Any,
) -> None:
    conn.execute(
        "INSERT INTO stock_ingest_event VALUES (?, ?, ?, ?, ?, ?)",
        [
            uuid.uuid4().hex,
            run_id,
            snapshot_date,
            action,
            detail if isinstance(detail, str) else report_json(detail),
            to_utc_naive_now(),
        ],
    )


def _bundle_fingerprint(bundle: RunBundle) -> dict:
    """run 的内容指纹：日期 + manifest 哈希 + 每个仓文件的哈希。"""
    return {
        "snapshot_date": bundle.snapshot_date.isoformat(),
        "manifest_sha256": bundle.manifest_sha256,
        "files": {
            wh.file_name: wh.file_sha256
            for wh in bundle.warehouses
            if wh.file_name and wh.file_sha256
        },
    }


def _stored_fingerprint(
    conn: "duckdb.DuckDBPyConnection", run_id: str
) -> dict | None:
    """库里已存在的同一 run_id 的指纹；不存在返回 None。"""
    try:
        rows = conn.execute(
            "SELECT snapshot_date, manifest_sha256 FROM stock_run WHERE run_id = ?",
            [run_id],
        ).fetchall()
    except duckdb.CatalogException:
        return None
    if not rows:
        return None
    snapshot_date, manifest_sha = rows[0]
    if isinstance(snapshot_date, datetime):
        snapshot_date = snapshot_date.date()
    try:
        files = dict(
            conn.execute(
                "SELECT file, file_sha256 FROM stock_run_warehouse"
                " WHERE run_id = ? AND file IS NOT NULL AND file_sha256 IS NOT NULL",
                [run_id],
            ).fetchall()
        )
    except duckdb.CatalogException:
        files = {}
    return {
        "snapshot_date": snapshot_date.isoformat() if snapshot_date else None,
        "manifest_sha256": manifest_sha,
        "files": files,
    }


def stage_run(
    conn: "duckdb.DuckDBPyConnection", bundle: RunBundle, now: datetime | None = None
) -> dict:
    """幂等写入 run 元数据与行。同一 run 重复导入不改变业务内容与 ingested_at。"""
    now = now or to_utc_naive_now()
    existing = conn.execute(
        "SELECT ingested_at FROM stock_run WHERE run_id = ?", [bundle.run_id]
    ).fetchall()
    ingested_at = existing[0][0] if existing and existing[0][0] is not None else now

    # 同一 run_id 的重新导入必须与首次入库的哈希基线完全一致；任何文件内容
    # 变更（哪怕 manifest 哈希没变，只改了 JSONL）都拒绝，绝不"先删后插"。
    stored = _stored_fingerprint(conn, bundle.run_id)
    if stored is not None:
        incoming = _bundle_fingerprint(bundle)
        if stored != incoming:
            _record_event(
                conn,
                bundle.run_id,
                bundle.snapshot_date,
                "reimport_changed_rejected",
                {"stored": stored, "incoming": incoming},
            )
            raise DataIntegrityError(
                f"run {bundle.run_id} 已入库且内容哈希与基线不同，拒绝覆盖："
                f"stored={stored['manifest_sha256']} incoming={incoming['manifest_sha256']} "
                f"files_changed="
                f"{sorted(set(stored['files'].items()) ^ set(incoming['files'].items()))}"
            )

    if stored is not None and not bundle.integrity_ok:
        # 任何已入库的 run（不只是当前发布的那一个）被重新读入且校验失败：不覆盖
        # 已存的元数据 / 原始行 / 发布指针，记录证据后拒绝。回滚目标几乎总不是
        # 当前发布 run：A 发布 → B 替换 → 重导 A 失败 若清掉 A，之后回滚到 A 就
        # 不再可用。因此"是否仍发布"不能作为保护条件。
        _record_event(conn, bundle.run_id, bundle.snapshot_date, "reimport_rejected", bundle.integrity_errors)
        raise DataIntegrityError(
            f"run {bundle.run_id} 已入库但重新校验失败，拒绝覆盖: {bundle.integrity_errors[:3]}"
        )

    conn.execute("BEGIN TRANSACTION")
    try:
        conn.execute("DELETE FROM stock_history_run WHERE run_id = ?", [bundle.run_id])
        conn.execute("DELETE FROM stock_id_observation WHERE run_id = ?", [bundle.run_id])
        conn.execute("DELETE FROM stock_run_warehouse WHERE run_id = ?", [bundle.run_id])
        conn.execute("DELETE FROM stock_run WHERE run_id = ?", [bundle.run_id])
        conn.execute(
            "INSERT INTO stock_run VALUES (?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?)",
            [
                bundle.run_id,
                bundle.snapshot_date,
                bundle.snapshot_at_raw,
                to_naive_local(bundle.snapshot_at),
                to_naive_local(bundle.started_at),
                to_naive_local(bundle.ended_at),
                bundle.exit_code,
                bundle.trigger,
                bundle.manifest_sha256,
                bundle.manifest_complete,
                bundle.scope_complete,
                bundle.run_complete,
                bundle.scope_coverage,
                bundle.source,
                bundle.sealed,
                bundle.sealing_exemption,
                json_dumps(bundle.warehouse_scope),
                bundle.run_dir,
                bundle.rows_read,
                bundle.rows_ingested,
                bundle.duplicate_rows,
                bundle.bad_rows,
                bundle.integrity_ok,
                json_dumps(bundle.integrity_errors),
                ingested_at,
            ],
        )
        for wh in bundle.warehouses:
            conn.execute(
                "INSERT INTO stock_run_warehouse VALUES (?,?,?,?,?,?,?,?,?,?,?,?,?)",
                [
                    bundle.run_id,
                    wh.warehouse_id,
                    wh.warehouse_name,
                    wh.rows_read,
                    wh.unique_rows,
                    wh.bad_rows,
                    wh.duplicate_rows,
                    wh.batch_complete,
                    wh.manifest_error,
                    wh.file_name,
                    wh.file_sha256,
                    wh.manifest_rows,
                    wh.batch_complete,
                ],
            )

        if bundle.integrity_ok:
            insert_rows = [
                (
                    bundle.run_id,
                    bundle.snapshot_date,
                    row["warehouse_id"],
                    row["goods_id"],
                    row["goods_sku"],
                    row["warehouse_name"],
                    row["available"],
                    row["intransit"],
                    row["defects"],
                    row["waiting_shipment"],
                    wh.batch_complete,
                    row["is_test"],
                    row["uom_basis"],
                    ingested_at,
                )
                for wh in bundle.warehouses
                for row in wh.records
            ]
            if insert_rows:
                conn.executemany(
                    "INSERT INTO stock_history_run VALUES (?,?,?,?,?,?,?,?,?,?,?,?,?,?)",
                    insert_rows,
                )
            observations = {
                (wh.warehouse_id, wh.warehouse_name)
                for wh in bundle.warehouses
                if wh.warehouse_name
            }
            if observations:
                conn.executemany(
                    "INSERT INTO stock_id_observation VALUES (?, 'warehouse', ?, ?)"
                    " ON CONFLICT DO NOTHING",
                    [(bundle.run_id, wid, name) for wid, name in sorted(observations)],
                )
            goods_observations = {
                (goods_id, sku)
                for wh in bundle.warehouses
                for goods_id, sku in wh.goods_aliases
            }
            if goods_observations:
                conn.executemany(
                    "INSERT INTO stock_id_observation VALUES (?, 'goods', ?, ?)"
                    " ON CONFLICT DO NOTHING",
                    [(bundle.run_id, gid, sku) for gid, sku in sorted(goods_observations)],
                )
        else:
            _record_event(
                conn, bundle.run_id, bundle.snapshot_date, "integrity_rejected", bundle.integrity_errors
            )
        conn.execute("COMMIT")
    except Exception:
        conn.execute("ROLLBACK")
        raise
    return {"ingested_at": ingested_at, "rows": bundle.rows_ingested}


def _published_alias_conflicts(
    conn: "duckdb.DuckDBPyConnection", bundle: RunBundle
) -> list[dict]:
    """同一别名在同一天已发布的 run 中指向其他 goods_id → 冲突。"""
    current = get_publish(conn, bundle.snapshot_date)
    if not current or current["run_id"] == bundle.run_id:
        return []
    try:
        published = conn.execute(
            "SELECT DISTINCT goods_sku, goods_id FROM stock_history"
            " WHERE snapshot_date = ? AND goods_sku <> ''",
            [bundle.snapshot_date],
        ).fetchall()
    except duckdb.CatalogException:
        return []
    published_map: dict[str, set[str]] = {}
    for sku, goods_id in published:
        published_map.setdefault(sku, set()).add(goods_id)
    conflicts: list[dict] = []
    for sku, ids in _run_alias_map(bundle).items():
        other = published_map.get(sku, set()) - ids
        if other:
            conflicts.append(
                {
                    "code": "alias_conflict_with_published",
                    "goods_sku": sku,
                    "run_goods_ids": sorted(ids),
                    "published_goods_ids": sorted(other),
                    "published_run_id": current["run_id"],
                }
            )
    return conflicts


def _run_alias_map(bundle: RunBundle) -> dict[str, set[str]]:
    aliases: dict[str, set[str]] = {}
    for wh in bundle.warehouses:
        for goods_id, sku in wh.goods_aliases:
            aliases.setdefault(sku, set()).add(goods_id)
    return aliases


def alias_conflicts(bundle: RunBundle) -> list[dict]:
    return [
        {"code": "alias_conflict", "goods_sku": sku, "goods_ids": sorted(ids)}
        for sku, ids in sorted(_run_alias_map(bundle).items())
        if len(ids) > 1
    ]


def id_aliases(bundle: RunBundle) -> list[dict]:
    """同一 goods_id 多个展示别名（允许，写 stock_id_history）。"""
    mapping: dict[str, set[str]] = {}
    for wh in bundle.warehouses:
        for goods_id, sku in wh.goods_aliases:
            mapping.setdefault(goods_id, set()).add(sku)
    return [
        {"goods_id": goods_id, "skus": sorted(skus)}
        for goods_id, skus in sorted(mapping.items())
        if len(skus) > 1
    ]


def evaluate_publish(
    conn: "duckdb.DuckDBPyConnection", bundle: RunBundle
) -> dict:
    """决定是否发布；不写任何东西（供 dry-run 与写模式共用）。

    同日跨 run 的别名冲突不再"先到先占"：冲突双方用同一个总序（`rank_key`）
    裁决——低者确定性 `reject`，高者可以发布。因此无论导入顺序如何，最终
    已发布的 run 相同；冲突证据随决策返回（写模式由 record_decision 落事件）。
    """
    hard_errors = list(bundle.integrity_errors)
    conflicts = alias_conflicts(bundle)
    if conflicts:
        hard_errors.append({"code": "alias_conflict", "conflicts": conflicts})
    if hard_errors:
        return {
            "action": "reject",
            "reason": "integrity_or_alias_conflict",
            "reasons": hard_errors,
            "current_run_id": (get_publish(conn, bundle.snapshot_date) or {}).get("run_id"),
            "previous_run_id": None,
        }

    # 只读路径（dry-run --db）同样要能发现"同 run_id 内容已变"，与写模式一致。
    stored = _stored_fingerprint(conn, bundle.run_id)
    if stored is not None:
        incoming = _bundle_fingerprint(bundle)
        if stored != incoming:
            return {
                "action": "reject",
                "reason": "reimport_changed",
                "reasons": [
                    {"code": "reimport_changed", "stored": stored, "incoming": incoming}
                ],
                "current_run_id": (get_publish(conn, bundle.snapshot_date) or {}).get("run_id"),
                "previous_run_id": None,
            }

    current = get_publish(conn, bundle.snapshot_date)
    if current is None:
        return {
            "action": "publish",
            "reason": "no_published_run_for_date",
            "current_run_id": None,
            "previous_run_id": None,
        }
    if current["run_id"] == bundle.run_id:
        return {
            "action": "already",
            "reason": "candidate_is_already_published",
            "current_run_id": current["run_id"],
            "previous_run_id": current.get("previous_run_id"),
        }

    current_row = _fetch_run_row(conn, current["run_id"])
    if current_row is None:  # 指针指向不存在的 run：允许接管
        return {
            "action": "publish",
            "reason": "published_run_missing_from_stock_run",
            "current_run_id": current["run_id"],
            "previous_run_id": current["run_id"],
        }
    current_key = (
        int(current_row["run_complete"]),
        int(current_row["scope_complete"]),
        int(current_row["scope_coverage"]),
        to_naive_local(current_row["ended_at"]) or datetime.min,
        current_row["run_id"],
    )
    candidate_outranks = bundle.rank_key() > current_key
    candidate_rank = list(bundle.rank_key()[:3]) + [
        str(bundle.rank_key()[3]),
        bundle.rank_key()[4],
    ]
    current_rank = list(current_key[:3]) + [str(current_key[3]), current_key[4]]

    pub_conflicts = _published_alias_conflicts(conn, bundle)
    if pub_conflicts:
        if candidate_outranks:
            return {
                "action": "publish",
                "reason": "candidate_outranks_published_with_alias_conflict",
                "current_run_id": current["run_id"],
                "previous_run_id": current["run_id"],
                "alias_conflicts": pub_conflicts,
                "candidate_rank": candidate_rank,
                "current_rank": current_rank,
            }
        return {
            "action": "reject",
            "reason": "alias_conflict_with_published",
            "reasons": pub_conflicts,
            "current_run_id": current["run_id"],
            "previous_run_id": current.get("previous_run_id"),
            "candidate_rank": candidate_rank,
            "current_rank": current_rank,
        }

    if candidate_outranks:
        return {
            "action": "publish",
            "reason": "candidate_outranks_published",
            "current_run_id": current["run_id"],
            "previous_run_id": current["run_id"],
        }
    return {
        "action": "skip",
        "reason": "published_run_outranks_candidate",
        "current_run_id": current["run_id"],
        "previous_run_id": current.get("previous_run_id"),
        "candidate_rank": candidate_rank,
        "current_rank": current_rank,
    }


def record_decision(
    conn: "duckdb.DuckDBPyConnection", bundle: RunBundle, decision: dict
) -> None:
    """拒绝发布时落一条证据事件（写模式调用；dry-run 不写）。"""
    if decision.get("action") == "reject":
        _record_event(
            conn,
            bundle.run_id,
            bundle.snapshot_date,
            "publish_rejected",
            decision.get("reasons", []),
        )


def _rebuild_id_history(conn: "duckdb.DuckDBPyConnection") -> None:
    """按日期重建别名/改名生效区间，结果只取决于已发布的 run，与导入顺序无关。

    只使用 `stock_publish` 当前指向的 run 的观察；按 snapshot_date 升序遍历，
    某天名字缺席即把该名字的 `valid_to` 截止到当天。因为始终按日期正序重建，
    反向导入（先新后旧）不会产生 `valid_to < valid_from`。同一天被新 run
    替换后，旧 run 的别名自然不再出现在当前发布事实里；回滚重放前序 run 时
    会重新把它的区间建回来。
    """
    conn.execute("DELETE FROM stock_id_history")
    rows = conn.execute(
        "SELECT o.entity_type, o.entity_id, o.name, r.snapshot_date, p.run_id"
        " FROM stock_id_observation o"
        " JOIN stock_run r ON r.run_id = o.run_id"
        " JOIN stock_publish p"
        "   ON p.snapshot_date = r.snapshot_date AND p.run_id = r.run_id"
        " ORDER BY o.entity_type, o.entity_id, r.snapshot_date, o.name"
    ).fetchall()

    # (entity_type, entity_id) -> date -> (该日发布 run_id, 当天观察到的名字集合)
    per_entity: dict[tuple[str, str], dict[date, tuple[str, set[str]]]] = {}
    for entity_type, entity_id, name, snapshot_date, run_id in rows:
        day = snapshot_date.date() if isinstance(snapshot_date, datetime) else snapshot_date
        per_entity.setdefault((entity_type, entity_id), {}).setdefault(
            day, (run_id, set())
        )[1].add(name)

    intervals: list[tuple] = []
    for (entity_type, entity_id), by_day in sorted(per_entity.items()):
        open_names: dict[str, tuple[date, str]] = {}
        for day in sorted(by_day):
            run_id, names = by_day[day]
            for name in sorted(open_names):
                if name not in names:
                    start, source_run = open_names.pop(name)
                    intervals.append(
                        (entity_type, entity_id, name, start, day, source_run)
                    )
            for name in sorted(names):
                if name not in open_names:
                    open_names[name] = (day, run_id)
        for name, (start, source_run) in sorted(open_names.items()):
            intervals.append((entity_type, entity_id, name, start, None, source_run))

    if intervals:
        conn.executemany(
            "INSERT INTO stock_id_history VALUES (?,?,?,?,?,?)", intervals
        )


def materialize(
    conn: "duckdb.DuckDBPyConnection",
    snapshot_date: date,
    run_id: str,
    previous_run_id: str | None,
    action: str = "publish",
) -> dict:
    """单事务替换该日 published 行并更新发布指针。"""
    run = _fetch_run_row(conn, run_id)
    if run is None:
        raise IngestError(f"run 不存在，无法发布: {run_id}")
    if not run["integrity_ok"]:
        raise DataIntegrityError(f"run {run_id} integrity_ok=false，禁止发布")

    conn.execute("BEGIN TRANSACTION")
    try:
        conn.execute("DELETE FROM stock_history WHERE snapshot_date = ?", [snapshot_date])
        conn.execute(
            "INSERT INTO stock_history"
            " SELECT snapshot_date, run_id, warehouse_id, goods_id, goods_sku, warehouse_name,"
            " available, intransit, defects, waiting_shipment, batch_complete, is_test,"
            " (batch_complete AND available = 0) AS stockout_observed,"
            " uom_basis, ingested_at"
            " FROM stock_history_run WHERE run_id = ?",
            [run_id],
        )
        conn.execute("DELETE FROM stock_publish WHERE snapshot_date = ?", [snapshot_date])
        conn.execute(
            "INSERT INTO stock_publish VALUES (?,?,?,?)",
            [snapshot_date, run_id, to_utc_naive_now(), previous_run_id],
        )
        # 必须在发布指针写入之后重建：重建只认 stock_publish 当前指向的 run。
        _rebuild_id_history(conn)
        _record_event(
            conn,
            run_id,
            snapshot_date,
            action,
            {"previous_run_id": previous_run_id},
        )
        conn.execute("COMMIT")
    except Exception:
        conn.execute("ROLLBACK")
        raise

    rows = conn.execute(
        "SELECT COUNT(*) FROM stock_history WHERE snapshot_date = ?", [snapshot_date]
    ).fetchone()[0]
    return {
        "published_run_id": run_id,
        "previous_run_id": previous_run_id,
        "rows": int(rows),
    }


def rollback(
    conn: "duckdb.DuckDBPyConnection", snapshot_date: date, dry_run: bool = False
) -> dict:
    current = get_publish(conn, snapshot_date)
    if current is None:
        raise RollbackUnavailable(f"{snapshot_date} 没有发布记录，无法回滚")
    previous = current.get("previous_run_id")
    if not previous:
        raise RollbackUnavailable(f"{snapshot_date} 的发布记录没有 previous_run_id，无法回滚")
    previous_run = _fetch_run_row(conn, previous)
    if previous_run is None:
        raise RollbackUnavailable(f"previous run {previous} 不在 stock_run，无法重放")
    if not previous_run["integrity_ok"]:
        raise RollbackUnavailable(f"previous run {previous} integrity_ok=false，禁止重放")
    expected_rows = conn.execute(
        "SELECT COUNT(*) FROM stock_history_run WHERE run_id = ?", [previous]
    ).fetchone()[0]
    if expected_rows == 0:
        # 0 行本身不代表不可回滚：全部仓都 batch_complete 的成功空仓是合法事实。
        # 只有批次有效性不足（缺文件/截断/坏行，或 manifest 未声明全量）时，
        # 才无法断言"那天真的是空"。
        total, complete = conn.execute(
            "SELECT COUNT(*), COALESCE(SUM(CASE WHEN batch_complete THEN 1 ELSE 0 END), 0)"
            " FROM stock_run_warehouse WHERE run_id = ?",
            [previous],
        ).fetchone()
        if not previous_run["run_complete"]:
            raise RollbackUnavailable(
                f"previous run {previous} 没有可重放的行，且批次不完整"
                f"（{int(complete)}/{int(total)} 仓 batch_complete,"
                f" run_complete=false），无法判定为空仓"
            )
    report = {
        "snapshot_date": snapshot_date.isoformat(),
        "from_run_id": current["run_id"],
        "to_run_id": previous,
        "rows": int(expected_rows),
    }
    if dry_run:
        report["dry_run"] = True
        return report
    result = materialize(conn, snapshot_date, previous, current["run_id"], action="rollback")
    report.update(result)
    report["dry_run"] = False
    return report


# --------------------------------------------------------------------------- #
# 只读分析保护
# --------------------------------------------------------------------------- #


def sum_available(
    conn: "duckdb.DuckDBPyConnection", snapshot_date: date | None = None
) -> float:
    """跨 SKU 求和会被拒绝：uom_basis=unknown 时数量不可相加。"""
    sql = "SELECT COUNT(*) FROM stock_history WHERE uom_basis <> 'known'"
    params: list[Any] = []
    if snapshot_date is not None:
        sql += " AND snapshot_date = ?"
        params.append(snapshot_date)
    unknown = conn.execute(sql, params).fetchone()[0]
    if unknown:
        raise UomBasisError(
            f"{unknown} 行 uom_basis='unknown'：禁止跨 SKU/品类求和；"
            "请按 (warehouse_id, goods_id) 使用 v_stock_by_sku"
        )
    agg = "SELECT COALESCE(SUM(available), 0) FROM stock_history"
    if snapshot_date is not None:
        agg += " WHERE snapshot_date = ?"
    return float(conn.execute(agg, params).fetchone()[0])


# --------------------------------------------------------------------------- #
# CLI
# --------------------------------------------------------------------------- #


def _format_text(report: dict) -> str:
    lines: list[str] = []
    if report.get("mode") == "rollback":
        lines.append(f"== rollback {report['snapshot_date']} ==")
        lines.append(
            f"{report['from_run_id']} -> {report['to_run_id']}  rows={report['rows']}"
            + ("  (dry-run)" if report.get("dry_run") else "")
        )
        return "\n".join(lines)
    lines.append(f"== run {report['run_id']} ({report['source']}) ==")
    lines.append(
        f"date={report['snapshot_date']}  snapshot_at={report['snapshot_at_raw']}  "
        f"attr={report['snapshot_at_local']}"
    )
    lines.append(f"manifest_sha256={report['manifest_sha256']}")
    sealed = "sealed" if report["sealed"] else (
        f"unsealed ({report['sealing_exemption']} exemption)" if report["sealing_exemption"] else "UNSEALED"
    )
    lines.append(f"sealing: {sealed}")
    lines.append(
        f"warehouses {report['warehouses_complete']}/{report['warehouses_total']} complete  "
        f"scope_complete={report['scope_complete']}  run_complete={report['run_complete']}"
    )
    lines.append(
        f"rows read={report['rows_read']} ingested={report['rows_ingested']} "
        f"duplicates={report['duplicate_rows']} bad={report['bad_rows']} "
        f"test_sku={report['test_sku_rows']}"
    )
    incomplete = [w for w in report["warehouses"] if not w["batch_complete"]]
    if incomplete:
        lines.append("incomplete warehouses:")
        for wh in incomplete:
            detail = wh["error"] or ", ".join(
                e.get("code", "?") for e in wh["validation_errors"]
            )
            lines.append(
                f"  - {wh['warehouse_name']} ({wh['warehouse_id']}): "
                f"rows={wh['rows_read']} manifest_rows={wh['manifest_rows']} {detail}"
            )
    lines.append(f"integrity: {'ok' if report['integrity_ok'] else 'FAILED'}")
    for err in report["integrity_errors"][:10]:
        lines.append(f"  ! {err.get('code')}: {err.get('message') or err}")
    decision = report["publish"]
    lines.append(f"publish: {decision['action']} ({decision['reason']})")
    if decision.get("current_run_id"):
        lines.append(f"  current={decision['current_run_id']}")
    if report.get("dry_run"):
        lines.append("dry-run: 未写数据库")
    return "\n".join(lines)


def _open_connection(db_path: str) -> "duckdb.DuckDBPyConnection":
    if db_path != ":memory:":
        Path(db_path).expanduser().resolve().parent.mkdir(parents=True, exist_ok=True)
    return duckdb.connect(db_path)


def _default_lock_path(db_path: str) -> Path:
    if db_path == ":memory:":
        return Path.cwd() / "stock_history.lock"
    return Path(db_path).expanduser().resolve().parent / "stock_history.lock"


def build_report(bundle: RunBundle, decision: dict, dry_run: bool) -> dict:
    report = bundle.to_report()
    report["complete_day"] = bundle.run_complete
    report["publish"] = decision
    report["dry_run"] = dry_run
    return report


def run(args: argparse.Namespace) -> tuple[int, dict]:
    if args.rollback:
        try:
            day = date.fromisoformat(args.rollback)
        except ValueError as exc:
            raise IngestError(f"--rollback 需要 YYYY-MM-DD: {args.rollback!r}") from exc
        db_path = args.db
        if args.dry_run:
            if db_path == ":memory:" or not Path(db_path).exists():
                raise IngestError("回滚 dry-run 需要一个已存在的 --db 文件")
            conn = duckdb.connect(db_path, read_only=True)
            try:
                report = rollback(conn, day, dry_run=True)
            finally:
                conn.close()
            report["mode"] = "rollback"
            return 0, report
        lock = acquire_lock(args.lock_path or _default_lock_path(db_path), None, args.lock_stale_seconds)
        try:
            conn = _open_connection(db_path)
            try:
                migrate(conn)
                report = rollback(conn, day, dry_run=False)
            finally:
                conn.close()
        finally:
            lock.release()
        report["mode"] = "rollback"
        return 0, report

    if not args.run_dir:
        raise IngestError("需要 --run-dir（或 --rollback DATE）")
    bundle = load_run(
        args.run_dir,
        source=args.source,
        run_id=args.run_id,
        baseline_in=args.baseline_in,
    )

    if args.dry_run:
        if args.db != ":memory:" and Path(args.db).exists():
            conn = duckdb.connect(args.db, read_only=True)
            try:
                decision = evaluate_publish(conn, bundle)
            finally:
                conn.close()
        else:
            conn = duckdb.connect(":memory:")
            try:
                migrate(conn)
                decision = evaluate_publish(conn, bundle)
            finally:
                conn.close()
        report = build_report(bundle, decision, dry_run=True)
        return 0, report

    if args.db == ":memory:":
        raise IngestError(
            "写模式需要真实的 --db 路径（默认 :memory: 只用于 dry-run / 测试）"
        )
    lock = acquire_lock(
        args.lock_path or _default_lock_path(args.db), bundle.run_dir, args.lock_stale_seconds
    )
    try:
        conn = _open_connection(args.db)
        try:
            migrate(conn)
            stage_run(conn, bundle)
            decision = evaluate_publish(conn, bundle)
            report = build_report(bundle, decision, dry_run=False)
            if decision["action"] == "reject":
                record_decision(conn, bundle, decision)
                return 4, report
            if decision["action"] == "publish":
                materialized = materialize(
                    conn,
                    bundle.snapshot_date,
                    bundle.run_id,
                    decision.get("previous_run_id"),
                )
                report["materialized"] = materialized
                if decision.get("alias_conflicts"):
                    _record_event(
                        conn,
                        bundle.run_id,
                        bundle.snapshot_date,
                        "alias_conflict_superseded",
                        decision["alias_conflicts"],
                    )
        finally:
            conn.close()
    finally:
        lock.release()
    return 0, report


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        description="通途每日库存快照离线入库 / dry-run（v4）",
        formatter_class=argparse.ArgumentDefaultsHelpFormatter,
    )
    parser.add_argument("--run-dir", help="包含 manifest.json 与 warehouse=*.jsonl 的 run 目录")
    parser.add_argument("--source", choices=SOURCES, default="unknown", help="run 来源")
    parser.add_argument("--run-id", help="覆盖 run_meta / 目录推导的 run_id（测试用）")
    parser.add_argument("--dry-run", action="store_true", help="只校验并打印，不写数据库")
    parser.add_argument("--db", default=DEFAULT_DB, help="DuckDB 路径；默认 :memory:")
    parser.add_argument("--rollback", metavar="DATE", help="按 previous_run_id 回滚该日期")
    parser.add_argument("--lock-path", help="锁文件路径（默认 <db>/stock_history.lock）")
    parser.add_argument(
        "--lock-stale-seconds",
        type=int,
        default=DEFAULT_LOCK_STALE_SECONDS,
        help="已废弃（保留兼容）：OS 文件锁由内核随进程释放，不再按时间抢锁",
    )
    parser.add_argument("--baseline-in", help="比对既有 SHA256 基线，不一致则拒绝发布")
    parser.add_argument("--baseline-out", help="把本次 SHA256 基线写入该 JSON 文件")
    parser.add_argument("--json", action="store_true", help="输出 JSON 报告（默认文本）")
    parser.add_argument("--report", help="把 JSON 报告另存到该路径")
    return parser


def main(argv: list[str] | None = None) -> int:
    parser = build_parser()
    args = parser.parse_args(argv)

    try:
        code, report = run(args)
    except LockHeld as exc:
        print(f"[lock] {exc}", file=sys.stderr)
        return 3
    except RollbackUnavailable as exc:
        print(f"[rollback] {exc}", file=sys.stderr)
        return 4
    except MigrationFailure as exc:
        print(f"[migration] {exc}", file=sys.stderr)
        return 5
    except DateAttributionError as exc:
        print(f"[date] {exc}", file=sys.stderr)
        return 2
    except (IngestError, DataIntegrityError) as exc:
        print(f"[error] {exc}", file=sys.stderr)
        return 2

    if args.baseline_out:
        if report.get("mode") == "rollback":
            print("[baseline] 回滚模式不写基线", file=sys.stderr)
        else:
            out = Path(args.baseline_out)
            out.parent.mkdir(parents=True, exist_ok=True)
            out.write_text(report_json(report["baseline"]) + "\n", encoding="utf-8")

    payload = report_json(report)
    if args.report:
        Path(args.report).parent.mkdir(parents=True, exist_ok=True)
        Path(args.report).write_text(payload + "\n", encoding="utf-8")
    print(payload if args.json else _format_text(report))
    return code


if __name__ == "__main__":
    raise SystemExit(main())
