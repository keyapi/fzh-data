#!/usr/bin/env python
# -*- coding: utf-8 -*-
"""SC04 映射资产盘点 + 三态分类 + 证据分级 + UOM 核对（只读，不改 EN）。

用户明确要求：**先复用已有 sku_item / 配套 BOM 映射，不要宣布全局缺 SKU 映射**。

(1) 盘点映射资产：sku_item / sku_map / BOM / bom_exploded / destinations / item_attr
(2) 对 dn_split 的 39 张有号 DN 物料行逐行三态：已映射 / 可推导 / 未映射
(3) 证据分级：单据级 vs 数量级，并指出哪些结论只能停在单据级
(4) UOM：DN 行单位 vs 库存单位，列出需换算的物料，禁止跨 UOM 相加

不做数量抵扣、不出补货量；行级数据留本地。

输出：
  out/business_phase/map_evidence_lines.csv   DN 行级三态
  out/business_phase/map_evidence_codes.csv   物料码级三态
  out/business_phase/map_evidence.json        聚合
"""
from __future__ import annotations

import csv
import json
from collections import Counter, defaultdict
from pathlib import Path

import duckdb

OUT = Path(__file__).resolve().parents[3] / "out" / "business_phase"
DB_PATH = Path("D:/Work/fzh-order-store/order_store.duckdb")


