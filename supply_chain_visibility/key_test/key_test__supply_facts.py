# -*- coding: utf-8 -*-
"""Supply facts contract v1: stage balances, milestones, availability, links.

One calculation shared by the machine batch entry and the SO human view.
This module never writes to ERPNext and never guesses quantities or dates:
missing evidence stays null with an explicit reason.
"""
import json
import uuid
from collections import defaultdict

import frappe
from frappe.utils import getdate, now_datetime, today

from key_test.supply_query import dn_logistic_numbers

SCHEMA_VERSION = "supply-facts/v1"
RULE_VERSION = "2026-10-27.2"

STAGE_NOT_PLANNED = "not_planned"
STAGE_IN_PRODUCTION = "in_production"
STAGE_PRODUCED_PENDING = "produced_pending_dn"
STAGE_IN_TRANSIT = "shipped_in_transit"
STAGE_ARRIVED = "arrived_not_sellable"
STAGE_DELIVERED = "delivered_sellable"
STAGE_CANCELLED = "cancelled"
STAGE_RETURNED = "returned"
STAGE_DRAFT = "draft_dn"
STAGE_UNKNOWN = "unknown"

ARRIVED_STATUSES = {
    "已到港", "清关中", "已清关", "已转运", "派送中", "已签收", "已上传POD",
}
RECEIVED_STATUSES = {"已签收", "已上传POD"}
EXECUTED_STAGES = {
    STAGE_NOT_PLANNED, STAGE_IN_PRODUCTION, STAGE_PRODUCED_PENDING,
    STAGE_IN_TRANSIT, STAGE_ARRIVED, STAGE_DELIVERED,
}


def _num(value):
    try:
        return float(value or 0)
    except (TypeError, ValueError):
        return 0.0


def _day(value):
    return str(value)[:10] if value else None


def _iso(value):
    return str(value).replace(" ", "T")[:19] if value else None


def _qty_status(qty, uom):
    if qty is None:
        return "unknown"
    return "known" if uom else "unknown"


def _balance(line, stage, qty, uom, detail="", batch_key="", source="",
             reason="", in_stock="unknown", qty_status=None, qty_basis="",
             demand_status="active", warehouse=None):
    status = qty_status or _qty_status(qty, uom)
    return {
        "so": line.get("so"), "so_line_id": line.get("so_line"),
        "item_code": line.get("item_code"),
        "warehouse": warehouse if warehouse is not None else line.get("warehouse"),
        "uom": uom, "stage": stage, "stage_detail": detail,
        "qty": None if qty is None else round(_num(qty), 6),
        "qty_status": status, "qty_basis": qty_basis,
        "batch_key": batch_key, "source_record": source,
        "exclusion_reason": reason, "included_in_stock": in_stock,
        "demand_status": demand_status,
        "scope": line.get("scope") or "in_house",
        "role": line.get("role") or "finished",
    }


