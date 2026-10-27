from __future__ import annotations

from datetime import date, datetime, timezone
from decimal import Decimal

import pytest

from tongtool_api.purchase_receipts import (
    PURCHASE_STOCK_QUERY_TOOL,
    fetch_receipts,
    normalize_receipts,
)


def mcp_response(rows: list[dict], page_no: int, page_size: int) -> dict:
    import json

    return {
        "result": {
            "content": [
                {
                    "type": "text",
                    "text": json.dumps(
                        {
                            "code": 200,
                            "datas": {
                                "pageNo": page_no,
                                "pageSize": page_size,
                                "array": rows,
                            },
                        }
                    ),
                }
            ]
        }
    }


def test_fetches_all_pages_with_bounded_query_and_throttles_between_calls() -> None:
    rows = [[{"sku": "SKU-A"}, {"sku": "SKU-B"}], [{"sku": "SKU-C"}]]
    calls: list[tuple[str, dict]] = []
    sleeps: list[float] = []

    def caller(tool: str, arguments: dict) -> dict:
        calls.append((tool, arguments))
        page = arguments["pageNo"]
        return mcp_response(rows[page - 1], page_no=page, page_size=2)

    result = fetch_receipts(
        caller,
        "2026-10-15 00:00:00",
        "2026-10-16 00:00:00",
        po_code="PO-123",
        page_size=2,
        max_pages=3,
        sleep=sleeps.append,
    )

    assert [tool for tool, _ in calls] == [PURCHASE_STOCK_QUERY_TOOL] * 2
    assert calls[0][1] == {
        "warehousingDateFrom": "2026-10-15 00:00:00",
        "warehousingDateTo": "2026-10-16 00:00:00",
        "purchaseOrderCode": "PO-123",
        "pageNo": 1,
        "pageSize": 2,
    }
    assert calls[1][1]["pageNo"] == 2
    assert sleeps == [13.0]
    assert [r["sku"] for r in result.rows] == ["SKU-A", "SKU-B", "SKU-C"]
    assert result.complete is True
    assert result.truncated is False


def test_normalizes_aware_bounds_to_shanghai_and_expands_date_only_end() -> None:
    calls: list[dict] = []

    def caller(_tool: str, arguments: dict) -> dict:
        calls.append(arguments)
        return mcp_response([], page_no=1, page_size=100)

    fetch_receipts(
        caller,
        datetime(2026, 10, 14, 16, 30, tzinfo=timezone.utc),
        date(2026, 10, 15),
        sleep=lambda _: None,
    )

    assert calls[0]["warehousingDateFrom"] == "2026-10-15 00:30:00"
    assert calls[0]["warehousingDateTo"] == "2026-10-15 23:59:59"


def test_accepts_utc_z_bounds_and_formats_them_in_shanghai() -> None:
    calls: list[dict] = []

    def caller(_tool: str, arguments: dict) -> dict:
        calls.append(arguments)
        return mcp_response([], page_no=1, page_size=100)

    fetch_receipts(
        caller,
        "2026-10-15T00:00:00Z",
        "2026-10-15T01:00:00Z",
        sleep=lambda _: None,
    )

    assert calls[0]["warehousingDateFrom"] == "2026-10-15 08:00:00"
    assert calls[0]["warehousingDateTo"] == "2026-10-15 09:00:00"


def test_normalizes_aware_string_bounds_and_mixed_date_datetime() -> None:
    calls: list[dict] = []

    def caller(_tool: str, arguments: dict) -> dict:
        calls.append(arguments)
        return mcp_response([], page_no=1, page_size=100)

    fetch_receipts(
        caller,
        "2026-10-15T23:30:00-04:00",
        "2026-10-16 13:00:00",
        sleep=lambda _: None,
    )

    assert calls[0]["warehousingDateFrom"] == "2026-10-16 11:30:00"
    assert calls[0]["warehousingDateTo"] == "2026-10-16 13:00:00"


def test_rejects_reversed_instants_after_timezone_conversion() -> None:
    with pytest.raises(ValueError, match="after"):
        fetch_receipts(
            lambda _tool, _arguments: pytest.fail("must validate before calling"),
            "2026-10-15T12:00:00+08:00",
            "2026-10-15T03:00:00Z",
            sleep=lambda _: None,
        )


def test_full_last_page_at_limit_is_marked_incomplete() -> None:
    calls: list[dict] = []

    def caller(_tool: str, arguments: dict) -> dict:
        calls.append(arguments)
        return mcp_response([{"sku": "SKU-A"}], page_no=1, page_size=1)

    result = fetch_receipts(
        caller,
        "2026-10-15 00:00:00",
        "2026-10-16 00:00:00",
        page_size=1,
        max_pages=1,
        sleep=lambda _: None,
    )

    assert len(calls) == 1
    assert result.complete is False
    assert result.truncated is True


@pytest.mark.parametrize(
    "request_page_size,response_page_no,response_page_size,expected_calls",
    [(1, 1, 1, 2), (2, 1, 1, 1)],
)
def test_rejects_response_page_echo_that_does_not_match_request(
    request_page_size: int,
    response_page_no: int,
    response_page_size: int,
    expected_calls: int,
) -> None:
    calls = 0

    def caller(_tool: str, _arguments: dict) -> dict:
        nonlocal calls
        calls += 1
        return mcp_response(
            [{"sku": f"SKU-{calls}"}],
            page_no=response_page_no,
            page_size=response_page_size,
        )

    with pytest.raises(RuntimeError, match="pageNo|pageSize"):
        fetch_receipts(
            caller,
            "2026-10-15",
            "2026-10-16",
            page_size=request_page_size,
            max_pages=2,
            sleep=lambda _: None,
        )

    assert calls == expected_calls


