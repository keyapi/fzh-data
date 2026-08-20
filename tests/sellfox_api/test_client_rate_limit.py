"""Tests for SellfoxClient rate-limit retry (Issue #188)."""
from __future__ import annotations

from pathlib import Path
import sys

import pytest

ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT / "SELLFOX_API"))

from client import (  # noqa: E402
    RateLimitPolicy,
    SellfoxClient,
    SellfoxConfig,
    SELLFOX_RATE_LIMIT_CODE,
    is_rate_limited_response,
    parse_retry_after_seconds,
    rate_limit_sleep_seconds,
)


def test_is_rate_limited_response_proxy_detail():
    assert is_rate_limited_response({"detail": "Rate limited for account"})
    assert not is_rate_limited_response({"code": 0, "data": {}})


def test_is_rate_limited_response_sellfox_40019():
    assert is_rate_limited_response({"code": SELLFOX_RATE_LIMIT_CODE, "msg": "调用超过限制"})
    assert not is_rate_limited_response({"code": 40021, "msg": "permission"})


def test_parse_retry_after_from_detail_and_header():
    assert parse_retry_after_seconds(detail="Rate limited. Retry after 7s") == 7.0
    assert parse_retry_after_seconds(header="12") == 12.0


def test_rate_limit_sleep_prefers_retry_after(monkeypatch):
    policy = RateLimitPolicy(default_wait_s=10.0, jitter_s=0.0)
    monkeypatch.setattr("client.random.uniform", lambda _a, _b: 0.0)
    wait = rate_limit_sleep_seconds(
        {"detail": "Rate limited. Retry after 5s"},
        attempt=0,
        policy=policy,
    )
    assert wait == 5.0


def test_rate_limit_sleep_default_with_jitter(monkeypatch):
    policy = RateLimitPolicy(default_wait_s=10.0, jitter_s=0.5)
    monkeypatch.setattr("client.random.uniform", lambda _a, b: b)
    wait = rate_limit_sleep_seconds({"code": SELLFOX_RATE_LIMIT_CODE}, attempt=0, policy=policy)
    assert wait == 10.5


def test_proxy_retries_sellfox_40019_then_succeeds(monkeypatch):
    calls: list[int] = []

    def fake_once(_self, url_path, body):
        calls.append(1)
        if len(calls) < 3:
            return {"code": SELLFOX_RATE_LIMIT_CODE, "msg": "调用超过限制"}, None
        return {"code": 0, "data": {"rows": []}}, None

    sleeps: list[float] = []
    monkeypatch.setattr("client.time.sleep", lambda s: sleeps.append(s))
    monkeypatch.setattr(SellfoxClient, "_post_once_proxy", fake_once)
    monkeypatch.setattr("client.random.uniform", lambda _a, _b: 0.0)

    client = SellfoxClient(
        SellfoxConfig(mode="proxy", proxy_api_key="sk-test"),
        rate_limit=RateLimitPolicy(max_retries=5, default_wait_s=10.0, jitter_s=0.0),
    )
    data = client.signed_post("/api/commodity/pageList.json", {})
    assert data == {"rows": []}
    assert len(calls) == 3
    assert sleeps == [10.0, 10.0]


def test_proxy_honors_retry_after_header(monkeypatch):
    calls: list[int] = []

    def fake_once(_self, url_path, body):
        calls.append(1)
        if len(calls) == 1:
            return {"detail": "Rate limited"}, "8"
        return {"code": 0, "data": {"ok": True}}, None

    sleeps: list[float] = []
    monkeypatch.setattr("client.time.sleep", lambda s: sleeps.append(s))
    monkeypatch.setattr(SellfoxClient, "_post_once_proxy", fake_once)
    monkeypatch.setattr("client.random.uniform", lambda _a, _b: 0.0)

    client = SellfoxClient(
        SellfoxConfig(mode="proxy", proxy_api_key="sk-test"),
        rate_limit=RateLimitPolicy(max_retries=3, default_wait_s=10.0, jitter_s=0.0),
    )
    assert client.signed_post("/api/x.json", {}) == {"ok": True}
    assert sleeps == [8.0]


