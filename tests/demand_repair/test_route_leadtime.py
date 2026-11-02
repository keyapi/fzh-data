import pandas as pd

from supply_netting.route_leadtime import build_route_evidence


def test_dn_route_pool_and_role_are_kept_separate_and_recent_only():
    dn = pd.DataFrame(
        [
            {"dn": "DN-OLD", "posting_date": "2025-01-01", "customer": "CENTRADE", "so": "SO-1", "role": "cover", "lead_days": 99},
            {"dn": "DN-USNJ", "posting_date": "2026-08-01", "customer": "CENTRADE", "so": "SO-1", "role": "cover", "lead_days": 24},
            {"dn": "DN-USTX", "posting_date": "2026-08-02", "customer": "DANEEY", "so": "SO-2", "role": "cover", "lead_days": 41},
            {"dn": "DN-PL", "posting_date": "2026-08-03", "customer": "波兰公司", "so": "SO-3", "role": "finished", "lead_days": 32},
            {"dn": "DN-UNKNOWN", "posting_date": "2026-08-04", "customer": "other", "so": "SO-4", "role": "cover", "lead_days": 19},
        ]
    )

    production, _head, report = build_route_evidence(dn, pd.DataFrame(), "2026-11-02")

    assert production == {
        ("USNJ", "cover"): [24.0],
        ("USTX", "cover"): [41.0],
        ("PL", "finished"): [32.0],
        ("unknown", "cover"): [19.0],
    }
    assert report["dn"]["older_than_6_months"] == 1
    assert report["dn"]["included"] == 4
    assert report["dn"]["small_sample_groups"] == 4
    assert "do not guarantee" in report["dn"]["groups"][("USNJ", "cover")]["sample_note"]


def test_zmt_full_route_uses_direct_date_pair_and_keeps_pools_separate():
    zmt = pd.DataFrame(
        [
            {"region": "美东", "wms_in_time": "2026-08-01", "dlvr": "2026-08-25", "transport": "FBA海运", "carrier": "COSCO", "way": "卡车派送", "seg1": 99, "seg2": 99, "seg3": 99},
            {"region": "美中", "wms_in_time": "2026-08-01", "dlvr": "2026-09-11", "transport": "海运", "carrier": "EVERGREEN", "way": "快递派送", "seg1": 99, "seg2": 99, "seg3": 99},
            {"region": "波兰", "wms_in_time": "2026-08-01", "dlvr": "2026-08-20", "transport": "空运", "carrier": "KOREAN AIR", "way": "快递", "seg1": 99, "seg2": 99, "seg3": 99},
            {"region": "FBA", "wms_in_time": "2026-08-01", "dlvr": "2026-08-10", "transport": "FBA海运", "carrier": "Matson", "way": "卡派", "dest": "FBA destination", "seg1": 99, "seg2": 99, "seg3": 99},
        ]
    )

    _production, head, report = build_route_evidence(pd.DataFrame(), zmt, "2026-11-02")

    assert head == {
        ("USNJ", "sea_regular", "truck"): [24.0],
        ("USTX", "sea_regular", "express"): [41.0],
        ("PL", "air", "express"): [19.0],
        ("unknown", "sea_fast", "truck"): [9.0],
    }
    assert report["head"]["included"] == 4
    assert report["head"]["scope"] == "physical_route_samples"
    assert report["head"]["delivery_purpose_counts"][("unknown", "sea_fast", "truck")]["mixed_delivery_purpose"] == 1
    assert report["head"]["ownership_claim"] is False
    assert "not guarantees" in report["head"]["sample_note"]


def test_incomplete_future_unknown_and_unclassified_route_rows_stay_out_of_known_groups():
    zmt = pd.DataFrame(
        [
            {"region": "美东", "wms_in_time": "2026-08-01", "dlvr": None, "transport": "快递/专线", "carrier": None, "way": "专线"},
            {"region": "美东", "wms_in_time": "2026-08-01", "dlvr": "2026-12-01", "transport": "快递/专线", "carrier": None, "way": "专线"},
            {"region": "美东", "wms_in_time": "2026-08-01", "dlvr": "2026-08-20", "transport": "快递/专线", "carrier": None, "way": "专线"},
        ]
    )

    _production, head, report = build_route_evidence(pd.DataFrame(), zmt, "2026-11-02")

    assert head == {("USNJ", "unknown", "unknown"): [19.0]}
    assert report["head"]["incomplete"] == 1
    assert report["head"]["future_delivery"] == 1
    assert report["head"]["unknown_main_haul"] == 1
    assert report["head"]["unknown_last_mile"] == 1


def test_dn_unknown_identity_negative_values_and_future_dates_are_counted_not_sampled():
    dn = pd.DataFrame(
        [
            {"dn": "DN-OK", "posting_date": "2026-08-01", "customer": "CENTRADE", "so": "SO-1", "role": "cover", "lead_days": 24},
            {"dn": "DN-NO-SO", "posting_date": "2026-08-02", "customer": "CENTRADE", "so": None, "role": "cover", "lead_days": 20},
            {"dn": "DN-NEG", "posting_date": "2026-08-03", "customer": "DANEEY", "so": "SO-2", "role": "cover", "lead_days": -3},
            {"dn": "DN-FUTURE", "posting_date": "2026-11-03", "customer": "波兰公司", "so": "SO-3", "role": "finished", "lead_days": 11},
        ]
    )

    production, _head, report = build_route_evidence(dn, pd.DataFrame(), "2026-11-02")

    assert production == {("USNJ", "cover"): [24.0]}
    assert report["dn"]["missing_so_identity"] == 1
    assert report["dn"]["invalid_negative_lead_days"] == 1
    assert report["dn"]["posting_after_as_of"] == 1
