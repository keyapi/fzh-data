from __future__ import annotations


INVENTORY_SNAPSHOT_READ = "inventory:snapshot:read"
INVENTORY_LIVE_READ = "inventory:live:read"
INVENTORY_TRANSACTIONS_READ = "inventory:transactions:read"
INBOUND_READ = "inbound:read"
SNAPSHOT_RUN = "snapshot:run"

ALL_OPERATIONS = frozenset(
    {
        INVENTORY_SNAPSHOT_READ,
        INVENTORY_LIVE_READ,
        INVENTORY_TRANSACTIONS_READ,
        INBOUND_READ,
        SNAPSHOT_RUN,
    }
)
