from __future__ import annotations

import sqlite3

import pytest

from auth import authorize
from db import Database


@pytest.mark.anyio
async def test_api_key_is_stored_hash_only_and_returned_once(tmp_path):
    db = Database(tmp_path / "wayfair.db")
    await db.initialize()

    created = await db.create_api_key(
        name="forecast-service",
        accounts=["centrade"],
        operations=["inventory:snapshot:read"],
        rate_limit_rps=2.0,
    )

    assert created.raw_key.startswith("wf-")
    record = await db.lookup_api_key(created.raw_key)
    assert record is not None
    assert record.name == "forecast-service"

    with sqlite3.connect(db.path) as conn:
        columns = {row[1] for row in conn.execute("PRAGMA table_info(api_keys)")}
        stored = conn.execute(
            "SELECT key_hash, key_prefix FROM api_keys WHERE id = ?", (created.id,)
        ).fetchone()

    assert "key_encrypted" not in columns
    assert "raw_key" not in columns
    assert created.raw_key not in stored
    assert len(stored[0]) == 64


@pytest.mark.anyio
async def test_inactive_key_cannot_be_looked_up(tmp_path):
    db = Database(tmp_path / "wayfair.db")
    await db.initialize()
    created = await db.create_api_key(
        name="disabled",
        accounts=["centrade"],
        operations=["inventory:snapshot:read"],
    )

    await db.set_api_key_active(created.id, False)

    assert await db.lookup_api_key(created.raw_key) is None


def test_authorization_requires_account_and_operation():
    key = {
        "accounts": ["centrade"],
        "operations": ["inventory:snapshot:read"],
    }

    authorize(key, "centrade", "inventory:snapshot:read")

    with pytest.raises(PermissionError, match="account"):
        authorize(key, "account-two", "inventory:snapshot:read")
    with pytest.raises(PermissionError, match="operation"):
        authorize(key, "centrade", "inventory:live:read")
