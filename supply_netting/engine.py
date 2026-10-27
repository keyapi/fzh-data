# -*- coding: utf-8 -*-
"""供给净额引擎：需求净额 × 库存/供应事实，按可售日期分桶。

本模块只做「分桶净额」这一件事：
- 需求只接受 ``demand_netting.parquet`` 的四列唯一行（调用方先按 series 取值）；
- 供应只接受已过 Jack ``SupplyRow`` 校验与 overlap gates 的行；
- 分桶交由 ``supply_chain_visibility.receipt_buckets.bucket_receipts``（原样引入）；
- 逐桶账数学复用 ``bucket_gaps`` / ``assert_bucket_identities``（原样引入）。

不做预测、不做采购决策、不写生产。
"""

from __future__ import annotations

from dataclasses import dataclass
from datetime import date, datetime, time, timedelta
from decimal import Decimal
from typing import Iterable, Sequence

from supply_chain_visibility.receipt_buckets import bucket_receipts
from supply_chain_visibility.overlap_gates import apply_overlap_gates
from supply_chain_visibility.supply_row import SupplyRow

from .legacy_ledger import allocate_so, assert_bucket_identities, bucket_gaps

SCENARIOS = ("conservative", "expected")

# 供应侧「保留情景」的原因：这些数量不进已证到货，但必须留痕，不能写成 0。
CONDITIONAL_REASONS = frozenset({
    "date_unproven", "eligibility_unproven", "allocation_unproven",
    "quantity_unproven", "identity_unproven", "pre_asof_inclusion_unproven",
    "outside_buckets",
})
# gates 已判定「这条输入根本不是可计供应事件」：两种情景都只留证据。
PRE_DISPOSED = {
    "unmapped": "warehouse_unmapped",
    "trace_only": "trace_only",
    "evidence_only": "evidence_only",
    "not_collected": "not_collected",
    "qty_unknown": "quantity_unproven",
    "uom_unproven": "uom_unproven",
    "source_unproven": "source_unproven",
    "duplicate_unproven": "duplicate_unproven",
}
# overlap gates 已判定的重复/冲突：两种情景都只计一次。
ALWAYS_DEDUPED = frozenset({"proven_batch_replay", "batch_quantity_conflict"})
# gates 只对保守情景排除 PO 一侧（B_max 情景保留两侧）。
CONSERVATIVE_ONLY_EXCLUSIONS = frozenset({"po_not_counted"})


@dataclass(frozen=True)
class Bucket:
    bucket_id: str
    start: datetime
    end: datetime


def build_buckets(as_of: datetime, protect_days: int = 7, weeks: int = 4) -> tuple[Bucket, ...]:
    """保护期 + N 个周桶，左闭右开、不重叠、起点等于库存基准时点。"""
    if as_of.tzinfo is None or as_of.utcoffset() is None:
        raise ValueError("as_of 必须带时区")
    if protect_days < 1:
        raise ValueError("protect_days 至少为 1 天")
    if weeks < 0:
        raise ValueError("weeks 不能为负")
    buckets = [Bucket("protect", as_of, as_of + timedelta(days=protect_days))]
    cursor = buckets[0].end
    for index in range(1, weeks + 1):
        nxt = cursor + timedelta(days=7)
        buckets.append(Bucket(f"w{index}", cursor, nxt))
        cursor = nxt
    return tuple(buckets)


def day_instant(value, tzinfo) -> datetime | None:
    """把日级/日时时间统一成带时区的瞬间。

    日级数据按「基准时区的当日 00:00」放置——这是本层显式记录的适配规则
    （manifest 的 ``date_adapter_rule``），不是 ``bucket_receipts`` 偷偷补午夜。
    """
    if value is None:
        return None
    if isinstance(value, datetime):
        parsed = value
    elif isinstance(value, date):
        return datetime.combine(value, time(0, 0), tzinfo=tzinfo)
    elif isinstance(value, str):
        text = value.strip()
        if not text:
            return None
        try:
            parsed = datetime.fromisoformat(text.replace("Z", "+00:00"))
        except ValueError:
            try:
                return datetime.combine(date.fromisoformat(text[:10]), time(0, 0), tzinfo=tzinfo)
            except ValueError:
                return None
    else:
        return None
    if parsed.tzinfo is None or parsed.utcoffset() is None:
        return parsed.replace(tzinfo=tzinfo)
    return parsed


