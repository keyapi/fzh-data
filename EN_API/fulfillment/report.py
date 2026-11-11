"""统一查询结果分区与顶部摘要（蓝图 §9.1 / §9.2）。"""
from __future__ import annotations

from item_shipment_status import fmt_qty, num

from .rules import next_actions
from .stages import STAGE_NAMES


def _weight(line) -> float:
    if line.stage and line.stage.stage == 0:
        return num(line.quantities.get("cancelled_or_amended_qty"))
    return num(line.open_qty)


def build_summary(result) -> dict:
    lines = result.lines
    t = result.totals or {}
    resol = result.resolutions
    hit = sum(1 for r in resol if not r.miss_reason)
    miss = sum(1 for r in resol if r.miss_reason)

    stage_qty = {}
    for ln in lines:
        w = _weight(ln)
        if w <= 0:
            continue
        stage_qty[ln.stage.stage] = stage_qty.get(ln.stage.stage, 0.0) + w

    dist = " | ".join(
        f"{STAGE_NAMES.get(s, s)} {fmt_qty(v)}" for s, v in sorted(stage_qty.items()))

    risk = {"error": 0, "warn": 0, "info": 0}
    for a in result.anomalies:
        risk[a.severity] = risk.get(a.severity, 0) + 1

    actions = next_actions(result.anomalies)
    actions_txt = "、".join(f"{role} {n} 项" for role, n in actions.items()) or "无"

    return {
        "query": f"{result.inputs_text}（输入 {len(resol)}，命中 {hit}，未命中 {miss}）",
        "demand": (f"{len({ln.so for ln in lines})} 张 SO / {fmt_qty(t.get('order_qty', 0))} 件；"
                   f"有效 {fmt_qty(t.get('valid_qty', 0))}"
                   + (f"；已改单/作废 {fmt_qty(t.get('voided_qty', 0))}" if t.get('voided_qty') else "")
                   + (f"；已取消 {fmt_qty(t.get('cancelled_qty', 0))}" if t.get('cancelled_qty') else "")),
        "stage_dist": dist or "-",
        "risk": f"高 {risk.get('error', 0)} / 中 {risk.get('warn', 0)} / 提示 {risk.get('info', 0)}",
        "availability": (f"事实(已出库) {fmt_qty(t.get('shipped_qty', 0))} | "
                         f"未发 {fmt_qty(t.get('open_qty', 0))}"),
        "next_actions": actions_txt,
    }


def headline(result) -> str:
    """一句业务结论（蓝图 §1.1 风格）。"""
    if result.empty:
        return "无匹配的销售订单。"
    t = result.totals or {}
    open_qty = num(t.get("open_qty", 0))
    dead = num(t.get("dead_qty", 0))
    parts = [f"命中 {len(result.lines)} 行订单，未发 {fmt_qty(open_qty)} 件"]
    if dead:
        parts.append(f"其中 {fmt_qty(dead)} 件为 Closed 死单，不会发")
    inprog = num(t.get("in_progress_qty", 0))
    if inprog:
        parts.append(f"在产/待发 {fmt_qty(inprog)} 件")
    return "；".join(parts) + "。"


def build_partitions(result) -> dict:
    lines = result.lines
    orders = [{
        "so": ln.so, "line_id": ln.so_line_id, "item_code": ln.item_code,
        "so_status": ln.so_status, "delivery_date": ln.delivery_date,
        "ordered_qty": ln.ordered_qty, "shipped_qty": ln.shipped_qty, "open_qty": ln.open_qty,
        "stage": ln.stage.stage, "substate": ln.stage.substate,
        "input_sources": ln.input_sources,
    } for ln in lines]

    stage_qty = {}
    for ln in lines:
        w = _weight(ln)
        if w > 0:
            stage_qty[ln.stage.stage] = stage_qty.get(ln.stage.stage, 0.0) + w
    stage = [{"stage": s, "name": STAGE_NAMES.get(s, ""), "qty": v}
             for s, v in sorted(stage_qty.items())]

    reconcile = [{"so": ln.so, "line_id": ln.so_line_id, "ok": ln.quantities.get("reconcile_ok"),
                  "valid_demand_qty": ln.quantities.get("valid_demand_qty"),
                  "shipped": ln.quantities.get("factory_shipped_qty"),
                  "open": ln.quantities.get("factory_open_qty")} for ln in lines]

    return {"orders": orders, "stage_qty": stage, "reconcile": reconcile}
