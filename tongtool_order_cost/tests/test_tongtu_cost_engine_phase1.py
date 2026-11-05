# -*- coding: utf-8 -*-
"""Phase 1.1 单元测试：拆包合并 shadow。

覆盖：SKU 归一化 / EN method / 歧义阻断 / 配件排除 / 守恒 /
cost_eligible / 成本行唯一 / 原单校验跳过 / 载体身份冲突 / 合并明细。
"""
from __future__ import annotations

import sys
from pathlib import Path

import pandas as pd
import pytest

_ROOT = Path(__file__).resolve().parents[1]
if str(_ROOT) not in sys.path:
    sys.path.insert(0, str(_ROOT))

from tongtool_order_cost.tongtu_cost_engine.domain.split_merge import (  # noqa: E402
    EnResolver,
    build_merge_shadow,
    load_orders,
    normalize_sku,
    run_merge_shadow,
    sku_base,
    sku_shape,
)

ORDER_HEADER = ["订单号", "平台SKU", "通途SKU", "发货数量", "售价", "售价(人民币)", "运费", "发货仓库"]
EN_HEADER = ["order_id_code", "tongtool_sku", "shipping_method"]


# ── 小样构造 ──


def write_items(tmp_path: Path, rows: list[dict]) -> Path:
    """rows: name, customer_code, item_group, variant_of"""
    path = tmp_path / "items.csv"
    pd.DataFrame(rows, columns=["name", "customer_code", "item_group", "variant_of"]).to_csv(
        path, index=False, encoding="utf-8"
    )
    return path


def write_orders(tmp_path: Path, rows: list[list]) -> Path:
    """每行 7 列（默认仓库 WH1）或 8 列（自带发货仓库）。"""
    full = [list(r) + ["WH1"] if len(r) == 7 else list(r) for r in rows]
    path = tmp_path / "orders.csv"
    pd.DataFrame(full, columns=ORDER_HEADER).to_csv(path, index=False, encoding="utf-8")
    return path


def write_en_items(tmp_path: Path, rows: list[list]) -> Path:
    """rows: [order_id, tongtool_sku, shipping_method]（同键可重复，method 需一致）"""
    path = tmp_path / "en_items.csv"
    pd.DataFrame(rows, columns=EN_HEADER).to_csv(path, index=False, encoding="utf-8")
    return path


def write_en_full(tmp_path: Path, rows: list[list]) -> Path:
    """rows: [order_id, tongtool_sku, erp_item_code, quantity, shipping_method, despatch_time?]"""
    full = [list(r) + [""] if len(r) == 5 else list(r) for r in rows]
    path = tmp_path / "en_full.csv"
    pd.DataFrame(
        full,
        columns=["order_id_code", "tongtool_sku", "erp_item_code", "quantity",
                 "shipping_method", "despatch_complete_time"],
    ).to_csv(path, index=False, encoding="utf-8")
    return path


def write_flags(tmp_path: Path, rows: list[list]) -> Path:
    path = tmp_path / "flags.csv"
    pd.DataFrame(rows, columns=["order_id_code", "invalid", "suspended", "order_status"]).to_csv(
        path, index=False, encoding="utf-8"
    )
    return path


ITEMS = [
    # 成品（KS100）的客户码别名包含皮壳/海绵包装 SKU
    {"name": "KS100-FINISH-RED", "customer_code": "TT001-FIN,TT001,TT001-FIN-Cover,TT001-FIN-Foam", "item_group": "靠枕", "variant_of": "KS100"},
    {"name": "KS100-FINISH-BLUE", "customer_code": "TT002", "item_group": "靠枕", "variant_of": "KS100"},
    # 配件：不同产品 KS900
    {"name": "KS900-ACC", "customer_code": "ACC-1,Buttonkit", "item_group": "配件", "variant_of": "KS900"},
    # 另一个产品 KS200（正常独立别名）
    {"name": "KS200-OTHER", "customer_code": "TT777", "item_group": "其它", "variant_of": "KS200"},
]


# ── 归一化 / 形态 ──


def test_normalize_sku_strips_spaces_and_uppercases():
    assert normalize_sku("  tt0031 249k00 - cover ") == "TT0031249K00-COVER"
    assert normalize_sku(None) == ""
    assert normalize_sku("nan") == ""
    assert normalize_sku("C/Linen-Coffee-194-661-WOW") == "C/LINEN-COFFEE-194-661-WOW"


def test_normalize_sku_keeps_item_name_as_alias(tmp_path):
    items = write_items(tmp_path, ITEMS)
    resolver = EnResolver.from_items_csv(items)
    # 大小写/空格归一后能命中 item name 本身
    assert resolver.resolve(" ks100-finish-red ").product_id == "KS100"
    # customer_code 别名（逗号分隔）也能命中
    assert resolver.resolve("tt001").product_id == "KS100"
    assert resolver.resolve("Tt002").product_id == "KS100"


def test_sku_base_and_shape():
    assert sku_base("TT001-FIN-2") == "TT001-FIN"
    assert sku_base("TT001-FIN") == "TT001-FIN"
    # 非 TT SKU 的 -N 是尺寸，不能剥
    assert sku_base("CEN-Linen-100") == "CEN-LINEN-100"
    assert sku_shape("TT001-FIN-Cover") == "cover"
    assert sku_shape("TT0031247K0064095-Cover1") == "cover"
    assert sku_shape("TT001-FIN-Foam") == "foam"
    assert sku_shape("TT001-FIN") == "finished"


