# -*- coding: utf-8 -*-
"""政策选项 v2 用例：数值不变、撤回推荐、hash 重锁、资格证据、与对账并列。"""

from __future__ import annotations

import json

import pandas as pd
import pytest

from supply_netting.policy_options_v2 import build

KEY = ["canonical_sku", "canonical_warehouse", "canonical_uom"]


def _inputs(tmp_path):
    # by_key：两单位 × 一个格子，足以复算三档
    rows = []
    cells = {(0.90, 1.0): (0.75, 0.76), (0.95, 1.5): (0.90, 0.90), (0.98, 2.0): (0.95, 0.95)}
    for uom, base_inv in (("个", 1000.0), ("套", 10.0)):
        for (level, mult), (fill, csl) in cells.items():
            rows.append(dict(lead_days=90, service_level=level, target_multiplier=mult,
                             SKU=f"{uom}-1", 仓库="W", 单位=uom, 窗口需求=100.0,
                             满足=100.0 * fill, 缺货量=100.0 * (1 - fill), 缺货天数=10,
                             平均库存=base_inv * mult, CSL=csl, 补货周期数=13))
    by_key = pd.DataFrame(rows)
    by_key_path = tmp_path / "by_key.csv"
    by_key.to_csv(by_key_path, index=False)

    v1 = tmp_path / "v1"
    v1.mkdir()
    pd.DataFrame([
        dict(单位="个", 选项="保守（控库存）", 服务档=0.90, 目标倍数=1.0, fill_rate=0.75,
             **{"CSL(需求加权)": 0.76}, 平均库存=1000.0, 相对同交期同单位1倍的增量=0.0,
             缺货量=25.0, 缺货天数=10, 涉及键数=1, 窗口需求=100.0, 适用假设="a",
             取舍说明="b", 推荐倾向="推荐", 状态="pending re-review", 口径="c", UOM备注=""),
        dict(单位="个", 选项="均衡（推荐倾向）", 服务档=0.95, 目标倍数=1.5, fill_rate=0.9,
             **{"CSL(需求加权)": 0.9}, 平均库存=1500.0, 相对同交期同单位1倍的增量=500.0,
             缺货量=10.0, 缺货天数=5, 涉及键数=1, 窗口需求=100.0, 适用假设="a",
             取舍说明="b", 推荐倾向="推荐", 状态="pending re-review", 口径="c", UOM备注=""),
        dict(单位="个", 选项="服务优先", 服务档=0.98, 目标倍数=2.0, fill_rate=0.95,
             **{"CSL(需求加权)": 0.95}, 平均库存=2000.0, 相对同交期同单位1倍的增量=1000.0,
             缺货量=5.0, 缺货天数=2, 涉及键数=1, 窗口需求=100.0, 适用假设="a",
             取舍说明="b", 推荐倾向="推荐", 状态="pending re-review", 口径="c", UOM备注=""),
    ]).to_csv(v1 / "policy_options.csv", index=False, encoding="utf-8-sig")
    (v1 / "manifest.json").write_text(json.dumps({"inputs": {"by_key_sha": "0a5c3eacfake"}}),
                                      encoding="utf-8")
    frontier = tmp_path / "frontier_manifest.json"
    frontier.write_text(json.dumps({"coverage": {
        "eligible_keys": 557, "zero_eval_sales_keys": 79,
        "reconciliation": "557 个合格键 − 79 个评估期零销量键 = 478 个实际回放键；"
                          "零销量键的库存成本未纳入任何合计"}}), encoding="utf-8")
    return v1, by_key_path, frontier


def run(tmp_path):
    v1, by_key, frontier = _inputs(tmp_path)
    out = tmp_path / "v2"
    return build(v1, by_key, out, frontier), out


def test_numbers_unchanged_from_v1(tmp_path):
    manifest, out = run(tmp_path)
    frame = pd.read_csv(out / "policy_options.csv")
    piece = frame[frame["单位"] == "个"].set_index("选项")
    assert piece.loc["保守（控库存）", "fill_rate"] == pytest.approx(0.75)
    assert piece.loc["均衡（参考档）", "平均库存"] == pytest.approx(1500.0)


def test_recommendation_withdrawn_and_kit_is_single_key_only(tmp_path):
    _, out = run(tmp_path)
    frame = pd.read_csv(out / "policy_options.csv")
    assert all("不推荐默认政策" in text for text in frame.loc[frame["单位"] == "个", "推荐倾向"])
    assert all("单键样本" in text for text in frame.loc[frame["单位"] == "套", "推荐倾向"])
    assert "（推荐倾向）" not in " ".join(frame["选项"])


def test_hash_mismatch_explained_and_relocked(tmp_path):
    manifest, out = run(tmp_path)
    block = manifest["inputs"]
    assert block["hash_mismatch"]["recorded"] == "0a5c3eacfake"
    assert block["hash_mismatch"]["explained"] is True
    assert block["by_key_sha"] != block["hash_mismatch"]["recorded"]
    frozen = block["by_key_sha_history"][1]["frozen_copy"]
    assert (out / "_inputs").exists() and frozen.endswith(".csv")


def test_evidence_discloses_zero_sales_and_eligibility(tmp_path):
    manifest, out = run(tmp_path)
    ev = manifest["evidence"]
    assert ev["replayed_keys"] == 2
    assert ev["eligible_keys"] == 557 and ev["zero_eval_sales_keys"] == 79
    assert ev["inventory_cost_excludes_zero_sales"] is True
    assert "包装费" in ev["packaging_fee_note"]
    assert "删失" in ev["censoring_note"]
    memo = (out / "memo.md").read_text(encoding="utf-8")
    assert "478 = 557 − 79" not in memo and "557 − 79" in memo or "557" in memo
    assert "撤回" in memo and "不是 95% 承诺" in memo


def test_reconcile_dimensions_present(tmp_path):
    manifest, _ = run(tmp_path)
    dims = {row["维度"] for row in manifest["reconcile_with_policy_reconcile"]}
    assert dims == {"预测误差", "库存基线", "母集"}
    assert manifest["status"] == "pending"
