"""离线 FedEx Track JSON 夹具。"""

from __future__ import annotations


def _ev(date: str, event_type: str, desc: str, derived: str, code: str, city: str = "Newark", state: str = "DE"):
    return {
        "date": date,
        "eventType": event_type,
        "eventDescription": desc,
        "derivedStatus": derived,
        "derivedStatusCode": code,
        "scanLocation": {"city": city, "stateOrProvinceCode": state, "postalCode": "19702", "countryCode": "US"},
    }


def track_payload(number: str, track_results: list[dict]) -> dict:
    return {
        "output": {
            "completeTrackResults": [{
                "trackingNumber": number,
                "trackResults": track_results,
            }]
        }
    }


def delivered_result(number: str) -> dict:
    return {
        "trackingNumberInfo": {"trackingNumber": number, "carrierCode": "FDXG"},
        "latestStatusDetail": {"code": "DL", "description": "Delivered", "scanLocation": {"city": "Newark"}},
        "scanEvents": [
            _ev("2026-08-05T10:44:00-04:00", "DL", "Delivered", "Delivered", "DL"),
            _ev("2026-08-04T09:00:00-04:00", "PU", "Picked up", "Picked up", "PU", "East Hanover", "NJ"),
            _ev("2026-08-03T08:00:00-04:00", "OC", "Shipment information sent to FedEx", "Label created", "IN", "East Hanover", "NJ"),
        ],
    }


def cancelled_result(number: str) -> dict:
    return {
        "trackingNumberInfo": {"trackingNumber": number, "carrierCode": "FDXG"},
        "latestStatusDetail": {"code": "CA", "description": "Shipment cancelled by sender"},
        "scanEvents": [
            _ev("2026-08-05T11:00:00-04:00", "CA", "Shipment cancelled by sender", "Cancelled", "CA"),
            _ev("2026-08-03T08:00:00-04:00", "OC", "Shipment information sent to FedEx", "Label created", "IN"),
        ],
    }


def delivered_with_ca_residue(number: str) -> dict:
    """最终已交付，但事件流残留一条 CA。"""
    r = delivered_result(number)
    r["scanEvents"].append(_ev("2026-08-03T09:00:00-04:00", "CA", "Shipment cancelled", "Cancelled", "CA"))
    return r


def returned_to_shipper_result(number: str) -> dict:
    """RTS 文案、非 CA/CAF 码。"""
    return {
        "trackingNumberInfo": {"trackingNumber": number, "carrierCode": "FDXG"},
        "latestStatusDetail": {"code": "RS", "description": "Returned to shipper"},
        "scanEvents": [
            _ev("2026-08-06T12:00:00-04:00", "RS", "Returned to shipper", "Returned to shipper", "RS"),
            _ev("2026-08-03T08:00:00-04:00", "OC", "Shipment information sent to FedEx", "Label created", "IN"),
        ],
    }