# ── 正常合并：皮壳 + 海绵（含两张子单，EN method=成品） ──


def test_merge_cover_foam_and_conservation(tmp_path):
    items = write_items(tmp_path, ITEMS)
    orders = write_orders(tmp_path, [
        ["ORD-1000001_1", "PSK", "TT001-FIN-Cover", 1, 10, 50, 5],
        ["ORD-1000001_1", "PSK", "TT001-FIN-Foam", 1, 0, 0, 0],
        ["ORD-1000001_2", "PSK", "TT001-FIN-Cover", 1, 10, 50, 5],
        ["ORD-1000001_2", "PSK", "TT001-FIN-Foam", 1, 0, 0, 0],
    ])
    en = write_en_items(tmp_path, [
        ["ORD-1000001_1", "TT001-FIN-Cover", "成品"],
        ["ORD-1000001_1", "TT001-FIN-Foam", "成品"],
        ["ORD-1000001_2", "TT001-FIN-Cover", "成品"],
        ["ORD-1000001_2", "TT001-FIN-Foam", "成品"],
    ])
    result = run_merge_shadow(orders, items, en, month="202608")
    assert result.ok, [a for a in result.assertions if a.status == "fail"]
    assert result.stats["merged_groups"] == 1
    assert result.stats["blocked_groups"] == 0
    assert result.stats["method_counts"]["成品"] == 1
    assert result.stats["rows_in_groups"] == 4
    assert result.stats["rows_absorbed"] == 3
    assert result.stats["rows_shadow"] == 1
    assert result.stats["rows_detail"] == 1
    assert result.stats["pieces_merged"] == 2
    assert result.stats["qty_total"] == 4
    assert result.stats["cost_eligible_rows"] == 1
    assert result.stats["cost_blocked_rows"] == 0

    group = result.groups[0]
    assert group.product_id == "KS100"
    assert group.method == "成品"
    assert group.carrier_sku == "TT001-FIN-COVER"
    assert group.sub_orders == ["ORD-1000001_1", "ORD-1000001_2"]

    detail = result.detail_rows[0]
    assert detail["group_id"] == "G0001"
    assert detail["merged"] is True
    assert detail["role"] == "成品"
    assert detail["pricing_method"] == "成品"
    assert detail["shipping_method"] == "成品"
    # GS 参考列：raw 快照没有该列 → 留空，绝不参与定价
    assert detail["当月给分公司发货类型"] == ""
    assert detail["cost_eligible"] is True
    assert detail["cost_blocked_reason"] == ""
    assert detail["carrier_sku"] == "TT001-FIN-COVER"
    assert detail["发货数量"] == "4"
    assert detail["售价(人民币)"] == "100"
    assert detail["pieces"] == 2

    # 无原单基行 → 原单校验必须是「跳过」，不能记通过
    assertion = next(a for a in result.assertions if a.name == "原单件数=有效子单之和")
    assert assertion.status == "skip"
    assert assertion.skipped >= 1
    assert result.stats["original_status"] == "skip"


# ── 半成品：KS0390 型 Cover+Foam 两行，必须保留半成品语义 ──


def test_semi_finished_group_keeps_method_and_merges_one_piece(tmp_path):
    items = write_items(tmp_path, ITEMS)
    orders = write_orders(tmp_path, [
        ["ORD-1100001_1", "PSK", "TT001-FIN-Foam", 1, 0, 0, 0],
        ["ORD-1100001_2", "PSK", "TT001-FIN-Cover", 1, 10, 50, 0],
    ])
    en = write_en_items(tmp_path, [
        ["ORD-1100001_1", "TT001-FIN-Foam", "半成品"],
        ["ORD-1100001_2", "TT001-FIN-Cover", "半成品"],
    ])
    result = run_merge_shadow(orders, items, en, month="202608")
    assert result.ok, [a for a in result.assertions if a.status == "fail"]
    assert result.stats["merged_groups"] == 1
    assert result.stats["method_counts"]["半成品"] == 1
    group = result.groups[0]
    assert group.method == "半成品"
    assert group.carrier_sku == "TT001-FIN-COVER"
    assert group.pieces == 1
    # 合并明细：两行合成一行，pricing_method 保持半成品，不变成皮壳
    assert result.stats["rows_detail"] == 1
    detail = result.detail_rows[0]
    assert detail["role"] == "半成品"
    assert detail["pricing_method"] == "半成品"
    assert detail["shipping_method"] == "半成品"
    assert detail["当月给分公司发货类型"] == ""
    assert detail["merged"] is True
    assert detail["cost_eligible"] is True
    assert detail["group_id"] == "G0001"
    assert detail["发货数量"] == "2"
    assert detail["pieces"] == 1


