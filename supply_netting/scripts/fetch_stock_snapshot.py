# -*- coding: utf-8 -*-
"""通途 ERP2 库存 API → en_stock 快照 parquet（只读拉取，不写生产）。

背景
- 项目里没有现成的 en_stock 构建脚本；历史快照（2026-10-26）的 `source=tongtool_api`，
  字段与本脚本输出一致，因此本轮按同一口径重建，保证与 10-26 可比。
- 数据源：MCP 工具 `erp2_stocks_stocksquery`（ERP2/Stocks 库存查询），只读。

字段映射（通途 → en_stock）
    goodsSku                    → sku
    warehouseName               → warehouse_name
    warehouseIdKey              → warehouse_id
    availableStockQuantity      → available
    intransitStockQuantity      → intransit
    waitingShipmentStockQuantity→ waiting_shipment
    defectsStockQuantity        → defects
    goodsAvgCost                → avg_cost
其余列（snapshot_date/snapshot_at/source/run_id/schema_version）由本脚本写入。

限流
- 通途同一商户所有 App 共享 5 次/分钟。脚本默认每次调用间隔 12.5 秒，
  遇 526（超频）等 65 秒后重试，最多 5 次。

不做的事
- 不写 `en_stock.parquet`（共享输入），只写新文件；
- 不做任何库存调整，不写通途。
"""

from __future__ import annotations

import argparse
import json
import sys
import time
from datetime import datetime, timezone
from pathlib import Path

import pandas as pd

ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT / "tongtool_api"))
import mcp_http  # noqa: E402

ENV_CANDIDATES = (
    ROOT / "tongtool_api" / ".env",
    Path("D:/Work/赛狐/Cursor/tongtool_api/.env"),
)
TOOL = "erp2_stocks_stocksquery"
PAGE_SIZE = 100                      # API 上限 100，传更大会被截断
MIN_INTERVAL = 12.5                  # 5 次/分钟
RATE_LIMIT_CODE = 526
SCHEMA_COLUMNS = ["snapshot_date", "snapshot_at", "warehouse_id", "warehouse_name", "sku",
                  "available", "intransit", "waiting_shipment", "defects", "avg_cost",
                  "source", "run_id", "schema_version"]

# 与 10-26 快照同集合的活跃仓；WayfairCG-* 不在通途，取不到（脚本会报缺失）
DEFAULT_WAREHOUSES = ("美东-CENTRADE", "美中-FZH-DANEEY", "波兰-FZHPoland-covers",
                      "多渠道仓库", "大件云仓", "星链海外仓", "美中-FZH-DANEEY-退货产品仓")


def load_credentials() -> tuple[str, str]:
    for path in ENV_CANDIDATES:
        env = mcp_http.load_env(path)
        key = env.get("TONGTOOL_ERP2_PRIMARY_KEY", "").strip()
        secret = env.get("TONGTOOL_ERP2_PRIMARY_SECRET", "").strip()
        if key and secret:
            return key, secret
    raise FileNotFoundError("找不到 TONGTOOL_ERP2_PRIMARY_KEY/SECRET（检查 tongtool_api/.env）")


class Pacer:
    """全局限流闸：保证相邻两次调用至少间隔 MIN_INTERVAL 秒。"""

    def __init__(self, interval: float = MIN_INTERVAL) -> None:
        self.interval = interval
        self.last = 0.0
        self.calls = 0

    def wait(self) -> None:
        gap = time.time() - self.last
        if gap < self.interval:
            time.sleep(self.interval - gap)
        self.last = time.time()
        self.calls += 1


def _payload(resp: dict) -> dict:
    content = (resp.get("result") or {}).get("content") or []
    if not content:
        raise RuntimeError(f"空响应：{str(resp)[:200]}")
    return json.loads(content[0].get("text", ""))


def fetch_warehouse(client, pacer: Pacer, warehouse: str, max_pages: int = 400) -> list[dict]:
    rows: list[dict] = []
    page = 1
    while page <= max_pages:
        for attempt in range(5):
            pacer.wait()
            payload = _payload(client.call(
                TOOL, {"warehouseName": warehouse, "pageNo": page, "pageSize": PAGE_SIZE}))
            if payload.get("code") == RATE_LIMIT_CODE:
                wait = 65 + attempt * 15
                print(f"  [rate-limit] {warehouse} p{page} 526，等 {wait}s", flush=True)
                time.sleep(wait)
                continue
            break
        code = payload.get("code")
        if code != 200:
            raise RuntimeError(f"{warehouse} p{page} 失败：code={code} {payload.get('message')}")
        batch = ((payload.get("datas") or {}).get("array")) or []
        rows.extend(batch)
        print(f"  {warehouse} p{page}: +{len(batch)} (累计 {len(rows)})", flush=True)
        if len(batch) < PAGE_SIZE:
            break
        page += 1
    return rows


