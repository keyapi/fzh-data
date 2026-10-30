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
from collections import defaultdict

import frappe
from frappe.utils import getdate, now_datetime, today
from key_test.production_evidence import (
    build_wo_evidence,
    evidence_status,
    proven_qty,
    rollup_line_evidence,
)
from key_test.supply_facts import (
    build_shipment_progress,
    load_job_card_time_logs,
    load_quality_inspections,
    load_shipments,
    load_stock_entries,
)
from key_test.supply_query import dn_logistic_numbers


def _num(v):
    try:
        return float(v or 0)
    except (TypeError, ValueError):
        return 0.0


def _merge_source_status(current, incoming):
    """Conservative aggregation. Unavailable/restricted is never overwritten."""
    incoming = dict(incoming or {})
    if current is None:
        return incoming
    if current.get("available", True) and not incoming.get("available", True):
        return incoming
    return current


def completion_state(evidence, qty, finished):
    """Return (completed, status); only eligible confidence can be complete."""
    evidence = evidence or {}
    if evidence.get("wo_cancelled"):
        return False, "unknown"
    target = ((evidence.get("stock_in_posted") if finished
               else evidence.get("all_process_done")) or {})
    proven = proven_qty(target)
    if proven is not None and proven + 1e-6 >= _num(qty) > 0:
        return True, "complete"
    if target.get("confidence") == "unknown":
        return False, "unknown"
    return False, "partial"


