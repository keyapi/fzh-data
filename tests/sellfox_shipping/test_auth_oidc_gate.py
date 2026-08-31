"""OIDC enable-path: config completeness, cookie secure, middleware gate."""

from __future__ import annotations

import pytest
from starlette.requests import Request as StarletteRequest
from starlette.testclient import TestClient

from sellfox_shipping.auth_oidc import (
    OidcSettings,
    assert_oidc_config_complete,
    cookie_should_be_secure,
    make_session_token,
    resolve_actor,
)


def _settings(**overrides) -> OidcSettings:
    base = dict(
        enabled=True,
        issuer="https://api.example/oidc",
        client_id="sellfox-shipping",
        client_secret="secret",
        redirect_uri="https://ship.example/oidc-callback",
        session_secret="session-secret",
    )
    base.update(overrides)
    return OidcSettings(**base)


def test_assert_oidc_config_complete_ok_when_disabled():
    assert_oidc_config_complete(_settings(enabled=False, session_secret=""))


def test_assert_oidc_config_complete_raises_when_enabled_missing_secret():
    with pytest.raises(RuntimeError, match="SESSION_SECRET|session_secret"):
        assert_oidc_config_complete(_settings(session_secret=""))


def test_assert_oidc_config_complete_raises_when_enabled_missing_client_secret():
    with pytest.raises(RuntimeError, match="CLIENT_SECRET|client_secret"):
        assert_oidc_config_complete(_settings(client_secret=""))


def test_cookie_secure_follows_https_redirect():
    assert cookie_should_be_secure("https://ship.example/oidc-callback") is True
    assert cookie_should_be_secure("http://127.0.0.1:8401/oidc-callback") is False


def test_resolve_actor_prefers_oidc_identity_when_enabled():
    scope = {
        "type": "http",
        "method": "GET",
        "path": "/",
        "headers": [],
        "query_string": b"",
    }
    request = StarletteRequest(scope)
    request.state.user = {"identity": "ding-u42", "display_name": "张三"}
    assert resolve_actor(request, _settings(), fallback="web-user") == "ding-u42"


def test_resolve_actor_uses_fallback_when_auth_disabled():
    scope = {
        "type": "http",
        "method": "GET",
        "path": "/",
        "headers": [],
        "query_string": b"",
    }
    request = StarletteRequest(scope)
    assert (
        resolve_actor(request, _settings(enabled=False), fallback="ops-alice")
        == "ops-alice"
    )


def test_middleware_api_returns_json_401_when_enabled(monkeypatch):
    from sellfox_shipping import app as app_mod

    monkeypatch.setattr(app_mod, "_oidc_settings", _settings())
    client = TestClient(app_mod.app)
    r = client.get("/api/packages")
    assert r.status_code == 401
    assert r.headers.get("content-type", "").startswith("application/json")
    assert r.json()["detail"] == "Authentication required"


def test_middleware_page_redirects_to_login_when_enabled(monkeypatch):
    from sellfox_shipping import app as app_mod

    monkeypatch.setattr(app_mod, "_oidc_settings", _settings())
    client = TestClient(app_mod.app)
    r = client.get("/packages", follow_redirects=False)
    assert r.status_code in (302, 303, 307)
    assert "/oidc-login" in r.headers.get("location", "")


def test_middleware_allows_api_with_valid_session(monkeypatch):
    from sellfox_shipping import app as app_mod

    settings = _settings()
    monkeypatch.setattr(app_mod, "_oidc_settings", settings)
    token = make_session_token(
        "ding-u9", "Tester", secret=settings.session_secret
    )
    client = TestClient(app_mod.app)
    r = client.get(
        "/api/packages",
        cookies={settings.cookie_name: token},
    )
    assert r.status_code == 200
    assert "packages" in r.json() or "total" in r.json() or isinstance(r.json(), dict)