#!/usr/bin/env python
# -*- coding: utf-8 -*-
"""EN V0.2: split external demand from internal (pending) SOs — READ-ONLY.

Reuses the V0.1 module (gates + net rules) and reads V0.1 outputs for the
comparison. No V0.1 number is changed; this script only splits and isolates.

External view: `is_internal_customer` false open SOs -> V0.1 three gates and
H=15/30/60 net suggestions (separate, never summed).
Internal ledger: `is_internal_customer` true open SOs -> original lines kept
(hash/status/lines/items/qty/delivery/warehouse), marked
"待业务确认：补货 / 调拨 / 履约"; no replacement order, no deduction, no deletion.

Budget: <=80 GET, single-threaded, 200 ms interval, stop on timeout/5xx.
Outputs: out/auto_order/external_view.csv, internal_pending.csv, split_report.md
"""
from __future__ import annotations

import argparse
import csv
import json
import sys
from collections import Counter, defaultdict
from datetime import datetime
from pathlib import Path

HERE = Path(__file__).resolve()
sys.path.insert(0, str(HERE.parent))
import build_order_suggestions as v01  # noqa: E402  (V0.1 gates/net rules)

CLAUDE_DIR = HERE.parents[2]
OUT = CLAUDE_DIR / "out" / "auto_order"
MAX_GETS = 80
SCOPE_FROM = "2026-01-01"
PENDING = "待业务确认：补货 / 调拨 / 履约"


