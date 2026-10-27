# -*- coding: utf-8 -*-
"""W1 供应事实（Jack ``/api/method/key_test.supply_facts.get_supply_facts``）→ 决策包动作列。

只做映射与聚合，不改净额口径：
- SO 行 → 分公司仓（``so_backlog.customer_branch``）→ 决策包 ``canonical_warehouse``；
- SO 行 ``item_code``（皮壳去 ``PK#``）→ 决策包 ``canonical_sku``；
- 阶段量按 ``SKU × 分公司仓 × UOM`` 求和并标跨单数；**不跨 UOM、不跨仓合并**。

``shipped_in_transit`` 只是阶段事实，**不是海外仓可用**，动作文案里也不能写成已可用。
"""

from __future__ import annotations

import json
from pathlib import Path

import pandas as pd

from .so_backlog import finished_item

STAGE_FIELDS = {
    "produced_pending_dn": "so_stage_produced_pending_dn",
    "in_production": "so_stage_in_production",
    "not_planned": "so_stage_not_planned",
    "shipped_in_transit": "so_stage_in_transit",
    "unknown": "so_stage_unknown",
    "over_produced": "so_stage_over_produced",
    "arrived_not_sellable": "so_stage_arrived_not_sellable",
    "delivered_sellable": "so_stage_delivered_sellable",
}

ACTION_NO_NEED = "不需补（当前窗口）"
ACTION_SHIP = "催发运"
ACTION_PRODUCE = "催生产"
ACTION_WORK_ORDER = "催建工单"
ACTION_VERIFY_STAGE = "核实阶段（W1 unknown）"
ACTION_VERIFY_ARRIVAL = "核实到仓 ETA"
ACTION_VERIFY_ETA = "核实 ETA"
ACTION_BUY = "补单"


def load_w1_stages(cache_path: str | Path) -> pd.DataFrame:
    """读取逐 SO 缓存（JSONL，每行 ``{so, payload}``）→ 阶段余额长表。"""
    path = Path(cache_path)
    if not path.exists():
        return pd.DataFrame(columns=["so", "so_line_id", "item_code", "warehouse", "uom",
                                     "stage", "qty", "source_record", "qty_status"])
    rows = []
    for line in path.read_text(encoding="utf-8").splitlines():
        if not line.strip():
            continue
        record = json.loads(line)
        for balance in (record.get("payload") or {}).get("stage_balances") or []:
            rows.append(dict(
                so=balance.get("so") or record.get("so"),
                so_line_id=balance.get("so_line_id"),
                item_code=balance.get("item_code"),
                warehouse=balance.get("warehouse"),
                uom=balance.get("uom"),
                stage=balance.get("stage"),
                qty=balance.get("qty"),
                qty_status=balance.get("qty_status", "known"),
                source_record=balance.get("source_record"),
                demand_status=balance.get("demand_status"),
            ))
    frame = pd.DataFrame(rows)
    if len(frame):
        frame["qty"] = pd.to_numeric(frame["qty"], errors="coerce")
    return frame


def map_stage_keys(stages: pd.DataFrame, so_branch: dict[str, str | None]) -> pd.DataFrame:
    """给每条阶段余额补 ``canonical_sku`` / ``canonical_warehouse``。"""
    if not len(stages):
        return stages.assign(canonical_sku=None, canonical_warehouse=None)
    frame = stages.copy()
    mapped = [finished_item(code) for code in frame["item_code"]]
    frame["canonical_sku"] = [item for item, _assumed in mapped]
    frame["conversion_assumed"] = [assumed for _item, assumed in mapped]
    frame["canonical_warehouse"] = frame["so"].map(lambda so: so_branch.get(str(so)))
    return frame


def aggregate_stages(stages: pd.DataFrame) -> pd.DataFrame:
    """按 ``SKU × 分公司仓 × UOM`` 聚合阶段量；跨 SO 求和并记录 SO/WO 数。

    UOM 不合并：不同单位各成一行；单位缺失的行留空但单列（不塞进别单位）。
    """
    columns = ["canonical_sku", "canonical_warehouse", "uom"] + list(STAGE_FIELDS.values()) + [
        "so_stage_so_count", "wo_completed_count", "wo_in_process_count",
        "wo_not_started_count", "w1_stage_rows"]
    if not len(stages):
        return pd.DataFrame(columns=columns)
    if "canonical_warehouse" not in stages.columns:
        return pd.DataFrame(columns=columns)
    frame = stages[stages["canonical_warehouse"].notna()].copy()
    if not len(frame):
        return pd.DataFrame(columns=columns)
    frame["uom"] = frame["uom"].fillna("<unknown>")
    frame["qty"] = pd.to_numeric(frame["qty"], errors="coerce")

    records = []
    for key, group in frame.groupby(["canonical_sku", "canonical_warehouse", "uom"]):
        record = dict(zip(["canonical_sku", "canonical_warehouse", "uom"], key))
        for stage, column in STAGE_FIELDS.items():
            record[column] = round(float(group.loc[group["stage"] == stage, "qty"].sum()), 6)
        record["so_stage_so_count"] = int(group["so"].nunique())
        record["wo_completed_count"] = int(
            group.loc[group["stage"] == "produced_pending_dn", "source_record"]
            .dropna().astype(str).loc[lambda s: s.str.startswith("WO")].nunique())
        record["wo_in_process_count"] = int(
            group.loc[group["stage"] == "in_production", "source_record"]
            .dropna().astype(str).loc[lambda s: s.str.startswith("WO")].nunique())
        record["wo_not_started_count"] = int(
            (group["stage"] == "not_planned").sum())
        record["w1_stage_rows"] = int(len(group))
        records.append(record)
    return pd.DataFrame(records, columns=columns)


