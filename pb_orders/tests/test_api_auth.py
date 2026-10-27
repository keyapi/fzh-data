#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""JSON API 鉴权：API Key、OIDC Bearer、scope、速率限制、登录闸门边界。

`/api/v1` 不接受 cookie 会话：没带 token 必须是 JSON 401，而不是 303 去登录页。
"""

from __future__ import annotations

import pytest
from fastapi.testclient import TestClient

import web.api_auth as api_auth
import web.app as web_app
from web.config import get_settings, reset_settings

ISSUER = "https://api.example.test/oidc"
REDIRECT = "https://api.example.test/pb/oidc-callback"


def _enable_oidc(monkeypatch, allowed: str = ""):
    monkeypatch.setenv("PB_ORDERS_OIDC_ISSUER", ISSUER)
    monkeypatch.setenv("PB_ORDERS_OIDC_REDIRECT_URI", REDIRECT)
    monkeypatch.setenv("PB_ORDERS_SESSION_SECRET", "test-session-secret")
    monkeypatch.setenv("PB_ORDERS_ALLOWED_USERS", allowed)
    reset_settings()
    # userinfo 缓存是模块级的，别让上一个用例的 token 影响这一次
    api_auth._USERINFO_CACHE.clear()


def _mock_userinfo(monkeypatch, payload, status_code: int = 200):
    class _Resp:
        def __init__(self):
            self.status_code = status_code

        def json(self):
            return payload

    class _Client:
        async def __aenter__(self):
            return self

        async def __aexit__(self, *exc):
            return False

        async def get(self, url, headers=None, timeout=None):
            return _Resp()

    monkeypatch.setattr(api_auth.httpx, "AsyncClient", lambda *a, **k: _Client())


# ---------- API Key ----------

def test_missing_bearer_returns_json_401(client):
    resp = client.get("/api/v1/settings/no-stock")
    assert resp.status_code == 401
    assert resp.headers["content-type"].startswith("application/json")
    assert resp.json()["error"]["code"] == "unauthorized"
    assert "Bearer" in resp.headers.get("www-authenticate", "")


def test_invalid_key_is_rejected(client):
    client.headers["Authorization"] = "Bearer sk-not-a-real-key"
    resp = client.get("/api/v1/settings/no-stock")
    assert resp.status_code == 401
    assert resp.json()["error"]["code"] == "unauthorized"


def test_revoked_key_is_rejected(api_client, api_key):
    assert api_client.repo.revoke_api_key(api_key["id"])
    resp = api_client.get("/api/v1/settings/no-stock")
    assert resp.status_code == 401


def test_key_scope_is_enforced(client, pb_env):
    row = client.repo.create_api_key("readonly", "read")
    client.headers["Authorization"] = f"Bearer {row['key']}"
    resp = client.post(
        "/api/v1/checks",
        files={"raw_csv": ("new.csv", pb_env.csv.read_bytes(), "text/csv")},
        data={"no_stock": ""},
    )
    assert resp.status_code == 403
    assert resp.json()["error"]["code"] == "forbidden_scope"


def test_rate_limit_returns_429(api_client):
    # 0.001 rps -> 每分钟 1 次，第二次必被挡
    object.__setattr__(api_client.settings, "api_key_rate_limit_rps", 0.001)
    assert api_client.get("/api/v1/settings/no-stock").status_code == 200
    resp = api_client.get("/api/v1/settings/no-stock")
    assert resp.status_code == 429
    assert resp.json()["error"]["code"] == "rate_limited"


def test_key_is_hashed_not_stored_plaintext(client, api_key):
    with client.repo.connect() as conn:
        row = conn.execute(
            "SELECT key_hash, key_prefix FROM api_keys WHERE id = ?", (api_key["id"],)
        ).fetchone()
    assert api_key["key"] not in (row["key_hash"], row["key_prefix"])
    assert len(row["key_hash"]) == 64


# ---------- OIDC 用户 token ----------

def test_api_is_not_gated_by_login_redirect(pb_env, monkeypatch):
    """认证开着时 /api 也要 401 JSON —— 不能 303 去登录页（Agent 没法跟）。"""
    _enable_oidc(monkeypatch)
    app = web_app.create_app()
    with TestClient(app) as c:
        resp = c.get("/api/v1/settings/no-stock", follow_redirects=False)
        assert resp.status_code == 401
        assert resp.headers["content-type"].startswith("application/json")


def test_oidc_token_is_accepted(pb_env, monkeypatch):
    _enable_oidc(monkeypatch)
    _mock_userinfo(monkeypatch, {"sub": "user-1", "name": "张三"})
    app = web_app.create_app()
    with TestClient(app) as c:
        resp = c.get(
            "/api/v1/settings/no-stock",
            headers={"Authorization": "Bearer oidc-token-1"},
        )
        assert resp.status_code == 200


def test_oidc_token_respects_allowlist(pb_env, monkeypatch):
    _enable_oidc(monkeypatch, allowed="李四")
    _mock_userinfo(monkeypatch, {"sub": "user-1", "name": "张三"})
    app = web_app.create_app()
    with TestClient(app) as c:
        resp = c.get(
            "/api/v1/settings/no-stock",
            headers={"Authorization": "Bearer oidc-token-2"},
        )
        assert resp.status_code == 403
        assert resp.json()["error"]["code"] == "forbidden"


def test_invalid_oidc_token_is_rejected(pb_env, monkeypatch):
    _enable_oidc(monkeypatch)
    _mock_userinfo(monkeypatch, {"error": "invalid_token"}, status_code=401)
    app = web_app.create_app()
    with TestClient(app) as c:
        resp = c.get(
            "/api/v1/settings/no-stock",
            headers={"Authorization": "Bearer expired-token"},
        )
        assert resp.status_code == 401


def test_userinfo_cache_avoids_repeat_calls(pb_env, monkeypatch):
    _enable_oidc(monkeypatch)
    calls = {"n": 0}

    class _Resp:
        status_code = 200

        def json(self):
            return {"sub": "user-9", "name": "缓存"}

    class _Client:
        async def __aenter__(self):
            return self

        async def __aexit__(self, *exc):
            return False

        async def get(self, url, headers=None, timeout=None):
            calls["n"] += 1
            return _Resp()

    monkeypatch.setattr(api_auth.httpx, "AsyncClient", lambda *a, **k: _Client())
    app = web_app.create_app()
    with TestClient(app) as c:
        for _ in range(3):
            assert c.get(
                "/api/v1/settings/no-stock",
                headers={"Authorization": "Bearer cache-token"},
            ).status_code == 200
    assert calls["n"] == 1


def test_api_healthz_is_public_even_with_oidc(pb_env, monkeypatch):
    _enable_oidc(monkeypatch)
    app = web_app.create_app()
    with TestClient(app) as c:
        assert c.get("/api/v1/healthz").status_code == 200
