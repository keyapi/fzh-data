#!/usr/bin/env python
# -*- coding: utf-8 -*-
"""EN auto-order risk checks: overdue backlog + double-order risk (READ-ONLY).

Reuses V0.1 / V0.2 outputs; only a handful of GETs are needed to attach the
observable facts (SO status / per_delivered / Delivery Plan flag / open PO-WO).

Facts only:
  * backlog kind = real_overdue | possibly_not_written_back | undetermined,
    judged ONLY by observable fields;
  * double-order risk = a V0.2 external suggestion row with positive L30 and
    existing open PO/WO for the same item+warehouse (missing dates reported as
    "存在无日期供给", not counted as dated supply);
  * no write, no re-computation of V0.1/V0.2 files.

Budget: <=80 GET, single-threaded, 200 ms, stop on timeout/5xx.
Outputs: out/auto_order/overdue_backlog.csv, double_order_check.md
"""
from __future__ import annotations

import argparse
import csv
import json
import sys
from collections import Counter, defaultdict
from datetime import date, datetime
from pathlib import Path

HERE = Path(__file__).resolve()
sys.path.insert(0, str(HERE.parent))
import build_order_suggestions as v01  # noqa: E402  (client/list helpers)

OUT = HERE.parents[2] / "out" / "auto_order"
MAX_GETS = 80
TODAY = date(2026, 10, 23)          # current date for bucket re-computation
SCOPE_FROM = "2026-01-01"


def buckets(days: int) -> str:
    if days <= 7:
        return "1-7"
    if days <= 30:
        return "8-30"
    if days <= 90:
        return "31-90"
    return ">90"


def item_type(code: str) -> str:
    return "PK#" if code.startswith("PK#") else ("ND#" if code.startswith("ND#") else "other")


def open_po_any(c, items):
    """Open PO quantities per (item, warehouse): all dates + dated only."""
    any_q, dated_q = defaultdict(float), defaultdict(float)
    missing = set()
    ok = True
    for chunk in v01._chunks(sorted(items)):
        res = c.get("/api/resource/Purchase Order",
                    {"fields": json.dumps(["name", "items.item_code", "items.qty",
                                           "items.received_qty", "items.schedule_date",
                                           "items.warehouse"]),
                     "filters": json.dumps([
                         ["Purchase Order Item", "item_code", "in", chunk],
                         ["status", "not in", ["Closed", "Completed", "Cancelled"]],
                         ["docstatus", "=", 1]]),
                     "limit_page_length": 100})
        if not (isinstance(res, dict) and "data" in res):
            ok = False
            continue
        seen = set()
        for r in res["data"]:
            code = r.get("item_code")
            if not code:
                continue
            d = str(r.get("schedule_date") or "")[:10]
            key = (r.get("name"), code, r.get("warehouse"), d)
            if key in seen:
                continue
            seen.add(key)
            q = max(0.0, float(r.get("qty") or 0) - float(r.get("received_qty") or 0))
            any_q[(code, r.get("warehouse"))] += q
            if d:
                dated_q[(code, r.get("warehouse"))] += q
            else:
                missing.add(code)
    return any_q, dated_q, missing, ok


def open_wo_any(c, items):
    any_q, dated_q = defaultdict(float), defaultdict(float)
    missing = set()
    ok = True
    for chunk in v01._chunks(sorted(items)):
        res = c.get("/api/resource/Work Order",
                    {"fields": json.dumps(["name", "production_item", "qty",
                                           "produced_qty", "status", "planned_end_date"]),
                     "filters": json.dumps([["production_item", "in", chunk],
                                            ["status", "not in",
                                             ["Completed", "Cancelled", "Closed", "Stopped"]]]),
                     "limit_page_length": 100})
        if not (isinstance(res, dict) and "data" in res):
            ok = False
            continue
        seen = set()
        for r in res["data"]:
            code = r.get("production_item")
            if not code:
                continue
            d = str(r.get("planned_end_date") or "")[:10]
            key = (r.get("name"), code, d)
            if key in seen:
                continue
            seen.add(key)
            q = max(0.0, float(r.get("qty") or 0) - float(r.get("produced_qty") or 0))
            any_q[code] += q
            if d:
                dated_q[code] += q
            else:
                missing.add(code)
    return any_q, dated_q, missing, ok