def _dec(value) -> Decimal | None:
    if value is None:
        return None
    if isinstance(value, Decimal):
        return value
    return Decimal(str(value))


def _as_bucket_list(buckets: Sequence[Bucket]):
    return [(b.bucket_id, b.start, b.end) for b in buckets]


def _assign_demand(demand_rows: Iterable[dict], buckets: Sequence[Bucket],
                   as_of: datetime) -> dict:
    """逐条需求给一个去向：某个桶 / 基准前 / 视界后 / 日期未证（落最早桶）。"""
    totals = {b.bucket_id: Decimal(0) for b in buckets}
    dispositions: list[dict] = []
    hidden_qty = Decimal(0)
    for row in demand_rows:
        qty = _dec(row.get("quantity")) or Decimal(0)
        row_id = row.get("demand_row_id")
        instant = day_instant(row.get("demand_date"), as_of.tzinfo)
        if instant is None:
            # 日期未知的未履约量：不丢、不写 0，落最早桶并标条件。
            totals[buckets[0].bucket_id] += qty
            dispositions.append(dict(demand_row_id=row_id, quantity=qty, bucket_id=buckets[0].bucket_id,
                                     reason="demand_date_unproven_earliest"))
            continue
        if instant < as_of:
            hidden_qty += qty
            dispositions.append(dict(demand_row_id=row_id, quantity=qty, bucket_id=None,
                                     reason="before_as_of"))
            continue
        bucket = next((b for b in buckets if b.start <= instant < b.end), None)
        if bucket is None:
            hidden_qty += qty
            dispositions.append(dict(demand_row_id=row_id, quantity=qty, bucket_id=None,
                                     reason="after_horizon"))
            continue
        totals[bucket.bucket_id] += qty
        dispositions.append(dict(demand_row_id=row_id, quantity=qty, bucket_id=bucket.bucket_id,
                                 reason="bucketed"))
    return dict(totals=totals, dispositions=dispositions, hidden_qty=hidden_qty)


def _allocation_status(row: SupplyRow, scenario: str) -> str:
    if row.scope == "external_fba":
        return "fba"
    if row.scope != "in_house":
        return "unknown"
    if row.not_collected or row.warehouse_confidence != "confirmed" or row.identity_confidence != "proven":
        return "unknown"
    eligible = row.b_min_eligible if scenario == "conservative" else row.b_max_eligible
    return "free" if eligible else "unknown"


def _event(row: SupplyRow, scenario: str, index: int) -> dict:
    source = row.source_key or row.document_key or row.batch_key or "row"
    return dict(
        event_id=f"{row.source_layer}:{source}:{index}",
        sku=row.sku, warehouse=row.warehouse, uom=row.uom,
        qty=None if row.qty is None else str(row.qty),
        available_at=row.available_date,
        date_confidence=row.date_confidence,
        b_min_eligible=True if scenario == "expected" else row.b_min_eligible,
        scope=row.scope,
        allocation_status=_allocation_status(row, scenario),
        source_layer=row.source_layer,
        batch_key=row.batch_key,
        batch_proven=row.batch_proven,
    )


def _fact(row: SupplyRow, *, reason: str, bucket_id: str | None = None) -> dict:
    return dict(
        source_layer=row.source_layer, stage=row.stage, qty=row.qty,
        available_date=row.available_date, date_confidence=row.date_confidence,
        scope=row.scope, identity_confidence=row.identity_confidence,
        warehouse_confidence=row.warehouse_confidence,
        b_min_eligible=row.b_min_eligible, b_max_eligible=row.b_max_eligible,
        batch_key=row.batch_key, batch_proven=row.batch_proven,
        document_key=row.document_key, source_key=row.source_key,
        exclusion_reason=row.exclusion_reason, disposition_reason=reason,
        bucket_id=bucket_id, counted=reason == "counted",
        conditional=reason in CONDITIONAL_REASONS,
    )


