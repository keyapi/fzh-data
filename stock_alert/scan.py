# -*- coding: utf-8 -*-
"""低库存扫描：过滤「可用库存 < 阈值」，按仓聚合。

计入规则：**可用库存 < 阈值**，且**不是「可用=0 且 在途=0」的死库存**
（那种既没货也没在途，一般是历史/停用 SKU，过滤掉不统计）。

纯粹对已归一化的 StockRow 做记账，不碰网络，便于离线测试。
"""

from __future__ import annotations

from dataclasses import dataclass, field

from .client import StockRow

DEFAULT_WAREHOUSES: tuple[str, ...] = (
    "美中-FZH-DANEEY",
    "美东-CENTRADE",
    "波兰-FZHPoland-covers",
)
DEFAULT_THRESHOLD = 5


@dataclass
class LowSku:
    sku: str
    available: float
    intransit: float


@dataclass
class WarehouseSummary:
    warehouse: str
    low: list[LowSku] = field(default_factory=list)
    scanned: int = 0

    @property
    def count(self) -> int:
        """该仓可用库存 < 阈值的 SKU 数。"""
        return len(self.low)

    @property
    def intransit_total(self) -> float:
        """该仓低库存 SKU 的在途数量合计。"""
        return sum(s.intransit for s in self.low)


@dataclass
class ScanResult:
    threshold: float
    warehouses: list[WarehouseSummary]

    @property
    def total_low(self) -> int:
        return sum(w.count for w in self.warehouses)


def is_low_stock(row: StockRow, threshold: float) -> bool:
    """是否计入低库存。

    规则：可用库存 < 阈值，**且不是「可用=0 且 在途=0」的死库存**（过滤掉，不统计）。
    """
    if row.available >= threshold:
        return False
    if row.available == 0 and row.intransit == 0:
        return False
    return True


def scan(rows_by_warehouse: dict[str, list[StockRow]], *, threshold: float = DEFAULT_THRESHOLD) -> ScanResult:
    """按 warehouse 分组的库存行 → 各仓低库存汇总。"""
    summaries: list[WarehouseSummary] = []
    for warehouse, rows in rows_by_warehouse.items():
        summary = WarehouseSummary(warehouse=warehouse, scanned=len(rows))
        for row in rows:
            if is_low_stock(row, threshold):
                summary.low.append(LowSku(sku=row.sku, available=row.available, intransit=row.intransit))
        summary.low.sort(key=lambda s: (s.available, s.sku))
        summaries.append(summary)
    return ScanResult(threshold=threshold, warehouses=summaries)
