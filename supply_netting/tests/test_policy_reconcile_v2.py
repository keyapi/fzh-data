# -*- coding: utf-8 -*-
"""政策对账 v2 用例：四字段分开、撤回错误表述、τ99 口径、证据分列与哈希。"""

from __future__ import annotations

import json

import pandas as pd

from supply_netting.policy_reconcile_v2 import build


def run(tmp_path):
    policy = tmp_path / "policy.csv"
    pd.DataFrame([dict(单位="个", 选项="保守", fill_rate=0.75, 平均库存=100.0)]).to_csv(
        policy, index=False, encoding="utf-8-sig")
    annex = tmp_path / "annex.md"
    annex.write_text("annex", encoding="utf-8")
    digest = tmp_path / "digest.md"
    digest.write_text("digest", encoding="utf-8")
    out = tmp_path / "out"
    manifest = build(str(policy), str(out), annex_path=str(annex), digest_path=str(digest))
    return out, manifest


def test_f1_four_fields_are_separate(tmp_path):
    out, _ = run(tmp_path)
    metrics = pd.read_csv(out / "reconcile_metrics.csv")
    assert {"目标档位", "预测乘数", "库存比值", "目标倍数"} <= set(metrics.columns)
    # 2.4–4.6× 只能出现在库存比值列，不能出现在预测乘数列
    assert not metrics["预测乘数"].astype(str).str.contains("2.4–4.6").any()
    row = metrics[metrics["来源"].str.contains("路径①")].iloc[0]
    assert "2.4–4.6" in str(row["库存比值"]) and row["预测乘数"] == "—"
    # v2 行不产生预测乘数
    v2 = metrics[metrics["来源"].str.startswith("v2")]
    assert all("不产生" in str(x) or str(x) == "—" for x in v2["预测乘数"])


def test_f2_withdraws_perfect_error_free_claims(tmp_path):
    out, manifest = run(tmp_path)
    memo = (out / "memo.md").read_text(encoding="utf-8")
    for banned in ("预测完全正确", "无误差上限", "机制上限"):
        assert f"「{banned}」" not in memo or "不再说" in memo
        assert banned in manifest["withdrawn"] or banned not in memo
    assert "未接入模型误差链" in memo
    assert "另一套历史经验分位政策" in memo
    assert "机制上限" not in manifest["fixes"]["F2"]


def test_f3_tau99_cells_and_cost_range(tmp_path):
    out, _ = run(tmp_path)
    metrics = pd.read_csv(out / "reconcile_metrics.csv")
    row = metrics[metrics["来源"].str.contains("τ99")].iloc[0]
    assert "0.78–1.00" in row["实际服务"] and "5 格 ≥95%" in row["实际服务"]
    hard = metrics[metrics["来源"].str.contains("路径②")].iloc[0]
    assert "8.8–40" in hard["库存比值"] and "部分高成本格" in hard["库存比值"]


def test_f4_evidence_split_and_source_hashes(tmp_path):
    out, _ = run(tmp_path)
    evidence = pd.read_csv(out / "reconcile_evidence.csv")
    synth = evidence[evidence["证据族"].str.contains("合成")]
    real = evidence[evidence["证据族"].str.contains("真实数据")]
    assert int(synth["格数"].iloc[0]) == 18 and "否" in synth["是否有预测误差"].iloc[0]
    assert int(real["格数"].iloc[0]) == 6 and real["是否有预测误差"].iloc[0] == "是"
    hashes = json.loads((out / "source_hashes.json").read_text(encoding="utf-8"))
    assert len(hashes) >= 4
    assert all(len(info["sha256"]) == 64 for info in hashes.values())


def test_status_pending_and_no_withdrawn_conclusions(tmp_path):
    out, manifest = run(tmp_path)
    memo = (out / "memo.md").read_text(encoding="utf-8")
    assert manifest["status"] == "pending"
    assert "拐点" not in memo
    assert "压交期比加库存划算" not in memo
    assert "不是 95% 承诺" in memo
