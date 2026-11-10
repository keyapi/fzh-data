# -*- coding: utf-8 -*-
"""Phase 3.0 测试：写回演练（模板/阻断留空/映射/血缘/差异归因）。"""
from __future__ import annotations

import sys
from pathlib import Path

import pandas as pd
import pytest

_ROOT = Path(__file__).resolve().parents[1]
if str(_ROOT) not in sys.path:
    sys.path.insert(0, str(_ROOT))

from tongtool_order_cost.tongtu_cost_engine.domain.bom_cost import compute_phase2  # noqa: E402
from tongtool_order_cost.tongtu_cost_engine.domain.split_merge import run_merge_shadow  # noqa: E402
from tongtool_order_cost.tongtu_cost_engine.domain.writeback_rehearsal import (  # noqa: E402
    build_writeback_rehearsal,
    render_markdown,
    write_csv,
    write_xlsx,
)

ORDER_HEADER = ["订单号", "平台SKU", "通途SKU", "发货数量", "售价", "售价(人民币)",
                "运费", "发货仓库", "收入(人民币)", "包裹总运费"]
EN_HEADER = ["order_id_code", "tongtool_sku", "erp_item_code", "quantity",
             "shipping_method", "despatch_complete_time"]
WB_HEADER = [
    "订单号", "平台SKU", "通途SKU", "发货数量",
    "皮壳成本", "头程运费金额", "二次加工成本", "绍兴二次加工成本",
    "成本来源编码", "运费", "订单号_公共部分", "平台SKU_统一", "皮壳成本*数量",
    "头程运费*数量", "二次加工成本*数量", "绍兴二次加工成本*数量",
    "1件产品成本", "产品成本*数量", "订单总成本", "订单利润",
]
BOM_NUMERIC = [
    "cost_fg", "cost_sxbzbcp", "cost_sxbzcp", "sx_cost_all",
    "usnj_valuation_rate", "ustx_valuation_rate", "pl_valuation_rate",
    "cover_freight_2kk9fsq8ln", "sfg_freight_2kk9fsq8ln", "freight_2kk9fsq8ln",
    "cover_freight_e5asph24tk", "sfg_freight_e5asph24tk", "freight_e5asph24tk",
    "cover_freight_tmvvepd80f", "sfg_freight_tmvvepd80f", "freight_tmvvepd80f",
    "freight_9rr7m7g3aj", "freight_88hko2ad7l", "freight_0hn57vpr4u", "freight_3s2n1bnpbj",
]
BOM_HEADER = ["item_fg", "shipping_method"] + BOM_NUMERIC

ITEMS = [
    {"name": "KS100-FINISH-RED", "customer_code": "TT001-FIN-Cover,TT001-FIN-Foam",
     "item_group": "靠枕", "variant_of": "KS100"},
    {"name": "KS200-OTHER", "customer_code": "TT777", "item_group": "其它", "variant_of": "KS200"},
]


def _write_items(tmp_path: Path) -> Path:
    path = tmp_path / "items.csv"
    pd.DataFrame(ITEMS, columns=["name", "customer_code", "item_group", "variant_of"]).to_csv(
        path, index=False, encoding="utf-8")
    return path


def _write_orders(tmp_path: Path, rows) -> Path:
    full = []
    for r in rows:
        r = list(r)
        while len(r) < len(ORDER_HEADER):
            r.append("")
        full.append(r)
    path = tmp_path / "orders.csv"
    pd.DataFrame(full, columns=ORDER_HEADER).to_csv(path, index=False, encoding="utf-8")
    return path


def _write_en(tmp_path: Path, rows) -> Path:
    path = tmp_path / "en.csv"
    pd.DataFrame([list(r) + [""] for r in rows], columns=EN_HEADER).to_csv(
        path, index=False, encoding="utf-8")
    return path


