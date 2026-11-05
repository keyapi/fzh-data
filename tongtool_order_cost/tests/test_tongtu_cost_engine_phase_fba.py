# -*- coding: utf-8 -*-
"""Phase 4.FBA 测试：桥接/分摊/成本/套件/待审/重复/78 列。"""
from __future__ import annotations

import sys
from pathlib import Path

import pandas as pd
import pytest

_ROOT = Path(__file__).resolve().parents[1]
if str(_ROOT) not in sys.path:
    sys.path.insert(0, str(_ROOT))

from tongtool_order_cost.tongtu_cost_engine.domain.fba_shadow import (  # noqa: E402
    MERGED_COLUMNS,
    build_fba_shadow,
)

BOM_COLS = [
    "item_fg", "item_fg_name", "shipping_method", "cost_fg", "cost_sxbzbcp", "cost_sxbzcp", "sx_cost_all",
    "usnj_valuation_rate", "ustx_valuation_rate", "pl_valuation_rate",
    "cover_freight_2kk9fsq8ln", "sfg_freight_2kk9fsq8ln", "freight_2kk9fsq8ln",
    "cover_freight_e5asph24tk", "sfg_freight_e5asph24tk", "freight_e5asph24tk",
    "cover_freight_tmvvepd80f", "sfg_freight_tmvvepd80f", "freight_tmvvepd80f",
    "freight_9rr7m7g3aj", "freight_88hko2ad7l", "freight_0hn57vpr4u", "freight_3s2n1bnpbj",
]
GS_COLS = ["图片", "MSKU", "SKU", "品类", "产品名称", "站点", "开发人员", "订单数量", "销量",
           "上期销量", "销量环比", "销量占比", "销售额", "上期销售额", "销售额环比", "销售额占比",
           "成本", "订单费用", "头程费用", "自定义费用", "利润", "上期利润", "利润环比",
           "利润占比", "利润率"]