def build_stage_balances(line, ctx):
    """Mutually exclusive current-stage balances; historical totals stay separate."""
    qty = line.get("qty")
    uom = line.get("uom")
    if qty is None or not uom:
        return [_balance(line, STAGE_UNKNOWN, qty, uom, reason="订单数量或单位未证")]
    cancelled = int(line.get("so_docstatus") or 0) == 2
    demand_status = "cancelled" if cancelled else "active"
    if not ctx.get("dn_permission"):
        return [_balance(line, STAGE_UNKNOWN, qty, uom, reason="无出库单读取权限",
                         demand_status=demand_status)]

    dns = ctx.get("dns") or []
    submitted = [d for d in dns if int(d.get("docstatus") or 0) == 1]
    drafts = [d for d in dns if int(d.get("docstatus") or 0) == 0]
    rows = []

    open_drafts = [d for d in drafts if not int(d.get("is_return") or 0)]
    if open_drafts:
        rows.append(_balance(line, STAGE_DRAFT, None, uom,
                             detail="草稿出库 %d 张（未执行，不计入余额）" % len(open_drafts),
                             reason="草稿不是已执行出库，数量不重复计入",
                             demand_status=demand_status))

    returns = [d for d in submitted if int(d.get("is_return") or 0)]
    nonreturns = [d for d in submitted if not int(d.get("is_return") or 0)]

    unconverted = [d for d in submitted if not d.get("uom") or d.get("uom") != uom]
    if unconverted:
        missing = [d for d in unconverted if not d.get("uom")]
        rows.append(_balance(
            line, STAGE_UNKNOWN, None, uom,
            reason=("出库单位缺失，无换算依据，数量归属未知" if missing
                    else "出库单位与订单单位不一致，无换算证据，数量归属未知"),
            demand_status=demand_status))
        for dn in submitted:
            if int(dn.get("is_return") or 0):
                rows.append(_balance(
                    line, STAGE_RETURNED, abs(_num(dn.get("qty"))), dn.get("uom"),
                    detail="销售退货（单位未归一）", batch_key=dn.get("dn"),
                    source=dn.get("dn"), reason="退货单位未证，未按原单抵扣",
                    warehouse=dn.get("warehouse"), demand_status=demand_status))
            else:
                rows.append(_balance(
                    line, STAGE_IN_TRANSIT, _num(dn.get("qty")), dn.get("uom"),
                    detail="出库单位 %s（未归一）" % (dn.get("uom") or "缺失"),
                    batch_key=dn.get("dn"), source=dn.get("dn"),
                    reason="单位与订单不一致或缺失，未归一",
                    warehouse=dn.get("warehouse"), demand_status=demand_status))
        return rows

    allocated = defaultdict(float)
    allocated_by_item = defaultdict(float)
    unallocated = []
    dn_names = {d.get("dn") for d in nonreturns}
    for ret in returns:
        against = ret.get("return_against")
        amount = -_num(ret.get("qty"))
        if against and against in dn_names:
            allocated[against] += amount
            item = ret.get("dn_detail")
            if item:
                allocated_by_item[item] += amount
        else:
            unallocated.append(ret)
    returned_total = sum(-_num(r.get("qty")) for r in returns)
    if returned_total > 1e-9:
        rows.append(_balance(line, STAGE_RETURNED, returned_total, uom,
                             detail="销售退货（%d 张）" % len(returns),
                             reason=("退货未关联原出库单，实物去向未证"
                                     if unallocated else "已按原出库单抵扣"),
                             demand_status=demand_status))

    numbers = ctx.get("numbers_by_dn") or {}
    shipment_by_number = ctx.get("shipment_by_number") or {}
    shipped_physical = 0.0
    shipped_net = 0.0
    grouped_dns = defaultdict(list)
    for dn in nonreturns:
        grouped_dns[dn.get("dn")].append(dn)
    for dn_name, dn_rows in grouped_dns.items():
        gross_total = sum(_num(r.get("qty")) for r in dn_rows)
        ret_total = min(allocated.get(dn_name, 0.0), gross_total)
        net_total = max(0.0, gross_total - ret_total)
        shipped_physical += gross_total
        shipped_net += net_total
        row_allocs = []
        for dn in dn_rows:
            names = dn.get("dn_items") or [dn.get("dn_item")]
            alloc = sum(allocated_by_item.get(n, 0.0) for n in names if n)
            row_allocs.append(min(alloc, _num(dn.get("qty"))))
        leftover = ret_total - sum(row_allocs)
        if leftover > 1e-9 and len(dn_rows) == 1:
            room = max(0.0, _num(dn_rows[0].get("qty")) - row_allocs[0])
            absorbed = min(leftover, room)
            row_allocs[0] += absorbed
            leftover -= absorbed
        if leftover > 1e-9:
            if net_total > 1e-9:
                rows.append(_balance(
                    line, STAGE_UNKNOWN, net_total, uom,
                    detail="退货无原出库明细归属，分仓数量未知",
                    reason="退货无法归属到原出库明细，仅保留 DN 净额，不摊到具体仓库",
                    batch_key=dn_name, source=dn_name,
                    demand_status=demand_status))
            continue
        for dn, row_alloc in zip(dn_rows, row_allocs):
            gross_qty = _num(dn.get("qty"))
            net_qty = max(0.0, gross_qty - row_alloc)
            if net_qty <= 1e-9:
                continue
            dn_numbers = [n["number"] for n in numbers.get(dn_name, [])]
            statuses = [((shipment_by_number.get(number) or {}).get("status11") or "")
                        for number in dn_numbers]
            known = [s for s in statuses if s]
            stage, detail, reason = STAGE_IN_TRANSIT, "在途", ""
            if not dn_numbers:
                detail, reason = "运单未登记", ""
            elif (len(known) == len(statuses)
                  and all(s in RECEIVED_STATUSES for s in known)):
                stage, detail, reason = STAGE_ARRIVED, "已签收/POD（不等于可售）", "缺入库/上架证据"
            elif (len(known) == len(statuses)
                  and all(s in ARRIVED_STATUSES for s in known)):
                stage, detail, reason = STAGE_ARRIVED, "到港/清关/派送（未证可售）", "缺入库/上架证据"
            elif len(known) < len(statuses):
                detail = ("运单状态未知（未匹配 Shipment）" if not known
                          else "部分运单状态未知，不判定到港")
                reason = "缺运单状态证据"
            elif len(dn_numbers) > 1:
                detail, reason = "多运单，到货分配未知", "多运单未提供数量分配证据"
            if not ctx.get("shipment_permission"):
                detail, reason = "状态未知（无 Shipment 读取权限）", "缺 Shipment 权限"
            rows.append(_balance(line, stage, net_qty, uom, detail=detail,
                                 batch_key=dn_name, source=dn_name, reason=reason,
                                 warehouse=dn.get("warehouse"),
                                 demand_status=demand_status))

    own_wos = [w for w in (ctx.get("wos") or []) if w.get("item_code") == line.get("item_code")]
    own_pps = [p for p in (ctx.get("pps") or []) if p.get("item_code") == line.get("item_code")]
    pp_coverage = min(sum(_num(p.get("planned_qty")) for p in own_pps), _num(qty))
    pp_ok = ctx.get("production_plan_permission", True)
    wo_units_ok = all((w.get("stock_uom") or "") == uom for w in own_wos)
    produced_estimated = any(w.get("produced_basis") == "wo_produced_qty" for w in own_wos)
    produced_total = (sum(_num(w.get("produced")) for w in own_wos)
                      if wo_units_ok else 0.0)
    produced_capped = min(produced_total, _num(qty))
    wo_coverage = (min(sum(_num(w.get("qty")) for w in own_wos), _num(qty))
                   if wo_units_ok else 0.0)
    open_net = _num(qty) - shipped_net
    produced_pending = max(0.0, min(produced_capped - shipped_physical, open_net))
    remaining = max(0.0, open_net - produced_pending)
    if produced_pending > 1e-9:
        rows.append(_balance(line, STAGE_PRODUCED_PENDING, produced_pending, uom,
                             detail="合格完工待出库", reason="缺出库单",
                             qty_status="estimated" if produced_estimated else "known",
                             qty_basis="wo_produced_qty" if produced_estimated
                             else "job_card_first_op",
                             demand_status=demand_status))
    if not cancelled and remaining > 1e-9:
        return_gap = min(returned_total, remaining)
        if return_gap > 1e-9:
            rows.append(_balance(line, STAGE_UNKNOWN, return_gap, uom,
                                 reason="退货实物可用性未证，需求余额不推断为待出库/在产",
                                 demand_status=demand_status))
            remaining -= return_gap
        if remaining > 1e-9:
            if not ctx.get("work_order_permission"):
                rows.append(_balance(line, STAGE_UNKNOWN, remaining, uom,
                                     reason="无工单读取权限（含行级受限），阶段未知",
                                     demand_status=demand_status))
            elif not wo_units_ok:
                rows.append(_balance(line, STAGE_UNKNOWN, remaining, uom,
                                     reason="工单单位与订单单位不一致，完工/在产数量未归一",
                                     demand_status=demand_status))
            else:
                production_gap = max(0.0, wo_coverage - produced_capped)
                in_production = min(remaining, production_gap)
                if in_production > 1e-9:
                    rows.append(_balance(
                        line, STAGE_IN_PRODUCTION, in_production, uom,
                        detail="在产/部分完工",
                        source=",".join(w.get("wo") for w in own_wos),
                        demand_status=demand_status))
                leftover = remaining - in_production
                if leftover > 1e-9:
                    plan_only = min(leftover, max(0.0, pp_coverage - wo_coverage))
                    if plan_only > 1e-9:
                        rows.append(_balance(
                            line, STAGE_UNKNOWN, plan_only, uom,
                            detail="已提交生产计划，未建工单",
                            reason="生产计划覆盖但阶段枚举无法表达，不判为未计划",
                            demand_status=demand_status))
                        leftover -= plan_only
                    if leftover > 1e-9:
                        if not pp_ok:
                            rows.append(_balance(
                                line, STAGE_UNKNOWN, leftover, uom,
                                reason="无生产计划读取权限（含行级受限），阶段未知",
                                demand_status=demand_status))
                        else:
                            detail = ("无工单/生产计划"
                                      if wo_coverage <= 1e-9 and pp_coverage <= 1e-9
                                      else "无工单/生产计划覆盖")
                            rows.append(_balance(line, STAGE_NOT_PLANNED, leftover, uom,
                                                 detail=detail,
                                                 demand_status=demand_status))

    if cancelled:
        rows.append(_balance(line, STAGE_CANCELLED, qty, uom,
                             detail="需求已取消（实物见同组 physical 片段）",
                             source=line.get("so"),
                             reason="取消不删除已生产/已发实物，实物单独保留",
                             demand_status="cancelled"))
        return rows

    known = sum(r["qty"] for r in rows
                if r["qty"] is not None
                and r["stage"] not in (STAGE_RETURNED, STAGE_DRAFT, STAGE_CANCELLED))
    diff = round(_num(qty) - known, 6)
    if diff > 1e-6:
        rows.append(_balance(line, STAGE_UNKNOWN, diff, uom,
                             reason="数量阶段证据不足，未归属", demand_status=demand_status))
    elif diff < -1e-6:
        rows.append(_balance(line, STAGE_UNKNOWN, -diff, uom,
                             reason="超发/重复证据或退货无仓级归属，待核实",
                             demand_status=demand_status))
    return rows


