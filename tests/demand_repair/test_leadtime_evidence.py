import pandas as pd
import pytest

from supply_netting.leadtime_evidence import (
    completed_transit_days,
    production_leadtime_rows,
    summarize_leadtimes,
)


def test_completed_transit_uses_posting_to_warehouse_endpoints_not_max_of_segments():
    shipments = pd.DataFrame(
        [
            {
                "shipment": "SHIP-24",
                "posting_date": "2026-09-23",
                "depart": "2026-10-01",
                "arrive": "2026-01-10",
                "warehouse_in": "2026-10-17",
                "shipping_days": 99,
                "ocean_days": 15,
                "warehouse_days": 15,
            },
            {
                "shipment": "SHIP-62",
                "posting_date": "2026-08-04",
                "depart": "2026-08-25",
                "arrive": "2026-01-20",
                "warehouse_in": "2026-10-05",
                "shipping_days": 19,
                "ocean_days": 43,
                "warehouse_days": 43,
            },
        ]
    )

    result = completed_transit_days(shipments)

    assert result["duration_days"].tolist() == [24, 62]
    assert result["shipping_days"].tolist() == [8, 21]
    assert result["depart_to_warehouse_days"].tolist() == [16, 41]
    assert result["stage"].tolist() == ["posting_date->warehouse_in"] * 2
    assert result["complete_headhaul"].tolist() == [True, True]
    assert result["status"].tolist() == ["complete", "complete"]


def test_depart_start_is_explicitly_a_different_duration_stage():
    shipments = pd.DataFrame(
        [{"posting_date": "2026-09-23", "depart": "2026-10-01", "warehouse_in": "2026-10-17"}]
    )

    result = completed_transit_days(shipments, start_column="depart")

    assert result.loc[0, "duration_days"] == 16
    assert result.loc[0, "stage"] == "depart->warehouse_in"
    assert bool(result.loc[0, "complete_headhaul"]) is True


def test_missing_posting_date_does_not_fall_back_to_depart():
    shipments = pd.DataFrame(
        [{"posting_date": None, "depart": "2026-10-01", "warehouse_in": "2026-10-17"}]
    )

    result = completed_transit_days(shipments)

    assert pd.isna(result.loc[0, "duration_days"])
    assert bool(result.loc[0, "complete_headhaul"]) is False
    assert result.loc[0, "status"] == "incomplete"
    assert result.loc[0, "reason"] == "missing_posting_date"


def test_incomplete_shipping_only_record_is_not_a_completed_transit_observation():
    shipments = pd.DataFrame([{
        "shipment": "SHIP-OPEN", "posting_date": "2026-01-01", "depart": "2026-01-02",
        "arrive": "2026-01-20", "warehouse_in": None,
    }])

    result = completed_transit_days(shipments)

    assert pd.isna(result.loc[0, "duration_days"])
    assert result.loc[0, "status"] == "incomplete"
    assert result.loc[0, "reason"] == "missing_warehouse_in"


def test_missing_transit_endpoint_column_is_an_explicit_error():
    with pytest.raises(ValueError, match="missing required columns: posting_date"):
        completed_transit_days(pd.DataFrame([{"warehouse_in": "2026-01-10"}]))


def test_dn_so_role_rows_are_order_independent_and_keep_roles():
    records = pd.DataFrame(
        [
            {"dn": "DN-1", "so": "SO-1", "role": "finished", "lead_days": 24},
            {"dn": "DN-1", "so": "SO-1", "role": "cover", "lead_days": 24},
            {"dn": "DN-1", "so": "SO-1", "role": "cover", "lead_days": 24},
            {"dn": "DN-1", "so": "SO-1", "role": "cover", "lead_days": 62},
            {"dn": "DN-2", "so": "SO-1", "role": "cover", "lead_days": 62},
        ]
    )

    a = production_leadtime_rows(records)
    b = production_leadtime_rows(records.sample(frac=1, random_state=41))

    pd.testing.assert_frame_equal(a, b)
    assert set(a["role"]) == {"cover", "finished"}
    first_cover = a[(a["dn"] == "DN-1") & (a["role"] == "cover")].iloc[0]
    assert first_cover["lead_days_first"] == 24
    assert first_cover["lead_days_final"] == 62
    assert first_cover["n_records"] == 3


def test_summary_reports_distinct_dn_and_record_grains_and_small_sample_status():
    records = pd.DataFrame(
        [
            {"dn": "DN-1", "so": "SO-1", "role": "cover", "lead_days": 24, "destination": "USA"},
            {"dn": "DN-1", "so": "SO-2", "role": "cover", "lead_days": 62, "destination": "USA"},
        ]
    )

    result = summarize_leadtimes(records, ["destination"])

    usa = result.iloc[0]
    assert usa["n_unique_dn"] == 1
    assert usa["n_records"] == 2
    assert usa["p50"] == 43
    assert bool(usa["small_sample"]) is True
    assert "not a guarantee" in usa["sample_note"]


def test_destination_groups_keep_us_poland_and_unknown_separate():
    records = pd.DataFrame(
        [
            {"dn": "DN-US", "lead_days": 24, "destination": "USA"},
            {"dn": "DN-PL", "lead_days": 62, "destination": "Poland"},
            {"dn": "DN-UNK", "lead_days": 10, "destination": "unknown"},
        ]
    )

    result = summarize_leadtimes(records, ["destination"])

    assert result.set_index("destination")["p50"].to_dict() == {"Poland": 62.0, "USA": 24.0, "unknown": 10.0}


def test_production_rows_retain_unknown_and_invalid_lead_day_counts():
    records = pd.DataFrame(
        [
            {"dn": "DN-1", "so": "SO-1", "role": "cover", "lead_days": 24},
            {"dn": "DN-2", "so": "SO-1", "role": "cover", "lead_days": None},
            {"dn": "DN-3", "so": "SO-1", "role": "cover", "lead_days": "bad"},
        ]
    )

    result = production_leadtime_rows(records)

    assert len(result) == 3
    assert int(result["n_unknown_lead_days"].sum()) == 1
    assert int(result["n_invalid_lead_days"].sum()) == 1


def test_negative_lead_days_and_missing_so_identity_do_not_enter_statistics():
    records = pd.DataFrame(
        [
            {"dn": "DN-1", "so": "SO-1", "role": "cover", "lead_days": 24},
            {"dn": "DN-2", "so": "SO-1", "role": "cover", "lead_days": -3},
            {"dn": "DN-3", "so": None, "role": "cover", "lead_days": 15},
        ]
    )

    result = production_leadtime_rows(records)
    summary = summarize_leadtimes(result, ["role"])

    assert result.loc[result["dn"] == "DN-2", "lead_days"].isna().all()
    assert result.loc[result["dn"] == "DN-3", "lead_days"].isna().all()
    assert int(result["n_invalid_lead_days"].sum()) == 1
    assert int(result["n_identity_unknown_records"].sum()) == 1
    assert summary.loc[0, "n_records"] == 1
    assert summary.loc[0, "n_invalid"] == 1
    assert summary.loc[0, "p50"] == 24
