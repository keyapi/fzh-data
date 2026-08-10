"""Sellfox API client — communicates through sellfox-api-proxy.

All Sellfox API calls are routed through the existing proxy, which handles
OAuth 2.0 token refresh, HMAC signing, and IP whitelist.
"""

from __future__ import annotations

import copy
import os
from datetime import datetime
from pathlib import Path
from typing import Optional

import httpx
import yaml

from sellfox_shipping.models import Address, Order, OrderItem, PackageStatus
from sellfox_shipping.package_models import (
    PackageRowError,
    SellfoxPackageAddress,
    SellfoxPackageItemRecord,
    SellfoxPackageLogistics,
    SellfoxPackageOrderRecord,
    SellfoxPackagePage,
    SellfoxPackageRecord,
)


class SellfoxApiError(RuntimeError):
    """Sellfox HTTP-level rejection carrying the HTTP status code.

    4xx means Sellfox definitively rejected the request (nothing applied);
    5xx/network means the outcome is unknown. Callers use ``status_code``
    to tell the two apart.
    """

    def __init__(self, message: str, *, status_code: int | None = None):
        super().__init__(message)
        self.status_code = status_code


class SellfoxClient:
    """Thin wrapper over sellfox-api-proxy for order fetch + tracking write-back."""

    def __init__(
        self,
        proxy_base_url: str,
        proxy_account: str,
        proxy_api_key: str = "",
        http_client: httpx.Client | None = None,
    ):
        self.base_url = proxy_base_url.rstrip("/")
        self.account = proxy_account
        self.api_key = proxy_api_key
        self._client = http_client or httpx.Client(timeout=30)

    def _proxy_path(self, api_path: str) -> str:
        return f"/v1/{self.account}{api_path}"

    def _post(self, path: str, body: dict) -> dict:
        """Call the proxy. The proxy handles Sellfox OAuth + signing."""
        url = f"{self.base_url}{path}"
        headers = {}
        if self.api_key:
            headers["Authorization"] = f"Bearer {self.api_key}"
        resp = self._client.post(url, json=body, headers=headers)
        if resp.status_code >= 400:
            raise SellfoxApiError(
                f"Sellfox HTTP {resp.status_code} on {path}: {(resp.text or '')[:1000]}",
                status_code=resp.status_code,
            )
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

        data = self._post(self._proxy_path("/api/order/pageList.json"), body)

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
        data = self._post(
            self._proxy_path("/api/order/detailByOrderId.json"),
            body,
        )

        if data.get("code") != 0:
            return None

        detail = data.get("data", {})
        return _parse_order_detail(detail)

    # ── Package fetching ────────────────────────────────────────

    def fetch_package_page(
        self,
        date_start: str,
        date_end: str,
        status: Optional[str] = None,
        shop_ids: Optional[list[str]] = None,
        page_no: int = 1,
        page_size: int = 20,
    ) -> SellfoxPackagePage:
        """Fetch and parse one package-processing page from Sellfox."""
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

        data = self._post(
            self._proxy_path("/api/packageShip/v1/getPackagePage.json"),
            body,
        )

        if data.get("code") != 0:
            raise RuntimeError(f"Sellfox API error: {data.get('msg', 'unknown')}")

        page = data.get("data", {})
        rows = page.get("rows", [])
        records: list[SellfoxPackageRecord] = []
        errors: list[PackageRowError] = []
        for row_index, row in enumerate(rows, start=1):
            try:
                record = parse_sellfox_package(self.account, row)
                record.source_row_index = row_index
                records.append(record)
            except (AttributeError, TypeError, ValueError) as exc:
                package_sn = ""
                if isinstance(row, dict):
                    package_sn = str(row.get("packageSn") or "")
                errors.append(
                    PackageRowError(
                        row_index=row_index,
                        package_sn=package_sn,
                        reason=str(exc),
                    )
                )

        return SellfoxPackagePage(
            page_no=int(page.get("pageNo") or page_no),
            page_size=int(page.get("pageSize") or page_size),
            total_size=int(page.get("totalSize") or 0),
            records=records,
            errors=errors,
        )

    def fetch_packages(
        self,
        date_start: str,
        date_end: str,
        status: Optional[str] = None,
        shop_ids: Optional[list[str]] = None,
        page_no: int = 1,
        page_size: int = 20,
    ) -> tuple[list[Order], int]:
        """Deprecated compatibility wrapper preserving the legacy Order result."""
        page = self.fetch_package_page(
            date_start=date_start,
            date_end=date_end,
            status=status,
            shop_ids=shop_ids,
            page_no=page_no,
            page_size=page_size,
        )
        return [
            _package_record_to_legacy_order(record)
            for record in page.records
        ], page.total_size

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
        data = self._post(
            self._proxy_path("/api/packageShip/submitToPlatform.json"),
            body,
        )

        return data.get("code") == 0

    def submit_to_platform(self, wire_body: dict[str, object]) -> dict[str, object]:
        """POST submitToPlatform with caller-built wire JSON (uses orderId, not amazonOrderId)."""
        data = self._post(
            self._proxy_path("/api/packageShip/submitToPlatform.json"),
            wire_body,
        )
        if not isinstance(data, dict):
            return {"code": -1, "raw": data}
        return data

    def quick_outbound(self, package_list: list[dict]) -> dict:
        """POST quickOutbound (快速出库): submit package tracking to platform.

        Each package: {packageSn, carrier, trackNo, shipmentType(0=仅提交平台不扣库存),
        warehouseId?, isOversea?}. Returns OpenResult«QuickOutboundOpenVO».
        """
        return self._post(
            self._proxy_path("/api/packageShip/quickOutbound.json"),
            {"packageList": package_list},
        )

    def fetch_package_detail(self, package_sn: str) -> dict | None:
        """POST packageDetail; returns data object or None on soft failure."""
        sn = (package_sn or "").strip()
        if not sn:
            raise ValueError("package_sn is required")
        data = self._post(
            self._proxy_path("/api/packageShip/v1/packageDetail.json"),
            {"packageSn": sn},
        )
        if not isinstance(data, dict) or data.get("code") != 0:
            return None
        detail = data.get("data")
        return detail if isinstance(detail, dict) else None


