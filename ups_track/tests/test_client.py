"""client.py 单测：OAuth token 缓存/刷新、请求头、错误分类（httpx.MockTransport，无网）。"""

from __future__ import annotations

import httpx
import pytest

from ups_track.client import UpsTrackClient, UpsTrackError
from ups_track.models import UpsTrackInfo

from _payloads import delivered_payload, empty_payload

CID = "client-1"
SECRET = "secret-1"


def _client(handler, base_url: str = "https://wwwcie.ups.com") -> UpsTrackClient:
    return UpsTrackClient(
        client_id=CID,
        client_secret=SECRET,
        base_url=base_url,
        transport=httpx.MockTransport(handler),
    )


def _token_handler(token_hits, *, expires_in: int = 14400):
    def handler(request: httpx.Request) -> httpx.Response:
        if request.url.path == "/security/v1/oauth/token":
            token_hits[0] += 1
            assert request.method == "POST"
            assert request.headers["authorization"] == "Basic Y2xpZW50LTE6c2VjcmV0LTE="  # base64(client-1:secret-1)
            body = request.content.decode()
            assert "grant_type=client_credentials" in body
            return httpx.Response(200, json={"access_token": "tok-1", "expires_in": expires_in})
        if request.url.path.startswith("/api/track/v1/details/"):
            number = request.url.path.rsplit("/", 1)[-1]
            assert request.headers["authorization"] == "Bearer tok-1"
            assert "transId" in request.headers
            assert request.headers["transactionsrc"] == "fzh_ups_track"
            return httpx.Response(200, json=delivered_payload(number))
        return httpx.Response(404, json={})
    return handler


def test_token_cached_and_track_ok():
    hits = [0]
    with _client(_token_handler(hits)) as client:
        info1 = client.track("1Z999AA10123456784")
        info2 = client.track("1Z999AA10123456785")
    assert isinstance(info1, UpsTrackInfo)
    assert info1.delivered is True
    assert hits[0] == 1  # token 只取一次


def test_token_refresh_when_expired():
    hits = [0]
    with _client(_token_handler(hits, expires_in=14400)) as client:
        client.track("1Z999AA10123456784")
        # 直接把缓存置为已过期，验证下次请求会重新取 token
        import time
        client._expires_at = time.time() - 1
        client.track("1Z999AA10123456785")
    assert hits[0] == 2


def test_track_empty_payload_returns_not_found():
    hits = [0]
    def handler(request: httpx.Request) -> httpx.Response:
        if request.url.path.startswith("/api/track/v1/details/"):
            return httpx.Response(200, json=empty_payload())
        return httpx.Response(200, json={"access_token": "tok-1", "expires_in": 14400})
    with _client(handler) as client:
        info = client.track("1Z999AA10123456784")
    assert info.not_found is True


@pytest.mark.parametrize(
    "status,code,expect_cat,expect_retry",
    [
        (401, "250002", "auth", False),
        (401, None, "permission", False),
        (429, None, "rate_limit", True),
        (500, None, "transport", True),
        (400, "200000", "not_found", False),
        (400, "991053", "invalid", False),
        (404, None, "invalid", False),
    ],
)
def test_track_error_classification(status, code, expect_cat, expect_retry):
    def handler(request: httpx.Request) -> httpx.Response:
        if request.url.path == "/security/v1/oauth/token":
            return httpx.Response(200, json={"access_token": "tok-1", "expires_in": 14400})
        err = {"response": {"errors": [{"code": code, "message": f"UPS {code or status}"}]}}
        return httpx.Response(status, json=err)
    with _client(handler) as client:
        with pytest.raises(UpsTrackError) as ei:
            client.track("1Z999AA10123456784")
    assert ei.value.category == expect_cat
    assert ei.value.retriable is expect_retry


def test_requires_credentials():
    with pytest.raises(ValueError):
        UpsTrackClient(client_id="", client_secret="", base_url="https://x")
    with pytest.raises(ValueError):
        UpsTrackClient(client_id="a", client_secret="b", proxy="http://p",
                       transport=httpx.MockTransport(lambda r: httpx.Response(200)))
