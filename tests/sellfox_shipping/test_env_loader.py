from __future__ import annotations

import os
from pathlib import Path

from sellfox_shipping.env_loader import load_dotenv


def test_load_dotenv_sets_missing_keys_only(tmp_path, monkeypatch) -> None:
    env_file = tmp_path / ".env"
    env_file.write_text(
        "SELLFOX_PROXY_API_KEY=from-file\nALREADY_SET=from-file\n",
        encoding="utf-8",
    )
    monkeypatch.delenv("SELLFOX_PROXY_API_KEY", raising=False)
    monkeypatch.setenv("ALREADY_SET", "from-env")

    loaded = load_dotenv(env_file)

    assert loaded == env_file
    assert os.environ["SELLFOX_PROXY_API_KEY"] == "from-file"
    assert os.environ["ALREADY_SET"] == "from-env"


def test_load_dotenv_aliases_sellfox_api_key(tmp_path, monkeypatch) -> None:
    env_file = tmp_path / ".env"
    env_file.write_text("SELLFOX_API_KEY=sk-from-admin\n", encoding="utf-8")
    monkeypatch.delenv("SELLFOX_PROXY_API_KEY", raising=False)
    monkeypatch.delenv("SELLFOX_API_KEY", raising=False)

    load_dotenv(env_file)

    assert os.environ["SELLFOX_PROXY_API_KEY"] == "sk-from-admin"
