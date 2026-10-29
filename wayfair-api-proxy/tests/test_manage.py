from __future__ import annotations

from types import SimpleNamespace

import pytest

from db import Database
from manage import _create, _list, _set_active, _validate


def _config_file(tmp_path):
    path = tmp_path / "config.yaml"
    path.write_text(
        """
accounts:
  centrade:
    upstream: https://api.example.test
    credentials:
      client_id: id
      client_secret: secret
""".strip(),
        encoding="utf-8",
    )
    return path


def _args(**overrides):
    values = {
        "name": "forecast",
        "owner": None,
        "accounts": ["centrade"],
        "operations": ["inventory:snapshot:read"],
        "rate_limit": 1.0,
        "id": "",
    }
    values.update(overrides)
    return SimpleNamespace(**values)


def test_validate_rejects_unknown_account(tmp_path):
    with pytest.raises(SystemExit):
        _validate(_args(accounts=["unknown"]), _config_file(tmp_path))


def test_validate_rejects_unknown_operation(tmp_path):
    with pytest.raises(SystemExit):
        _validate(_args(operations=["inventory:write"]), _config_file(tmp_path))


@pytest.mark.anyio
async def test_created_key_is_listed_and_can_be_deactivated(tmp_path, capsys):
    db_path = tmp_path / "wayfair.db"

    assert await _create(_args(), db_path) == 0
    printed = capsys.readouterr().out
    assert "shown only once" in printed

    rows = await _list(_args(), db_path)
    assert rows == 0

    listed = capsys.readouterr().out
    assert "forecast" in listed
    assert "active" in listed

    key_id = listed.split()[0]
    assert await _set_active(_args(id=key_id), db_path, False) == 0

    db = Database(db_path)
    await db.initialize()
    assert (await db.list_api_keys())[0]["is_active"] is False
    assert await db.lookup_api_key("wf-does-not-exist") is None
