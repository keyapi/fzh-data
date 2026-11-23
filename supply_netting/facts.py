# -*- coding: utf-8 -*-
"""三类供应事实中的 A/B/C 最小可运行结构。

- A ``stage_balances``：订单执行数量归属，阶段互斥；累计完工/累计出库不再相加成新供应。
- B ``milestones``：原计划 / 当前预计 / 实际，三者分列，保留观测时间。
- C ``availability_schedule``：分批「可售数量 × 日期」tranche；是同一份额度的未来表示，
  不是第二份供应；已含期初库存的不得再补入。

本模块只做结构与校验：不计算补货量、不预测、不改订单状态。
"""

from __future__ import annotations

from dataclasses import asdict, dataclass, fields, replace
from datetime import datetime
from decimal import Decimal

STAGES = (
    "unreleased", "in_production", "finished_waiting_shipment", "shipped_in_transit",
    "arrived_waiting_receipt", "completed_sellable_delivery",
    "cancelled", "loss", "unattributed",
)
SUPPLY_STAGES = ("in_production", "finished_waiting_shipment",
                 "shipped_in_transit", "arrived_waiting_receipt")
TERMINAL_STAGES = ("completed_sellable_delivery", "cancelled", "loss")
STAGE_SOURCE_LAYER = {
    "in_production": "work_order",
    "finished_waiting_shipment": "work_order",
    "shipped_in_transit": "in_transit",
    # F4：到仓待上架若已有「已证、未含期初」的未来可售日，它是可售 tranche，
    # 不是原始收货证据；原始收货事件仍走 receipt_event 且不计（gate 的 evidence_only）。
    "arrived_waiting_receipt": "in_transit",
}
STAGE_PRECEDENCE = {           # 同一批次跨阶段时「更靠后＝更接近可售」
    "in_production": 1,
    "finished_waiting_shipment": 2,
    "shipped_in_transit": 3,
    "arrived_waiting_receipt": 4,
}
DATE_CONFIDENCES = ("confirmed", "estimated", "unknown")


@dataclass(frozen=True)
class StageBalance:
    """一条互斥的阶段余额。``order_qty`` 只用于对账，不参与供给计算。"""

    balance_id: str
    order_key: str
    sku: str
    warehouse: str
    uom: str
    stage: str
    qty: Decimal | None
    qty_status: str = "known"
    order_qty: Decimal | None = None
    allocation_status: str = "unknown"      # free / fba / unknown
    included_in_opening: bool = False
    sellable_at: str | None = None
    date_confidence: str = "unknown"
    planned_at: str | None = None
    expected_at: str | None = None
    actual_at: str | None = None
    observed_at: str | None = None
    source: str = "unknown"
    source_key: str | None = None
    # F2：证明状态必须随行传递；默认「未证」，禁止在转换时抬升。
    warehouse_confidence: str = "unmapped"
    identity_confidence: str = "unproven"
    source_complete: bool = False
    # F3：稳定批次身份（已证才可以跨阶段判重）
    batch_key: str | None = None
    batch_proven: bool = False
    # 合法拆分：split_of 指向原余额；没有它就不允许同阶段重复出现
    split_of: str | None = None
    # 拆分总量（父余额数量），用于校验子额度合计，不参与供给计算
    split_total: Decimal | None = None


class DuplicateBalanceError(ValueError):
    """同一 balance_id 出现两次：结构性错误，失败关闭。"""


@dataclass(frozen=True)
class Tranche:
    tranche_id: str
    balance_id: str
    stage: str
    sku: str
    warehouse: str
    uom: str
    qty: Decimal | None
    available_at: str | None
    date_confidence: str
    allocation_status: str
    scenario: str
    included_in_opening: bool
    exclusion_reason: str = ""
    identity_confidence: str = "unproven"
    warehouse_confidence: str = "unmapped"
    source_complete: bool = False
    batch_key: str | None = None
    batch_proven: bool = False
    # R1：拆分谱系必须传到计数侧，否则合法子额度会被跨阶段去重误删
    split_of: str | None = None


def _aware(value) -> bool:
    if not isinstance(value, str) or not value.strip():
        return False
    try:
        parsed = datetime.fromisoformat(value.replace("Z", "+00:00"))
    except ValueError:
        return False
    return parsed.tzinfo is not None and parsed.utcoffset() is not None


