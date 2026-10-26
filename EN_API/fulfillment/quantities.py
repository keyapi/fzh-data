"""数量阶梯与对账（蓝图 §3.1，本包只实现阶段 0–3 的子集）。"""
from __future__ import annotations

from item_shipment_status import num, op_progress


def credible_produced_qty(row, jc_map) -> float:
    """本行可信完工量 = 各工单「第一道工序完成量」之和（不跨工序求和，复用引擎口径）。"""
    total = 0.0
    for w in row.get("wos") or []:
        total += op_progress(w, jc_map.get(w["name"], []))["done_qty"]
    return total


def quantity_ladder(row, jc_map) -> dict:
    """一行 SO×物料的阶段 0–3 数量阶梯 + 对账结果。

    对账恒等式（蓝图 §3.1）：有效需求 = 已工厂出库 + 工厂未出库。
    """
    qty = num(row.get("qty"))
    voided = bool(row.get("voided"))
    cancelled = bool(row.get("cancelled"))

    cancelled_or_amended = qty if (voided or cancelled) else 0.0
    valid_demand = 0.0 if (voided or cancelled) else qty

    planned = sum(num(p.get("planned_qty")) for p in (row.get("pps") or []))
    wo_qty = sum(num(w.get("qty")) for w in (row.get("wos") or []))
    produced = credible_produced_qty(row, jc_map)

    shipped = num(row.get("delivered_qty"))
    open_qty = num(row.get("open_qty"))

    ladder = {
        "ordered_qty": qty,
        "cancelled_or_amended_qty": cancelled_or_amended,
        "valid_demand_qty": valid_demand,
        "planned_qty": planned,
        "work_order_qty": wo_qty,
        "credible_produced_qty": produced,
        "factory_shipped_qty": shipped,
        "draft_dn_qty": num(row.get("draft_dn")),
        "factory_open_qty": open_qty,
    }
    # 对账（阶段 0–3）：
    #   有效行 → 有效需求 = 已工厂出库 + 工厂未出库
    #   作废/取消行 → 订购量全部计入 取消/作废（其 open_qty 不参与未发口径）
    if voided or cancelled:
        ladder["reconcile_ok"] = abs(qty - cancelled_or_amended) < 1e-6
    else:
        ladder["reconcile_ok"] = abs(valid_demand - (shipped + open_qty)) < 1e-6
    return ladder
