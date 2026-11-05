# -*- coding: utf-8 -*-
"""Phase 1 同订单锚定：CURVE-PILLOW Cover 歧义（PPCotton/Foam）锁定产品线。"""
from __future__ import annotations

import sys
from pathlib import Path

import pandas as pd

_ROOT = Path(__file__).resolve().parents[1]
if str(_ROOT) not in sys.path:
    sys.path.insert(0, str(_ROOT))

from tongtool_order_cost.tongtu_cost_engine.domain.split_merge import (  # noqa: E402
    EnResolver,
    load_orders,
)

ORDER_COLS = ["订单号", "平台SKU", "通途SKU", "发货数量", "售价", "售价(人民币)"]


def _resolver(tmp_path: Path) -> EnResolver:
    ref = tmp_path / "item_refcode.csv"
    pd.DataFrame([
        {"name": "KS-A-1", "customer_code": "CURVE-PP,C-COVER",
         "item_group": "弧形PP棉靠枕-拉链款", "variant_of": "KS-A"},
        {"name": "KS-B-1", "customer_code": "CURVE-FOAM,C-COVER",
         "item_group": "弧形海绵靠枕-拉链款", "variant_of": "KS-B"},
    ]).to_csv(ref, index=False, encoding="utf-8")
    return EnResolver.from_items_csv(ref)


def _orders(tmp_path: Path) -> Path:
    rows = [
        # O1：Cover + 同订单 PPCotton 行
        {"订单号": "O1", "平台SKU": "Curve-Pillow-Linen-PPCotton-Yellow-50",
         "通途SKU": "C-COVER", "发货数量": "1", "售价": "10", "售价(人民币)": "70"},
        {"订单号": "O1", "平台SKU": "Curve-Pillow-Linen-PPCotton-Yellow-50",
         "通途SKU": "CURVE-PP", "发货数量": "1", "售价": "0", "售价(人民币)": "0"},
        # O2：只有 Cover，平台 SKU 自带 Foam
        {"订单号": "O2", "平台SKU": "Curve-Pillow-Linen-Foam-White-50",
         "通途SKU": "C-COVER", "发货数量": "1", "售价": "10", "售价(人民币)": "70"},
        # O3：两条线都在，平台 SKU 自带 Foam
        {"订单号": "O3", "平台SKU": "Curve-Pillow-Linen-Foam-Yellow-50",
         "通途SKU": "C-COVER", "发货数量": "1", "售价": "10", "售价(人民币)": "70"},
        {"订单号": "O3", "平台SKU": "Curve-Pillow-50-PPCotton",
         "通途SKU": "CURVE-PP", "发货数量": "1", "售价": "0", "售价(人民币)": "0"},
        {"订单号": "O3", "平台SKU": "Curve-Pillow-50-Foam",
         "通途SKU": "CURVE-FOAM", "发货数量": "1", "售价": "0", "售价(人民币)": "0"},
        # O4：两条线都在，平台无材质词 → 按颜色（Ivory 只在 PPCotton 行）
        {"订单号": "O4", "平台SKU": "Et-zipperpillow-Ivory",
         "通途SKU": "C-COVER", "发货数量": "1", "售价": "10", "售价(人民币)": "70"},
        {"订单号": "O4", "平台SKU": "Curve-Pillow-50-PPCotton-Ivory",
         "通途SKU": "CURVE-PP", "发货数量": "1", "售价": "0", "售价(人民币)": "0"},
        {"订单号": "O4", "平台SKU": "Curve-Pillow-50-Foam-Gray",
         "通途SKU": "CURVE-FOAM", "发货数量": "1", "售价": "0", "售价(人民币)": "0"},
        # O5：两条线都在，颜色对不上 → 保持歧义
        {"订单号": "O5", "平台SKU": "Et-zipperpillow-Blush",
         "通途SKU": "C-COVER", "发货数量": "1", "售价": "10", "售价(人民币)": "70"},
        {"订单号": "O5", "平台SKU": "Curve-Pillow-50-PPCotton-Ivory",
         "通途SKU": "CURVE-PP", "发货数量": "1", "售价": "0", "售价(人民币)": "0"},
        {"订单号": "O5", "平台SKU": "Curve-Pillow-50-Foam-Gray",
         "通途SKU": "CURVE-FOAM", "发货数量": "1", "售价": "0", "售价(人民币)": "0"},
    ]
    p = tmp_path / "raw_orders.csv"
    pd.DataFrame(rows, columns=ORDER_COLS).to_csv(p, index=False, encoding="utf-8")
    return p


