"""
new-api-dingtalk-oidc: DingTalk OAuth → OIDC Bridge

Exposes standard OIDC endpoints so new-api's Custom OAuth can consume
DingTalk enterprise login without modifying new-api source code.

Usage:
    docker build -t new-api-dingtalk-oidc .
    docker run -p 8086:8086 \
      -e ISSUER=https://your-domain.com/oidc \
      -e DINGTALK_CLIENT_ID=xxx \
      -e DINGTALK_CLIENT_SECRET=xxx \
      -e ALLOWED_CORP_ID=xxx \
      new-api-dingtalk-oidc
"""

import asyncio
import hashlib
import logging
import os
import secrets
import sqlite3
import time
from html import escape
from urllib.parse import urlencode

import httpx
from cryptography.hazmat.primitives import serialization
from cryptography.hazmat.primitives.asymmetric import rsa
from fastapi import FastAPI, Form, HTTPException, Request
from fastapi.responses import HTMLResponse, JSONResponse, RedirectResponse
from contextlib import asynccontextmanager
from jwcrypto import jwk, jwt

logger = logging.getLogger("new-api-dingtalk-oidc")

# ── Config ──────────────────────────────────────────────────────────

ISSUER = os.getenv("ISSUER", "http://localhost:8086").rstrip("/")
DINGTALK_CLIENT_ID = os.getenv("DINGTALK_CLIENT_ID", "")
DINGTALK_CLIENT_SECRET = os.getenv("DINGTALK_CLIENT_SECRET", "")
ALLOWED_CORP_ID = os.getenv("ALLOWED_CORP_ID", "")  # restrict to one corp
# 登录闸门：只放本公司钉钉组织的成员。默认开启，出问题时可临时设 0 关掉（只做日志）。
REQUIRE_COMPANY_MEMBER = os.getenv("REQUIRE_COMPANY_MEMBER", "1").strip().lower() not in (
    "0", "false", "no", "off"
)
BIND_HOST = os.getenv("BIND_HOST", "0.0.0.0")
BIND_PORT = int(os.getenv("BIND_PORT", "8086"))
DB_PATH = os.getenv("DB_PATH", "/data/new-api-dingtalk-oidc.db")
KEY_PATH = os.getenv("KEY_PATH", "/data/oidc-key.pem")

REDIRECT_URI = f"{ISSUER}/callback"

# ── RSA Key (persisted) ─────────────────────────────────────────────

def _load_or_generate_key():
    if os.path.exists(KEY_PATH):
        with open(KEY_PATH, "rb") as f:
            return serialization.load_pem_private_key(f.read(), password=None)
    key = rsa.generate_private_key(public_exponent=65537, key_size=2048)
    os.makedirs(os.path.dirname(KEY_PATH), exist_ok=True)
    with open(KEY_PATH, "wb") as f:
        f.write(key.private_bytes(
            encoding=serialization.Encoding.PEM,
            format=serialization.PrivateFormat.PKCS8,
            encryption_algorithm=serialization.NoEncryption(),
        ))
    return key

_PRIVATE_KEY = _load_or_generate_key()
_PRIVATE_KEY_PEM = _PRIVATE_KEY.private_bytes(
    encoding=serialization.Encoding.PEM,
    format=serialization.PrivateFormat.PKCS8,
    encryption_algorithm=serialization.NoEncryption(),
).decode()
_PUBLIC_KEY_PEM = _PRIVATE_KEY.public_key().public_bytes(
    encoding=serialization.Encoding.PEM,
    format=serialization.PublicFormat.SubjectPublicKeyInfo,
).decode()

_jwk_key = jwk.JWK.from_pem(_PRIVATE_KEY_PEM.encode())
_KEY_ID = hashlib.sha256(_PUBLIC_KEY_PEM.encode()).hexdigest()[:16]
_jwk_key["kid"] = _KEY_ID
_jwk_key["alg"] = "RS256"
_jwk_key["use"] = "sig"

# ── SQLite ───────────────────────────────────────────────────────────