def test_method_missing_blocks_merge_and_cost(tmp_path):
    items = write_items(tmp_path, ITEMS)
    orders = write_orders(tmp_path, [
        ["ORD-1200001", "PSK", "TT001-FIN-Cover", 1, 10, 50, 0],
        ["ORD-1200001", "PSK", "TT001-FIN-Foam", 1, 0, 0, 0],
    ])
    en = write_en_items(tmp_path, [
        ["ORD-1200001", "TT001-FIN-Cover", ""],
        ["ORD-1200001", "TT001-FIN-Foam", ""],
    ])
    result = run_merge_shadow(orders, items, en, month="202608")
    assert result.stats["merged_groups"] == 0
    assert result.stats["blocked_groups"] == 1
    assert result.blocked[0].reason == "method_missing"
    assert result.stats["rows_detail"] == 2
    assert all(row["merged"] is False for row in result.detail_rows)
    # method 缺失 / 阻断组行不得自动定价
    assert result.stats["cost_eligible_rows"] == 0
    assert result.stats["cost_blocked_rows"] == 2
    for row in result.detail_rows:
        assert row["cost_eligible"] is False
        assert row["cost_blocked_reason"]
    assert result.ok


def test_mixed_methods_blocks_merge(tmp_path):
    items = write_items(tmp_path, ITEMS)
    orders = write_orders(tmp_path, [
        ["ORD-1300001", "PSK", "TT001-FIN-Cover", 1, 10, 50, 0],
        ["ORD-1300001", "PSK", "TT001-FIN-Foam", 1, 0, 0, 0],
    ])
    en = write_en_items(tmp_path, [
        ["ORD-1300001", "TT001-FIN-Cover", "皮壳"],
        ["ORD-1300001", "TT001-FIN-Foam", "半成品"],
    ])
    result = run_merge_shadow(orders, items, en, month="202608")
    assert result.stats["merged_groups"] == 0
    assert result.stats["blocked_groups"] == 1
    assert result.blocked[0].reason == "mixed_methods"


# ── 歧义阻断：一个别名 → 两个产品 ──


def test_ambiguous_alias_blocks_merge_and_cost(tmp_path):
    items = write_items(tmp_path, ITEMS + [
        {"name": "KS300-OTHER", "customer_code": "TT001-FIN,TT001-FIN-Cover,TT001-FIN-Foam", "item_group": "其它", "variant_of": "KS300"},
    ])
    resolver = EnResolver.from_items_csv(items)
    resolution = resolver.resolve("tt001-fin")
    assert resolution.status == "ambiguous"
    assert set(resolution.products) == {"KS100", "KS300"}

    orders = write_orders(tmp_path, [
        ["ORD-2000001", "PSK", "TT001-FIN-Cover", 1, 10, 50, 0],
        ["ORD-2000001", "PSK", "TT001-FIN-Foam", 1, 0, 0, 0],
    ])
    en = write_en_items(tmp_path, [
        ["ORD-2000001", "TT001-FIN-Cover", "成品"],
        ["ORD-2000001", "TT001-FIN-Foam", "成品"],
    ])
    result = run_merge_shadow(orders, items, en, month="202608")
    assert result.stats["merged_groups"] == 0
    assert result.stats["rows_ambiguous"] == 2
    assert result.stats["sku_ambiguous"] == 2
    assert result.stats["rows_shadow"] == 2
    assert result.stats["cost_eligible_rows"] == 0
    assert all("歧义" in row["cost_blocked_reason"] for row in result.detail_rows)
    assert result.ok


def test_unresolved_sku_passes_through_but_not_priced(tmp_path):
    items = write_items(tmp_path, ITEMS)
    orders = write_orders(tmp_path, [
        ["ORD-3000001", "PSK", "UNKNOWN-SKU", 2, 10, 50, 1],
    ])
    en = write_en_items(tmp_path, [])
    result = run_merge_shadow(orders, items, en, month="202608")
    assert result.stats["rows_unresolved"] == 1
    assert result.stats["rows_shadow"] == 1
    assert result.stats["rows_detail"] == 1
    assert result.shadow_rows[0]["merged"] is False
    assert result.shadow_rows[0]["qty"] == 2
    assert result.stats["cost_eligible_rows"] == 0
    assert result.detail_rows[0]["cost_eligible"] is False
    assert "未登记" in result.detail_rows[0]["cost_blocked_reason"]
    assert result.ok


# ── 配件排除：Buttonkit 属于不同产品 → 不合并 ──


def test_accessory_product_mismatch_excluded(tmp_path):
    items = write_items(tmp_path, ITEMS)
    orders = write_orders(tmp_path, [
        ["ORD-4000001", "PSK", "TT001-FIN", 1, 10, 50, 0],
        ["ORD-4000001", "PSK", "Buttonkit", 1, 0, 0, 0],
    ])
    en = write_en_items(tmp_path, [
        ["ORD-4000001", "TT001-FIN", "成品"],
        ["ORD-4000001", "Buttonkit", "成品"],
    ])
    result = run_merge_shadow(orders, items, en, month="202608")
    assert result.stats["candidate_groups"] == 0
    assert result.stats["merged_groups"] == 0
    assert result.stats["rows_shadow"] == 2
    assert all(not s["merged"] for s in result.shadow_rows)
    assert result.ok


# ── 组内多个成品 SKU → 阻断，不取 first ──


