# -*- coding: utf-8 -*-
"""EN 系统写入器：将独立站产品链接写入物料组的 daneey_product_details 字段。

写入规则：
  - 同一物料组关联的多个产品，合并为一个 HTML 列表写入
  - HTML 格式便于在 ERPNext 页面直接展示为可点击链接
"""

from __future__ import annotations

from collections import defaultdict
from typing import Any

from common.erpnext_client import ErpnextClient


class EnWriter:
    """物料组 daneey_product_details 写入器。"""

    def __init__(self, client: ErpnextClient) -> None:
        self.client = client
        self.stats = {
            "成功更新": 0,
            "更新失败": 0,
            "跳过(无匹配)": 0,
        }

    def group_by_item_group(
        self, matched_products: list[dict[str, Any]]
    ) -> dict[str, list[dict[str, Any]]]:
        """将匹配成功的产品按物料组分组。"""
        groups: dict[str, list[dict[str, Any]]] = defaultdict(list)
        for prod in matched_products:
            ig = prod.get("match", {}).get("item_group")
            if ig:
                groups[ig].append(prod)
        return dict(groups)

    def build_html(self, products: list[dict[str, Any]]) -> str:
        """为同一物料组的产品列表生成 HTML。"""
        parts = [
            '<div class="daneey-products" style="margin-top:8px;">'
        ]
        for prod in products:
            title = prod.get("title", "Unknown")
            url = prod.get("url", "#")
            skus = ", ".join(prod.get("skus", []))
            parts.append(
                f'  <div style="margin-bottom:8px;">'
                f'<span style="font-weight:bold;">独立站详情链接：</span>'
                f'<a href="{url}" target="_blank" rel="noopener">{title}</a>'
                f'<br><span style="color:#666;font-size:12px;">SKU: {skus}</span>'
                f'</div>'
            )
        parts.append("</div>")
        return "\n".join(parts)

    def write_all(self, matched_products: list[dict[str, Any]],
                  dry_run: bool = False,
                  write_env: str = "") -> list[dict[str, Any]]:
        """全量覆盖写入：匹配的写入，不匹配的历史数据清空。

        Args:
            matched_products: 匹配成功（match_status="ok"）的产品列表
            dry_run: True=只预览不写入
            write_env: 写入环境标签（用于提示）

        Returns:
            操作日志列表
        """
        groups = self.group_by_item_group(matched_products)
        log: list[dict[str, Any]] = []

        print(f"\n── {'预览' if dry_run else '写入'}物料组 daneey_product_details ──")
        print(f"  本次匹配物料组: {len(groups)} 个")

        # ── 更新匹配到的物料组 ──
        for ig_name, products in sorted(groups.items()):
            html = self.build_html(products)
            sku_count = sum(len(p.get("skus", [])) for p in products)

            if dry_run:
                print(f"  [UPDATE] {ig_name} ({len(products)} 产品, {sku_count} SKU)")
                log.append({
                    "物料组": ig_name,
                    "产品数": len(products),
                    "SKU数": sku_count,
                    "操作": "更新",
                })
            else:
                ok = self.client.update_daneey_urls(ig_name, html)
                status = "更新成功" if ok else "更新失败"
                if ok:
                    self.stats["成功更新"] += 1
                else:
                    self.stats["更新失败"] += 1
                print(f"  [{status}] {ig_name} ({len(products)} 产品, {sku_count} SKU)")
                log.append({
                    "物料组": ig_name,
                    "产品数": len(products),
                    "SKU数": sku_count,
                    "操作": status,
                })

        # ── 清空不再匹配的历史数据 ──
        if not dry_run:
            print(f"\n  -- 检查需清空的旧数据...")
            existing = self.client.find_groups_with_daneey_urls()
            to_clear = [g for g in existing
                        if g not in groups and g.strip()]
            if to_clear:
                print(f"  发现 {len(to_clear)} 个物料组需清空（独立站已下架）")
                for ig_name in sorted(to_clear):
                    ok = self.client.clear_daneey_urls(ig_name)
                    if ok:
                        self.stats["清空旧数据"] = self.stats.get("清空旧数据", 0) + 1
                        print(f"  [CLEAR] {ig_name}")
                    else:
                        print(f"  [CLEAR-FAIL] {ig_name}")
                    log.append({
                        "物料组": ig_name,
                        "操作": "清空" if ok else "清空失败",
                    })
            else:
                print(f"  无需清空，所有已有数据均在本次匹配中")
        else:
            # dry-run 时也查一下哪些会被清空
            existing = self.client.find_groups_with_daneey_urls()
            to_clear = [g for g in existing
                        if g not in groups and g.strip()]
            if to_clear:
                print(f"\n  [DRY-RUN] 以下 {len(to_clear)} 个物料组将被清空（独立站已下架）:")
                for g in sorted(to_clear):
                    print(f"    - {g}")
                log.append({
                    "物料组": ", ".join(sorted(to_clear)),
                    "产品数": len(to_clear),
                    "操作": "将清空(DRY-RUN)",
                })

        return log

    def print_summary(self) -> None:
        """打印写入汇总。"""
        print(f"\n── 写入汇总 ──")
        for k, v in self.stats.items():
            print(f"  {k}: {v}")
