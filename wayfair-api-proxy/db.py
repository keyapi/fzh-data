from __future__ import annotations

import asyncio
import hashlib
import json
import secrets
import sqlite3
import time
from dataclasses import dataclass
from datetime import datetime, timedelta, timezone
from pathlib import Path


@dataclass(frozen=True)
class CreatedApiKey:
    id: str
    raw_key: str
    prefix: str


@dataclass(frozen=True)
class ApiKeyRecord:
    id: str
    name: str
    prefix: str
    accounts: list[str]
    operations: list[str]
    rate_limit_rps: float


class Database:
    def __init__(self, path: str | Path):
        self.path = Path(path)

    async def initialize(self) -> None:
        await asyncio.to_thread(self._initialize_sync)

    def _connect(self) -> sqlite3.Connection:
        connection = sqlite3.connect(self.path, timeout=5)
        connection.row_factory = sqlite3.Row
        connection.execute("PRAGMA foreign_keys=ON")
        connection.execute("PRAGMA busy_timeout=5000")
        return connection

    def _initialize_sync(self) -> None:
        self.path.parent.mkdir(parents=True, exist_ok=True)
        with self._connect() as connection:
            connection.execute("PRAGMA journal_mode=WAL")
            connection.executescript(
                """
                CREATE TABLE IF NOT EXISTS api_keys (
                    id TEXT PRIMARY KEY,
                    key_hash TEXT NOT NULL UNIQUE,
                    key_prefix TEXT NOT NULL,
                    name TEXT NOT NULL,
                    owner TEXT,
                    accounts TEXT NOT NULL,
                    operations TEXT NOT NULL,
                    rate_limit_rps REAL NOT NULL,
                    is_active INTEGER NOT NULL DEFAULT 1,
                    created_at REAL NOT NULL,
                    last_used_at REAL,
                    request_count INTEGER NOT NULL DEFAULT 0
                );

                CREATE TABLE IF NOT EXISTS snapshot_runs (
                    id TEXT PRIMARY KEY,
                    account TEXT NOT NULL,
                    started_at TEXT NOT NULL,
                    finished_at TEXT,
                    status TEXT NOT NULL,
                    upstream_count INTEGER NOT NULL DEFAULT 0,
                    written_count INTEGER NOT NULL DEFAULT 0,
                    skipped_count INTEGER NOT NULL DEFAULT 0,
                    failed_count INTEGER NOT NULL DEFAULT 0,
                    error_category TEXT
                );

                CREATE TABLE IF NOT EXISTS inventory_positions (
                    account TEXT NOT NULL,
                    sku TEXT NOT NULL,
                    wayfair_sku TEXT,
                    warehouse TEXT NOT NULL,
                    available INTEGER,
                    on_hand INTEGER,
                    reserved INTEGER,
                    unavailable INTEGER,
                    run_id TEXT NOT NULL REFERENCES snapshot_runs(id),
                    fetched_at TEXT NOT NULL,
                    PRIMARY KEY (account, sku, warehouse, run_id)
                );

                CREATE TABLE IF NOT EXISTS current_snapshots (
                    account TEXT PRIMARY KEY,
                    run_id TEXT NOT NULL REFERENCES snapshot_runs(id)
                );

                CREATE TABLE IF NOT EXISTS audit_events (
                    id INTEGER PRIMARY KEY AUTOINCREMENT,
                    created_at REAL NOT NULL,
                    request_id TEXT,
                    key_id TEXT,
                    account TEXT,
                    operation TEXT,
                    status_code INTEGER NOT NULL,
                    duration_ms INTEGER NOT NULL,
                    result_count INTEGER,
                    error_category TEXT
                );

                CREATE INDEX IF NOT EXISTS idx_audit_created
                    ON audit_events (created_at);
                """
            )
            columns = {
                row["name"]
                for row in connection.execute("PRAGMA table_info(api_keys)").fetchall()
            }
            if "owner" not in columns:
                connection.execute("ALTER TABLE api_keys ADD COLUMN owner TEXT")

            position_columns = {
                row["name"]
                for row in connection.execute(
                    "PRAGMA table_info(inventory_positions)"
                ).fetchall()
            }
            if "wayfair_sku" not in position_columns:
                connection.execute(
                    "ALTER TABLE inventory_positions ADD COLUMN wayfair_sku TEXT"
                )

    async def create_api_key(
        self,
        *,
        name: str,
        accounts: list[str],
        operations: list[str],
        rate_limit_rps: float = 1.0,
        owner: str | None = None,
    ) -> CreatedApiKey:
        raw_key = f"wf-{secrets.token_urlsafe(32)}"
        key_id = secrets.token_hex(16)
        prefix = raw_key[:12]
        key_hash = hashlib.sha256(raw_key.encode()).hexdigest()
        await asyncio.to_thread(
            self._insert_key,
            key_id,
            key_hash,
            prefix,
            name,
            owner,
            accounts,
            operations,
            rate_limit_rps,
        )
        return CreatedApiKey(id=key_id, raw_key=raw_key, prefix=prefix)

    def _insert_key(
        self,
        key_id: str,
        key_hash: str,
        prefix: str,
        name: str,
        owner: str | None,
        accounts: list[str],
        operations: list[str],
        rate_limit_rps: float,
    ) -> None:
        with self._connect() as connection:
            connection.execute(
                """
                INSERT INTO api_keys (
                    id, key_hash, key_prefix, name, owner, accounts, operations,
                    rate_limit_rps, created_at
                ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?)
                """,
                (
                    key_id,
                    key_hash,
                    prefix,
                    name,
                    owner,
                    json.dumps(accounts),
                    json.dumps(operations),
                    rate_limit_rps,
                    time.time(),
                ),
            )

    async def lookup_api_key(self, raw_key: str) -> ApiKeyRecord | None:
        key_hash = hashlib.sha256(raw_key.encode()).hexdigest()
        return await asyncio.to_thread(self._lookup_key, key_hash)

    def _lookup_key(self, key_hash: str) -> ApiKeyRecord | None:
        with self._connect() as connection:
            row = connection.execute(
                """
                SELECT id, name, key_prefix, accounts, operations, rate_limit_rps
                FROM api_keys
                WHERE key_hash = ? AND is_active = 1
                """,
                (key_hash,),
            ).fetchone()
        if row is None:
            return None
        return ApiKeyRecord(
            id=row["id"],
            name=row["name"],
            prefix=row["key_prefix"],
            accounts=json.loads(row["accounts"]),
            operations=json.loads(row["operations"]),
            rate_limit_rps=row["rate_limit_rps"],
        )

    async def set_api_key_active(self, key_id: str, active: bool) -> bool:
        return await asyncio.to_thread(self._set_active, key_id, active)

    def _set_active(self, key_id: str, active: bool) -> bool:
        with self._connect() as connection:
            cursor = connection.execute(
                "UPDATE api_keys SET is_active = ? WHERE id = ?",
                (int(active), key_id),
            )
        return cursor.rowcount > 0

    async def list_api_keys(self) -> list[dict]:
        return await asyncio.to_thread(self._list_keys)

    def _list_keys(self) -> list[dict]:
        with self._connect() as connection:
            rows = connection.execute(
                """
                SELECT id, key_prefix, name, owner, accounts, operations,
                       rate_limit_rps, is_active, created_at, last_used_at,
                       request_count
                FROM api_keys
                ORDER BY created_at
                """
            ).fetchall()
        return [
            {
                **dict(row),
                "accounts": json.loads(row["accounts"]),
                "operations": json.loads(row["operations"]),
                "is_active": bool(row["is_active"]),
            }
            for row in rows
        ]

    async def deactivate_keys_by_owner(self, owner: str) -> int:
        return await asyncio.to_thread(self._deactivate_by_owner, owner)

    def _deactivate_by_owner(self, owner: str) -> int:
        with self._connect() as connection:
            cursor = connection.execute(
                "UPDATE api_keys SET is_active = 0 WHERE owner = ? AND is_active = 1",
                (owner,),
            )
        return cursor.rowcount

    async def publish_inventory_snapshot(
        self,
        *,
        account: str,
        started_at: datetime,
        items: list[dict],
        upstream_count: int,
        retention_days: int = 7,
    ) -> str:
        return await asyncio.to_thread(
            self._publish_inventory_snapshot,
            account,
            started_at,
            items,
            upstream_count,
            retention_days,
        )

    def _publish_inventory_snapshot(
        self,
        account: str,
        started_at: datetime,
        items: list[dict],
        upstream_count: int,
        retention_days: int,
    ) -> str:
        run_id = secrets.token_hex(16)
        finished_at = datetime.now(timezone.utc)
        with self._connect() as connection:
            connection.execute("BEGIN IMMEDIATE")
            connection.execute(
                """
                INSERT INTO snapshot_runs (
                    id, account, started_at, finished_at, status,
                    upstream_count, written_count, skipped_count, failed_count
                ) VALUES (?, ?, ?, ?, 'success', ?, ?, 0, 0)
                """,
                (
                    run_id,
                    account,
                    started_at.isoformat(),
                    finished_at.isoformat(),
                    upstream_count,
                    len(items),
                ),
            )
            for item in items:
                connection.execute(
                    """
                    INSERT INTO inventory_positions (
                        account, sku, wayfair_sku, warehouse, available, on_hand,
                        reserved, unavailable, run_id, fetched_at
                    ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
                    """,
                    (
                        account,
                        item["sku"],
                        item.get("wayfair_sku"),
                        item["warehouse"],
                        item.get("available"),
                        item.get("on_hand"),
                        item.get("reserved"),
                        item.get("unavailable"),
                        run_id,
                        finished_at.isoformat(),
                    ),
                )
            connection.execute(
                """
                INSERT INTO current_snapshots (account, run_id) VALUES (?, ?)
                ON CONFLICT(account) DO UPDATE SET run_id = excluded.run_id
                """,
                (account, run_id),
            )
            if retention_days > 0:
                cutoff = (
                    finished_at - timedelta(days=retention_days)
                ).isoformat()
                connection.execute(
                    """
                    DELETE FROM inventory_positions
                    WHERE run_id IN (
                        SELECT id FROM snapshot_runs
                        WHERE account = ? AND finished_at < ?
                          AND id NOT IN (
                              SELECT run_id FROM current_snapshots WHERE account = ?
                          )
                    )
                    """,
                    (account, cutoff, account),
                )
                connection.execute(
                    """
                    DELETE FROM snapshot_runs
                    WHERE account = ? AND finished_at < ?
                      AND id NOT IN (
                          SELECT run_id FROM current_snapshots WHERE account = ?
                      )
                    """,
                    (account, cutoff, account),
                )
        return run_id

    async def record_failed_snapshot(
        self,
        *,
        account: str,
        started_at: datetime,
        error_category: str,
    ) -> str:
        return await asyncio.to_thread(
            self._record_failed_snapshot,
            account,
            started_at,
            error_category,
        )

    def _record_failed_snapshot(
        self,
        account: str,
        started_at: datetime,
        error_category: str,
    ) -> str:
        run_id = secrets.token_hex(16)
        with self._connect() as connection:
            connection.execute(
                """
                INSERT INTO snapshot_runs (
                    id, account, started_at, finished_at, status,
                    failed_count, error_category
                ) VALUES (?, ?, ?, ?, 'failed', 1, ?)
                """,
                (
                    run_id,
                    account,
                    started_at.isoformat(),
                    datetime.now(timezone.utc).isoformat(),
                    error_category,
                ),
            )
        return run_id

    async def read_inventory(self, account: str, skus: list[str]):
        return await asyncio.to_thread(self._read_inventory, account, skus)

    def _read_inventory(self, account: str, skus: list[str]):
        with self._connect() as connection:
            snapshot = connection.execute(
                """
                SELECT r.id, r.finished_at
                FROM current_snapshots c
                JOIN snapshot_runs r ON r.id = c.run_id
                WHERE c.account = ?
                """,
                (account,),
            ).fetchone()
            if snapshot is None:
                return [], None
            placeholders = ",".join("?" for _ in skus)
            rows = connection.execute(
                f"""
                SELECT sku, wayfair_sku, warehouse, available, on_hand, reserved,
                       unavailable
                FROM inventory_positions
                WHERE account = ? AND run_id = ? AND sku IN ({placeholders})
                ORDER BY sku, warehouse
                """,
                (account, snapshot["id"], *skus),
            ).fetchall()
        return (
            [dict(row) for row in rows],
            {
                "run_id": snapshot["id"],
                "fetched_at": datetime.fromisoformat(snapshot["finished_at"]),
            },
        )

    async def touch_api_key(self, key_id: str) -> None:
        await asyncio.to_thread(self._touch_key, key_id)

    def _touch_key(self, key_id: str) -> None:
        with self._connect() as connection:
            connection.execute(
                """
                UPDATE api_keys
                SET last_used_at = ?, request_count = request_count + 1
                WHERE id = ?
                """,
                (time.time(), key_id),
            )

    async def record_audit(
        self,
        *,
        request_id: str | None,
        key_id: str | None,
        account: str | None,
        operation: str | None,
        status_code: int,
        duration_ms: int,
        result_count: int | None = None,
        error_category: str | None = None,
    ) -> None:
        await asyncio.to_thread(
            self._insert_audit,
            request_id,
            key_id,
            account,
            operation,
            status_code,
            duration_ms,
            result_count,
            error_category,
        )

    def _insert_audit(
        self,
        request_id: str | None,
        key_id: str | None,
        account: str | None,
        operation: str | None,
        status_code: int,
        duration_ms: int,
        result_count: int | None,
        error_category: str | None,
    ) -> None:
        with self._connect() as connection:
            connection.execute(
                """
                INSERT INTO audit_events (
                    created_at, request_id, key_id, account, operation,
                    status_code, duration_ms, result_count, error_category
                ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?)
                """,
                (
                    time.time(),
                    request_id,
                    key_id,
                    account,
                    operation,
                    status_code,
                    duration_ms,
                    result_count,
                    error_category,
                ),
            )

    async def readiness(self, accounts: list[str]) -> dict:
        return await asyncio.to_thread(self._readiness, accounts)

    def _readiness(self, accounts: list[str]) -> dict:
        with self._connect() as connection:
            connection.execute("SELECT 1").fetchone()
            result = {}
            for account in accounts:
                row = connection.execute(
                    """
                    SELECT r.finished_at
                    FROM current_snapshots c
                    JOIN snapshot_runs r ON r.id = c.run_id
                    WHERE c.account = ?
                    """,
                    (account,),
                ).fetchone()
                if row is None or row["finished_at"] is None:
                    result[account] = {"has_snapshot": False}
                    continue
                finished_at = datetime.fromisoformat(row["finished_at"])
                age_seconds = max(
                    int((datetime.now(timezone.utc) - finished_at).total_seconds()),
                    0,
                )
                result[account] = {
                    "has_snapshot": True,
                    "last_success_at": finished_at.isoformat(),
                    "age_seconds": age_seconds,
                }
            return {"database": "ok", "accounts": result}

    async def read_all_inventory(self, account: str):
        return await asyncio.to_thread(self._read_all_inventory, account)

    def _read_all_inventory(self, account: str):
        with self._connect() as connection:
            snapshot = connection.execute(
                """
                SELECT r.id, r.finished_at
                FROM current_snapshots c
                JOIN snapshot_runs r ON r.id = c.run_id
                WHERE c.account = ?
                """,
                (account,),
            ).fetchone()
            if snapshot is None:
                return [], None
            rows = connection.execute(
                """
                SELECT sku, wayfair_sku, warehouse, available, on_hand, reserved,
                       unavailable
                FROM inventory_positions
                WHERE account = ? AND run_id = ?
                ORDER BY sku, warehouse
                """,
                (account, snapshot["id"]),
            ).fetchall()
        return (
            [dict(row) for row in rows],
            {
                "run_id": snapshot["id"],
                "fetched_at": datetime.fromisoformat(snapshot["finished_at"]),
            },
        )

    async def get_snapshot_run(self, run_id: str) -> dict | None:
        return await asyncio.to_thread(self._get_snapshot_run, run_id)

    def _get_snapshot_run(self, run_id: str) -> dict | None:
        with self._connect() as connection:
            row = connection.execute(
                "SELECT * FROM snapshot_runs WHERE id = ?", (run_id,)
            ).fetchone()
        return dict(row) if row else None
