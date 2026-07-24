import json
from contextlib import asynccontextmanager

import httpx
from fastapi import FastAPI, HTTPException, Request
from fastapi.responses import JSONResponse

from auth import verify_api_key
from config import settings, app_config
from db import get_db, lookup_key, record_usage as _record_usage
from rate_limit import RateLimiter
from signing import compute_sign
from token_cache import token_cache
from admin import router as admin_router


@asynccontextmanager
async def lifespan(app: FastAPI):
    db = await get_db()

    async def _lookup(raw_key: str):
        return await lookup_key(db, raw_key)

    async def _record(key_id: str):
        await _record_usage(db, key_id)

    app.state.db = db
    app.state.db_lookup = _lookup
    app.state.db_record_usage = _record

    # Per-account global rate limiters
    limiters: dict[str, RateLimiter] = {}
    for aid, acc in app_config.accounts.items():
        limiters[aid] = RateLimiter(default_rps=acc.rate_limit.global_rps)
    app.state.limiters = limiters

    yield
    await db.close()


app = FastAPI(title="sellfox-api-proxy", version="0.4.0", lifespan=lifespan)
app.include_router(admin_router)


@app.get("/health")
async def health():
    reachable = False
    try:
        async with httpx.AsyncClient() as c:
            r = await c.get("https://openapi.sellfox.com/api/oauth/v2/token.json", timeout=5)
            reachable = r.status_code < 500
    except Exception:
        pass
    return {"status": "ok", "sellfox_reachable": reachable}


@app.api_route("/v1/{account}/{path:path}", methods=["POST"])
async def proxy_route(request: Request, account: str, path: str):
    # 1. Verify API key
    key = await verify_api_key(request)

    # 2. Check account access
    if key["account"] != account:
        raise HTTPException(403, f"Key not authorized for account '{account}'")

    # 3. Get account config
    acc = app_config.accounts.get(account)
    if not acc:
        raise HTTPException(404, f"Unknown account: {account}")

    # 4. Per-key rate limit
    limiter = request.app.state.limiters.get(account)
    if limiter is None:
        limiter = RateLimiter(default_rps=acc.rate_limit.global_rps)
        request.app.state.limiters[account] = limiter

    allowed, retry = await limiter.check(key["id"], key["rate_limit_rps"])
    if not allowed:
        raise HTTPException(429, f"Rate limited. Retry after {retry:.1f}s",
                            headers={"Retry-After": str(int(retry) + 1)})

    # 5. Global rate limit (per account)
    allowed, retry = await limiter.check(f"global:{account}", None)
    if not allowed:
        raise HTTPException(429, f"Global rate limited. Retry after {retry:.1f}s",
                            headers={"Retry-After": str(int(retry) + 1)})

    # 6. Get upstream token
    access_token = None
    if acc.auth_type == "oauth2_cc":
        try:
            access_token = await token_cache.get(account)
        except Exception as e:
            raise HTTPException(502, f"Upstream auth failed: {e}")

    # 7. Build upstream request
    url_path = f"/{path}"
    raw_body = await request.body()
    body = json.loads(raw_body) if raw_body else {}

    if acc.signing_type == "sellfox_hmac" and access_token:
        app_id = app_config.resolve_env(acc.credentials.app_id)
        app_secret = app_config.resolve_env(acc.credentials.app_secret)
        query = compute_sign(
            access_token=access_token,
            client_id=app_id,
            client_secret=app_secret,
            url_path=url_path,
        )
    else:
        query = {}

    # 8. Forward to upstream
    headers = {"Content-Type": "application/json"}
    async with httpx.AsyncClient(timeout=60) as client:
        resp = await client.post(
            f"{acc.upstream}{url_path}",
            params=query, json=body, headers=headers,
        )
        data = resp.json()

    # 9. Retry once on token expiry
    if data.get("code") == 40001 and acc.auth_type == "oauth2_cc":
        token_cache._tokens.pop(account, None)
        access_token = await token_cache.get(account)
        app_id = app_config.resolve_env(acc.credentials.app_id)
        app_secret = app_config.resolve_env(acc.credentials.app_secret)
        query = compute_sign(
            access_token=access_token,
            client_id=app_id,
            client_secret=app_secret,
            url_path=url_path,
        )
        async with httpx.AsyncClient(timeout=60) as client:
            resp = await client.post(
                f"{acc.upstream}{url_path}",
                params=query, json=body, headers=headers,
            )
            data = resp.json()

    return JSONResponse(content=data, status_code=resp.status_code)
