"""Tests for SQLite cross-process submit rate gate."""

from __future__ import annotations

import time
from concurrent.futures import ThreadPoolExecutor
from pathlib import Path

from sellfox_shipping.submission_rate_limit import SqliteSubmitRateLimiter


def test_sqlite_rate_limiter_spaces_calls(tmp_path: Path) -> None:
    db = tmp_path / "gate.db"
    limiter = SqliteSubmitRateLimiter(db, min_interval_seconds=0.2)
    t0 = time.monotonic()
    w1 = limiter.wait()
    w2 = limiter.wait()
    elapsed = time.monotonic() - t0
    assert w1 == 0.0
    assert w2 >= 0.15
    assert elapsed >= 0.15


def test_sqlite_rate_limiter_two_instances_share_gate(tmp_path: Path) -> None:
    db = tmp_path / "gate.db"
    a = SqliteSubmitRateLimiter(db, min_interval_seconds=0.25)
    b = SqliteSubmitRateLimiter(db, min_interval_seconds=0.25)
    times: list[float] = []

    def hit(lim: SqliteSubmitRateLimiter) -> None:
        lim.wait()
        times.append(time.monotonic())

    with ThreadPoolExecutor(max_workers=2) as pool:
        f1 = pool.submit(hit, a)
        f2 = pool.submit(hit, b)
        f1.result()
        f2.result()
    times.sort()
    assert times[1] - times[0] >= 0.20
