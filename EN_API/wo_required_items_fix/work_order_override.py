# apps/your_app/your_app/overrides/work_order.py

from erpnext.manufacturing.doctype.work_order.work_order import (
    WorkOrder as ERPNextWorkOrder,
    StockOverProductionError,
)
import json

import frappe
from frappe import _
from frappe.utils import cint, flt


class CustomWorkOrder(ERPNextWorkOrder):
    """
    自定义 Work Order 类
    继承自 原生 的 Work Order，取消自动创建工序卡。
    """

    def update_work_order_qty(self):
        """重写：当工单有开料分配(open_material_qty>0)时，允许入库量=已开料数量；支持配置开关放宽为max(已开料数量, qty+超产%)"""
        allowance_percentage = flt(
            frappe.db.get_single_value("Manufacturing Settings", "overproduction_percentage_for_work_order")
        )

        if flt(self.get("open_material_qty")) > 0:
            allow_beyond = cint(
                frappe.db.get_single_value(
                    "Manufacturing Settings", "allow_wo_completion_beyond_open_material_qty"
                )
            )
            if allow_beyond:
                completed_qty = max(
                    flt(self.open_material_qty),
                    self.qty + (allowance_percentage / 100 * self.qty),
                )
            else:
                completed_qty = flt(self.open_material_qty)
        else:
            completed_qty = self.qty + (allowance_percentage / 100 * self.qty)

        for purpose, fieldname in (
            ("Manufacture", "produced_qty"),
            ("Material Transfer for Manufacture", "material_transferred_for_manufacturing"),
        ):
            if (
                purpose == "Material Transfer for Manufacture"
                and self.operations
                and self.transfer_material_against == "Job Card"
            ):
                continue

            qty = self.get_transferred_or_manufactured_qty(purpose)
            if qty > completed_qty:
                frappe.throw(
                    _("{0} ({1}) cannot be greater than planned quantity ({2}) in Work Order {3}").format(
                        self.meta.get_label(fieldname), qty, completed_qty, self.name
                    ),
                    StockOverProductionError,
                )

            self.db_set(fieldname, qty)
            self.set_process_loss_qty()

            from erpnext.selling.doctype.sales_order.sales_order import update_produced_qty_in_so_item

            if self.sales_order and self.sales_order_item:
                update_produced_qty_in_so_item(self.sales_order, self.sales_order_item)

        if self.production_plan:
            self.set_produced_qty_for_sub_assembly_item()
            self.update_production_plan_status()

    def on_submit(self):
        # 保留原有校验和其它逻辑，但不调用 self.create_job_card()
        if not self.wip_warehouse and not self.skip_transfer:
            frappe.throw(_("Work-in-Progress Warehouse is required before Submit"))
        if not self.fg_warehouse:
            frappe.throw(_("For Warehouse is required before Submit"))

        if self.production_plan and frappe.db.exists(
            "Production Plan Item Reference", {"parent": self.production_plan}
        ):
            self.update_work_order_qty_in_combined_so()
        else:
            self.update_work_order_qty_in_so()

        self.update_ordered_qty()
        self.update_reserved_qty_for_production()
        self.update_completed_qty_in_material_request()
        self.update_planned_qty()
        # self.create_job_card()  # 注释掉此函数，不自动创建工序卡

def get_item_group_descendants(item_group):
    """获取物料组及其所有子孙物料组（含「面料」及子组）"""
    descendants = [item_group]

    def get_children(parent):
        children = frappe.get_all(
            "Item Group", filters={"parent_item_group": parent}, fields=["name"]
        )
        for child in children:
            if child.name not in descendants:
                descendants.append(child.name)
                get_children(child.name)

    get_children(item_group)
    return descendants


def _work_order_item_as_child_dict(item):
    """子表行转为 append 用字典，尽量保留原字段（含自定义字段）"""
    row = item.as_dict()
    skip = {
        "name",
        "owner",
        "creation",
        "modified",
        "modified_by",
        "docstatus",
        "idx",
        "parent",
        "parentfield",
        "parenttype",
        "doctype",
    }
    return {k: v for k, v in row.items() if k not in skip and not str(k).startswith("_")}


