# -*- coding: utf-8 -*-
"""补货信号快照（第一版）

输入：
- DuckDB 里的 gs_orders（销量）+ sku_map（通途SKU→EN 物料）
- EN 的 Bin（现存）与未结 Purchase Order（在途）

输出：DuckDB 表 replenishment
  item_code, warehouse, on_hand, on_order, avg_daily_demand_90d,
  days_cover, target_days, suggested_qty

只读：只查 EN，不写任何数据。

用法：
  uv run python scripts/forecast_replenishment.py --target-days 60
"""
from __future__ import annotations

import argparse
import json
import os
import tempfile
import time
from pathlib import Path

import duckdb
import requests

ENV_FILE = Path("D:/Work/赛狐/Cursor/EN_API/.env")
BASE = "https://erpnext.vilavi.cn"
OPEN_PO_STATUS = ("Draft", "To Receive and Bill", "To Receive", "To Bill", "On Hold")


def load_env(path: Path) -> dict:
    vals = {}
    for raw in path.read_text(encoding="utf-8").splitlines():
        line = raw.strip()
        if line and not line.startswith("#") and "=" in line:
            k, v = line.split("=", 1)
            vals[k.strip()] = v.strip().strip('"').strip("'")
    return vals


def auth() -> dict:
    env = load_env(ENV_FILE)
    return {"Authorization": f"token {env['ERP_API_KEY']}:{env['ERP_API_SECRET']}"}


def paginate(resource: str, fields: list[str], filters: list | None = None, page: int = 0):
    """一次取全（limit_page_length=0），失败重试。"""
    headers = auth()
    params = {"fields": json.dumps(fields), "limit_page_length": page}
    if filters:
        params["filters"] = json.dumps(filters)
    last = None
    for _ in range(6):
        try:
            r = requests.get(f"{BASE}/api/resource/{resource}", headers=headers, params=params, timeout=600)
            if r.status_code == 200:
                return r.json().get("data", [])
            last = f"HTTP {r.status_code}: {r.text[:120]}"
            raise RuntimeError(last)
        except Exception as e:
            last = e
            time.sleep(5)
    raise RuntimeError(f"paginate failed {resource}: {last}")


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--target-days", type=int, default=60)
    ap.add_argument("--demand-days", type=int, default=90)
    ap.add_argument("--out", default=os.path.join(tempfile.gettempdir(), "order_store"))
    args = ap.parse_args()

    db_path = Path(args.out) / "order_store.duckdb"
    con = duckdb.connect(str(db_path))

    bins = paginate("Bin", ["item_code", "warehouse", "actual_qty", "projected_qty"])
    con.register("_bins", __import__("pandas").DataFrame(bins))
    con.execute("CREATE OR REPLACE TABLE stock_bin AS SELECT * FROM _bins")
    con.unregister("_bins")

    import pandas as pd
    po_tsv = Path(args.out) / "po_open.tsv"
    po_df = pd.read_csv(po_tsv, sep="	", header=None, dtype=str, quoting=3,
                        names=["parent", "item_code", "qty", "received_qty", "warehouse"])
    for c in ("qty", "received_qty"):
        po_df[c] = pd.to_numeric(po_df[c], errors="coerce")
    con.register("_po", po_df)
    con.execute("""CREATE OR REPLACE TABLE po_open AS
        SELECT item_code, IFNULL(warehouse,'') AS warehouse,
               SUM(CASE WHEN IFNULL(qty,0) > IFNULL(received_qty,0)
                        THEN qty - received_qty ELSE 0 END) AS on_order
        FROM _po GROUP BY item_code, IFNULL(warehouse,'')""")
    con.unregister("_po")

    con.execute(f"""
        CREATE OR REPLACE TABLE replenishment AS
        WITH demand AS (
            SELECT m.item_code,
                   SUM(g.qty) / {args.demand_days}.0 AS avg_daily_demand
            FROM gs_orders g
            JOIN sku_map m ON g.sku_tongtool = m.tongtool_sku
            WHERE g.sale_date >= strftime(current_date - INTERVAL {args.demand_days} DAY, '%Y-%m-%d')
              AND m.item_code IS NOT NULL
            GROUP BY m.item_code
        ),
        wh AS (
            SELECT item_code, warehouse, actual_qty AS on_hand FROM stock_bin
            UNION ALL
            SELECT item_code, warehouse, on_order FROM po_open
        ),
        agg AS (
            SELECT item_code, '' AS warehouse,
                   SUM(CASE WHEN actual_qty IS NOT NULL THEN actual_qty ELSE 0 END) AS on_hand,
                   SUM(CASE WHEN on_order IS NOT NULL THEN on_order ELSE 0 END) AS on_order
            FROM (SELECT b.item_code, b.warehouse, b.actual_qty, NULL::DOUBLE AS on_order FROM stock_bin b
                  UNION ALL
                  SELECT p.item_code, p.warehouse, NULL::DOUBLE, p.on_order FROM po_open p) t
            GROUP BY item_code
        )
        SELECT a.item_code, a.warehouse, a.on_hand, a.on_order,
               IFNULL(d.avg_daily_demand, 0) AS avg_daily_demand_90d,
               CASE WHEN IFNULL(d.avg_daily_demand,0) > 0
                    THEN ROUND((a.on_hand + a.on_order) / d.avg_daily_demand, 1) END AS days_cover,
               {args.target_days} AS target_days,
               CASE WHEN IFNULL(d.avg_daily_demand,0) > 0
                    THEN GREATEST(0, ROUND(d.avg_daily_demand * {args.target_days} - (a.on_hand + a.on_order), 0)) END AS suggested_qty
        FROM agg a LEFT JOIN demand d ON a.item_code = d.item_code
    """)

    n = con.execute("SELECT COUNT(*) FROM replenishment").fetchone()[0]
    low = con.execute("SELECT COUNT(*) FROM replenishment WHERE suggested_qty > 0").fetchone()[0]
    print(json.dumps({"rows": n, "need_replenish": low, "target_days": args.target_days,
                      "db": str(db_path)}, ensure_ascii=False))
    con.close()


if __name__ == "__main__":
    main()
