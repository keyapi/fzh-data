from __future__ import annotations

import asyncio

import pytest

from oauth_cache import TokenCache


@pytest.mark.anyio
async def test_concurrent_refresh_is_single_flight():
    calls = 0
    release = asyncio.Event()

    async def refresh(account_id: str):
        nonlocal calls
        calls += 1
        await release.wait()
        return f"token-{account_id}", 3600

    cache = TokenCache(refresh, refresh_margin_seconds=300)
    tasks = [asyncio.create_task(cache.get("centrade")) for _ in range(5)]
    await asyncio.sleep(0)
    release.set()

    assert await asyncio.gather(*tasks) == ["token-centrade"] * 5
    assert calls == 1


@pytest.mark.anyio
async def test_invalidate_forces_next_refresh():
    calls = 0

    async def refresh(account_id: str):
        nonlocal calls
        calls += 1
        return f"token-{calls}", 3600

    cache = TokenCache(refresh)

    assert await cache.get("centrade") == "token-1"
    assert await cache.get("centrade") == "token-1"
    cache.invalidate("centrade")
    assert await cache.get("centrade") == "token-2"