def build_milestones(line, ctx):
    observed = _iso(ctx.get("observed_at") or now_datetime())
    order_uom = line.get("uom")
    rows = []

    def add(node, baseline=None, committed=None, latest=None, actual=None, qty=None,
            source="", note=""):
        rows.append({
            "so": line.get("so"), "so_line_id": line.get("so_line"),
            "item_code": line.get("item_code"), "uom": line.get("uom"), "node": node,
            "baseline_planned_at": _day(baseline),
            "committed_due_at": _day(committed),
            "latest_expected_at": _day(latest),
            "actual_at": _day(actual),
            "qty": None if qty is None else round(_num(qty), 6),
            "qty_status": _qty_status(qty, line.get("uom")),
            "date_precision": "day", "timezone_status": "unverified",
            "observed_at": observed, "source_record": source,
            "note": note, "rule_version": RULE_VERSION,
        })

    def join_notes(*notes):
        return "；".join(n for n in notes if n)

    def unit_note(units):
        return "来源单位 %s 与订单单位 %s 不一致或缺失，数量未归一" % (
            "/".join(sorted(u or "缺失" for u in units)) or "缺失", order_uom or "缺失")

    add("order_placed", actual=line.get("transaction_date"), qty=line.get("qty"),
        source="Sales Order.transaction_date")
    add("promised_delivery", baseline=line.get("delivery_date"), latest=line.get("delivery_date"),
        qty=line.get("qty"), source="Sales Order Item.delivery_date",
        note="无独立承诺字段；当前预计沿用订单交期")

    wos = ctx.get("wos") or []
    own_wos = [w for w in wos if w.get("item_code") == line.get("item_code")]
    if own_wos:
        starts = [w["planned_start_date"] for w in own_wos if w.get("planned_start_date")]
        ends = [w["planned_end_date"] for w in own_wos if w.get("planned_end_date")]
        jc_starts = [w["jc_start"] for w in own_wos if w.get("jc_start")]
        jc_ends = [w["jc_end"] for w in own_wos if w.get("jc_end")]
        wo_units = {w.get("stock_uom") or "" for w in own_wos}
        wo_units_ok = wo_units == {order_uom}
        add("production_start", baseline=min(starts, default=None),
            latest=min(starts, default=None), actual=min(jc_starts, default=None),
            qty=(min(sum(_num(w.get("qty")) for w in own_wos), _num(line.get("qty")))
                 if wo_units_ok else None),
            source="Work Order/JC",
            note=join_notes("有计划无报工时不填实际",
                            "" if wo_units_ok else unit_note(wo_units)))
        add("production_end", baseline=max(ends, default=None),
            latest=max(ends, default=None), actual=max(jc_ends, default=None),
            qty=(min(sum(_num(w.get("produced")) for w in own_wos), _num(line.get("qty")))
                 if wo_units_ok else None),
            source="Work Order/JC",
            note=join_notes("实际完工取工序卡；计划仅供延期分析",
                            "" if wo_units_ok else unit_note(wo_units)))

    submitted = [d for d in (ctx.get("dns") or []) if int(d.get("docstatus") or 0) == 1]
    nonreturns = [d for d in submitted if not int(d.get("is_return") or 0)]
    if nonreturns:
        dn_units = {d.get("uom") or "" for d in nonreturns}
        dn_units_ok = dn_units == {order_uom}
        add("dispatch",
            actual=min((d["date"] for d in nonreturns if d.get("date")), default=None),
            qty=(sum(_num(d.get("qty")) for d in nonreturns) if dn_units_ok else None),
            source="Delivery Note.posting_date",
            note=join_notes("过账不等于实际起运",
                            "" if dn_units_ok else unit_note(dn_units)))

    shipments = list((ctx.get("shipment_by_number") or {}).values())
    if shipments:
        add("departure",
            actual=min((s.get("atd") for s in shipments if s.get("atd")), default=None),
            source="Shipment.custom_zmt_atd")
        add("arrival",
            latest=max((s.get("eta") for s in shipments if s.get("eta")), default=None),
            actual=max((s.get("ata") for s in shipments if s.get("ata")), default=None),
            source="Shipment.custom_zmt_eta/ata", note="ETA 为承运商预计，不是可用日")
        add("delivery",
            actual=max((s.get("dlvr") for s in shipments if s.get("dlvr")), default=None),
            source="Shipment.custom_zmt_dlvr", note="POD/签收不等于上架可售")
    return rows


