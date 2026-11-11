# -*- coding: utf-8 -*-
"""只读数据源盘点与快照（盈利审计 U1）。

设计约束（对应 plan R1–R5）：
- **只用读接口**：本模块只暴露 `list_worksheets` / `read_values`；没有任何
  写入、追加、清空、复制、归档、提交、删除的调用点。
- **先冻结再分析**：把每个源 worksheet 的整值原样落成 CSV + 一条 manifest 记录
  （时间戳 / 行数 / 表头 / sha256 / 相对路径 / 状态 / 失败原因）。
- **不猜**：`写回*` 永不当作原始表；同一角色出现多个候选时必须显式选择，
  否则报错而不是按位置/名称近似。
- **失败隔离**：某个 worksheet 读失败不影响其它源；失败原因写进 manifest。
"""
from __future__ import annotations

import csv
import hashlib
import json
import re
import time
from dataclasses import asdict, dataclass, field
from datetime import datetime
from pathlib import Path
from typing import Any, Protocol

# ---------------------------------------------------------------------------
# 角色分类
# ---------------------------------------------------------------------------

RAW = "raw_order"           # 原始订单表（数据源，唯一允许作为 raw 的角色）
RAW_FBA = "raw_fba"         # 原始 FBA 表
WRITEBACK = "writeback"     # 写回*（派生输出，绝不是 raw）
WRITEBACK_FBA = "writeback_fba"
WRITEBACK_COMBINED = "writeback_combined"
CHECK = "check"             # 检查运营人员-写回*
PIVOT = "pivot"             # 透视表*
BACKUP = "backup"           # 备份*
ARCHIVE = "archive"         # 弃用*
OTHER = "other"

# 派生/非原始前缀（R5：写回* 永不作为 raw）
_DERIVED_PREFIXES = ("写回", "检查运营人员-写回")
_PIVOT_PREFIXES = ("透视表",)
_BACKUP_PREFIXES = ("备份",)
_ARCHIVE_PREFIXES = ("弃用",)


def classify_worksheet(title: str, headers: list[str]) -> str:
    """按**精确标题前缀** + **表头证据**归类 worksheet 角色。

    只看结构化证据，不做模糊匹配：标题已足够说明角色时不看表头；
    标题中性时用表头里是否有 `订单号` 判原始 vs 透视。
    """
    name = (title or "").strip()
    header_set = {str(h).strip() for h in headers}

    if any(name.startswith(p) for p in _ARCHIVE_PREFIXES):
        return ARCHIVE
    if any(name.startswith(p) for p in _BACKUP_PREFIXES):
        return BACKUP
    if any(name.startswith(p) for p in _PIVOT_PREFIXES):
        return PIVOT
    if name.startswith("检查运营人员-写回"):
        return CHECK
    if name.startswith("写回"):
        if "FBA" in name and "非FBA" in name:
            return WRITEBACK_COMBINED
        if "FBA" in name:
            return WRITEBACK_FBA
        return WRITEBACK
    if "FBA" in name and "非FBA" not in name:
        return RAW_FBA
    if "订单号" in header_set:
        return RAW
    return OTHER


# ---------------------------------------------------------------------------
# 只读客户端协议
# ---------------------------------------------------------------------------


@dataclass(frozen=True)
class WorksheetMeta:
    title: str
    row_count: int
    col_count: int


class SheetReader(Protocol):
    """只读 Sheets 访问协议。实现方**不得**提供写方法。

    `render_option`: `"values"`（显示值，默认）或 `"formulas"`（A1 公式文本）。
    成本重建要靠公式证据，必须能把同一 worksheet 分别冻结成值与公式两份。
    """

    def list_worksheets(self, spreadsheet: str) -> list[WorksheetMeta]: ...
    def read_values(
        self, spreadsheet: str, worksheet: str, render_option: str = "values"
    ) -> list[list[str]]: ...


def _retry(operation, attempts: int = 12, base_sleep: float = 0.5):
    """对间歇性网络失败（www.googleapis.com 的 SSL reset）重试。

    实测该主机约 4 成连接被重置，其它 google 主机正常；连接级失败必须重试。
    """
    last: Exception | None = None
    for attempt in range(attempts):
        try:
            return operation()
        except Exception as exc:  # noqa: BLE001 - 网络层需吞掉任意异常后重试
            last = exc
            if attempt == attempts - 1:
                break
            time.sleep(base_sleep + min(2 ** attempt, 10) * 0.2)
    assert last is not None
    raise last


