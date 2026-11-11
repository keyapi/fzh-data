# -*- coding: utf-8 -*-
"""Phase 3.8 build-order-tabs 单元测试：FBA 展开 / 78 列映射 / 属性解析 / 仓库映射。"""
from __future__ import annotations

import sys
from pathlib import Path

import pandas as pd

_ROOT = Path(__file__).resolve().parents[1]
if str(_ROOT) not in sys.path:
    sys.path.insert(0, str(_ROOT))

from tongtool_order_cost.tongtu_cost_engine.domain.build_tabs import (  # noqa: E402
    _build_fba_rows,
    _cost_gates,
    _fba_to_merged,
    _parse_bom_attrs,
    _parse_name_attrs,
    _self_to_merged,
    _source_indices,
    _uuid_for,
    _warehouse_source,
)
from tongtool_order_cost.tongtu_cost_engine.domain.fba_shadow import (  # noqa: E402
    fba_cache_key,
    fba_input_paths,
    fba_manifest_path,
    validate_fba_cache,
)


def _num(s: object) -> float:
    try:
        return float(str(s))
    except (TypeError, ValueError):
        return 0.0


def test_source_indices_handles_merged_and_single() -> None:
    assert _source_indices("3") == [3]
    assert _source_indices("3, 5,7") == [3, 5, 7]
    assert _source_indices("") == []


def test_parse_bom_attrs_splits_category_fabric_size() -> None:
    attrs = _parse_bom_attrs({
        "item_zlmb_name": "重量模板#身体支撑阅读枕-涤麻-92x56x75cm",
        "item_fg_name": "身体支撑阅读枕-涤麻-92x56x75cm-灰色",
    })
    assert attrs["品类"] == "身体支撑阅读枕"
    assert attrs["面料提取"] == "涤麻"
    assert attrs["材料名称"] == "涤麻"
    assert attrs["尺寸"] == "92"
    assert attrs["带*尺寸"] == "92*56*75"
    assert attrs["尺寸先大后小"] == "92*75*56"
    assert "有无扣" not in attrs


def test_parse_bom_attrs_triangle_buttons() -> None:
    attrs = _parse_bom_attrs({"item_zlmb_name": "重量模板#三角靠枕无扣-纯棉麻-60"})
    assert attrs["品类"] == "三角靠枕无扣"
    assert attrs["面料提取"] == "纯棉麻"
    assert attrs["尺寸"] == "60"
    assert attrs["有无扣"] == "无扣"


def test_parse_name_attrs_fallback() -> None:
    attrs = _parse_name_attrs("三角有扣 纯棉平绒 100cm 黑色 靠枕 wow SET2")
    assert attrs["有无扣"] == "有扣"
    assert attrs["尺寸"] == "100"
    assert attrs["件套"] == "SET2"


def test_warehouse_source_exact_and_multichannel() -> None:
    sources = {
        "CENTRADE": {"发货仓库": "CENTRADE", "成本来源编码": "COST-US",
                     "发货仓分类": "分公司"},
        "美国多渠道仓库": {"发货仓库": "美国多渠道仓库", "成本来源编码": "COST-USFBA",
                          "发货仓分类": "FBA"},
        "德国FBA仓": {"发货仓库": "德国FBA仓", "成本来源编码": "COST-EUFBA",
                      "发货仓分类": "FBA"},
    }
    assert _warehouse_source("CENTRADE", sources)["成本来源编码"] == "COST-US"
    assert _warehouse_source("德国FBA仓", sources)["成本来源编码"] == "COST-EUFBA"
    assert _warehouse_source("不存在仓", sources) == {}


def _gs_row(**over):
    row = {
        "图片": "", "MSKU": "MSKU-A", "SKU": "SKU-A", "品类": "自产-三角靠枕-涤麻",
        "产品名称": "三角无扣 涤麻 60cm 灰色 靠枕", "站点": "AMZDE", "开发人员": "",
        "订单数量": "3", "销量": "5", "上期销量": "4", "销量环比": "25%",
        "销量占比": "1%", "销售额": "500", "上期销售额": "400", "销售额环比": "25%",
        "销售额占比": "2%", "成本": "1", "订单费用": "2", "头程费用": "3",
        "自定义费用": "4", "利润": "5", "上期利润": "6", "利润环比": "7%",
        "利润占比": "8%", "利润率": "9%",
    }
    row.update(over)
    return row


