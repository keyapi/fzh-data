"""Read-only adapter for Tongtool ERP2 purchase stock-in records."""
from __future__ import annotations

import json
import time
from dataclasses import dataclass
from datetime import date, datetime, time as datetime_time
from decimal import Decimal, InvalidOperation
from typing import Callable, Iterable
from zoneinfo import ZoneInfo

PURCHASE_STOCK_QUERY_TOOL = "erp2_purchase_purchasestockquery"
CALL_INTERVAL_SECONDS = 13.0
MAX_PAGE_SIZE = 100
BUSINESS_TIMEZONE = ZoneInfo("Asia/Shanghai")


@dataclass(frozen=True)
class ReceiptFetchResult:
    """Fetched rows plus explicit pagination completeness."""

    rows: list[dict]
    pages_fetched: int
    complete: bool
    truncated: bool


def _parse_bound(value: str | date | datetime, field: str, *, end_of_day: bool) -> datetime:
    """Parse a bound; naive values mean Asia/Shanghai business time."""
    if isinstance(value, datetime):
        parsed = value
    elif isinstance(value, date):
        parsed = datetime.combine(
            value, datetime_time.max.replace(microsecond=0) if end_of_day else datetime_time.min
        )
    elif isinstance(value, str) and value.strip():
        text = value.strip()
        try:
            if len(text) == 10:
                parsed = datetime.combine(
                    date.fromisoformat(text),
                    datetime_time.max.replace(microsecond=0) if end_of_day else datetime_time.min,
                )
            else:
                iso_text = text[:-1] + "+00:00" if text[-1:].upper() == "Z" else text
                parsed = datetime.fromisoformat(iso_text)
        except ValueError as error:
            raise ValueError(f"{field} must be an ISO date or datetime") from error
    else:
        raise ValueError(f"{field} must be a non-empty date or datetime")

    if parsed.tzinfo is not None and parsed.utcoffset() is not None:
        return parsed.astimezone(BUSINESS_TIMEZONE).replace(tzinfo=None, microsecond=0)
    # API parameters use the business timezone and have no offset slot.
    return parsed.replace(tzinfo=None, microsecond=0)


def _format_bound(value: datetime) -> str:
    return value.strftime("%Y-%m-%d %H:%M:%S")


def _mcp_business_payload(response: dict) -> dict:
    if not isinstance(response, dict):
        raise RuntimeError("MCP response must be an object")
    if "error" in response:
        error = response.get("error") or {}
        code = error.get("code", "unknown") if isinstance(error, dict) else "unknown"
        raise RuntimeError(f"MCP RPC error: {code}")

    result = response.get("result", response)
    if not isinstance(result, dict):
        raise RuntimeError("MCP result must be an object")
    if response.get("isError") or result.get("isError"):
        raise RuntimeError("MCP tool error")

    payload = result.get("structuredContent") or response.get("structuredContent")
    if payload is None:
        content = result.get("content") or response.get("content") or []
        text_blocks = [item.get("text", "") for item in content
                       if isinstance(item, dict) and item.get("type") == "text"]
        if text_blocks:
            try:
                payload = json.loads(text_blocks[0])
            except (TypeError, json.JSONDecodeError) as error:
                raise RuntimeError("MCP tool returned invalid JSON content") from error
        elif "code" in result:
            payload = result
    if not isinstance(payload, dict):
        raise RuntimeError("MCP tool response has no business payload")

    code = payload.get("code")
    if str(code) != "200":
        raise RuntimeError(f"Tongtool business error: {code if code is not None else 'missing code'}")
    return payload


