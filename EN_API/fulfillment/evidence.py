"""证据分层构造器（蓝图 §4）：fact / derived / estimate / assertion。"""
from __future__ import annotations

from datetime import datetime, timezone

from .model import (KIND_ASSERTION, KIND_DERIVED, KIND_ESTIMATE, KIND_FACT,
                    FieldValue)


def _now() -> str:
    return datetime.now(timezone.utc).astimezone().isoformat(timespec="seconds")


def fact(value, source: str, record: str = "") -> FieldValue:
    """来自已提交单据或可验证事件（SO 日期、DN 数量、工序卡完工）。"""
    return FieldValue(value=value, kind=KIND_FACT, source=source,
                      source_record=record, observed_at=_now())


def derived(value, source: str, record: str = "") -> FieldValue:
    """由事实按稳定规则计算（未发量、工序瓶颈、阶段停留天数）。"""
    return FieldValue(value=value, kind=KIND_DERIVED, source=source,
                      source_record=record, observed_at=_now())


def estimate(value, source: str, record: str = "", confidence: str = "low") -> FieldValue:
    """对未来日期/状态的预测（下单+3月、货代 ETA）。"""
    return FieldValue(value=value, kind=KIND_ESTIMATE, source=source,
                      source_record=record, observed_at=_now(), confidence=confidence)


def assertion(value, source: str, record: str = "") -> FieldValue:
    """人工确认但暂无系统证据（如「此 Closed 单实际作废」）。"""
    return FieldValue(value=value, kind=KIND_ASSERTION, source=source,
                      source_record=record, observed_at=_now())
