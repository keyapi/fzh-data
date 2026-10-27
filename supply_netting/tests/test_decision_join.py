# -*- coding: utf-8 -*-
"""动作层 join 用例：待核留空、不可算/无需补货映射、数量与去向零改动、join 完整性。"""

from __future__ import annotations

import pandas as pd
import pytest

from supply_netting.decision_join import (ACTION_NOT_COMPUTABLE, ACTION_NO_NEED,
                                          ACTION_PENDING, ACTION_REPLENISH, CONFLICT_NOTE,
                                          HAS_EVIDENCE, NO_EVIDENCE, join_actions)

KEY = ["canonical_sku", "canonical_warehouse", "canonical_uom"]


def wide(rows):
    return pd.DataFrame(rows, columns=KEY + ["destination", "opening", "qty_current",
                                             "protect_gap"])


def pack(rows):
    return pd.DataFrame(rows, columns=KEY + ["action", "action_confidence", "action_qty",
                                             "residual_gap", "action_basis"])


def test_pending_rows_have_empty_actions_and_no_replenish():
    frame, stats = join_actions(
        wide([("S1", "W", "个", ACTION_PENDING, 0.0, 10.0, 3.0)]),
        pack([]),
    )
    row = frame.iloc[0]
    assert row["action"] == "" and row["action_applicability"] == NO_EVIDENCE
    assert row["action_confidence"] == "" and row["action_basis"] == ""
    assert "补单" not in str(row["action"])
    assert stats["unmatched"] == 1


def test_no_need_and_not_computable_are_mapped_from_destination():
    frame, _ = join_actions(
        wide([("S1", "W", "个", "无需补货", 5.0, 0.0, 0.0),
              ("S2", "W", "个", ACTION_NOT_COMPUTABLE, None, 0.0, None)]),
        pack([("S1", "W", "个", "补单", "measured", 9.0, 0.0, "旧动作"),
              ("S2", "W", "个", "补单", "unknown", None, None, "")]),
    )
    by_sku = frame.set_index("canonical_sku")
    assert by_sku.loc["S1", "action"] == ACTION_NO_NEED
    assert by_sku.loc["S2", "action"] == ACTION_NOT_COMPUTABLE
    assert by_sku.loc["S1", "action_applicability"] == HAS_EVIDENCE


def test_destination_and_quantities_are_untouched():
    source = wide([("S1", "W", "个", ACTION_REPLENISH, 1.5, 44.0, 4.767287)])
    frame, _ = join_actions(source,
                            pack([("S1", "W", "个", "催发运", "measured", 4.0, 0.767287, "证据")]))
    for column in ["destination", "opening", "qty_current", "protect_gap"]:
        assert frame.iloc[0][column] == source.iloc[0][column]
    assert frame.iloc[0]["action"] == "催发运"
    assert frame.iloc[0]["action_qty"] == 4.0


def test_suggested_replenish_always_has_action_and_conflict_is_flagged():
    frame, stats = join_actions(
        wide([("S1", "W", "个", ACTION_REPLENISH, 1.0, 5.0, 2.0),
              ("S2", "W", "个", ACTION_REPLENISH, 1.0, 6.0, 2.0)]),
        pack([("S1", "W", "个", "催生产", "measured", 2.0, 0.0, "在产 2"),
              ("S2", "W", "个", ACTION_NO_NEED, "measured", 0.0, 0.0, "无缺口")]),
    )
    assert stats["suggested_with_action"] == 2
    assert stats["destination_action_conflicts"] == 1
    conflicted = frame.set_index("canonical_sku").loc["S2"]
    assert conflicted["action"] == ACTION_NO_NEED          # 不擅自改成补单
    assert CONFLICT_NOTE in conflicted["action_basis"]


def test_join_keeps_row_and_column_shape():
    source = wide([("S1", "W", "个", ACTION_REPLENISH, 1.0, 2.0, 1.0),
                   ("S2", "W", "个", ACTION_PENDING, 0.0, 0.0, 0.0)])
    frame, stats = join_actions(source, pack([("S1", "W", "个", "补单", "unknown", 0.0, 1.0, "")]))
    assert len(frame) == len(source)
    assert stats["match_rate"] == pytest.approx(0.5)
    assert list(frame.columns[:len(source.columns)]) == list(source.columns)


def test_duplicate_join_keys_in_pack_are_rejected():
    duplicate = pack([("S1", "W", "个", "补单", "unknown", 0.0, 1.0, ""),
                      ("S1", "W", "个", "催发运", "unknown", 0.0, 0.0, "")])
    with pytest.raises(ValueError):
        join_actions(wide([("S1", "W", "个", ACTION_REPLENISH, 0.0, 1.0, 1.0)]), duplicate)


def test_missing_evidence_groups_follow_destination_reason():
    frame, stats = join_actions(
        pd.DataFrame([
            dict(canonical_sku="S1", canonical_warehouse="W", canonical_uom="个",
                 destination=ACTION_PENDING, destination_reason="预测键未过资格",
                 opening=0.0, qty_current=0.0, protect_gap=0.0),
            dict(canonical_sku="S2", canonical_warehouse="W", canonical_uom="个",
                 destination=ACTION_PENDING,
                 destination_reason="无预测覆盖（仅有库存，缺需求证据）",
                 opening=3.0, qty_current=0.0, protect_gap=0.0),
        ]),
        pack([]),
    )
    groups = frame.set_index("canonical_sku")["missing_evidence"].to_dict()
    assert groups == {"S1": "not_qualified", "S2": "stock_only_no_demand"}
    counts = stats["missing_evidence_counts"]
    assert counts["not_qualified"] == 1 and counts["stock_only_no_demand"] == 1
    # 四个分组始终出现（含 0），避免下游漏看某一类缺证
    assert set(counts) == {"not_qualified_no_stock_basis", "not_qualified",
                           "stock_only_no_demand", "no_forecast_no_stock"}
    # 原 reason 列不被改写
    assert frame.loc[frame.canonical_sku == "S1", "destination_reason"].iloc[0] == "预测键未过资格"


def test_pending_rows_keep_nan_not_zero():
    frame, _ = join_actions(
        pd.DataFrame([dict(canonical_sku="S3", canonical_warehouse="W", canonical_uom="个",
                           destination=ACTION_PENDING, destination_reason="预测键未过资格且无库存基准",
                           opening=0.0, qty_current=0.0, protect_gap=0.0)]),
        pack([]),
    )
    row = frame.iloc[0]
    assert pd.isna(row["action_qty"]) and pd.isna(row["residual_gap"])
    assert str(row["action"]) == ""
