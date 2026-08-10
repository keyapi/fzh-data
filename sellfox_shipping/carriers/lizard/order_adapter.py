"""Build 蜴国际 createOrder body from Sellfox package (adapter; Excel still default).

Pins:
- ``reference_no`` = ``package_sn`` (must match getLabel/cancelOrder)
- ``shipper_address`` from filed shipper code (e.g. S0143), not the Excel code alone
"""

from __future__ import annotations

from typing import Any

from sellfox_shipping.carriers.lizard.spreadsheet import (
    SHIPPER_CODE_DEFAULT,
    clean_phone,
    state_abbrev,
)
from sellfox_shipping.package_models import SellfoxPackageRecord

# Filed addresses from yiglobal-api/AGENT_HANDOFF.md (production registry).
# Excel only stores the code; API requires the expanded JSON.
_SHIPPER_ADDRESSES: dict[str, dict[str, str]] = {
    "S0143": {
        "shipper_name": "Dan-zhao",
        "shipper_postal_code": "77099",
        "shipper_address1": "10812 Fallstone Rd",
        "shipper_address2": "Suite 402",
        "shipper_state_province": "TX",
        "shipper_city": "Houston",
        "shipper_country": "US",
        "shipper_telphone": "2816770938",
    },
    "S0886": {
        "shipper_name": "Nickole Ayala",
        "shipper_postal_code": "10451",
        "shipper_address1": "417 East 162nd Street",
        "shipper_address2": "",
        "shipper_state_province": "NY",
        "shipper_city": "Bronx",
        "shipper_country": "US",
        "shipper_telphone": "9178817328",
    },
    "S0656": {
        "shipper_name": "Qiang Ma",
        "shipper_postal_code": "07936",
        "shipper_address1": "389 Route 10 Unit R",
        "shipper_address2": "",
        "shipper_state_province": "NJ",
        "shipper_city": "East Hanover",
        "shipper_country": "US",
        "shipper_telphone": "1234567890",
    },
    "S0625": {
        "shipper_name": "A_TX_77091",
        "shipper_postal_code": "77099",
        "shipper_address1": "10812 Fallstone Rd",
        "shipper_address2": "Suite 402",
        "shipper_state_province": "TX",
        "shipper_city": "Houston",
        "shipper_country": "US",
        "shipper_telphone": "0000000000",
    },
    "S0941": {
        "shipper_name": "FULFILLMENT CENTER",
        "shipper_postal_code": "07094",
        "shipper_address1": "915 Secaucus Rd",
        "shipper_address2": "",
        "shipper_state_province": "NJ",
        "shipper_city": "Secaucus",
        "shipper_country": "US",
        "shipper_telphone": "0000000000",
    },
    "S0795": {
        "shipper_name": "Qiang Ma",
        "shipper_postal_code": "07936",
        "shipper_address1": "389 STATE ROUTE 10 UNIT R",
        "shipper_address2": "",
        "shipper_state_province": "NJ",
        "shipper_city": "EAST HANOVER",
        "shipper_country": "US",
        "shipper_telphone": "1234567890",
    },
    "S1261": {
        "shipper_name": "77489",
        "shipper_postal_code": "77489",
        "shipper_address1": "611 S. Cravens Rd Suite 100",
        "shipper_address2": "",
        "shipper_state_province": "TX",
        "shipper_city": "Missori City",
        "shipper_country": "US",
        "shipper_telphone": "6083349880",
    },
}

_COUNTRY_ISO2 = {
    "US": "US",
    "USA": "US",
    "United States": "US",
    "美国": "US",
}


class UnknownShipperCodeError(ValueError):
    """Shipper code is not in the filed registry."""


def shipper_address_for_code(code: str) -> dict[str, str]:
    key = (code or "").strip().upper()
    # Preserve original casing of keys in registry (S0143 style).
    for registered, addr in _SHIPPER_ADDRESSES.items():
        if registered.upper() == key:
            return dict(addr)
    raise UnknownShipperCodeError(f"unknown shipper code: {code!r}")


