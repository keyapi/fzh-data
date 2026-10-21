# -*- coding: utf-8 -*-
"""通途库存快照（只读）

通过 ERP2 MCP 拉取「当前启用仓库」的库存，写入 DuckDB：
  warehouse_dim  (warehouse_name, status)
  tongtool_stock (warehouse_name, goods_sku, available, intransit, defects, waiting_shipment,
                  avg_cost, snapshot_at)

说明：
- 通途 API 只给**当前**库存，没有历史序列；需每日跑一次形成序列。
- 限流 5 次/分钟（全商户共享），这里强制 12 秒间隔。
- 只读，不写通途/EN。

用法：
  uv run python scripts/tongtool_stock_snapshot.py --out <order_store 目录>
"""
from __future__ import annotations

import argparse
import datetime as dt
import json
import os
import sys
import tempfile
import time
from pathlib import Path

import duckdb
import pandas as pd

REPO_ROOT = Path(__file__).resolve().parents[1]
ENV_FILE = Path("D:/Work/赛狐/Cursor/tongtool_api/.env")
PACE_SECONDS = 12


def load_env(path: Path) -> dict:
    vals = {}
    for raw in path.read_text(encoding="utf-8").splitlines():
        line = raw.strip()
        if line and not line.startswith("#") and "=" in line:
            k, v = line.split("=", 1)
            vals[k.strip()] = v.strip().strip('"').strip("'")
    return vals


def mcp_client():
    sys.path.insert(0, str(REPO_ROOT))
    from tongtool_api.mcp_http import McpClient
    env = load_env(ENV_FILE)
    return McpClient(env["TONGTOOL_ERP2_PRIMARY_KEY"], env["TONGTOOL_ERP2_PRIMARY_SECRET"])


def call(client, name, args, tries=6):
    last = None
    for i in range(tries):
        try:
            r = client.call(name, args)
            txt = r.get("result", {}).get("content", [{}])[0].get("text", "{}")
            try:
                return json.loads(txt)
            except Exception:
                return {"_raw": txt[:200]}
        except Exception as e:  # 502/超时等
            last = e
            time.sleep(20)
    raise RuntimeError(f"MCP call failed {name}: {str(last)[:120]}")


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--out", default="D:/Work/fzh-order-store")
    ap.add_argument("--max-warehouses", type=int, default=0, help="0=全部启用仓")
    ap.add_argument("--max-pages", type=int, default=60, help="每仓最多页数")
    ap.add_argument("--warehouses", default="", help="逗号分隔的仓库名；为空则取前 N 个启用仓")
    args = ap.parse_args()

    client = mcp_client()
    out_dir = Path(args.out)
    con = duckdb.connect(str(out_dir / "order_store.duckdb"))

    # 1) 仓库清单
    wh, page = [], 1
    while True:
        if page > 1:
            time.sleep(PACE_SECONDS)
        d = call(client, "erp2_basedata_warehousequery", {"pageNo": page, "pageSize": 100})
        arr = (d.get("datas") or {}).get("array") or []
        if not arr:
            break
        wh.extend(arr)
        if len(arr) < 100:
            break
        page += 1
    wdf = pd.DataFrame([{"warehouse_name": w.get("warehouseName"), "status": w.get("status")} for w in wh])
    active = [w["warehouse_name"] for w in wdf.to_dict("records") if str(w["status"]) == "1" and w.get("warehouse_name")]
    if args.warehouses:
        active = [w.strip() for w in args.warehouses.split(",") if w.strip()]
    elif args.max_warehouses:
        active = active[: args.max_warehouses]
    print(json.dumps({"warehouses_total": len(wdf), "active": len(active)}, ensure_ascii=False))

    # 2) 逐仓拉库存
    now = dt.datetime.now().strftime("%Y-%m-%d %H:%M:%S")
    rows = []
    for name in active:
        for p in range(1, args.max_pages + 1):
            time.sleep(PACE_SECONDS)
            d = call(client, "erp2_stocks_stocksquery",
                     {"warehouseName": name, "pageNo": p, "pageSize": 100})
            arr = (d.get("datas") or {}).get("array") or []
            if not arr:
                break
            for x in arr:
                rows.append({
                    "warehouse_name": x.get("warehouseName") or name,
                    "goods_sku": x.get("goodsSku"),
                    "available": x.get("availableStockQuantity"),
                    "intransit": x.get("intransitStockQuantity"),
                    "defects": x.get("defectsStockQuantity"),
                    "waiting_shipment": x.get("waitingShipmentStockQuantity"),
                    "avg_cost": x.get("goodsAvgCost"),
                    "snapshot_at": now,
                })
            if len(arr) < 100:
                break
        print(f"  {name}: rows so far={len(rows)}", flush=True)

    # 3) 落库（保留历史快照：按 snapshot_at 追加）
    con.register("_wh", wdf)
    con.execute("CREATE OR REPLACE TABLE warehouse_dim AS SELECT * FROM _wh")
    con.unregister("_wh")
    if rows:
        sdf = pd.DataFrame(rows)
        for c in ("available", "intransit", "defects", "waiting_shipment", "avg_cost"):
            sdf[c] = pd.to_numeric(sdf[c], errors="coerce")
        con.register("_stock", sdf)
        con.execute("""CREATE TABLE IF NOT EXISTS tongtool_stock AS SELECT * FROM _stock WHERE 1=0""")
        con.execute("INSERT INTO tongtool_stock SELECT * FROM _stock")
        con.unregister("_stock")
    try:
        n = con.execute("SELECT COUNT(*) FROM tongtool_stock").fetchone()[0]
    except Exception:
        n = 0
    con.close()
    print(json.dumps({"stock_rows_total": n, "snapshot_at": now}, ensure_ascii=False))


if __name__ == "__main__":
    main()
