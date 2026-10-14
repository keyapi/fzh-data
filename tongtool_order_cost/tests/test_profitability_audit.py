# -*- coding: utf-8 -*-
"""U2：稳定行身份 / grain 视图 / 件数 / 数量对账 —— 纯函数，不联网。"""
from __future__ import annotations

import sys
from pathlib import Path

import pytest

_ROOT = Path(__file__).resolve().parents[1]
if str(_ROOT) not in sys.path:
    sys.path.insert(0, str(_ROOT))

from tongtool_order_cost import profitability_audit as P  # noqa: E402

HEADERS = ["订单号", "通途SKU", "平台SKU", "包裹号", "发货数量", "订单总售价", "订单总成本"]


def _rows(*rows):
    return P.build_source_rows(HEADERS, list(rows), "2026年7月订单")


def test_repeated_order_total_kept_once_in_order_view_but_visible_per_row():
    rows = _rows(
        ["A-1", "SKU-1", "", "P1", "1", "100", ""],
        ["A-1", "SKU-2", "", "P1", "1", "100", ""],
    )
    orders = P.order_grain(rows, sum_columns=["发货数量"], first_columns=["订单总售价"])
    assert len(orders) == 1
    g = orders[0]
    assert g.piece_count == 2
    assert g.sums["发货数量"] == 2.0
    # 订单级字段只取一次，不被重复相乘
    assert g.firsts["订单总售价"] == "100"
    assert g.row_numbers == (2, 3)
    # 每一行原始值仍可见
    assert [r.get("订单总售价") for r in rows] == ["100", "100"]


def test_duplicate_business_keys_get_deterministic_occurrence_index():
    rows = _rows(
        ["A-1", "SKU-1", "", "P1", "1", "", ""],
        ["A-1", "SKU-1", "", "P1", "1", "", ""],  # 完全相同的业务键
        ["A-1", "SKU-1", "", "P1", "1", "", ""],
    )
    assert [r.key.occurrence_index for r in rows] == [0, 1, 2]
    assert [r.key.ambiguous for r in rows] == [False, True, True]
    assert not rows[0].key.incomplete


def test_blank_sku_placeholder_retained_but_zero_pieces():
    rows = _rows(
        ["A-1", "C/Linen-DKBlue-100-660-WOW", "", "P1", "1", "", ""],
        ["A-1", "", "", "P1", "1", "", ""],  # 占位行
    )
    assert len(rows) == 2                      # 血缘里仍在
    assert rows[1].key.incomplete              # 标记为不完整
    orders = P.order_grain(rows)
    assert orders[0].piece_count == 1          # 不因占位行加件
    assert orders[0].piece_rule == "成品口径"


def test_split_package_child_counts_once_with_base_and_standalone():
    both = _rows(
        ["O-1", "TT0031217K0064032", "", "P1", "1", "", ""],
        ["O-1", "TT0031217K0064032-2", "", "P2", "1", "", ""],
    )
    assert P.order_grain(both)[0].piece_count == 1

    standalone = _rows(["O-2", "TT0031217K0064032-2", "", "P1", "1", "", ""])
    assert P.order_grain(standalone)[0].piece_count == 1


def test_filling_only_order_preserved_as_review_not_dropped():
    rows = _rows(
        ["O-3", "Curve-Foam", "", "P1", "3", "", ""],
        ["O-3", "Curve-PPCotton", "", "P1", "1", "", ""],
    )
    orders = P.order_grain(rows)
    assert len(orders) == 1
    assert orders[0].piece_rule == "只发部件·待复核"
    assert orders[0].piece_count == 3
    assert P.row_conservation(rows).closes


def test_row_conservation_accounts_for_every_row():
    rows = _rows(
        ["A-1", "SKU-1", "", "P1", "1", "", ""],   # matched
        ["", "SKU-2", "", "P1", "1", "", ""],       # unmatched（无订单号）
        ["A-2", "SKU-3", "", "P2", "1", "", ""],    # matched
        ["A-3", "SKU-4", "", "P3", "1", "", ""],    # excluded
        ["A-4", "SKU-5", "", "P4", "1", "", ""],    # failed
    )
    cons = P.row_conservation(
        rows,
        excluded_reason={4: "占位行"},
        failed_rows={6},
    )
    assert cons.input == 5
    assert cons.matched == 2
    assert cons.unmatched == 1
    assert cons.excluded == 1
    assert cons.failed == 1
    assert cons.reasons == {"占位行": 1}
    assert cons.closes
    assert cons.to_dict()["closes"] is True


