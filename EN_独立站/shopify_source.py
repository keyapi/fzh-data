# -*- coding: utf-8 -*-
"""独立站数据源适配器。

支持两种数据源模式：
  1. CSV 文件读取（初始导入）—— Shopify 标准导出格式
  2. Shopify API 拉取（增量维护）—— /products.json

两种模式输出统一格式的 product dict 列表。
"""

from __future__ import annotations

import csv
import time
from dataclasses import dataclass, field, asdict
from typing import Any

import requests


@dataclass
class Product:
    """统一产品数据结构。"""
    handle: str = ""
    title: str = ""
    url: str = ""
    skus: list[str] = field(default_factory=list)
    variants: list[dict[str, str]] = field(default_factory=list)
    images: list[str] = field(default_factory=list)
    product_category: str = ""
    seo_title: str = ""
    seo_description: str = ""

    def to_dict(self) -> dict[str, Any]:
        return asdict(self)


def from_csv(filepath: str, store_url: str = "https://daneey.com") -> list[dict[str, Any]]:
    """从 Shopify 标准导出 CSV 读取产品数据。

    Args:
        filepath: CSV 文件路径
        store_url: 独立站域名（用于构建产品 URL）

    Returns:
        产品 dict 列表，统一格式
    """
    products: dict[str, Product] = {}

    with open(filepath, encoding="utf-8") as f:
        reader = csv.DictReader(f)
        for row in reader:
            handle = row.get("Handle", "").strip()
            if not handle:
                continue

            # 首次遇到此 Handle 时创建产品记录
            if handle not in products:
                products[handle] = Product(
                    handle=handle,
                    title=row.get("Title", "").strip(),
                    url=f"{store_url.rstrip('/')}/products/{handle}",
                    product_category=row.get("Product Category", "").strip(),
                    seo_title=row.get("SEO Title", "").strip(),
                    seo_description=row.get("SEO Description", "").strip(),
                )

            p = products[handle]

            # 收集 SKU（有值才算变体行）
            sku = row.get("Variant SKU", "").strip()
            if sku:
                if sku not in p.skus:
                    p.skus.append(sku)
                p.variants.append({
                    "sku": sku,
                    "price": row.get("Variant Price", "").strip(),
                    "option1_name": row.get("Option1 Name", "").strip(),
                    "option1_value": row.get("Option1 Value", "").strip(),
                })

            # 收集图片
            img = row.get("Image Src", "").strip()
            if img and img not in p.images:
                p.images.append(img)

    return [p.to_dict() for p in products.values()]


def from_api(store_url: str = "https://daneey.com",
             max_products: int | None = None) -> list[dict[str, Any]]:
    """从 Shopify Products API 拉取实时产品数据。

    Args:
        store_url: 独立站域名
        max_products: 最大拉取数（None=全部）

    Returns:
        产品 dict 列表
    """
    base = store_url.rstrip("/")
    products: dict[str, Product] = {}
    page = 1
    limit = 250  # Shopify 每页最大 250

    while True:
        url = f"{base}/products.json?limit={limit}&page={page}"
        print(f"  [API] 拉取第 {page} 页...")
        resp = requests.get(url, timeout=30)
        resp.raise_for_status()
        data = resp.json().get("products", [])

        if not data:
            break

        for item in data:
            handle = item.get("handle", "").strip()
            if not handle:
                continue

            p = Product(
                handle=handle,
                title=item.get("title", "").strip(),
                url=f"{base}/products/{handle}",
                seo_title=item.get("seo_title", "").strip() if item.get("seo_title") else "",
                seo_description=item.get("seo_description", "").strip() if item.get("seo_description") else "",
            )

            # 收集变体 SKU
            for v in item.get("variants", []):
                sku = (v.get("sku") or "").strip()
                if sku:
                    if sku not in p.skus:
                        p.skus.append(sku)
                    p.variants.append({
                        "sku": sku,
                        "price": str(v.get("price", "")),
                        "option1_name": "",
                        "option1_value": v.get("option1", ""),
                    })

            # 收集图片
            for img in item.get("images", []):
                src = img.get("src", "").strip()
                if src and src not in p.images:
                    p.images.append(src)

            products[handle] = p

        page += 1

        if max_products and len(products) >= max_products:
            break

        # 避免请求过快
        time.sleep(0.3)

    return [p.to_dict() for p in products.values()]


def print_stats(products: list[dict[str, Any]]) -> None:
    """打印产品统计信息。"""
    total = len(products)
    multi_sku = sum(1 for p in products if len(p["skus"]) > 1)
    total_skus = sum(len(p["skus"]) for p in products)
    tt_skus = sum(
        1 for p in products for s in p["skus"] if s.startswith("TT")
    )
    print(f"  产品总数: {total}")
    print(f"  多变体产品: {multi_sku}")
    print(f"  SKU总数: {total_skus}")
    print(f"  TT前缀SKU: {tt_skus}")
