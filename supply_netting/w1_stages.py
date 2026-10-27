# -*- coding: utf-8 -*-
"""W1 供应事实（Jack ``key_test.supply_facts``）→ 决策包动作列（G1/G3 口径）。

只做映射与聚合，不改净额口径：

- 只把 ``scope=in_house`` 计入分公司动作；``external_fba`` 单列 ``so_stage_fba_*``，
  **不得覆盖自发货仓缺口**。
- ``qty_basis=job_card_first_op`` 只证明首工序，不等于可发运 → ``estimated``。
- ``unknown`` 阶段不得写成“没生产”：动作是「核实生产进度/开工证据」；
  只有 ``exclusion_reason`` 明确“缺开工证据”才给「催生产」。
- 动作按**能否覆盖缺口**选：能全覆盖的优先，同覆盖按
  produced → in_production → in_transit → not_planned → PO 顺序；
  覆盖不足给 ``action_qty`` 与 ``residual_gap``，并在动作名上标“+ 补单剩余”。
- 没有 ETa/需要日时只能标 ``timely_coverage_unproven``，不得声称及时。
"""

from __future__ import annotations

import json
from pathlib import Path

import pandas as pd

from .so_backlog import finished_item

IN_HOUSE = "in_house"
FBA_SCOPES = frozenset({"external_fba"})
FIRST_OP_BASIS = "job_card_first_op"

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
FBA_FIELDS = {
    "produced_pending_dn": "so_stage_fba_produced_pending_dn",
    "in_production": "so_stage_fba_in_production",
    "shipped_in_transit": "so_stage_fba_in_transit",
    "not_planned": "so_stage_fba_not_planned",
}

ACTION_NO_NEED = "不需补（当前窗口）"
ACTION_SHIP = "催发运"
ACTION_PRODUCE = "催生产"
ACTION_WORK_ORDER = "催建工单"
ACTION_VERIFY_PROGRESS = "核实生产进度/开工证据"
ACTION_VERIFY_ARRIVAL = "核实到仓 ETA"
ACTION_VERIFY_ETA = "核实 ETA"
ACTION_BUY = "补单"
SUFFIX_BUY_REST = " + 补单剩余"

COVERAGE_ORDER = (
    (ACTION_SHIP, "so_stage_produced_pending_dn", "produced"),
    (ACTION_PRODUCE, "so_stage_in_production", "in_production"),
    (ACTION_VERIFY_ARRIVAL, "so_stage_in_transit", "transit"),
    (ACTION_WORK_ORDER, "so_stage_not_planned", "not_planned"),
    (ACTION_VERIFY_PROGRESS, "so_stage_unknown_other", "unknown_other"),
    (ACTION_VERIFY_ETA, "conditional_supply_qty", "conditional"),
)

W1_COLUMNS = ["so", "so_line_id", "item_code", "warehouse", "uom", "stage", "qty",
              "qty_status", "qty_basis", "source_record", "scope", "role", "demand_status",
              "exclusion_reason", "stage_detail"]


def load_w1_stages(cache_path: str | Path) -> pd.DataFrame:
    """读取逐 SO 缓存（JSONL）→ 阶段余额长表，保留 scope/role/qty_basis 等证据字段。"""
    path = Path(cache_path)
    if not path.exists():
        return pd.DataFrame(columns=W1_COLUMNS)
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
                qty_status=balance.get("qty_status") or "known",
                qty_basis=balance.get("qty_basis") or "",
                source_record=balance.get("source_record"),
                scope=balance.get("scope") or "in_house",
                role=balance.get("role") or "",
                demand_status=balance.get("demand_status") or "",
                exclusion_reason=balance.get("exclusion_reason") or "",
                stage_detail=balance.get("stage_detail") or "",
            ))
    frame = pd.DataFrame(rows, columns=W1_COLUMNS)
    if len(frame):
        frame["qty"] = pd.to_numeric(frame["qty"], errors="coerce")
    return frame


def map_stage_keys(stages: pd.DataFrame, so_branch: dict[str, str | None]) -> pd.DataFrame:
    """给每条阶段余额补 ``canonical_sku`` / ``canonical_warehouse``。"""
    if not len(stages):
        frame = stages.copy()
        frame["canonical_sku"] = None
        frame["canonical_warehouse"] = None
        frame["conversion_assumed"] = False
        return frame
    frame = stages.copy()
    mapped = [finished_item(code) for code in frame["item_code"]]
    frame["canonical_sku"] = [item for item, _assumed in mapped]
    frame["conversion_assumed"] = [assumed for _item, assumed in mapped]
    frame["canonical_warehouse"] = frame["so"].map(lambda so: so_branch.get(str(so)))
    return frame


