from __future__ import annotations

import logging
import os
import time
import uuid
from contextlib import asynccontextmanager
from pathlib import Path

import httpx
from fastapi import FastAPI, HTTPException, Request
from fastapi.responses import JSONResponse

from auth import authorize
from admin import build_admin_router
from config import AppConfig, load_config
from db import ApiKeyRecord, Database
from errors import CapabilityUnavailable, SnapshotMissing, UpstreamError
from models import InboundQuery, InventoryQuery, TransactionQuery
from portal import build_portal_router
from operations import (
    INBOUND_READ,
    INVENTORY_LIVE_READ,
    INVENTORY_SNAPSHOT_READ,
    INVENTORY_TRANSACTIONS_READ,
    SNAPSHOT_RUN,
)
from rate_limit import RateLimiter
from service import InventoryService
from wayfair_client import WayfairClient

logger = logging.getLogger("wayfair_api_proxy")


def _error(request: Request, status: int, code: str, message: str) -> HTTPException:
    request.state.error_code = code
    return HTTPException(status_code=status, detail={"code": code, "message": message})


async def _verify_api_key(request: Request) -> ApiKeyRecord:
    header = request.headers.get("Authorization", "")
    if not header.startswith("Bearer "):
        raise _error(request, 401, "unauthorized", "Missing Bearer token")
    record = await request.app.state.db.lookup_api_key(header[7:])
    if record is None:
        raise _error(request, 401, "unauthorized", "Invalid or inactive API key")
    request.state.key_id = record.id
    await request.app.state.db.touch_api_key(record.id)
    return record


async def _authorize_route(
    request: Request,
    key: ApiKeyRecord,
    account: str,
    permission: str,
) -> None:
    request.state.account = account
    request.state.operation = permission
    try:
        authorize(
            {"accounts": key.accounts, "operations": key.operations},
            account,
            permission,
        )
    except PermissionError as exc:
        code = "forbidden_account" if "account" in str(exc) else "forbidden_operation"
        raise _error(request, 403, code, str(exc)) from exc


async def _enforce_rate_limits(
    request: Request,
    key: ApiKeyRecord,
    account: str,
    mode: str,
    account_rps: float,
) -> None:
    allowed, retry_after = await request.app.state.limiter.check(
        f"key:{key.id}", key.rate_limit_rps
    )
    if not allowed:
        error = _error(request, 429, "rate_limited", "API key rate limit exceeded")
        error.headers = {"Retry-After": str(max(int(retry_after + 0.999), 1))}
        raise error

    allowed, retry_after = await request.app.state.limiter.check(
        f"account:{account}:{mode}", account_rps
    )
    if not allowed:
        error = _error(request, 429, "rate_limited", "Account rate limit exceeded")
        error.headers = {"Retry-After": str(max(int(retry_after + 0.999), 1))}
        raise error


