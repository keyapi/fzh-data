"""Process-local and SQLite cross-process throttles for submitToPlatform.

Rate-limit layers (do not confuse):

1. **Official Sellfox OpenAPI** — max ~1 request/second when calling their base URL
   directly. Client interval should be ``>= 1.0`` seconds.
2. **Shared proxy** ``https://api.vilavi.cn/sellfox`` (admin UI under
   ``/sellfox/admin``) — currently throttled around **0.5 rps** so multiple
   operators do not stampede one upstream account. Proxy ops may change this;
   set ``sellfox.submit_min_interval_seconds`` in config.yaml to match
   (default ``2.0`` ≈ 0.5 rps for the proxy path).
3. **This module** — client-side spacing. Use ``SqliteSubmitRateLimiter`` when
   Web + CLI (or multiple workers) share one SQLite DB; process-local alone
   cannot coordinate across processes.
"""

from __future__ import annotations

import sqlite3
import threading
import time
from pathlib import Path
from typing import Protocol


class RateLimiter(Protocol):
    def wait(self) -> float:
        """Block until a slot is available; return seconds slept."""


class SubmitRateLimiter:
    """Ensure at least ``min_interval_seconds`` between successive waits.

    Single-process only. Prefer ``SqliteSubmitRateLimiter`` for multi-process.
    """

    def __init__(self, min_interval_seconds: float = 2.0) -> None:
        self._min_interval = max(0.0, float(min_interval_seconds))
        self._lock = threading.Lock()
        self._last_monotonic: float | None = None

    def wait(self) -> float:
        with self._lock:
            now = time.monotonic()
            waited = 0.0
            if self._last_monotonic is not None and self._min_interval > 0:
                elapsed = now - self._last_monotonic
                if elapsed < self._min_interval:
                    waited = self._min_interval - elapsed
                    time.sleep(waited)
                    now = time.monotonic()
            self._last_monotonic = now
            return waited


class SqliteSubmitRateLimiter:
    """Cross-process gate using a single-row SQLite table + BEGIN IMMEDIATE."""

    def __init__(
        self,
        db_path: str | Path,
        min_interval_seconds: float = 2.0,
    ) -> None:
        self._db_path = str(db_path)
        self._min_interval = max(0.0, float(min_interval_seconds))
        self._ensure_row()

    def _connect(self) -> sqlite3.Connection:
        conn = sqlite3.connect(self._db_path, timeout=30.0)
        conn.execute("PRAGMA busy_timeout=30000")
        return conn

    def _ensure_row(self) -> None:
        with self._connect() as conn:
            conn.execute(
                """
                CREATE TABLE IF NOT EXISTS shipping_submit_rate_gate (
                    id INTEGER PRIMARY KEY,
                    last_submit_unix REAL NOT NULL DEFAULT 0
                )
                """
            )
            conn.execute(
                """
                INSERT OR IGNORE INTO shipping_submit_rate_gate (id, last_submit_unix)
                VALUES (1, 0)
                """
            )
            conn.commit()

    def wait(self) -> float:
        if self._min_interval <= 0:
            return 0.0
        total_waited = 0.0
        while True:
            with self._connect() as conn:
                conn.execute("BEGIN IMMEDIATE")
                row = conn.execute(
                    "SELECT last_submit_unix FROM shipping_submit_rate_gate WHERE id = 1"
                ).fetchone()
                last = float(row[0]) if row else 0.0
                now = time.time()
                elapsed = now - last
                if elapsed >= self._min_interval:
                    conn.execute(
                        "UPDATE shipping_submit_rate_gate SET last_submit_unix = ? WHERE id = 1",
                        (now,),
                    )
                    conn.commit()
                    return total_waited
                need = self._min_interval - elapsed
                conn.rollback()
            time.sleep(need)
            total_waited += need