def _setup(tmp_path: Path):
    out = tmp_path / "out"
    out.mkdir()
    ref = pd.DataFrame([
        {"name": "ITEM1", "customer_code": "GS1", "item_group": "靠枕", "variant_of": "P1"},
        {"name": "ITEM2", "customer_code": "GS2", "item_group": "靠枕", "variant_of": "P2"},
        {"name": "C1", "customer_code": "C1", "item_group": "配件", "variant_of": "C1P"},
        {"name": "TJ#TEST", "customer_code": "TJBUNDLE", "item_group": "套件#", "variant_of": ""},
    ])
    ref.to_csv(out / "item_refcode.csv", index=False, encoding="utf-8")
    bom_rows = []
    for item, freight in (("ITEM1", 3), ("C1", 4)):
        rec = {c: "0" for c in BOM_COLS}
        rec.update({"item_fg": item, "shipping_method": "皮壳", "cost_fg": 10,
                    "cost_sxbzcp": 2, "sx_cost_all": 12, "freight_9rr7m7g3aj": freight})
        bom_rows.append(rec)
    pd.DataFrame(bom_rows, columns=BOM_COLS).to_csv(out / "bom_cost_product_with_kits.csv",
                                                    index=False, encoding="utf-8")
    pd.DataFrame([{"bundle_item": "TJ#TEST", "component_item": "C1", "qty": 1,
                   "bundle_version": "v1|h"}]).to_csv(out / "product_bundles.csv", index=False, encoding="utf-8")
    pd.DataFrame(columns=["item_fg", "cost_fg"]).to_csv(out / "kit.csv", index=False, encoding="utf-8")
    en = pd.DataFrame([
        {"order_id_code": "O1", "warehouse_name": "美国FBA仓", "despatch_complete_time": "2026-08-15 10:00:00",
         "package_id": "P1", "tongtool_sku": "GS1", "erp_item_code": "ITEM1", "quantity": "2",
         "shipping_method": "皮壳", "cost_fg": "20", "cost_sxbzbcp": "0", "cost_sxbzcp": "10",
         "sx_cost_all": "30", "sx_shipping_cost": "30", "split_package_cost_factor": "1"},
        {"order_id_code": "O2", "warehouse_name": "美国FBA仓", "despatch_complete_time": "2026-08-15 11:00:00",
         "package_id": "P2", "tongtool_sku": "GS2", "erp_item_code": "ITEM2", "quantity": "1",
         "shipping_method": "皮壳", "cost_fg": "5", "cost_sxbzbcp": "0", "cost_sxbzcp": "1",
         "sx_cost_all": "6", "sx_shipping_cost": "6", "split_package_cost_factor": "1"},
        {"order_id_code": "O3", "warehouse_name": "美国FBA仓", "despatch_complete_time": "2026-08-16 10:00:00",
         "package_id": "P3", "tongtool_sku": "TJBUNDLE", "erp_item_code": "TJ#TEST", "quantity": "1",
         "shipping_method": "皮壳", "cost_fg": "10", "cost_sxbzbcp": "0", "cost_sxbzcp": "2",
         "sx_cost_all": "12", "sx_shipping_cost": "12", "split_package_cost_factor": "1"},
    ])
    en.to_csv(out / "en_items_all_089.csv", index=False, encoding="utf-8")
    gs = pd.DataFrame([
        {"MSKU": "M1", "SKU": "GS1", "站点": "AMZDANEEYUS", "销量": "1", "销售额": "100", "成本": "10", "头程费用": "3"},
        {"MSKU": "M2", "SKU": "GS1", "站点": "AMZDANEEYUS", "销量": "1", "销售额": "100", "成本": "10", "头程费用": "3"},
        {"MSKU": "M3", "SKU": "UNKNOWN", "站点": "AMZDANEEYUS", "销量": "1", "销售额": "50", "成本": "5", "头程费用": "1"},
        {"MSKU": "M4", "SKU": "TJBUNDLE", "站点": "AMZDANEEYUS", "销量": "1", "销售额": "80", "成本": "10", "头程费用": "4"},
    ])
    gs.to_csv(out / "raw_fba_202608.csv", index=False, encoding="utf-8")
    gs.to_csv(out / "fba_export_202608.csv", index=False, encoding="utf-8")
    # 非FBA 一行，与 M1 同 business key → 重复
    nf = {c: "" for c in MERGED_COLUMNS}
    nf.update({"订单号": "SELF1", "平台SKU": "M1", "平台SKU_统一": "M1", "通途SKU": "GS1",
               "发货数量": "1"})
    pd.DataFrame([nf]).to_csv(out / "nonfba.csv", index=False, encoding="utf-8")
    return out


