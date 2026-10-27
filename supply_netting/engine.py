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

from .facts import STAGE_PRECEDENCE
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
    """逐条需求给一个去向：某个桶 / 基准前 / 视界后 / 日期未证（落最早桶）。

    ``demand_source`` 区分「已发生订单（demand_netting）」与「刷新预测」，两者不混算。
    """
    totals = {b.bucket_id: Decimal(0) for b in buckets}
    by_source = {b.bucket_id: {} for b in buckets}
    dispositions: list[dict] = []
    hidden_qty = Decimal(0)

    def add(bucket_id, quantity, source):
        totals[bucket_id] += quantity
        bucket_map = by_source[bucket_id]
        bucket_map[source] = bucket_map.get(source, Decimal(0)) + quantity

    for row in demand_rows:
        qty = _dec(row.get("quantity")) or Decimal(0)
        row_id = row.get("demand_row_id")
        source = row.get("demand_source") or "demand_netting"
        instant = day_instant(row.get("demand_date"), as_of.tzinfo)
        if instant is None:
            # 日期未知的未履约量：不丢、不写 0，落最早桶并标条件。
            add(buckets[0].bucket_id, qty, source)
            dispositions.append(dict(demand_row_id=row_id, quantity=qty,
                                     bucket_id=buckets[0].bucket_id, demand_source=source,
                                     reason="demand_date_unproven_earliest"))
            continue
        if instant < as_of:
            hidden_qty += qty
            dispositions.append(dict(demand_row_id=row_id, quantity=qty, bucket_id=None,
                                     demand_source=source, reason="before_as_of"))
            continue
        bucket = next((b for b in buckets if b.start <= instant < b.end), None)
        if bucket is None:
            hidden_qty += qty
            dispositions.append(dict(demand_row_id=row_id, quantity=qty, bucket_id=None,
                                     demand_source=source, reason="after_horizon"))
            continue
        add(bucket.bucket_id, qty, source)
        dispositions.append(dict(demand_row_id=row_id, quantity=qty, bucket_id=bucket.bucket_id,
                                 demand_source=source, reason="bucketed"))
    return dict(totals=totals, by_source=by_source, dispositions=dispositions,
                hidden_qty=hidden_qty)


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


def _run_scenario(name: str, rows: Sequence[SupplyRow], *, target: tuple,
                  as_of: datetime, buckets: Sequence[Bucket],
                  extra_pres: Sequence[tuple[SupplyRow, str]] = ()) -> dict:
    events, pres, owner = [], [], {}
    for row, reason in extra_pres:
        pres.append(_fact(row, reason=reason))
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
    result = bucket_receipts(events, target=target, as_of=as_of,
                             buckets=_as_bucket_list(buckets))
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


# F1：期初可用资格。gate 已把「不能计」的原因写好，这里必须照着用，不能只看 source_layer。
_OPENING_DEFINITIVE_EXCLUSIONS = frozenset({
    "external_fba", "exact_replay", "source_identity_conflict", "source_grain_conflict",
    "proven_batch_replay",
})


def _opening_eligible(row: SupplyRow) -> bool:
    if row.source_layer != "inventory_snapshot":
        return False
    if row.scope == "external_fba":
        return False
    if row.exclusion_reason in _OPENING_DEFINITIVE_EXCLUSIONS:
        return False
    # 结构性的整行排除（身份/单位/仓/重复/批次冲突）由 gate 关掉 b_max 表示；
    # 只收紧 b_min 的原因（如来源时点未证）不影响期初基准本身。
    return bool(row.b_max_eligible)


def opening_basis(rows: Sequence[SupplyRow]) -> dict:
    """把库存行拆成「计入 / 明确排除 / 可能属于基准但未证」。

    R2：只要还有「可能属于基准但数量/身份未证」的行，精确期初就是未知——
    不能返回已知小计并让读者把它当成完整期初。此时给出 ``lower_bound``（已知下界），
    ``opening=None``。
    """
    included = [row for row in rows if _opening_eligible(row)]
    excluded = [row for row in rows if not _opening_eligible(row)]
    unproven = [row for row in excluded
                if row.qty is None or row.exclusion_reason not in _OPENING_DEFINITIVE_EXCLUSIONS]
    definitive = [row for row in excluded if row not in unproven]
    known = (sum((row.qty for row in included), Decimal(0))
             if included and all(row.qty is not None for row in included) else Decimal(0))

    if unproven:
        return dict(opening=None, reason="opening_partially_unproven",
                    lower_bound=known if included else Decimal(0),
                    included=included, excluded=excluded, unproven=unproven)
    if included:
        if any(row.qty is None for row in included):
            return dict(opening=None, reason="opening_qty_unproven", lower_bound=None,
                        included=included, excluded=excluded, unproven=[])
        total = sum((row.qty for row in included), Decimal(0))
        return dict(opening=total, reason="snapshot", lower_bound=total,
                    included=included, excluded=excluded, unproven=[])
    if definitive:
        return dict(opening=Decimal(0), reason="all_opening_excluded", lower_bound=Decimal(0),
                    included=[], excluded=excluded, unproven=[])
    return dict(opening=None, reason="no_snapshot_basis", lower_bound=None,
                included=[], excluded=[], unproven=[])


