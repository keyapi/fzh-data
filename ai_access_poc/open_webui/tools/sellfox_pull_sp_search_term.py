"""
title: Sellfox SP Search Term Pull
author: fzh-data
version: 0.1.0
license: MIT
description: Read-only — pull SP search-term report from Sellfox OpenAPI (createTask → download xlsx). No ad write operations.
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
from datetime import datetime, timedelta
from pathlib import Path
from typing import Optional

from pydantic import BaseModel, Field


# --- Inlined Sellfox client (same contract as SELLFOX_API/client.py) ---


class _Sellfox:
    def __init__(self, app_id: str, app_secret: str, domain: str):
        self.app_id = app_id
        self.app_secret = app_secret
        self.domain = domain.rstrip("/")
        self.access_token: Optional[str] = None

    def authenticate(self) -> str:
        url = (
            f"{self.domain}/api/oauth/v2/token.json"
            f"?client_id={self.app_id}&client_secret={self.app_secret}"
            f"&grant_type=client_credentials"
        )
        with urllib.request.urlopen(urllib.request.Request(url), timeout=15) as resp:
            data = json.loads(resp.read().decode("utf-8"))
        if data.get("code") != 0:
            raise RuntimeError(f"Token failed: {data}")
        self.access_token = data["data"]["access_token"]
        return self.access_token

    def signed_post(self, url_path: str, body: Optional[dict] = None):
        if not self.access_token:
            self.authenticate()
        ts = str(int(time.time() * 1000))
        nonce = str(random.randint(1, 99999))
        sign_params = {
            "access_token": self.access_token,
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
        query = (
            f"access_token={self.access_token}&client_id={self.app_id}"
            f"&nonce={nonce}&timestamp={ts}&sign={sig}"
        )
        full_url = f"{self.domain}{url_path}?{query}"
        req = urllib.request.Request(
            full_url,
            data=json.dumps(body or {}).encode("utf-8"),
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
                f"API error {url_path}: code={result.get('code')} msg={result.get('msg', result)}"
            )
        return result["data"]

    def list_shops(self):
        return self.signed_post("/api/shop/pageList.json", {"pageSize": 200}).get("rows") or []

    def resolve_shop(self, shop_id: Optional[str], shop_name: Optional[str]):
        if shop_id:
            return str(shop_id), shop_name or str(shop_id)
        shops = self.list_shops()
        if not shops:
            raise RuntimeError("No shops found")
        if shop_name:
            shops = [s for s in shops if shop_name.lower() in (s.get("name") or "").lower()]
            if not shops:
                raise RuntimeError(f"No shops matching '{shop_name}'")
        shop = shops[0]
        return str(shop["id"]), str(shop.get("name") or shop["id"])

    def create_search_term_task(self, shop_id: str, start: str, end: str) -> str:
        data = self.signed_post(
            "/api/cpc/download/createTask.json",
            {
                "shopIds": [str(shop_id)],
                "adTypeCode": "sp",
                "reportTypeCode": "adSearchTermReport",
                "timeUnit": "daily",
                "reportStartDate": start,
                "reportEndDate": end,
            },
        )
        tid = data.get("id")
        if not tid:
            raise RuntimeError(f"createTask no id: {data}")
        return str(tid)

    def check_task(self, task_id: str):
        data = self.signed_post(
            "/api/cpc/download/pageList.json",
            {"taskIds": [str(task_id)], "pageNo": 1, "pageSize": 50},
        )
        for row in data.get("rows") or []:
            if str(row.get("id")) == str(task_id):
                return row.get("reportState", "unknown"), row
        return "unknown", {}

    @staticmethod
    def download(url: str, filepath: Path) -> int:
        parts = urllib.parse.urlparse(url)
        encoded_path = urllib.parse.quote(parts.path, safe="/:@!$&()*+,;=")
        safe_url = parts._replace(path=encoded_path).geturl()
        with urllib.request.urlopen(urllib.request.Request(safe_url), timeout=120) as resp:
            content = resp.read()
        filepath.parent.mkdir(parents=True, exist_ok=True)
        filepath.write_bytes(content)
        return len(content)


class Tools:
    class Valves(BaseModel):
        SELLFOX_APP_ID: str = Field(
            default="", description="Sellfox OpenAPI App ID (server-side only)"
        )
        SELLFOX_APP_SECRET: str = Field(
            default="", description="Sellfox OpenAPI App Secret (server-side only)"
        )
        SELLFOX_API_DOMAIN: str = Field(
            default="https://openapi.sellfox.com",
            description="Sellfox API domain (or corporate proxy base if applicable)",
        )
        REPORT_DIR: str = Field(
            default="/data/sellfox_reports",
            description="Directory inside Open WebUI container for xlsx output",
        )
        MAX_WAIT_S: int = Field(default=300, description="Max seconds to poll report task")
        DEFAULT_DAYS: int = Field(default=7, description="Default lookback days if days omitted")

    def __init__(self):
        self.valves = self.Valves()

    def _client(self) -> _Sellfox:
        app_id = self.valves.SELLFOX_APP_ID or os.environ.get("SELLFOX_APP_ID", "")
        app_secret = self.valves.SELLFOX_APP_SECRET or os.environ.get(
            "SELLFOX_APP_SECRET", ""
        )
        domain = self.valves.SELLFOX_API_DOMAIN or os.environ.get(
            "SELLFOX_API_DOMAIN", "https://openapi.sellfox.com"
        )
        if not app_id or not app_secret:
            raise RuntimeError(
                "Configure Valves SELLFOX_APP_ID / SELLFOX_APP_SECRET "
                "(admin only). Do not ask end users for secrets."
            )
        return _Sellfox(app_id, app_secret, domain)

    def sellfox_pull_sp_search_term(
        self,
        days: Optional[int] = None,
        shop_id: Optional[str] = None,
        shop_name: Optional[str] = None,
    ) -> str:
        """
        Pull a Sellfox SP search-term report (read-only) and save as xlsx.

        Ask the user for shop name or shop id if unknown. Never create/modify
        campaigns, keywords, or negative keywords — Sellfox has no ad write API
        in this PoC and this tool must stay read-only.

        :param days: Lookback days (default from Valves, typically 7)
        :param shop_id: Sellfox shop id (preferred if known)
        :param shop_name: Substring match on shop name if shop_id omitted
        :return: JSON string with task_id, filepath, shop info
        """
        days_i = int(days if days is not None else self.valves.DEFAULT_DAYS)
        if days_i < 1 or days_i > 90:
            return json.dumps({"ok": False, "error": "days must be 1..90"}, ensure_ascii=False)

        client = self._client()
        end_date = (datetime.now() - timedelta(days=1)).strftime("%Y-%m-%d")
        start_date = (datetime.now() - timedelta(days=days_i)).strftime("%Y-%m-%d")
        sid, sname = client.resolve_shop(shop_id=shop_id, shop_name=shop_name)
        tid = client.create_search_term_task(sid, start_date, end_date)

        out_dir = Path(self.valves.REPORT_DIR)
        waited = 0
        poll = 5
        max_wait = int(self.valves.MAX_WAIT_S)
        while waited < max_wait:
            time.sleep(poll)
            waited += poll
            state, row = client.check_task(tid)
            if state == "已生成":
                urls = row.get("downloadUrl") or []
                if not urls:
                    return json.dumps(
                        {"ok": False, "error": "done but no downloadUrl", "row": row},
                        ensure_ascii=False,
                    )
                # sanitize filename fragment
                safe_name = "".join(c if c.isalnum() or c in "-_" else "_" for c in sname)[:40]
                fpath = out_dir / f"SearchTerm_{safe_name}_{start_date}_{end_date}.xlsx"
                size = client.download(urls[0], fpath)
                return json.dumps(
                    {
                        "ok": True,
                        "shop_id": sid,
                        "shop_name": sname,
                        "task_id": tid,
                        "start_date": start_date,
                        "end_date": end_date,
                        "filepath": str(fpath),
                        "bytes": size,
                        "waited_s": waited,
                        "warning": (
                            "READ-ONLY. Do not auto-negate keywords. "
                            "Hand analysis / ops review only."
                        ),
                    },
                    ensure_ascii=False,
                )
            if state == "失败":
                return json.dumps(
                    {"ok": False, "error": "task failed", "row": row},
                    ensure_ascii=False,
                )

        return json.dumps(
            {
                "ok": False,
                "error": f"timeout after {waited}s",
                "task_id": tid,
                "shop_id": sid,
            },
            ensure_ascii=False,
        )

    def sellfox_list_shops(self) -> str:
        """
        List Sellfox shops (id + name). Read-only helper before pulling reports.

        :return: JSON string with shops array
        """
        client = self._client()
        shops = client.list_shops()
        slim = [
            {
                "id": s.get("id"),
                "name": s.get("name"),
                "marketplaceId": s.get("marketplaceId"),
                "region": s.get("region"),
                "adStatus": s.get("adStatus"),
            }
            for s in shops
        ]
        return json.dumps({"ok": True, "count": len(slim), "shops": slim}, ensure_ascii=False)
