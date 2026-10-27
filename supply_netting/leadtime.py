# -*- coding: utf-8 -*-
"""版本化交期配置（``config/leadtime_config.json``）的消费侧加载器。

来历与范围
----------
资产复用审计 A4（`docs/asset-reuse-audit-2026-10-28.md`）指出：90 / 7 / 60 / 35 / 40 /
春节 60 这批交期假设硬编码在 `so_backlog.py` 与 `scripts/so_conditional_supply.py` 两处，
既无版本也无 ``source`` / ``sample_size``，与 sc13 合约
（`docs/research/supply-chain/2026-10-20/claude/experiments/sc13/leadtime_config.py`）
零接线。本模块按该合约的**字段与规则**实现消费侧：``version`` / ``effective_from`` /
分段 ``segments`` / ``source`` / ``sample_size`` / ``owner`` / ``notes``，缺文件或缺字段
一律报错，**没有内置默认值、没有环境变量回退**。

与 sc13 的差异（有意为之，不是重造）
----------------------------------
sc13 的 profile 是 ``route × warehouse × mode`` 三段
（``order_to_departure`` / ``departure_to_arrival`` / ``arrival_to_stock``），且同一
``(route, warehouse, mode)`` 只能有一条。我们两个消费方的起点不同：

- ``so_backlog`` 从**工厂交付日**起算到分公司可发货（整条路径 90 天）；
- ``so_conditional_supply`` 从**审计日**起算：完工待发运 = 发运 7 + 海运；在产 = 生产 60 +
  发运 7 + 海运。

同一路线上「完工待发运」与「在产」是两条不同的前段，用 sc13 的三段式表达它们会撞成
重复 profile（歧义）。因此分段改为 ``production`` / ``shipping`` / ``ocean``，由消费方
按阶段自行取舍；``route_id`` / ``warehouse`` / ``mode`` / ``source`` / ``sample_size`` /
``notes`` 与 sc13 同名同义。

规则
----
* 天数按自然日（calendar days）。
* ``source=assumed`` 可用作情景，但**不得**被当成实测；``source=measured`` 必须
  ``sample_size > 0``。
* 文件缺失、JSON 非法、必填字段缺失/类型非法、``(route_id, warehouse)`` 重复 → 报错。
* 未知字段只记 warning（向前兼容后续加字段），已知字段绝不回退默认值。
* ``effective_from`` 只作口径生效日记录进 manifest；本层消费方按审计日向前推日期，
  不做「拿新口径回算历史下单日」的拦截（sc13 的 ``ConfigNotEffective`` 在此无对象）。
"""

from __future__ import annotations

import hashlib
import json
import re
from dataclasses import dataclass, field
from datetime import date
from pathlib import Path
from typing import Any

MODES = ("slow_boat", "fast_boat", "air", "3pl")
SOURCES = ("measured", "assumed", "business")
SEGMENT_KEYS = ("production", "shipping", "ocean")
ROUTE_KEYS = ("route_id", "warehouse", "mode", "segments", "source", "sample_size", "notes")
PIPELINE_KEYS = ("order_to_branch_days", "order_to_branch_range_days",
                 "stage_eta_assumption_days", "source", "sample_size", "notes")
FESTIVAL_KEYS = ("anchor", "shutdown_days", "recovery_days", "window_days",
                 "source", "sample_size", "notes")
TOP_KEYS = ("version", "effective_from", "so_pipeline", "spring_festival", "routes")
_VERSION_RE = re.compile(r"^\d{4}-\d{2}-\d{2}(\.\d+)?(-[A-Za-z0-9._-]+)?$")

#: 包内默认配置（确定性路径，不是隐式回退：文件不存在即报错）
DEFAULT_CONFIG_PATH = Path(__file__).resolve().parent / "config" / "leadtime_config.json"


# ---------------------------------------------------------------------------
# 错误：每一个都显式，不吞、不兜底
# ---------------------------------------------------------------------------

