# -*- coding: utf-8 -*-
"""SKU 分型政策用例：排除规则、角色×形态映射、皮壳不独立定档、交集链。"""

from __future__ import annotations

import pandas as pd

from supply_netting.sku_segment_policy import (COVER_POLICY, POLICY, build, load_classification,
                                               write_report)


def classification_csv(tmp_path):
    rows = [
        dict(sku="KS1", role="成品", cls="正常", total=100.0),
        dict(sku="KS2", role="成品", cls="慢销", total=20.0),
        dict(sku="KS3", role="成品", cls="短史/新品", total=5.0),
        dict(sku="PK1", role="皮壳", cls="正常", total=300.0),
        dict(sku="SEMI1", role="半成品", cls="长尾/间歇", total=10.0),
        dict(sku="497268621", role="", cls="正常", total=0.0),            # 无角色
        dict(sku="礼盒包装费-10in", role="成品", cls="正常", total=0.0),      # 包装费
        dict(sku="123456789", role="成品", cls="正常", total=0.0),         # 纯数字
    ]
    path = tmp_path / "cls.csv"
    pd.DataFrame(rows).to_csv(path, index=False)
    return path


def forecast_parquet(tmp_path):
    frame = pd.DataFrame([
        dict(tongtool_sku="KS1", canonical_sku="KS1", forecast_eligible=True),
        dict(tongtool_sku="PK1", canonical_sku="PK1", forecast_eligible=True),
        dict(tongtool_sku="KS3", canonical_sku="KS3", forecast_eligible=False),
        dict(tongtool_sku="OTHER", canonical_sku="OTHER", forecast_eligible=True),
    ])
    path = tmp_path / "forecast.parquet"
    frame.to_parquet(path, index=False)
    return path


def netting_parquet(tmp_path):
    frame = pd.DataFrame([dict(canonical_sku=s) for s in ("KS1", "PK1", "KS2", "OTHER")])
    path = tmp_path / "netting.parquet"
    frame.to_parquet(path, index=False)
    return path


def run(tmp_path):
    return build(classification_csv(tmp_path), forecast_parquet(tmp_path),
                 netting_parquet(tmp_path))


def test_excludes_fee_no_role_and_numeric_skus(tmp_path):
    classified, excluded = load_classification(classification_csv(tmp_path))
    assert set(classified["sku"]) == {"KS1", "KS2", "KS3", "PK1", "SEMI1"}
    assert len(excluded) == 3
    assert set(excluded["sku"]) == {"497268621", "礼盒包装费-10in", "123456789"}


def test_role_form_mapping_and_cover_rule(tmp_path):
    data = run(tmp_path)
    policy = data["classified"].set_index("sku")
    assert policy.loc["KS1", "服务档"] == "A" and policy.loc["KS1", "τ目标"] == 0.95
    assert policy.loc["KS2", "服务档"] == "B"
    assert policy.loc["KS3", "服务档"] == "观察" and pd.isna(policy.loc["KS3", "τ目标"])
    # 皮壳任何形态都不独立定档
    assert policy.loc["PK1", "服务档"] == COVER_POLICY[0] == "跟随成品/BOM"
    assert policy.loc["SEMI1", "服务档"] == "C"


def test_matrix_and_role_summary_are_complete(tmp_path):
    data = run(tmp_path)
    matrix = data["matrix"]
    assert set(matrix["role"]) == {"皮壳", "成品", "半成品"}
    assert matrix["SKU数"].sum() == len(data["classified"])
    assert abs(matrix["销量占比"].sum() - 100) < 0.5
    roles = data["role_summary"].set_index("role")
    assert roles.loc["皮壳", "主推服务档"] == "跟随成品/BOM"


def test_intersection_uses_forecast_mapping_and_netting(tmp_path):
    data = run(tmp_path)
    ctx = data["context"]
    # KS1、PK1 在预测+净额；KS3 预测不可评；KS2 不在预测表
    assert ctx["triple"] == 2
    assert ctx["matched_to_forecast"] == 3
    assert ctx["in_netting"] == 2


def test_report_states_no_commitment_and_uom(tmp_path):
    data = run(tmp_path)
    path = tmp_path / "report.md"
    write_report(path, data, "2026-10-28T00:00:00+08:00",
                 dict(classification="c.csv", classification_sha="x",
                      forecast="f.parquet", netting="n.parquet"))
    text = path.read_text(encoding="utf-8")
    assert "不是 95% 承诺" in text
    assert "UOM-CANONICAL" in text
    assert "不能按皮壳自身销量判死库存" in text
    assert "forecast_eligible ∩ netting_eligible" in text
