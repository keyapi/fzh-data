import base64
import hashlib
import json
import secrets
import time
import uuid

import aiosqlite

from config import settings


def _derive_bytes(seed: str, length: int) -> bytes:
    result = b""
    i = 0
    while len(result) < length:
        result += hashlib.sha256(f"{seed}:{i}".encode()).digest()
        i += 1
    return result[:length]


def _encrypt(raw: str) -> str:
    data = raw.encode()
    key = _derive_bytes(settings.admin_key, len(data))
    return base64.urlsafe_b64encode(
        bytes(a ^ b for a, b in zip(data, key))
    ).decode()


def _decrypt(enc: str) -> str:
    data = base64.urlsafe_b64decode(enc.encode())
    key = _derive_bytes(settings.admin_key, len(data))
    return bytes(a ^ b for a, b in zip(data, key)).decode()

SCHEMA = """
CREATE TABLE IF NOT EXISTS api_keys (
    id                TEXT PRIMARY KEY,
    key_hash          TEXT NOT NULL UNIQUE,
    key_encrypted     TEXT NOT NULL DEFAULT '',
    key_prefix        TEXT NOT NULL,
    name              TEXT NOT NULL,
    dingtalk_union_id TEXT,
    dingtalk_user_name TEXT,
    account           TEXT NOT NULL DEFAULT '',
    permissions       TEXT NOT NULL DEFAULT '["*"]',
    rate_limit_rps    REAL NOT NULL DEFAULT 1.0,
    is_active         INTEGER NOT NULL DEFAULT 1,
    created_at        REAL NOT NULL,
    last_used_at      REAL,
    request_count     INTEGER NOT NULL DEFAULT 0
);
"""


async def _migrate(db: aiosqlite.Connection):
    cursor = await db.execute("PRAGMA table_info(api_keys)")
    cols = [r[1] for r in await cursor.fetchall()]
    if "account" not in cols:
        await db.execute("ALTER TABLE api_keys ADD COLUMN account TEXT NOT NULL DEFAULT ''")
        await db.execute("UPDATE api_keys SET account = 'sellfox-main' WHERE account = ''")
    if "key_encrypted" not in cols:
        await db.execute("ALTER TABLE api_keys ADD COLUMN key_encrypted TEXT NOT NULL DEFAULT ''")
    await db.commit()


async def get_db() -> aiosqlite.Connection:
    db = await aiosqlite.connect(settings.db_path)
    db.row_factory = aiosqlite.Row
    await db.execute("PRAGMA journal_mode=WAL")
    await db.execute("PRAGMA foreign_keys=ON")
    await db.executescript(SCHEMA)
    await _migrate(db)
    await db.commit()
    return db


async def create_key(
    db: aiosqlite.Connection,
    name: str,
    dingtalk_union_id: str | None = None,
    dingtalk_user_name: str | None = None,
    account: str = "",
    permissions: list[str] | None = None,
    rate_limit_rps: float = 1.0,
) -> str:
    raw_key = f"sk-{secrets.token_urlsafe(32)}"
    key_hash = hashlib.sha256(raw_key.encode()).hexdigest()
    key_encrypted = _encrypt(raw_key)
    key_prefix = raw_key[:10]
    key_id = str(uuid.uuid4())

    await db.execute(
        """INSERT INTO api_keys (id, key_hash, key_encrypted, key_prefix, name,
           dingtalk_union_id, dingtalk_user_name, account, permissions,
           rate_limit_rps, created_at)
           VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)""",
        (key_id, key_hash, key_encrypted, key_prefix, name,
         dingtalk_union_id, dingtalk_user_name, account,
         json.dumps(permissions or ["*"]), rate_limit_rps, time.time()),
    )
    await db.commit()
    return raw_key


async def reveal_key(db: aiosqlite.Connection, key_id: str) -> str | None:
    cursor = await db.execute(
        "SELECT key_encrypted FROM api_keys WHERE id = ?", (key_id,)
    )
    row = await cursor.fetchone()
    if not row or not row[0]:
        return None
    return _decrypt(row[0])


async def lookup_key(db: aiosqlite.Connection, raw_key: str) -> dict | None:
    key_hash = hashlib.sha256(raw_key.encode()).hexdigest()
    cursor = await db.execute(
        "SELECT * FROM api_keys WHERE key_hash = ? AND is_active = 1",
        (key_hash,),
    )
    row = await cursor.fetchone()
    if row is None:
        return None
    record = dict(row)
    record["permissions"] = json.loads(record["permissions"])
    return record


async def get_key_owner(db: aiosqlite.Connection, key_id: str) -> str | None:
    cursor = await db.execute(
        "SELECT dingtalk_union_id FROM api_keys WHERE id = ?", (key_id,)
    )
    row = await cursor.fetchone()
    return row[0] if row else None


async def record_usage(db: aiosqlite.Connection, key_id: str):
    await db.execute(
        "UPDATE api_keys SET last_used_at = ?, request_count = request_count + 1 "
        "WHERE id = ?",
        (time.time(), key_id),
    )
    await db.commit()


async def list_keys(db: aiosqlite.Connection, union_id: str | None = None) -> list[dict]:
    if union_id:
        cursor = await db.execute(
            "SELECT id, key_prefix, name, dingtalk_user_name, account, "
            "permissions, rate_limit_rps, is_active, created_at, "
            "last_used_at, request_count "
            "FROM api_keys WHERE dingtalk_union_id = ? "
            "ORDER BY created_at DESC",
            (union_id,),
        )
    else:
        cursor = await db.execute(
            "SELECT id, key_prefix, name, dingtalk_user_name, account, "
            "permissions, rate_limit_rps, is_active, created_at, "
            "last_used_at, request_count "
            "FROM api_keys ORDER BY created_at DESC"
        )
    rows = await cursor.fetchall()
    result = []
    for row in rows:
        r = dict(row)
        r["permissions"] = json.loads(r["permissions"])
        result.append(r)
    return result


async def get_user_key_count(db: aiosqlite.Connection, union_id: str) -> int:
    cursor = await db.execute(
        "SELECT COUNT(*) FROM api_keys WHERE dingtalk_union_id = ? AND is_active = 1",
        (union_id,),
    )
    row = await cursor.fetchone()
    return row[0] if row else 0


async def toggle_key(db: aiosqlite.Connection, key_id: str) -> bool:
    cursor = await db.execute(
        "UPDATE api_keys SET is_active = CASE WHEN is_active THEN 0 ELSE 1 END "
        "WHERE id = ?",
        (key_id,),
    )
    await db.commit()
    return cursor.rowcount > 0


async def delete_key(db: aiosqlite.Connection, key_id: str) -> bool:
    cursor = await db.execute("DELETE FROM api_keys WHERE id = ?", (key_id,))
    await db.commit()
    return cursor.rowcount > 0


async def disable_keys_by_union_id(db: aiosqlite.Connection, union_id: str) -> int:
    """Disable all active API keys for a DingTalk user. Returns count of disabled keys.

    Called from offboarding flow (admin API or external scripts).
    """
    cursor = await db.execute(
        "UPDATE api_keys SET is_active = 0 "
        "WHERE dingtalk_union_id = ? AND is_active = 1",
        (union_id,),
    )
    await db.commit()
    return cursor.rowcount
