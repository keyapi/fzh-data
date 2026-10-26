#!/usr/bin/env python
# -*- coding: utf-8 -*-
"""SC13 consumer-side contract for the lead-time / transport-mode configuration.

Jack (W2) will publish a versioned JSON config: route x warehouse x mode with
segmented days. This module is OUR side of the contract — it consumes that file
and **fails loudly** when anything is missing or unproven. There is deliberately
no built-in default, no fallback path and no environment variable: a missing
file, a missing field, an unknown route or an unusable version raises.

Schema (version 1)
------------------
{
  "version": "2026-10-23.1",            # 必填，格式 YYYY-MM-DD[.N][-SUFFIX]
  "effective_from": "2026-10-23",       # 必填，ISO 日期
  "profiles": [                         # 必填，非空
    {
      "route_id": "CN->US-WEST",        # 必填，非空字符串
      "warehouse": "美中-FZH-DANEEY",   # 必填，非空字符串（与库存口径同名）
      "mode": "slow_boat",              # 必填，slow_boat|fast_boat|air|3pl
      "segments": {                     # 必填，三个非负天数（自然日）
        "order_to_departure": 14,
        "departure_to_arrival": 30,
        "arrival_to_stock": 7
      },
      "source": "assumed",              # 必填，measured|assumed|business
      "sample_size": 0,                 # 必填，整数 >= 0；measured 时必须 > 0
      "owner": "business",              # 必填，非空字符串
      "notes": "示例，不是业务已批准参数"   # 必填，字符串
    }
  ]
}

Contract rules
--------------
* 天数按自然日（calendar days）计算 —— 这一点需与业务/Jack 书面确认，见报告。
* `source=assumed` 的配置可以用于情景，但**不得**被调用方当成实测；返回的
  `Availability.is_assumed` 为 True，`explain()` 会显式写出来源与版本。
* 同一 (route_id, warehouse, mode) 不得重复（重复 = 歧义，直接报错）。
* 未知字段不报错但记入 `config.warnings`（向前兼容 Jack 后续加字段）；
  已知字段缺失或类型非法一律报错。
* 配置在 `effective_from` 之前不生效：用早于它的下单日计算会报错，
  避免拿新口径回算历史。

Usage
-----
    cfg = load_config("path/to/leadtime.json", expected_version="2026-10-23.1")
    av = cfg.expected_available_date("CN->US-WEST", "slow_boat", date(2026, 10, 24))
    av.available_date, av.source, av.is_assumed, av.explain()

Run tests:
  uv run python docs/research/supply-chain/2026-10-20/claude/experiments/sc13/test_leadtime_config.py
  uv run python -m pytest docs/research/supply-chain/2026-10-20/claude/experiments/sc13/test_leadtime_config.py -q
"""
from __future__ import annotations

import json
import re
from dataclasses import dataclass, field
from datetime import date, timedelta
from pathlib import Path
from typing import Any

MODES = ("slow_boat", "fast_boat", "air", "3pl")
SOURCES = ("measured", "assumed", "business")
SEGMENT_KEYS = ("order_to_departure", "departure_to_arrival", "arrival_to_stock")
PROFILE_KEYS = ("route_id", "warehouse", "mode", "segments", "source",
                "sample_size", "owner", "notes")
TOP_KEYS = ("version", "effective_from", "profiles")
_VERSION_RE = re.compile(r"^\d{4}-\d{2}-\d{2}(\.\d+)?(-[A-Za-z0-9._-]+)?$")


# ---------------------------------------------------------------------------
# errors — every one of them is explicit; none of them silently defaults
# ---------------------------------------------------------------------------

class LeadTimeConfigError(Exception):
    """Base class: the caller must handle or propagate, never swallow."""


class ConfigNotFound(LeadTimeConfigError):
    """The config file does not exist (we do NOT fall back to built-in days)."""


class ConfigParseError(LeadTimeConfigError):
    """The file is not valid JSON / not a JSON object."""


class ConfigSchemaError(LeadTimeConfigError):
    """A required field is missing or invalid. `.field` names the exact path."""

    def __init__(self, field_path: str, problem: str) -> None:
        self.field = field_path
        self.problem = problem
        super().__init__(f"配置字段 `{field_path}` 不合法：{problem}")


class ConfigVersionError(LeadTimeConfigError):
    """The version is missing, malformed, or does not match what the caller expects."""


class ConfigNotEffective(LeadTimeConfigError):
    """The config is not in force yet for the requested date."""


class UnknownRoute(LeadTimeConfigError):
    """No profile matches route/warehouse/mode — the caller must not guess days."""


