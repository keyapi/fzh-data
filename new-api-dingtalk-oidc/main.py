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

import hashlib
import os
import secrets
import sqlite3
import time
from urllib.parse import urlencode

import httpx
from cryptography.hazmat.primitives import serialization
from cryptography.hazmat.primitives.asymmetric import rsa
from fastapi import FastAPI, Form, HTTPException, Request
from fastapi.responses import JSONResponse, RedirectResponse
from jwcrypto import jwk, jwt

# ── Config ──────────────────────────────────────────────────────────

ISSUER = os.getenv("ISSUER", "http://localhost:8086").rstrip("/")
DINGTALK_CLIENT_ID = os.getenv("DINGTALK_CLIENT_ID", "")
DINGTALK_CLIENT_SECRET = os.getenv("DINGTALK_CLIENT_SECRET", "")
ALLOWED_CORP_ID = os.getenv("ALLOWED_CORP_ID", "")  # restrict to one corp
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

app = FastAPI(title="DingTalk OIDC Bridge", version="0.1.0")


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

        # Fetch user info
        user_resp = await client.get(
            "https://api.dingtalk.com/v1.0/contact/users/me",
            headers={"x-acs-dingtalk-access-token": access_token},
        )
        user_data = user_resp.json()

    dingtalk_user_id = user_data.get("unionId") or user_data.get("openId")
    if not dingtalk_user_id:
        raise HTTPException(400, f"DingTalk user info missing ID: {user_data}")

    # corpId is not always returned by /contact/users/me; only enforce if present
    corp_id = user_data.get("corpId", "")
    if corp_id and ALLOWED_CORP_ID and corp_id != ALLOWED_CORP_ID:
        raise HTTPException(403, f"user not in allowed corp (got {corp_id})")

    user_name = user_data.get("nick") or user_data.get("name") or dingtalk_user_id
    email = user_data.get("email") or f"{dingtalk_user_id}@dingtalk"
    avatar = user_data.get("avatarUrl") or ""

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