os.makedirs(os.path.dirname(DB_PATH), exist_ok=True)
_db = sqlite3.connect(DB_PATH, check_same_thread=False)
_db.execute("""
    CREATE TABLE IF NOT EXISTS sessions (
        state TEXT PRIMARY KEY,
        original_state TEXT,
        nonce TEXT,
        redirect_uri TEXT,
        created_at INTEGER
    )
""")
_db.execute("""
    CREATE TABLE IF NOT EXISTS auth_codes (
        code TEXT PRIMARY KEY,
        user_id TEXT,
        user_name TEXT,
        email TEXT,
        avatar TEXT,
        nonce TEXT,
        created_at INTEGER
    )
""")
_db.execute("""
    CREATE TABLE IF NOT EXISTS access_tokens (
        token TEXT PRIMARY KEY,
        user_id TEXT,
        user_name TEXT,
        email TEXT,
        avatar TEXT,
        created_at INTEGER
    )
""")
_db.commit()

# ── FastAPI app ──────────────────────────────────────────────────────

@asynccontextmanager
async def lifespan(app: FastAPI):
    """Start background services on app startup."""
    import stream_listener
    stream_listener.start_stream_listener()
    yield

app = FastAPI(title="new-api-dingtalk-oidc", version="0.2.0", lifespan=lifespan)


def _cleanup_expired():
    """Remove expired auth codes (>5 min) and access tokens (>1 hour)."""
    now = int(time.time())
    _db.execute("DELETE FROM sessions WHERE created_at < ?", (now - 600,))
    _db.execute("DELETE FROM auth_codes WHERE created_at < ?", (now - 300,))
    _db.execute("DELETE FROM access_tokens WHERE created_at < ?", (now - 3600,))
    _db.commit()


# ── OIDC Discovery ───────────────────────────────────────────────────

@app.get("/.well-known/openid-configuration")
def openid_configuration():
    return {
        "issuer": ISSUER,
        "authorization_endpoint": f"{ISSUER}/authorize",
        "token_endpoint": f"{ISSUER}/token",
        "userinfo_endpoint": f"{ISSUER}/userinfo",
        "jwks_uri": f"{ISSUER}/jwks.json",
        "response_types_supported": ["code"],
        "subject_types_supported": ["public"],
        "id_token_signing_alg_values_supported": ["RS256"],
        "scopes_supported": ["openid", "profile", "email"],
        "claims_supported": ["sub", "name", "email", "picture"],
    }


@app.get("/jwks.json")
def jwks():
    return {"keys": [_jwk_key.export_public(as_dict=True)]}


# ── OIDC Authorize ──────────────────────────────────────────────────

@app.get("/authorize")
async def authorize(
    client_id: str = "",
    redirect_uri: str = "",
    response_type: str = "code",
    scope: str = "openid",
    state: str = "",
    nonce: str = "",
):
    if response_type != "code":
        raise HTTPException(400, "only response_type=code is supported")

    # Persist OIDC state so we can resume after DingTalk callback
    state_key = secrets.token_urlsafe(32)
    _db.execute(
        "INSERT INTO sessions(state, original_state, nonce, redirect_uri, created_at) VALUES (?, ?, ?, ?, ?)",
        (state_key, state, nonce, redirect_uri, int(time.time())),
    )
    _db.commit()

    dd_params = {
        "client_id": DINGTALK_CLIENT_ID,
        "redirect_uri": REDIRECT_URI,
        "response_type": "code",
        "scope": "openid",
        "state": state_key,
        "prompt": "consent",
    }
    dd_url = f"https://login.dingtalk.com/oauth2/auth?{urlencode(dd_params)}"
    return RedirectResponse(dd_url)


# ── DingTalk Callback ────────────────────────────────────────────────

def _deny_html(message: str, status_code: int = 403) -> HTMLResponse:
    """被闸门拒绝时给人话页面，而不是一行 JSON —— 这是浏览器导航命中，不是 API。"""
    return HTMLResponse(
        "<!doctype html><html lang=\"zh-CN\"><meta charset=\"utf-8\">"
        "<title>无法登录</title>"
        "<body style=\"font-family:system-ui,-apple-system,sans-serif;"
        "max-width:32rem;margin:4rem auto;line-height:1.8;padding:0 1rem\">"
        "<h2>无法登录</h2>"
        f"<p>{escape(message)}</p>"
        "<p style=\"color:#666\">如果你是本公司员工，请稍后重试；"
        "仍无法登录请联系管理员。</p>"
        "</body></html>",
        status_code=status_code,
    )