def get_sellfox_client():
    """Return the best Sellfox gateway for the current environment.

    When SELLFOX_APP_ID/SECRET are set, talk directly to the official OpenAPI
    (OAuth2 + HMAC signing); otherwise fall back to the shared proxy. Shared by
    CLI and Web so the gateway choice stays in one place.
    """
    app_id = os.getenv("SELLFOX_APP_ID", "").strip()
    app_secret = os.getenv("SELLFOX_APP_SECRET", "").strip()
    if app_id and app_secret:
        from sellfox_shipping.direct_sellfox_client import DirectSellfoxClient

        return DirectSellfoxClient()

    with open(Path(__file__).parent / "config.yaml", encoding="utf-8") as f:
        config = yaml.safe_load(f)
    return SellfoxClient(
        proxy_base_url=config["sellfox"]["proxy_base_url"],
        proxy_account=config["sellfox"]["proxy_account"],
        proxy_api_key=os.getenv("SELLFOX_PROXY_API_KEY", ""),
    )


# ── Response parsers ──────────────────────────────────────────────

def parse_sellfox_package(account_key: str, payload: object) -> SellfoxPackageRecord:
    """Convert one Sellfox wire payload into an internal snake_case record."""
    if not isinstance(payload, dict):
        raise ValueError("package row must be an object")
    package_sn = str(payload.get("packageSn") or "").strip()
    if not package_sn:
        raise ValueError("missing packageSn")

    address_data = _object_field(payload, "address")
    logistics_data = _object_field(payload, "logistics")
    order_data = _object_list_field(payload, "orders")
    item_data = _object_list_field(payload, "items")
    orders = [
        SellfoxPackageOrderRecord(
            external_order_id=str(order.get("amazonOrderId") or ""),
            order_status=str(order.get("orderStatus") or ""),
            purchase_date=_parse_date(order.get("purchaseDate")),
            earliest_ship_date=_parse_date(order.get("earliestShipDate")),
            latest_ship_date=_parse_date(order.get("latestShipDate")),
            order_total=_to_float(order.get("orderTotalAmount")),
            currency=str(order.get("orderTotalCurrency") or ""),
        )
        for order in order_data
        if str(order.get("amazonOrderId") or "").strip()
    ]
    items = [
        SellfoxPackageItemRecord(
            external_order_id=str(item.get("amazonOrderId") or ""),
            order_item_id=str(item.get("orderItemId") or ""),
            seller_sku=str(item.get("sellerSku") or ""),
            commodity_sku=str(item.get("commoditySku") or ""),
            quantity=_to_int(item.get("quantityOrdered")),
            main_image=str(item.get("mainImage") or ""),
            variation=str(item.get("variationChildStr") or ""),
        )
        for item in item_data
        if str(item.get("orderItemId") or "").strip()
    ]

    return SellfoxPackageRecord(
        account_key=account_key,
        package_sn=package_sn,
        shop_id=str(payload.get("shopId") or ""),
        shop_name=str(payload.get("shopName") or ""),
        platform_name=str(payload.get("platformName") or ""),
        marketplace=str(payload.get("marketplace") or ""),
        package_status=str(payload.get("status") or ""),
        address=SellfoxPackageAddress(
            name=str(address_data.get("name") or ""),
            company=str(address_data.get("company") or ""),
            address_line_1=str(address_data.get("address1") or ""),
            address_line_2=str(address_data.get("address2") or ""),
            city=str(address_data.get("city") or ""),
            state_or_region=str(address_data.get("stateOrRegion") or ""),
            postal_code=str(address_data.get("postalCode") or ""),
            country=str(address_data.get("country") or ""),
            country_code=str(address_data.get("countryCode") or ""),
            phone=str(address_data.get("phone") or ""),
            mobile=str(address_data.get("mobile") or ""),
            email=str(address_data.get("buyerEmail") or ""),
        ),
        logistics=SellfoxPackageLogistics(
            warehouse_name=str(logistics_data.get("warehouseName") or ""),
            channel_name=str(logistics_data.get("channelName") or ""),
            tracking_number=str(logistics_data.get("trackNo") or ""),
            forward_number=str(logistics_data.get("forwardNo") or ""),
            estimated_cost=_to_float(logistics_data.get("fbmCost")),
            currency=str(logistics_data.get("orderTotalCurrency") or ""),
            weight_grams=_to_float(logistics_data.get("packageWeight")),
            length_cm=_to_float(logistics_data.get("length")),
            width_cm=_to_float(logistics_data.get("width")),
            height_cm=_to_float(logistics_data.get("height")),
        ),
        orders=orders,
        items=items,
        raw_payload=copy.deepcopy(payload),
    )