def test_fba_bridge_allocation_and_outputs(tmp_path):
    out = _setup(tmp_path)
    res = build_fba_shadow(month="202608", root=tmp_path, nonfba_csv=out / "nonfba.csv",
                           bom_csv=out / "bom_cost_product_with_kits.csv",
                           ref_map_csv=out / "item_refcode.csv",
                           bundle_csv=out / "product_bundles.csv",
                           kit_report_csv=out / "kit.csv",
                           out_dir=out / "fba_shadow")
    assert res.stats["fba_rows"] == 4
    assert res.stats["fba_priced"] == 3   # ITEM1 x2 + TJ kit
    priced = [r for r in res.fba_rows if r["bridge_status"] == "ok"]
    m1 = [r for r in priced if r["gs_msku"] == "M1"][0]
    m2 = [r for r in priced if r["gs_msku"] == "M2"][0]
    # 成品口径单位成本：皮壳=cost_fg、绍兴二次=sx_cost_all−cost_fg、二次=FBA valuation 0
    assert float(m1["皮壳成本*数量"]) == 10
    assert float(m1["绍兴二次加工成本*数量"]) == 2   # (12−10) × 1
    assert float(m1["二次加工成本*数量"]) == 0
    assert float(m1["头程运费*数量"]) == 3
    assert float(m1["1件产品成本"]) == 12
    assert float(m2["皮壳成本*数量"]) == 10
    assert float(m2["绍兴二次加工成本*数量"]) == 2
    kit = [r for r in priced if r["gs_msku"] == "M4"][0]
    assert kit["kit_method"] == "皮壳"
    assert float(kit["头程运费*数量"]) == 4   # bundle C1 FBA freight
    assert float(kit["皮壳成本*数量"]) == 10
    assert float(kit["绍兴二次加工成本*数量"]) == 2
    for row in priced:
        assert float(row["皮壳成本*数量"]) + float(row["绍兴二次加工成本*数量"]) \
            + float(row["二次加工成本*数量"]) == float(row["产品成本*数量"])
    assert res.stats["cost_identity_violations"] == 0
    assert res.stats["fba_sx_nonzero_rows"] == 3
    pending = [r for r in res.fba_rows if r["bridge_status"] != "ok"]
    assert any(r["bridge_reason"] == "gs_sku_unresolved" for r in pending)
    # 78 列 + extras
    for col in MERGED_COLUMNS:
        assert col in res.fba_rows[0]
    assert "fulfillment" in res.fba_rows[0]
    # 重复：SELF1 与 M1 同 business key
    assert res.stats["duplicate_rows"] >= 2
    assert any(float(r.get("duplicate_flag") or 0) == 1 for r in res.merged_rows)
    # 合并：每行带 fulfillment / 唯一键 / pending 状态
    keys = [r["unique_key"] for r in res.merged_rows]
    assert len(keys) == len(set(keys))
    assert res.stats["merged_unique_key_dupes"] == 0
    for r in res.merged_rows:
        assert r["fulfillment"] in ("SELF", "FBA")
        assert r["unique_key"]
        assert r["pending_flag"] is (r["bridge_status"] != "ok")
    fba_pending = [r for r in res.merged_rows if r["fulfillment"] == "FBA" and r["bridge_status"] != "ok"]
    assert fba_pending and all(r["pending_flag"] for r in fba_pending)
    assert res.stats["merged_pending_rows"] == len(fba_pending)
    # 文件输出
    assert (out / "fba_shadow" / "fba_shadow_202608.csv").exists()
    assert (out / "fba_shadow" / "merged_shadow_202608.csv").exists()


def test_fba_kit_head_from_bundle(tmp_path):
    out = _setup(tmp_path)
    res = build_fba_shadow(month="202608", root=tmp_path, nonfba_csv=None,
                           bom_csv=out / "bom_cost_product_with_kits.csv",
                           ref_map_csv=out / "item_refcode.csv",
                           bundle_csv=out / "product_bundles.csv",
                           kit_report_csv=out / "kit.csv")
    kit = [r for r in res.fba_rows if r["canonical_sku"] == "TJ#TEST"]
    assert len(kit) == 1
    assert kit[0]["bridge_status"] == "ok"
    assert float(kit[0]["头程运费*数量"]) == 4   # bundle C1 FBA freight


def _rewrite_fixture(out: Path, *, item: str, bom_rows: list[dict],
                     gs_sku: str = "GSX") -> None:
    pd.DataFrame([
        {"name": item, "customer_code": gs_sku, "item_group": "靠枕", "variant_of": "P1"},
    ]).to_csv(out / "item_refcode.csv", index=False, encoding="utf-8")
    pd.DataFrame(bom_rows, columns=BOM_COLS).to_csv(
        out / "bom_cost_product_with_kits.csv", index=False, encoding="utf-8")
    pd.DataFrame([
        {"order_id_code": "O1", "warehouse_name": "美国FBA仓",
         "despatch_complete_time": "2026-08-15 10:00:00", "package_id": "P1",
         "tongtool_sku": gs_sku, "erp_item_code": item, "quantity": "1",
         "shipping_method": "皮壳", "cost_fg": "1", "cost_sxbzcp": "0",
         "cost_sxbzbcp": "0", "sx_cost_all": "1", "sx_shipping_cost": "1",
         "split_package_cost_factor": "1"},
    ]).to_csv(out / "en_items_all_089.csv", index=False, encoding="utf-8")
    pd.DataFrame([
        {"MSKU": "M1", "SKU": gs_sku, "站点": "AMZDANEEYUS", "销量": "1",
         "销售额": "100", "成本": "1", "头程费用": "1"},
    ]).to_csv(out / "raw_fba_202608.csv", index=False, encoding="utf-8")
    pd.DataFrame(columns=["bundle_item", "component_item", "qty", "bundle_version"]).to_csv(
        out / "product_bundles.csv", index=False, encoding="utf-8")


