#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""同站 POST 的 CSRF 令牌。

api.vilavi.cn 上还有别的服务。cookie 的 Path 限定在本服务前缀下，
其它路径的页面读不到这个 cookie，但可以提交表单到本服务。
因此 POST 必须带上与 cookie 一致的表单字段，不能只靠 SameSite。
"""

from __future__ import annotations

import hmac
import secrets

from starlette.requests import Request

COOKIE_NAME = "pb_orders_csrf"
MIN_LEN = 20


def current_or_new(request: Request) -> tuple[str, bool]:
    """返回 (令牌, 是否本次新签发)。已有令牌不轮换，避免开着的表单失效。"""
    current = request.cookies.get(COOKIE_NAME, "")
    if len(current) >= MIN_LEN:
        return current, False
    return secrets.token_urlsafe(32), True


def accepted(request: Request, submitted: str) -> bool:
    expected = request.cookies.get(COOKIE_NAME, "")
    if len(expected) < MIN_LEN or not submitted:
        return False
    return hmac.compare_digest(expected, submitted)


def cookie_is_secure(request: Request) -> bool:
    """反代会带 X-Forwarded-Proto；应用自己看到的 scheme 在 TLS 终结后仍是 http。"""
    if request.url.scheme == "https":
        return True
    proto = request.headers.get("x-forwarded-proto", "")
    return proto.split(",")[0].strip().lower() == "https"
