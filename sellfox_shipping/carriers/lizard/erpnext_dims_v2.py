"""ERPNext ZLMB# dims lookup with sibling borrowing (V2).

Key rules:
- commodity_sku "KS0001-DM-194-IVORY" → first 3 segments → ZLMB#KS0001-DM-194
- Weight and L/W/H are independent atomic units — one missing doesn't block the other.
- L/W/H are a unit: if any one is 0/missing, borrow the entire set from a sibling.
- Siblings = same KS + same size, different fabric: ZLMB#KS0001-*-194.
"""

from __future__ import annotations

from typing import Any
from urllib.parse import quote

import httpx

from sellfox_shipping.carriers.lizard.dims import CartonDims
from sellfox_shipping.carriers.lizard.zlmb import commodity_sku_to_zlmb_item_name

# Priority 1: overseas finished-good; Priority 2: Shaoxing factory
_FG_WEIGHT = "custom_finish_good_weight_per_unit"
_FG_LENGTH = "custom_fg_package_length"
_FG_WIDTH = "custom_fg_package_width"
_FG_HEIGHT = "custom_fg_package_height"

_FTY_WEIGHT = "custom_fg_weight_per_unit"
_FTY_LENGTH = "custom_package_length"
_FTY_WIDTH = "custom_package_width"
_FTY_HEIGHT = "custom_package_height"

_FIELDS = ",".join(
    [
        "name",
        "item_code",
        "item_name",
        _FG_WEIGHT,
        _FG_LENGTH,
        _FG_WIDTH,
        _FG_HEIGHT,
        _FTY_WEIGHT,
        _FTY_LENGTH,
        _FTY_WIDTH,
        _FTY_HEIGHT,
    ]
)


class ErpnextDimsLookupV2:
    """ZLMB# dims with cross-fabric sibling borrowing + persistent in-memory cache."""

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
        # Cache: commodity_sku → CartonDims | None (None = known-missing)
        self._cache: dict[str, CartonDims | None] = {}
        # Name cache: commodity_sku → item_name
        self._name_cache: dict[str, str] = {}
        # Sibling cache: (style, size) → list[dict] of sibling Item docs
        self._sibling_cache: dict[tuple[str, str], list[dict] | None] = {}

    # ── Public API ──────────────────────────────────────────────

    def get(self, commodity_sku: str) -> CartonDims | None:
        sku = (commodity_sku or "").strip()
        if not sku:
            return None
        if sku not in self._cache:
            self._cache[sku] = self._resolve(sku)
        return self._cache[sku]

    def prefetch(self, commodity_skus: list[str]) -> None:
        for sku in commodity_skus:
            self.get(sku)

    def get_item_name(self, commodity_sku: str) -> str:
        """Return cached item_name for a commodity_sku (empty string if unknown)."""
        sku = (commodity_sku or "").strip()
        if not sku:
            return ""
        if sku not in self._cache:
            self.get(sku)  # triggers _resolve which populates _name_cache
        return self._name_cache.get(sku, "")

    def refresh(self, commodity_sku: str) -> CartonDims | None:
        """Force re-fetch (bypass cache)."""
        sku = (commodity_sku or "").strip()
        if not sku:
            return None
        self._cache.pop(sku, None)
        return self.get(sku)

    # ── Resolution ──────────────────────────────────────────────

    def _resolve(self, commodity_sku: str) -> CartonDims | None:
        parts = _split_sku(commodity_sku)
        if not parts:
            return None
        zlmb_name = f"ZLMB#{parts['key']}"  # ZLMB#KS0001-DM-194
        item = self._fetch_item(zlmb_name)
        if item is None:
            return None

        # Cache item_name
        item_name = (item.get("item_name") or "").strip()
        if item_name:
            self._name_cache[commodity_sku] = item_name

        siblings = self._fetch_siblings(parts["style"], parts["size"])

        weight_g = _resolve_weight(item, siblings)

        fg_ok = _all_positive(item, _FG_LENGTH, _FG_WIDTH, _FG_HEIGHT)
        fty_ok = _all_positive(item, _FTY_LENGTH, _FTY_WIDTH, _FTY_HEIGHT)

        length_cm = width_cm = height_cm = 0.0

        if fg_ok:
            length_cm = _as_float(item.get(_FG_LENGTH)) or 0
            width_cm = _as_float(item.get(_FG_WIDTH)) or 0
            height_cm = _as_float(item.get(_FG_HEIGHT)) or 0
        else:
            borrowed = _borrow_dims(item, siblings, _FG_LENGTH, _FG_WIDTH, _FG_HEIGHT)
            if borrowed:
                length_cm, width_cm, height_cm = borrowed
            elif fty_ok:
                length_cm = _as_float(item.get(_FTY_LENGTH)) or 0
                width_cm = _as_float(item.get(_FTY_WIDTH)) or 0
                height_cm = _as_float(item.get(_FTY_HEIGHT)) or 0
            else:
                borrowed = _borrow_dims(
                    item, siblings, _FTY_LENGTH, _FTY_WIDTH, _FTY_HEIGHT
                )
                if borrowed:
                    length_cm, width_cm, height_cm = borrowed

        dims = CartonDims(
            weight_kg=weight_g / 1000.0 if weight_g else 0,
            length_cm=length_cm,
            width_cm=width_cm,
            height_cm=height_cm,
        )
        return dims if dims.is_complete else None

    # ── EN API ───────────────────────────────────────────────────

    def _fetch_item(self, item_name: str) -> dict | None:
        path = quote(item_name, safe="")
        url = f"{self.base_url}/api/resource/Item/{path}?fields={_FIELDS}"
        resp = self._client.get(url, headers=self._headers)
        if resp.status_code == 404:
            return None
        resp.raise_for_status()
        return resp.json().get("data") or {}

    def _fetch_siblings(self, style: str, size: str) -> list[dict]:
        """Return sibling ZLMB# items matching same style+size, any fabric."""
        cache_key = (style, size)
        if cache_key in self._sibling_cache:
            cached = self._sibling_cache[cache_key]
            return list(cached) if cached else []

        pattern = f"ZLMB#{style}-%-{size}"
        url = (
            f"{self.base_url}/api/resource/Item"
            f"?filters=[[\"name\",\"like\",\"{quote(pattern, safe='')}\"]]"
            f"&fields={_FIELDS}"
            f"&limit_page_length=50"
        )
        resp = self._client.get(url, headers=self._headers)
        if resp.status_code != 200:
            self._sibling_cache[cache_key] = None
            return []
        data = resp.json().get("data") or []
        self._sibling_cache[cache_key] = list(data)
        return list(data)

    # Needed for DimsLookup protocol compatibility
    def prefetch(self, commodity_skus: list[str]) -> None:
        for sku in commodity_skus:
            self.get(sku)


