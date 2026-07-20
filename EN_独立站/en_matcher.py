# -*- coding: utf-8 -*-
"""EN 系统匹配器：TT-SKU → 物料组。

匹配路径：
  TT-SKU
    → 调用 EN 系统 API: get_sku_item_itemgroup_mapping
    → API 内部通过 SQL 直查 tabItem Customer Detail
    → 返回 Item + Item Group 信息

API 由用户 Agent 在 EN 系统创建，支持批量查询。
"""

from __future__ import annotations

from typing import Any

from common.erpnext_client import ErpnextClient


class EnMatcher:
    """TT-SKU → EN 系统物料组匹配器。"""

    def __init__(self, client: ErpnextClient) -> None:
        self.client = client

    def load_all_skus(self, products: list[dict[str, Any]]) -> None:
        """从产品列表中提取所有 SKU，批量加载映射到缓存。

        只需调用一次，后续 match_by_tt_sku 走缓存 O(1) 查询。
        """
        all_skus = list({
            sku.strip()
            for prod in products
            for sku in prod.get("skus", [])
            if sku.strip()
        })
        self.client.load_sku_mappings(all_skus)

    def match_by_tt_sku(self, tt_sku: str) -> tuple[str | None, str | None]:
        """通过 TT-SKU 匹配到物料组。"""
        return self.client.find_item_group_by_tt_sku(tt_sku)

    def match_batch(self, products: list[dict[str, Any]],
                    progress_cb=None) -> list[dict[str, Any]]:
        """批量匹配产品列表。

        自动先批量加载所有 SKU 映射，然后逐产品匹配。
        """
        # 1. 批量加载所有 SKU → 缓存
        self.load_all_skus(products)

        # 2. 逐产品匹配（走缓存）
        results = []
        total = len(products)

        for i, prod in enumerate(products):
            matched_groups: set[str] = set()
            matched_items: set[str] = set()

            for sku in prod.get("skus", []):
                item_name, item_group = self.match_by_tt_sku(sku)
                if item_group:
                    matched_groups.add(item_group)
                    matched_items.add(item_name or "")

            if matched_groups:
                prod["match"] = {
                    "item_name": ", ".join(sorted(matched_items)),
                    "item_group": next(iter(matched_groups)),
                    "all_groups": sorted(matched_groups),
                }
                prod["match_status"] = "ok"
            else:
                prod["match"] = None
                prod["match_status"] = "no_match"

            results.append(prod)

            if progress_cb:
                progress_cb(i + 1, total)

        return results

    @property
    def cache_size(self) -> int:
        return len(self.client._sku_cache)
