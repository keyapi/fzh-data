from __future__ import annotations

from urllib.parse import parse_qs, urlparse

import httpx
from fastapi.testclient import TestClient

import admin
from config import AccountConfig, AppConfig, Credentials, OIDCConfig
from main import create_app


def _config(admin_identities=None) -> AppConfig:
    return AppConfig(
        accounts={
            "centrade": AccountConfig(
                upstream="https://api.example.test",
                credentials=Credentials(client_id="id", client_secret="secret"),
            )
        },
        oidc=OIDCConfig(
            issuer="https://oidc.example.test",
            client_id="wayfair",
            client_secret="oidc-secret",
            redirect_uri="http://testserver/admin/oidc-callback",
            admin_identities=admin_identities or ["ding-admin"],
            cookie_secure=False,
        ),
    )


def _mock_oidc(monkeypatch, sub="ding-admin"):
    def handler(request: httpx.Request) -> httpx.Response:
        if request.url.path.endswith("/token"):
            return httpx.Response(200, json={"access_token": "tok"})
        if request.url.path.endswith("/userinfo"):
            assert request.headers["Authorization"] == "Bearer tok"
            return httpx.Response(200, json={"sub": sub, "name": "Admin"})
        return httpx.Response(404)

    monkeypatch.setattr(
        admin,
        "_client",
        lambda: httpx.AsyncClient(transport=httpx.MockTransport(handler)),
    )


def _login(client, monkeypatch, sub="ding-admin"):
    _mock_oidc(monkeypatch, sub)
    start = client.get("/admin/oidc-login", follow_redirects=False)
    assert start.status_code in (302, 307)
    state = parse_qs(urlparse(start.headers["location"]).query)["state"][0]
    return client.get(f"/admin/oidc-callback?code=abc&state={state}")


def test_admin_routes_are_absent_without_session_secret(tmp_path, monkeypatch):
    monkeypatch.delenv("WAYFAIR_ADMIN_SESSION_SECRET", raising=False)
    app = create_app(_config(), db_path=tmp_path / "wayfair.db")
    with TestClient(app) as client:
        assert client.get("/admin/api/me").status_code == 404


def test_oidc_login_rejects_unknown_state(tmp_path, monkeypatch):
    monkeypatch.setenv("WAYFAIR_ADMIN_SESSION_SECRET", "session-secret")
    app = create_app(_config(), db_path=tmp_path / "wayfair.db")
    with TestClient(app) as client:
        response = client.get("/admin/oidc-callback?code=abc&state=forged")

    assert response.status_code == 400
    assert response.json()["detail"]["code"] == "invalid_state"


def test_non_admin_identity_is_rejected(tmp_path, monkeypatch):
    monkeypatch.setenv("WAYFAIR_ADMIN_SESSION_SECRET", "session-secret")
    app = create_app(_config(), db_path=tmp_path / "wayfair.db")
    with TestClient(app) as client:
        response = _login(client, monkeypatch, sub="someone-else")

    assert response.status_code == 403
    assert response.json()["detail"]["code"] == "forbidden_admin"


def test_admin_can_create_list_and_deactivate_keys(tmp_path, monkeypatch):
    monkeypatch.setenv("WAYFAIR_ADMIN_SESSION_SECRET", "session-secret")
    app = create_app(_config(), db_path=tmp_path / "wayfair.db")
    with TestClient(app) as client:
        login = _login(client, monkeypatch)
        assert login.status_code == 200

        me = client.get("/admin/api/me")
        assert me.status_code == 200
        assert me.json()["identity"] == "ding-admin"

        created = client.post(
            "/admin/api/keys",
            json={
                "name": "forecast",
                "accounts": ["centrade"],
                "operations": ["inventory:snapshot:read"],
            },
        )
        assert created.status_code == 201
        body = created.json()
        assert body["key"].startswith("wf-")
        key_id = body["id"]

        listed = client.get("/admin/api/keys")
        assert listed.status_code == 200
        entry = listed.json()["keys"][0]
        assert entry["id"] == key_id
        assert "key" not in entry
        assert body["key"] not in listed.text

        deactivated = client.post(f"/admin/api/keys/{key_id}/deactivate")
        assert deactivated.status_code == 200

    async def lookup():
        return await app.state.db.lookup_api_key(body["key"])

    with TestClient(app) as client:
        assert client.portal.call(lookup) is None


def test_admin_deactivates_all_keys_for_owner(tmp_path, monkeypatch):
    monkeypatch.setenv("WAYFAIR_ADMIN_SESSION_SECRET", "session-secret")
    app = create_app(_config(), db_path=tmp_path / "wayfair.db")
    payload = {
        "name": "forecast",
        "accounts": ["centrade"],
        "operations": ["inventory:snapshot:read"],
    }
    with TestClient(app) as client:
        _login(client, monkeypatch)
        for owner in ("leaver", "leaver", "stayer"):
            response = client.post(
                "/admin/api/keys",
                json={**payload, "owner": owner},
            )
            assert response.status_code == 201

        result = client.post("/admin/api/owners/leaver/deactivate")
        assert result.status_code == 200
        assert result.json() == {"owner": "leaver", "deactivated": 2}

        keys = client.get("/admin/api/keys").json()["keys"]
        by_owner = {key["owner"]: key["is_active"] for key in keys}

    assert by_owner == {"leaver": False, "stayer": True}


def test_admin_rejects_unknown_account_and_operation(tmp_path, monkeypatch):
    monkeypatch.setenv("WAYFAIR_ADMIN_SESSION_SECRET", "session-secret")
    app = create_app(_config(), db_path=tmp_path / "wayfair.db")
    with TestClient(app) as client:
        _login(client, monkeypatch)

        bad_account = client.post(
            "/admin/api/keys",
            json={
                "name": "x",
                "accounts": ["nope"],
                "operations": ["inventory:snapshot:read"],
            },
        )
        bad_operation = client.post(
            "/admin/api/keys",
            json={
                "name": "x",
                "accounts": ["centrade"],
                "operations": ["inventory:write"],
            },
        )

    assert bad_account.json()["detail"]["code"] == "unknown_account"
    assert bad_operation.json()["detail"]["code"] == "unknown_operation"