def test_package_grain_collapses_repeated_package_fee():
    rows = _rows(
        ["A-1", "SKU-1", "", "P9", "1", "", "50"],   # 同一包裹级成本重复在两行
        ["A-1", "SKU-2", "", "P9", "1", "", "50"],
    )
    pkgs = P.package_grain(rows, sum_columns=["发货数量"], first_columns=["订单总成本"])
    assert len(pkgs) == 1
    assert pkgs[0].package_id == "P9"
    assert pkgs[0].firsts["订单总成本"] == "50"   # 只取一次，未翻倍
    assert pkgs[0].sums["发货数量"] == 2.0


def test_canonical_alias_report_maps_children_to_base():
    rows = _rows(
        ["BJRYECLTUS-113-8425888-9901842", "S1", "", "P1", "1", "", ""],
        ["BJRYECLTUS-113-8425888-9901842_1", "S1", "", "P2", "1", "", ""],
        ["BJRYECLTUS-113-8425888-9901842_2", "S1", "", "P3", "1", "", ""],
        ["OTHER-1", "S2", "", "P4", "1", "", ""],
    )
    rep = P.canonical_alias_report(rows)
    assert rep["unique_order_ids"] == 4
    assert rep["canonical_orders"] == 2
    assert rep["relationship_alias_orders"] == 2
    assert rep["multi_member_canonicals"][
        "BJRYECLTUS-113-8425888-9901842"
    ] == [
        "BJRYECLTUS-113-8425888-9901842",
        "BJRYECLTUS-113-8425888-9901842_1",
        "BJRYECLTUS-113-8425888-9901842_2",
    ]


def test_long_numeric_body_not_stripped():
    rows = _rows(["OS-474530280", "S1", "", "P1", "1", "", ""])
    assert rows[0].key.base_order_id == "OS-474530280"
    assert P.canonical_alias_report(rows)["canonical_orders"] == 1


def test_load_snapshot_csv_roundtrip(tmp_path):
    path = tmp_path / "x.csv"
    path.write_text("订单号,通途SKU\nA-1,SKU-1\n", encoding="utf-8-sig")
    headers, rows = P.load_snapshot_csv(path)
    assert headers == ["订单号", "通途SKU"]
    assert rows == [["A-1", "SKU-1"]]


def test_fba_summary_sheet_keyed_by_msku_not_order():
    headers = ["MSKU", "SKU", "站点", "销量", "销售额", "利润"]
    rows = [["M-1", "S-1", "AMZUS", "14", "6508.02", "2190.88"]]
    srows = P.build_source_rows(headers, rows, "2026年7月FBA订单", P.FBA_BUSINESS_KEYS)
    assert srows[0].key.order_id == ""            # FBA 汇总没有订单号
    assert not srows[0].key.incomplete            # MSKU/SKU/站点 齐全
    agg = P.aggregate_grain(
        srows,
        key_columns=P.FBA_BUSINESS_KEYS,
        sum_columns=["销量", "利润"],
        first_columns=["销售额"],
    )
    assert agg[0].business_key == ("M-1", "S-1", "AMZUS")
    assert agg[0].sums["利润"] == 2190.88
    assert agg[0].firsts["销售额"] == "6508.02"


def test_cost_evidence_classification_order():
    no_item = P.CostEvidence(item_code="X", exists=False)
    self_bom = P.CostEvidence(item_code="X", exists=True, standard_price=22.5, has_self_bom=True)
    price_no_bom = P.CostEvidence(item_code="X", exists=True, standard_price=24.0)
    no_price = P.CostEvidence(item_code="X", exists=True, standard_price=None)

    assert P.classify_cost_evidence(no_item) == P.COST_NO_ITEM
    assert P.classify_cost_evidence(self_bom) == P.COST_SELF_BOM_PRESENT
    assert P.classify_cost_evidence(price_no_bom) == P.COST_MISSING_SELF_BOM
    assert P.classify_cost_evidence(no_price) == P.COST_MISSING_PURCHASE_PRICE

    # 有采购价、无自套 BOM → 是「该建但没建」的候选
    assert P.classify_self_bom_candidate(price_no_bom) is True
    assert P.classify_self_bom_candidate(self_bom) is False
    assert P.classify_self_bom_candidate(no_item) is False