def _write_bom(tmp_path: Path, rows) -> Path:
    full = []
    for row in rows:
        rec = {c: "0" for c in BOM_NUMERIC}
        rec.update({"item_fg": row["item_fg"], "shipping_method": row.get("shipping_method", "")})
        rec.update({k: str(v) for k, v in row.items()})
        full.append(rec)
    path = tmp_path / "bom.csv"
    pd.DataFrame(full, columns=BOM_HEADER).to_csv(path, index=False, encoding="utf-8")
    return path


def _write_wh(tmp_path: Path) -> Path:
    path = tmp_path / "wh.tsv"
    path.write_text(
        "name\twarehouse_classification\nWH1\tUSTX美中分公司\nWH-NJ\tUSNJ美东分公司\n",
        encoding="utf-8",
    )
    return path


def _write_old_wb(tmp_path: Path, rows) -> Path:
    path = tmp_path / "old_wb.csv"
    pd.DataFrame(rows, columns=WB_HEADER).to_csv(path, index=False, encoding="utf-8")
    return path


def _case(tmp_path, *, missing_ks200=False):
    items = _write_items(tmp_path)
    orders = _write_orders(tmp_path, [
        ["ORD-1000001_1", "PSK", "TT001-FIN-Cover", 1, 10, 50, "", "WH1", "", "2"],
        ["ORD-1000001_1", "PSK", "TT001-FIN-Foam", 1, 0, 0, "", "WH1", "", "0"],
        ["ORD-1000001_2", "PSK", "TT001-FIN-Cover", 1, 10, 50, "", "WH1", "", "2"],
        ["ORD-1000001_2", "PSK", "TT001-FIN-Foam", 1, 0, 0, "", "WH1", "", "0"],
        ["ORD-1000001", "PSK", "TT777", 3, 10, 50, "", "WH-NJ", "", "6"],
    ])
    en = _write_en(tmp_path, [
        ["ORD-1000001_1", "TT001-FIN-Cover", "", 1, "半成品"],
        ["ORD-1000001_1", "TT001-FIN-Foam", "", 1, "半成品"],
        ["ORD-1000001_2", "TT001-FIN-Cover", "", 1, "半成品"],
        ["ORD-1000001_2", "TT001-FIN-Foam", "", 1, "半成品"],
        ["ORD-1000001", "TT777", "", 3, "成品"],
    ])
    shadow = run_merge_shadow(orders, items, en, None, month="202608")
    bom_rows = [{
        "item_fg": "KS100-FINISH-RED", "shipping_method": "半成品",
        "cost_fg": 10, "cost_sxbzbcp": 2, "cost_sxbzcp": 5,
        "ustx_valuation_rate": 3,
        "cover_freight_e5asph24tk": 1, "sfg_freight_e5asph24tk": 4,
        "freight_e5asph24tk": 9,
    }]
    if not missing_ks200:
        bom_rows.append({
            "item_fg": "KS200-OTHER", "shipping_method": "成品",
            "cost_fg": 5, "cost_sxbzcp": 1, "usnj_valuation_rate": 2,
            "cover_freight_2kk9fsq8ln": 3, "freight_2kk9fsq8ln": 7,
        })
    bom = _write_bom(tmp_path, bom_rows)
    p2 = compute_phase2(shadow, bom, items, _write_wh(tmp_path))
    old = _write_old_wb(tmp_path, [
        # 合并组来源子单：成本来源编码一致、运费冲突（5 vs 7）
        ["ORD-1000001_1", "PSK", "TT001-FIN-Cover", 1, 99, 99, 99, 99,
         "COST-US", "5", "ORD-1000001", "PSK", "99", "99", "99", "99", "99", "99", "99", "99"],
        ["ORD-1000001_2", "PSK", "TT001-FIN-Cover", 1, 99, 99, 99, 99,
         "COST-US", "7", "ORD-1000001", "PSK", "99", "99", "99", "99", "99", "99", "99", "99"],
        # 透传行
        ["ORD-1000001", "PSK", "TT777", 3, 99, 99, 99, 99,
         "COST-US", "3", "ORD-1000001", "PSK", "99", "99", "99", "99", "99", "99", "99", "99"],
    ])
    rehearsal = build_writeback_rehearsal(
        shadow, p2, old, month="202608", disabled_items={"KS200-OTHER"},
    )
    return shadow, p2, rehearsal


