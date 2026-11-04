# -*- coding: utf-8 -*-
"""通途库存查询客户端（OpenAPI 直连）。

MCP 网关自 2026-11-03 起对该 app 返回 524（unknown 不在白名单），改用 OpenAPI：

  POST https://open.tongtool.com/api-service/openapi/tongtool/stocksQuery
    query: app_token / sign / timestamp
    body : {merchantId, warehouseName, pageNo, pageSize}

返回字段：goodsSku / availableStockQuantity / intransitStockQuantity /
         defectsStockQuantity / waitingShipmentStockQuantity / goodsAvgCost

认证、限流与 526 退避见 `tongtool_api/openapi_client.py`。
"""

from __future__ import annotations

import sys
from dataclasses import dataclass, field
from pathlib import Path

_REPO_ROOT = Path(__file__).resolve().parents[1]
if str(_REPO_ROOT) not in sys.path:
    sys.path.insert(0, str(_REPO_ROOT))

from tongtool_api.mcp_http import primary_credentials  # noqa: E402 - 仅复用 .env 读取
from tongtool_api.openapi_client import TongtoolOpenApiClient  # noqa: E402

# 行列表可能出现的容器键（OpenAPI 实测为 datas.array）
_ROW_KEYS = ("array", "list", "records", "dataList", "data", "items", "rows", "stocks")


@dataclass
class StockRow:
    """一行库存记录（已归一化）。"""

    warehouse: str
    sku: str
    available: float = 0.0
    intransit: float = 0.0
    defects: float = 0.0
    waiting: float = 0.0
    raw: dict = field(default_factory=dict)


def _to_num(value) -> float:
    if value is None or value == "":
        return 0.0
    try:
        return float(value)
    except (TypeError, ValueError):
        return 0.0


def rows_and_total(payload: dict) -> tuple[list, int | None]:
    """定位库存行列表与**显式** total（无 total 字段时返回 None，用于分页判断）。"""
    if not isinstance(payload, dict):
        return [], None
    datas = payload.get("datas")
    if isinstance(datas, list):
        return datas, None
    if isinstance(datas, dict):
        for key in _ROW_KEYS:
            value = datas.get(key)
            if isinstance(value, list):
                total = datas.get("total") or datas.get("totalCount") or datas.get("count")
                try:
                    total = int(total) if total is not None else None
                except (TypeError, ValueError):
                    total = None
                return value, total
    for key in _ROW_KEYS:
        value = payload.get(key)
        if isinstance(value, list):
            return value, None
    return [], None


def normalize_row(warehouse: str, item: dict) -> StockRow:
    item = item if isinstance(item, dict) else {}
    sku = str(
        item.get("goodsSku")
        or item.get("sku")
        or item.get("goodsNumber")
        or item.get("productSku")
        or ""
    ).strip()
    return StockRow(
        warehouse=warehouse,
        sku=sku,
        available=_to_num(item.get("availableStockQuantity")),
        intransit=_to_num(item.get("intransitStockQuantity")),
        defects=_to_num(item.get("defectsStockQuantity")),
        waiting=_to_num(item.get("waitingShipmentStockQuantity")),
        raw=item,
    )


class TongtoolStockClient:
    """库存查询封装（OpenAPI）。"""

    def __init__(self, api=None, *, min_interval: float = 13.0):
        if api is None:
            key, secret = primary_credentials()
            api = TongtoolOpenApiClient(key, secret, min_interval=min_interval)
        self.api = api

    def list_stocks(self, warehouse: str, *, page_size: int = 100, max_pages: int = 100) -> list[StockRow]:
        """按仓库分页拉全量库存行。

        OpenAPI 的 `datas.array` 未必带 total：优先用 total 判断；没有 total 时靠
        「本页不足 page_size 即末页」。
        """
        rows: list[StockRow] = []
        page = 1
        while page <= max_pages:
            payload = self.api.stocks(warehouse, page, page_size)
            items, total = rows_and_total(payload)
            rows.extend(normalize_row(warehouse, it) for it in items)
            if not items:
                break
            if total is not None and page * page_size >= total:
                break
            if len(items) < page_size:
                break
            page += 1
        return rows
