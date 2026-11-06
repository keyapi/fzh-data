from __future__ import annotations

import json

from stock_alert.client import (
    CODE_RATE_LIMIT,
    StockRow,
    TongtoolStockClient,
    business_code,
    extract_payload,
    normalize_row,
    rows_and_total,
)


def _resp(payload: dict) -> dict:
    return {"result": {"content": [{"type": "text", "text": json.dumps(payload, ensure_ascii=False)}]}}


class _FakeMcp:
    """按调用顺序返回预置 payload 的假 MCP。"""

    def __init__(self, payloads: list[dict]):
        self.payloads = list(payloads)
        self.calls: list[tuple[str, dict]] = []

    def call(self, name: str, arguments: dict) -> dict:
        self.calls.append((name, arguments))
        payload = self.payloads.pop(0) if self.payloads else {"code": 200, "datas": {"list": [], "total": 0}}
        return _resp(payload)


def test_extract_payload_parses_json_text():
    payload = {"code": 200, "datas": {"total": 0, "list": []}}
    assert extract_payload(_resp(payload)) == payload


def test_extract_payload_raises_on_mcp_error():
    try:
        extract_payload({"error": {"code": -32602, "message": "bad"}})
    except RuntimeError as exc:
        assert "MCP error" in str(exc)
    else:
        raise AssertionError("MCP error 应当抛出")


def test_business_code_reads_variants():
    assert business_code({"code": 200}) == 200
    assert business_code({"businessCode": "526"}) == 526
    assert business_code({}) is None


def test_rows_and_total_supports_common_containers():
    assert rows_and_total({"datas": {"list": [1, 2], "total": 5}}) == ([1, 2], 5)
    assert rows_and_total({"datas": [1, 2, 3]}) == ([1, 2, 3], 3)
    assert rows_and_total({"datas": {"array": [{"a": 1}]}}) == ([{"a": 1}], 1)
    assert rows_and_total({"text": "oops"}) == ([], 0)


def test_normalize_row_maps_documented_fields():
    row = normalize_row(
        "美中-FZH-DANEEY",
        {"goodsSku": "CEN961NLinen-SageGreen-138", "availableStockQuantity": "0",
         "intransitStockQuantity": 2, "defectsStockQuantity": None},
    )
    assert row == StockRow(
        warehouse="美中-FZH-DANEEY",
        sku="CEN961NLinen-SageGreen-138",
        available=0.0,
        intransit=2.0,
        defects=0.0,
        waiting=0.0,
        raw=row.raw,
    )


def test_list_stocks_paginates_until_total_reached():
    page1 = {"code": 200, "datas": {"total": 3, "list": [
        {"goodsSku": "A", "availableStockQuantity": 1},
        {"goodsSku": "B", "availableStockQuantity": 9},
    ]}}
    page2 = {"code": 200, "datas": {"total": 3, "list": [
        {"goodsSku": "C", "availableStockQuantity": 0},
    ]}}
    mcp = _FakeMcp([page1, page2])
    client = TongtoolStockClient(mcp, min_interval=0, sleep=lambda _s: None)
    rows = client.list_stocks("WH", page_size=2)
    assert [r.sku for r in rows] == ["A", "B", "C"]
    assert [c[1]["pageNo"] for c in mcp.calls] == [1, 2]


def test_list_stocks_stops_when_page_empty():
    mcp = _FakeMcp([{"code": 200, "datas": {"total": 0, "list": []}}])
    client = TongtoolStockClient(mcp, min_interval=0, sleep=lambda _s: None)
    assert client.list_stocks("WH", page_size=100) == []
    assert len(mcp.calls) == 1


def test_list_stocks_backs_off_on_526():
    throttle = {"code": CODE_RATE_LIMIT, "datas": None}
    ok = {"code": 200, "datas": {"total": 1, "list": [{"goodsSku": "A", "availableStockQuantity": 0}]}}
    mcp = _FakeMcp([throttle, ok])
    client = TongtoolStockClient(mcp, min_interval=0, max_retries=2, sleep=lambda _s: None)
    rows = client.list_stocks("WH", page_size=10)
    assert [r.sku for r in rows] == ["A"]
    assert len(mcp.calls) == 2


def test_list_stocks_raises_on_business_error():
    mcp = _FakeMcp([{"code": 524, "message": "unauthorized"}])
    client = TongtoolStockClient(mcp, min_interval=0, sleep=lambda _s: None)
    try:
        client.list_stocks("WH", page_size=10)
    except RuntimeError as exc:
        assert "524" in str(exc)
    else:
        raise AssertionError("业务错误码应当抛出")
