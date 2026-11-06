# -*- coding: utf-8 -*-
"""Phase 2 测试：BOM 单位成本 × 件数（四列）、方法分支、阻断、写回对账。"""
from __future__ import annotations

import sys
from pathlib import Path

import pandas as pd
import pytest

_ROOT = Path(__file__).resolve().parents[1]
if str(_ROOT) not in sys.path:
    sys.path.insert(0, str(_ROOT))

from tongtool_order_cost.tongtu_cost_engine.domain.bom_cost import (  # noqa: E402
    compute_phase2,
    phase2_markdown,
    phase2_summary_rows,
)
from tongtool_order_cost.tongtu_cost_engine.domain.split_merge import (  # noqa: E402
    render_markdown,
    run_merge_shadow,
    write_shadow_xlsx,
)

ORDER_HEADER = ["订单号", "平台SKU", "通途SKU", "发货数量", "售价", "售价(人民币)", "运费", "发货仓库"]
EN_HEADER = ["order_id_code", "tongtool_sku", "erp_item_code", "quantity",
             "shipping_method", "despatch_complete_time"]
WB_HEADER = ["订单号", "通途SKU", "发货数量", "皮壳成本", "头程运费金额",
             "二次加工成本", "绍兴二次加工成本"]

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
    {"name": "KS100-FINISH-RED", "customer_code": "TT001-FIN,TT001-FIN-Cover,TT001-FIN-Foam",
     "item_group": "靠枕", "variant_of": "KS100"},
    {"name": "KS200-OTHER", "customer_code": "TT777", "item_group": "其它", "variant_of": "KS200"},
]


def write_items(tmp_path: Path) -> Path:
    path = tmp_path / "items.csv"
    pd.DataFrame(ITEMS, columns=["name", "customer_code", "item_group", "variant_of"]).to_csv(
        path, index=False, encoding="utf-8")
    return path


def write_orders(tmp_path: Path, rows: list[list]) -> Path:
    full = [list(r) + ["WH1"] if len(r) == 7 else list(r) for r in rows]
    path = tmp_path / "orders.csv"
    pd.DataFrame(full, columns=ORDER_HEADER).to_csv(path, index=False, encoding="utf-8")
    return path


def write_en(tmp_path: Path, rows: list[list]) -> Path:
    full = [list(r) + [""] if len(r) == 5 else list(r) for r in rows]
    path = tmp_path / "en.csv"
    pd.DataFrame(full, columns=EN_HEADER).to_csv(path, index=False, encoding="utf-8")
    return path


def write_bom(tmp_path: Path, rows: list[dict]) -> Path:
    full = []
    for row in rows:
        rec = {c: "0" for c in BOM_NUMERIC}
        rec.update({"item_fg": row["item_fg"], "shipping_method": row.get("shipping_method", "")})
        rec.update({k: str(v) for k, v in row.items()})
        full.append(rec)
    path = tmp_path / "bom.csv"
    pd.DataFrame(full, columns=BOM_HEADER).to_csv(path, index=False, encoding="utf-8")
    return path


def write_wh_map(tmp_path: Path) -> Path:
    path = tmp_path / "wh_map.tsv"
    path.write_text(
        "name\twarehouse_classification\n"
        "WH1\tUSTX美中分公司\n"
        "WH-NJ\tUSNJ美东分公司\n"
        "WH-PL\tPL波兰分公司\n"
        "WH-FBA\t美国FBA\n",
        encoding="utf-8",
    )
    return path


def write_writeback(tmp_path: Path, rows: list[list]) -> Path:
    path = tmp_path / "writeback.csv"
    pd.DataFrame(rows, columns=WB_HEADER).to_csv(path, index=False, encoding="utf-8")
    return path


def _shadow(tmp_path, orders_rows, en_rows, flags_rows=None):
    items = write_items(tmp_path)
    orders = write_orders(tmp_path, orders_rows)
    en = write_en(tmp_path, en_rows)
    flags = None
    if flags_rows:
        flags = tmp_path / "flags.csv"
        pd.DataFrame(flags_rows, columns=["order_id_code", "invalid", "suspended", "order_status"]).to_csv(
            flags, index=False, encoding="utf-8")
    return run_merge_shadow(orders, items, en, flags, month="202608")


# ── 合并组半成品：pieces × 四列 ──


def test_merged_semi_finished_cost(tmp_path):
    shadow = _shadow(tmp_path, [
        ["ORD-2000001_1", "PSK", "TT001-FIN-Cover", 1, 10, 50, 0, "WH1"],
        ["ORD-2000001_1", "PSK", "TT001-FIN-Foam", 1, 0, 0, 0, "WH1"],
        ["ORD-2000001_2", "PSK", "TT001-FIN-Cover", 1, 10, 50, 0, "WH1"],
        ["ORD-2000001_2", "PSK", "TT001-FIN-Foam", 1, 0, 0, 0, "WH1"],
    ], [
        ["ORD-2000001_1", "TT001-FIN-Cover", "", 1, "半成品"],
        ["ORD-2000001_1", "TT001-FIN-Foam", "", 1, "半成品"],
        ["ORD-2000001_2", "TT001-FIN-Cover", "", 1, "半成品"],
        ["ORD-2000001_2", "TT001-FIN-Foam", "", 1, "半成品"],
    ])
    assert shadow.stats["merged_groups"] == 1
    bom = write_bom(tmp_path, [{
        "item_fg": "KS100-FINISH-RED", "shipping_method": "半成品",
        "cost_fg": 10, "cost_sxbzbcp": 2, "cost_sxbzcp": 5, "sx_cost_all": 12,
        "ustx_valuation_rate": 3,
        "cover_freight_e5asph24tk": 1, "sfg_freight_e5asph24tk": 4,
        "freight_e5asph24tk": 9,
    }])
    p2 = compute_phase2(shadow, bom, write_items(tmp_path), write_wh_map(tmp_path))
    assert p2.ok, [a for a in p2.assertions if a.status == "fail"]
    assert p2.stats["phase2_priced"] == 1
    row = p2.rows[0]
    assert row["merged"] is True
    assert row["method"] == "半成品"
    assert row["warehouse_bucket"] == "USTX"
    assert row["units"] == 2
    assert row["皮壳成本"] == 20          # 10 × 2
    assert row["头程运费金额"] == 8        # sfg 4 × 2
    assert row["二次加工成本"] == 6        # ustx 3 × 2
    assert row["绍兴二次加工成本"] == 4    # sxbzbcp 2 × 2
    assert row["四列合计"] == 38
    assert row["1件成本(不含头程)"] == 15  # 10 + 2 + 3


# ── 透传行：按 qty；USNJ 二次加工 / 成品 ──


