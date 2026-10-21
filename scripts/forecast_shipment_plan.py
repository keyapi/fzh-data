# -*- coding: utf-8 -*-
"""分公司补货「发货形态」拆解：成品 / 皮壳 / 半成品

背景（先读 docs/solutions/architecture-patterns/order-history-duckdb-store.md §10）：
- 绍兴发货方式维护在 EN **物料组** 的 `custom_shipment_type_to_branch`：
  皮壳 / 半成品 / 成品。它决定分公司实际收到的是什么，而不是成品 SKU。
- 「给分公司发皮壳」是口语说法：按 BOM，皮壳单一般还带内胆（PK# + ND#）；
  个别产品只有皮壳没有内胆，以 BOM 为准。
- 销售订单的「为所有行增加配套物料」按钮**不是读 BOM**，而是按
  皮壳物料组 + 尺寸属性找 `内胆#...` 变体（`key_test.item_utils.get_supporting_item`），
  并遵循物料组的 `custom_replaced_by_other_item_group`。本脚本同时给出两种口径：
  BOM 有内胆但按钮找不到 → `bom_nd_no_button_match`；
  BOM 没内胆但按钮会加 → `nd_from_button_not_bom`。
- 面料/拉链/PP 棉属于中国生产物料/分公司填充耗材，不做分公司补货。
- 分公司库存池仍用通途（listing SKU，`-Cover` 是独立 SKU 账，不镜像）；
  本脚本不在成品补货之外再算一套供给，只把补货量换算成「该发什么」。

输入（默认 D:/Work/fzh-order-store）：
  ks_items.tsv          EN 物料 → 物料组（KS/PK#/ND#）
  item_groups_full.tsv  EN 物料组 → 发货形态 + custom_replaced_by_other_item_group
  nd_items.tsv          EN 内胆物料（物料组/是否变体模板/停用）
  variant_attrs.tsv     EN 变体属性（用于取「尺寸」值）
  replenishment_v3      成品 SKU×仓 补货建议（先跑 forecast_replenishment_v3.py）

输出：
  replenishment_v3_ship   补货行 + 发货形态 + cover 库存提示
  component_ship_plan     按 BOM 第一层 + 按钮逻辑拆到 PK#/ND# 的发货清单
  component_ship_summary  按仓 × 组件汇总

用法：
  uv run python scripts/forecast_shipment_plan.py
"""
from __future__ import annotations

import argparse
import json
from pathlib import Path

import duckdb
import pandas as pd

DEFAULT_OUT = Path("D:/Work/fzh-order-store")


def read_tsv(path: Path, names: list[str]) -> pd.DataFrame:
    return pd.read_csv(path, sep="\t", header=None, names=names, dtype=str, encoding="utf-8").fillna("")