def _bom_row(item: str, *, cost_fg: float, sx_cost_all: float, freight: float = 3,
             method: str = "皮壳", name: str = "", sxbzcp: float = 0) -> dict:
    rec = {c: "0" for c in BOM_COLS}
    rec.update({"item_fg": item, "item_fg_name": name, "shipping_method": method,
                "cost_fg": cost_fg, "sx_cost_all": sx_cost_all,
                "cost_sxbzcp": sxbzcp, "freight_9rr7m7g3aj": freight})
    return rec


def test_fba_bom_lookup_uses_exact_erp_item_code_case(tmp_path):
    """EN 明细 `110x81x25` 小写 x：BOM 必须 exact 命中，不能先大写化。"""
    out = _setup(tmp_path)
    exact = "ITEM-110x81x25"
    _rewrite_fixture(out, item=exact, bom_rows=[
        _bom_row(exact, cost_fg=10, sx_cost_all=14),
        _bom_row(exact.upper(), cost_fg=99, sx_cost_all=199),  # 大写诱饵，若上大写必错取
    ])
    res = build_fba_shadow(month="202608", root=tmp_path, nonfba_csv=None,
                           bom_csv=out / "bom_cost_product_with_kits.csv",
                           ref_map_csv=out / "item_refcode.csv",
                           bundle_csv=out / "product_bundles.csv",
                           kit_report_csv=out / "kit.csv")
    assert res.stats["fba_priced"] == 1, res.stats["pending_reasons"]
    row = [r for r in res.fba_rows if r["bridge_status"] == "ok"][0]
    assert row["en_item_code"] == exact
    assert float(row["皮壳成本*数量"]) == 10
    assert float(row["绍兴二次加工成本*数量"]) == 4
    assert float(row["二次加工成本*数量"]) == 0
    assert float(row["头程运费*数量"]) == 3
    assert float(row["产品成本*数量"]) == 14


def test_fba_direct_purchase_zero_priced(tmp_path):
    """直采成品（cost_fg==sx_cost_all 且 cost_sxbzcp==0）→ 允许绍兴二次=0 并定价。"""
    out = _setup(tmp_path)
    item = "ITEM-DIRECT"
    _rewrite_fixture(out, item=item, bom_rows=[
        _bom_row(item, cost_fg=48, sx_cost_all=48, method="成品", name="颈椎枕-冰丝-灰色")])
    res = build_fba_shadow(month="202608", root=tmp_path, nonfba_csv=None,
                           bom_csv=out / "bom_cost_product_with_kits.csv",
                           ref_map_csv=out / "item_refcode.csv",
                           bundle_csv=out / "product_bundles.csv",
                           kit_report_csv=out / "kit.csv")
    assert res.stats["fba_priced"] == 1
    assert res.stats["direct_purchase_zero_rows"] == 1
    assert res.stats["fba_pending"] == 0
    row = res.fba_rows[0]
    assert row["bridge_status"] == "ok"
    assert row["bridge_reason"] == "direct_purchase_zero"
    assert float(row["绍兴二次加工成本"]) == 0
    assert float(row["皮壳成本*数量"]) == 48
    assert float(row["1件产品成本"]) == 48
    assert res.pending_rows == []


def test_fba_zero_sx_non_direct_pending(tmp_path):
    """sx_cost_all == cost_fg 但 cost_sxbzcp≠0 → 不是直采，仍 pending sx_zero。"""
    out = _setup(tmp_path)
    item = "ITEM-NOSX"
    _rewrite_fixture(out, item=item, bom_rows=[
        _bom_row(item, cost_fg=10, sx_cost_all=10, sxbzcp=2)])
    res = build_fba_shadow(month="202608", root=tmp_path, nonfba_csv=None,
                           bom_csv=out / "bom_cost_product_with_kits.csv",
                           ref_map_csv=out / "item_refcode.csv",
                           bundle_csv=out / "product_bundles.csv",
                           kit_report_csv=out / "kit.csv")
    assert res.stats["fba_priced"] == 0
    row = res.fba_rows[0]
    assert row["bridge_status"] == "pending"
    assert row["bridge_reason"] == "sx_zero"
    assert row["绍兴二次加工成本"] == ""


