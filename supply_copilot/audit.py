"""统一审计头 + ``bundle_id`` + 本地校验 + 按版本选包（P0）。

设计约束（见 ``DELIVERY_AND_VERSIONING.md`` §1–§3）：

- **纯函数 / 离线**：不联网、不下载、不写数据目录；只读本地文件。
- **不猜**：缺失的轴一律 ``None``，不填默认值、不填当前时间。
- **哈希才是身份**：``bundle_id`` 是对规范化 JSON（``sort_keys`` +
  ``ensure_ascii=False``）取 sha256，字段顺序无关。
- **禁止按 mtime 选包**：``select_current`` 只按 manifest 的
  ``version``/``as_of`` 排序，后拷入的旧包无法冒充最新。

轴的口径（调用方负责采集，本模块只合成）：

- ``tool``：``{version, git_sha, dirty}``
- ``engine``：``{rule_version, schema}``
- ``policy``：``{version, sha256}``
- ``data``：``{pack/orders/history: {version, sha256, as_of}, as_of}``
- ``live``：``{snapshot_at, stock_sha256, so_sha256, po_sha256}``
- ``forecast``：``{run_id, as_of}``
"""

from __future__ import annotations

import hashlib
import json
import re
from datetime import date, datetime
from pathlib import Path
from typing import Any, Mapping

from .history import MANIFEST as DEFAULT_HISTORY_MANIFEST
from .history import ORDERS_MANIFEST as DEFAULT_ORDERS_MANIFEST
from .paths import DEFAULT_MANIFEST as DEFAULT_PACK_MANIFEST

AXES = ("tool", "engine", "policy", "data", "live", "forecast")
MANIFEST_KINDS = ("pack", "history", "orders")
FRESH_DAYS = 7  # 数据 as_of 超过该天数即提示新鲜度告警

_DATE_RE = re.compile(r"(\d{4})-(\d{2})-(\d{2})")
_SEQ_RE = re.compile(r"\.(\d+)$")


# --------------------------------------------------------------------------- #
# 审计头 / bundle_id
# --------------------------------------------------------------------------- #
def _axis(name: str, value: Any) -> dict | None:
    """单个版本轴：None 保持 None；映射做浅拷贝（不共享可变引用）。"""
    if value is None:
        return None
    if not isinstance(value, Mapping):
        raise TypeError(f"{name} 必须是 dict 或 None，收到 {type(value).__name__}")
    return dict(value)


def build_bundle_meta(*, tool=None, engine=None, policy=None, data=None,
                      live=None, forecast=None, computed_at=None) -> dict:
    """合并五轴 + 计算时间；缺省轴为 ``None``，不猜。

    ``computed_at`` 可传 ISO 字符串或 ``datetime``（会转成 ISO）；不传即
    ``None``——本函数不会用当前时间替你补。
    """
    if isinstance(computed_at, datetime):
        computed_at = computed_at.isoformat()
    return {
        "tool": _axis("tool", tool),
        "engine": _axis("engine", engine),
        "policy": _axis("policy", policy),
        "data": _axis("data", data),
        "live": _axis("live", live),
        "forecast": _axis("forecast", forecast),
        "computed_at": computed_at,
    }


def canonical_json(meta: Mapping) -> str:
    """规范化 JSON：键排序、保留中文、紧凑分隔符；用于哈希与复现比对。"""
    return json.dumps(meta, sort_keys=True, ensure_ascii=False,
                      separators=(",", ":"))


def bundle_id(meta: Mapping) -> str:
    """对规范化 JSON 取 sha256，返回 64 位小写 hex。"""
    return hashlib.sha256(canonical_json(meta).encode("utf-8")).hexdigest()


# --------------------------------------------------------------------------- #
# 本地校验（doctor --verify 的离线部分）
# --------------------------------------------------------------------------- #
def _sha256_file(path: Path) -> str:
    digest = hashlib.sha256()
    with Path(path).open("rb") as handle:
        for block in iter(lambda: handle.read(1024 * 1024), b""):
            digest.update(block)
    return digest.hexdigest()


def _row_count(path: Path) -> int | None:
    """按文件类型数行；数不了返回 None（不猜、不报假错）。"""
    suffix = path.suffix.lower()
    try:
        if suffix == ".parquet":
            import pyarrow.parquet as pq
            return int(pq.ParquetFile(path).metadata.num_rows)
        if suffix == ".jsonl":
            with path.open("rb") as handle:
                return sum(1 for line in handle if line.strip())
        if suffix == ".csv":
            with path.open("rb") as handle:
                return max(sum(1 for line in handle if line.strip()) - 1, 0)
        if suffix == ".tsv":
            # 供应链导出 TSV 无表头；按非空行计数
            with path.open("rb") as handle:
                return sum(1 for line in handle if line.strip())
    except Exception:
        return None
    return None


