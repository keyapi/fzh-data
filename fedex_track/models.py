"""FedEx Track API 响应 → 归一化模型。

解析 ``POST /track/v1/trackingnumbers`` 的 JSON。FedEx 事件结构（best-effort）：
``output.completeTrackResults[].trackResults[].scanEvents[]``，每条含
``date``(ISO, 带 UTC 偏移)、``eventType``(码)、``eventDescription``、``derivedStatus``、
``scanLocation``。**scanEvents 为倒序（最新在前）**，本模型按升序保留全部历史。

关键时点（销售核查迟发/漏发）：
- label_created_dt：建标（Label created / Shipment information sent to FedEx）
- picked_up_dt：站点/站点收件（Picked up / Arrived at FedEx location / Shipment picked up）
- delivery_dt：交付（Delivered）
本模块采用"事件码 + derivedStatus/description 关键字兜底"提取，全部节点都保留在 ``events``。
"""

from __future__ import annotations

import datetime as _dt
from dataclasses import dataclass, field
from typing import Any

_LABEL_KEYWORDS = ("label created", "shipment information sent to fedex", "label(s) created")
_PICKUP_KEYWORDS = (
    "picked up", "shipment picked up", "pickup", "arrived at fedex location",
    "fedex received", "received by fedex", "origin scan", "at fedex origin facility",
    "shipper information sent",
)
_DELIVERED_KEYWORDS = ("delivered",)
_CANCELLED_KEYWORDS = ("cancelled", "canceled", "returned to shipper")


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


def _parse_iso(s: str | None) -> _dt.datetime | None:
    s = (s or "").strip()
    if not s:
        return None
    try:
        d = _dt.datetime.fromisoformat(s.replace("Z", "+00:00"))
    except ValueError:
        try:
            d = _dt.datetime.fromisoformat(s)
        except ValueError:
            return None
    # 去掉 tz，得到扫描地墙钟时间（便于排序与展示）
    return d.replace(tzinfo=None)


def parse_event_dt(value: Any) -> _dt.datetime | None:
    """接受 ISO 字符串或 {…date…} 之类，返回 naive datetime。"""
    if isinstance(value, str):
        return _parse_iso(value)
    if isinstance(value, list):
        for item in value:
            d = _parse_iso(_text(_dig(item, "date")))
            if d:
                return d
    if isinstance(value, dict):
        return _parse_iso(_text(_dig(value, "date")))
    return None


@dataclass
class FdxEvent:
    """单条跟踪节点（scanEvents 项）。"""

    dt: _dt.datetime | None
    event_type: str | None  # eventType，如 DL / OC / PU / AR / OD
    description: str | None  # eventDescription
    derived_status: str | None  # derivedStatus，如 Label created / Delivered
    derived_status_code: str | None
    exception: str | None  # exceptionDescription
    city: str | None
    state: str | None
    postal: str | None
    country: str | None
    raw: dict[str, Any] | None = None


@dataclass
class FdxTrackInfo:
    """单个跟踪号归一化结果。events 保留完整历史（升序）。"""

    tracking_number: str
    carrier_code: str | None = None  # FDXG=Ground, FDXE=Express, …
    not_found: bool = False
    delivered: bool = False
    cancelled: bool = False
    current_status: str | None = None
    current_status_code: str | None = None
    current_status_scan_location: str | None = None
    label_created_dt: _dt.datetime | None = None
    picked_up_dt: _dt.datetime | None = None  # 站点收件（关键：查迟发/漏发）
    delivery_dt: _dt.datetime | None = None
    delivery_city: str | None = None
    delivery_state: str | None = None
    last_event_dt: _dt.datetime | None = None
    events: list[FdxEvent] = field(default_factory=list)  # 时间升序
    raw: dict[str, Any] | None = None


def _match_kw(text: str | None, kws: tuple[str, ...]) -> bool:
    if not text:
        return False
    low = text.lower()
    return any(k in low for k in kws)


