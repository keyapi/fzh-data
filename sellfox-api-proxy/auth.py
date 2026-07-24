import hashlib
import hmac as _hmac
import time
from urllib.parse import quote, unquote

from fastapi import HTTPException, Request

from config import settings

COOKIE_NAME = "proxy_admin_session"
SESSION_TTL = 28800  # 8 hours


def make_session_token(identity: str, display_name: str) -> str:
    ts = str(int(time.time()))
    payload = f"{ts}|{identity}|{quote(display_name, safe='')}"
    sig = _hmac.new(
        settings.admin_key.encode(), payload.encode(), hashlib.sha256
    ).hexdigest()[:32]
    return f"{payload}|{sig}"


def parse_session_token(token: str) -> dict | None:
    try:
        parts = token.rsplit("|", 1)
        if len(parts) != 2:
            return None
        payload, sig = parts
        expected = _hmac.new(
            settings.admin_key.encode(), payload.encode(), hashlib.sha256
        ).hexdigest()[:32]
        if not _hmac.compare_digest(sig, expected):
            return None
        fields = payload.split("|", 2)
        if len(fields) != 3:
            return None
        ts, identity, display_name_encoded = fields
        if time.time() - int(ts) > SESSION_TTL:
            return None
        return {"identity": identity, "display_name": unquote(display_name_encoded)}
    except Exception:
        return None


async def verify_api_key(request: Request) -> dict:
    auth = request.headers.get("Authorization", "")
    if not auth.startswith("Bearer "):
        raise HTTPException(401, "Missing Bearer token")
    raw_key = auth[7:]
    if not raw_key:
        raise HTTPException(401, "Empty API key")
    record = await request.app.state.db_lookup(raw_key)
    if record is None:
        raise HTTPException(401, "Invalid or inactive API key")
    await request.app.state.db_record_usage(record["id"])
    return record


async def verify_user(request: Request) -> dict:
    """Authenticate and return {role, identity, display_name}.
    role = 'admin' | 'user'
    """
    session = request.cookies.get(COOKIE_NAME, "")
    if session:
        data = parse_session_token(session)
        if data:
            role = "admin" if data["identity"] == "admin" else "user"
            return {"role": role, **data}

    dingtalk_id = request.headers.get("X-DingTalk-User-Id", "")
    if dingtalk_id:
        return {
            "role": "user",
            "identity": dingtalk_id,
            "display_name": request.headers.get("X-DingTalk-User-Name", dingtalk_id),
        }

    admin_key = request.headers.get("X-Admin-Key", "")
    if admin_key and settings.admin_key:
        if _hmac.compare_digest(admin_key, settings.admin_key):
            return {"role": "admin", "identity": "admin", "display_name": "admin"}

    raise HTTPException(401, "Authentication required")


def require_admin(user: dict):
    """Raise 403 if user is not admin."""
    if user["role"] != "admin":
        raise HTTPException(403, "Admin access required")