def test_evidence_client_is_read_only():
    from tongtool_order_cost.audit_sources import assert_no_write_methods

    assert_no_write_methods(P.ErpnextEvidenceClient(object()), "ErpnextEvidenceClient")


def test_is_self_bom_requires_single_self_child():
    assert P._is_self_bom("IT", {"items": [{"item_code": "IT", "qty": 1}]})
    assert not P._is_self_bom("IT", {"items": [{"item_code": "IT"}, {"item_code": "OTHER"}]})
    assert not P._is_self_bom("IT", {"items": []})
    # 扁平写法（Frappe items.item_code 扁平成 components）
    assert P._is_self_bom("IT", {"components": ["IT"]})
    assert not P._is_self_bom("IT", {"components": ["IT", "OTHER"]})
    assert not P._is_self_bom("IT", {"components": []})


# --------------------------- U4: 指标口径矩阵 ---------------------------

def _metric_rows():
    headers = ["订单号", "通途SKU", "包裹号", "发货数量", "1件产品成本", "运费", "售价*汇率", "订单总成本", "订单利润"]
    rows = [
        # 一件成品：1 条带成本行 + 2 条零成本部件行（稀释行均值）
        ["A-1", "PROD", "P1", "1", "100", "10", "300", "100", "200"],
        ["A-1", "PROD-Cover", "P1", "1", "0", "0", "0", "0", "0"],
        ["A-1", "PROD-Foam", "P1", "1", "0", "0", "0", "0", "0"],
    ]
    return P.build_source_rows(headers, rows, "wb")


def test_metric_dilution_vs_piece_ratio_of_totals():
    rows = _metric_rows()
    specs = [
        P.MetricSpec("产品成本_行均值", "1件产品成本", P.DEN_ROWS, grain="row"),
        P.MetricSpec(
            "产品成本_件均", "1件产品成本", P.DEN_COLUMN,
            denominator_column="发货数量", grain="piece",
        ),
    ]
    recs = {r.name: r for r in P.metric_matrix(rows, specs)}
    assert recs["产品成本_行均值"].value == pytest.approx(100 / 3)   # 133.3/3 被稀释
    assert recs["产品成本_件均"].value == pytest.approx(100 / 3)     # 100/3 件（3 行数量都算）
    # 两种口径都被显式标注
    assert recs["产品成本_行均值"].denominator_kind == P.DEN_ROWS
    assert recs["产品成本_件均"].denominator_column == "发货数量"


def test_metric_repeated_revenue_not_multiplied_at_order_grain():
    headers = ["订单号", "通途SKU", "包裹号", "发货数量", "1件产品成本", "运费", "售价*汇率", "订单总成本", "订单利润"]
    rows = [
        ["A-1", "PROD", "P1", "1", "100", "10", "300", "100", "200"],
        ["A-1", "PROD2", "P1", "1", "100", "10", "300", "100", "200"],
    ]
    srows = P.build_source_rows(headers, rows, "wb")
    spec = P.MetricSpec("收入_订单均", "售价*汇率", P.DEN_ORDERS, grain="order")
    rec = P.evaluate_metric(srows, spec)
    # 行总数 600，但订单数 1 → 订单均 = 600（不是把 300 重复乘 2 再平均）
    assert rec.denominator == 1.0
    assert rec.value == 600.0


def test_metric_zero_denominator_is_undefined_not_inf():
    headers = ["订单号", "通途SKU", "包裹号", "发货数量", "1件产品成本"]
    srows = P.build_source_rows(headers, [["A-1", "S", "P1", "1", "0"]], "wb")
    spec = P.MetricSpec("x", "1件产品成本", P.DEN_COLUMN, denominator_column="不存在的列")
    rec = P.evaluate_metric(srows, spec)
    assert rec.denominator == 0.0
    assert rec.status == P.METRIC_UNDEFINED
    assert rec.value is None


