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


def _page(title: str, body: str, *, center: bool = False) -> HTMLResponse:
    wrapper = "login-wrap" if center else "container"
    html = f"""<!DOCTYPE html>
<html lang="zh-CN"><head><meta charset="UTF-8">
<meta name="viewport" content="width=device-width,initial-scale=1">
<title>{title}</title>
<style>
*{{margin:0;padding:0;box-sizing:border-box}}
body{{font-family:-apple-system,BlinkMacSystemFont,'Segoe UI',sans-serif;background:#f5f5f5;color:#333;line-height:1.5}}
.container{{max-width:960px;margin:40px auto;padding:0 20px}}
.login-wrap{{min-height:100vh;display:flex;align-items:center;justify-content:center;padding:20px}}
.card{{background:#fff;border-radius:12px;box-shadow:0 1px 3px rgba(0,0,0,.1);padding:24px}}
.login{{width:400px;max-width:100%;padding:40px;box-shadow:0 4px 20px rgba(0,0,0,.08)}}
.login h1{{font-size:20px;margin-bottom:8px}}
.login p{{color:#777;font-size:13px;margin-bottom:20px}}
.header{{display:flex;justify-content:space-between;align-items:center;gap:12px;margin-bottom:8px}}
.header h1{{font-size:20px}}
.user{{font-size:13px;color:#666;display:flex;align-items:center;gap:8px;margin-bottom:20px}}
.dot{{width:8px;height:8px;border-radius:50%;background:#34a853;display:inline-block}}
.btn{{display:inline-block;padding:8px 16px;border:none;border-radius:6px;cursor:pointer;font-size:14px;text-decoration:none;color:#333;background:#eee}}
.btn:hover{{filter:brightness(.96)}}
.btn-primary{{background:#1a73e8;color:#fff}}
.btn-primary:hover{{background:#1557b0}}
.btn-danger{{background:#dc3545;color:#fff}}
.btn-danger:hover{{background:#b02a37}}
.btn-dingtalk{{display:block;text-align:center;background:#0089FF;color:#fff;padding:11px;border-radius:8px;font-size:15px}}
.btn-dingtalk:hover{{background:#0074d9}}
.btn-sm{{padding:4px 10px;font-size:12px}}
.btn[disabled]{{opacity:.5;cursor:not-allowed}}
.badge{{display:inline-block;padding:2px 8px;border-radius:10px;font-size:11px}}
.badge-active{{background:#e6f4ea;color:#1e8e3e}}
.badge-inactive{{background:#fce8e6;color:#d93025}}
code{{background:#f1f3f4;padding:2px 6px;border-radius:4px;font-size:12px;word-break:break-all}}
.key-card{{margin-top:16px}}
.key-row{{display:flex;justify-content:space-between;gap:16px;align-items:center;flex-wrap:wrap;padding:14px 0;border-top:1px solid #eee}}
.key-meta{{display:flex;gap:24px;flex-wrap:wrap;font-size:13px;color:#666}}
.key-meta b{{color:#333;font-weight:600}}
.actions{{display:flex;gap:8px;flex-wrap:wrap;margin-top:16px}}
.key-box{{background:#f1f8e9;border:1px solid #c8e6c9;border-radius:8px;padding:16px;margin-top:16px}}
.key-box strong{{font-size:13px;color:#2e7d32}}
.key-box code{{display:block;margin:10px 0;padding:10px;background:#fff;font-size:14px}}
.usage{{background:#263238;color:#aed581;border-radius:8px;padding:16px;margin-top:12px;font-family:ui-monospace,Consolas,monospace;font-size:12px;white-space:pre-wrap;overflow-x:auto}}
.notice{{background:#fff7e6;border:1px solid #f0c36d;border-radius:8px;padding:12px;margin-top:16px;font-size:13px}}
.error{{background:#fce8e6;color:#d93025;border-radius:8px;padding:12px;margin-top:16px;font-size:13px}}
.empty{{text-align:center;padding:40px 16px;color:#999}}
.empty h2{{font-size:16px;color:#555;margin-bottom:6px}}
.hint{{color:#999;font-size:12px;margin-top:14px}}
@media(max-width:600px){{.container{{margin:20px auto}}.header{{align-items:flex-start;flex-direction:column}}.key-row{{align-items:flex-start;flex-direction:column}}}}
</style></head><body><div class="{wrapper}">{body}</div></body></html>"""
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
                '<div class="card login">'
                "<h1>Wayfair API 门户</h1>"
                "<p>使用公司钉钉登录，自助领取只读库存 Key。</p>"
                '<a class="btn btn-dingtalk" href="/portal/oidc-login">钉钉登录</a>'
                '<p class="hint">任何公司员工均可登录；自助 Key 仅能读取 CG 库存快照。</p>'
                "</div>",
                center=True,
            )

        key = await db.get_portal_key(session["identity"])
        csrf, is_new = csrf_for(request)
        csrf_input = f'<input type="hidden" name="csrf" value="{html.escape(csrf)}">'
        logout = (
            f'<form method="post" action="/portal/logout">{csrf_input}'
            '<button class="btn btn-sm" type="submit">退出登录</button></form>'
        )
        header = (
            '<div class="header"><h1>Wayfair API 门户</h1>'
            f"{logout}</div>"
            f'<div class="user"><span class="dot"></span>'
            f'{html.escape(session["display_name"])}（钉钉）</div>'
        )

        if key:
            operations = ", ".join(key["operations"])
            card = f"""
<div class="card key-card">
  <div class="key-row">
    <div><b>当前 Key</b> <code>{html.escape(key["key_prefix"])}…</code>
      <span class="badge badge-active">启用</span></div>
    <div class="key-meta">
      <span>账号 <b>{html.escape(config.portal_account)}</b></span>
      <span>权限 <b>{html.escape(operations)}</b></span>
      <span>请求 <b>{key["request_count"]}</b></span>
    </div>
  </div>
  <div class="actions">
    <form method="post" action="/portal/key/issue">{csrf_input}
      <button class="btn btn-primary" type="submit">重建 Key</button></form>
    <form method="post" action="/portal/key/deactivate"
          onsubmit="return confirm('停用后当前 Key 立即失效，确认？')">{csrf_input}
      <button class="btn btn-danger" type="submit">停用 Key</button></form>
  </div>
  <div class="notice">重建会立即停用旧 Key；明文只显示一次，请及时保存。</div>
</div>
<div class="card key-card">
  <b>使用示例</b>
  <div class="usage">curl -X POST https://wayfair-api.vilavi.cn/v1/accounts/{html.escape(config.portal_account)}/inventory/query \\
  -H "Authorization: Bearer &lt;your-key&gt;" \\
  -H "Content-Type: application/json" \\
  -d '{{"skus":["SKU-1"],"mode":"snapshot"}}'</div>
</div>
"""
        else:
            card = f"""
<div class="card empty">
  <h2>还没有 API Key</h2>
  <p>自助 Key 只能读取 <code>inventory:snapshot:read</code>，账号固定为
     <code>{html.escape(config.portal_account)}</code>。</p>
  <form method="post" action="/portal/key/issue" style="margin-top:16px">{csrf_input}
    <button class="btn btn-primary" type="submit">领取 Key</button></form>
</div>
"""
        response = _page("Wayfair API 门户", header + card)
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
                '<div class="card">'
                "<h1>暂时不能重建</h1>"
                f'<div class="notice">{html.escape(str(exc))}</div>'
                '<div class="actions"><a class="btn" href="/portal/">返回门户</a></div>'
                "</div>",
            )
        request.state.key_id = created.id
        request.state.result_count = 1
        body = f"""
<div class="header"><h1>Key 已生成</h1></div>
<div class="card">
  <div class="key-box">
    <strong>明文只显示一次，请立即保存；刷新后无法再次查看。</strong>
    <code id="raw-key">{html.escape(created.raw_key)}</code>
    <button class="btn btn-primary btn-sm" type="button" onclick="copyKey()">复制 Key</button>
  </div>
  <div class="key-meta" style="margin-top:16px">
    <span>账号 <b>{html.escape(config.portal_account)}</b></span>
    <span>权限 <b>{html.escape(INVENTORY_SNAPSHOT_READ)}</b></span>
  </div>
  <div class="usage">curl -X POST https://wayfair-api.vilavi.cn/v1/accounts/{html.escape(config.portal_account)}/inventory/query \\
  -H "Authorization: Bearer &lt;your-key&gt;" \\
  -H "Content-Type: application/json" \\
  -d '{{"skus":["SKU-1"],"mode":"snapshot"}}'</div>
  <div class="actions"><a class="btn" href="/portal/">返回门户</a></div>
</div>
<script>
function copyKey() {{
  const text = document.getElementById("raw-key").textContent;
  const done = () => {{ document.querySelector(".key-box .btn").textContent = "已复制"; }};
  if (navigator.clipboard && navigator.clipboard.writeText) {{
    navigator.clipboard.writeText(text).then(done).catch(fallback);
  }} else {{ fallback(); }}
  function fallback() {{
    const ta = document.createElement("textarea");
    ta.value = text; ta.style.position = "fixed"; ta.style.left = "-9999px";
    document.body.appendChild(ta); ta.select(); document.execCommand("copy");
    document.body.removeChild(ta); done();
  }}
}}
</script>
"""
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
            '<div class="card">'
            f"<h1>Key 已停用</h1><p>共停用 {count} 个 Key。</p>"
            '<div class="actions"><a class="btn btn-primary" href="/portal/">返回门户</a></div>'
            "</div>",
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
