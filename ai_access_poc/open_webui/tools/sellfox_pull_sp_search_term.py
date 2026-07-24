"""
title: Sellfox SP Search Term Pull
author: fzh-data
version: 0.3.0
license: MIT
description: Read-only — pull SP search-term report via Sellfox proxy (preferred) or direct OpenAPI, and return a text summary for analysis. No ad write operations.
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
from typing import Any, Optional

from pydantic import BaseModel, Field


def _summarize_search_term_xlsx(filepath: Path, top_n: int = 20) -> dict[str, Any]:
    """Parse Sellfox SP search-term xlsx into totals + top search terms (for LLM text)."""
    try:
        import pandas as pd
    except ImportError as e:
        return {"ok": False, "error": f"pandas not available: {e}"}

    try:
        df = pd.read_excel(filepath)
    except Exception as e:
        return {"ok": False, "error": f"failed to read xlsx: {e}"}

    if df.empty:
        return {"ok": True, "rows": 0, "totals": {}, "top_by_spend": [], "note": "empty report"}

    # Expected Chinese column names from Sellfox SP search-term export
    col_map = {
        "term": "用户搜索词",
        "spend": "广告花费",
        "impr": "广告曝光量",
        "clicks": "广告点击量",
        "sales": "广告销售额",
        "orders": "广告订单量",
        "acos": "ACoS",
        "roas": "ROAS",
        "cpc": "CPC",
        "shop": "店铺",
        "date": "日期",
    }
    missing = [v for v in ("用户搜索词", "广告花费") if v not in df.columns]
    if missing:
        return {
            "ok": False,
            "error": f"unexpected columns, missing {missing}",
            "columns": [str(c) for c in df.columns],
        }

    for key in ("spend", "impr", "clicks", "sales", "orders", "acos", "roas", "cpc"):
        c = col_map[key]
        if c in df.columns:
            df[c] = pd.to_numeric(df[c], errors="coerce").fillna(0)

    spend_c, sales_c, orders_c = col_map["spend"], col_map["sales"], col_map["orders"]
    clicks_c, impr_c = col_map["clicks"], col_map["impr"]
    term_c = col_map["term"]

    totals = {
        "rows": int(len(df)),
        "spend": round(float(df[spend_c].sum()), 2),
        "sales": round(float(df[sales_c].sum()), 2) if sales_c in df.columns else None,
        "orders": int(df[orders_c].sum()) if orders_c in df.columns else None,
        "clicks": int(df[clicks_c].sum()) if clicks_c in df.columns else None,
        "impressions": int(df[impr_c].sum()) if impr_c in df.columns else None,
    }
    if totals["spend"] and totals.get("sales") is not None:
        totals["acos"] = round(totals["spend"] / totals["sales"], 4) if totals["sales"] else None
        totals["roas"] = round(totals["sales"] / totals["spend"], 4) if totals["spend"] else None

    agg_map = {spend_c: "sum"}
    if clicks_c in df.columns:
        agg_map[clicks_c] = "sum"
    if sales_c in df.columns:
        agg_map[sales_c] = "sum"
    if orders_c in df.columns:
        agg_map[orders_c] = "sum"
    if impr_c in df.columns:
        agg_map[impr_c] = "sum"

    g = (
        df.groupby(term_c, as_index=False)
        .agg(agg_map)
        .rename(
            columns={
                spend_c: "spend",
                clicks_c: "clicks",
                sales_c: "sales",
                orders_c: "orders",
                impr_c: "impressions",
            }
        )
        .sort_values("spend", ascending=False)
        .head(int(top_n))
    )
    top = []
    for _, r in g.iterrows():
        spend = float(r.get("spend", 0) or 0)
        sales = float(r.get("sales", 0) or 0) if "sales" in g.columns else 0.0
        top.append(
            {
                "search_term": str(r[term_c]),
                "spend": round(spend, 2),
                "sales": round(sales, 2),
                "orders": int(r["orders"]) if "orders" in g.columns else None,
                "clicks": int(r["clicks"]) if "clicks" in g.columns else None,
                "impressions": int(r["impressions"]) if "impressions" in g.columns else None,
                "acos": round(spend / sales, 4) if sales else None,
            }
        )
    # CSV block the model can quote directly (UTF-8 text, not binary xlsx)
    csv_lines = ["search_term,spend,sales,orders,clicks,impressions,acos"]
    for t in top:
        csv_lines.append(
            f"{t['search_term']},{t['spend']},{t['sales']},{t['orders']},"
            f"{t['clicks']},{t['impressions']},{t['acos']}"
        )

    return {
        "ok": True,
        "rows": totals["rows"],
        "totals": totals,
        "top_by_spend": top,
        "top_by_spend_csv": "\n".join(csv_lines),
        "analysis_hint": (
            "Use totals + top_by_spend_csv for analysis. "
            "Do NOT claim you cannot read xlsx — summary is already in this JSON. "
            "READ-ONLY: do not auto-negate keywords."
        ),
    }


# --- Inlined Sellfox client (same contract as SELLFOX_API/client.py) ---


class _Sellfox:
    """mode=proxy (Bearer via api.vilavi.cn/sellfox) or mode=direct (App ID/Secret)."""

    def __init__(
        self,
        *,
        mode: str,
        proxy_base_url: str = "https://api.vilavi.cn/sellfox",
        proxy_account: str = "sellfox-main",
        proxy_api_key: str = "",
        app_id: str = "",
        app_secret: str = "",
        domain: str = "https://openapi.sellfox.com",
    ):
        self.mode = mode
        self.proxy_base_url = proxy_base_url.rstrip("/")
        self.proxy_account = proxy_account
        self.proxy_api_key = proxy_api_key
        self.app_id = app_id
        self.app_secret = app_secret
        self.domain = domain.rstrip("/")
        self.access_token: Optional[str] = None

    def authenticate(self) -> Optional[str]:
        if self.mode == "proxy":
            return None
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
        if self.mode == "proxy":
            return self._proxy_post(url_path, body)
        return self._direct_post(url_path, body)

    def _proxy_post(self, url_path: str, body: Optional[dict] = None):
        if not url_path.startswith("/"):
            url_path = "/" + url_path
        full_url = f"{self.proxy_base_url}/v1/{self.proxy_account}{url_path}"
        payload = json.dumps(body or {}).encode("utf-8")
        last_err = None
        for attempt in range(6):
            req = urllib.request.Request(
                full_url,
                data=payload,
                headers={
                    "Content-Type": "application/json",
                    "Authorization": f"Bearer {self.proxy_api_key}",
                },
                method="POST",
            )
            try:
                with urllib.request.urlopen(req, timeout=60) as resp:
                    raw = resp.read().decode("utf-8")
            except urllib.error.HTTPError as e:
                raw = e.read().decode("utf-8")
            result = json.loads(raw)
            detail = result.get("detail") if isinstance(result, dict) else None
            if isinstance(detail, str) and "Rate limited" in detail:
                wait_s = 1.0 + attempt
                if "Retry after" in detail:
                    try:
                        wait_s = float(detail.split("Retry after")[-1].strip().rstrip("s"))
                        wait_s = max(wait_s, 0.5) + 0.2
                    except ValueError:
                        pass
                time.sleep(wait_s)
                last_err = RuntimeError(f"Rate limited: {detail}")
                continue
            if result.get("code") != 0:
                raise RuntimeError(
                    f"API error {url_path}: code={result.get('code')} msg={result.get('msg', result)}"
                )
            return result["data"]
        raise last_err or RuntimeError(f"Rate limited on {url_path}")

    def _direct_post(self, url_path: str, body: Optional[dict] = None):
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
        SELLFOX_PROXY_API_KEY: str = Field(
            default="",
            description="Preferred: Bearer key from https://api.vilavi.cn/sellfox/admin",
        )
        SELLFOX_PROXY_BASE_URL: str = Field(
            default="https://api.vilavi.cn/sellfox",
            description="Sellfox corporate proxy base",
        )
        SELLFOX_PROXY_ACCOUNT: str = Field(
            default="sellfox-main",
            description="Proxy account slug",
        )
        SELLFOX_APP_ID: str = Field(
            default="",
            description="Fallback direct OpenAPI App ID (VPS whitelist only)",
        )
        SELLFOX_APP_SECRET: str = Field(
            default="",
            description="Fallback direct OpenAPI App Secret (VPS whitelist only)",
        )
        SELLFOX_API_DOMAIN: str = Field(
            default="https://openapi.sellfox.com",
            description="Direct OpenAPI domain",
        )
        REPORT_DIR: str = Field(
            default="/data/sellfox_reports",
            description="Directory inside Open WebUI container for xlsx output",
        )
        MAX_WAIT_S: int = Field(default=300, description="Max seconds to poll report task")
        DEFAULT_DAYS: int = Field(default=7, description="Default lookback days if days omitted")
        SUMMARY_TOP_N: int = Field(
            default=20, description="How many top search terms to include in text summary"
        )

    def __init__(self):
        self.valves = self.Valves()

    def _client(self) -> _Sellfox:
        proxy_key = (
            self.valves.SELLFOX_PROXY_API_KEY
            or os.environ.get("SELLFOX_PROXY_API_KEY", "")
            or os.environ.get("SELLFOX_API_KEY", "")
            or os.environ.get("SAIFU_KEY", "")
        ).strip()
        if proxy_key:
            return _Sellfox(
                mode="proxy",
                proxy_base_url=self.valves.SELLFOX_PROXY_BASE_URL
                or os.environ.get("SELLFOX_PROXY_BASE_URL", "https://api.vilavi.cn/sellfox"),
                proxy_account=self.valves.SELLFOX_PROXY_ACCOUNT
                or os.environ.get("SELLFOX_PROXY_ACCOUNT", "sellfox-main"),
                proxy_api_key=proxy_key,
            )
        app_id = self.valves.SELLFOX_APP_ID or os.environ.get("SELLFOX_APP_ID", "")
        app_secret = self.valves.SELLFOX_APP_SECRET or os.environ.get(
            "SELLFOX_APP_SECRET", ""
        )
        domain = self.valves.SELLFOX_API_DOMAIN or os.environ.get(
            "SELLFOX_API_DOMAIN", "https://openapi.sellfox.com"
        )
        if not app_id or not app_secret:
            raise RuntimeError(
                "Configure Valves SELLFOX_PROXY_API_KEY (preferred, from "
                "https://api.vilavi.cn/sellfox/admin) or fallback "
                "SELLFOX_APP_ID / SELLFOX_APP_SECRET. Do not ask end users for secrets."
            )
        return _Sellfox(
            mode="direct",
            app_id=app_id,
            app_secret=app_secret,
            domain=domain,
        )

    def sellfox_pull_sp_search_term(
        self,
        days: Optional[int] = None,
        shop_id: Optional[str] = None,
        shop_name: Optional[str] = None,
    ) -> str:
        """
        Pull a Sellfox SP search-term report (read-only), save as xlsx, and
        return a JSON text summary (totals + top search terms CSV) so the
        assistant can analyze without opening the binary xlsx.

        Prefer corporate proxy (SELLFOX_PROXY_API_KEY). Ask the user for shop
        name or shop id if unknown. Never create/modify campaigns, keywords,
        or negative keywords.

        :param days: Lookback days (default from Valves, typically 7)
        :param shop_id: Sellfox shop id (preferred if known)
        :param shop_name: Substring match on shop name if shop_id omitted
        :return: JSON string with filepath + summary for analysis
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
                safe_name = "".join(c if c.isalnum() or c in "-_" else "_" for c in sname)[:40]
                fpath = out_dir / f"SearchTerm_{safe_name}_{start_date}_{end_date}.xlsx"
                size = client.download(urls[0], fpath)
                summary = _summarize_search_term_xlsx(
                    fpath, top_n=int(self.valves.SUMMARY_TOP_N)
                )
                return json.dumps(
                    {
                        "ok": True,
                        "mode": client.mode,
                        "shop_id": sid,
                        "shop_name": sname,
                        "task_id": tid,
                        "start_date": start_date,
                        "end_date": end_date,
                        "filepath": str(fpath),
                        "bytes": size,
                        "waited_s": waited,
                        "summary": summary,
                        "warning": (
                            "READ-ONLY. Do not auto-negate keywords. "
                            "Analyze from summary / top_by_spend_csv only."
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

    def sellfox_summarize_search_term_xlsx(self, filepath: str) -> str:
        """
        Summarize an already-downloaded Sellfox SP search-term xlsx into
        totals + top search terms (text/CSV). Use this when the file path is
        known but you need analysis text (xlsx alone is not readable in chat).

        :param filepath: Absolute path inside container, e.g. /data/sellfox_reports/...
        :return: JSON string with summary
        """
        path = Path(filepath)
        if not path.is_file():
            # Also try under REPORT_DIR by basename
            alt = Path(self.valves.REPORT_DIR) / path.name
            if alt.is_file():
                path = alt
            else:
                return json.dumps(
                    {"ok": False, "error": f"file not found: {filepath}"},
                    ensure_ascii=False,
                )
        summary = _summarize_search_term_xlsx(path, top_n=int(self.valves.SUMMARY_TOP_N))
        return json.dumps(
            {"ok": bool(summary.get("ok")), "filepath": str(path), "summary": summary},
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
        return json.dumps(
            {"ok": True, "mode": client.mode, "count": len(slim), "shops": slim},
            ensure_ascii=False,
        )
