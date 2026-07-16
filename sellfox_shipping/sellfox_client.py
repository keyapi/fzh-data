"""Sellfox API client — communicates through sellfox-api-proxy.

All Sellfox API calls are routed through the existing proxy, which handles
OAuth 2.0 token refresh, HMAC signing, and IP whitelist.
"""

from __future__ import annotations

import hashlib
import hmac
import time
from datetime import datetime
from typing import Optional

import httpx

from sellfox_shipping.models import Address, Order, OrderItem, PackageStatus


class SellfoxClient:
    """Thin wrapper over sellfox-api-proxy for order fetch + tracking write-back."""

    def __init__(self, proxy_base_url: str, proxy_account: str, proxy_api_key: str = ""):
        self.base_url = proxy_base_url.rstrip("/")
        self.account = proxy_account
        self.api_key = proxy_api_key
        self._client = httpx.Client(timeout=30)

    def _post(self, path: str, body: dict) -> dict:
        """Call the proxy. The proxy handles Sellfox OAuth + signing."""
        url = f"{self.base_url}{path}"
        resp = self._client.post(url, json=body)
        resp.raise_for_status()
        return resp.json()

    # ── Order fetching ──────────────────────────────────────────

    def fetch_orders(
        self,
        date_start: str,
        date_end: str,
        status: Optional[str] = None,
        shop_ids: Optional[list[str]] = None,
        page_no: int = 1,
        page_size: int = 20,
    ) -> tuple[list[Order], int]:
        """Fetch orders from Sellfox. Returns (orders, total_count)."""
        body = {
            "dateType": "purchase",
            "dateStart": date_start,
            "dateEnd": date_end,
            "pageNo": str(page_no),
            "pageSize": str(page_size),
        }
        if status and status != "all":
            body["orderStatus"] = status
        if shop_ids:
            body["shopIdList"] = shop_ids

        data = self._post("/v1/sellfox-main/api/order/pageList.json", body)

        if data.get("code") != 0:
            raise RuntimeError(f"Sellfox API error: {data.get('msg', 'unknown')}")

        page = data.get("data", {})
        rows = page.get("rows", [])
        orders = [_parse_order_row(r) for r in rows]
        return orders, page.get("totalSize", 0)

    def get_order_detail(
        self, shop_id: str, amazon_order_id: str,
    ) -> Optional[Order]:
        """Fetch full order detail including address and package list."""
        body = {
            "shopId": shop_id,
            "amazonOrderId": amazon_order_id,
        }
        data = self._post("/v1/sellfox-main/api/order/detailByOrderId.json", body)

        if data.get("code") != 0:
            return None

        detail = data.get("data", {})
        return _parse_order_detail(detail)

    # ── Package fetching ────────────────────────────────────────

    def fetch_packages(
        self,
        date_start: str,
        date_end: str,
        status: Optional[str] = None,
        shop_ids: Optional[list[str]] = None,
        page_no: int = 1,
        page_size: int = 20,
    ) -> tuple[list[Order], int]:
        """Fetch packages (order processing view) from Sellfox."""
        body = {
            "purchaseDateStart": date_start,
            "purchaseDateEnd": date_end,
            "pageNo": str(page_no),
            "pageSize": str(page_size),
        }
        if status:
            body["packageStatus"] = status
        if shop_ids:
            body["shopIdList"] = shop_ids

        data = self._post("/v1/sellfox-main/api/packageShip/v1/getPackagePage.json", body)

        if data.get("code") != 0:
            raise RuntimeError(f"Sellfox API error: {data.get('msg', 'unknown')}")

        page = data.get("data", {})
        rows = page.get("rows", [])
        orders = [_parse_package_row(r) for r in rows]
        return orders, page.get("totalSize", 0)

    # ── Tracking write-back ─────────────────────────────────────

    def write_tracking(
        self,
        shop_id: str,
        amazon_order_id: str,
        carrier_name: str,
        track_no: str,
        ship_service: str = "",
        items: Optional[list[dict]] = None,
    ) -> bool:
        """Write tracking number back to Sellfox platform."""
        body = {
            "shopId": shop_id,
            "amazonOrderId": amazon_order_id,
            "carrierName": carrier_name,
            "trackNo": track_no,
        }
        if ship_service:
            body["shipService"] = ship_service
        if items:
            body["items"] = items

        # endpoint TBD — may need to check exact Sellfox API path
        data = self._post("/v1/sellfox-main/api/packageShip/submitToPlatform.json", body)

        return data.get("code") == 0


# ── Response parsers ──────────────────────────────────────────────

