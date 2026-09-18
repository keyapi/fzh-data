"""UPS 官方 Track API 客户端（REST + OAuth2 client_credentials）。

- Token：POST ``/security/v1/oauth/token``（Basic auth，``grant_type=client_credentials``）
- Track：GET  ``/api/track/v1/details/{inquiryNumber}``（Bearer token）

凭证只从 env 读取（UPS_CLIENT_ID / UPS_CLIENT_SECRET），绝不硬编码/提交。
测试环境 CIE 的 token 与生产不通用，见 ``from_env`` / ``UpsTrackClient`` 文档。
"""

from __future__ import annotations

import base64
import os
import threading
import time
import uuid
from typing import Any
from urllib.parse import quote

import httpx

from .models import UpsTrackInfo, parse_track_payload

DEFAULT_PROD_BASE = "https://onlinetools.ups.com"
DEFAULT_CIE_BASE = "https://wwwcie.ups.com"
TOKEN_REFRESH_MARGIN = 300  # 秒：到期前预刷新
APP_SRC = "fzh_ups_track"


def _b64(s: str) -> str:
    return base64.b64encode(s.encode("utf-8")).decode("ascii")


def _first_error(body: Any) -> tuple[str | None, str | None]:
    """从 UPS 错误响应里取出 (code, message)，兼容多种形状。"""
    resp = body.get("response") if isinstance(body, dict) else None
    errors = []
    if isinstance(resp, dict):
        errors = resp.get("errors") or []
    if not errors and isinstance(body, dict):
        errors = body.get("errors") or []
    if not errors and isinstance(resp, dict):
        errs = resp.get("error")
        errors = [errs] if isinstance(errs, dict) else []
    for e in errors if isinstance(errors, list) else []:
        if isinstance(e, dict):
            return _text(e.get("code")), _text(e.get("message"))
    return None, None


def _text(v: Any) -> str | None:
    if v is None:
        return None
    s = str(v).strip()
    return s or None


class UpsTrackError(Exception):
    """UPS 查询失败。category ∈ {auth, permission, not_found, rate_limit, invalid, transport, other}。"""

    def __init__(
        self,
        message: str,
        *,
        http_status: int | None = None,
        code: str | None = None,
        category: str = "other",
        retriable: bool = False,
    ):
        super().__init__(message)
        self.message = message
        self.http_status = http_status
        self.code = code
        self.category = category
        self.retriable = retriable

    def __str__(self) -> str:  # pragma: no cover - 调试友好
        bits = [self.message]
        if self.code:
            bits.append(f"code={self.code}")
        if self.http_status:
            bits.append(f"http={self.http_status}")
        bits.append(f"category={self.category}")
        return " ".join(bits)


def classify_http_error(
    http_status: int | None, code: str | None
) -> tuple[str, bool]:
    """把 (http status, UPS error code) 归类为 (category, retriable)。"""
    if http_status == 401:
        if code == "250002":
            return "auth", False
        return "permission", False
    if http_status == 429:
        return "rate_limit", True
    if http_status in (500, 502, 503, 504):
        return "transport", True
    if http_status in (400, 404):
        # UPS 常见 track 错误码：250002=认证；200000/200001/…=查无此号
        if code == "250002":
            return "auth", False
        if code and code.startswith("200"):
            return "not_found", False
        return "invalid", False
    if http_status is None:
        return "transport", True
    return "other", False