def _extract_events(track_result: dict[str, Any]) -> list[FdxEvent]:
    events: list[FdxEvent] = []
    for sc in _dig(track_result, "scanEvents", default=[]) or []:
        loc = _dig(sc, "scanLocation", default={}) or {}
        events.append(
            FdxEvent(
                dt=parse_event_dt(_dig(sc, "date")),
                event_type=_text(_dig(sc, "eventType")) or _text(_dig(sc, "derivedStatusCode")),
                description=_text(_dig(sc, "eventDescription")) or _text(_dig(sc, "derivedStatus")),
                derived_status=_text(_dig(sc, "derivedStatus")),
                derived_status_code=_text(_dig(sc, "derivedStatusCode")),
                exception=_text(_dig(sc, "exceptionDescription")),
                city=_text(_dig(loc, "city")),
                state=_text(_dig(loc, "stateOrProvinceCode")),
                postal=_text(_dig(loc, "postalCode")),
                country=_text(_dig(loc, "countryCode")),
                raw=sc,
            )
        )
    # 去重（同时间+描述+城市）
    seen: set[tuple[Any, ...]] = set()
    uniq: list[FdxEvent] = []
    for ev in events:
        key = (ev.dt, ev.event_type, ev.description, ev.city)
        if key in seen:
            continue
        seen.add(key)
        uniq.append(ev)
    # 升序；缺时间放最后
    uniq.sort(key=lambda e: (e.dt is None, e.dt))
    return uniq


def _first_dt(events: list[FdxEvent], kws: tuple[str, ...]) -> _dt.datetime | None:
    cand = [e for e in events if e.dt is not None and (
        _match_kw(e.description, kws) or _match_kw(e.derived_status, kws)
    )]
    if cand:
        return cand[0].dt
    return None


def parse_track_result(number: str, track_result: dict[str, Any]) -> FdxTrackInfo:
    """把单个 trackResult 解析成 FdxTrackInfo。"""
    info = FdxTrackInfo(
        tracking_number=number,
        carrier_code=_text(_dig(track_result, "trackingNumberInfo", "carrierCode")),
        raw=track_result,
    )
    events = _extract_events(track_result)
    if not events:
        info.not_found = True
    else:
        info.events = events
        info.last_event_dt = max((e.dt for e in events if e.dt), default=None)

    latest = _dig(track_result, "latestStatusDetail", default={}) or {}
    info.current_status = _text(_dig(latest, "description")) or info.current_status
    info.current_status_code = _text(_dig(latest, "code")) or info.current_status_code
    sl = _dig(latest, "scanLocation", default={}) or {}
    info.current_status_scan_location = _text(_dig(sl, "city")) or ""

    # 已交付 / 取消：FedEx 事件流里可能出现一条 CA(取消)节点，但包裹实际已交付；
    # 故名"取消"仅当**最终状态**为取消且未交付（latestStatusDetail.code in CA/CAF 且未 delivered）。
    deliv_events = [
        e for e in events
        if e.event_type == "DL" or _match_kw(e.description, _DELIVERED_KEYWORDS)
        or _match_kw(e.derived_status, _DELIVERED_KEYWORDS)
    ]
    if deliv_events:
        info.delivered = True
        last_d = max((e for e in deliv_events if e.dt), key=lambda e: e.dt, default=None)
        if last_d is not None:
            info.delivery_dt = last_d.dt
            info.delivery_city = last_d.city
            info.delivery_state = last_d.state

    if not info.delivered and (
        info.current_status_code in ("CA", "CAF")
        or _match_kw(info.current_status, _CANCELLED_KEYWORDS)
    ):
        info.cancelled = True

    # 建标（最早的 Label created / Shipment information sent）
    info.label_created_dt = _first_dt(events, _LABEL_KEYWORDS)
    # 站点收件（Picked up / Arrived at FedEx location）
    info.picked_up_dt = _first_dt(events, _PICKUP_KEYWORDS)
    if info.picked_up_dt is None:
        # 兜底：已交付但找不到 pickup 节点 → 用首条非"建标"节点
        non_label = [e for e in events if e.dt is not None and not _match_kw(e.description, _LABEL_KEYWORDS)]
        if non_label:
            info.picked_up_dt = non_label[0].dt

    return info


def parse_track_results(number: str, track_results: list[dict[str, Any]]) -> list[FdxTrackInfo]:
    """一个跟踪号可能对应**多票**（FedEx 复用跟踪号，约 4–6 年一轮回），逐条解析。"""
    return [parse_track_result(number, tr) for tr in track_results or []]


def parse_track_payload(number: str, payload: dict[str, Any]) -> list[FdxTrackInfo]:
    """从完整响应里按 trackingNumber 取出**全部** trackResult 解析；找不到则一条 not_found。"""
    results: list[FdxTrackInfo] = []
    for ctr in _dig(payload, "output", "completeTrackResults", default=[]) or []:
        if _text(ctr.get("trackingNumber")) == number:
            for tr in _dig(ctr, "trackResults", default=[]) or []:
                results.append(parse_track_result(number, tr))
    if results:
        return results
    return [FdxTrackInfo(tracking_number=number, not_found=True, raw=payload)]
