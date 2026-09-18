"""models.py 归一化：多票、取消 vs 交付、pickup 兜底。"""

from __future__ import annotations

import datetime as _dt

from fedex_track.models import parse_track_payload, parse_track_result

from _payloads import (
    cancelled_result,
    delivered_result,
    delivered_with_ca_residue,
    returned_to_shipper_result,
    track_payload,
)


def test_multi_ticket_payload_keeps_both():
    n = "382954490594"
    old = delivered_result(n)
    old["scanEvents"] = [
        {"date": "2026-06-01T10:00:00-05:00", "eventType": "DL", "eventDescription": "Delivered",
         "derivedStatus": "Delivered", "derivedStatusCode": "DL",
         "scanLocation": {"city": "Venus", "stateOrProvinceCode": "TX"}},
        {"date": "2026-05-28T09:00:00-05:00", "eventType": "OC", "eventDescription": "Shipment information sent to FedEx",
         "derivedStatus": "Label created", "derivedStatusCode": "IN",
         "scanLocation": {"city": "Venus", "stateOrProvinceCode": "TX"}},
    ]
    new = delivered_result(n)
    infos = parse_track_payload(n, track_payload(n, [old, new]))
    assert len(infos) == 2
    assert infos[0].delivered and infos[1].delivered
    assert infos[0].label_created_dt != infos[1].label_created_dt


def test_cancelled_only_when_latest_ca_and_not_delivered():
    n = "875397181317"
    info = parse_track_result(n, cancelled_result(n))
    assert info.cancelled is True
    assert info.delivered is False


def test_delivered_wins_over_ca_residue():
    n = "382915919064"
    info = parse_track_result(n, delivered_with_ca_residue(n))
    assert info.delivered is True
    assert info.cancelled is False


def test_returned_to_shipper_is_not_cancelled():
    n = "111111111111"
    info = parse_track_result(n, returned_to_shipper_result(n))
    assert info.cancelled is False
    assert info.delivered is False


def test_pickup_fallback_only_when_delivered():
    n = "222222222222"
    tr = {
        "trackingNumberInfo": {"trackingNumber": n, "carrierCode": "FDXG"},
        "latestStatusDetail": {"code": "IT", "description": "In transit"},
        "scanEvents": [
            {"date": "2026-08-04T09:00:00-04:00", "eventType": "AR", "eventDescription": "At local FedEx facility",
             "derivedStatus": "In transit", "derivedStatusCode": "IT",
             "scanLocation": {"city": "Newark", "stateOrProvinceCode": "DE"}},
            {"date": "2026-08-03T08:00:00-04:00", "eventType": "OC", "eventDescription": "Shipment information sent to FedEx",
             "derivedStatus": "Label created", "derivedStatusCode": "IN",
             "scanLocation": {"city": "East Hanover", "stateOrProvinceCode": "NJ"}},
        ],
    }
    info = parse_track_result(n, tr)
    assert info.delivered is False
    assert info.picked_up_dt is None
    assert info.label_created_dt == _dt.datetime(2026, 8, 3, 8, 0)


def test_undelivered_description_does_not_mark_delivered():
    n = "333333333333"
    tr = {
        "trackingNumberInfo": {"trackingNumber": n, "carrierCode": "FDXG"},
        "latestStatusDetail": {"code": "IT", "description": "Shipment undelivered"},
        "scanEvents": [
            {"date": "2026-08-04T09:00:00-04:00", "eventType": "DE", "eventDescription": "Shipment undelivered",
             "derivedStatus": "Delivery exception", "derivedStatusCode": "DE",
             "scanLocation": {"city": "Newark", "stateOrProvinceCode": "DE"}},
            {"date": "2026-08-03T08:00:00-04:00", "eventType": "OC", "eventDescription": "Shipment information sent to FedEx",
             "derivedStatus": "Label created", "derivedStatusCode": "IN"},
        ],
    }
    info = parse_track_result(n, tr)
    assert info.delivered is False