def _company_member_verdict(user_data: dict) -> bool | None:
    """这个登录用户是不是本公司钉钉组织的成员。

    True / False / None(判定不了) 三态由 `stream_listener.check_org_membership`
    给出，闸门对 None 采取**拒绝**（宁可让本人重试一次，也不放行身份不明的账号）。
    """
    union_id = user_data.get("unionId")
    if not union_id:
        # 拿不到 unionId 就没法查本公司通讯录 —— 不能当成"是成员"
        logger.warning("登录缺少 unionId，无法判定公司成员身份: keys=%s", sorted(user_data))
        return None
    try:
        import stream_listener  # 局部导入，避免模块顶层循环依赖
        return stream_listener.check_org_membership(
            union_id, stream_listener.get_app_access_token()
        )
    except Exception as exc:  # noqa: BLE001 - 判定不了时由调用方拒绝
        logger.error("公司成员校验失败 union_id=%s: %s", union_id, exc)
        return None


@app.get("/callback")
async def dingtalk_callback(code: str = "", state: str = ""):
    if not code:
        raise HTTPException(400, "missing authorization code from DingTalk")

    row = _db.execute(
        "SELECT original_state, nonce, redirect_uri FROM sessions WHERE state = ?", (state,)
    ).fetchone()
    if not row:
        raise HTTPException(400, "unknown state — possible CSRF")
    original_state, nonce, redirect_uri = row

    # Exchange DingTalk authorization code for access token
    async with httpx.AsyncClient() as client:
        token_resp = await client.post(
            "https://api.dingtalk.com/v1.0/oauth2/userAccessToken",
            json={
                "clientId": DINGTALK_CLIENT_ID,
                "clientSecret": DINGTALK_CLIENT_SECRET,
                "code": code,
                "grantType": "authorization_code",
            },
            headers={"Content-Type": "application/json"},
        )
        token_data = token_resp.json()
        access_token = token_data.get("accessToken")
        if not access_token:
            raise HTTPException(400, f"DingTalk token exchange failed: {token_data}")
        # scope 含 corpid 时这里也会带回 corpId；当前 scope 只有 openid，通常为空
        corp_id = token_data.get("corpId") or ""

        # Fetch user info
        user_resp = await client.get(
            "https://api.dingtalk.com/v1.0/contact/users/me",
            headers={"x-acs-dingtalk-access-token": access_token},
        )
        user_data = user_resp.json()

    dingtalk_user_id = user_data.get("unionId") or user_data.get("openId")
    if not dingtalk_user_id:
        raise HTTPException(400, f"DingTalk user info missing ID: {user_data}")

    corp_id = corp_id or user_data.get("corpId", "")
    if corp_id and ALLOWED_CORP_ID and corp_id != ALLOWED_CORP_ID:
        logger.warning("拒绝登录：corpId=%s 不匹配", corp_id)
        return _deny_html("该钉钉账号不属于本公司组织。")

    # 公司成员闸门（权威判据）。历史上这里只比 corpId，而 /contact/users/me 常常
    # 不返回它，于是校验被整段跳过 —— 任何钉钉账号（含外部的）都能登录。
    # 现在按组织成员查：不在本公司通讯录的人 getbyunionid 返回 60121。
    if REQUIRE_COMPANY_MEMBER:
        verdict = _company_member_verdict(user_data)
        logger.info(
            "登录校验 union_id=%s name=%s corp_id=%s 公司成员=%s",
            user_data.get("unionId") or dingtalk_user_id,
            user_data.get("name"),
            corp_id or "(未返回)",
            verdict,
        )
        if verdict is not True:
            return _deny_html(
                "该钉钉账号不在本公司组织内。" if verdict is False
                else "暂时无法确认你的公司身份（钉钉接口异常），请稍后重试。"
            )

    user_name = user_data.get("name") or user_data.get("nick") or dingtalk_user_id
    email = user_data.get("email") or f"{dingtalk_user_id}@dingtalk"
    avatar = user_data.get("avatarUrl") or ""

    # Best-effort: 登录时记录 unionId↔userId 映射（后台线程），失败绝不影响登录。
    # 若 DingTalk OAuth 只返回 openId（无 unionId），跳过（映射无法以 unionId 为键）。
    if user_data.get("unionId"):
        try:
            import stream_listener  # 局部导入，避免模块顶层循环依赖
            loop = asyncio.get_running_loop()
            loop.run_in_executor(
                None,
                lambda: stream_listener.record_login_identity(user_data["unionId"], user_name),
            )
        except Exception as e:  # 记录映射只是优化，登录主流程必须继续
            logger.warning("identity map record skipped (non-fatal): %s", e)

    # Generate OIDC authorization code
    oidc_code = secrets.token_urlsafe(32)
    _db.execute(
        "INSERT INTO auth_codes(code, user_id, user_name, email, avatar, nonce, created_at) "
        "VALUES (?, ?, ?, ?, ?, ?, ?)",
        (oidc_code, dingtalk_user_id, user_name, email, avatar, nonce, int(time.time())),
    )
    _db.execute("DELETE FROM sessions WHERE state = ?", (state,))
    _db.commit()

    oidc_params = {"code": oidc_code, "state": original_state}
    if redirect_uri:
        sep = "&" if "?" in redirect_uri else "?"
        return RedirectResponse(f"{redirect_uri}{sep}{urlencode(oidc_params)}")
    return JSONResponse({"code": oidc_code})


