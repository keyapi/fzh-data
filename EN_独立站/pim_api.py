# -*- coding: utf-8 -*-
"""vilavi_pim/api/pim_api.py

独立站 SKU → 物料组 查询 API。
部署在 vilavi_pim app 中，需 bench restart 或 clear-cache 生效。

接口：POST /api/method/vilavi_pim.api.pim_api.get_sku_item_itemgroup_mapping

数据链路：
    tabItem Customer Detail.ref_code (SKU)
        → tabItem.name (parent)
        → tabItem.item_group (物料组)

请求体：{"skus": ["TT0031038K0062927", "TT0312685K0064373"]}

响应体：
{
    "total": 2,
    "results": [
        {
            "sku": "TT0031038K0062927",
            "customer_name": "",
            "item_code": "KS0156-NYBDSFH-52x52x5-BLACK",
            "item_name": "沙发支撑垫-耐臭氧防紫外线-52x52x5cm-黑色",
            "item_group": "沙发支撑垫",
            "item_group_url": "/app/item-group/沙发支撑垫"
        }
    ],
    "not_found": ["TT0312685K0064373"],
    "message": "Found 1 mappings, 1 SKUs not found"
}
"""

import frappe


@frappe.whitelist(allow_guest=False)
def get_sku_item_itemgroup_mapping():
    """批量查询 SKU → 物料组映射。

    通过 SQL 直查 tabItem Customer Detail（子表），绕过 REST API 权限限制。
    同一个 SKU 可能对应多条记录（不同客户组），均返回。
    """
    data = frappe.local.form_dict
    skus = data.get("skus") or []

    if not skus or not isinstance(skus, list):
        frappe.local.response["message"] = {
            "total": 0,
            "results": [],
            "not_found": [],
            "message": "请提供 skus 参数 (List[str])",
        }
        return

    # 批量 SQL 查询（用占位符防止 SQL 注入）
    placeholders = ", ".join(["%s"] * len(skus))
    sql = f"""
        SELECT DISTINCT
            icd.ref_code              AS sku,
            icd.customer_name         AS customer_name,
            icd.parent                AS item_name,
            i.item_code               AS item_code,
            i.item_name               AS item_name_full,
            i.item_group              AS item_group
        FROM `tabItem Customer Detail` icd
        LEFT JOIN `tabItem` i
            ON i.name = icd.parent
        WHERE icd.ref_code IN ({placeholders})
    """

    rows = frappe.db.sql(sql, skus, as_dict=True)

    found_skus = set()
    results = []
    for row in rows:
        found_skus.add(row["sku"])
        results.append({
            "sku": row["sku"],
            "customer_name": row.get("customer_name") or "",
            "item_code": row.get("item_code") or "",
            "item_name": row.get("item_name_full") or "",
            "item_group": row.get("item_group") or "",
            "item_group_url": f"/app/item-group/{row.get('item_group', '')}",
        })

    not_found = [s for s in skus if s not in found_skus]

    frappe.local.response["message"] = {
        "total": len(results),
        "results": results,
        "not_found": not_found,
        "message": f"Found {len(results)} mappings, {len(not_found)} SKUs not found",
    }
