# -*- coding: utf-8 -*-
"""Phase 4.0 测试：run 包 / canary / 门禁 / 回读 / 排除与利润空白。"""
from __future__ import annotations

import sys
from pathlib import Path

import pandas as pd
import pytest

_ROOT = Path(__file__).resolve().parents[1]
if str(_ROOT) not in sys.path:
    sys.path.insert(0, str(_ROOT))

from tongtool_order_cost.tongtu_cost_engine.domain.bom_cost import Phase2Result  # noqa: E402
from tongtool_order_cost.tongtu_cost_engine.domain.run_package import (  # noqa: E402
    build_run_package,
)
from tongtool_order_cost.tongtu_cost_engine.domain.split_merge import (  # noqa: E402
    MergeShadowResult,
)
from tongtool_order_cost.tongtu_cost_engine.domain.writeback_rehearsal import (  # noqa: E402
    WritebackRehearsal,
)

TEMPLATE = [
    "订单号", "平台SKU", "平台SKU_统一", "通途SKU", "发货数量",
    "皮壳成本", "头程运费金额", "二次加工成本", "绍兴二次加工成本",
    "皮壳成本*数量", "头程运费*数量", "二次加工成本*数量", "绍兴二次加工成本*数量",
    "订单利润",
]


def _row(order, sku, status="ok", profit="10", reason="", bucket="USNJ"):
    return {
        "订单号": order, "订单号_公共部分": order,
        "平台SKU": "PSK", "平台SKU_统一": "PSK", "通途SKU": sku,
        "发货数量": "1",
        "item_fg": "ITEM1", "method": "成品", "method_source": "en", "cost_status": status,
        "cost_reason": "", "derived_reason": reason,
        "订单利润": profit, "订单总成本": "5" if profit else "",
        "皮壳成本": "10", "头程运费金额": "2", "二次加工成本": "3",
        "绍兴二次加工成本": "1",
        "皮壳成本*数量": "10", "头程运费*数量": "2",
        "二次加工成本*数量": "3", "绍兴二次加工成本*数量": "1",
        "revenue_available": "是" if profit else "否",
        "warehouse_bucket": bucket,
    }


def _rehearsal():
    rows = [
        _row("O1", "S1"),
        _row("O2", "S2", status="non_product_accessory", profit="",
             reason="非商品配件：零成本，不参与订单成本"),
        _row("O3", "S3", profit="", reason="订单利润:收入不可得"),
        _row("O4", "S4", bucket="USTX"),
    ]
    for r in rows[1:3]:  # 非商品配件四列必须 0
        if r["cost_status"] == "non_product_accessory":
            for c in ("皮壳成本", "头程运费金额", "二次加工成本", "绍兴二次加工成本",
                      "皮壳成本*数量", "头程运费*数量", "二次加工成本*数量", "绍兴二次加工成本*数量"):
                r[c] = "0"
    p2_rows = [
        {"warehouse_bucket": "USNJ", "item_fg": "ITEM1", "method": "成品",
         "method_source": "en", "merged": False, "SKU": "S1"},
        {"warehouse_bucket": "USNJ", "item_fg": "ITEM1", "method": "成品",
         "method_source": "en", "merged": False, "SKU": "S2"},
        {"warehouse_bucket": "USNJ", "item_fg": "ITEM1", "method": "成品",
         "method_source": "en", "merged": False, "SKU": "S3"},
        {"warehouse_bucket": "USTX", "item_fg": "ITEM1", "method": "成品",
         "method_source": "en", "merged": False, "SKU": "S4"},
    ]
    shadow = MergeShadowResult(
        month="202608", rows=[], aux_rows=[], aux_entries=[], aux_table=[],
        groups=[], blocked=[], sku_issues=[],
        shadow_rows=[], detail_rows=[], sku_coverage=[], detail_columns=[], assertions=[], stats={},
    )
    phase2 = Phase2Result(rows=p2_rows, assertions=[], stats={})
    rehearsal = WritebackRehearsal(
        month="202608", template_columns=TEMPLATE, rows=rows, assertions=[],
        stats={}, diff_breakdown=[], mapping_comparison=[],
    )
    return shadow, phase2, rehearsal


