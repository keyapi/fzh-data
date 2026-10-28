from __future__ import annotations

import asyncio
import time
from dataclasses import dataclass


@dataclass
class _Bucket:
    tokens: float
    updated: float


class RateLimiter:
    """Per-process token bucket. State is not shared across workers."""

    def __init__(self, default_rps: float = 1.0):
        self._default_rps = default_rps
        self._buckets: dict[str, _Bucket] = {}
        self._lock = asyncio.Lock()

    async def check(self, key: str, rps: float | None = None) -> tuple[bool, float]:
        limit = rps if rps is not None else self._default_rps
        if limit <= 0:
            return True, 0.0

        async with self._lock:
            now = time.monotonic()
            capacity = max(1.0, limit)
            bucket = self._buckets.get(key)
            if bucket is None:
                bucket = _Bucket(tokens=capacity, updated=now)
                self._buckets[key] = bucket
            else:
                elapsed = max(now - bucket.updated, 0.0)
                bucket.tokens = min(capacity, bucket.tokens + elapsed * limit)
                bucket.updated = now

            if bucket.tokens >= 1.0:
                bucket.tokens -= 1.0
                return True, 0.0

            return False, (1.0 - bucket.tokens) / limit
