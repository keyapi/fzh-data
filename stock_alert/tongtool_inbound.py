# -*- coding: utf-8 -*-
"""直连通途 OpenAPI 查询采购入库（库存变动明细）。

EN 的 `stock_change.parquet` 每天约 05:53 才同步一次，不能支撑白天 10/14/17 点的
实时查询。本模块直接调用：

    POST /openapi/tongtool/stocksChangeDetailQuery

参数：`warehouseName`、`updatedDateFrom`（YYYY-MM-DD HH:MM:SS）、`pageNo`、`pageSize`。
返回行里 `relatedVoucherType == "02"` 为采购单，`availableStockIncrease > 0` 为正向入库。
归一化成与 `inbound.aggregate` 相同的字段（sku / voucher_type / available_increase）。
"""

from __future__ import annotations

import datetime as _dt

from .client import _to_num

ENDPOINT = "/openapi/tongtool/stocksChangeDetailQuery"
PURCHASE_VOUCHER = "02"
PAGE_SIZE = 100
MAX_PAGES = 200


def _rows(payload: dict) -> list[dict]:
    datas = payload.get("datas")
    if isinstance(datas, list):
        return datas
    if isinstance(datas, dict):
        for key in ("array", "list", "records", "dataList", "items", "rows", "stocks"):
            value = datas.get(key)
            if isinstance(value, list):
                return value
    return []


def _normalize(row: dict, warehouse: str) -> dict:
    return {
        "operate_time": row.get("operateTime"),
        "warehouse_name": warehouse,
        "sku": row.get("goodsSku"),
        "voucher_type": row.get("relatedVoucherType"),
        "voucher_type_name": row.get("relatedVoucherTypeName"),
        "voucher_number": row.get("relatedVoucherNumber"),
        "operator": row.get("operaterUserName"),
        "available_increase": _to_num(row.get("availableStockIncrease")),
    }


def fetch_changes(api, warehouse: str, since: _dt.datetime, *, page_size: int = PAGE_SIZE,
                  max_pages: int = MAX_PAGES) -> list[dict]:
    """按 updatedDateFrom 拉取某仓库存变动，自动翻页。"""
    page_size = max(1, min(int(page_size or PAGE_SIZE), 100))
    since_text = since.strftime("%Y-%m-%d %H:%M:%S")
    out: list[dict] = []
    for page in range(1, max_pages + 1):
        payload = api.request(ENDPOINT, {
            "warehouseName": warehouse,
            "updatedDateFrom": since_text,
            "pageNo": page,
            "pageSize": page_size,
        })
        batch = _rows(payload)
        out.extend(_normalize(row, warehouse) for row in batch)
        if len(batch) < page_size:
            return out
    raise RuntimeError(f"{warehouse}: 通途库存变动达到分页上限，拒绝使用不完整数据")


def filter_purchase(rows: list[dict], since: _dt.datetime,
                    until: _dt.datetime | None = None) -> list[dict]:
    """只保留窗口内、采购单（02）、正向 available_increase 的事件。"""
    out: list[dict] = []
    for row in rows or []:
        if str(row.get("voucher_type")) != PURCHASE_VOUCHER:
            continue
        qty = _to_num(row.get("available_increase"))
        if qty <= 0:
            continue
        text = str(row.get("operate_time") or "").strip()[:19]
        try:
            when = _dt.datetime.strptime(text, "%Y-%m-%d %H:%M:%S")
        except ValueError:
            continue
        if when < since or (until is not None and when > until):
            continue
        row = dict(row)
        row["available_increase"] = qty
        out.append(row)
    return out


def collect_inbound(warehouses: list[str], since: _dt.datetime,
                    until: _dt.datetime | None = None, *,
                    min_interval: float = 13.0, page_size: int = PAGE_SIZE,
                    api=None) -> dict[str, list[dict]]:
    """逐仓拉取并过滤；rate limit 由 TongtoolOpenApiClient 统一节流。"""
    if api is None:
        from tongtool_api.mcp_http import primary_credentials
        from tongtool_api.openapi_client import TongtoolOpenApiClient

        api = TongtoolOpenApiClient(*primary_credentials(), min_interval=min_interval,
                                    max_retries=2)
    out: dict[str, list[dict]] = {}
    for warehouse in warehouses:
        rows = fetch_changes(api, warehouse, since, page_size=page_size)
        out[warehouse] = filter_purchase(rows, since, until)
    return out