def fetch_receipts(
    caller: Callable[[str, dict], dict],
    date_from: str | date | datetime,
    date_to: str | date | datetime,
    po_code: str | None = None,
    page_size: int = MAX_PAGE_SIZE,
    max_pages: int = 1,
    sleep: Callable[[float], object] = time.sleep,
) -> ReceiptFetchResult:
    """Fetch a bounded purchase-stock query; never retries business errors.

    ``caller`` receives ``(tool_name, arguments)`` and returns the raw MCP
    JSON-RPC response. Rows are preserved as returned; this function does not
    deduplicate records without a source-provided event identity. Bounds are
    sent in Asia/Shanghai business time; naive datetimes are interpreted in
    that timezone, aware datetimes are converted to it, and a date-only end
    bound expands through 23:59:59.
    """
    start_dt = _parse_bound(date_from, "date_from", end_of_day=False)
    end_dt = _parse_bound(date_to, "date_to", end_of_day=True)
    if start_dt > end_dt:
        raise ValueError("date_from must not be after date_to")
    start = _format_bound(start_dt)
    end = _format_bound(end_dt)
    if isinstance(page_size, bool) or not isinstance(page_size, int) or not 1 <= page_size <= MAX_PAGE_SIZE:
        raise ValueError(f"page_size must be an integer from 1 to {MAX_PAGE_SIZE}")
    if isinstance(max_pages, bool) or not isinstance(max_pages, int) or max_pages < 1:
        raise ValueError("max_pages must be a positive integer")

    rows: list[dict] = []
    pages_fetched = 0
    complete = False
    for page_no in range(1, max_pages + 1):
        if pages_fetched:
            sleep(CALL_INTERVAL_SECONDS)
        arguments = {
            "warehousingDateFrom": start,
            "warehousingDateTo": end,
            "pageNo": page_no,
            "pageSize": page_size,
        }
        if po_code:
            arguments["purchaseOrderCode"] = po_code
        payload = _mcp_business_payload(caller(PURCHASE_STOCK_QUERY_TOOL, arguments))
        datas = payload.get("datas")
        if not isinstance(datas, dict) or not isinstance(datas.get("array"), list):
            raise RuntimeError("Tongtool response datas.array must be a list")
        for field, expected in (("pageNo", page_no), ("pageSize", page_size)):
            if field in datas and str(datas[field]) != str(expected):
                raise RuntimeError(
                    f"Tongtool response {field} {datas[field]!r} does not match request {expected}"
                )
        page_rows = datas["array"]
        if not all(isinstance(row, dict) for row in page_rows):
            raise RuntimeError("Tongtool receipt rows must be objects")
        rows.extend(dict(row) for row in page_rows)
        pages_fetched += 1
        if len(page_rows) < page_size:
            complete = True
            break

    truncated = not complete
    return ReceiptFetchResult(rows, pages_fetched, complete, truncated)


def _decimal_field(row: dict, field: str) -> Decimal | None:
    value = row.get(field)
    if value is None or value == "":
        return None
    try:
        number = Decimal(str(value))
    except (InvalidOperation, ValueError) as error:
        raise ValueError(f"{field} must be a decimal number") from error
    if not number.is_finite():
        raise ValueError(f"{field} must be a finite decimal number")
    return number


def _datetime_field(row: dict, field: str) -> datetime | None:
    value = row.get(field)
    if value is None or value == "":
        return None
    if isinstance(value, datetime):
        return value
    if not isinstance(value, str):
        raise ValueError(f"{field} must be an ISO datetime string")
    try:
        iso_text = value[:-1] + "+00:00" if value[-1:].upper() == "Z" else value
        return datetime.fromisoformat(iso_text)
    except ValueError as error:
        raise ValueError(f"{field} must be an ISO datetime string") from error


def normalize_receipts(rows: Iterable[dict]) -> list[dict]:
    """Normalize known fields while preserving each exact source row.

    Tongtool supplies no stable receipt or line ID and no UOM in the observed
    response. The adapter marks those gaps explicitly and never invents IDs.
    """
    normalized = []
    for source_index, source in enumerate(rows):
        if not isinstance(source, dict):
            raise ValueError(f"receipt row {source_index} must be an object")
        row = dict(source)
        normalized.append({
            "source_index": source_index,
            "raw": row,
            "purchase_order_code": row.get("purchaseOrderCode"),
            "purchase_order_id": row.get("purchaseOrderId"),
            "purchase_date": _datetime_field(row, "purchaseDate"),
            "purchase_date_source_field": "purchaseDate",
            "purchase_date_timezone_status": "unverified",
            "created_date": _datetime_field(row, "createdDate"),
            "created_date_source_field": "createdDate",
            "created_date_timezone_status": "unverified",
            "goods_detail_id": row.get("goodsDetailId"),
            "sku": row.get("sku"),
            "warehouse_id": row.get("warehouseId"),
            "warehouse_name": row.get("warehouseName"),
            "warehousing_number": row.get("warehousingNum"),
            "reported_receipt_quantity": _decimal_field(row, "warehousingNum"),
            "reported_receipt_quantity_source_field": "warehousingNum",
            "order_quantity": _decimal_field(row, "quantity"),
            "order_quantity_source_field": "quantity",
            "warehousing_date": _datetime_field(row, "warehousingDate"),
            "warehousing_date_source_field": "warehousingDate",
            "warehousing_date_timezone_status": "unverified",
            "event_id": None,
            "identity_confidence": "weak_identity",
            "uom": None,
            "uom_confidence": "unknown_uom",
            "time_timezone_status": "unverified",
            "time_source_timezone": "unverified",
        })
    return normalized
