# -*- coding: utf-8 -*-
"""W1 阶段事实 → 动作列用例：判定顺序、跨单聚合、映射回退、无 W1 行。"""

from __future__ import annotations

import json

import pandas as pd

from supply_netting.w1_stages import (ACTION_BUY, ACTION_NO_NEED, ACTION_PRODUCE,
                                      ACTION_SHIP, ACTION_VERIFY_ARRIVAL,
                                      ACTION_VERIFY_ETA, ACTION_VERIFY_STAGE,
                                      ACTION_WORK_ORDER,
                                      aggregate_stages, apply_actions, load_w1_stages,
                                      map_stage_keys)

KEY = ["canonical_sku", "canonical_warehouse", "canonical_uom"]


def stage_rows(rows):
    frame = pd.DataFrame(rows, columns=["so", "so_line_id", "item_code", "warehouse",
                                        "uom", "stage", "qty", "source_record"])
    frame["qty"] = pd.to_numeric(frame["qty"], errors="coerce")
    return frame


def mapped(rows, branch="美中-FZH-DANEEY"):
    """把阶段行映射到分公司仓（等价于 pack 里 so → branch 的一步）。"""
    frame = stage_rows(rows)
    return map_stage_keys(frame, {so: branch for so in frame["so"].unique()})


def pack_row(**extra):
    base = dict(canonical_sku="KS1", canonical_warehouse="美中-FZH-DANEEY",
                canonical_uom="个", protect_gap=2.0, po_qty=0.0, intransit_qty=0.0)
    base.update(extra)
    return pd.DataFrame([base])


def test_action_order_prefers_earlier_stage_and_keeps_both_basis():
    stages = mapped([
        ("SO1", "L1", "PK#KS1", "半成品仓 - FZH", "个", "produced_pending_dn", 5, "WO-1"),
        ("SO1", "L1", "PK#KS1", "半成品仓 - FZH", "个", "shipped_in_transit", 3, "DN-1"),
    ])
    out = apply_actions(pack_row(), stages)
    row = out.iloc[0]
    assert row["action"] == ACTION_SHIP                     # 完工优先于在途
    assert "完工待发运 5" in row["action_basis"]
    assert "在途 3" in row["action_basis"]
    assert row["action_confidence"] == "measured"


def test_transit_action_is_verify_arrival_not_buy():
    stages = mapped([
        ("SO2", "L2", "KS1", "成品仓 - FZH", "个", "shipped_in_transit", 4, "DN-2"),
    ])
    row = apply_actions(pack_row(), stages).iloc[0]
    assert row["action"] == ACTION_VERIFY_ARRIVAL
    assert row["so_stage_in_transit"] == 4.0


def test_action_chain_produce_work_order_eta_buy():
    produce = apply_actions(pack_row(), mapped([
        ("SO3", "L3", "KS1", "半成品仓 - FZH", "个", "in_production", 6, "WO-3")])).iloc[0]
    assert produce["action"] == ACTION_PRODUCE

    work_order = apply_actions(pack_row(), mapped([
        ("SO4", "L4", "KS1", "半成品仓 - FZH", "个", "not_planned", 7, None)])).iloc[0]
    assert work_order["action"] == ACTION_WORK_ORDER
    assert work_order["wo_not_started_count"] == 1

    eta = apply_actions(pack_row(po_qty=9.0), stage_rows([])).iloc[0]
    assert eta["action"] == ACTION_VERIFY_ETA

    buy = apply_actions(pack_row(), stage_rows([])).iloc[0]
    assert buy["action"] == ACTION_BUY
    assert buy["action_confidence"] == "assumed"


def test_no_gap_is_no_need_regardless_of_stage():
    stages = mapped([("SO5", "L5", "KS1", "半成品仓 - FZH", "个", "in_production", 3, "WO-5")])
    row = apply_actions(pack_row(protect_gap=0.0), stages).iloc[0]
    assert row["action"] == ACTION_NO_NEED


def test_transit_and_conditional_marks_dedup_unproven():
    stages = mapped([("SO6", "L6", "KS1", "成品仓 - FZH", "个", "shipped_in_transit", 3, "DN-6")])
    row = apply_actions(pack_row(intransit_qty=8.0), stages).iloc[0]
    assert row["transit_dedup_status"] == "dedup_unproven"


def test_mapping_strips_cover_prefix_and_uses_branch_from_so():
    stages = stage_rows([("SO7", "L7", "PK#KS1", "半成品仓 - FZH", "个", "in_production", 2, "WO-7")])
    mapped = map_stage_keys(stages, {"SO7": "美中-FZH-DANEEY"})
    assert mapped.iloc[0]["canonical_sku"] == "KS1"
    assert mapped.iloc[0]["canonical_warehouse"] == "美中-FZH-DANEEY"
    assert bool(mapped.iloc[0]["conversion_assumed"]) is True

    # 未知 SO 不猜仓：canonical_warehouse 为空，聚合时被排除而不是塞进别的仓
    unmapped = map_stage_keys(stages, {})
    assert unmapped.iloc[0]["canonical_warehouse"] is None
    assert len(aggregate_stages(unmapped)) == 0


