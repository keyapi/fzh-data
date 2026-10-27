# -*- coding: utf-8 -*-
"""动作层 join 用例（r2 口径）：视界末 gap 重算动作、待核留空、层与分组、数量零改动。"""

from __future__ import annotations

import pandas as pd
import pytest

from supply_netting.decision_join import (ACTION_BUY, ACTION_NOT_COMPUTABLE, ACTION_NO_NEED,
                                          ACTION_PENDING, ACTION_REPLENISH, ACTION_SHIP,
                                          ACTION_VERIFY_ARRIVAL, HAS_EVIDENCE, NO_EVIDENCE,
                                          REPLENISH_ACTIONS, join_actions)

KEY = ["canonical_sku", "canonical_warehouse", "canonical_uom"]


def wide(rows):
    return pd.DataFrame(rows, columns=KEY + ["destination", "destination_reason", "opening",
                                             "opening_lower_bound", "qty_current", "gap_today",
                                             "protect_gap"])


def pack(rows):
    return pd.DataFrame(rows, columns=KEY + ["action", "action_confidence",
                                             "so_stage_produced_pending_dn",
                                             "so_stage_in_production", "so_stage_in_transit",
                                             "so_stage_not_planned",
                                             "so_stage_unknown_missing_start",
                                             "so_stage_unknown_other",
                                             "conditional_supply_qty", "w1_confidence",
                                             "protect_gap"])


def row(sku, dest, reason="", opening=0.0, lower=float("nan"), qty=None, gap_today=None,
        protect_gap=0.0):
    return (sku, "W", "个", dest, reason, opening, lower, qty, gap_today, protect_gap)


def pack_row(sku, action, produced=0.0, in_prod=0.0, transit=0.0, not_planned=0.0,
             missing_start=0.0, unknown_other=0.0, conditional=0.0, confidence="measured",
             protect_gap=0.0):
    return (sku, "W", "个", action, confidence, produced, in_prod, transit, not_planned,
            missing_start, unknown_other, conditional, confidence, protect_gap)


def test_pending_rows_have_empty_actions_and_group():
    frame, stats = join_actions(
        wide([row("S1", ACTION_PENDING, "预测键未过资格", qty=None)]), pack([]))
    out = frame.iloc[0]
    assert out["action_applicability"] == NO_EVIDENCE
    assert str(out["action"]) == "" and pd.isna(out["action_qty"])
    assert out["missing_evidence"] == "not_qualified"
    assert stats["unmatched"] == 1


def test_actions_are_recomputed_on_horizon_gap_not_protect_gap():
    """旧动作层按 7 天保护期判「不需补」，宽表视界末 gap=44 → 必须重算成阶段动作。"""
    frame, stats = join_actions(
        wide([row("S1", ACTION_REPLENISH, "模型化缺口 > 0", opening=1.0, qty=44.0,
                  gap_today=43.0, protect_gap=0.0)]),
        pack([pack_row("S1", ACTION_NO_NEED, transit=30.0, protect_gap=0.0)]),
    )
    out = frame.iloc[0]
    assert out["action"] == ACTION_VERIFY_ARRIVAL          # 不再是不需补
    assert out["action"] in REPLENISH_ACTIONS
    assert out["action_gap"] == 44.0
    assert out["action_gap_basis"] == "horizon_end"
    assert out["action_qty"] == 30.0 and out["residual_gap"] == 14.0
    assert stats["destination_action_conflicts"] == 0      # 终态无冲突
    assert stats["legacy_action_layer_mismatches"] == 1    # 旧动作层判无需补的差异已记账
    assert stats["replenish_action_values"] == [ACTION_VERIFY_ARRIVAL]


def test_replenish_actions_are_always_within_five_values():
    frame, stats = join_actions(
        wide([row("S1", ACTION_REPLENISH, "模型化缺口 > 0", qty=10.0),
              row("S2", ACTION_REPLENISH, "模型化缺口 > 0", qty=5.0),
              row("S3", ACTION_REPLENISH, "模型化缺口 > 0", qty=3.0)]),
        pack([pack_row("S1", "催发运", produced=20.0),
              pack_row("S2", "不需补（当前窗口）", in_prod=9.0),
              pack_row("S3", "不需补（当前窗口）")]),
    )
    replenish_actions = set(frame["action"])
    assert replenish_actions <= set(REPLENISH_ACTIONS)
    assert frame.set_index("canonical_sku").loc["S3", "action"] == ACTION_BUY
    assert stats["replenish_action_values"] == sorted({ACTION_SHIP, "催生产", ACTION_BUY})


