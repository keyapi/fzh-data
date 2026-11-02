import pytest
import pandas as pd

from supply_netting.replenishment_actions import (
    action_export_fields,
    bootstrap_independent_route,
    classify_cg_inventory,
    horizon_net_need,
    production_samples_for_pool_role,
    unknown_age_transit_days,
    route_candidates_for_pool,
    select_route_candidate,
    select_snapshot_date,
    split_actions,
)


def test_cg_credit_requires_explicit_eligibility_and_non_stale_source():
    records = [
        {"erp_item_code": "A", "cg_owner": "USNJ", "cg_available": 8,
         "cg_status": "cg_eligible", "cg_stale": 0},
        {"erp_item_code": "A", "cg_owner": "USNJ", "cg_available": 5,
         "cg_status": "cg_pending", "cg_stale": 0},
        {"erp_item_code": "B", "cg_owner": "USTX", "cg_available": 11,
         "cg_status": "cg_eligible", "cg_stale": 1},
    ]

    credit, unknown, diagnostics = classify_cg_inventory(records)

    assert credit == {("A", "USNJ"): 8.0}
    assert unknown[("A", "USNJ")]["unknown_qty"] == 5.0
    assert unknown[("B", "USTX")]["unknown_qty"] == 11.0
    assert [row["cg_available"] for row in diagnostics] == [8, 5, 11]


def test_cg_unknown_is_scoped_to_source_sku_owner_pair():
    credit, unknown, diagnostics = classify_cg_inventory([
        {"erp_item_code": "A", "cg_owner": "USNJ", "cg_available": 6,
         "cg_eligible": True, "stale": False},
    ])

    assert credit == {("A", "USNJ"): 6.0}
    assert set(unknown) == set()
    assert len(diagnostics) == 1
    assert ("UNRELATED", "USNJ") not in unknown


def test_explicit_false_cg_eligibility_overrides_status_and_future_source_is_unusable():
    row = {"erp_item_code": "A", "cg_owner": "USNJ", "cg_available": 6,
           "cg_eligible": False, "cg_status": "cg_eligible", "cg_stale": 0}

    credit, unknown, _ = classify_cg_inventory([row])
    assert credit == {}
    assert "cg_eligibility_conflict" in unknown[("A", "USNJ")]["reasons"]

    credit, unknown, _ = classify_cg_inventory([{
        "erp_item_code": "B", "cg_owner": "USTX", "cg_available": 9,
        "cg_eligible": True, "stale": False,
    }], source_usable=False)
    assert credit == {}
    assert unknown[("B", "USTX")]["unknown_qty"] == 9


def test_late_supply_and_new_order_are_independent_actions():
    result = split_actions(577.87, 55)

    assert result == {
        "expedite_qty": 55,
        "new_order_qty": 523,
        "remaining_need": pytest.approx(522.87),
        "actions": ["催已有", "新补"],
    }
    assert result["expedite_qty"] + result["remaining_need"] == pytest.approx(577.87)


@pytest.mark.parametrize("horizon_demand", [577.87, 812.4])
def test_horizon_gap_uses_total_quantile_without_lead_time_scaling(horizon_demand):
    assert horizon_net_need(horizon_demand, 0, 0) == pytest.approx(horizon_demand)


def test_unknown_horizon_demand_stays_unknown():
    assert horizon_net_need(float("nan"), 10, 0) is None


def test_final_export_observation_quantities_are_null_not_zero():
    export_rows = [
        action_export_fields(split_actions(5156, 0, blocked=True), "观察"),
        action_export_fields(split_actions(-4, 0), "不补"),
        action_export_fields(split_actions(9, 0), "补", new_order_qty=9),
    ]
    export = pd.DataFrame(export_rows).rename(columns={
        "action": "建议动作", "qty": "建议数量", "expedite_qty": "催已有量",
        "new_order_qty": "新补数量", "has_new_order_action": "新补行动",
    })

    assert export.loc[0, "建议动作"] == "观察"
    assert pd.isna(export.loc[0, "建议数量"])
    assert pd.isna(export.loc[0, "催已有量"])
    assert pd.isna(export.loc[0, "新补数量"])
    assert not bool(export.loc[0, "新补行动"])
    assert export.loc[1, "建议数量"] == 0
    assert export.loc[2, "建议数量"] == 9


