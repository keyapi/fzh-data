from __future__ import annotations

import pytest

from rate_limit import RateLimiter


@pytest.mark.anyio
async def test_key_and_account_limits_are_independent():
    limiter = RateLimiter(default_rps=2)

    assert (await limiter.check("key:key-1", 1))[0] is True
    allowed, retry_after = await limiter.check("key:key-1", 1)
    assert allowed is False
    assert retry_after > 0

    assert (await limiter.check("account:centrade", 2))[0] is True
    assert (await limiter.check("account:centrade", 2))[0] is True
    assert (await limiter.check("account:centrade", 2))[0] is False


@pytest.mark.anyio
async def test_fractional_rate_enforces_real_interval(monkeypatch):
    clock = [1000.0]
    monkeypatch.setattr("rate_limit.time.monotonic", lambda: clock[0])
    limiter = RateLimiter()

    assert (await limiter.check("live:centrade", 0.2))[0] is True

    clock[0] += 1.0
    allowed, retry_after = await limiter.check("live:centrade", 0.2)
    assert allowed is False
    assert retry_after == pytest.approx(4.0)

    clock[0] += 3.0
    allowed, retry_after = await limiter.check("live:centrade", 0.2)
    assert allowed is False
    assert retry_after == pytest.approx(1.0)

    clock[0] += 1.0
    assert (await limiter.check("live:centrade", 0.2))[0] is True
