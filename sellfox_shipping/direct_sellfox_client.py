"""Direct Sellfox OpenAPI client with OAuth2 + HMAC-SHA256 signing.

No proxy — talks directly to https://openapi.sellfox.com.
"""

from __future__ import annotations

import hashlib
import hmac
import os
import random
import time
from threading import Lock

import httpx

from sellfox_shipping.package_models import (
    PackageRowError,
    SellfoxPackagePage,
)
from sellfox_shipping.sellfox_client import SellfoxApiError


class DirectSellfoxClient:
    """Sellfox OpenAPI client using OAuth2 client_credentials + HMAC signing."""

    def __init__(
        self,
        app_id: str | None = None,
        app_secret: str | None = None,
        api_domain: str | None = None,
        http_client: httpx.Client | None = None,
    ):
        self.app_id = app_id or os.getenv("SELLFOX_APP_ID", "").strip()
        self.app_secret = app_secret or os.getenv("SELLFOX_APP_SECRET", "").strip()
        self.api_domain = (
            api_domain
            or os.getenv("SELLFOX_API_DOMAIN", "https://openapi.sellfox.com").strip()
        ).rstrip("/")
        if not self.app_id or not self.app_secret:
            raise ValueError("SELLFOX_APP_ID and SELLFOX_APP_SECRET are required")
        self._client = http_client or httpx.Client(timeout=60)
        self._token: str | None = None
        self._token_expires_at: float = 0.0
        self._lock = Lock()

    # ── Token ──────────────────────────────────────────────────

    def _get_token(self) -> str:
        now = time.monotonic()
        if self._token and now < self._token_expires_at - 300:
            return self._token

        with self._lock:
            if self._token and now < self._token_expires_at - 300:
                return self._token
            token_url = f"{self.api_domain}/api/oauth/v2/token.json"
            resp = self._client.get(
                token_url,
                params={
                    "client_id": self.app_id,
                    "client_secret": self.app_secret,
                    "grant_type": "client_credentials",
                },
                timeout=15,
            )
            resp.raise_for_status()
            data = resp.json()
            if data.get("code") != 0:
                raise RuntimeError(f"Token refresh failed: {data}")
            self._token = str(data["data"]["access_token"])
            expires_ms = int(data["data"]["expires_in"])
            self._token_expires_at = time.monotonic() + (expires_ms / 1000)
            return self._token

    # ── Signing ────────────────────────────────────────────────

    def _compute_sign(self, url_path: str) -> dict[str, str]:
        access_token = self._get_token()
        ts = str(int(time.time() * 1000))
        nonce = str(random.randint(1, 99999))

        sign_params = {
            "access_token": access_token,
            "client_id": self.app_id,
            "method": "post",
            "nonce": nonce,
            "timestamp": ts,
            "url": url_path,
        }
        sorted_str = "&".join(f"{k}={v}" for k, v in sorted(sign_params.items()))
        sig = hmac.new(
            self.app_secret.encode(), sorted_str.encode(), hashlib.sha256
        ).hexdigest()

        return {
            "access_token": access_token,
            "client_id": self.app_id,
            "nonce": nonce,
            "timestamp": ts,
            "sign": sig,
        }

    # ── POST helper ────────────────────────────────────────────

    def _post(self, path: str, body: dict) -> dict:
        url = f"{self.api_domain}{path}"
        query = self._compute_sign(path)
        resp = self._client.post(url, params=query, json=body, timeout=60)
        self._ensure_http_ok(path, resp)
        data = resp.json()
        # Retry once on token expiry
        if data.get("code") == 40001:
            with self._lock:
                self._token = None
            query = self._compute_sign(path)
            resp = self._client.post(url, params=query, json=body, timeout=60)
            self._ensure_http_ok(path, resp)
            data = resp.json()
        return data

    @staticmethod
    def _ensure_http_ok(path: str, resp: httpx.Response) -> None:
        """Surface Sellfox's error body instead of losing it on raise_for_status()."""
        if resp.status_code >= 400:
            raise SellfoxApiError(
                f"Sellfox HTTP {resp.status_code} on {path}: {(resp.text or '')[:1000]}",
                status_code=resp.status_code,
            )

    # ── Package page gateway ───────────────────────────────────

    def fetch_package_page(
        self,
        *,
        date_start: str,
        date_end: str,
        status: str | None = None,
        shop_ids: list[str] | None = None,
        page_no: int = 1,
        page_size: int = 20,
    ) -> SellfoxPackagePage:
        from sellfox_shipping.sellfox_client import parse_sellfox_package

        body: dict[str, object] = {
            "purchaseDateStart": date_start,
            "purchaseDateEnd": date_end,
            "pageNo": str(page_no),
            "pageSize": str(page_size),
        }
        if status:
            body["packageStatus"] = status
        if shop_ids:
            body["shopIdList"] = shop_ids

        data = self._post("/api/packageShip/v1/getPackagePage.json", body)
        if data.get("code") != 0:
            raise RuntimeError(f"Sellfox API error: {data.get('msg', 'unknown')}")

        page = data.get("data", {})
        rows = page.get("rows", [])
        account_key = "sellfox-main"
        records = []
        errors = []
        for row_index, row in enumerate(rows, start=1):
            try:
                record = parse_sellfox_package(account_key, row)
                record.source_row_index = row_index
                records.append(record)
            except (AttributeError, TypeError, ValueError) as exc:
                package_sn = ""
                if isinstance(row, dict):
                    package_sn = str(row.get("packageSn") or "")
                errors.append(
                    PackageRowError(
                        row_index=row_index,
                        package_sn=package_sn,
                        reason=str(exc),
                    )
                )

        return SellfoxPackagePage(
            page_no=int(page.get("pageNo") or page_no),
            page_size=int(page.get("pageSize") or page_size),
            total_size=int(page.get("totalSize") or 0),
            records=records,
            errors=errors,
        )

    # ── Submit platform (write trackNo back to Sellfox) ───────

    def submit_to_platform(self, wire_body: dict) -> dict:
        """POST submitToPlatform with caller-built wire JSON."""
        return self._post("/api/packageShip/submitToPlatform.json", wire_body)

    def fetch_package_detail(self, package_sn: str) -> dict | None:
        """POST packageDetail; returns data object or None on soft failure."""
        sn = (package_sn or "").strip()
        if not sn:
            return None
        try:
            data = self._post(
                "/api/packageShip/v1/packageDetail.json",
                {"packageSn": sn},
            )
        except Exception:
            return None
        if data.get("code") != 0:
            return None
        return data.get("data") if isinstance(data, dict) else None
