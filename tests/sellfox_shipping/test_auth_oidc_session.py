"""Unit tests for OIDC session token helpers (no live DingTalk)."""

from sellfox_shipping.auth_oidc import make_session_token, parse_session_token


def test_session_token_roundtrip():
    token = make_session_token("u1", "张三", secret="test-secret")
    parsed = parse_session_token(token, secret="test-secret")
    assert parsed == {"identity": "u1", "display_name": "张三"}


def test_session_token_rejects_bad_secret():
    token = make_session_token("u1", "n", secret="a")
    assert parse_session_token(token, secret="b") is None
