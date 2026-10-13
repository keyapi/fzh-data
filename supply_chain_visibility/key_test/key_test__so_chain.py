# -*- coding: utf-8 -*-
"""key_test app 新增文件：key_test/key_test/so_chain.py

销售订单表单「供应链链条摘要」的服务端数据方法（@frappe.whitelist）。
由 public/js/sales_order.js 里追加的 refresh 钩子调用，把结果渲染进 frm.dashboard。

口径与 fzh-data 仓库 EN_API/item_shipment_status.py 一致：
  * 订单行主键 = Sales Order Item.name
  * 工单按 production_item == 订单行 item_code 且 sales_order == 本 SO
  * 工序进度 = 第一道工序（sequence_id 最小）的已完成量，**不跨工序求和**
  * 已发 = 出库单(Delivery Note)按 item_code 匹配的 **带符号 qty 之和**（退货行负数自动抵扣）
  * 阶段 0-3：已改单/已取消 / 未排产 / 生产中 / 生产完成待出库 / 工厂待出库 / 已出库完成
  * WO.status / produced_qty 不可信，进度只看工序卡

放在 app 根目录（与 sales_order_utils.py 同级），方法路径 = key_test.so_chain.get_so_chain。
"""
import frappe


def _num(v):
    try:
        return float(v or 0)
    except (TypeError, ValueError):
        return 0.0


def _first_op_done(wo_ops, jcs):
    """第一道工序的已完成量；空则退各工序最大值。工序卡 completed 才计数。"""
    if not wo_ops:
        return 0.0
    def op_done(opname):
        return sum((_num(j.total_completed_qty) or _num(j.for_quantity))
                   for j in jcs if j.operation == opname and j.status == "Completed")
    first = min(wo_ops, key=lambda o: (_num(o.sequence_id), o.operation or ""))
    q = op_done(first.operation)
    if q <= 0:
        q = max([op_done(o.operation) for o in wo_ops] or [0.0])
    return q


@frappe.whitelist()
def get_so_chain(sales_order):
    """返回某张销售订单的链条摘要（供表单内嵌展示）。只读。"""
    doc = frappe.get_doc("Sales Order", sales_order)
    if not frappe.has_permission("Sales Order", "read", doc):
        frappe.throw("无权限读取该销售订单")

    lines = []
    for it in doc.items:
        wo_rows = frappe.get_all(
            "Work Order",
            filters={"docstatus": 1, "production_item": it.item_code, "sales_order": doc.name},
            fields=["name", "qty", "status", "produced_qty"])
        wo_names = [w.name for w in wo_rows]

        jcs = frappe.get_all(
            "Job Card",
            filters={"work_order": ["in", wo_names or [""]], "docstatus": ["<", 2]},
            fields=["work_order", "operation", "status", "total_completed_qty", "for_quantity"]) if wo_names else []

        produced = 0.0
        wo_progress = []
        for w in wo_rows:
            ops = frappe.get_all("Work Order Operation", filters={"parent": w.name},
                                 fields=["operation", "sequence_id", "status"])
            jc_w = [j for j in jcs if j.work_order == w.name]
            done = _first_op_done(ops, jc_w)
            produced += done
            if not jc_w:
                txt = "未开工(0工序卡)"
            else:
                done_ops = {j.operation for j in jc_w if j.status == "Completed"}
                txt = f"{len(done_ops)}/{len(ops)}工序完({done:g}件)"
            wo_progress.append({"wo": w.name, "text": txt, "done": done})

        dn = frappe.db.sql(
            """select dni.qty as qty
               from `tabDelivery Note Item` dni
               join `tabDelivery Note` dn on dn.name = dni.parent
               where dn.docstatus = 1 and dni.against_sales_order = %s and dni.item_code = %s""",
            (doc.name, it.item_code), as_dict=True)
        shipped = sum(_num(r.qty) for r in dn)   # 退货行 qty 为负，自动净额

        qty = _num(it.qty)
        delivered = _num(it.delivered_qty)
        open_qty = qty - delivered

        # 阶段（与 fulfillment/stages.py 对齐）
        voided = doc.docstatus == 2 and doc.amended_from
        if doc.docstatus == 2 and not voided:
            stage, sub = 0, "已取消"
        elif doc.docstatus == 2:
            stage, sub = 0, "已改单(作废)"
        elif doc.docstatus == 0:
            stage, sub = 0, "草稿"
        elif open_qty <= 0:
            stage, sub = 3, "已出库完成"
        elif doc.status == "Closed":
            stage, sub = 3, "Closed未发(死单)"
        elif not wo_rows:
            stage, sub = 1, "未排产(无工单)"
        elif produced + 1e-6 >= qty:
            stage, sub = 3, "生产完成待出库"
        elif all(w["done"] <= 0 for w in wo_progress):
            stage, sub = 2, "未开工"
        else:
            stage, sub = 2, "生产中"

        lines.append({
            "so_line": it.name,
            "item_code": it.item_code,
            "item_name": it.item_name,
            "customer_item_code": it.customer_item_code,
            "qty": qty, "delivered": delivered, "open_qty": open_qty,
            "shipped_dn": shipped,
            "stage": stage, "substate": sub,
            "work_orders": wo_progress,
        })

    return {
        "sales_order": doc.name,
        "customer": doc.customer_name or doc.customer,
        "status": doc.status,
        "lines": lines,
    }
