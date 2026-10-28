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
SOURCES = ("measured", "assumed", "business", "mixed", "plan_override")
#: 分段级来源：measured=实测分位；plan_override=规划覆盖（不是实测 P90）；assumed=假设
SEGMENT_SOURCES = ("measured", "assumed", "business", "plan_override")
SEGMENT_KEYS = ("production", "shipping", "ocean")
#: 可选的中位数分段（P50）；缺省为 None，不默认等于 P90
P50_SEGMENT_KEYS = ("production_p50", "shipping_p50")
SEGMENT_ALL_KEYS = SEGMENT_KEYS + P50_SEGMENT_KEYS
ROUTE_KEYS = ("route_id", "warehouse", "mode", "segments", "source", "sample_size", "notes",
              "segment_sources", "segment_sample_size", "measured_p90", "plan_override",
              "rounding_rule")
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
    sample_size: int | None
    notes: str
    production_p50_days: int | float | None = None
    shipping_p50_days: int | float | None = None
    segment_sources: dict | None = None
    segment_sample_size: dict | None = None
    measured_p90: dict | None = None
    plan_override: dict | None = None
    rounding_rule: str | None = None

    @property
    def segments(self) -> dict[str, int | float]:
        return dict(production=self.production_days, shipping=self.shipping_days,
                    ocean=self.ocean_days)

    @property
    def p50_segments(self) -> dict[str, int | float] | None:
        """P50 分段；未配置时返回 None（不把 P90 冒充中位）。"""
        if self.production_p50_days is None and self.shipping_p50_days is None:
            return None
        return dict(production=self.production_p50_days, shipping=self.shipping_p50_days,
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
    sample_size: int | None
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
    sample_size: int | None
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
    @property
    def config_label(self) -> str:
        """仓库相对路径（worktree 换目录后仍可读）；不在仓库内才记绝对路径。"""
        try:
            return self.path.resolve().relative_to(
                Path(__file__).resolve().parent.parent).as_posix()
        except ValueError:
            return str(self.path)

    def provenance(self) -> dict:
        """最小留痕块：version / sha256 / source / sample_size / path。

        ``sha256`` 按加载时读到的同一份字节计算。``source`` 各块一致时给单值、不一致给
        去重列表；``sample_size`` 取各块**最小值** —— 只要有一块未实测（0），整块就不
        声称有实测样本。
        """
        sources = sorted({self.so_pipeline.source, self.spring_festival.source,
                          *(r.source for r in self.routes),
                          *(seg for r in self.routes
                            for seg in (r.segment_sources or {}).values())})
        return dict(
            version=self.version,
            sha256=self.config_sha256,
            source=sources[0] if len(sources) == 1 else sources,
            sample_size=_aggregate_sample_size(self),
            path=self.config_label,
        )

    def to_manifest(self) -> dict:
        """写进 manifest 的完整留痕：版本 + 文件哈希 + 来源 + 每条路线的分段。

        ``sha256`` 按加载时读到的同一份字节计算：即使加载后文件被改，留痕仍指被解析的那份。
        """
        return dict(
            config=self.config_label,
            version=self.version,
            sha256=self.config_sha256,
            effective_from=self.effective_from.isoformat(),
            sources=sorted({self.so_pipeline.source, self.spring_festival.source,
                            *(r.source for r in self.routes),
                            *(seg for r in self.routes
                              for seg in (r.segment_sources or {}).values())}),
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
                         segments=r.segments,
                         p50_segments=r.p50_segments,
                         source=r.source, sample_size=r.sample_size,
                         sample_size_applicable=r.sample_size is not None,
                         segment_sources=r.segment_sources,
                         segment_sample_size=r.segment_sample_size,
                         measured_p90=r.measured_p90,
                         plan_override=r.plan_override,
                         rounding_rule=r.rounding_rule)
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


ROUNDING_POLICIES = ("ceil", "floor")


def _aggregate_sample_size(cfg) -> int:
    """聚合最小样本量（只用于「整体是否可声称实测」的单一数字）。

    ``None``（mixed 路线）表示该块没有单一来源样本 → 视作「未实测」，聚合值为 0；
    这样既有 5 字段 provenance 的语义不变，又不会把 None 写成测得的 0 个样本。
    """
    values = [cfg.so_pipeline.sample_size, cfg.spring_festival.sample_size,
              *(r.sample_size for r in cfg.routes)]
    if any(v is None or v <= 0 for v in values):
        return 0
    return int(min(values))


def _validate_route_evidence(item: dict, seg: dict, source: str, where: str) -> None:
    """``source=mixed`` 的路线必须带完整、类型正确、且与执行分段一致的分段证据。

    缺证据/类型错/来源非法/样本非正/与 segments 不一致 → **fail closed**（抛 ConfigSchemaError），
    不允许回退成「measured」之类的默认断言。
    """
    if source != "mixed":
        for key in ("segment_sources", "segment_sample_size", "measured_p90", "plan_override"):
            if key in item:
                raise ConfigSchemaError(f"{where}{key}",
                                        f"只有 source=mixed 才允许 {key}（避免与单一来源混淆）")
        return

    sources = item.get("segment_sources")
    if not isinstance(sources, dict):
        raise ConfigSchemaError(f"{where}segment_sources", "source=mixed 必须给 segment_sources 对象")
    if set(sources) != set(SEGMENT_KEYS):
        raise ConfigSchemaError(f"{where}segment_sources",
                                f"分段必须恰好是 {list(SEGMENT_KEYS)}，收到 {sorted(sources)}")
    for key, value in sources.items():
        if not isinstance(value, str) or value not in SEGMENT_SOURCES:
            raise ConfigSchemaError(f"{where}segment_sources.{key}",
                                    f"{value!r} 不在允许值 {list(SEGMENT_SOURCES)} 中")

    samples = item.get("segment_sample_size")
    if not isinstance(samples, dict) or set(samples) != set(SEGMENT_KEYS):
        raise ConfigSchemaError(f"{where}segment_sample_size",
                                f"必须恰好覆盖 {list(SEGMENT_KEYS)}")
    for key, value in samples.items():
        if sources[key] in ("measured", "plan_override"):
            # plan_override 的样本量正是「实测 P90=24」的依据，必须为正
            if value is None or isinstance(value, bool) or not isinstance(value, (int, float))                     or value <= 0:
                raise ConfigSchemaError(
                    f"{where}segment_sample_size.{key}",
                    f"{sources[key]} 分段必须给正整数样本量（实测依据）")
        elif value is not None:
            raise ConfigSchemaError(f"{where}segment_sample_size.{key}",
                                    f"assumed/business 分段（{sources[key]}）样本量应为 null")

    measured = item.get("measured_p90")
    if not isinstance(measured, dict) or set(measured) != set(SEGMENT_KEYS):
        raise ConfigSchemaError(f"{where}measured_p90", f"必须恰好覆盖 {list(SEGMENT_KEYS)}")
    for key, value in measured.items():
        if sources[key] == "measured" and value is None:
            raise ConfigSchemaError(f"{where}measured_p90.{key}", "measured 分段必须给实测 P90")
        if value is not None and (isinstance(value, bool) or not isinstance(value, (int, float))):
            raise ConfigSchemaError(f"{where}measured_p90.{key}", "实测 P90 必须是数字")

    if "plan_override" not in item:
        raise ConfigSchemaError(f"{where}plan_override",
                                "source=mixed 必须显式给 plan_override（无覆盖时写 {}）")
    override = item.get("plan_override")
    if not isinstance(override, dict):
        raise ConfigSchemaError(f"{where}plan_override", "必须是对象")
    for key, plan in override.items():
        if key not in SEGMENT_KEYS:
            raise ConfigSchemaError(f"{where}plan_override.{key}", "分段名不合法")
        if not isinstance(plan, dict):
            raise ConfigSchemaError(f"{where}plan_override.{key}", "必须是对象")
        if sources[key] != "plan_override":
            raise ConfigSchemaError(
                f"{where}plan_override.{key}",
                f"只有 segment_sources={key!r} 为 plan_override 时才允许覆盖（当前 "
                f"{sources[key]!r}）")
        planning = plan.get("planning_days")
        # 规划值必须**等于实际执行的分段值**
        if planning is None or float(planning) != float(seg[key]):
            raise ConfigSchemaError(
                f"{where}plan_override.{key}.planning_days",
                f"必须等于实际执行分段 {seg[key]!r}，收到 {planning!r}")
        measured_value = plan.get("measured_p90_days")
        if measured_value is None or float(measured_value) != float(measured[key]):
            raise ConfigSchemaError(
                f"{where}plan_override.{key}.measured_p90_days",
                f"必须等于 measured_p90.{key}={measured[key]!r}，收到 {measured_value!r}")

    rounding = item.get("rounding_rule")
    if rounding not in ROUNDING_POLICIES:
        raise ConfigSchemaError(f"{where}rounding_rule",
                                f"{rounding!r} 不是可执行取整策略 {list(ROUNDING_POLICIES)}")


def _provenance(doc: dict, where: str) -> tuple[str, int | None]:
    """每条假设都必须自报 source / sample_size；measured 不得样本为零。"""
    source = _non_empty_str(doc, "source", where)
    if source not in SOURCES:
        raise ConfigSchemaError(f"{where}source", f"{source!r} 不在允许值 {list(SOURCES)} 中")
    if source == "mixed":
        # 混合来源：route 级必须显式 sample_size: null，来源/样本改由 segment_* 承载
        if "sample_size" not in doc:
            raise ConfigSchemaError(f"{where}sample_size",
                                    "source=mixed 需要显式 sample_size: null（不隐式省略）")
        raw = doc.get("sample_size")
        if raw is not None:
            raise ConfigSchemaError(f"{where}sample_size",
                                    "source=mixed 时不得给单一 sample_size，请用 segment_sample_size")
        return source, None
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
        for key in P50_SEGMENT_KEYS:
            if key in segments:
                value = _number(segments, key, f"{where}segments.")
                p90_key = key.replace("_p50", "")
                p90 = _number(segments, p90_key, f"{where}segments.")
                if value > p90:
                    raise ConfigSchemaError(
                        f"{where}segments.{key}", f"P50={value} 大于 P90={p90}，分位顺序不成立")
        for extra in sorted(set(segments) - set(SEGMENT_ALL_KEYS)):
            warnings.append(f"未知字段 {where}segments.{extra} 已忽略")
        seg = {k: _number(segments, k, f"{where}segments.") for k in SEGMENT_KEYS}

        source, sample_size = _provenance(item, where)
        _validate_route_evidence(item, seg, source, where)
        route = Route(route_id=route_id, warehouse=warehouse, mode=mode,
                      production_days=seg["production"], shipping_days=seg["shipping"],
                      ocean_days=seg["ocean"], source=source, sample_size=sample_size,
                      notes=_text(item, "notes", where),
                      production_p50_days=segments.get("production_p50"),
                      shipping_p50_days=segments.get("shipping_p50"),
                      segment_sources=item.get("segment_sources"),
                      segment_sample_size=item.get("segment_sample_size"),
                      measured_p90=item.get("measured_p90"),
                      plan_override=item.get("plan_override"),
                      rounding_rule=item.get("rounding_rule"))
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
