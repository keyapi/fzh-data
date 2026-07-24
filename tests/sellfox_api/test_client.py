"""Unit tests for SellfoxClient helpers (no live API)."""
from __future__ import annotations

import hashlib
import hmac
from pathlib import Path
import sys

ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT / "SELLFOX_API"))

from client import SellfoxClient, SellfoxConfig  # noqa: E402


def test_sign_string_stable():
    sign_params = {
        "access_token": "tok",
        "client_id": "id",
        "method": "post",
        "nonce": "123",
        "timestamp": "1700000000000",
        "url": "/api/shop/pageList.json",
    }
    sorted_str = "&".join(f"{k}={v}" for k, v in sorted(sign_params.items()))
    sig = hmac.new(b"secret", sorted_str.encode(), hashlib.sha256).hexdigest()
    assert len(sig) == 64
    assert "access_token=tok" in sorted_str
    assert "client_id=id" in sorted_str


def test_config_dataclass():
    cfg = SellfoxConfig(app_id="a", app_secret="b")
    assert cfg.domain == "https://openapi.sellfox.com"
    client = SellfoxClient(cfg)
    assert client.access_token is None