def test_aggregation_sums_across_orders_but_not_across_uom():
    stages = stage_rows([
        ("SO8", "L8", "KS1", "半成品仓 - FZH", "个", "in_production", 3, "WO-8"),
        ("SO9", "L9", "KS1", "半成品仓 - FZH", "个", "in_production", 4, "WO-9"),
        ("SO10", "L10", "KS1", "半成品仓 - FZH", "套", "in_production", 2, "WO-10"),
    ])
    mapped = map_stage_keys(stages, {"SO8": "美中-FZH-DANEEY", "SO9": "美中-FZH-DANEEY",
                                     "SO10": "美中-FZH-DANEEY"})
    agg = aggregate_stages(mapped)
    assert len(agg) == 2                                  # 个 / 套 分开
    piece = agg[agg["uom"] == "个"].iloc[0]
    assert piece["so_stage_in_production"] == 7.0
    assert piece["so_stage_so_count"] == 2                # 跨 2 张 SO
    assert piece["wo_in_process_count"] == 2


def test_load_w1_stages_reads_cached_jsonl(tmp_path):
    payload = dict(payload=dict(stage_balances=[
        dict(so="SO11", so_line_id="L11", item_code="KS1", warehouse="半成品仓 - FZH",
             uom="个", stage="not_planned", qty=3, qty_status="known", source_record=None)]))
    path = tmp_path / "w1.jsonl"
    path.write_text(json.dumps(payload, ensure_ascii=False), encoding="utf-8")
    frame = load_w1_stages(path)
    assert len(frame) == 1 and frame.iloc[0]["stage"] == "not_planned"
    assert len(load_w1_stages(tmp_path / "missing.jsonl")) == 0


def test_unknown_stage_is_verify_not_buy():
    stages = mapped([("SO12", "L12", "KS1", "成品仓 - FZH", "个", "unknown", 40, "WO-12")])
    row = apply_actions(pack_row(), stages).iloc[0]
    assert row["action"] == ACTION_VERIFY_STAGE
    assert "阶段未归类 40" in row["action_basis"]
    assert row["action_confidence"] == "measured"


def test_unknown_without_start_evidence_is_produce_action():
    frame = stage_rows([("SO13", "L13", "KS1", "半成品仓 - FZH", "个", "unknown", 120, "WO-13")])
    frame["exclusion_reason"] = "工单覆盖只能证明计划，缺开工证据，不判为在产"
    stages = map_stage_keys(frame, {"SO13": "美中-FZH-DANEEY"})
    row = apply_actions(pack_row(), stages).iloc[0]
    assert row["action"] == ACTION_PRODUCE
    assert row["so_stage_unknown_missing_start"] == 120.0


def test_conditional_uses_max_not_sum_to_avoid_double_count():
    stages = mapped([("SO14", "L14", "KS1", "成品仓 - FZH", "个", "delivered_sellable", 1, "DN-14")])
    row = apply_actions(pack_row(po_qty=143.0, intransit_qty=143.0), stages).iloc[0]
    # 同一批量在 PO 与在途各出现一次：basis 只能写 143，不能写 286
    assert "143" in row["action_basis"] and "286" not in row["action_basis"]
    assert row["action"] == ACTION_VERIFY_ETA


def test_other_branch_in_production_is_annotated_not_counted():
    stages = mapped([
        ("SO15", "L15", "KS1", "半成品仓 - FZH", "个", "not_planned", 5, None),
    ], branch="美中-FZH-DANEEY")
    other = mapped([("SO17", "L17", "KS1", "半成品仓 - FZH", "个", "in_production", 16, "WO-17")],
                   branch="美东-CENTRADE")
    combined = pd.concat([stages, other], ignore_index=True)
    row = apply_actions(pack_row(), combined).iloc[0]
    assert row["action"] == ACTION_WORK_ORDER        # 本仓未排产优先；别仓在产不算本仓
    assert row["so_stage_in_production"] == 0.0       # 只算本仓
    assert "别仓在产 16" in row["action_basis"]


def test_nan_conditional_does_not_leak_into_basis():
    import numpy as np
    stages = mapped([("SO18", "L18", "KS1", "成品仓 - FZH", "个", "in_production", 2, "WO-18")])
    row = apply_actions(pack_row(po_qty=np.nan, intransit_qty=np.nan), stages).iloc[0]
    assert "nan" not in row["action_basis"].lower()
    assert row["action"] == ACTION_PRODUCE
