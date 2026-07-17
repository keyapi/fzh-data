"""蜴国际 logistics API httpx client (thin adapter; Excel remains production default).

Uses **sync** ``httpx.Client`` — same stack as Sellfox/VITE/ERPNext in this repo.
Async is available in httpx but not why we chose it; Service/CLI today are sync.

Credentials via env only — never hardcode. Docs: origin/main ``蜴国际-API/`` (PR #90/#91).
"""

from __future__ import annotations

import os
from typing import Any

import httpx


DEFAULT_BASE = "http://47.106.72.196"


class LizardApiError(RuntimeError):
    def __init__(
        self,
        message: str,
        *,
        status_code: int | None = None,
        business_code: Any = None,
    ):
        super().__init__(message)
        self.status_code = status_code
        self.business_code = business_code


class LizardApiClient:
    """Minimal API: token, ratesv2, createOrder, getLabel, cancelOrder."""

    def __init__(
        self,
        *,
        app_token: str,
        app_key: str,
        base_url: str = DEFAULT_BASE,
        timeout: float = 30.0,
        transport: httpx.BaseTransport | None = None,
        access_token: str | None = None,
    ):
        token = (app_token or "").strip()
        key = (app_key or "").strip()
        if not token or not key:
            raise ValueError("Lizard app_token and app_key are required")
        self._app_token = token
        self._app_key = key
        self._base = base_url.rstrip("/")
        self._access_token = (access_token or "").strip() or None
        self._client = httpx.Client(
            base_url=self._base,
            timeout=timeout,
            transport=transport,
        )

    def close(self) -> None:
        self._client.close()

    def __enter__(self) -> LizardApiClient:
        return self

    def __exit__(self, *args: object) -> None:
        self.close()

    @classmethod
    def from_env(cls) -> LizardApiClient:
        return cls(
            app_token=os.getenv("LIZARD_APP_TOKEN", ""),
            app_key=os.getenv("LIZARD_APP_KEY", ""),
            base_url=os.getenv("LIZARD_API_BASE_URL", DEFAULT_BASE),
        )

    def get_token(self, *, force: bool = False) -> str:
        if self._access_token and not force:
            return self._access_token
        resp = self._client.post(
            "/api/svc/getToken",
            data={"app_token": self._app_token, "app_key": self._app_key},
            headers={"Content-Type": "application/x-www-form-urlencoded"},
        )
        data = self._parse_http(resp)
        result = data.get("result") if isinstance(data, dict) else None
        access = ""
        if isinstance(result, dict):
            access = str(result.get("access_token") or "").strip()
        if not access:
            raise LizardApiError("getToken missing access_token", business_code=data.get("code"))
        self._access_token = access
        return access

    def ratesv2(self, body: dict[str, Any]) -> dict[str, Any]:
        return self._post_auth_json("/api/svc/ratesv2", body)

    def create_order(self, body: dict[str, Any]) -> dict[str, Any]:
        return self._post_auth_json("/api/svc/createOrder", body)

    def get_label(self, *, order_code: str, reference_no: str) -> dict[str, Any]:
        """POST getLabel. reference_no must match createOrder exactly."""
        oc = (order_code or "").strip()
        ref = (reference_no or "").strip()
        if not oc or not ref:
            raise ValueError("order_code and reference_no are required")
        return self._post_auth_json(
            "/api/svc/getLabel",
            {"order_code": oc, "reference_no": ref},
        )

    def cancel_order(self, *, order_code: str, reference_no: str) -> dict[str, Any]:
        oc = (order_code or "").strip()
        ref = (reference_no or "").strip()
        if not oc or not ref:
            raise ValueError("order_code and reference_no are required")
        return self._post_auth_json(
            "/api/svc/cancelOrder",
            {"order_code": oc, "reference_no": ref},
        )

    def _post_auth_json(self, path: str, body: dict[str, Any]) -> dict[str, Any]:
        access = self.get_token()
        resp = self._client.post(
            path,
            json=body,
            headers={
                "Authorization": access,
                "Content-Type": "application/json",
            },
        )
        if resp.status_code == 401:
            # Token expired — refresh once.
            access = self.get_token(force=True)
            resp = self._client.post(
                path,
                json=body,
                headers={
                    "Authorization": access,
                    "Content-Type": "application/json",
                },
            )
        return self._parse_business(resp)

    def _parse_http(self, resp: httpx.Response) -> dict[str, Any]:
        if resp.status_code >= 400:
            raise LizardApiError(
                f"Lizard HTTP {resp.status_code}: {resp.text[:500]}",
                status_code=resp.status_code,
            )
        data = resp.json()
        if not isinstance(data, dict):
            raise LizardApiError("Lizard response is not a JSON object")
        return data

    def _parse_business(self, resp: httpx.Response) -> dict[str, Any]:
        data = self._parse_http(resp)
        code = data.get("code")
        # 200 success; 202 getLabel still processing (caller may poll).
        if code in (200, "200", 202, "202"):
            return data
        if code in (401, "401"):
            raise LizardApiError(
                f"Lizard auth error: {data.get('msg')!r}",
                status_code=resp.status_code,
                business_code=code,
            )
        raise LizardApiError(
            f"Lizard business error code={code!r} msg={data.get('msg')!r}",
            status_code=resp.status_code,
            business_code=code,
        )
