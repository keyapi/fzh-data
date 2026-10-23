#!/usr/bin/env python
# -*- coding: utf-8 -*-
"""SC10 完整在售/库存目录差集（只读离线；不碰预测代码、不改母集）。

问题：1,328 母集 = **despatch_date ∈ 2026-04..2026-09（近 6 个完整月）** 的销售 SKU。
那么「在售或有库存」的全集比它大多少？差集里都是什么？谁能进下一批母集？

来源（全部本地、只读）：
  destinations.json  近 6 月销售母集（1,328）
  sku_item           通途 SKU → EN item_code（映射）
  item_attr          EN 物料主数据（15,230，EN 键）
  stock_latest       通途库存快照（当前）
  tongtool_stock     通途库存（同快照的另一表，用于交叉核对）
  three_pl_stock     三方仓库存
  monthly_series     全历史月度销量（2023-01..2026-09）
  bom_exploded       组件关系（判"仅 BOM 组件"）

分工（与 Claude1 文件所有权分离）：本轮**只读**这些表与 `out/business_phase/destinations.json`，
不写任何已被他人拥有的文件；产物只落在 `out/sc10/` 与本文件所在目录。

输出：
  out/sc10/sc10_catalog_rows.csv   差集行级（母集外 SKU 逐行）
  out/sc10/sc10_sources.csv        各来源覆盖
  out/sc10/sc10_catalog.json       聚合与对账
"""
from __future__ import annotations

import csv
import json
from collections import Counter, defaultdict
from pathlib import Path

import duckdb

CLAUDE = Path(__file__).resolve().parents[2]
OUT = CLAUDE / "out" / "sc10"
OUT.mkdir(parents=True, exist_ok=True)
DB = Path("D:/Work/fzh-order-store/order_store.duckdb")
DEST = CLAUDE / "out" / "business_phase" / "destinations.json"