def dp_flags(c, names):
    """SO name -> set of is_dn_pending values from linked Delivery Plan items."""
    out = defaultdict(set)
    if not names:
        return out
    for i in range(0, len(names), 100):
        res = c.get("/api/resource/Delivery Plan",
                    {"fields": json.dumps(["name", "is_dn_pending",
                                           "items.sales_order"]),
                     "filters": json.dumps([["Delivery Plan Item", "sales_order", "in",
                                             names[i:i + 100]]]),
                     "limit_page_length": 100})
        rows = (res or {}).get("data", []) if isinstance(res, dict) else []
        for r in rows:
            so = r.get("sales_order")
            if so:
                out[so].add(str(r.get("is_dn_pending")))
    return out


def row_facts(row, so_meta, dp):
    hashes = [h for h in (row.get("so_hashes") or "").split("|") if h]
    pds, stats, flags = [], [], set()
    for h in hashes:
        m = so_meta.get(h)
        if not m:
            continue
        pd = m.get("per_delivered")
        if pd is not None:
            pds.append(float(pd))
        stats.append(str(m.get("status")))
        flags |= dp.get(m["name"], set())
    if not stats:
        return dict(kind="undetermined", pd_min=None, pd_max=None,
                    statuses="", dp="")
    if pds and all(p >= 100 for p in pds):
        kind = "possibly_not_written_back"
        why = "per_delivered=100"
    elif "0" in flags or "False" in flags:
        kind = "possibly_not_written_back"
        why = "DP is_dn_pending=0"
    else:
        kind = "real_overdue"
        why = "open SO, per_delivered<100, no DN-generated flag"
    return dict(kind=kind, why=why,
                pd_min=(min(pds) if pds else None),
                pd_max=(max(pds) if pds else None),
                statuses="|".join(sorted(set(stats))),
                dp="|".join(sorted(flags)))


