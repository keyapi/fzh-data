# -*- coding: utf-8 -*-
"""P1 条件决策包用例：匹配分级、ABC 分档、服务水平分位、建议判定。"""

from __future__ import annotations

from datetime import date
from decimal import Decimal

import pandas as pd
import pytest

from supply_netting.pack import (abc_tiers, assumed_uom, _strip_suffix, _z,
                                 decision_pack, match_unmapped, service_level_scenarios)

KEY = ["canonical_sku", "canonical_warehouse", "canonical_uom"]


def sku_map(rows):
    frame = pd.DataFrame(rows, columns=["tongtool_sku", "item_codes"])
    frame["item_codes"] = frame["item_codes"].map(tuple)
    frame["n_items"] = frame["item_codes"].map(len)
    frame["mapping_status"] = "mapped"
    frame["mapping_evidence"] = "fixture"
    return frame


def unmapped(rows):
    return pd.DataFrame(rows, columns=["raw_sku", "quantity", "rows"])


def test_assumed_uom_default_and_kit():
    assert assumed_uom("TT0031245K0064088") == "个"
    assert assumed_uom("TJ#KS0001-SET") == "套"


def test_strip_suffix_candidates():
    assert "TT0031245K0064088" in _strip_suffix("TT0031245K0064088-Foam")
    assert "TT0031245K0064088" in _strip_suffix("TT0031245K0064088-0")
    assert _strip_suffix("YCSOFA001") == []


def test_r1_strips_suffix_and_hits_sku_map():
    sm = sku_map([("TT0031245K0064088-Foam", ("KS0394-CTTM-135x152x80-REDDISHGRAY",))])
    out = match_unmapped(unmapped([("TT0031245K0064088-Foam", 5, 1)]), sm)
    row = out.iloc[0]
    assert row["confidence"] == "high"
    assert row["candidates"] == "KS0394-CTTM-135x152x80-REDDISHGRAY"
    assert row["suggestion"] == "map"


def test_r1b_inherits_from_registered_variant():
    """任务里的实测例子：未登记基码靠已登记的 -Foam 兄弟命中同一物料。"""
    sm = sku_map([("TT0031245K0064088-Foam", ("KS0394-CTTM-135x152x80-REDDISHGRAY",)),
                  ("TT0031245K0064087", ("KS0394-CTTM-135x152x80-REDDISHGRAY",))])
    out = match_unmapped(unmapped([("TT0031245K0064088", 483, 12)]), sm)
    row = out.iloc[0]
    assert row["confidence"] == "high"
    assert row["match_method"] == "R1b_sibling_of_registered_variant"
    assert row["candidates"] == "KS0394-CTTM-135x152x80-REDDISHGRAY"


def test_sibling_conflict_is_low_confidence_not_bound():
    sm = sku_map([("TT0031245K0064088-Foam", ("KS0394-A",)),
                  ("TT0031245K0064088-Cover", ("KS0394-B",))])
    row = match_unmapped(unmapped([("TT0031245K0064088", 1, 1)]), sm).iloc[0]
    assert row["confidence"] == "low"
    assert row["suggestion"] == "manual"
    assert "KS0394-A" in row["candidates"] and "KS0394-B" in row["candidates"]


def test_r2_unique_model_is_medium_r3_family_is_low():
    one = sku_map([("TT0031245K0064086", ("KS0394-CTTM-CREAMYBEIGE",))])
    row = match_unmapped(unmapped([("TT0031245K9999999", 1, 1)]), one).iloc[0]
    assert row["match_method"] == "R2_model_unique" and row["confidence"] == "medium"
    assert row["suggestion"] == "map_after_confirm"

    many = sku_map([("TT0031245K0064086", ("KS0394-A",)),
                    ("TT0031245K0064087", ("KS0394-B",))])
    row = match_unmapped(unmapped([("TT0031245K9999999", 1, 1)]), many).iloc[0]
    assert row["match_method"] == "R3_model_family" and row["confidence"] == "low"


def test_unmatched_is_manual_not_hard_bound():
    row = match_unmapped(unmapped([("YCSOFA001", 248, 1)]), sku_map([])).iloc[0]
    assert row["confidence"] == "none" and row["suggestion"] == "manual_or_skip"
    assert row["candidates"] != row["candidates"] or row["candidates"] in ("", None) or pd.isna(row["candidates"])


def test_z_quantiles_match_known_values():
    assert _z(0.98) == pytest.approx(2.0537, abs=1e-3)
    assert _z(0.95) == pytest.approx(1.6449, abs=1e-3)
    assert _z(0.90) == pytest.approx(1.2816, abs=1e-3)


def test_abc_tiers_split_by_cumulative_share():
    demand = pd.DataFrame([
        dict(canonical_sku="A1", canonical_warehouse="W", canonical_uom="个", quantity=80.0),
        dict(canonical_sku="B1", canonical_warehouse="W", canonical_uom="个", quantity=15.0),
        dict(canonical_sku="C1", canonical_warehouse="W", canonical_uom="个", quantity=5.0),
    ])
    out = abc_tiers(demand).set_index("canonical_sku")
    assert out.loc["A1", "tier"] == "A" and out.loc["A1", "service_level"] == 0.98
    assert out.loc["B1", "tier"] == "B" and out.loc["B1", "service_level"] == 0.95
    assert out.loc["C1", "tier"] == "C" and out.loc["C1", "service_level"] == 0.90


def test_service_level_buffer_is_zero_without_variation():
    demand = pd.DataFrame([dict(canonical_sku="A1", canonical_warehouse="W",
                                canonical_uom="个", quantity=10.0)])
    history = pd.DataFrame([dict(canonical_sku="A1", canonical_warehouse="W",
                                 canonical_uom="个", demand_date=date(2026, 10, 1),
                                 quantity=1.0)])
    out = service_level_scenarios(history, demand)
    row = out.iloc[0]
    assert row["buffer_abc"] == 0.0
    assert "未含提前期" in row["note"]


def _netting(opening, gap, period, cond, status="conditional"):
    rows = []
    for bucket, period_qty, gap_qty in (("protect", period, gap), ("w1", 0, gap)):
        rows.append(dict(canonical_sku="S", canonical_warehouse="W", canonical_uom="个",
                         scenario="expected", bucket_id=bucket, opening=opening,
                         receipts=0.0, demand=period_qty, period_demand=period_qty,
                         carried_unserved=0.0, unserved=gap_qty, gap=gap_qty,
                         conditional_receipts=cond, status=status))
    return pd.DataFrame(rows)


def test_decision_pack_recommends_gap_observe_and_insufficient_data():
    scenarios = pd.DataFrame([dict(canonical_sku="S", canonical_warehouse="W",
                                   canonical_uom="个", tier="A", service_level=0.98, z=2.05,
                                   sigma_daily=0.0, buffer_abc=0.0, buffer_flat95=0.0)])
    facts = pd.DataFrame(columns=["canonical_sku", "canonical_warehouse", "canonical_uom",
                                 "source_layer", "qty"])
    gap_pack = decision_pack(_netting(0, 3, 3, 0), scenarios, facts)
    assert gap_pack.iloc[0]["recommendation"] == "补（缺口已证）"

    cond_pack = decision_pack(_netting(0, 3, 3, 50), scenarios, facts)
    assert cond_pack.iloc[0]["recommendation"] == "观察（有条件供给，需核实 ETA）"

    unknown_pack = decision_pack(_netting(None, 0, 0, 0, status="unknown"), scenarios, facts)
    assert unknown_pack.iloc[0]["recommendation"] == "数据不足"
