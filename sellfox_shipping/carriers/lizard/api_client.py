"""蜴国际 logistics API httpx client (thin adapter; Excel remains production default).

Uses **sync** ``httpx.Client`` — same stack as Sellfox/VITE/ERPNext in this repo.
Async is available in httpx but not why we chose it; Service/CLI today are sync.

Credentials via env only — never hardcode. Docs: ``yiglobal-api/`` on main (PR #90/#91; was 蜴国际-API).
"""

from __future__ import annotations

import os
from typing import Any

import httpx


DEFAULT_BASE = "http://47.106.72.196"

# Pinned field paths from yiglobal-api/docs/api-reference.md (createOrder / getLabel).
# Primary: result.labels.{tracking_number,label_url}
# Fallback: same keys on result root (some live responses omit nesting).


def _env_first(*names: str, default: str = "") -> str:
    for name in names:
        val = (os.getenv(name) or "").strip()
        if val:
            return val
    return default


def _as_dict(value: Any) -> dict[str, Any]:
    return value if isinstance(value, dict) else {}


def _pick_str(*candidates: Any) -> str:
    for c in candidates:
        if c is None:
            continue
        s = str(c).strip()
        if s:
            return s
    return ""


def parse_create_order_result(payload: dict[str, Any]) -> dict[str, str]:
    """Extract order_code / tracking_number / label_url from createOrder JSON.

    Canonical shape (api-reference)::

        result.order_code
        result.labels.tracking_number
        result.labels.label_url
    """
    result = _as_dict(payload.get("result"))
    labels = _as_dict(result.get("labels"))
    return {
        "order_code": _pick_str(result.get("order_code"), payload.get("order_code")),
        "tracking_number": _pick_str(
            labels.get("tracking_number"),
            result.get("tracking_number"),
        ),
        "label_url": _pick_str(
            labels.get("label_url"),
            result.get("label_url"),
        ),
        "file_type": _pick_str(labels.get("file_type"), result.get("file_type")),
    }


def parse_get_label_result(payload: dict[str, Any]) -> dict[str, Any]:
    """Extract tracking / label URL / sync flags from getLabel JSON.

    When ready (code=200), tracking and PDF match createOrder ``labels`` shape.
    Also surfaces ``sync_service_status`` / ``order_status`` / ``logistics_err``.
    """
    result = _as_dict(payload.get("result"))
    labels = _as_dict(result.get("labels"))
    return {
        "code": payload.get("code"),
        "sync_service_status": result.get("sync_service_status"),
        "order_status": result.get("order_status"),
        "logistics_err": result.get("logistics_err"),
        "tracking_number": _pick_str(
            labels.get("tracking_number"),
            result.get("tracking_number"),
        ),
        "label_url": _pick_str(
            labels.get("label_url"),
            result.get("label_url"),
        ),
        "file_type": _pick_str(labels.get("file_type"), result.get("file_type")),
        "label_ready": (
            payload.get("code") in (200, "200")
            and result.get("sync_service_status") in (1, "1")
        ),
    }


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
            app_token=_env_first("YIGLOBAL_APP_TOKEN", "LIZARD_APP_TOKEN", "LIZARD_TOKEN"),
            app_key=_env_first("YIGLOBAL_APP_KEY", "LIZARD_APP_KEY", "LIZARD_KEY"),
            base_url=_env_first(
                "YIGLOBAL_API_BASE_URL",
                "LIZARD_API_BASE_URL",
                default=DEFAULT_BASE,
            ),
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