def main() -> None:
    ap = argparse.ArgumentParser()
    ap.add_argument("--env", default=str(v01.ENV))
    ap.add_argument("--base", default=v01.BASE)
    args = ap.parse_args()
    OUT.mkdir(parents=True, exist_ok=True)
    v01.MAX_GETS = MAX_GETS                        # enforce the V0.2 budget
    env = v01.load_env(Path(args.env))
    c = v01.Client(args.base, env["ERP_API_KEY"], env["ERP_API_SECRET"])
    items_meta, boms, comps = v01.local_data()

    fields = ["name", "docstatus", "status", "transaction_date", "po_no",
              "customer", "is_internal_customer",
              "items.item_code", "items.qty", "items.delivered_qty",
              "items.delivery_date", "items.warehouse", "items.uom",
              "items.stock_uom"]
    filters = [["docstatus", "=", 1],
               ["status", "not in", ["Closed", "Cancelled"]],
               ["transaction_date", ">=", SCOPE_FROM]]
    rows = []
    try:
        rows = v01.list_all(c, "Sales Order", fields, filters)
    except v01.StopRun:
        pass

    # group flattened rows into SOs
    sos = {}
    for r in rows:
        name = r.get("name")
        if not name:
            continue
        s = sos.setdefault(name, dict(name=name, status=r.get("status"),
                                      transaction_date=r.get("transaction_date"),
                                      po_no=(r.get("po_no") or "").strip(),
                                      customer_hash=v01.sha(r.get("customer") or ""),
                                      internal=bool(r.get("is_internal_customer")),
                                      items=[]))
        if r.get("item_code"):
            s["items"].append(dict(
                item=r["item_code"], qty=float(r.get("qty") or 0),
                delivered=float(r.get("delivered_qty") or 0),
                delivery_date=str(r.get("delivery_date") or "")[:10],
                warehouse=r.get("warehouse") or "",
                uom=(r.get("uom") or "").strip(),
                stock_uom=(r.get("stock_uom") or "").strip()))

    external = {n: s for n, s in sos.items() if not s["internal"]}
    internal = {n: s for n, s in sos.items() if s["internal"]}
    def has_demand(s):
        return any(max(0.0, x["qty"] - x["delivered"]) > 0 for x in s["items"])
    internal_active = {n: s for n, s in internal.items() if has_demand(s)}
    external_active = {n: s for n, s in external.items() if has_demand(s)}

    # external demand lines + targets
    lines = []
    for name, s in external.items():
        for idx, it in enumerate(s["items"]):
            unfulfilled = max(0.0, it["qty"] - it["delivered"])
            if unfulfilled <= 0:
                continue
            lines.append(dict(so_hash=v01.sha(name), so_name=name,
                              so_status=s["status"], po_no=s["po_no"],
                              line_idx=idx, **it, unfulfilled=unfulfilled))
    groups = defaultdict(list)
    for ln in lines:
        if ln["po_no"]:
            groups[(ln["po_no"], ln["item"], ln["delivery_date"],
                    ln["warehouse"])].append(ln)
    dup = {id(x) for v in groups.values() if len(v) > 1 for x in v}
    for ln in lines:
        ln["dup_suspect"] = id(ln) in dup

    targets = set()
    for ln in lines:
        code = ln["item"]
        if code.startswith(("PK#", "ND#")) or len(boms.get(code, [])) != 1:
            targets.add(code)
        else:
            targets |= {x[0] for x in comps.get(boms[code][0], [])}
    stock, bin_ok = v01.bin_stock(c, targets)
    po, po_ok, po_missing = v01.open_po(c, targets)
    wo, wo_ok, wo_missing = v01.open_wo(c, targets)

    ext_rows = []
    for ln in lines:
        code = ln["item"]
        rule, tgt = "直接物料", [(code, 1.0, ln["uom"])]
        if not code.startswith(("PK#", "ND#")):
            if len(boms.get(code, [])) == 1:
                comp = comps.get(boms[code][0], [])
                pk = [x for x in comp if x[0].startswith("PK#")]
                nd = [x for x in comp if x[0].startswith("ND#")]
                if pk and nd:
                    rule = "BOM"
                    tgt = [(pk[0][0], pk[0][1], pk[0][2]),
                           (nd[0][0], nd[0][1], nd[0][2])]
                else:
                    rule = "规则未证"
            else:
                rule = "规则未证"
        for target, per, tuom in tgt:
            uom_proven = (ln["uom"] != "" and ln["uom"] == ln["stock_uom"]
                          and ln["uom"] in v01.UOM_OK)
            if rule == "BOM":
                uom_proven = uom_proven and tuom in v01.UOM_OK and float(per or 0) > 0
            mapped = target in items_meta or target.startswith(("PK#", "ND#"))
            item_stock = stock.get(target)
            s = (float(item_stock.get(ln["warehouse"]))
                 if item_stock is not None and ln["warehouse"] in item_stock else None)
            blockers, cls = [], "A"
            if not uom_proven:
                blockers.append("uom_unproven"); cls = "C"
            if not mapped:
                blockers.append("mapping_unproven"); cls = "C"
            if s is None:
                blockers.append("bin_missing")
                cls = "B" if cls == "A" else cls
            if ln["dup_suspect"]:
                blockers.append("duplicate_demand_suspect")
                cls = "B" if cls == "A" else cls
            if not ln["po_no"]:
                blockers.append("dedupe_key_missing")
                cls = "B" if cls == "A" else cls
            if rule == "规则未证":
                blockers.append("bom_rule_unproven")
                cls = "B" if cls == "A" else cls
            if target in po_missing or target in wo_missing:
                blockers.append("supply_date_missing")
                cls = "B" if cls == "A" else cls
            if not ln["delivery_date"]:
                blockers.append("delivery_date_missing")
                cls = "B" if cls == "A" else cls
            nets = {}
            for H in v01.HORIZONS:
                due = ln["unfulfilled"] * per if v01.within(ln["delivery_date"], H) else 0.0
                p = v01.po_h(po, target, ln["warehouse"], H)
                w = v01.wo_h(wo, target, H)
                nets[f"due_L{H}"] = round(due, 2)
                nets[f"po_L{H}"] = round(p, 2)
                nets[f"wo_L{H}"] = round(w, 2)
                nets[f"net_L{H}"] = (round(max(0.0, due - s - p - w), 2)
                                     if s is not None else None)
            ext_rows.append(dict(
                so_hash=ln["so_hash"], so_status=ln["so_status"],
                po_no_hash=v01.sha(ln["po_no"]) if ln["po_no"] else "",
                line_idx=ln["line_idx"], src_item=code, target_item=target,
                rule=rule, warehouse=ln["warehouse"],
                delivery_date=ln["delivery_date"],
                overdue_days=(max(0, (v01.TODAY - datetime.strptime(
                    ln["delivery_date"][:10], "%Y-%m-%d").date()).days)
                    if ln["delivery_date"] else None),
                unfulfilled=round(ln["unfulfilled"], 2), qty_per=per,
                stock=(round(s, 2) if s is not None else None),
                class_=cls, blockers=sorted(set(blockers)), **nets))

    agg = defaultdict(list)
    for r in ext_rows:
        agg[(r["target_item"], r["warehouse"])].append(r)
    ext = []
    for (target, wh), rr in agg.items():
        cls = "C" if any(x["class_"] == "C" for x in rr) else (
            "B" if any(x["class_"] == "B" for x in rr) else "A")
        need = min((x["delivery_date"] for x in rr if x["delivery_date"]), default="")
        overdue = (max(0, (v01.TODAY - datetime.strptime(need, "%Y-%m-%d").date()).days)
                   if need else None)
        stock_v = next((x["stock"] for x in rr if x["stock"] is not None), None)
        out = dict(target_item=target, warehouse=wh, class_=cls, need_by=need,
                   overdue_days=overdue, stock=stock_v, n_lines=len(rr),
                   n_so=len({x["so_hash"] for x in rr}),
                   so_hashes=sorted({x["so_hash"] for x in rr}),
                   rule=rr[0]["rule"], blockers=sorted({b for x in rr for b in x["blockers"]}))
        for H in v01.HORIZONS:
            due = sum(x[f"due_L{H}"] for x in rr)
            p = sum(x[f"po_L{H}"] for x in rr)
            w = sum(x[f"wo_L{H}"] for x in rr)
            out[f"due_L{H}"] = round(due, 2)
            out[f"po_L{H}"] = round(p, 2)
            out[f"wo_L{H}"] = round(w, 2)
            out[f"suggest_L{H}"] = (round(max(0.0, due - stock_v - p - w), 2)
                                    if stock_v is not None else None)
        ext.append(out)

    ext_fields = ["target_item", "warehouse", "class_", "need_by", "overdue_days",
                  "stock", "rule", "n_lines", "n_so",
                  "due_L15", "po_L15", "wo_L15", "suggest_L15",
                  "due_L30", "po_L30", "wo_L30", "suggest_L30",
                  "due_L60", "po_L60", "wo_L60", "suggest_L60",
                  "blockers", "so_hashes"]
    with (OUT / "external_view.csv").open("w", encoding="utf-8-sig", newline="") as f:
        w = csv.DictWriter(f, fieldnames=ext_fields)
        w.writeheader()
        for x in ext:
            w.writerow({**x, "blockers": "|".join(x["blockers"]),
                        "so_hashes": "|".join(x["so_hashes"])})

    # internal ledger: original lines, no change
    int_fields = ["so_hash", "status", "transaction_date", "po_no_hash",
                  "n_lines", "n_items", "total_qty", "total_delivered",
                  "min_delivery", "max_delivery", "warehouses", "materials",
                  "pending_action", "note"]
    with (OUT / "internal_pending.csv").open("w", encoding="utf-8-sig", newline="") as f:
        w = csv.DictWriter(f, fieldnames=int_fields)
        w.writeheader()
        for name, s in sorted(internal_active.items(), key=lambda kv: v01.sha(kv[0])):
            its = s["items"]
            mats = [dict(item=x["item"], qty=round(x["qty"], 2),
                         delivered=round(x["delivered"], 2),
                         delivery_date=x["delivery_date"], warehouse=x["warehouse"])
                    for x in its]
            dates = [x["delivery_date"] for x in its if x["delivery_date"]]
            w.writerow(dict(
                so_hash=v01.sha(name), status=s["status"],
                transaction_date=str(s["transaction_date"] or "")[:10],
                po_no_hash=v01.sha(s["po_no"]) if s["po_no"] else "",
                n_lines=len(its), n_items=len({x["item"] for x in its}),
                total_qty=round(sum(x["qty"] for x in its), 2),
                total_delivered=round(sum(x["delivered"] for x in its), 2),
                min_delivery=min(dates) if dates else "",
                max_delivery=max(dates) if dates else "",
                warehouses="|".join(sorted({x["warehouse"] for x in its})),
                materials=json.dumps(mats, ensure_ascii=False),
                pending_action=PENDING,
                note="原账保留；不生成替代单、不从外部需求扣减、不删除"))

    # V0.1 comparison
    v01j = json.loads((OUT / "order_suggestions.json").read_text(encoding="utf-8"))
    v01_classes = v01j.get("classes", {})
    ext_classes = Counter(x["class_"] for x in ext)
    def total(field):
        vals = [x[field] for x in ext if x[field] is not None]
        return round(sum(vals), 2) if vals else None
    L = ["# V0.2 外部/内部双视图", "",
         "> 只读；预算 ≤80 GET、单线程、200 ms。**V0.1 数字不改，只做拆分与隔离。**", "",
         "## 0. 预算与范围", "",
         f"- 请求 **{c.gets}** / 80；停止：{c.stop_reason or '无（正常完成）'}",
         f"- open SO：**{len(sos)}**（其中 9 个全部行已交付）；**有未履约需求 {len(external_active)+len(internal_active)}**："
         f"外部 **{len(external_active)}** / 内部 **{len(internal_active)}**；"
         f"外部未履约行 {len(lines)} 条；内部原账行 {sum(len(s['items']) for s in internal_active.values())} 条", "",
         "## 1. 外部需求视图（A/B/C 与三 H）", "",
         f"- A/B/C：**{ext_classes.get('A',0)} / {ext_classes.get('B',0)} / {ext_classes.get('C',0)}**"
         f"（{len(ext)} 条 target×仓）",
         f"- 建议量合计（仅非空 target）：L15 **{total('suggest_L15')}** / "
         f"L30 **{total('suggest_L30')}** / L60 **{total('suggest_L60')}**"
         f"（三列独立，不相加；空值=库存未取得）",
         f"- 外部 blockers：{dict(Counter(b for x in ext for b in x['blockers']))}", "",
         "## 2. 内部待确认隔离（原账保留）", "",
         f"- **{len(internal_active)} 个 SO** 原账保留在 `internal_pending.csv`（SO 哈希、行数/物料/数量/交期/仓）。",
         f"- 每行标注：**{PENDING}**；不生成替代单、不从外部需求扣减、不删除。",
         f"- 内部 SO 涉及行数 {sum(len(s['items']) for s in internal_active.values())}；"
         f"另有 {len(internal)-len(internal_active)} 个内部 open SO 全部行已交付，无待确认需求。", "",
         "## 3. 给业务的问题清单（一页）", "",
         "| 问题 | 影响范围 | 需要谁回答 |", "|---|---|---|",
         f"| `is_internal_customer` 是什么语义？（V0.2 按其拆分） | 内部 **{len(internal_active)}** 个 SO；"
         f"外部 **{len(external_active)}** 个 SO；外部建议 {len(ext)} 行 | 业务 / 主数据 |",
         "| `po_no` 缺失的 SO 如何做需求去重？ | V0.1 中 25 个 SO 无键；本视图内外部缺失行见 blockers | 业务 / 数据 |",
         "| 疑似重复需求（同 po_no+物料+交期+仓）如何处理？ | V0.1 16 条建议命中；外部视图 blockers 中列出 | 业务 |",
         "| 252 条 Bin 缺记录的目标仓是哪个？ | 外部视图 `bin_missing` 的 target×仓（CSV 可筛） | 主数据 / 仓储 |",
         "| 357 条 WO 缺完工日怎么补？ | 外部视图 `supply_date_missing`；V0.1 全量 357 条 | 生产 / PMC |", "",
         "## 4. V0.1 数字未变", "",
         f"- V0.1 classes（原文件）：{v01_classes}；总建议 {v01j.get('scope',{}).get('suggestions')} 行。",
         f"- V0.2 只拆分为外部 {len(ext)} 行 + 内部 {len(internal_active)} 个 SO 原账；"
         "未回写、未重算 V0.1 文件。", "",
         "## 5. 看到 / 看不到", "",
         "- 看到：外部需求的 A/B/C 与三 H 建议；内部 SO 原账与待确认标注；问题清单及影响范围。",
         "- 看不到：`is_internal_customer` 的业务语义（只按字段拆分）、替代单/调拨可行性、"
         "Bin/WO 缺失的补齐结果，这些都需要业务/主数据/生产回答。", "",
         "## 6. 复现", "",
         "```bash",
         "uv run python docs/research/supply-chain/2026-10-20/claude/experiments/auto_order/split_external.py",
         "uv run python scripts/check_secrets.py",
         "```", ""]
    (OUT / "split_report.md").write_text("\n".join(L) + "\n", encoding="utf-8")
    print("wrote external_view.csv / internal_pending.csv / split_report.md")
    print("requests", c.gets, "open", len(sos), "external", len(external),
          "internal", len(internal), "ext rows", len(ext),
          "ext classes", dict(ext_classes))


if __name__ == "__main__":
    main()
