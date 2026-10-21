# -*- coding: utf-8 -*-
"""补货建议 v3：基于 ens5 预测的 ROP（SKU × 主仓）

供给：tongtool_stock 最新快照（available + intransit）
需求：forecast_sku_wh.method='ens5' 未来 3 个月 → 日均
ROP  ：日均 × (交期天数 + 安全天数)
建议 ：max(0, ROP − (available + intransit))

只读，不调 API。

用法：
  uv run python scripts/forecast_replenishment_v3.py --lead-days 45 --safety-days 30
"""
from __future__ import annotations

import argparse
import json
import os
from pathlib import Path

import duckdb

MAIN_WH = ("美东-CENTRADE", "美中-FZH-DANEEY", "波兰-FZHPoland-covers")


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--out", default="D:/Work/fzh-order-store")
    ap.add_argument("--lead-days", type=int, default=45)
    ap.add_argument("--safety-days", type=int, default=30)
    args = ap.parse_args()

    con = duckdb.connect(str(Path(args.out) / "order_store.duckdb"))
    rop_days = args.lead_days + args.safety_days

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

    con.execute("""
        CREATE OR REPLACE TABLE demand_forecast_90 AS
        SELECT sku, warehouse, SUM(forecast_qty) / 90.0 AS daily_forecast
        FROM forecast_sku_wh
        WHERE method = 'ens5'
        GROUP BY 1, 2
    """)

    con.execute("""
        CREATE OR REPLACE TABLE replenishment_v3 AS
        SELECT s.warehouse, s.sku,
               s.available, s.intransit, s.waiting_shipment, s.defects,
               ROUND(IFNULL(d.daily_forecast,0), 3) AS daily_forecast,
               CASE WHEN IFNULL(d.daily_forecast,0) > 0
                    THEN ROUND((s.available + s.intransit) / d.daily_forecast, 1) END AS days_cover,
               {rops} AS rop_days,
               CASE WHEN IFNULL(d.daily_forecast,0) > 0
                    THEN ROUND(d.daily_forecast * {rops}, 0) END AS rop_qty,
               CASE WHEN IFNULL(d.daily_forecast,0) > 0
                    THEN GREATEST(0, ROUND(d.daily_forecast * {rops} - (s.available + s.intransit), 0)) END AS suggested_qty
        FROM stock_latest s
        LEFT JOIN demand_forecast_90 d ON s.sku = d.sku AND s.warehouse = d.warehouse
        WHERE s.warehouse IN {whs}
    """.replace("{rops}", str(rop_days)).replace("{whs}", str(tuple(MAIN_WH))))

    n = con.execute("SELECT COUNT(*) FROM replenishment_v3").fetchone()[0]
    need = con.execute("SELECT COUNT(*) FROM replenishment_v3 WHERE suggested_qty > 0").fetchone()[0]
    cover = con.execute("SELECT COUNT(*) FROM replenishment_v3 WHERE daily_forecast > 0").fetchone()[0]
    total = con.execute("SELECT SUM(suggested_qty) FROM replenishment_v3").fetchone()[0] or 0
    con.close()
    print(json.dumps({"sku_wh_rows": n, "with_forecast": cover, "need_replenish": need,
                      "total_suggested_qty": int(total),
                      "rop_days": rop_days}, ensure_ascii=False))


if __name__ == "__main__":
    main()
