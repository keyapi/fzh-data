from __future__ import annotations

import os
from collections.abc import Mapping
from datetime import datetime, timezone

import httpx

from config import AccountConfig
from errors import (
    CapabilityUnavailable,
    UpstreamAuthFailed,
    UpstreamForbidden,
    UpstreamRateLimited,
    UpstreamUnavailable,
)
from oauth_cache import TokenCache

TOKEN_URL = "https://sso.auth.wayfair.com/oauth/token"
AUDIENCE = "https://api.wayfair.com/"
PAGE_SIZE = 100
MAX_PAGES = 100
# inventoryAdjustmentList uses a 0-based page number.
ADJUSTMENT_PAGE_SIZE = 100
MAX_ADJUSTMENT_PAGES = 100

INVENTORY_QUERY = """
query($supplierId: Int!, $filter: InventoryFilterInput, $page: InventoryPageInput) {
  inventorySummaryList(supplierId: $supplierId, filter: $filter, page: $page) {
    pageInfo { hasNextPage endCursor }
    edges {
      node {
        supplierPartNumber
        sku
        productName
        inventoryPosition {
          castleGate {
            onHandQty
            onHand {
              allocatedQty
              unreconciledQty
              inStockQty
              inStock {
                fulfillableQty
                unfulfillableQty
                unfulfillable {
                  expiredQty
                  heldQty
                  unpickableQty
                  onTransferQty
                }
              }
            }
            warehouses {
              warehouseId
              onHandQty
              onHand {
                allocatedQty
                inStockQty
                inStock { fulfillableQty unfulfillableQty }
              }
            }
          }
        }
      }
    }
  }
}
"""


ADJUSTMENT_QUERY = """
query($supplierId: Int!, $filter: InventoryAdjustmentFilterInput, $page: InventoryAdjustmentPageInput) {
  inventoryAdjustmentList(supplierId: $supplierId, filter: $filter, page: $page) {
    pageInfo { pageNumber pageSize totalPages totalElements }
    nodes {
      eventDate
      adjustmentType
      supplierPartNumber
      quantity
      warehouse { warehouseId name }
      description
    }
  }
}
"""


class _Unauthorized(Exception):
    pass


def _resolve(value: str) -> str:
    if value.startswith("${") and value.endswith("}"):
        resolved = os.getenv(value[2:-1], "")
        if not resolved:
            raise UpstreamAuthFailed("Upstream credential is not configured")
        return resolved
    return value


def _quantity(source: dict | None, key: str) -> int | None:
    if not source:
        return None
    value = source.get(key)
    return value if isinstance(value, int) else None


def _breakdown(on_hand: dict | None) -> dict:
    in_stock = (on_hand or {}).get("inStock") or {}
    return {
        "available": _quantity(in_stock, "fulfillableQty"),
        "reserved": _quantity(on_hand, "allocatedQty"),
        "unavailable": _quantity(in_stock, "unfulfillableQty"),
    }


def _iso(value: datetime) -> str:
    if value.tzinfo is None:
        value = value.replace(tzinfo=timezone.utc)
    return value.isoformat()


def _map_adjustment(node: dict) -> dict:
    warehouse = node.get("warehouse") or {}
    return {
        "event_date": node.get("eventDate"),
        "adjustment_type": node.get("adjustmentType"),
        "sku": node.get("supplierPartNumber"),
        "quantity": node.get("quantity"),
        "warehouse_id": warehouse.get("warehouseId"),
        "warehouse_name": warehouse.get("name"),
        "description": node.get("description"),
    }


def _map_node(node: dict) -> list[dict]:
    wayfair_sku = node.get("sku")
    sku = node.get("supplierPartNumber") or wayfair_sku
    if not sku:
        return []
    castle_gate = ((node.get("inventoryPosition") or {}).get("castleGate")) or {}
    warehouses = castle_gate.get("warehouses") or []
    rows = []
    if warehouses:
        for warehouse in warehouses:
            rows.append(
                {
                    "sku": sku,
                    "wayfair_sku": wayfair_sku,
                    "warehouse": str(warehouse.get("warehouseId")),
                    "on_hand": _quantity(warehouse, "onHandQty"),
                    **_breakdown(warehouse.get("onHand")),
                }
            )
    else:
        rows.append(
            {
                "sku": sku,
                "wayfair_sku": wayfair_sku,
                "warehouse": "CG",
                "on_hand": _quantity(castle_gate, "onHandQty"),
                **_breakdown(castle_gate.get("onHand")),
            }
        )
    return rows