def test_multiple_finished_skus_split_to_products(tmp_path):
    items = write_items(tmp_path, ITEMS)
    orders = write_orders(tmp_path, [
        ["ORD-5000001", "PSK", "TT001-FIN", 1, 10, 50, 0],
        ["ORD-5000001", "PSK", "TT002", 1, 10, 50, 0],
    ])
    en = write_en_items(tmp_path, [
        ["ORD-5000001", "TT001-FIN", "成品"],
        ["ORD-5000001", "TT002", "成品"],
    ])
    result = run_merge_shadow(orders, items, en, month="202608")
    # 两个不同整件成品 SKU → 拆成两件分别计价，不是拆包组件
    assert result.stats["split_products_groups"] == 1
    assert result.stats["split_products_rows"] == 2
    assert result.stats["merged_groups"] == 0
    assert result.stats["blocked_groups"] == 0
    assert result.stats["rows_shadow"] == 2
    assert result.ok


def test_tt_package_suffix_counts_single_piece(tmp_path):
    items = write_items(tmp_path, [
        {"name": "KS500-FIN", "customer_code": "TT500", "item_group": "沙发", "variant_of": "KS500"},
        {"name": "KS500-FIN-B", "customer_code": "TT500-2", "item_group": "沙发", "variant_of": "KS500"},
    ])
    orders = write_orders(tmp_path, [
        ["ORD-6000001", "PSK", "TT500", 1, 10, 50, 0],
        ["ORD-6000001", "PSK", "TT500-2", 1, 0, 0, 0],
    ])
    en = write_en_items(tmp_path, [
        ["ORD-6000001", "TT500", "皮壳"],
        ["ORD-6000001", "TT500-2", "皮壳"],
    ])
    result = run_merge_shadow(orders, items, en, month="202608")
    assert result.stats["merged_groups"] == 1
    # -2 是包裹尾号，不算第二件成品
    assert result.groups[0].pieces == 1
    assert result.groups[0].method == "皮壳"
    assert result.ok


def test_carrier_identity_conflict_blocks(tmp_path):
    items = write_items(tmp_path, ITEMS)
    orders = write_orders(tmp_path, [
        ["ORD-6100001_1", "PSK", "TT001-FIN-Cover", 1, 10, 50, 0, "WH-A"],
        ["ORD-6100001_1", "PSK", "TT001-FIN-Foam", 1, 0, 0, 0, "WH-A"],
        ["ORD-6100001_2", "PSK", "TT001-FIN-Cover", 1, 10, 50, 0, "WH-B"],
        ["ORD-6100001_2", "PSK", "TT001-FIN-Foam", 1, 0, 0, 0, "WH-B"],
    ])
    en = write_en_items(tmp_path, [
        ["ORD-6100001_1", "TT001-FIN-Cover", "成品"],
        ["ORD-6100001_1", "TT001-FIN-Foam", "成品"],
        ["ORD-6100001_2", "TT001-FIN-Cover", "成品"],
        ["ORD-6100001_2", "TT001-FIN-Foam", "成品"],
    ])
    result = run_merge_shadow(orders, items, en, month="202608")
    assert result.stats["merged_groups"] == 0
    assert result.stats["blocked_groups"] == 1
    assert result.blocked[0].reason == "carrier_identity_conflict"
    assert result.stats["cost_eligible_rows"] == 0


# ── 成品件数 = 皮壳件数 ──


def test_piece_cover_mismatch_fails(tmp_path):
    items = write_items(tmp_path, [
        {"name": "KS600-INNER", "customer_code": "TT600-INNER", "item_group": "靠枕", "variant_of": "KS600"},
        {"name": "KS600-COVER", "customer_code": "TT600-COVER", "item_group": "靠枕", "variant_of": "KS600"},
    ])
    orders = write_orders(tmp_path, [
        ["ORD-6200001", "PSK", "TT600-INNER", 2, 20, 100, 0],
        ["ORD-6200001", "PSK", "TT600-COVER", 1, 5, 25, 0],
    ])
    en = write_en_items(tmp_path, [
        ["ORD-6200001", "TT600-INNER", "成品"],
        ["ORD-6200001", "TT600-COVER", "成品"],
    ])
    result = run_merge_shadow(orders, items, en, month="202608")
    assertion = next(a for a in result.assertions if a.name == "成品件数=皮壳件数")
    assert assertion.status == "fail"
    assert not result.ok


# ── 原单 = 有效子单之和 ──


def test_original_equals_suborders_pass(tmp_path):
    items = write_items(tmp_path, ITEMS)
    flags = write_flags(tmp_path, [["ORD-7000001", "0", "0", "已发货"]])
    orders = write_orders(tmp_path, [
        ["ORD-7000001", "PSK", "TT001-FIN", 2, 20, 100, 2],
        ["ORD-7000001_1", "PSK", "TT001-FIN", 1, 10, 50, 1],
        ["ORD-7000001_2", "PSK", "TT001-FIN", 1, 10, 50, 1],
    ])
    en = write_en_items(tmp_path, [
        ["ORD-7000001", "TT001-FIN", "成品"],
        ["ORD-7000001_1", "TT001-FIN", "成品"],
        ["ORD-7000001_2", "TT001-FIN", "成品"],
    ])
    resolver = EnResolver.from_items_csv(items)
    loaded = load_orders(orders, resolver, en, flags)
    result = build_merge_shadow(loaded.rows, loaded.aux_rows, loaded.sku_issues, month="202608")
    assertion = next(a for a in result.assertions if a.name == "原单件数=有效子单之和")
    assert assertion.status == "pass"
    assert assertion.checked >= 1