def test_metric_zero_policy_visible():
    headers = ["订单号", "通途SKU", "包裹号", "发货数量", "运费"]
    srows = P.build_source_rows(
        headers,
        [
            ["A-1", "S1", "P1", "1", "10"],
            ["A-2", "S2", "P2", "1", "0"],   # 零运费行
        ],
        "wb",
    )
    inc = P.evaluate_metric(srows, P.MetricSpec("运费_行均值", "运费", P.DEN_ROWS))
    exc = P.evaluate_metric(
        srows, P.MetricSpec("运费_非零行均值", "运费", P.DEN_NONZERO_ROWS, zero_policy="exclude_zero")
    )
    assert inc.value == 5.0
    assert exc.value == 10.0
    assert inc.zero_policy == "include" and exc.zero_policy == "exclude_zero"
    assert inc.to_dict()["denominator_kind"] == P.DEN_ROWS


def test_reproduce_flags_unreproduced_with_differences():
    rows = _metric_rows()
    recs = P.metric_matrix(rows, [P.MetricSpec("产品成本_行均值", "1件产品成本", P.DEN_ROWS)])
    out = P.reproduce(recs, {"产品成本_行均值": 33.33}, currency_tol=0.01)
    assert out["产品成本_行均值"]["status"] == P.METRIC_REPRODUCED
    out2 = P.reproduce(recs, {"产品成本_行均值": 999.0}, currency_tol=0.01)
    assert out2["产品成本_行均值"]["status"] == P.METRIC_UNREPRODUCED
    assert out2["产品成本_行均值"]["matched_metric"] is None
    assert out2["产品成本_行均值"]["differences"]


def test_fba_and_track_partitions_are_labeled():
    specs = P.default_metric_specs(track="coefficient", fba_scope="fba")
    assert all(s.track == "coefficient" and s.fba_scope == "fba" for s in specs)
    rows = _metric_rows()
    recs = P.metric_matrix(rows, specs)
    assert all(r.track == "coefficient" and r.fba_scope == "fba" for r in recs)


# --------------------------- U5: 异常分类器 ---------------------------

def _u5_rows(rows):
    headers = ["订单号", "通途SKU", "包裹号", "发货数量", "1件产品成本",
               "产品成本*数量", "物流商运费", "通途运费", "包裹总运费"]
    return P.build_source_rows(headers, rows, "wb")


def test_cost_present_at_order_grain_is_dilution_not_missing():
    rows = _u5_rows([
        ["ORD-A", "PROD", "P1", "1", "100", "100", "10", "9", "10"],
        ["ORD-A", "PROD-Cover", "P1", "1", "0", "0", "0", "0", "0"],
        ["ORD-A", "PROD-Foam", "P1", "1", "0", "0", "0", "0", "0"],
    ])
    cats = {f.key: f.category for f in P.classify_product_cost(rows)}
    assert cats["ORD-A"] == P.COST_DILUTION      # 订单成本闭合，只是行均被稀释
    assert cats["ORD-A"] != P.COST_MISSING


def test_cost_on_one_line_and_missing_anywhere():
    rows = _u5_rows([
        ["ORD-B", "S1", "P1", "1", "0", "0", "0", "0", "0"],
        ["ORD-B", "S2", "P1", "1", "0", "50", "0", "0", "0"],
        ["ORD-C", "S2", "P2", "1", "0", "0", "0", "0", "0"],
    ])
    cats = {f.key: f.category for f in P.classify_product_cost(rows)}
    assert cats["ORD-B"] == P.COST_ON_ONE_LINE
    assert cats["ORD-C"] == P.COST_MISSING


def test_missing_item_is_classified_before_bom_gap():
    # 无物料 → missing_item（不是 self-BOM 候选）
    assert P.classify_cost_evidence(P.CostEvidence("X", exists=False)) == P.COST_NO_ITEM
    # 有采购价 + 无自套 BOM → 才是 self-BOM 候选
    ev = P.CostEvidence("X", exists=True, standard_price=24.0, has_self_bom=False)
    assert P.classify_cost_evidence(ev) == P.COST_MISSING_SELF_BOM
    assert P.classify_self_bom_candidate(ev) is True


