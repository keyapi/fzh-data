"""Process-local 1 rps gate for submitToPlatform side effects."""

from __future__ import annotations

import threading
import time


class SubmitRateLimiter:
    """Ensure at least ``min_interval_seconds`` between successive waits.

    Single-process only (matches P1 SQLite single writer). Returns seconds waited.
    """

    def __init__(self, min_interval_seconds: float = 1.0) -> None:
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
