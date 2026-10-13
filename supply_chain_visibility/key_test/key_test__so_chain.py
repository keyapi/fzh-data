# -*- coding: utf-8 -*-
"""key_test app：key_test/so_chain.py

销售订单表单「供应链链条」的服务端数据方法（@frappe.whitelist），v4。
被 public/js/sales_order.js 追加的 refresh 钩子调用。

## 口径（与 fzh-data 的 EN_API/item_shipment_status.py 一致）
  * 订单行主键 = Sales Order Item.name
  * 工单：**行级外键 Work Order.sales_order_item == 行 name**（不是 sales_order+production_item！
    生产实测：同 SO 内同 item_code 最多 40 行，复合键会让 1464 张工单重复挂、139 张漏挂）。
    兜底：sales_order_item 空 → production_plan_item→PP.sales_order_item，或 fg_sales_order_item。
  * 生产计划：Production Plan Item.sales_order_item = 行 name
  * **菲号 = 一批(组)皮壳/半成品的实物流身份证**，开料时按组生成(name=<皮壳WO>-NNN)，
    贯穿该工单全部工序；**每个菲号在每个工序恰 1 张 Job Card**。成品(KS)工单基本无菲号。
    → 展示层级 = **工单 → 菲号 → 逐工序 Job Card**（工序是菲号内部的轴）。
  * 工序进度：逐道工序的 Job Card 完成量；「工单完成量」取第一道工序，**不跨工序求和**
  * 已发：出库单按 item_code 匹配的带符号 qty 之和（退货行负数自动抵扣）
  * WO.status / produced_qty 不可信，进度只看工序卡
"""
import frappe
from frappe.utils import getdate, today


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

    # 返工/纠正工序（如「质检发现问题」「通用返工」）—— 非常规必经，**不计入进度分母**
    corrective = {r.name for r in frappe.get_all(
        "Operation", filters={"is_corrective_operation": 1}, fields=["name"])}

    lines = []
    for it in doc.items:
        qty = _num(it.qty)
        delivered = _num(it.delivered_qty)
        open_qty = qty - delivered

        # 生产计划（按订单行连接键）—— 用于顶部的「本行计划/待产」数字
        plans = frappe.db.sql(
            """select pp.name as pp, ppi.name as ppi, ppi.planned_qty, ppi.pending_qty
               from `tabProduction Plan Item` ppi
               join `tabProduction Plan` pp on pp.name = ppi.parent
               where pp.docstatus = 1 and ppi.sales_order_item = %s""",
            it.name, as_dict=True)

        # 工单 —— **成品**用 sales_order_item；**皮壳/内胆**用 fg_sales_order_item（不是 sales_order_item！）。
        # 一条成品(KS)行的标准结构 = 1 成品 + 1 皮壳(PK#) + 1 内胆(ND#)。兜底 production_plan_item。
        wos = frappe.db.sql(
            """select w.name, w.qty, w.status, w.produced_qty, w.production_item, w.production_plan_item
               from `tabWork Order` w
               where w.docstatus = 1 and (
                   w.sales_order_item = %(line)s
                   or w.fg_sales_order_item = %(line)s
                   or (ifnull(w.sales_order_item, '') = '' and ifnull(w.fg_sales_order_item, '') = '' and exists(
                        select 1 from `tabProduction Plan Item` ppi
                        where ppi.name = w.production_plan_item and ppi.sales_order_item = %(line)s))
               )
               order by w.name""", {"line": it.name}, as_dict=True)

        # WO 的 production_plan_item → PP。**不过滤 sales_order_item**：
        # 皮壳/内胆的计划行通常不带 SO 行（实测 WO.production_plan_item 100% 指向 Production Plan Item）。
        pp_by_ppi = {p.ppi: p.pp for p in plans}
        _ppi = [w.production_plan_item for w in wos if w.production_plan_item]
        if _ppi:
            for r in frappe.get_all("Production Plan Item", filters={"name": ["in", _ppi]},
                                    fields=["name", "parent"]):
                pp_by_ppi[r.name] = r.parent
        wo_names = [w.name for w in wos]

        # 工序行（菲号内部的排序轴）
        ops_by_wo = {}
        if wo_names:
            for o in frappe.get_all("Work Order Operation",
                                    filters={"parent": ["in", wo_names]},
                                    fields=["parent", "operation", "sequence_id", "status", "completed_qty"]):
                ops_by_wo.setdefault(o.parent, []).append(o)

        # 工序卡（Job Card）—— 每张恰一个菲号(tracking_number) + 一道工序
        jc_done, jc_by_op = {}, {}
        if wo_names:
            for j in frappe.get_all("Job Card",
                                    filters={"work_order": ["in", wo_names], "docstatus": ["<", 2]},
                                    fields=["name", "work_order", "operation", "status", "total_completed_qty",
                                            "for_quantity", "actual_end_date", "tracking_number"]):
                q = _num(j.total_completed_qty) or _num(j.for_quantity)
                rec = {"name": j.name, "status": j.status, "qty": q,
                       "end": str(j.actual_end_date or "")[:19], "tn": j.tracking_number or ""}
                key = (j.work_order, j.operation)
                jc_by_op.setdefault(key, []).append(rec)
                if j.status == "Completed":
                    jc_done[key] = jc_done.get(key, 0.0) + q

        # 菲号（跟踪单号）
        tn_by_wo = {}
        if wo_names:
            for t in frappe.get_all("Tracking Number",
                                    filters={"work_order": ["in", wo_names]},
                                    fields=["name", "work_order", "qty", "initial_work_order",
                                            "so_materials", "finished_product_work_order"]):
                tn_by_wo.setdefault(t.work_order, []).append(t)

        wo_detail, line_produced, line_tn = [], 0.0, 0
        prog_vals = []          # 每个菲号的「必经工序完成数」，用于算 line 的 最慢/最快
        for w in wos:
            ops = sorted(ops_by_wo.get(w.name, []), key=lambda o: (_num(o.sequence_id), o.operation or ""))
            # 必经工序（排除返工/纠正分支）
            req_ops = [o for o in ops if o.operation not in corrective]
            op_axis = [{"operation": o.operation, "seq": o.sequence_id, "status": o.status,
                        "corrective": o.operation in corrective} for o in ops]
            # 工单完成量 = 第一道**必经**工序完成量，空则各必经工序最大值
            done_qty = 0.0
            if req_ops:
                first = jc_done.get((w.name, req_ops[0].operation), 0.0)
                done_qty = first or max([jc_done.get((w.name, o.operation), 0.0) for o in req_ops] or [0.0])
            line_produced += done_qty

            # 菲号 → 逐工序 Job Card（同时算该菲号的必经工序完成数）
            tn_rows = []
            for t in tn_by_wo.get(w.name, []):
                steps, done_op_names = [], set()
                for o in ops:
                    for x in jc_by_op.get((w.name, o.operation), []):
                        if x["tn"] == t.name:
                            steps.append({"operation": o.operation, "seq": o.sequence_id,
                                          "jc": x["name"], "status": x["status"],
                                          "qty": x["qty"], "end": x["end"],
                                          "corrective": o.operation in corrective})
                            if x["status"] == "Completed" and o.operation not in corrective:
                                done_op_names.add(o.operation)
                t_done = len(done_op_names)
                prog_vals.append((t_done, len(req_ops)))
                tn_rows.append({"tn": t.name, "qty": _num(t.qty),
                                "iwo": t.initial_work_order or "", "mat": t.so_materials or "",
                                "fgw": t.finished_product_work_order or "", "steps": steps,
                                "ops_done": t_done, "ops_total": len(req_ops)})
            # 无菲号的工序卡（未分配菲号 / 成品工单报工）
            unassigned = []
            for o in ops:
                for x in jc_by_op.get((w.name, o.operation), []):
                    if not x["tn"]:
                        unassigned.append({"operation": o.operation, "seq": o.sequence_id,
                                           "jc": x["name"], "status": x["status"],
                                           "qty": x["qty"], "end": x["end"]})
            jc_ends = [s["end"] for tn in tn_rows for s in tn["steps"] if s["end"]] + \
                      [u["end"] for u in unassigned if u["end"]]
            # 完成的必经工序数（该工序下任一工序卡 Completed）
            ops_done = sum(1 for o in req_ops
                           if any(x["status"] == "Completed" for x in jc_by_op.get((w.name, o.operation), [])))
            line_tn += len(tn_rows)
            pic = w.production_item or ''
            kind = ('成品' if pic.startswith('KS')
                    else '皮壳' if pic.startswith('PK#')
                    else '内胆' if (pic.startswith('ND#') or pic.startswith('DKND#')) else '')
            completed = (w.status == 'Completed') or (_num(w.produced_qty) + 1e-6 >= _num(w.qty) > 0)
            wo_detail.append({"wo": w.name, "qty": _num(w.qty), "status": w.status,
                              "item_code": pic, "kind": kind, "completed": completed,
                              "pp": pp_by_ppi.get(w.production_plan_item or "", ""),
                              "produced_head": _num(w.produced_qty), "done": done_qty,
                              "ops_done": ops_done, "ops_total": len(req_ops),
                              "last_end": max(jc_ends) if jc_ends else "",
                              "operations": op_axis, "tracking_numbers": tn_rows,
                              "unassigned": unassigned})

        # 「忘点完工」探测：成品(KS)工单未完工，但同行的皮壳/内胆兄弟工单**全部已完成**
        fins = [w for w in wo_detail if w["kind"] == "成品"]
        comps = [w for w in wo_detail if w["kind"] in ("皮壳", "内胆")]
        forgot = [f["wo"] for f in fins if not f["completed"]] if (comps and all(c["completed"] for c in comps)) else []

        # 本行计划 = 按 SO 行连接的计划行 + 工单所属计划（皮壳/内胆的计划行可能不带 SO 行，靠工单反查补上）
        by_pp = {}
        for p in plans:
            e = by_pp.setdefault(p.pp, {"pp": p.pp, "planned_qty": 0.0, "pending_qty": 0.0})
            e["planned_qty"] += _num(p.planned_qty)
            e["pending_qty"] += _num(p.pending_qty)
        for _w in wo_detail:
            if _w["pp"]:
                by_pp.setdefault(_w["pp"], {"pp": _w["pp"], "planned_qty": 0.0, "pending_qty": 0.0})
        _plans_out = list(by_pp.values())

        # 销售出库（可能一对多：一条订单行拆多张 DN / 含退货）
        dns = frappe.db.sql(
            """select dn.name as dn, dn.posting_date as date, dn.status as status,
                      dn.docstatus as docstatus, ifnull(dn.is_return, 0) as is_return,
                      dni.qty as qty, dni.so_detail as so_detail
               from `tabDelivery Note Item` dni
               join `tabDelivery Note` dn on dn.name = dni.parent
               where dni.against_sales_order = %(so)s
                 and (dni.so_detail = %(line)s
                      or (ifnull(dni.so_detail, '') = '' and dni.item_code = %(item)s))
                 and dn.docstatus in (0, 1)
               order by dn.posting_date, dn.name""",
            {"so": doc.name, "line": it.name, "item": it.item_code}, as_dict=True)
        shipped = sum(_num(d.qty) for d in dns if d.docstatus == 1)

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
            "plans": _plans_out,
            "wo_count": len(wos), "tn_count": line_tn,
            "forgot_complete": forgot,
            "dns": [{"dn": d.dn, "date": str(d.date or "")[:10], "qty": _num(d.qty),
                     "status": d.status, "docstatus": d.docstatus,
                     "is_return": d.is_return} for d in dns],
            "prog": ({"min": min(p[0] for p in prog_vals), "max": max(p[0] for p in prog_vals),
                      "total": max(p[1] for p in prog_vals)} if prog_vals else None),
            "delivery_date": str(it.delivery_date or "")[:10],
            "overdue_days": (getdate(today()) - getdate(it.delivery_date)).days
                            if it.delivery_date and open_qty > 0 else 0,
            "work_orders": wo_detail,
        })

    return {"sales_order": doc.name, "customer": doc.customer_name or doc.customer,
            "status": doc.status, "lines": lines}
