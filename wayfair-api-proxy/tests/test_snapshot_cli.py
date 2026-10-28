from __future__ import annotations

import sqlite3
from datetime import datetime, timezone

import pytest

from errors import CapabilityUnavailable, UpstreamForbidden
from snapshot import run_snapshot


def _config(tmp_path, capability: bool):
    path = tmp_path / "config.yaml"
    path.write_text(
        f"""
accounts:
  centrade:
    upstream: https://api.example.test/graphql
    credentials:
      client_id: id
      client_secret: secret
    supplier_id: 80197
    capabilities:
      inventory_snapshot: {str(capability).lower()}
""".strip(),
        encoding="utf-8",
    )
    return path


class FakeClient:
    def __init__(self, items=None, error=None):
        self.items = items or []
        self.error = error

    async def query_inventory(self, account, skus):
        if self.error is not None:
            raise self.error
        return self.items, datetime.now(timezone.utc)


@pytest.mark.anyio
async def test_snapshot_is_blocked_when_capability_disabled(tmp_path):
    db_path = tmp_path / "wayfair.db"

    with pytest.raises(CapabilityUnavailable):
        await run_snapshot("centrade", _config(tmp_path, False), db_path)

    assert not db_path.exists()


@pytest.mark.anyio
async def test_snapshot_publishes_successful_run(tmp_path):
    db_path = tmp_path / "wayfair.db"
    client = FakeClient(
        items=[{"sku": "SKU-1", "warehouse": "CG", "available": 5, "on_hand": 6}]
    )

    assert await run_snapshot("centrade", _config(tmp_path, True), db_path, client) == 0

    with sqlite3.connect(db_path) as connection:
        run = connection.execute(
            "SELECT status, upstream_count, written_count FROM snapshot_runs"
        ).fetchone()
        current = connection.execute("SELECT COUNT(*) FROM current_snapshots").fetchone()

    assert run == ("success", 1, 1)
    assert current[0] == 1


@pytest.mark.anyio
async def test_snapshot_records_failure_without_publishing(tmp_path):
    db_path = tmp_path / "wayfair.db"
    client = FakeClient(error=UpstreamForbidden("not authorized"))

    assert await run_snapshot("centrade", _config(tmp_path, True), db_path, client) == 1

    with sqlite3.connect(db_path) as connection:
        run = connection.execute(
            "SELECT status, error_category FROM snapshot_runs"
        ).fetchone()
        current = connection.execute("SELECT COUNT(*) FROM current_snapshots").fetchone()

    assert run == ("failed", "upstream_forbidden")
    assert current[0] == 0
