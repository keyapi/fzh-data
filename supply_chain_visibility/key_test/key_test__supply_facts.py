# -*- coding: utf-8 -*-
"""Supply facts contract v2: stage balances, milestones, availability, links, shipment progress.

One calculation shared by the machine batch entry and the SO human view.
This module never writes to ERPNext and never guesses quantities or dates:
missing evidence stays null with an explicit reason.
"""
import json
import uuid
from collections import defaultdict

import frappe
from frappe.utils import getdate, now_datetime, today

from key_test.production_evidence import (
    build_wo_evidence,
    evidence_status,
    proven_qty,
    rollup_line_evidence,
    unknown_line_evidence,
)
from key_test.shipment_progress import (
    SIGNED_PENDING_STAGE,
    TRANSPORT_STAGE,
    UNKNOWN_STAGE,
    classify_stage,
    progress_from_shipment,
)
from key_test.supply_query import dn_logistic_numbers

SCHEMA_VERSION = "supply-facts/v2"
RULE_VERSION = "2026-10-29.7"
IMPLEMENTATION_VERSION = "key_test.supply_facts@2026-10-30.2"

STAGE_NOT_PLANNED = "not_planned"
STAGE_IN_PRODUCTION = "in_production"
STAGE_PRODUCED_PENDING = "produced_pending_dn"
STAGE_IN_TRANSIT = "shipped_in_transit"
STAGE_ARRIVED = "arrived_not_sellable"
STAGE_SIGNED_PENDING = "signed_pending_tongtool_receipt"
STAGE_TONGTOOL_RECEIVED = "tongtool_received"
STAGE_DELIVERED = "delivered_sellable"
STAGE_CANCELLED = "cancelled"
STAGE_RETURNED = "returned"
STAGE_DRAFT = "draft_dn"
STAGE_UNKNOWN = "unknown"
STAGE_OVER_PRODUCED = "over_produced"

FILTER_KEYS = {
    "sales_order", "so_line", "customer", "item_code", "customer_item_code",
    "warehouse", "stage", "from_date", "to_date", "as_of",
    "include_delivered", "limit", "offset",
}
STAGE_VALUES = {
    STAGE_NOT_PLANNED, STAGE_IN_PRODUCTION, STAGE_PRODUCED_PENDING,
    STAGE_IN_TRANSIT, STAGE_ARRIVED, STAGE_SIGNED_PENDING,
    STAGE_TONGTOOL_RECEIVED, STAGE_DELIVERED, STAGE_CANCELLED,
    STAGE_RETURNED, STAGE_DRAFT, STAGE_UNKNOWN, STAGE_OVER_PRODUCED,
}
DEFAULT_LIMIT = 500
MAX_LIMIT = 2000
SORT_KEYS = ["so", "so_line"]
# Frappe's execute_cmd forwards the whole form_dict; these are framework
# controls, not business filters. Everything else at top level is rejected.
FRAMEWORK_ARGS = {"cmd", "csrf_token", "_"}

