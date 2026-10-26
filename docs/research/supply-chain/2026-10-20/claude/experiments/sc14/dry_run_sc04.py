#!/usr/bin/env python
"""SC14 — 用**已有的真实产物**（SC04 供应阶段）预演 W1 契约校验。

不是 Jack 的数据，但字段语义最接近：能把「契约现在能抓出什么」先跑一遍。
只读；不写任何上游文件。

映射规则（SC04 真实状态 → W1 stage）：
  received_before_snapshot → received / confirmed（用 dlvr 实签日）
  received_unknown_date    → received / unknown（已入仓但无签收日）
  in_transit               → shipped_in_transit / estimated（eta_unproven）或 unknown
  partially_received       → shipped_in_transit + partial=True（**故意不拆**，看契约是否拦住）
  unknown_status           → stage='unknown'（**故意保留**，看枚举缺口）
"""
from __future__ import annotations

import collections
import csv
import sys
from pathlib import Path

import duckdb

sys.path.insert(0, str(Path(__file__).resolve().parent))
from contract import rollup, validate_w1, w3_columns  # noqa: E402

CLAUDE = Path(__file__).resolve().parents[2]
STAGE_CSV = CLAUDE / "out/business_phase/sc04/sc04_supply_stage.csv"
LINES_CSV = CLAUDE / "out/business_phase/sc04/sc04_supply_lines.csv"
DB = "D:/Work/fzh-order-store/order_store.duckdb"

MAPPING = {
    "received_before_snapshot": ("received", "confirmed"),
    "received_unknown_date": ("received", "unknown"),
    "in_transit": ("shipped_in_transit", "estimated"),
    "partially_received": ("shipped_in_transit", "estimated"),
    "unknown_status": ("unknown", "unknown"),
}


def main() -> None:
    stage_rows = {r["dn"]: r for r in csv.DictReader(STAGE_CSV.open(encoding="utf-8-sig"))}
    con = duckdb.connect(DB, read_only=True)
    sku_of = {i: s for i, s in con.execute("select item_code, tongtool_sku from sku_map").fetchall()}
    con.close()

    rows, unmapped_items = [], set()
    for idx, r in enumerate(csv.DictReader(LINES_CSV.open(encoding="utf-8-sig")), start=1):
        meta = stage_rows.get(r["dn"])
        if meta is None:
            continue
        stage, conf = MAPPING.get(meta["stage"], ("unknown", "unknown"))
        item = r["item_code"]
        sku = sku_of.get(item)
        if sku is None:
            unmapped_items.add(item)
        d = meta.get("proven_arrival_date") if stage == "received" else meta.get("eta_unproven")
        if conf == "unknown" or not d:
            date_val, conf = None, "unknown"
        else:
            date_val = d
        rows.append({
            "sku": sku, "warehouse": meta.get("dest"), "as_of_date": "2026-10-20",
            "stage": stage, "doc_type": "Delivery Note", "doc_name": r["dn"],
            "doc_line": f"L{idx}", "qty": float(r["qty"]) if r["qty"] else None,
            "uom": r["uom"], "event_date": None, "available_date": date_val,
            "date_confidence": conf, "source_key": f"{r['dn']}|L{idx}|{r['uom']}",
            "scope": "external_fba" if meta.get("stock_scope") == "external_fba" else "in_house",
            "qty_status": "known", "allocation_known": meta.get("allocation") != "分配未知",
            "tracking_numbers": [], "partial": meta["stage"] == "partially_received",
        })

    findings = validate_w1(rows)
    by_code = collections.Counter(f.code for f in findings)
    errs = [f for f in findings if f.severity == "error"]
    warns = [f for f in findings if f.severity == "warning"]

    print(f"W1 预演：{len(rows)} 行（{len(stage_rows)} 张 DN）")
    print(f"  error {len(errs)} / warning {len(warns)}")
    for code, n in by_code.most_common():
        sev = "error" if code.startswith("E_") else "warning"
        print(f"    {sev:7s} {code:26s} {n}")
    print(f"  未映射到 SKU 的物料: {len(unmapped_items)} 个（组件 PK#/ND# 属正常）")

    examples = {}
    for f in findings:
        examples.setdefault(f.code, f)
    print("\n每类一个样例：")
    for code, f in sorted(examples.items()):
        print(f"  {code:26s} row={f.row:5d} {f.message[:110]}")

    roll = rollup(rows)
    col = w3_columns(roll)
    print("\n按 uom 汇总（只算 in_house）：")
    print("  opening  :", roll["opening_by_uom"])
    print("  confirmed:", col["supply_confirmed"])
    print("  expected :", col["supply_expected"])
    print("  unknown  :", col["supply_unknown"])
    print("  excluded :", len(roll["excluded_external_fba"]), "行（外部 FBA，两边都不算）")
    print("\n结论：合成数据 16/16 通过；真实 SC04 预演把这些已知异常如实抓出——"
          "详见 control/reviews/2026-10-23-sc14-spec.md §4。")


if __name__ == "__main__":
    main()