def _row_confidence(group: pd.DataFrame) -> str:
    """三档：measured（已知量且非首工序）/ estimated（首工序或推断）/ unknown（阶段 unknown）。"""
    if not len(group):
        return "unknown"
    if (group["stage"] == "unknown").all():
        return "unknown"
    if (group["qty_status"].fillna("unknown") != "known").any():
        return "estimated"
    if (group["qty_basis"].fillna("").str.contains(FIRST_OP_BASIS)).any():
        return "estimated"
    return "measured"


def aggregate_stages(stages: pd.DataFrame) -> pd.DataFrame:
    """按 ``SKU × 分公司仓 × UOM`` 聚合；只累加 ``scope=in_house``，FBA 单列。"""
    columns = (["canonical_sku", "canonical_warehouse", "uom"] + list(STAGE_FIELDS.values())
               + list(FBA_FIELDS.values())
               + ["so_stage_unknown_missing_start", "so_stage_unknown_other",
                  "so_stage_so_count", "wo_completed_count", "wo_in_process_count",
                  "wo_not_started_count", "w1_stage_rows", "w1_confidence"])
    if not len(stages) or "canonical_warehouse" not in stages.columns:
        return pd.DataFrame(columns=columns)
    frame = stages[stages["canonical_warehouse"].notna()].copy()
    if not len(frame):
        return pd.DataFrame(columns=columns)
    frame["uom"] = frame["uom"].fillna("<unknown>")
    frame["qty"] = pd.to_numeric(frame["qty"], errors="coerce")
    if "scope" not in frame.columns:
        frame["scope"] = IN_HOUSE
    for column in ("exclusion_reason", "qty_basis", "scope", "qty_status"):
        if column not in frame.columns:
            frame[column] = "" if column != "qty_status" else "known"

    # scope 缺失/为空时按 in_house 处理（旧缓存没有 scope 字段）
    frame["scope"] = frame["scope"].fillna("").replace("", IN_HOUSE)
    in_house = frame[frame["scope"].eq(IN_HOUSE)]
    fba = frame[frame["scope"].fillna("").isin(FBA_SCOPES)]

    records = []
    for key, group in in_house.groupby(["canonical_sku", "canonical_warehouse", "uom"]):
        record = dict(zip(["canonical_sku", "canonical_warehouse", "uom"], key))
        for stage, column in STAGE_FIELDS.items():
            record[column] = round(float(group.loc[group["stage"] == stage, "qty"].sum()), 6)
        fba_group = fba[(fba["canonical_sku"] == key[0]) & (fba["canonical_warehouse"] == key[1])
                        & (fba["uom"].fillna("<unknown>") == key[2])]
        for stage, column in FBA_FIELDS.items():
            record[column] = round(float(fba_group.loc[fba_group["stage"] == stage, "qty"].sum()), 6)
        unknown_rows = group[group["stage"] == "unknown"]
        missing_start = unknown_rows["exclusion_reason"].fillna("").str.contains("缺开工证据")
        record["so_stage_unknown_missing_start"] = round(
            float(unknown_rows.loc[missing_start, "qty"].sum()), 6)
        record["so_stage_unknown_other"] = round(
            float(unknown_rows.loc[~missing_start, "qty"].sum()), 6)
        record["so_stage_so_count"] = int(group["so"].nunique())
        record["wo_completed_count"] = int(
            group.loc[group["stage"] == "produced_pending_dn", "source_record"]
            .dropna().astype(str).loc[lambda s: s.str.startswith("WO")].nunique())
        record["wo_in_process_count"] = int(
            group.loc[group["stage"] == "in_production", "source_record"]
            .dropna().astype(str).loc[lambda s: s.str.startswith("WO")].nunique())
        record["wo_not_started_count"] = int((group["stage"] == "not_planned").sum())
        record["w1_stage_rows"] = int(len(group))
        record["w1_confidence"] = _row_confidence(group)
        records.append(record)
    return pd.DataFrame(records, columns=columns)


def _num(value) -> float:
    """NaN/None → 0.0；避免 float(nan) 被当成真值写进依据。"""
    if value is None:
        return 0.0
    try:
        number = float(value)
    except (TypeError, ValueError):
        return 0.0
    return 0.0 if pd.isna(number) else number


