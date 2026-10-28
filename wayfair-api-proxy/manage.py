from __future__ import annotations

import argparse
import asyncio
import os
import sys
from pathlib import Path

from config import load_config
from db import Database
from operations import ALL_OPERATIONS


def _paths(args) -> tuple[Path, Path]:
    config_path = Path(args.config or os.getenv("WAYFAIR_CONFIG", "config.yaml"))
    database_path = Path(args.database or os.getenv("WAYFAIR_DATABASE", "/data/wayfair.db"))
    return config_path, database_path


def _validate(args, config_path: Path) -> None:
    config = load_config(config_path)
    unknown_accounts = sorted(set(args.accounts) - set(config.accounts))
    if unknown_accounts:
        raise SystemExit(f"Unknown account(s): {', '.join(unknown_accounts)}")
    unknown_operations = sorted(set(args.operations) - ALL_OPERATIONS)
    if unknown_operations:
        raise SystemExit(f"Unknown operation(s): {', '.join(unknown_operations)}")


async def _create(args, database_path: Path) -> int:
    db = Database(database_path)
    await db.initialize()
    created = await db.create_api_key(
        name=args.name,
        accounts=args.accounts,
        operations=args.operations,
        rate_limit_rps=args.rate_limit,
        owner=args.owner,
    )
    print(f"id:     {created.id}")
    print(f"prefix: {created.prefix}")
    print(f"key:    {created.raw_key}")
    print()
    print("This key is shown only once. Store it in the caller's secret manager now.")
    return 0


async def _list(args, database_path: Path) -> int:
    db = Database(database_path)
    await db.initialize()
    rows = await db.list_api_keys()
    if not rows:
        print("no api keys")
        return 0
    for row in rows:
        status = "active" if row["is_active"] else "inactive"
        print(
            f"{row['id']}  {row['key_prefix']}  {row['name']}  {status}  "
            f"owner={row['owner'] or '-'}  "
            f"accounts={','.join(row['accounts'])}  "
            f"operations={','.join(row['operations'])}  "
            f"requests={row['request_count']}"
        )
    return 0


async def _set_active(args, database_path: Path, active: bool) -> int:
    db = Database(database_path)
    await db.initialize()
    await db.set_api_key_active(args.id, active)
    print(f"{'activated' if active else 'deactivated'} {args.id}")
    return 0


def main() -> int:
    parser = argparse.ArgumentParser(description="Manage Wayfair API proxy keys")
    parser.add_argument("--config")
    parser.add_argument("--database")
    subparsers = parser.add_subparsers(dest="command", required=True)

    create = subparsers.add_parser("create")
    create.add_argument("--name", required=True)
    create.add_argument("--owner", default=None)
    create.add_argument("--account", dest="accounts", action="append", required=True)
    create.add_argument("--operation", dest="operations", action="append", required=True)
    create.add_argument("--rate-limit", type=float, default=1.0)

    subparsers.add_parser("list")

    for command in ("deactivate", "activate"):
        sub = subparsers.add_parser(command)
        sub.add_argument("--id", required=True)

    args = parser.parse_args()
    config_path, database_path = _paths(args)

    if args.command == "create":
        _validate(args, config_path)
        return asyncio.run(_create(args, database_path))
    if args.command == "list":
        return asyncio.run(_list(args, database_path))
    if args.command == "deactivate":
        return asyncio.run(_set_active(args, database_path, False))
    return asyncio.run(_set_active(args, database_path, True))


if __name__ == "__main__":
    sys.exit(main())
