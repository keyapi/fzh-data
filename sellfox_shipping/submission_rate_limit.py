"""Process-local throttle for Sellfox submitToPlatform side effects.

Rate-limit layers (do not confuse):

1. **Official Sellfox OpenAPI** — max ~1 request/second when calling their base URL
   directly. Client interval should be ``>= 1.0`` seconds.
2. **Shared proxy** ``https://api.vilavi.cn/sellfox`` (admin UI under
   ``/sellfox/admin``) — currently throttled around **0.5 rps** so multiple
   operators do not stampede one upstream account. Proxy ops may change this;
   set ``sellfox.submit_min_interval_seconds`` in config.yaml to match
   (default ``2.0`` ≈ 0.5 rps for the proxy path).

This module only enforces the **client-side** interval inside one process.
"""

from __future__ import annotations

import threading
import time


class SubmitRateLimiter:
    """Ensure at least ``min_interval_seconds`` between successive waits.

    Single-process only (matches P1 SQLite single writer). Returns seconds waited.
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