def _run_scenario(name: str, rows: Sequence[SupplyRow], *, as_of: datetime,
                  buckets: Sequence[Bucket]) -> dict:
    events, pres, owner = [], [], {}
    for index, row in enumerate(rows):
        if not row.b_max_eligible and row.exclusion_reason in PRE_DISPOSED:
            pres.append(_fact(row, reason=PRE_DISPOSED[row.exclusion_reason]))
            continue
        if row.exclusion_reason in ALWAYS_DEDUPED:
            pres.append(_fact(row, reason="same_batch_counted_once"))
            continue
        if row.exclusion_reason in CONSERVATIVE_ONLY_EXCLUSIONS and name == "conservative":
            pres.append(_fact(row, reason="same_batch_counted_once"))
            continue
        event = _event(row, name, index)
        events.append(event)
        owner[event["event_id"]] = row
    result = bucket_receipts(events, target=(rows[0].sku, rows[0].warehouse, rows[0].uom),
                             as_of=as_of, buckets=_as_bucket_list(buckets))
    facts = list(pres)
    for disposition in result["dispositions"]:
        row = owner[disposition["event_id"]]
        reason = disposition["reason"]
        item = _fact(row, reason=reason, bucket_id=disposition["bucket"])
        item.update(event_id=disposition["event_id"], qty=_dec(disposition["qty"]),
                    counted=bool(disposition["bucket"]))
        facts.append(item)
    return dict(receipts=result["receipts"], facts=facts,
                has_unresolved=result["has_unresolved"],
                counts=result["counts"], ledger=result["quantity_ledger"],
                input_rows=result["input_rows"], counted_rows=result["counted_rows"],
                excluded_rows=result["excluded_rows"])


def _to_decimal(value) -> Decimal:
    return Decimal(str(round(float(value), 6)))


def net_target(*, sku: str, warehouse: str, uom: str, as_of: datetime,
               buckets: Sequence[Bucket], demand_rows: Iterable[dict],
               supply_rows: Sequence[SupplyRow], backlog_qty: Decimal = Decimal("0"),
               so_mode: str = "earliest", supply_sources_complete: bool = False) -> dict:
    """对单个 ``sku × 仓 × 单位`` 做逐桶净额。仓与单位是硬边界，跨仓不抵消。"""
    key = (sku, warehouse, uom)
    rows = apply_overlap_gates([r for r in supply_rows if (r.sku, r.warehouse, r.uom) == key])
    demand = _assign_demand(demand_rows, buckets, as_of)
    demand_b = [demand["totals"][b.bucket_id] for b in buckets]

    if backlog_qty > 0:
        allocated = allocate_so(float(backlog_qty), [float(x) for x in demand_b], mode=so_mode)
        for index, value in enumerate(allocated):
            demand_b[index] += _to_decimal(value)
        backlog_flag = "allocated"
    else:
        backlog_flag = "none"

    opening_rows = [r for r in rows if r.source_layer == "inventory_snapshot"]
    if not opening_rows:
        opening, opening_reason = None, "no_snapshot_basis"
    elif any(r.qty is None for r in opening_rows):
        opening, opening_reason = None, "opening_qty_unproven"
    else:
        opening = sum((r.qty for r in opening_rows), Decimal(0))
        opening_reason = "snapshot"

    future_rows = [r for r in rows if r.source_layer != "inventory_snapshot"]
    has_future_evidence = bool(future_rows)
    scenarios = {name: _run_scenario(name, future_rows, as_of=as_of, buckets=buckets)
                 for name in SCENARIOS} if future_rows else {
        name: dict(receipts={b.bucket_id: Decimal(0) for b in buckets}, facts=[],
                   has_unresolved=False, counts={}, ledger={}, input_rows=0,
                   counted_rows=0, excluded_rows=0)
        for name in SCENARIOS
    }

    out_rows = []
    for name in SCENARIOS:
        scenario = scenarios[name]
        if opening is None:
            out_rows.extend(_unknown_rows(key, buckets, name, opening_reason))
            continue
        claims = [dict(name=b.bucket_id,
                       opening=float(opening) if index == 0 else None,
                       receipts=float(scenario["receipts"][b.bucket_id]),
                       demand=float(demand_b[index]))
                  for index, b in enumerate(buckets)]
        ledger = bucket_gaps(claims)
        conditional_qty = sum((f["qty"] or Decimal(0) for f in scenario["facts"] if f["conditional"]),
                              Decimal(0))
        for row in ledger:
            assert_bucket_identities(row)
            out_rows.append(dict(
                scenario=name, bucket_id=row["name"],
                opening=_to_decimal(row["opening"]), receipts=_to_decimal(row["receipts"]),
                demand=_to_decimal(row["demand"]), fulfilled=_to_decimal(row["fulfilled"]),
                closing=_to_decimal(row["closing"]), unserved=_to_decimal(row["unserved"]),
                gap=_to_decimal(row["gap"]),
                conditional_receipts=conditional_qty,
                has_unresolved=bool(scenario["has_unresolved"]),
                supply_evidence=has_future_evidence, status=(
                    "conditional" if (scenario["has_unresolved"] or conditional_qty > 0
                                      or not supply_sources_complete
                                      or not has_future_evidence) else "valued"),
            ))

    return dict(key=key, opening=opening, opening_reason=opening_reason,
                opening_facts=[_fact(r, reason="opening_basis") for r in opening_rows],
                demand_buckets=demand_b, demand_dispositions=demand["dispositions"],
                demand_hidden_qty=demand["hidden_qty"], backlog=backlog_flag,
                scenarios=scenarios, rows=out_rows)


