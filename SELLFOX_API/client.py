"""Sellfox OpenAPI client (stdlib only).

Extracted for reuse by CLI scripts and Open WebUI Tools.
Auth: OAuth client_credentials + HMAC-SHA256 request signing.
Same contract as SELLFOX_API/fetch_ad_reports.py.
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
from typing import Any, Dict, List, Optional, Tuple


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
    app_id: str
    app_secret: str
    domain: str = "https://openapi.sellfox.com"

    @classmethod
    def from_env(cls, *extra_env_files: Path) -> "SellfoxConfig":
        here = Path(__file__).resolve().parent
        root = here.parent
        paths = [here / ".env", root / "advertise" / ".env", *extra_env_files]
        env = load_env(paths)
        app_id = env.get("SELLFOX_APP_ID", "")
        app_secret = env.get("SELLFOX_APP_SECRET", "")
        if not app_id or not app_secret:
            raise ValueError(
                "SELLFOX_APP_ID and SELLFOX_APP_SECRET required "
                "(SELLFOX_API/.env or environment)"
            )
        return cls(
            app_id=app_id,
            app_secret=app_secret,
            domain=env.get("SELLFOX_API_DOMAIN", "https://openapi.sellfox.com").rstrip("/"),
        )


class SellfoxClient:
    """Minimal Sellfox OpenAPI client for read/report flows."""

    def __init__(self, config: SellfoxConfig):
        self.config = config
        self.access_token: Optional[str] = None

    def authenticate(self) -> str:
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

    def signed_post(self, url_path: str, body: Optional[dict] = None) -> Any:
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
        if result.get("code") != 0:
            raise RuntimeError(
                f"API error on {url_path}: code={result.get('code')} "
                f"msg={result.get('msg', result)}"
            )
        return result["data"]

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
            matched = [s for s in shops if shop_name.lower() in (s.get("name") or "").lower()]
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
            result[tid] = (state, row)
        return result

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
        end_date = (datetime.now() - timedelta(days=1)).strftime("%Y-%m-%d")
        start_date = (datetime.now() - timedelta(days=days)).strftime("%Y-%m-%d")
        sid, sname = self.resolve_shop(shop_id=shop_id, shop_name=shop_name)
        tid = self.create_report_task(
            sid, "adSearchTermReport", start_date, end_date
        )
        pending = {tid}
        waited = 0
        filepath: Optional[Path] = None
        while pending and waited < max_wait_s:
            time.sleep(poll_s)
            waited += poll_s
            results = self.check_tasks([tid])
            state, row = results.get(tid, ("unknown", {}))
            if state == "已生成":
                urls = row.get("downloadUrl") or []
                if not urls:
                    raise RuntimeError(f"Task done but no downloadUrl: {row}")
                filepath = out_dir / f"SearchTerm_{sname}_{start_date}_{end_date}.xlsx"
                size = self.download_file(urls[0], filepath)
                pending.discard(tid)
                return {
                    "ok": True,
                    "shop_id": sid,
                    "shop_name": sname,
                    "task_id": tid,
                    "start_date": start_date,
                    "end_date": end_date,
                    "filepath": str(filepath),
                    "bytes": size,
                    "waited_s": waited,
                    "note": "Read-only pull. Do not negate keywords automatically.",
                }
            if state == "失败":
                raise RuntimeError(f"Report task failed: {row}")
        raise TimeoutError(f"Search-term report still pending after {waited}s task={tid}")
