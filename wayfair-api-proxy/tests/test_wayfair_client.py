from __future__ import annotations

import json
from datetime import datetime, timezone

import httpx
import pytest

from config import AccountConfig, AppConfig, Credentials
from errors import (
    CapabilityUnavailable,
    UpstreamAuthFailed,
    UpstreamForbidden,
    UpstreamRateLimited,
)
from wayfair_client import WayfairClient


def _config(**overrides) -> AppConfig:
    values = {
        "upstream": "https://api.example.test/v1/supplier-order-api/graphql",
        "credentials": Credentials(client_id="id", client_secret="secret"),
        "supplier_id": 80197,
    }
    values.update(overrides)
    return AppConfig(accounts={"centrade": AccountConfig(**values)})


def _edge(sku, warehouses, on_hand_qty=10):
    return {
        "node": {
            "supplierPartNumber": sku,
            "sku": sku,
            "inventoryPosition": {
                "castleGate": {
                    "onHandQty": on_hand_qty,
                    "onHand": {
                        "allocatedQty": 2,
                        "inStock": {"fulfillableQty": 6, "unfulfillableQty": 2},
                    },
                    "warehouses": warehouses,
                }
            },
        }
    }


def _warehouse(warehouse_id, on_hand_qty):
    return {
        "warehouseId": warehouse_id,
        "onHandQty": on_hand_qty,
        "onHand": {
            "allocatedQty": 2,
            "inStock": {"fulfillableQty": 6, "unfulfillableQty": 2},
        },
    }


def _page(edges, has_next=False, cursor=None):
    return {
        "data": {
            "inventorySummaryList": {
                "pageInfo": {"hasNextPage": has_next, "endCursor": cursor},
                "edges": edges,
            }
        }
    }


@pytest.mark.anyio
async def test_maps_castlegate_fields_and_paginates():
    calls = {"token": 0, "graphql": []}
    pages = [
        _page(
            [
                _edge("SKU-1", [_warehouse(11, 4)]),
                _edge("SKU-2", []),
            ],
            has_next=True,
            cursor="c1",
        ),
        _page([_edge("SKU-3", [_warehouse(12, 8)])]),
    ]

    def handler(request: httpx.Request) -> httpx.Response:
        if request.url.path.endswith("/oauth/token"):
            calls["token"] += 1
            body = json.loads(request.content)
            assert body["grant_type"] == "client_credentials"
            return httpx.Response(200, json={"access_token": "tok", "expires_in": 3600})
        body = json.loads(request.content)
        calls["graphql"].append(body)
        return httpx.Response(200, json=pages[len(calls["graphql"]) - 1])

    async with httpx.AsyncClient(transport=httpx.MockTransport(handler)) as http:
        rows, fetched_at = await WayfairClient(_config().accounts, http).query_inventory(
            "centrade", ["SKU-1", "SKU-2", "SKU-3"]
        )

    assert calls["token"] == 1
    assert calls["graphql"][0]["variables"]["filter"] == {
        "supplierPartNumbers": ["SKU-1", "SKU-2", "SKU-3"]
    }
    assert calls["graphql"][1]["variables"]["page"]["after"] == "c1"

    assert [row["sku"] for row in rows] == ["SKU-1", "SKU-2", "SKU-3"]
    first = rows[0]
    assert first == {
        "sku": "SKU-1",
        "wayfair_sku": "SKU-1",
        "warehouse": "11",
        "on_hand": 4,
        "available": 6,
        "reserved": 2,
        "unavailable": 2,
    }
    assert rows[1]["warehouse"] == "CG"
    assert rows[1]["on_hand"] == 10
    assert fetched_at.tzinfo is timezone.utc


@pytest.mark.anyio
async def test_supplier_part_number_wins_over_wayfair_sku():
    node = _edge("C/Cord-Black-100-707-wow", [], on_hand_qty=5)["node"]
    node["sku"] = "WWMA1193"

    def handler(request: httpx.Request) -> httpx.Response:
        if request.url.path.endswith("/oauth/token"):
            return httpx.Response(200, json={"access_token": "tok", "expires_in": 3600})
        return httpx.Response(200, json=_page([{"node": node}]))

    async with httpx.AsyncClient(transport=httpx.MockTransport(handler)) as http:
        rows, _ = await WayfairClient(_config().accounts, http).query_inventory(
            "centrade", ["C/Cord-Black-100-707-wow"]
        )

    assert rows[0]["sku"] == "C/Cord-Black-100-707-wow"
    assert rows[0]["wayfair_sku"] == "WWMA1193"