class WayfairClient:
    def __init__(self, accounts: Mapping[str, AccountConfig], http_client: httpx.AsyncClient):
        self._accounts = accounts
        self._http = http_client
        self._tokens = TokenCache(self._refresh_token)

    async def _refresh_token(self, account: str) -> tuple[str, float]:
        account_config = self._require(account)
        try:
            response = await self._http.post(
                TOKEN_URL,
                json={
                    "grant_type": "client_credentials",
                    "client_id": _resolve(account_config.credentials.client_id),
                    "client_secret": _resolve(account_config.credentials.client_secret),
                    "audience": AUDIENCE,
                },
            )
        except httpx.HTTPError as exc:
            raise UpstreamUnavailable("Wayfair token endpoint is unreachable") from exc

        if response.status_code in (400, 401, 403):
            raise UpstreamAuthFailed("Wayfair rejected the client credentials")
        if response.status_code == 429:
            raise UpstreamRateLimited("Wayfair token endpoint rate limited the client")
        if response.status_code != 200:
            raise UpstreamUnavailable("Wayfair token endpoint failed")
        try:
            payload = response.json()
        except ValueError as exc:
            raise UpstreamUnavailable("Wayfair token response was not JSON") from exc
        token = payload.get("access_token")
        if not token:
            raise UpstreamAuthFailed("Wayfair token response contained no access token")
        try:
            expires_in = float(payload.get("expires_in") or 3600)
        except (TypeError, ValueError):
            expires_in = 3600.0
        return token, expires_in

    def _require(self, account: str) -> AccountConfig:
        account_config = self._accounts.get(account)
        if account_config is None:
            raise KeyError(account)
        return account_config

    async def _post(
        self,
        account_config: AccountConfig,
        token: str,
        query: str,
        variables: dict,
        result_key: str,
    ) -> dict:
        try:
            response = await self._http.post(
                str(account_config.upstream),
                json={"query": query, "variables": variables},
                headers={"Authorization": f"Bearer {token}"},
            )
        except httpx.HTTPError as exc:
            raise UpstreamUnavailable("Wayfair API is unreachable") from exc

        if response.status_code == 401:
            raise _Unauthorized()
        if response.status_code == 403:
            raise UpstreamForbidden("Wayfair client is not authorized for this operation")
        if response.status_code == 429:
            raise UpstreamRateLimited("Wayfair API rate limited the request")
        if response.status_code != 200:
            raise UpstreamUnavailable("Wayfair API returned an unexpected status")

        try:
            payload = response.json()
        except ValueError as exc:
            raise UpstreamUnavailable("Wayfair API response was not JSON") from exc

        errors = payload.get("errors") or []
        if errors:
            message = " ".join(str(item.get("message", "")) for item in errors).lower()
            if "not authorized" in message or "forbidden" in message:
                raise UpstreamForbidden(
                    "Wayfair client is not authorized for this operation"
                )
            if "rate" in message:
                raise UpstreamRateLimited("Wayfair API rate limited the request")
            raise UpstreamUnavailable("Wayfair API returned a GraphQL error")

        data = payload.get("data") or {}
        result = data.get(result_key)
        if result is None:
            raise UpstreamUnavailable("Wayfair API returned no data")
        return result

    async def _query_page(
        self,
        account: str,
        account_config: AccountConfig,
        query: str,
        variables: dict,
        result_key: str,
    ) -> dict:
        try:
            return await self._post(
                account_config,
                await self._tokens.get(account),
                query,
                variables,
                result_key,
            )
        except (_Unauthorized, UpstreamForbidden):
            self._tokens.invalidate(account)
            try:
                return await self._post(
                    account_config,
                    await self._tokens.get(account),
                    query,
                    variables,
                    result_key,
                )
            except _Unauthorized as exc:
                raise UpstreamAuthFailed("Wayfair rejected the access token") from exc

    async def query_inventory(
        self,
        account: str,
        skus: list[str] | None,
    ) -> tuple[list[dict], datetime]:
        account_config = self._require(account)
        if account_config.supplier_id is None:
            raise CapabilityUnavailable("supplier_id is not configured")

        variables: dict = {"supplierId": account_config.supplier_id}
        if skus:
            variables["filter"] = {"supplierPartNumbers": skus}

        rows: list[dict] = []
        seen: set[tuple[str, str]] = set()
        after = None

        for _ in range(MAX_PAGES):
            page = {"first": PAGE_SIZE, "after": after}
            result = await self._query_page(
                account,
                account_config,
                INVENTORY_QUERY,
                {**variables, "page": page},
                "inventorySummaryList",
            )

            for edge in result.get("edges") or []:
                for row in _map_node(edge.get("node") or {}):
                    key = (row["sku"], row["warehouse"])
                    if key not in seen:
                        seen.add(key)
                        rows.append(row)

            page_info = result.get("pageInfo") or {}
            if page_info.get("hasNextPage"):
                after = page_info.get("endCursor")
                if not after:
                    raise UpstreamUnavailable(
                        "Wayfair reported more pages but returned no cursor"
                    )
            else:
                break
        else:
            raise UpstreamUnavailable("Wayfair pagination exceeded the safety limit")

        return rows, datetime.now(timezone.utc)

    async def query_adjustments(
        self,
        account: str,
        *,
        from_date: datetime | None = None,
        to_date: datetime | None = None,
        sku: str | None = None,
        page_size: int = ADJUSTMENT_PAGE_SIZE,
    ) -> tuple[list[dict], datetime]:
        account_config = self._require(account)
        if account_config.supplier_id is None:
            raise CapabilityUnavailable("supplier_id is not configured")

        filter_payload: dict = {}
        if sku:
            filter_payload["supplierPartNumber"] = sku
        interval: dict = {}
        if from_date is not None:
            interval["from"] = _iso(from_date)
        if to_date is not None:
            interval["to"] = _iso(to_date)
        if interval:
            filter_payload["transactionDateInterval"] = interval

        variables: dict = {"supplierId": account_config.supplier_id}
        if filter_payload:
            variables["filter"] = filter_payload

        rows: list[dict] = []
        page_number = 0
        while page_number < MAX_ADJUSTMENT_PAGES:
            result = await self._query_page(
                account,
                account_config,
                ADJUSTMENT_QUERY,
                {
                    **variables,
                    "page": {"page": page_number, "pageSize": page_size},
                },
                "inventoryAdjustmentList",
            )
            nodes = result.get("nodes") or []
            rows.extend(_map_adjustment(node) for node in nodes)
            page_info = result.get("pageInfo") or {}
            total_pages = page_info.get("totalPages")
            if not nodes:
                break
            if isinstance(total_pages, int) and page_number + 1 >= total_pages:
                break
            page_number += 1
        else:
            raise UpstreamUnavailable("Wayfair pagination exceeded the safety limit")

        return rows, datetime.now(timezone.utc)

    async def query_inbound(self, account: str, skus: list[str] | None = None):
        raise CapabilityUnavailable(
            "Wayfair inbound operation is not verified"
        )
