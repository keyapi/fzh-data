# -*- coding: utf-8 -*-
"""发布 PREPARED / 完整回读 / 失败 partial / 恢复（R3）。

``reports/t2_hardening_20261120.md`` R3 的运行时落点：

- **首个 clear 之前**保存目标**全集快照**（每一张将被覆盖的表的现有全部行）、write_set
  （写入哪几张表、期望行数与行 hash）、输入/输出预期、权限探针结果与恢复方案；
- 逐表写入后**完整回读**并与期望 hash 比对；全部一致才算 ``published``；
- 任一张表失败立即 ``partial``，**不写后续批次**，不宣称多表写天然原子；
- 恢复：先把每张表**恢复前**的当前 hash 与「我们最后一次写下的 hash」比对——
  外部并发改动存在时**一次写都不做**（``attempts=0``），交人工决定；只有目标仍是我们
  留下的状态、且调用方允许恢复时，才把快照整表写回并逐表校验回到基线 hash。

本模块只处理「内存里的行 + 网关读写」，不依赖 gspread；真实网关在
``phase3_gsheet`` / ``gsheet_tax`` 里适配，测试用 fake gateway 演练。
"""
from __future__ import annotations

import hashlib
import json
from dataclasses import dataclass, field
from decimal import Decimal, InvalidOperation
from typing import Any, Iterable, Mapping, Protocol, Sequence

STATUS_PREPARED = "prepared"
STATUS_PUBLISHED = "published"
STATUS_PARTIAL = "partial"
STATUS_BLOCKED = "blocked"

_NUMERIC_SENTINELS = frozenset({"", "nan", "none", "<na>", "nat", "null"})


def _canon_cell(value) -> str:
    """单元格归一：数字去尾零（19920.0 → 19920），其余按去空白字符串。"""
    if value is None:
        return ""
    if isinstance(value, bool):
        return "TRUE" if value else "FALSE"
    s = str(value).strip()
    if s.lower() in _NUMERIC_SENTINELS:
        return ""
    try:
        d = Decimal(s)
    except (InvalidOperation, ValueError):
        return s
    if not d.is_finite():
        return s
    text = format(d, "f")
    if "." in text:
        text = text.rstrip("0").rstrip(".")
    return "0" if text in ("", "-0", "+0") else text


def normalize_rows(rows: Iterable[Sequence[Any]] | None) -> list[list[str]]:
    return [[_canon_cell(v) for v in row] for row in (rows or [])]


def rows_hash(rows: Iterable[Sequence[Any]] | None) -> str:
    payload = json.dumps(normalize_rows(rows), ensure_ascii=False, separators=(",", ":"))
    return hashlib.sha256(payload.encode("utf-8")).hexdigest()


def dependency_hash(deps: Mapping[str, Any]) -> str:
    payload = json.dumps(
        {str(k): "" if v is None else str(v) for k, v in sorted(deps.items())},
        ensure_ascii=False,
        separators=(",", ":"),
    )
    return hashlib.sha256(payload.encode("utf-8")).hexdigest()


class WorksheetGateway(Protocol):  # pragma: no cover - 结构化协议
    def read_values(self, title: str) -> list[list]:
        ...

    def write_values(self, title: str, rows: list[list]) -> None:
        ...


@dataclass
class WriteItem:
    """一张将被覆盖的目标表：写入内容 + 期望（由 ``prepare_publish`` 补齐基线）。"""

    worksheet: str
    rows: list[list] = field(default_factory=list)
    rows_hash: str = ""
    row_count: int = 0
    existed: bool = False
    baseline_rows: list[list] = field(default_factory=list)
    baseline_hash: str = ""

    def __post_init__(self):
        self.rows_hash = rows_hash(self.rows)
        self.row_count = len(self.rows)


@dataclass
class PublishResult:
    status: str
    published: bool
    errors: list[str] = field(default_factory=list)
    written: list[str] = field(default_factory=list)
    failed_worksheet: str | None = None
    readback: dict[str, dict] = field(default_factory=dict)


def prepare_publish(
    gateway: WorksheetGateway,
    items: Sequence[WriteItem],
    *,
    run_id: str = "",
    inputs: Mapping[str, Any] | None = None,
    outputs: Mapping[str, Any] | None = None,
    permission_probe=None,
    prepared_at: str | None = None,
) -> dict:
    """首个 clear 之前：保存目标全集快照 + write_set + 输入/输出预期 + 权限 + 恢复方案。"""
    titles = [it.worksheet for it in items]
    dup = sorted({t for t in titles if titles.count(t) > 1})
    if dup:
        raise ValueError(f"write_set 同名工作表重复: {dup}")
    for it in items:
        baseline = gateway.read_values(it.worksheet) or []
        it.baseline_rows = baseline
        it.baseline_hash = rows_hash(baseline)
        it.existed = bool(baseline)
    permissions: dict[str, Any]
    if permission_probe is None:
        permissions = {"probed": False, "status": "unverified"}
    else:
        try:
            probed = permission_probe()
            permissions = {"probed": True, "status": "ok", "detail": probed}
        except Exception as e:  # 权限探针失败本身不阻断 prepare，但必须可见并阻断发布
            permissions = {"probed": True, "status": "failed", "error": f"{type(e).__name__}: {e}"}
    return {
        "run_id": run_id,
        "status": STATUS_PREPARED,
        "prepared_at": prepared_at,
        "inputs": {str(k): "" if v is None else str(v) for k, v in (inputs or {}).items()},
        "outputs": dict(outputs or {}),
        "permissions": permissions,
        "write_set": [
            {
                "worksheet": it.worksheet,
                "row_count": it.row_count,
                "rows_hash": it.rows_hash,
                "existed": it.existed,
                "baseline_row_count": len(it.baseline_rows),
                "baseline_hash": it.baseline_hash,
            }
            for it in items
        ],
        "recovery_plan": [
            {
                "worksheet": it.worksheet,
                "action": "restore_baseline_rows" if it.existed else "clear_to_empty",
                "baseline_hash": it.baseline_hash,
            }
            for it in items
        ],
        "last_hash": {},
        "target_baseline_hash": dependency_hash(
            {it.worksheet: it.baseline_hash for it in items}
        ),
    }


