# -*- coding: utf-8 -*-
"""DN-26-00078 / 出货计划 2609004 缺货修复 — 完整干跑（只读，零写入）

背景
----
DN-26-00078 提交时报「库存不足」36 组。根因：其出货计划 2609004 对应的销售订单 SO-26-00097
的生产计划 PP-26-00033 下的**成品工单被批量删除**（Deleted Document 有台账），导致
`finished_product_work_order` 回填不上 → `_create_manufacture_for_finished_goods` 静默跳过。

本脚本只读生产数据，输出三部分：
  ① 需要在 PP-26-00033 下重建的成品工单（依据被删工单的原始数据）
  ② 每个跟踪单号拟回填的成品工单
  ③ 每个跟踪单号的皮壳库存落在哪个仓（决定能否入库 / 是否需要调拨）

用法:
  python EN_API/dn_stock_fix_dryrun.py                 # prod，默认
  python EN_API/dn_stock_fix_dryrun.py --plan 2609004

输出:
  EN_API/out/dn_stock_fix_dryrun_<ts>.xlsx
"""

from __future__ import annotations

import argparse
import json
import sys
from collections import Counter, defaultdict
from datetime import datetime
from pathlib import Path

sys.stdout.reconfigure(encoding="utf-8")

_DIR = Path(__file__).resolve().parent
sys.path.insert(0, str(_DIR))
from bom_fabric_trim_report import ErpnextClient, load_env, ENV_URLS  # noqa: E402

from openpyxl import Workbook  # noqa: E402
from openpyxl.styles import Alignment, Font, PatternFill  # noqa: E402
from openpyxl.utils import get_column_letter  # noqa: E402

OUT_DIR = _DIR / "out"
PLAN = "2609004"
HALF_WAREHOUSE = "待包装成品仓 - FZH"      # 代码里 KS 前缀跟踪单号固定查这个仓
FG_WAREHOUSE = "成品仓 - FZH"


def gl(client: ErpnextClient, dt: str, fields: list[str], filters: list,
       limit: int = 0, order: str | None = None) -> list[dict]:
    import json as _j
    import requests as _rq
    from urllib.parse import quote
    p = {"fields": _j.dumps(fields), "filters": _j.dumps(filters),
         "limit_page_length": str(limit)}
    if order:
        p["order_by"] = order
    r = client._request("GET", f"/api/resource/{quote(dt, safe='')}", params=p, timeout=300)
    return r.json()["data"]