def _tranche(line, tranche_id, qty, uom, *, stage, available_date=None, eta=None,
             scenario="unknown", reason="", batch_key="", source="", date_kind="unknown",
             qty_status=None, qty_basis="", demand_status="active", warehouse=None):
    return {
        "tranche_id": "%s::%s" % (line.get("so_line"), tranche_id),
        "so": line.get("so"), "so_line_id": line.get("so_line"),
        "item_code": line.get("item_code"),
        "warehouse": warehouse if warehouse is not None else line.get("warehouse"),
        "uom": uom, "qty": None if qty is None else round(_num(qty), 6),
        "qty_status": qty_status or _qty_status(qty, uom), "qty_basis": qty_basis,
        "stage": stage,
        "available_date": _day(available_date), "latest_expected_at": _day(eta),
        "date_kind": date_kind,
        "date_confidence": "unknown" if not available_date else "estimated",
        "scenario": scenario, "eligible": False, "exclusion_reason": reason,
        "batch_key": batch_key, "source_record": source, "rule_version": RULE_VERSION,
        "demand_status": demand_status,
    }


def build_availability(line, ctx, stage_rows):
    """Sellable tranches; no tranche enters B_min/B_max without receipt evidence."""
    numbers = ctx.get("numbers_by_dn") or {}
    shipment_by_number = ctx.get("shipment_by_number") or {}
    dn_items = {}
    for dn in ctx.get("dns") or []:
        if int(dn.get("docstatus") or 0) != 1 or int(dn.get("is_return") or 0):
            continue
        dn_items[(dn.get("dn"), dn.get("warehouse"), dn.get("uom"))] = dn.get("dn_item") or ""
    rows = []
    for stage_row in stage_rows:
        if stage_row["stage"] in (STAGE_CANCELLED, STAGE_UNKNOWN, STAGE_RETURNED, STAGE_DRAFT):
            continue
        if stage_row.get("demand_status") == "cancelled":
            continue
        unit = stage_row.get("uom")
        warehouse = stage_row.get("warehouse")
        if stage_row["stage"] in (STAGE_IN_TRANSIT, STAGE_ARRIVED):
            dn = stage_row["batch_key"]
            dn_item = dn_items.get((dn, warehouse, unit), "")
            dn_numbers = [n["number"] for n in numbers.get(dn, [])]
            if len(dn_numbers) > 1:
                rows.append(_tranche(
                    line, "%s::%s::%s::multi" % (dn, warehouse or "", dn_item), None, unit,
                    stage=stage_row["stage"], scenario="allocation_unknown",
                    batch_key=dn, source=dn, warehouse=warehouse,
                    reason="多运单分配未知，不复制 DN 全量"))
                continue
            shipment = shipment_by_number.get(dn_numbers[0]) if dn_numbers else {}
            eta = (shipment or {}).get("eta")
            reason = ("到货/POD 未证可售" if stage_row["stage"] == STAGE_ARRIVED
                      else "ETA 未经入库/上架验证")
            rows.append(_tranche(
                line, "%s::%s::%s::%s" % (dn, warehouse or "", dn_item,
                                          dn_numbers[0] if dn_numbers else "NO_NUMBER"),
                stage_row["qty"], unit, stage=stage_row["stage"], eta=eta,
                scenario="conditional" if eta else "unknown", batch_key=dn, source=dn,
                warehouse=warehouse, reason=reason,
                qty_status=stage_row.get("qty_status"),
                qty_basis=stage_row.get("qty_basis", "")))
        elif stage_row["stage"] in (STAGE_PRODUCED_PENDING, STAGE_IN_PRODUCTION,
                                    STAGE_NOT_PLANNED, STAGE_DELIVERED):
            rows.append(_tranche(
                line, "%s::%s" % (stage_row["stage"], stage_row.get("batch_key") or ""),
                stage_row["qty"], unit, stage=stage_row["stage"],
                scenario="unknown", reason="缺生产/完工/入库日期证据",
                warehouse=warehouse, qty_status=stage_row.get("qty_status"),
                qty_basis=stage_row.get("qty_basis", "")))
    return rows


