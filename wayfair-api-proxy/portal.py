from __future__ import annotations

import hashlib
import hmac
import html
import os
import secrets
import time
from urllib.parse import parse_qs, quote, unquote, urlencode, urlparse

import httpx
from fastapi import APIRouter, HTTPException, Request
from fastapi.responses import HTMLResponse, JSONResponse, RedirectResponse

from config import AppConfig
from db import Database
from errors import PortalQuotaExceeded
from operations import INVENTORY_SNAPSHOT_READ

SESSION_COOKIE = "wayfair_portal_session"
STATE_COOKIE = "wayfair_portal_state"
CSRF_COOKIE = "wayfair_portal_csrf"
SESSION_TTL = 28800
STATE_TTL = 300
PURPOSE = "portal"

_states: dict[str, float] = {}


def _error(status: int, code: str, message: str) -> HTTPException:
    return HTTPException(status_code=status, detail={"code": code, "message": message})


def _client() -> httpx.AsyncClient:
    return httpx.AsyncClient(timeout=15.0)


def _sign(secret: str, payload: str) -> str:
    return hmac.new(secret.encode(), payload.encode(), hashlib.sha256).hexdigest()[:32]


def make_session(secret: str, identity: str, display_name: str) -> str:
    payload = "|".join(
        [
            PURPOSE,
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
        purpose, timestamp, identity, display_name = payload.split("|", 3)
        if purpose != PURPOSE:
            return None
        if time.time() - int(timestamp) > SESSION_TTL:
            return None
        return {"identity": unquote(identity), "display_name": unquote(display_name)}
    except (ValueError, TypeError):
        return None


def _prune_states() -> None:
    cutoff = time.time() - STATE_TTL
    for state in list(_states):
        if _states[state] < cutoff:
            del _states[state]


def _page(title: str, body: str, *, csrf: str | None = None) -> HTMLResponse:
    token_input = (
        f'<input type="hidden" name="csrf" value="{csrf}">' if csrf else ""
    )
    html = f"""<!DOCTYPE html>
<html lang="zh-CN"><head><meta charset="UTF-8">
<meta name="viewport" content="width=device-width,initial-scale=1">
<title>{title}</title>
<style>
body{{font-family:system-ui,-apple-system,sans-serif;max-width:720px;margin:40px auto;padding:0 16px;line-height:1.6;color:#222}}
code{{background:#f3f3f3;padding:2px 6px;border-radius:4px;word-break:break-all}}
button{{padding:8px 16px;margin:4px 8px 4px 0;border:1px solid #444;background:#fff;border-radius:6px;cursor:pointer}}
.danger{{border-color:#a33;color:#a33}}
.notice{{background:#fff7e6;border:1px solid #f0c36d;padding:10px;border-radius:6px}}
</style></head><body>{body}</body></html>"""
    return HTMLResponse(html)


def build_portal_router(config: AppConfig, db: Database, session_secret: str) -> APIRouter:
    oidc = config.oidc
    if oidc is None or not oidc.portal_redirect_uri:
        raise ValueError("OIDC portal configuration is required")
    router = APIRouter(prefix="/portal", tags=["portal"])

    def client_secret() -> str:
        if oidc.client_secret.startswith("${") and oidc.client_secret.endswith("}"):
            value = os.getenv(oidc.client_secret[2:-1], "")
            if not value:
                raise _error(503, "oidc_not_configured", "OIDC client secret is missing")
            return value
        return oidc.client_secret

    def require_user(request: Request) -> dict:
        session = parse_session(session_secret, request.cookies.get(SESSION_COOKIE, ""))
        if session is None or not session.get("identity"):
            raise _error(401, "unauthorized", "请先使用钉钉登录")
        return session

    def require_same_origin(request: Request) -> None:
        origin = request.headers.get("origin")
        if origin:
            scheme = request.headers.get("x-forwarded-proto", request.url.scheme)
            scheme = scheme.split(",")[0].strip()
            if urlparse(origin).scheme != scheme or urlparse(origin).netloc != request.headers.get("host", ""):
                raise _error(403, "forbidden_origin", "跨源请求被拒绝")
            return
        if request.headers.get("sec-fetch-site") in ("cross-site", "same-site"):
            raise _error(403, "forbidden_origin", "跨源请求被拒绝")

    async def read_form(request: Request) -> dict:
        body = (await request.body()).decode("utf-8", "replace")
        return {key: values[0] for key, values in parse_qs(body).items()}

    def require_csrf(request: Request, form: dict) -> None:
        cookie = request.cookies.get(CSRF_COOKIE, "")
        token = form.get("csrf", "")
        if not cookie or not token or not hmac.compare_digest(cookie, token):
            raise _error(403, "forbidden_csrf", "CSRF 校验失败")

    def csrf_for(request: Request) -> tuple[str, bool]:
        token = request.cookies.get(CSRF_COOKIE, "")
        if token:
            return token, False
        return secrets.token_urlsafe(24), True

    @router.get("", response_class=HTMLResponse)
    @router.get("/", response_class=HTMLResponse)
    async def portal_home(request: Request):
        session = parse_session(session_secret, request.cookies.get(SESSION_COOKIE, ""))
        if session is None:
            return _page(
                "Wayfair API 门户",
                '<h1>Wayfair API 门户</h1>'
                "<p>同事可使用公司钉钉登录，自助领取只读库存 key。</p>"
                '<p><a href="/portal/oidc-login">使用钉钉登录</a></p>',
            )
        key = await db.get_portal_key(session["identity"])
        if key:
            status = (
                f"<p>当前 key：<code>{html.escape(key['key_prefix'])}…</code> "
                f"（创建于 {key['created_at']:.0f}，请求 {key['request_count']} 次）</p>"
            )
        else:
            status = "<p>当前没有 key。</p>"
        csrf, is_new = csrf_for(request)
        csrf_input = f'<input type="hidden" name="csrf" value="{html.escape(csrf)}">'
        body = (
            f"<h1>Wayfair API 门户</h1>"
            f"<p>登录身份：<code>{html.escape(session['display_name'])}</code></p>"
            f"{status}"
            "<p>自助 key 只能读取 <code>inventory:snapshot:read</code>，"
            f"账号固定为 <code>{html.escape(config.portal_account)}</code>。"
            "重建后旧 key 立即失效，明文只显示一次。</p>"
            f'<form method="post" action="/portal/key/issue">{csrf_input}'
            '<button type="submit">领取 / 重建 key</button></form>'
            f'<form method="post" action="/portal/key/deactivate">{csrf_input}'
            '<button type="submit" class="danger">停用我的 key</button></form>'
            f'<form method="post" action="/portal/logout">{csrf_input}'
            '<button type="submit">退出登录</button></form>'
        )
        response = _page("Wayfair API 门户", body)
        if is_new:
            response.set_cookie(
                CSRF_COOKIE,
                csrf,
                max_age=SESSION_TTL,
                httponly=True,
                secure=oidc.cookie_secure,
                samesite="lax",
                path="/portal",
            )
        return response

    @router.get("/oidc-login")
    async def oidc_login():
        _prune_states()
        state = secrets.token_urlsafe(32)
        _states[state] = time.time()
        query = urlencode(
            {
                "client_id": oidc.client_id,
                "redirect_uri": oidc.portal_redirect_uri,
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
            path="/portal",
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
                        "redirect_uri": oidc.portal_redirect_uri,
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
        if not identity:
            raise _error(403, "invalid_identity", "OIDC 未返回用户身份")

        response = RedirectResponse("/portal/", status_code=303)
        response.set_cookie(
            SESSION_COOKIE,
            make_session(session_secret, identity, str(user.get("name", identity))),
            max_age=SESSION_TTL,
            httponly=True,
            secure=oidc.cookie_secure,
            samesite="lax",
            path="/portal",
        )
        response.delete_cookie(STATE_COOKIE, path="/portal")
        return response

    @router.post("/key/issue", response_class=HTMLResponse)
    async def issue_key(request: Request):
        session = require_user(request)
        require_same_origin(request)
        form = await read_form(request)
        require_csrf(request, form)
        request.state.account = config.portal_account
        request.state.operation = "portal:key:issue"
        try:
            created = await db.replace_portal_key(
                owner=session["identity"],
                accounts=[config.portal_account],
                operations=[INVENTORY_SNAPSHOT_READ],
                rate_limit_rps=config.portal_key_rps,
                daily_limit=config.portal_key_daily_limit,
                cooldown_seconds=config.portal_key_cooldown_seconds,
            )
        except PortalQuotaExceeded as exc:
            return _page(
                "Wayfair API 门户",
                f'<p class="notice">暂时不能重建：{exc}</p>'
                '<p><a href="/portal/">返回</a></p>',
            )
        request.state.key_id = created.id
        request.state.result_count = 1
        body = (
            "<h1>Key 已生成</h1>"
            '<p class="notice">明文只显示一次，请立即保存；刷新后无法再次查看。</p>'
            f"<p><code>{html.escape(created.raw_key)}</code></p>"
            f"<p>账号：<code>{config.portal_account}</code>；"
            "权限：<code>inventory:snapshot:read</code></p>"
            '<p><a href="/portal/">返回门户</a></p>'
        )
        response = _page("Key 已生成", body)
        response.headers["Cache-Control"] = "no-store"
        return response

    @router.post("/key/deactivate", response_class=HTMLResponse)
    async def deactivate_key(request: Request):
        session = require_user(request)
        require_same_origin(request)
        form = await read_form(request)
        require_csrf(request, form)
        request.state.account = config.portal_account
        request.state.operation = "portal:key:deactivate"
        count = await db.deactivate_portal_key(session["identity"])
        request.state.result_count = count
        return _page(
            "Wayfair API 门户",
            f"<p>已停用 {count} 个 key。</p><p><a href=\"/portal/\">返回</a></p>",
        )

    @router.get("/api/key")
    async def api_key(request: Request):
        session = require_user(request)
        key = await db.get_portal_key(session["identity"])
        if key is None:
            return JSONResponse({"key": None})
        return JSONResponse(
            {
                "key": {
                    "prefix": key["key_prefix"],
                    "created_at": key["created_at"],
                    "last_used_at": key["last_used_at"],
                    "request_count": key["request_count"],
                    "accounts": key["accounts"],
                    "operations": key["operations"],
                }
            }
        )

    @router.post("/logout")
    async def logout(request: Request):
        require_user(request)
        require_same_origin(request)
        form = await read_form(request)
        require_csrf(request, form)
        response = RedirectResponse("/portal/", status_code=303)
        response.delete_cookie(SESSION_COOKIE, path="/portal")
        return response

    return router
