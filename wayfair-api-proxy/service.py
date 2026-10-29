from __future__ import annotations

from collections.abc import Callable, Mapping
from datetime import datetime, timezone
from typing import Protocol

from config import AccountConfig
from errors import CapabilityUnavailable, SnapshotMissing
from models import (
    InventoryItem,
    InventoryResponse,
    InventoryTransaction,
    ResponseMeta,
    TransactionResponse,
)


class SnapshotStore(Protocol):
    async def read_inventory(self, account: str, skus: list[str]): ...

    async def read_all_inventory(self, account: str): ...


class InventoryService:
    def __init__(
        self,
        *,
        accounts: Mapping[str, AccountConfig],
        snapshot_store: SnapshotStore | None = None,
        live_client=None,
        now: Callable[[], datetime] | None = None,
        stale_after_seconds: int = 90000,
    ):
        self._accounts = accounts
        self._snapshot_store = snapshot_store
        self._live_client = live_client
        self._now = now or (lambda: datetime.now(timezone.utc))
        self._stale_after_seconds = stale_after_seconds

    async def query_inventory(
        self,
        account: str,
        skus: list[str],
        *,
        mode: str,
    ) -> InventoryResponse:
        account_config = self._accounts.get(account)
        if account_config is None:
            raise KeyError(account)

        capability = f"inventory_{mode}"
        if not getattr(account_config.capabilities, capability, False):
            raise CapabilityUnavailable(capability)

        if mode == "snapshot":
            if self._snapshot_store is None:
                raise SnapshotMissing(account)
            items, snapshot = await self._snapshot_store.read_inventory(account, skus)
            if snapshot is None:
                raise SnapshotMissing(account)
            return self._snapshot_response(account, items, snapshot)

        if mode == "live":
            if self._live_client is None:
                raise CapabilityUnavailable(capability)
            items, fetched_at = await self._live_client.query_inventory(account, skus)
            return InventoryResponse(
                items=[InventoryItem.model_validate(item) for item in items],
                meta=ResponseMeta(
                    account=account,
                    source="live",
                    fetched_at=fetched_at,
                    age_seconds=0,
                    stale=False,
                ),
            )

        raise ValueError(f"Unsupported inventory mode: {mode}")

    async def export_snapshot(self, account: str) -> InventoryResponse:
        account_config = self._accounts.get(account)
        if account_config is None:
            raise KeyError(account)
        if not account_config.capabilities.inventory_snapshot:
            raise CapabilityUnavailable("inventory_snapshot")
        if self._snapshot_store is None:
            raise SnapshotMissing(account)
        items, snapshot = await self._snapshot_store.read_all_inventory(account)
        if snapshot is None:
            raise SnapshotMissing(account)
        return self._snapshot_response(account, items, snapshot)

    def _snapshot_response(
        self,
        account: str,
        items: list[dict],
        snapshot: dict,
    ) -> InventoryResponse:
        fetched_at = snapshot["fetched_at"]
        age_seconds = max(int((self._now() - fetched_at).total_seconds()), 0)
        return InventoryResponse(
            items=[InventoryItem.model_validate(item) for item in items],
            meta=ResponseMeta(
                account=account,
                source="snapshot",
                fetched_at=fetched_at,
                age_seconds=age_seconds,
                stale=age_seconds > self._stale_after_seconds,
                snapshot_run_id=snapshot["run_id"],
            ),
        )

    async def query_transactions(
        self,
        account: str,
        *,
        from_date=None,
        to_date=None,
        sku: str | None = None,
    ) -> TransactionResponse:
        account_config = self._accounts.get(account)
        if account_config is None:
            raise KeyError(account)
        if not account_config.capabilities.inventory_transactions:
            raise CapabilityUnavailable("inventory_transactions")
        if self._live_client is None:
            raise CapabilityUnavailable("inventory_transactions")
        items, fetched_at = await self._live_client.query_adjustments(
            account,
            from_date=from_date,
            to_date=to_date,
            sku=sku,
        )
        return TransactionResponse(
            items=[InventoryTransaction.model_validate(item) for item in items],
            meta=ResponseMeta(
                account=account,
                source="live",
                fetched_at=fetched_at,
                age_seconds=0,
                stale=False,
            ),
        )

    async def query_inbound(self, account: str, skus: list[str]):
        account_config = self._accounts.get(account)
        if account_config is None:
            raise KeyError(account)
        if not account_config.capabilities.inbound_live:
            raise CapabilityUnavailable("inbound_live")
        if self._live_client is None:
            raise CapabilityUnavailable("inbound_live")
        return await self._live_client.query_inbound(account, skus)
