"""FedEx Track API 客户端（httpx + OAuth2 client_credentials）。

- Token：POST ``{base}/oauth/token``（form 编码，client_id/client_secret 放 body，非 Basic）
- Track：POST ``{base}/track/v1/trackingnumbers``（Bearer token，body 含 trackingInfo ≤30，includeDetailedScans）

凭证只从 env 读取（FEDEX_API_KEY / FEDEX_SECRET_KEY），绝不硬编码/提交。
"""

from __future__ import annotations

import os
import threading
import time
from typing import Any

import httpx

from .models import FdxTrackInfo, parse_track_result

DEFAULT_PROD_BASE = "https://apis.fedex.com"
DEFAULT_SANDBOX_BASE = "https://apis-sandbox.fedex.com"
TOKEN_REFRESH_MARGIN = 300
MAX_NUMBERS_PER_REQUEST = 30


def _text(v: Any) -> str | None:
    if v is None:
        return None
    s = str(v).strip()
    return s or None


def _first_error(body: Any) -> tuple[str | None, str | None]:
    resp = body if isinstance(body, dict) else {}
    errors = resp.get("errors") or []
    if not errors:
        errors = resp.get("error") or []
    if isinstance(errors, dict):
        errors = [errors]
    for e in errors if isinstance(errors, list) else []:
        if isinstance(e, dict):
            if isinstance(e.get("code") or e.get("message"), str):
                return _text(e.get("code")), _text(e.get("message"))
    return None, None


class FedexTrackError(Exception):
    """FedEx 查询失败。category ∈ {auth, permission, not_found, rate_limit, invalid, transport, other}。"""

    def __init__(self, message: str, *, http_status: int | None = None,
                 code: str | None = None, category: str = "other", retriable: bool = False):
        super().__init__(message)
        self.message = message
        self.http_status = http_status
        self.code = code
        self.category = category
        self.retriable = retriable

    def __str__(self) -> str:  # pragma: no cover
        bits = [self.message]
        if self.code:
            bits.append(f"code={self.code}")
        if self.http_status:
            bits.append(f"http={self.http_status}")
        bits.append(f"category={self.category}")
        return " ".join(bits)


def classify_http_error(http_status: int | None, code: str | None) -> tuple[str, bool]:
    if http_status == 401:
        return ("auth", False) if code == "AUTH.TOKEN.INVALID" else ("permission", False)
    if http_status == 429:
        return "rate_limit", True
    if http_status in (500, 502, 503, 504):
        return "transport", True
    if http_status in (400, 404):
        if code and ("NOT.FOUND" in code or code.endswith(".NOT.FOUND") or "AUTHORIZATION" in code):
            return ("not_found", False) if "AUTHORIZATION" not in code else ("permission", False)
        return "invalid", False
    if http_status is None:
        return "transport", True
    return "other", False


