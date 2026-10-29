from __future__ import annotations

import re
from urllib.parse import parse_qs, urlparse

import httpx
from fastapi.testclient import TestClient

import portal
from config import AccountConfig, AppConfig, Credentials, OIDCConfig
from main import create_app


def _config() -> AppConfig:
    return AppConfig(
        accounts={
            "centrade": AccountConfig(
                upstream="https://api.example.test",
                credentials=Credentials(client_id="id", client_secret="secret"),
            )
        },
        portal_key_cooldown_seconds=0,
        oidc=OIDCConfig(
            issuer="https://oidc.example.test",
            client_id="wayfair",
            client_secret="oidc-secret",
            redirect_uri="http://testserver/admin/oidc-callback",
            admin_identities=[],
            portal_redirect_uri="http://testserver/portal/oidc-callback",
            cookie_secure=False,
        ),
    )


def _mock_oidc(monkeypatch, sub="ding-user"):
    def handler(request: httpx.Request) -> httpx.Response:
        if request.url.path.endswith("/token"):
            return httpx.Response(200, json={"access_token": "tok"})
        if request.url.path.endswith("/userinfo"):
            return httpx.Response(200, json={"sub": sub, "name": "User"})
        return httpx.Response(404)

    monkeypatch.setattr(
        portal,
        "_client",
        lambda: httpx.AsyncClient(transport=httpx.MockTransport(handler)),
    )


def _login(client, monkeypatch, sub="ding-user"):
    _mock_oidc(monkeypatch, sub)
    start = client.get("/portal/oidc-login", follow_redirects=False)
    assert start.status_code in (302, 307)
    state = parse_qs(urlparse(start.headers["location"]).query)["state"][0]
    return client.get(f"/portal/oidc-callback?code=abc&state={state}")


def _csrf(client) -> str:
    client.get("/portal/")
    return client.cookies.get("wayfair_portal_csrf")


def test_portal_is_absent_without_secret(tmp_path, monkeypatch):
    monkeypatch.delenv("WAYFAIR_PORTAL_SESSION_SECRET", raising=False)
    app = create_app(_config(), db_path=tmp_path / "wayfair.db")
    with TestClient(app) as client:
        assert client.get("/portal/").status_code == 404


def test_portal_accepts_any_company_identity(tmp_path, monkeypatch):
    monkeypatch.setenv("WAYFAIR_PORTAL_SESSION_SECRET", "portal-secret")
    app = create_app(_config(), db_path=tmp_path / "wayfair.db")
    with TestClient(app) as client:
        assert _login(client, monkeypatch, sub="any-company-member").status_code == 200
        assert client.get("/portal/").status_code == 200


def test_portal_issue_rotate_and_deactivate(tmp_path, monkeypatch):
    monkeypatch.setenv("WAYFAIR_PORTAL_SESSION_SECRET", "portal-secret")
    app = create_app(_config(), db_path=tmp_path / "wayfair.db")
    with TestClient(app) as client:
        assert _login(client, monkeypatch).status_code == 200
        assert client.get("/portal/").status_code == 200
        csrf = _csrf(client)

        created = client.post("/portal/key/issue", data={"csrf": csrf})
        assert created.status_code == 200
        assert created.headers["cache-control"] == "no-store"
        raw_key = re.search(r"wf-[A-Za-z0-9_-]+", created.text).group(0)

        async def lookup(raw):
            return await app.state.db.lookup_api_key(raw)

        record = client.portal.call(lambda: lookup(raw_key))
        assert record is not None
        assert record.operations == ["inventory:snapshot:read"]

        rotated = client.post("/portal/key/issue", data={"csrf": csrf})
        rotated_key = re.search(r"wf-[A-Za-z0-9_-]+", rotated.text).group(0)
        assert rotated_key != raw_key
        assert client.portal.call(lambda: lookup(raw_key)) is None
        assert client.portal.call(lambda: lookup(rotated_key)) is not None

        listed = client.get("/portal/api/key")
        assert listed.status_code == 200
        assert listed.json()["key"]["prefix"] == rotated_key[:12]
        assert rotated_key not in listed.text

        deactivated = client.post("/portal/key/deactivate", data={"csrf": csrf})
        assert deactivated.status_code == 200
        assert client.portal.call(lambda: lookup(rotated_key)) is None


def test_portal_requires_csrf_and_same_origin(tmp_path, monkeypatch):
    monkeypatch.setenv("WAYFAIR_PORTAL_SESSION_SECRET", "portal-secret")
    app = create_app(_config(), db_path=tmp_path / "wayfair.db")
    with TestClient(app) as client:
        _login(client, monkeypatch)
        missing = client.post("/portal/key/issue", data={})
        assert missing.status_code == 403
        assert missing.json()["detail"]["code"] == "forbidden_csrf"

        csrf = _csrf(client)
        cross = client.post(
            "/portal/key/issue",
            data={"csrf": csrf},
            headers={"Origin": "https://evil.example"},
        )
        assert cross.status_code == 403
        assert cross.json()["detail"]["code"] == "forbidden_origin"


def test_portal_accepts_same_host_with_proxy_scheme_difference(tmp_path, monkeypatch):
    monkeypatch.setenv("WAYFAIR_PORTAL_SESSION_SECRET", "portal-secret")
    app = create_app(_config(), db_path=tmp_path / "wayfair.db")
    with TestClient(app) as client:
        _login(client, monkeypatch)
        csrf = _csrf(client)
        response = client.post(
            "/portal/key/issue",
            data={"csrf": csrf},
            headers={"Origin": "https://testserver"},
        )

    assert response.status_code == 200
    assert "wf-" in response.text


def test_portal_does_not_touch_manual_keys(tmp_path, monkeypatch):
    monkeypatch.setenv("WAYFAIR_PORTAL_SESSION_SECRET", "portal-secret")
    app = create_app(_config(), db_path=tmp_path / "wayfair.db")
    with TestClient(app) as client:
        _login(client, monkeypatch)
        csrf = _csrf(client)
        client.post("/portal/key/issue", data={"csrf": csrf})

        async def create_manual():
            return await app.state.db.create_api_key(
                name="en",
                accounts=["centrade"],
                operations=["inventory:snapshot:read"],
                owner="ding-user",
            )

        manual = client.portal.call(create_manual)
        client.post("/portal/key/deactivate", data={"csrf": csrf})

        async def lookup(raw):
            return await app.state.db.lookup_api_key(raw)

        assert client.portal.call(lambda: lookup(manual.raw_key)) is not None