def test_rehearsal_rows_and_lineage(tmp_path):
    shadow, p2, rehearsal = _case(tmp_path)
    assert rehearsal.ok, [a for a in rehearsal.assertions if a.status == "fail"]
    assert len(rehearsal.rows) == len(shadow.detail_rows) == 2
    merged = next(r for r in rehearsal.rows if r["merged"])
    passthru = next(r for r in rehearsal.rows if not r["merged"])
    assert merged["group_id"] == "G0001"
    assert merged["source_row"] == "0,1,2,3"
    assert merged["pieces"] == "2.0"
    assert merged["method"] == "半成品"
    assert passthru["source_row"] == "4"
    assert passthru["group_id"] == ""
    assert all(r["lineage_status"] == "ok" for r in rehearsal.rows)
    assert rehearsal.stats["lineage_fail"] == 0
    by_name = {a.name: a for a in rehearsal.assertions}
    assert by_name["per_unit×数量=Phase2合计"].status == "pass"
    assert by_name["1件成本=四列(除头程)之和"].status == "pass"
    assert rehearsal.stats["per_unit_fail_rows"] == 0
    assert rehearsal.stats["one_piece_fail_rows"] == 0


def test_rehearsal_costs_from_phase2_not_old(tmp_path):
    _, _, rehearsal = _case(tmp_path)
    merged = next(r for r in rehearsal.rows if r["merged"])
    passthru = next(r for r in rehearsal.rows if not r["merged"])
    # 四列是单位成本：Phase2 合计 / 行数量（合并行数量=pieces）
    assert merged["发货数量"] == "2"          # pieces
    assert merged["皮壳成本"] == "10"
    assert merged["头程运费金额"] == "4"
    assert merged["二次加工成本"] == "3"
    assert merged["绍兴二次加工成本"] == "2"
    assert merged["皮壳成本*数量"] == "20"
    assert merged["头程运费*数量"] == "8"
    assert merged["二次加工成本*数量"] == "6"
    assert merged["绍兴二次加工成本*数量"] == "4"
    assert merged["1件产品成本"] == "15"      # 10 + 3 + 2（不含头程）
    assert merged["产品成本*数量"] == "30"
    assert passthru["皮壳成本"] == "5"
    assert passthru["头程运费金额"] == "7"
    assert passthru["二次加工成本"] == "0"   # 分公司发成品：目的地加工=0
    assert passthru["绍兴二次加工成本"] == "1"
    assert passthru["皮壳成本*数量"] == "15"
    assert passthru["1件产品成本"] == "6"
    # 旧写回 99 不得被沿用
    assert "99" not in (merged["皮壳成本"], passthru["皮壳成本"])


def test_blocked_row_four_columns_blank_and_reason(tmp_path):
    _, _, rehearsal = _case(tmp_path, missing_ks200=True)
    blocked = [r for r in rehearsal.rows if r["cost_status"] == "blocked"]
    assert len(blocked) == 1
    row = blocked[0]
    for col in ("皮壳成本", "头程运费金额", "二次加工成本", "绍兴二次加工成本"):
        assert row[col] == ""
    assert row["cost_reason"] == "bom_item_missing"
    assert rehearsal.stats["blank_cost_rows"] == 1
    assert rehearsal.ok  # 阻断行留空是合法演练结果


def test_missing_columns_mapped_or_flagged(tmp_path):
    _, _, rehearsal = _case(tmp_path)
    merged = next(r for r in rehearsal.rows if r["merged"])
    passthru = next(r for r in rehearsal.rows if not r["merged"])
    # 成本来源编码按 (order_common, 平台SKU) 映射
    assert merged["成本来源编码"] == "COST-US"
    assert passthru["成本来源编码"] == "COST-US"
    # 合并组运费 = 各组件行之和（5 + 7），不是只取承运行
    assert merged["运费"] == "12"
    assert passthru["运费"] == "3"
    assert "运费:conflict" not in merged["unmapped_columns"]
    # 小模板里的列都已被原始订单/映射/兜底补齐
    assert rehearsal.stats["rows_with_unmapped"] == 0
    assert rehearsal.stats["key_blank"]["运费"] == 0