def build_pk_nd_button(ks: pd.DataFrame, grp: pd.DataFrame,
                       nd: pd.DataFrame, va: pd.DataFrame) -> pd.DataFrame:
    """复刻 key_test.item_utils.get_supporting_item 的内胆查找逻辑。"""
    size = (va[va["attribute"].str.contains("尺寸", na=False)]
            .drop_duplicates("item_code")
            .set_index("item_code")["attribute_value"].to_dict())

    pk = ks[ks["item_code"].str.startswith("PK#")].copy()
    pk["group_no_prefix"] = pk["item_group"].str.split("#", n=1).str[-1]
    pk["target_group"] = "内胆#" + pk["group_no_prefix"]
    remap = dict(zip(grp["item_group"], grp["replaced_by"]))
    pk["target_group"] = pk["target_group"].map(lambda g: remap.get(g) or g)
    pk["pk_size"] = pk["item_code"].map(size)

    nd_valid = nd[(nd["has_variants"] == "0") & (nd["disabled"] == "0")].copy()
    nd_valid["nd_size"] = nd_valid["item_code"].map(size)
    lookup = {}
    for r in nd_valid.itertuples():
        if r.nd_size:
            lookup[(r.item_group, r.nd_size)] = r.item_code

    pk["nd_item"] = [lookup.get((g, s)) for g, s in zip(pk["target_group"], pk["pk_size"])]
    return pk.loc[pk["nd_item"].notna(), ["item_code", "nd_item"]].rename(
        columns={"item_code": "pk_item"})


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--out", default=str(DEFAULT_OUT))
    args = ap.parse_args()
    out = Path(args.out)

    ks = read_tsv(out / "ks_items.tsv", ["item_code", "item_group", "item_name"])
    grp = read_tsv(out / "item_groups_full.tsv", ["item_group", "ship_type", "replaced_by"])
    nd = read_tsv(out / "nd_items.tsv", ["item_code", "item_group", "has_variants", "disabled", "variant_of"])
    va = read_tsv(out / "variant_attrs.tsv", ["item_code", "attribute", "attribute_value"])
    pk_nd = build_pk_nd_button(ks, grp, nd, va)

    con = duckdb.connect(str(out / "order_store.duckdb"))
    con.register("_ks", ks)
    con.register("_grp", grp)
    con.register("_pk_nd", pk_nd)
    con.execute("CREATE OR REPLACE TABLE item_group_ship AS SELECT item_group, ship_type FROM _grp")
    con.execute("""CREATE OR REPLACE TABLE item_ship_type AS
        SELECT i.item_code, i.item_group, IFNULL(g.ship_type, '') AS ship_type
        FROM _ks i LEFT JOIN _grp g ON g.item_group = i.item_group""")
    con.execute("""CREATE OR REPLACE TABLE pk_nd_button AS
        SELECT pk_item, nd_item FROM _pk_nd""")
    for n in ("_ks", "_grp", "_pk_nd"):
        con.unregister(n)

    con.execute("""
        CREATE OR REPLACE TABLE item_cover_stock AS
        SELECT m.item_code, s.warehouse, SUM(s.available) AS cover_available
        FROM stock_latest s
        JOIN sku_map m ON m.tongtool_sku = s.sku
        WHERE lower(s.sku) LIKE '%-cover' AND s.available > 0
        GROUP BY 1, 2
    """)

    con.execute("""
        CREATE OR REPLACE TABLE replenishment_v3_ship AS
        SELECT r.*, m.item_code AS en_item_code,
               IFNULL(t.ship_type, '') AS ship_type,
               IFNULL(cs.cover_available, 0) AS cover_stock_same_item,
               CASE WHEN IFNULL(cs.cover_available, 0) > 0
                          AND (r.available + r.intransit + IFNULL(r.on_order, 0)) = 0 THEN 'cover_only'
                    WHEN IFNULL(cs.cover_available, 0) > 0 THEN 'cover_also'
                    ELSE '' END AS pool_note
        FROM replenishment_v3 r
        LEFT JOIN sku_map m ON m.tongtool_sku = r.sku
        LEFT JOIN item_ship_type t ON t.item_code = m.item_code
        LEFT JOIN item_cover_stock cs ON cs.item_code = m.item_code AND cs.warehouse = r.warehouse
    """)

    # 只取 BOM 第一层：皮壳 PK# / 内胆 ND#（面料、拉链、PP 棉不在分公司补货范围）
    con.execute("""
        CREATE OR REPLACE TABLE level1_components AS
        SELECT x.root AS item_code, x.node AS component_item, x.qty_per_unit,
               bi.item_name AS component_name
        FROM bom_exploded x
        LEFT JOIN (SELECT item_code, MAX(item_name) AS item_name FROM bom_item GROUP BY 1) bi
               ON bi.item_code = x.node
        WHERE x.level = 1 AND (x.node LIKE 'PK#%' OR x.node LIKE 'ND#%')
    """)
    con.execute("""
        CREATE OR REPLACE TABLE bom_nd AS
        SELECT DISTINCT item_code, component_item AS nd_item
        FROM level1_components WHERE component_item LIKE 'ND#%'
    """)

    con.execute("""
        CREATE OR REPLACE TABLE component_ship_plan AS
        WITH need AS (
            SELECT warehouse, sku, en_item_code, ship_type, suggested_qty
            FROM replenishment_v3_ship
            WHERE suggested_qty > 0
        ), bom_expanded AS (
            SELECT n.warehouse, n.sku, n.en_item_code, n.ship_type, n.suggested_qty,
                   c.component_item, c.component_name, c.qty_per_unit,
                   ROUND(n.suggested_qty * c.qty_per_unit, 1) AS component_qty,
                   CASE WHEN c.component_item LIKE 'ND#%'
                             AND NOT EXISTS (
                                 SELECT 1 FROM level1_components pk
                                 JOIN pk_nd_button b ON b.pk_item = pk.component_item
                                 WHERE pk.item_code = n.en_item_code
                                   AND pk.component_item LIKE 'PK#%'
                                   AND b.nd_item = c.component_item)
                        THEN 'bom_nd_no_button_match' ELSE '' END AS flag
            FROM need n JOIN level1_components c ON c.item_code = n.en_item_code
            WHERE n.ship_type IN ('皮壳', '半成品')
        ), button_added AS (
            -- BOM 没有内胆，但销售订单按钮会按物料组+尺寸补一条内胆
            SELECT n.warehouse, n.sku, n.en_item_code, n.ship_type, n.suggested_qty,
                   b.nd_item AS component_item, bi.item_name AS component_name,
                   1.0 AS qty_per_unit,
                   ROUND(n.suggested_qty * pk.qty_per_unit, 1) AS component_qty,
                   'nd_from_button_not_bom' AS flag
            FROM need n
            JOIN level1_components pk ON pk.item_code = n.en_item_code AND pk.component_item LIKE 'PK#%'
            JOIN pk_nd_button b ON b.pk_item = pk.component_item
            LEFT JOIN (SELECT item_code, MAX(item_name) AS item_name FROM bom_item GROUP BY 1) bi
                   ON bi.item_code = b.nd_item
            WHERE n.ship_type IN ('皮壳', '半成品')
              AND NOT EXISTS (SELECT 1 FROM bom_nd x WHERE x.item_code = n.en_item_code)
        ), fallback AS (
            -- 成品 / 没匹配到物料 / 没有 BOM：保留原行，明确标记
            SELECT n.warehouse, n.sku, n.en_item_code, n.ship_type, n.suggested_qty,
                   n.en_item_code AS component_item, NULL AS component_name, 1.0 AS qty_per_unit,
                   n.suggested_qty AS component_qty,
                   CASE WHEN n.ship_type = '成品' THEN 'ship_finished'
                        WHEN n.en_item_code IS NULL THEN 'no_item_mapping'
                        ELSE 'no_bom' END AS flag
            FROM need n
            WHERE n.ship_type NOT IN ('皮壳', '半成品')
               OR NOT EXISTS (SELECT 1 FROM level1_components c WHERE c.item_code = n.en_item_code)
        )
        SELECT * FROM bom_expanded
        UNION ALL SELECT * FROM button_added
        UNION ALL SELECT * FROM fallback
    """)

    con.execute("""
        CREATE OR REPLACE TABLE component_ship_summary AS
        SELECT warehouse, component_item, ANY_VALUE(component_name) AS component_name,
               SUM(component_qty) AS component_qty, COUNT(DISTINCT en_item_code) AS n_products
        FROM component_ship_plan
        WHERE component_item LIKE 'PK#%' OR component_item LIKE 'ND#%'
        GROUP BY 1, 2
    """)

    split = con.execute("""
        SELECT COALESCE(NULLIF(ship_type,''),'(unknown)') AS ship_type,
               COUNT(*) AS sku_wh, SUM(suggested_qty) AS qty
        FROM replenishment_v3_ship WHERE suggested_qty > 0
        GROUP BY 1 ORDER BY qty DESC
    """).df()
    nd_source = con.execute("""
        SELECT CASE WHEN component_item LIKE 'ND#%' AND flag = '' THEN 'bom'
                    WHEN component_item LIKE 'ND#%' THEN flag
                    ELSE 'cover' END AS source,
               COUNT(*) AS lines, SUM(component_qty) AS qty
        FROM component_ship_plan
        WHERE component_item LIKE 'PK#%' OR component_item LIKE 'ND#%'
        GROUP BY 1 ORDER BY qty DESC
    """).df()
    plan = con.execute("""
        SELECT ship_type, component_item, component_name,
               SUM(component_qty) AS qty, COUNT(*) AS lines
        FROM component_ship_plan WHERE flag = ''
        GROUP BY 1,2,3 ORDER BY qty DESC LIMIT 12
    """).df()
    flags = con.execute("""
        SELECT flag, COUNT(*) n FROM component_ship_plan WHERE flag <> '' GROUP BY 1
    """).df()
    con.close()

    print(json.dumps({"need_rows": int((split["qty"].sum() or 0)),
                      "by_ship_type": split.to_dict("records")}, ensure_ascii=False))
    print(nd_source.to_string(index=False))
    print(plan.to_string(index=False))
    print(flags.to_string(index=False))


if __name__ == "__main__":
    main()