def build_links(line, ctx):
    rows = []

    def edge(source_doctype, source_name, source_line, relation, target_doctype,
             target_name, qty=None, uom=None, proof="", allocation=None):
        rows.append({
            "so": line.get("so"), "so_line_id": line.get("so_line"),
            "source_doctype": source_doctype, "source_name": source_name,
            "source_line_id": source_line, "relation": relation,
            "target_doctype": target_doctype, "target_name": target_name,
            "qty": None if qty is None else round(_num(qty), 6),
            "uom": uom, "proof": proof, "allocation": allocation or "unknown",
        })

    order_uom = line.get("uom")
    edge("Sales Order", line.get("so"), line.get("so_line"), "order_line",
         "Item", line.get("item_code"), qty=line.get("qty"), uom=order_uom,
         proof="so_item_fk")
    for pp in ctx.get("pps") or []:
        pp_uom = pp.get("stock_uom")
        pp_ok = bool(pp_uom) and pp_uom == order_uom
        edge("Sales Order Item", line.get("so_line"), line.get("so_line"), "planned_by",
             "Production Plan", pp.get("pp"),
             qty=pp.get("planned_qty") if pp_ok else None,
             uom=pp_uom if pp_ok else (pp_uom or None),
             proof="ppi.sales_order_item")
    for wo in ctx.get("wos") or []:
        wo_uom = wo.get("stock_uom")
        wo_ok = bool(wo_uom) and wo_uom == order_uom
        edge("Sales Order Item", line.get("so_line"), line.get("so_line"), "produced_by",
             "Work Order", wo.get("wo"), qty=wo.get("qty") if wo_ok else None,
             uom=wo_uom if wo_ok else (wo_uom or None),
             proof=wo.get("link_proof") or "work_order_fk")
        for tn in wo.get("tracking_numbers") or []:
            edge("Work Order", wo.get("wo"), None, "tracking_number",
                 "Tracking Number", tn, proof="tn.work_order")
    numbers = ctx.get("numbers_by_dn") or {}
    for dn in ctx.get("dns") or []:
        dn_uom = dn.get("uom")
        dn_ok = bool(dn_uom) and dn_uom == order_uom
        edge("Sales Order Item", line.get("so_line"), line.get("so_line"), "shipped_by",
             "Delivery Note", dn.get("dn"), qty=dn.get("qty") if dn_ok else None,
             uom=dn_uom or None, proof="dni.so_detail")
        dn_numbers = numbers.get(dn.get("dn"), [])
        for number in dn_numbers:
            shipment = (ctx.get("shipment_by_number") or {}).get(number["number"]) or {}
            allocation = "unknown" if len(dn_numbers) > 1 else "single_waybill"
            edge("Delivery Note", dn.get("dn"), None, "waybill",
                 "Shipment", shipment.get("shipment") or number["number"],
                 qty=None if len(dn_numbers) > 1 or not dn_ok else dn.get("qty"),
                 uom=dn_uom or None,
                 proof="dn_logistics_number", allocation=allocation)
    return rows


def build_line_facts(line, ctx):
    stage_rows = build_stage_balances(line, ctx)
    return {
        "line": {k: line.get(k) for k in (
            "so", "so_line", "item_code", "item_name", "customer", "customer_item_code",
            "so_status", "so_docstatus", "transaction_date", "delivery_date",
            "qty", "delivered_qty", "uom", "warehouse", "scope", "role")},
        "stage_balances": stage_rows,
        "milestones": build_milestones(line, ctx),
        "availability_schedule": build_availability(line, ctx, stage_rows),
        "links": build_links(line, ctx),
    }


def build_manifest(*, as_of, scope, lines, facts, coverage, counts, partial, notes=None):
    return {
        "schema_version": SCHEMA_VERSION,
        "rule_version": RULE_VERSION,
        "run_id": uuid.uuid4().hex,
        "as_of": _iso(as_of),
        "generated_at": _iso(now_datetime()),
        "scope": scope,
        "coverage": coverage,
        "counts": counts,
        "partial": bool(partial),
        "notes": notes or [],
        "outputs": {
            "lines": len(lines),
            "stage_balances": sum(len(f["stage_balances"]) for f in facts),
            "milestones": sum(len(f["milestones"]) for f in facts),
            "availability_schedule": sum(len(f["availability_schedule"]) for f in facts),
            "links": sum(len(f["links"]) for f in facts),
        },
    }


# ── EN loading (batched; doctype permissions checked before child reads) ────

