import secrets
import time
from pathlib import Path

import httpx
from fastapi import APIRouter, Form, HTTPException, Request
from fastapi.responses import HTMLResponse, RedirectResponse

from auth import (
    COOKIE_NAME,
    SESSION_TTL,
    make_session_token,
    require_admin,
    verify_user,
)
from config import app_config, settings
from db import (
    create_key as _create_key,
    delete_key as _delete_key,
    get_key_owner,
    get_user_key_count,
    list_keys as _list_keys,
    reveal_key as _reveal_key,
    toggle_key as _toggle_key,
)

router = APIRouter(prefix="/admin", tags=["admin"])

TEMPLATE_DIR = Path(__file__).parent / "admin" / "templates"
STATIC_DIR = Path(__file__).parent / "admin" / "static"

_oidc_states: dict[str, float] = {}


def _read_template(name: str) -> str:
    return (TEMPLATE_DIR / name).read_text(encoding="utf-8")


def _resolve_account(dingtalk_id: str | None) -> str:
    """Determine which account a user gets. Checks overrides then default."""
    if dingtalk_id and dingtalk_id in app_config.account_overrides:
        return app_config.account_overrides[dingtalk_id]
    return app_config.default_account


async def _ensure_user_has_key(db, dingtalk_id: str, dingtalk_name: str) -> str | None:
    """Auto-create a key if user has none. Returns the account used, or None."""
    count = await get_user_key_count(db, dingtalk_id)
    if count > 0:
        return None
    account = _resolve_account(dingtalk_id)
    acc_cfg = app_config.accounts.get(account)
    if not acc_cfg:
        return None
    rps = acc_cfg.rate_limit.default_key_rps
    await _create_key(db, name=f"auto-{dingtalk_name}", dingtalk_union_id=dingtalk_id,
                      dingtalk_user_name=dingtalk_name, account=account, rate_limit_rps=rps)
    return account


# ── OIDC Login ─────────────────────────────────────────────────────

@router.get("/oidc-login")
async def oidc_login():
    oidc = app_config.oidc
    state = secrets.token_urlsafe(32)
    _oidc_states[state] = time.time()
    cutoff = time.time() - 300
    for s in list(_oidc_states):
        if _oidc_states[s] < cutoff:
            del _oidc_states[s]
    params = {
        "client_id": oidc.client_id, "redirect_uri": oidc.redirect_uri,
        "response_type": "code", "scope": "openid", "state": state,
    }
    qs = "&".join(f"{k}={v}" for k, v in params.items())
    return RedirectResponse(f"{oidc.issuer}/authorize?{qs}")


@router.get("/oidc-callback")
async def oidc_callback(request: Request, code: str = "", state: str = ""):
    if not state or state not in _oidc_states:
        raise HTTPException(400, "Invalid state")
    del _oidc_states[state]

    oidc = app_config.oidc
    async with httpx.AsyncClient() as client:
        r = await client.post(f"{oidc.issuer}/token", data={
            "grant_type": "authorization_code", "code": code,
            "client_id": oidc.client_id, "client_secret": oidc.client_secret,
            "redirect_uri": oidc.redirect_uri,
        }, timeout=15)
        if r.status_code != 200:
            raise HTTPException(400, f"Token exchange failed: {r.text}")
        access_token = r.json().get("access_token", "")
    async with httpx.AsyncClient() as client:
        r = await client.get(f"{oidc.issuer}/userinfo",
            headers={"Authorization": f"Bearer {access_token}"}, timeout=15)
        if r.status_code != 200:
            raise HTTPException(400, f"Userinfo failed: {r.text}")
        user = r.json()

    dingtalk_id = user.get("sub", "")
    display_name = user.get("name", dingtalk_id)

    # Auto-provision key for new users
    await _ensure_user_has_key(request.app.state.db, dingtalk_id, display_name)

    token = make_session_token(dingtalk_id, display_name)
    resp = HTMLResponse(_read_template("admin.html"))
    resp.set_cookie(COOKIE_NAME, token, max_age=SESSION_TTL,
                    httponly=True, samesite="lax", path="/")
    return resp


# ── Dev login ──────────────────────────────────────────────────────

@router.get("/dev-login")
async def dev_login(request: Request, name: str = "测试用户", id: str = "test-union-id"):
    if not settings.admin_key:
        raise HTTPException(404)
    await _ensure_user_has_key(request.app.state.db, id, name)
    token = make_session_token(id, name)
    resp = HTMLResponse(_read_template("admin.html"))
    resp.set_cookie(COOKIE_NAME, token, max_age=SESSION_TTL,
                    httponly=True, samesite="lax", path="/")
    return resp


# ── Page routes ────────────────────────────────────────────────────