def publish_prepared(
    gateway: WorksheetGateway,
    items: Sequence[WriteItem],
    prepared: Mapping[str, Any],
) -> PublishResult:
    """按 write_set 顺序写入 + 逐表完整回读；失败即 partial 并停止后续表。"""
    errors: list[str] = []
    if not isinstance(prepared.get("write_set"), list) or not prepared["write_set"]:
        return PublishResult(STATUS_BLOCKED, False, ["PREPARED 缺 write_set（拒绝写入）"])
    if prepared.get("permissions", {}).get("status") == "failed":
        return PublishResult(
            STATUS_BLOCKED,
            False,
            [f"权限探针失败: {prepared['permissions'].get('error')}"],
        )
    prepared_hashes = {w["worksheet"]: w["baseline_hash"] for w in prepared["write_set"]}
    # 准备之后目标被外部改动 → 基线与 PREPARED 不符，一次写都不做。
    for it in items:
        current = rows_hash(gateway.read_values(it.worksheet) or [])
        if current != prepared_hashes.get(it.worksheet):
            return PublishResult(
                STATUS_BLOCKED,
                False,
                [
                    f"{it.worksheet}: 目标表在 PREPARED 后被外部改动"
                    f"（{current[:12]}… != {prepared_hashes.get(it.worksheet, '')[:12]}…）"
                ],
            )

    result = PublishResult(STATUS_PUBLISHED, True)
    for it in items:
        try:
            gateway.write_values(it.worksheet, it.rows)
        except Exception as e:
            result.errors.append(f"{it.worksheet}: 写入失败 {type(e).__name__}: {e}")
            result.failed_worksheet = it.worksheet
            try:
                prepared["last_hash"][it.worksheet] = rows_hash(  # type: ignore[index]
                    gateway.read_values(it.worksheet) or []
                )
            except Exception:
                prepared["last_hash"][it.worksheet] = None  # type: ignore[index]
            break
        try:
            actual = gateway.read_values(it.worksheet) or []
        except Exception as e:
            result.errors.append(f"{it.worksheet}: 回读失败 {type(e).__name__}: {e}")
            result.failed_worksheet = it.worksheet
            prepared["last_hash"][it.worksheet] = None  # type: ignore[index]
            break
        actual_hash = rows_hash(actual)
        prepared["last_hash"][it.worksheet] = actual_hash  # type: ignore[index]
        result.readback[it.worksheet] = {
            "row_count": len(actual),
            "expected_hash": it.rows_hash,
            "actual_hash": actual_hash,
            "match": actual_hash == it.rows_hash,
        }
        if actual_hash != it.rows_hash:
            result.errors.append(
                f"{it.worksheet}: 回读与写入内容不一致"
                f"（{actual_hash[:12]}… != {it.rows_hash[:12]}…），停止后续批次"
            )
            result.failed_worksheet = it.worksheet
            break
        result.written.append(it.worksheet)

    if result.errors:
        result.status = STATUS_PARTIAL
        result.published = False
    return result


def recover_prepared(
    gateway: WorksheetGateway,
    items: Sequence[WriteItem],
    prepared: Mapping[str, Any],
    *,
    allow: bool = True,
) -> dict:
    """把 write_set 恢复到 PREPARED 基线；目标有外部并发改动时一次都不写。"""
    if not allow:
        return {"recovered": False, "refused": "recovery_not_allowed", "attempts": 0}
    last_hash = prepared.get("last_hash") or {}
    if any(last_hash.get(it.worksheet) is None for it in items if it.worksheet in last_hash):
        return {"recovered": False, "refused": "unverifiable_state", "attempts": 0}
    # 第一遍只读：任何一张表已不是「我们留下的状态」→ 外部改动，拒绝恢复。
    for it in items:
        if it.worksheet not in last_hash:
            continue
        current = rows_hash(gateway.read_values(it.worksheet) or [])
        if current != last_hash[it.worksheet]:
            return {
                "recovered": False,
                "refused": "external_concurrent_change",
                "worksheet": it.worksheet,
                "attempts": 0,
            }
    attempts = 0
    restored: list[str] = []
    mismatched: list[dict] = []
    for it in items:
        if it.worksheet not in last_hash:
            continue
        current = rows_hash(gateway.read_values(it.worksheet) or [])
        if current == it.baseline_hash:
            continue  # 已经是基线（例如写失败但没改到内容）：无需再写一次
        attempts += 1
        gateway.write_values(it.worksheet, it.baseline_rows)
        actual = rows_hash(gateway.read_values(it.worksheet) or [])
        if actual != it.baseline_hash:
            mismatched.append(
                {"worksheet": it.worksheet, "expected": it.baseline_hash, "actual": actual}
            )
        else:
            restored.append(it.worksheet)
    return {
        "recovered": not mismatched,
        "refused": None,
        "attempts": attempts,
        "restored": restored,
        "mismatched": mismatched,
    }