ARRIVED_STATUSES = {
    "已到港", "清关中", "已清关", "已转运", "派送中", "已签收", "已上传POD",
}
RECEIVED_STATUSES = {"已签收", "已上传POD"}
EXECUTED_STAGES = {
    STAGE_NOT_PLANNED, STAGE_IN_PRODUCTION, STAGE_PRODUCED_PENDING,
    STAGE_IN_TRANSIT, STAGE_ARRIVED, STAGE_SIGNED_PENDING,
    STAGE_TONGTOOL_RECEIVED, STAGE_DELIVERED,
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


def _source_state(available, restricted=False, status=None):
    """Uniform source status. available/restricted plus preserved reason/error."""
    state = {"available": bool(available), "restricted": bool(restricted),
             "reason": ""}
    if status:
        if status.get("reason"):
            state["reason"] = status["reason"]
        if status.get("error"):
            state["error"] = status["error"]
    if not state["available"] and not state["reason"]:
        state["reason"] = "permission"
    return state


def _balance(line, stage, qty, uom, detail="", batch_key="", source="",
             reason="", in_stock="unknown", qty_status=None, qty_basis="",
             demand_status="active", warehouse=None, cumulative_excess_qty=None):
    status = qty_status or _qty_status(qty, uom)
    return {
        "so": line.get("so"), "so_line_id": line.get("so_line"),
        "item_code": line.get("item_code"),
        "warehouse": warehouse if warehouse is not None else line.get("warehouse"),
        "uom": uom, "stage": stage, "stage_detail": detail,
        "qty": None if qty is None else round(_num(qty), 6),
        "qty_status": status, "qty_basis": qty_basis,
        "cumulative_excess_qty": (None if cumulative_excess_qty is None
                                  else round(_num(cumulative_excess_qty), 6)),
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

    unallocated = []
    dn_names = {d.get("dn") for d in nonreturns}
    grouped_dns = defaultdict(list)
    for dn in nonreturns:
        grouped_dns[dn.get("dn")].append(dn)

    def group_item_names(dn, idx):
        item_qty = dn.get("item_qty") or {}
        if item_qty:
            return list(item_qty)
        names = [n for n in (dn.get("dn_items") or [dn.get("dn_item")]) if n]
        return names or ["__group__%d" % idx]

    def original_item_names(dn_rows):
        names = []
        for idx, dn in enumerate(dn_rows):
            for name in group_item_names(dn, idx):
                if name not in names:
                    names.append(name)
        return names

    def item_capacity(dn_rows, name):
        for dn in dn_rows:
            item_qty = dn.get("item_qty") or {}
            if name in item_qty:
                return _num(item_qty[name])
        for dn in dn_rows:
            names = [n for n in (dn.get("dn_items") or [dn.get("dn_item")]) if n]
            if names == [name]:
                return _num(dn.get("qty"))
        return None

    matched_by_item = defaultdict(float)
    matched_by_dn = defaultdict(float)
    matched_total = 0.0
    excess_total = 0.0
    conflict_total = 0.0
    unattributed_total = 0.0
    for ret in returns:
        amount = -_num(ret.get("qty"))
        if amount <= 0:
            continue
        against = ret.get("return_against")
        if not against or against not in dn_names:
            unallocated.append(ret)
            continue
        dn_rows = grouped_dns[against]
        detail = ret.get("dn_detail")
        matched_here = 0.0
        if detail:
            capacity = item_capacity(dn_rows, detail)
            if capacity is None:
                conflict_total += amount
            else:
                remaining = max(0.0, capacity - matched_by_item[(against, detail)])
                take = min(amount, remaining)
                matched_by_item[(against, detail)] += take
                matched_here += take
                amount -= take
                excess_total += amount
        else:
            names = original_item_names(dn_rows)
            if len(names) == 1:
                name = names[0]
                capacity = item_capacity(dn_rows, name)
                if capacity is None:
                    capacity = sum(_num(dn.get("qty")) for dn in dn_rows)
                remaining = max(0.0, capacity - matched_by_item[(against, name)])
                take = min(amount, remaining)
                matched_by_item[(against, name)] += take
                matched_here += take
                amount -= take
                excess_total += amount
            else:
                unattributed_total += amount
        matched_total += matched_here
        matched_by_dn[against] += matched_here
    unallocated_total = sum(-_num(r.get("qty")) for r in unallocated)
    returned_total = sum(-_num(r.get("qty")) for r in returns)
    if matched_total > 1e-9:
        rows.append(_balance(line, STAGE_RETURNED, matched_total, uom,
                             detail="销售退货（已按原出库明细抵扣）",
                             reason="已按原出库明细抵扣",
                             demand_status=demand_status))
    if excess_total > 1e-9:
        rows.append(_balance(line, STAGE_RETURNED, excess_total, uom,
                             detail="超退：超出原出库明细可抵扣量",
                             reason="超出原出库明细的可抵扣量，超退部分无原明细可抵",
                             demand_status=demand_status))
    if conflict_total > 1e-9:
        rows.append(_balance(line, STAGE_RETURNED, conflict_total, uom,
                             detail="退货明细引用冲突（dn_detail 不匹配原出库明细）",
                             reason="明细引用冲突，未抵扣，待核实",
                             demand_status=demand_status))
    if unattributed_total > 1e-9:
        rows.append(_balance(line, STAGE_RETURNED, unattributed_total, uom,
                             detail="退货明细缺失且原单多行，无法归属",
                             reason="退货明细缺失且原出库单多行，未抵扣（归属未知）",
                             demand_status=demand_status))
    if unallocated_total > 1e-9:
        rows.append(_balance(line, STAGE_RETURNED, unallocated_total, uom,
                             detail="销售退货（未关联原出库单）",
                             reason="退货未关联原出库单，实物去向未证",
                             demand_status=demand_status))

    numbers = ctx.get("numbers_by_dn") or {}
    shipment_by_number = ctx.get("shipment_by_number") or {}
    shipped_physical = 0.0
    shipped_net = 0.0
    for dn_name, dn_rows in grouped_dns.items():
        gross_total = sum(_num(r.get("qty")) for r in dn_rows)
        net_total = max(0.0, gross_total - min(matched_by_dn.get(dn_name, 0.0),
                                               gross_total))
        shipped_physical += gross_total
        shipped_net += net_total
        for idx, dn in enumerate(dn_rows):
            gross_qty = _num(dn.get("qty"))
            names = group_item_names(dn, idx)
            row_alloc = min(sum(matched_by_item[(dn_name, name)] for name in names),
                            gross_qty)
            net_qty = max(0.0, gross_qty - row_alloc)
            if net_qty <= 1e-9:
                continue
            dn_numbers = [n["number"] for n in numbers.get(dn_name, [])]
            progresses = []
            missing_progress = False
            for number in dn_numbers:
                shipment = shipment_by_number.get(number) or {}
                progress = (shipment.get("progress")
                            or progress_from_shipment(shipment)) if shipment else None
                if not progress:
                    missing_progress = True
                    progress = {}
                progresses.append((number, progress))
            stage, detail, reason = STAGE_IN_TRANSIT, "在途", ""
            if not dn_numbers:
                detail, reason = "运单未登记", ""
            elif not ctx.get("shipment_permission"):
                detail, reason = "状态未知（无 Shipment 读取权限）", "缺 Shipment 权限"
            elif missing_progress:
                stage, detail, reason = (STAGE_IN_TRANSIT,
                                         "部分运单无状态，保守计在途",
                                         "缺运单状态证据")
            else:
                classes = [classify_stage(progress) for _, progress in progresses]
                conflicts = sorted({reason_code
                                    for _, progress in progresses
                                    for reason_code in progress.get("conflict_reasons") or []})
                if all(item == SIGNED_PENDING_STAGE for item in classes):
                    stage = STAGE_SIGNED_PENDING
                    detail = ("已签收/POD，待通途入库" if len(dn_numbers) == 1
                              else "多运单均已签收，单箱分配未知")
                    reason = "缺通途采购入库证据"
                    if len(dn_numbers) > 1:
                        reason += "；多运单未提供数量分配证据"
                    if conflicts:
                        reason = reason + "；" + ",".join(conflicts)
                elif any(item == SIGNED_PENDING_STAGE for item in classes):
                    stage = STAGE_IN_TRANSIT
                    detail = "部分运单已签收，分配未知，保守计在途"
                    reason = "签收运单与在途运单未提供数量分配证据"
                elif all(item == TRANSPORT_STAGE for item in classes):
                    stage = STAGE_IN_TRANSIT
                    detail = "运输中（到港/清关/转运/派送仍属运输）"
                    reason = "未签收"
                else:
                    stage = STAGE_UNKNOWN
                    detail = "物流进度冲突或未知"
                    reason = ",".join(conflicts) or "物流状态未知"
            rows.append(_balance(line, stage, net_qty, uom, detail=detail,
                                 batch_key=dn_name, source=dn_name, reason=reason,
                                 warehouse=dn.get("warehouse"),
                                 demand_status=demand_status))

    own_wos = [w for w in (ctx.get("wos") or []) if w.get("item_code") == line.get("item_code")]
    active_wos = [w for w in own_wos if int(w.get("docstatus") or 0) != 2]
    own_pps = [p for p in (ctx.get("pps") or []) if p.get("item_code") == line.get("item_code")]
    pp_units = {p.get("stock_uom") or "" for p in own_pps}
    pp_units_ok = not own_pps or pp_units == {uom}
    pp_coverage = (min(sum(_num(p.get("planned_qty")) for p in own_pps), _num(qty))
                   if pp_units_ok else 0.0)
    pp_ok = ctx.get("production_plan_permission", True)
    wo_units_ok = all((w.get("stock_uom") or "") == uom for w in active_wos)
    evidence = ctx.get("evidence") or {}
    all_ev = evidence.get("all_process_done") or {}
    first_ev = evidence.get("first_process_done") or {}
    stock_ev = evidence.get("stock_in_posted") or {}
    all_proven = proven_qty(all_ev)
    all_est = (all_ev.get("qty_estimated")
               if all_ev.get("confidence") in ("estimated", "mixed") else None)
    all_status = evidence_status(all_ev)
    if all_status == "known":
        produced_total, produced_status = _num(all_proven), "known"
    elif all_status == "estimated":
        produced_total, produced_status = _num(all_est), "estimated"
    else:
        produced_total, produced_status = 0.0, "unknown"
    all_unknown = produced_status == "unknown"
    stock_total = proven_qty(stock_ev)
    produced_capped = 0.0 if all_unknown else min(produced_total, _num(qty))
    produced_basis = all_ev.get("qty_basis") or (
        "wo_produced_qty" if produced_status == "estimated" else "all_process_done")
    first_total = proven_qty(first_ev) or 0.0
    wo_coverage = (min(sum(_num(w.get("qty")) for w in active_wos), _num(qty))
                   if wo_units_ok else 0.0)
    started_wos = [w for w in active_wos if w.get("jc_start")]
    started_names = {w.get("wo") for w in started_wos}
    started_coverage = (min(sum(_num(w.get("qty")) for w in started_wos), _num(qty))
                        if wo_units_ok else 0.0)
    if not started_wos and first_total > 1e-9 and wo_units_ok:
        started_coverage = min(wo_coverage, _num(first_total))
    open_net = _num(qty) - shipped_net
    produced_pending = (0.0 if all_unknown else
                        max(0.0, min(produced_capped - shipped_physical, open_net)))
    remaining = max(0.0, open_net - produced_pending)
    if produced_pending > 1e-9:
        rows.append(_balance(line, STAGE_PRODUCED_PENDING, produced_pending, uom,
                             detail="全工序完成待出库", reason="缺出库单",
                             qty_status=produced_status,
                             qty_basis=produced_basis,
                             demand_status=demand_status))
    if stock_total is not None:
        cumulative_excess = max(0.0, stock_total - _num(qty))
        excess_physical = max(
            0.0, stock_total - max(shipped_physical, min(stock_total, _num(qty))))
    else:
        cumulative_excess = excess_physical = 0.0
    if cumulative_excess > 1e-9:
        rows.append(_balance(
            line, STAGE_OVER_PRODUCED, excess_physical, uom,
            detail="超订单完工现存（来源入库 %g / 订单 %g / 累计超产 %g）" % (
                stock_total, _num(qty), cumulative_excess),
            source=",".join(w.get("wo") for w in own_wos),
            reason=("超订单实物现存，不计入本订单阶段余额与可售供给"
                    if excess_physical > 1e-9
                    else "累计超产异常；当前无超产实物余额，证据保留在累计字段"),
            qty_status="known",
            qty_basis="stock_in_posted",
            cumulative_excess_qty=cumulative_excess,
            demand_status="excess"))
    if all_unknown and not cancelled and remaining > 1e-9:
        if not ctx.get("work_order_permission"):
            reason = "无工单读取权限（含行级受限），阶段未知"
        elif not wo_units_ok or "unit_mismatch" in (all_ev.get("reasons") or []):
            reason = "单位不一致或缺失，全工序证据未知"
        else:
            reason = "全工序证据未知，不推断为待出库/在产"
        rows.append(_balance(line, STAGE_UNKNOWN, remaining, uom, reason=reason,
                             demand_status=demand_status))
        remaining = 0.0
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
                production_gap = max(0.0, started_coverage - produced_capped)
                in_production = min(remaining, production_gap)
                if in_production > 1e-9:
                    rows.append(_balance(
                        line, STAGE_IN_PRODUCTION, in_production, uom,
                        detail="在产/部分完工",
                        source=",".join(w.get("wo") for w in started_wos),
                        demand_status=demand_status))
                leftover = remaining - in_production
                if leftover > 1e-9:
                    wo_plan_only = min(leftover,
                                       max(0.0, wo_coverage - started_coverage))
                    if wo_plan_only > 1e-9:
                        rows.append(_balance(
                            line, STAGE_UNKNOWN, wo_plan_only, uom,
                            detail="工单已下达，无实际开工记录",
                            reason="工单覆盖只能证明计划，缺开工证据，不判为在产",
                            source=",".join(w.get("wo") for w in own_wos
                                            if w.get("wo") not in started_names),
                            demand_status=demand_status))
                        leftover -= wo_plan_only
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
                        if own_pps and not pp_units_ok:
                            rows.append(_balance(
                                line, STAGE_UNKNOWN, leftover, uom,
                                reason="生产计划单位与订单单位不一致或缺失，计划覆盖量未归一",
                                demand_status=demand_status))
                        elif not pp_ok:
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
                and r["stage"] not in (STAGE_RETURNED, STAGE_DRAFT, STAGE_CANCELLED,
                                       STAGE_OVER_PRODUCED))
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

    def over_note(total):
        order_qty = _num(line.get("qty"))
        if total > order_qty + 1e-9:
            return "来源数量 %g 超过订单量 %g，超额部分见阶段余额 over_produced" % (
                total, order_qty)
        return ""

    add("order_placed", actual=line.get("transaction_date"), qty=line.get("qty"),
        source="Sales Order.transaction_date")
    add("promised_delivery", baseline=line.get("delivery_date"), latest=line.get("delivery_date"),
        qty=line.get("qty"), source="Sales Order Item.delivery_date",
        note="无独立承诺字段；当前预计沿用订单交期")

    wos = ctx.get("wos") or []
    own_wos = [w for w in wos if w.get("item_code") == line.get("item_code")
               and int(w.get("docstatus") or 0) != 2]
    evidence = ctx.get("evidence") or {}
    first_ev = evidence.get("first_process_done") or {}
    all_ev = evidence.get("all_process_done") or {}
    start_total = proven_qty(first_ev)
    end_total = proven_qty(all_ev)
    start_est = (first_ev.get("qty_estimated")
                 if first_ev.get("confidence") in ("estimated", "mixed") else None)
    end_est = (all_ev.get("qty_estimated")
               if all_ev.get("confidence") in ("estimated", "mixed") else None)
    if own_wos:
        starts = [w["planned_start_date"] for w in own_wos if w.get("planned_start_date")]
        ends = [w["planned_end_date"] for w in own_wos if w.get("planned_end_date")]
        wo_units = {w.get("stock_uom") or "" for w in own_wos}
        wo_units_ok = wo_units == {order_uom}
        start_qty = _num(start_total) if start_total is not None else None
        end_qty = _num(end_total) if end_total is not None else None
        start_actual = (first_ev.get("started_at")
                        if start_total is not None
                        and first_ev.get("time_status") == "complete" else None)
        end_actual = (all_ev.get("completed_at")
                      if end_total is not None
                      and all_ev.get("time_status") == "complete" else None)
        add("production_start", baseline=min(starts, default=None),
            latest=min(starts, default=None),
            actual=start_actual,
            qty=start_qty if wo_units_ok else None,
            source="Production evidence",
            note=join_notes("启动以首工序实际事件为准",
                            "估算 %g（未证，不计数量）" % start_est
                            if start_est is not None and start_total is None else "",
                            over_note(start_qty) if start_qty is not None and wo_units_ok else "",
                            "" if wo_units_ok else unit_note(wo_units)))
        add("production_end", baseline=max(ends, default=None),
            latest=max(ends, default=None),
            actual=end_actual,
            qty=end_qty if wo_units_ok else None,
            source="Production evidence",
            note=join_notes("完成以全工序已证事件为准",
                            "估算 %g（未证，不计数量）" % end_est
                            if end_est is not None and end_total is None else "",
                            over_note(end_qty) if end_qty is not None and wo_units_ok else "",
                            "" if wo_units_ok else unit_note(wo_units)))

    submitted = [d for d in (ctx.get("dns") or []) if int(d.get("docstatus") or 0) == 1]
    nonreturns = [d for d in submitted if not int(d.get("is_return") or 0)]
    by_dn = {}
    for dn in nonreturns:
        by_dn.setdefault(dn.get("dn"), []).append(dn)
    for dn_name, dn_rows in by_dn.items():
        dn_units = {d.get("uom") or "" for d in dn_rows}
        dn_units_ok = dn_units == {order_uom}
        add("dispatch",
            actual=min((d["date"] for d in dn_rows if d.get("date")), default=None),
            qty=(sum(_num(d.get("qty")) for d in dn_rows) if dn_units_ok else None),
            source="Delivery Note %s.posting_date" % dn_name,
            note=join_notes("过账不等于实际起运；数量为该单过账数量，退货在阶段余额中净额抵扣",
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
        if stage_row["stage"] in (STAGE_CANCELLED, STAGE_UNKNOWN, STAGE_RETURNED,
                                  STAGE_DRAFT, STAGE_OVER_PRODUCED):
            continue
        if stage_row.get("demand_status") == "cancelled":
            continue
        unit = stage_row.get("uom")
        warehouse = stage_row.get("warehouse")
        if stage_row["stage"] in (STAGE_IN_TRANSIT, STAGE_ARRIVED,
                                  STAGE_SIGNED_PENDING, STAGE_TONGTOOL_RECEIVED):
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
            reason = ("已签收/待通途入库，未证可售"
                      if stage_row["stage"] == STAGE_SIGNED_PENDING else
                      "到货/POD 未证可售" if stage_row["stage"] == STAGE_ARRIVED else
                      "通途入库不自动等于海外可售"
                      if stage_row["stage"] == STAGE_TONGTOOL_RECEIVED else
                      "ETA 未经入库/上架验证")
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
             target_name, qty=None, uom=None, proof="", allocation=None,
             target_is_record=True):
        rows.append({
            "so": line.get("so"), "so_line_id": line.get("so_line"),
            "source_doctype": source_doctype, "source_name": source_name,
            "source_line_id": source_line, "relation": relation,
            "target_doctype": target_doctype, "target_name": target_name,
            "target_is_record": bool(target_is_record),
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
                 proof="dn_logistics_number", allocation=allocation,
                 target_is_record=bool(shipment.get("shipment")))
        if dn.get("tongtool_po"):
            edge("Delivery Note", dn.get("dn"), None, "tongtool_purchase_order",
                 "Tongtool Purchase Order", dn.get("tongtool_po"),
                 proof="dn.custom_tongtool_purchase_order",
                 allocation="code_only", target_is_record=False)
    return rows


def build_shipment_progress(line, ctx):
    """Per DN × waybill progress evidence for one SO line; receipt side is unknown.

    One outbound DN can appear as several grouped rows (per item detail or
    warehouse). Returns are excluded: they never belong to the outbound
    progress set. Identical (dn, waybill, shipment) entries are emitted once.
    """
    rows = []
    seen = set()
    for dn in ctx.get("dns") or []:
        if int(dn.get("is_return") or 0):
            continue
        numbers = (ctx.get("numbers_by_dn") or {}).get(dn.get("dn"), [])
        for entry in numbers:
            number = entry.get("number")
            shipment = (ctx.get("shipment_by_number") or {}).get(number) or {}
            progress = shipment.get("progress") or progress_from_shipment(shipment)
            candidates = progress.get("progress_candidates") or []
            identity_conflict = bool(shipment.get("identity_conflict"))
            identity_key = (dn.get("dn"), number,
                            tuple(shipment.get("shipment_candidates") or [])
                            if identity_conflict else shipment.get("shipment"))
            if identity_key in seen:
                continue
            seen.add(identity_key)
            manual = next((item for item in candidates
                           if item.get("line") == "status4"), None)
            stage = classify_stage(progress)
            is_final = bool(progress.get("is_final"))
            rows.append({
                "so": line.get("so"), "so_line_id": line.get("so_line"),
                "item_code": line.get("item_code"), "dn": dn.get("dn"),
                "shipment": shipment.get("shipment"), "logistic_number": number,
                "shipment_candidates": shipment.get("shipment_candidates") or [],
                "identity_conflict": identity_conflict,
                "tongtool_po": dn.get("tongtool_po"),
                "warehouse": dn.get("warehouse"), "uom": dn.get("uom"),
                "status11": shipment.get("status11"),
                "status4": shipment.get("status4"),
                "status4_normalized": (manual or {}).get("normalized_status"),
                "status4_normalization": (manual or {}).get("normalization"),
                "status_semantics": "unproven",
                "eta": _day(shipment.get("eta")),
                "atd": _day(shipment.get("atd")),
                "ata": _day(shipment.get("ata")),
                "dlvr": _day(shipment.get("dlvr")),
                "latest_progress_status": progress.get("latest_progress_status"),
                "latest_progress_at": progress.get("latest_progress_at"),
                "latest_progress_kind": progress.get("latest_progress_kind"),
                "progress_source": progress.get("progress_source"),
                "is_final": is_final,
                "conflict_flag": progress.get("conflict_flag"),
                "conflict_reasons": progress.get("conflict_reasons") or [],
                "progress_candidates": candidates,
                "stage": stage,
                "shipment_signed_at": (progress.get("latest_progress_at")
                                       if is_final else None),
                "tongtool_first_receipt_at": None,
                "tongtool_last_receipt_at": None,
                "tongtool_receipt_at": None,
                "receipt_lag_days": None,
                "receipt_completion": "unknown",
                "received_qty": None,
                "pending_qty": None,
                "received_evidence_status": "unknown",
                "pending_evidence_status": "unknown",
                "receipt_basis": ("signed_assumed" if is_final else None),
                "identity_confidence": ("shipment_dn_link" if dn.get("dn") else "unproven"),
                "receipt_source_status": "not_integrated",
                "inventory_inclusion_status": "unknown",
                "source_status": {"receipt": "not_integrated",
                                  "inventory": "not_integrated"},
            })
    rows.sort(key=lambda row: (str(row.get("dn") or ""),
                               str(row.get("logistic_number") or ""),
                               str(row.get("shipment") or "")))
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
        "production_evidence": ctx.get("evidence") or {},
        "shipment_progress": build_shipment_progress(line, ctx),
    }


def build_manifest(*, as_of, scope, lines, facts, coverage, counts, partial, notes=None):
    return {
        "schema_version": SCHEMA_VERSION,
        "rule_version": RULE_VERSION,
        "implementation_version": IMPLEMENTATION_VERSION,
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

def _normalize_filters(filters=None, extra=None):
    """Validate and normalize the public filter contract.

    Unknown top-level kwargs and unknown filter keys are rejected instead of
    being silently ignored (which previously widened the query to all SOs).
    """
    if extra:
        unexpected = sorted(set(extra) - FRAMEWORK_ARGS)
        if unexpected:
            frappe.throw(
                "Unknown parameter(s): %s; wrap supported filters in `filters`"
                % ", ".join(unexpected), frappe.ValidationError)
    if filters is None:
        filters = {}
    elif isinstance(filters, str):
        try:
            filters = json.loads(filters or "{}")
        except Exception:
            frappe.throw("filters must be a JSON object", frappe.ValidationError)
    if not isinstance(filters, dict):
        frappe.throw("filters must be a JSON object", frappe.ValidationError)

    unknown = sorted(set(filters) - FILTER_KEYS)
    if unknown:
        frappe.throw(
            "Unknown filter(s): %s; allowed: %s"
            % (", ".join(unknown), ", ".join(sorted(FILTER_KEYS))),
            frappe.ValidationError)

    out = {}
    for key in ("sales_order", "so_line", "customer", "item_code",
                "customer_item_code", "warehouse", "stage", "from_date",
                "to_date", "as_of"):
        value = filters.get(key)
        if value is None or value == "":
            continue
        if not isinstance(value, str):
            frappe.throw("filter %s must be a string" % key, frappe.ValidationError)
        value = value.strip()
        if value:
            out[key] = value
    if out.get("stage") and out["stage"] not in STAGE_VALUES:
        frappe.throw("Unknown stage: %s" % out["stage"], frappe.ValidationError)

    if "include_delivered" in filters:
        value = filters["include_delivered"]
        if isinstance(value, bool):
            out["include_delivered"] = value
        elif isinstance(value, (int, float)):
            out["include_delivered"] = bool(value)
        elif isinstance(value, str):
            low = value.strip().lower()
            if low in ("1", "true", "yes", "on"):
                out["include_delivered"] = True
            elif low in ("0", "false", "no", "off", ""):
                out["include_delivered"] = False
            else:
                frappe.throw("include_delivered must be boolean", frappe.ValidationError)
        else:
            frappe.throw("include_delivered must be boolean", frappe.ValidationError)

    limit = filters.get("limit", DEFAULT_LIMIT)
    if limit in (None, ""):
        limit = DEFAULT_LIMIT
    try:
        limit = int(limit)
    except Exception:
        frappe.throw("limit must be an integer", frappe.ValidationError)
    if limit < 1 or limit > MAX_LIMIT:
        frappe.throw("limit must be between 1 and %d" % MAX_LIMIT, frappe.ValidationError)

    offset = filters.get("offset", 0) or 0
    try:
        offset = int(offset)
    except Exception:
        frappe.throw("offset must be an integer", frappe.ValidationError)
    if offset < 0:
        frappe.throw("offset must be >= 0", frappe.ValidationError)

    out["limit"] = limit
    out["offset"] = offset
    return out


def _pagination(filters, returned, total, cursor=None):
    offset = filters["offset"]
    limit = filters["limit"]
    exhausted = offset + returned >= total
    next_offset = None if exhausted else offset + returned
    return {
        "limit": limit,
        "offset": offset,
        "returned": returned,
        "total": total,
        "next_offset": next_offset,
        "next_cursor": cursor if next_offset is not None else None,
        "exhausted": exhausted,
        "partial": not exhausted,
        "termination_reason": "exhausted" if exhausted else "page_limit",
        "sort": list(SORT_KEYS),
        "unique_key": "so_line",
    }


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
        so_filters.append(["transaction_date", ">=", filters["from_date"]])
        conditions.append("so.transaction_date >= %(from_date)s")
        values["from_date"] = filters["from_date"]
    if filters.get("to_date"):
        so_filters.append(["transaction_date", "<=", filters["to_date"]])
        conditions.append("so.transaction_date <= %(to_date)s")
        values["to_date"] = filters["to_date"]
    if filters.get("so_line"):
        conditions.append("soi.name = %(so_line)s")
        values["so_line"] = filters["so_line"]
    if not filters.get("include_delivered"):
        conditions.append("(soi.qty - soi.delivered_qty) > 0")
    permitted = [row.name for row in frappe.get_list(
        "Sales Order", filters=so_filters, fields=["name"], limit_page_length=0)]
    total = frappe.db.count("Sales Order", filters=so_filters)
    restricted = total > len(permitted)
    if not permitted:
        return [], restricted, 0
    conditions.append("so.name in %(permitted)s")
    values["permitted"] = tuple(permitted)
    count_sql = (
        "select count(*) as total from `tabSales Order` so "
        "join `tabSales Order Item` soi on soi.parent = so.name "
        "where " + " and ".join(conditions))
    count_rows = frappe.db.sql(count_sql, values, as_dict=True) or []
    total_lines = int((count_rows[0] or {}).get("total") or 0)
    fba_expr = ("ifnull(soi.custom_fba_sku, '')"
                if frappe.db.has_column("Sales Order Item", "custom_fba_sku") else "''")
    order = "order by so.name, soi.name"
    if filters.get("limit"):
        order += " limit %(limit)s offset %(offset)s"
        values["limit"] = int(filters["limit"])
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
    return rows, restricted, total_lines


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
    status = {"available": True, "restricted": False, "reason": "",
              "restricted_wos": set(),
              "job_card_unavailable_wos": set(),
              "tracking_unavailable_wos": set()}
    line_ids = [l.so_line for l in lines]
    if not line_ids:
        return {}, status
    ppi_to_line = {p["ppi"]: line for line, rows in pps.items() for p in rows}
    values = {"lines": tuple(line_ids)}
    conditions = ["w.sales_order_item in %(lines)s", "w.fg_sales_order_item in %(lines)s"]
    if ppi_to_line:
        conditions.append("w.production_plan_item in %(ppis)s")
        values["ppis"] = tuple(ppi_to_line)
    try:
        wos = frappe.db.sql(
            f"""select w.name as wo, w.qty, w.produced_qty, w.status, w.docstatus,
                       w.production_item, w.stock_uom, w.sales_order_item,
                       w.fg_sales_order_item, w.production_plan_item, w.planned_start_date,
                       w.planned_end_date
                from `tabWork Order` w
                where w.docstatus in (0, 1, 2) and ({' or '.join(conditions)})""",
            values, as_dict=True)
    except Exception as exc:  # noqa: BLE001
        status.update(available=False, reason="query_error", error=str(exc))
        return {}, status
    wo_names = [w.wo for w in wos]
    try:
        permitted = {row.name for row in frappe.get_list(
            "Work Order",
            filters=[["name", "in", wo_names], ["docstatus", "in", (0, 1, 2)]],
            fields=["name"], limit_page_length=0)} if wo_names else set()
    except Exception as exc:  # noqa: BLE001
        status.update(available=False, reason="query_error", error=str(exc))
        return {}, status
    if set(wo_names) != permitted:
        status.update(restricted=True, reason="permission")
        status["restricted_wos"] = set(wo_names) - permitted
    wos = [w for w in wos if w.wo in permitted]
    wo_names = [w.wo for w in wos]
    ops, jcs, tns = defaultdict(list), defaultdict(list), defaultdict(list)
    tn_rows = defaultdict(list)
    if wo_names:
        for op in frappe.get_all("Work Order Operation",
                                 filters={"parent": ["in", wo_names]},
                                 fields=["name", "parent", "operation", "sequence_id",
                                         "status", "completed_qty"]):
            ops[op.parent].append(op)
        try:
            jc_rows = list(frappe.get_all(
                "Job Card",
                filters={"work_order": ["in", wo_names], "docstatus": ["<", 2]},
                fields=["name", "work_order", "operation_id", "operation", "status",
                        "total_completed_qty", "for_quantity", "actual_start_date",
                        "actual_end_date", "tracking_number", "docstatus",
                        "quality_inspection"]))
            permitted_jc = {row.name for row in frappe.get_list(
                "Job Card",
                filters=[["name", "in", [j.name for j in jc_rows]],
                         ["docstatus", "<", 2]],
                fields=["name"], limit_page_length=0)} if jc_rows else set()
        except Exception:  # noqa: BLE001
            jc_rows, permitted_jc = [], set()
            status["job_card_unavailable_wos"] = set(wo_names)
            status["restricted"] = True
        if permitted_jc != {j.name for j in jc_rows}:
            hidden = {j.work_order for j in jc_rows if j.name not in permitted_jc}
            status["job_card_unavailable_wos"] |= hidden
            status["restricted"] = True
            jc_rows = [j for j in jc_rows if j.name in permitted_jc]
        time_logs, time_log_status = load_job_card_time_logs([j.name for j in jc_rows])
        if not time_log_status["available"]:
            # Time-log failure only degrades time fields; JC/TN quantity
            # evidence stays usable.
            status["job_card_time_log"] = time_log_status
        for j in jc_rows:
            j["time_logs"] = time_logs.get(j.name, [])
            jcs[j.work_order].append(j)
        try:
            tn_candidates = list(frappe.get_all(
                "Tracking Number", filters={"work_order": ["in", wo_names]},
                fields=["name", "work_order", "qty"]))
            permitted_tn = {row.name for row in frappe.get_list(
                "Tracking Number",
                filters=[["name", "in", [t.name for t in tn_candidates]]],
                fields=["name"], limit_page_length=0)} if tn_candidates else set()
        except Exception:  # noqa: BLE001
            tn_candidates, permitted_tn = [], set()
            status["tracking_unavailable_wos"] = set(wo_names)
            status["restricted"] = True
        if permitted_tn != {t.name for t in tn_candidates}:
            hidden = {t.work_order for t in tn_candidates if t.name not in permitted_tn}
            status["tracking_unavailable_wos"] |= hidden
            status["restricted"] = True
            tn_candidates = [t for t in tn_candidates if t.name in permitted_tn]
        for t in tn_candidates:
            tns[t.work_order].append(t.name)
            tn_rows[t.work_order].append(t)
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
            "cancelled": int(wo.docstatus or 0) == 2,
            "planned_start_date": wo.planned_start_date,
            "planned_end_date": wo.planned_end_date,
            "jc_start": min(starts) if starts else None,
            "jc_end": max(ends) if ends else None,
            "tracking_numbers": tns.get(wo.wo, []),
            "tracking_number_rows": list(tn_rows.get(wo.wo, [])),
            "operations": [
                {"name": op.name, "operation": op.operation,
                 "sequence_id": op.sequence_id,
                 "is_corrective_operation": op.operation in corrective,
                 "work_order": wo.wo}
                for op in ops.get(wo.wo, [])
            ],
            "job_cards": list(jcs.get(wo.wo, [])),
            "link_proof": ("wo.sales_order_item" if wo.sales_order_item else
                           "wo.fg_sales_order_item" if wo.fg_sales_order_item else
                           "ppi.sales_order_item"),
        })
    return grouped, status


def load_job_card_time_logs(jc_names):
    """Child time logs per Job Card; complements top-level actual dates."""
    status = {"available": True, "reason": ""}
    names = [name for name in (jc_names or []) if name]
    if not names:
        return {}, status
    try:
        rows = frappe.get_all(
            "Job Card Time Log",
            filters={"parent": ["in", names]},
            fields=["parent", "from_time", "to_time"])
        logs = defaultdict(list)
        for row in rows:
            logs[row.parent].append({"from_time": row.from_time,
                                     "to_time": row.to_time})
        return logs, status
    except Exception as exc:  # noqa: BLE001
        return {}, {"available": False, "reason": "query_error", "error": str(exc)}


def load_stock_entries(wo_names):
    """Load Manufacture Stock Entries + finished rows with permission completeness."""
    status = {"available": True, "reason": ""}
    if not wo_names:
        return {}, status
    if not frappe.has_permission("Stock Entry", "read"):
        return {}, {"available": False, "reason": "permission"}
    try:
        candidates = frappe.db.sql(
            """select name, work_order, docstatus, ifnull(is_return, 0) as is_return,
                      posting_date, posting_time, outgoing_stock_entry
               from `tabStock Entry`
               where work_order in %(wos)s and purpose = 'Manufacture'
                 and docstatus in (0, 1, 2)""",
            {"wos": tuple(wo_names)}, as_dict=True)
        names = [row.name for row in candidates]
        permitted = {row.name for row in frappe.get_list(
            "Stock Entry", filters=[["name", "in", names],
                                    ["docstatus", "in", (0, 1, 2)]],
            fields=["name"], limit_page_length=0)} if names else set()
        if set(names) != permitted:
            return {}, {"available": False, "reason": "permission"}
        details = frappe.get_all(
            "Stock Entry Detail", filters={"parent": ["in", names]},
            fields=["name", "parent", "is_finished_item", "item_code", "qty",
                    "uom", "stock_uom", "t_warehouse", "batch_no",
                    "stock_tracking_number", "against_stock_entry"]) if names else []
        items_by_parent = defaultdict(list)
        for detail in details:
            items_by_parent[detail.parent].append({
                "name": detail.name, "is_finished_item": detail.is_finished_item,
                "item_code": detail.item_code, "qty": detail.qty,
                "uom": detail.uom, "stock_uom": detail.stock_uom,
                "t_warehouse": detail.t_warehouse, "batch_no": detail.batch_no,
                "stock_tracking_number": detail.stock_tracking_number,
                "against_stock_entry": detail.against_stock_entry,
            })
        grouped = defaultdict(list)
        for row in candidates:
            grouped[row.work_order].append({
                "name": row.name, "work_order": row.work_order,
                "purpose": "Manufacture", "stock_entry_type": "Manufacture",
                "docstatus": row.docstatus, "is_return": row.is_return,
                "posting_date": row.posting_date, "posting_time": row.posting_time,
                "outgoing_stock_entry": row.outgoing_stock_entry,
                "items": items_by_parent.get(row.name, []),
            })
        return grouped, status
    except Exception as exc:  # noqa: BLE001
        return {}, {"available": False, "reason": "query_error", "error": str(exc)}


def load_quality_inspections(jc_to_wo, se_to_wo):
    """Load QIs by Job Card / Stock Entry reference with permission completeness."""
    status = {"available": True, "reason": ""}
    names = sorted(set(jc_to_wo) | set(se_to_wo))
    if not names:
        return {}, status
    if not frappe.has_permission("Quality Inspection", "read"):
        return {}, {"available": False, "reason": "permission"}
    try:
        candidates = frappe.db.sql(
            """select name, docstatus, status, reference_type, reference_name,
                      item_code, sample_size, stock_tracking_number, report_date
               from `tabQuality Inspection`
               where reference_name in %(names)s and docstatus = 1""",
            {"names": tuple(names)}, as_dict=True)
        permitted = {row.name for row in frappe.get_list(
            "Quality Inspection", filters=[["name", "in", [r.name for r in candidates]]],
            fields=["name"], limit_page_length=0)} if candidates else set()
        if {row.name for row in candidates} != permitted:
            return {}, {"available": False, "reason": "permission"}
        grouped = defaultdict(list)
        for row in candidates:
            work_order = (jc_to_wo.get(row.reference_name)
                          or se_to_wo.get(row.reference_name))
            if work_order:
                grouped[work_order].append({
                    "name": row.name, "docstatus": row.docstatus,
                    "status": row.status, "reference_type": row.reference_type,
                    "reference_name": row.reference_name,
                    "item_code": row.item_code, "sample_size": row.sample_size,
                    "stock_tracking_number": row.stock_tracking_number,
                    "report_date": row.report_date,
                    "coverage_qty": None,
                })
        return grouped, status
    except Exception as exc:  # noqa: BLE001
        return {}, {"available": False, "reason": "query_error", "error": str(exc)}


def load_dns(lines):
    line_ids = [l.so_line for l in lines]
    if not line_ids:
        return {}, False
    po_expr = ("dn.custom_tongtool_purchase_order"
               if frappe.db.has_column("Delivery Note", "custom_tongtool_purchase_order")
               else "null")
    rows = frappe.db.sql(
        f"""select dn.name as dn, dn.posting_date as date, dn.status as status,
                  dn.docstatus as docstatus, ifnull(dn.is_return, 0) as is_return,
                  dn.return_against as return_against,
                  {po_expr} as tongtool_po,
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
               row.uom, row.warehouse, row.dn_detail)
        if key not in grouped:
            grouped[key] = frappe._dict(row)
            grouped[key]["qty"] = 0.0
            grouped[key]["dn_items"] = []
            grouped[key]["item_qty"] = {}
        grouped[key]["qty"] += _num(row.qty)
        if row.dn_item:
            grouped[key]["dn_items"].append(row.dn_item)
            grouped[key]["item_qty"][row.dn_item] = (
                grouped[key]["item_qty"].get(row.dn_item, 0.0) + _num(row.qty))
    for row in grouped.values():
        row["dn_item"] = ",".join(sorted(set(row["dn_items"])))
    out = defaultdict(list)
    for row in grouped.values():
        out[row.so_line].append(row)
    return out, restricted


def _load_shipment_events(shipment_names):
    """Batch-load the Shipment Logistics Event child rows (read-only)."""
    events = defaultdict(list)
    names = sorted({name for name in (shipment_names or []) if name})
    if not names:
        return events
    try:
        rows = frappe.get_all(
            "Shipment Logistics Event",
            filters={"parent": ["in", names], "parenttype": "Shipment"},
            fields=["parent", "seq", "event_time", "event_name", "event_date",
                    "location", "description"],
            order_by="parent asc, idx asc")
    except Exception:  # noqa: BLE001
        # Event history is additive evidence; losing it must not hide the
        # status lines already loaded.
        return events
    for event in rows:
        events[event.parent].append({
            "seq": event.seq,
            "time": event.event_time,
            "name": event.event_name,
            "date": event.event_date,
            "location": event.location,
            "description": event.description,
        })
    return events


def _identity_conflict_progress(rows, events_by_shipment):
    candidates = []
    for row in rows:
        progress = progress_from_shipment(
            row, events_by_shipment.get(row.shipment, []))
        candidates.extend(progress.get("progress_candidates") or [])
    candidates.sort(key=lambda item: (
        str(item.get("source") or ""), str(item.get("source_record") or ""),
        str(item.get("raw_status") or "")))
    return {
        "latest_progress_status": None,
        "latest_progress_at": None,
        "latest_progress_kind": None,
        "progress_source": None,
        "is_final": False,
        "conflict_flag": True,
        "conflict_reasons": ["shipment_identity_conflict"],
        "progress_candidates": candidates,
    }


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
                      custom_zmt_match_status as match_status, modified
               from `tabShipment`
               where custom_zmt_logistic_number in %(numbers)s and docstatus in (0, 1)""",
            {"numbers": tuple(all_numbers)}, as_dict=True)
        permitted = {r.name for r in frappe.get_list(
            "Shipment", filters=[["custom_zmt_logistic_number", "in", all_numbers],
                                 ["docstatus", "in", (0, 1)]],
            fields=["name"], limit_page_length=0)}
        restricted = {c.shipment for c in candidates} != permitted
        grouped = defaultdict(list)
        for row in candidates:
            if row.shipment in permitted:
                grouped[row.number].append(row)
        events_by_shipment = _load_shipment_events(
            [row.shipment for row in candidates if row.shipment in permitted])
        for number in sorted(grouped):
            rows = sorted(grouped[number], key=lambda row: str(row.shipment))
            if len(rows) == 1:
                row = rows[0]
                row["progress"] = progress_from_shipment(
                    row, events_by_shipment.get(row.shipment, []))
                shipments[number] = row
                continue
            representative = dict(rows[0])
            representative["shipment"] = None
            representative["identity_conflict"] = True
            representative["shipment_candidates"] = [row.shipment for row in rows]
            representative["progress"] = _identity_conflict_progress(
                rows, events_by_shipment)
            shipments[number] = representative
    return numbers, shipments, restricted


def _permission_flags():
    return {
        "sales_order": frappe.has_permission("Sales Order", "read"),
        "delivery_note": frappe.has_permission("Delivery Note", "read"),
        "work_order": frappe.has_permission("Work Order", "read"),
        "production_plan": frappe.has_permission("Production Plan", "read"),
        "shipment": frappe.has_permission("Shipment", "read"),
        "job_card": frappe.has_permission("Job Card", "read"),
        "stock_entry": frappe.has_permission("Stock Entry", "read"),
        "quality_inspection": frappe.has_permission("Quality Inspection", "read"),
    }


@frappe.whitelist()
def get_supply_facts(filters=None, **kwargs):
    """Batch machine entry: SO lines → stage balances, milestones, tranches, links."""
    filters = _normalize_filters(filters, kwargs)
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
    lines, so_restricted, total_lines = load_lines(filters)
    if not lines:
        external = {
            "tongtool_po": "not_integrated",
            "receipt": "not_integrated",
            "inventory": "not_integrated",
            "warehouse_receipt": "not_integrated",
        }
        if total_lines:
            empty_reason = "offset_out_of_range"
        elif so_restricted:
            empty_reason = "all_restricted"
        else:
            empty_reason = "no_matching_lines"
        pagination = _pagination(filters, 0, total_lines)
        applied = {k: v for k, v in filters.items() if k not in ("limit", "offset")}
        empty_source_status = {
            name: _source_state(ok) for name, ok in permissions.items()}
        for name in ("tongtool_po", "receipt", "inventory"):
            empty_source_status[name] = {"available": False, "restricted": False,
                                         "reason": "not_integrated"}
        coverage = {
            "sales_orders": 0, "so_lines": 0, "so_lines_total": total_lines,
            "sources": permissions,
            "restricted": {"sales_order": so_restricted},
            "source_status": empty_source_status,
            "external_sources": external, "observed_at": _iso(observed_at),
            "empty_reason": empty_reason,
        }
        notes = ["empty_result: " + empty_reason,
                 "external sources not integrated: tongtool_po, receipt, warehouse_receipt"]
        manifest = build_manifest(as_of=as_of, scope=dict(filters),
                                  lines=[], facts=[], coverage=coverage,
                                  counts={"input": 0, "output": 0},
                                  partial=True, notes=notes)
        manifest["observed_at"] = _iso(observed_at)
        manifest["pagination"] = pagination
        manifest["truncated"] = pagination["partial"]
        manifest["termination_reason"] = pagination["termination_reason"]
        return {
            "schema_version": SCHEMA_VERSION, "rule_version": RULE_VERSION,
            "implementation_version": IMPLEMENTATION_VERSION,
            "as_of": str(as_of), "lines": [], "stage_balances": [], "milestones": [],
            "availability_schedule": [], "links": [], "production_evidence": [],
            "shipment_progress": [],
            "source_status": empty_source_status,
            "manifest": manifest,
            "applied_filters": applied, "pagination": pagination,
        }

    pps, pp_restricted = (load_pps(lines) if permissions["production_plan"] else ({}, False))
    if permissions["work_order"]:
        wos, wo_status = load_wos(lines, pps)
    else:
        wos, wo_status = {}, {"available": False, "reason": "permission",
                              "restricted": False, "restricted_wos": set(),
                              "job_card_unavailable_wos": set(),
                              "tracking_unavailable_wos": set()}
    wo_restricted = bool(wo_status.get("restricted"))
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

    facts = []
    dn_ok = permissions["delivery_note"] and not dn_restricted
    wo_ok = (permissions["work_order"] and wo_status.get("available", True)
             and not wo_restricted)
    ship_ok = permissions["shipment"] and not ship_restricted
    wo_names_all = sorted({wo["wo"] for values in wos.values() for wo in values})
    jc_to_wo = {jc.get("name"): wo["wo"] for values in wos.values()
                for wo in values for jc in wo.get("job_cards", [])}
    stock_by_wo, stock_status = (
        load_stock_entries(wo_names_all) if permissions["stock_entry"]
        else ({}, {"available": False, "reason": "permission"}))
    se_to_wo = {entry.get("name"): wo_name
                for wo_name, entries in stock_by_wo.items()
                for entry in entries}
    qc_by_wo, qc_status = (
        load_quality_inspections(jc_to_wo, se_to_wo)
        if permissions["quality_inspection"]
        else ({}, {"available": False, "reason": "permission"}))
    evidence_by_line = {}
    jc_unavailable = wo_status.get("job_card_unavailable_wos") or set()
    tn_unavailable = wo_status.get("tracking_unavailable_wos") or set()
    for line in lines:
        line_wos = wos.get(line.so_line, [])
        line_wo_names = {wo["wo"] for wo in line_wos}
        if not wo_ok and not line_wos:
            evidence_by_line[line.so_line] = unknown_line_evidence("permission")
            continue
        jc_ok = permissions["job_card"] and not (jc_unavailable & line_wo_names)
        tn_ok = not (tn_unavailable & line_wo_names)
        wo_evidence = []
        for wo in line_wos:
            wo_evidence.append(build_wo_evidence(
                {"name": wo["wo"], "qty": wo["qty"],
                 "stock_uom": wo["stock_uom"],
                 "production_item": wo["item_code"],
                 "docstatus": wo["docstatus"]},
                wo.get("operations", []), wo.get("job_cards", []),
                wo.get("tracking_number_rows", []),
                stock_by_wo.get(wo["wo"], []),
                qc_by_wo.get(wo["wo"], []),
                order_uom=line.uom,
                availability={
                    "job_cards": jc_ok,
                    "work_order": wo_ok,
                    "tracking_numbers": tn_ok,
                    "stock_entries": stock_status["available"],
                    "quality_inspections": qc_status["available"],
                },
                observed_at=_iso(observed_at)))
        evidence_by_line[line.so_line] = rollup_line_evidence(
            wo_evidence, item_code=line.item_code, order_uom=line.uom)
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
            "evidence": evidence_by_line.get(line.so_line),
            "evidence_source_status": {"stock_entry": stock_status,
                                       "quality_inspection": qc_status},
            "observed_at": observed_at,
        }))

    stage_filter = filters.get("stage")
    if stage_filter:
        for fact in facts:
            fact["stage_balances"] = [
                row for row in fact["stage_balances"] if row["stage"] == stage_filter]
            fact["availability_schedule"] = [
                row for row in fact["availability_schedule"]
                if row.get("stage") == stage_filter]

    counts = {
        "input": len(lines), "output": len(facts),
        "stage_balances": sum(len(f["stage_balances"]) for f in facts),
        "milestones": sum(len(f["milestones"]) for f in facts),
        "availability_schedule": sum(len(f["availability_schedule"]) for f in facts),
        "links": sum(len(f["links"]) for f in facts),
        "shipment_progress": sum(len(f.get("shipment_progress", [])) for f in facts),
    }
    jc_unavailable = bool(wo_status.get("job_card_unavailable_wos"))
    tn_unavailable = bool(wo_status.get("tracking_unavailable_wos"))
    source_status = {
        "sales_order": _source_state(
            permissions["sales_order"], so_restricted,
            {"reason": "permission"} if not permissions["sales_order"] else None),
        "production_plan": _source_state(
            permissions["production_plan"], pp_restricted,
            {"reason": "permission"} if not permissions["production_plan"] else None),
        "work_order": _source_state(
            wo_status.get("available", True), wo_restricted, wo_status),
        "job_card": _source_state(
            permissions["job_card"] and not jc_unavailable, jc_unavailable,
            {"reason": "permission"}
            if (not permissions["job_card"] or jc_unavailable) else None),
        "tracking_number": _source_state(
            not tn_unavailable, tn_unavailable,
            {"reason": "permission"} if tn_unavailable else None),
        "stock_entry": _source_state(
            stock_status.get("available", True), False, stock_status),
        "quality_inspection": _source_state(
            qc_status.get("available", True), False, qc_status),
        "delivery_note": _source_state(
            permissions["delivery_note"], dn_restricted,
            {"reason": "permission"} if not permissions["delivery_note"] else None),
        "shipment": _source_state(
            permissions["shipment"], ship_restricted,
            {"reason": "permission"} if not permissions["shipment"] else None),
    }
    if "job_card_time_log" in wo_status:
        source_status["job_card_time_log"] = _source_state(
            wo_status["job_card_time_log"].get("available", True), False,
            wo_status["job_card_time_log"])
    for name in ("tongtool_po", "receipt", "inventory"):
        source_status[name] = {"available": False, "restricted": False,
                               "reason": "not_integrated"}
    for name, state in source_status.items():
        if (not state.get("available", True)
                and state.get("reason") != "not_integrated"):
            partial_reasons.append("%s source unavailable: %s" % (
                name.replace("_", " "), state.get("reason", "unknown")))
    partial = bool(partial_reasons)
    coverage = {
        "sales_orders": len({l.so for l in lines}), "so_lines": len(lines),
        "so_lines_total": total_lines,
        "delivery_notes": len(dn_names), "shipments": len(shipment_by_number),
        "sources": permissions, "restricted": restricted,
        "source_status": source_status,
        "source_timestamps": {"sales_order": _iso(observed_at)},
        "observed_at": _iso(observed_at),
        "external_sources": {
            "tongtool_po": "not_integrated",
            "receipt": "not_integrated",
            "inventory": "not_integrated",
            "warehouse_receipt": "not_integrated",
        },
    }
    pagination = _pagination(filters, len(lines), total_lines,
                             cursor=lines[-1].so_line if lines else None)
    applied = {k: v for k, v in filters.items() if k not in ("limit", "offset")}
    manifest = build_manifest(
        as_of=as_of, scope=dict(filters),
        lines=[f["line"] for f in facts], facts=facts,
        coverage=coverage, counts=counts, partial=partial,
        notes=partial_reasons)
    manifest["observed_at"] = _iso(observed_at)
    manifest["pagination"] = pagination
    manifest["truncated"] = pagination["partial"]
    manifest["termination_reason"] = pagination["termination_reason"]
    manifest["partial_reasons"] = list(partial_reasons)
    return {
        "schema_version": SCHEMA_VERSION, "rule_version": RULE_VERSION,
        "implementation_version": IMPLEMENTATION_VERSION,
        "as_of": str(as_of),
        "lines": [f["line"] for f in facts],
        "stage_balances": [r for f in facts for r in f["stage_balances"]],
        "milestones": [r for f in facts for r in f["milestones"]],
        "availability_schedule": [r for f in facts for r in f["availability_schedule"]],
        "links": [r for f in facts for r in f["links"]],
        "production_evidence": [
            dict({"so": f["line"]["so"], "so_line": f["line"]["so_line"]},
                 **(f.get("production_evidence") or {}))
            for f in facts
        ],
        "shipment_progress": [
            row for f in facts for row in f.get("shipment_progress", [])],
        "source_status": source_status,
        "manifest": manifest,
        "applied_filters": applied, "pagination": pagination,
    }


def _num_or_none(value):
    return None if value is None else round(_num(value), 6)
