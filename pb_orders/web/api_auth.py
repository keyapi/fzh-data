#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""JSON API 的 Bearer 鉴权：API Key + OIDC 用户 token。

- `sk-` 开头：sha256 查 `api_keys`，按 key 的 scopes 授权。
- 其他：调用公司 OIDC 桥的 `/userinfo`（60s 缓存），按 `PB_ORDERS_OIDC_API_SCOPES` 授权。
- 两种身份都套 `PB_ORDERS_ALLOWED_USERS` 白名单。
- `/api/v1` 不接受 cookie 会话，因此不走 CSRF；HTML 表单的 CSRF 逻辑保持不变。
"""

from __future__ import annotations

import hashlib
import threading
import time
from dataclasses import dataclass, field

import httpx
from starlette.requests import Request

from web.api_errors import ApiError
from web.auth import is_allowed
from web.config import Settings
from web.repository import Repository

_USERINFO_CACHE: dict[str, tuple[float, dict]] = {}
_CACHE_LOCK = threading.Lock()
_CACHE_TTL = 60.0

_RATE_LOCK = threading.Lock()
_RATE_WINDOW: dict[str, list[float]] = {}


@dataclass
class Principal:
    identity: str
    display_name: str
    kind: str  # "api_key" | "oidc"
    scopes: set[str] = field(default_factory=set)
    api_key_id: str | None = None

    def has(self, scope: str) -> bool:
        return scope in self.scopes


def _unauthorized(message: str = "缺少或无效的 Bearer token") -> ApiError:
    return ApiError(401, "unauthorized", message, hint="请在 Authorization: Bearer 中提供 API Key 或 OIDC access token。")


def _hash(token: str) -> str:
    return hashlib.sha256(token.encode("utf-8")).hexdigest()


async def _userinfo(settings: Settings, token: str) -> dict:
    key = _hash(token)
    now = time.time()
    with _CACHE_LOCK:
        hit = _USERINFO_CACHE.get(key)
        if hit and hit[0] > now:
            return hit[1]
    if not settings.oidc_issuer:
        raise _unauthorized("未配置 OIDC issuer，无法校验该 token")
    url = f"{settings.oidc_issuer}/userinfo"
    try:
        async with httpx.AsyncClient(timeout=5.0) as client:
            resp = await client.get(url, headers={"Authorization": f"Bearer {token}"})
    except httpx.HTTPError as exc:
        raise ApiError(503, "auth_unavailable", "OIDC userinfo 暂不可用", hint="稍后重试，或使用 API Key。") from exc
    if resp.status_code != 200:
        raise _unauthorized("OIDC token 无效或已过期")
    data = resp.json()
    if not data.get("sub"):
        raise _unauthorized("OIDC userinfo 缺少 sub")
    with _CACHE_LOCK:
        _USERINFO_CACHE[key] = (now + _CACHE_TTL, data)
    return data


def _rate_limit(principal: Principal, rps: float) -> None:
    if rps <= 0:
        return
    now = time.time()
    bucket = _RATE_WINDOW.setdefault(principal.identity, [])
    with _RATE_LOCK:
        bucket[:] = [t for t in bucket if t > now - 60]
        if len(bucket) >= max(1, int(rps * 60)):
            raise ApiError(429, "rate_limited", "请求过于频繁", hint="请降低频率后重试。")
        bucket.append(now)


async def authenticate_bearer(request: Request, settings: Settings, repo: Repository) -> Principal:
    header = request.headers.get("authorization", "")
    if not header.lower().startswith("bearer "):
        raise _unauthorized()
    token = header[7:].strip()
    if not token:
        raise _unauthorized()

    if token.startswith("sk-"):
        row = repo.lookup_api_key(_hash(token))
        if row is None:
            raise _unauthorized("API Key 不存在或已吊销")
        repo.touch_api_key(row["id"])
        principal = Principal(
            identity=f"api-key:{row['id']}",
            display_name=row["name"] or row["key_prefix"],
            kind="api_key",
            scopes={s.strip() for s in (row["scopes"] or "").split(",") if s.strip()},
            api_key_id=row["id"],
        )
    else:
        data = await _userinfo(settings, token)
        user = {
            "identity": str(data.get("sub")),
            "display_name": str(data.get("name") or data.get("sub")),
        }
        if not is_allowed(user, settings):
            raise ApiError(403, "forbidden", f"账号「{user['display_name']}」不在允许名单内。")
        principal = Principal(
            identity=f"oidc:{user['identity']}",
            display_name=user["display_name"],
            kind="oidc",
            scopes=set(settings.oidc_api_scopes),
        )

    _rate_limit(principal, settings.api_key_rate_limit_rps)
    return principal


def require_scope(principal: Principal, scope: str) -> None:
    if not principal.has(scope):
        raise ApiError(
            403, "forbidden_scope", f"当前身份没有 {scope} 权限",
            hint=f"需要的 scope：{scope}；当前：{', '.join(sorted(principal.scopes)) or '无'}",
        )
