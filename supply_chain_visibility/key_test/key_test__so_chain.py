# -*- coding: utf-8 -*-
"""key_test app：key_test/so_chain.py

销售订单表单「供应链链条」的服务端数据方法（@frappe.whitelist），v2。
被 public/js/sales_order.js 追加的 refresh 钩子调用。

口径（与 fzh-data 的 EN_API/item_shipment_status.py 一致）：
  * 订单行主键 = Sales Order Item.name
  * 工单：production_item == 行 item_code 且 sales_order == 本 SO
  * 生产计划：Production Plan Item.sales_order_item = 行 name（**不要**用 pp 行的 work_order 字段，实测为空）
  * 工序进度：逐道工序的 Job Card 完成量；「工单完成量」取第一道工序，**不跨工序求和**
  * 菲号：Tracking Number.work_order = 工单；initial_work_order 非空 = 已开料
  * 已发：出库单按 item_code 匹配的带符号 qty 之和（退货行负数自动抵扣）
  * WO.status / produced_qty 不可信，进度只看工序卡
"""
import frappe


def _num(v):
    try:
        return float(v or 0)
    except (TypeError, ValueError):
        return 0.0


@frappe.whitelist()
def get_so_chain(sales_order):
    doc = frappe.get_doc("Sales Order", sales_order)
    if not frappe.has_permission("Sales Order", "read", doc):
        frappe.throw("无权限读取该销售订单")

    lines = []
    for it in doc.items:
        qty = _num(it.qty)
        delivered = _num(it.delivered_qty)
        open_qty = qty - delivered

        # 生产计划（按订单行连接键）
        plans = frappe.db.sql(
            """select pp.name as pp, ppi.planned_qty, ppi.pending_qty
               from `tabProduction Plan Item` ppi
               join `tabProduction Plan` pp on pp.name = ppi.parent
               where pp.docstatus = 1 and ppi.sales_order_item = %s""",
            it.name, as_dict=True)

        # 工单
        wos = frappe.get_all(
            "Work Order",
            filters={"docstatus": 1, "production_item": it.item_code, "sales_order": doc.name},
            fields=["name", "qty", "status", "produced_qty"])
        wo_names = [w.name for w in wos]

        # 工序行（含顺序）
        ops_by_wo = {}
        if wo_names:
            for o in frappe.get_all("Work Order Operation",
                                    filters={"parent": ["in", wo_names]},
                                    fields=["parent", "operation", "sequence_id", "status", "completed_qty"]):
                ops_by_wo.setdefault(o.parent, []).append(o)

        # 逐(工单, 工序)的工序卡完成量
        jc_done = {}
        if wo_names:
            for j in frappe.get_all("Job Card",
                                    filters={"work_order": ["in", wo_names], "docstatus": ["<", 2]},
                                    fields=["work_order", "operation", "status", "total_completed_qty", "for_quantity"]):
                if j.status == "Completed":
                    q = _num(j.total_completed_qty) or _num(j.for_quantity)
                    key = (j.work_order, j.operation)
                    jc_done[key] = jc_done.get(key, 0.0) + q

        # 菲号（跟踪单号）
        tn_by_wo = {}
        if wo_names:
            for t in frappe.get_all("Tracking Number",
                                    filters={"work_order": ["in", wo_names]},
                                    fields=["name", "work_order", "qty", "initial_work_order", "so_materials"]):
                tn_by_wo.setdefault(t.work_order, []).append(t)

        wo_detail, line_produced, line_tn = [], 0.0, 0
        for w in wos:
            ops = sorted(ops_by_wo.get(w.name, []), key=lambda o: (_num(o.sequence_id), o.operation or ""))
            operations = [{"operation": o.operation, "seq": o.sequence_id, "status": o.status,
                           "done": jc_done.get((w.name, o.operation), 0.0)} for o in ops]
            # 工单完成量 = 第一道工序完成量，空则各工序最大值
            done_qty = 0.0
            if operations:
                done_qty = operations[0]["done"] or max([x["done"] for x in operations] or [0.0])
            line_produced += done_qty
            tns = [{"tn": t.name, "qty": _num(t.qty),
                    "iwo": t.initial_work_order or "", "mat": t.so_materials or ""}
                   for t in tn_by_wo.get(w.name, [])]
            line_tn += len(tns)
            wo_detail.append({"wo": w.name, "qty": _num(w.qty), "status": w.status,
                              "produced_head": _num(w.produced_qty), "done": done_qty,
                              "operations": operations, "tracking_numbers": tns})

        # 出库净额
        dn = frappe.db.sql(
            """select dni.qty as qty from `tabDelivery Note Item` dni
               join `tabDelivery Note` d on d.name = dni.parent
               where d.docstatus = 1 and dni.against_sales_order = %s and dni.item_code = %s""",
            (doc.name, it.item_code), as_dict=True)
        shipped = sum(_num(r.qty) for r in dn)

        # 阶段 0–3
        if doc.docstatus == 2 and doc.amended_from:
            stage, sub = 0, "已改单(作废)"
        elif doc.docstatus == 2:
            stage, sub = 0, "已取消"
        elif doc.docstatus == 0:
            stage, sub = 0, "草稿"
        elif open_qty <= 0:
            stage, sub = 3, "已出库完成"
        elif doc.status == "Closed":
            stage, sub = 3, "Closed未发(死单)"
        elif not wos:
            stage, sub = (1, "已排产(无工单)") if plans else (1, "未排产(无工单)")
        elif line_produced + 1e-6 >= qty:
            stage, sub = 3, "生产完成待出库"
        elif line_produced <= 0:
            stage, sub = 2, "未开工"
        else:
            stage, sub = 2, "生产中"

        lines.append({
            "so_line": it.name, "item_code": it.item_code, "item_name": it.item_name,
            "customer_item_code": it.customer_item_code,
            "qty": qty, "delivered": delivered, "open_qty": open_qty, "shipped_dn": shipped,
            "stage": stage, "substate": sub,
            "plans": [{"pp": p.pp, "planned_qty": _num(p.planned_qty), "pending_qty": _num(p.pending_qty)}
                      for p in plans],
            "wo_count": len(wos), "tn_count": line_tn,
            "work_orders": wo_detail,
        })

    return {"sales_order": doc.name, "customer": doc.customer_name or doc.customer,
            "status": doc.status, "lines": lines}
