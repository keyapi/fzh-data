from __future__ import annotations

from parcel_track.route import detect_carrier, split_tracking_cell


def test_column_beats_numeric_looking_number():
    r = detect_carrier("123456789012", {"邮寄方式": "UPS Ground"})
    assert r.carrier == "ups"


def test_1z_fallback_when_column_empty():
    r = detect_carrier("1Z999AA10123456784", {})
    assert r.carrier == "ups"


def test_fedex_hint():
    r = detect_carrier("382954490594", {"邮寄方式": "FedEx Ground"})
    assert r.carrier == "fedex"


def test_gls_routed():
    r = detect_carrier("29626585597", {"邮寄方式": "GLS-Poland>>GLS-Poland"})
    assert r.carrier == "gls"


def test_gls_cell_1z_goes_ups():
    r = detect_carrier("1ZE935936893803162", {"邮寄方式": "GLS-Poland>>GLS-Poland"})
    assert r.carrier == "ups"


def test_gls_allegro_u_parked():
    r = detect_carrier("ABC123U", {"邮寄方式": "GLS-Poland"})
    assert r.carrier is None
    assert r.reason == "not_gls_number"


def test_gofo_prefix_parked():
    r = detect_carrier("GFUS010188602773264169", {})
    assert r.carrier is None
    assert r.reason == "unsupported:gofo"


def test_tiktok_parked():
    r = detect_carrier("9234690390471506916903", {"邮寄方式": "Tiktok物流>>Tiktok派送"})
    assert r.carrier is None
    assert r.reason == "unsupported:tiktok"


def test_missing_tracking():
    r = detect_carrier("  ", {})
    assert r.reason == "missing_tracking"


def test_split_cell():
    toks = split_tracking_cell("29626585597, 1ZE935936893803162")
    assert toks == ["29626585597", "1ZE935936893803162"]