@frappe.whitelist()
def get_so_chain(sales_order):
    doc = frappe.get_doc("Sales Order", sales_order)
    if not frappe.has_permission("Sales Order", "read", doc):
        frappe.throw("无权限读取该销售订单")

    # 返工/纠正工序（如「质检发现问题」「通用返工」）—— 非常规必经，**不计入进度分母**
    corrective = {r.name for r in frappe.get_all(
        "Operation", filters={"is_corrective_operation": 1}, fields=["name"])}

    lines = []
    source_status = {}
    for it in doc.items:
        qty = _num(it.qty)
        delivered = _num(it.delivered_qty)
        open_qty = qty - delivered

        # 生产计划（按订单行连接键）—— 用于顶部的「本行计划/待产」数字
        plans = []
        pp_available = frappe.has_permission("Production Plan", "read")
        if pp_available:
            try:
                plan_rows = frappe.db.sql(
                    """select pp.name as pp, ppi.name as ppi, ppi.planned_qty, ppi.pending_qty
                       from `tabProduction Plan Item` ppi
                       join `tabProduction Plan` pp on pp.name = ppi.parent
                       where pp.docstatus = 1 and ppi.sales_order_item = %s""",
                    it.name, as_dict=True)
                plan_names = [p.pp for p in plan_rows if p.pp]
                permitted_pp = {row.name for row in frappe.get_list(
                    "Production Plan",
                    filters=[["name", "in", plan_names], ["docstatus", "=", 1]],
                    fields=["name"], limit_page_length=0)} if plan_names else set()
                if permitted_pp != set(plan_names):
                    pp_available = False
                    source_status.setdefault("production_plan", {
                        "available": False, "reason": "permission"})
                    plan_rows = [p for p in plan_rows if p.pp in permitted_pp]
                plans = plan_rows
            except Exception as exc:  # noqa: BLE001
                pp_available = False
                source_status["production_plan"] = {
                    "available": False, "reason": "query_error", "error": str(exc)}
        else:
            source_status.setdefault("production_plan", {
                "available": False, "reason": "permission"})

        # 工单 —— **成品**用 sales_order_item；**皮壳/内胆**用 fg_sales_order_item（不是 sales_order_item！）。
        # 一条成品(KS)行的标准结构 = 1 成品 + 1 皮壳(PK#) + 1 内胆(ND#)。兜底 production_plan_item。
        wos = frappe.db.sql(
            """select w.name, w.qty, w.status, w.docstatus, w.produced_qty,
                      w.production_item, w.production_plan_item, w.stock_uom
               from `tabWork Order` w
               where w.docstatus in (0, 1, 2) and (
                   w.sales_order_item = %(line)s
                   or w.fg_sales_order_item = %(line)s
                   or (ifnull(w.sales_order_item, '') = '' and ifnull(w.fg_sales_order_item, '') = '' and exists(
                        select 1 from `tabProduction Plan Item` ppi
                        where ppi.name = w.production_plan_item and ppi.sales_order_item = %(line)s))
               )
               order by w.name""", {"line": it.name}, as_dict=True)
        # 行级权限：先取当前用户可读的工单集合；受限单据不进入响应。
        wo_available = True
        if wos:
            if not frappe.has_permission("Work Order", "read"):
                wo_available = False
                source_status.setdefault("work_order", {"available": False,
                                                        "reason": "permission"})
                wos = []
            else:
                try:
                    permitted = {row.name for row in frappe.get_list(
                        "Work Order",
                        filters=[["name", "in", [w.name for w in wos]],
                                 ["docstatus", "in", (0, 1, 2)]],
                        fields=["name"], limit_page_length=0)}
                except Exception as exc:  # noqa: BLE001
                    wo_available = False
                    permitted = set()
                    source_status["work_order"] = {
                        "available": False, "reason": "query_error",
                        "error": str(exc)}
                if permitted != {w.name for w in wos}:
                    wo_available = False
                    source_status.setdefault("work_order", {
                        "available": False, "reason": "permission"})
                    wos = [w for w in wos if w.name in permitted]
        # 排序：**成品工单在前**（它是父），皮壳/内胆（子装配件）随后
        kind_rank = {"成品": 0, "皮壳": 1, "内胆": 2}
        wos.sort(key=lambda w: (kind_rank.get(
            "成品" if (w.production_item or "").startswith("KS")
            else "皮壳" if (w.production_item or "").startswith("PK#")
            else "内胆" if (w.production_item or "").startswith(("ND#", "DKND#")) else "z", 9),
            w.name))

        # WO 的 production_plan_item → PP。**不过滤 sales_order_item**：
        # 皮壳/内胆的计划行通常不带 SO 行（实测 WO.production_plan_item 100% 指向 Production Plan Item）。
        pp_by_ppi = {p.ppi: p.pp for p in plans}
        _ppi = [w.production_plan_item for w in wos if w.production_plan_item]
        if pp_available and _ppi:
            for r in frappe.get_all("Production Plan Item", filters={"name": ["in", _ppi]},
                                    fields=["name", "parent"]):
                pp_by_ppi[r.name] = r.parent

        # 工单物料名（用于明细里显示）
        _wo_items = sorted({w.production_item for w in wos if w.production_item})
        _item_name = {}
        if _wo_items:
            for r in frappe.get_all("Item", filters={"name": ["in", _wo_items]}, fields=["name", "item_name"]):
                _item_name[r.name] = r.item_name
        wo_names = [w.name for w in wos]

        # 工序行（菲号内部的排序轴）
        ops_by_wo = {}
        if wo_names:
            for o in frappe.get_all("Work Order Operation",
                                    filters={"parent": ["in", wo_names]},
                                    fields=["name", "parent", "operation", "sequence_id",
                                            "status", "completed_qty"]):
                ops_by_wo.setdefault(o.parent, []).append(o)

        # 工序卡（Job Card）—— 每张恰一个菲号(tracking_number) + 一道工序
        jc_done, jc_by_op = {}, {}
        jcs_by_wo = {}
        jc_available = True
        if wo_names:
            try:
                jc_rows = list(frappe.get_all(
                    "Job Card",
                    filters={"work_order": ["in", wo_names], "docstatus": ["<", 2]},
                    fields=["name", "work_order", "operation_id", "operation",
                            "status", "total_completed_qty", "for_quantity",
                            "actual_start_date", "actual_end_date",
                            "tracking_number", "docstatus"]))
            except Exception as exc:  # noqa: BLE001
                jc_rows = []
                jc_available = False
                source_status["job_card"] = {"available": False,
                                             "reason": "query_error",
                                             "error": str(exc)}
            if jc_rows and not frappe.has_permission("Job Card", "read"):
                jc_rows = []
                jc_available = False
                source_status.setdefault("job_card", {"available": False,
                                                      "reason": "permission"})
            elif jc_rows:
                try:
                    permitted = {row.name for row in frappe.get_list(
                        "Job Card",
                        filters=[["name", "in", [j.name for j in jc_rows]],
                                 ["docstatus", "<", 2]],
                        fields=["name"], limit_page_length=0)}
                except Exception as exc:  # noqa: BLE001
                    permitted = set()
                    jc_available = False
                    source_status["job_card"] = {"available": False,
                                                 "reason": "query_error",
                                                 "error": str(exc)}
                if permitted != {j.name for j in jc_rows}:
                    jc_available = False
                    source_status.setdefault("job_card", {"available": False,
                                                          "reason": "permission"})
                    jc_rows = [j for j in jc_rows if j.name in permitted]
            jc_time_logs, jc_time_status = load_job_card_time_logs(
                [j.name for j in jc_rows])
            if not jc_time_status["available"]:
                source_status["job_card_time_log"] = jc_time_status
            for j in jc_rows:
                j["time_logs"] = jc_time_logs.get(j.name, [])
                q = _num(j.total_completed_qty) or _num(j.for_quantity)
                rec = {"name": j.name, "status": j.status, "qty": q, "docstatus": j.docstatus,
                       "end": str(j.actual_end_date or "")[:19], "tn": j.tracking_number or ""}
                key = (j.work_order, j.operation)
                jc_by_op.setdefault(key, []).append(rec)
                jcs_by_wo.setdefault(j.work_order, []).append(j)
                if j.status == "Completed":
                    jc_done[key] = jc_done.get(key, 0.0) + q

        # 菲号（跟踪单号）
        tn_by_wo = {}
        tn_available = True
        if wo_names:
            try:
                tn_rows = list(frappe.get_all(
                    "Tracking Number",
                    filters={"work_order": ["in", wo_names]},
                    fields=["name", "work_order", "qty", "initial_work_order",
                            "so_materials", "finished_product_work_order"]))
            except Exception as exc:  # noqa: BLE001
                tn_rows = []
                tn_available = False
                source_status["tracking_number"] = {
                    "available": False, "reason": "query_error", "error": str(exc)}
            if tn_rows and not frappe.has_permission("Tracking Number", "read"):
                tn_rows = []
                tn_available = False
                source_status.setdefault("tracking_number", {
                    "available": False, "reason": "permission"})
            elif tn_rows:
                try:
                    permitted = {row.name for row in frappe.get_list(
                        "Tracking Number",
                        filters=[["name", "in", [t.name for t in tn_rows]]],
                        fields=["name"], limit_page_length=0)}
                except Exception as exc:  # noqa: BLE001
                    permitted = set()
                    tn_available = False
                    source_status["tracking_number"] = {
                        "available": False, "reason": "query_error", "error": str(exc)}
                if permitted != {t.name for t in tn_rows}:
                    tn_available = False
                    source_status.setdefault("tracking_number", {
                        "available": False, "reason": "permission"})
                    tn_rows = [t for t in tn_rows if t.name in permitted]
            for t in tn_rows:
                tn_by_wo.setdefault(t.work_order, []).append(t)

        # 统一生产证据（与 supply_facts 同一实现；不在本处单独算完工量）
        stock_by_wo, stock_status = (
            load_stock_entries(wo_names) if frappe.has_permission("Stock Entry", "read")
            else ({}, {"available": False, "reason": "permission"}))
        jc_to_wo = {jc.name: wo_name for wo_name, rows in jcs_by_wo.items()
                    for jc in rows}
        se_to_wo = {entry.get("name"): wo_name for wo_name, rows in stock_by_wo.items()
                    for entry in rows}
        qc_by_wo, qc_status = (
            load_quality_inspections(jc_to_wo, se_to_wo)
            if frappe.has_permission("Quality Inspection", "read")
            else ({}, {"available": False, "reason": "permission"}))
        process_available = (wo_available and jc_available and tn_available
                             and frappe.has_permission("Job Card", "read"))
        availability = {
            "job_cards": process_available,
            "work_order": wo_available,
            "tracking_numbers": tn_available and wo_available,
            "stock_entries": stock_status["available"],
            "quality_inspections": qc_status["available"],
        }
        source_status["stock_entry"] = _merge_source_status(
            source_status.get("stock_entry"), stock_status)
        source_status["quality_inspection"] = _merge_source_status(
            source_status.get("quality_inspection"), qc_status)
        wo_evidence_map = {}
        for w in wos:
            wo_evidence_map[w.name] = build_wo_evidence(
                {"name": w.name, "qty": _num(w.qty), "stock_uom": w.stock_uom,
                 "production_item": w.production_item, "docstatus": w.docstatus},
                [{"name": o.name, "operation": o.operation,
                  "sequence_id": o.sequence_id,
                  "is_corrective_operation": o.operation in corrective,
                  "work_order": w.name}
                 for o in ops_by_wo.get(w.name, [])],
                [dict(j) for j in jcs_by_wo.get(w.name, [])],
                tn_by_wo.get(w.name, []),
                stock_by_wo.get(w.name, []), qc_by_wo.get(w.name, []),
                order_uom=it.uom,
                availability=availability,
                observed_at=str(now_datetime()))
        line_evidence = rollup_line_evidence(
            list(wo_evidence_map.values()), item_code=it.item_code,
            order_uom=it.uom)

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

            # 末道「报工完成量」：取**有工序卡**的最大 sequence 必经工序（护栏：将来启用无扫码的工序不会被选成末道），
            # 去重 = max(整批卡[无菲号]和, 逐菲号卡和) —— 生产实测「整批卡+逐菲号卡」并存会让朴素求和翻倍。
            last_done, last_op = None, ""
            if req_ops:
                ordered = sorted(req_ops, key=lambda o: (_num(o.sequence_id), o.operation or ""), reverse=True)
                chosen = next((o for o in ordered if jc_by_op.get((w.name, o.operation))), ordered[0])
                last_op = chosen.operation
                cards = [x for x in jc_by_op.get((w.name, chosen.operation), []) if x.get("docstatus") == 1]
                _batch = sum(x["qty"] for x in cards if not x["tn"])
                _per_tn = sum(x["qty"] for x in cards if x["tn"])
                last_done = max(_batch, _per_tn)

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
            evidence = wo_evidence_map.get(w.name) or {}
            all_ev = evidence.get("all_process_done") or {}
            first_ev = evidence.get("first_process_done") or {}
            stock_ev = evidence.get("stock_in_posted") or {}
            qc_ev = evidence.get("qc_performed") or {}
            all_qty = proven_qty(all_ev)
            stock_qty = proven_qty(stock_ev)
            completed, completion_status = completion_state(
                evidence, w.qty, kind == "成品")
            wo_detail.append({"wo": w.name, "qty": _num(w.qty), "status": w.status,
                              "docstatus": w.docstatus,
                              "cancelled": _num(w.docstatus) == 2,
                              "item_code": pic, "item_name": _item_name.get(pic, ""),
                              "kind": kind, "completed": completed,
                              "completion_status": completion_status,
                              "pp": pp_by_ppi.get(w.production_plan_item or "", ""),
                              "produced_head": _num(w.produced_qty), "done": all_qty,
                              "first_done": proven_qty(first_ev),
                              "all_process_done": all_qty,
                              "all_process_estimated": all_ev.get("qty_estimated"),
                              "all_process_confidence": all_ev.get("confidence"),
                              "all_process_status": evidence_status(all_ev),
                              "stock_in_posted": stock_qty,
                              "stock_status": evidence_status(stock_ev),
                              "qc_performed": proven_qty(qc_ev),
                              "last_op": last_op, "last_op_done": last_done,
                              "ops_done": ops_done, "ops_total": len(req_ops),
                              "last_end": max(jc_ends) if jc_ends else "",
                              "operations": op_axis, "tracking_numbers": tn_rows,
                              "unassigned": unassigned})

        # 「忘点完工」探测：成品(KS)工单未完工，但同行的皮壳/内胆兄弟工单**全部已完成**
        active_detail = [w for w in wo_detail if not w["cancelled"]]
        fins = [w for w in active_detail if w["kind"] == "成品"]
        comps = [w for w in active_detail if w["kind"] in ("皮壳", "内胆")]
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

        # 全工序 / 质检 / 入库统一来自 production_evidence；本处不再单独算完工量。
        all_ev = line_evidence.get("all_process_done") or {}
        first_ev = line_evidence.get("first_process_done") or {}
        stock_ev = line_evidence.get("stock_in_posted") or {}
        qc_ev = line_evidence.get("qc_performed") or {}
        qc_passed_ev = line_evidence.get("qc_passed") or {}
        line_produced = proven_qty(all_ev)
        line_estimated = (all_ev.get("qty_estimated")
                          if all_ev.get("confidence") in ("estimated", "mixed") else None)
        line_first = proven_qty(first_ev)
        reported = line_produced
        reported_estimated = line_estimated
        reported_status = evidence_status(all_ev)
        report_note = ("全工序已证" if line_produced is not None
                       else ("全工序仅估算" if line_estimated is not None
                             else "全工序证据未知"))
        instock = proven_qty(stock_ev)
        instock_status = evidence_status(stock_ev)
        qc_status = evidence_status(qc_ev)
        produced_sum = line_produced

        # 销售出库（可能一对多：一条订单行拆多张 DN / 含退货）—— 按**出库单**归组：
        # 一张 DN 可含多行(同物料也会拆多行)，所以「N单」必须数 DN 张数，不能数明细行数。
        dns, shipped = [], 0.0
        dn_available = frappe.has_permission("Delivery Note", "read")
        if dn_available:
            try:
                dn_rows = frappe.db.sql(
                    """select dn.name as dn, dn.posting_date as date, dn.status as status,
                              dn.docstatus as docstatus, ifnull(dn.is_return, 0) as is_return,
                              dni.item_code as item_code, dni.qty as qty, dni.so_detail as so_detail
                       from `tabDelivery Note Item` dni
                       join `tabDelivery Note` dn on dn.name = dni.parent
                       where dni.against_sales_order = %(so)s
                         and (dni.so_detail = %(line)s
                              or (ifnull(dni.so_detail, '') = '' and dni.item_code = %(item)s))
                         and dn.docstatus in (0, 1)
                       order by dn.posting_date, dn.name, dni.idx""",
                    {"so": doc.name, "line": it.name, "item": it.item_code}, as_dict=True)
                dn_names = sorted({d.dn for d in dn_rows if d.dn})
                permitted_dn = {row.name for row in frappe.get_list(
                    "Delivery Note",
                    filters=[["name", "in", dn_names], ["docstatus", "in", (0, 1)]],
                    fields=["name"], limit_page_length=0)} if dn_names else set()
                if permitted_dn != set(dn_names):
                    dn_available = False
                    source_status.setdefault("delivery_note", {
                        "available": False, "reason": "permission"})
                    dn_rows = [d for d in dn_rows if d.dn in permitted_dn]
            except Exception as exc:  # noqa: BLE001
                dn_rows = []
                dn_available = False
                source_status["delivery_note"] = {
                    "available": False, "reason": "query_error", "error": str(exc)}
            _dn_map = {}
            for d in dn_rows:
                e = _dn_map.setdefault(d.dn, {"dn": d.dn, "date": str(d.date or "")[:10],
                                              "status": d.status, "docstatus": d.docstatus,
                                              "is_return": d.is_return, "qty": 0.0, "lines": []})
                e["qty"] += _num(d.qty)
                e["lines"].append({"qty": _num(d.qty), "item_code": d.item_code})
            dns = list(_dn_map.values())
            shipped = sum(_num(d["qty"]) for d in dns if d["docstatus"] == 1)
        else:
            source_status.setdefault("delivery_note", {
                "available": False, "reason": "permission"})
        if dns and frappe.has_permission("Shipment", "read"):
            ship_numbers, shipment_by_number, _ship_restricted, event_status = \
                load_shipments(sorted({d.get("dn") for d in dns if d.get("dn")}))
        else:
            ship_numbers, shipment_by_number = {}, {}
            event_status = {"available": False, "restricted": False,
                            "reason": "permission"}
        if not event_status.get("available", True):
            source_status["shipment_logistics_event"] = event_status
        shipment_progress = build_shipment_progress(
            {"so": doc.name, "so_line": it.name, "item_code": it.item_code},
            {"dns": dns, "numbers_by_dn": ship_numbers,
             "shipment_by_number": shipment_by_number})
        # 阶段 0–3
        active_wos = [w for w in wos if _num(w.docstatus) != 2]
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
        elif not active_wos:
            stage, sub = 2, "工单已取消/证据未知"
        elif line_produced is None:
            stage, sub = 2, ("生产中/待证" if (line_first or 0) > 0 else "未开工/证据未知")
        elif line_produced + 1e-6 >= qty:
            stage, sub = 3, "全工序完成待出库"
        elif line_produced <= 0:
            stage, sub = 2, ("生产中" if (line_first or 0) > 0 else "未开工")
        else:
            stage, sub = 2, "生产中"

        lines.append({
            "so_line": it.name, "item_code": it.item_code, "item_name": it.item_name,
            "customer_item_code": it.customer_item_code,
            "qty": qty, "delivered": delivered, "open_qty": open_qty, "shipped_dn": shipped,
            "produced": produced_sum, "reported": reported, "instock": instock,
            "reported_status": reported_status,
            "reported_confidence": all_ev.get("confidence"),
            "instock_status": instock_status,
            "instock_confidence": stock_ev.get("confidence"),
            "instock_estimated": (stock_ev.get("qty_estimated")
                                  if stock_ev.get("confidence") in ("estimated", "mixed")
                                  else None),
            "qc_status": qc_status, "qc_confidence": qc_ev.get("confidence"),
            "qc_passed_status": qc_passed_ev.get("status"),
            "subassemblies": line_evidence.get("subassemblies") or [],
            "shipment_progress": shipment_progress,
            "evidence_reasons": all_ev.get("reasons") or [],
            "evidence_conflicts": sorted(
                {conflict.get("code") for conflict in (all_ev.get("conflicts") or [])
                 if conflict.get("code")}),
            "report_note": report_note,
            "first_process_done": line_first,
            "all_process_done": line_produced,
            "all_process_estimated": line_estimated,
            "qc_performed": proven_qty(qc_ev),
            "qc_passed": line_evidence.get("qc_passed"),
            "stock_in_posted": instock,
            "completion_status": completion_state(line_evidence, qty, False)[1],
            "production_evidence": line_evidence,
            "stage": stage, "substate": sub,
            "plans": _plans_out,
            "wo_count": len(wos), "active_wo_count": len(active_wos),
            "tn_count": line_tn,
            "forgot_complete": forgot,
            "dns": dns,
            "prog": ({"min": min(p[0] for p in prog_vals), "max": max(p[0] for p in prog_vals),
                      "total": max(p[1] for p in prog_vals)} if prog_vals else None),
            "delivery_date": str(it.delivery_date or "")[:10],
            "overdue_days": (getdate(today()) - getdate(it.delivery_date)).days
                            if it.delivery_date and open_qty > 0 else 0,
            "work_orders": wo_detail,
        })

    for name in ("sales_order", "production_plan", "delivery_note", "work_order",
                 "job_card", "tracking_number", "stock_entry",
                 "quality_inspection", "shipment_logistics_event"):
        source_status.setdefault(name, {"available": True})
    for name in ("tongtool_po", "receipt", "inventory"):
        source_status.setdefault(name, {"available": False,
                                        "reason": "not_integrated"})
    for state in source_status.values():
        state.setdefault("restricted", False)
        state.setdefault("reason", "")
    partial_reasons = [
        "%s source unavailable: %s" % (name.replace("_", " "),
                                       status.get("reason", "unknown"))
        for name, status in source_status.items()
        if not status.get("available", True)]
    return {"sales_order": doc.name, "customer": doc.customer_name or doc.customer,
            "status": doc.status, "lines": lines,
            "source_status": source_status,
            "partial": bool(partial_reasons),
            "partial_reasons": partial_reasons}