def test_pass_row_usnj_finished_cost(tmp_path):
    shadow = _shadow(tmp_path, [
        ["ORD-2100001", "PSK", "TT777", 3, 10, 50, 0, "WH-NJ"],
    ], [
        ["ORD-2100001", "TT777", "", 3, "成品"],
    ])
    bom = write_bom(tmp_path, [{
        "item_fg": "KS200-OTHER", "shipping_method": "成品",
        "cost_fg": 5, "cost_sxbzcp": 1,
        "usnj_valuation_rate": 2,
        "cover_freight_2kk9fsq8ln": 3, "freight_2kk9fsq8ln": 7,
    }])
    p2 = compute_phase2(shadow, bom, write_items(tmp_path), write_wh_map(tmp_path))
    assert p2.ok, [a for a in p2.assertions if a.status == "fail"]
    row = p2.rows[0]
    assert row["merged"] is False
    assert row["units"] == 3
    assert row["皮壳成本"] == 15
    assert row["头程运费金额"] == 21
    assert row["二次加工成本"] == 6
    assert row["绍兴二次加工成本"] == 3


def test_fba_cost_branch(tmp_path):
    shadow = _shadow(tmp_path, [
        ["ORD-2200001", "PSK", "TT777", 1, 10, 50, 0, "WH-FBA"],
    ], [
        ["ORD-2200001", "TT777", "", 1, "成品"],
    ])
    bom = write_bom(tmp_path, [{
        "item_fg": "KS200-OTHER", "shipping_method": "成品",
        "cost_fg": 5, "sx_cost_all": 8, "freight_9rr7m7g3aj": 11,
    }])
    p2 = compute_phase2(shadow, bom, write_items(tmp_path), write_wh_map(tmp_path))
    row = p2.rows[0]
    assert row["status"] == "ok"
    assert row["warehouse_bucket"] == "USFBA"
    assert row["皮壳成本"] == 5
    assert row["头程运费金额"] == 11
    assert row["二次加工成本"] == 0
    assert row["绍兴二次加工成本"] == 3  # sx_cost_all 8 − cost_fg 5


def test_cover_pass_row_uses_cover_freight_and_zero_sx(tmp_path):
    shadow = _shadow(tmp_path, [
        ["ORD-2300001", "PSK", "TT001-FIN-Cover", 2, 10, 50, 0, "WH-PL"],
    ], [
        ["ORD-2300001", "TT001-FIN-Cover", "", 2, "皮壳"],
    ])
    bom = write_bom(tmp_path, [{
        "item_fg": "KS100-FINISH-RED", "shipping_method": "皮壳",
        "cost_fg": 4, "cost_sxbzcp": 9,
        "pl_valuation_rate": 1,
        "cover_freight_tmvvepd80f": 2, "freight_tmvvepd80f": 10,
    }])
    p2 = compute_phase2(shadow, bom, write_items(tmp_path), write_wh_map(tmp_path))
    row = p2.rows[0]
    assert row["皮壳成本"] == 8
    assert row["头程运费金额"] == 4       # cover 2 × 2
    assert row["二次加工成本"] == 0       # -COVER：加工成本清 0
    assert row["绍兴二次加工成本"] == 0   # -COVER：绍兴发货成本 = 皮壳成本


# ── 阻断 ──


def test_missing_bom_blocks(tmp_path):
    shadow = _shadow(tmp_path, [
        ["ORD-2400001", "PSK", "TT777", 1, 10, 50, 0, "WH-NJ"],
    ], [["ORD-2400001", "TT777", "", 1, "成品"]])
    bom = write_bom(tmp_path, [{"item_fg": "OTHER-ITEM", "shipping_method": "成品", "cost_fg": 1}])
    p2 = compute_phase2(shadow, bom, write_items(tmp_path), write_wh_map(tmp_path))
    assert p2.rows[0]["status"] == "blocked"
    assert p2.rows[0]["reason"] == "bom_item_missing"
    assert p2.rows[0]["皮壳成本"] is None
    assert p2.stats["phase2_integrity_status"] == "fail"
    assert not p2.ok


def test_duplicate_bom_row_blocks(tmp_path):
    shadow = _shadow(tmp_path, [
        ["ORD-2500001", "PSK", "TT777", 1, 10, 50, 0, "WH-NJ"],
    ], [["ORD-2500001", "TT777", "", 1, "成品"]])
    bom = write_bom(tmp_path, [
        {"item_fg": "KS200-OTHER", "shipping_method": "成品", "cost_fg": 1},
        {"item_fg": "KS200-OTHER", "shipping_method": "成品", "cost_fg": 2},
    ])
    p2 = compute_phase2(shadow, bom, write_items(tmp_path), write_wh_map(tmp_path))
    assert p2.rows[0]["reason"] == "bom_row_duplicate"
    assert not p2.ok


def test_negative_cost_blocks(tmp_path):
    shadow = _shadow(tmp_path, [
        ["ORD-2600001", "PSK", "TT777", 1, 10, 50, 0, "WH-NJ"],
    ], [["ORD-2600001", "TT777", "", 1, "成品"]])
    bom = write_bom(tmp_path, [{
        "item_fg": "KS200-OTHER", "shipping_method": "成品",
        "cost_fg": -1, "usnj_valuation_rate": 2,
    }])
    p2 = compute_phase2(shadow, bom, write_items(tmp_path), write_wh_map(tmp_path))
    assert p2.rows[0]["reason"] == "negative_cost"
    assert not p2.ok


def test_method_diff_is_flagged_not_blocked(tmp_path):
    """BOM method 与 EN 不一致：按 EN 定价，method_diff 标记，不阻断。"""
    shadow = _shadow(tmp_path, [
        ["ORD-2700001", "PSK", "TT777", 1, 10, 50, 0, "WH-NJ"],
    ], [["ORD-2700001", "TT777", "", 1, "皮壳"]])
    bom = write_bom(tmp_path, [{
        "item_fg": "KS200-OTHER", "shipping_method": "成品",
        "cost_fg": 5, "cost_sxbzcp": 1, "usnj_valuation_rate": 2,
        "cover_freight_2kk9fsq8ln": 3, "freight_2kk9fsq8ln": 7,
    }])
    p2 = compute_phase2(shadow, bom, write_items(tmp_path), write_wh_map(tmp_path))
    row = p2.rows[0]
    assert row["status"] == "ok"
    assert row["method"] == "皮壳"
    assert row["bom_method"] == "成品"
    assert row["method_diff"] is True
    assert row["绍兴二次加工成本"] == 0
    assert p2.stats["phase2_method_diff_rows"] == 1


# ── 写回对账（仅对账） ──


