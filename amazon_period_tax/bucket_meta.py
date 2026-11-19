# -*- coding: utf-8 -*-
"""账期桶名 → 日期窗口 / 账期月（Tax、Phase3、ledger 共用）。"""
from __future__ import annotations

import re
from datetime import date

_PERIOD_RE = re.compile(r"(?:账期)?(\d{4})(\d{2})(\d{2})-(\d{4})(\d{2})(\d{2})")


def bucket_period_range(name: str) -> tuple[date, date] | None:
    """``账期20260704-20260803`` → (date(2026,7,4), date(2026,8,3))；无法解析/非法日历返回 None。"""
    m = _PERIOD_RE.search(str(name or ""))
    if not m:
        return None
    y1, mo1, d1, y2, mo2, d2 = (int(x) for x in m.groups())
    try:
        return date(y1, mo1, d1), date(y2, mo2, d2)
    except ValueError:
        return None


def bucket_yyyymm(name: str) -> str | None:
    """``账期20260704-20260803`` → ``202607``。"""
    m = _PERIOD_RE.search(str(name or ""))
    return f"{m.group(1)}{m.group(2)}" if m else None


def resolve_exchange_month(bucket_name: str, requested: str = "", *, force: bool = False) -> str:
    """`--exchange-month` 缺省从桶名推导；显式值必须与桶起始月一致（除非 ``force``）。

    在读写任何表之前调用，避免「8 月桶配 7 月汇率」这类静默错配。
    """
    requested = (requested or "").strip()
    derived = bucket_yyyymm(bucket_name)
    if not requested:
        if not derived:
            raise ValueError(f"无法从桶名推导账期月（需 YYYYMMDD-YYYYMMDD）: {bucket_name!r}")
        return derived
    if not re.fullmatch(r"\d{6}", requested):
        raise ValueError(f"--exchange-month 须为 YYYYMM，收到 {requested!r}")
    if derived and requested != derived and not force:
        raise ValueError(
            f"--exchange-month {requested} 与桶 {bucket_name!r} 的账期月 {derived} 不一致；"
            "确需覆盖请加 --force-month"
        )
    return requested
