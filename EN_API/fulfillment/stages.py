"""阶段 0–3 状态机（蓝图 §3）。阶段 4–8（头程/到港/上架）数据不在 EN，标为外部缺失，本包不产出。

判定只用现有 ERPNext 事实：SO docstatus/status、PP 覆盖、工序卡（op_progress）、DN docstatus。
**不得**用 Work Order.status / produced_qty 当事实（不可信，见引擎文档）；进度一律读工序卡。
"""
from __future__ import annotations

from item_shipment_status import num, op_progress

from . import evidence as ev
from .model import StageResult

STAGE_NAMES = {0: "销售需求", 1: "待计划", 2: "生产中", 3: "工厂待出库"}


def resolve_stage(row, jc_map) -> StageResult:
    qty = num(row.get("qty"))
    open_qty = num(row.get("open_qty"))
    evid = []

    evid.append(ev.fact(row.get("so_status"), "erpnext:sales_order", row.get("so")))
    evid.append(ev.derived(open_qty, "qty - delivered_qty",
                           f"{row.get('so')}/{row.get('line_id')}"))

    # ── 阶段 0：销售需求（终态/草稿）──
    if row.get("voided"):
        return StageResult(0, "已改单(作废)", evid)
    if row.get("cancelled"):
        return StageResult(0, "已取消", evid)
    if num(row.get("so_docstatus")) == 0:
        return StageResult(0, "草稿", evid)

    # ── 阶段 3：已全部工厂出库 ──
    if open_qty <= 0:
        return StageResult(3, "已出库完成", evid)

    # ── 阶段 3：Closed 却未发（死单，不会发）──
    if row.get("so_status") == "Closed":
        return StageResult(3, "Closed未发(死单)", evid)

    pps, wos = row.get("pps") or [], row.get("wos") or []

    # ── 阶段 1：待计划 ──
    if not wos:
        sub = "未排产(无工单无生产计划)" if not pps else "已排产待下达(有计划无工单)"
        return StageResult(1, sub, evid)

    # ── 阶段 2/3：有工单 ──
    pros = [op_progress(w, jc_map.get(w["name"], [])) for w in wos]
    produced = sum(p["done_qty"] for p in pros)
    evid.append(ev.derived(produced, "job_card:first_op_total_completed_qty",
                           ", ".join(w["name"] for w in wos)))
    if not any(p["jc_count"] > 0 for p in pros):
        return StageResult(2, "未开工", evid)
    if produced + 1e-6 >= qty:
        return StageResult(3, "生产完成待出库", evid)
    return StageResult(2, "生产中", evid)


def stage_label(stage: int) -> str:
    return f"{stage} {STAGE_NAMES.get(stage, '')}"