def test_diff_breakdown_dimensions(tmp_path):
    _, p2, rehearsal = _case(tmp_path)
    assert rehearsal.diff_breakdown
    merged_pc = [
        r for r in rehearsal.diff_breakdown
        if r["列"] == "皮壳成本" and r["method"] == "半成品"
        and r["合并/透传"] == "合并" and r["status"] == "ok"
    ]
    assert merged_pc
    # disabled 维度：KS200 标记 disabled
    disabled = [r for r in rehearsal.diff_breakdown if r["disabled"] == "是"]
    assert disabled


def test_key_columns_and_derived_rates(tmp_path):
    _, _, rehearsal = _case(tmp_path)
    for row in rehearsal.rows:
        assert row["是否皮壳"] in ("皮壳", "否")
    assert rehearsal.stats["key_blank"]["是否皮壳"] == 0
    assert rehearsal.stats["key_blank"]["运费"] == 0
    assert rehearsal.stats["derived_blank_counts"]["订单总成本"] == rehearsal.stats["blank_cost_rows"]
    by_name = {a.name: a for a in rehearsal.assertions}
    assert by_name["关键列非空率"].status == "pass"
    assert by_name["派生列可算率"].status == "pass"


def test_rehearsal_outputs(tmp_path):
    _, _, rehearsal = _case(tmp_path)
    out = tmp_path / "out"
    csv = write_csv(rehearsal, out / "writeback_new_202608.csv")
    df = pd.read_csv(csv, dtype=str, keep_default_na=False)
    assert list(df.columns[:len(rehearsal.template_columns)]) == rehearsal.template_columns
    for extra in ("source_row", "group_id", "merged", "pieces", "method", "source",
                  "cost_status", "cost_reason", "lineage_status", "mapping_status",
                  "unmapped_columns"):
        assert extra in df.columns
    xlsx = write_xlsx(rehearsal, out / "writeback_new_202608.xlsx")
    sheets = pd.read_excel(xlsx, sheet_name=None)
    assert {"汇总", "写回行", "差异归因", "映射缺口", "未映射对比", "断言", "阻断清单"} <= set(sheets)
    md = render_markdown(rehearsal)
    assert "写回演练 — 202608" in md
    assert "四列合计" in md


def test_order_total_and_profit_when_inputs_available(tmp_path):
    """运费唯一 + 收入可得 → 订单总成本/利润按合同计算。"""
    items = _write_items(tmp_path)
    orders = _write_orders(tmp_path, [
        ["ORD-5000001", "PSK", "TT777", 3, 10, 50, "", "WH-NJ", "100"],
    ])
    en = _write_en(tmp_path, [["ORD-5000001", "TT777", "", 3, "成品"]])
    shadow = run_merge_shadow(orders, items, en, None, month="202608")
    bom = _write_bom(tmp_path, [{
        "item_fg": "KS200-OTHER", "shipping_method": "成品",
        "cost_fg": 5, "cost_sxbzcp": 1, "usnj_valuation_rate": 2,
        "cover_freight_2kk9fsq8ln": 3, "freight_2kk9fsq8ln": 7,
    }])
    p2 = compute_phase2(shadow, bom, items, _write_wh(tmp_path))
    old = _write_old_wb(tmp_path, [
        ["ORD-5000001", "PSK", "TT777", 3, 99, 99, 99, 99,
         "COST-US", "2", "ORD-5000001", "PSK", "99", "99", "99", "99", "99", "99", "99", "99"],
    ])
    rehearsal = build_writeback_rehearsal(shadow, p2, old, month="202608")
    row = rehearsal.rows[0]
    assert row["发货数量"] == "3"
    assert row["皮壳成本"] == "5"
    assert row["运费"] == "2"
    # 运费是行总额，不乘数量：(5 + 7 + 0 + 1) × 3 + 2 = 41
    assert row["订单总成本"] == "41"
    assert row["订单利润"] == "59"       # 收入 100 − 41
    assert row["derived_reason"] == ""
    assert rehearsal.stats["derived_blank_counts"]["订单总成本"] == 0