def _shadow_row(**over):
    row = {
        "site": "AMZDE", "gs_msku": "MSKU-A", "gs_sku": "SKU-A",
        "bridge_status": "ok",
        "品类orig": "自产-三角靠枕-涤麻", "品类": "三角靠枕", "品类统一名": "三角靠枕",
        "面料提取": "涤麻", "材料编码": "ML-DM", "尺寸": "60", "有无扣": "无扣",
        "品类编码": "SX-KZSJ", "品类尺寸编码": "SX-KZSJ-60",
        "品类尺寸面料编码": "KS0001-DM-60-GREY", "产品名称": "三角无扣 涤麻 60cm 灰色 靠枕",
        "渠道": "亚马逊", "渠道账号": "AMZDE", "发货仓库": "德国FBA仓",
        "对应成本工作簿": "欧洲FBA", "成本来源编码": "COST-EUFBA", "发货仓分类": "FBA",
        "头程运费来源编码": "HEAD-EUFBA", "二次加工成本来源编码": "2CJG-SX",
        "发货区域": "欧洲", "发货仓按销售汇总分类": "欧洲FBA",
        "是否皮壳": "皮壳",
        "皮壳成本": "10", "绍兴二次加工成本": "20", "二次加工成本": "0",
        "头程运费金额": "1", "运费": "0",
        "皮壳含包装成本": "10", "皮壳不含包装成本": "9.5",
        "海外仓成本": "",
    }
    row.update(over)
    return row


def test_fba_expands_by_order_qty_and_zeroes_placeholders() -> None:
    gs = pd.DataFrame([_gs_row()])
    shadow = pd.DataFrame([_shadow_row()])
    rows, checks, stats = _build_fba_rows("202608", gs, shadow)
    assert len(rows) == 3
    assert stats["rows"] == 3
    assert not checks
    first, rest = rows[0], rows[1:]
    assert first["订单数量"] == "1"
    assert _num(first["销量"]) == 5
    assert _num(first["销售额"]) == 500
    assert _num(first["售价*汇率"]) == 500
    assert _num(first["发货数量"]) == 5
    assert _num(first["皮壳成本"]) == 10
    assert _num(first["皮壳成本*数量"]) == 50
    assert _num(first["绍兴二次加工成本*数量"]) == 100
    assert _num(first["1件产品成本"]) == 30
    assert _num(first["头程运费*数量"]) == 5
    assert _num(first["订单总成本"]) == 155
    assert _num(first["订单利润"]) == 345
    assert first["绍兴成本系数"] == "1"
    # 占位行：量/额为零，单位成本保留
    for r in rest:
        assert _num(r["销量"]) == 0
        assert _num(r["销售额"]) == 0
        assert _num(r["发货数量"]) == 0
        assert _num(r["皮壳成本"]) == 10
        assert _num(r["皮壳成本*数量"]) == 0
        assert _num(r["订单总成本"]) == 0
        assert _num(r["订单利润"]) == 0
    # index_col 连续、UUID 稳定
    assert [r["index_col"] for r in rows] == ["0", "1", "2"]
    assert rows[0]["订单号"] == _uuid_for("202608", "AMZDE", "MSKU-A", "SKU-A", 0)
    assert len({r["订单号"] for r in rows}) == 3


def test_fba_missing_shadow_blocks_costs() -> None:
    gs = pd.DataFrame([_gs_row()])
    rows, checks, stats = _build_fba_rows("202608", gs, pd.DataFrame())
    assert len(rows) == 3
    assert stats["missing_shadow"] == 1
    assert stats["cost_blocked"] == 3
    assert rows[0]["订单总成本"] == ""
    assert not checks  # 阻断行不做恒等校验