def _legacy_fixture(out: Path, legacy: str, product_name: str, bom_rows: list[dict],
                    ref_rows: list[dict], qty: str = "5", site: str = "AMZRosoonDE",
                    warehouse: str = "德国FBA仓") -> None:
    pd.DataFrame(ref_rows).to_csv(out / "item_refcode.csv", index=False, encoding="utf-8")
    pd.DataFrame(bom_rows, columns=BOM_COLS).to_csv(
        out / "bom_cost_product_with_kits.csv", index=False, encoding="utf-8")
    pd.DataFrame([
        {"order_id_code": "O1", "warehouse_name": warehouse,
         "despatch_complete_time": "2026-08-15 10:00:00", "package_id": "P1",
         "tongtool_sku": legacy, "erp_item_code": "NULL", "quantity": "1",
         "shipping_method": "皮壳", "cost_fg": "0", "cost_sxbzcp": "0",
         "cost_sxbzbcp": "0", "sx_cost_all": "0", "sx_shipping_cost": "0",
         "split_package_cost_factor": "1"},
    ]).to_csv(out / "en_items_all_089.csv", index=False, encoding="utf-8")
    pd.DataFrame([
        {"MSKU": "M1", "SKU": legacy, "站点": site, "销量": qty,
         "销售额": "100", "产品名称": product_name, "成本": "0", "头程费用": "0"},
    ]).to_csv(out / "raw_fba_202608.csv", index=False, encoding="utf-8")
    pd.DataFrame(columns=["bundle_item", "component_item", "qty", "bundle_version"]).to_csv(
        out / "product_bundles.csv", index=False, encoding="utf-8")


def _run(out: Path):
    return build_fba_shadow(month="202608", root=out.parent, nonfba_csv=None,
                            bom_csv=out / "bom_cost_product_with_kits.csv",
                            ref_map_csv=out / "item_refcode.csv",
                            bundle_csv=out / "product_bundles.csv",
                            kit_report_csv=out / "kit.csv",
                            out_dir=out / "fba_shadow" / "202608")


def test_fba_whitelist_auto_superset_when_only_buttons_differ(tmp_path):
    """同款只差有无扣（KS0001 vs KS0248）→ 自动映射 KS0001，标 auto_pref=superset。"""
    out = _setup(tmp_path)
    legacy = "RR1005SN10918RS-EU-FBA"
    _legacy_fixture(
        out, legacy, "三角无扣 荷兰绒 45cm 深蓝色 靠枕",
        bom_rows=[
            _bom_row("KS0001-HLR-45-DEEPBLUE", cost_fg=24, sx_cost_all=45, method="成品",
                     name="三角靠枕-荷兰绒-45-深蓝色"),
            _bom_row("KS0248-HLR-45-DEEPBLUE", cost_fg=22, sx_cost_all=44, method="成品",
                     name="三角靠枕无扣-荷兰绒-45-深蓝色"),
        ],
        ref_rows=[
            {"name": "KS0001-HLR-45-DEEPBLUE", "customer_code": "OTHER1",
             "item_group": "三角靠枕", "variant_of": "KS0001"},
            {"name": "KS0248-HLR-45-DEEPBLUE", "customer_code": "OTHER2",
             "item_group": "三角靠枕无扣", "variant_of": "KS0248"},
        ])
    res = _run(out)
    assert res.stats["fba_priced"] == 1
    assert res.stats["auto_mapped_skus"] == 1
    assert res.stats["whitelist_pending_skus"] == 0
    row = res.fba_rows[0]
    assert row["bridge_status"] == "ok"
    assert row["auto_pref"] == "superset"
    assert row["en_item_code"] == "KS0001-HLR-45-DEEPBLUE"
    assert float(row["绍兴二次加工成本*数量"]) == 105  # (45−24)×5
    assert float(row["皮壳成本*数量"]) == 120
    wl = pd.read_csv(out / "fba_shadow" / "202608" / "fba_whitelist_202608.csv",
                     dtype=str, keep_default_na=False)
    assert len(wl) == 1
    w = wl.iloc[0].to_dict()
    assert w["status"] == "auto_mapped"
    assert w["auto_pref"] == "superset"
    assert w["approved_item_code"] == "KS0001-HLR-45-DEEPBLUE"
    assert "KS0248-HLR-45-DEEPBLUE" in w["candidate_items"]
    assert int(w["candidate_count"]) == 2
    assert "KS0001" in w["note"]
    assert res.pending_rows == []