def test_repeated_package_freight_detected_with_effect():
    rows = _u5_rows([
        ["A-1", "S1", "P9", "1", "0", "0", "83.47", "0", "0"],
        ["A-1", "S2", "P9", "1", "0", "0", "83.47", "0", "0"],
        ["A-1", "S3", "P9", "1", "0", "0", "83.47", "0", "0"],
    ])
    reps = P.find_repeated_package_freight(rows)
    assert len(reps) == 1
    assert reps[0].category == P.FREIGHT_REPEATED
    assert reps[0].monetary_effect == pytest.approx(2 * 83.47)  # (3-1)*X

    # 值不同 = 按件分摊，不算重复
    amort = _u5_rows([
        ["B-1", "S1", "P8", "1", "0", "0", "123.79", "0", "0"],
        ["B-1", "S2", "P8", "1", "0", "0", "2.18", "0", "0"],
    ])
    assert P.find_repeated_package_freight(amort) == []


def test_freight_observed_vs_estimate_labeled_without_replacing():
    rows = _u5_rows([
        ["A-1", "S1", "P1", "1", "0", "0", "100", "90", "0"],   # 实收 vs 估算不同
        ["A-2", "S2", "P2", "1", "0", "0", "0", "70", "0"],     # 只有估算
        ["A-3", "S3", "P3", "1", "0", "0", "0", "0", "0"],      # 都缺
    ])
    bycat = {f.category: f for f in P.classify_freight(rows)}
    assert bycat[P.FREIGHT_ACTUAL].evidence["rows"] == 1
    assert bycat[P.FREIGHT_ESTIMATE_ONLY].monetary_effect == 70.0   # 估算不计入实收覆盖
    assert bycat[P.FREIGHT_ESTIMATE_ONLY].evidence["rows"] == 1
    assert bycat[P.FREIGHT_MISSING_BOTH].evidence["rows"] == 1
    assert bycat[P.FREIGHT_SOURCE_MISMATCH].evidence["rows"] == 1


def test_fba_tail_reference_classification():
    assert P.classify_fba_tail_reference(12.5) == P.FBA_TAIL_SKIPPED
    assert P.classify_fba_tail_reference(0.0) == P.FBA_TAIL_SKIPPED
    assert P.classify_fba_tail_reference(-3.2) == P.FBA_TAIL_NEGATIVE


def test_summarize_findings_counts_and_money():
    rows = _u5_rows([
        ["A-1", "S1", "P9", "1", "0", "0", "50", "0", "0"],
        ["A-1", "S2", "P9", "1", "0", "0", "50", "0", "0"],
    ])
    findings = P.find_repeated_package_freight(rows) + P.classify_freight(rows)
    summ = P.summarize_findings(findings)
    assert summ[P.FREIGHT_REPEATED]["count"] == 1
    assert summ[P.FREIGHT_REPEATED]["monetary_effect"] == pytest.approx(50.0)
    assert summ[P.FREIGHT_ACTUAL]["monetary_effect"] == pytest.approx(100.0)
    assert summ[P.FREIGHT_ACTUAL]["owners"] == [P.OWNER_TECH]


# --------------------------- U6: 利润倒挂 ---------------------------

def _u6_rows(rows):
    headers = ["订单号", "通途SKU", "包裹号", "发货数量", "售价*汇率",
               "订单总成本", "订单利润", "订单总成本*系数", "订单利润*系数",
               "VAT", "渠道成交费(人民币)", "PayPal fee(人民币)", "渠道账号"]
    return P.build_source_rows(headers, rows, "wb")


def test_cohort_summary_and_inversion_flagged():
    rows = _u6_rows([
        # 高回款、低毛利
        ["O-1", "S1", "P1", "1", "1000", "900", "100", "900", "100", "0", "0", "0", "BIG"],
        # 低回款、高毛利（倒挂候选）
        ["O-2", "S1", "P2", "1", "100", "10", "90", "10", "90", "0", "0", "0", "SMALL"],
    ])
    cohorts = P.cohort_summary(rows, key_col="渠道账号")
    assert {c["key"] for c in cohorts} == {"BIG", "SMALL"}
    inv = P.find_profit_inversions(cohorts)
    assert any(f.key == "SMALL" for f in inv)
    small = next(f for f in inv if f.key == "SMALL")
    assert small.evidence["margin"] > small.evidence["overall_margin"]


