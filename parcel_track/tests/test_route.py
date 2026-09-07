from __future__ import annotations

from parcel_track.route import detect_carrier


def test_column_beats_numeric_looking_number():
    r = detect_carrier("123456789012", {"邮寄方式": "UPS Ground"})
    assert r.carrier == "ups"


def test_1z_fallback_when_column_empty():
    r = detect_carrier("1Z999AA10123456784", {})
    assert r.carrier == "ups"


def test_fedex_hint():
    r = detect_carrier("382954490594", {"邮寄方式": "FedEx Ground"})
    assert r.carrier == "fedex"


def test_gls_parked():
    r = detect_carrier("1234567890", {"邮寄方式": "GLS"})
    assert r.carrier is None
    assert r.reason == "unsupported:gls"


def test_gofo_prefix_parked():
    r = detect_carrier("GFUS010188602773264169", {})
    assert r.carrier is None
    assert r.reason == "unsupported:gofo"


def test_missing_tracking():
    r = detect_carrier("  ", {})
    assert r.reason == "missing_tracking"