def to_frame(raw: list[dict], snapshot_date: str, snapshot_at: datetime,
             run_id: str) -> pd.DataFrame:
    frame = pd.DataFrame([{
        "snapshot_date": snapshot_date,
        "snapshot_at": snapshot_at,
        "warehouse_id": r.get("warehouseIdKey"),
        "warehouse_name": r.get("warehouseName"),
        "sku": r.get("goodsSku"),
        "available": r.get("availableStockQuantity"),
        "intransit": r.get("intransitStockQuantity"),
        "waiting_shipment": r.get("waitingShipmentStockQuantity"),
        "defects": r.get("defectsStockQuantity"),
        "avg_cost": r.get("goodsAvgCost"),
    } for r in raw])
    if frame.empty:
        return pd.DataFrame(columns=SCHEMA_COLUMNS)
    for col in ("available", "intransit", "waiting_shipment", "defects", "avg_cost"):
        frame[col] = pd.to_numeric(frame[col], errors="coerce")
    frame["skus"] = frame["sku"].astype(str)
    frame = frame.drop(columns=["skus"])
    frame = frame[frame["sku"].notna()].copy()
    frame["source"] = "tongtool_api"
    frame["run_id"] = run_id
    frame["schema_version"] = 1
    return frame[SCHEMA_COLUMNS]


def main(argv=None) -> int:
    ap = argparse.ArgumentParser(description="通途库存 → en_stock 快照（只读）")
    ap.add_argument("--out", required=True)
    ap.add_argument("--warehouse", action="append", default=None,
                    help="可重复；缺省用与 10-26 同集合的活跃仓")
    ap.add_argument("--snapshot-date", default=datetime.now().strftime("%Y-%m-%d"))
    ap.add_argument("--list-warehouses", action="store_true", help="只列通途仓库，不拉库存")
    args = ap.parse_args(argv)

    key, secret = load_credentials()
    client = mcp_http.McpClient(key, secret)
    pacer = Pacer()

    if args.list_warehouses:
        pacer.wait()
        payload = _payload(client.call("erp2_basedata_warehousequery",
                                       {"pageNo": 1, "pageSize": 200}))
        for w in ((payload.get("datas") or {}).get("array") or []):
            print(f"{w.get('warehouseName'):34s} status={w.get('status')} "
                  f"id={w.get('warehouseId')}")
        return 0

    warehouses = tuple(args.warehouse) if args.warehouse else DEFAULT_WAREHOUSES
    snapshot_at = datetime.now(timezone.utc).astimezone().replace(microsecond=0)
    run_id = snapshot_at.strftime("%Y%m%dT%H%M%S")

    frames, errors = [], {}
    for wh in warehouses:
        print(f"[fetch] {wh}", flush=True)
        try:
            raw = fetch_warehouse(client, pacer, wh)
        except Exception as exc:                       # noqa: BLE001 - 记录后继续其它仓
            errors[wh] = f"{type(exc).__name__}: {exc}"
            print(f"  FAILED: {exc}", flush=True)
            continue
        frames.append(to_frame(raw, args.snapshot_date, snapshot_at, run_id))

    if not frames:
        print(json.dumps({"status": "failed", "errors": errors}, ensure_ascii=False, indent=1))
        return 2

    out = pd.concat(frames, ignore_index=True)
    out_path = Path(args.out)
    out_path.parent.mkdir(parents=True, exist_ok=True)
    out.to_parquet(out_path, index=False)

    summary = {
        "status": "ok" if not errors else "partial",
        "out": str(out_path),
        "snapshot_date": args.snapshot_date,
        "snapshot_at": snapshot_at.isoformat(),
        "run_id": run_id,
        "rows": int(len(out)),
        "warehouses": {k: int(v) for k, v in out.groupby("warehouse_name").size().items()},
        "available_sum": float(out["available"].fillna(0).sum()),
        "intransit_sum": float(out["intransit"].fillna(0).sum()),
        "errors": errors,
        "api_calls": pacer.calls,
    }
    print(json.dumps(summary, ensure_ascii=False, indent=1))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