class LeadTimeConfigError(Exception):
    """基类：调用方必须处理或向上抛，不得静默忽略。"""


class ConfigNotFound(LeadTimeConfigError):
    """配置文件不存在（不回退到内置天数）。"""


class ConfigParseError(LeadTimeConfigError):
    """文件不是合法 JSON / 顶层不是对象。"""


class ConfigSchemaError(LeadTimeConfigError):
    """必填字段缺失或非法；``.field`` 给出精确路径。"""

    def __init__(self, field_path: str, problem: str) -> None:
        self.field = field_path
        self.problem = problem
        super().__init__(f"交期配置字段 `{field_path}` 不合法：{problem}")


class ConfigVersionError(LeadTimeConfigError):
    """version 缺失、格式不对，或与调用方要求的不一致。"""


class UnknownRoute(LeadTimeConfigError):
    """配置里没有这条 warehouse —— 调用方不得自行猜天数。"""


class ConfigAmbiguous(LeadTimeConfigError):
    """同一条 warehouse 命中多条 profile，调用方未消歧。"""


# ---------------------------------------------------------------------------
# 值对象
# ---------------------------------------------------------------------------

@dataclass(frozen=True)
class Route:
    route_id: str
    warehouse: str
    mode: str
    production_days: int | float
    shipping_days: int | float
    ocean_days: int | float
    source: str
    sample_size: int
    notes: str

    @property
    def segments(self) -> dict[str, int | float]:
        return dict(production=self.production_days, shipping=self.shipping_days,
                    ocean=self.ocean_days)

    @property
    def total_days(self) -> int | float:
        return sum(self.segments.values())


@dataclass(frozen=True)
class SpringFestival:
    anchor: date
    shutdown_days: int | float
    recovery_days: int | float
    window_days: int | float
    source: str
    sample_size: int
    notes: str

    @property
    def buffer_days(self) -> int | float:
        return self.shutdown_days + self.recovery_days


@dataclass(frozen=True)
class SoPipeline:
    order_to_branch_days: int | float
    order_to_branch_range_days: tuple[int | float, int | float]
    stage_eta_assumption_days: int | float
    source: str
    sample_size: int
    notes: str


@dataclass(frozen=True)
class LeadTimeConfig:
    version: str
    effective_from: date
    so_pipeline: SoPipeline
    spring_festival: SpringFestival
    routes: tuple[Route, ...]
    path: Path
    config_sha256: str
    warnings: tuple[str, ...] = field(default_factory=tuple)

    # ---- 查询 ------------------------------------------------------------
    def route_for(self, warehouse: str, *, mode: str | None = None) -> Route:
        hits = [r for r in self.routes
                if r.warehouse == warehouse and (mode is None or r.mode == mode)]
        if not hits:
            raise UnknownRoute(
                f"warehouse={warehouse!r} mode={mode!r} 不在交期配置 {self.version} 中"
                "（不回退到默认天数）")
        if len(hits) > 1:
            raise ConfigAmbiguous(
                f"warehouse={warehouse!r} 命中多条 profile "
                f"{sorted(r.mode for r in hits)}，请显式传入 mode")
        return hits[0]

    def shared_days(self, segment: str) -> int | float:
        """所有路线该分段一致时返回单值；不一致即报错（不擅自压成单值）。"""
        if segment not in SEGMENT_KEYS:
            raise ConfigSchemaError(f"segments.{segment}", f"未知分段 {segment!r}")
        values = {r.segments[segment] for r in self.routes}
        if len(values) != 1:
            raise ConfigSchemaError(
                f"routes[*].segments.{segment}",
                f"各路线取值不一致 {sorted(values)}，不能压成单值")
        return values.pop()

    # ---- 留痕 ------------------------------------------------------------
    def to_manifest(self) -> dict:
        """写进 manifest 的完整留痕：版本 + 文件哈希 + 来源 + 每条路线的分段。

        ``sha256`` 按加载时读到的同一份字节计算：即使加载后文件被改，留痕仍指被解析的那份。
        ``config`` 尽量记仓库相对路径（worktree 换目录后仍可读），不在仓库内才记绝对路径。
        """
        try:
            config_label = self.path.resolve().relative_to(
                Path(__file__).resolve().parent.parent).as_posix()
        except ValueError:
            config_label = str(self.path)
        return dict(
            config=config_label,
            version=self.version,
            sha256=self.config_sha256,
            effective_from=self.effective_from.isoformat(),
            sources=sorted({self.so_pipeline.source, self.spring_festival.source,
                            *(r.source for r in self.routes)}),
            so_pipeline=dict(days=self.so_pipeline.order_to_branch_days,
                             range_days=list(self.so_pipeline.order_to_branch_range_days),
                             stage_eta_assumption_days=self.so_pipeline.stage_eta_assumption_days,
                             source=self.so_pipeline.source,
                             sample_size=self.so_pipeline.sample_size),
            spring_festival=dict(anchor=self.spring_festival.anchor.isoformat(),
                                 shutdown_days=self.spring_festival.shutdown_days,
                                 recovery_days=self.spring_festival.recovery_days,
                                 buffer_days=self.spring_festival.buffer_days,
                                 window_days=self.spring_festival.window_days,
                                 source=self.spring_festival.source,
                                 sample_size=self.spring_festival.sample_size),
            routes=[dict(route_id=r.route_id, warehouse=r.warehouse, mode=r.mode,
                         segments=r.segments, source=r.source, sample_size=r.sample_size)
                    for r in self.routes],
            warnings=list(self.warnings),
        )