@frappe.whitelist()
def get_so_line_logistics(sales_order, so_line):
    """First-leg logistics for one SO line: DN → waybill numbers → Shipment + events."""
    doc = frappe.get_doc("Sales Order", sales_order)
    if not frappe.has_permission("Sales Order", "read", doc):
        frappe.throw("无权限读取该销售订单")
    item = next((it for it in doc.items if it.name == so_line), None)
    if not item:
        frappe.throw("订单行不存在或不属于该销售订单")

    result = {
        "sales_order": doc.name, "so_line": item.name, "item_code": item.item_code,
        "item_name": item.item_name,
        "permissions": {"delivery_note": True, "shipment": True},
        "source_status": {}, "partial": False,
        "dns": [],
    }
    if not frappe.has_permission("Delivery Note", "read"):
        result["permissions"]["delivery_note"] = False
        return result

    dn_rows = frappe.db.sql(
        """select distinct dn.name as dn, dn.posting_date as date, dn.status as status,
                  dn.docstatus as docstatus, ifnull(dn.is_return, 0) as is_return
           from `tabDelivery Note Item` dni
           join `tabDelivery Note` dn on dn.name = dni.parent
           where dni.against_sales_order = %(so)s
             and (dni.so_detail = %(line)s
                  or (ifnull(dni.so_detail, '') = '' and dni.item_code = %(item)s))
             and dn.docstatus in (0, 1)
           order by dn.posting_date, dn.name""",
        {"so": doc.name, "line": item.name, "item": item.item_code}, as_dict=True,
    )
    if not dn_rows:
        return result

    dn_names = [row.dn for row in dn_rows]
    permitted_dns = {row.name for row in frappe.get_list(
        "Delivery Note", filters=[["name", "in", dn_names], ["docstatus", "in", (0, 1)]],
        fields=["name"], limit_page_length=0)}
    if permitted_dns != set(dn_names):
        result["permissions"]["delivery_note"] = False
        return result

    numbers_by_dn = dn_logistic_numbers(dn_names)
    all_numbers = sorted({n["number"] for values in numbers_by_dn.values() for n in values})
    shipment_by_number, shipment_groups = {}, defaultdict(list)
    events_by_shipment, identity_conflicts = defaultdict(list), {}
    event_status = {"available": True, "restricted": False, "reason": ""}
    if all_numbers and not (
            frappe.has_permission("Shipment", "read")
            and frappe.db.has_column("Shipment", "custom_zmt_logistic_number")):
        result["permissions"]["shipment"] = False
        event_status = {"available": False, "restricted": False,
                        "reason": "permission"}
    elif all_numbers:
        candidates = frappe.db.sql(
            """select name, custom_zmt_logistic_number as number,
                      custom_zmt_status4 as status4, custom_zmt_status11 as status11,
                      custom_zmt_last_node as last_node, custom_zmt_eta as eta,
                      custom_zmt_atd as atd, custom_zmt_ata as ata, custom_zmt_dlvr as dlvr,
                      custom_zmt_match_status as match_status, custom_zmt_source as source
               from `tabShipment`
               where custom_zmt_logistic_number in %(numbers)s and docstatus in (0, 1)""",
            {"numbers": tuple(all_numbers)}, as_dict=True,
        )
        permitted_shipments = {row.name for row in frappe.get_list(
            "Shipment",
            filters=[["custom_zmt_logistic_number", "in", all_numbers],
                     ["docstatus", "in", (0, 1)]],
            fields=["name"], limit_page_length=0)}
        for candidate in candidates:
            if candidate.name in permitted_shipments:
                shipment_groups[candidate.number].append(candidate)
        for number, rows in shipment_groups.items():
            rows.sort(key=lambda row: str(row.name))
            if len(rows) == 1:
                shipment_by_number[number] = rows[0]
            else:
                # Never elect a representative: the whole number is unresolved.
                identity_conflicts[number] = [row.name for row in rows]
        parents = sorted({row.name for rows in shipment_groups.values()
                          for row in rows})
        if parents:
            try:
                # Child event rows inherit the parent Shipment permission; do
                # not probe the child doctype itself (false negatives).
                for event in frappe.get_all(
                        "Shipment Logistics Event",
                        filters={"parent": ["in", parents],
                                 "parenttype": "Shipment"},
                        fields=["parent", "seq", "event_time", "event_name",
                                "event_date", "location", "description"],
                        order_by="parent asc, idx asc"):
                    events_by_shipment[event.parent].append({
                        "seq": event.seq,
                        "time": str(event.event_time or "")[:16],
                        "name": event.event_name or "",
                        "date": str(event.event_date or "")[:10],
                        "location": event.location or "",
                        "description": event.description or "",
                    })
            except Exception as exc:  # noqa: BLE001
                permission = type(exc).__name__ in (
                    "PermissionError", "frappe.exceptions.PermissionError")
                event_status = {
                    "available": False, "restricted": permission,
                    "reason": "permission" if permission else "query_error",
                    "error": str(exc)}

    def _evidence(raw):
        return {
            "shipment": raw.name,
            "status4": raw.status4 or "", "status11": raw.status11 or "",
            "last_node": str(raw.last_node or "")[:10],
            "eta": str(raw.eta or "")[:10], "atd": str(raw.atd or "")[:10],
            "ata": str(raw.ata or "")[:10], "dlvr": str(raw.dlvr or "")[:10],
            "match_status": raw.match_status or "", "source": raw.source or "",
            "events": events_by_shipment.get(raw.name, []),
        }

    result["source_status"] = {"shipment_logistics_event": event_status}
    result["partial"] = not event_status.get("available", True)

    for row in dn_rows:
        numbers = []
        for entry in numbers_by_dn.get(row.dn, []):
            rows = shipment_groups.get(entry["number"], [])
            shipment = shipment_by_number.get(entry["number"])
            numbers.append({
                "number": entry["number"], "primary": entry["primary"],
                "shipment": shipment.name if shipment else "",
                "identity_conflict": len(rows) > 1,
                "shipment_candidates": [raw.name for raw in rows] if len(rows) > 1 else [],
                "shipment_evidence": [_evidence(raw) for raw in rows],
                "status4": shipment.status4 if shipment else "",
                "status11": shipment.status11 if shipment else "",
                "last_node": str(shipment.last_node or "")[:10] if shipment else "",
                "eta": str(shipment.eta or "")[:10] if shipment else "",
                "atd": str(shipment.atd or "")[:10] if shipment else "",
                "ata": str(shipment.ata or "")[:10] if shipment else "",
                "dlvr": str(shipment.dlvr or "")[:10] if shipment else "",
                "match_status": shipment.match_status if shipment else "",
                "source": shipment.source if shipment else "",
                "events": events_by_shipment.get(shipment.name, []) if shipment else [],
            })
        result["dns"].append({
            "dn": row.dn, "date": str(row.date or "")[:10], "status": row.status,
            "docstatus": row.docstatus, "is_return": row.is_return, "numbers": numbers,
        })
    return result