def load_lines(filters):
    conditions = ["so.docstatus <= 2"]
    values = {}
    so_filters = [["docstatus", "<=", 2]]
    for field, column in (("sales_order", "name"), ("customer", "customer")):
        if filters.get(field):
            so_filters.append([column, "=", filters[field]])
            conditions.append("so.%s = %%(%s)s" % (column, field))
            values[field] = filters[field]
    child_filters = (("item_code", "soi.item_code"), ("customer_item_code",
                                                     "soi.customer_item_code"),
                     ("warehouse", "soi.warehouse"))
    for field, column in child_filters:
        if filters.get(field):
            conditions.append("%s = %%(%s)s" % (column, field))
            values[field] = filters[field]
    if filters.get("from_date"):
        so_filters.append(["transaction_date", ">=", filters.from_date])
        conditions.append("so.transaction_date >= %(from_date)s")
        values["from_date"] = filters.from_date
    if filters.get("to_date"):
        so_filters.append(["transaction_date", "<=", filters.to_date])
        conditions.append("so.transaction_date <= %(to_date)s")
        values["to_date"] = filters.to_date
    if not filters.get("include_delivered"):
        conditions.append("(soi.qty - soi.delivered_qty) > 0")
    permitted = [row.name for row in frappe.get_list(
        "Sales Order", filters=so_filters, fields=["name"], limit_page_length=0)]
    total = frappe.db.count("Sales Order", filters=so_filters)
    restricted = total > len(permitted)
    if not permitted:
        return [], restricted
    conditions.append("so.name in %(permitted)s")
    values["permitted"] = tuple(permitted)
    fba_expr = ("ifnull(soi.custom_fba_sku, '')"
                if frappe.db.has_column("Sales Order Item", "custom_fba_sku") else "''")
    order = "order by so.name, soi.idx"
    if filters.get("limit"):
        order += " limit %(limit)s offset %(offset)s"
        values["limit"] = int(filters.limit)
        values["offset"] = int(filters.get("offset") or 0)
    rows = frappe.db.sql(
        f"""select so.name as so, so.status as so_status, so.docstatus as so_docstatus,
                   so.customer as customer, so.customer_name as customer_name,
                   so.transaction_date as transaction_date,
                   soi.name as so_line, soi.item_code, soi.item_name,
                   soi.customer_item_code, soi.qty, soi.delivered_qty, soi.uom,
                   soi.warehouse, soi.delivery_date,
                   {fba_expr} as fba_sku
            from `tabSales Order` so
            join `tabSales Order Item` soi on soi.parent = so.name
            where {' and '.join(conditions)}
            {order}""", values, as_dict=True)
    return rows, restricted


def load_pps(lines):
    line_ids = [l.so_line for l in lines]
    if not line_ids:
        return {}, False
    rows = frappe.db.sql(
        """select ppi.sales_order_item as so_line, ppi.name as ppi, ppi.parent as pp,
                  pp.posting_date as pp_date, ppi.item_code, ppi.planned_qty,
                  ppi.pending_qty, ppi.stock_uom
           from `tabProduction Plan Item` ppi
           join `tabProduction Plan` pp on pp.name = ppi.parent
           where pp.docstatus = 1 and ppi.sales_order_item in %(lines)s""",
        {"lines": tuple(line_ids)}, as_dict=True)
    candidates = {row.pp for row in rows}
    permitted = {r.name for r in frappe.get_list(
        "Production Plan", filters=[["name", "in", sorted(candidates)]],
        fields=["name"], limit_page_length=0)} if candidates else set()
    restricted = candidates != permitted
    out = defaultdict(list)
    for row in rows:
        if row.pp in permitted:
            out[row.so_line].append(row)
    return out, restricted


def _wo_produced(wo_name, ops, cards, corrective, produced_qty):
    required = sorted((o for o in ops if o.operation not in corrective),
                      key=lambda o: (_num(o.sequence_id), o.operation or ""))
    if not required:
        return _num(produced_qty), "wo_produced_qty"
    first = required[0].operation
    done = [c for c in cards if c.operation == first and c.status == "Completed"
            and int(c.docstatus or 0) == 1]
    batch = sum(_num(c.total_completed_qty) or _num(c.for_quantity)
                for c in done if not c.tracking_number)
    per_tn = sum(_num(c.total_completed_qty) or _num(c.for_quantity)
                 for c in done if c.tracking_number)
    return max(batch, per_tn), "job_card_first_op"


def load_wos(lines, pps):
    line_ids = [l.so_line for l in lines]
    if not line_ids:
        return {}, False
    ppi_to_line = {p["ppi"]: line for line, rows in pps.items() for p in rows}
    values = {"lines": tuple(line_ids)}
    conditions = ["w.sales_order_item in %(lines)s", "w.fg_sales_order_item in %(lines)s"]
    if ppi_to_line:
        conditions.append("w.production_plan_item in %(ppis)s")
        values["ppis"] = tuple(ppi_to_line)
    wos = frappe.db.sql(
        f"""select w.name as wo, w.qty, w.produced_qty, w.status, w.docstatus,
                   w.production_item, w.stock_uom, w.sales_order_item,
                   w.fg_sales_order_item, w.production_plan_item, w.planned_start_date,
                   w.planned_end_date
            from `tabWork Order` w
            where w.docstatus in (0, 1) and ({' or '.join(conditions)})""",
        values, as_dict=True)
    wo_names = [w.wo for w in wos]
    permitted = {row.name for row in frappe.get_list(
        "Work Order", filters=[["name", "in", wo_names], ["docstatus", "in", (0, 1)]],
        fields=["name"], limit_page_length=0)} if wo_names else set()
    restricted = set(wo_names) != permitted
    wos = [w for w in wos if w.wo in permitted]
    wo_names = [w.wo for w in wos]
    ops, jcs, tns = defaultdict(list), defaultdict(list), defaultdict(list)
    if wo_names:
        for op in frappe.get_all("Work Order Operation",
                                 filters={"parent": ["in", wo_names]},
                                 fields=["parent", "operation", "sequence_id", "status",
                                         "completed_qty"]):
            ops[op.parent].append(op)
        for j in frappe.get_all(
                "Job Card",
                filters={"work_order": ["in", wo_names], "docstatus": ["<", 2]},
                fields=["name", "work_order", "operation", "status", "total_completed_qty",
                        "for_quantity", "actual_start_date", "actual_end_date",
                        "tracking_number", "docstatus"]):
            jcs[j.work_order].append(j)
        for t in frappe.get_all("Tracking Number",
                                filters={"work_order": ["in", wo_names]},
                                fields=["name", "work_order"]):
            tns[t.work_order].append(t.name)
    corrective = {r.name for r in frappe.get_all(
        "Operation", filters={"is_corrective_operation": 1}, fields=["name"])}
    grouped = defaultdict(list)
    for wo in wos:
        line = wo.sales_order_item or wo.fg_sales_order_item or \
            ppi_to_line.get(wo.production_plan_item)
        if line not in line_ids:
            continue
        cards = jcs.get(wo.wo, [])
        starts = [_day(c.actual_start_date) for c in cards if c.actual_start_date]
        ends = [_day(c.actual_end_date) for c in cards if c.actual_end_date]
        produced, basis = _wo_produced(wo.wo, ops.get(wo.wo, []), cards, corrective,
                                       wo.produced_qty)
        grouped[line].append({
            "wo": wo.wo, "qty": _num(wo.qty),
            "item_code": wo.production_item, "stock_uom": wo.stock_uom,
            "produced": produced, "produced_basis": basis,
            "status": wo.status, "docstatus": wo.docstatus,
            "planned_start_date": wo.planned_start_date,
            "planned_end_date": wo.planned_end_date,
            "jc_start": min(starts) if starts else None,
            "jc_end": max(ends) if ends else None,
            "tracking_numbers": tns.get(wo.wo, []),
            "link_proof": ("wo.sales_order_item" if wo.sales_order_item else
                           "wo.fg_sales_order_item" if wo.fg_sales_order_item else
                           "ppi.sales_order_item"),
        })
    return grouped, restricted


