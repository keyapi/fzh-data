# -*- coding: utf-8 -*-
"""多方案费率模型的单元测试（层级链、可信度、发布与预测）。"""
from __future__ import annotations

import sys
from pathlib import Path

import pandas as pd
import pytest

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))

from tongtool_order_cost.history_last_leg_analysis import (
    add_outlier_flags,
    build_package_observations,
    prepare_order_rows,
)
from tongtool_order_cost.model_variants import (
    MODERN_LEVELS,
    NON_US_LEVELS,
    US_SKU_FIRST,
    US_ZONE_FIRST,
    _credibility_weight,
    build_variant_tiers,
    estimate_credibility_k,
    level_chain_for,
    predict_with_variant,
)


def order_rows(rows: list[dict]) -> pd.DataFrame:
    defaults = {
        "发货日期": "2026-01-15",
        "通途SKU": "SKU-1",
        "发货数量": "1",
        "商品重量": "4500",
        "渠道": "AMAZON",
        "渠道账号": "AMZUS",
        "发货仓库": "CENTRADE",
        "包裹号": "P1",
        "邮寄方式": "VITE-Fedex>>FEDEX_GROUND-Centrade",
        "通途重量": "4800",
        "物流商重量": "0",
        "包裹总运费": "0",
        "跟踪号": "TRACK-1",
        "物流商单号": "",
        "订单号": "O1",
        "国家/地区": "US",
        "邮编": "90210-1234",
        "通途运费": "0",
        "物流商运费": "120",
    }
    return pd.DataFrame([{**defaults, **row} for row in rows])


def observe(rows: list[dict], month: str = "202601") -> pd.DataFrame:
    return add_outlier_flags(build_package_observations(prepare_order_rows(order_rows(rows), month)))


def grid(rows: list[dict]) -> pd.DataFrame:
    """构造跨两个月的观察，满足覆盖月份门槛。"""
    return add_outlier_flags(
        build_package_observations(
            pd.concat(
                [prepare_order_rows(order_rows(rows), "202601"),
                 prepare_order_rows(order_rows(rows), "202602")],
                ignore_index=True,
            )
        )
    )


def test_level_chain_depends_on_channel_and_nation():
    # 强分区渠道：分区档优先于 SKU 档
    assert level_chain_for("US", "M6180", "adaptive") == US_ZONE_FIRST
    assert level_chain_for("US", "US-FEDEX", "adaptive") == US_ZONE_FIRST
    # 平坦渠道：SKU 档优先
    assert level_chain_for("US", "VITE", "adaptive") == US_SKU_FIRST
    # 非美国走精简链，且必须包含「国家×重量」与仓库/渠道层
    assert level_chain_for("DE", "GLS-PL", "adaptive") == NON_US_LEVELS
    assert "L5b_国家重量" in NON_US_LEVELS
    assert {"L6_仓库渠道", "L7_仓库"} <= set(NON_US_LEVELS)
    # 显式 scheme 覆盖渠道自适应
    assert level_chain_for("US", "VITE", "zone_first") == US_ZONE_FIRST
    assert level_chain_for("US", "M6180", "sku_first") == US_SKU_FIRST


def test_credibility_weight_is_monotone_and_bounded():
    assert _credibility_weight(0, 100) == 0.0
    assert _credibility_weight(100, 100) == pytest.approx(0.5)
    assert _credibility_weight(1000, 100) == pytest.approx(1000 / 1100)
    weights = [_credibility_weight(n, 50) for n in (1, 10, 100, 1000)]
    assert weights == sorted(weights)
    assert all(0 <= w < 1 for w in weights)


def test_estimate_k_reflects_between_group_difference():
    # 组间差异明显 → k 有限，细层能保留自身经验
    distinct = grid(
        [
            {"包裹号": f"A{i}", "通途SKU": f"A{i}", "邮编": "07001",
             "物流商运费": str(50 + i % 3)}
            for i in range(40)
        ]
        + [
            {"包裹号": f"B{i}", "通途SKU": f"B{i}", "邮编": "94501",
             "物流商运费": str(200 + i % 3)}
            for i in range(40)
        ]
    )
    k_distinct = estimate_credibility_k(distinct, ["国家", "美国ZIP3"])
    # 组间无差异 → 返回极大 k（几乎完全池化）
    flat = grid(
        [{"包裹号": f"C{i}", "通途SKU": f"C{i}", "邮编": "07001", "物流商运费": "120"}
         for i in range(40)]
        + [{"包裹号": f"D{i}", "通途SKU": f"D{i}", "邮编": "94501", "物流商运费": "120"}
           for i in range(40)]
    )
    assert estimate_credibility_k(flat, ["国家", "美国ZIP3"]) > k_distinct


