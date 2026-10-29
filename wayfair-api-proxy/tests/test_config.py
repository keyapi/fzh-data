from __future__ import annotations

import pytest

from config import load_config


def test_loads_three_accounts_with_explicit_capabilities(tmp_path, monkeypatch):
    monkeypatch.setenv("CENTRADE_CLIENT_ID", "client-id")
    monkeypatch.setenv("CENTRADE_CLIENT_SECRET", "client-secret")
    config_path = tmp_path / "config.yaml"
    config_path.write_text(
        """
accounts:
  centrade:
    upstream: https://api.example.test
    credentials:
      client_id: ${CENTRADE_CLIENT_ID}
      client_secret: ${CENTRADE_CLIENT_SECRET}
    capabilities:
      inventory_snapshot: true
      inventory_live: true
      inbound_live: false
  account-two:
    upstream: https://api.example.test
    credentials:
      client_id: ${ACCOUNT_TWO_CLIENT_ID}
      client_secret: ${ACCOUNT_TWO_CLIENT_SECRET}
    capabilities: {}
  account-three:
    upstream: https://api.example.test
    credentials:
      client_id: ${ACCOUNT_THREE_CLIENT_ID}
      client_secret: ${ACCOUNT_THREE_CLIENT_SECRET}
    capabilities: {}
""",
        encoding="utf-8",
    )

    config = load_config(config_path)

    assert set(config.accounts) == {"centrade", "account-two", "account-three"}
    assert config.accounts["centrade"].capabilities.inventory_live is True
    assert config.accounts["centrade"].capabilities.inbound_live is False
    assert config.accounts["account-two"].capabilities.inventory_snapshot is False
    assert config.resolve_secret(config.accounts["centrade"].credentials.client_secret) == "client-secret"


def test_missing_environment_secret_is_rejected(tmp_path, monkeypatch):
    monkeypatch.delenv("MISSING_SECRET", raising=False)
    config_path = tmp_path / "config.yaml"
    config_path.write_text(
        """
accounts:
  centrade:
    upstream: https://api.example.test
    credentials:
      client_id: literal-id
      client_secret: ${MISSING_SECRET}
""",
        encoding="utf-8",
    )

    config = load_config(config_path)

    with pytest.raises(ValueError, match="MISSING_SECRET"):
        config.resolve_secret(config.accounts["centrade"].credentials.client_secret)
