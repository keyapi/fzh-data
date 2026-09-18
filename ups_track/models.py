"""UPS Track API 响应 → 归一化模型。

解析 ``GET /api/track/v1/details/{inquiryNumber}`` 的 JSON（best-effort）。
UPS 事件词表/字段结构以真实响应为准——先用 CIE 样例校准（见 docs/index.md），
本模块采用"status type 优先 + description 文本兜底"的提取策略，全部原始事件都会保留。
"""

from __future__ import annotations

import datetime as _dt
from dataclasses import dataclass, field
from typing import Any

# UPS 交付关键字的兜底匹配（不区分大小写）
_LABEL_KEYWORDS = ("label created", "shipper created", "label for shipment", "label(s) created")
_WE_HAVE_KEYWORDS = ("we have your package",)
_ORIGIN_KEYWORDS = (
    "origin scan",
    "shipment received",
    "package received after label created",
    "picked up",
    "pickup scan",
    "arrived at ups facility",
)


def _dig(obj: Any, *keys: str, default: Any = None) -> Any:
    cur = obj
    for k in keys:
        if not isinstance(cur, dict):
            return default
        if k not in cur:
            return default
        cur = cur[k]
    return cur


def _text(val: Any) -> str | None:
    if val is None:
        return None
    s = str(val).strip()
    return s or None


def _parse_ymd(s: str | None) -> _dt.datetime | None:
    s = (s or "").strip()
    if not s:
        return None
    for fmt in ("%Y%m%d", "%Y-%m-%d", "%m/%d/%Y"):
        try:
            return _dt.datetime.strptime(s, fmt)
        except ValueError:
            continue
    return None


def parse_event_dt(date_s: str | None, time_s: str | None) -> _dt.datetime | None:
    """UPS date ``YYYYMMDD`` + time ``HHMMSS``（可带冒号/缺秒）→ naive datetime。"""
    d = _parse_ymd(date_s)
    if d is None:
        return None
    h = m = s = 0
    if time_s:
        t = str(time_s).strip()
        if ":" in t:
            parts = [int(x) for x in t.split(":") if x != ""]
        else:
            t2 = t.replace(".", "").replace(" ", "")
            if len(t2) >= 6:
                parts = [int(t2[0:2]), int(t2[2:4]), int(t2[4:6])]
            elif len(t2) >= 4:
                parts = [int(t2[0:2]), int(t2[2:4])]
            else:
                parts = [int(t2)]
        if parts:
            h = parts[0]
        if len(parts) > 1:
            m = parts[1]
        if len(parts) > 2:
            s = parts[2]
    return d.replace(hour=h, minute=m, second=s, microsecond=0)


@dataclass
class UpsEvent:
    """单条跟踪节点（activity 项）。"""

    dt: _dt.datetime | None
    status_type: str | None
    status_code: str | None
    description: str | None
    city: str | None
    state: str | None
    postal: str | None
    raw: dict[str, Any] | None = None


@dataclass
class UpsTrackInfo:
    """单个跟踪号归一化后的结果（PB 核查关注三时点：建标/实际发货/交付）。"""

    tracking_number: str
    not_found: bool = False
    delivered: bool = False
    current_status: str | None = None
    current_status_code: str | None = None
    current_status_type: str | None = None
    label_created_dt: _dt.datetime | None = None
    actual_ship_dt: _dt.datetime | None = None  # "We Have Your Package"/Origin Scan
    delivery_dt: _dt.datetime | None = None
    delivery_city: str | None = None
    delivery_state: str | None = None
    delivery_signed_by: str | None = None
    last_event_dt: _dt.datetime | None = None
    events: list[UpsEvent] = field(default_factory=list)  # 按时间升序
    raw: dict[str, Any] | None = None


def _first_date(value: Any) -> _dt.datetime | None:
    """deliveryDate 可能是字符串或 [{"date": ...}]，兼容两者。"""
    if isinstance(value, str):
        return _parse_ymd(value)
    if isinstance(value, list):
        for item in value:
            d = _text(_dig(item, "date"))
            if d:
                return _parse_ymd(d)
    return None


def _match_keywords(desc: str | None, kws: tuple[str, ...]) -> bool:
    if not desc:
        return False
    low = desc.lower()
    return any(k in low for k in kws)


