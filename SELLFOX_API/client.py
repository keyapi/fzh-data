"""Sellfox OpenAPI client (stdlib only).

Two access modes (prefer proxy when key is present):

1. **Proxy** — ``SELLFOX_PROXY_API_KEY`` → ``https://api.vilavi.cn/sellfox``
   (Bearer; proxy handles OAuth + HMAC).
2. **Direct** — ``SELLFOX_APP_ID`` + ``SELLFOX_APP_SECRET`` → ``openapi.sellfox.com``
   (client_credentials + HMAC-SHA256). Requires VPS whitelist IP.

Extracted for reuse by CLI scripts and Open WebUI Tools.
"""
from __future__ import annotations

import hashlib
import hmac
import json
import os
import random
import time
import urllib.error
import urllib.parse
import urllib.request
from dataclasses import dataclass
from datetime import datetime, timedelta
from pathlib import Path
from typing import Any, Callable, Dict, List, Optional, Tuple


SELLFOX_RATE_LIMIT_CODE = 40019


@dataclass
class RateLimitPolicy:
    max_retries: int = 6
    default_wait_s: float = 10.0
    jitter_s: float = 0.5

    @classmethod
    def from_env(cls) -> "RateLimitPolicy":
        def _int(name: str, default: int) -> int:
            raw = os.environ.get(name, "").strip()
            return int(raw) if raw.isdigit() else default

        def _float(name: str, default: float) -> float:
            raw = os.environ.get(name, "").strip()
            if not raw:
                return default
            try:
                return float(raw)
            except ValueError:
                return default

        return cls(
            max_retries=_int("SELLFOX_RATE_LIMIT_MAX_RETRIES", 6),
            default_wait_s=_float("SELLFOX_RATE_LIMIT_WAIT_S", 10.0),
            jitter_s=_float("SELLFOX_RATE_LIMIT_JITTER_S", 0.5),
        )


def parse_retry_after_seconds(
    *,
    detail: str | None = None,
    header: str | None = None,
) -> float | None:
    """Parse Retry-After from proxy detail text or HTTP header."""
    if header:
        header = header.strip()
        if header.isdigit():
            return max(float(header), 0.5)
        try:
            return max(
                (datetime.strptime(header, "%a, %d %b %Y %H:%M:%S GMT") - datetime.utcnow()).total_seconds(),
                0.5,
            )
        except ValueError:
            pass
    if detail and "Retry after" in detail:
        try:
            return max(float(detail.split("Retry after")[-1].strip().rstrip("s")), 0.5)
        except ValueError:
            pass
    return None


def is_rate_limited_response(result: dict[str, Any]) -> bool:
    detail = result.get("detail") if isinstance(result, dict) else None
    if isinstance(detail, str) and "Rate limited" in detail:
        return True
    return result.get("code") == SELLFOX_RATE_LIMIT_CODE


def rate_limit_sleep_seconds(
    result: dict[str, Any],
    *,
    attempt: int,
    policy: RateLimitPolicy,
    retry_after_header: str | None = None,
) -> float:
    detail = result.get("detail") if isinstance(result.get("detail"), str) else None
    retry_after = parse_retry_after_seconds(detail=detail, header=retry_after_header)
    if retry_after is not None:
        return retry_after + random.uniform(0, policy.jitter_s)
    return policy.default_wait_s + random.uniform(0, policy.jitter_s)


def load_env(paths: List[Path]) -> Dict[str, str]:
    env: Dict[str, str] = {}
    for path in paths:
        try:
            with open(path, encoding="utf-8") as f:
                for line in f:
                    line = line.strip()
                    if line and not line.startswith("#") and "=" in line:
                        k, v = line.split("=", 1)
                        env[k.strip()] = v.strip()
        except FileNotFoundError:
            pass
    env.update({k: v for k, v in os.environ.items() if v})
    return env