def test_fba_whitelist_multi_candidate_still_pending(tmp_path):
    """多候选但不是「只差有无扣」→ 不自动映射，交业务确认。"""
    out = _setup(tmp_path)
    legacy = "RR999SN10000RS-EU-FBA"
    _legacy_fixture(
        out, legacy, "三角有扣 荷兰绒 45cm 深蓝色 靠枕",
        bom_rows=[
            _bom_row("KS0002-HLR-45-DEEPBLUE", cost_fg=20, sx_cost_all=40, method="成品",
                     name="三角靠枕-荷兰绒-45-深蓝色"),
            _bom_row("KS0005-HLR-45-DEEPBLUE", cost_fg=21, sx_cost_all=41, method="成品",
                     name="三角靠枕-荷兰绒-45-深蓝色"),
        ],
        ref_rows=[
            {"name": "KS0002-HLR-45-DEEPBLUE", "customer_code": "OTHER1",
             "item_group": "三角靠枕", "variant_of": "KS0002"},
            {"name": "KS0005-HLR-45-DEEPBLUE", "customer_code": "OTHER2",
             "item_group": "三角靠枕", "variant_of": "KS0005"},
        ])
    res = _run(out)
    assert res.stats["fba_priced"] == 0
    assert res.stats["auto_mapped_skus"] == 0
    assert res.stats["whitelist_pending_skus"] == 1
    row = res.fba_rows[0]
    assert row["bridge_status"] == "pending"
    assert row["bridge_reason"] == "en_item_missing"
    assert row["皮壳成本"] == ""
    wl = pd.read_csv(out / "fba_shadow" / "202608" / "fba_whitelist_202608.csv",
                     dtype=str, keep_default_na=False)
    w = wl.iloc[0].to_dict()
    assert w["status"] == "needs_business_confirmation"
    assert w["approved_item_code"] == ""
    assert int(w["candidate_count"]) == 2
    assert "未自动映射" in w["note"]


def test_fba_whitelist_single_candidate_auto(tmp_path):
    """唯一候选且尺寸+面料+颜色全命中 → 自动映射，标 auto_pref=single_candidate。"""
    out = _setup(tmp_path)
    legacy = "RR1005SN10918RS-EU-FBA"
    _legacy_fixture(
        out, legacy, "三角无扣 荷兰绒 45cm 深蓝色 靠枕",
        bom_rows=[_bom_row("KS0248-HLR-45-DEEPBLUE", cost_fg=22, sx_cost_all=44,
                           method="成品", name="三角靠枕无扣-荷兰绒-45-深蓝色")],
        ref_rows=[{"name": "KS0248-HLR-45-DEEPBLUE", "customer_code": "OTHER2",
                   "item_group": "三角靠枕无扣", "variant_of": "KS0248"}])
    res = _run(out)
    assert res.stats["whitelist_skus"] == 1
    assert res.stats["whitelist_qty"] == 5
    assert res.stats["fba_priced"] == 1
    assert res.stats["auto_mapped_skus"] == 1
    assert res.stats["whitelist_pending_skus"] == 0
    row = res.fba_rows[0]
    assert row["bridge_status"] == "ok"
    assert row["auto_pref"] == "single_candidate"
    assert row["en_item_code"] == "KS0248-HLR-45-DEEPBLUE"
    assert float(row["绍兴二次加工成本*数量"]) == 110  # (44−22)×5
    wl = pd.read_csv(out / "fba_shadow" / "202608" / "fba_whitelist_202608.csv",
                     dtype=str, keep_default_na=False)
    w = wl.iloc[0].to_dict()
    assert w["status"] == "auto_mapped"
    assert w["auto_pref"] == "single_candidate"
    assert w["approved_item_code"] == "KS0248-HLR-45-DEEPBLUE"
    assert w["approved_by"] == "auto:single_candidate"
    assert "尺寸+面料+颜色" in w["candidate_basis"]
    assert "强依据" in w["note"]
    template = out / "fba_shadow" / "fba_whitelist_template.csv"
    assert template.exists()
    assert legacy in pd.read_csv(template, dtype=str, keep_default_na=False)["sku"].tolist()
    sku_summary = out / "fba_shadow" / "fba_whitelist_skus.csv"
    assert sku_summary.exists()
    skus = pd.read_csv(sku_summary, dtype=str, keep_default_na=False)
    assert skus["sku"].tolist() == [legacy]
    assert float(skus.iloc[0]["qty"]) == 5
    assert skus.iloc[0]["status"] == "auto_mapped"
    assert skus.iloc[0]["auto_pref"] == "single_candidate"


