# -*- coding: utf-8 -*-
"""历史尾程费用只读分析测试。"""
from __future__ import annotations

import sys
from pathlib import Path

import pandas as pd
import pytest

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))

from tongtool_order_cost.history_last_leg_analysis import (
    add_outlier_flags,
    analyze_history_last_leg,
    build_group_statistics,
    build_monthly_regime,
    build_package_observations,
    build_publishable_tiers,
    compare_holdout_precedence,
    normalize_channel,
    normalize_mail_method,
    normalize_postal,
    normalize_warehouse,
    prepare_order_rows,
)


from tongtool_order_cost.history_last_leg_export import (
    LEVEL_NAMES,
    build_import_rows,
    build_model_key,
    parse_weight_tier,
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
        "包裹总运费": "120",
        "跟踪号": "TRACK-1",
        "物流商单号": "",
        "订单号": "O1",
        "国家/地区": "US",
        "邮编": "90210-1234",
        "通途运费": "110",
        "物流商运费": "0",
    }
    return pd.DataFrame([{**defaults, **row} for row in rows])


def test_channel_separates_distinct_fedex_price_books():
    # 三个 FedEx 供应商是不同价目，不能按 carrier=FEDEX 合并
    assert normalize_channel("VITE-Fedex", "FEDEX_GROUND-Centrade") == "VITE"
    assert normalize_channel("US-FedEx", "US-FedEx") == "US-FEDEX"
    assert normalize_channel("M6180蜴国际", "M6180蜴国际-Fedex") == "M6180"
    assert normalize_channel("Overstock", "OSTK") == "OSTK"
    assert normalize_channel("Wayfair-CastleGate", "WFCG-FedEx") == "WFCG"
    assert normalize_channel("GLS-Poland", "GLS-Poland") == "GLS-PL"
    assert normalize_channel("星链海外仓", "星链渠道") == "星链"
    assert normalize_channel("云仓直发", "第三方云仓直发") == "云仓直发"


def test_monthly_regime_flags_flat_rate_month():
    flat = order_rows(
        [{"包裹号": f"F{i}", "邮编": f"{i:05d}", "包裹总运费": "126", "物流商运费": "0"} for i in range(1, 25)]
    )
    varied = order_rows(
        [{"包裹号": f"V{i}", "邮编": f"{i:05d}", "包裹总运费": str(80 + 4 * i), "物流商运费": "0"} for i in range(1, 25)]
    )
    report = analyze_history_last_leg([("202603", flat), ("202606", varied)])
    regime = report.monthly_regime
    assert regime.set_index("月份").loc["202603", "费率形态"] == "平坦（疑似整月一价）"
    assert regime.set_index("月份").loc["202606", "费率形态"] == "正常"


def test_zone_gradient_detects_zoned_and_flat_channels():
    # 目的地邮编首位 0..9，中位费随分区单调上升 → 分区显著
    zoned = order_rows(
        [
            {"包裹号": f"Z{i}{j}", "邮编": f"{i}{j:02d}00", "包裹总运费": str(100 + 4 * i), "物流商运费": "0"}
            for i in range(10)
            for j in range(40)
        ]
    )
    # 同一目的地邮编分布但费率恒定 → 近乎不分区
    flat = order_rows(
        [
            {"包裹号": f"F{i}{j}", "邮编": f"{i}{j:02d}00", "包裹总运费": "120", "物流商运费": "0"}
            for i in range(10)
            for j in range(40)
        ]
    )
    from tongtool_order_cost.history_last_leg_analysis import build_zone_gradient

    zoned_obs = build_package_observations(prepare_order_rows(zoned, "202601"))
    flat_obs = build_package_observations(prepare_order_rows(flat, "202601"))
    assert build_zone_gradient(zoned_obs).loc[0, "分区结论"] == "分区显著"
    assert build_zone_gradient(flat_obs).loc[0, "分区结论"] == "近乎不分区"