def _resolve_item_rate(wo, item_code, qty, stock_uom=None):
    """解析新增物料行的单价。

    口径与「工单从 BOM 建行」时一致：用本工单 BOM 的取价方式（rm_cost_as_per）——
    Price List 就查该 BOM 的 buying_price_list，Valuation Rate 就取库存估值。
    取不到时回落到物料主数据的 valuation_rate。

    注意 ERPNext 自己在工单里手动加行时并不会带单价
    （work_order.get_item_details 只返回 uom/名称/描述等），所以这里必须自己算。
    """
    rate = 0
    if wo.get("bom_no") and frappe.db.exists("BOM", wo.bom_no):
        try:
            bom = frappe.get_doc("BOM", wo.bom_no)
            rate = bom.get_rm_rate(
                {
                    "company": wo.company,
                    "item_code": item_code,
                    "bom_no": "",
                    "qty": qty,
                    "uom": stock_uom,
                    "stock_uom": stock_uom,
                    "conversion_factor": 1,
                    "sourced_by_supplier": 0,
                }
            )
        except Exception:
            frappe.log_error(
                "解析物料单价失败 - 工单 {0} / BOM {1} / 物料 {2}".format(
                    wo.name, wo.bom_no, item_code
                ),
                "Update Required Items Rate",
            )
            rate = 0

    if not rate:
        rate = flt(frappe.db.get_value("Item", item_code, "valuation_rate"))

    return flt(rate)


@frappe.whitelist()
def update_required_items(work_order_name, items):
    """
    变更生产工单的所需物料
    支持：添加、修改需求数量、删除物料行
    items: JSON 字符串，包含变更后的物料数据
    """
    if not frappe.db.exists("Work Order", work_order_name):
        frappe.throw(_("工单 {0} 不存在").format(work_order_name))

    wo = frappe.get_doc("Work Order", work_order_name)

    # 解析前端传来的数据
    if isinstance(items, str):
        try:
            new_items = json.loads(items)
        except json.JSONDecodeError:
            frappe.throw(_("数据格式错误"))
    else:
        new_items = items or []

    # 获取原有的行数据（用于判断是否可以删除）
    original_rows = {row.name: row for row in wo.required_items}
    original_item_codes = {row.item_code for row in wo.required_items}

    # 分离：需要更新的行（已有 docname）、需要新增的行（无 docname 或 docname 为空）
    items_to_update = []
    items_to_add = []

    for item in new_items:
        if not item.get("item_code"):
            continue

        if item.get("docname") and item.get("docname") in original_rows:
            # 现有行 - 检查是否有不允许删除的情况
            original_row = original_rows[item.get("docname")]
            transferred_or_consumed = (
                flt(original_row.get("transferred_qty", 0)) > 0
                or flt(original_row.get("consumed_qty", 0)) > 0
            )
            if transferred_or_consumed and item.get("required_qty", 0) < flt(original_row.get("required_qty", 0)):
                # 如果数量被减少且已有发料/消耗，给出警告但仍允许（前端应已提醒）
                pass
            items_to_update.append({
                "name": item.get("docname"),
                "item_code": item.get("item_code"),
                "item_name": item.get("item_name"),
                "required_qty": flt(item.get("required_qty", 0)),
                "source_warehouse": item.get("source_warehouse"),
                "operation": item.get("operation"),
            })
        else:
            # 新增行
            item_code = item.get("item_code")
            qty = flt(item.get("required_qty", 0))
            item_master = (
                frappe.db.get_value(
                    "Item",
                    item_code,
                    ["stock_uom", "include_item_in_manufacturing"],
                    as_dict=True,
                )
                or {}
            )
            # 前端弹窗不传单价/金额，也不传 include_item_in_manufacturing；
            # 不显式带出的话：单价金额归零、且勾选落到默认 0（该料不进工单发料/耗用）。
            rate = _resolve_item_rate(wo, item_code, qty, item_master.get("stock_uom"))
            items_to_add.append({
                "item_code": item_code,
                "item_name": item.get("item_name") or "",
                "required_qty": qty,
                "rate": rate,
                "amount": flt(rate * qty),
                "source_warehouse": item.get("source_warehouse"),
                "operation": item.get("operation"),
                # 按物料主数据带出，与 ERPNext 从 BOM 建行时的行为一致
                "include_item_in_manufacturing": 1
                if item_master.get("include_item_in_manufacturing")
                else 0,
            })

    # 统计变更
    original_count = len(wo.required_items)
    updated_count = len(items_to_update)
    added_count = len(items_to_add)
    deleted_count = original_count - updated_count

    # 清空现有行并重新构建
    wo.required_items = []

    # 重新添加更新后的行（保留原有顺序和自定义字段）
    for item in items_to_update:
        original_row = original_rows[item["name"]]
        # 复用原行的所有字段
        new_row = _work_order_item_as_child_dict(original_row)
        # 更新关键字段
        new_row["item_code"] = item["item_code"]
        new_row["item_name"] = item["item_name"]
        new_row["required_qty"] = item["required_qty"]
        if item.get("source_warehouse"):
            new_row["source_warehouse"] = item["source_warehouse"]
        if item.get("operation"):
            new_row["operation"] = item["operation"]
        wo.append("required_items", new_row)

    # 添加新行
    for item in items_to_add:
        wo.append("required_items", {
            "item_code": item["item_code"],
            "item_name": item["item_name"],
            "required_qty": item["required_qty"],
            "rate": item.get("rate") or 0,
            "amount": item.get("amount") or 0,
            "source_warehouse": item.get("source_warehouse") or "",
            "operation": item.get("operation") or "",
            # 见上面 items_to_add 的说明：这两个必须显式带出，否则单价金额归零、勾选丢失
            "include_item_in_manufacturing": item.get("include_item_in_manufacturing") or 0,
        })

    # 使用特殊标志忽略提交后的验证（因为已发料的物料不能随意删除/减少数量）
    wo.flags.ignore_validate_update_after_submit = True
    wo.save(ignore_permissions=True)
    frappe.db.commit()

    new_count = len(wo.required_items)

    return {
        "success": True,
        "message": _("物料变更成功：更新 {0} 行，新增 {1} 行，删除 {2} 行，共 {3} 行").format(
            updated_count, added_count, deleted_count, new_count
        ),
        "updated_count": updated_count,
        "added_count": added_count,
        "deleted_count": deleted_count,
        "total_count": new_count,
    }