def test_fba_whitelist_single_candidate_weak_basis_not_auto(tmp_path):
    """唯一候选但尺寸未命中（非强依据）→ 不自动映射，仍待业务确认。"""
    out = _setup(tmp_path)
    legacy = "RR111SN10000RS-EU-FBA"
    _legacy_fixture(
        out, legacy, "三角有扣 荷兰绒 70cm 深蓝色 靠枕",
        bom_rows=[_bom_row("KS0005-HLR-60-DEEPBLUE", cost_fg=22, sx_cost_all=44,
                           method="成品", name="三角靠枕-荷兰绒-60-深蓝色")],
        ref_rows=[{"name": "KS0005-HLR-60-DEEPBLUE", "customer_code": "OTHER",
                   "item_group": "三角靠枕", "variant_of": "KS0005"}])
    res = _run(out)
    assert res.stats["fba_priced"] == 0
    assert res.stats["auto_mapped_skus"] == 0
    assert res.stats["whitelist_pending_skus"] == 1
    w = res.fba_rows[0]
    assert w["bridge_status"] == "pending"
    wl = pd.read_csv(out / "fba_shadow" / "202608" / "fba_whitelist_202608.csv",
                     dtype=str, keep_default_na=False)
    row = wl.iloc[0].to_dict()
    assert row["status"] == "needs_business_confirmation"
    assert row["auto_pref"] == ""
    assert row["approved_item_code"] == ""
    assert "尺寸+面料+颜色" not in row["candidate_basis"]


def test_fba_whitelist_alias_auto_pref(tmp_path):
    """已登记别名（归一化后）直接命中 → auto_pref=alias，优先于候选推断。"""
    out = _setup(tmp_path)
    legacy = "RR-LEGACY-ALIAS-1"
    _legacy_fixture(
        out, legacy, "三角有扣 荷兰绒 45cm 深蓝色 靠枕",
        bom_rows=[_bom_row("KS-ALIAS-HLR-45-DEEPBLUE", cost_fg=10, sx_cost_all=14,
                           method="成品", name="三角靠枕-荷兰绒-45-深蓝色")],
        ref_rows=[{"name": "KS-ALIAS-HLR-45-DEEPBLUE",
                   "customer_code": f"OTHER-SKU,{legacy}",
                   "item_group": "三角靠枕", "variant_of": "KS-ALIAS"}])
    res = _run(out)
    assert res.stats["fba_priced"] == 1
    assert res.stats["auto_alias_skus"] == 1
    row = res.fba_rows[0]
    assert row["bridge_status"] == "ok"
    assert row["auto_pref"] == "alias"
    assert row["en_item_code"] == "KS-ALIAS-HLR-45-DEEPBLUE"
    assert float(row["绍兴二次加工成本*数量"]) == 20  # (14−10)×5
    wl = pd.read_csv(out / "fba_shadow" / "202608" / "fba_whitelist_202608.csv",
                     dtype=str, keep_default_na=False)
    w = wl.iloc[0].to_dict()
    assert w["status"] == "auto_mapped"
    assert w["auto_pref"] == "alias"
    assert w["approved_by"] == "auto:alias"
    assert "别名" in w["note"]