def main() -> int:
    ap = argparse.ArgumentParser(description=__doc__,
                                 formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("--env", choices=("prod", "test"), default="prod")
    ap.add_argument("--plan", default=PLAN)
    args = ap.parse_args()

    key, sec = load_env(args.env)
    base = ENV_URLS[args.env]
    c = ErpnextClient(base, key, sec)
    print(f"环境: {args.env} ({base})   出货计划: {args.plan}\n")

    # ── 1. 出货计划 → 跟踪单号 ────────────────────────────────────────────
    plan = c.get_doc("Delivery Plan", args.plan)
    qty_rows = plan.get("item_qties") or []
    print(f"[1/5] 计划 {args.plan}: docstatus={plan.get('docstatus')} item_qties={len(qty_rows)} "
          f"计划量={plan.get('total_planned_delivery_qty')} 实配={plan.get('total_assigned_actual_qty')}")
    tns = sorted({(r.get("tracking_number") or "").strip() for r in qty_rows if r.get("tracking_number")})
    print(f"      跟踪单号 {len(tns)} 个")

    trk = {x["name"]: x for x in gl(c, "Tracking Number",
           ["name", "work_order", "item_code", "item_name", "so_materials",
            "finished_product_work_order", "qty"],
           [["name", "in", tns]])}
    missing = [t for t in tns if not (trk.get(t, {}).get("finished_product_work_order") or "").strip()]
    print(f"      其中未回填成品工单: {len(missing)}")

    # 皮壳工单 → 生产计划
    wo_names = sorted({trk[t]["work_order"] for t in missing if trk.get(t, {}).get("work_order")})
    wos = {x["name"]: x for x in gl(c, "Work Order",
           ["name", "production_item", "production_plan", "production_plan_item",
            "production_plan_sub_assembly_item", "qty", "produced_qty", "status", "docstatus"],
           [["name", "in", wo_names]])}
    plans = Counter(w.get("production_plan") for w in wos.values())
    print(f"      皮壳工单 {len(wos)} 个，所属生产计划: {dict(plans)}")
    target_pp = plans.most_common(1)[0][0]
    print(f"      → 目标生产计划: {target_pp}")

    # ── 2. 被删除的成品工单 ───────────────────────────────────────────────
    print(f"\n[2/5] 查 Deleted Document（成品工单）…")
    dels = gl(c, "Deleted Document",
              ["name", "deleted_name", "creation", "owner", "data"],
              [["deleted_doctype", "=", "Work Order"]])
    print(f"      Deleted Document(Work Order) 共 {len(dels)} 条")
    deleted_fg: dict[str, list[dict]] = defaultdict(list)
    for x in dels:
        try:
            d = json.loads(x["data"])
        except Exception:
            continue
        item = str(d.get("production_item") or "")
        if d.get("production_plan") != target_pp or item.startswith(("PK#", "ND#")):
            continue
        deleted_fg[item].append({
            "name": x["deleted_name"], "item": item, "qty": d.get("qty"),
            "plan_item": d.get("production_plan_item"), "bom": d.get("bom_no"),
            "del_at": str(x["creation"])[:19], "del_by": x["owner"],
            "status": d.get("status"), "docstatus": d.get("docstatus"),
        })
    for v in deleted_fg.values():
        v.sort(key=lambda z: z["del_at"])

    # ── 3. 计划里现存的成品工单 ───────────────────────────────────────────
    st, _ = None, None
    exist_wo = gl(c, "Work Order",
                  ["name", "production_item", "qty", "produced_qty", "status", "docstatus", "production_plan_item"],
                  [["production_plan", "=", target_pp]])
    exist_fg = [w for w in exist_wo if not str(w["production_item"]).startswith(("PK#", "ND#"))]
    print(f"      {target_pp} 现存工单 {len(exist_wo)} 个，其中成品 {len(exist_fg)} 个")

    # ── 4. 皮壳库存（按跟踪单号 × 仓库）────────────────────────────────────
    print(f"\n[3/5] 查皮壳 SLE（按跟踪单号维度）…")
    pk_items = sorted({trk[t]["item_code"] for t in missing if trk.get(t)})
    sle = gl(c, "Stock Ledger Entry",
             ["item_code", "warehouse", "tracking_number", "actual_qty"],
             [["item_code", "in", pk_items]])
    print(f"      SLE {len(sle)} 行")
    bal = defaultdict(float)
    for x in sle:
        bal[(x["tracking_number"], x["item_code"], x["warehouse"])] += x["actual_qty"]

    # 现有 FG 工单（全库，用于参考）
    fg_items = sorted({trk[t]["so_materials"] for t in missing if trk.get(t)})
    all_fg_wo = gl(c, "Work Order",
                   ["name", "production_item", "qty", "produced_qty", "status", "docstatus", "production_plan"],
                   [["production_item", "in", fg_items]])

    # ── 5. 组装 ───────────────────────────────────────────────────────────
    print(f"\n[4/5] 组装结论 …")
    wh_list = sorted({w for (_, _, w) in bal})
    rebuild, fill, loc = [], [], []
    for item in fg_items:
        cand = deleted_fg.get(item, [])
        latest = cand[-1] if cand else None
        rebuild.append({
            "item": item, "n_track": sum(1 for t in missing if trk[t]["so_materials"] == item),
            "need_qty": sum(float(trk[t].get("qty") or 0) for t in missing if trk[t]["so_materials"] == item),
            "deleted_count": len(cand),
            "ref_wo": latest["name"] if latest else "",
            "qty": latest["qty"] if latest else "",
            "plan_item": latest["plan_item"] if latest else "",
            "bom": latest["bom"] if latest else "",
            "del_at": latest["del_at"] if latest else "",
            "exist_open": sum(1 for w in exist_fg
                              if w["production_item"] == item
                              and w["status"] not in ("Completed", "Closed", "Cancelled")),
        })
    for t in missing:
        x = trk[t]
        pk = x["item_code"]
        half = bal.get((t, pk, HALF_WAREHOUSE), 0.0)
        others = {w: round(v, 2) for (tt, ii, w), v in bal.items()
                  if tt == t and ii == pk and w != HALF_WAREHOUSE and abs(v) > 1e-6}
        total_other = sum(others.values())
        if half > 0:
            verdict = "可直接入库"
        elif total_other > 0:
            verdict = "需先调拨到待包装成品仓"
        else:
            verdict = "无货"
        fill.append({"tn": t, "pk": pk, "fg": x["so_materials"], "need": x.get("qty"),
                     "pk_wo": x.get("work_order"), "half": half, "verdict": verdict})
        loc.append({"tn": t, "pk": pk, "half": round(half, 2),
                    "others": "; ".join(f"{w}={v:g}" for w, v in sorted(others.items())),
                    "verdict": verdict})

    # ── 6. 输出 ───────────────────────────────────────────────────────────
    print(f"\n[5/5] 写 Excel …")
    OUT_DIR.mkdir(parents=True, exist_ok=True)
    out = OUT_DIR / f"dn_stock_fix_dryrun_{datetime.now():%Y%m%d_%H%M%S}.xlsx"
    wb = Workbook()
    hf = PatternFill("solid", fgColor="DDEBF7")
    red = PatternFill("solid", fgColor="FFC7CE")
    yellow = PatternFill("solid", fgColor="FFEB9C")
    green = PatternFill("solid", fgColor="E2EFDA")

    def sheet(title, headers, rows, widths):
        ws = wb.create_sheet(title)
        ws.append(headers)
        for c_ in ws[1]:
            c_.font = Font(bold=True); c_.fill = hf
            c_.alignment = Alignment(horizontal="center", vertical="center")
        for r in rows:
            ws.append(r)
        for i, w in enumerate(widths, start=1):
            ws.column_dimensions[get_column_letter(i)].width = w
        ws.freeze_panes = "A2"
        if ws.max_row > 1:
            ws.auto_filter.ref = f"A1:{get_column_letter(len(headers))}{ws.max_row}"
        return ws

    ws = wb.active
    ws.title = "汇总"
    ws.append(["DN-26-00078 / 出货计划 2609004 — 缺货修复干跑（只读，未写库）"])
    ws["A1"].font = Font(bold=True, size=12)
    ws.append([])
    ws.append(["出货计划", args.plan, "销售订单", ", ".join(
        sorted({r.get("sales_order") for r in (plan.get("sale_orders") or []) if r.get("sales_order")}))])
    ws.append(["目标是生产计划", target_pp, "生成时间", datetime.now().isoformat(timespec="seconds")])
    ws.append([])
    ws.append(["跟踪单号总数", len(tns), "未回填成品工单", len(missing)])
    ws.append(["需重建的成品工单", len([r for r in rebuild if r["deleted_count"] > 0]),
               "被删成品工单条数", sum(r["deleted_count"] for r in rebuild)])
    vc = Counter(r["verdict"] for r in fill)
    ws.append(["可直接入库", vc.get("可直接入库", 0), "需先调拨", vc.get("需先调拨到待包装成品仓", 0)])
    ws.append(["无货", vc.get("无货", 0), "", ""])
    for c_ in ws[6]:
        c_.font = Font(bold=True); c_.fill = hf
    for col, w in {"A": 24, "B": 14, "C": 20, "D": 46}.items():
        ws.column_dimensions[col].width = w

    sheet("①待重建成品工单",
          ["成品", "跟踪单号数", "需求数", "该成品被删次数", "参考被删工单", "数量", "production_plan_item", "BOM", "最近删除时间", "现存未完结成品工单"],
          [[r["item"], r["n_track"], r["need_qty"], r["deleted_count"], r["ref_wo"], r["qty"],
            r["plan_item"], r["bom"], r["del_at"], r["exist_open"]] for r in sorted(rebuild, key=lambda z: z["item"])],
          [30, 11, 9, 13, 16, 8, 18, 36, 19, 18])

    ws2 = sheet("②跟踪单号回填",
                ["跟踪单号", "皮壳", "销售订单物料(成品)", "单号数量", "皮壳工单"],
                [[r["tn"], r["pk"], r["fg"], r["need"], r["pk_wo"]] for r in fill],
                [20, 32, 30, 10, 16])

    ws3 = sheet("③皮壳库位与可入库性",
                ["跟踪单号", "皮壳", "待包装成品仓(按单号)", "其它仓余额", "判定"],
                [[r["tn"], r["pk"], r["half"], r["others"], r["verdict"]] for r in loc],
                [20, 32, 22, 40, 22])
    for row in ws3.iter_rows(min_row=2, max_row=ws3.max_row, max_col=5):
        v = row[4].value
        fillc = {"可直接入库": green, "需先调拨到待包装成品仓": yellow, "无货": red}.get(v)
        if fillc:
            for c_ in row:
                c_.fill = fillc
    wb.save(str(out))

    print("\n" + "=" * 62)
    print("干跑结论")
    print("=" * 62)
    print(f"  目标生产计划        : {target_pp}")
    print(f"  未回填成品工单的单号: {len(missing)}")
    print(f"  需重建成品工单      : {len([r for r in rebuild if r['deleted_count']])} 种")
    print(f"  判定分布            : {dict(vc)}")
    print(f"\n✓ {out}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
