# -*- coding: utf-8 -*-
"""补货信号 v2：通途SKU × 通途仓

数据：
- 需求：gs_orders（按发货仓 × 通途SKU，近 N 天日均）
- 供给：tongtool_stock（available / intransit / defects / waiting_shipment，最新快照）

关键：
- 不再使用 EN 库存（口径不对）。
- 仓库按「通途当前启用仓」归一：GS 的旧名/新前缀名映射到当前仓。
- 只读，不调 API（库存由 tongtool_stock_snapshot.py 负责拉取）。

用法：
  uv run python scripts/forecast_replenishment_v2.py --target-days 60 --demand-days 90
"""
from __future__ import annotations

import argparse
import json
import os
import tempfile
from pathlib import Path

import duckdb

# GS 历史仓名 → 当前仓名（通途改名）
PREFIXES = ("美东-", "美中-", "波兰-")


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--target-days", type=int, default=60)
    ap.add_argument("--demand-days", type=int, default=90)
    ap.add_argument("--out", default="D:/Work/fzh-order-store")
    args = ap.parse_args()

    con = duckdb.connect(str(Path(args.out) / "order_store.duckdb"))

    # 1) 当前启用仓
    cur = [r[0] for r in con.execute(
        "SELECT warehouse_name FROM warehouse_dim WHERE CAST(status AS VARCHAR)='1'").fetchall()]
    cur_set = set(cur)

    # 2) GS 仓名 → 当前仓（精确 → 加前缀 → 未映射）
    gs_wh = [r[0] for r in con.execute(
        "SELECT DISTINCT warehouse FROM gs_orders WHERE IFNULL(warehouse,'')<>''").fetchall()]
    mapping = []
    for w in gs_wh:
        target = w if w in cur_set else None
        if target is None:
            for p in PREFIXES:
                if p + w in cur_set:
                    target = p + w
                    break
        mapping.append({"gs_warehouse": w, "current_warehouse": target or w,
                        "mapped": target is not None})
    con.register("_m", __import__("pandas").DataFrame(mapping))
    con.execute("CREATE OR REPLACE TABLE warehouse_map AS SELECT * FROM _m")
    con.unregister("_m")
    unmapped = [m["gs_warehouse"] for m in mapping if not m["mapped"]]

    # 3) 需求：按（映射后仓 × 通途SKU）近 N 天日均
    con.execute(f"""
        CREATE OR REPLACE TABLE demand_sku_wh AS
        SELECT m.current_warehouse AS warehouse, g.sku_tongtool AS sku,
               SUM(g.qty) / {args.demand_days}.0 AS avg_daily
        FROM gs_orders g
        LEFT JOIN warehouse_map m ON g.warehouse = m.gs_warehouse
        WHERE g.sale_date >= strftime(current_date - INTERVAL {args.demand_days} DAY, '%Y-%m-%d')
          AND IFNULL(g.sku_tongtool, '') <> ''
        GROUP BY 1, 2
    """)

    # 4) 供给：最新快照
    con.execute("""
        CREATE OR REPLACE TABLE stock_latest AS
        SELECT warehouse_name AS warehouse, goods_sku AS sku,
               SUM(IFNULL(available,0)) AS available,
               SUM(IFNULL(intransit,0)) AS intransit,
               SUM(IFNULL(waiting_shipment,0)) AS waiting_shipment,
               SUM(IFNULL(defects,0)) AS defects
        FROM tongtool_stock
        WHERE snapshot_at = (SELECT MAX(snapshot_at) FROM tongtool_stock)
        GROUP BY 1, 2
    """)

    # 5) 补货
    con.execute(f"""
        CREATE OR REPLACE TABLE replenishment_v2 AS
        SELECT s.warehouse, s.sku,
               s.available, s.intransit, s.waiting_shipment, s.defects,
               IFNULL(d.avg_daily, 0) AS avg_daily_demand,
               CASE WHEN IFNULL(d.avg_daily,0) > 0
                    THEN ROUND((s.available + s.intransit) / d.avg_daily, 1) END AS days_cover,
               {args.target_days} AS target_days,
               CASE WHEN IFNULL(d.avg_daily,0) > 0
                    THEN GREATEST(0, ROUND(d.avg_daily * {args.target_days} - (s.available + s.intransit), 0)) END AS suggested_qty
        FROM stock_latest s
        LEFT JOIN demand_sku_wh d ON s.sku = d.sku AND s.warehouse = d.warehouse
    """)

    n = con.execute("SELECT COUNT(*) FROM replenishment_v2").fetchone()[0]
    need = con.execute("SELECT COUNT(*) FROM replenishment_v2 WHERE suggested_qty > 0").fetchone()[0]
    matched = con.execute("SELECT COUNT(*) FROM replenishment_v2 WHERE avg_daily_demand > 0").fetchone()[0]
    con.close()
    print(json.dumps({
        "rows": n, "need_replenish": need, "with_demand": matched,
        "target_days": args.target_days, "demand_days": args.demand_days,
        "warehouses_active": len(cur), "unmapped_gs_warehouses": unmapped,
    }, ensure_ascii=False))


if __name__ == "__main__":
    main()
