#!/usr/bin/env python
# -*- coding: utf-8 -*-
"""T6: usability audit of the main table (replenishment_v2.csv).

Three questions, answered from the sources rather than from the table's own claims:
1. Is `可用` the warehouse's OWN stock, or a SKU-level total allocated to it?
   Per SKU: count warehouses with a stock row vs warehouses in the main table, and
   verify every row's `可用` against stock_latest for that exact warehouse.
2. Who owns each missing item, and how many rows / SKUs does each gap cover?
3. What does `item_attr.lead_days` actually cover, and how does it relate to the
   fixed L60/L90/L120 scenarios? (No defaults are treated as measured.)

Read-only inputs: replenishment_v2.csv, decision_v2.csv, destinations.json,
order_store.duckdb.
Outputs: usability_audit.csv, usability_audit.json
"""
from __future__ import annotations

import csv
import hashlib
import json
from collections import Counter, defaultdict
from pathlib import Path

import duckdb

DB_PATH = Path("D:/Work/fzh-order-store/order_store.duckdb")
HERE = Path(__file__).resolve()
CLAUDE_DIR = HERE.parents[2]
OUT = CLAUDE_DIR / "out" / "business_phase"
MAIN = OUT / "replenishment_v2.csv"
DECISION = OUT / "decision_v2.csv"
DEST = OUT / "destinations.json"
OUT_CSV = OUT / "usability_audit.csv"
OUT_JSON = OUT / "usability_audit.json"

OWNERS = [
    ("PO ETA", "采购/供应链", ("PO ETA", "到货日", "will_arrive_date", "ETA 全表缺失")),
    ("在产 WO", "生产/PMC", ("在产 WO", "完工日", "planned_end_date", "work_order")),
    ("UOM/映射", "主数据/EN", ("UOM", "单位", "scope:", "映射")),
    ("MOQ/包装/成本", "采购/财务", ("MOQ", "包装", "成本", "采购约束")),
    ("需求上下界", "业务", ("需求上下界", "G8")),
    ("共享池/跨仓", "供应链管理", ("共享池", "跨仓")),
    ("去重/关单键", "数据/系统", ("去重", "关单键", "重叠")),
]


def sha(p: Path) -> str:
    return hashlib.sha256(p.read_bytes()).hexdigest()


