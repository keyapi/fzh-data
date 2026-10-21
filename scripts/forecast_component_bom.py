# -*- coding: utf-8 -*-
"""组件级补货：EN BOM 展开 + 预测销量 → 皮壳/内胆/面料/辅料需求

背景：
- 成品补货（forecast_replenishment_v3.py）只看成品 SKU×主仓；
  但皮壳（PK#）、内胆（ND#）、面料、拉链、PP 棉等组件要单独备料。
- 通途库存接口只覆盖三家主仓，组件不在其中；组件库存/在途取 EN
  `Bin.actual_qty` + 未结 Purchase Order（只读导出 TSV）。
- 需求来自 ens5 预测的日均销量 × BOM 累计用量（多级展开，最多 4 层）。

输入（默认 D:/Work/fzh-order-store）：
  bom.tsv          EN 启用且默认的 BOM（name, item, quantity, uom）
  bom_items.tsv    BOM 明细（parent, idx, item_code, item_name, qty, uom, source_warehouse, rate）
  items_attr.tsv   Item 属性（MOQ/装箱数/交期/安全库存）
  bin.tsv          EN Bin 非零库存（item_code, warehouse, actual_qty, stock_value）
  po_items.tsv     EN 未结 PO 行（item_code, parent, qty, received_qty, warehouse）

只读，不调 API。用法：
  uv run python scripts/forecast_component_bom.py --lead-days 30 --safety-days 15
"""
from __future__ import annotations

import argparse
import json
from pathlib import Path

import duckdb
import pandas as pd

DEFAULT_OUT = Path("D:/Work/fzh-order-store")

# 只把中国境内（FZH / 绍）的仓库算作组件可用库存；
# 排除聚合视图、海外到货/在途、不良/报废/呆滞/样品等不可用库存。
EXCLUDE_WH_PATTERNS = (
    "所有仓库", "FBA", "到货仓", "在途", "不良", "报废", "呆滞",
    "样品", "采购退货", "退货", "办公用品", "工具配件", "易耗品",
    "物流包装", "海外仓",
)


def is_component_wh(name: str) -> bool:
    if not name:
        return False
    if not (name.endswith("- FZH") or name.endswith("- 绍")):
        return False
    return not any(p in name for p in EXCLUDE_WH_PATTERNS)


