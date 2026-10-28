from __future__ import annotations

import argparse
import asyncio
import os
from datetime import datetime, timezone
from pathlib import Path

import httpx

from config import AppConfig, load_config
from db import Database
from errors import CapabilityUnavailable, UpstreamError
from wayfair_client import WayfairClient


def _validate(config: AppConfig, account: str) -> None:
    account_config = config.accounts.get(account)
    if account_config is None:
        raise ValueError(f"Unknown account: {account}")
    if not account_config.capabilities.inventory_snapshot:
        raise CapabilityUnavailable(
            f"inventory_snapshot capability is disabled for {account}"
        )


async def _collect(
    config: AppConfig,
    account: str,
    db: Database,
    client: WayfairClient,
) -> int:
    started_at = datetime.now(timezone.utc)
    try:
        items, fetched_at = await client.query_inventory(account, None)
    except UpstreamError as exc:
        await db.record_failed_snapshot(
            account=account,
            started_at=started_at,
            error_category=exc.code,
        )
        print(f"FAILED: {exc.code}")
        return 1

    run_id = await db.publish_inventory_snapshot(
        account=account,
        started_at=started_at,
        items=items,
        upstream_count=len(items),
        retention_days=config.snapshot_retention_days,
    )
    print(
        f"run={run_id} account={account} fetched_at={fetched_at.isoformat()} "
        f"upstream={len(items)} written={len(items)} skipped=0 failed=0"
    )
    return 0


async def run_snapshot(
    account: str,
    config_path: Path,
    db_path: Path,
    client: WayfairClient | None = None,
) -> int:
    config = load_config(config_path)
    _validate(config, account)

    db = Database(db_path)
    await db.initialize()

    if client is not None:
        return await _collect(config, account, db, client)

    async with httpx.AsyncClient(
        timeout=httpx.Timeout(30.0, connect=5.0)
    ) as http_client:
        return await _collect(
            config,
            account,
            db,
            WayfairClient(config.accounts, http_client),
        )


def main() -> int:
    parser = argparse.ArgumentParser(description="Run one Wayfair inventory snapshot")
    parser.add_argument("--account", required=True)
    parser.add_argument(
        "--config",
        type=Path,
        default=Path(os.getenv("WAYFAIR_CONFIG", "config.yaml")),
    )
    parser.add_argument(
        "--database",
        type=Path,
        default=Path(os.getenv("WAYFAIR_DATABASE", "/data/wayfair.db")),
    )
    args = parser.parse_args()
    try:
        return asyncio.run(run_snapshot(args.account, args.config, args.database))
    except CapabilityUnavailable as exc:
        print(f"BLOCKED: {exc}")
        return 2
    except ValueError as exc:
        print(f"ERROR: {exc}")
        return 2


if __name__ == "__main__":
    raise SystemExit(main())