@router.get("", response_class=HTMLResponse)
@router.get("/", response_class=HTMLResponse)
async def admin_page(request: Request):
    try:
        await verify_user(request)
        return HTMLResponse(_read_template("admin.html"))
    except HTTPException:
        return HTMLResponse(_read_template("login.html"))


@router.post("/login")
async def login(request: Request, password: str = Form(...)):
    import hmac as _hmac
    if not _hmac.compare_digest(password, settings.admin_key):
        html = _read_template("login.html").replace(
            '<div id="error" style="display:none', '<div id="error" style="display:block')
        return HTMLResponse(html)
    token = make_session_token("admin", "admin")
    resp = HTMLResponse(_read_template("admin.html"))
    resp.set_cookie(COOKIE_NAME, token, max_age=SESSION_TTL,
                    httponly=True, samesite="lax", path="/")
    return resp


@router.post("/logout")
async def logout():
    resp = HTMLResponse(_read_template("login.html"))
    resp.delete_cookie(COOKIE_NAME, path="/")
    return resp


@router.get("/static/app.js")
async def admin_js():
    return HTMLResponse(
        (STATIC_DIR / "app.js").read_text(encoding="utf-8"),
        media_type="application/javascript",
    )


# ── API routes ─────────────────────────────────────────────────────

@router.get("/api/me")
async def get_me(request: Request):
    user = await verify_user(request)
    return {"role": user["role"], "name": user["display_name"]}


@router.get("/api/accounts")
async def list_accounts(request: Request):
    """Return accounts visible to current user."""
    user = await verify_user(request)
    result = {}
    if user["role"] == "admin":
        # Admin sees all accounts
        for aid, acc in app_config.accounts.items():
            result[aid] = {
                "name": acc.name,
                "rate_limit_rps": acc.rate_limit.default_key_rps,
            }
    else:
        # User only sees their assigned account
        account_id = _resolve_account(user["identity"])
        acc = app_config.accounts.get(account_id)
        if acc:
            result[account_id] = {
                "name": acc.name,
                "rate_limit_rps": acc.rate_limit.default_key_rps,
            }
    return result


@router.get("/api/keys")
async def list_keys(request: Request):
    user = await verify_user(request)
    db = request.app.state.db
    if user["role"] == "admin":
        keys = await _list_keys(db)
    else:
        keys = await _list_keys(db, union_id=user["identity"])
    return {"keys": keys}


@router.post("/api/keys")
async def create_key(request: Request):
    user = await verify_user(request)
    body = await request.json()

    if user["role"] == "admin":
        account_id = body.get("account", app_config.default_account)
        dingtalk_id = body.get("dingtalk_union_id")
        dingtalk_name = body.get("dingtalk_user_name", "admin")
    else:
        account_id = _resolve_account(user["identity"])
        dingtalk_id = user["identity"]
        dingtalk_name = user["display_name"]

    acc = app_config.accounts.get(account_id)
    if not acc:
        raise HTTPException(400, f"Unknown account: {account_id}")

    rps = body.get("rate_limit_rps", acc.rate_limit.default_key_rps)

    db = request.app.state.db
    raw_key = await _create_key(
        db, name=body.get("name", "unnamed"),
        dingtalk_union_id=dingtalk_id, dingtalk_user_name=dingtalk_name,
        account=account_id, permissions=body.get("permissions"),
        rate_limit_rps=rps,
    )
    return {"key": raw_key, "name": body.get("name"), "account": account_id}


@router.post("/api/keys/{key_id}/toggle")
async def toggle_key(key_id: str, request: Request):
    user = await verify_user(request)
    db = request.app.state.db
    if user["role"] != "admin":
        owner = await get_key_owner(db, key_id)
        if owner != user["identity"]:
            raise HTTPException(403, "Not your key")
    ok = await _toggle_key(db, key_id)
    if not ok:
        raise HTTPException(404, "Key not found")
    return {"ok": True}


@router.delete("/api/keys/{key_id}")
async def delete_key(key_id: str, request: Request):
    user = await verify_user(request)
    db = request.app.state.db
    if user["role"] != "admin":
        owner = await get_key_owner(db, key_id)
        if owner != user["identity"]:
            raise HTTPException(403, "Not your key")
    ok = await _delete_key(db, key_id)
    if not ok:
        raise HTTPException(404, "Key not found")
    return {"ok": True}


@router.post("/api/keys/{key_id}/reveal")
async def reveal_key(key_id: str, request: Request):
    user = await verify_user(request)
    db = request.app.state.db
    if user["role"] != "admin":
        owner = await get_key_owner(db, key_id)
        if owner != user["identity"]:
            raise HTTPException(403, "Not your key")
    raw = await _reveal_key(db, key_id)
    if raw is None:
        raise HTTPException(404, "Key not found or not recoverable")
    return {"key": raw}
