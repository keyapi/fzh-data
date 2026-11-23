# -*- coding: utf-8 -*-
"""Codex 复核 G1–G4 的针对性用例：scope 过滤 / 首工序 confidence / 部分覆盖 /
层拆分 / 已逾期日期 / 春节 applicability / 时效未证。"""

from __future__ import annotations

from datetime import date

import pandas as pd
import pytest

from supply_netting.pack import build_layers
from supply_netting.so_backlog import (build_so_backlog, spring_festival_status)
from supply_netting.w1_stages import (ACTION_PRODUCE, ACTION_SHIP, SUFFIX_BUY_REST,
                                      apply_actions, map_stage_keys)


def stages(rows, branch="美中-FZH-DANEEY"):
    frame = pd.DataFrame(rows, columns=["so", "so_line_id", "item_code", "warehouse", "uom",
                                        "stage", "qty", "source_record", "qty_status",
                                        "qty_basis", "scope", "exclusion_reason"])
    frame["qty"] = pd.to_numeric(frame["qty"], errors="coerce")
    return map_stage_keys(frame, {so: branch for so in frame["so"].unique()})


def pack_row(**extra):
    base = dict(canonical_sku="KS1", canonical_warehouse="美中-FZH-DANEEY",
                canonical_uom="个", protect_gap=10.0, po_qty=0.0, intransit_qty=0.0,
                opening=0.0, proven_receipts=0.0, period_demand=5.0)
    base.update(extra)
    return pd.DataFrame([base])


# ── G1 ──────────────────────────────────────────────────────────────────

def test_external_fba_rows_are_not_counted_but_listed():
    frame = stages([
        ("SO1", "L1", "KS1", "成品仓 - FZH", "个", "produced_pending_dn", 50, "WO-1",
         "known", "", "external_fba", ""),
        ("SO1", "L2", "KS1", "成品仓 - FZH", "个", "in_production", 2, "WO-2",
         "known", "", "in_house", ""),
    ])
    row = apply_actions(pack_row(protect_gap=2.0), frame).iloc[0]
    assert row["so_stage_produced_pending_dn"] == 0.0          # FBA 不算自发货可覆盖
    assert row["so_stage_fba_produced_pending_dn"] == 50.0     # 单列
    assert row["action"] == ACTION_PRODUCE
    assert "FBA 单列 50" in row["action_basis"]


def test_first_op_basis_is_estimated_not_measured():
    frame = stages([
        ("SO2", "L3", "KS1", "半成品仓 - FZH", "个", "produced_pending_dn", 20, "WO-3",
         "known", "job_card_first_op", "in_house", ""),
    ])
    row = apply_actions(pack_row(), frame).iloc[0]
    assert row["action"] == ACTION_SHIP
    assert row["action_confidence"] == "estimated"
    assert "首工序" in row["action_basis"]


# ── G3 ──────────────────────────────────────────────────────────────────

def test_partial_coverage_splits_action_and_residual_gap():
    frame = stages([
        ("SO3", "L4", "KS1", "半成品仓 - FZH", "个", "produced_pending_dn", 4, "WO-4",
         "known", "", "in_house", ""),
    ])
    row = apply_actions(pack_row(protect_gap=10.0), frame).iloc[0]
    assert row["action"] == ACTION_SHIP + SUFFIX_BUY_REST
    assert row["action_qty"] == 4.0
    assert row["residual_gap"] == 6.0


def test_full_coverage_leaves_no_residual_and_flags_timeliness():
    frame = stages([
        ("SO4", "L5", "KS1", "成品仓 - FZH", "个", "shipped_in_transit", 30, "DN-4",
         "known", "", "in_house", ""),
    ])
    row = apply_actions(pack_row(protect_gap=3.0), frame).iloc[0]
    assert row["residual_gap"] == 0.0
    assert row["action_qty"] == 3.0
    assert row["timely_coverage_flag"] == "timely_coverage_unproven"