def _source_evidence(mapped: pd.DataFrame, key, stage_column: str) -> tuple[str, str]:
    """该阶段贡献的 SO / WO 编号（去重、限量）。"""
    stage = next((s for s, c in STAGE_FIELDS.items() if c == stage_column), None)
    if stage is None:
        return "", ""
    if "scope" not in mapped.columns:
        mapped = mapped.assign(scope=IN_HOUSE)
    group = mapped[(mapped["canonical_sku"] == key[0])
                   & (mapped["canonical_warehouse"] == key[1])
                   & (mapped["uom"].fillna("<unknown>") == key[2])
                   & (mapped["stage"] == stage)
                   & (mapped["scope"].fillna("").replace("", IN_HOUSE) == IN_HOUSE)]
    sos = sorted({str(s) for s in group["so"].dropna()})
    wos = sorted({str(r) for r in group["source_record"].dropna()
                  if str(r).startswith("WO")})
    return ";".join(sos[:5]), ";".join(wos[:5])


def apply_actions(pack: pd.DataFrame, stages: pd.DataFrame) -> pd.DataFrame:
    """新增动作列（G1/G3）；不改原 ``recommendation``。"""
    out = pack.copy()
    key = ["canonical_sku", "canonical_warehouse", "canonical_uom"]
    agg = aggregate_stages(stages) if len(stages) else pd.DataFrame()
    sku_in_prod_totals = {}
    if len(agg):
        sku_in_prod_totals = (agg.groupby(["canonical_sku", "uom"])["so_stage_in_production"]
                              .sum().to_dict())
        agg = agg.rename(columns={"uom": "canonical_uom"})
        out = out.merge(agg, on=key, how="left")
    for column in list(STAGE_FIELDS.values()) + list(FBA_FIELDS.values()):
        if column not in out.columns:
            out[column] = 0.0
        out[column] = pd.to_numeric(out[column], errors="coerce").fillna(0.0)
    for column in ("wo_completed_count", "wo_in_process_count", "wo_not_started_count",
                   "so_stage_so_count", "w1_stage_rows", "so_stage_unknown_missing_start",
                   "so_stage_unknown_other"):
        if column not in out.columns:
            out[column] = 0
        out[column] = pd.to_numeric(out[column], errors="coerce").fillna(0).astype(int)
    if "w1_confidence" not in out.columns:
        out["w1_confidence"] = None
    if "conditional_supply_qty" not in out.columns:
        out["conditional_supply_qty"] = None
    out["conditional_supply_qty"] = [
        max(_num(p), _num(i)) for p, i in zip(out.get("po_qty", pd.Series([0] * len(out))),
                                              out.get("intransit_qty", pd.Series([0] * len(out))))]

    actions, bases, confidences, action_qty, residual, dedup = [], [], [], [], [], []
    sources_so, sources_wo, timely, defer = [], [], [], []
    for row in out.to_dict("records"):
        gap = _num(row.get("protect_gap"))
        produced = _num(row.get("so_stage_produced_pending_dn"))
        in_prod = _num(row.get("so_stage_in_production"))
        produced_missing_start = _num(row.get("so_stage_unknown_missing_start"))
        produce_qty = in_prod + produced_missing_start
        transit = _num(row.get("so_stage_in_transit"))
        not_planned = _num(row.get("so_stage_not_planned"))
        unknown_other = _num(row.get("so_stage_unknown_other"))
        conditional = _num(row.get("conditional_supply_qty"))
        piece_key = (row["canonical_sku"], row["canonical_warehouse"], row["canonical_uom"])

        pieces = []
        if row["so_stage_so_count"]:
            pieces.append(f"{row['so_stage_so_count']} 张 SO")
        if produced:
            pieces.append(f"完工待发运 {produced:g}")
        if produce_qty:
            label = f"在产 {in_prod:g}" if in_prod else "工单已覆盖但缺开工证据"
            if produced_missing_start and in_prod:
                label += f" + 缺开工证据 {produced_missing_start:g}"
            pieces.append(label)
        if transit:
            pieces.append(f"在途 {transit:g}（阶段事实，非海外可用）")
        if not_planned:
            pieces.append(f"未排产 {not_planned:g}")
        if unknown_other:
            pieces.append(f"阶段待核实 {unknown_other:g}（unknown，不得解读为没生产）")
        if conditional:
            pieces.append(f"在途/PO 条件量 {conditional:g}（无 ETA）")
        fba_total = sum(_num(row.get(c)) for c in FBA_FIELDS.values())
        if fba_total:
            pieces.append(f"FBA 单列 {fba_total:g}（不计自发货仓）")
        other_branch_in_prod = (sku_in_prod_totals.get(
            (row["canonical_sku"], row["canonical_uom"]), 0.0) - in_prod)
        if other_branch_in_prod > 0:
            pieces.append(f"别仓在产 {other_branch_in_prod:g}（未计入）")
        if row["w1_confidence"] == "estimated":
            pieces.append("量来自首工序/推断，非可发运证明")

        candidates = [
            (ACTION_SHIP, produced, "so_stage_produced_pending_dn"),
            (ACTION_PRODUCE, produce_qty, "so_stage_unknown_missing_start" if produced_missing_start
             and not in_prod else "so_stage_in_production"),
            (ACTION_VERIFY_ARRIVAL, transit, "so_stage_in_transit"),
            (ACTION_WORK_ORDER, not_planned, "so_stage_not_planned"),
            (ACTION_VERIFY_PROGRESS, unknown_other, "so_stage_unknown_other"),
            (ACTION_VERIFY_ETA, conditional, "conditional_supply_qty"),
        ]
        available = [(name, qty, col) for name, qty, col in candidates if qty > 0]

        if gap <= 0:
            action, covered, chosen_col = ACTION_NO_NEED, 0.0, None
        elif not available:
            action, covered, chosen_col = ACTION_BUY, 0.0, None
        else:
            full = [c for c in available if c[1] >= gap]
            name, qty, chosen_col = full[0] if full else available[0]
            covered = min(qty, gap)
            action = name
            if covered < gap:
                action = name + SUFFIX_BUY_REST
                pieces.append(f"该阶段 {qty:g} 覆盖不足缺口 {gap:g}，剩余 {gap - qty:g} 需补单")

        residual_value = max(0.0, gap - covered)
        # 时效：没有需要日/ETA 时只能算“可能覆盖”
        timely_flag = "timely_coverage_unproven" if (covered > 0 and chosen_col) else ""
        if timely_flag:
            pieces.append("timely_coverage_unproven（无需要日/ETA，不能声称及时）")

        if row["w1_stage_rows"] == 0:
            confidence = "unknown"
        elif action in (ACTION_VERIFY_PROGRESS,) or (
                chosen_col in ("so_stage_unknown_other",) and row["w1_confidence"] == "unknown"):
            confidence = "unknown"
        elif row["w1_confidence"] == "estimated":
            confidence = "estimated"
        elif row["w1_confidence"] == "measured":
            confidence = "measured"
        else:
            confidence = "estimated"

        source_so, source_wo = ("", "")
        if chosen_col and len(stages):
            source_so, source_wo = _source_evidence(stages, piece_key, chosen_col)

        suggestion = ""
        if gap <= 0:
            opening = _num(row.get("opening"))
            proven = _num(row.get("proven_receipts"))
            demand = _num(row.get("period_demand"))
            # 只在有实际需求、且(期初+已证到货)达到 2 倍需求且至少 10 件时才提示，
            # 避免慢销/微小分母刷出几百条噪声
            if demand >= 1 and (opening + proven) >= max(2 * demand, 10):
                suggestion = ("考虑推迟/减量（期初+已证到货远超本期需求；"
                              "需求口径未含未履约 SO，需人工确认）")

        actions.append(action)
        action_qty.append(round(covered, 6))
        residual.append(round(residual_value, 6))
        bases.append("；".join(pieces) if pieces else "无 W1 阶段行，也无在途/PO 条件量")
        confidences.append(confidence)
        dedup.append("dedup_unproven" if (transit > 0 and conditional > 0) else "")
        timely.append(timely_flag)
        defer.append(suggestion)
        sources_so.append(source_so)
        sources_wo.append(source_wo)

    out["action"] = actions
    out["action_qty"] = action_qty
    out["residual_gap"] = residual
    out["action_basis"] = bases
    out["action_confidence"] = confidences
    out["action_source_so"] = sources_so
    out["action_source_wo"] = sources_wo
    out["timely_coverage_flag"] = timely
    out["cancel_or_defer_suggestion"] = defer
    out["transit_dedup_status"] = dedup
    out["action_note"] = ("action 是运营动作，优先于 recommendation；shipped_in_transit 只用于决定动作，"
                          "不进可用供给；action_qty 只是可能覆盖量，不代表及时")
    return out