@pytest.mark.anyio
async def test_adjustments_map_and_paginate():
    calls = []

    def handler(request: httpx.Request) -> httpx.Response:
        if request.url.path.endswith("/oauth/token"):
            return httpx.Response(200, json={"access_token": "tok", "expires_in": 3600})
        body = json.loads(request.content)
        calls.append(body["variables"])
        page = body["variables"]["page"]["page"]
        node = {
            "eventDate": "2026-02-20T09:59:33.000-05:00",
            "adjustmentType": "Inbound Receipt Adjustment",
            "supplierPartNumber": "SKU-1",
            "quantity": 3,
            "warehouse": {"warehouseId": 323004, "name": "NJ WH13"},
            "description": "receipt",
        }
        return httpx.Response(
            200,
            json={
                "data": {
                    "inventoryAdjustmentList": {
                        "pageInfo": {"pageNumber": page, "pageSize": 100, "totalPages": 2},
                        "nodes": [node],
                    }
                }
            },
        )

    from datetime import datetime, timezone

    async with httpx.AsyncClient(transport=httpx.MockTransport(handler)) as http:
        rows, _ = await WayfairClient(_config().accounts, http).query_adjustments(
            "centrade",
            from_date=datetime(2026, 2, 1, tzinfo=timezone.utc),
            to_date=datetime(2026, 2, 28, tzinfo=timezone.utc),
            sku="SKU-1",
        )

    assert len(rows) == 2
    assert rows[0] == {
        "event_date": "2026-02-20T09:59:33.000-05:00",
        "adjustment_type": "Inbound Receipt Adjustment",
        "sku": "SKU-1",
        "quantity": 3,
        "warehouse_id": 323004,
        "warehouse_name": "NJ WH13",
        "description": "receipt",
    }
    assert calls[0]["filter"]["supplierPartNumber"] == "SKU-1"
    assert calls[0]["filter"]["transactionDateInterval"]["from"].startswith("2026-02-01")
    assert calls[1]["page"]["page"] == 1


@pytest.mark.anyio
async def test_adjustment_window_drops_microseconds():
    calls = []

    def handler(request: httpx.Request) -> httpx.Response:
        if request.url.path.endswith("/oauth/token"):
            return httpx.Response(200, json={"access_token": "tok", "expires_in": 3600})
        calls.append(json.loads(request.content)["variables"])
        return httpx.Response(
            200,
            json={
                "data": {
                    "inventoryAdjustmentList": {
                        "pageInfo": {"pageNumber": 0, "pageSize": 100, "totalPages": 1},
                        "nodes": [],
                    }
                }
            },
        )

    from datetime import datetime, timezone

    async with httpx.AsyncClient(transport=httpx.MockTransport(handler)) as http:
        await WayfairClient(_config().accounts, http).query_adjustments(
            "centrade",
            from_date=datetime(2026, 2, 1, 10, 0, 0, 123456, tzinfo=timezone.utc),
            to_date=datetime(2026, 2, 28, 23, 59, 59, 999999, tzinfo=timezone.utc),
        )

    interval = calls[0]["filter"]["transactionDateInterval"]
    assert interval["from"] == "2026-02-01T10:00:00+00:00"
    assert interval["to"] == "2026-02-28T23:59:59+00:00"


@pytest.mark.anyio
async def test_missing_cursor_is_an_error_not_partial_success():
    def handler(request: httpx.Request) -> httpx.Response:
        if request.url.path.endswith("/oauth/token"):
            return httpx.Response(200, json={"access_token": "tok", "expires_in": 3600})
        result = {
            "data": {
                "inventorySummaryList": {
                    "pageInfo": {"hasNextPage": True, "endCursor": None},
                    "edges": [_edge("SKU-1", [])],
                }
            }
        }
        return httpx.Response(200, json=result)

    from errors import UpstreamUnavailable

    async with httpx.AsyncClient(transport=httpx.MockTransport(handler)) as http:
        with pytest.raises(UpstreamUnavailable):
            await WayfairClient(_config().accounts, http).query_inventory(
                "centrade", ["SKU-1"]
            )


@pytest.mark.anyio
async def test_operation_not_authorized_maps_to_forbidden():
    def handler(request: httpx.Request) -> httpx.Response:
        if request.url.path.endswith("/oauth/token"):
            return httpx.Response(200, json={"access_token": "tok", "expires_in": 3600})
        return httpx.Response(
            200,
            json={"errors": [{"message": "The provided client is not authorized to use this operation"}]},
        )

    async with httpx.AsyncClient(transport=httpx.MockTransport(handler)) as http:
        with pytest.raises(UpstreamForbidden):
            await WayfairClient(_config().accounts, http).query_inventory("centrade", ["SKU-1"])


@pytest.mark.anyio
async def test_rate_limit_and_auth_failure_are_mapped():
    def rate_limited(request: httpx.Request) -> httpx.Response:
        if request.url.path.endswith("/oauth/token"):
            return httpx.Response(200, json={"access_token": "tok", "expires_in": 3600})
        return httpx.Response(429)

    async with httpx.AsyncClient(transport=httpx.MockTransport(rate_limited)) as http:
        with pytest.raises(UpstreamRateLimited):
            await WayfairClient(_config().accounts, http).query_inventory("centrade", ["SKU-1"])

    calls = {"token": 0}

    def unauthorized(request: httpx.Request) -> httpx.Response:
        if request.url.path.endswith("/oauth/token"):
            calls["token"] += 1
            return httpx.Response(200, json={"access_token": "tok", "expires_in": 3600})
        return httpx.Response(401)

    async with httpx.AsyncClient(transport=httpx.MockTransport(unauthorized)) as http:
        with pytest.raises(UpstreamAuthFailed):
            await WayfairClient(_config().accounts, http).query_inventory("centrade", ["SKU-1"])

    assert calls["token"] == 2


@pytest.mark.anyio
async def test_missing_supplier_id_is_capability_unavailable():
    config = _config(supplier_id=None)

    async with httpx.AsyncClient(transport=httpx.MockTransport(lambda r: httpx.Response(500))) as http:
        with pytest.raises(CapabilityUnavailable):
            await WayfairClient(config.accounts, http).query_inventory("centrade", ["SKU-1"])