def test_original_vs_suborders_mismatch_fails(tmp_path):
    items = write_items(tmp_path, ITEMS)
    orders = write_orders(tmp_path, [
        ["ORD-8000001", "PSK", "TT001-FIN", 3, 30, 150, 3],
        ["ORD-8000001_1", "PSK", "TT001-FIN", 1, 10, 50, 1],
        ["ORD-8000001_2", "PSK", "TT001-FIN", 1, 10, 50, 1],
    ])
    en = write_en_items(tmp_path, [
        ["ORD-8000001", "TT001-FIN", "成品"],
        ["ORD-8000001_1", "TT001-FIN", "成品"],
        ["ORD-8000001_2", "TT001-FIN", "成品"],
    ])
    result = run_merge_shadow(orders, items, en, month="202608")
    assertion = next(a for a in result.assertions if a.name == "原单件数=有效子单之和")
    assert assertion.status == "fail"
    assert not result.ok


def test_original_check_skip_is_not_pass(tmp_path):
    """只有拆分子单、没有原单基行：必须记跳过并单列原因，不能算通过。"""
    items = write_items(tmp_path, ITEMS)
    orders = write_orders(tmp_path, [
        ["ORD-8100001_1", "PSK", "TT001-FIN-Cover", 1, 10, 50, 0],
        ["ORD-8100001_2", "PSK", "TT001-FIN-Foam", 1, 0, 0, 0],
    ])
    en = write_en_items(tmp_path, [
        ["ORD-8100001_1", "TT001-FIN-Cover", "成品"],
        ["ORD-8100001_2", "TT001-FIN-Foam", "成品"],
    ])
    result = run_merge_shadow(orders, items, en, month="202608")
    assertion = next(a for a in result.assertions if a.name == "原单件数=有效子单之和")
    assert assertion.status == "skip"
    assert assertion.skipped == 1
    assert assertion.skip_reasons
    assert result.stats["original_status"] == "skip"
    assert result.stats["original_skipped"] == 1
    assert result.ok  # skip 不算 fail


def test_invalid_original_is_aux_only(tmp_path):
    items = write_items(tmp_path, ITEMS)
    flags = write_flags(tmp_path, [["ORD-9000001", "1", "0", "作废"]])
    orders = write_orders(tmp_path, [
        ["ORD-9000001", "PSK", "TT001-FIN", 1, 10, 50, 1],
        ["ORD-9000001_1", "PSK", "TT001-FIN", 1, 10, 50, 1],
    ])
    en = write_en_items(tmp_path, [
        ["ORD-9000001", "TT001-FIN", "成品"],
        ["ORD-9000001_1", "TT001-FIN", "成品"],
    ])
    resolver = EnResolver.from_items_csv(items)
    loaded = load_orders(orders, resolver, en, flags)
    assert [r.order_id for r in loaded.rows] == ["ORD-9000001_1"]
    assert [r.order_id for r in loaded.aux_rows] == ["ORD-9000001"]
    result = build_merge_shadow(loaded.rows, loaded.aux_rows, loaded.sku_issues)
    # 作废原单不参与合并，只用于校验；数量/金额一致 → 通过
    assert result.stats["rows_aux_original"] == 1
    assertion = next(a for a in result.assertions if a.name == "原单件数=有效子单之和")
    assert assertion.status == "pass"
    assert result.ok


# ── 输出 ──


def test_reports_written_with_merged_detail_and_coverage(tmp_path):
    items = write_items(tmp_path, ITEMS)
    orders = write_orders(tmp_path, [
        ["ORD-1010001", "PSK", "TT001-FIN-Cover", 1, 10, 50, 0],
        ["ORD-1010001", "PSK", "TT001-FIN-Foam", 1, 0, 0, 0],
        ["ORD-1010001", "PSK", "TT777", 1, 20, 100, 0],
        ["ORD-1010001", "PSK", "UNKNOWN-SKU", 1, 5, 25, 0],
    ])
    en = write_en_items(tmp_path, [
        ["ORD-1010001", "TT001-FIN-Cover", "成品"],
        ["ORD-1010001", "TT001-FIN-Foam", "成品"],
        ["ORD-1010001", "TT777", "成品"],
        ["ORD-1010001", "UNKNOWN-SKU", "成品"],
    ])
    result = run_merge_shadow(orders, items, en, month="202608")
    from tongtool_order_cost.tongtu_cost_engine.domain.split_merge import (
        DETAIL_EXTRA_COLUMNS,
        render_markdown,
        write_shadow_xlsx,
    )

    assert result.stats["cost_eligible_rows"] == 2   # 合并组 1 + TT777 1
    assert result.stats["cost_blocked_rows"] == 1    # UNKNOWN-SKU

    md = render_markdown(result)
    assert "拆包合并 shadow — 202608" in md
    assert "合并组（1）" in md
    assert "pricing_method" in md
    assert "SKU 覆盖与 EN 解析依据" in md
    assert "UNKNOWN-SKU" in md

    xlsx = write_shadow_xlsx(result, tmp_path / "out" / "merge_shadow_202608.xlsx")
    assert xlsx.exists()
    sheets = pd.read_excel(xlsx, sheet_name=None)
    assert set(sheets) == {"汇总", "合并明细", "合并组", "EN原单(aux)", "阻断清单", "SKU覆盖", "断言"}
    detail = sheets["合并明细"]
    # 一条合并 + TT777 + UNKNOWN-SKU
    assert len(detail) == 3
    for col in ORDER_HEADER:
        assert col in detail.columns
    for col in DETAIL_EXTRA_COLUMNS:
        assert col in detail.columns
    merged = detail[detail["merged"].astype(str).str.upper() == "TRUE"]
    assert len(merged) == 1
    assert merged.iloc[0]["group_id"] == "G0001"
    assert merged.iloc[0]["pricing_method"] == "成品"
    assert str(merged.iloc[0]["cost_eligible"]).upper() == "TRUE"
    assert merged.iloc[0]["carrier_sku"] == "TT001-FIN-COVER"
    assert float(merged.iloc[0]["发货数量"]) == 2
    assert len(detail) == result.stats["rows_shadow"]

    coverage = sheets["SKU覆盖"]
    unknown = coverage[coverage["SKU"] == "UNKNOWN-SKU"]
    assert len(unknown) == 1
    assert str(unknown.iloc[0]["已覆盖"]).upper() in ("FALSE", "0")