@dataclass
class SellfoxConfig:
    """Prefer proxy when ``proxy_api_key`` is set; else direct App ID/Secret."""

    mode: str = "direct"  # "proxy" | "direct"
    # Proxy (api.vilavi.cn/sellfox)
    proxy_base_url: str = "https://api.vilavi.cn/sellfox"
    proxy_account: str = "sellfox-main"
    proxy_api_key: str = ""
    # Direct (openapi.sellfox.com)
    app_id: str = ""
    app_secret: str = ""
    domain: str = "https://openapi.sellfox.com"

    @classmethod
    def from_env(cls, *extra_env_files: Path) -> "SellfoxConfig":
        here = Path(__file__).resolve().parent
        root = here.parent
        paths = [
            root / ".env",
            here / ".env",
            root / "advertise" / ".env",
            root / "ai_access_poc" / "open_webui" / ".env",
            *extra_env_files,
        ]
        env = load_env(paths)
        proxy_key = (
            env.get("SELLFOX_PROXY_API_KEY")
            or env.get("SELLFOX_API_KEY")
            or env.get("SAIFU_KEY")
            or ""
        ).strip()
        if proxy_key:
            return cls(
                mode="proxy",
                proxy_base_url=env.get(
                    "SELLFOX_PROXY_BASE_URL", "https://api.vilavi.cn/sellfox"
                ).rstrip("/"),
                proxy_account=env.get("SELLFOX_PROXY_ACCOUNT", "sellfox-main"),
                proxy_api_key=proxy_key,
            )
        app_id = env.get("SELLFOX_APP_ID", "")
        app_secret = env.get("SELLFOX_APP_SECRET", "")
        if not app_id or not app_secret:
            raise ValueError(
                "Prefer SELLFOX_PROXY_API_KEY (api.vilavi.cn/sellfox), "
                "or set SELLFOX_APP_ID + SELLFOX_APP_SECRET for direct OpenAPI"
            )
        return cls(
            mode="direct",
            app_id=app_id,
            app_secret=app_secret,
            domain=env.get("SELLFOX_API_DOMAIN", "https://openapi.sellfox.com").rstrip(
                "/"
            ),
        )


