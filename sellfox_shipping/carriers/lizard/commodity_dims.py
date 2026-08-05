"""Sellfox commodity pageList → CartonDims (primary dims source for P1B)."""

from __future__ import annotations

from typing import Any

import httpx

from sellfox_shipping.carriers.lizard.dims import CartonDims


class CommodityPageListDimsLookup:
    """Batch-fetch carton dims via POST /api/commodity/pageList.json.

    Official filter field is ``isGroup`` (0 = normal SKU). ERPNext fallback is
    intentionally out of scope here — inject a composite DimsLookup later.
    """

    def __init__(
        self,
        *,
        proxy_base_url: str,
        proxy_account: str,
        proxy_api_key: str = "",
        http_client: httpx.Client | None = None,
        page_size: int = 100,
    ):
        self.base_url = proxy_base_url.rstrip("/")
        self.account = proxy_account
        self.api_key = proxy_api_key
        self._client = http_client or httpx.Client(timeout=60)
        self._page_size = page_size
        self._cache: dict[str, CartonDims | None] = {}

    def get(self, commodity_sku: str) -> CartonDims | None:
        sku = (commodity_sku or "").strip()
        if not sku:
            return None
        if sku not in self._cache:
            self.prefetch([sku])
        return self._cache.get(sku)

    def prefetch(self, commodity_skus: list[str]) -> None:
        missing = [
            s.strip()
            for s in commodity_skus
            if s and s.strip() and s.strip() not in self._cache
        ]
        if not missing:
            return
        # pageList accepts skus[]; chunk to stay under page_size
        for i in range(0, len(missing), self._page_size):
            chunk = missing[i : i + self._page_size]
            rows = self._fetch_rows(chunk)
            found: set[str] = set()
            for row in rows:
                sku = str(row.get("sku") or "").strip()
                if not sku:
                    continue
                dims = _row_to_dims(row)
                self._cache[sku] = dims if dims and dims.is_complete else None
                found.add(sku)
            for sku in chunk:
                if sku not in found:
                    self._cache[sku] = None

    def _fetch_rows(self, skus: list[str]) -> list[dict[str, Any]]:
        url = f"{self.base_url}/v1/{self.account}/api/commodity/pageList.json"
        headers = {}
        if self.api_key:
            headers["Authorization"] = f"Bearer {self.api_key}"
        body = {
            "skus": skus,
            "pageNo": "1",
            "pageSize": str(max(self._page_size, len(skus))),
            "isGroup": "0",
        }
        resp = self._client.post(url, json=body, headers=headers)
        resp.raise_for_status()
        data = resp.json()
        if data.get("code") != 0:
            raise RuntimeError(
                f"commodity pageList error: {data.get('msg', 'unknown')}"
            )
        page = data.get("data") or {}
        return list(page.get("rows") or [])


def _row_to_dims(row: dict[str, Any]) -> CartonDims | None:
    try:
        return CartonDims(
            weight_kg=float(row.get("cartonWeight") or 0),
            length_cm=float(row.get("cartonLength") or 0),
            width_cm=float(row.get("cartonWidth") or 0),
            height_cm=float(row.get("cartonHeight") or 0),
        )
    except (TypeError, ValueError):
        return None
