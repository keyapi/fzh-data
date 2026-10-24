# -*- coding: utf-8 -*-
"""EN 订单侧输入纯函数测试（合并键 / 件数 / 补发）。用例取 B3 实测真实订单号。"""
from __future__ import annotations

import json
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))

from tongtool_order_cost.order_side_input import (
    ErpnextOrderClient,
    FetchReport,
    Item,
    count_pieces,
    fetch_order_inputs,
    group_order_documents,
    is_cover,
    is_part,
    is_supplementary,
    normalize_order_document,
    order_base,
    platform_body,
    tiktok_platform_body,
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


def test_tiktok_platform_body_rejects_short_or_non_tiktok_bodies():
    assert tiktok_platform_body("TTDaneeyUS-577247129175429589_2") == "577247129175429589"
    assert tiktok_platform_body("TTBNKC-577247129175429589") == "577247129175429589"
    assert tiktok_platform_body("KFL5-A") == ""
    assert tiktok_platform_body("WFUS-CS659537172_2") == ""


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
    # 只发填充件（无成品行）→ 给数并标待复核
    assert count_pieces([Item("X-Foam", 1)]) == (1, "只发部件·待复核")
    assert count_pieces([]) == (0, "空")


def test_count_pieces_plain_product_line_is_one_piece_per_quantity():
    # 裸成品码（无 -Cover/-Foam）：每行本身即成品，按 quantity 计
    assert count_pieces([Item("C/Velvet-Black-100-703-wow", 2)]) == (2, "成品口径")


def test_count_pieces_sums_distinct_products_not_max():
    # 一单两件不同成品（成品 KS0233 + 半成品 KS0205）⇒ 2 件；max 只给 1
    items = [Item("TT0020046K0063668", 1), Item("TT0020038K0063336", 1)]
    assert count_pieces(items) == (2, "成品口径")


def test_count_pieces_ignores_filling_rows_when_no_cover():
    # 无 -Cover，但有成品行 + 填充行：只算成品行
    items = [Item("X-Sofa", 2), Item("X-Foam", 2)]
    assert count_pieces(items) == (2, "成品口径")


def test_count_pieces_prefers_explicit_cover_over_shipping_method_component():
    items = [
        Item("Curve-Pillow-50-PPCotton", 1, "皮壳"),
        Item("Curve-Pillow-50-Cover", 1, "成品"),
    ]
    assert count_pieces(items) == (1, "皮壳口径")


def test_count_pieces_plain_cover_sku_with_pikou_shipping_counts_by_quantity():
    # 裸码 + EN 发货方式=皮壳：不是填充件，按成品口径计
    assert count_pieces([Item("C/Velvet-Black-100-703-wow", 2, "皮壳")]) == (2, "成品口径")


def test_count_pieces_ignores_empty_sku_placeholder_rows():
    # EN 里存在空 SKU 的占位行（脏数据），不能算成成品
    assert count_pieces([Item("C/Linen-DKBlue-100-660-WOW", 1, "皮壳"), Item("", 1)]) == (
        1,
        "成品口径",
    )
    assert count_pieces([Item("", 1)]) == (0, "空")


def test_count_pieces_merges_split_package_part_rows():
    # 同一件的第 2 个包裹：SKU `<base>-2` 且 base 也在同一单 → 不另计件
    items = [Item("TT0031217K0064032", 1, "成品"), Item("TT0031217K0064032-2", 1, "成品")]
    assert count_pieces(items) == (1, "成品口径")
    # base 不在同一单时，`-N` 行本身是独立成品，照常计
    assert count_pieces([Item("TT0031217K0064032-2", 1)]) == (1, "成品口径")


def test_count_pieces_sums_multiple_distinct_products_in_set():
    # 4 件套：4 个不同成品各 1 件 ⇒ 4
    items = [Item(f"TT0312637K00642{i}", 1, "皮壳") for i in (67, 70, 76, 79)]
    assert count_pieces(items) == (4, "成品口径")
    # 2 个成品各 qty2 ⇒ 4
    assert count_pieces(
        [Item("TT0312639K0064283", 2, "皮壳"), Item("TT0312639K0064284", 2, "皮壳")]
    ) == (4, "成品口径")


def test_normalize_order_document_keeps_cost_and_relationship_fields():
    doc = {
        "name": "RSUS-112-9990006-6105830_1-M2001",
        "warehouse_name": "美国仓",
        "is_supplementary": "是",
        "order_items": [
            {
                "tongtool_sku": "A-Cover",
                "platform_sku": "PL-A",
                "erp_item_code": "ITEM-A",
                "quantity": 1,
                "shipping_method": "成品",
                "split_package_cost_factor": 0.5,
                "cost_fg": 10,
                "cost_sxbzcp": 2,
                "cost_sxbzbcp": 3,
                "sx_shipping_cost": 4,
                "first_freight": 5,
                "bcp_first_freight": 6,
                "pk_first_freight": 7,
                "last_leg_fee": 8,
            },
            {
                "tongtool_sku": "A-Foam",
                "quantity": 1,
                "shipping_method": "成品",
            },
        ],
    }

    row = normalize_order_document(doc, requested_order_id=doc["name"])

    assert row.order_id == doc["name"]
    assert row.base_order_id == "RSUS-112-9990006-6105830"
    assert row.is_child is True
    assert row.original_order_exists is None
    assert row.is_supplementary is True
    assert row.piece_count == 1
    assert row.piece_rule == "皮壳口径"
    assert row.shipping_methods == ("成品",)
    assert row.status == "ok"
    assert row.items[0].split_package_cost_factor == 0.5
    assert row.items[0].cost_fg == 10.0
    assert row.items[0].last_leg_fee == 8.0


def test_normalize_order_document_marks_empty_shell_and_no_cover():
    empty = normalize_order_document(
        {"name": "EMPTY-1", "warehouse_name": "", "order_items": []}
    )
    assert empty.status == "empty_shell"
    assert empty.piece_count == 0

    no_cover = normalize_order_document(
        {
            "name": "PART-1",
            "warehouse_name": "美国仓",
            "order_items": [{"tongtool_sku": "X-Foam", "quantity": 2}],
        }
    )
    assert no_cover.status == "review"
    assert no_cover.piece_count == 2
    assert no_cover.piece_rule == "只发部件·待复核"


def test_fetch_order_inputs_keeps_parent_state_unknown_until_checked():
    documents = {
        "ORDER-1": {
            "name": "ORDER-1",
            "order_items": [{"tongtool_sku": "X-Cover", "quantity": 1}],
        }
    }

    class FakeClient:
        def get_order(self, order_id: str):
            return documents.get(order_id)

    unchecked_rows, _ = fetch_order_inputs(FakeClient(), ["ORDER-1"])
    assert unchecked_rows[0].original_order_exists is None
    assert unchecked_rows[0].status == "ok"

    checked_rows, _ = fetch_order_inputs(FakeClient(), ["ORDER-1", "ORDER"])
    assert checked_rows[0].original_order_exists is False
    assert checked_rows[0].status == "child_only"

    documents["ORDER"] = {
        "name": "ORDER",
        "order_items": [{"tongtool_sku": "X-Cover", "quantity": 1}],
    }
    existing_rows, report = fetch_order_inputs(FakeClient(), ["ORDER-1", "ORDER"])
    assert existing_rows[0].original_order_exists is True
    assert existing_rows[0].status == "ok"
    assert report.child_only_count == 0


def test_erpnext_order_client_retries_transient_status_and_handles_404():
    class FakeResponse:
        def __init__(self, status_code: int, data=None):
            self.status_code = status_code
            self._data = data

        def raise_for_status(self):
            if self.status_code >= 400:
                raise RuntimeError(f"HTTP {self.status_code}")

        def json(self):
            return {"data": self._data}

    class FakeSession:
        def __init__(self, responses):
            self.responses = iter(responses)
            self.urls = []

        def get(self, url, timeout):
            self.urls.append(url)
            return next(self.responses)

    client = ErpnextOrderClient("https://example.invalid", "key", "secret", retries=1)
    session = FakeSession(
        [FakeResponse(503), FakeResponse(200, {"name": "ORDER / 1"})]
    )
    client.session = session

    assert client.get_order("ORDER / 1") == {"name": "ORDER / 1"}
    assert len(session.urls) == 2
    assert session.urls[0].endswith("/Tongtool%20Order/ORDER%20%2F%201")

    client.session = FakeSession([FakeResponse(404)])
    assert client.get_order("MISSING") is None


def test_fetch_order_inputs_reports_every_requested_order():
    documents = {
        "GOOD-1": {
            "name": "GOOD-1",
            "warehouse_name": "美国仓",
            "order_items": [{"tongtool_sku": "X-Cover", "quantity": 1}],
        },
        "EMPTY-1": {"name": "EMPTY-1", "warehouse_name": "", "order_items": []},
    }

    class FakeClient:
        def get_order(self, order_id: str):
            if order_id in {"GOOD", "EMPTY", "MISSING-1"}:
                return None
            if order_id == "BROKEN-1":
                raise RuntimeError("boom")
            return documents[order_id]

    rows, report = fetch_order_inputs(
        FakeClient(),
        ["GOOD-1", "GOOD", "EMPTY-1", "EMPTY", "MISSING-1", "BROKEN-1"],
    )

    assert len(rows) == 2
    assert rows[0].original_order_exists is False
    assert rows[0].status == "child_only"
    assert rows[1].original_order_exists is False
    assert report == FetchReport(
        input_count=6,
        fetched_count=2,
        missing_count=3,
        failed_count=1,
        empty_shell_count=1,
        supplementary_count=0,
        parts_only_count=0,
        child_only_count=2,
        failures=("BROKEN-1: RuntimeError: boom",),
        missing_order_ids=("GOOD", "EMPTY", "MISSING-1"),
    )


def test_erpnext_order_client_pages_parent_and_child_lists():
    class FakeResponse:
        status_code = 200

        def __init__(self, data):
            self._data = data

        def raise_for_status(self):
            pass

        def json(self):
            return {"data": self._data}

    class FakeSession:
        def __init__(self):
            self.calls = []

        def get(self, url, params=None, timeout=None):
            self.calls.append((url, params, timeout))
            offset = params["limit_start"]
            if offset == 0:
                return FakeResponse([{"name": "ORDER-1"}, {"name": "ORDER-2"}])
            return FakeResponse([{"name": "ORDER-3"}])

    client = ErpnextOrderClient("https://example.invalid", "key", "secret")
    session = FakeSession()
    client.session = session

    rows = client.list_documents(
        "Tongtool Order",
        ["name", "warehouse_name"],
        page_size=2,
    )

    assert rows == [
        {"name": "ORDER-1"},
        {"name": "ORDER-2"},
        {"name": "ORDER-3"},
    ]
    assert len(session.calls) == 2
    assert json.loads(session.calls[0][1]["fields"]) == ["name", "warehouse_name"]
    assert "parent" not in session.calls[0][1]

    session.calls.clear()
    client.list_order_items(["name", "parent"], page_size=2)
    assert session.calls[0][1]["parent"] == "Tongtool Order"


def test_erpnext_order_client_filters_orders_and_items_by_id_chunks():
    class FakeResponse:
        status_code = 200

        def __init__(self, data):
            self._data = data

        def raise_for_status(self):
            pass

        def json(self):
            return {"data": self._data}

    class FakeSession:
        def __init__(self):
            self.calls = []

        def get(self, url, params=None, timeout=None):
            self.calls.append((url, params, timeout))
            filters = json.loads(params["filters"])
            return FakeResponse([{"name": value} for value in filters[0][2]])

    client = ErpnextOrderClient("https://example.invalid", "key", "secret")
    session = FakeSession()
    client.session = session

    parents = client.list_orders_by_ids(["A", "B", "C"], chunk_size=2)
    assert parents == [{"name": "A"}, {"name": "B"}, {"name": "C"}]
    assert len(session.calls) == 2
    assert json.loads(session.calls[0][1]["filters"]) == [["name", "in", ["A", "B"]]]

    session.calls.clear()
    children = client.list_order_items_by_order_ids(["A", "B"], chunk_size=2)
    assert children == [{"name": "A"}, {"name": "B"}]
    assert session.calls[0][1]["parent"] == "Tongtool Order"
    assert json.loads(session.calls[0][1]["filters"]) == [["parent", "in", ["A", "B"]]]


def test_group_order_documents_joins_children_and_keeps_empty_shells():
    parents = [
        {"name": "ORDER-1", "warehouse_name": "美国仓"},
        {"name": "EMPTY-1", "warehouse_name": ""},
    ]
    children = [
        {
            "name": "ITEM-1",
            "parent": "ORDER-1",
            "tongtool_sku": "A-Cover",
            "quantity": 1,
            "shipping_method": "成品",
        },
        {
            "name": "ITEM-2",
            "parent": "ORDER-1",
            "tongtool_sku": "A-Foam",
            "quantity": 1,
            "shipping_method": "半成品",
        },
        {"name": "ORPHAN", "parent": "NOT-FETCHED", "quantity": 1},
    ]

    documents = group_order_documents(parents, children)

    assert documents == [
        {
            "name": "ORDER-1",
            "warehouse_name": "美国仓",
            "order_items": children[:2],
        },
        {"name": "EMPTY-1", "warehouse_name": "", "order_items": []},
    ]
    row = normalize_order_document(documents[0])
    assert row.shipping_methods == ("半成品", "成品")
