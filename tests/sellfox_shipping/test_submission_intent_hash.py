"""Tests for canonical request hashing (P1C)."""

from __future__ import annotations

from sellfox_shipping.submission_service import (
    build_canonical_request,
    canonical_to_wire_body,
)


def test_same_request_same_hash() -> None:
    items = [{"order_item_id": "I1", "quantity": 2}]
    _, _, h1 = build_canonical_request(
        account_key="sellfox-main",
        package_db_id=10,
        external_order_id="O-1",
        shop_id="S1",
        tracking_number="TN1",
        carrier_name="FedEx",
        shipping_service="Ground",
        items=items,
    )
    _, _, h2 = build_canonical_request(
        account_key="sellfox-main",
        package_db_id=10,
        external_order_id="O-1",
        shop_id="S1",
        tracking_number="TN1",
        carrier_name="FedEx",
        shipping_service="Ground",
        items=items,
    )
    assert h1 == h2
    assert len(h1) == 64


def test_changed_tracking_changes_hash() -> None:
    base = dict(
        account_key="sellfox-main",
        package_db_id=10,
        external_order_id="O-1",
        shop_id="S1",
        carrier_name="FedEx",
        shipping_service="",
        items=[{"order_item_id": "I1", "quantity": 1}],
    )
    _, _, h1 = build_canonical_request(**base, tracking_number="TN-A")
    _, _, h2 = build_canonical_request(**base, tracking_number="TN-B")
    assert h1 != h2


def test_wire_body_uses_order_id_not_amazon_order_id() -> None:
    req, _, _ = build_canonical_request(
        account_key="sellfox-main",
        package_db_id=1,
        external_order_id="111-222",
        shop_id="shop-1",
        tracking_number="TN",
        carrier_name="Carrier",
        shipping_service="svc",
        items=[{"order_item_id": "item-1", "quantity": 3}],
    )
    wire = canonical_to_wire_body(req)
    assert wire["orderId"] == "111-222"
    assert "amazonOrderId" not in wire
    # quantity is a string per PackageSubmitToPlatformOpenQO.SubmitOrderItemOpenQO
    assert wire["items"] == [{"orderItemId": "item-1", "quantity": "3"}]
