"""VITE / GOFO Express httpx client (P1C spike — test env only).

Units: lbs + inches. Auth: ``x-api-key`` header.
Does not replace Tongtu production. Credentials via env only — never hardcode.
Docs: origin/main ``vite-api/`` (PR #88/#89).
"""

from __future__ import annotations

import os
from typing import Any

import httpx


DEFAULT_TEST_BASE = "https://test-api.vitedirect.com"


class ViteClientError(RuntimeError):
    def __init__(self, message: str, *, status_code: int | None = None):
        super().__init__(message)
        self.status_code = status_code


class ViteGofoClient:
    """Minimal GOFO Express adapter: rate + create shipment + get label."""

    def __init__(
        self,
        *,
        api_key: str,
        base_url: str = DEFAULT_TEST_BASE,
        timeout: float = 30.0,
        transport: httpx.BaseTransport | None = None,
    ):
        key = (api_key or "").strip()
        if not key:
            raise ValueError("VITE api_key is required")
        self._base = base_url.rstrip("/")
        self._client = httpx.Client(
            base_url=self._base,
            headers={
                "x-api-key": key,
                "Content-Type": "application/json",
            },
            timeout=timeout,
            transport=transport,
        )

    def close(self) -> None:
        self._client.close()

    def __enter__(self) -> ViteGofoClient:
        return self

    def __exit__(self, *args: object) -> None:
        self.close()

    @classmethod
    def from_env(cls) -> ViteGofoClient:
        return cls(
            api_key=os.getenv("VITE_API_KEY", ""),
            base_url=os.getenv("VITE_API_BASE_URL", DEFAULT_TEST_BASE),
        )

    def rate_gofo(self, body: dict[str, Any]) -> dict[str, Any]:
        return self._post_json("/rate2/gofo", body)

    def create_shipment_gofo(self, body: dict[str, Any]) -> dict[str, Any]:
        return self._post_json("/shipment2/gofo", body)

    def get_label(self, order_id: str) -> list[dict[str, Any]]:
        """GET label; official success body is a JSON array of label objects."""
        oid = (order_id or "").strip()
        if not oid:
            raise ValueError("order_id is required")
        data = self._request_json("GET", f"/shipment2/label/{oid}")
        if isinstance(data, list):
            return [item for item in data if isinstance(item, dict)]
        if isinstance(data, dict):
            return [data]
        raise ViteClientError("VITE label response is neither list nor object")

    def _post_json(self, path: str, body: dict[str, Any]) -> dict[str, Any]:
        data = self._request_json("POST", path, body=body)
        if not isinstance(data, dict):
            raise ViteClientError("VITE response is not a JSON object")
        return data

    def _request_json(
        self,
        method: str,
        path: str,
        *,
        body: dict[str, Any] | None = None,
    ) -> Any:
        kwargs: dict[str, Any] = {}
        if body is not None:
            kwargs["json"] = body
        resp = self._client.request(method, path, **kwargs)
        if resp.status_code == 401:
            raise ViteClientError("invalid x-api-key", status_code=401)
        if resp.status_code >= 400:
            raise ViteClientError(
                f"VITE HTTP {resp.status_code}: {resp.text[:500]}",
                status_code=resp.status_code,
            )
        return resp.json()