def test_writeback_diff_is_reported_not_used(tmp_path):
    shadow = _shadow(tmp_path, [
        ["ORD-2800001", "PSK", "TT777", 3, 10, 50, 0, "WH-NJ"],
    ], [["ORD-2800001", "TT777", "", 3, "成品"]])
    bom = write_bom(tmp_path, [{
        "item_fg": "KS200-OTHER", "shipping_method": "成品",
        "cost_fg": 5, "cost_sxbzcp": 1, "usnj_valuation_rate": 2,
        "cover_freight_2kk9fsq8ln": 3, "freight_2kk9fsq8ln": 7,
    }])
    wb = write_writeback(tmp_path, [
        ["ORD-2800001", "TT777", 3, 1, 2, 3, 4],
    ])
    p2 = compute_phase2(shadow, bom, write_items(tmp_path), write_wh_map(tmp_path), wb)
    row = p2.rows[0]
    assert row["wb匹配行数"] == 1
    assert row["wb_皮壳成本"] == 3
    assert row["diff_vs_writeback_皮壳成本"] == 12   # 15 − 3
    assert row["diff_vs_writeback_头程运费金额"] == 15
    assert row["diff_vs_writeback_二次加工成本"] == -3
    assert row["diff_vs_writeback_绍兴二次加工成本"] == -9
    assert row["diff_vs_writeback_合计"] == 15
    # 写回只对账，不影响 BOM 计算值
    assert row["皮壳成本"] == 15


# ── 输出集成 ──


def test_phase2_output_sheet_and_markdown(tmp_path):
    shadow = _shadow(tmp_path, [
        ["ORD-2900001", "PSK", "TT777", 1, 10, 50, 0, "WH-NJ"],
    ], [["ORD-2900001", "TT777", "", 1, "成品"]])
    bom = write_bom(tmp_path, [{
        "item_fg": "KS200-OTHER", "shipping_method": "成品",
        "cost_fg": 5, "cost_sxbzcp": 1, "usnj_valuation_rate": 2,
        "freight_2kk9fsq8ln": 7,
    }])
    p2 = compute_phase2(shadow, bom, write_items(tmp_path), write_wh_map(tmp_path))
    xlsx = write_shadow_xlsx(shadow, tmp_path / "out" / "merge.xlsx", p2)
    sheets = pd.read_excel(xlsx, sheet_name=None)
    assert "Phase2成本" in sheets
    p2sheet = sheets["Phase2成本"]
    assert len(p2sheet) == 1
    for col in ("皮壳成本", "头程运费金额", "二次加工成本", "绍兴二次加工成本",
                "method", "source", "units", "diff_vs_writeback_合计"):
        assert col in p2sheet.columns
    md = render_markdown(shadow, p2)
    assert "Phase 2 — BOM Cost List 单位成本 × 件数" in md
    assert "写回对账" in md
    assert phase2_markdown(p2) == phase2_markdown(p2)
    assert any(r["指标"] == "Phase2 可定价行" for r in phase2_summary_rows(p2))


# ── Phase 2.1：Phase1 产品锁定 / method_diff 规则 / 差异归因 ──


class FakeResolver:
    def __init__(self, sku_items, item_products):
        self.sku_items = sku_items
        self.item_products = item_products

    def items_for_sku(self, sku):
        return tuple(self.sku_items.get(sku, ()))

    def product_for_item(self, item):
        return self.item_products.get(item, "")


def test_item_resolution_uses_phase1_locked_product():
    from tongtool_order_cost.tongtu_cost_engine.domain.bom_cost import item_for_detail

    resolver = FakeResolver(
        {"X": ("ITEM-A", "ITEM-B")},
        {"ITEM-A": "P1", "ITEM-B": "P2"},
    )
    detail = {"merged": False, "通途SKU": "X", "product_id": "P1"}
    bom_index = {"ITEM-A": [{"cost_fg": "1"}], "ITEM-B": [{"cost_fg": "2"}]}
    item, reason = item_for_detail(detail, resolver, bom_index)
    assert (item, reason) == ("ITEM-A", "")


def test_same_product_multiple_items_still_ambiguous():
    from tongtool_order_cost.tongtu_cost_engine.domain.bom_cost import item_for_detail

    resolver = FakeResolver(
        {"X": ("ITEM-A", "ITEM-C")},
        {"ITEM-A": "P1", "ITEM-C": "P1"},
    )
    detail = {"merged": False, "通途SKU": "X", "product_id": "P1"}
    bom_index = {"ITEM-A": [{"cost_fg": "1"}], "ITEM-C": [{"cost_fg": "2"}]}
    item, reason = item_for_detail(detail, resolver, bom_index)
    assert item == ""
    assert reason == "bom_item_ambiguous"  # 绝不从同产品的多个 BOM 里任选


def test_method_diff_alt_delta_is_audited(tmp_path):
    shadow = _shadow(tmp_path, [
        ["ORD-3100001", "PSK", "TT777", 1, 10, 50, 0, "WH-NJ"],
    ], [["ORD-3100001", "TT777", "", 1, "皮壳"]])
    bom = write_bom(tmp_path, [{
        "item_fg": "KS200-OTHER", "shipping_method": "成品",
        "cost_fg": 5, "cost_sxbzcp": 1, "usnj_valuation_rate": 2,
        "cover_freight_2kk9fsq8ln": 3, "freight_2kk9fsq8ln": 7,
    }])
    p2 = compute_phase2(shadow, bom, write_items(tmp_path), write_wh_map(tmp_path))
    row = p2.rows[0]
    assert row["method_diff"] is True
    # EN 皮壳：5+3+2+0=10；BOM 成品：5+7+2+1=15 → 审计差 +5
    assert row["method_diff_alt_delta"] == 5
    assert p2.stats["phase2_method_diff_alt_delta"] == 5


def test_diff_breakdown_dimensions(tmp_path):
    shadow = _shadow(tmp_path, [
        ["ORD-3200001", "PSK", "TT777", 3, 10, 50, 0, "WH-NJ"],
    ], [["ORD-3200001", "TT777", "", 3, "成品"]])
    bom = write_bom(tmp_path, [{
        "item_fg": "KS200-OTHER", "shipping_method": "成品",
        "cost_fg": 5, "cost_sxbzcp": 1, "usnj_valuation_rate": 2,
        "cover_freight_2kk9fsq8ln": 3, "freight_2kk9fsq8ln": 7,
    }])
    wb = write_writeback(tmp_path, [["ORD-3200001", "TT777", 3, 1, 2, 3, 4]])
    p2 = compute_phase2(shadow, bom, write_items(tmp_path), write_wh_map(tmp_path), wb)
    from tongtool_order_cost.tongtu_cost_engine.domain.bom_cost import phase2_diff_breakdown

    rows = phase2_diff_breakdown(p2)
    shell = [
        r for r in rows
        if r["列"] == "皮壳成本" and r["method"] == "成品"
        and r["合并/透传"] == "透传" and r["status"] == "ok" and r["method_diff"] == "否"
    ]
    assert len(shell) == 1
    assert shell[0]["差异(我方−写回)"] == 12
    assert shell[0]["绝对差"] == 12
    xlsx = write_shadow_xlsx(shadow, tmp_path / "out" / "merge.xlsx", p2)
    sheets = pd.read_excel(xlsx, sheet_name=None)
    assert "差异归因" in sheets