def test_sufficient_late_supply_only_expedites():
    result = split_actions(20, 30)

    assert result["expedite_qty"] == 20
    assert result["new_order_qty"] == 0
    assert result["remaining_need"] == 0
    assert result["actions"] == ["催已有"]


def test_no_late_supply_only_places_new_order():
    result = split_actions(20.1, 0)

    assert result["expedite_qty"] == 0
    assert result["new_order_qty"] == 21
    assert result["remaining_need"] == pytest.approx(20.1)
    assert result["actions"] == ["新补"]


@pytest.mark.parametrize("unknown", [None, float("nan")])
def test_unknown_gap_blocks_executable_actions(unknown):
    result = split_actions(unknown, 55)

    assert result["expedite_qty"] is None
    assert result["new_order_qty"] is None
    assert result["remaining_need"] is None
    assert result["actions"] == ["观察"]


def test_blocked_gap_does_not_create_new_order():
    result = split_actions(12.2, 5, blocked=True)

    assert result["expedite_qty"] is None
    assert result["new_order_qty"] is None
    assert result["remaining_need"] == pytest.approx(12.2)
    assert result["actions"] == ["观察"]


def test_intransit_and_waiting_stock_use_head_only_without_production():
    assert unknown_age_transit_days("intr", production_days=22, full_transit_days=81) == 81
    assert unknown_age_transit_days("wait", production_days=22, full_transit_days=81) == 81


def test_po_unknown_stage_uses_head_only_without_production():
    assert unknown_age_transit_days("po", production_days=22, full_transit_days=81) == 81


def test_future_snapshot_is_not_selected_for_historical_as_of():
    assert select_snapshot_date(["2026-10-28", "2026-10-30"], "2026-10-28") == "2026-10-28"
    assert select_snapshot_date(["2026-10-30"], "2026-10-28") is None


def test_pool_without_known_route_does_not_invent_air_route():
    routes = {("PL", "unknown", "truck"): [35, 40]}

    assert route_candidates_for_pool(routes, "PL") == []


def test_same_named_route_uses_its_own_pool_samples():
    prod = {("USNJ", "KS/成品"): [10], ("PL", "KS/成品"): [10]}
    head = {("USNJ", "sea_regular", "truck"): [10],
            ("PL", "sea_regular", "truck"): [30]}

    us = bootstrap_independent_route(prod[("USNJ", "KS/成品")],
                                     head[("USNJ", "sea_regular", "truck")], n=100)
    pl = bootstrap_independent_route(prod[("PL", "KS/成品")],
                                     head[("PL", "sea_regular", "truck")], n=100)

    assert us["p50"] == pytest.approx(20)
    assert pl["p50"] == pytest.approx(40)


def test_missing_role_production_falls_back_only_within_pool():
    samples, source = production_samples_for_pool_role(
        {("PL", "KS/成品"): [9], ("PL", "PK#皮壳"): [17],
         ("USNJ", "KS/成品"): [90]}, "PL", "ND#组件")

    assert samples == [9, 17]
    assert source == "pool_all_roles_fallback"


def test_pool_fallback_prefers_dn_so_final_samples_without_role_duplicates():
    samples, source = production_samples_for_pool_role(
        {("PL", "KS/成品"): [9, 13], ("PL", "PK#皮壳"): [17, 21],
         ("PL", "__all_roles__"): [13, 21]}, "PL", "ND#组件")

    assert samples == [13, 21]
    assert source == "pool_all_roles_fallback"


def test_route_priority_uses_regular_ocean_when_multiple_routes_fit():
    routes = [
        ("sea_regular", "truck", {"p90": 50}),
        ("sea_regular", "express", {"p90": 48}),
        ("air", "express", {"p90": 20}),
    ]

    chosen, fits = select_route_candidate(routes, need_days=60)

    assert chosen == routes[0]
    assert fits is True


def test_route_priority_uses_air_only_when_earlier_modes_are_late():
    routes = [
        ("sea_regular", "truck", {"p90": 70}),
        ("sea_regular", "express", {"p90": 65}),
        ("air", "express", {"p90": 20}),
    ]

    chosen, fits = select_route_candidate(routes, need_days=30)

    assert chosen == routes[2]
    assert fits is True


def test_all_late_routes_choose_fastest_and_remain_manual_review():
    routes = [("sea_regular", "truck", {"p90": 70}),
              ("air", "express", {"p90": 45})]

    chosen, fits = select_route_candidate(routes, need_days=30)

    assert chosen == routes[1]
    assert fits is False