def test_coverage_beats_stage_order():
    """在产能全覆盖、完工只覆盖一半 → 按“能否覆盖”选在产。"""
    frame = stages([
        ("SO5", "L6", "KS1", "半成品仓 - FZH", "个", "produced_pending_dn", 4, "WO-5",
         "known", "", "in_house", ""),
        ("SO5", "L7", "KS1", "半成品仓 - FZH", "个", "in_production", 40, "WO-6",
         "known", "", "in_house", ""),
    ])
    row = apply_actions(pack_row(protect_gap=10.0), frame).iloc[0]
    assert row["action"] == ACTION_PRODUCE
    assert row["residual_gap"] == 0.0


def test_cancel_or_defer_suggestion_when_stock_far_exceeds_demand():
    # 绝对量启发式：(opening+proven) - 2*demand >= 500 才提示
    hit = apply_actions(pack_row(protect_gap=0.0, opening=600.0, period_demand=5.0)
                        .assign(proven_receipts=0.0), stages([])).iloc[0]
    assert "推迟" in hit["cancel_or_defer_suggestion"]
    quiet = apply_actions(pack_row(protect_gap=0.0, opening=100.0, period_demand=5.0)
                          .assign(proven_receipts=0.0), stages([])).iloc[0]
    assert quiet["cancel_or_defer_suggestion"] == ""


# ── G2 ──────────────────────────────────────────────────────────────────

def test_layers_split_spot_and_transit_with_only_spot_counted():
    pack = pd.DataFrame([dict(opening=100.0, intransit_qty=40.0, po_qty=7.0,
                              so_pipeline_qty=9.0)])
    layers = build_layers(pack, po_total=20.0, so_total=30.0).set_index("layer")
    assert layers.loc["1a_海外仓现货", "counted_as_available"] is True \
        or bool(layers.loc["1a_海外仓现货", "counted_as_available"]) is True
    assert bool(layers.loc["1b_海外仓在途", "counted_as_available"]) is False
    assert layers.loc["1b_海外仓在途", "conditional_total"] == 40.0
    assert sum(1 for value in layers["counted_as_available"] if value) == 1


def test_recommendation_scope_is_marked():
    from supply_netting.pack import decision_pack
    netting = pd.DataFrame([
        dict(canonical_sku="S", canonical_warehouse="W", canonical_uom="个", scenario="expected",
             bucket_id="protect", opening=1.0, receipts=0.0, demand=2.0, period_demand=2.0,
             carried_unserved=0.0, unserved=1.0, gap=1.0, conditional_receipts=0.0,
             status="conditional"),
    ])
    out = decision_pack(netting, pd.DataFrame(), pd.DataFrame())
    assert out.iloc[0]["recommendation_scope"] == "netting_only_pre_supply"
    assert "实际动作见 action" in out.iloc[0]["recommendation_note"]


# ── G4 ──────────────────────────────────────────────────────────────────

def test_overdue_delivery_has_no_estimated_date():
    frame = build_so_backlog(pd.DataFrame([
        dict(so="SO6", customer="DANEEY", delivery_date="2026-09-01", item_code="KS1",
             customer_item_code="TT1", warehouse="成品仓 - FZH", open_qty=5.0)],
        columns=["so", "customer", "delivery_date", "item_code", "customer_item_code",
                 "warehouse", "open_qty"]), as_of=date(2026, 10, 27))
    row = frame.iloc[0]
    assert row["estimated_branch_date"] is None
    assert row["date_confidence"] == "unknown"
    assert row["plan_based_branch_date"] is not None            # 只作对照保留


@pytest.mark.parametrize("delivery,expected", [
    ("2026-09-01", "not_applicable"),     # 生产窗口 6-9 月，不跨春节
    ("2026-02-10", "applicable"),         # 生产窗口跨 1-2 月
    (None, "unknown"),
])
def test_spring_festival_applicability_by_production_window(delivery, expected):
    value = date.fromisoformat(delivery) if delivery else None
    status, buffer_days = spring_festival_status(value)
    assert status == expected
    assert buffer_days == (60 if expected == "applicable" else 0)