def _package_record_to_legacy_order(record: SellfoxPackageRecord) -> Order:
    first_order = record.orders[0] if record.orders else None
    try:
        package_status = PackageStatus(record.package_status)
    except ValueError:
        package_status = PackageStatus.TO_AUDIT
    return Order(
        amazon_order_id=first_order.external_order_id if first_order else "",
        package_sn=record.package_sn,
        shop_id=record.shop_id,
        shop_name=record.shop_name,
        platform=record.platform_name or "Amazon",
        marketplace=record.marketplace,
        order_status=first_order.order_status if first_order else "",
        package_status=package_status,
        purchase_date=first_order.purchase_date if first_order else None,
        earliest_ship_date=(
            first_order.earliest_ship_date if first_order else None
        ),
        latest_ship_date=first_order.latest_ship_date if first_order else None,
        shipping_address=Address(
            name=record.address.name,
            company=record.address.company,
            address1=record.address.address_line_1,
            address2=record.address.address_line_2,
            city=record.address.city,
            state=record.address.state_or_region,
            postal_code=record.address.postal_code,
            country=record.address.country,
            country_code=record.address.country_code,
            phone=record.address.phone or record.address.mobile,
            email=record.address.email,
        ),
        items=[
            OrderItem(
                order_item_id=item.order_item_id,
                seller_sku=item.seller_sku,
                commodity_sku=item.commodity_sku,
                quantity=item.quantity,
                main_image=item.main_image,
                variation=item.variation,
            )
            for item in record.items
        ],
        raw_json=_truncate_json(record.raw_payload),
    )


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


def _to_float(value: object) -> float:
    try:
        return float(value or 0)
    except (TypeError, ValueError):
        return 0.0


def _to_int(value: object) -> int:
    try:
        return int(value or 0)
    except (TypeError, ValueError):
        return 0


def _object_field(payload: dict, field_name: str) -> dict:
    value = payload.get(field_name)
    if value is None:
        return {}
    if not isinstance(value, dict):
        raise ValueError(f"invalid {field_name}: expected object")
    return value


def _object_list_field(payload: dict, field_name: str) -> list[dict]:
    value = payload.get(field_name)
    if value is None:
        return []
    if not isinstance(value, list) or any(
        not isinstance(item, dict) for item in value
    ):
        raise ValueError(f"invalid {field_name}: expected object list")
    return value


def _truncate_json(obj: dict, max_chars: int = 50000) -> str:
    import json
    raw = json.dumps(obj, ensure_ascii=False, default=str)
    if len(raw) > max_chars:
        raw = raw[:max_chars] + '..."}'
    return raw