def _extract_activity_events(payload: dict[str, Any]) -> list[UpsEvent]:
    events: list[UpsEvent] = []
    tr = _dig(payload, "trackResponse", default={})
    for sh in _dig(tr, "shipment", default=[]) or []:
        for pkg in _dig(sh, "package", default=[]) or []:
            for act in _dig(pkg, "activity", default=[]) or []:
                loc_addr = _dig(act, "location", "address", default={})
                ev = UpsEvent(
                    dt=parse_event_dt(
                        _text(_dig(act, "date")), _text(_dig(act, "time"))
                    ),
                    status_type=_text(_dig(act, "status", "type")),
                    status_code=_text(_dig(act, "status", "code"))
                    or _text(_dig(act, "status", "statusCode")),
                    description=_text(_dig(act, "status", "description")),
                    city=_text(_dig(loc_addr, "city")),
                    state=_text(_dig(loc_addr, "stateProvince")),
                    postal=_text(_dig(loc_addr, "postalCode")),
                    raw=act,
                )
                events.append(ev)
    # 去重（同 时间+描述+城市），保留首次出现的原始顺序
    seen: set[tuple[Any, ...]] = set()
    uniq: list[UpsEvent] = []
    for ev in events:
        key = (ev.dt, ev.status_type, ev.description, ev.city)
        if key in seen:
            continue
        seen.add(key)
        uniq.append(ev)
    # 时间升序；缺时间的放最后保持原序
    uniq.sort(key=lambda e: (e.dt is None, e.dt))
    return uniq


def parse_track_payload(number: str, payload: dict[str, Any]) -> UpsTrackInfo:
    """把 track/details 响应解析成 UpsTrackInfo。

    status type 约定：``D`` = 已交付；description 文本做兜底。
    事件词表如有出入以真实 CIE/prod 响应对齐后调整 *_KEYWORDS。
    """
    info = UpsTrackInfo(tracking_number=number, raw=payload)
    tr = _dig(payload, "trackResponse", default={})
    shipments = _dig(tr, "shipment", default=[]) or []

    events = _extract_activity_events(payload)
    if not events:
        info.not_found = True
    else:
        info.events = events
        info.last_event_dt = max((e.dt for e in events if e.dt), default=None)

    # ── 已交付：任一 status.type == "D"，或描述含 delivered ──
    delivered_events = [
        e for e in events if e.status_type == "D" or _match_keywords(e.description, ("delivered",))
    ]
    if delivered_events:
        info.delivered = True
        last_d = max((e for e in delivered_events if e.dt), key=lambda e: e.dt, default=None)
        if last_d is not None:
            info.delivery_dt = last_d.dt
            info.delivery_city = last_d.city
            info.delivery_state = last_d.state
        elif delivered_events:
            e0 = delivered_events[0]
            info.delivery_city = info.delivery_city or e0.city
            info.delivery_state = info.delivery_state or e0.state

    # ── 建标：description 含 Label Created / Shipper created（无则留空，不猜）──
    label_events = [e for e in events if _match_keywords(e.description, _LABEL_KEYWORDS)]
    if label_events and label_events[0].dt is not None:
        info.label_created_dt = label_events[0].dt

    # ── 实际发货（We Have Your Package / Origin Scan / Shipment Received）──
    whp = [e for e in events if _match_keywords(e.description, _WE_HAVE_KEYWORDS)]
    origin = [e for e in events if _match_keywords(e.description, _ORIGIN_KEYWORDS)]
    ship_cand = (whp or origin)
    ship_cand = [e for e in ship_cand if e.dt is not None]
    if ship_cand:
        info.actual_ship_dt = ship_cand[0].dt
    else:
        # 若已交付但找不到 pickup 节点，用首条非"建标"事件兜底（仅当存在）
        non_label = [e for e in events if e.dt is not None and not _match_keywords(e.description, _LABEL_KEYWORDS)]
        if non_label:
            info.actual_ship_dt = non_label[0].dt

    # ── 顶层 currentStatus / 交付信息（以 shipment[0] 为准，best-effort）──
    sh0 = shipments[0] if shipments else {}
    cur = _dig(sh0, "currentStatus", default={})
    info.current_status_type = _text(_dig(cur, "type"))
    info.current_status_code = _text(_dig(cur, "code"))
    info.current_status = _text(_dig(cur, "description"))
    if not info.current_status and events:
        last = events[-1]
        info.current_status = last.description or info.current_status
        info.current_status_type = info.current_status_type or last.status_type

    if not info.delivery_dt:
        dd = _first_date(_dig(sh0, "deliveryDate"))
        if dd is not None:
            info.delivery_dt = dd
    if not info.delivery_dt:
        pkg0 = _dig(sh0, "package", default=[{}])[0] if _dig(sh0, "package", default=[]) else {}
        dd2 = _first_date(_dig(pkg0, "deliveryDate"))
        if dd2 is not None:
            info.delivery_dt = dd2

    dinfo = _dig(sh0, "deliveryInformation", default={})
    info.delivery_signed_by = _text(_dig(dinfo, "signedBy"))
    if not info.delivery_signed_by:
        info.delivery_signed_by = _text(_dig(dinfo, "location"))
    if not info.delivery_city:
        dloc = _dig(dinfo, "deliveryLocation", "address", default={})
        info.delivery_city = info.delivery_city or _text(_dig(dloc, "city"))
        info.delivery_state = info.delivery_state or _text(_dig(dloc, "stateProvince"))

    return info
