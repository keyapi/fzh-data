from __future__ import annotations

import hashlib
import hmac
import os
import secrets
import time
from urllib.parse import quote, unquote, urlencode, urlparse

import httpx
from fastapi import APIRouter, HTTPException, Request
from fastapi.responses import HTMLResponse, RedirectResponse
from pydantic import BaseModel, Field

from config import AppConfig
from db import Database
from operations import ALL_OPERATIONS

SESSION_COOKIE = "wayfair_admin_session"
STATE_COOKIE = "wayfair_oidc_state"
SESSION_TTL = 28800
STATE_TTL = 300

_states: dict[str, float] = {}


class KeyCreate(BaseModel):
    name: str = Field(min_length=1, max_length=100)
    owner: str | None = Field(default=None, max_length=200)
    accounts: list[str] = Field(min_length=1)
    operations: list[str] = Field(min_length=1)
    rate_limit_rps: float = Field(default=1.0, gt=0)


def _error(status: int, code: str, message: str) -> HTTPException:
    return HTTPException(status_code=status, detail={"code": code, "message": message})


def _client() -> httpx.AsyncClient:
    return httpx.AsyncClient(timeout=15.0)


def _sign(secret: str, payload: str) -> str:
    return hmac.new(secret.encode(), payload.encode(), hashlib.sha256).hexdigest()[:32]


def make_session(secret: str, identity: str, display_name: str) -> str:
    payload = "|".join(
        [
            str(int(time.time())),
            quote(identity, safe=""),
            quote(display_name, safe=""),
        ]
    )
    return f"{payload}|{_sign(secret, payload)}"


def parse_session(secret: str, token: str) -> dict | None:
    try:
        payload, signature = token.rsplit("|", 1)
        if not hmac.compare_digest(signature, _sign(secret, payload)):
            return None
        timestamp, identity, display_name = payload.split("|", 2)
        if time.time() - int(timestamp) > SESSION_TTL:
            return None
        return {
            "identity": unquote(identity),
            "display_name": unquote(display_name),
        }
    except (ValueError, TypeError):
        return None


def _prune_states() -> None:
    cutoff = time.time() - STATE_TTL
    for state in list(_states):
        if _states[state] < cutoff:
            del _states[state]