# ── Phase 2.2：disabled 快照 / 组内统一产品 / 通用组件按订单锚定 ──


def write_items_rows(tmp_path: Path, rows: list[dict]) -> Path:
    path = tmp_path / "items_custom.csv"
    pd.DataFrame(rows, columns=["name", "customer_code", "item_group", "variant_of"]).to_csv(
        path, index=False, encoding="utf-8")
    return path


def test_merged_group_uses_carrier_item_only():
    from tongtool_order_cost.tongtu_cost_engine.domain.bom_cost import item_for_detail

    resolver = FakeResolver(
        {"CARRIER": ("ITEM-CARRIER",), "MEMBER": ("ITEM-M1", "ITEM-M2")},
        {"ITEM-CARRIER": "P1", "ITEM-M1": "P1", "ITEM-M2": "P1"},
    )
    detail = {
        "merged": True, "carrier_sku": "CARRIER", "skus": "CARRIER, MEMBER",
        "product_id": "P1",
    }
    bom_index = {"ITEM-CARRIER": [{}], "ITEM-M1": [{}], "ITEM-M2": [{}]}
    item, reason = item_for_detail(detail, resolver, bom_index)
    assert (item, reason) == ("ITEM-CARRIER", "")


def test_generic_component_uses_order_anchor():
    from tongtool_order_cost.tongtu_cost_engine.domain.bom_cost import item_for_detail

    resolver = FakeResolver(
        {"GEN": ("ITEM-A", "ITEM-B")},
        {"ITEM-A": "P1", "ITEM-B": "P1"},
    )
    detail = {"merged": False, "通途SKU": "GEN", "product_id": "P1"}
    bom_index = {"ITEM-A": [{}], "ITEM-B": [{}], "ITEM-ANCHOR": [{}]}
    item, reason = item_for_detail(detail, resolver, bom_index, ("ITEM-ANCHOR",))
    assert (item, reason) == ("ITEM-ANCHOR", "")


def test_generic_component_multiple_anchors_blocks():
    from tongtool_order_cost.tongtu_cost_engine.domain.bom_cost import item_for_detail

    resolver = FakeResolver(
        {"GEN": ("ITEM-A", "ITEM-B")},
        {"ITEM-A": "P1", "ITEM-B": "P1"},
    )
    detail = {"merged": False, "通途SKU": "GEN", "product_id": "P1"}
    bom_index = {"ITEM-A": [{}], "ITEM-B": [{}], "A1": [{}], "A2": [{}]}
    item, reason = item_for_detail(detail, resolver, bom_index, ("A1", "A2"))
    assert item == ""
    assert reason == "bom_item_ambiguous"


def _generic_case(tmp_path, covers):
    """同订单：若干 Cover 行 + 一个通用组件行；不同平台SKU避免合并。"""
    items = write_items_rows(tmp_path, covers + [
        {"name": "KS700-INNER-A", "customer_code": "GEN", "item_group": "靠枕", "variant_of": "KS700"},
        {"name": "KS700-INNER-B", "customer_code": "GEN", "item_group": "靠枕", "variant_of": "KS700"},
    ])
    orders_rows = []
    en_rows = []
    for i, c in enumerate(covers, start=1):
        code = c["customer_code"]
        orders_rows.append(["ORD-400", f"PSK-C{i}", code, 1, 10, 50, 0, "WH-NJ"])
        en_rows.append(["ORD-400", code, "", 1, "成品"])
    orders_rows.append(["ORD-400", "PSK-GEN", "GEN", 1, 10, 50, 0, "WH-NJ"])
    en_rows.append(["ORD-400", "GEN", "", 1, "成品"])
    orders = write_orders(tmp_path, orders_rows)
    en = write_en(tmp_path, en_rows)
    return items, orders, en


def test_generic_ppcotton_anchored_to_cover(tmp_path):
    items, orders, en = _generic_case(tmp_path, [
        {"name": "KS700-COVER-1", "customer_code": "C1", "item_group": "靠枕", "variant_of": "KS700"},
    ])
    shadow = run_merge_shadow(orders, items, en, None, month="202608")
    assert shadow.stats["merged_groups"] == 0
    bom = write_bom(tmp_path, [{
        "item_fg": "KS700-COVER-1", "shipping_method": "成品",
        "cost_fg": 10, "cost_sxbzcp": 1, "usnj_valuation_rate": 2,
        "freight_2kk9fsq8ln": 7,
    }])
    p2 = compute_phase2(shadow, bom, items, write_wh_map(tmp_path))
    gen = [r for r in p2.rows if r["SKU"] == "GEN"][0]
    assert gen["status"] == "ok"
    assert gen["item_fg"] == "KS700-COVER-1"   # 用同订单 Cover 锚定
    assert gen["皮壳成本"] == 10


def test_generic_component_multiple_covers_blocks(tmp_path):
    items, orders, en = _generic_case(tmp_path, [
        {"name": "KS700-COVER-1", "customer_code": "C1", "item_group": "靠枕", "variant_of": "KS700"},
        {"name": "KS700-COVER-2", "customer_code": "C2", "item_group": "靠枕", "variant_of": "KS700"},
    ])
    shadow = run_merge_shadow(orders, items, en, None, month="202608")
    bom = write_bom(tmp_path, [
        {"item_fg": "KS700-COVER-1", "shipping_method": "成品", "cost_fg": 10,
         "cost_sxbzcp": 1, "usnj_valuation_rate": 2, "freight_2kk9fsq8ln": 7},
        {"item_fg": "KS700-COVER-2", "shipping_method": "成品", "cost_fg": 10,
         "cost_sxbzcp": 1, "usnj_valuation_rate": 2, "freight_2kk9fsq8ln": 7},
    ])
    p2 = compute_phase2(shadow, bom, items, write_wh_map(tmp_path))
    gen = [r for r in p2.rows if r["SKU"] == "GEN"][0]
    assert gen["status"] == "blocked"
    assert gen["reason"] == "bom_item_ambiguous"


def test_disabled_bom_snapshot_contains_disabled_items():
    """成本快照必须 include disabled：历史订单可能引用停用物料。"""
    from tongtool_order_cost.tongtu_cost_engine.domain.bom_cost import load_bom_cost

    path = _ROOT / "out" / "bom_cost_product_with_disabled.csv"
    if not path.exists():
        pytest.skip("disabled BOM snapshot not present")
    index = load_bom_cost(path)
    # KS0143-HLR-165-GREY 在 EN 是 disabled=1，且曾出现在 8 月订单里
    assert "KS0143-HLR-165-GREY" in index
    assert "KS0143-HLR-165-GREY" not in load_bom_cost(_ROOT / "out" / "bom_cost_product_latest.csv")


# ── Phase 3.3：非商品配件 / 套件 / 建议白名单 ──


