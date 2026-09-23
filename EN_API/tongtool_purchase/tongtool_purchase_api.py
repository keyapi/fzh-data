# Copyright (c) 2024, delivery_plan contributors
# For license information, please see license.txt

"""销售出库单(Delivery Note) → 通途采购单 的 whitelist 入口。

前端 delivery_plan/public/js/delivery_note.js 的按钮调用这里。
业务实现在 delivery_plan.utils.tongtool_purchase。
"""

import frappe
from frappe import _

from delivery_plan.utils.tongtool_purchase import (
    build_preview,
    create_purchase_order as _create_purchase_order,
    get_purchase_settings,
    reset_purchase_order as _reset_purchase_order,
    supported_customers,
)


@frappe.whitelist()
def get_purchase_options():
    """弹窗下拉项：采购员 / 仓库 / 供应商 / 币种，来自 Tongtool Purchase Settings。"""
    settings = get_purchase_settings()
    settings["supported_customers"] = supported_customers()
    return settings


@frappe.whitelist()
def preview_purchase_order(delivery_note: str):
    """只读预演：DN 明细 → 通途货品。未匹配行原样返回，不静默丢弃。"""
    if not delivery_note:
        frappe.throw(_("缺少 delivery_note 参数"))
    frappe.has_permission("Delivery Note", "read", doc=delivery_note, throw=True)
    return build_preview(delivery_note)


@frappe.whitelist()
def reset_purchase_order(delivery_note: str):
    """清空 DN 上的通途采购单号。仅当通途那边已作废（status=4）才允许。

    未作废会直接抛错，不返回成功 —— 避免误清还在执行的采购单。
    """
    if not delivery_note:
        frappe.throw(_("缺少 delivery_note 参数"))
    frappe.has_permission("Delivery Note", "write", doc=delivery_note, throw=True)
    return _reset_purchase_order(delivery_note)


@frappe.whitelist()
def create_purchase_order(
    delivery_note: str,
    supplier_id: str,
    warehouse_id_key: str,
    purchase_user_id: str,
    currency: str = None,
    remark: str = None,
    shipping_fee: float = 0,
    lines=None,
    force: bool = False,
):
    """在通途创建采购单并回写单号。写操作，前端需二次确认。"""
    if not delivery_note:
        frappe.throw(_("缺少 delivery_note 参数"))
    frappe.has_permission("Delivery Note", "write", doc=delivery_note, throw=True)

    return _create_purchase_order(
        delivery_note=delivery_note,
        supplier_id=supplier_id,
        warehouse_id_key=warehouse_id_key,
        purchase_user_id=purchase_user_id,
        currency=currency,
        remark=remark,
        shipping_fee=shipping_fee,
        lines=lines,
        force=force,
    )