def main() -> None:
    db_hash = sha(DB_PATH)
    main_rows = list(csv.DictReader(open(MAIN, encoding="utf-8-sig")))
    decision = list(csv.DictReader(open(DECISION, encoding="utf-8-sig")))
    if len(decision) != len(main_rows):
        raise SystemExit("decision/main row mismatch")
    dest = {r["sku"]: r for r in json.loads(DEST.read_text(encoding="utf-8"))["rows"]}

    con = duckdb.connect(str(DB_PATH), read_only=True)
    try:
        stock = defaultdict(dict)
        for sku, wh, av, it in con.execute(
                "SELECT sku, warehouse, available, intransit FROM stock_latest").fetchall():
            stock[sku][wh] = dict(available=int(av or 0), intransit=int(it or 0))
        lead = dict(con.execute("SELECT item, lead_days FROM item_attr").fetchall())
        sales3 = defaultdict(lambda: defaultdict(float))
        for sku, ym, wh_raw, q in con.execute("""
                SELECT sku_tongtool, substr(despatch_date,1,7), warehouse, SUM(qty)
                FROM gs_orders
                WHERE substr(despatch_date,1,7) BETWEEN '2026-07' AND '2026-09'
                  AND NOT regexp_matches(lower(platform_sku), '(^|[-_])test([-_]|$)')
                GROUP BY 1,2,3""").fetchall():
            sales3[sku][wh_raw] += float(q)
        wmap = {r[0]: r[1] for r in con.execute(
            "SELECT gs_warehouse, current_warehouse FROM warehouse_map").fetchall()}
    finally:
        con.close()
    if sha(DB_PATH) != db_hash:
        raise SystemExit("DB changed during the run")

    # warehouse counts per SKU (main table vs stock records)
    main_wh = defaultdict(set)
    for r in main_rows:
        if r["状态"] != "C":
            main_wh[r["SKU"]].add(r["仓"])
    stock_wh = {sku: set(d) for sku, d in stock.items()}

    def item_of(sku: str):
        rec = dest.get(sku) or {}
        return rec.get("mapped_item_code")

    out_rows = []
    inv_mismatch = []
    inv_alloc_rows = 0
    demand_alloc_rows = 0
    no_lead_rows = 0
    for r, drow in zip(main_rows, decision):
        sku, wh, status = r["SKU"], r["仓"], r["状态"]
        st = stock.get(sku, {}).get(wh)
        main_avail = r.get("可用", "")
        same_wh = None
        if status != "C":
            if main_avail in ("", None):
                same_wh = "unknown(no_stock_row)"
            elif st is None:
                same_wh = "unknown(no_stock_row)"
                inv_mismatch.append((sku, wh, "row has qty but no stock row"))
            else:
                same_wh = "yes" if int(float(main_avail)) == st["available"] else "NO"
                if same_wh == "NO":
                    inv_mismatch.append((sku, wh, f"main={main_avail} stock={st['available']}"))
                    inv_alloc_rows += 1
        # demand allocation share (SKU-level -> warehouse)
        tot3 = sum(sales3.get(sku, {}).values())
        mine3 = sales3.get(sku, {}).get(wh, 0.0)
        share = (mine3 / tot3) if tot3 > 1e-9 else None
        multi_wh_sales = sum(1 for v in sales3.get(sku, {}).values() if v > 0) > 1
        demand_alloc = ("yes" if (status != "C" and multi_wh_sales) else "no")
        if demand_alloc == "yes":
            demand_alloc_rows += 1
        item = item_of(sku)
        ld = lead.get(item) if item else None
        has_ld = bool(ld is not None and ld > 0)
        if status != "C" and not has_ld:
            no_lead_rows += 1
        # missing categories -> owners
        text = r.get("缺失字段与证据", "") or ""
        cats, owners = [], []
        for name, owner, keys in OWNERS:
            if name == "去重/关单键":
                # the main table carries this as structured columns, not prose
                po_dedup = r.get("PO去重状态", "") or ""
                intr_dedup = r.get("在途去重状态", "") or ""
                if (po_dedup not in ("", "none_recorded")
                        or intr_dedup not in ("", "none_recorded")):
                    cats.append(name)
                    owners.append(owner)
                continue
            if any(k in text for k in keys):
                cats.append(name)
                owners.append(owner)
        out_rows.append(dict(
            SKU=sku, 仓=wh, 状态=status,
            主表可用=main_avail,
            同仓库存行可用=(st["available"] if st else None),
            可用是否同仓事实=same_wh,
            该SKU有库存行仓数=(len(stock_wh.get(sku, set())) if sku in stock else 0),
            该SKU主表仓数=len(main_wh.get(sku, set())),
            库存摊派=("no（逐仓库存行）" if status != "C" else "n/a"),
            需求摊派=demand_alloc,
            需求摊派比例=(round(share, 4) if share is not None else None),
            lead_days=(ld if has_ld else None),
            lead_days来源=("item_attr.lead_days" if has_ld else "无（未用默认值）"),
            缺失类别=("；".join(cats) if cats else ""),
            责任方=("；".join(sorted(set(owners))) if owners else ""),
            事实列="可用(同仓快照)、PO未结(按PO行)、在途(快照)、状态",
            假设列="月需求率/需求P50(分配)、压力情景上限、去重情景批、PR297基线、L60/L90/L120窗口",
        ))

    # ---- aggregate statistics -------------------------------------------
    cat_rows = Counter()
    cat_skus = defaultdict(set)
    for r in out_rows:
        for c in [x for x in (r["缺失类别"] or "").split("；") if x]:
            cat_rows[c] += 1
            cat_skus[c].add(r["SKU"])
    owner_of = {name: owner for name, owner, _ in OWNERS}

    lead_cov = {
        "item_attr_rows_with_lead_days": sum(1 for v in lead.values()
                                              if v is not None and v > 0),
        "items_with_positive_lead_days": sum(1 for v in lead.values()
                                             if v is not None and v > 0),
        "all_skus": len(dest),
        "all_skus_with_lead_days": sum(1 for s in dest
                                       if lead.get(item_of(s) or "", 0) > 0),
        "eligible_skus": sum(1 for s in dest if dest[s]["destination"] == "mapped_eligible"),
        "eligible_skus_with_lead_days": sum(1 for s in dest
                                            if dest[s]["destination"] == "mapped_eligible"
                                            and lead.get(item_of(s) or "", 0) > 0),
        "eligible_rows": sum(1 for r in out_rows if r["状态"] != "C"),
        "eligible_rows_with_lead_days": sum(1 for r in out_rows
                                            if r["状态"] != "C" and r["lead_days"]),
        "value_range": [min(v for v in lead.values() if v and v > 0),
                        max(v for v in lead.values() if v and v > 0)],
        "relation_to_scenarios": ("主表 L60/L90/L120 是固定的日历窗口情景（提前期+复核），"
                                  "不是由 lead_days 推导；lead_days 最大 30 天 < 60 天，"
                                  "不能当端到端提前期实测"),
        "rows_without_lead_days": no_lead_rows,
        "handling": "不填默认值；这些行仍给三情景，但只能读作情景，不能当实测提前期",
    }

    conclusions = dict(
        inventory=dict(
            verdict=("主表“可用”是逐仓库存快照值，不是 SKU 跨仓汇总摊派"
                     if not inv_mismatch else "发现个别行与同仓库存不一致，见 mismatches"),
            rows_checked=sum(1 for r in out_rows if r["状态"] != "C"),
            rows_same_warehouse_fact=sum(1 for r in out_rows
                                         if r["可用是否同仓事实"] == "yes"),
            rows_unknown_no_stock_row=sum(1 for r in out_rows
                                          if r["可用是否同仓事实"] == "unknown(no_stock_row)"),
            rows_allocated=inv_alloc_rows,
            mismatches=inv_mismatch[:20],
            note=("有库存记录的仓数 < 主表仓数 的 SKU，是“有销售但无库存行”的仓，"
                  "其库存未知（null），不是摊派值"),
        ),
        demand=dict(
            allocated_rows=demand_alloc_rows,
            note=("需求是 SKU 级 AutoETS/MA3 预测按该仓近 3 月销量占比分配（比例见每行），"
                  "这部分是**假设**，不是同仓实测需求"),
        ),
        lead_days=lead_cov,
        missing_categories=[dict(category=c, owner=owner_of.get(c, ""),
                                 rows=cat_rows[c], skus=len(cat_skus[c]))
                            for c in [n for n, _, _ in OWNERS]],
        facts_vs_assumptions=dict(
            facts=["可用（同仓 stock_latest 快照）", "在途（同仓快照）",
                   "PO未结（tongtool_po 按行汇总，去重状态另列）",
                   "状态/仓/SKU 键", "lead_days（主数据字段，但那只是配置，不是实测到货）"],
            assumptions=["月需求率 = SKU 预测 × 仓销量占比（分配假设）",
                         "需求 P50 = 窗口权重 × 该率",
                         "压力情景上限 = P50 × (1+MA3 残差系数)，截顶 3×，未验证覆盖",
                         "去重情景批：重复 PO 一笔 / 在途=PO 同批 / 否则两批",
                         "PR297 基线 = 新率 × 覆盖期 − 可用 − 在途",
                         "L60/L90/L120 = 固定日历窗口，不是实测提前期"],
        ),
    )

    with OUT_CSV.open("w", encoding="utf-8-sig", newline="") as f:
        w = csv.DictWriter(f, fieldnames=list(out_rows[0].keys()))
        w.writeheader()
        w.writerows(out_rows)

    OUT_JSON.write_text(json.dumps(dict(
        schema_version="t6_usability_audit/1",
        inputs=dict(main=dict(path=str(MAIN), sha256=sha(MAIN)),
                    decision_sha256=sha(DECISION),
                    db=dict(path=str(DB_PATH), sha256=db_hash)),
        counts=dict(rows=len(out_rows),
                    eligible_rows=sum(1 for r in out_rows if r["状态"] != "C"),
                    skus=len({r["SKU"] for r in out_rows})),
        conclusions=conclusions,
    ), ensure_ascii=False, indent=1) + "\n", encoding="utf-8")

    print(f"wrote {OUT_CSV} ({OUT_CSV.stat().st_size:,} bytes)")
    print(f"wrote {OUT_JSON}")
    print("rows", len(out_rows), "inventory mismatches", len(inv_mismatch),
          "demand allocated rows", demand_alloc_rows)
    for c in conclusions["missing_categories"]:
        print(f"  {c['category']:12s} owner={c['owner']:10s} rows={c['rows']:5d} skus={c['skus']}")
    print("lead_days:", {k: v for k, v in lead_cov.items() if k != "relation_to_scenarios"})


if __name__ == "__main__":
    main()