def test_no_need_and_not_computable_follow_destination():
    frame, _ = join_actions(
        wide([row("S1", "无需补货", "期初覆盖已知需求", opening=5.0, qty=0.0),
              row("S2", ACTION_NOT_COMPUTABLE, "no_snapshot_basis", qty=None)]),
        pack([pack_row("S1", ACTION_BUY, produced=9.0), pack_row("S2", ACTION_BUY)]),
    )
    by_sku = frame.set_index("canonical_sku")
    assert by_sku.loc["S1", "action"] == ACTION_NO_NEED
    assert by_sku.loc["S2", "action"] == ACTION_NOT_COMPUTABLE
    assert by_sku.loc["S1", "action_applicability"] == HAS_EVIDENCE


def test_destination_and_quantities_are_untouched():
    source = wide([row("S1", ACTION_REPLENISH, "模型化缺口 > 0", opening=1.5,
                       qty=44.0, gap_today=43.028819, protect_gap=4.767287)])
    frame, _ = join_actions(source, pack([pack_row("S1", ACTION_SHIP, produced=140.0)]))
    for column in ["destination", "opening", "qty_current", "gap_today", "protect_gap"]:
        assert frame.iloc[0][column] == source.iloc[0][column]
    assert frame.iloc[0]["protect_gap_action_layer"] == 0.0   # pack 的保护期缺口只作附注


def test_missing_evidence_groups_split_stock_only_without_stock_basis():
    frame, stats = join_actions(
        wide([row("S1", ACTION_PENDING, "预测键未过资格且无库存基准", qty=None),
              row("S2", ACTION_PENDING, "预测键未过资格", qty=None),
              row("S3", ACTION_PENDING, "无预测覆盖（仅有库存，缺需求证据）", opening=5.0, qty=None),
              row("S4", ACTION_PENDING, "无预测覆盖（仅有库存，缺需求证据）",
                  opening=float("nan"), lower=float("nan"), qty=None)]),
        pack([]),
    )
    groups = frame.set_index("canonical_sku")["missing_evidence"].to_dict()
    assert groups["S1"] == "not_qualified_no_stock_basis"
    assert groups["S2"] == "not_qualified"
    assert groups["S3"] == "stock_only_no_demand"
    assert groups["S4"] == "no_forecast_no_stock"      # 无库存基准单独成组
    assert stats["missing_evidence_counts"]["no_forecast_no_stock"] == 1


def test_action_gap_falls_back_to_gap_today():
    frame, _ = join_actions(
        wide([row("S1", ACTION_REPLENISH, "模型化缺口 > 0", qty=None, gap_today=12.5)]),
        pack([pack_row("S1", ACTION_BUY)]))
    assert frame.iloc[0]["action_gap"] == 12.5


def test_pending_rows_keep_nan_not_zero():
    frame, _ = join_actions(
        wide([row("S3", ACTION_PENDING, "预测键未过资格且无库存基准", qty=None)]), pack([]))
    out = frame.iloc[0]
    assert pd.isna(out["action_qty"]) and pd.isna(out["residual_gap"])


def test_join_keeps_row_and_column_shape():
    source = wide([row("S1", ACTION_REPLENISH, "模型化缺口 > 0", qty=2.0),
                   row("S2", ACTION_PENDING, "预测键未过资格", qty=None)])
    frame, stats = join_actions(source, pack([pack_row("S1", ACTION_SHIP, produced=5.0)]))
    assert len(frame) == len(source)
    assert stats["match_rate"] == pytest.approx(0.5)
    assert list(frame.columns[:len(source.columns)]) == list(source.columns)


def test_duplicate_join_keys_in_pack_are_rejected():
    duplicate = pack([pack_row("S1", ACTION_BUY), pack_row("S1", ACTION_SHIP)])
    with pytest.raises(ValueError):
        join_actions(wide([row("S1", ACTION_REPLENISH, "模型化缺口 > 0", qty=1.0)]), duplicate)