def test_freight_raw_fallback_when_writeback_missing(tmp_path):
    """旧写回没有运费时，用原始订单包裹总运费 / 数量（单位化）。"""
    items = _write_items(tmp_path)
    orders = _write_orders(tmp_path, [
        ["ORD-6000001", "PSK", "TT777", 2, 10, 50, "", "WH-NJ", "", "10"],
    ])
    en = _write_en(tmp_path, [["ORD-6000001", "TT777", "", 2, "成品"]])
    shadow = run_merge_shadow(orders, items, en, None, month="202608")
    bom = _write_bom(tmp_path, [{
        "item_fg": "KS200-OTHER", "shipping_method": "成品",
        "cost_fg": 5, "cost_sxbzcp": 1, "usnj_valuation_rate": 2,
        "freight_2kk9fsq8ln": 7,
    }])
    p2 = compute_phase2(shadow, bom, items, _write_wh(tmp_path))
    old = _write_old_wb(tmp_path, [
        ["ORD-6000001", "PSK", "TT777", 2, 99, 99, 99, 99,
         "COST-US", "", "ORD-6000001", "PSK", "99", "", "", "", "", "", "", ""],
    ])
    rehearsal = build_writeback_rehearsal(shadow, p2, old, month="202608")
    row = rehearsal.rows[0]
    assert row["运费"] == "10"   # 包裹总运费（行总额，不除数量）
    assert row["订单总成本"] != ""


def test_non_product_accessory_explicit_zero(tmp_path):
    items = _write_items(tmp_path)
    orders = _write_orders(tmp_path, [
        ["ORD-7000001", "PSK", "BUTTONKIT", 1, 10, 50, "", "WH-NJ", "", "2"],
    ])
    en = _write_en(tmp_path, [["ORD-7000001", "BUTTONKIT", "", 1, ""]])
    shadow = run_merge_shadow(orders, items, en, None, month="202608")
    bom = _write_bom(tmp_path, [])
    p2 = compute_phase2(shadow, bom, items, _write_wh(tmp_path))
    old = _write_old_wb(tmp_path, [
        ["ORD-7000001", "PSK", "BUTTONKIT", 1, 99, 99, 99, 99,
         "COST-US", "2", "ORD-7000001", "PSK", "99", "99", "99", "99", "99", "99", "99", "99"],
    ])
    rehearsal = build_writeback_rehearsal(shadow, p2, old, month="202608")
    row = rehearsal.rows[0]
    assert row["cost_status"] == "non_product_accessory"
    for col in ("皮壳成本", "头程运费金额", "二次加工成本", "绍兴二次加工成本"):
        assert row[col] == "0"
    assert row["皮壳成本*数量"] == "0"
    assert row["1件产品成本"] == "0"
    assert rehearsal.stats["zero_cost_rows"] == 1
    by_name = {a.name: a for a in rehearsal.assertions}
    assert by_name["四列口径（阻断留空、不填0）"].status == "pass"


def test_whitelist_sheet_lists_suggestions(tmp_path):
    _, _, rehearsal = _case(tmp_path, missing_ks200=True)
    blocked = next(r for r in rehearsal.rows if r["cost_status"] == "blocked")
    blocked["suggested_items"] = "KS200-OTHER"
    xlsx = write_xlsx(rehearsal, tmp_path / "out" / "merge.xlsx")
    sheets = pd.read_excel(xlsx, sheet_name=None)
    assert "待审建议白名单" in sheets
    wl = sheets["待审建议白名单"]
    assert len(wl) >= 1
    assert "KS200-OTHER" in wl["suggested_items"].astype(str).tolist()