# ── Phase 1.2：EN 作废原单（aux） ──


def _aux_case(tmp_path, *, orig_qty=1, orig_method="成品", sub_method="成品"):
    """一条作废原单（cover+foam）+ 一条子单；返回 (items, orders, en, flags)。"""
    items = write_items(tmp_path, ITEMS)
    flags = write_flags(tmp_path, [["ORD-1100001", "1", "0", "作废"]])
    orders = write_orders(tmp_path, [
        ["ORD-1100001_1", "PSK", "TT001-FIN-Cover", 1, 10, 50, 0],
        ["ORD-1100001_1", "PSK", "TT001-FIN-Foam", 1, 0, 0, 0],
    ])
    en = write_en_full(tmp_path, [
        ["ORD-1100001", "TT001-FIN-Cover", "KS100-FINISH-RED", orig_qty, orig_method],
        ["ORD-1100001", "TT001-FIN-Foam", "KS100-FINISH-RED", orig_qty, orig_method],
        ["ORD-1100001_1", "TT001-FIN-Cover", "", 1, sub_method],
        ["ORD-1100001_1", "TT001-FIN-Foam", "", 1, sub_method],
    ])
    return items, orders, en, flags


def test_aux_original_qty_and_method_pass(tmp_path):
    items, orders, en, flags = _aux_case(tmp_path)
    result = run_merge_shadow(orders, items, en, flags, month="202608")
    assert result.ok, [a for a in result.assertions if a.status == "fail"]
    assert result.stats["merged_groups"] == 1
    assert result.stats["aux_entries"] == 1
    assert result.stats["aux_status"] == {"通过": 1}
    assert result.stats["aux_groups"] == 1
    assert result.stats["aux_used_groups"] == 0
    aux = result.aux_table[0]
    assert aux["原单号"] == "ORD-1100001"
    assert aux["产品"] == "KS100"
    assert aux["qty"] == 1          # Cover 件数，不是组件 qty 合计
    assert aux["原始组件qty"] == 2
    assert aux["子单qty"] == 1
    assert aux["校验结果"] == "通过"
    assert aux["关联group_id"] == "G0001"
    # 原单只校验，不进明细/不叠加计数
    assert result.stats["rows_detail"] == 1
    assert result.stats["qty_total"] == 2
    assert result.detail_rows[0]["pieces_source"] == "suborder"

    qty = next(a for a in result.assertions if a.name == "原单件数=有效子单之和")
    assert qty.status == "pass"
    amount = next(a for a in result.assertions if a.name == "原单金额=有效子单之和")
    assert amount.status == "skip"   # EN 原单行无金额字段
    method = next(a for a in result.assertions if a.name == "原单产品/method一致")
    assert method.status == "pass"


def test_aux_original_qty_mismatch_blocks_group(tmp_path):
    items, orders, en, flags = _aux_case(tmp_path, orig_qty=2)  # 原单 4 vs 子单 2
    result = run_merge_shadow(orders, items, en, flags, month="202608")
    assert result.stats["merged_groups"] == 0
    assert result.stats["blocked_groups"] == 1
    assert result.blocked[0].reason == "aux_qty_mismatch"
    assert result.stats["cost_eligible_rows"] == 0
    assert result.aux_table[0]["校验结果"] == "阻断"
    qty = next(a for a in result.assertions if a.name == "原单件数=有效子单之和")
    assert qty.status == "fail"
    assert not result.ok


def test_aux_original_method_mismatch_blocks_group(tmp_path):
    items, orders, en, flags = _aux_case(tmp_path, orig_method="皮壳", sub_method="成品")
    result = run_merge_shadow(orders, items, en, flags, month="202608")
    assert result.stats["merged_groups"] == 0
    assert result.blocked[0].reason == "aux_method_mismatch"
    assert result.aux_table[0]["校验结果"] == "阻断"
    qty = next(a for a in result.assertions if a.name == "原单件数=有效子单之和")
    assert qty.status == "pass"
    method = next(a for a in result.assertions if a.name == "原单产品/method一致")
    assert method.status == "fail"
    assert not result.ok


