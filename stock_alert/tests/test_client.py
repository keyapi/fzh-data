from __future__ import annotations

import hashlib

import requests

import stock_alert.client as client_mod
from stock_alert.client import (
    StockRow,
    TongtoolStockClient,
    normalize_row,
    rows_and_total,
)
from tongtool_api.openapi_client import TongToolApiError, TongtoolOpenApiClient, make_sign


# ── 归一化 / 响应解析 ──────────────────────────────────────
def test_rows_and_total_variants():
    assert rows_and_total({"datas": {"array": [1, 2], "total": 5}}) == ([1, 2], 5)
    assert rows_and_total({"datas": {"array": [1, 2]}}) == ([1, 2], None)
    assert rows_and_total({"datas": [1, 2, 3]}) == ([1, 2, 3], None)
    assert rows_and_total({"datas": {"list": [{"a": 1}]}}) == ([{"a": 1}], None)
    assert rows_and_total({"text": "oops"}) == ([], None)


def test_normalize_row_maps_documented_fields():
    row = normalize_row(
        "美中-FZH-DANEEY",
        {"goodsSku": "CEN961NLinen-SageGreen-138", "availableStockQuantity": "0",
         "intransitStockQuantity": 2, "defectsStockQuantity": None},
    )
    assert (row.warehouse, row.sku, row.available, row.intransit, row.defects) == (
        "美中-FZH-DANEEY", "CEN961NLinen-SageGreen-138", 0.0, 2.0, 0.0)


# ── 库存客户端分页 ─────────────────────────────────────────
class _FakeApi:
    def __init__(self, pages):
        self.pages = pages
        self.calls: list[tuple] = []

    def stocks(self, warehouse, page_no=1, page_size=100):
        self.calls.append((warehouse, page_no, page_size))
        return self.pages[page_no - 1] if page_no - 1 < len(self.pages) else {"code": 200, "datas": {"array": []}}


def _page(items, total=None):
    d = {"array": items}
    if total is not None:
        d["total"] = total
    return {"code": 200, "datas": d}


def test_list_stocks_paginates_until_short_page():
    api = _FakeApi([
        _page([{"goodsSku": "A", "availableStockQuantity": 1},
               {"goodsSku": "B", "availableStockQuantity": 9}]),
        _page([{"goodsSku": "C", "availableStockQuantity": 0}]),
    ])
    rows = TongtoolStockClient(api).list_stocks("WH", page_size=2)
    assert [r.sku for r in rows] == ["A", "B", "C"]
    assert [c[1] for c in api.calls] == [1, 2]


def test_list_stocks_respects_explicit_total():
    api = _FakeApi([_page([{"goodsSku": "A", "availableStockQuantity": 1}], total=1)])
    rows = TongtoolStockClient(api).list_stocks("WH", page_size=10)
    assert [r.sku for r in rows] == ["A"]
    assert len(api.calls) == 1


def test_stock_client_no_longer_uses_mcp():
    """回归：MCP 停用后，库存客户端不再依赖 McpClient。"""
    assert not hasattr(client_mod, "McpClient")
    assert not hasattr(client_mod, "extract_payload")


# ── OpenAPI 客户端 ────────────────────────────────────────
class _Resp:
    def __init__(self, payload=None, status_code=200):
        self._payload = payload or {}
        self.status_code = status_code

    def raise_for_status(self):
        if self.status_code >= 400:
            raise requests.HTTPError(str(self.status_code))

    def json(self):
        return self._payload


class _Session:
    def __init__(self, responses):
        self.responses = list(responses)
        self.headers = {}
        self.calls: list[tuple] = []

    def get(self, url, params=None, timeout=None):
        self.calls.append(("GET", url, params))
        return self.responses.pop(0)

    def post(self, url, params=None, json=None, timeout=None):
        self.calls.append(("POST", url, params, json))
        return self.responses.pop(0)


def _auth_responses():
    return [
        _Resp({"success": True, "datas": "TOKEN"}),
        _Resp({"success": True, "datas": [{"partnerOpenId": "M1"}]}),
    ]


def test_make_sign_formula():
    token, ts, secret = "TOKEN", 1700000000, "SECRET"
    expected = hashlib.md5(f"app_token{token}timestamp{ts}{secret}".encode()).hexdigest()
    assert make_sign(token, ts, secret) == expected


def test_openapi_stocks_injects_merchant_id():
    sess = _Session(_auth_responses() + [_Resp({"code": 200, "datas": {"array": []}})])
    api = TongtoolOpenApiClient("K", "S", session=sess, min_interval=0, sleep=lambda _s: None)
    payload = api.stocks("WH", 1, 10)
    assert payload["code"] == 200
    post = [c for c in sess.calls if c[0] == "POST"][0]
    assert post[3]["merchantId"] == "M1"
    assert post[3]["warehouseName"] == "WH"
    assert post[2]["app_token"] == "TOKEN"


def test_openapi_524_is_not_retried():
    sess = _Session(_auth_responses() + [_Resp({"code": 524, "message": "unknown不在白名单列表里"})])
    api = TongtoolOpenApiClient("K", "S", session=sess, min_interval=0, max_retries=3, sleep=lambda _s: None)
    try:
        api.stocks("WH", 1, 10)
    except TongToolApiError as exc:
        assert exc.code == 524
    else:
        raise AssertionError("524 应直接抛出（确定性错误不重试）")
    assert len([c for c in sess.calls if c[0] == "POST"]) == 1


def test_openapi_526_retries_then_succeeds():
    sess = _Session(_auth_responses() + [
        _Resp({"code": 526, "message": "接口请求超频"}),
        _Resp({"code": 200, "datas": {"array": []}}),
    ])
    api = TongtoolOpenApiClient("K", "S", session=sess, min_interval=0, max_retries=3, sleep=lambda _s: None)
    payload = api.stocks("WH", 1, 10)
    assert payload["code"] == 200
    assert len([c for c in sess.calls if c[0] == "POST"]) == 2


def test_openapi_warehouse_query_uses_endpoint():
    sess = _Session(_auth_responses() + [_Resp({"code": 200, "datas": {"array": [{"warehouseName": "W", "status": 1}]}})])
    api = TongtoolOpenApiClient("K", "S", session=sess, min_interval=0, sleep=lambda _s: None)
    api.warehouses()
    post = [c for c in sess.calls if c[0] == "POST"][0]
    assert post[1].endswith("/openapi/tongtool/warehouseQuery")
