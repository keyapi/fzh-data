#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""钉钉 OIDC 登录（复用公司的 OIDC 桥，不重造）。

复用 `sellfox_shipping.auth_oidc` 的 **会话签名**（HMAC-SHA256 签名 cookie，
无状态、重启不丢），只把下面三件事按 PB 的需要重做：

1. **state 存 Redis** —— 上游模块用进程内 dict，多 worker / 重启后回调会报
   `Invalid state`；PB 自带 Redis，直接用它（Redis 不可用时降级为进程内，单 worker 够用）。
2. **支持 URL 前缀** —— 挂在 `/pb/` 下时所有生成的 URL 都要带前缀。
3. **登录后回到用户原本想去的页面**，而不是上游硬编码的 `/packages`；
   并把「任意钉钉用户可登录」这个已知现状补一层可选白名单。

认证默认关闭（`PB_ORDERS_OIDC_ISSUER` 为空），本机开发无需登录。
"""

from __future__ import annotations

import logging
import secrets
import sys
import time
from dataclasses import dataclass
from pathlib import Path
from urllib.parse import quote, urlencode

_PB_DIR = Path(__file__).resolve().parent.parent
if str(_PB_DIR) not in sys.path:
    sys.path.insert(0, str(_PB_DIR))

import httpx  # noqa: E402
from fastapi import APIRouter, HTTPException, Request  # noqa: E402
from fastapi.responses import HTMLResponse, RedirectResponse  # noqa: E402

from sellfox_shipping.auth_oidc import (  # noqa: E402
    make_session_token,
    parse_session_token,
)
from web.config import Settings  # noqa: E402

log = logging.getLogger("pb_orders.auth")

COOKIE_NAME = "pb_orders_session"
SESSION_TTL = 8 * 3600
STATE_TTL = 300
STATE_KEY = "pb-orders:oidc-state:"
HTTP_TIMEOUT = 15

# 不需要登录的路径（应用侧路径，不含 URL 前缀 —— 前缀在反代层已剥掉）
PUBLIC_PATHS = ("/healthz", "/oidc-login", "/oidc-callback", "/logout")


@dataclass(frozen=True)
class AuthContext:
    settings: Settings

    @property
    def prefix(self) -> str:
        return self.settings.url_prefix

    @property
    def cookie_path(self) -> str:
        return f"{self.prefix}/" if self.prefix else "/"

    def url(self, path: str) -> str:
        return f"{self.prefix}{path}"


class StateStore:
    """一次性 OIDC state -> return_to 的映射，优先 Redis。"""

    def __init__(self, redis_url: str):
        self._memory: dict[str, tuple[float, str]] = {}
        self._redis = None
        try:
            from redis import Redis

            self._redis = Redis.from_url(redis_url, socket_connect_timeout=2)
            self._redis.ping()
        except Exception as exc:  # noqa: BLE001 - 单 worker 开发环境没有 Redis
            log.warning("OIDC state 降级为进程内存储（Redis 不可用：%s）", type(exc).__name__)
            self._redis = None

    def put(self, state: str, return_to: str) -> None:
        if self._redis is not None:
            self._redis.setex(f"{STATE_KEY}{state}", STATE_TTL, return_to)
            return
        self._purge()
        self._memory[state] = (time.time(), return_to)

    def pop(self, state: str) -> str | None:
        """取出并作废；state 不存在或已过期返回 None。"""
        if not state:
            return None
        if self._redis is not None:
            key = f"{STATE_KEY}{state}"
            value = self._redis.get(key)
            self._redis.delete(key)
            return value.decode() if value is not None else None
        self._purge()
        item = self._memory.pop(state, None)
        return item[1] if item else None

    def _purge(self) -> None:
        cutoff = time.time() - STATE_TTL
        for key in [k for k, (ts, _) in self._memory.items() if ts < cutoff]:
            self._memory.pop(key, None)


def safe_return_to(value: str, ctx: AuthContext) -> str:
    """只允许回到**本站本服务**的相对路径。

    两层防护：
    - 必须是相对路径且不以 `//` 开头（挡 `//evil.com` 这类开放重定向）；
    - 配了前缀时必须落在该前缀之下（挡跳到同一域名下的**其它服务**，
      比如 `api.vilavi.cn/` 根路径挂的是公司大模型路由）。
    """
    root = ctx.url("/")
    raw = (value or "").strip()
    if not raw.startswith("/") or raw.startswith("//"):
        return root
    if ctx.prefix and not (raw == ctx.prefix or raw.startswith(f"{ctx.prefix}/")):
        return root
    return raw


def is_allowed(user: dict[str, str], settings: Settings) -> bool:
    if not settings.allowed_users:
        return True
    allowed = {u.lower() for u in settings.allowed_users}
    candidates = {
        str(user.get("identity", "")).lower(),
        str(user.get("display_name", "")).lower(),
    }
    return bool(candidates & allowed)


def current_user(request: Request, settings: Settings) -> dict[str, str] | None:
    if not settings.auth_enabled:
        return {"identity": "local", "display_name": "本机（未启用登录）"}
    raw = request.cookies.get(COOKIE_NAME, "")
    return parse_session_token(raw, secret=settings.session_secret, ttl=SESSION_TTL)


def build_router(ctx: AuthContext, states: StateStore, templates) -> APIRouter:
    settings = ctx.settings
    router = APIRouter(tags=["auth"])

    @router.get("/oidc-login")
    async def oidc_login(return_to: str = ""):
        if not settings.auth_enabled:
            return RedirectResponse(ctx.url("/"))
        state = secrets.token_urlsafe(32)
        states.put(state, safe_return_to(return_to, ctx))
        params = {
            "client_id": settings.oidc_client_id,
            "redirect_uri": settings.oidc_redirect_uri,
            "response_type": "code",
            "scope": "openid",
            "state": state,
        }
        return RedirectResponse(f"{settings.oidc_issuer}/authorize?{urlencode(params)}")

    @router.get("/oidc-callback")
    async def oidc_callback(request: Request, code: str = "", state: str = ""):
        if not settings.auth_enabled:
            raise HTTPException(404, "OIDC 未启用")
        return_to = states.pop(state)
        if return_to is None:
            return templates.TemplateResponse(
                request,
                "error.html",
                {"message": "登录状态已过期或无效，请重新登录。", "prefix": ctx.prefix},
                status_code=400,
            )
        if not code:
            raise HTTPException(400, "缺少授权码")

        async with httpx.AsyncClient() as client:
            resp = await client.post(
                f"{settings.oidc_issuer}/token",
                data={
                    "grant_type": "authorization_code",
                    "code": code,
                    "client_id": settings.oidc_client_id,
                    "client_secret": settings.oidc_client_secret,
                    "redirect_uri": settings.oidc_redirect_uri,
                },
                timeout=HTTP_TIMEOUT,
            )
            if resp.status_code != 200:
                raise HTTPException(400, f"换取 token 失败：{resp.text[:200]}")
            access_token = resp.json().get("access_token", "")
            user_resp = await client.get(
                f"{settings.oidc_issuer}/userinfo",
                headers={"Authorization": f"Bearer {access_token}"},
                timeout=HTTP_TIMEOUT,
            )
            if user_resp.status_code != 200:
                raise HTTPException(400, f"获取用户信息失败：{user_resp.text[:200]}")
            user = user_resp.json()

        identity = str(user.get("sub") or "")
        display_name = str(user.get("name") or identity)
        if not identity:
            raise HTTPException(400, "OIDC 返回的用户缺少 sub")

        if not is_allowed({"identity": identity, "display_name": display_name}, settings):
            log.warning("拒绝未授权用户：%s(%s)", display_name, identity)
            return templates.TemplateResponse(
                request,
                "error.html",
                {
                    "message": f"账号「{display_name}」不在允许名单内，请联系管理员开通。",
                    "prefix": ctx.prefix,
                },
                status_code=403,
            )

        token = make_session_token(
            identity, display_name, secret=settings.session_secret, ttl=SESSION_TTL
        )
        resp = RedirectResponse(return_to)
        resp.set_cookie(
            COOKIE_NAME,
            token,
            max_age=SESSION_TTL,
            httponly=True,
            samesite="lax",
            path=ctx.cookie_path,
            secure=settings.oidc_redirect_uri.lower().startswith("https://"),
        )
        log.info("登录成功：%s(%s)", display_name, identity)
        return resp

    @router.post("/logout")
    async def logout():
        resp = RedirectResponse(ctx.url("/"))
        resp.delete_cookie(COOKIE_NAME, path=ctx.cookie_path)
        return resp

    return router