def _custom_items(tmp_path: Path, rows: list[dict]) -> Path:
    path = tmp_path / "items_custom.csv"
    pd.DataFrame(rows, columns=["name", "customer_code", "item_group", "variant_of"]).to_csv(
        path, index=False, encoding="utf-8")
    return path


def test_non_product_accessory_zero_cost(tmp_path):
    shadow = _shadow(tmp_path, [
        ["ORD-9000001", "PSK", "BUTTONKIT", 1, 10, 50, 0, "WH-NJ"],
    ], [["ORD-9000001", "BUTTONKIT", "", 1, ""]])
    bom = write_bom(tmp_path, [])
    p2 = compute_phase2(shadow, bom, write_items(tmp_path), write_wh_map(tmp_path))
    row = p2.rows[0]
    assert row["status"] == "non_product_accessory"
    assert row["source"] == "non_product_accessory"
    assert row["皮壳成本"] == 0.0
    assert row["头程运费金额"] == 0.0
    assert row["二次加工成本"] == 0.0
    assert row["绍兴二次加工成本"] == 0.0
    assert p2.stats["phase2_zero_cost"] == 1


def test_tj_bundle_pending(tmp_path):
    items = _custom_items(tmp_path, [
        {"name": "TJ#TEST-001", "customer_code": "TTBUNDLE", "item_group": "套件#", "variant_of": ""},
    ])
    orders = write_orders(tmp_path, [["ORD-9100001", "PSK", "TTBUNDLE", 1, 10, 50, 0]])
    en = write_en(tmp_path, [["ORD-9100001", "TTBUNDLE", "", 1, ""]])
    shadow = run_merge_shadow(orders, items, en, None, month="202608")
    bom = write_bom(tmp_path, [])
    p2 = compute_phase2(shadow, bom, items, write_wh_map(tmp_path))
    row = p2.rows[0]
    assert row["status"] == "pending_bundle"
    assert row["皮壳成本"] is None
    assert p2.stats["phase2_pending_bundle"] == 1


def test_ambiguous_generic_suggests_candidates(tmp_path):
    items = _custom_items(tmp_path, [
        {"name": "KS900-A", "customer_code": "GEN", "item_group": "靠枕", "variant_of": "KS900"},
        {"name": "KS900-B", "customer_code": "GEN", "item_group": "靠枕", "variant_of": "KS900"},
    ])
    orders = write_orders(tmp_path, [["ORD-9200001", "PSK", "GEN", 1, 10, 50, 0]])
    en = write_en(tmp_path, [["ORD-9200001", "GEN", "", 1, "成品"]])
    shadow = run_merge_shadow(orders, items, en, None, month="202608")
    bom = write_bom(tmp_path, [
        {"item_fg": "KS900-A", "shipping_method": "成品", "cost_fg": 1},
        {"item_fg": "KS900-B", "shipping_method": "成品", "cost_fg": 2},
    ])
    p2 = compute_phase2(shadow, bom, items, write_wh_map(tmp_path))
    row = p2.rows[0]
    assert row["status"] == "blocked"
    assert row["reason"] == "bom_item_ambiguous"
    assert "KS900-A" in row["suggested_items"]
    assert "KS900-B" in row["suggested_items"]


# ── Phase 3.4：订单产品上下文 / 组件吸收 / Product Bundle 展开 ──


def test_ambiguous_cover_resolved_by_order_product_context(tmp_path):
    items = _custom_items(tmp_path, [
        {"name": "KS900-A", "customer_code": "COVER-GEN", "item_group": "靠枕", "variant_of": "KS900"},
        {"name": "KS910-A", "customer_code": "COVER-GEN", "item_group": "靠枕", "variant_of": "KS910"},
        {"name": "KS910-FOAM", "customer_code": "FOAM-X", "item_group": "靠枕", "variant_of": "KS910"},
    ])
    orders = write_orders(tmp_path, [
        ["ORD-9300001", "PSK", "COVER-GEN", 1, 10, 50, 0, "WH-NJ"],
        ["ORD-9300001", "PSK", "FOAM-X", 1, 0, 0, 0, "WH-NJ"],
    ])
    en = write_en(tmp_path, [
        ["ORD-9300001", "COVER-GEN", "", 1, "成品"],
        ["ORD-9300001", "FOAM-X", "", 1, "成品"],
    ])
    shadow = run_merge_shadow(orders, items, en, None, month="202608")
    bom = write_bom(tmp_path, [
        {"item_fg": "KS910-A", "shipping_method": "成品", "cost_fg": 10,
         "cost_sxbzcp": 1, "usnj_valuation_rate": 2, "freight_2kk9fsq8ln": 7},
        {"item_fg": "KS910-FOAM", "shipping_method": "成品", "cost_fg": 2,
         "cost_sxbzcp": 0, "usnj_valuation_rate": 2, "freight_2kk9fsq8ln": 3},
    ])
    p2 = compute_phase2(shadow, bom, items, write_wh_map(tmp_path))
    # Phase1 已按同订单 FOAM 行锚定封面到 KS910，两行合并成一组计价
    cover = [r for r in p2.rows if "COVER-GEN" in str(r.get("SKU", ""))][0]
    assert cover["status"] == "ok"
    assert cover["item_fg"] == "KS910-A"   # 同订单 FOAM 锁定 KS910
    assert shadow.stats["rows_anchored"] == 1


def test_generic_component_absorbed_into_priced_cover(tmp_path):
    items = _custom_items(tmp_path, [
        {"name": "KS900-A", "customer_code": "COVER-GEN", "item_group": "靠枕", "variant_of": "KS900"},
        {"name": "KS910-A", "customer_code": "COVER-GEN", "item_group": "靠枕", "variant_of": "KS910"},
        {"name": "KS910-F1", "customer_code": "GEN-FOAM", "item_group": "靠枕", "variant_of": "KS910"},
        {"name": "KS910-F2", "customer_code": "GEN-FOAM", "item_group": "靠枕", "variant_of": "KS910"},
    ])
    orders = write_orders(tmp_path, [
        ["ORD-9400001", "PSK-C", "COVER-GEN", 1, 10, 50, 0, "WH-NJ"],
        ["ORD-9400001", "PSK-F", "GEN-FOAM", 1, 0, 0, 0, "WH-NJ"],
    ])
    en = write_en(tmp_path, [
        ["ORD-9400001", "COVER-GEN", "", 1, "成品"],
        ["ORD-9400001", "GEN-FOAM", "", 1, "成品"],
    ])
    shadow = run_merge_shadow(orders, items, en, None, month="202608")
    bom = write_bom(tmp_path, [
        {"item_fg": "KS910-A", "shipping_method": "成品", "cost_fg": 10,
         "cost_sxbzcp": 1, "usnj_valuation_rate": 2, "freight_2kk9fsq8ln": 7},
    ])
    p2 = compute_phase2(shadow, bom, items, write_wh_map(tmp_path))
    foam = [r for r in p2.rows if r["SKU"] == "GEN-FOAM"][0]
    assert foam["status"] == "component_absorbed"
    assert foam["皮壳成本"] == 0
    assert p2.stats["phase2_component_absorbed"] == 1


