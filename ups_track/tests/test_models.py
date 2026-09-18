"""models.py 归一化逻辑单测（离线）。"""

from __future__ import annotations

import datetime as _dt

import pytest

from ups_track.models import parse_event_dt, parse_track_payload

from _payloads import delivered_payload, empty_payload


def test_parse_dt_variants():
    assert parse_event_dt("20260723", "141200") == _dt.datetime(2026, 7, 23, 14, 12)
    assert parse_event_dt("2026-07-23", "14:12") == _dt.datetime(2026, 7, 23, 14, 12)
    assert parse_event_dt("20260723", "") == _dt.datetime(2026, 7, 23)
    assert parse_event_dt(None, "141200") is None


def test_parse_delivered_payload():
    info = parse_track_payload("1Z999AA10123456784", delivered_payload())
    assert info.tracking_number == "1Z999AA10123456784"
    assert info.not_found is False
    assert info.delivered is True
    assert info.current_status == "Delivered"
    assert info.label_created_dt == _dt.datetime(2026, 7, 6, 9, 15)
    assert info.actual_ship_dt == _dt.datetime(2026, 7, 20, 18, 30)
    assert info.delivery_dt == _dt.datetime(2026, 7, 23, 14, 12)
    assert info.delivery_city == "West Roxbury"
    assert info.delivery_state == "MA"
    assert info.delivery_signed_by == "A.ROOM"
    assert info.last_event_dt == _dt.datetime(2026, 7, 23, 14, 12)
    # 事件按时间升序
    assert len(info.events) == 4
    assert [e.dt for e in info.events] == sorted(e.dt for e in info.events)


def test_parse_empty_payload():
    info = parse_track_payload("1Z999AA10123456784", empty_payload())
    assert info.not_found is True
    assert info.events == []
    assert info.delivered is False
    assert info.raw is not None


def test_dedup_same_event():
    p = delivered_payload()
    sh = p["trackResponse"]["shipment"][0]
    act = sh["package"][0]["activity"]
    act.append(dict(act[-1]))  # 重复一条 Delivered
    info = parse_track_payload("1Z999AA10123456784", p)
    assert len(info.events) == 4  # 去重后不变