def _read_manifest(kind: str, source, default_path: Path, issues: list) -> dict | None:
    """manifest 可直接传 dict，也可传路径；读不到记为 issue。"""
    if isinstance(source, Mapping):
        return dict(source)
    path = Path(source) if source is not None else Path(default_path)
    if not path.is_file():
        issues.append({"scope": kind, "file": str(path),
                       "expected": "manifest 文件存在", "actual": "缺失"})
        return None
    try:
        loaded = json.loads(path.read_text(encoding="utf-8"))
    except (OSError, ValueError) as exc:
        issues.append({"scope": kind, "file": str(path),
                       "expected": "合法 JSON", "actual": f"读取失败: {exc.__class__.__name__}"})
        return None
    if not isinstance(loaded, dict):
        issues.append({"scope": kind, "file": str(path),
                       "expected": "JSON 对象", "actual": type(loaded).__name__})
        return None
    return loaded


def _kind_base(root: Path, kind: str, manifest: dict) -> Path:
    if kind == "pack":
        return root
    version = str(manifest.get("version") or "")
    return root / kind / version


def verify_local(root, *, pack_manifest=None, history_manifest=None,
                 orders_manifest=None) -> dict:
    """校验本地三个 manifest 列出的文件：存在、sha256、rows。

    - ``pack_manifest`` / ``history_manifest`` / ``orders_manifest`` 可传
      dict 或路径；``None`` 用仓库内默认 manifest。
    - 不联网、不下载；``root`` 不存在时按"文件缺失"逐条报告。
    - 返回 ``{"ok": bool, "issues": [{scope, file, expected, actual}], "checked": int}``。
    """
    root = Path(root)
    issues: list[dict] = []
    sources = (
        ("pack", pack_manifest, DEFAULT_PACK_MANIFEST),
        ("history", history_manifest, DEFAULT_HISTORY_MANIFEST),
        ("orders", orders_manifest, DEFAULT_ORDERS_MANIFEST),
    )
    checked = 0
    for kind, source, default_path in sources:
        manifest = _read_manifest(kind, source, default_path, issues)
        if manifest is None:
            continue
        base = _kind_base(root, kind, manifest)
        for item in manifest.get("files") or []:
            if not isinstance(item, Mapping):
                continue
            name = item.get("path") or item.get("name")
            if not name:
                continue
            checked += 1
            target = base / str(name)
            if not target.is_file():
                issues.append({"scope": kind, "file": str(name),
                               "expected": "文件存在", "actual": "缺失"})
                continue
            expected_sha = item.get("sha256")
            if expected_sha:
                actual_sha = _sha256_file(target)
                if actual_sha != expected_sha:
                    issues.append({"scope": kind, "file": str(name),
                                   "expected": expected_sha, "actual": actual_sha})
                    continue
            expected_rows = item.get("rows")
            if expected_rows is not None:
                actual_rows = _row_count(target)
                if actual_rows is None:
                    issues.append({"scope": kind, "file": str(name),
                                   "expected": int(expected_rows), "actual": "无法读取行数"})
                elif int(actual_rows) != int(expected_rows):
                    issues.append({"scope": kind, "file": str(name),
                                   "expected": int(expected_rows), "actual": int(actual_rows)})
    return {"ok": not issues, "issues": issues, "checked": checked}


# --------------------------------------------------------------------------- #
# 按版本选包（替代 cli._latest_file 的 mtime 排序）
# --------------------------------------------------------------------------- #
def _version_key(version: str, as_of: str | None = None) -> tuple:
    """版本排序键：(as_of 日期, 序号, 原始版本串)。与 mtime 无关。"""
    text = str(version or "")
    date_text = str(as_of or "")
    match = _DATE_RE.search(date_text) or _DATE_RE.search(text)
    date_key = match.group(0) if match else ""
    seq_match = _SEQ_RE.search(text)
    seq = int(seq_match.group(1)) if seq_match else 0
    return (date_key, seq, text)