def test_nonexclusive_publishing_keeps_fine_and_coarse_rows():
    rows = [
        {"包裹号": f"P{i}", "通途SKU": f"SKU-{i % 2}", "邮编": "07001",
         "物流商运费": str(100 + i % 5)}
        for i in range(60)
    ]
    observations = grid(rows)
    inclusive, _ = build_variant_tiers(observations, min_samples=5, min_months=1, exclusive=False)
    exclusive, _ = build_variant_tiers(observations, min_samples=5, min_months=1, exclusive=True)
    assert len(inclusive) > len(exclusive)
    # 独立发布时，粗层（国家）必然存在
    assert "L8_国家" in set(inclusive["匹配层级"])
    # 排他阶梯会把细层吃光，粗层可能为空
    assert (exclusive["匹配层级"] == "L8_国家").sum() <= (inclusive["匹配层级"] == "L8_国家").sum()


def test_lower_threshold_publishes_more_layers():
    rows = [
        {"包裹号": f"P{i}", "通途SKU": f"SKU-{i % 7}", "邮编": f"0700{i % 9}",
         "物流商运费": str(90 + i % 11)}
        for i in range(60)
    ]
    observations = grid(rows)
    high, _ = build_variant_tiers(observations, min_samples=30, min_months=2, exclusive=False)
    low, _ = build_variant_tiers(observations, min_samples=5, min_months=1, exclusive=False)
    assert len(low) > len(high)


def test_credibility_blend_pulls_thin_cells_toward_parent():
    rows = [
        # 主体：同一层大量样本，中位数 120
        {"包裹号": f"M{i}", "通途SKU": "SKU-MAIN", "邮编": "07001", "物流商运费": "120"}
        for i in range(120)
    ] + [
        # 细层：仅 3 个样本、值 400，应被拉向父层
        {"包裹号": f"T{i}", "通途SKU": "SKU-THIN", "邮编": "94501", "物流商运费": "400"}
        for i in range(3)
    ]
    observations = grid(rows)
    blended, meta = build_variant_tiers(
        observations, min_samples=3, min_months=1, exclusive=False, credibility=True
    )
    assert meta  # 记录了每层的 k
    thin = blended[(blended["匹配层级"] == "L2_SKU_重量")
                   & (blended["通途SKU"] == "SKU-THIN")]
    assert len(thin) == 1
    assert thin.iloc[0]["可信度Z"] < 1
    assert thin.iloc[0]["中位数"] < 400  # 已被父层拉低
    assert thin.iloc[0]["可信度Z"] < 1


def test_predict_prefers_finest_published_level_then_returns_zero():
    rows = [
        {"包裹号": f"P{i}", "通途SKU": "SKU-A", "邮编": "07001", "物流商运费": "150"}
        for i in range(60)
    ]
    observations = grid(rows)
    tiers, _ = build_variant_tiers(observations, min_samples=5, min_months=1, exclusive=False)

    target = pd.DataFrame(
        [
            {"国家": "US", "标准仓库": "USNJ", "标准渠道": "VITE", "通途SKU": "SKU-A",
             "美国ZIP3": "070", "目的地邮编首位": "0", "观察重量阶梯": "(4,5]kg"},
            {"国家": "US", "标准仓库": "USNJ", "标准渠道": "VITE", "通途SKU": "SKU-UNKNOWN",
             "美国ZIP3": "999", "目的地邮编首位": "9", "观察重量阶梯": "(9,10]kg"},
            {"国家": "JP", "标准仓库": "XX", "标准渠道": "YY", "通途SKU": "SKU-A",
             "美国ZIP3": "", "目的地邮编首位": "", "观察重量阶梯": "(4,5]kg"},
        ]
    )
    prediction = predict_with_variant(target, tiers, scheme="zone_first")
    assert prediction.iloc[0] > 0          # 细层命中
    assert prediction.iloc[2] == 0         # 无任何候选 → 0，不静默编造
    assert set(MODERN_LEVELS[0][1]) >= {"国家", "通途SKU", "美国ZIP3", "观察重量阶梯"}