def main() -> None:
    lines = list(csv.DictReader((OUT / "dn_split_lines.csv").open(encoding="utf-8-sig", newline="")))
    dns = list(csv.DictReader((OUT / "dn_split_dn.csv").open(encoding="utf-8-sig", newline="")))

    con = duckdb.connect(str(DB_PATH), read_only=True)
    def q(sql, p=None):
        return con.execute(sql, p or []).fetchall()

    n_sku_item = q("SELECT count(*), count(DISTINCT sku), count(DISTINCT item_code) FROM sku_item")[0]
    n_sku_map = q("SELECT count(*), count(DISTINCT tongtool_sku), count(DISTINCT item_code) FROM sku_map")[0]
    ship_type = dict(q("SELECT ship_type, count(*) FROM sku_item GROUP BY 1 ORDER BY 2 DESC"))
    n_bom = q("SELECT count(*), count(DISTINCT bom), count(DISTINCT item) FROM bom")[0]
    n_exp = q("SELECT count(*), count(DISTINCT root), count(DISTINCT node) FROM bom_exploded")[0]
    n_attr = q("SELECT count(*) FROM item_attr")[0][0]
    uom_basis = dict(q("SELECT uom_basis, count(*) FROM stock_history GROUP BY 1"))
    stock_tt = {r[0] for r in q("SELECT DISTINCT goods_sku FROM stock_history")}

    pairs = defaultdict(set)          # EN item_code -> set(通途 sku)
    for ic, sku in q("SELECT item_code, sku FROM sku_item"):
        pairs[ic].add(sku)
    parents = defaultdict(set)        # component -> set(root)
    for node, root in q("SELECT node, root FROM bom_exploded"):
        parents[node].add(root)
    bom_uom = defaultdict(set)
    for it, u in q("SELECT item, uom FROM bom"):
        bom_uom[it].add(u)
    con.close()

    codes = sorted({x["item_code"] for x in lines})

    def classify(code):
        if code in pairs:
            return "已映射", "sku_item: 通途码 %d 个" % len(pairs[code])
        ps = parents.get(code)
        if ps:
            mapped_roots = [r for r in ps if r in pairs]
            if mapped_roots:
                return "可推导", ("bom_exploded: 组件归属 %d 个成品，其中 %d 个成品已在 sku_item"
                                 % (len(ps), len(mapped_roots)))
            return "未映射", "bom_exploded 有组件关系但父成品均未在 sku_item"
        if code in bom_uom:
            return "未映射", "有 BOM 头但不在 bom_exploded，也无 sku_item 映射"
        return "未映射", "既不在 sku_item，也不在任何 BOM 结构"

    code_state, code_reason = {}, {}
    for c in codes:
        code_state[c], code_reason[c] = classify(c)

    # ---- 行级三态 ------------------------------------------------------------
    line_rows = []
    for x in lines:
        c = x["item_code"]
        line_rows.append(dict(
            dn=x["dn"], item_code=c, qty=x["qty"], uom=x["uom"],
            warehouse=x["warehouse"],
            mapping_state=code_state[c],
            mapping_reason=code_reason[c],
            tongtool_skus=("|".join(sorted(pairs[c]))[:200] if c in pairs else ""),
            bom_parents=("|".join(sorted(parents.get(c, []))[:5]) if c in parents else ""),
            bom_uom=("|".join(sorted(bom_uom.get(c, []))) if c in bom_uom else ""),
        ))
    with (OUT / "map_evidence_lines.csv").open("w", encoding="utf-8-sig", newline="") as fh:
        w = csv.DictWriter(fh, fieldnames=list(line_rows[0].keys()))
        w.writeheader()
        w.writerows(line_rows)

    code_rows = []
    for c in codes:
        qty_by_uom_c = defaultdict(float)
        for x in lines:
            if x["item_code"] == c:
                qty_by_uom_c[x["uom"]] += float(x["qty"])
        uoms = sorted({x["uom"] for x in lines if x["item_code"] == c})
        code_rows.append(dict(
            item_code=c, mapping_state=code_state[c], mapping_reason=code_reason[c],
            n_lines=sum(1 for x in lines if x["item_code"] == c),
            qty_by_uom="|".join(f"{u}:{round(v, 2)}" for u, v in sorted(qty_by_uom_c.items())),
            uoms="|".join(uoms),
            tongtool_skus=("|".join(sorted(pairs[c]))[:300] if c in pairs else ""),
            n_tongtool=len(pairs.get(c, ())),
            tongtool_in_stock=len([s for s in pairs.get(c, ()) if s in stock_tt]),
            bom_parents=("|".join(sorted(parents.get(c, []))[:5]) if c in parents else ""),
            bom_uom=("|".join(sorted(bom_uom.get(c, []))) if c in bom_uom else ""),
        ))
    with (OUT / "map_evidence_codes.csv").open("w", encoding="utf-8-sig", newline="") as fh:
        w = csv.DictWriter(fh, fieldnames=list(code_rows[0].keys()))
        w.writeheader()
        w.writerows(code_rows)

    # ---- 证据分级（逐 DN）----------------------------------------------------
    by_dn = defaultdict(list)
    for x in lines:
        by_dn[x["dn"]].append(x)
    dn_evidence = []
    for d in dns:
        ls = by_dn.get(d["dn"], [])
        qty_by_uom_d = defaultdict(float)
        for x in ls:
            qty_by_uom_d[x["uom"]] += float(x["qty"])
        states = {code_state[x["item_code"]] for x in ls}
        uoms = sorted({x["uom"] for x in ls})
        all_mapped = states == {"已映射"}
        single_uom = len(uoms) == 1
        doc_level = bool(ls)                     # DN 行 + 数量 + 状态 -> 单据级
        qty_level = bool(doc_level and all_mapped and single_uom)
        dn_evidence.append(dict(
            dn=d["dn"], n_lines=len(ls),
            qty_by_uom="|".join(f"{u}:{round(v, 2)}" for u, v in sorted(qty_by_uom_d.items())),
            uoms="|".join(uoms),
            states="|".join(sorted(states)),
            doc_level_ok=doc_level,
            qty_level_would_hold=("yes" if qty_level else "no"),
            qty_level_blocker=("" if qty_level else
                               ";".join([b for b, c in (
                                   ("有行未直接映射", not all_mapped),
                                   ("跨 UOM", not single_uom),
                                   ("库存 UOM 未证", True)) if c])),
            qty_level_ok="no",                    # 库存 uom_basis 全 unknown -> 无法到数量级
        ))

    # ---- UOM 汇总 ------------------------------------------------------------
    qty_by_uom = defaultdict(float)
    for x in lines:
        qty_by_uom[x["uom"]] += float(x["qty"])
    non_piece = [r for r in code_rows if r["uoms"] != "个"]
    need_convert = [dict(item_code=r["item_code"], uoms=r["uoms"], qty_by_uom=r["qty_by_uom"],
                         bom_uom=r["bom_uom"], state=r["mapping_state"]) for r in non_piece]

    payload = dict(
        schema_version="map_evidence/1",
        assets=dict(
            sku_item=dict(rows=n_sku_item[0], distinct_tongtool=n_sku_item[1],
                          distinct_item_code=n_sku_item[2], ship_type=ship_type),
            sku_map=dict(rows=n_sku_map[0], distinct_tongtool=n_sku_map[1],
                         distinct_item_code=n_sku_map[2]),
            bom=dict(rows=n_bom[0], boms=n_bom[1], items=n_bom[2]),
            bom_exploded=dict(rows=n_exp[0], roots=n_exp[1], nodes=n_exp[2]),
            item_attr_rows=n_attr,
            destinations_json="out/business_phase/destinations.json：母集 1,328，mapped 1,266 / unmapped 62",
            stock_side=dict(stock_history_skus=len(stock_tt), uom_basis=uom_basis),
        ),
        dn_coverage=dict(
            n_distinct_codes=len(codes),
            by_state=dict(Counter(code_state.values())),
            direct_mapped_codes=len([c for c in codes if c in pairs]),
            direct_mapped_with_stock_hit=len([c for c in codes if c in pairs
                                              and any(s in stock_tt for s in pairs[c])]),
        ),
        evidence=dict(
            n_dns=len(dn_evidence),
            doc_level_all=all(d["doc_level_ok"] for d in dn_evidence),
            qty_level_ok=sum(1 for d in dn_evidence if d["qty_level_ok"] == "yes"),
            qty_level_would_hold=sum(1 for d in dn_evidence if d["qty_level_would_hold"] == "yes"),
            blockers=dict(Counter(d["qty_level_blocker"] for d in dn_evidence)),
        ),
        uom=dict(qty_by_uom={k: round(v, 2) for k, v in qty_by_uom.items()},
                 note="跨 UOM 不合计（个与套不同单位）",
                 non_piece_codes=len(need_convert), need_convert=need_convert,
                 stock_uom_basis=uom_basis),
    )
    (OUT / "map_evidence.json").write_text(
        json.dumps(payload, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")

    # 证据分级明细也落表
    with (OUT / "map_evidence_dn.csv").open("w", encoding="utf-8-sig", newline="") as fh:
        w = csv.DictWriter(fh, fieldnames=list(dn_evidence[0].keys()))
        w.writeheader()
        w.writerows(dn_evidence)

    print(json.dumps({k: payload[k] for k in ("assets", "dn_coverage", "evidence", "uom")},
                     ensure_ascii=False, indent=1)[:3000])


if __name__ == "__main__":
    main()