def build_admin_router(config: AppConfig, db: Database, session_secret: str) -> APIRouter:
    oidc = config.oidc
    if oidc is None:
        raise ValueError("OIDC configuration is required for the admin router")

    router = APIRouter(prefix="/admin", tags=["admin"])

    def require_admin(request: Request) -> dict:
        token = request.cookies.get(SESSION_COOKIE, "")
        session = parse_session(session_secret, token)
        if session is None:
            raise _error(401, "unauthorized", "Administrator login required")
        if session["identity"] not in oidc.admin_identities:
            raise _error(403, "forbidden_admin", "Administrator access required")
        return session

    def require_same_origin(request: Request) -> None:
        origin = request.headers.get("origin")
        if origin:
            if urlparse(origin).netloc != request.headers.get("host", ""):
                raise _error(403, "forbidden_origin", "Cross-origin admin request rejected")
            return
        if request.headers.get("sec-fetch-site") in ("cross-site", "same-site"):
            raise _error(403, "forbidden_origin", "Cross-origin admin request rejected")

    def client_secret() -> str:
        if oidc.client_secret.startswith("${") and oidc.client_secret.endswith("}"):
            value = os.getenv(oidc.client_secret[2:-1], "")
            if not value:
                raise _error(503, "oidc_not_configured", "OIDC client secret is missing")
            return value
        return oidc.client_secret

    @router.get("/oidc-login")
    async def oidc_login(request: Request):
        _prune_states()
        state = secrets.token_urlsafe(32)
        _states[state] = time.time()
        query = urlencode(
            {
                "client_id": oidc.client_id,
                "redirect_uri": oidc.redirect_uri,
                "response_type": "code",
                "scope": "openid profile",
                "state": state,
            }
        )
        response = RedirectResponse(f"{oidc.issuer.rstrip('/')}/authorize?{query}")
        response.set_cookie(
            STATE_COOKIE,
            state,
            max_age=STATE_TTL,
            httponly=True,
            secure=oidc.cookie_secure,
            samesite="lax",
            path="/admin",
        )
        return response

    @router.get("/oidc-callback")
    async def oidc_callback(request: Request, code: str = "", state: str = ""):
        _prune_states()
        cookie_state = request.cookies.get(STATE_COOKIE, "")
        if (
            not state
            or state not in _states
            or not cookie_state
            or not hmac.compare_digest(state, cookie_state)
        ):
            raise _error(400, "invalid_state", "Invalid or expired OIDC state")
        del _states[state]
        if not code:
            raise _error(400, "invalid_grant", "Missing authorization code")

        try:
            async with _client() as client:
                token_response = await client.post(
                    f"{oidc.issuer.rstrip('/')}/token",
                    data={
                        "grant_type": "authorization_code",
                        "code": code,
                        "client_id": oidc.client_id,
                        "client_secret": client_secret(),
                        "redirect_uri": oidc.redirect_uri,
                    },
                )
                if token_response.status_code != 200:
                    raise _error(502, "upstream_auth_failed", "OIDC token exchange failed")
                access_token = token_response.json().get("access_token", "")
                if not access_token:
                    raise _error(502, "upstream_auth_failed", "OIDC token response was empty")

                user_response = await client.get(
                    f"{oidc.issuer.rstrip('/')}/userinfo",
                    headers={"Authorization": f"Bearer {access_token}"},
                )
                if user_response.status_code != 200:
                    raise _error(502, "upstream_auth_failed", "OIDC userinfo failed")
                user = user_response.json()
        except HTTPException:
            raise
        except httpx.HTTPError:
            raise _error(502, "upstream_unavailable", "OIDC provider is unreachable")
        except ValueError:
            raise _error(502, "upstream_auth_failed", "OIDC provider returned invalid JSON")

        identity = str(user.get("sub", ""))
        if identity not in oidc.admin_identities:
            raise _error(403, "forbidden_admin", "Administrator access required")

        response = HTMLResponse(
            "<!DOCTYPE html><html><head><meta charset=\"UTF-8\">"
            "<title>Signed in</title></head><body>"
            "<p>Signed in. <a href=\"/admin/api/me\">Continue</a></p></body></html>"
        )
        response.set_cookie(
            SESSION_COOKIE,
            make_session(session_secret, identity, str(user.get("name", identity))),
            max_age=SESSION_TTL,
            httponly=True,
            secure=oidc.cookie_secure,
            samesite="lax",
            path="/",
        )
        response.delete_cookie(STATE_COOKIE, path="/admin")
        return response

    @router.post("/logout")
    async def logout(request: Request):
        require_same_origin(request)
        response = HTMLResponse("<p>Signed out.</p>")
        response.delete_cookie(SESSION_COOKIE, path="/")
        return response

    @router.get("/api/me")
    async def me(request: Request):
        session = require_admin(request)
        return {"identity": session["identity"], "name": session["display_name"], "role": "admin"}

    @router.get("/api/keys")
    async def list_keys(request: Request):
        require_admin(request)
        request.state.operation = "admin:keys:list"
        rows = await db.list_api_keys()
        return {
            "keys": [
                {
                    "id": row["id"],
                    "prefix": row["key_prefix"],
                    "name": row["name"],
                    "owner": row["owner"],
                    "accounts": row["accounts"],
                    "operations": row["operations"],
                    "rate_limit_rps": row["rate_limit_rps"],
                    "is_active": row["is_active"],
                    "request_count": row["request_count"],
                    "last_used_at": row["last_used_at"],
                }
                for row in rows
            ]
        }

    @router.post("/api/keys", status_code=201)
    async def create_key(request: Request, payload: KeyCreate):
        require_same_origin(request)
        require_admin(request)
        request.state.operation = "admin:keys:create"
        unknown_accounts = sorted(set(payload.accounts) - set(config.accounts))
        if unknown_accounts:
            raise _error(
                422,
                "unknown_account",
                f"Unknown account(s): {', '.join(unknown_accounts)}",
            )
        unknown_operations = sorted(set(payload.operations) - ALL_OPERATIONS)
        if unknown_operations:
            raise _error(
                422,
                "unknown_operation",
                f"Unknown operation(s): {', '.join(unknown_operations)}",
            )
        created = await db.create_api_key(
            name=payload.name,
            accounts=payload.accounts,
            operations=payload.operations,
            rate_limit_rps=payload.rate_limit_rps,
            owner=payload.owner,
        )
        return {
            "id": created.id,
            "prefix": created.prefix,
            "key": created.raw_key,
            "notice": "The key is shown once and cannot be retrieved again.",
        }

    @router.post("/api/keys/{key_id}/deactivate")
    async def deactivate_key(request: Request, key_id: str):
        require_same_origin(request)
        require_admin(request)
        request.state.operation = "admin:keys:deactivate"
        if not await db.set_api_key_active(key_id, False):
            raise _error(404, "unknown_key", "API key not found")
        return {"id": key_id, "is_active": False}

    @router.post("/api/owners/{owner}/deactivate")
    async def deactivate_owner(request: Request, owner: str):
        require_same_origin(request)
        require_admin(request)
        request.state.operation = "admin:owners:deactivate"
        deactivated = await db.deactivate_keys_by_owner(owner)
        return {"owner": owner, "deactivated": deactivated}

    return router