def _en(tmp_path: Path) -> Path:
    rows = []
    for oid in ("O1", "O2", "O3", "O4", "O5"):
        for sku in ("C-COVER", "CURVE-PP", "CURVE-FOAM"):
            rows.append({"order_id_code": oid, "tongtool_sku": sku,
                         "shipping_method": "皮壳"})
    p = tmp_path / "en_items.csv"
    pd.DataFrame(rows).to_csv(p, index=False, encoding="utf-8")
    return p


def test_curve_cover_anchor_same_order_material_and_color(tmp_path):
    resolver = _resolver(tmp_path)
    loaded = load_orders(_orders(tmp_path), resolver, _en(tmp_path))

    covers = {
        (r.order_id, r.raw["平台SKU"]): r
        for r in loaded.rows if r.sku == "C-COVER"
    }
    o1 = covers[("O1", "Curve-Pillow-Linen-PPCotton-Yellow-50")]
    assert o1.product_id == "KS-A" and o1.resolution_status == "resolved"
    assert o1.raw["_anchor_source"] == "same_order"

    o2 = covers[("O2", "Curve-Pillow-Linen-Foam-White-50")]
    assert o2.product_id == "KS-B" and o2.raw["_anchor_source"] == "material"

    o3 = covers[("O3", "Curve-Pillow-Linen-Foam-Yellow-50")]
    assert o3.product_id == "KS-B" and o3.raw["_anchor_source"] == "material"

    o4 = covers[("O4", "Et-zipperpillow-Ivory")]
    assert o4.product_id == "KS-A" and o4.raw["_anchor_source"] == "color"

    o5 = covers[("O5", "Et-zipperpillow-Blush")]
    assert o5.product_id == "" and o5.resolution_status == "ambiguous"

    # 仍歧义的只剩 O5 一行
    amb = [i for i in loaded.sku_issues if i["status"] == "ambiguous"]
    assert len(amb) == 1 and amb[0]["rows"] == 1 and amb[0]["sku"] == "C-COVER"
    assert not [i for i in loaded.sku_issues if i["status"] == "unresolved"]


def test_mixed_cover_fill_method_uses_fill_row(tmp_path):
    """Cover 行与填充行 method 不同 → 以非 Cover 行为准；两条填充行仍不一致才阻断。"""
    from tongtool_order_cost.tongtu_cost_engine.domain.split_merge import OrderRow, _pick_carrier

    def row(sku: str, method: str, i: int) -> OrderRow:
        return OrderRow(
            index=i, order_id="O1", order_common="O1", platform_sku="P",
            sku_raw=sku, sku=sku, qty=1.0, sale=0.0, sale_cny=0.0, freight=None,
            product_id="KS-A", item_group="g", resolution_status="resolved",
            shipping_method=method, method_source="en", raw={},
        )

    cover_finished = [row("C-COVER", "成品", 0), row("CURVE-PP", "皮壳", 1)]
    assert _pick_carrier(cover_finished)[0] == "皮壳"

    cover_foam = [row("C-COVER", "皮壳", 0), row("CURVE-FOAM", "成品", 1)]
    assert _pick_carrier(cover_foam)[0] == "成品"

    two_fills = [row("C-COVER", "成品", 0), row("CURVE-PP", "皮壳", 1),
                 row("CURVE-FOAM", "成品", 2)]
    assert _pick_carrier(two_fills)[3] == "mixed_methods"

    only_cover = [row("C-COVER", "皮壳", 0)]
    assert _pick_carrier(only_cover)[0] == "皮壳"
