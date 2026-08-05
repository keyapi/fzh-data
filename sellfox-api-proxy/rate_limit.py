import asyncio
import time
from collections import defaultdict, deque


class RateLimiter:
    """In-memory sliding window rate limiter. Async-safe, single-process."""

    def __init__(self, default_rps: float = 1.0):
        self._default_rps = default_rps
        self._buckets: dict[str, deque[float]] = defaultdict(deque)
        self._lock = asyncio.Lock()

    async def check(self, key: str, rps: float | None = None) -> tuple[bool, float]:
        """Check and record. Returns (allowed, retry_after_seconds)."""
        limit = rps if rps is not None else self._default_rps
        if limit <= 0:
            return True, 0.0

        async with self._lock:
            now = time.monotonic()
            cutoff = now - 1.0
            bucket = self._buckets[key]

            while bucket and bucket[0] < cutoff:
                bucket.popleft()

            if len(bucket) >= limit:
                retry_after = bucket[0] - cutoff if bucket else 1.0
                return False, max(retry_after, 0.1)

            bucket.append(now)
            return True, 0.0
