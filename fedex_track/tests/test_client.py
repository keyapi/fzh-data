"""client：sandbox URL、401 清 token 重试、track_many 键规范化。"""

from __future__ import annotations

import httpx
import pytest

from fedex_track.client import (
    DEFAULT_SANDBOX_BASE,
    FedexTrackClient,
    FedexTrackError,
    resolve_base_url,
)
from fedex_track.cli import _base_for, _make_parser, _mock_payload
from fedex_track.models import parse_track_payload

from _payloads import delivered_result, track_payload


def test_resolve_base_sandbox_ignores_prod_fedex_base_url(monkeypatch):
    monkeypatch.setenv("FEDEX_BASE_URL", "https://apis.fedex.com")
    monkeypatch.setenv("FEDEX_ENV", "sandbox")
    monkeypatch.delenv("FEDEX_SANDBOX_BASE_URL", raising=False)
    assert resolve_base_url() == DEFAULT_SANDBOX_BASE.rstrip("/")


def test_cli_env_sandbox_wins_over_fedex_base_url(monkeypatch):
    monkeypatch.setenv("FEDEX_BASE_URL", "https://apis.fedex.com")
    args = _make_parser().parse_args(["query", "--input", "x.txt", "--env", "sandbox"])
    assert _base_for(args) == DEFAULT_SANDBOX_BASE.rstrip("/")


def test_cli_base_url_flag_still_overrides():
    args = _make_parser().parse_args(
        ["query", "--input", "x.txt", "--env", "sandbox", "--base-url", "https://example.test"]
    )
    assert _base_for(args) == "https://example.test"


def test_track_many_401_refreshes_token():
    hits = {"token": 0, "track": 0}

    def handler(request: httpx.Request) -> httpx.Response:
        if request.url.path == "/oauth/token":
            hits["token"] += 1
            return httpx.Response(200, json={"access_token": f"tok-{hits['token']}", "expires_in": 7200})
        if request.url.path == "/track/v1/trackingnumbers":
            hits["track"] += 1
            auth = request.headers.get("authorization")
            if auth == "Bearer tok-1":
                return httpx.Response(401, json={"errors": [{"code": "AUTH.TOKEN.INVALID", "message": "expired"}]})
            n = "382915919064"
            return httpx.Response(200, json=track_payload(n, [delivered_result(n)]))
        return httpx.Response(404, json={})

    client = FedexTrackClient(
        api_key="k", secret_key="s", base_url="https://apis.fedex.com",
        transport=httpx.MockTransport(handler),
    )
    with client:
        out = client.track_many(["382915919064"])
    assert hits["token"] == 2
    assert hits["track"] == 2
    assert out["382915919064"][0].delivered is True


def test_track_many_keys_uppercased_from_api_echo():
    n = "382915919064"

    def handler(request: httpx.Request) -> httpx.Response:
        if request.url.path == "/oauth/token":
            return httpx.Response(200, json={"access_token": "tok", "expires_in": 7200})
        payload = track_payload(n, [delivered_result(n)])
        payload["output"]["completeTrackResults"][0]["trackingNumber"] = n.lower()
        return httpx.Response(200, json=payload)

    client = FedexTrackClient(api_key="k", secret_key="s", transport=httpx.MockTransport(handler))
    with client:
        out = client.track_many([n])
        assert n in out
        client.track(n)  # 键已 upper，不应 KeyError


def test_track_empty_raises_value_error():
    client = FedexTrackClient(api_key="k", secret_key="s", transport=httpx.MockTransport(lambda r: httpx.Response(200)))
    with client:
        with pytest.raises(ValueError):
            client.track("  ")


def test_mock_payload_event_times_increase():
    p = _mock_payload("123")
    ev = p["output"]["completeTrackResults"][0]["trackResults"][0]["scanEvents"]
    times = [e["date"] for e in ev]
    infos = parse_track_payload("123", p)
    dts = [e.dt for e in infos[0].events if e.dt]
    assert dts == sorted(dts)
    assert times[0] < times[1]