def _dedupe_exact(rows: Sequence[SupplyRow]) -> tuple[list[SupplyRow], list[SupplyRow]]:
    """完全相同的供应行只留一条；重复输入失败关闭，不靠改 event_id 变成两条。"""
    seen: set[tuple] = set()
    kept, dropped = [], []
    for row in rows:
        signature = (row.source_layer, row.source_key, row.stage, row.qty, row.available_date)
        if row.source_key and signature in seen:
            dropped.append(row)
            continue
        seen.add(signature)
        kept.append(row)
    return kept, dropped


def _quota_key(row: SupplyRow) -> str:
    """额度身份：合法拆分子额度各有自己的身份；其余用批次键本身。

    R1：拆分谱系来自 ``facts.split_balance``，经 Tranche 写进 ``document_key``。
    同一父余额的 6+4 是两个额度，必须各自计数；只有同一额度的跨阶段观察才去重。
    """
    document = row.document_key or ""
    prefix = "split-quota:"
    if document.startswith(prefix):
        return document[len(prefix):]
    return row.batch_key or ""


def apply_batch_quota(rows: Sequence[SupplyRow]) -> tuple[list[SupplyRow], list[tuple[SupplyRow, str]], list[tuple]]:
    """同批跨阶段只计一次（按额度身份）。

    只对「已证批次」生效：同一 ``(sku, 仓, 单位, batch_key, 额度)`` 出现在多个阶段时，
    保留最靠后可售的阶段，其余留证；同阶段同额度重复也只留一条。
    合法拆分的不同子额度是不同额度，全部保留数量与日期。
    数量不一致记为 ``batch_quantity_conflict``，绝不把两侧相加。
    """
    groups: dict[tuple, list[SupplyRow]] = {}
    for row in rows:
        if row.batch_proven and row.batch_key:
            groups.setdefault((row.sku, row.warehouse, row.uom, row.batch_key,
                               _quota_key(row)), []).append(row)
    excluded: dict[int, tuple[SupplyRow, str]] = {}
    for group in groups.values():
        if len(group) < 2:
            continue
        best = max(group, key=lambda row: (STAGE_PRECEDENCE.get(row.stage, 0), row.qty or 0))
        conflict = any(row.qty != best.qty for row in group if row is not best)
        reason = "batch_quantity_conflict" if conflict else "same_batch_counted_once"
        for row in group:
            if row is best:
                continue
            excluded[id(row)] = (row, reason)

    # 同一批次同时出现「合法拆分」与「整批观察」：谱系无法证明是否同一实物，
    # 按额度各自保留，但必须把冲突显式报出来，便于人工核实。
    kinds: dict[tuple, set] = {}
    for key in groups:
        kinds.setdefault(key[:4], set()).add("split" if key[4] != key[3] else "whole")
    split_conflicts = [batch for batch, seen in kinds.items() if len(seen) > 1]
    kept = [row for row in rows if id(row) not in excluded]
    return kept, list(excluded.values()), split_conflicts


