"""Optional DingTalk OIDC login (reuses company OIDC bridge).

Default: disabled. Enable with auth.enabled=true in config.yaml and
SELLFOX_SHIPPING_SESSION_SECRET (+ OIDC_CLIENT_SECRET) in env.

Pattern copied from sellfox-api-proxy/admin.py (JS redirect after callback).
"""

from __future__ import annotations

import hashlib
import hmac
import os
import secrets
import time
from dataclasses import dataclass
from typing import Any
from urllib.parse import quote, unquote

import httpx
from fastapi import APIRouter, HTTPException, Request
from fastapi.responses import HTMLResponse, RedirectResponse

COOKIE_NAME_DEFAULT = "shipping_session"
SESSION_TTL_DEFAULT = 28800


@dataclass(frozen=True)
class OidcSettings:
    enabled: bool
    issuer: str
    client_id: str
    client_secret: str
    redirect_uri: str
    session_secret: str
    cookie_name: str = COOKIE_NAME_DEFAULT
    session_ttl: int = SESSION_TTL_DEFAULT


def load_oidc_settings(config: dict[str, Any]) -> OidcSettings:
    auth = config.get("auth") or {}
    oidc = config.get("oidc") or {}
    enabled = bool(auth.get("enabled", False)) or (
        os.getenv("SELLFOX_SHIPPING_AUTH_ENABLED", "").strip() in ("1", "true", "yes")
    )
    return OidcSettings(
        enabled=enabled,
        issuer=(oidc.get("issuer") or os.getenv("OIDC_ISSUER") or "").rstrip("/"),
        client_id=str(oidc.get("client_id") or os.getenv("OIDC_CLIENT_ID") or ""),
        client_secret=str(
            oidc.get("client_secret") or os.getenv("OIDC_CLIENT_SECRET") or ""
        ),
        redirect_uri=str(
            oidc.get("redirect_uri") or os.getenv("OIDC_REDIRECT_URI") or ""
        ),
        session_secret=str(
            auth.get("session_secret")
            or os.getenv("SELLFOX_SHIPPING_SESSION_SECRET")
            or ""
        ),
        cookie_name=str(auth.get("cookie_name") or COOKIE_NAME_DEFAULT),
        session_ttl=int(auth.get("session_ttl_seconds") or SESSION_TTL_DEFAULT),
    )


def make_session_token(
    identity: str,
    display_name: str,
    *,
    secret: str,
    ttl: int = SESSION_TTL_DEFAULT,
) -> str:
    if not secret:
        raise ValueError("session secret required")
    ts = str(int(time.time()))
    payload = f"{ts}|{identity}|{quote(display_name, safe='')}"
    sig = hmac.new(secret.encode(), payload.encode(), hashlib.sha256).hexdigest()[:32]
    return f"{payload}|{sig}"


def parse_session_token(
    token: str,
    *,
    secret: str,
    ttl: int = SESSION_TTL_DEFAULT,
) -> dict[str, str] | None:
    if not secret or not token:
        return None
    try:
        parts = token.rsplit("|", 1)
        if len(parts) != 2:
            return None
        payload, sig = parts
        expected = hmac.new(
            secret.encode(), payload.encode(), hashlib.sha256
        ).hexdigest()[:32]
        if not hmac.compare_digest(sig, expected):
            return None
        fields = payload.split("|", 2)
        if len(fields) != 3:
            return None
        ts, identity, display_name_encoded = fields
        if time.time() - int(ts) > ttl:
            return None
        return {
            "identity": identity,
            "display_name": unquote(display_name_encoded),
        }
    except Exception:
        return None


_oidc_states: dict[str, float] = {}


def build_oidc_router(settings: OidcSettings) -> APIRouter:
    router = APIRouter(tags=["auth"])

    @router.get("/oidc-login")
    async def oidc_login():
        if not settings.enabled:
            raise HTTPException(404, "OIDC disabled")
        if not settings.issuer or not settings.client_id or not settings.redirect_uri:
            raise HTTPException(500, "OIDC not configured")
        state = secrets.token_urlsafe(32)
        _oidc_states[state] = time.time()
        cutoff = time.time() - 300
        for s in list(_oidc_states):
            if _oidc_states[s] < cutoff:
                del _oidc_states[s]
        params = {
            "client_id": settings.client_id,
            "redirect_uri": settings.redirect_uri,
            "response_type": "code",
            "scope": "openid",
            "state": state,
        }
        qs = "&".join(f"{k}={v}" for k, v in params.items())
        return RedirectResponse(f"{settings.issuer}/authorize?{qs}")

    @router.get("/oidc-callback")
    async def oidc_callback(code: str = "", state: str = ""):
        if not settings.enabled:
            raise HTTPException(404, "OIDC disabled")
        if not state or state not in _oidc_states:
            raise HTTPException(400, "Invalid state")
        del _oidc_states[state]
        if not code:
            raise HTTPException(400, "Missing code")
        async with httpx.AsyncClient() as client:
            r = await client.post(
                f"{settings.issuer}/token",
                data={
                    "grant_type": "authorization_code",
                    "code": code,
                    "client_id": settings.client_id,
                    "client_secret": settings.client_secret,
                    "redirect_uri": settings.redirect_uri,
                },
                timeout=15,
            )
            if r.status_code != 200:
                raise HTTPException(400, f"Token exchange failed: {r.text[:200]}")
            access_token = r.json().get("access_token", "")
            r2 = await client.get(
                f"{settings.issuer}/userinfo",
                headers={"Authorization": f"Bearer {access_token}"},
                timeout=15,
            )
            if r2.status_code != 200:
                raise HTTPException(400, f"Userinfo failed: {r2.text[:200]}")
            user = r2.json()
        identity = str(user.get("sub") or "")
        display_name = str(user.get("name") or identity)
        if not identity:
            raise HTTPException(400, "OIDC user missing sub")
        token = make_session_token(
            identity,
            display_name,
            secret=settings.session_secret,
            ttl=settings.session_ttl,
        )
        redirect_html = (
            '<!DOCTYPE html><html><head><meta charset="UTF-8">'
            '<script>window.location.replace("/packages");</script>'
            "</head><body><p>登录成功，正在跳转...</p></body></html>"
        )
        resp = HTMLResponse(redirect_html)
        resp.set_cookie(
            settings.cookie_name,
            token,
            max_age=settings.session_ttl,
            httponly=True,
            samesite="lax",
            path="/",
        )
        return resp

    @router.post("/logout")
    async def logout():
        resp = HTMLResponse(
            '<!DOCTYPE html><html><body><p>已退出</p>'
            '<a href="/oidc-login">重新登录</a></body></html>'
        )
        resp.delete_cookie(settings.cookie_name, path="/")
        return resp

    return router


PUBLIC_PATH_PREFIXES = (
    "/api/health",
    "/oidc-login",
    "/oidc-callback",
    "/logout",
    "/docs",
    "/openapi.json",
    "/redoc",
)


def current_user(request: Request, settings: OidcSettings) -> dict[str, str] | None:
    if not settings.enabled:
        return {"identity": "anonymous", "display_name": "anonymous"}
    raw = request.cookies.get(settings.cookie_name, "")
    return parse_session_token(
        raw, secret=settings.session_secret, ttl=settings.session_ttl
    )


def require_user(request: Request, settings: OidcSettings) -> dict[str, str]:
    user = current_user(request, settings)
    if user:
        return user
    raise HTTPException(401, "Authentication required")