@frappe.whitelist()
def get_bom_items_preview(work_order_name):
    """
    获取 BOM 物料预览列表.
    返回 BOM 的 items 子表：物料编码、物料名称、数量
    """
    if not frappe.db.exists("Work Order", work_order_name):
        frappe.throw(_("工单 {0} 不存在").format(work_order_name))

    wo = frappe.get_doc("Work Order", work_order_name)

    if not wo.bom_no:
        return {
            "success": False,
            "error": _("工单未关联 BOM")
        }

    bom = frappe.get_cached_doc("BOM", wo.bom_no)
    items = []
    for row in bom.items:
        items.append({
            "item_code": row.item_code or "",
            "item_name": row.item_name or "",
            "qty": row.qty or 0,
            "uom": row.uom or "",
            "rate": row.rate or 0,
            "amount": row.amount or 0,
        })

    return {
        "success": True,
        "bom_no": wo.bom_no,
        "bom_name": bom.name,
        "items": items,
        "items_count": len(items),
    }


@frappe.whitelist()
def resync_bom_items(work_order_name):
    """
    从 BOM 重新同步所有物料、工序、成本信息

    适用于 BOM 变更后需要同步到已提交工单的场
    """
    if not frappe.has_permission("Work Order", "write", work_order_name):
        frappe.throw(_("没有权限执行此操作"), frappe.PermissionError)

    wo = frappe.get_doc("Work Order", work_order_name)

    if not wo.bom_no:
        return {
            "success": False,
            "error": _("工单未关联 BOM，无法同步")
        }

    if wo.docstatus != 1:
        return {
            "success": False,
            "error": _("只能对已提交的单据执行同步操作")
        }

    if wo.status in ["Completed", "Closed"]:
        return {
            "success": False,
            "error": _("已完工或已关闭的工单不能同步 BOM")
        }

    # 记录原始行信息（用于保留自定义字段）
    original_rows = {row.item_code: row.as_dict() for row in wo.required_items}

    # 保存已发料/已消耗的数量记录（按物料代码）
    consumed_data = {}
    transferred_data = {}
    for row in wo.required_items:
        if row.consumed_qty:
            consumed_data[row.item_code] = row.consumed_qty
        if row.transferred_qty:
            transferred_data[row.item_code] = row.transferred_qty

    # 设置忽略验证标志，允许修改已提交单据
    wo.flags.ignore_validate_update_after_submit = True
    wo.flags.ignore_permissions = True

    # 重新设置工序（从 BOM 同步工艺路线）
    if wo.bom_no:
        bom = frappe.get_cached_doc("BOM", wo.bom_no)
        if bom.operations:
            wo.set_work_order_operations()

    # 重新设置所需物料（从 BOM 重新加载）
    wo.set_required_items(reset_only_qty=False)

    # 刷新可用数量
    wo.set_available_qty()

    # 保留原有自定义字段值
    for row in wo.required_items:
        if row.item_code in original_rows:
            original = original_rows[row.item_code]
            # 保留原行的自定义字段
            for key in original:
                if key.startswith("custom_") and original[key]:
                    setattr(row, key, original[key])

    wo.save(ignore_permissions=True)
    frappe.db.commit()

    items_count = len(wo.required_items)

    return {
        "success": True,
        "message": _("BOM 同步成功，已刷新 {0} 行物料").format(items_count),
        "items_count": items_count,
    }