def net_target(*, sku: str, warehouse: str, uom: str, as_of: datetime,
               buckets: Sequence[Bucket], demand_rows: Iterable[dict],
               supply_rows: Sequence[SupplyRow], backlog_qty: Decimal = Decimal("0"),
               so_mode: str = "earliest", supply_sources_complete: bool = False) -> dict:
    """对单个 ``sku × 仓 × 单位`` 做逐桶净额。仓与单位是硬边界，跨仓不抵消。"""
    key = (sku, warehouse, uom)
    gated = apply_overlap_gates([r for r in supply_rows if (r.sku, r.warehouse, r.uom) == key])
    deduped, duplicated = _dedupe_exact(gated)
    demand = _assign_demand(demand_rows, buckets, as_of)
    demand_b = [demand["totals"][b.bucket_id] for b in buckets]

    if backlog_qty > 0:
        allocated = allocate_so(float(backlog_qty), [float(x) for x in demand_b], mode=so_mode)
        for index, value in enumerate(allocated):
            demand_b[index] += _to_decimal(value)
        backlog_flag = "allocated"
    else:
        backlog_flag = "none"

    opening_rows = [r for r in deduped if r.source_layer == "inventory_snapshot"]
    basis = opening_basis(opening_rows)
    opening, opening_reason = basis["opening"], basis["reason"]
    opening_lower_bound = basis.get("lower_bound")

    future_rows = [r for r in deduped if r.source_layer != "inventory_snapshot"]
    future_rows, quota_excluded, split_conflicts = apply_batch_quota(future_rows)
    extra_pres = [(row, "duplicate_supply_row") for row in duplicated] + quota_excluded
    has_future_evidence = bool(future_rows) or bool(extra_pres)
    scenarios = {name: _run_scenario(name, future_rows, target=key, as_of=as_of,
                                     buckets=buckets, extra_pres=extra_pres)
                 for name in SCENARIOS} if (future_rows or extra_pres) else {
        name: dict(receipts={b.bucket_id: Decimal(0) for b in buckets}, facts=[],
                   has_unresolved=False, counts={}, ledger={}, input_rows=0,
                   counted_rows=0, excluded_rows=0)
        for name in SCENARIOS
    }

    out_rows = []
    for name in SCENARIOS:
        scenario = scenarios[name]
        if opening is None:
            out_rows.extend(_unknown_rows(key, buckets, name, opening_reason,
                                          opening_lower_bound))
            continue
        claims = [dict(name=b.bucket_id,
                       opening=float(opening) if index == 0 else None,
                       receipts=float(scenario["receipts"][b.bucket_id]),
                       demand=float(demand_b[index]))
                  for index, b in enumerate(buckets)]
        ledger = bucket_gaps(claims)
        conditional_qty = sum((f["qty"] or Decimal(0) for f in scenario["facts"] if f["conditional"]),
                              Decimal(0))
        for index, row in enumerate(ledger):
            assert_bucket_identities(row)
            carried = _to_decimal(row["demand"]) - _to_decimal(demand_b[index])
            out_rows.append(dict(
                scenario=name, bucket_id=row["name"],
                opening=_to_decimal(row["opening"]), receipts=_to_decimal(row["receipts"]),
                # demand/gap 为「含跨桶结转」口径：等于本桶需求 + 上桶未满足。
                # 逐桶求和会重复计数，请用 period_demand / carried_unserved。
                demand=_to_decimal(row["demand"]), fulfilled=_to_decimal(row["fulfilled"]),
                closing=_to_decimal(row["closing"]), unserved=_to_decimal(row["unserved"]),
                gap=_to_decimal(row["gap"]),
                period_demand=_to_decimal(demand_b[index]),
                carried_unserved=carried,
                forecast_demand=_to_decimal(demand["by_source"][buckets[index].bucket_id].get("forecast", Decimal(0))),
                historical_demand=_to_decimal(
                    demand["by_source"][buckets[index].bucket_id].get("demand_netting", Decimal(0))),
                conditional_receipts=conditional_qty,
                opening_lower_bound=opening_lower_bound,
                has_unresolved=bool(scenario["has_unresolved"]),
                supply_evidence=has_future_evidence, status=(
                    "conditional" if (scenario["has_unresolved"] or conditional_qty > 0
                                      or not supply_sources_complete
                                      or not has_future_evidence) else "valued"),
            ))

    opening_facts = ([_fact(r, reason="opening_basis") for r in basis["included"]]
                     + [_fact(r, reason=f"opening_excluded:{r.exclusion_reason or 'unproven'}")
                        for r in basis["excluded"]])
    return dict(key=key, opening=opening, opening_reason=opening_reason,
                opening_lower_bound=opening_lower_bound,
                opening_unproven=len(basis.get("unproven", [])),
                batch_split_conflicts=len(split_conflicts),
                opening_facts=opening_facts,
                opening_included=len(basis["included"]),
                opening_excluded=len(basis["excluded"]),
                demand_buckets=demand_b, demand_sources=demand["by_source"],
                demand_dispositions=demand["dispositions"],
                demand_hidden_qty=demand["hidden_qty"], backlog=backlog_flag,
                scenarios=scenarios, rows=out_rows)


def _unknown_rows(key, buckets: Sequence[Bucket], scenario: str, reason: str,
                  lower_bound=None) -> list[dict]:
    return [dict(scenario=scenario, bucket_id=b.bucket_id, opening=None, receipts=None,
                 demand=None, fulfilled=None, closing=None, unserved=None, gap=None,
                 conditional_receipts=None, opening_lower_bound=lower_bound,
                 has_unresolved=True, supply_evidence=False,
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