def test_product_bundle_expands_to_component_cost(tmp_path):
    items = _custom_items(tmp_path, [
        {"name": "TJ#TEST-001", "customer_code": "TTBUNDLE", "item_group": "套件#", "variant_of": ""},
        {"name": "C1", "customer_code": "C1", "item_group": "配件", "variant_of": "C1P"},
        {"name": "C2", "customer_code": "C2", "item_group": "配件", "variant_of": "C2P"},
    ])
    orders = write_orders(tmp_path, [["ORD-9500001", "PSK", "TTBUNDLE", 1, 10, 50, 0, "WH-NJ"]])
    en = write_en(tmp_path, [["ORD-9500001", "TTBUNDLE", "", 1, ""]])
    shadow = run_merge_shadow(orders, items, en, None, month="202608")
    bom = write_bom(tmp_path, [
        {"item_fg": "C1", "shipping_method": "成品", "cost_fg": 10,
         "cost_sxbzcp": 1, "usnj_valuation_rate": 2, "freight_2kk9fsq8ln": 7},
        {"item_fg": "C2", "shipping_method": "成品", "cost_fg": 5,
         "cost_sxbzcp": 0.5, "usnj_valuation_rate": 2, "freight_2kk9fsq8ln": 3},
    ])
    bundles = tmp_path / "bundles.csv"
    pd.DataFrame([
        {"bundle_item": "TJ#TEST-001", "component_item": "C1", "qty": 1,
         "bundle_modified": "2026-01-01 00:00:00", "bundle_version": "2026-01-01 00:00:00|abcd"},
        {"bundle_item": "TJ#TEST-001", "component_item": "C2", "qty": 2,
         "bundle_modified": "2026-01-01 00:00:00", "bundle_version": "2026-01-01 00:00:00|abcd"},
    ]).to_csv(bundles, index=False, encoding="utf-8")
    kit = tmp_path / "kit.csv"
    pd.DataFrame([{
        "item_fg": "TJ#TEST-001", "cost_fg": 20, "cost_sxbzbcp": 0,
        "cost_sxbzcp": 2, "sx_cost_all": 22, "usnj_valuation_rate": 6,
        "ustx_valuation_rate": 0, "pl_valuation_rate": 0,
    }]).to_csv(kit, index=False, encoding="utf-8")
    p2 = compute_phase2(shadow, bom, items, write_wh_map(tmp_path),
                        bundle_map_csv=bundles, kit_report_csv=kit)
    row = p2.rows[0]
    assert row["status"] == "ok"
    assert row["method_source"] == "kit_bundle"
    assert row["kit_method"] == "成品"
    assert row["bundle_version"] == "2026-01-01 00:00:00|abcd"
    assert row["item_fg"] == "TJ#TEST-001"
    assert row["皮壳成本"] == 20      # 10 + 5×2
    assert row["头程运费金额"] == 13  # 7 + 3×2
    assert p2.stats["phase2_pending_bundle"] == 0
    assert p2.stats["phase2_kit_priced"] == 1


# ── Phase 3.5：套件 method / 版本 / 报表对账 / 双计 ──


def _kit_case(tmp_path, *, methods=("成品", "成品"), with_version=True, report_cost=20):
    items = _custom_items(tmp_path, [
        {"name": "TJ#TEST-001", "customer_code": "TTBUNDLE", "item_group": "套件#", "variant_of": ""},
        {"name": "C1", "customer_code": "C1", "item_group": "配件", "variant_of": "C1P"},
        {"name": "C2", "customer_code": "C2", "item_group": "配件", "variant_of": "C2P"},
    ])
    orders = write_orders(tmp_path, [["ORD-9600001", "PSK", "TTBUNDLE", 1, 10, 50, 0, "WH-NJ"]])
    en = write_en(tmp_path, [["ORD-9600001", "TTBUNDLE", "", 1, ""]])
    shadow = run_merge_shadow(orders, items, en, None, month="202608")
    bom = write_bom(tmp_path, [
        {"item_fg": "C1", "shipping_method": methods[0], "cost_fg": 10,
         "cost_sxbzbcp": 1, "cost_sxbzcp": 1, "sx_cost_all": 11,
         "usnj_valuation_rate": 2, "freight_2kk9fsq8ln": 7},
        {"item_fg": "C2", "shipping_method": methods[1], "cost_fg": 5,
         "cost_sxbzbcp": 1, "cost_sxbzcp": 0.5, "sx_cost_all": 5.5,
         "usnj_valuation_rate": 2, "freight_2kk9fsq8ln": 3},
    ])
    rows = [
        {"bundle_item": "TJ#TEST-001", "component_item": "C1", "qty": 1},
        {"bundle_item": "TJ#TEST-001", "component_item": "C2", "qty": 2},
    ]
    if with_version:
        for r in rows:
            r.update({"bundle_modified": "2026-01-01", "bundle_version": "2026-01-01|abcd"})
    bundles = tmp_path / "bundles.csv"
    pd.DataFrame(rows).to_csv(bundles, index=False, encoding="utf-8")
    kit = tmp_path / "kit.csv"
    pd.DataFrame([{
        "item_fg": "TJ#TEST-001", "cost_fg": report_cost, "cost_sxbzbcp": 3,
        "cost_sxbzcp": 2, "sx_cost_all": report_cost + 5, "usnj_valuation_rate": 6,
        "ustx_valuation_rate": 0, "pl_valuation_rate": 0,
    }]).to_csv(kit, index=False, encoding="utf-8")
    return shadow, bom, items, bundles, kit


def test_kit_method_mixed_pending(tmp_path):
    shadow, bom, items, bundles, kit = _kit_case(tmp_path, methods=("成品", "半成品"))
    p2 = compute_phase2(shadow, bom, items, write_wh_map(tmp_path),
                        bundle_map_csv=bundles, kit_report_csv=kit)
    row = p2.rows[0]
    assert row["status"] == "pending_bundle"
    assert row["reason"] == "kit_method_mixed"
    assert p2.stats["phase2_kit_pending"] == 1


def test_kit_version_missing_pending(tmp_path):
    shadow, bom, items, bundles, kit = _kit_case(tmp_path, with_version=False)
    p2 = compute_phase2(shadow, bom, items, write_wh_map(tmp_path),
                        bundle_map_csv=bundles, kit_report_csv=kit)
    row = p2.rows[0]
    assert row["status"] == "pending_bundle"
    assert row["reason"] == "bundle_version_missing"


def test_kit_report_mismatch_blocks(tmp_path):
    shadow, bom, items, bundles, kit = _kit_case(tmp_path, report_cost=99)
    p2 = compute_phase2(shadow, bom, items, write_wh_map(tmp_path),
                        bundle_map_csv=bundles, kit_report_csv=kit)
    row = p2.rows[0]
    assert row["status"] == "blocked"
    assert row["reason"] == "kit_report_mismatch"
    assert p2.stats["phase2_kit_reconcile_fail"] == 1