def test_publishable_tiers_merge_to_coarser_level_when_thin():
    from tongtool_order_cost.history_last_leg_analysis import build_publishable_tiers

    # 单个 ZIP3 只有 3 个样本，达不到阈值 → 无法发布任何层
    thin = order_rows(
        [{"包裹号": f"P{i}", "邮编": f"0700{i}", "包裹总运费": str(110 + i), "物流商运费": "0"} for i in range(3)]
    )
    obs = add_outlier_flags(build_package_observations(prepare_order_rows(thin, "202601")))
    assert build_publishable_tiers(obs, min_samples=30, min_months=1).empty

    # 60 个包裹、60 个不同 SKU，但同一 ZIP3 与同一重量层：
    # SKU 层各自仅 1 样本 → 必须跳过 L1/L2，在 L3（分区×重量）发布
    merged = order_rows(
        [
            {
                "包裹号": f"P{i}",
                "通途SKU": f"SKU-{i}",
                "邮编": "07001",
                "包裹总运费": str(110 + i % 5),
                "物流商运费": "0",
            }
            for i in range(60)
        ]
    )
    obs_merged = add_outlier_flags(build_package_observations(prepare_order_rows(merged, "202601")))
    published = build_publishable_tiers(obs_merged, min_samples=30, min_months=1)
    assert set(published["匹配层级"]) == {"L3_分区_重量"}
    assert int(published["样本数"].sum()) == 60


def test_legacy_matcher_reproduces_unit_defect():
    """线上兜底把千克有效重量与克字段比较 → 恒定命中该国最小非零重量记录。"""
    from tongtool_order_cost.history_last_leg_analysis import legacy_predict_fee_faithful

    legacy = pd.DataFrame(
        [
            {"sku": "TT-A", "nation": "US", "w": 3750.0, "cost": 146.73},
            {"sku": "TT-B", "nation": "US", "w": 50.0, "cost": 0.26},
            {"sku": "TT-C", "nation": "DE", "w": 4930.0, "cost": 108.14},
        ]
    )
    # 精确匹配命中
    assert legacy_predict_fee_faithful(legacy, "US", "TT-A", 3.75) == (146.73, "精确SKU+国家")
    # 非精确匹配：无论重量多少都返回 0.26
    for weight in (1.0, 4.8, 12.5, 25.0):
        assert legacy_predict_fee_faithful(legacy, "US", "TT-Z", weight) == (0.26, "重量兜底")
    assert legacy_predict_fee_faithful(legacy, "DE", "TT-Z", 4.9) == (108.14, "重量兜底")


def test_backtest_reports_both_models_and_keeps_coverage():
    from tongtool_order_cost.history_last_leg_analysis import backtest_against_legacy

    rows = prepare_order_rows(
        order_rows(
            [
                {
                    "包裹号": f"P{i}",
                    "通途SKU": f"TT-{i:03d}",
                    "邮编": f"{i:05d}",
                    "包裹总运费": "120",
                    "物流商运费": "0",
                }
                for i in range(40)
            ]
        ),
        "202601",
    )
    observations = add_outlier_flags(build_package_observations(rows))
    legacy = pd.DataFrame([{"sku": "TT-000", "nation": "US", "w": 50.0, "cost": 0.26}])
    publishable = build_publishable_tiers(observations, min_samples=30, min_months=1)
    by_market, overall = backtest_against_legacy(observations, legacy, publishable)
    assert len(overall) == 1
    row = overall.iloc[0]
    assert row["包裹数"] == 40
    assert row["旧模型_有预测"] == 40
    assert row["旧模型_精确匹配"] == 1
    assert row["旧模型_MdAE"] > 100  # 兜底 0.26 vs 实际 120
    assert row["新模型_MAE"] < 5
    assert "US" in set(by_market["国家"])


def test_holdout_precedence_uses_training_months_only_and_compares_variants():
    training = order_rows(
        [
            {
                "包裹号": f"TR-{sku}-{zip3}-{i}",
                "通途SKU": sku,
                "邮编": f"{zip3}01",
                "包裹总运费": str(fee),
                "物流商运费": "0",
            }
            for sku in ("SKU-A", "SKU-B")
            for zip3, fee in (("070", 80), ("945", 160))
            for i in range(20)
        ]
    )
    validation = order_rows(
        [
            {
                "包裹号": f"VA-{sku}-{zip3}-{i}",
                "通途SKU": sku,
                "邮编": f"{zip3}01",
                "包裹总运费": str(fee),
                "物流商运费": "0",
            }
            for sku in ("SKU-A", "SKU-B")
            for zip3, fee in (("070", 80), ("945", 160))
            for i in range(5)
        ]
    )
    observations = add_outlier_flags(
        build_package_observations(
            pd.concat(
                [
                    prepare_order_rows(training, "202604"),
                    prepare_order_rows(validation, "202605"),
                ],
                ignore_index=True,
            )
        )
    )
    legacy = pd.DataFrame([{"sku": "NO-HIT", "nation": "US", "w": 50.0, "cost": 0.26}])
    detail, summary = compare_holdout_precedence(
        observations,
        legacy,
        train_end_month="202604",
        validation_start_month="202605",
        min_samples=30,
        min_months=1,
    )
    assert set(detail["月份"]) == {"202605"}
    metrics = summary.set_index("方案")
    assert metrics.loc["分区优先", "MAE"] == pytest.approx(0)
    assert metrics.loc["SKU优先", "MAE"] == pytest.approx(40)
    assert metrics.loc["渠道自适应", "MAE"] == pytest.approx(40)  # VITE 分区弱，优先 SKU
    assert metrics.loc["HLF0001", "MAE"] > 100
    assert metrics.loc["分区优先", "训练截止月份"] == "202604"
    assert metrics.loc["分区优先", "验证起始月份"] == "202605"