def validate_stage_balances(balances, order_totals: dict | None = None) -> list[str]:
    errors = []
    grouped: dict[tuple, list[StageBalance]] = {}
    for row in balances:
        label = row.balance_id or "<no id>"
        if row.stage not in STAGES:
            errors.append(f"{label}: 未知阶段 {row.stage}")
        if row.date_confidence not in DATE_CONFIDENCES:
            errors.append(f"{label}: 非法 date_confidence {row.date_confidence}")
        if row.qty is None and row.qty_status != "unknown":
            errors.append(f"{label}: qty=null 必须 qty_status=unknown")
        if row.qty is not None and (not row.qty.is_finite() or row.qty < 0):
            errors.append(f"{label}: qty 必须是非负有限数")
        if row.qty is not None and row.qty_status == "unknown":
            errors.append(f"{label}: qty_status=unknown 时 qty 必须为 null")
        if row.batch_proven and not (row.batch_key and str(row.batch_key).strip()):
            errors.append(f"{label}: batch_proven 需要非空 batch_key")
        if row.sellable_at and not _aware(row.sellable_at):
            errors.append(f"{label}: sellable_at 必须带时区")
        grouped.setdefault((row.order_key, row.sku, row.warehouse, row.uom, row.stage), []).append(row)

    for rows in grouped.values():
        if len(rows) < 2:
            continue
        parents = {row.split_of for row in rows}
        totals = {row.split_total for row in rows}
        # 只有「同一父余额的显式拆分」才合法；其余重复一律失败关闭。
        if len(parents) != 1 or None in parents:
            labels = ", ".join(row.balance_id for row in rows)
            errors.append(f"同订单/物料/仓/单位阶段重复且不是同一父余额拆分：{labels}")
            continue
        # R1：合法拆分的子额度合计必须等于父余额数量（split_total）。
        if len(totals) != 1 or None in totals:
            errors.append(f"拆分 {rows[0].split_of} 的父余额（split_total）声明不一致")
            continue
        children_total = sum((row.qty or Decimal(0)) for row in rows)
        if children_total != next(iter(totals)):
            errors.append(f"拆分 {rows[0].split_of} 子额度合计 {children_total} "
                          f"≠ 父余额 {next(iter(totals))}")
    for row in balances:
        if order_totals is None or row.order_qty is None:
            continue
        expected = order_totals.get(row.order_key, row.order_qty)
        if row.order_qty != expected:
            errors.append(f"{row.balance_id}: order_qty 与订单总额不一致")
    return errors


def summarize_stage_balances(balances, order_totals: dict | None = None) -> list[dict]:
    """按订单×物料×单位对账：阶段合计 vs 净订单量；差额单列，不塞进任何阶段。

    单位是硬边界：同一订单的「件」和「套」不合并（无换算证明不得相加）。
    """
    groups: dict[tuple, list[StageBalance]] = {}
    for row in balances:
        groups.setdefault((row.order_key, row.sku, row.uom), []).append(row)
    out = []
    for (order_key, sku, uom), rows in groups.items():
        by_stage: dict[str, float] = {}
        for row in rows:
            if row.qty is not None:
                by_stage[row.stage] = by_stage.get(row.stage, 0.0) + float(row.qty)
        total = sum(by_stage.values())
        declared = order_totals.get(order_key) if order_totals else next(
            (r.order_qty for r in rows if r.order_qty is not None), None)
        delta = None if declared is None else float(declared) - total
        out.append(dict(
            order_key=order_key, sku=sku, uom=uom,
            total=round(total, 6), declared=None if declared is None else float(declared),
            delta=None if delta is None else round(delta, 6),
            by_stage=by_stage,
            terminal_qty=round(sum(by_stage.get(s, 0.0) for s in TERMINAL_STAGES), 6),
            supply_qty=round(sum(by_stage.get(s, 0.0) for s in SUPPLY_STAGES), 6),
            balanced=None if delta is None else abs(delta) <= 1e-9,
        ))
    return out


def split_balance(balance: StageBalance, splits) -> list[StageBalance]:
    """把一条阶段余额拆成分批可售 tranche；拆分必须精确等于原数量。"""
    if balance.qty is None:
        raise ValueError("数量未证不能拆分")
    total = sum(Decimal(str(qty)) for _, qty, _ in splits)
    if total != balance.qty:
        raise ValueError(f"拆分合计 {total} ≠ 原余额 {balance.qty}，拒绝凑数")
    out = []
    for index, (label, qty, available_at) in enumerate(splits, start=1):
        out.append(replace(balance, balance_id=f"{balance.balance_id}#{label}{index}",
                           qty=Decimal(str(qty)), sellable_at=available_at,
                           date_confidence="confirmed" if _aware(available_at) else "unknown",
                           split_of=balance.split_of or balance.balance_id,
                           split_total=balance.qty))
    return out


def build_availability_schedule(balances) -> list[Tranche]:
    """阶段余额 → 可售 tranche。每条余额必须全部落在「计入」或「排除」之一。"""
    tranches: list[Tranche] = []
    ledger: dict[str, dict] = {}
    seen: set[str] = set()
    for row in balances:
        if row.balance_id in seen:
            raise DuplicateBalanceError(
                f"重复的阶段余额 {row.balance_id}：重复输入必须失败关闭，不得靠改 event_id 绕过")
        seen.add(row.balance_id)
        account = ledger.setdefault(row.balance_id, dict(input_known=Decimal(0),
                                                         scheduled=Decimal(0), excluded=Decimal(0)))
        if row.qty is not None:
            account["input_known"] += row.qty
        reason = _exclusion(row)
        tranche = Tranche(
            tranche_id=f"{row.balance_id}@{row.stage}",
            balance_id=row.balance_id, stage=row.stage, sku=row.sku, warehouse=row.warehouse, uom=row.uom,
            qty=row.qty,
            available_at=row.sellable_at or (row.actual_at if _aware(row.actual_at)
                                             else row.expected_at),
            date_confidence=row.date_confidence,
            allocation_status=row.allocation_status,
            scenario="conditional" if (reason or row.date_confidence != "confirmed") else "base",
            included_in_opening=row.included_in_opening,
            exclusion_reason=reason,
            identity_confidence=row.identity_confidence,
            warehouse_confidence=row.warehouse_confidence,
            source_complete=row.source_complete,
            batch_key=row.batch_key,
            batch_proven=row.batch_proven,
            split_of=row.split_of,
        )
        tranches.append(tranche)
        if row.qty is not None:
            account["excluded" if reason else "scheduled"] += row.qty
    for balance_id, account in ledger.items():
        assert account["input_known"] == account["scheduled"] + account["excluded"], \
            f"{balance_id}: tranche 数量账不平"
    return tranches