class SellfoxClient:
    """Minimal Sellfox client for read/report flows (proxy or direct)."""

    def __init__(self, config: SellfoxConfig, *, rate_limit: RateLimitPolicy | None = None):
        self.config = config
        self.access_token: Optional[str] = None
        self.rate_limit = rate_limit or RateLimitPolicy.from_env()

    def authenticate(self) -> Optional[str]:
        """Direct mode only. Proxy mode is a no-op (Bearer key is enough)."""
        if self.config.mode == "proxy":
            return None
        url = (
            f"{self.config.domain}/api/oauth/v2/token.json"
            f"?client_id={self.config.app_id}"
            f"&client_secret={self.config.app_secret}"
            f"&grant_type=client_credentials"
        )
        req = urllib.request.Request(url)
        with urllib.request.urlopen(req, timeout=15) as resp:
            data = json.loads(resp.read().decode("utf-8"))
        if data.get("code") != 0:
            raise RuntimeError(f"Token failed: {data}")
        self.access_token = data["data"]["access_token"]
        return self.access_token

    def _post_once_proxy(
        self, url_path: str, body: Optional[dict]
    ) -> tuple[dict[str, Any], str | None]:
        if not url_path.startswith("/"):
            url_path = "/" + url_path
        full_url = (
            f"{self.config.proxy_base_url}/v1/{self.config.proxy_account}{url_path}"
        )
        payload = json.dumps(body or {}).encode("utf-8")
        req = urllib.request.Request(
            full_url,
            data=payload,
            headers={
                "Content-Type": "application/json",
                "Authorization": f"Bearer {self.config.proxy_api_key}",
            },
            method="POST",
        )
        retry_after_header: str | None = None
        try:
            with urllib.request.urlopen(req, timeout=60) as resp:
                raw = resp.read().decode("utf-8")
                retry_after_header = resp.headers.get("Retry-After")
        except urllib.error.HTTPError as e:
            raw = e.read().decode("utf-8")
            retry_after_header = e.headers.get("Retry-After")
        try:
            result = json.loads(raw)
        except json.JSONDecodeError as e:
            raise RuntimeError(
                f"Non-JSON proxy response on {url_path}: {raw[:200]}"
            ) from e
        if not isinstance(result, dict):
            raise RuntimeError(f"Non-object proxy response on {url_path}: {raw[:200]}")
        return result, retry_after_header

    def _post_once_direct(self, url_path: str, body: Optional[dict]) -> dict[str, Any]:
        if not self.access_token:
            self.authenticate()
        ts = str(int(time.time() * 1000))
        nonce = str(random.randint(1, 99999))
        sign_params = {
            "access_token": self.access_token,
            "client_id": self.config.app_id,
            "method": "post",
            "nonce": nonce,
            "timestamp": ts,
            "url": url_path,
        }
        sorted_str = "&".join(f"{k}={v}" for k, v in sorted(sign_params.items()))
        sig = hmac.new(
            self.config.app_secret.encode(),
            sorted_str.encode(),
            hashlib.sha256,
        ).hexdigest()
        query = (
            f"access_token={self.access_token}&client_id={self.config.app_id}"
            f"&nonce={nonce}&timestamp={ts}&sign={sig}"
        )
        full_url = f"{self.config.domain}{url_path}?{query}"
        data_bytes = json.dumps(body or {}).encode("utf-8")
        req = urllib.request.Request(
            full_url,
            data=data_bytes,
            headers={"Content-Type": "application/json"},
            method="POST",
        )
        try:
            with urllib.request.urlopen(req, timeout=30) as resp:
                raw = resp.read().decode("utf-8")
        except urllib.error.HTTPError as e:
            raw = e.read().decode("utf-8")
        result = json.loads(raw)
        if not isinstance(result, dict):
            raise RuntimeError(f"Non-object direct response on {url_path}: {raw[:200]}")
        return result

    def _post_with_rate_limit_retry(
        self,
        url_path: str,
        body: Optional[dict],
        *,
        once: Callable[[], tuple[dict[str, Any], str | None] | dict[str, Any]],
    ) -> Any:
        last_err: Exception | None = None
        for attempt in range(self.rate_limit.max_retries):
            outcome = once()
            if isinstance(outcome, dict):
                result, retry_after_header = outcome, None
            else:
                result, retry_after_header = outcome
            if is_rate_limited_response(result):
                wait_s = rate_limit_sleep_seconds(
                    result,
                    attempt=attempt,
                    policy=self.rate_limit,
                    retry_after_header=retry_after_header,
                )
                time.sleep(wait_s)
                detail = result.get("detail") or result.get("msg") or result
                last_err = RuntimeError(f"Rate limited on {url_path}: {detail}")
                continue
            if result.get("code") != 0:
                raise RuntimeError(
                    f"API error on {url_path}: code={result.get('code')} "
                    f"msg={result.get('msg', result)}"
                )
            return result["data"]
        raise last_err or RuntimeError(f"Rate limited on {url_path} after retries")

    def _proxy_post(self, url_path: str, body: Optional[dict] = None) -> Any:
        return self._post_with_rate_limit_retry(
            url_path,
            body,
            once=lambda: self._post_once_proxy(url_path, body),
        )

    def _direct_post(self, url_path: str, body: Optional[dict] = None) -> Any:
        return self._post_with_rate_limit_retry(
            url_path,
            body,
            once=lambda: self._post_once_direct(url_path, body),
        )

    def signed_post(self, url_path: str, body: Optional[dict] = None) -> Any:
        """POST to Sellfox path (proxy Bearer or direct signed)."""
        if self.config.mode == "proxy":
            return self._proxy_post(url_path, body)
        return self._direct_post(url_path, body)

    def list_shops(self) -> List[dict]:
        data = self.signed_post("/api/shop/pageList.json", {"pageSize": 200})
        return data.get("rows") or []

    def resolve_shop(
        self,
        shop_id: Optional[str] = None,
        shop_name: Optional[str] = None,
    ) -> Tuple[str, str]:
        """Return (shop_id, shop_name)."""
        if shop_id:
            return str(shop_id), shop_name or str(shop_id)
        shops = self.list_shops()
        if not shops:
            raise RuntimeError("No shops found")
        if shop_name:
            matched = [
                s for s in shops if shop_name.lower() in (s.get("name") or "").lower()
            ]
            if not matched:
                raise RuntimeError(f"No shops matching '{shop_name}'")
            shops = matched
        shop = shops[0]
        return str(shop["id"]), str(shop.get("name") or shop["id"])

    def create_report_task(
        self,
        shop_id: str,
        report_type_code: str,
        start: str,
        end: str,
        ad_type_code: str = "sp",
        time_unit: str = "daily",
    ) -> str:
        data = self.signed_post(
            "/api/cpc/download/createTask.json",
            {
                "shopIds": [str(shop_id)],
                "adTypeCode": ad_type_code,
                "reportTypeCode": report_type_code,
                "timeUnit": time_unit,
                "reportStartDate": start,
                "reportEndDate": end,
            },
        )
        tid = data.get("id")
        if not tid:
            raise RuntimeError(f"createTask returned no id: {data}")
        return str(tid)

    def check_tasks(self, task_ids: List[str]) -> Dict[str, Tuple[str, dict]]:
        data = self.signed_post(
            "/api/cpc/download/pageList.json",
            {
                "taskIds": [str(t) for t in task_ids],
                "pageNo": 1,
                "pageSize": 50,
            },
        )
        result: Dict[str, Tuple[str, dict]] = {}
        for row in data.get("rows") or []:
            tid = row.get("id")
            state = row.get("reportState", "unknown")
            # Sellfox may return id as int — normalize keys to str
            result[str(tid)] = (state, row)
        return result

    def download_ready_task(
        self,
        *,
        shop_name: str,
        report_type_code: str,
        file_prefix: str,
        start_date: str,
        end_date: str,
        row: dict,
        out_dir: Path,
    ) -> dict:
        """Download a task that is already in 已生成 state."""
        urls = row.get("downloadUrl") or []
        if not urls:
            raise RuntimeError(f"Task done but no downloadUrl: {row}")
        safe_name = "".join(
            c if c.isalnum() or c in "-_" else "_" for c in shop_name
        )[:40]
        filepath = out_dir / f"{file_prefix}_{safe_name}_{start_date}_{end_date}.xlsx"
        size = self.download_file(urls[0], filepath)
        return {
            "ok": True,
            "mode": self.config.mode,
            "shop_name": shop_name,
            "report_type_code": report_type_code,
            "start_date": start_date,
            "end_date": end_date,
            "filepath": str(filepath),
            "bytes": size,
            "note": "Read-only pull.",
        }

    @staticmethod
    def download_file(url: str, filepath: Path) -> int:
        parts = urllib.parse.urlparse(url)
        encoded_path = urllib.parse.quote(parts.path, safe="/:@!$&()*+,;=")
        safe_url = parts._replace(path=encoded_path).geturl()
        req = urllib.request.Request(safe_url)
        with urllib.request.urlopen(req, timeout=120) as resp:
            content = resp.read()
        filepath.parent.mkdir(parents=True, exist_ok=True)
        filepath.write_bytes(content)
        return len(content)

    def pull_cpc_report(
        self,
        report_type_code: str,
        *,
        days: int = 7,
        shop_id: Optional[str] = None,
        shop_name: Optional[str] = None,
        out_dir: Path,
        file_prefix: str = "Report",
        ad_type_code: str = "sp",
        max_wait_s: int = 300,
        poll_s: int = 5,
    ) -> dict:
        """Create + poll + download a CPC download-center report. Read-only."""
        end_date = (datetime.now() - timedelta(days=1)).strftime("%Y-%m-%d")
        start_date = (datetime.now() - timedelta(days=days)).strftime("%Y-%m-%d")
        sid, sname = self.resolve_shop(shop_id=shop_id, shop_name=shop_name)
        tid = self.create_report_task(
            sid, report_type_code, start_date, end_date, ad_type_code=ad_type_code
        )
        pending = {tid}
        waited = 0
        while pending and waited < max_wait_s:
            time.sleep(poll_s)
            waited += poll_s
            results = self.check_tasks([tid])
            state, row = results.get(tid, ("unknown", {}))
            if state == "已生成":
                urls = row.get("downloadUrl") or []
                if not urls:
                    raise RuntimeError(f"Task done but no downloadUrl: {row}")
                safe_name = "".join(
                    c if c.isalnum() or c in "-_" else "_" for c in sname
                )[:40]
                filepath = out_dir / f"{file_prefix}_{safe_name}_{start_date}_{end_date}.xlsx"
                size = self.download_file(urls[0], filepath)
                pending.discard(tid)
                return {
                    "ok": True,
                    "mode": self.config.mode,
                    "shop_id": sid,
                    "shop_name": sname,
                    "task_id": tid,
                    "report_type_code": report_type_code,
                    "start_date": start_date,
                    "end_date": end_date,
                    "filepath": str(filepath),
                    "bytes": size,
                    "waited_s": waited,
                    "note": "Read-only pull.",
                }
            if state == "失败":
                raise RuntimeError(f"Report task failed: {row}")
        raise TimeoutError(
            f"{report_type_code} still pending after {waited}s task={tid}"
        )

    def pull_sp_search_term(
        self,
        *,
        days: int = 7,
        shop_id: Optional[str] = None,
        shop_name: Optional[str] = None,
        out_dir: Path,
        max_wait_s: int = 300,
        poll_s: int = 5,
    ) -> dict:
        """Create + poll + download SP search-term report. Read-only."""
        out = self.pull_cpc_report(
            "adSearchTermReport",
            days=days,
            shop_id=shop_id,
            shop_name=shop_name,
            out_dir=out_dir,
            file_prefix="SearchTerm",
            max_wait_s=max_wait_s,
            poll_s=poll_s,
        )
        out["note"] = "Read-only pull. Do not negate keywords automatically."
        return out