def build_shipper_address_from_warehouse(
    warehouse_name: str, warehouses_cfg: dict
) -> dict[str, str]:
    """Build 蜴国际 shipper_address from config.warehouses[warehouse].address.

    Fail-closed: a missing warehouse or incomplete address raises ValueError so a
    label is never created with the wrong shipping address (lizard has no shipper
    codes — the S0143 table was a VITE concept).
    """
    key = (warehouse_name or "").strip()
    if not key:
        raise ValueError("warehouse_name is required for lizard shipper_address")
    wh = (warehouses_cfg or {}).get(key, {})
    if not wh:
        raise ValueError(f"warehouse '{key}' not found in config.warehouses")
    addr = wh.get("address", {}) or {}
    name = (addr.get("name") or "").strip()
    address1 = (addr.get("address1") or "").strip()
    city = (addr.get("city") or "").strip()
    state = (addr.get("state") or "").strip()
    postal = (addr.get("postal_code") or "").strip()
    phone = (addr.get("phone") or "").strip()
    missing = [
        field
        for field, value in (
            ("name", name),
            ("address1", address1),
            ("city", city),
            ("state", state),
            ("postal_code", postal),
            ("phone", phone),
        )
        if not value
    ]
    if missing:
        raise ValueError(
            f"warehouse '{key}' address incomplete: missing " + ", ".join(missing)
        )
    return {
        "shipper_name": name[:35],
        "shipper_postal_code": postal[:10],
        "shipper_address1": address1[:50],
        "shipper_address2": (addr.get("address2") or "")[:35],
        "shipper_state_province": state[:2],
        "shipper_city": city[:28],
        "shipper_country": (addr.get("country_code") or addr.get("country") or "US").strip().upper(),
        "shipper_telphone": phone[:15],
    }


def _oa_country(country: str, country_code: str) -> str:
    for key in (country_code, country):
        mapped = _COUNTRY_ISO2.get((key or "").strip())
        if mapped:
            return mapped
    raw = (country_code or country or "").strip()
    return raw.upper() if len(raw) == 2 else raw


def build_create_order_body(
    package: SellfoxPackageRecord,
    *,
    sm_code: str,
    shipper_code: str = SHIPPER_CODE_DEFAULT,
    weight_unit_type: str = "2",  # 2=KG/CM per API doc
    parcel_declared_value: float = 10.0,
    reference_no: str = "",
    shipper_address: dict[str, str] | None = None,
) -> dict[str, Any]:
    """Map a Sellfox package to 蜴国际 createOrder JSON (no HTTP).

    Does not replace Excel production path; use with ``LizardApiClient.create_order``.
    ``reference_no`` defaults to ``package_sn``; pass a unique value when a
    cancelled order still reserves the package_sn reference on 蜴国际.

    ``shipper_address`` (full address object) is preferred; when omitted it falls
    back to ``shipper_address_for_code(shipper_code)`` for backwards compatibility.
    """
    sn = (package.package_sn or "").strip()
    if not sn:
        raise ValueError("missing package_sn")
    product = (sm_code or "").strip()
    if not product:
        raise ValueError("sm_code is required")

    addr = package.address
    logistics = package.logistics
    weight_kg = max(logistics.weight_grams, 0.0) / 1000.0
    if weight_kg <= 0:
        raise ValueError("missing logistics weight_grams")
    length = logistics.length_cm
    width = logistics.width_cm
    height = logistics.height_cm
    if min(length, width, height) <= 0:
        raise ValueError("missing logistics length/width/height_cm")

    name_en = ""
    name_cn = ""
    qty = 1
    if package.items:
        first = package.items[0]
        name_en = (first.variation or first.seller_sku or first.commodity_sku or "item").strip()
        name_cn = name_en
        qty = max(int(first.quantity or 1), 1)

    return {
        "sm_code": product,
        "reference_no": (reference_no or "").strip() or sn,
        "weight_unit_type": weight_unit_type,
        "parcel_declared_value": parcel_declared_value,
        "parcel_quantity": 1,
        "box_list": [
            {
                "box_actual_weight": round(weight_kg, 3),
                "box_length": round(length, 2),
                "box_width": round(width, 2),
                "box_height": round(height, 2),
                "product_name_cn": name_cn or "item",
                "product_name_en": name_en or "item",
                "product_num": qty,
                "product_price": float(parcel_declared_value),
            }
        ],
        "oa_firstname": (addr.name or "").strip() or "Consignee",
        "oa_company": (addr.company or "").strip() or "FZH",
        "oa_country": _oa_country(addr.country, addr.country_code),
        "oa_state": state_abbrev(addr.state_or_region),
        "oa_city": (addr.city or "").strip(),
        "oa_postcode": (addr.postal_code or "").strip(),
        "oa_street_address1": (addr.address_line_1 or "").strip(),
        "oa_street_address2": (addr.address_line_2 or "").strip(),
        "oa_telphone": clean_phone(addr.phone or addr.mobile),
        "oa_email": (addr.email or "").strip() or "noreply@example.com",
        "oa_doorplate": "",
        "oa_phone_ext": "",
        "signature_service": "",
        "shipper_address": (
            shipper_address
            if shipper_address is not None
            else shipper_address_for_code(shipper_code)
        ),
    }
