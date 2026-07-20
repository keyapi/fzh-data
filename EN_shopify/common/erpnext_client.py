# -*- coding: utf-8 -*-
"""ERPNext REST API 客户端。

复用自 EN_API/restructure_prod_full.py 的 ErpnextClient，
包含 nginx 417 Expect 头处理 + 自动重试。
"""

from __future__ import annotations

import json
import time
from pathlib import Path
from typing import Any
from urllib.parse import quote

import requests
from requests.adapters import HTTPAdapter

import urllib3
from urllib3.connectionpool import HTTPConnectionPool

# ── urllib3 全局补丁 — 阻止 nginx 417 Expectation Failed ──
_orig_make_request = HTTPConnectionPool._make_request

def _patched_make_request(self, conn, method, url, body=None, headers=None, *args, **kw):
    if headers and "Expect" in headers:
        del headers["Expect"]
    return _orig_make_request(self, conn, method, url, body, headers, *args, **kw)

HTTPConnectionPool._make_request = _patched_make_request


class _NoExpectAdapter(HTTPAdapter):
    """发送前从 PreparedRequest 剥离 Expect 头。"""
    def send(self, request, **kwargs):
        request.headers.pop("Expect", None)
        return super().send(request, **kwargs)


class ErpnextClient:
    """ERPNext REST API 客户端。"""

    def __init__(self, base_url: str, api_key: str, api_secret: str,
                 label: str = "") -> None:
        self.base_url = base_url.rstrip("/")
        self.label = label or base_url
        self.session = requests.Session()
        self.session.headers["Authorization"] = f"token {api_key}:{api_secret}"
        self.session.mount("https://", _NoExpectAdapter())
        self.session.mount("http://", _NoExpectAdapter())
        # 用于缓存已加载的 SKU 映射
        self._sku_cache: dict[str, dict[str, str]] = {}

    # ── 通用请求 ──────────────────────────────────────

    def _request(self, method: str, url: str, *,
                 retries: int = 3, retry_delay: float = 3.0,
                 **kwargs) -> requests.Response:
        """带重试的 HTTP 请求。"""
        timeout = kwargs.pop("timeout", (60, 180))
        last = None
        for a in range(retries + 1):
            try:
                r = self.session.request(method, url, timeout=timeout, **kwargs)
                r.raise_for_status()
                return r
            except requests.RequestException as e:
                last = e
                status = getattr(getattr(e, "response", None), "status_code", 0)
                if status in (500, 502, 503, 504, 417, 408) and a < retries:
                    delay = retry_delay * (a + 1) * 2
                    print(f"    [RETRY {a+1}/{retries}] HTTP {status}, 等待 {delay:.0f}s...")
                    time.sleep(delay)
                elif isinstance(e, (requests.exceptions.ConnectTimeout,
                                    requests.exceptions.ConnectionError,
                                    requests.exceptions.SSLError)):
                    if a < retries:
                        delay = retry_delay * (a + 1)
                        print(f"    [RETRY {a+1}/{retries}] {type(e).__name__}, 等待 {delay:.0f}s...")
                        time.sleep(delay)
                    else:
                        raise
                elif a < retries:
                    time.sleep(retry_delay)
        raise last  # type: ignore[misc]

    def _get(self, resource: str, docname: str | None = None,
             filters: list | None = None, fields: list[str] | None = None,
             params: dict | None = None) -> dict[str, Any]:
        """GET 资源列表 或 单个文档。"""
        if docname is not None:
            url = f"{self.base_url}/api/resource/{resource}/{quote(docname, safe='')}"
        else:
            url = f"{self.base_url}/api/resource/{resource}"
        p = params or {}
        if fields:
            p["fields"] = json.dumps(fields)
        if filters:
            p["filters"] = json.dumps(filters)
        resp = self._request("GET", url, params=p)
        return resp.json()

    def _put(self, resource: str, docname: str,
             data: dict[str, Any]) -> dict[str, Any]:
        """PUT 更新文档。"""
        url = f"{self.base_url}/api/resource/{resource}/{quote(docname, safe='')}"
        resp = self._request("PUT", url, json=data)
        return resp.json()

    # ── TT-SKU 映射 API ────────────────────────────

    API_PATH = "vilavi_pim.api.pim_api.get_sku_item_itemgroup_mapping"

    def load_sku_mappings(self, skus: list[str],
                          force_refresh: bool = False) -> dict[str, dict[str, str]]:
        """通过 EN 系统 API 批量查询 SKU → 物料组 映射。

        调用 Server Script 自定义端点批量查询，避免遍历所有 Item。
        API 内部使用 SQL 直查 tabItem Customer Detail，不受子表权限限制。

        Args:
            skus: SKU 列表（如 TT0031038K0062927）
            force_refresh: 是否强制重新拉取（跳过缓存）

        Returns:
            {sku: {"item_name": ..., "item_code": ..., "item_group": ..., "item_group_url": ...}}
        """
        # 过滤掉已在缓存中的 SKU
        skus_to_query = [s for s in skus if s not in self._sku_cache]
        if not skus_to_query and not force_refresh:
            return self._sku_cache

        url = f"{self.base_url}/api/method/{self.API_PATH}"
        print(f"  [API] 查询 {len(skus_to_query)} 个 SKU 的物料组映射...")

        # 方法1: 调用自定义 API
        try:
            resp = self._request("POST", url,
                                 json={"skus": skus_to_query},
                                 retries=1, retry_delay=2,
                                 timeout=(60, 300))
            result = resp.json()
            result = resp.json()
            message = result.get("message", {})

            # 提取结果
            for item in message.get("results", []):
                sku = item.get("sku", "").strip()
                if sku:
                    self._sku_cache[sku] = {
                        "item_name": item.get("item_name", ""),
                        "item_code": item.get("item_code", ""),
                        "item_group": item.get("item_group", ""),
                        "customer_name": item.get("customer_name", ""),
                        "item_group_url": item.get("item_group_url", ""),
                    }

            not_found = message.get("not_found", [])
            if not_found:
                for sku in not_found:
                    self._sku_cache[sku] = {}  # 标记为已查询但未找到

            total = message.get("total", 0)
            print(f"  [API] 成功: {total} 条, 未找到: {len(not_found)} 个")
            return self._sku_cache

        except Exception as e:
            err = getattr(e, "response", None)
            err_body = err.text if err else ""
            status = err.status_code if err else 0

            if status == 417 and "module not found" in err_body.lower():
                print(f"  [WARN] API 端点不存在 (需在 EN 系统创建 {self.API_PATH})")
                print(f"  [FALLBACK] 使用批量遍历方式查找...")
                self._fallback_build_index(skus_to_query)
            elif status == 404:
                print(f"  [ERROR] API 端点不存在: {self.API_PATH}")
            else:
                detail = err_body[:200] if err else str(e)
                print(f"  [ERROR] 查询失败: {detail}")

        return self._sku_cache

    def _fallback_build_index(self, skus: list[str]) -> None:
        """降级方案：遍历所有 Item 构建索引（API 不可用时）。

        当自定义 API 不存在时使用此方法。
        遍历约 14,756 个 Item，耗时 3-8 分钟。
        """
        from concurrent.futures import ThreadPoolExecutor, as_completed

        sku_set = set(skus)
        print(f"  [FALLBACK] 获取 Item 列表...")
        try:
            data = self._get("Item", fields=["name", "item_code", "item_group"],
                             params={"limit_page_length": "0"})
            items = data.get("data", [])
        except Exception as e:
            print(f"  [FALLBACK] 获取 Item 列表失败: {e}")
            return

        total = len(items)
        found = 0

        def _fetch(item_info: dict) -> list[tuple[str, dict]]:
            try:
                full = self._get("Item", docname=item_info["name"],
                                 fields=["name", "item_code", "item_group",
                                         "customer_items"])
                d = full.get("data", {})
                results = []
                for ci in (d.get("customer_items") or []):
                    ref = (ci.get("ref_code") or "").strip()
                    if ref in sku_set:
                        results.append((ref, {
                            "item_name": d.get("name", ""),
                            "item_code": d.get("item_code", ""),
                            "item_group": d.get("item_group", ""),
                        }))
                return results
            except Exception:
                return []

        t0 = time.time()
        done = 0
        with ThreadPoolExecutor(max_workers=8) as pool:
            fut_map = {pool.submit(_fetch, it): it["name"] for it in items}
            for fut in as_completed(fut_map):
                done += 1
                if done % 2000 == 0:
                    elapsed = time.time() - t0
                    rate = done / elapsed if elapsed > 0 else 0
                    eta = (total - done) / rate if rate > 0 else 0
                    print(f"    {done}/{total} ({done/total*100:.0f}%), "
                          f"{rate:.0f} 条/秒, 剩余约 {eta:.0f}s")
                for ref, info in fut.result():
                    if ref not in self._sku_cache:
                        self._sku_cache[ref] = info
                        found += 1

        elapsed = time.time() - t0
        print(f"  [FALLBACK] 完成: 找到 {found} 个 SKU 映射, "
              f"耗时 {elapsed:.0f}s")

    def find_item_group_by_tt_sku(
        self, tt_sku: str
    ) -> tuple[str | None, str | None]:
        """从已加载的缓存中查找 SKU 对应的 (item_name, item_group)。"""
        info = self._sku_cache.get(tt_sku.strip(), {})
        if info and info.get("item_group"):
            return info.get("item_name"), info.get("item_group")
        return None, None

    # ── Item Group 更新 ─────────────────────────────

    def update_daneey_urls(self, ig_name: str,
                           html_content: str) -> bool:
        """更新物料组的 daneey_product_details 字段。"""
        try:
            self._put("Item Group", ig_name,
                      data={"daneey_product_details": html_content})
            return True
        except Exception as e:
            print(f"    [ERROR] 更新 {ig_name} 失败: {e}")
            return False

    def clear_daneey_urls(self, ig_name: str) -> bool:
        """清空物料组的 daneey_product_details 字段。"""
        return self.update_daneey_urls(ig_name, "")

    def find_groups_with_daneey_urls(self) -> list[str]:
        """查询所有已填写 daneey_product_details 的物料组名称。"""
        try:
            data = self._get(
                "Item Group",
                filters=[["Item Group", "daneey_product_details", "!=", ""]],
                fields=["item_group_name"],
                params={"limit_page_length": "0"},
            )
            return [d.get("item_group_name", "")
                    for d in data.get("data", []) if d.get("item_group_name")]
        except Exception as e:
            print(f"  [ERROR] 查询已有 daneey_product_details 物料组失败: {e}")
            return []