def test_aux_pieces_fallback_without_double_count(tmp_path):
    """组内只有拆单尾号、件数无法确定时，用 EN 原单件数兜底；原单不叠加计数。"""
    items = write_items(tmp_path, [
        {"name": "KS600-INNER", "customer_code": "TT600-INNER,TT600-INNER-1,TT600-INNER-2", "item_group": "靠枕", "variant_of": "KS600"},
    ])
    flags = write_flags(tmp_path, [["ORD-1200001", "1", "0", "作废"]])
    orders = write_orders(tmp_path, [
        ["ORD-1200001_1", "PSK", "TT600-INNER-1", 1, 10, 50, 0],
        ["ORD-1200001_1", "PSK", "TT600-INNER-2", 1, 5, 25, 0],
    ])
    en = write_en_full(tmp_path, [
        ["ORD-1200001", "TT600-INNER", "KS600-INNER", 2, "成品"],
        ["ORD-1200001_1", "TT600-INNER-1", "", 1, "成品"],
        ["ORD-1200001_1", "TT600-INNER-2", "", 1, "成品"],
    ])
    result = run_merge_shadow(orders, items, en, flags, month="202608")
    assert result.ok, [a for a in result.assertions if a.status == "fail"]
    assert result.stats["merged_groups"] == 1
    group = result.groups[0]
    assert group.pieces == 2
    assert group.pieces_source == "aux"
    assert group.aux_used is True
    assert result.stats["pieces_from_aux"] == 1
    # 原单未叠加：合并明细/总数量仍只来自子单
    assert result.stats["qty_total"] == 2
    assert result.stats["qty_shadow"] == 2
    aux = result.aux_table[0]
    assert aux["是否用于兜底"] == "是"
    assert aux["校验结果"] == "通过"


def test_aux_report_and_sheet(tmp_path):
    items, orders, en, flags = _aux_case(tmp_path)
    result = run_merge_shadow(orders, items, en, flags, month="202608")
    from tongtool_order_cost.tongtu_cost_engine.domain.split_merge import (
        AUX_COLUMNS,
        render_markdown,
        write_shadow_xlsx,
    )

    md = render_markdown(result)
    assert "EN 作废原单（aux）校验" in md
    assert "ORD-1100001" in md
    assert "cost_fg" in md

    xlsx = write_shadow_xlsx(result, tmp_path / "out" / "merge_shadow_202608.xlsx")
    sheets = pd.read_excel(xlsx, sheet_name=None)
    assert "EN原单(aux)" in sheets
    aux = sheets["EN原单(aux)"]
    for col in AUX_COLUMNS:
        assert col in aux.columns
    assert len(aux) == 1
    assert aux.iloc[0]["原单号"] == "ORD-1100001"
    assert aux.iloc[0]["校验结果"] == "通过"


# ── Phase 1.3：件数口径 / 跨月 / component_sum_error ──


def test_aux_component_rows_do_not_sum_pieces(tmp_path):
    """KFLDE 场景：原单 2 Cover + 2 Foam，组件 qty 合计 4 是错的，按 Cover 应为 2。"""
    items = write_items(tmp_path, ITEMS)
    flags = write_flags(tmp_path, [["ORD-1300001", "1", "0", "作废"]])
    orders = write_orders(tmp_path, [
        ["ORD-1300001_1", "PSK", "TT001-FIN-Cover", 1, 10, 50, 0],
        ["ORD-1300001_1", "PSK", "TT001-FIN-Foam", 1, 0, 0, 0],
    ])
    en = write_en_full(tmp_path, [
        ["ORD-1300001", "TT001-FIN-Cover", "KS100-FINISH-RED", 1, "半成品"],
        ["ORD-1300001", "TT001-FIN-Cover", "KS100-FINISH-RED", 1, "半成品"],
        ["ORD-1300001", "TT001-FIN-Foam", "KS100-FINISH-RED", 1, "半成品"],
        ["ORD-1300001", "TT001-FIN-Foam", "KS100-FINISH-RED", 1, "半成品"],
        ["ORD-1300001_1", "TT001-FIN-Cover", "", 1, "半成品"],
        ["ORD-1300001_1", "TT001-FIN-Foam", "", 1, "半成品"],
    ])
    result = run_merge_shadow(orders, items, en, flags, month="202608")
    assert result.ok, [a for a in result.assertions if a.status == "fail"]
    assert result.stats["merged_groups"] == 1
    group = result.groups[0]
    assert group.pieces == 2           # ΣCover qty，不是 4
    assert group.pieces_source == "aux"
    assert group.aux_used is True
    aux = result.aux_table[0]
    assert aux["qty"] == 2
    assert aux["原始组件qty"] == 4
    assert aux["子单qty"] == 2
    assert aux["校验结果"] == "component_sum_error"
    assert "组件行重复" in aux["原因"]
    assert result.stats["aux_component_sum_error"] == 1
    # 原单不叠加：总数仍只来自子单
    assert result.stats["qty_total"] == 2
    assert result.stats["qty_shadow"] == 2