def test_kit_child_double_count_blocks(tmp_path):
    items = _custom_items(tmp_path, [
        {"name": "TJ#TEST-001", "customer_code": "TTBUNDLE", "item_group": "套件#", "variant_of": ""},
        {"name": "C1", "customer_code": "C1", "item_group": "配件", "variant_of": "C1P"},
    ])
    orders = write_orders(tmp_path, [
        ["ORD-9700001", "PSK-B", "TTBUNDLE", 1, 10, 50, 0, "WH-NJ"],
        ["ORD-9700001", "PSK-C", "C1", 1, 10, 50, 0, "WH-NJ"],
    ])
    en = write_en(tmp_path, [
        ["ORD-9700001", "TTBUNDLE", "", 1, ""],
        ["ORD-9700001", "C1", "", 1, "成品"],
    ])
    shadow = run_merge_shadow(orders, items, en, None, month="202608")
    bom = write_bom(tmp_path, [
        {"item_fg": "C1", "shipping_method": "成品", "cost_fg": 10,
         "cost_sxbzcp": 1, "usnj_valuation_rate": 2, "freight_2kk9fsq8ln": 7},
    ])
    bundles = tmp_path / "bundles.csv"
    pd.DataFrame([{"bundle_item": "TJ#TEST-001", "component_item": "C1", "qty": 1,
                   "bundle_modified": "2026-01-01", "bundle_version": "2026-01-01|abcd"}]).to_csv(
        bundles, index=False, encoding="utf-8")
    kit = tmp_path / "kit.csv"
    pd.DataFrame([{"item_fg": "TJ#TEST-001", "cost_fg": 10, "cost_sxbzbcp": 0,
                   "cost_sxbzcp": 1, "sx_cost_all": 11, "usnj_valuation_rate": 2,
                   "ustx_valuation_rate": 0, "pl_valuation_rate": 0}]).to_csv(
        kit, index=False, encoding="utf-8")
    p2 = compute_phase2(shadow, bom, items, write_wh_map(tmp_path),
                        bundle_map_csv=bundles, kit_report_csv=kit)
    assert p2.stats["phase2_kit_double_count"] == 2
    assert all(r["status"] == "blocked" for r in p2.rows if r["reason"] == "kit_child_double_count")


def test_bundle_version_hash(tmp_path):
    from tongtool_order_cost.tongtu_cost_engine.domain.bom_cost import load_bundles
    import hashlib
    path = tmp_path / "b.csv"
    pd.DataFrame([
        {"bundle_item": "TJ#X", "component_item": "A", "qty": 1, "bundle_modified": "2026-01-01"},
        {"bundle_item": "TJ#X", "component_item": "B", "qty": 2, "bundle_modified": "2026-01-01"},
    ]).to_csv(path, index=False, encoding="utf-8")
    info = load_bundles(path)["TJ#X"]
    expected = hashlib.sha256("A:1|B:2".encode()).hexdigest()[:12]
    assert info.child_hash == expected
    assert info.version == f"2026-01-01|{expected}"


# ── EN 行级身份 + 单品后缀（单独卖皮壳/海绵/PP棉） ──


def write_items_custom(tmp_path: Path, rows: list[dict]) -> Path:
    path = tmp_path / "items_custom.csv"
    pd.DataFrame(rows, columns=["name", "customer_code", "item_group", "variant_of"]).to_csv(
        path, index=False, encoding="utf-8")
    return path


def test_en_line_resolves_ambiguous_cover_as_standalone(tmp_path):
    """同一 Cover 别名挂两个产品 → EN 行 erp_item_code 唯一指定 KS-B，按单独卖皮壳计价。"""
    items = write_items_custom(tmp_path, [
        {"name": "KS-A-COVER", "customer_code": "SHARED-COVER", "item_group": "靠枕", "variant_of": "KS-A"},
        {"name": "KS-B-COVER", "customer_code": "SHARED-COVER", "item_group": "靠枕", "variant_of": "KS-B"},
    ])
    orders = write_orders(tmp_path, [
        ["ORD-3000001", "PSK", "SHARED-COVER", 1, 10, 50, 0, "WH-PL"],
    ])
    en = write_en(tmp_path, [["ORD-3000001", "SHARED-COVER", "KS-B-COVER", 1, "成品"]])
    shadow = run_merge_shadow(orders, items, en, None, month="202608")
    assert shadow.rows[0].product_id == "KS-B"
    assert shadow.rows[0].resolution_status == "resolved"
    assert shadow.stats["en_line_used"] == 1
    assert shadow.stats["anchor_sources"].get("en_line") == 1

    bom = write_bom(tmp_path, [{
        "item_fg": "KS-B-COVER", "shipping_method": "成品",
        "cost_fg": 40, "cost_sxbzcp": 50,
        "pl_valuation_rate": 7,
        "cover_freight_tmvvepd80f": 3, "freight_tmvvepd80f": 20,
    }])
    p2 = compute_phase2(shadow, bom, items, write_wh_map(tmp_path))
    row = p2.rows[0]
    assert row["status"] == "ok"
    assert row["皮壳成本"] == 40
    assert row["头程运费金额"] == 3          # 皮壳头程
    assert row["绍兴二次加工成本"] == 0
    assert row["二次加工成本"] == 0          # -COVER 加工成本清 0


def test_en_line_overrides_alias_product(tmp_path):
    """别名解析到 KS-OLD，EN 行给 KS-NEW → 以 EN 行为准并记冲突。"""
    items = write_items_custom(tmp_path, [
        {"name": "KS-OLD", "customer_code": "NBOX", "item_group": "靠枕", "variant_of": ""},
        {"name": "KS-NEW", "customer_code": "", "item_group": "靠枕", "variant_of": ""},
    ])
    orders = write_orders(tmp_path, [
        ["ORD-3100001", "PSK", "NBOX", 1, 10, 50, 0, "WH1"],
    ])
    en = write_en(tmp_path, [["ORD-3100001", "NBOX", "KS-NEW", 1, "皮壳"]])
    shadow = run_merge_shadow(orders, items, en, None, month="202608")
    assert shadow.rows[0].product_id == "KS-NEW"
    assert shadow.stats["alias_en_conflict"] == 1


