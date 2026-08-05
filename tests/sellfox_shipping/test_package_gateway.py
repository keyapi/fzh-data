from __future__ import annotations

import httpx

from sellfox_shipping.models import Order
from sellfox_shipping.package_models import SellfoxPackageRecord
from sellfox_shipping.sellfox_client import SellfoxClient, parse_sellfox_package


def _package_payload(package_sn: str = "P10001") -> dict:
    return {
        "packageSn": package_sn,
        "shopId": "shop-1",
        "shopName": "US Store",
        "platformName": "Amazon",
        "marketplace": "ATVPDKIKX0DER",
        "status": "to_audit",
        "address": {
            "name": "Receiver",
            "countryCode": "US",
            "postalCode": "10001",
            "stateOrRegion": "NY",
            "city": "New York",
            "address1": "1 Test Street",
        },
        "logistics": {
            "warehouseName": "US-WH",
            "channelName": "蜴国际",
            "trackNo": "",
            "forwardNo": "",
            "fbmCost": "12.50",
            "orderTotalCurrency": "USD",
            "packageWeight": "1500",
            "length": "20",
            "width": "15",
            "height": "10",
            "unit": "cm",
        },
        "orders": [
            {
                "amazonOrderId": "ORDER-1",
                "orderStatus": "Unshipped",
                "purchaseDate": "2026-07-15 10:00:00",
                "orderTotalAmount": "20.00",
                "orderTotalCurrency": "USD",
            },
            {
                "amazonOrderId": "ORDER-2",
                "orderStatus": "Unshipped",
                "purchaseDate": "2026-07-15 11:00:00",
                "orderTotalAmount": "30.00",
                "orderTotalCurrency": "USD",
            },
        ],
        "items": [
            {
                "orderItemId": "ITEM-1",
                "amazonOrderId": "ORDER-1",
                "sellerSku": "SKU-1",
                "commoditySku": "KS0001",
                "quantityOrdered": "2",
            },
            {
                "orderItemId": "ITEM-2",
                "amazonOrderId": "ORDER-2",
                "sellerSku": "SKU-2",
                "commoditySku": "KS0002",
                "quantityOrdered": "1",
            },
        ],
    }


def test_parse_sellfox_package_preserves_multi_order_relationships() -> None:
    package = parse_sellfox_package("sellfox-main", _package_payload())

    assert isinstance(package, SellfoxPackageRecord)
    assert package.account_key == "sellfox-main"
    assert package.package_sn == "P10001"
    assert package.logistics.channel_name == "蜴国际"
    assert package.logistics.estimated_cost == 12.5
    assert [order.external_order_id for order in package.orders] == [
        "ORDER-1",
        "ORDER-2",
    ]
    assert [
        (item.external_order_id, item.order_item_id, item.quantity)
        for item in package.items
    ] == [
        ("ORDER-1", "ITEM-1", 2),
        ("ORDER-2", "ITEM-2", 1),
    ]


def test_fetch_package_page_uses_proxy_account_and_bearer_auth() -> None:
    def handler(request: httpx.Request) -> httpx.Response:
        assert request.url.path == (
            "/v1/sellfox-main/api/packageShip/v1/getPackagePage.json"
        )
        assert request.headers["Authorization"] == "Bearer x"
        assert request.read()
        return httpx.Response(
            200,
            json={
                "code": 0,
                "data": {
                    "pageNo": 1,
                    "pageSize": 20,
                    "totalSize": 1,
                    "rows": [_package_payload()],
                },
            },
        )

    http_client = httpx.Client(transport=httpx.MockTransport(handler))
    client = SellfoxClient(
        proxy_base_url="https://proxy.example.test",
        proxy_account="sellfox-main",
        proxy_api_key="x",
        http_client=http_client,
    )

    page = client.fetch_package_page(
        date_start="2026-07-15",
        date_end="2026-07-16",
    )

    assert page.total_size == 1
    assert len(page.records) == 1
    assert page.errors == []


def test_fetch_package_page_keeps_valid_rows_when_one_row_is_invalid() -> None:
    def handler(request: httpx.Request) -> httpx.Response:
        return httpx.Response(
            200,
            json={
                "code": 0,
                "data": {
                    "pageNo": 1,
                    "pageSize": 20,
                    "totalSize": 2,
                    "rows": [_package_payload(), _package_payload(package_sn="")],
                },
            },
        )

    client = SellfoxClient(
        proxy_base_url="https://proxy.example.test",
        proxy_account="sellfox-main",
        proxy_api_key="x",
        http_client=httpx.Client(transport=httpx.MockTransport(handler)),
    )

    page = client.fetch_package_page(
        date_start="2026-07-15",
        date_end="2026-07-16",
    )

    assert [record.package_sn for record in page.records] == ["P10001"]
    assert len(page.errors) == 1
    assert page.errors[0].row_index == 2
    assert page.errors[0].reason == "missing packageSn"


def test_fetch_package_page_keeps_valid_rows_when_nested_data_is_malformed() -> None:
    malformed = _package_payload(package_sn="P-BAD")
    malformed["address"] = ["not", "an", "object"]

    def handler(request: httpx.Request) -> httpx.Response:
        return httpx.Response(
            200,
            json={
                "code": 0,
                "data": {
                    "pageNo": 1,
                    "pageSize": 20,
                    "totalSize": 2,
                    "rows": [malformed, _package_payload()],
                },
            },
        )

    client = SellfoxClient(
        proxy_base_url="https://proxy.example.test",
        proxy_account="sellfox-main",
        proxy_api_key="x",
        http_client=httpx.Client(transport=httpx.MockTransport(handler)),
    )

    page = client.fetch_package_page(
        date_start="2026-07-15",
        date_end="2026-07-16",
    )

    assert [record.package_sn for record in page.records] == ["P10001"]
    assert len(page.errors) == 1
    assert page.errors[0].package_sn == "P-BAD"


def test_legacy_fetch_packages_still_returns_orders() -> None:
    def handler(request: httpx.Request) -> httpx.Response:
        return httpx.Response(
            200,
            json={
                "code": 0,
                "data": {
                    "pageNo": 1,
                    "pageSize": 20,
                    "totalSize": 1,
                    "rows": [_package_payload()],
                },
            },
        )

    client = SellfoxClient(
        proxy_base_url="https://proxy.example.test",
        proxy_account="sellfox-main",
        proxy_api_key="x",
        http_client=httpx.Client(transport=httpx.MockTransport(handler)),
    )

    packages, total = client.fetch_packages(
        date_start="2026-07-15",
        date_end="2026-07-16",
    )

    assert total == 1
    assert isinstance(packages[0], Order)
    assert packages[0].package_sn == "P10001"