# ── OIDC Token ──────────────────────────────────────────────────────

@app.post("/token")
async def token(
    grant_type: str = Form(default="authorization_code"),
    code: str = Form(default=""),
    client_id: str = Form(default=""),
    client_secret: str = Form(default=""),
    redirect_uri: str = Form(default=""),
):
    _cleanup_expired()

    if grant_type != "authorization_code":
        raise HTTPException(400, "only authorization_code grant is supported")

    row = _db.execute(
        "SELECT user_id, user_name, email, avatar, nonce FROM auth_codes WHERE code = ?",
        (code,),
    ).fetchone()
    if not row:
        raise HTTPException(400, "invalid or expired authorization code")

    user_id, user_name, email, avatar, nonce = row

    # Generate access token
    access_token = secrets.token_urlsafe(32)
    _db.execute(
        "INSERT INTO access_tokens(token, user_id, user_name, email, avatar, created_at) "
        "VALUES (?, ?, ?, ?, ?, ?)",
        (access_token, user_id, user_name, email, avatar, int(time.time())),
    )
    _db.execute("DELETE FROM auth_codes WHERE code = ?", (code,))
    _db.commit()

    # Build id_token
    now = int(time.time())
    claims = {
        "iss": ISSUER,
        "sub": user_id,
        "aud": client_id or "new-api",
        "exp": now + 3600,
        "iat": now,
        "name": user_name,
        "email": email,
        "picture": avatar,
    }
    if nonce:
        claims["nonce"] = nonce

    token_jwt = jwt.JWT(header={"alg": "RS256", "kid": _KEY_ID, "typ": "JWT"},
                        claims=claims)
    token_jwt.make_signed_token(_jwk_key)
    id_token = token_jwt.serialize()

    return {
        "access_token": access_token,
        "token_type": "Bearer",
        "expires_in": 3600,
        "id_token": id_token,
    }


# ── OIDC UserInfo ───────────────────────────────────────────────────

@app.get("/userinfo")
def userinfo(request: Request):
    auth = request.headers.get("Authorization", "")
    if not auth.startswith("Bearer "):
        raise HTTPException(401, "missing Bearer token")
    access_token = auth[7:]

    row = _db.execute(
        "SELECT user_id, user_name, email, avatar FROM access_tokens WHERE token = ?",
        (access_token,),
    ).fetchone()
    if not row:
        raise HTTPException(401, "invalid or expired access token")

    user_id, user_name, email, avatar = row
    return {
        "sub": user_id,
        "name": user_name,
        "email": email,
        "picture": avatar,
    }


# ── Health ───────────────────────────────────────────────────────────

@app.get("/health")
def health():
    return {"status": "ok"}


