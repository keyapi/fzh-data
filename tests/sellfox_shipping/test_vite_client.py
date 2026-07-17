"""Mock-only tests for VITE GOFO httpx spike (no live network)."""

from __future__ import annotations

import json

import httpx
import pytest

from sellfox_shipping.carriers.vite import ViteClientError, ViteGofoClient


def _client(handler) -> ViteGofoClient:
    return ViteGofoClient(
        api_key="test-key-not-real",
        base_url="https://test-api.vitedirect.com",
        transport=httpx.MockTransport(handler),
    )


def test_rate_gofo_posts_json_and_api_key_header():
    seen: dict = {}

    def handler(request: httpx.Request) -> httpx.Response:
        seen["path"] = request.url.path
        seen["method"] = request.method
        seen["api_key"] = request.headers.get("x-api-key")
        seen["body"] = json.loads(request.content)
        return httpx.Response(
            200,
            json={"carrier": "GOFO", "totalAmount": 4.5, "serviceType": "GOFO_PX"},
        )

    with _client(handler) as client:
        out = client.rate_gofo({"serviceType": "GOFO_PX", "packages": [{"weight": 2}]})

    assert seen["method"] == "POST"
    assert seen["path"] == "/rate2/gofo"
    assert seen["api_key"] == "test-key-not-real"
    assert seen["body"]["serviceType"] == "GOFO_PX"
    assert out["totalAmount"] == 4.5


def test_create_shipment_gofo():
    def handler(request: httpx.Request) -> httpx.Response:
        assert request.url.path == "/shipment2/gofo"
        return httpx.Response(
            200,
            json={"orderId": "PPGF-1", "trackingNumber": "9400", "status": "OK"},
        )

    with _client(handler) as client:
        out = client.create_shipment_gofo({"requestId": "rid-1", "serviceType": "GOFO_PX"})

    assert out["orderId"] == "PPGF-1"


def test_get_label_accepts_array_body():
    def handler(request: httpx.Request) -> httpx.Response:
        assert request.url.path == "/shipment2/label/PPGF-1"
        return httpx.Response(
            200,
            json=[{"orderId": "PPGF-1", "url": "https://example.com/a.pdf", "status": "OK"}],
        )

    with _client(handler) as client:
        labels = client.get_label("PPGF-1")

    assert len(labels) == 1
    assert labels[0]["url"].endswith(".pdf")


def test_401_raises_vite_client_error():
    def handler(request: httpx.Request) -> httpx.Response:
        return httpx.Response(401, text="unauthorized")

    with _client(handler) as client:
        with pytest.raises(ViteClientError, match="invalid x-api-key") as exc:
            client.rate_gofo({})
    assert exc.value.status_code == 401


def test_empty_api_key_rejected():
    with pytest.raises(ValueError, match="api_key"):
        ViteGofoClient(api_key="  ")
