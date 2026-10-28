from __future__ import annotations

from datetime import datetime, timezone

import pytest

from db import Database


@pytest.mark.anyio
async def test_failed_snapshot_does_not_replace_last_success(tmp_path):
    db = Database(tmp_path / "wayfair.db")
    await db.initialize()

    successful = await db.publish_inventory_snapshot(
        account="centrade",
        started_at=datetime(2026, 10, 28, 8, 0, tzinfo=timezone.utc),
        items=[{"sku": "SKU-1", "warehouse": "CG", "available": 8}],
        upstream_count=1,
    )
    failed = await db.record_failed_snapshot(
        account="centrade",
        started_at=datetime(2026, 10, 28, 9, 0, tzinfo=timezone.utc),
        error_category="upstream_unavailable",
    )

    items, meta = await db.read_inventory("centrade", ["SKU-1"])

    assert failed != successful
    assert items[0]["available"] == 8
    assert meta["run_id"] == successful


@pytest.mark.anyio
async def test_snapshot_report_reconciles_counts(tmp_path):
    db = Database(tmp_path / "wayfair.db")
    await db.initialize()

    run_id = await db.publish_inventory_snapshot(
        account="centrade",
        started_at=datetime(2026, 10, 28, 8, 0, tzinfo=timezone.utc),
        items=[
            {"sku": "SKU-1", "warehouse": "CG", "available": 8},
            {"sku": "SKU-2", "warehouse": "CG", "available": 0},
        ],
        upstream_count=2,
    )

    report = await db.get_snapshot_run(run_id)
    assert report["upstream_count"] == 2
    assert report["written_count"] == 2
    assert report["skipped_count"] == 0
    assert report["failed_count"] == 0
