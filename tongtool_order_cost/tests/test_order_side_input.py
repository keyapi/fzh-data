# -*- coding: utf-8 -*-
"""EN 订单侧输入纯函数测试（合并键 / 件数 / 补发）。用例取 B3 实测真实订单号。"""
from __future__ import annotations

import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))

from tongtool_order_cost.order_side_input import (
    Item,
    count_pieces,
    is_cover,
    is_part,
    is_supplementary,
    order_base,
    platform_body,
)


def test_order_base_strips_only_1_2_digit_suffix():
    assert order_base("DY-LAPW-24868_1") == "DY-LAPW-24868"
    assert order_base("WFUS-CS659537172_2") == "WFUS-CS659537172"
    assert order_base("OS-474530280") == "OS-474530280"  # 9 位本体不被吃掉
    assert order_base("OS-468010867_1") == "OS-468010867"
    assert order_base("OS-468672500-1") == "OS-468672500"
    assert order_base("PBUS-137242161") == "PBUS-137242161"


def test_order_base_keeps_supplementary_marker():
    assert order_base("RSUS-112-9990006-6105830_1-M2001") == "RSUS-112-9990006-6105830"


def test_platform_body_matches_across_prefixes():
    a = platform_body("TTDaneeyUS-577247129175429589_2")
    b = platform_body("TTDaneeyGo-577247129175429589")
    c = platform_body("TTBNKC-577247129175429589")
    assert a == b == c == "577247129175429589"


def test_is_supplementary():
    assert is_supplementary("TOODDLYUS-112-6886198-5601804-M8132") is True
    assert is_supplementary("RSUS-112-9990006-6105830_1-M2001") is True
    assert is_supplementary("WFUS-CS659537172_1") is False
    assert is_supplementary("WFUS-CS659537172_1", flag="是") is True


def test_cover_part_classification():
    assert is_cover("TT0031246K0064094-Cover")
    assert not is_cover("Curve-Pillow-50-PPCotton")  # PP棉内胆不是皮壳
    assert is_part("TT0031246K0064094-Foam")
    assert is_part("TT0312701K0064561", "松饼大沙发 主体骨架")


def test_count_pieces_cover_sum_not_max():
    # 1 件成品 = 皮壳1 + 海绵1
    assert count_pieces([Item("X-Cover", 1), Item("X-Foam", 1)]) == (1, "皮壳口径")
    # MXXXL：3 色皮壳各3 + 海绵9 ⇒ 9 件
    items = [Item(f"KS-Cover{i}", 3) for i in range(3)] + [Item("X-Foam", 9)]
    assert count_pieces(items) == (9, "皮壳口径")
    # RSUS-112-9990006：皮壳A3 海绵3 皮壳B1 海绵1 ⇒ 4 件（max 只给 3）
    items = [Item("A-Cover", 3), Item("A-Foam", 3), Item("B-Cover", 1), Item("B-Foam", 1)]
    assert count_pieces(items) == (4, "皮壳口径")
    # 多色各一件：3 皮壳各1 + 3 海绵各1 ⇒ 3 件（max 只给 1）
    items = [Item(f"C-Cover{i}", 1) for i in range(3)] + [Item(f"C-Foam{i}", 1) for i in range(3)]
    assert count_pieces(items) == (3, "皮壳口径")


def test_count_pieces_fallback_no_cover():
    assert count_pieces([Item("X-Foam", 1)]) == (1, "无皮壳·待复核")
    assert count_pieces([]) == (0, "空")
