"""Unit tests for the shared Sellfox gateway factory (get_sellfox_client)."""

from __future__ import annotations

from sellfox_shipping.sellfox_client import get_sellfox_client


def test_factory_returns_direct_client_when_credentials_set(monkeypatch) -> None:
    """SELLFOX_APP_ID/SECRET set → talk directly to the official OpenAPI."""
    monkeypatch.setenv("SELLFOX_APP_ID", "app-id")
    monkeypatch.setenv("SELLFOX_APP_SECRET", "app-secret")

    from sellfox_shipping.direct_sellfox_client import DirectSellfoxClient

    client = get_sellfox_client()
    assert isinstance(client, DirectSellfoxClient)
    assert client.app_id == "app-id"


def test_factory_returns_proxy_client_when_no_credentials(monkeypatch) -> None:
    """No credentials → fall back to the shared sellfox-api-proxy."""
    monkeypatch.delenv("SELLFOX_APP_ID", raising=False)
    monkeypatch.delenv("SELLFOX_APP_SECRET", raising=False)
    monkeypatch.setenv("SELLFOX_PROXY_API_KEY", "proxy-key")

    from sellfox_shipping.sellfox_client import SellfoxClient

    client = get_sellfox_client()
    assert isinstance(client, SellfoxClient)
    assert client.base_url == "https://api.vilavi.cn/sellfox"
    assert client.account == "sellfox-main"
    assert client.api_key == "proxy-key"