# ---------------------------------------------------------------------------
# 校验工具
# ---------------------------------------------------------------------------

def _require(doc: dict, key: str, where: str) -> Any:
    if key not in doc:
        raise ConfigSchemaError(f"{where}{key}", "缺少必填字段")
    return doc[key]


def _non_empty_str(doc: dict, key: str, where: str) -> str:
    value = _require(doc, key, where)
    if not isinstance(value, str) or not value.strip():
        raise ConfigSchemaError(f"{where}{key}", f"需要非空字符串，收到 {value!r}")
    return value


def _text(doc: dict, key: str, where: str) -> str:
    value = _require(doc, key, where)
    if not isinstance(value, str):
        raise ConfigSchemaError(f"{where}{key}", f"需要字符串，收到 {type(value).__name__}")
    return value


def _number_value(value: Any, field_path: str, *, minimum: float = 0.0) -> int | float:
    if isinstance(value, bool) or not isinstance(value, (int, float)):
        raise ConfigSchemaError(field_path, f"需要数字，收到 {value!r}")
    if value < minimum:
        raise ConfigSchemaError(field_path, f"需要 >= {minimum:g}，收到 {value}")
    return int(value) if float(value).is_integer() else float(value)


def _number(doc: dict, key: str, where: str, *, minimum: float = 0.0) -> int | float:
    return _number_value(_require(doc, key, where), f"{where}{key}", minimum=minimum)


def _provenance(doc: dict, where: str) -> tuple[str, int]:
    """每条假设都必须自报 source / sample_size；measured 不得样本为零。"""
    source = _non_empty_str(doc, "source", where)
    if source not in SOURCES:
        raise ConfigSchemaError(f"{where}source", f"{source!r} 不在允许值 {list(SOURCES)} 中")
    sample_size = _number(doc, "sample_size", where)
    if sample_size != int(sample_size):
        raise ConfigSchemaError(f"{where}sample_size", f"需要整数，收到 {sample_size}")
    sample_size = int(sample_size)
    if source == "measured" and sample_size <= 0:
        raise ConfigSchemaError(
            f"{where}sample_size", "source=measured 必须 sample_size>0（实测声明不得样本为零）")
    return source, sample_size


def _parse_date(value: Any, field_path: str) -> date:
    if not isinstance(value, str):
        raise ConfigSchemaError(field_path, f"需要 ISO 日期字符串，收到 {value!r}")
    try:
        return date.fromisoformat(value)
    except ValueError as exc:
        raise ConfigSchemaError(field_path, f"无法解析为 ISO 日期：{value!r}") from exc