def test_standalone_foam_rows_zero_shell(tmp_path):
    """单独卖海绵（-Foam，非 FBA）：皮壳=0，绍兴二次=绍兴包装成品成本，头程=总额−皮壳。"""
    shadow = _shadow(tmp_path, [
        ["ORD-3200001", "PSK", "TT001-FIN-Foam", 1, 10, 50, 0, "WH-PL"],
    ], [["ORD-3200001", "TT001-FIN-Foam", "", 1, "成品"]])
    bom = write_bom(tmp_path, [{
        "item_fg": "KS100-FINISH-RED", "shipping_method": "成品",
        "cost_fg": 10, "cost_sxbzcp": 50,
        "pl_valuation_rate": 7,
        "cover_freight_tmvvepd80f": 3, "freight_tmvvepd80f": 20,
    }])
    p2 = compute_phase2(shadow, bom, write_items(tmp_path), write_wh_map(tmp_path))
    row = p2.rows[0]
    assert row["皮壳成本"] == 0
    assert row["绍兴二次加工成本"] == 50
    assert row["头程运费金额"] == 17         # 20 − 3
    assert row["二次加工成本"] == 7


def test_standalone_ppcotton_zero_cost(tmp_path):
    """单独卖 PP棉（-PPCOTTON，method=皮壳）：皮壳/绍兴二次/头程 = 0，保留目的地加工。"""
    items = write_items_custom(tmp_path, [
        {"name": "KS-PP", "customer_code": "CURVE-PPCOTTON", "item_group": "靠枕", "variant_of": ""},
    ])
    orders = write_orders(tmp_path, [
        ["ORD-3300001", "PSK", "CURVE-PPCOTTON", 1, 10, 50, 0, "WH-PL"],
    ])
    en = write_en(tmp_path, [["ORD-3300001", "CURVE-PPCOTTON", "", 1, "皮壳"]])
    shadow = run_merge_shadow(orders, items, en, None, month="202608")
    bom = write_bom(tmp_path, [{
        "item_fg": "KS-PP", "shipping_method": "皮壳",
        "cost_fg": 10, "cost_sxbzcp": 5,
        "pl_valuation_rate": 7,
        "cover_freight_tmvvepd80f": 3, "freight_tmvvepd80f": 20,
    }])
    p2 = compute_phase2(shadow, bom, items, write_wh_map(tmp_path))
    row = p2.rows[0]
    assert row["皮壳成本"] == 0
    assert row["绍兴二次加工成本"] == 0
    assert row["头程运费金额"] == 0
    assert row["二次加工成本"] == 7


def test_fba_bypasses_suffix_rules(tmp_path):
    """FBA 仓忽略后缀：仍取 cost_fg + (sx_cost_all−cost_fg) + 成品头程。"""
    shadow = _shadow(tmp_path, [
        ["ORD-3400001", "PSK", "TT001-FIN-Cover", 1, 10, 50, 0, "WH-FBA"],
    ], [["ORD-3400001", "TT001-FIN-Cover", "", 1, "成品"]])
    bom = write_bom(tmp_path, [{
        "item_fg": "KS100-FINISH-RED", "shipping_method": "成品",
        "cost_fg": 10, "sx_cost_all": 25,
        "freight_9rr7m7g3aj": 6,
    }])
    p2 = compute_phase2(shadow, bom, write_items(tmp_path), write_wh_map(tmp_path))
    row = p2.rows[0]
    assert row["皮壳成本"] == 10
    assert row["绍兴二次加工成本"] == 15
    assert row["二次加工成本"] == 0


def test_en_item_unmapped_keeps_ambiguous_block(tmp_path):
    """EN 行给了物料但不在 Item 表 → 不静默回退；别名仍歧义时保持歧义。"""
    items = write_items_custom(tmp_path, [
        {"name": "KS-A-COVER", "customer_code": "SHARED-COVER", "item_group": "靠枕", "variant_of": "KS-A"},
        {"name": "KS-B-COVER", "customer_code": "SHARED-COVER", "item_group": "靠枕", "variant_of": "KS-B"},
    ])
    orders = write_orders(tmp_path, [
        ["ORD-3500001", "PSK", "SHARED-COVER", 1, 10, 50, 0, "WH-PL"],
    ])
    en = write_en(tmp_path, [["ORD-3500001", "SHARED-COVER", "NOT-IN-ITEM-TABLE", 1, "成品"]])
    shadow = run_merge_shadow(orders, items, en, None, month="202608")
    assert shadow.rows[0].resolution_status == "ambiguous"
    assert shadow.stats["en_item_unmapped"] == 1


def test_cover_in_merged_group_defers_to_filler_line(tmp_path):
    """拆单组内 Cover 行不采信自身 EN 物料号；产品身份取填充行（EN 填充行）→ KS-B。"""
    items = write_items_custom(tmp_path, [
        {"name": "KS-A-COVER", "customer_code": "SH-COVER", "item_group": "靠枕", "variant_of": "KS-A"},
        {"name": "KS-B-COVER", "customer_code": "SH-COVER", "item_group": "靠枕", "variant_of": "KS-B"},
        {"name": "KS-B-FOAM", "customer_code": "CURVE-FOAM", "item_group": "靠枕", "variant_of": "KS-B"},
    ])
    orders = write_orders(tmp_path, [
        ["ORD-3600001", "PSK", "SH-COVER", 1, 10, 50, 0, "WH1"],
        ["ORD-3600001", "PSK", "CURVE-FOAM", 0, 0, 0, 0, "WH1"],
    ])
    en = write_en(tmp_path, [
        ["ORD-3600001", "SH-COVER", "KS-A-COVER", 1, "成品"],
        ["ORD-3600001", "CURVE-FOAM", "KS-B-FOAM", 1, "成品"],
    ])
    shadow = run_merge_shadow(orders, items, en, None, month="202608")
    assert shadow.stats["en_line_skipped_cover_in_group"] == 1
    detail = shadow.detail_rows[0]
    assert detail["product_id"] == "KS-B"
    assert detail["merged"] is True


def test_unique_cover_product_overrides_shared_filler(tmp_path):
    """皮壳别名唯一 → 皮壳决定组内产品；共用海绵登记在另一产品上也不采用。"""
    items = write_items_custom(tmp_path, [
        {"name": "KS-DIAMOND-COVER", "customer_code": "DIAMOND-COVER", "item_group": "床头板", "variant_of": "KS-DIAMOND"},
        {"name": "KS-SQUARE", "customer_code": "SHARED-FOAM", "item_group": "床头板", "variant_of": "KS-SQUARE"},
    ])
    orders = write_orders(tmp_path, [
        ["ORD-3700001", "PSK", "DIAMOND-COVER", 1, 10, 50, 0, "WH1"],
        ["ORD-3700001", "PSK", "SHARED-FOAM", 1, 0, 0, 0, "WH1"],
    ])
    en = write_en(tmp_path, [
        ["ORD-3700001", "DIAMOND-COVER", "KS-DIAMOND-COVER", 1, "成品"],
        ["ORD-3700001", "SHARED-FOAM", "KS-SQUARE", 1, "成品"],
    ])
    shadow = run_merge_shadow(orders, items, en, None, month="202608")
    assert shadow.stats["group_cover_override"] == 1
    detail = shadow.detail_rows[0]
    assert detail["product_id"] == "KS-DIAMOND"
    assert detail["merged"] is True