def _unknown_rows(key, buckets: Sequence[Bucket], scenario: str, reason: str) -> list[dict]:
    return [dict(scenario=scenario, bucket_id=b.bucket_id, opening=None, receipts=None,
                 demand=None, fulfilled=None, closing=None, unserved=None, gap=None,
                 conditional_receipts=None, has_unresolved=True, supply_evidence=False,
                 status="unknown", unknown_reason=reason)
            for b in buckets]


def _has_horizon_demand(rows: Iterable[dict], as_of: datetime) -> bool:
    for row in rows:
        instant = day_instant(row.get("demand_date"), as_of.tzinfo)
        if instant is None or instant >= as_of:   # 日期未知的未履约量同样落桶
            return True
    return False


def net_all(*, demand_rows: Sequence[dict], supply_rows: Sequence[SupplyRow],
            as_of: datetime, buckets: Sequence[Bucket],
            backlog: dict | None = None, so_mode: str = "earliest",
            supply_sources_complete: bool = False) -> dict:
    """对需求侧出现的每个 ``sku × 仓 × 单位`` 建一条逐桶净额。"""
    grouped: dict[tuple, list[dict]] = {}
    for row in demand_rows:
        key = (row["canonical_sku"], row["canonical_warehouse"], row["canonical_uom"])
        grouped.setdefault(key, []).append(row)

    by_key: dict[tuple, list[SupplyRow]] = {}
    for row in supply_rows:
        by_key.setdefault((row.sku, row.warehouse, row.uom), []).append(row)

    backlog = backlog or {}
    for key, quantity in backlog.items():
        if quantity and key not in grouped:
            grouped[key] = []    # 只有未履约余额、没有需求行的键同样要建账
    results = []
    for key in sorted(grouped):
        sku, warehouse, uom = key
        if not _has_horizon_demand(grouped[key], as_of) and not backlog.get(key):
            continue    # 视界内没有需求、也没有未履约余额的键不产出净额行
        results.append(net_target(
            sku=sku, warehouse=warehouse, uom=uom, as_of=as_of, buckets=buckets,
            demand_rows=grouped[key], supply_rows=by_key.get(key, ()),
            backlog_qty=_dec(backlog.get(key, 0)) or Decimal(0), so_mode=so_mode,
            supply_sources_complete=supply_sources_complete,
        ))
    return dict(targets=results, demand_keys=len(grouped))