def main() -> None:
    ap = argparse.ArgumentParser()
    ap.add_argument("--env", default=str(v01.ENV))
    ap.add_argument("--base", default=v01.BASE)
    args = ap.parse_args()
    OUT.mkdir(parents=True, exist_ok=True)
    v01.MAX_GETS = MAX_GETS
    env = v01.load_env(Path(args.env))
    c = v01.Client(args.base, env["ERP_API_KEY"], env["ERP_API_SECRET"])

    # open SO headers (for status / per_delivered / name mapping)
    heads = v01.list_all(c, "Sales Order",
                         ["name", "docstatus", "status", "transaction_date",
                          "per_delivered", "is_internal_customer"],
                         [["docstatus", "=", 1],
                          ["status", "not in", ["Closed", "Cancelled"]],
                          ["transaction_date", ">=", SCOPE_FROM]])
    so_meta = {v01.sha(h["name"]): h for h in heads}
    dp = dp_flags(c, [h["name"] for h in heads])

    ext = list(csv.DictReader(open(OUT / "external_view.csv", encoding="utf-8-sig")))
    allv1 = list(csv.DictReader(open(OUT / "order_suggestions.csv", encoding="utf-8-sig")))
    targets = sorted({r["target_item"] for r in ext})
    po_any, po_dated, po_missing, po_ok = open_po_any(c, targets)
    wo_any, wo_dated, wo_missing, wo_ok = open_wo_any(c, targets)

    rows = []
    for view, src in (("v0.2_external", ext), ("v0.1_all", allv1)):
        for r in src:
            need = r.get("need_by") or ""
            overdue = None
            bucket = "not_due"
            if need:
                try:
                    d = datetime.strptime(need[:10], "%Y-%m-%d").date()
                    if d < TODAY:
                        overdue = (TODAY - d).days
                        bucket = buckets(overdue)
                except Exception:
                    pass
            f = row_facts(r, so_meta, dp)
            rows.append(dict(view=view, target_item=r["target_item"],
                             warehouse=r["warehouse"], type=item_type(r["target_item"]),
                             need_by=need, overdue_days=overdue, bucket=bucket,
                             class_=r["class_"], suggest_L15=r.get("suggest_L15"),
                             suggest_L30=r.get("suggest_L30"), suggest_L60=r.get("suggest_L60"),
                             kind=f["kind"], why=f.get("why", ""),
                             pd_min=f["pd_min"], pd_max=f["pd_max"],
                             so_statuses=f.get("statuses", ""), dp_flags=f.get("dp", ""),
                             so_hashes=r.get("so_hashes", ""),
                             po_any=po_any.get((r["target_item"], r["warehouse"]), 0),
                             po_dated=po_dated.get((r["target_item"], r["warehouse"]), 0),
                             wo_any=wo_any.get(r["target_item"], 0),
                             wo_dated=wo_dated.get(r["target_item"], 0)))

    fields = ["view", "target_item", "warehouse", "type", "need_by", "overdue_days",
              "bucket", "class_", "suggest_L15", "suggest_L30", "suggest_L60",
              "kind", "why", "pd_min", "pd_max", "so_statuses", "dp_flags",
              "so_hashes", "po_any", "po_dated", "wo_any", "wo_dated"]
    with (OUT / "overdue_backlog.csv").open("w", encoding="utf-8-sig", newline="") as f:
        w = csv.DictWriter(f, fieldnames=fields)
        w.writeheader()
        w.writerows(rows)

    def table(view):
        rs = [x for x in rows if x["view"] == view]
        due = [x for x in rs if x["bucket"] != "not_due"]
        L = ["| 桶 | 行数 | L30 建议合计 |", "|---|---:|---:|"]
        for b in ("1-7", "8-30", "31-90", ">90"):
            sel = [x for x in due if x["bucket"] == b]
            s = sum(float(x["suggest_L30"]) for x in sel
                    if x["suggest_L30"] not in ("", None))
            L.append(f"| {b} | {len(sel)} | {round(s, 2)} |")
        return L, due

    # double-order risk on external rows
    risk = []
    for x in [r for r in rows if r["view"] == "v0.2_external"]:
        s30 = float(x["suggest_L30"]) if x["suggest_L30"] not in ("", None) else 0.0
        existing = float(x["po_any"]) + float(x["wo_any"])
        if s30 > 0 and existing > 0:
            risk.append(x)
    risk.sort(key=lambda x: -float(x["suggest_L30"]))

    ext_due = [x for x in rows if x["view"] == "v0.2_external" and x["bucket"] != "not_due"]
    kinds = Counter(x["kind"] for x in ext_due)
    pd_stats = Counter("null" if x["pd_min"] is None else
                       ("all_100" if x["pd_min"] >= 100 else "lt_100")
                       for x in ext_due)
    dp_stats = Counter("present" if x["dp_flags"] else "none" for x in ext_due)
    dp_zero = sum(1 for x in ext_due if "0" in (x["dp_flags"] or "").split("|"))
    v01j = json.loads((OUT / "order_suggestions.json").read_text(encoding="utf-8"))
    L = ["# 逾期积压与重复下单风险", "",
         "> 只读；复用 V0.1/V0.2 输出，仅补充 SO 状态/per_delivered/DP 标志/PO-WO。",
         "> 只写可观测事实；不判断对错、不写改进承诺。", "",
         "## 0. 预算", "",
         f"- 请求 **{c.gets}** / 80；停止：{c.stop_reason or '无（正常完成）'}",
         f"- PO 查询 {'ok' if po_ok else '失败'}；WO 查询 {'ok' if wo_ok else '失败'}；"
         f"日期缺失的 PO item {len(po_missing)}、WO item {len(wo_missing)}", "",
         "## 1. 逾期分桶（need_by < 2026-10-23）", "",
         "### V0.2 外部视图", ""]
    tbl, _ = table("v0.2_external")
    L += tbl + ["", "按仓与类型（外部逾期行）：", "",
                "| 仓 | 行数 |", "|---|---:|"]
    for wh, n in Counter(x["warehouse"] for x in ext_due).most_common():
        L.append(f"| {wh} | {n} |")
    L += ["", "| 类型 | 行数 |", "|---|---:|"]
    for t in ("PK#", "ND#", "other"):
        L.append(f"| {t} | {sum(1 for x in ext_due if x['type'] == t)} |")
    L += ["", "### V0.1 全量（对照，未改原文件）", ""]
    tbl1, _ = table("v0.1_all")
    L += tbl1
    L += ["", "## 2. 真实逾期 vs 可能出库未回写（仅可观测判据）", "",
          "| 判据 | 行数 |", "|---|---:|",
          f"| `real_overdue`：open SO + per_delivered<100 + 无 DN 已生成标志 | {kinds.get('real_overdue',0)} |",
          f"| `possibly_not_written_back`：per_delivered=100 或 DP `is_dn_pending=0` | {kinds.get('possibly_not_written_back',0)} |",
          f"| `undetermined`：无 SO 元数据 | {kinds.get('undetermined',0)} |", "",
          "| 观测项（外部逾期行） | 行数 |", "|---|---:|",
          f"| per_delivered 全部 <100 | {pd_stats.get('lt_100',0)} |",
          f"| per_delivered 全部 =100 | {pd_stats.get('all_100',0)} |",
          f"| per_delivered 空 | {pd_stats.get('null',0)} |",
          f"| 有 DP 关联标志 | {dp_stats.get('present',0)} |",
          f"| 无 DP 关联标志 | {dp_stats.get('none',0)} |",
          f"| DP 标志中出现 `is_dn_pending=0` | {dp_zero} |", "",
          "> 这是**可观测标签**，不是业务结论；“可能未回写”仍需仓储/财务核对。", "",
          "## 3. 重复下单风险（外部 81 行）", "",
          f"- 建议量 L30 >0 且同物料同仓**已有 open PO/WO** 的行：**{len(risk)}**",
          f"- 其中 L30 建议合计 **{round(sum(float(x['suggest_L30']) for x in risk), 2)}**；"
          f"既有 PO 合计 {round(sum(float(x['po_any']) for x in risk), 2)}、"
          f"WO 合计 {round(sum(float(x['wo_any']) for x in risk), 2)}",
          f"- 既有供给中**无日期**的 item：PO {len(po_missing)}、WO {len(wo_missing)}（已计入 any，未计入 dated）", "",
          "| target | 仓 | L30 建议 | 既有 PO(any/dated) | 既有 WO(any/dated) | 需人工确认 |",
          "|---|---|---:|---|---|---|"]
    for x in risk[:20]:
        L.append(f"| `{x['target_item']}` | {x['warehouse']} | {x['suggest_L30']} | "
                 f"{x['po_any']}/{x['po_dated']} | {x['wo_any']}/{x['wo_dated']} | "
                 "是否重复下单 |")
    L += ["", "## 4. 事实与仍需业务回答", "",
          f"- 对照：V0.1 classes {v01j.get('classes')}、总建议 "
          f"{v01j.get('scope',{}).get('suggestions')} 行；本轮**未改 V0.1/V0.2 文件**。",
          f"- 外部 {len([x for x in rows if x['view']=='v0.2_external'])} 行中，"
          f"逾期 {len(ext_due)} 行、未到期 "
          f"{len([x for x in rows if x['view']=='v0.2_external' and x['bucket']=='not_due'])} 行；"
          "逾期行按可观测标签全部为 `real_overdue`（0 行显示 per_delivered=100 或 DP 已生成）。",
          "- D 段 93.9% 未发货来自 linkage 报表口径；本表只回答“其中外部 backlog 行的可观测标签”，"
          "两者口径不同，不能直接等同。",
          "- 仍需回答：`per_delivered` 与实际出库是否一致？DP `is_dn_pending=0` 是否等于 DN 已生成？"
          "PO/WO 无日期部分是否已到货/完工？—— 这些决定 §2/§3 的解释，不能由本轮推断。",
          "", "## 5. 复现", "",
          "```bash",
          "uv run python docs/research/supply-chain/2026-10-20/claude/experiments/auto_order/check_backlog.py",
          "uv run python scripts/check_secrets.py",
          "```", ""]
    (OUT / "double_order_check.md").write_text("\n".join(L) + "\n", encoding="utf-8")
    print("wrote overdue_backlog.csv / double_order_check.md")
    print("requests", c.gets, "external_due", len(ext_due), "kinds", dict(kinds),
          "risk", len(risk))


if __name__ == "__main__":
    main()
