# -*- coding: utf-8 -*-
"""补货建议 v3：基于 ens5 预测的 ROP（SKU × 主仓 + 物料级合并池）

供给：tongtool_stock 最新快照 + 通途 PO 未入库；两者高度重叠，
      按 available + GREATEST(intransit, PO) 计一次（不重复相加）。
需求：forecast_sku_wh.method='ens5' 未来月 → 日均（按实际未来月数归一）
ROP  ：日均 × (交期天数 + 安全天数)
建议 ：max(0, ROP − supply)；PO/库存源缺失时置 NULL 并打 data_flags。

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
import pandas as pd

MAIN_WH = ("美东-CENTRADE", "美中-FZH-DANEEY", "波兰-FZHPoland-covers")


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--out", default="D:/Work/fzh-order-store")
    ap.add_argument("--lead-days", type=int, default=45)
    ap.add_argument("--safety-days", type=int, default=30)
    args = ap.parse_args()

    con = duckdb.connect(str(Path(args.out) / "order_store.duckdb"))
    rop_days = args.lead_days + args.safety_days

    # 每个仓各自取最新快照（不同仓可能分批拉取，不能只取全局 MAX(snapshot_at)）
    con.execute("""
        CREATE OR REPLACE TABLE stock_latest AS
        WITH latest AS (
            SELECT warehouse_name, MAX(snapshot_at) AS snapshot_at
            FROM tongtool_stock GROUP BY 1
        )
        SELECT t.warehouse_name AS warehouse, t.goods_sku AS sku,
               SUM(IFNULL(t.available,0)) AS available,
               SUM(IFNULL(t.intransit,0)) AS intransit,
               SUM(IFNULL(t.waiting_shipment,0)) AS waiting_shipment,
               SUM(IFNULL(t.defects,0)) AS defects
        FROM tongtool_stock t
        JOIN latest l ON t.warehouse_name = l.warehouse_name AND t.snapshot_at = l.snapshot_at
        GROUP BY 1, 2
    """)

    po_present = True
    try:
        con.execute("""
            CREATE OR REPLACE TABLE po_open_latest AS
            SELECT sku, warehouse, SUM(on_order) AS on_order
            FROM tongtool_po_open GROUP BY 1, 2
        """)
    except Exception:
        po_present = False
        con.execute("CREATE OR REPLACE TABLE po_open_latest (sku VARCHAR, warehouse VARCHAR, on_order DOUBLE)")

    con.execute("""
        CREATE OR REPLACE TABLE demand_forecast_90 AS
        SELECT sku, warehouse,
               SUM(forecast_qty) / (COUNT(DISTINCT month) * 30.0) AS daily_forecast
        FROM forecast_sku_wh
        WHERE method = 'ens5'
          AND month >= strftime(CURRENT_DATE, '%Y-%m')   -- 只取未来月，排除回测/历史外推
        GROUP BY 1, 2
    """)

    # EN 物料 × 发货形态（物料组 custom_shipment_type_to_branch）
    out = Path(args.out)
    if (out / "ks_items.tsv").exists() and (out / "item_groups_full.tsv").exists():
        ks = pd.read_csv(out / "ks_items.tsv", sep="\t", header=None,
                         names=["item_code", "item_group", "item_name"], dtype=str, encoding="utf-8").fillna("")
        grp = pd.read_csv(out / "item_groups_full.tsv", sep="\t", header=None,
                          names=["item_group", "ship_type", "replaced_by"], dtype=str, encoding="utf-8").fillna("")
        con.register("_ks", ks)
        con.register("_grp", grp)
        con.execute("""CREATE OR REPLACE TABLE item_ship_type AS
            SELECT i.item_code, IFNULL(g.ship_type,'') AS ship_type
            FROM _ks i LEFT JOIN _grp g ON g.item_group=i.item_group""")
        con.unregister("_ks")
        con.unregister("_grp")
    else:
        con.execute("CREATE OR REPLACE TABLE item_ship_type (item_code VARCHAR, ship_type VARCHAR)")

    con.execute("""
        CREATE OR REPLACE TABLE sku_item AS
        SELECT DISTINCT m.tongtool_sku AS sku, m.item_code,
               IFNULL(t.ship_type,'') AS ship_type
        FROM sku_map m LEFT JOIN item_ship_type t ON t.item_code=m.item_code
    """)

    # 3PL（WayfairCG）库存单独一层：先按库存数量展示，不并入分公司 ROP
    # （通途只有 Cranbury 有量；权威仍是 Wayfair 后台导出）
    con.execute("""
        CREATE OR REPLACE TABLE three_pl_stock AS
        SELECT s.warehouse, s.sku, m.item_code,
               IFNULL(t.ship_type,'') AS ship_type,
               s.available, s.intransit
        FROM stock_latest s
        LEFT JOIN sku_map m ON m.tongtool_sku = s.sku
        LEFT JOIN item_ship_type t ON t.item_code = m.item_code
        WHERE s.warehouse LIKE 'WayfairCG%'
    """)

    # 输入健康度：缺表/缺数必须显式记录，不能静默当 0
    if po_present:
        con.execute("""
            CREATE OR REPLACE TABLE input_health AS
            SELECT (SELECT COUNT(*) FROM tongtool_stock) AS stock_rows,
                   (SELECT MIN(snapshot_at) FROM tongtool_stock) AS stock_snapshot_min,
                   (SELECT MAX(snapshot_at) FROM tongtool_stock) AS stock_snapshot,
                   (SELECT COUNT(DISTINCT warehouse_name) FROM tongtool_stock) AS stock_warehouses,
                   1 AS po_source_present,
                   (SELECT COUNT(*) FROM tongtool_po) AS po_rows,
                   (SELECT MAX(purchase_date) FROM tongtool_po) AS po_max_purchase,
                   (SELECT COUNT(*) FROM sku_map) AS sku_map_rows,
                   (SELECT COUNT(*) FROM forecast_sku_wh WHERE method='ens5') AS forecast_rows,
                   (SELECT COUNT(*) FROM forecast_sku_wh WHERE method='ens5'
                     AND month >= strftime(CURRENT_DATE, '%Y-%m')) AS forecast_future_rows,
                   (SELECT COUNT(*) FROM item_ship_type WHERE ship_type<>'') AS ship_type_items,
                   (SELECT COUNT(*) FROM three_pl_stock) AS three_pl_rows
        """)
    else:
        con.execute("""
            CREATE OR REPLACE TABLE input_health AS
            SELECT (SELECT COUNT(*) FROM tongtool_stock) AS stock_rows,
                   (SELECT MIN(snapshot_at) FROM tongtool_stock) AS stock_snapshot_min,
                   (SELECT MAX(snapshot_at) FROM tongtool_stock) AS stock_snapshot,
                   (SELECT COUNT(DISTINCT warehouse_name) FROM tongtool_stock) AS stock_warehouses,
                   0 AS po_source_present,
                   0 AS po_rows, NULL AS po_max_purchase,
                   (SELECT COUNT(*) FROM sku_map) AS sku_map_rows,
                   (SELECT COUNT(*) FROM forecast_sku_wh WHERE method='ens5') AS forecast_rows,
                   (SELECT COUNT(*) FROM forecast_sku_wh WHERE method='ens5'
                     AND month >= strftime(CURRENT_DATE, '%Y-%m')) AS forecast_future_rows,
                   (SELECT COUNT(*) FROM item_ship_type WHERE ship_type<>'') AS ship_type_items,
                   (SELECT COUNT(*) FROM three_pl_stock) AS three_pl_rows
        """)

    con.execute("""
        CREATE OR REPLACE TABLE replenishment_v3 AS
        WITH base AS (
            SELECT s.warehouse, s.sku,
                   s.available, s.intransit, IFNULL(p.on_order,0) AS on_order,
                   s.waiting_shipment, s.defects,
                   ROUND(IFNULL(d.daily_forecast,0), 3) AS daily_forecast,
                   s.available + GREATEST(s.intransit, IFNULL(p.on_order,0)) AS supply_used,
                   CASE WHEN s.intransit > 0 AND IFNULL(p.on_order,0) > 0
                        THEN 'intransit 与 PO 未入库重叠，按 max 计一次' ELSE '' END AS supply_note
            FROM stock_latest s
            LEFT JOIN demand_forecast_90 d ON s.sku = d.sku AND s.warehouse = d.warehouse
            LEFT JOIN po_open_latest p ON s.sku = p.sku AND s.warehouse = p.warehouse
            WHERE s.warehouse IN {whs}
        )
        SELECT warehouse, sku, available, intransit, on_order,
               waiting_shipment, defects, daily_forecast,
               CASE WHEN daily_forecast > 0 THEN ROUND(supply_used / daily_forecast, 1) END AS days_cover,
               {rops} AS rop_days,
               CASE WHEN daily_forecast > 0 THEN ROUND(daily_forecast * {rops}, 0) END AS rop_qty,
               CASE WHEN daily_forecast > 0
                    THEN GREATEST(0, ROUND(daily_forecast * {rops} - supply_used, 0)) END AS suggested_qty,
               supply_note
        FROM base
    """.replace("{rops}", str(rop_days)).replace("{whs}", str(tuple(MAIN_WH))))

    # 物料 × 仓 的「合并库存池」：同一物料的所有通途 SKU（含 -Cover）合并，
    # 避免同一物料的多个通途 SKU 各自算一遍。皮壳/半成品把 -Cover 计入供给；
    # 成品不把 cover 计入（除非齐套确认），但保留 cover_available 供核对。
    con.execute("""
        CREATE OR REPLACE TABLE replenishment_pool AS
        WITH dem AS (
            SELECT si.item_code, d.warehouse, SUM(d.daily_forecast) AS daily_forecast
            FROM demand_forecast_90 d JOIN sku_item si ON si.sku = d.sku
            GROUP BY 1, 2
        ), st AS (
            SELECT si.item_code, s.warehouse,
                   SUM(s.available) AS available_all,
                   SUM(s.intransit) AS intransit_all,
                   SUM(CASE WHEN lower(s.sku) LIKE '%-cover' THEN s.available ELSE 0 END) AS cover_available,
                   SUM(CASE WHEN lower(s.sku) LIKE '%-cover' THEN s.intransit ELSE 0 END) AS cover_intransit,
                   COUNT(DISTINCT s.sku) AS n_skus
            FROM stock_latest s JOIN sku_item si ON si.sku = s.sku
            WHERE s.warehouse IN {whs}
            GROUP BY 1, 2
        ), po AS (
            SELECT si.item_code, p.warehouse, SUM(p.on_order) AS on_order,
                   SUM(CASE WHEN lower(p.sku) LIKE '%-cover' THEN p.on_order ELSE 0 END) AS cover_on_order
            FROM po_open_latest p JOIN sku_item si ON si.sku = p.sku
            WHERE p.warehouse IN {whs}
            GROUP BY 1, 2
        ), base AS (
            SELECT d.warehouse, d.item_code, IFNULL(t.ship_type,'') AS ship_type,
                   ROUND(d.daily_forecast, 3) AS daily_forecast,
                   IFNULL(st.available_all,0) AS available_all,
                   IFNULL(st.intransit_all,0) AS intransit_all,
                   IFNULL(st.cover_available,0) AS cover_available,
                   IFNULL(st.cover_intransit,0) AS cover_intransit,
                   IFNULL(st.n_skus,0) AS n_skus,
                   IFNULL(po.on_order,0) AS on_order,
                   IFNULL(po.cover_on_order,0) AS cover_on_order,
                   CASE WHEN IFNULL(t.ship_type,'') IN ('皮壳','半成品')
                        THEN IFNULL(st.available_all,0) + GREATEST(IFNULL(st.intransit_all,0), IFNULL(po.on_order,0))
                        ELSE (IFNULL(st.available_all,0) - IFNULL(st.cover_available,0))
                             + GREATEST(GREATEST(0, IFNULL(st.intransit_all,0) - IFNULL(st.cover_intransit,0)),
                                        GREATEST(0, IFNULL(po.on_order,0) - IFNULL(po.cover_on_order,0))) END AS supply_in_rop,
                   {rops} AS rop_days,
                   (CASE WHEN (SELECT po_source_present FROM input_health)=0 THEN 'po_missing;' ELSE '' END
                    || CASE WHEN (SELECT stock_rows FROM input_health)=0 THEN 'stock_missing;' ELSE '' END
                    || CASE WHEN IFNULL(t.ship_type,'')='' THEN 'ship_type_missing;' ELSE '' END
                    || CASE WHEN IFNULL(st.n_skus,0)=0 THEN 'no_stock_row;' ELSE '' END) AS data_flags
            FROM dem d
            LEFT JOIN st ON st.item_code = d.item_code AND st.warehouse = d.warehouse
            LEFT JOIN po ON po.item_code = d.item_code AND po.warehouse = d.warehouse
            LEFT JOIN item_ship_type t ON t.item_code = d.item_code
        )
        SELECT *,
               CASE WHEN daily_forecast > 0 THEN ROUND(supply_in_rop / daily_forecast, 1) END AS days_cover,
               CASE WHEN daily_forecast > 0 THEN ROUND(daily_forecast * rop_days, 0) END AS rop_qty,
               CASE WHEN (SELECT po_source_present FROM input_health)=0
                          OR (SELECT stock_rows FROM input_health)=0 THEN NULL
                    WHEN daily_forecast > 0
                    THEN GREATEST(0, ROUND(daily_forecast * rop_days - supply_in_rop, 0)) END AS suggested_qty,
               'available + max(intransit, PO)' AS supply_basis
        FROM base
    """.replace("{rops}", str(rop_days)).replace("{whs}", str(tuple(MAIN_WH))))

    n = con.execute("SELECT COUNT(*) FROM replenishment_v3").fetchone()[0]
    need = con.execute("SELECT COUNT(*) FROM replenishment_v3 WHERE suggested_qty > 0").fetchone()[0]
    cover = con.execute("SELECT COUNT(*) FROM replenishment_v3 WHERE daily_forecast > 0").fetchone()[0]
    total = con.execute("SELECT SUM(suggested_qty) FROM replenishment_v3").fetchone()[0] or 0
    pn = con.execute("SELECT COUNT(*) FROM replenishment_pool").fetchone()[0]
    pneed = con.execute("SELECT COUNT(*) FROM replenishment_pool WHERE suggested_qty > 0").fetchone()[0]
    ptotal = con.execute("SELECT SUM(suggested_qty) FROM replenishment_pool").fetchone()[0] or 0
    tp = con.execute("SELECT COUNT(*), COUNT(DISTINCT sku), SUM(available) FROM three_pl_stock").fetchone()
    health = con.execute("SELECT * FROM input_health").df().to_dict("records")[0]
    con.close()
    print(json.dumps({"sku_wh_rows": n, "with_forecast": cover, "need_replenish": need,
                      "total_suggested_qty": int(total),
                      "pool_item_wh_rows": pn, "pool_need_replenish": pneed,
                      "pool_total_suggested_qty": int(ptotal),
                      "three_pl_rows": tp[0], "three_pl_skus": tp[1],
                      "three_pl_available": int(tp[2] or 0),
                      "input_health": health,
                      "rop_days": rop_days}, ensure_ascii=False))


if __name__ == "__main__":
    main()