class GspreadSheetReader:
    """gspread 只读包装：仅 list/read，无任何写方法。"""

    def __init__(self, gc) -> None:  # gc: gspread.Client
        self._gc = gc

    def _open(self, spreadsheet: str):
        return _retry(lambda: self._gc.open(spreadsheet))

    def list_worksheets(self, spreadsheet: str) -> list[WorksheetMeta]:
        sh = self._open(spreadsheet)
        metas = _retry(lambda: sh.worksheets())
        return [
            WorksheetMeta(title=ws.title, row_count=ws.row_count, col_count=ws.col_count)
            for ws in metas
        ]

    def read_values(
        self, spreadsheet: str, worksheet: str, render_option: str = "values"
    ) -> list[list[str]]:
        from gspread.utils import ValueRenderOption

        sh = self._open(spreadsheet)
        ws = _retry(lambda: sh.worksheet(worksheet))
        if render_option == "formulas":
            return _retry(
                lambda: ws.get_all_values(
                    value_render_option=ValueRenderOption.formula
                )
            )
        return _retry(lambda: ws.get_all_values())

    def spreadsheet_id(self, spreadsheet: str) -> str:
        return self._open(spreadsheet).id


# ---------------------------------------------------------------------------
# 快照与 manifest
# ---------------------------------------------------------------------------


@dataclass(frozen=True)
class SourceSpec:
    key: str
    spreadsheet: str
    worksheet: str
    role: str = ""                  # 空=由 classify 推断
    required: bool = False
    required_columns: tuple[str, ...] = ()
    render_option: str = "values"   # "values"（显示值）或 "formulas"（A1 公式）


@dataclass
class SourceRecord:
    key: str
    spreadsheet: str
    worksheet: str
    role: str
    required: bool
    status: str                     # ok / failed
    render_option: str = "values"
    data_rows: int = 0
    value_rows: int = 0
    columns: list[str] = field(default_factory=list)
    column_count: int = 0
    path: str = ""
    sha256: str = ""
    error: str = ""


@dataclass
class Manifest:
    run_id: str
    created_at: str
    spreadsheets: dict[str, str]    # 名称 → id
    sources: list[SourceRecord] = field(default_factory=list)
    failures: list[dict[str, str]] = field(default_factory=list)
    notes: list[str] = field(default_factory=list)

    def find(self, key: str) -> SourceRecord | None:
        for rec in self.sources:
            if rec.key == key:
                return rec
        return None

    def to_dict(self) -> dict[str, Any]:
        return {
            "run_id": self.run_id,
            "created_at": self.created_at,
            "spreadsheets": dict(self.spreadsheets),
            "sources": [asdict(rec) for rec in self.sources],
            "failures": list(self.failures),
            "notes": list(self.notes),
        }


def _sha256_of_rows(rows: list[list[str]]) -> str:
    payload = json.dumps(rows, ensure_ascii=False, separators=(",", ":"))
    return hashlib.sha256(payload.encode("utf-8")).hexdigest()