def test_weight_tier_bounds_match_observed_semantics():
    from tongtool_order_cost.history_last_leg_analysis import observed_weight_tier

    lower, upper = parse_weight_tier(observed_weight_tier(4.0))
    assert (lower, upper) == (3.0, 4.0)
    # 下界开、上界闭：4.0 落在 (3,4]，3.0 不落在 (3,4]
    assert lower < 4.0 <= upper
    assert not (lower < 3.0 <= upper)
    assert parse_weight_tier("") == (0.0, 0.0)
    assert parse_weight_tier(None) == (0.0, 0.0)
    assert parse_weight_tier("坏值") == (0.0, 0.0)


def test_import_rows_use_kg_bounds_and_stable_model_keys():
    from tongtool_order_cost.model_variants import build_recommended_tiers

    rows = prepare_order_rows(
        order_rows(
            [
                {
                    "包裹号": f"P{i}",
                    "通途SKU": f"TT-{i:03d}",
                    "邮编": "07001",
                    "包裹总运费": "0",
                    "物流商运费": str(110 + i % 5),
                }
                for i in range(60)
            ]
        ),
        "202601",
    )
    observations = add_outlier_flags(build_package_observations(rows))
    publishable = build_recommended_tiers(observations, min_samples=5, min_months=1)
    import_rows = build_import_rows(publishable)

    assert list(import_rows.columns)[:3] == ["model_key", "match_level", "nation"]
    assert set(import_rows["match_level"]) <= set(LEVEL_NAMES)
    assert import_rows["model_key"].is_unique
    assert import_rows["avg_per_shipping_cost"].gt(0).all()
    # 带重量维度的层是 (4,5]kg；不带重量维度的粗层下上界都是 0
    bounds = set(zip(import_rows["weight_lower_kg"], import_rows["weight_upper_kg"]))
    assert bounds <= {(0.0, 0.0), (4.0, 5.0)}
    assert (4.0, 5.0) in bounds
    # 起运仓非空的层必须带起运邮编；国家层等粗层起运仓为空
    with_warehouse = import_rows[import_rows["origin_warehouse"] != ""]
    assert with_warehouse["origin_zip"].eq("07936").all()
    assert with_warehouse["origin_warehouse"].eq("USNJ").all()
    # 带 ZIP3 维度的层写 destination_zip3，带 ZIP1 维度的层写 destination_zip1
    zip3_rows = import_rows[import_rows["match_level"].str.contains("ZIP3")]
    zip1_rows = import_rows[import_rows["match_level"].str.contains("ZIP1")]
    assert zip3_rows["destination_zip3"].eq("070").all()
    assert zip3_rows["destination_zip1"].eq("").all()
    assert zip1_rows["destination_zip1"].eq("0").all()
    assert zip1_rows["destination_zip3"].eq("").all()
    assert import_rows["quality_status"].eq("Eligible").all()
    assert import_rows["sample_count"].sum() >= 60

    # 同一输入重复导出必须得到相同模型键，导入才能幂等
    again = build_import_rows(publishable)
    assert import_rows["model_key"].tolist() == again["model_key"].tolist()
    assert build_model_key(import_rows.iloc[0].to_dict()) == import_rows.loc[0, "model_key"]
    assert build_import_rows(pd.DataFrame()).empty