def _exclusion(row: StageBalance) -> str:
    if row.qty is None:
        return "quantity_unproven"
    if row.stage == "unreleased":
        return "not_released"
    if row.stage == "completed_sellable_delivery":
        return "already_delivered"
    if row.stage == "cancelled":
        return "order_cancelled"
    if row.stage == "loss":
        return "loss"
    if row.stage == "unattributed":
        return "unattributed"
    if row.included_in_opening:
        return "included_in_opening"
    if row.allocation_status == "fba":
        return "fba_allocated"
    if row.allocation_status != "free":
        return "allocation_unproven"
    return ""


def tranches_to_supply_rows(tranches):
    """可售 tranche → Jack ``SupplyRow``，供 ``bucket_receipts`` 分桶。"""
    from supply_chain_visibility.supply_row import SupplyRow

    rows, evidence = [], []
    for tranche in tranches:
        if tranche.exclusion_reason:
            evidence.append(dict(
                event_id=tranche.tranche_id, source_layer=STAGE_SOURCE_LAYER.get(tranche.stage, "in_transit"),
                stage=tranche.stage, sku=tranche.sku, warehouse=tranche.warehouse, uom=tranche.uom,
                qty=tranche.qty, available_date=tranche.available_at,
                date_confidence=tranche.date_confidence, scope="in_house",
                identity_confidence=None, warehouse_confidence=None,
                b_min_eligible=False, b_max_eligible=False, batch_key=None, batch_proven=False,
                document_key=None, source_key=tranche.balance_id,
                exclusion_reason=tranche.exclusion_reason,
                disposition_reason=tranche.exclusion_reason, bucket_id=None,
                counted=False, conditional=tranche.exclusion_reason not in (
                    "already_delivered", "order_cancelled", "loss", "fba_allocated",
                    "not_released", "unattributed"),
                scenario="any", raw_sku=None, raw_warehouse=None,
            ))
            continue
        rows.append(SupplyRow(
            sku=tranche.sku, warehouse=tranche.warehouse,
            stage=tranche.stage,
            source_layer=STAGE_SOURCE_LAYER.get(tranche.stage, "in_transit"),
            qty=tranche.qty, qty_status="known",
            uom=tranche.uom, uom_proven=True,
            event_date=None, available_date=tranche.available_at,
            date_confidence=tranche.date_confidence,
            timezone_status="verified" if _aware(tranche.available_at) else "unverified",
            # F2：原样传递，绝不在这里抬升成 proven/confirmed
            identity_confidence=tranche.identity_confidence,
            source_as_of=tranche.available_at if _aware(tranche.available_at) else None,
            scope="in_house", warehouse_confidence=tranche.warehouse_confidence, role="finished",
            b_min_eligible=False, b_max_eligible=True,
            source_key=tranche.tranche_id, source_complete=tranche.source_complete,
            batch_key=tranche.batch_key, batch_proven=tranche.batch_proven,
            # R1：拆分谱系写进 document_key，供计数侧区分「合法子额度」与「同额度重放」
            document_key=(f"split-quota:{tranche.balance_id}" if tranche.split_of else None),
        ))
    return rows, evidence


def stages_frame(balances) -> list[dict]:
    return [dict(asdict(row), qty=None if row.qty is None else float(row.qty),
                 order_qty=None if row.order_qty is None else float(row.order_qty))
            for row in balances]


def milestones_frame(balances) -> list[dict]:
    return [dict(balance_id=row.balance_id, order_key=row.order_key, stage=row.stage,
                 planned_at=row.planned_at, expected_at=row.expected_at, actual_at=row.actual_at,
                 observed_at=row.observed_at, source=row.source)
            for row in balances if any((row.planned_at, row.expected_at, row.actual_at))]


def tranches_frame(tranches) -> list[dict]:
    return [dict(asdict(row), qty=None if row.qty is None else float(row.qty))
            for row in tranches]


# F9：空表也必须带固定 schema，别让「没有记录」变成零列。
STAGE_FRAME_COLUMNS = [field.name for field in fields(StageBalance)]
TRANCHE_FRAME_COLUMNS = [field.name for field in fields(Tranche)]
MILESTONE_FRAME_COLUMNS = ["balance_id", "order_key", "stage", "planned_at", "expected_at",
                           "actual_at", "observed_at", "source"]