def _write_csv(path: Path, rows: list[list[str]]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    with path.open("w", encoding="utf-8-sig", newline="") as fh:
        writer = csv.writer(fh)
        writer.writerows(rows)


def require_columns(headers: list[str], required: tuple[str, ...], context: str) -> None:
    """精确检查必需列；缺列立即失败，不猜列名（R1/R7）。"""
    present = {str(h).strip() for h in headers}
    missing = [c for c in required if c not in present]
    if missing:
        raise ValueError(
            f"{context} 缺少必需列: {missing}；现有列数={len(headers)}"
        )


def assert_no_write_methods(obj: object, label: str) -> None:
    """静态自证：只读对象不得暴露写方法。"""
    forbidden = (
        "update", "append", "clear", "batch_update", "delete", "duplicate",
        "copy_to", "submit", "cancel", "insert_row", "insert_col",
    )
    exposed = [m for m in forbidden if callable(getattr(obj, m, None))]
    if exposed:
        raise AssertionError(f"{label} 暴露了禁止的写方法: {exposed}")


def snapshot_sources(
    reader: SheetReader,
    specs: list[SourceSpec],
    out_dir: Path | str,
    *,
    run_id: str | None = None,
    now: str | None = None,
    known_worksheets: dict[str, list[str]] | None = None,
) -> Manifest:
    """把每个 SourceSpec 的整值落盘为 CSV，并返回 manifest。

    - 每个源独立 try/except：一个失败不拖垮其它（失败写进 manifest）。
    - `required` 源失败或校验不过 → 抛错，调用方须以失败退出（不产出分析）。
    - 不做任何 Google 写操作。
    """
    out_dir = Path(out_dir)
    created_at = now or datetime.now().isoformat(timespec="seconds")
    run_id = run_id or f"{created_at.replace(':', '').replace('-', '')}"
    manifest = Manifest(run_id=run_id, created_at=created_at, spreadsheets={})

    listings: dict[str, list[WorksheetMeta]] = {}

    for spec in specs:
        record = SourceRecord(
            key=spec.key,
            spreadsheet=spec.spreadsheet,
            worksheet=spec.worksheet,
            role=spec.role,
            required=spec.required,
            status="failed",
            render_option=spec.render_option,
        )
        try:
            if spec.spreadsheet not in listings:
                listings[spec.spreadsheet] = _retry(
                    lambda: reader.list_worksheets(spec.spreadsheet)
                )
                titles = [m.title for m in listings[spec.spreadsheet]]
                known_worksheets = known_worksheets or {}
                known_worksheets[spec.spreadsheet] = titles
                if hasattr(reader, "spreadsheet_id"):
                    try:
                        manifest.spreadsheets[spec.spreadsheet] = reader.spreadsheet_id(  # type: ignore[attr-defined]
                            spec.spreadsheet
                        )
                    except Exception:  # noqa: BLE001 - id 缺失不阻断快照
                        manifest.spreadsheets[spec.spreadsheet] = ""

            titles = [m.title for m in listings[spec.spreadsheet]]
            if spec.worksheet not in titles:
                raise ValueError(
                    f"worksheet 不存在: {spec.worksheet!r}；"
                    f"现有 {len(titles)} 张: {titles}"
                )

            rows = _retry(
                lambda: reader.read_values(
                    spec.spreadsheet, spec.worksheet, render_option=spec.render_option
                )
            )
            headers = [str(h) for h in (rows[0] if rows else [])]
            require_columns(headers, spec.required_columns, f"{spec.key}")
            role = spec.role or classify_worksheet(spec.worksheet, headers)
            record.role = role
            record.columns = headers
            record.column_count = len(headers)
            record.value_rows = len(rows)
            record.data_rows = max(len(rows) - 1, 0)
            record.sha256 = _sha256_of_rows(rows)
            rel = Path(spec.key) / f"{_safe_name(spec.worksheet)}.csv"
            _write_csv(out_dir / rel, rows)
            record.path = rel.as_posix()
            record.status = "ok"
        except Exception as exc:  # noqa: BLE001 - 逐源隔离
            record.error = f"{type(exc).__name__}: {exc}"
            manifest.failures.append(
                {"key": spec.key, "worksheet": spec.worksheet, "error": record.error}
            )
        manifest.sources.append(record)

    manifest.notes.append(
        "www.googleapis.com 连接间歇性被重置；读取已带重试（GspreadSheetReader）。"
    )
    return manifest


def write_manifest(manifest: Manifest, out_dir: Path | str) -> Path:
    path = Path(out_dir) / "manifest.json"
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(
        json.dumps(manifest.to_dict(), ensure_ascii=False, indent=2), encoding="utf-8"
    )
    return path


_SAFE_RE = re.compile(r"[^\w一-鿿.-]+")


def _safe_name(name: str) -> str:
    return _SAFE_RE.sub("_", name).strip("_") or "sheet"


def require_successful(manifest: Manifest) -> None:
    """required 源若失败则抛错（触发 gate 阻断，R2/AE6）。"""
    bad = [r for r in manifest.sources if r.required and r.status != "ok"]
    if bad:
        detail = "; ".join(f"{r.key}({r.worksheet}): {r.error}" for r in bad)
        raise RuntimeError(f"必需数据源快照失败，已阻断: {detail}")


def require_single_choice(
    candidates: list[str], *, role: str, explicit: str | None = None
) -> str | None:
    """同角色候选表中选出唯一一个。

    - 0 个 → None（该源缺失，由调用方决定是必需还是可选）。
    - 1 个 → 直接选。
    - >1 个 → 必须 `explicit` 且必须在候选里，否则报错 —— **不按位置/名称近似**。
    """
    uniq = list(dict.fromkeys(candidates))
    if explicit is not None:
        if explicit not in uniq:
            raise ValueError(
                f"角色 {role} 显式选择 {explicit!r} 不在候选中: {uniq}"
            )
        return explicit
    if len(uniq) == 0:
        return None
    if len(uniq) == 1:
        return uniq[0]
    raise ValueError(
        f"角色 {role} 有多个候选，必须显式选择: {uniq}"
    )


def list_worksheet_titles(reader: SheetReader, spreadsheet: str) -> list[str]:
    return [m.title for m in _retry(lambda: reader.list_worksheets(spreadsheet))]


# ---------------------------------------------------------------------------
# 批量取数：分块 + 二分失败隔离（R15）
# ---------------------------------------------------------------------------


def chunked(seq: list[str], size: int):
    for start in range(0, len(seq), size):
        yield seq[start : start + size]


def resilient_fetch(
    fetch_chunk,
    ids: list[str],
    failures: list[str],
    failed_ids: set[str],
    label: str,
) -> list[dict]:
    """批量取数，失败时二分降级到单条，逐单定位并把失败记录进 failures/failed_ids。

    Frappe 的 `in [...]` 过滤一旦过大或某条异常会整批报错；二分保证其余单照常取回，
    失败的单不会被静默丢弃（数量对账必须闭合）。
    """
    if not ids:
        return []
    try:
        return fetch_chunk(ids)
    except Exception as exc:  # noqa: BLE001 - 需捕获任意批次异常以继续对账
        if len(ids) == 1:
            failures.append(f"{label} {ids[0]}: {type(exc).__name__}: {exc}")
            failed_ids.add(ids[0])
            return []
        mid = len(ids) // 2
        return resilient_fetch(
            fetch_chunk, ids[:mid], failures, failed_ids, label
        ) + resilient_fetch(fetch_chunk, ids[mid:], failures, failed_ids, label)