def _inputs(tmp_path: Path):
    files = {}
    for name, header in {
        "orders": "订单号,平台SKU,通途SKU\n",
        "en_items": "order_id_code,tongtool_sku,shipping_method\n",
        "bom_kits": "item_fg,cost_fg\n",
        "wh_map": "name\twarehouse_classification\nWH1\tUSNJ分公司\n",
        "item_refcode": "name,customer_code,variant_of\n",
        "flags": "order_id_code,invalid\n",
        "kit_report": "item_fg,cost_fg\n",
        "branch_map": "name\tbranch\tparent\n",
    }.items():
        p = tmp_path / f"{name}.csv"
        p.write_text(header, encoding="utf-8")
        if name == "wh_map" or name == "branch_map":
            p = tmp_path / f"{name}.tsv"
            p.write_text(header, encoding="utf-8")
        files[name] = p
    bom = tmp_path / "bom_kits.csv"
    pd.DataFrame([{
        "item_fg": "ITEM1", "shipping_method": "成品", "cost_fg": 10,
        "cost_sxbzbcp": 0, "cost_sxbzcp": 1, "sx_cost_all": 11,
        "usnj_valuation_rate": 3, "ustx_valuation_rate": 0, "pl_valuation_rate": 0,
        "cover_freight_2kk9fsq8ln": 0, "sfg_freight_2kk9fsq8ln": 0,
        "freight_2kk9fsq8ln": 2,
    }]).to_csv(bom, index=False, encoding="utf-8")
    files["bom_kits"] = bom
    bundles = tmp_path / "product_bundles.csv"
    pd.DataFrame([{"bundle_item": "TJ#X", "component_item": "C1", "qty": 1,
                   "bundle_version": "v1|abc"}]).to_csv(bundles, index=False, encoding="utf-8")
    files["product_bundles"] = bundles
    old = tmp_path / "old_wb.csv"
    pd.DataFrame([
        {"订单号": "O1", "订单号_公共部分": "O1", "平台SKU": "PSK", "平台SKU_统一": "PSK",
         "通途SKU": "S1", "发货数量": "1", "皮壳成本": "9", "头程运费金额": "1",
         "二次加工成本": "3", "绍兴二次加工成本": "1", "发货仓按销售汇总分类": "USNJ分公司"},
        {"订单号": "O2", "订单号_公共部分": "O2", "平台SKU": "PSK", "平台SKU_统一": "PSK",
         "通途SKU": "S2", "发货数量": "1", "皮壳成本": "0", "头程运费金额": "0",
         "二次加工成本": "0", "绍兴二次加工成本": "0", "发货仓按销售汇总分类": "USNJ分公司"},
        {"订单号": "O3", "订单号_公共部分": "O3", "平台SKU": "PSK", "平台SKU_统一": "PSK",
         "通途SKU": "S3", "发货数量": "1", "皮壳成本": "10", "头程运费金额": "2",
         "二次加工成本": "3", "绍兴二次加工成本": "1", "发货仓按销售汇总分类": "USNJ分公司"},
    ]).to_csv(old, index=False, encoding="utf-8")
    files["old_writeback"] = old
    return files, old


def test_run_package_canary_outputs_and_readback(tmp_path):
    shadow, phase2, rehearsal = _rehearsal()
    inputs, old = _inputs(tmp_path)
    package = build_run_package(
        shadow, phase2, rehearsal, input_paths=inputs,
        runs_root=tmp_path / "runs", month="202608", bucket="USNJ",
        old_writeback_csv=old, run_id="test-run-1",
    )
    assert package.ok
    assert package.run_dir.exists()
    for name in ("manifest.json", "audit.log", "summary.md", "diff.xlsx"):
        assert (package.run_dir / name).exists()
    canary = package.run_dir / "writeback_canary_202608_USNJ.csv"
    df = pd.read_csv(canary, dtype=str, keep_default_na=False)
    assert len(df) == 3                # USTX 行不进入 canary
    excluded = df[df["cost_status"] == "excluded_non_product"]
    assert len(excluded) == 1
    assert all(excluded[c].iloc[0] == "0" for c in
               ("皮壳成本", "头程运费金额", "二次加工成本", "绍兴二次加工成本"))
    assert package.summary["accessory_check"]["four_zero"] is True
    assert package.summary["profit_blank"]["rows"] == 2  # 非商品配件 + 显式利润空白
    assert package.summary["profit_blank"]["not_zero"] is True
    assert package.summary["row_match"]["matched"] == 3
    assert all(c["status"] == "pass" for c in package.readback)
    # manifest hashes / version
    import json
    manifest = json.loads((package.run_dir / "manifest.json").read_text(encoding="utf-8"))
    assert all("sha256" in v for v in manifest["inputs"].values())
    assert manifest["bundle_versions"] == ["v1|abc"]
    assert manifest["month_end"] == "2026-08-31"


def test_run_package_immutable_and_duplicate(tmp_path):
    shadow, phase2, rehearsal = _rehearsal()
    inputs, old = _inputs(tmp_path)
    kwargs = dict(input_paths=inputs, runs_root=tmp_path / "runs", month="202608",
                  bucket="USNJ", old_writeback_csv=old)
    build_run_package(shadow, phase2, rehearsal, run_id="run-a", **kwargs)
    with pytest.raises(FileExistsError):
        build_run_package(shadow, phase2, rehearsal, run_id="run-a", **kwargs)
    with pytest.raises(RuntimeError):
        build_run_package(shadow, phase2, rehearsal, run_id="run-b", **kwargs)


def test_run_package_dimensions(tmp_path):
    shadow, phase2, rehearsal = _rehearsal()
    inputs, old = _inputs(tmp_path)
    package = build_run_package(
        shadow, phase2, rehearsal, input_paths=inputs,
        runs_root=tmp_path / "runs", month="202608", bucket="USNJ",
        old_writeback_csv=old, run_id="run-d",
    )
    layers = {l["layer"]: l for l in package.amount_layers}
    assert "非商品配件" in layers
    assert layers["非商品配件"]["diff_皮壳成本"] == 0
    assert package.column_diffs is not None
    assert (package.run_dir / "diff.xlsx").exists()
