# 以下代码让您的 Agent 在 ERPNext 测试系统 (ensh.vilavi.cn) 创建 Server Script

"""
Server Script 配置:
  Script Type: API Endpoint
  Module: 任意（如 Items）
  Path: get_sku_item_itemgroup_mapping
  (Script 内容如下)
"""

import frappe
import json

def get_sku_item_itemgroup_mapping():
    """根据 SKU 列表查询对应的 Item 和物料组信息。"""
    data = frappe.local.form_dict
    skus = data.get("skus") or []

    if not skus or not isinstance(skus, list):
        frappe.local.response["message"] = {
            "total": 0,
            "results": [],
            "not_found": [],
            "message": "请提供 skus 参数 (List[str])"
        }
        return

    # 用 SQL 直查子表（绕过权限限制）
    placeholders = ", ".join(["%s"] * len(skus))
    sql = f"""
        SELECT DISTINCT
            icd.ref_code AS sku,
            icd.customer_name,
            icd.parent AS item_name,
            i.item_code,
            i.item_name,
            i.item_group
        FROM `tabItem Customer Detail` icd
        LEFT JOIN `tabItem` i ON i.name = icd.parent
        WHERE icd.ref_code IN ({placeholders})
    """

    rows = frappe.db.sql(sql, skus, as_dict=True)

    # 构建结果
    found_skus = set()
    results = []
    for row in rows:
        found_skus.add(row["sku"])
        results.append({
            "sku": row["sku"],
            "customer_name": row.get("customer_name", ""),
            "item_code": row.get("item_code", ""),
            "item_name": row.get("item_name", ""),
            "item_group": row.get("item_group", ""),
            "item_group_url": f"/app/item-group/{row.get('item_group', '')}",
        })

    not_found = [s for s in skus if s not in found_skus]

    frappe.local.response["message"] = {
        "total": len(results),
        "results": results,
        "not_found": not_found,
        "message": f"Found {len(results)} mappings, {len(not_found)} SKUs not found"
    }