def test_non_rate_limit_error_is_not_retried(monkeypatch):
    calls: list[int] = []

    def fake_once(_self, url_path, body):
        calls.append(1)
        return {"code": 40021, "msg": "permission denied"}, None

    monkeypatch.setattr(SellfoxClient, "_post_once_proxy", fake_once)
    client = SellfoxClient(
        SellfoxConfig(mode="proxy", proxy_api_key="sk-test"),
        rate_limit=RateLimitPolicy(max_retries=5, default_wait_s=10.0, jitter_s=0.0),
    )
    with pytest.raises(RuntimeError, match="40021"):
        client.signed_post("/api/commodity/create.json", {"sku": "X"})
    assert len(calls) == 1


def test_rate_limit_retries_exhausted(monkeypatch):
    def fake_once(_self, url_path, body):
        return {"code": SELLFOX_RATE_LIMIT_CODE, "msg": "调用超过限制"}, None

    sleeps: list[float] = []
    monkeypatch.setattr("client.time.sleep", lambda s: sleeps.append(s))
    monkeypatch.setattr(SellfoxClient, "_post_once_proxy", fake_once)
    monkeypatch.setattr("client.random.uniform", lambda _a, _b: 0.0)

    client = SellfoxClient(
        SellfoxConfig(mode="proxy", proxy_api_key="sk-test"),
        rate_limit=RateLimitPolicy(max_retries=2, default_wait_s=1.0, jitter_s=0.0),
    )
    with pytest.raises(RuntimeError, match="Rate limited"):
        client.signed_post("/api/x.json", {})
    assert sleeps == [1.0]


def test_rate_limit_policy_clamps_invalid_values():
    policy = RateLimitPolicy(max_retries=0, default_wait_s=-1.0, jitter_s=-1.0)
    assert policy.max_retries == 6
    assert policy.default_wait_s == 10.0
    assert policy.jitter_s == 0.0


def test_rate_limit_policy_from_env_clamps_invalid(monkeypatch):
    monkeypatch.setenv("SELLFOX_RATE_LIMIT_MAX_RETRIES", "0")
    monkeypatch.setenv("SELLFOX_RATE_LIMIT_WAIT_S", "-1")
    monkeypatch.setenv("SELLFOX_RATE_LIMIT_JITTER_S", "-1")
    policy = RateLimitPolicy.from_env()
    assert policy.max_retries == 6
    assert policy.default_wait_s == 10.0
    assert policy.jitter_s == 0.0


def test_rate_limit_policy_rejects_nan_and_inf():
    policy = RateLimitPolicy(default_wait_s=float("nan"), jitter_s=float("inf"))
    assert policy.default_wait_s == 10.0
    assert policy.jitter_s == 0.0
    policy_neg_inf = RateLimitPolicy(default_wait_s=float("-inf"), jitter_s=float("-inf"))
    assert policy_neg_inf.default_wait_s == 10.0
    assert policy_neg_inf.jitter_s == 0.0


def test_rate_limit_policy_from_env_rejects_nan_and_inf(monkeypatch):
    monkeypatch.setenv("SELLFOX_RATE_LIMIT_WAIT_S", "nan")
    monkeypatch.setenv("SELLFOX_RATE_LIMIT_JITTER_S", "inf")
    policy = RateLimitPolicy.from_env()
    assert policy.default_wait_s == 10.0
    assert policy.jitter_s == 0.0


def test_direct_mode_honors_retry_after_header(monkeypatch):
    calls: list[int] = []

    def fake_once(_self, url_path, body):
        calls.append(1)
        if len(calls) == 1:
            return {"code": SELLFOX_RATE_LIMIT_CODE, "msg": "调用超过限制"}, "6"
        return {"code": 0, "data": {"ok": True}}, None

    sleeps: list[float] = []
    monkeypatch.setattr("client.time.sleep", lambda s: sleeps.append(s))
    monkeypatch.setattr(SellfoxClient, "_post_once_direct", fake_once)
    monkeypatch.setattr("client.random.uniform", lambda _a, _b: 0.0)

    client = SellfoxClient(
        SellfoxConfig(mode="direct", app_id="id", app_secret="secret"),
        rate_limit=RateLimitPolicy(max_retries=3, default_wait_s=10.0, jitter_s=0.0),
    )
    assert client.signed_post("/api/x.json", {}) == {"ok": True}
    assert sleeps == [6.0]