def test_profit_decomposition_sums_components():
    rows = _u6_rows([
        ["O-1", "S1", "P1", "1", "1000", "900", "100", "900", "100", "0", "50", "0", "A"],
    ])
    dec = P.profit_decomposition(rows, ["售价*汇率", "订单总成本", "渠道成交费(人民币)"])
    assert dec["售价*汇率"] == 1000.0
    assert dec["渠道成交费(人民币)"] == 50.0


def test_track_confusion_keeps_both_tracks():
    assert P.flag_track_confusion(100.0, 100.0) is None
    f = P.flag_track_confusion(2898063.44, 2896992.82)
    assert f is not None
    assert f.category == P.PROFIT_TRACK_CONFUSION
    assert f.decision_owner == P.OWNER_FINANCE
    assert f.evidence["delta"] == pytest.approx(-1070.62)


def test_zero_column_evidence_flags_missing_fees():
    rows = _u6_rows([
        ["O-1", "S1", "P1", "1", "100", "50", "50", "50", "50", "0", "10", "0", "A"],
    ])
    findings = P.zero_column_evidence(rows, P.FEE_COLUMNS)
    cats = {f.category for f in findings}
    assert f"column_all_zero:{P.FEE_VAT}" in cats        # VAT 全零
    assert f"column_all_zero:{P.FEE_PAYPAL}" in cats     # PayPal 全零
    assert f"column_all_zero:{P.FEE_CHANNEL}" not in cats  # 渠道费有值


# --------------------------- U6 补：规则轨 / 仓库口径体检 ---------------------------

def test_rule_track_delta_uses_in_sheet_columns_only():
    headers = ["订单号", "通途SKU", "包裹号", "发货数量",
               "皮壳成本", "皮壳成本*系数", "订单总成本", "订单总成本*系数"]
    rows = P.build_source_rows(headers, [
        ["O-1", "S1", "P1", "1", "100", "100", "500", "500"],
        ["O-2", "S2", "P2", "1", "200", "150", "800", "760"],
    ], "wb")
    out = {f.key: f for f in P.rule_track_delta(
        rows, pairs=(("皮壳成本", "皮壳成本*系数"), ("订单总成本", "订单总成本*系数")))}
    f = out["皮壳成本->皮壳成本*系数"]
    assert f.evidence["plain_sum"] == 300.0
    assert f.evidence["coeff_sum"] == 250.0
    assert f.evidence["delta"] == -50.0
    assert f.evidence["affected_rows"] == 1
    assert out["订单总成本->订单总成本*系数"].evidence["delta"] == -40.0


def test_warehouse_cost_source_check_flags_borrowed_shaoxing():
    headers = ["订单号", "通途SKU", "包裹号", "发货数量", "发货仓库",
               "发货区域", "二次加工成本来源编码", "二次加工成本*数量"]
    rows = P.build_source_rows(headers, [
        ["O-1", "S1", "P1", "1", "FZH-DANEEY-成品仓", "美国", "2CJG-SX", "10"],
        ["O-2", "S2", "P2", "1", "FZH-DANEEY-成品仓", "美国", "2CJG-SX", "20"],
        ["O-3", "S3", "P3", "1", "美东-CENTRADE", "美国", "2CJG-US", "99"],   # 正常，不报
        ["O-4", "S4", "P4", "1", "德国", "其它", "2CJG-SX", "5"],             # 真绍兴自发货，不报
    ], "wb")
    out = P.warehouse_cost_source_check(rows)
    assert len(out) == 1
    assert out[0].evidence["warehouse"] == "FZH-DANEEY-成品仓"
    assert out[0].evidence["rows"] == 2
    assert out[0].evidence["cost_sum"] == 30.0
    assert out[0].decision_owner == P.OWNER_MASTER


def test_track_pairs_have_matching_columns_for_july_writeback():
    # 纯结构检查：除 头程运费金额（单列）外，成对的普通列与 *系数 列都存在
    plain = [a for a, b in P.TRACK_PAIRS]
    assert "订单总成本" in plain and "订单利润" in plain
    assert ("头程运费金额", "头程运费金额") in P.TRACK_PAIRS