class ConfigAmbiguous(LeadTimeConfigError):
    """More than one profile matches and the caller did not disambiguate."""


# ---------------------------------------------------------------------------
# value objects
# ---------------------------------------------------------------------------

@dataclass(frozen=True)
class Profile:
    route_id: str
    warehouse: str
    mode: str
    segments: dict
    source: str
    sample_size: int
    owner: str
    notes: str
    total_days: float

    @property
    def is_assumed(self) -> bool:
        return self.source == "assumed"

    @property
    def key(self) -> tuple[str, str, str]:
        return (self.route_id, self.warehouse, self.mode)


@dataclass(frozen=True)
class LeadTimeConfig:
    version: str
    effective_from: date
    profiles: tuple[Profile, ...]
    path: Path
    warnings: tuple[str, ...] = field(default_factory=tuple)

    def find(self, route_id: str, mode: str, warehouse: str | None = None) -> Profile:
        if mode not in MODES:
            raise ConfigSchemaError("mode", f"{mode!r} 不在允许值 {list(MODES)} 中")
        hits = [p for p in self.profiles
                if p.route_id == route_id and p.mode == mode
                and (warehouse is None or p.warehouse == warehouse)]
        if not hits:
            raise UnknownRoute(
                f"route_id={route_id!r} mode={mode!r} warehouse={warehouse!r} "
                f"不在配置 {self.version} 中（不回退到默认天数）")
        if len(hits) > 1:
            whs = sorted(p.warehouse for p in hits)
            raise ConfigAmbiguous(
                f"route_id={route_id!r} mode={mode!r} 匹配到多个仓 {whs}，"
                "请显式传入 warehouse")
        return hits[0]

    def expected_available_date(self, route_id: str, mode: str, order_date: date,
                                *, warehouse: str | None = None) -> "Availability":
        profile = self.find(route_id, mode, warehouse)
        if not isinstance(order_date, date):
            raise ConfigSchemaError("order_date", f"需要 datetime.date，收到 {type(order_date).__name__}")
        if order_date < self.effective_from:
            raise ConfigNotEffective(
                f"配置 {self.version} 自 {self.effective_from.isoformat()} 起生效，"
                f"不能用于 {order_date.isoformat()} 的下单日（不做追溯回算）")
        s = profile.segments
        departure = order_date + timedelta(days=s["order_to_departure"])
        arrival = departure + timedelta(days=s["departure_to_arrival"])
        available = arrival + timedelta(days=s["arrival_to_stock"])
        return Availability(
            route_id=profile.route_id, warehouse=profile.warehouse, mode=profile.mode,
            order_date=order_date, departure_date=departure, arrival_date=arrival,
            available_date=available, total_days=profile.total_days,
            segments=dict(s), source=profile.source, sample_size=profile.sample_size,
            owner=profile.owner, notes=profile.notes, version=self.version,
            effective_from=self.effective_from,
        )


@dataclass(frozen=True)
class Availability:
    """The answer the evaluator receives — the source always travels with it."""
    route_id: str
    warehouse: str
    mode: str
    order_date: date
    departure_date: date
    arrival_date: date
    available_date: date
    total_days: float
    segments: dict
    source: str
    sample_size: int
    owner: str
    notes: str
    version: str
    effective_from: date

    @property
    def is_assumed(self) -> bool:
        return self.source == "assumed"

    @property
    def is_measured(self) -> bool:
        return self.source == "measured"

    def explain(self) -> str:
        """One line a decision can carry: dates, mode, source and config version."""
        return (f"{self.route_id} / {self.warehouse} / {self.mode}："
                f"下单 {self.order_date.isoformat()} → 预计可用 {self.available_date.isoformat()}"
                f"（{self.total_days:g} 自然日，source={self.source}"
                + (f"，样本 {self.sample_size}" if self.sample_size else "，未实测")
                + f"，配置版本 {self.version}）")


# ---------------------------------------------------------------------------
# loader
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


def _number(doc: dict, key: str, where: str, *, minimum: float = 0.0) -> float:
    value = _require(doc, key, where)
    if isinstance(value, bool) or not isinstance(value, (int, float)):
        raise ConfigSchemaError(f"{where}{key}", f"需要数字，收到 {value!r}")
    if value < minimum:
        raise ConfigSchemaError(f"{where}{key}", f"需要 >= {minimum:g}，收到 {value}")
    return float(value)


