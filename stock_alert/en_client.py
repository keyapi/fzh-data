# -*- coding: utf-8 -*-
"""从 EN（ERPNext）读通途库存快照 `Tongtool Stock Latest`。

EN 每天把通途 14 仓库存拉到 MariaDB 的 `Tongtool Stock Latest`（字段与通途一致），
09:23 的低库存告警直接读它即可：**不占通途 5 次/分钟额度、不受 MCP 524 影响**。

⚠️ 必须先做**新鲜度门禁**：若当天 `job=stock_snapshot` 的最近一次运行不是
`Success`/`complete=1`，或 `snapshot_at` 不是今天，则视为同步未完成 —— 不能拿旧快照
按“可用<5”统计，否则会把同步失败误报成“全部断货”。

认证：`Authorization: token <ERP_API_KEY>:<ERP_API_SECRET>`（环境变量，勿写死）。
"""

from __future__ import annotations

import datetime as _dt
import json
import urllib.parse
import urllib.request

from .client import StockRow, _to_num

DEFAULT_BASE = "https://erpnext.vilavi.cn"
_FIELDS = [
    "warehouse", "sku", "available", "intransit",
    "waiting_shipment", "defects", "snapshot_at", "run_id",
]


def _j(obj) -> str:
    """JSON 参数用原始中文（与已验证的 REST probe 一致）。"""
    return json.dumps(obj, ensure_ascii=False)


class StockSyncIncomplete(Exception):
    """EN 库存快照不是今天/最近一次同步失败 —— 不应生成低库存明细。"""


class EnStockClient:
    def __init__(self, base_url: str, api_key: str, api_secret: str, *, timeout: int = 30):
        self.base_url = base_url.rstrip("/")
        self.api_key = api_key
        self.api_secret = api_secret
        self.timeout = timeout

    def _get(self, path: str, params: dict | None = None) -> dict:
        url = self.base_url + urllib.parse.quote(path)
        if params:
            url += "?" + urllib.parse.urlencode(params)
        req = urllib.request.Request(
            url,
            headers={
                "Authorization": f"token {self.api_key}:{self.api_secret}",
                "Accept": "application/json",
            },
        )
        with urllib.request.urlopen(req, timeout=self.timeout) as resp:
            return json.loads(resp.read().decode("utf-8"))

    def check_freshness(self, today: _dt.date | None = None) -> tuple[bool, str]:
        """返回 (是否新鲜, 说明)。不新鲜时说明里带原因。"""
        today = today or _dt.date.today()

        runs = self._get("/api/resource/Tongtool Stock Run", {
            "fields": _j(["name", "status", "complete", "snapshot_at", "creation"]),
            "filters": _j([["job", "=", "stock_snapshot"]]),
            "order_by": "creation desc",
            "limit_page_length": "1",
        })
        run = (runs.get("data") or [None])[0]
        if not run:
            return False, "Tongtool Stock Run 没有 stock_snapshot 记录"
        if run.get("status") != "Success" or str(run.get("complete")) not in ("1", "True", "true"):
            return False, (
                f"最近一次 stock_snapshot 未成功：status={run.get('status')} "
                f"complete={run.get('complete')}（{run.get('creation')}）"
            )
        snap = str(run.get("snapshot_at") or "")
        if not snap.startswith(today.isoformat()):
            return False, f"最近成功快照 snapshot_at={snap}，不是今天（{today.isoformat()}）"

        latest = self._get("/api/resource/Tongtool Stock Latest", {
            "fields": _j(["snapshot_at"]),
            "order_by": "snapshot_at desc",
            "limit_page_length": "1",
        })
        row = (latest.get("data") or [None])[0]
        max_snap = str((row or {}).get("snapshot_at") or "")
        if not max_snap.startswith(today.isoformat()):
            return False, f"Tongtool Stock Latest 最新 snapshot_at={max_snap or '空'}，不是今天"
        return True, f"快照 {snap}（run {run.get('name')}）"

    def list_stocks(self, warehouse: str, *, page_size: int = 1000, max_pages: int = 20) -> list[StockRow]:
        rows: list[StockRow] = []
        start = 0
        for _ in range(max_pages):
            data = self._get("/api/resource/Tongtool Stock Latest", {
                "fields": _j(_FIELDS),
                "filters": _j([["warehouse", "=", warehouse]]),
                "limit_start": str(start),
                "limit_page_length": str(page_size),
            })
            items = data.get("data") or []
            rows.extend(self._to_row(it) for it in items)
            if len(items) < page_size:
                break
            start += page_size
        return rows

    @staticmethod
    def _to_row(item: dict) -> StockRow:
        return StockRow(
            warehouse=str(item.get("warehouse") or ""),
            sku=str(item.get("sku") or "").strip(),
            available=_to_num(item.get("available")),
            intransit=_to_num(item.get("intransit")),
            defects=_to_num(item.get("defects")),
            waiting=_to_num(item.get("waiting_shipment")),
            raw=item,
        )
