# -*- coding: utf-8 -*-
"""通途 ERP2 库存查询客户端 —— `erp2_stocks_stocksquery`。

按仓库分页拉取整仓 SKU 库存。**商户级限流 5 次/分钟**（多 App 共享，MCP 也绕不过），
所以这里用 `min_interval` 节流，遇业务码 526 指数退避重试。

实测（2026-10-13，测试凭证）：
* 入参 `warehouseName`（必填）+ `pageNo`/`pageSize`；`skus` 可选（传了就按 SKU 查）。
  **只给 warehouseName 即可整仓列举全量**，无需逐个 SKU。
* `pageSize` 服务端**上限 100**（传 500 仍返回 100）。
* 响应 `datas.array` 是行列表，**不含 total 字段** —— 翻页靠「本页 < pageSize 即末页」判断。
* 行字段：`goodsSku` / `availableStockQuantity` / `intransitStockQuantity` /
  `defectsStockQuantity` / `waitingShipmentStockQuantity`（另有 `sync*` 变体，未用）。

`rows_and_total` / `normalize_row` 仍对容器名与字段名做容错，便于换源。
探测：`python -m stock_alert.cli probe --warehouse 美中-FZH-DANEEY`
"""

from __future__ import annotations

import json
import re
import sys
import time
from dataclasses import dataclass, field
from pathlib import Path

_REPO_ROOT = Path(__file__).resolve().parents[1]
if str(_REPO_ROOT) not in sys.path:
    sys.path.insert(0, str(_REPO_ROOT))

from tongtool_api.mcp_http import McpClient, primary_credentials  # noqa: E402

STOCK_QUERY_TOOL = "erp2_stocks_stocksquery"

CODE_OK = 200
CODE_RATE_LIMIT = 526

# 行列表可能出现的容器键（按优先级）
_ROW_KEYS = ("list", "array", "records", "dataList", "data", "items", "rows", "stocks")


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


def extract_payload(resp: dict) -> dict:
    """从 MCP tools/call 响应中取出业务 payload（dict）。"""
    if "error" in resp:
        raise RuntimeError(f"MCP error: {resp['error']}")
    texts = [
        c.get("text", "")
        for c in resp.get("result", {}).get("content", [])
        if c.get("type") == "text"
    ]
    raw = "\n".join(texts).strip()
    if not raw:
        return {}
    if raw[0] in "{[":
        parsed = json.loads(raw)
        return parsed if isinstance(parsed, dict) else {"datas": parsed}
    return {"text": raw}


def business_code(payload: dict):
    """取通途业务码（200 成功 / 526 超频 / 524 无权限 / 525 参数错）。"""
    if not isinstance(payload, dict):
        return None
    for key in ("code", "businessCode", "statusCode"):
        if key in payload:
            try:
                return int(payload[key])
            except (TypeError, ValueError):
                return None
    return None


def rows_and_total(payload: dict) -> tuple[list, int]:
    """在 payload 中定位库存行列表与总数（容错多种容器名）。"""
    if not isinstance(payload, dict):
        return [], 0
    datas = payload.get("datas")
    if isinstance(datas, list):
        return datas, len(datas)
    if isinstance(datas, dict):
        for key in _ROW_KEYS:
            value = datas.get(key)
            if isinstance(value, list):
                total = datas.get("total") or datas.get("totalCount") or datas.get("count") or len(value)
                try:
                    total = int(total)
                except (TypeError, ValueError):
                    total = len(value)
                return value, total
    for key in _ROW_KEYS:
        value = payload.get(key)
        if isinstance(value, list):
            return value, len(value)
    return [], 0


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


def is_transient_error(exc: Exception) -> bool:
    """可重试的瞬时错误：网关 5xx / 网络错误（不含 4xx、参数错等确定性失败）。"""
    if isinstance(exc, RuntimeError):
        match = re.search(r"MCP HTTP (\d{3})", str(exc))
        return bool(match and match.group(1).startswith("5"))
    return isinstance(exc, OSError)


class TongtoolStockClient:
    """节流 + 退避的通途库存客户端。"""

    def __init__(self, mcp=None, *, min_interval: float = 13.0, max_retries: int = 3, sleep=time.sleep):
        if mcp is None:
            key, secret = primary_credentials()
            mcp = McpClient(key, secret, client_name="fzh-stock-alert")
        self.mcp = mcp
        self.min_interval = min_interval
        self.max_retries = max_retries
        self._sleep = sleep
        self._last_call = 0.0

    def _throttle(self) -> None:
        wait = self.min_interval - (time.monotonic() - self._last_call)
        if wait > 0:
            self._sleep(wait)
        self._last_call = time.monotonic()

    def _call(self, arguments: dict) -> dict:
        self._throttle()
        return extract_payload(self.mcp.call(STOCK_QUERY_TOOL, arguments))

    def _call_with_retry(self, arguments: dict) -> dict:
        """对**瞬时错误**（网关 5xx / 网络）与**业务码 526** 做指数退避重试。

        4xx 等确定性错误不重试，直接抛。2026-10-19 那次 `MCP HTTP 502`（openresty
        网关抖动）就是没重试才整跑失败。
        """
        delay = 60.0
        last_reason = ""
        for attempt in range(self.max_retries + 1):
            try:
                payload = self._call(arguments)
            except Exception as exc:  # noqa: BLE001 - 只对瞬时错误重试
                if not is_transient_error(exc):
                    raise
                last_reason = f"{type(exc).__name__}: {str(exc)[:120]}"
            else:
                if business_code(payload) != CODE_RATE_LIMIT:
                    return payload
                last_reason = "业务码 526（超频）"
            if attempt >= self.max_retries:
                break
            self._sleep(delay)
            delay = min(delay * 2, 300)
        raise RuntimeError(f"通途 MCP 调用重试 {self.max_retries} 次仍失败：{last_reason}")

    def list_stocks(self, warehouse: str, *, page_size: int = 100, max_pages: int = 200) -> list[StockRow]:
        """按仓库分页拉全量库存行。

        实测（2026-10-13）响应 `datas.array` **不含 total 字段**，所以翻页靠
        「本页返回行数 < page_size 即到末页」判断，不依赖 total。
        """
        rows: list[StockRow] = []
        page = 1
        while page <= max_pages:
            payload = self._call_with_retry(
                {"warehouseName": warehouse, "pageNo": page, "pageSize": page_size}
            )
            code = business_code(payload)
            if code not in (None, CODE_OK):
                raise RuntimeError(f"通途 stocksquery 业务码 {code}：{json.dumps(payload, ensure_ascii=False)[:300]}")
            items, _total = rows_and_total(payload)
            rows.extend(normalize_row(warehouse, it) for it in items)
            if len(items) < page_size:
                break
            page += 1
        return rows


def get_tool_schema(name: str = STOCK_QUERY_TOOL, mcp=None) -> dict:
    """拉取某个工具的 MCP schema（tools/list），用于确认入参名与分页能力。"""
    if mcp is None:
        key, secret = primary_credentials()
        mcp = McpClient(key, secret, client_name="fzh-stock-probe")
    resp = mcp.list_tools()
    tools = resp.get("result", {}).get("tools", []) if isinstance(resp, dict) else []
    for tool in tools:
        if tool.get("name") == name:
            return tool
    return {"name": name, "found": False, "available": sorted(t.get("name", "") for t in tools)}
