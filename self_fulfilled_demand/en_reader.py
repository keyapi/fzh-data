# -*- coding: utf-8 -*-
"""EN（ERPNext）只读客户端。

只允许：
- ``GET /api/resource/<doctype>``（列表/单据）
- ``POST /api/method/frappe.client.get_count``（只读计数）

不提供任何写方法；``EnReadOnlyClient`` 里没有 PUT/POST 资源/删除的入口。
凭证只从已有配置读取（环境变量或 EN_API/.env），不打印、不落盘。
"""

from __future__ import annotations

import json
import os
import time
from pathlib import Path
from typing import Iterator, Sequence

import requests

from .config import ORDER_HEAD_FIELDS

DEFAULT_BASE_URL = "https://erpnext.vilavi.cn"
DEFAULT_ENV_CANDIDATES = [
    Path("EN_API/.env"),
    Path("D:/Work/赛狐/Cursor/EN_API/.env"),
]

RETRY_STATUS = {408, 417, 425, 429, 500, 502, 503, 504}


class EnReadError(RuntimeError):
    """读取失败（保留状态码，不含凭证）。"""

    def __init__(self, message: str, status: int | None = None, url: str | None = None):
        super().__init__(message)
        self.status = status
        self.url = url


class EnBudgetExhausted(EnReadError):
    """分页预算耗尽（max_pages / max_orders），结果不完整，必须按 partial 处理。"""

    def __init__(self, message: str, fetched: int, cursor: str):
        super().__init__(message)
        self.fetched = fetched
        self.cursor = cursor


def load_env(paths: Sequence[Path] | None = None) -> dict[str, str]:
    """读 .env（逐行 key=value，不执行、不 source）。

    优先级：进程环境变量 > 第一个存在的 .env 文件。
    文件按 UTF-8 读，容忍 BOM 与畸形行（跳过而不是执行）。
    """
    values: dict[str, str] = {}
    for path in list(paths or DEFAULT_ENV_CANDIDATES):
        p = Path(path)
        if not p.exists():
            continue
        text = p.read_text(encoding="utf-8-sig", errors="replace")
        for raw in text.splitlines():
            line = raw.strip()
            if not line or line.startswith("#") or "=" not in line:
                continue
            key, val = line.split("=", 1)
            key = key.strip()
            if not key or any(ch.isspace() for ch in key):
                continue
            values[key] = val.strip().strip('"').strip("'")
        break
    for key in ("ERP_API_KEY", "ERP_API_SECRET", "ERP_BASE_URL"):
        if os.environ.get(key):
            values[key] = os.environ[key]
    return values