def test_export_level_names_match_analysis_levels():
    """导出契约的层级名必须与分析层完全一致，防止两处漂移。"""
    from tongtool_order_cost.model_variants import MODERN_LEVELS

    assert LEVEL_NAMES == tuple(name for name, _ in MODERN_LEVELS)


def test_import_rows_reject_unknown_level_name():
    publishable = pd.DataFrame(
        [
            {
                "匹配层级": "L9_不存在的层",
                "国家": "US",
                "标准仓库": "USNJ",
                "标准渠道": "VITE",
                "样本数": 40,
                "覆盖月份数": 3,
                "中位数": 120.0,
            },
        ]
    )
    with pytest.raises(ValueError, match="不认识的匹配层级"):
        build_import_rows(publishable)


def test_import_rows_reject_duplicate_model_keys():
    publishable = pd.DataFrame(
        [
            {
                "匹配层级": "L6_仓库渠道",
                "国家": "US",
                "标准仓库": "USNJ",
                "标准渠道": "VITE",
                "样本数": 40,
                "覆盖月份数": 3,
                "中位数": 120.0,
                "去异常中位数": 120.0,
                "置信等级": "高",
            },
            {
                "匹配层级": "L6_仓库渠道",
                "国家": "US",
                "标准仓库": "USNJ",
                "标准渠道": "VITE",
                "样本数": 40,
                "覆盖月份数": 3,
                "中位数": 121.0,
                "去异常中位数": 121.0,
                "置信等级": "高",
            },
        ]
    )
    with pytest.raises(ValueError, match="重复模型键"):
        build_import_rows(publishable)


def test_logistics_fee_outranks_ambiguous_package_total():
    """`物流商运费` 是实际回传扣款，优先级必须高于口径不稳的 `包裹总运费`。"""
    rows = prepare_order_rows(
        order_rows([{"包裹总运费": "52.88", "通途运费": "52.88", "物流商运费": "126.17"}]),
        "202605",
    )
    packages = build_package_observations(rows)
    assert packages.loc[0, "观察费用"] == pytest.approx(126.17)
    assert packages.loc[0, "费用来源"] == "物流商运费"

    # 三者都缺时才轮到通途运费
    rows = prepare_order_rows(
        order_rows([{"包裹总运费": "0", "通途运费": "52.88", "物流商运费": "0"}]),
        "202605",
    )
    assert build_package_observations(rows).loc[0, "费用来源"] == "通途运费"


def test_normalizers():
    assert normalize_warehouse("美东-CENTRADE-退货产品仓") == "USNJ"
    assert normalize_warehouse("FZH-DANEEY-皮壳仓库") == "USTX"
    assert normalize_warehouse("FZHPoland-covers") == "PL"
    assert normalize_postal("90210-1234", "US") == ("90210", "902", True)
    assert normalize_postal("ABC", "US") == ("ABC", "", False)
    assert normalize_mail_method("VITE-Fedex>>FEDEX_GROUND-Centrade") == (
        "VITE-Fedex",
        "FEDEX",
        "FEDEX_GROUND_CENTRADE",
    )


def test_prepare_rows_converts_grams_and_marks_exclusions():
    df = order_rows(
        [
            {},
            {"包裹号": "P2", "渠道": "OSTK"},
            {"包裹号": "P3", "渠道账号": "TTCozyDozyUS"},
            {"包裹号": "P4", "发货仓库": "US FBA"},
            {"包裹号": "P5", "发货仓库": "多渠道仓库"},
        ]
    )
    out = prepare_order_rows(df, "202601")
    assert out.loc[0, "观察重量_kg"] == pytest.approx(4.8)
    assert out.loc[0, "观察重量阶梯"] == "(4,5]kg"
    assert out.loc[0, "起点邮编"] == "07936"
    assert out["排除原因"].tolist() == [
        "",
        "平台承担尾程:渠道",
        "平台承担尾程:账号",
        "FBA仓",
        "多渠道仓库",
    ]


def test_package_fee_is_not_double_counted_for_multi_sku_package():
    rows = prepare_order_rows(
        order_rows(
            [
                {"通途SKU": "SKU-1", "包裹总运费": "120", "通途运费": "50"},
                {"通途SKU": "SKU-2", "包裹总运费": "120", "通途运费": "70"},
            ]
        ),
        "202601",
    )
    packages = build_package_observations(rows)
    assert len(packages) == 1
    assert packages.loc[0, "包裹总运费"] == pytest.approx(120)
    assert packages.loc[0, "通途运费"] == pytest.approx(120)
    assert packages.loc[0, "观察费用"] == pytest.approx(120)
    assert packages.loc[0, "费用来源"] == "包裹总运费"
    assert packages.loc[0, "SKU数"] == 2
    assert not packages.loc[0, "SKU精确层可用"]