def test_fba_cache_rejects_stale_bom(tmp_path) -> None:
    out = tmp_path / "out"
    out.mkdir()
    for name in ("bom_cost_product_with_kits.csv", "item_refcode.csv",
                 "product_bundles.csv", "en_items_all_089.csv",
                 "raw_fba_202608.csv", "fba_export_202608.csv"):
        (out / name).write_text("x\n1\n", encoding="utf-8")
    shadow_dir = out / "fba_shadow" / "202608"
    shadow_dir.mkdir(parents=True)
    shadow = shadow_dir / "fba_shadow_202608.csv"
    shadow.write_text("h\n1\n", encoding="utf-8")
    paths = fba_input_paths("202608", tmp_path)
    manifest = {
        "month": "202608",
        "cache_key": fba_cache_key("202608", paths),
        "inputs": {
            name: {"path": str(p), "sha256": __import__("hashlib").sha256(p.read_bytes()).hexdigest()}
            for name, p in paths.items()
        },
    }
    fba_manifest_path(shadow_dir, "202608").write_text(
        __import__("json").dumps(manifest), encoding="utf-8")
    ok, reason = validate_fba_cache(shadow, "202608", root=tmp_path)
    assert ok, reason
    # BOM 变化 → 缓存必须失效
    (out / "bom_cost_product_with_kits.csv").write_text("x\n2\n", encoding="utf-8")
    ok, reason = validate_fba_cache(shadow, "202608", root=tmp_path)
    assert not ok
    assert "cache_key_mismatch" in reason and "bom" in reason


def test_fba_cache_missing_manifest_invalid(tmp_path) -> None:
    out = tmp_path / "out"
    out.mkdir()
    shadow_dir = out / "fba_shadow" / "202608"
    shadow_dir.mkdir(parents=True)
    shadow = shadow_dir / "fba_shadow_202608.csv"
    shadow.write_text("h\n1\n", encoding="utf-8")
    ok, reason = validate_fba_cache(shadow, "202608", root=tmp_path)
    assert not ok
    assert reason == "manifest_missing"


def test_cost_gates_fail_on_blocked_or_missing_shadow() -> None:
    good = _cost_gates({"cost_blocked": 0}, {"cost_blocked": 0, "missing_shadow": 0})
    assert all(g["status"] == "pass" for g in good)
    bad_self = _cost_gates({"cost_blocked": 3}, {"cost_blocked": 0, "missing_shadow": 0})
    assert any(g["name"] == "self 成本阻断=0" and g["status"] == "fail" for g in bad_self)
    # Codex 场景：shadow 只有表头，133 SKU / 1,269 行全部阻断 → 必须失败
    bad_fba = _cost_gates({"cost_blocked": 0},
                          {"cost_blocked": 1269, "missing_shadow": 133})
    assert any(g["name"] == "FBA 成本阻断=0" and g["status"] == "fail" for g in bad_fba)
    assert any(g["name"] == "FBA shadow 已校验" and g["status"] == "fail" for g in bad_fba)


def test_fba_index_col_runs_globally_across_groups() -> None:
    gs = pd.DataFrame([
        _gs_row(MSKU="A", SKU="A", 订单数量="2"),
        _gs_row(MSKU="B", SKU="B", 订单数量="2"),
    ])
    shadow = pd.DataFrame([
        _shadow_row(gs_msku="A", gs_sku="A"),
        _shadow_row(gs_msku="B", gs_sku="B"),
    ])
    rows, _, _ = _build_fba_rows("202608", gs, shadow)
    assert [r["index_col"] for r in rows] == ["0", "1", "2", "3"]


def test_fba_to_merged_mapping() -> None:
    row = {
        "订单号": "u1", "MSKU": "M1", "SKU": "S1", "销售额": "123",
        "售价*汇率": "123", "发货数量": "2", "皮壳成本": "10",
        "渠道": "亚马逊", "渠道账号": "AMZDE",
    }
    out = _fba_to_merged(row)
    assert out["订单号"] == "u1"
    assert out["平台SKU"] == "M1"
    assert out["通途SKU"] == "S1"
    assert out["售价"] == ""
    assert out["汇率"] == ""
    assert out["运营部当月是否新品"] == ""
    assert out["售价*汇率"] == "123"
    assert out["发货数量"] == "2"
    assert out["皮壳成本"] == "10"


def test_self_to_merged_blanks_non_contract_columns() -> None:
    out = _self_to_merged({"订单号": "o1", "平台SKU": "p1", "通途SKU": "s1",
                           "售价*汇率": "88", "图片": "x", "运营部当月是否新品": "y"})
    assert out["订单号"] == "o1"
    assert out["售价*汇率"] == "88"
    assert out["图片"] == ""
    assert out["运营部当月是否新品"] == ""
