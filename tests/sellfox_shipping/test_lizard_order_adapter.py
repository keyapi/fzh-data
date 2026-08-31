"""TDD: S0143 shipper map + reference_no=package_sn for 蜴国际 API createOrder body."""

from __future__ import annotations

import pytest

from sellfox_shipping.carriers.lizard.order_adapter import (
    UnknownShipperCodeError,
    build_create_order_body,
    shipper_address_for_code,
)
from sellfox_shipping.package_models import (
    SellfoxPackageAddress,
    SellfoxPackageItemRecord,
    SellfoxPackageLogistics,
    SellfoxPackageRecord,
)


def _pkg(**kwargs) -> SellfoxPackageRecord:
    base = dict(
        account_key="acc",
        package_sn="P2A-TEST-001",
        address=SellfoxPackageAddress(
            name="Smoke Test",
            company="FZH",
            address_line_1="10812 Fallstone Rd",
            address_line_2="Suite 100",
            city="Houston",
            state_or_region="TX",
            postal_code="77099",
            country="United States",
            country_code="US",
            phone="2816770938",
            email="ops@example.com",
        ),
        logistics=SellfoxPackageLogistics(
            channel_name="FedEx",
            weight_grams=2000.0,
            length_cm=25.0,
            width_cm=20.0,
            height_cm=15.0,
        ),
        items=[
            SellfoxPackageItemRecord(
                external_order_id="O1",
                order_item_id="I1",
                seller_sku="SKU1",
                commodity_sku="KS0001",
                quantity=1,
                variation="Widget",
            )
        ],
    )
    base.update(kwargs)
    return SellfoxPackageRecord(**base)


def test_s0143_expands_to_filed_shipper_address():
    addr = shipper_address_for_code("S0143")
    assert addr["shipper_name"] == "Dan-zhao"
    assert addr["shipper_postal_code"] == "77099"
    assert addr["shipper_address1"] == "10812 Fallstone Rd"
    assert addr["shipper_address2"] == "Suite 402"
    assert addr["shipper_state_province"] == "TX"
    assert addr["shipper_city"] == "Houston"
    assert addr["shipper_country"] == "US"
    assert addr["shipper_telphone"] == "2816770938"


def test_unknown_shipper_code_raises():
    with pytest.raises(UnknownShipperCodeError, match="S9999"):
        shipper_address_for_code("S9999")


def test_create_order_body_sets_reference_no_to_package_sn():
    body = build_create_order_body(
        _pkg(),
        sm_code="FedEx-Ground-J-TX",
        shipper_code="S0143",
    )
    assert body["reference_no"] == "P2A-TEST-001"
    assert body["sm_code"] == "FedEx-Ground-J-TX"
    assert body["shipper_address"]["shipper_name"] == "Dan-zhao"
    assert body["oa_firstname"] == "Smoke Test"
    assert body["oa_country"] == "US"
    assert body["oa_state"] == "TX"
    assert body["oa_postcode"] == "77099"
    assert body["oa_street_address1"] == "10812 Fallstone Rd"
    assert body["box_list"][0]["box_actual_weight"] == pytest.approx(2.0)
    assert body["box_list"][0]["product_name_en"] == "Widget"


def test_blank_package_sn_rejected():
    with pytest.raises(ValueError, match="package_sn"):
        build_create_order_body(
            _pkg(package_sn="  "),
            sm_code="FedEx-Ground-J-TX",
        )


def test_shipper_address_from_warehouse_centrade():
    """蜴国际 shipper_address comes from config warehouse (fail-closed), not S0143."""
    from sellfox_shipping.carriers.lizard.order_adapter import (
        build_shipper_address_from_warehouse,
    )

    cfg = {
        "CENTRADE": {
            "address": {
                "name": "FZH USNJ Warehouse",
                "address1": "389 Route 10 Unit R",
                "city": "East Hanover",
                "state": "NJ",
                "postal_code": "07936",
                "country_code": "US",
                "phone": "1234567890",
            }
        }
    }
    addr = build_shipper_address_from_warehouse("CENTRADE", cfg)
    assert addr["shipper_name"] == "FZH USNJ Warehouse"
    assert addr["shipper_postal_code"] == "07936"
    assert addr["shipper_state_province"] == "NJ"
    assert addr["shipper_city"] == "East Hanover"
    assert addr["shipper_country"] == "US"


def test_shipper_address_from_warehouse_unknown_fails_closed():
    """Unknown warehouse → ValueError, never a silently-wrong address."""
    from sellfox_shipping.carriers.lizard.order_adapter import (
        build_shipper_address_from_warehouse,
    )

    with pytest.raises(ValueError, match="not found"):
        build_shipper_address_from_warehouse("NOPE", {"CENTRADE": {"address": {}}})
    with pytest.raises(ValueError, match="warehouse_name is required"):
        build_shipper_address_from_warehouse("", {"CENTRADE": {"address": {}}})


def test_build_create_order_body_uses_passed_shipper_address():
    """build_create_order_body prefers the passed shipper_address over shipper_code."""
    addr = {
        "shipper_name": "FZH USNJ Warehouse",
        "shipper_postal_code": "07936",
        "shipper_address1": "389 Route 10 Unit R",
        "shipper_address2": "",
        "shipper_state_province": "NJ",
        "shipper_city": "East Hanover",
        "shipper_country": "US",
        "shipper_telphone": "1234567890",
    }
    body = build_create_order_body(
        _pkg(),
        sm_code="FedEx-Ground-J-TX",
        shipper_address=addr,
    )
    assert body["shipper_address"] == addr
