# -*- coding: utf-8 -*-
"""采购入库汇总：EN `get_stock_change` 的 `voucher_type=02`（采购单）。

按仓、按 SKU 汇总 `available_increase`（当日所有采购入库凭证相加），
只汇总 available_increase > 0 的事件（排除创建/无变化及负增量），按数量降序。
"""

from __future__ import annotations

import datetime as _dt
import math
from dataclasses import dataclass, field

PURCHASE_VOUCHER = "02"


@dataclass
class InboundSku:
    sku: str
    qty: float
    name: str = ""


@dataclass
class InboundWarehouse:
    warehouse: str
    items: list[InboundSku] = field(default_factory=list)

    @property
    def count(self) -> int:
        return len(self.items)

    @property
    def total_qty(self) -> float:
        return sum(item.qty for item in self.items)


@dataclass
class InboundResult:
    day: _dt.date
    warehouses: list[InboundWarehouse]
    input_rows: int = 0
    accepted_rows: int = 0
    skipped: dict[str, int] = field(default_factory=dict)

    @property
    def total_skus(self) -> int:
        return sum(w.count for w in self.warehouses)

    @property
    def total_qty(self) -> float:
        return sum(w.total_qty for w in self.warehouses)


def aggregate(
    rows_by_warehouse: dict[str, list[dict]],
    *,
    names: dict[str, str] | None = None,
    day: _dt.date | None = None,
) -> InboundResult:
    """库存变动行 → 各仓采购入库汇总。"""
    names = names or {}
    summaries: list[InboundWarehouse] = []
    input_rows = accepted_rows = 0
    skipped: dict[str, int] = {}
    def skip(reason: str) -> None:
        skipped[reason] = skipped.get(reason, 0) + 1

    for warehouse, rows in rows_by_warehouse.items():
        totals: dict[str, float] = {}
        for row in rows or []:
            input_rows += 1
            if not {"sku", "voucher_type", "available_increase"} <= row.keys():
                raise ValueError(f"{warehouse}: 采购事件缺少必需字段")
            if str(row.get("voucher_type")) != PURCHASE_VOUCHER:
                skip("non_purchase")
                continue
            sku = str(row.get("sku") or "").strip()
            if not sku:
                skip("empty_sku")
                continue
            try:
                qty = float(row["available_increase"])
            except (TypeError, ValueError) as exc:
                raise ValueError(f"{warehouse}/{sku}: 非法 available_increase") from exc
            if not math.isfinite(qty):
                raise ValueError(f"{warehouse}/{sku}: 非有限 available_increase")
            if qty <= 0:
                skip("zero_change" if qty == 0 else "negative_change")
                continue
            accepted_rows += 1
            totals[sku] = totals.get(sku, 0.0) + qty
        items = [
            InboundSku(sku=sku, qty=qty, name=names.get(sku, ""))
            for sku, qty in totals.items()
            if qty > 0
        ]
        items.sort(key=lambda item: (-item.qty, item.sku))
        summaries.append(InboundWarehouse(warehouse=warehouse, items=items))
    return InboundResult(day=day or _dt.date.today(), warehouses=summaries,
                         input_rows=input_rows, accepted_rows=accepted_rows, skipped=skipped)