def create_app(
    config: AppConfig,
    *,
    db_path: str | Path,
    live_client=None,
    upstream_factory=None,
) -> FastAPI:
    db = Database(db_path)

    @asynccontextmanager
    async def lifespan(app: FastAPI):
        await db.initialize()
        app.state.db = db
        app.state.limiter = RateLimiter()
        http_client = None
        active_live = live_client
        if upstream_factory is not None:
            http_client = httpx.AsyncClient(
                timeout=httpx.Timeout(30.0, connect=5.0)
            )
            active_live = upstream_factory(http_client)
        app.state.inventory = InventoryService(
            accounts=config.accounts,
            snapshot_store=db,
            live_client=active_live,
            stale_after_seconds=config.snapshot_stale_after_seconds,
        )
        try:
            yield
        finally:
            if http_client is not None:
                await http_client.aclose()

    app = FastAPI(title="Wayfair API Proxy", lifespan=lifespan)
    app.state.config = config
    app.state.db = db

    admin_session_secret = os.getenv("WAYFAIR_ADMIN_SESSION_SECRET", "")
    if config.oidc is not None and admin_session_secret:
        app.include_router(build_admin_router(config, db, admin_session_secret))
        if not config.oidc.admin_identities:
            logger.warning("OIDC admin is enabled but admin_identities is empty")

    portal_session_secret = os.getenv("WAYFAIR_PORTAL_SESSION_SECRET", "")
    if (
        config.oidc is not None
        and config.oidc.portal_redirect_uri
        and portal_session_secret
        and config.portal_account in config.accounts
    ):
        app.include_router(build_portal_router(config, db, portal_session_secret))
        if not config.oidc.portal_identities:
            logger.warning("Wayfair portal is enabled but portal_identities is empty")
    elif config.oidc is not None and portal_session_secret:
        logger.warning("Wayfair portal is not enabled (missing redirect URI or account)")

    @app.middleware("http")
    async def audit_request(request: Request, call_next):
        request_id = request.headers.get("X-Request-ID") or uuid.uuid4().hex
        started = time.perf_counter()
        response = await call_next(request)
        response.headers["X-Request-ID"] = request_id
        duration_ms = int((time.perf_counter() - started) * 1000)
        log = logger.info if request.url.path.startswith(("/v1/", "/admin/", "/portal/")) else logger.debug
        log(
            "request id=%s method=%s path=%s status=%s duration_ms=%s",
            request_id,
            request.method,
            request.url.path,
            response.status_code,
            duration_ms,
        )
        if request.url.path.startswith(("/v1/", "/admin/", "/portal/")):
            try:
                await request.app.state.db.record_audit(
                    request_id=request_id,
                    key_id=getattr(request.state, "key_id", None),
                    account=getattr(request.state, "account", None),
                    operation=getattr(request.state, "operation", None),
                    status_code=response.status_code,
                    duration_ms=duration_ms,
                    result_count=getattr(request.state, "result_count", None),
                    error_category=getattr(request.state, "error_code", None),
                )
            except Exception:
                logger.exception("failed to write audit event id=%s", request_id)
        return response

    @app.get("/health")
    async def health():
        return {"status": "ok"}

    @app.get("/ready")
    async def ready(request: Request):
        try:
            state = await request.app.state.db.readiness(list(config.accounts))
        except Exception:
            logger.exception("readiness probe failed")
            return JSONResponse(
                status_code=503,
                content={"status": "unavailable", "database": "error", "accounts": {}},
            )
        return {"status": "ready", **state}

    @app.get("/v1/accounts")
    async def list_accounts(request: Request):
        key = await _verify_api_key(request)
        return {
            "accounts": [
                {
                    "id": account_id,
                    "capabilities": account.capabilities.model_dump(),
                }
                for account_id, account in config.accounts.items()
                if account_id in key.accounts
            ]
        }

    @app.post("/v1/accounts/{account}/inventory/query")
    async def query_inventory(account: str, query: InventoryQuery, request: Request):
        if query.mode not in {"snapshot", "live"}:
            raise _error(request, 422, "invalid_mode", "Mode must be snapshot or live")
        key = await _verify_api_key(request)
        permission = (
            INVENTORY_SNAPSHOT_READ
            if query.mode == "snapshot"
            else INVENTORY_LIVE_READ
        )
        await _authorize_route(request, key, account, permission)

        account_config = config.accounts.get(account)
        if account_config is None:
            raise _error(request, 404, "unknown_account", f"Unknown account '{account}'")
        account_rps = (
            account_config.live_rate_limit_rps
            if query.mode == "live"
            else account_config.account_rate_limit_rps
        )
        await _enforce_rate_limits(request, key, account, query.mode, account_rps)

        try:
            result = await request.app.state.inventory.query_inventory(
                account,
                query.skus,
                mode=query.mode,
            )
        except CapabilityUnavailable as exc:
            raise _error(
                request,
                501,
                exc.code,
                f"Capability is unavailable for {account}",
            ) from exc
        except SnapshotMissing as exc:
            raise _error(
                request,
                404,
                exc.code,
                f"No successful snapshot for {account}",
            ) from exc
        except UpstreamError as exc:
            raise _error(
                request,
                exc.status,
                exc.code,
                f"Upstream request failed for {account}",
            ) from exc

        request.state.result_count = len(result.items)
        return result

    @app.get("/v1/accounts/{account}/inventory/snapshot")
    async def export_inventory(account: str, request: Request):
        key = await _verify_api_key(request)
        await _authorize_route(request, key, account, INVENTORY_SNAPSHOT_READ)

        account_config = config.accounts.get(account)
        if account_config is None:
            raise _error(request, 404, "unknown_account", f"Unknown account '{account}'")
        await _enforce_rate_limits(
            request,
            key,
            account,
            "snapshot",
            account_config.account_rate_limit_rps,
        )

        try:
            result = await request.app.state.inventory.export_snapshot(account)
        except CapabilityUnavailable as exc:
            raise _error(
                request,
                501,
                exc.code,
                f"Capability is unavailable for {account}",
            ) from exc
        except SnapshotMissing as exc:
            raise _error(
                request,
                404,
                exc.code,
                f"No successful snapshot for {account}",
            ) from exc

        request.state.result_count = len(result.items)
        return result

    @app.post("/v1/accounts/{account}/inventory/transactions/query")
    async def query_transactions(account: str, query: TransactionQuery, request: Request):
        key = await _verify_api_key(request)
        await _authorize_route(request, key, account, INVENTORY_TRANSACTIONS_READ)

        account_config = config.accounts.get(account)
        if account_config is None:
            raise _error(request, 404, "unknown_account", f"Unknown account '{account}'")
        await _enforce_rate_limits(
            request,
            key,
            account,
            "transactions",
            account_config.live_rate_limit_rps,
        )

        try:
            result = await request.app.state.inventory.query_transactions(
                account,
                from_date=query.from_date,
                to_date=query.to_date,
                sku=query.sku,
            )
        except CapabilityUnavailable as exc:
            raise _error(
                request,
                501,
                exc.code,
                f"Capability is unavailable for {account}",
            ) from exc
        except UpstreamError as exc:
            raise _error(
                request,
                exc.status,
                exc.code,
                f"Upstream request failed for {account}",
            ) from exc

        request.state.result_count = len(result.items)
        return result

    @app.post("/v1/accounts/{account}/inbound/query")
    async def query_inbound(account: str, query: InboundQuery, request: Request):
        key = await _verify_api_key(request)
        await _authorize_route(request, key, account, INBOUND_READ)

        account_config = config.accounts.get(account)
        if account_config is None:
            raise _error(request, 404, "unknown_account", f"Unknown account '{account}'")
        await _enforce_rate_limits(
            request,
            key,
            account,
            "inbound",
            account_config.live_rate_limit_rps,
        )

        try:
            return await request.app.state.inventory.query_inbound(account, query.skus)
        except CapabilityUnavailable as exc:
            raise _error(
                request,
                501,
                exc.code,
                f"Capability is unavailable for {account}",
            ) from exc
        except UpstreamError as exc:
            raise _error(
                request,
                exc.status,
                exc.code,
                f"Upstream request failed for {account}",
            ) from exc

    @app.post("/admin/api/accounts/{account}/snapshot-runs", status_code=202)
    async def trigger_snapshot(account: str, request: Request):
        key = await _verify_api_key(request)
        await _authorize_route(request, key, account, SNAPSHOT_RUN)
        if account not in config.accounts:
            raise _error(request, 404, "unknown_account", f"Unknown account '{account}'")
        raise _error(
            request,
            501,
            "capability_unavailable",
            "Snapshot worker is disabled until the Wayfair contract is verified",
        )

    return app


def create_runtime_app() -> FastAPI:
    config_path = Path(os.getenv("WAYFAIR_CONFIG", "config.yaml"))
    database_path = Path(os.getenv("WAYFAIR_DATABASE", "/data/wayfair.db"))
    config = load_config(config_path)
    return create_app(
        config,
        db_path=database_path,
        upstream_factory=lambda http: WayfairClient(config.accounts, http),
    )