def test_aux_cross_month_linked_not_unlinked(tmp_path):
    """原单在 202608 无子单、子单在 202609 → 标跨月关联。"""
    items = write_items(tmp_path, ITEMS)
    flags = write_flags(tmp_path, [["ORD-1400001", "1", "0", "作废"]])
    orders = write_orders(tmp_path, [
        ["ORD-1500001", "PSK", "TT777", 1, 10, 50, 0],
    ])
    en = write_en_full(tmp_path, [
        # 作废原单：本月无 raw 子单
        ["ORD-1400001", "TT001-FIN-Cover", "KS100-FINISH-RED", 1, "成品", ""],
        ["ORD-1400001", "TT001-FIN-Foam", "KS100-FINISH-RED", 1, "成品", ""],
        # 子单在 9 月（完整 EN 明细仍能看到）
        ["ORD-1400001_1", "TT001-FIN-Cover", "", 1, "成品", "2026-09-05 10:00:00.000000"],
        ["ORD-1400001_1", "TT001-FIN-Foam", "", 1, "成品", "2026-09-05 10:00:00.000000"],
        ["ORD-1500001", "TT777", "", 1, "成品", "2026-08-10 10:00:00.000000"],
    ])
    result = run_merge_shadow(orders, items, en, flags, month="202608")
    assert result.ok, [a for a in result.assertions if a.status == "fail"]
    aux = result.aux_table[0]
    assert aux["原单号"] == "ORD-1400001"
    assert aux["校验结果"] == "跨月关联"
    assert aux["跨月"] == "是"
    assert "202609" in aux["关联月"]
    assert result.stats["aux_cross_month"] == 1


def test_aux_whole_rows_take_one_not_sum(tmp_path):
    """OS 场景：_1/_2 同产品整件行取其一，不相加。"""
    items = write_items(tmp_path, [
        {"name": "KS500-FIN", "customer_code": "TT500", "item_group": "沙发", "variant_of": "KS500"},
        {"name": "KS500-FIN-B", "customer_code": "TT500-2", "item_group": "沙发", "variant_of": "KS500"},
    ])
    flags = write_flags(tmp_path, [["ORD-1600001", "1", "0", "作废"]])
    orders = write_orders(tmp_path, [
        ["ORD-1600001_1", "PSK", "TT500", 1, 10, 50, 0],
        ["ORD-1600001_1", "PSK", "TT500-2", 1, 0, 0, 0],
    ])
    en = write_en_full(tmp_path, [
        ["ORD-1600001", "TT500", "KS500-FIN", 1, "皮壳"],
        ["ORD-1600001", "TT500-2", "KS500-FIN-B", 1, "皮壳"],
        ["ORD-1600001_1", "TT500", "", 1, "皮壳"],
        ["ORD-1600001_1", "TT500-2", "", 1, "皮壳"],
    ])
    result = run_merge_shadow(orders, items, en, flags, month="202608")
    assert result.ok, [a for a in result.assertions if a.status == "fail"]
    aux = result.aux_table[0]
    assert aux["qty"] == 1             # 整件行取其一
    assert aux["原始组件qty"] == 2
    assert aux["子单qty"] == 1
    assert aux["校验结果"] == "通过"


def test_method_fallback_from_item_group_branch(tmp_path):
    """EN shipping_method 为空时，按 item→item_group→branch 兜底。"""
    items = write_items(tmp_path, [
        {"name": "KS800-IRON", "customer_code": "IRON", "item_group": "主体骨架", "variant_of": "KS800"},
    ])
    orders = write_orders(tmp_path, [
        ["ORD-7000001", "PSK", "IRON", 1, 10, 50, 0],
    ])
    en = write_en_items(tmp_path, [["ORD-7000001", "IRON", ""]])
    branch = tmp_path / "branch.tsv"
    branch.write_text(
        "name\tbranch\tparent\n主体骨架\t成品\t配件\n子组\t\t主体骨架\n",
        encoding="utf-8",
    )
    result = run_merge_shadow(orders, items, en, month="202608", branch_map_csv=branch)
    row = result.rows[0]
    assert row.shipping_method == "成品"
    assert row.method_source == "item_group_fallback"
    assert result.detail_rows[0]["method_source"] == "item_group_fallback"
    assert result.stats["method_fallback_rows"] == 1


def test_method_fallback_walks_up_empty_ancestor(tmp_path):
    items = write_items(tmp_path, [
        {"name": "KS801-X", "customer_code": "X1", "item_group": "子组", "variant_of": "KS801"},
    ])
    orders = write_orders(tmp_path, [["ORD-7000002", "PSK", "X1", 1, 10, 50, 0]])
    en = write_en_items(tmp_path, [["ORD-7000002", "X1", ""]])
    branch = tmp_path / "branch.tsv"
    branch.write_text(
        "name\tbranch\tparent\n主体骨架\t成品\t配件\n子组\t\t主体骨架\n",
        encoding="utf-8",
    )
    result = run_merge_shadow(orders, items, en, month="202608", branch_map_csv=branch)
    assert result.rows[0].shipping_method == "成品"
    assert result.rows[0].method_source == "item_group_fallback"
