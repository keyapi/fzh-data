from __future__ import annotations

import datetime as dt
import os

import pytest
from PIL import Image

from stock_alert import card_image
from stock_alert.client import StockRow
from stock_alert.inbound import aggregate
from stock_alert.scan import apply_names, mark_new, scan

pytestmark = pytest.mark.skipif(not os.path.exists(card_image._FONT_REG), reason="no CJK font")


def _low():
    result = scan({"美中-FZH-DANEEY": [StockRow("美中-FZH-DANEEY", "A", 0, 3)],
                   "美东-CENTRADE": []})
    apply_names(result, {"A": "靠垫甲"})
    mark_new(result, {"美中-FZH-DANEEY": {"A": 8}, "美东-CENTRADE": {}})
    return result


def _inbound():
    return aggregate({"美中-FZH-DANEEY": [{"sku": "A", "voucher_type": "02", "available_increase": 45}],
                      "美东-CENTRADE": []},
                     names={"A": "靠垫甲"}, day=dt.date(2026, 11, 16))


def test_render_low_stock_card(tmp_path):
    path = card_image.render_low_stock(_low(), tmp_path / "low.png",
                                       when=dt.date(2026, 11, 17), new_count=1)
    with Image.open(path) as image:
        assert image.width == 1000
        assert image.height > 400
        assert image.mode == "RGB"


def test_render_inbound_card(tmp_path):
    path = card_image.render_inbound(_inbound(), tmp_path / "inbound.png")
    with Image.open(path) as image:
        assert image.width == 1000
        assert image.height > 400


def test_inbound_card_has_no_item_cap():
    items = [{"sku": f"S{i}", "voucher_type": "02", "available_increase": 1} for i in range(20)]
    many = aggregate({"W": items}, day=dt.date(2026, 11, 16))
    one = aggregate({"W": items[:1]}, day=dt.date(2026, 11, 16))
    assert card_image._inbound_height(many) - card_image._inbound_height(one) == 19 * 66


def test_low_stock_card_has_no_new_item_cap():
    rows = {"W": [StockRow("W", f"S{i}", 1, 0) for i in range(20)]}
    many = scan(rows)
    # 基线里没有这些 SKU → 全部算今日新增
    mark_new(many, {"W": {"OTHER": 10}})
    one = scan({"W": [StockRow("W", "S0", 1, 0)]})
    mark_new(one, {"W": {"OTHER": 10}})
    assert card_image._low_height(many) - card_image._low_height(one) == 19 * card_image.NEW_ROW_H