def load_dns(lines):
    line_ids = [l.so_line for l in lines]
    if not line_ids:
        return {}, False
    rows = frappe.db.sql(
        """select dn.name as dn, dn.posting_date as date, dn.status as status,
                  dn.docstatus as docstatus, ifnull(dn.is_return, 0) as is_return,
                  dn.return_against as return_against,
                  dni.so_detail as so_line, dni.name as dn_item, dni.dn_detail,
                  dni.qty, dni.uom, dni.warehouse
           from `tabDelivery Note Item` dni
           join `tabDelivery Note` dn on dn.name = dni.parent
           where dni.so_detail in %(lines)s and dn.docstatus in (0, 1)
           order by dn.posting_date, dn.name""",
        {"lines": tuple(line_ids)}, as_dict=True)
    candidates = {row.dn for row in rows}
    permitted = {r.name for r in frappe.get_list(
        "Delivery Note", filters=[["name", "in", sorted(candidates)],
                                  ["docstatus", "in", (0, 1)]],
        fields=["name"], limit_page_length=0)} if candidates else set()
    restricted = candidates != permitted
    grouped = {}
    for row in rows:
        if row.dn not in permitted:
            continue
        key = (row.so_line, row.dn, int(row.docstatus or 0), int(row.is_return or 0),
               row.uom, row.warehouse)
        if key not in grouped:
            grouped[key] = frappe._dict(row)
            grouped[key]["qty"] = 0.0
            grouped[key]["dn_items"] = []
        grouped[key]["qty"] += _num(row.qty)
        if row.dn_item:
            grouped[key]["dn_items"].append(row.dn_item)
    for row in grouped.values():
        row["dn_item"] = ",".join(sorted(set(row["dn_items"])))
    out = defaultdict(list)
    for row in grouped.values():
        out[row.so_line].append(row)
    return out, restricted


def load_shipments(dn_names):
    numbers = dn_logistic_numbers(dn_names) if dn_names else {}
    all_numbers = sorted({n["number"] for values in numbers.values() for n in values})
    shipments = {}
    restricted = False
    if all_numbers and frappe.db.has_column("Shipment", "custom_zmt_status11"):
        candidates = frappe.db.sql(
            """select name as shipment, custom_zmt_logistic_number as number,
                      custom_zmt_status11 as status11, custom_zmt_status4 as status4,
                      custom_zmt_eta as eta, custom_zmt_atd as atd,
                      custom_zmt_ata as ata, custom_zmt_dlvr as dlvr,
                      custom_zmt_match_status as match_status
               from `tabShipment`
               where custom_zmt_logistic_number in %(numbers)s and docstatus in (0, 1)""",
            {"numbers": tuple(all_numbers)}, as_dict=True)
        permitted = {r.name for r in frappe.get_list(
            "Shipment", filters=[["custom_zmt_logistic_number", "in", all_numbers],
                                 ["docstatus", "in", (0, 1)]],
            fields=["name"], limit_page_length=0)}
        restricted = {c.shipment for c in candidates} != permitted
        for row in candidates:
            if row.shipment in permitted:
                shipments[row.number] = row
    return numbers, shipments, restricted


def _permission_flags():
    return {
        "sales_order": frappe.has_permission("Sales Order", "read"),
        "delivery_note": frappe.has_permission("Delivery Note", "read"),
        "work_order": frappe.has_permission("Work Order", "read"),
        "production_plan": frappe.has_permission("Production Plan", "read"),
        "shipment": frappe.has_permission("Shipment", "read"),
    }


