"""ERPNext ZLMB# Item → CartonDims (Lesson 17 fallback)."""

from __future__ import annotations

from typing import Any
from urllib.parse import quote

import httpx

from sellfox_shipping.carriers.lizard.dims import CartonDims
from sellfox_shipping.carriers.lizard.zlmb import commodity_sku_to_zlmb_item_name

# Priority 1: overseas finish-good; Priority 2: Shaoxing factory (Lesson 17)
# ERPNext field names use *_length/width/height (not *_L/W/H abbreviations).
_FIELD_SETS = (
    (
        "custom_finish_good_weight_per_unit",
        "custom_fg_package_length",
        "custom_fg_package_width",
        "custom_fg_package_height",
    ),
    (
        "custom_fg_weight_per_unit",
        "custom_package_length",
        "custom_package_width",
        "custom_package_height",
    ),
)

# Kept for documentation / future selective field requests.
_ITEM_FIELDS = [
    "name",
    "item_code",
    "custom_finish_good_weight_per_unit",
    "custom_fg_package_length",
    "custom_fg_package_width",
    "custom_fg_package_height",
    "custom_fg_weight_per_unit",
    "custom_package_length",
    "custom_package_width",
    "custom_package_height",
]


class ErpnextZlmbDimsLookup:
    """Fetch ZLMB# weight-template Items from ERPNext (prod by default)."""

    def __init__(
        self,
        *,
        base_url: str,
        api_key: str,
        api_secret: str,
        http_client: httpx.Client | None = None,
    ):
        self.base_url = base_url.rstrip("/")
        self._client = http_client or httpx.Client(timeout=60)
        self._headers = {"Authorization": f"token {api_key}:{api_secret}"}
        self._cache: dict[str, CartonDims | None] = {}

    def get(self, commodity_sku: str) -> CartonDims | None:
        zlmb = commodity_sku_to_zlmb_item_name(commodity_sku)
        if not zlmb:
            return None
        if zlmb not in self._cache:
            self._cache[zlmb] = self._fetch_dims(zlmb)
        return self._cache[zlmb]

    def prefetch(self, commodity_skus: list[str]) -> None:
        for sku in commodity_skus:
            self.get(sku)

    def _fetch_dims(self, zlmb_name: str) -> CartonDims | None:
        # Item name may contain # — quote path segment
        path = quote(zlmb_name, safe="")
        url = f"{self.base_url}/api/resource/Item/{path}"
        resp = self._client.get(url, headers=self._headers)
        if resp.status_code == 404:
            return None
        resp.raise_for_status()
        data = resp.json().get("data") or {}
        return _doc_to_dims(data)


def _doc_to_dims(doc: dict[str, Any]) -> CartonDims | None:
    for weight_key, l_key, w_key, h_key in _FIELD_SETS:
        weight_g = _as_float(doc.get(weight_key))
        length = _as_float(doc.get(l_key))
        width = _as_float(doc.get(w_key))
        height = _as_float(doc.get(h_key))
        if weight_g and weight_g > 0 and length and length > 0 and width and width > 0 and height and height > 0:
            return CartonDims(
                weight_kg=weight_g / 1000.0,
                length_cm=length,
                width_cm=width,
                height_cm=height,
            )
    return None


def _as_float(value: Any) -> float | None:
    if value is None or value == "":
        return None
    try:
        return float(value)
    except (TypeError, ValueError):
        return None