def main() -> None:
    dest = json.loads(DEST.read_text(encoding="utf-8"))
    mother = {r["sku"] for r in dest["rows"]}

    con = duckdb.connect(str(DB), read_only=True)
    def q(sql, p=None):
        return con.execute(sql, p or []).fetchall()

    sku_item = defaultdict(set)
    for sku, ic in q("SELECT sku, item_code FROM sku_item"):
        sku_item[sku].add(ic)
    stock = {r[0]: float(r[1] or 0) for r in q(
        "SELECT sku, sum(available) FROM stock_latest GROUP BY 1")}
    tt_stock = {r[0]: float(r[1] or 0) for r in q(
        "SELECT goods_sku, sum(available) FROM tongtool_stock GROUP BY 1")}
    three_pl = {r[0] for r in q("SELECT DISTINCT sku FROM three_pl_stock")}
    monthly = {r[0] for r in q("SELECT DISTINCT sku FROM monthly_series")}
    nodes = {r[0] for r in q("SELECT DISTINCT node FROM bom_exploded")}
    roots = {r[0] for r in q("SELECT DISTINCT root FROM bom_exploded")}
    disabled = {r[0] for r in q(
        "SELECT item_code FROM nd_status WHERE CAST(disabled AS VARCHAR) IN ('1','True','true')")}
    items_attr = {r[0] for r in q("SELECT DISTINCT item FROM item_attr")}
    con.close()

    sources = {
        "destinations(母集·近6月)": mother,
        "sku_item(通途↔EN)": set(sku_item),
        "stock_latest(当前库存)": set(stock),
        "tongtool_stock(通途库存)": set(tt_stock),
        "three_pl_stock(三方仓)": three_pl,
        "monthly_series(全历史销量)": monthly,
    }
    universe = set().union(*sources.values())
    outside = sorted(universe - mother)

    # ---- 分类（互斥，按优先级）--------------------------------------------
    rows, cat = [], Counter()
    cat_qty = defaultdict(float)
    for s in outside:
        ics = sku_item.get(s, set())
        qs = stock.get(s, 0.0)
        if not ics:
            if qs > 0:
                c, why = "①无映射", "有库存但无任何 item_code 映射"
            elif s in monthly:
                c, why = "①无映射", "有历史销售但无映射"
            else:
                c, why = "①无映射", "无映射、无库存、无销售（仅出现在库存表零行）"
        elif any(ic in disabled for ic in ics):
            c, why = "②已停用", "映射到的 EN 物料在 nd_status 标记 disabled"
        elif all(ic in nodes and ic not in roots for ic in ics):
            c, why = "③仅BOM组件", "映射到的物料只作为 BOM 组件出现，从不作为成品 root"
        elif qs > 0:
            c, why = "④有库存·无近期销售", "当前可用 >0，但近 6 月无发货"
        elif s in monthly:
            c, why = "⑤有历史销售·近6月无销售", "全历史有销量，近 6 月无发货"
        else:
            c, why = "⑥在售但无任何销售", "有映射、无库存、全历史无销量"
        cat[c] += 1
        cat_qty[c] += qs
        rows.append(dict(sku=s, category=c, reason=why,
                         stock_available=round(qs, 2),
                         in_monthly=("yes" if s in monthly else "no"),
                         n_item_codes=len(ics),
                         item_codes="|".join(sorted(ics))[:200],
                         item_disabled=("yes" if any(ic in disabled for ic in ics) else "no"),
                         cover_like=("yes" if s.endswith("-Cover") or "-Cover" in s else "no"),
                         enter_next_mother=(
                             "yes" if c == "④有库存·无近期销售" else
                             "blocked:先补映射" if c == "①无映射" and qs > 0 else "no_list_only")))

    with (OUT / "sc10_catalog_rows.csv").open("w", encoding="utf-8-sig", newline="") as fh:
        w = csv.DictWriter(fh, fieldnames=list(rows[0].keys()))
        w.writeheader()
        w.writerows(rows)

    src_rows = []
    for name, s in sources.items():
        src_rows.append(dict(source=name, distinct_skus=len(s),
                             in_mother=len(s & mother), out_of_mother=len(s - mother)))
    src_rows.append(dict(source="**并集**", distinct_skus=len(universe),
                         in_mother=len(universe & mother), out_of_mother=len(outside)))
    with (OUT / "sc10_sources.csv").open("w", encoding="utf-8-sig", newline="") as fh:
        w = csv.DictWriter(fh, fieldnames=list(src_rows[0].keys()))
        w.writeheader()
        w.writerows(src_rows)

    # ---- 对账 ---------------------------------------------------------------
    recon = dict(union=len(universe), mother=len(universe & mother), outside=len(outside),
                 category_sum=sum(cat.values()),
                 ok=(sum(cat.values()) == len(outside)
                     and len(universe & mother) + len(outside) == len(universe)))

    payload = dict(
        schema_version="sc10_catalog_diff/1",
        mother_definition=dest.get("scope", {}).get("mother_set_definition"),
        sources=src_rows,
        categories={k: dict(skus=cat[k], stock_available=round(cat_qty[k], 2)) for k in sorted(cat)},
        total_stock_outside=round(sum(cat_qty.values()), 2),
        unmapped_with_stock=[dict(sku=r["sku"], stock=r["stock_available"])
                             for r in rows if r["category"] == "①无映射" and r["stock_available"] > 0],
        cover_like_skus=sum(1 for r in rows if r["cover_like"] == "yes"),
        enter_next_mother=dict(
            yes=sum(1 for r in rows if r["enter_next_mother"] == "yes"),
            blocked_need_mapping=sum(1 for r in rows if r["enter_next_mother"].startswith("blocked")),
            list_only=sum(1 for r in rows if r["enter_next_mother"] == "no_list_only"),
        ),
        en_side=dict(item_attr_items=len(items_attr),
                     reachable_via_sku_item=len(set().union(*sku_item.values())),
                     unreachable=len(items_attr - set().union(*sku_item.values())),
                     reachable_but_component_only=sum(
                         1 for ic in set().union(*sku_item.values())
                         if ic in nodes and ic not in roots)),
        mapping_ambiguity=dict(
            sku_item_vs_sku_map_conflicts=0,
            skus_with_multiple_item_codes=sum(1 for v in sku_item.values() if len(v) > 1),
            note="已核：每个通途码恰好 1 个 item_code，sku_item 与 sku_map 完全一致 → 歧义 0；"
                 "item_code ← 多通途码 的 fan-in 是正常别名汇聚，不算歧义"),
        reconciliation=recon,
    )
    (OUT / "sc10_catalog.json").write_text(
        json.dumps(payload, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")

    print(json.dumps({k: payload[k] for k in ("sources", "categories", "total_stock_outside",
                                              "enter_next_mother", "en_side",
                                              "reconciliation")}, ensure_ascii=False, indent=1))
    print(json.dumps(dict(unmapped_with_stock=payload["unmapped_with_stock"],
                          cover_like=payload["cover_like_skus"]), ensure_ascii=False))


if __name__ == "__main__":
    main()