@frappe.whitelist()
def get_supply_facts(filters=None):
    """Batch machine entry: SO lines → stage balances, milestones, tranches, links."""
    if isinstance(filters, str):
        filters = json.loads(filters or "{}")
    filters = frappe._dict(filters or {})
    if not frappe.has_permission("Sales Order", "read"):
        frappe.throw("No permission for Sales Order", frappe.PermissionError)
    try:
        current_day = getdate(today())
        requested_day = getdate(filters.get("as_of")) if filters.get("as_of") else current_day
    except Exception:
        frappe.throw("as_of must be a date")
    if requested_day != current_day:
        frappe.throw("Historical as_of is not supported; only the current snapshot can be exported")
    as_of = requested_day
    observed_at = now_datetime()
    permissions = _permission_flags()
    lines, so_restricted = load_lines(filters)
    if filters.get("so_line"):
        lines = [l for l in lines if l.so_line == filters.so_line]
    if not lines:
        external = {
            "tongtool_po": "not_integrated",
            "receipt": "not_integrated",
            "warehouse_receipt": "not_integrated",
        }
        empty_reason = "all_restricted" if so_restricted else "no_matching_lines"
        coverage = {
            "sales_orders": 0, "so_lines": 0, "sources": permissions,
            "restricted": {"sales_order": so_restricted},
            "external_sources": external, "observed_at": _iso(observed_at),
            "empty_reason": empty_reason,
        }
        notes = ["empty_result: " + empty_reason,
                 "external sources not integrated: tongtool_po, receipt, warehouse_receipt"]
        manifest = build_manifest(as_of=as_of, scope={k: v for k, v in filters.items()},
                                  lines=[], facts=[], coverage=coverage,
                                  counts={"input": 0, "output": 0},
                                  partial=True, notes=notes)
        manifest["observed_at"] = _iso(observed_at)
        return {
            "schema_version": SCHEMA_VERSION, "rule_version": RULE_VERSION,
            "as_of": str(as_of), "lines": [], "stage_balances": [], "milestones": [],
            "availability_schedule": [], "links": [], "manifest": manifest,
        }

    pps, pp_restricted = (load_pps(lines) if permissions["production_plan"] else ({}, False))
    wos, wo_restricted = (load_wos(lines, pps) if permissions["work_order"] else ({}, False))
    dns, dn_restricted = (load_dns(lines) if permissions["delivery_note"] else ({}, False))
    dn_names = sorted({d.dn for values in dns.values() for d in values})
    numbers_by_dn, shipment_by_number, ship_restricted = (
        load_shipments(dn_names) if permissions["shipment"] else ({}, {}, False)
    )
    if not permissions["shipment"]:
        numbers_by_dn = {dn: [] for dn in dn_names}

    partial_reasons = []
    if not all(permissions.values()):
        partial_reasons.append("permissions missing: " + ", ".join(
            k for k, v in permissions.items() if not v))
    restricted = {
        "sales_order": so_restricted, "production_plan": pp_restricted,
        "work_order": wo_restricted, "delivery_note": dn_restricted,
        "shipment": ship_restricted,
    }
    if any(restricted.values()):
        partial_reasons.append("row-level restricted: " + ", ".join(
            k for k, v in restricted.items() if v))
    partial_reasons.append(
        "external sources not integrated: tongtool_po, receipt, warehouse_receipt")
    partial = bool(partial_reasons)

    facts = []
    dn_ok = permissions["delivery_note"] and not dn_restricted
    wo_ok = permissions["work_order"] and not wo_restricted
    ship_ok = permissions["shipment"] and not ship_restricted
    for line in lines:
        ctx_dns = [d for d in dns.get(line.so_line, []) if d.so_line == line.so_line]
        line_numbers = []
        for dn in ctx_dns:
            line_numbers.extend(n["number"] for n in numbers_by_dn.get(dn.dn, []))
        line_shipments = {n: shipment_by_number[n] for n in line_numbers
                          if n in shipment_by_number}
        facts.append(build_line_facts({
            "so": line.so, "so_line": line.so_line, "item_code": line.item_code,
            "item_name": line.item_name, "customer": line.customer_name or line.customer,
            "customer_item_code": line.customer_item_code, "so_status": line.so_status,
            "so_docstatus": line.so_docstatus, "transaction_date": line.transaction_date,
            "delivery_date": line.delivery_date, "qty": _num_or_none(line.qty),
            "delivered_qty": _num_or_none(line.delivered_qty), "uom": line.uom,
            "warehouse": line.warehouse,
            "scope": "external_fba" if line.fba_sku else "in_house", "role": "finished",
        }, {
            "pps": pps.get(line.so_line, []),
            "wos": wos.get(line.so_line, []),
            "dns": ctx_dns,
            "numbers_by_dn": {d.dn: numbers_by_dn.get(d.dn, []) for d in ctx_dns},
            "shipment_by_number": line_shipments,
            "dn_permission": dn_ok,
            "shipment_permission": ship_ok,
            "work_order_permission": wo_ok,
            "production_plan_permission": permissions["production_plan"] and not pp_restricted,
            "observed_at": observed_at,
        }))

    counts = {
        "input": len(lines), "output": len(facts),
        "stage_balances": sum(len(f["stage_balances"]) for f in facts),
        "milestones": sum(len(f["milestones"]) for f in facts),
        "availability_schedule": sum(len(f["availability_schedule"]) for f in facts),
        "links": sum(len(f["links"]) for f in facts),
    }
    coverage = {
        "sales_orders": len({l.so for l in lines}), "so_lines": len(lines),
        "delivery_notes": len(dn_names), "shipments": len(shipment_by_number),
        "sources": permissions, "restricted": restricted,
        "source_timestamps": {"sales_order": _iso(observed_at)},
        "observed_at": _iso(observed_at),
        "external_sources": {
            "tongtool_po": "not_integrated",
            "receipt": "not_integrated",
            "warehouse_receipt": "not_integrated",
        },
    }
    manifest = build_manifest(
        as_of=as_of, scope={k: v for k, v in filters.items()},
        lines=[f["line"] for f in facts], facts=facts,
        coverage=coverage, counts=counts, partial=partial,
        notes=partial_reasons)
    manifest["observed_at"] = _iso(observed_at)
    return {
        "schema_version": SCHEMA_VERSION, "rule_version": RULE_VERSION,
        "as_of": str(as_of),
        "lines": [f["line"] for f in facts],
        "stage_balances": [r for f in facts for r in f["stage_balances"]],
        "milestones": [r for f in facts for r in f["milestones"]],
        "availability_schedule": [r for f in facts for r in f["availability_schedule"]],
        "links": [r for f in facts for r in f["links"]],
        "manifest": manifest,
    }


def _num_or_none(value):
    return None if value is None else round(_num(value), 6)
