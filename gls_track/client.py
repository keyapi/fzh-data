"""GLS 波兰公开 REST 客户端（httpx；无需账号/凭据）。

端点（实测 2026-09-07，宿主 gls-group.com，实例 /PL/en/）：
- 摘要：GET /app/service/open/rest/PL/en/rstt029?match={no}&type=&caller=witt002&millis={ms}
- 明细：GET /app/service/open/rest/PL/en/rstt028/{no}?caller=witt002&millis={ms}&postalCode={zip}

明细需目的邮编（页面在收货人侧用它做校验）；有邮编时一个明细调用即可拿全量
history + status（不必先摘要）。无邮编退化为摘要（只有状态/交付时间）。
"""

from __future__ import annotations

import os
import time
from typing import Any

import httpx

from .models import GlsParcel, parse_detail, parse_summary

DEFAULT_BASE = "https://gls-group.com/app/service/open/rest/PL/en"
DEFAULT_CALLER = "witt002"


class GlsTrackError(Exception):
    """GLS 查询失败。category ∈ {not_found, invalid, rate_limit, transport, other}。"""

    def __init__(
        self,
        message: str,
        *,
        http_status: int | None = None,
        category: str = "other",
        retriable: bool = False,
    ):
        super().__init__(message)
        self.message = message
        self.http_status = http_status
        self.category = category
        self.retriable = retriable

    def __str__(self) -> str:  # pragma: no cover - 调试友好
        bits = [self.message]
        if self.http_status:
            bits.append(f"http={self.http_status}")
        bits.append(f"category={self.category}")
        return " ".join(bits)


class GlsTrackClient:
    """GLS 公开 REST 客户端。无需任何凭证。

    Parameters
    ----------
    base_url : 公开 REST 前缀，默认波兰实例。
    caller : 页面 tracking widget 的应用标识（witt002）；如非必需可传 ''。
    timeout / transport : transport 仅供测试注入 ``httpx.MockTransport``。
    """

    def __init__(
        self,
        *,
        base_url: str = DEFAULT_BASE,
        caller: str = DEFAULT_CALLER,
        timeout: float = 30.0,
        proxy: str | None = None,
        transport: httpx.BaseTransport | None = None,
    ):
        self._base = (base_url or DEFAULT_BASE).rstrip("/")
        self._caller = caller
        kw: dict[str, Any] = {"timeout": timeout}
        if transport is not None and proxy:
            raise ValueError("transport 与 proxy 不能同时指定")
        if transport is not None:
            kw["transport"] = transport
        if proxy:
            kw["proxy"] = proxy
        self._client = httpx.Client(**kw)

    def close(self) -> None:
        self._client.close()

    def __enter__(self) -> "GlsTrackClient":
        return self

    def __exit__(self, *args: object) -> None:
        self.close()

    @classmethod
    def from_env(cls) -> "GlsTrackClient":
        return cls(base_url=os.getenv("GLS_BASE_URL", DEFAULT_BASE), proxy=os.getenv("GLS_HTTP_PROXY") or None)

    def _common_params(self) -> dict[str, str]:
        params: dict[str, str] = {"millis": str(int(time.time() * 1000))}
        if self._caller:
            params["caller"] = self._caller
        return params

    def summary(self, parcel_no: str) -> GlsParcel:
        number = (parcel_no or "").strip()
        if not number:
            raise ValueError("parcel_no is required")
        params = {"match": number, "type": ""}
        params.update(self._common_params())
        body = self._get("rstt029", params=params)
        return parse_summary(number, body)

    def detail(self, parcel_no: str, postal_code: str) -> GlsParcel:
        number = (parcel_no or "").strip()
        postal = (postal_code or "").strip()
        if not number:
            raise ValueError("parcel_no is required")
        if not postal:
            raise ValueError("postal_code is required for detail (GLS 收货人侧校验)")
        params = {"postalCode": postal}
        params.update(self._common_params())
        body = self._get(f"rstt028/{number}", params=params)
        return parse_detail(number, body)

    def track(self, parcel_no: str, postal_code: str | None = None) -> GlsParcel:
        """有邮编走明细（全量 history）；无邮编走摘要（状态/交付时间）。"""
        if postal_code and (postal_code or "").strip():
            return self.detail(parcel_no, postal_code)
        return self.summary(parcel_no)

    # ── 内部 ─────────────────────────────────────────────────
    def _get(self, path: str, *, params: dict[str, str]) -> Any:
        url = f"{self._base}/{path}"
        try:
            resp = self._client.get(url, params=params)
        except httpx.HTTPError as exc:
            raise GlsTrackError(f"GLS track 请求失败: {exc}", category="transport", retriable=True) from exc
        try:
            body = resp.json()
        except ValueError:
            body = None
        if resp.status_code != 200:
            err = None
            if isinstance(body, dict):
                err = _text(body.get("exceptionText"))
            msg = err or f"HTTP {resp.status_code}"
            category = "not_found" if resp.status_code in (404,) else "other"
            raise GlsTrackError(
                f"GLS track {path} 失败: {msg}",
                http_status=resp.status_code, category=category,
                retriable=resp.status_code in (429, 500, 502, 503, 504),
            )
        return body


def _text(v: Any) -> str | None:
    if v is None:
        return None
    s = str(v).strip()
    return s or None