# ---------------------------------------------------------------------------
# 加载
# ---------------------------------------------------------------------------

def load_config(path: str | Path | None = None, *, expected_version: str | None = None
                ) -> LeadTimeConfig:
    """加载并严格校验交期配置。

    Raises（从不兜底）：
      ConfigNotFound    文件缺失
      ConfigParseError  不是 JSON / 顶层不是对象
      ConfigSchemaError 字段缺失或非法（``.field`` 带路径）
      ConfigVersionError 版本非法或与 ``expected_version`` 不符
    """
    p = Path(path) if path is not None else DEFAULT_CONFIG_PATH
    if not p.is_file():
        raise ConfigNotFound(f"交期配置文件不存在：{p}（不回退到内置默认天数）")
    raw = p.read_bytes()
    try:
        doc = json.loads(raw.decode("utf-8"))
    except UnicodeDecodeError as exc:
        raise ConfigParseError(f"{p} 不是 UTF-8 文本：{exc}") from exc
    except json.JSONDecodeError as exc:
        raise ConfigParseError(f"{p} 不是合法 JSON：{exc}") from exc
    # 哈希按被解析的同一份字节算，加载后文件再被改也不会让留痕说谎
    config_sha256 = hashlib.sha256(raw).hexdigest()
    if not isinstance(doc, dict):
        raise ConfigParseError(f"{p} 顶层必须是 JSON 对象，收到 {type(doc).__name__}")

    warnings: list[str] = []

    version = _non_empty_str(doc, "version", "")
    if not _VERSION_RE.match(version):
        raise ConfigVersionError(
            f"version={version!r} 格式不合法，应为 YYYY-MM-DD、YYYY-MM-DD.N 或带 -SUFFIX 的变体")
    if expected_version is not None and version != expected_version:
        raise ConfigVersionError(f"版本不匹配：配置是 {version!r}，调用方要求 {expected_version!r}")
    effective_from = _parse_date(_require(doc, "effective_from", ""), "effective_from")

    # ---- so_pipeline ------------------------------------------------------
    pipeline_doc = _require(doc, "so_pipeline", "")
    if not isinstance(pipeline_doc, dict):
        raise ConfigSchemaError("so_pipeline", f"需要对象，收到 {type(pipeline_doc).__name__}")
    for extra in sorted(set(pipeline_doc) - set(PIPELINE_KEYS)):
        warnings.append(f"未知字段 so_pipeline.{extra} 已忽略")
    order_to_branch = _number(pipeline_doc, "order_to_branch_days", "so_pipeline.")
    raw_range = _require(pipeline_doc, "order_to_branch_range_days", "so_pipeline.")
    if not isinstance(raw_range, list) or len(raw_range) != 2:
        raise ConfigSchemaError("so_pipeline.order_to_branch_range_days",
                                f"需要 2 个数字的列表，收到 {raw_range!r}")
    low = _number_value(raw_range[0], "so_pipeline.order_to_branch_range_days[0]")
    high = _number_value(raw_range[1], "so_pipeline.order_to_branch_range_days[1]")
    if low > high:
        raise ConfigSchemaError("so_pipeline.order_to_branch_range_days",
                                f"下限 {low} 大于上限 {high}")
    if not low <= order_to_branch <= high:
        raise ConfigSchemaError(
            "so_pipeline.order_to_branch_range_days",
            f"范围 [{low}, {high}] 未包含 baseline {order_to_branch}")
    pipeline_source, pipeline_sample = _provenance(pipeline_doc, "so_pipeline.")
    pipeline = SoPipeline(order_to_branch_days=order_to_branch,
                          order_to_branch_range_days=(low, high),
                          stage_eta_assumption_days=_number(
                              pipeline_doc, "stage_eta_assumption_days", "so_pipeline."),
                          source=pipeline_source, sample_size=pipeline_sample,
                          notes=_text(pipeline_doc, "notes", "so_pipeline."))

    # ---- spring_festival --------------------------------------------------
    festival_doc = _require(doc, "spring_festival", "")
    if not isinstance(festival_doc, dict):
        raise ConfigSchemaError("spring_festival", f"需要对象，收到 {type(festival_doc).__name__}")
    for extra in sorted(set(festival_doc) - set(FESTIVAL_KEYS)):
        warnings.append(f"未知字段 spring_festival.{extra} 已忽略")
    festival_source, festival_sample = _provenance(festival_doc, "spring_festival.")
    festival = SpringFestival(
        anchor=_parse_date(_require(festival_doc, "anchor", "spring_festival."),
                           "spring_festival.anchor"),
        shutdown_days=_number(festival_doc, "shutdown_days", "spring_festival."),
        recovery_days=_number(festival_doc, "recovery_days", "spring_festival."),
        window_days=_number(festival_doc, "window_days", "spring_festival."),
        source=festival_source, sample_size=festival_sample,
        notes=_text(festival_doc, "notes", "spring_festival."))

    # ---- routes -----------------------------------------------------------
    raw_routes = _require(doc, "routes", "")
    if not isinstance(raw_routes, list) or not raw_routes:
        raise ConfigSchemaError("routes", "需要非空列表")

    routes: list[Route] = []
    seen: dict[tuple[str, str, str], int] = {}
    for i, item in enumerate(raw_routes):
        where = f"routes[{i}]."
        if not isinstance(item, dict):
            raise ConfigSchemaError(f"routes[{i}]", f"需要对象，收到 {type(item).__name__}")
        for extra in sorted(set(item) - set(ROUTE_KEYS)):
            warnings.append(f"未知字段 routes[{i}].{extra} 已忽略")
        route_id = _non_empty_str(item, "route_id", where)
        warehouse = _non_empty_str(item, "warehouse", where)
        mode = _non_empty_str(item, "mode", where)
        if mode not in MODES:
            raise ConfigSchemaError(f"{where}mode", f"{mode!r} 不在允许值 {list(MODES)} 中")

        segments = _require(item, "segments", where)
        if not isinstance(segments, dict):
            raise ConfigSchemaError(f"{where}segments", "需要对象")
        for key in SEGMENT_KEYS:
            _number(segments, key, f"{where}segments.")
        for extra in sorted(set(segments) - set(SEGMENT_KEYS)):
            warnings.append(f"未知字段 {where}segments.{extra} 已忽略")
        seg = {k: _number(segments, k, f"{where}segments.") for k in SEGMENT_KEYS}

        source, sample_size = _provenance(item, where)
        route = Route(route_id=route_id, warehouse=warehouse, mode=mode,
                      production_days=seg["production"], shipping_days=seg["shipping"],
                      ocean_days=seg["ocean"], source=source, sample_size=sample_size,
                      notes=_text(item, "notes", where))
        if (route.route_id, route.warehouse, route.mode) in seen:
            raise ConfigSchemaError(
                f"routes[{i}]",
                f"与 routes[{seen[(route.route_id, route.warehouse, route.mode)]}] 重复："
                f"({route.route_id}, {route.warehouse}, {route.mode})（重复会产生歧义）")
        seen[(route.route_id, route.warehouse, route.mode)] = i
        routes.append(route)

    for extra in sorted(set(doc) - set(TOP_KEYS)):
        warnings.append(f"未知顶层字段 {extra} 已忽略")

    return LeadTimeConfig(version=version, effective_from=effective_from,
                          so_pipeline=pipeline, spring_festival=festival,
                          routes=tuple(routes), path=p, config_sha256=config_sha256,
                          warnings=tuple(warnings))


def load_default_config(**kwargs) -> LeadTimeConfig:
    """加载包内默认配置（``supply_netting/config/leadtime_config.json``）。"""
    return load_config(None, **kwargs)