def _parse_date(value: Any, field_path: str) -> date:
    if not isinstance(value, str):
        raise ConfigSchemaError(field_path, f"需要 ISO 日期字符串，收到 {value!r}")
    try:
        return date.fromisoformat(value)
    except ValueError as exc:
        raise ConfigSchemaError(field_path, f"无法解析为 ISO 日期：{value!r}") from exc


def load_config(path: str | Path, *, expected_version: str | None = None,
                as_of: date | None = None) -> LeadTimeConfig:
    """Load and strictly validate the lead-time config.

    Raises (never defaults):
      ConfigNotFound     file missing
      ConfigParseError   not JSON / not an object
      ConfigSchemaError  missing or invalid field (`.field` carries the path)
      ConfigVersionError version malformed or != expected_version
      ConfigNotEffective effective_from is later than `as_of`
    """
    if path is None:
        raise TypeError("load_config(path) 需要显式路径；本模块不提供默认配置")
    p = Path(path)
    if not p.is_file():
        raise ConfigNotFound(f"配置文件不存在：{p}（不回退到内置默认天数）")
    try:
        doc = json.loads(p.read_text(encoding="utf-8"))
    except json.JSONDecodeError as exc:
        raise ConfigParseError(f"{p} 不是合法 JSON：{exc}") from exc
    if not isinstance(doc, dict):
        raise ConfigParseError(f"{p} 顶层必须是 JSON 对象，收到 {type(doc).__name__}")

    warnings: list[str] = []

    # ---- version / effective_from ----------------------------------------
    version = _non_empty_str(doc, "version", "")
    if not _VERSION_RE.match(version):
        raise ConfigVersionError(
            f"version={version!r} 格式不合法，应为 YYYY-MM-DD、YYYY-MM-DD.N 或带 -SUFFIX 的变体")
    if expected_version is not None and version != expected_version:
        raise ConfigVersionError(
            f"版本不匹配：配置是 {version!r}，调用方要求 {expected_version!r}")
    effective_from = _parse_date(_require(doc, "effective_from", ""), "effective_from")
    if as_of is not None and effective_from > as_of:
        raise ConfigNotEffective(
            f"配置自 {effective_from.isoformat()} 起生效，晚于请求日 {as_of.isoformat()}")

    # ---- profiles ---------------------------------------------------------
    raw_profiles = _require(doc, "profiles", "")
    if not isinstance(raw_profiles, list) or not raw_profiles:
        raise ConfigSchemaError("profiles", "需要非空列表")

    profiles: list[Profile] = []
    seen: dict[tuple[str, str, str], int] = {}
    for i, item in enumerate(raw_profiles):
        where = f"profiles[{i}]."
        if not isinstance(item, dict):
            raise ConfigSchemaError(f"profiles[{i}]", f"需要对象，收到 {type(item).__name__}")
        for extra in sorted(set(item) - set(PROFILE_KEYS)):
            warnings.append(f"未知字段 profiles[{i}].{extra} 已忽略")

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
        seg = {k: float(segments[k]) for k in SEGMENT_KEYS}

        source = _non_empty_str(item, "source", where)
        if source not in SOURCES:
            raise ConfigSchemaError(f"{where}source", f"{source!r} 不在允许值 {list(SOURCES)} 中")
        sample_size = _number(item, "sample_size", where)
        if sample_size != int(sample_size):
            raise ConfigSchemaError(f"{where}sample_size", f"需要整数，收到 {sample_size}")
        sample_size = int(sample_size)
        if source == "measured" and sample_size <= 0:
            raise ConfigSchemaError(
                f"{where}sample_size",
                "source=measured 必须 sample_size>0（实测声明不得样本为零）")
        owner = _non_empty_str(item, "owner", where)
        notes = _require(item, "notes", where)
        if not isinstance(notes, str):
            raise ConfigSchemaError(f"{where}notes", f"需要字符串，收到 {type(notes).__name__}")

        profile = Profile(route_id=route_id, warehouse=warehouse, mode=mode,
                          segments=seg, source=source, sample_size=sample_size,
                          owner=owner, notes=notes, total_days=sum(seg.values()))
        if profile.key in seen:
            raise ConfigSchemaError(
                f"profiles[{i}]",
                f"与 profiles[{seen[profile.key]}] 重复：{profile.key}（重复会产生歧义）")
        seen[profile.key] = i
        profiles.append(profile)

    for extra in sorted(set(doc) - set(TOP_KEYS)):
        warnings.append(f"未知顶层字段 {extra} 已忽略")

    return LeadTimeConfig(version=version, effective_from=effective_from,
                          profiles=tuple(profiles), path=p, warnings=tuple(warnings))