def apply_actions(pack: pd.DataFrame, stages: pd.DataFrame) -> pd.DataFrame:
    """新增 ``action`` / ``action_basis`` / ``action_confidence``；不改原 ``recommendation``。"""
    out = pack.copy()
    key = ["canonical_sku", "canonical_warehouse", "canonical_uom"]
    agg = aggregate_stages(stages) if len(stages) else pd.DataFrame()
    if len(agg):
        agg = agg.rename(columns={"uom": "canonical_uom"})
        out = out.merge(agg, on=key, how="left")
    for column in STAGE_FIELDS.values():
        if column not in out.columns:
            out[column] = 0.0
        out[column] = pd.to_numeric(out[column], errors="coerce").fillna(0.0)
    for column in ("wo_completed_count", "wo_in_process_count", "wo_not_started_count",
                   "so_stage_so_count", "w1_stage_rows"):
        if column not in out.columns:
            out[column] = 0
        out[column] = pd.to_numeric(out[column], errors="coerce").fillna(0).astype(int)

    actions, bases, confidences, dedup = [], [], [], []
    for row in out.to_dict("records"):
        gap = float(row.get("protect_gap") or 0)
        produced = float(row.get("so_stage_produced_pending_dn") or 0)
        in_prod = float(row.get("so_stage_in_production") or 0)
        transit = float(row.get("so_stage_in_transit") or 0)
        not_planned = float(row.get("so_stage_not_planned") or 0)
        unknown_stage = float(row.get("so_stage_unknown") or 0)
        conditional = float(row.get("po_qty") or 0) + float(row.get("intransit_qty") or 0)
        pieces = []
        if row["so_stage_so_count"]:
            pieces.append(f"{row['so_stage_so_count']} 张 SO")
        if row["wo_completed_count"]:
            pieces.append(f"完工 WO {row['wo_completed_count']} 张")
        if row["wo_in_process_count"]:
            pieces.append(f"在产 WO {row['wo_in_process_count']} 张")
        if produced:
            pieces.append(f"完工待发运 {produced:g}")
        if in_prod:
            pieces.append(f"在产 {in_prod:g}")
        if transit:
            pieces.append(f"在途 {transit:g}（阶段事实，非海外可用）")
        if not_planned:
            pieces.append(f"未排产 {not_planned:g}")
        if unknown_stage:
            pieces.append(f"阶段未归类 {unknown_stage:g}（有 W1 行但阶段 unknown）")
        if conditional:
            pieces.append(f"在途/PO 条件量 {conditional:g}（无 ETA）")

        # 顺序按用户口径：完工待发运 > 在产 > 在途（核实到仓 ETA）> 未排产 > 条件量 > 补单。
        # 同时有完工与在途时取靠前阶段，两者数量都写进 action_basis。
        if gap <= 0:
            action = ACTION_NO_NEED
        elif produced > 0:
            action = ACTION_SHIP
        elif in_prod > 0:
            action = ACTION_PRODUCE
        elif transit > 0:
            action = ACTION_VERIFY_ARRIVAL
        elif not_planned > 0:
            action = ACTION_WORK_ORDER
        elif unknown_stage > 0:
            # 有 W1 阶段行但 Jack 判成 unknown：不能直接判补单，先核实
            action = ACTION_VERIFY_STAGE
        elif conditional > 0:
            action = ACTION_VERIFY_ETA
        else:
            action = ACTION_BUY
        actions.append(action)
        dedup.append("dedup_unproven" if (transit > 0 and conditional > 0) else "")
        bases.append("；".join(pieces) if pieces else "无 W1 阶段行，也无在途/PO 条件量")
        confidences.append("measured" if row["w1_stage_rows"] else "assumed")

    out["action"] = actions
    out["action_basis"] = bases
    out["action_confidence"] = confidences
    out["transit_dedup_status"] = dedup
    out["action_note"] = ("shipped_in_transit 只用于决定动作，不进可用供给；"
                          "与通途在途/PO 是否重复无法证明时标 dedup_unproven；"
                          "W1 partial=true 仅因通途 PO/入库未接入")
    return out
