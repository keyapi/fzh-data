"""GLS 公开 REST 响应 → 归一化模型（best-effort，词表以真实 EN 响应校准）。

公开接口两段（免登录）：
- 摘要 rstt029：无邮编也能拿状态（progressBar.statusInfo / arrivalTime）。
- 明细 rstt028：需目的邮编，返回完整 history（建标/交接/中转/交付/签收）。

GLS 事件描述为英文短语；关键时点用关键字兜底匹配，词表随真实响应修正。
"""

from __future__ import annotations

import datetime as _dt
from dataclasses import dataclass, field
from typing import Any

_MONTHS = {
    "jan": 1, "feb": 2, "mar": 3, "apr": 4, "may": 5, "jun": 6,
    "jul": 7, "aug": 8, "sep": 9, "oct": 10, "nov": 11, "dec": 12,
}

# 关键时点关键词（事件描述小写匹配）
_DATA_ENTERED_KWS = ("entered into the gls it system", "data entered")
_HANDED_KWS = ("handed over to gls",)
_DELIVERED_KWS = ("delivered",)
# 建标事件描述形如 "...not yet handed over to GLS"——含 "handed over" 但并非交接，
# 匹配交接前须排除 "not yet"。
_NOT_YET = "not yet"


def _text(v: Any) -> str | None:
    if v is None:
        return None
    s = str(v).strip()
    return s or None


def _dig(obj: Any, *keys: str, default: Any = None) -> Any:
    cur = obj
    for k in keys:
        if not isinstance(cur, dict):
            return default
        if k not in cur:
            return default
        cur = cur[k]
    return cur


def _parse_event_dt(date_s: str | None, time_s: str | None) -> _dt.datetime | None:
    date_s = (date_s or "").strip()
    time_s = (time_s or "").strip()
    if not date_s:
        return None
    try:
        y, m, d = (int(x) for x in date_s.split("-"))
        base = _dt.date(y, m, d)
    except (ValueError, TypeError):
        return None
    h = mi = s = 0
    if time_s:
        parts = time_s.split(":")
        try:
            h = int(parts[0]) if len(parts) > 0 else 0
            mi = int(parts[1]) if len(parts) > 1 else 0
            s = int(parts[2]) if len(parts) > 2 else 0
        except (ValueError, IndexError):
            pass
    return _dt.datetime.combine(base, _dt.time(h, mi, s))


def parse_arrival_text(s: str | None) -> _dt.datetime | None:
    """'03-Sep-2026 at 12:39 o`clock' → datetime；解析失败返回 None。"""
    s = (s or "").strip()
    if not s:
        return None
    try:
        head = s.split(" at ")[0].strip()
        tail = s.split(" at ")[1].split("`")[0].strip().split(" ")[0]
        day, mon, year = head.split("-")
        hm = tail.split(":")
        return _dt.datetime(int(year), _MONTHS[mon[:3].lower()], int(day), int(hm[0]), int(hm[1]))
    except Exception:
        return None


@dataclass
class GlsEvent:
    """单条跟踪节点。"""

    dt: _dt.datetime | None
    description: str | None
    city: str | None
    country_code: str | None


@dataclass
class GlsParcel:
    """单个包裹归一化结果（覆盖 ops 关注时点：数据录入/交接 GLS/交付）。"""

    parcel_no: str
    current_status: str | None = None
    current_status_text: str | None = None
    delivered: bool = False
    delivered_dt: _dt.datetime | None = None
    data_entered_dt: _dt.datetime | None = None  # ≈ 建标/预报（数据录入 GLS IT）
    handed_dt: _dt.datetime | None = None        # ≈ 收件首扫（交接 GLS）
    last_event_dt: _dt.datetime | None = None
    cust_ref: str | None = None                  # CUSTREF（发货时客户引用，可回连订单）
    events: list[GlsEvent] = field(default_factory=list)  # 时间升序
    raw: dict[str, Any] | None = None


def _events_from_history(history: Any) -> list[GlsEvent]:
    events: list[GlsEvent] = []
    for h in history or []:
        if not isinstance(h, dict):
            continue
        addr = _dig(h, "address", default={})
        events.append(
            GlsEvent(
                dt=_parse_event_dt(_text(_dig(h, "date")), _text(_dig(h, "time"))),
                description=_text(_dig(h, "evtDscr")),
                city=_text(_dig(addr, "city")),
                country_code=_text(_dig(addr, "countryCode")),
            )
        )
    events.sort(key=lambda e: (e.dt is None, e.dt))
    return events


def _derive_times(p: GlsParcel) -> None:
    if p.events:
        p.last_event_dt = max((e.dt for e in p.events if e.dt), default=None)
    for e in p.events:
        d = (e.description or "").lower()
        if e.dt is not None and any(k in d for k in _HANDED_KWS) and _NOT_YET not in d and p.handed_dt is None:
            p.handed_dt = e.dt
        if e.dt is not None and any(k in d for k in _DATA_ENTERED_KWS) and p.data_entered_dt is None:
            p.data_entered_dt = e.dt
        if any(k in d for k in _DELIVERED_KWS):
            p.delivered = True
            if e.dt is not None and (p.delivered_dt is None or e.dt > p.delivered_dt):
                p.delivered_dt = e.dt


def parse_summary(no: str, payload: dict[str, Any]) -> GlsParcel:
    """解析 rstt029（摘要）响应。"""
    tu = _dig(payload, "tuStatus", default=[])
    item = tu[0] if tu else {}
    p = GlsParcel(parcel_no=no, raw=payload)
    if not item:
        return p
    pb = _dig(item, "progressBar", default={})
    p.current_status = _text(_dig(pb, "statusInfo"))
    p.current_status_text = _text(_dig(pb, "statusText"))
    p.delivered = (p.current_status or "").upper() == "DELIVERED"
    p.delivered_dt = parse_arrival_text(_text(_dig(_dig(item, "arrivalTime", default={}), "value")))
    return p


def parse_detail(no: str, payload: dict[str, Any]) -> GlsParcel:
    """解析 rstt028（明细，含完整 history）响应。"""
    p = GlsParcel(parcel_no=no, raw=payload)
    pb = _dig(payload, "progressBar", default={})
    p.current_status = _text(_dig(pb, "statusInfo"))
    p.current_status_text = _text(_dig(pb, "statusText"))
    p.events = _events_from_history(payload.get("history"))
    for r in payload.get("references") or []:
        if isinstance(r, dict) and r.get("type") == "CUSTREF":
            p.cust_ref = _text(r.get("value"))
    if (p.current_status or "").upper() == "DELIVERED":
        p.delivered = True
    _derive_times(p)
    if p.delivered and p.delivered_dt is None:
        p.delivered_dt = parse_arrival_text(_text(_dig(_dig(payload, "arrivalTime", default={}), "value")))
    return p