def _parse_order_row(r: dict) -> Order:
    items = []
    for item in (r.get("orderItemVoList") or []):
        items.append(OrderItem(
            order_item_id=item.get("orderItemId", ""),
            seller_sku=item.get("sellerSku", ""),
            commodity_sku=item.get("commoditySku", ""),
            commodity_name=item.get("commodityName", ""),
            asin=item.get("asin", ""),
            quantity=int(item.get("quantityOrdered", 0)),
        ))

    return Order(
        amazon_order_id=r.get("amazonOrderId", ""),
        shop_id=r.get("shopId", ""),
        shop_name=r.get("shopName", ""),
        marketplace=r.get("marketplaceId", ""),
        order_status=r.get("orderStatus", ""),
        order_total=float(r.get("orderTotalAmount", 0) or 0),
        currency=r.get("orderTotalCurrency", ""),
        purchase_date=_parse_date(r.get("purchaseDate")),
        earliest_ship_date=_parse_date(r.get("earliestShipDate")),
        latest_ship_date=_parse_date(r.get("latestShipDate")),
        items=items,
        raw_json=_truncate_json(r),
    )


def _parse_order_detail(d: dict) -> Order:
    items = []
    for item in (d.get("orderItemVoList") or []):
        items.append(OrderItem(
            order_item_id=item.get("orderItemId", ""),
            seller_sku=item.get("sellerSku", ""),
            commodity_sku=item.get("commoditySku", ""),
            commodity_name=item.get("commodityName", ""),
            asin=item.get("asin", ""),
            quantity=int(item.get("quantityOrdered", 0)),
        ))

    addr = Address(
        name=d.get("receiverName", ""),
        address1=d.get("detailAddress", ""),
        city=d.get("city", ""),
        state=d.get("stateOrRegion", ""),
        postal_code=d.get("postalCode", ""),
        country_code=d.get("countryCode", ""),
        phone=d.get("phone", ""),
        email=d.get("buyerEmail", ""),
    )

    # package info from orderPackageList
    package_sn = ""
    track_no = ""
    if d.get("orderPackageList"):
        pkg = d["orderPackageList"][0]
        package_sn = pkg.get("packageSn", "")
        track_no = pkg.get("trackNo", "")

    return Order(
        amazon_order_id=d.get("amazonOrderId", ""),
        seller_order_id=d.get("sellerOrderId", ""),
        package_sn=package_sn,
        shop_id=d.get("shopId", ""),
        marketplace=d.get("marketplaceId", ""),
        order_status=d.get("orderStatus", ""),
        order_total=float(d.get("orderTotalAmount", 0) or 0),
        currency=d.get("orderTotalCurrency", ""),
        purchase_date=_parse_date(d.get("purchaseDate")),
        earliest_ship_date=_parse_date(d.get("earliestShipDate")),
        latest_ship_date=_parse_date(d.get("latestShipDate")),
        shipping_address=addr,
        items=items,
        raw_json=_truncate_json(d),
    )


def _parse_package_row(r: dict) -> Order:
    addr_data = r.get("address") or {}
    addr = Address(
        name=addr_data.get("name", ""),
        company=addr_data.get("company", ""),
        address1=addr_data.get("address1", ""),
        address2=addr_data.get("address2", ""),
        city=addr_data.get("city", ""),
        state=addr_data.get("stateOrRegion", ""),
        postal_code=addr_data.get("postalCode", ""),
        country=addr_data.get("country", ""),
        country_code=addr_data.get("countryCode", ""),
        phone=addr_data.get("phone", ""),
        email=addr_data.get("buyerEmail", ""),
    )

    items = []
    for item in (r.get("items") or []):
        items.append(OrderItem(
            order_item_id=item.get("orderItemId", ""),
            seller_sku=item.get("sellerSku", ""),
            commodity_sku=item.get("commoditySku", ""),
            quantity=int(item.get("quantityOrdered", 0)),
            main_image=item.get("mainImage", ""),
            variation=item.get("variationChildStr", ""),
        ))

    logistics = r.get("logistics") or {}
    orders_data = r.get("orders") or []
    first_order = orders_data[0] if orders_data else {}

    return Order(
        amazon_order_id=first_order.get("amazonOrderId", ""),
        package_sn=r.get("packageSn", ""),
        shop_id=r.get("shopId", ""),
        shop_name=r.get("shopName", ""),
        platform=r.get("platformName", "Amazon"),
        marketplace=r.get("marketplace", ""),
        order_status=first_order.get("orderStatus", ""),
        package_status=PackageStatus(r.get("status", "to_audit")),
        purchase_date=_parse_date(first_order.get("purchaseDate")),
        earliest_ship_date=_parse_date(first_order.get("earliestShipDate")),
        latest_ship_date=_parse_date(first_order.get("latestShipDate")),
        shipping_address=addr,
        items=items,
        raw_json=_truncate_json(r),
    )


def _parse_date(val: Optional[str]) -> Optional[datetime]:
    if not val:
        return None
    # Try common ISO formats
    for fmt in ("%Y-%m-%d %H:%M:%S", "%Y-%m-%dT%H:%M:%S", "%Y-%m-%d"):
        try:
            return datetime.strptime(val, fmt)
        except ValueError:
            continue
    return None


def _truncate_json(obj: dict, max_chars: int = 50000) -> str:
    import json
    raw = json.dumps(obj, ensure_ascii=False, default=str)
    if len(raw) > max_chars:
        raw = raw[:max_chars] + '..."}'
    return raw