def test_fee_falls_back_to_logistics_when_package_total_missing():
    rows = prepare_order_rows(
        order_rows([{"包裹总运费": "0", "通途运费": "0", "物流商运费": "109.91"}]),
        "202511",
    )
    packages = build_package_observations(rows)
    assert packages.loc[0, "观察费用"] == pytest.approx(109.91)
    assert packages.loc[0, "费用来源"] == "物流商运费"


def test_rounding_noise_in_package_fee_is_not_treated_as_conflict():
    rows = prepare_order_rows(
        order_rows(
            [
                {"通途SKU": "SKU-1", "包裹总运费": "187.14", "通途运费": "0", "物流商运费": "93.57"},
                {"通途SKU": "SKU-2", "包裹总运费": "187.15", "通途运费": "0", "物流商运费": "93.58"},
            ]
        ),
        "202511",
    )
    packages = build_package_observations(rows)
    assert len(packages) == 1
    assert packages.loc[0, "建模状态"] == "可建模"
    assert packages.loc[0, "观察费用"] == pytest.approx(187.15)
    assert packages.loc[0, "物流商运费"] == pytest.approx(187.15)


def test_conflicting_package_fee_beyond_tolerance_is_skipped():
    rows = prepare_order_rows(
        order_rows(
            [
                {"通途SKU": "SKU-1", "包裹总运费": "100", "物流商运费": "100"},
                {"通途SKU": "SKU-2", "包裹总运费": "150", "物流商运费": "150"},
            ]
        ),
        "202511",
    )
    packages = build_package_observations(rows)
    assert packages.loc[0, "跳过原因"] == "同包裹费用不一致"


def test_invalid_values_are_retained_with_skip_reasons():
    rows = prepare_order_rows(
        order_rows(
            [
                {"包裹号": "P1", "包裹总运费": "0", "物流商运费": "0", "通途运费": "0"},
                {"包裹号": "P2", "通途重量": "0"},
                {"包裹号": "P3", "邮编": "bad"},
            ]
        ),
        "202601",
    )
    packages = build_package_observations(rows)
    assert len(packages) == 3
    assert packages["跳过原因"].tolist() == ["无正数费用", "重量非正数", "美国邮编无效"]


def test_outliers_are_flagged_but_retained():
    rows = prepare_order_rows(
        order_rows(
            [
                {"包裹号": f"P{i}", "包裹总运费": str(fee)}
                for i, fee in enumerate([100, 101, 99, 100, 500], start=1)
            ]
        ),
        "202601",
    )
    observations = add_outlier_flags(build_package_observations(rows))
    assert len(observations) == 5
    assert int(observations["统计异常"].sum()) == 1
    assert observations.loc[observations["包裹总运费"] == 500, "异常原因"].iloc[0] == "组内IQR/MAD异常"


def test_analysis_reconciles_and_builds_statistics():
    jan = order_rows(
        [
            {"包裹号": "P1", "包裹总运费": "100"},
            {"包裹号": "P2", "包裹总运费": "120"},
            {"包裹号": "P3", "渠道": "Wayfair"},
        ]
    )
    feb = order_rows(
        [
            {"包裹号": "P1", "包裹总运费": "140"},
            {"包裹号": "P2", "包裹总运费": "0", "物流商运费": "0", "通途运费": "0"},
        ]
    )
    report = analyze_history_last_leg([("202601", jan), ("202602", feb)])
    assert report.reconciliation["对账差异"].eq(0).all()
    assert report.reconciliation["输入包裹数"].sum() == 5
    assert report.reconciliation["可建模包裹数"].sum() == 3
    assert report.reconciliation["跳过包裹数"].sum() == 2
    stats = build_group_statistics(report.observations, ["国家", "标准仓库"])
    assert stats.loc[0, "中位数"] == pytest.approx(120)
    assert stats.loc[0, "覆盖月份数"] == 2


def test_missing_required_column_is_explicit():
    with pytest.raises(ValueError, match="邮编"):
        prepare_order_rows(order_rows([{}]).drop(columns=["邮编"]), "202601")