class UpsTrackClient:
    """UPS Track API 客户端（httpx，线程安全；token 缓存 + 到期前预刷新）。

    Parameters
    ----------
    client_id / client_secret : OAuth client_credentials（UPS Developer 后台取）。
    base_url : 生产 ``https://onlinetools.ups.com``；测试 CIE ``https://wwwcie.ups.com``。
    proxy : 可选 HTTP(S) 代理（国内直连 onlinetools.ups.com 不通时使用）。
    transport : 仅供测试注入 ``httpx.MockTransport``。
    """

    def __init__(
        self,
        *,
        client_id: str,
        client_secret: str,
        base_url: str = DEFAULT_CIE_BASE,
        timeout: float = 30.0,
        proxy: str | None = None,
        transport: httpx.BaseTransport | None = None,
    ):
        cid = (client_id or "").strip()
        secret = (client_secret or "").strip()
        if not cid or not secret:
            raise ValueError("UPS client_id/client_secret are required")
        if transport is not None and proxy:
            raise ValueError("transport 与 proxy 不能同时指定")
        self._cid = cid
        self._secret = secret
        self._base = (base_url or DEFAULT_CIE_BASE).rstrip("/")
        self._lock = threading.Lock()
        self._access_token: str | None = None
        self._expires_at: float = 0.0
        kw: dict[str, Any] = {"timeout": timeout}
        if transport is not None:
            kw["transport"] = transport
        if proxy:
            kw["proxy"] = proxy
        self._client = httpx.Client(**kw)

    # ── 生命周期 ──────────────────────────────────────────────
    def close(self) -> None:
        self._client.close()

    def __enter__(self) -> "UpsTrackClient":
        return self

    def __exit__(self, *args: object) -> None:
        self.close()

    @classmethod
    def from_env(cls) -> "UpsTrackClient":
        """从 env 构建：UPS_CLIENT_ID/SECRET、UPS_BASE_URL 或 UPS_API_ENV、UPS_HTTP_PROXY。"""
        env_mode = (os.getenv("UPS_API_ENV") or "cie").strip().lower()
        base = os.getenv("UPS_BASE_URL")
        if not base:
            base = DEFAULT_PROD_BASE if env_mode == "prod" else DEFAULT_CIE_BASE
        return cls(
            client_id=os.getenv("UPS_CLIENT_ID", ""),
            client_secret=os.getenv("UPS_CLIENT_SECRET", ""),
            base_url=base,
            proxy=os.getenv("UPS_HTTP_PROXY") or None,
        )

    # ── OAuth token ──────────────────────────────────────────
    def _obtain_token(self) -> None:
        url = f"{self._base}/security/v1/oauth/token"
        auth = f"Basic {_b64(f'{self._cid}:{self._secret}')}"
        try:
            resp = self._client.post(
                url,
                headers={
                    "Authorization": auth,
                    "Content-Type": "application/x-www-form-urlencoded",
                    "Accept": "application/json",
                },
                data={"grant_type": "client_credentials"},
            )
        except httpx.HTTPError as exc:
            raise UpsTrackError(f"UPS token 请求失败: {exc}", category="transport", retriable=True) from exc
        body = self._json_body(resp)
        if resp.status_code != 200:
            code, message = _first_error(body)
            category, retriable = classify_http_error(resp.status_code, code)
            msg = message or _text(code) or f"HTTP {resp.status_code}"
            raise UpsTrackError(
                f"UPS token 失败: {msg}", http_status=resp.status_code,
                code=code, category=category, retriable=retriable,
            )
        token = _text(body.get("access_token")) if isinstance(body, dict) else None
        if not token:
            raise UpsTrackError("UPS token 响应缺 access_token", category="other")
        try:
            ttl = int(body.get("expires_in", 14400))
        except (TypeError, ValueError):
            ttl = 14400
        with self._lock:
            self._access_token = token
            self._expires_at = time.time() + max(60, ttl - TOKEN_REFRESH_MARGIN)

    def _ensure_token(self) -> str:
        with self._lock:
            if self._access_token and time.time() < self._expires_at:
                return self._access_token
        self._obtain_token()
        with self._lock:
            return self._access_token or ""

    # ── Track ────────────────────────────────────────────────
    def track(
        self,
        inquiry_number: str,
        *,
        locale: str = "en_US",
        trans_id: str | None = None,
        transaction_src: str = APP_SRC,
    ) -> UpsTrackInfo:
        """查询单号，返回归一化结果（含原始 raw）。查无此号时 not_found=True 不抛错。"""
        number = (inquiry_number or "").strip().upper()
        if not number:
            raise ValueError("inquiry_number is required")
        token = self._ensure_token()
        qn = quote(number, safe="")
        url = f"{self._base}/api/track/v1/details/{qn}"
        headers = {
            "Authorization": f"Bearer {token}",
            "transId": trans_id or str(uuid.uuid4()),
            "transactionSrc": transaction_src,
            "Accept": "application/json",
        }
        try:
            resp = self._client.get(url, headers=headers, params={"locale": locale})
        except httpx.HTTPError as exc:
            raise UpsTrackError(
                f"UPS track {number} 请求失败: {exc}", category="transport", retriable=True
            ) from exc
        body = self._json_body(resp)
        if resp.status_code != 200:
            code, message = _first_error(body)
            category, retriable = classify_http_error(resp.status_code, code)
            msg = message or _text(code) or f"HTTP {resp.status_code}"
            raise UpsTrackError(
                f"UPS track {number} 失败: {msg}",
                http_status=resp.status_code, code=code,
                category=category, retriable=retriable,
            )
        return parse_track_payload(number, body)

    # ── 内部 ─────────────────────────────────────────────────
    def _json_body(self, resp: httpx.Response) -> Any:
        try:
            return resp.json()
        except ValueError:
            return {"response": {"errors": [{"code": None, "message": resp.text[:500]}]}}