class EnReadOnlyClient:
    def __init__(
        self,
        base_url: str | None = None,
        env_file: str | Path | None = None,
        timeout: int = 180,
        min_interval: float = 0.15,
        max_retries: int = 4,
    ):
        env = load_env([Path(env_file)] if env_file else None)
        self.base_url = (base_url or env.get("ERP_BASE_URL") or DEFAULT_BASE_URL).rstrip("/")
        key = env.get("ERP_API_KEY")
        secret = env.get("ERP_API_SECRET")
        if not key or not secret:
            raise EnReadError("缺少 ERP_API_KEY / ERP_API_SECRET（检查 EN_API/.env）")
        self._headers = {"Authorization": f"token {key}:{secret}"}
        self.timeout = timeout
        self.min_interval = min_interval
        self.max_retries = max_retries
        self._last_call = 0.0
        self.request_count = 0

    # -- 低层 ---------------------------------------------------------------
    def _throttle(self) -> None:
        wait = self.min_interval - (time.monotonic() - self._last_call)
        if wait > 0:
            time.sleep(wait)
        self._last_call = time.monotonic()

    def _request(self, method: str, path: str, **kwargs):
        if method != "GET":
            raise EnReadError("只读客户端拒绝非 GET 请求")
        url = f"{self.base_url}{path}"
        last_err: Exception | None = None
        for attempt in range(self.max_retries):
            self._throttle()
            try:
                resp = requests.request(
                    "GET", url, headers=self._headers, timeout=self.timeout, **kwargs
                )
                self.request_count += 1
                if resp.status_code == 200:
                    return resp
                if resp.status_code in RETRY_STATUS and attempt < self.max_retries - 1:
                    time.sleep(3 * (attempt + 1))
                    last_err = EnReadError(
                        f"HTTP {resp.status_code}", resp.status_code, url
                    )
                    continue
                raise EnReadError(
                    f"HTTP {resp.status_code}: {resp.text[:160]!r}",
                    resp.status_code,
                    url,
                )
            except requests.RequestException as exc:  # 网络层
                self.request_count += 1
                last_err = EnReadError(f"{type(exc).__name__}: {exc}", None, url)
                if attempt < self.max_retries - 1:
                    time.sleep(3 * (attempt + 1))
                    continue
        raise last_err or EnReadError("请求失败", None, url)

    # -- 公开只读 API --------------------------------------------------------
    def get_list(
        self,
        doctype: str,
        fields: Sequence[str],
        filters: Sequence | None = None,
        order_by: str | None = None,
        limit_start: int = 0,
        limit_page_length: int = 0,
    ) -> list[dict]:
        params = {
            "fields": json.dumps(list(fields), ensure_ascii=False),
            "limit_start": limit_start,
            "limit_page_length": limit_page_length,
        }
        if filters:
            params["filters"] = json.dumps(list(filters), ensure_ascii=False)
        if order_by:
            params["order_by"] = order_by
        resp = self._request("GET", f"/api/resource/{doctype.replace(' ', '%20')}", params=params)
        return resp.json().get("data", []) or []

    def count(self, doctype: str, filters: Sequence | None = None) -> int:
        # 只读计数；用 GET 走 /api/method 会 405，这里保持 POST 语义但仅此一个只读端点。
        url = f"{self.base_url}/api/method/frappe.client.get_count"
        payload = {"doctype": doctype, "filters": json.dumps(list(filters or []))}
        for attempt in range(self.max_retries):
            self._throttle()
            resp = requests.post(url, headers=self._headers, data=payload, timeout=self.timeout)
            self.request_count += 1
            if resp.status_code == 200:
                return int(resp.json().get("message", 0))
            if resp.status_code in RETRY_STATUS and attempt < self.max_retries - 1:
                time.sleep(3 * (attempt + 1))
                continue
            raise EnReadError(f"count HTTP {resp.status_code}", resp.status_code, url)
        raise EnReadError("count 失败", None, url)

    def get_doc(self, doctype: str, name: str) -> dict:
        from urllib.parse import quote

        resp = self._request("GET", f"/api/resource/{doctype.replace(' ', '%20')}/{quote(name, safe='')}")
        return resp.json().get("data", {})

    # -- 订单专用 ------------------------------------------------------------
    def iter_order_heads(
        self,
        cursor_field: str,
        cursor_start: str,
        until: str,
        extra_filters: Sequence | None = None,
        page_size: int = 500,
        max_orders: int = 50000,
        max_pages: int = 400,
    ) -> Iterator[list[dict]]:
        """按 ``cursor_field`` 键集分页取订单头（含 raw_data）。

        完整性保证
        - 排序用 ``(cursor_field, name)``，同一时间戳的多行不会乱序。
        - 用 ``>= cursor`` + 去重；当整页都停在同一时间戳（``max_cursor == cursor``）时，
          用 ``limit_start`` 在该时间戳桶内继续推进，不会漏行或死循环。
        - ``max_pages`` / ``max_orders`` 耗尽时抛 ``EnBudgetExhausted``，
          调用方必须标 partial 并阻止水位前进（不能静默结束）。
        """
        cursor = cursor_start
        offset = 0
        seen: set[str] = set()
        fetched = 0
        for page_no in range(max_pages + 1):
            if page_no >= max_pages:
                raise EnBudgetExhausted(
                    f"分页预算耗尽 max_pages={max_pages}（已取 {fetched} 单）", fetched, cursor
                )
            limit = min(page_size, max_orders - fetched)
            if limit <= 0:
                raise EnBudgetExhausted(
                    f"分页预算耗尽 max_orders={max_orders}（已取 {fetched} 单）", fetched, cursor
                )
            filters = list(extra_filters or [])
            filters += [
                ["Tongtool Order", cursor_field, ">=", cursor],
                ["Tongtool Order", cursor_field, "<=", until],
            ]
            rows = self.get_list(
                "Tongtool Order",
                ORDER_HEAD_FIELDS,
                filters=filters,
                order_by=f"{cursor_field} asc, name asc",
                limit_start=offset,
                limit_page_length=limit,
            )
            if not rows:
                return
            fresh = []
            for row in rows:
                if row["name"] not in seen:
                    seen.add(row["name"])
                    fresh.append(row)
            fetched += len(fresh)
            if fresh:
                yield fresh
            if len(rows) < limit:
                return
            new_cursor = max((r.get(cursor_field) or "") for r in rows)
            if new_cursor > cursor:
                # 跳过本页已消费的 new_cursor 同时间戳行，避免下一页重复占配额
                cursor = new_cursor
                offset = sum(1 for r in rows if (r.get(cursor_field) or "") == new_cursor)
            else:
                # 整页同一时间戳：在当前时间戳桶内向后推进
                offset += len(rows)

    def fetch_children(
        self,
        names: Sequence[str],
        child_field: str,
        child_fields: Sequence[str],
        batch_size: int = 50,
    ) -> list[dict]:
        """批量取子表行（``order_items`` / ``packages``）。

        Frappe 列表接口带子表字段时返回「父字段 + 子字段」扁平行；
        这里按 ``name in [...]`` 精确取，避免分页错位。
        """
        out: list[dict] = []
        names = list(dict.fromkeys(names))
        for i in range(0, len(names), batch_size):
            batch = names[i : i + batch_size]
            rows = self.get_list(
                "Tongtool Order",
                ["name"] + [f"{child_field}.{f}" for f in child_fields],
                filters=[["Tongtool Order", "name", "in", batch]],
                limit_page_length=0,
            )
            out.extend(rows)
        return out