def test_missing_page_echoes_do_not_fail() -> None:
    import json

    response = {
        "result": {
            "content": [
                {"type": "text", "text": json.dumps({"code": 200, "datas": {"array": []}})}
            ]
        }
    }

    result = fetch_receipts(
        lambda _tool, _arguments: response,
        "2026-10-15",
        "2026-10-16",
        sleep=lambda _: None,
    )

    assert result.complete is True


def test_empty_first_page_is_successful_complete_result() -> None:
    result = fetch_receipts(
        lambda _tool, _arguments: mcp_response([], page_no=1, page_size=100),
        "2026-10-15",
        "2026-10-16",
        sleep=lambda _: None,
    )

    assert result.rows == []
    assert result.complete is True
    assert result.truncated is False


@pytest.mark.parametrize(
    "response,match",
    [
        ({"error": {"code": -32603, "message": "rpc failed"}}, "MCP RPC"),
        (
            {
                "result": {
                    "content": [{"type": "text", "text": '{"code":526,"msg":"rate limited"}'}]
                }
            },
            "526",
        ),
    ],
)
def test_rpc_and_business_errors_raise_without_retry(response: dict, match: str) -> None:
    calls = 0

    def caller(_tool: str, _arguments: dict) -> dict:
        nonlocal calls
        calls += 1
        return response

    with pytest.raises(RuntimeError, match=match):
        fetch_receipts(
            caller,
            "2026-10-15",
            "2026-10-16",
            sleep=lambda _: None,
        )

    assert calls == 1


def test_normalization_marks_weak_identity_and_unknown_uom_and_keeps_duplicate_events() -> None:
    raw = {
        "purchaseOrderCode": "PO-123",
        "purchaseOrderId": "po-id",
        "goodsDetailId": "goods-id",
        "sku": "SKU-A",
        "warehouseName": "WH-A",
        "warehousingNum": "2.5",
        "quantity": "10",
        "warehousingDate": "2026-10-15 11:35:04",
        "purchaseDate": "2026-10-01 08:00:00",
        "createdDate": "2026-10-02T10:00:00Z",
        "amount": "12.30",
        "actualPayments": "11.00",
        "shippingCost": "3.00",
        "unitPrice": "4.92",
    }

    normalized = normalize_receipts([raw, dict(raw)])

    assert len(normalized) == 2
    row = normalized[0]
    assert row["source_index"] == 0
    assert row["raw"] == raw
    assert row["purchase_order_code"] == "PO-123"
    assert row["purchase_date"].isoformat(sep=" ") == "2026-10-01 08:00:00"
    assert row["purchase_date_source_field"] == "purchaseDate"
    assert row["purchase_date_timezone_status"] == "unverified"
    assert row["created_date"].isoformat(sep=" ") == "2026-10-02 10:00:00+00:00"
    assert row["created_date_source_field"] == "createdDate"
    assert row["created_date_timezone_status"] == "unverified"
    assert row["warehousing_date"].isoformat(sep=" ") == "2026-10-15 11:35:04"
    assert row["warehousing_date_source_field"] == "warehousingDate"
    assert row["time_timezone_status"] == "unverified"
    assert row["time_source_timezone"] == "unverified"
    assert row["reported_receipt_quantity"] == Decimal("2.5")
    assert row["reported_receipt_quantity_source_field"] == "warehousingNum"
    assert row["order_quantity"] == Decimal("10")
    assert row["order_quantity_source_field"] == "quantity"
    assert row["reported_receipt_quantity"] != Decimal(row["raw"]["amount"])
    assert "amount" not in row
    assert "actual_payments" not in row
    assert "shipping_cost" not in row
    assert "unit_price" not in row
    assert row["identity_confidence"] == "weak_identity"
    assert row["event_id"] is None
    assert row["uom"] is None
    assert row["uom_confidence"] == "unknown_uom"


def test_missing_warehousing_time_does_not_fall_back_to_po_or_arrival_time() -> None:
    [row] = normalize_receipts(
        [
            {
                "purchaseDate": "2026-10-15 09:00:00",
                "purchaseArrivalDate": "2026-10-15 09:30:00",
            }
        ]
    )

    assert row["warehousing_date"] is None
    assert row["warehousing_date_source_field"] == "warehousingDate"
    assert row["purchase_date"].isoformat(sep=" ") == "2026-10-15 09:00:00"
    assert row["created_date"] is None
    assert row["created_date_source_field"] == "createdDate"


def test_warehousing_date_accepts_utc_z_timestamp() -> None:
    [row] = normalize_receipts([{"warehousingDate": "2026-10-15T11:35:04Z"}])

    assert row["warehousing_date"].isoformat(sep=" ") == "2026-10-15 11:35:04+00:00"


@pytest.mark.parametrize(
    "field,value",
    [
        ("warehousingNum", "not-a-number"),
        ("warehousingDate", "not-a-date"),
    ],
)
def test_invalid_numeric_and_datetime_values_raise(field: str, value: str) -> None:
    with pytest.raises(ValueError, match=field):
        normalize_receipts([{field: value}])


def test_bad_financial_amount_does_not_block_receipt_quantity_or_time() -> None:
    [row] = normalize_receipts(
        [
            {
                "warehousingNum": "2.5",
                "quantity": "10",
                "warehousingDate": "2026-10-15 11:35:04",
                "amount": "not-a-number",
            }
        ]
    )

    assert row["source_index"] == 0
    assert row["reported_receipt_quantity"] == Decimal("2.5")
    assert row["order_quantity"] == Decimal("10")
    assert row["warehousing_date"].isoformat(sep=" ") == "2026-10-15 11:35:04"
    assert row["raw"]["amount"] == "not-a-number"
    assert "amount" not in row
