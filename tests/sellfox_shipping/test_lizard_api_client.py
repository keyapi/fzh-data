"""Mock tests for 蜴国际 API httpx client (no live network / no secrets)."""

from __future__ import annotations

import json

import httpx
import pytest

from sellfox_shipping.carriers.lizard.api_client import (
    LizardApiClient,
    LizardApiError,
    parse_create_order_result,
    parse_get_label_result,
)


def _client(handler) -> LizardApiClient:
    return LizardApiClient(
        app_token="tok",
        app_key="key",
        base_url="http://lizard.test",
        transport=httpx.MockTransport(handler),
    )


def test_get_token_form_urlencoded():
    seen: dict = {}

    def handler(request: httpx.Request) -> httpx.Response:
        seen["path"] = request.url.path
        seen["ctype"] = request.headers.get("content-type", "")
        seen["body"] = request.content.decode()
        return httpx.Response(
            200,
            json={"code": 200, "result": {"access_token": "jwt-abc", "customer_code": "M6180"}},
        )

    with _client(handler) as client:
        token = client.get_token()

    assert token == "jwt-abc"
    assert seen["path"] == "/api/svc/getToken"
    assert "application/x-www-form-urlencoded" in seen["ctype"]
    assert "app_token=tok" in seen["body"]
    assert "app_key=key" in seen["body"]


def test_create_order_sends_authorization_and_json():
    seen: dict = {}

    def handler(request: httpx.Request) -> httpx.Response:
        if request.url.path.endswith("getToken"):
            return httpx.Response(
                200, json={"code": 200, "result": {"access_token": "jwt-1"}}
            )
        seen["path"] = request.url.path
        seen["auth"] = request.headers.get("authorization")
        seen["body"] = json.loads(request.content)
        return httpx.Response(
            200,
            json={
                "code": 200,
                "result": {
                    "order_code": "M6180-1",
                    "tracking_number": "8745",
                },
            },
        )

    with _client(handler) as client:
        out = client.create_order({"reference_no": "P2A1", "sm_code": "FedEx-Ground-J-TX"})

    assert seen["path"] == "/api/svc/createOrder"
    assert seen["auth"] == "jwt-1"
    assert seen["body"]["reference_no"] == "P2A1"
    assert out["code"] == 200
    assert out["result"]["order_code"] == "M6180-1"


def test_get_label_and_cancel_require_matching_reference():
    calls: list[str] = []

    def handler(request: httpx.Request) -> httpx.Response:
        if request.url.path.endswith("getToken"):
            return httpx.Response(
                200, json={"code": 200, "result": {"access_token": "jwt-1"}}
            )
        calls.append(request.url.path)
        body = json.loads(request.content)
        assert body["order_code"] == "OC1"
        assert body["reference_no"] == "REF1"
        if request.url.path.endswith("getLabel"):
            return httpx.Response(
                200,
                json={"code": 200, "result": {"sync_service_status": 1, "order_status": 2}},
            )
        return httpx.Response(200, json={"code": 200, "msg": "Success"})

    with _client(handler) as client:
        lab = client.get_label(order_code="OC1", reference_no="REF1")
        can = client.cancel_order(order_code="OC1", reference_no="REF1")

    assert lab["result"]["sync_service_status"] == 1
    assert can["msg"] == "Success"
    assert "/api/svc/getLabel" in calls
    assert "/api/svc/cancelOrder" in calls


def test_get_label_202_processing_is_ok():
    def handler(request: httpx.Request) -> httpx.Response:
        if request.url.path.endswith("getToken"):
            return httpx.Response(
                200, json={"code": 200, "result": {"access_token": "jwt-1"}}
            )
        return httpx.Response(200, json={"code": 202, "msg": "processing"})

    with _client(handler) as client:
        out = client.get_label(order_code="OC1", reference_no="REF1")
    assert out["code"] == 202


def test_business_error_raises():
    def handler(request: httpx.Request) -> httpx.Response:
        if request.url.path.endswith("getToken"):
            return httpx.Response(
                200, json={"code": 200, "result": {"access_token": "jwt-1"}}
            )
        return httpx.Response(
            200, json={"code": 400, "msg": "订单数据不存在"}
        )

    with _client(handler) as client:
        with pytest.raises(LizardApiError, match="订单数据不存在") as exc:
            client.get_label(order_code="OC1", reference_no="WRONG")
    assert exc.value.business_code == 400
    assert exc.value.phase == "query"
    assert exc.value.outcome == "retryable_query"
    assert exc.value.category == "service_rejected"


def test_create_business_rejection_is_final_and_safe_for_new_generation():
    def handler(request: httpx.Request) -> httpx.Response:
        if request.url.path.endswith("getToken"):
            return httpx.Response(
                200, json={"code": 200, "result": {"access_token": "jwt-1"}}
            )
        return httpx.Response(200, json={"code": 400, "msg": "invalid address"})

    with _client(handler) as client:
        with pytest.raises(LizardApiError) as exc:
            client.create_order({"reference_no": "P1"})
    assert exc.value.phase == "create"
    assert exc.value.outcome == "rejected"
    assert exc.value.category == "service_rejected"
    assert exc.value.safe_to_create_again is True


def test_missing_credentials():
    with pytest.raises(ValueError, match="app_token"):
        LizardApiClient(app_token="", app_key="k")


def test_parse_create_order_prefers_labels_nesting():
    parsed = parse_create_order_result(
        {
            "code": 200,
            "result": {
                "order_code": "M6180-1",
                "labels": {
                    "tracking_number": "1ZABC",
                    "label_url": "http://cdn.example/a.pdf",
                    "file_type": "pdf",
                },
                "tracking_number": "IGNORE-TOP",
            },
        }
    )
    assert parsed == {
        "order_code": "M6180-1",
        "tracking_number": "1ZABC",
        "label_url": "http://cdn.example/a.pdf",
        "file_type": "pdf",
    }


def test_parse_create_order_falls_back_to_result_root():
    parsed = parse_create_order_result(
        {
            "code": 200,
            "result": {
                "order_code": "M6180-2",
                "tracking_number": "8745",
                "label_url": "http://cdn.example/b.pdf",
            },
        }
    )
    assert parsed["tracking_number"] == "8745"
    assert parsed["label_url"] == "http://cdn.example/b.pdf"


def test_parse_get_label_ready_and_nested_labels():
    parsed = parse_get_label_result(
        {
            "code": 200,
            "result": {
                "sync_service_status": 1,
                "order_status": 2,
                "labels": {
                    "tracking_number": "TN1",
                    "label_url": "http://cdn.example/c.pdf",
                },
            },
        }
    )
    assert parsed["label_ready"] is True
    assert parsed["tracking_number"] == "TN1"
    assert parsed["label_url"] == "http://cdn.example/c.pdf"


def test_parse_get_label_processing_not_ready():
    parsed = parse_get_label_result(
        {"code": 202, "msg": "processing", "result": {"sync_service_status": 0}}
    )
    assert parsed["label_ready"] is False
    assert parsed["tracking_number"] == ""
