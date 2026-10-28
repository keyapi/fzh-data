from __future__ import annotations

from datetime import datetime, timezone

import pytest

from config import AccountConfig, Capabilities, Credentials
from errors import CapabilityUnavailable
from service import InventoryService


def _account(**capabilities: bool) -> AccountConfig:
    return AccountConfig(
        upstream="https://api.example.test",
        credentials=Credentials(client_id="id", client_secret="secret"),
        capabilities=Capabilities(**capabilities),
    )


@pytest.mark.anyio
async def test_unverified_live_capability_is_rejected():
    service = InventoryService(accounts={"centrade": _account(inventory_snapshot=True)})

    with pytest.raises(CapabilityUnavailable) as exc:
        await service.query_inventory("centrade", ["SKU-1"], mode="live")

    assert exc.value.code == "capability_unavailable"


@pytest.mark.anyio
async def test_snapshot_query_returns_freshness_metadata():
    fetched_at = datetime(2026, 10, 28, 8, 0, tzinfo=timezone.utc)

    class Store:
        async def read_inventory(self, account, skus):
            return (
                [{"sku": "SKU-1", "warehouse": "CG", "available": 7}],
                {"run_id": "run-1", "fetched_at": fetched_at},
            )

    service = InventoryService(
        accounts={"centrade": _account(inventory_snapshot=True)},
        snapshot_store=Store(),
        now=lambda: datetime(2026, 10, 28, 8, 5, tzinfo=timezone.utc),
        stale_after_seconds=600,
    )

    response = await service.query_inventory("centrade", ["SKU-1"], mode="snapshot")

    assert response.items[0].available == 7
    assert response.meta.source == "snapshot"
    assert response.meta.age_seconds == 300
    assert response.meta.stale is False
    assert response.meta.snapshot_run_id == "run-1"