def _dir_meta(candidate: Path) -> tuple[str, str | None, bool]:
    """读目录自带的 manifest.json；返回 (version, as_of, 是否有 manifest)。"""
    manifest_path = candidate / "manifest.json"
    if manifest_path.is_file():
        try:
            payload = json.loads(manifest_path.read_text(encoding="utf-8"))
            if isinstance(payload, dict):
                return (str(payload.get("version") or candidate.name),
                        payload.get("as_of"), True)
        except (OSError, ValueError):
            pass
    return (candidate.name, None, False)


def select_current(root, manifest_kind: str) -> Path | None:
    """按 manifest 的 ``version``/``as_of`` 选出当前目录；绝不按 mtime。

    - ``history`` / ``orders``：扫描 ``root/<kind>/*``，读取每个目录的
      ``manifest.json``（缺省回退目录名），按 (as_of, 序号) 取最高版本。
    - ``pack``：仓库当前是平铺布局（``root/manifest.json`` + ``root/data``），
      存在则返回 ``root/data``，否则 ``None``。
    - 没有可识别版本的目录时返回 ``None``（不猜）。
    """
    root = Path(root)
    if manifest_kind == "pack":
        if (root / "manifest.json").is_file() and (root / "data").is_dir():
            return root / "data"
        return None
    if manifest_kind not in ("history", "orders"):
        raise ValueError(f"未知 manifest_kind：{manifest_kind}（可选 {', '.join(MANIFEST_KINDS)}）")

    base = root / manifest_kind
    if not base.is_dir():
        return None
    ranked: list[tuple[tuple, str, Path]] = []
    for candidate in base.iterdir():
        if not candidate.is_dir() or candidate.name.startswith("."):
            continue
        version, as_of, has_manifest = _dir_meta(candidate)
        key = _version_key(version, as_of)
        # 既无 manifest 又无法从目录名解析日期 → 不当作版本目录
        if not has_manifest and not key[0]:
            continue
        ranked.append((key, candidate.name, candidate))
    if not ranked:
        return None
    ranked.sort(key=lambda row: (row[0], row[1]))
    return ranked[-1][2]


# --------------------------------------------------------------------------- #
# 人读头部
# --------------------------------------------------------------------------- #
def _date_of(value: Any) -> date | None:
    if isinstance(value, date) and not isinstance(value, datetime):
        return value
    if isinstance(value, datetime):
        return value.date()
    if isinstance(value, str) and value:
        match = _DATE_RE.search(value)
        if match:
            try:
                return date.fromisoformat(match.group(0))
            except ValueError:
                return None
    return None


def _freshness(data: Mapping, computed_at: Any) -> str | None:
    as_of = _date_of((data or {}).get("as_of"))
    if as_of is None:
        return "⚠️ 数据新鲜度：未声明 as_of"
    ref = _date_of(computed_at) or date.today()
    age = (ref - as_of).days
    if age > FRESH_DAYS:
        return f"⚠️ 数据新鲜度：as_of {as_of.isoformat()} 距 {ref.isoformat()} 已 {age} 天"
    return None


def format_header(meta: Mapping) -> str:
    """人类可读 2–4 行：bundle_id、as_of、版本、数据新鲜度告警。"""
    meta = dict(meta or {})
    data = meta.get("data") if isinstance(meta.get("data"), Mapping) else {}
    forecast = meta.get("forecast") if isinstance(meta.get("forecast"), Mapping) else {}
    tool = meta.get("tool") if isinstance(meta.get("tool"), Mapping) else {}
    engine = meta.get("engine") if isinstance(meta.get("engine"), Mapping) else {}
    policy = meta.get("policy") if isinstance(meta.get("policy"), Mapping) else {}

    as_of = data.get("as_of") or forecast.get("as_of") or ""
    lines = [f"bundle_id: {bundle_id(meta)}",
             f"as_of: {as_of or '未声明'}"]

    parts: list[str] = []
    if tool.get("version"):
        suffix = f"@{str(tool['git_sha'])[:7]}" if tool.get("git_sha") else ""
        parts.append(f"tool={tool['version']}{suffix}")
    if engine.get("rule_version"):
        parts.append(f"engine={engine['rule_version']}")
    if policy.get("version"):
        parts.append(f"policy={policy['version']}")
    pack = data.get("pack") if isinstance(data.get("pack"), Mapping) else {}
    if pack.get("version"):
        parts.append(f"data={pack['version']}")
    if forecast.get("run_id"):
        parts.append(f"forecast={forecast['run_id']}")
    if parts:
        lines.append("版本: " + " | ".join(parts))

    warning = _freshness(data, meta.get("computed_at"))
    if warning:
        lines.append(warning)
    return "\n".join(lines)