def read_tsv(path: Path, names: list[str]) -> pd.DataFrame:
    return pd.read_csv(path, sep="\t", header=None, names=names, dtype=str, encoding="utf-8")


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--out", default=str(DEFAULT_OUT))
    ap.add_argument("--lead-days", type=int, default=30, help="Item 未维护交期时的默认交期")
    ap.add_argument("--safety-days", type=int, default=15)
    ap.add_argument("--max-level", type=int, default=4)
    args = ap.parse_args()
    out = Path(args.out)

    bom = read_tsv(out / "bom.tsv", ["bom", "item", "quantity", "uom"])
    bi = read_tsv(out / "bom_items.tsv",
                  ["parent", "idx", "item_code", "item_name", "qty", "uom", "source_warehouse", "rate"])
    attr = read_tsv(out / "items_attr.tsv",
                    ["item", "item_name", "item_group", "is_stock_item", "moq", "min_pack",
                     "qty_per_outer", "lead_days", "safety_stock", "disabled"])
    bins = read_tsv(out / "bin.tsv", ["item_code", "warehouse", "actual_qty", "stock_value"])
    pos = read_tsv(out / "po_items.tsv", ["item_code", "po", "qty", "received_qty", "warehouse"])

    # 同一 item 偶有多个默认 BOM（内容相同），保留名称最小的一个
    bom = bom.sort_values("bom").drop_duplicates("item", keep="first")
    bom["quantity"] = pd.to_numeric(bom["quantity"], errors="coerce").fillna(1).clip(lower=1e-9)
    bi["qty"] = pd.to_numeric(bi["qty"], errors="coerce").fillna(0)
    bi = bi[bi["parent"].isin(set(bom["bom"]))]
    for c in ("moq", "min_pack", "qty_per_outer", "lead_days", "safety_stock"):
        attr[c] = pd.to_numeric(attr[c], errors="coerce").fillna(0)
    bins["actual_qty"] = pd.to_numeric(bins["actual_qty"], errors="coerce").fillna(0)
    bins = bins[bins["warehouse"].map(is_component_wh)]
    for c in ("qty", "received_qty"):
        pos[c] = pd.to_numeric(pos[c], errors="coerce").fillna(0)

    con = duckdb.connect(str(out / "order_store.duckdb"))
    for name, df in (("_bom", bom), ("_bi", bi), ("_attr", attr), ("_bin", bins), ("_po", pos)):
        con.register(name, df)
    con.execute("CREATE OR REPLACE TABLE bom AS SELECT bom, item, quantity, uom FROM _bom")
    con.execute("CREATE OR REPLACE TABLE bom_item AS SELECT parent, item_code, item_name, qty, uom FROM _bi")
    con.execute("""CREATE OR REPLACE TABLE item_attr AS
        SELECT item, item_name, item_group, moq, min_pack, qty_per_outer, lead_days, safety_stock FROM _attr""")
    con.execute("""CREATE OR REPLACE TABLE en_bin_component AS
        SELECT item_code, warehouse, actual_qty FROM _bin""")
    con.execute("""CREATE OR REPLACE TABLE en_po_open AS
        SELECT item_code, po, qty, received_qty, warehouse, qty - received_qty AS open_qty FROM _po""")
    for name in ("_bom", "_bi", "_attr", "_bin", "_po"):
        con.unregister(name)

    # 多级 BOM 展开：qty_per_unit = 每 1 个父件所需的累计数量
    con.execute(f"""
        CREATE OR REPLACE TABLE bom_exploded AS
        WITH RECURSIVE ex AS (
            SELECT b.item AS root, b.item AS node, 1.0::DOUBLE AS qty_per_unit,
                   0 AS level, [b.item] AS path
            FROM bom b
            UNION ALL
            SELECT e.root, bi.item_code,
                   e.qty_per_unit * bi.qty / b.quantity,
                   e.level + 1, list_append(e.path, bi.item_code)
            FROM ex e
            JOIN bom b ON b.item = e.node
            JOIN bom_item bi ON bi.parent = b.bom
            WHERE e.level < {args.max_level}
              AND NOT list_contains(e.path, bi.item_code)
        )
        SELECT root, node, level, SUM(qty_per_unit) AS qty_per_unit
        FROM ex WHERE level > 0 GROUP BY 1, 2, 3
    """)

    # 成品需求（ens5 未来 3 个月日均）→ 组件需求
    con.execute("""
        CREATE OR REPLACE TABLE demand_forecast_90 AS
        SELECT sku, warehouse,
               SUM(forecast_qty) / (COUNT(DISTINCT month) * 30.0) AS daily_forecast
        FROM forecast_sku_wh
        WHERE method = 'ens5'
          AND month >= strftime(CURRENT_DATE, '%Y-%m')   -- 只取未来月
        GROUP BY 1, 2
    """)
    con.execute("""
        CREATE OR REPLACE TABLE finished_demand AS
        SELECT m.item_code AS item_code, d.warehouse, SUM(d.daily_forecast) AS daily_demand
        FROM demand_forecast_90 d
        JOIN sku_map m ON d.sku = m.tongtool_sku
        GROUP BY 1, 2
    """)
    con.execute("""
        CREATE OR REPLACE TABLE component_demand_wh AS
        SELECT x.node AS component_item, f.warehouse,
               SUM(f.daily_demand * x.qty_per_unit) AS daily_demand
        FROM finished_demand f
        JOIN bom_exploded x ON x.root = f.item_code
        GROUP BY 1, 2
    """)
    con.execute("""
        CREATE OR REPLACE TABLE component_demand AS
        WITH demand AS (
            SELECT component_item, SUM(daily_demand) AS daily_demand,
                   COUNT(DISTINCT warehouse) AS demand_warehouses
            FROM component_demand_wh GROUP BY 1
        ), usage AS (
            SELECT node AS component_item, COUNT(DISTINCT root) AS used_in_boms,
                   MIN(level) AS level,
                   MAX(CASE WHEN node IN (SELECT item FROM bom) THEN 1 ELSE 0 END) AS has_bom
            FROM bom_exploded GROUP BY 1
        )
        SELECT d.component_item, d.daily_demand, d.demand_warehouses,
               IFNULL(u.used_in_boms, 0) AS used_in_boms,
               IFNULL(u.level, 1) AS level, IFNULL(u.has_bom, 0) AS has_bom
        FROM demand d
        LEFT JOIN usage u ON u.component_item = d.component_item
    """)

    # 组件供应：EN Bin（中国仓）+ EN 未结 PO
    con.execute("""
        CREATE OR REPLACE TABLE component_stock AS
        SELECT item_code AS component_item, SUM(actual_qty) AS on_hand_raw,
               COUNT(DISTINCT warehouse) AS stock_wh
        FROM en_bin_component GROUP BY 1
    """)
    con.execute("""
        CREATE OR REPLACE TABLE component_po AS
        SELECT item_code AS component_item, SUM(open_qty) AS on_order
        FROM en_po_open WHERE open_qty > 0 GROUP BY 1
    """)

    con.execute(f"""
        CREATE OR REPLACE TABLE component_replenishment AS
        WITH base AS (
            SELECT d.component_item,
                   a.item_name, a.item_group,
                   d.daily_demand, d.used_in_boms, d.level, d.has_bom,
                   IFNULL(s.on_hand_raw, 0) AS on_hand_raw,
                   GREATEST(0, IFNULL(s.on_hand_raw, 0)) AS on_hand,
                   IFNULL(p.on_order, 0) AS on_order,
                   CASE WHEN IFNULL(s.on_hand_raw, 0) < 0 THEN 'negative_stock' ELSE '' END AS data_flag,
                   CASE WHEN IFNULL(a.lead_days,0) > 0 THEN a.lead_days ELSE {args.lead_days} END AS lead_days,
                   IFNULL(a.moq, 0) AS moq,
                   COALESCE(NULLIF(a.qty_per_outer,0), NULLIF(a.min_pack,0), 1) AS pack_size
            FROM component_demand d
            LEFT JOIN item_attr a ON a.item = d.component_item
            LEFT JOIN component_stock s ON s.component_item = d.component_item
            LEFT JOIN component_po p ON p.component_item = d.component_item
        ), calc AS (
            SELECT *,
                   lead_days + {args.safety_days} AS rop_days,
                   ROUND(daily_demand, 4) AS daily_rounded,
                   CASE WHEN daily_demand > 0
                        THEN ROUND((on_hand + on_order) / daily_demand, 1) END AS days_cover,
                   CASE WHEN daily_demand > 0
                        THEN ROUND(daily_demand * (lead_days + {args.safety_days}), 1) END AS rop_qty,
                   CASE WHEN daily_demand > 0
                        THEN GREATEST(0, daily_demand * (lead_days + {args.safety_days})
                                         - (on_hand + on_order)) END AS suggested_raw
            FROM base
        )
        SELECT component_item, item_name, item_group, level, has_bom, used_in_boms,
               daily_rounded AS daily_demand,
               ROUND(on_hand_raw, 1) AS on_hand_raw,
               ROUND(on_hand, 1) AS on_hand, ROUND(on_order, 1) AS on_order,
               days_cover, lead_days, rop_days, rop_qty, data_flag,
               ROUND(suggested_raw, 1) AS suggested_raw,
               moq, pack_size,
               CASE WHEN suggested_raw > 0
                    THEN GREATEST(CEIL(suggested_raw / pack_size) * pack_size, moq)
                    ELSE 0 END AS suggested_qty
        FROM calc
    """)

    n = con.execute("SELECT COUNT(*) FROM component_replenishment").fetchone()[0]
    need = con.execute("SELECT COUNT(*) FROM component_replenishment WHERE suggested_qty > 0").fetchone()[0]
    total_raw = con.execute("SELECT SUM(suggested_raw) FROM component_replenishment").fetchone()[0] or 0
    total_round = con.execute("SELECT SUM(suggested_qty) FROM component_replenishment").fetchone()[0] or 0
    top = con.execute("""
        SELECT component_item, item_name, ROUND(daily_demand,2) AS daily_demand,
               on_hand, on_order, days_cover, suggested_raw, suggested_qty
        FROM component_replenishment WHERE suggested_qty > 0
        ORDER BY suggested_raw DESC LIMIT 15
    """).df()
    con.close()

    print(json.dumps({
        "components_with_demand": n,
        "need_replenish": need,
        "total_suggested_raw": round(float(total_raw), 1),
        "total_suggested_rounded": round(float(total_round), 1),
        "lead_days_default": args.lead_days,
        "safety_days": args.safety_days,
    }, ensure_ascii=False))
    print(top.to_string(index=False))


if __name__ == "__main__":
    main()