class FedexTrackClient:
    """FedEx Track API 客户端（httpx，线程安全；token 缓存 + 到期前预刷新）。"""

    def __init__(self, *, api_key: str, secret_key: str, base_url: str = DEFAULT_PROD_BASE,
                 timeout: float = 30.0, proxy: str | None = None,
                 transport: httpx.BaseTransport | None = None):
        key = (api_key or "").strip()
        sec = (secret_key or "").strip()
        if not key or not sec:
            raise ValueError("FedEx api_key/secret_key are required")
        if transport is not None and proxy:
            raise ValueError("transport 与 proxy 不能同时指定")
        self._key = key
        self._secret = sec
        self._base = (base_url or DEFAULT_PROD_BASE).rstrip("/")
        self._lock = threading.Lock()
        self._access_token: str | None = None
        self._expires_at: float = 0.0
        kw: dict[str, Any] = {"timeout": timeout}
        if transport is not None:
            kw["transport"] = transport
        if proxy:
            kw["proxy"] = proxy
        self._client = httpx.Client(**kw)

    def close(self) -> None:
        self._client.close()

    def __enter__(self) -> "FedexTrackClient":
        return self

    def __exit__(self, *args: object) -> None:
        self.close()

    @classmethod
    def from_env(cls) -> "FedexTrackClient":
        env_mode = (os.getenv("FEDEX_ENV") or "production").strip().lower()
        base = os.getenv("FEDEX_BASE_URL")
        if not base:
            base = DEFAULT_PROD_BASE if env_mode in ("production", "prod") else DEFAULT_SANDBOX_BASE
        return cls(
            api_key=os.getenv("FEDEX_API_KEY", ""),
            secret_key=os.getenv("FEDEX_SECRET_KEY", ""),
            base_url=base,
            proxy=os.getenv("FEDEX_HTTP_PROXY") or None,
        )

    # ── OAuth token ──────────────────────────────────────────
    def _obtain_token(self) -> None:
        url = f"{self._base}/oauth/token"
        data = {"grant_type": "client_credentials", "client_id": self._key, "client_secret": self._secret}
        try:
            resp = self._client.post(url, data=data,
                headers={"Content-Type": "application/x-www-form-urlencoded", "Accept": "application/json"})
        except httpx.HTTPError as exc:
            raise FedexTrackError(f"FedEx token 请求失败: {exc}", category="transport", retriable=True) from exc
        body = self._json_body(resp)
        if resp.status_code != 200:
            code, message = _first_error(body)
            category, retriable = classify_http_error(resp.status_code, code)
            raise FedexTrackError(f"FedEx token 失败: {message or _text(code) or f'HTTP {resp.status_code}'}",
                http_status=resp.status_code, code=code, category=category, retriable=retriable)
        token = _text(body.get("access_token")) if isinstance(body, dict) else None
        if not token:
            raise FedexTrackError("FedEx token 响应缺 access_token", category="other")
        try:
            ttl = int(body.get("expires_in", 7200))
        except (TypeError, ValueError):
            ttl = 7200
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

    # ── Track 批量 ───────────────────────────────────────────
    def track_many(self, numbers: list[str], *, include_detailed: bool = True) -> dict[str, FdxTrackInfo]:
        """一次 POST 查询 ≤30 个跟踪号，返回 {号: FdxTrackInfo}。

        单个号失踪（未在响应中）会作为 not_found 返回；HTTP/限流类错误抛 FedexTrackError。
        """
        nums = [str(n).strip().upper() for n in numbers if str(n).strip()]
        if not nums:
            return {}
        if len(nums) > MAX_NUMBERS_PER_REQUEST:
            raise ValueError(f"一次最多 {MAX_NUMBERS_PER_REQUEST} 个跟踪号，收到 {len(nums)}")
        token = self._ensure_token()
        body = {
            "trackingInfo": [{"trackingNumberInfo": {"trackingNumber": n}} for n in nums],
            "includeDetailedScans": include_detailed,
        }
        try:
            resp = self._client.post(f"{self._base}/track/v1/trackingnumbers", json=body,
                headers={"Authorization": f"Bearer {token}", "Content-Type": "application/json", "X-locale": "en_US"})
        except httpx.HTTPError as exc:
            raise FedexTrackError(f"FedEx track 请求失败: {exc}", category="transport", retriable=True) from exc
        payload = self._json_body(resp)
        if resp.status_code != 200:
            code, message = _first_error(payload)
            category, retriable = classify_http_error(resp.status_code, code)
            raise FedexTrackError(
                f"FedEx track 失败: {message or _text(code) or f'HTTP {resp.status_code}'}",
                http_status=resp.status_code, code=code, category=category, retriable=retriable)
        # 解析每个号
        result: dict[str, FdxTrackInfo] = {}
        seen: set[str] = set()
        for ctr in (payload.get("output", {}).get("completeTrackResults") or []):
            tn = _text(ctr.get("trackingNumber"))
            if not tn:
                continue
            seen.add(tn)
            for tr in (ctr.get("trackResults") or []):
                result[tn] = parse_track_result(tn, tr)
                break
            else:
                result[tn] = FdxTrackInfo(tracking_number=tn, not_found=True, raw=ctr)
        for n in nums:
            if n not in seen:
                result[n] = FdxTrackInfo(tracking_number=n, not_found=True, raw=payload)
        return result

    def track(self, number: str) -> FdxTrackInfo:
        return self.track_many([number])[number.strip().upper()]

    def _json_body(self, resp: httpx.Response) -> Any:
        try:
            return resp.json()
        except ValueError:
            return {"errors": [{"code": None, "message": resp.text[:500]}]}
