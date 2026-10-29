from __future__ import annotations

import asyncio
import time
from collections.abc import Awaitable, Callable

Refresh = Callable[[str], Awaitable[tuple[str, float]]]


class TokenCache:
    def __init__(self, refresh: Refresh, refresh_margin_seconds: float = 300):
        self._refresh = refresh
        self._refresh_margin_seconds = refresh_margin_seconds
        self._tokens: dict[str, tuple[str, float]] = {}
        self._locks: dict[str, asyncio.Lock] = {}

    async def get(self, account_id: str) -> str:
        cached = self._valid_token(account_id)
        if cached is not None:
            return cached

        lock = self._locks.setdefault(account_id, asyncio.Lock())
        async with lock:
            cached = self._valid_token(account_id)
            if cached is not None:
                return cached
            token, expires_in_seconds = await self._refresh(account_id)
            self._tokens[account_id] = (
                token,
                time.monotonic() + expires_in_seconds,
            )
            return token

    def invalidate(self, account_id: str) -> None:
        self._tokens.pop(account_id, None)

    def _valid_token(self, account_id: str) -> str | None:
        cached = self._tokens.get(account_id)
        if cached is None:
            return None
        token, expires_at = cached
        if time.monotonic() >= expires_at - self._refresh_margin_seconds:
            return None
        return token