# ── Helpers ──────────────────────────────────────────────────────────


def _split_sku(commodity_sku: str) -> dict | None:
    """Parse SKU into style-fabric-size components."""
    parts = (commodity_sku or "").strip().split("-")
    if len(parts) < 3:
        return None
    return {
        "style": parts[0],   # KS0001
        "fabric": parts[1],  # DM
        "size": parts[2],    # 194
        "key": "-".join(parts[:3]),
    }


def _all_positive(item: dict, *fields: str) -> bool:
    for f in fields:
        v = _as_float(item.get(f))
        if v is None or v <= 0:
            return False
    return True


def _as_float(value: Any) -> float | None:
    if value is None or value == "":
        return None
    try:
        return float(value)
    except (TypeError, ValueError):
        return None


def _resolve_weight(item: dict, siblings: list[dict]) -> float | None:
    """Weight is independent: try FG, borrow FG, try FTY, borrow FTY."""
    w = _as_float(item.get(_FG_WEIGHT))
    if w and w > 0:
        return w
    w = _first_positive_from(siblings, _FG_WEIGHT)
    if w:
        return w
    w = _as_float(item.get(_FTY_WEIGHT))
    if w and w > 0:
        return w
    return _first_positive_from(siblings, _FTY_WEIGHT)


def _borrow_dims(
    item: dict,
    siblings: list[dict],
    l_field: str,
    w_field: str,
    h_field: str,
) -> tuple[float, float, float] | None:
    """Find the first sibling with all three dims > 0. Return (L, W, H) or None."""
    for sib in siblings:
        if sib.get("name") == item.get("name"):
            continue
        l = _as_float(sib.get(l_field))
        w = _as_float(sib.get(w_field))
        h = _as_float(sib.get(h_field))
        if l and l > 0 and w and w > 0 and h and h > 0:
            return (l, w, h)
    return None


def _first_positive_from(items: list[dict], field: str) -> float | None:
    for item in items:
        v = _as_float(item.get(field))
        if v and v > 0:
            return v
    return None
