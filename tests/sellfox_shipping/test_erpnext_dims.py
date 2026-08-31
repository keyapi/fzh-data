"""ERPNext ZLMB dims fallback + cascade with Sellfox commodity pageList."""

from __future__ import annotations

import json

import httpx

from sellfox_shipping.carriers.lizard.cascade import CascadingDimsLookup
from sellfox_shipping.carriers.lizard.dims import CartonDims, StaticDimsLookup
from sellfox_shipping.carriers.lizard.erpnext_dims import ErpnextZlmbDimsLookup
from sellfox_shipping.carriers.lizard.zlmb import commodity_sku_to_zlmb_item_name


def test_zlmb_item_name_strips_color_keeps_fabric() -> None:
    assert (
        commodity_sku_to_zlmb_item_name("KS0002-DL-194-IVORY")
        == "ZLMB#KS0002-DL-194"
    )
    assert commodity_sku_to_zlmb_item_name("KS0001-HLR-100") == "ZLMB#KS0001-HLR-100"
    assert commodity_sku_to_zlmb_item_name("KS0002") is None


def test_erpnext_lookup_uses_shaoxing_when_overseas_empty() -> None:
    def handler(request: httpx.Request) -> httpx.Response:
        assert "ZLMB%23KS0002-DL-194" in str(request.url)
        return httpx.Response(
            200,
            json={
                "data": {
                    "name": "ZLMB#KS0002-DL-194",
                    "custom_finish_good_weight_per_unit": 0,
                    "custom_fg_package_length": 0,
                    "custom_fg_package_width": 0,
                    "custom_fg_package_height": 0,
                    "custom_fg_weight_per_unit": 4100,
                    "custom_package_length": 58,
                    "custom_package_width": 19,
                    "custom_package_height": 45,
                }
            },
        )

    client = httpx.Client(transport=httpx.MockTransport(handler))
    lookup = ErpnextZlmbDimsLookup(
        base_url="https://erpnext.example",
        api_key="k",
        api_secret="s",
        http_client=client,
    )
    dims = lookup.get("KS0002-DL-194-IVORY")
    assert dims == CartonDims(
        weight_kg=4.1, length_cm=58.0, width_cm=19.0, height_cm=45.0
    )


def test_cascade_prefers_sellfox_over_erpnext() -> None:
    primary = StaticDimsLookup(
        {
            "KS0248-HLR-60-BLACK": CartonDims(
                weight_kg=2.5, length_cm=60, width_cm=55, height_cm=5
            )
        }
    )
    fallback = StaticDimsLookup(
        {
            "KS0248-HLR-60-BLACK": CartonDims(
                weight_kg=9.9, length_cm=1, width_cm=1, height_cm=1
            )
        }
    )
    dims = CascadingDimsLookup(primary, fallback).get("KS0248-HLR-60-BLACK")
    assert dims is not None
    assert dims.weight_kg == 2.5


def test_cascade_falls_back_when_primary_empty() -> None:
    primary = StaticDimsLookup({})
    fallback = StaticDimsLookup(
        {
            "KS0002-DL-194-IVORY": CartonDims(
                weight_kg=4.1, length_cm=58, width_cm=19, height_cm=45
            )
        }
    )
    dims = CascadingDimsLookup(primary, fallback).get("KS0002-DL-194-IVORY")
    assert dims is not None
    assert dims.weight_kg == 4.1
