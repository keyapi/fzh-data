# -*- coding: utf-8 -*-
"""「皮壳误挂在 SO 上 → 改成品」的通用 DRY-RUN / 盘点工具（只读，不写任何数据）。

背景：出货计划的 item_code 取自**生产计划 po_item.item_code**；仓库与「半成品→成品」组装
判定又取自**跟踪单号 so_materials 的前缀**（PK#/ND#=半成品、KS=成品）。所以 SO 行挂皮壳时，
整条链（出货计划/出库/组装）都会按皮壳走，永远转不出成品。

要改成成品，至少动 6 处（本工具只盘点、不修改）：
  1) Sales Order Item 行：物料码/名称/组/单位/仓库/价格
  2) Production Plan po_item 行：item_code（出货计划 item_code 的真正来源）
  3) 新建「成品工单」（并 submit），供组装用
  4) Tracking Number：so_materials → 成品码；finished_product_work_order → 新成品工单
  5) 皮壳库存移仓：待包装半成品仓 → 待包装成品仓（否则改完前缀后出货计划按 KS 去成品仓找不到货）
  6) 风险：产出缺口 / 成品 BOM 缺失 / SO 合计重算

用法:
  python EN_API/pk_to_fg_fix.py dry-run --site prod --so SO-26-00097 ^
        --pairs "PK#KS0195-DMNJB-58-GREY=KS0195-DMNJB-58-GREY,PK#KS0230-WGMSRKQCLG-60-WHITE=KS0230-WGMSRKQCLG-60-WHITE"
  python EN_API/pk_to_fg_fix.py dry-run --site test --so SO-26-00048 \
        --pairs "PK#KS0002-DL-100-GREY=KS0002-DL-100-GREY"
"""
from __future__ import annotations

import argparse
import json
import sys
from datetime import datetime
from pathlib import Path

sys.stdout.reconfigure(encoding="utf-8")

from bom_fabric_length_check import ENV_KEYS, ENV_URLS, ErpnextClient, load_env  # noqa: E402

WH_SEMI_PACK = "待包装半成品仓 - FZH"
WH_FG_PACK = "待包装成品仓 - FZH"
WH_FG = "成品仓 - FZH"
WH_WIP = "在制品仓 - FZH"


def parse_pairs(s: str) -> dict[str, str]:
    out = {}
    for part in (s or "").split(","):
        part = part.strip()
        if part:
            a, _, b = part.partition("=")
            out[a.strip()] = b.strip()
    return out


def dry_run(c: ErpnextClient, so_name: str, pairs: dict[str, str]) -> dict:
    so = c.get_doc("Sales Order", so_name)
    res: dict = {"site": c.base_url, "so": so_name,
                 "taken_at": datetime.now().isoformat(timespec="seconds"),
                 "so_header": {"customer": so.get("customer_name"), "status": so.get("status"),
                               "docstatus": so.get("docstatus"), "price_list": so.get("selling_price_list"),
                               "per_delivered": so.get("per_delivered")}}

    # ── 1) SO 行 ─────────────────────────────────────────────────────
    print(f"\n===== SO {so_name} · customer={so.get('customer_name')} status={so.get('status')} "
          f"ds={so.get('docstatus')} per_delivered={so.get('per_delivered')} =====")
    print("\n[1] Sales Order Item 行")
    res["step1_so_rows"] = []
    for r in so["items"]:
        if r["item_code"] not in pairs:
            continue
        fg = pairs[r["item_code"]]
        fg_item = c.get_doc("Item", fg)
        prices = c.get_list("Item Price", filters=[["item_code", "=", fg]],
                            fields=["price_list", "customer", "price_list_rate"], limit_page_length=0)
        pick = next((p for p in prices if p.get("price_list") == so.get("selling_price_list")), None)
        row = {"row_name": r["name"], "idx": r["idx"],
               "item_code": [r["item_code"], fg],
               "item_name": [r.get("item_name"), fg_item.get("item_name")],
               "item_group": [r.get("item_group"), fg_item.get("item_group")],
               "uom": [r.get("uom"), fg_item.get("stock_uom")],
               "warehouse": [r.get("warehouse"), WH_FG],
               "qty": r["qty"], "delivered_qty": r.get("delivered_qty"), "billed_amt": r.get("billed_amt"),
               "rate_now": r.get("rate"), "rate_item_price": pick["price_list_rate"] if pick else None}
        res["step1_so_rows"].append(row)
        print(f"   idx={r['idx']} {r['item_code']} → {fg} | 仓 {r.get('warehouse')} → {WH_FG} | "
              f"qty={r['qty']} 已交={r.get('delivered_qty')} | rate {r.get('rate')} → "
              f"ItemPrice={row['rate_item_price'] if row['rate_item_price'] is not None else '无'}")

    # ── 2) 皮壳工单 → PP po_item ─────────────────────────────────────
    print("\n[2] Production Plan po_item（出货计划 item_code 的真正来源）")
    res["step2_pp_rows"] = []
    res["step2_work_orders"] = []
    for pk, fg in pairs.items():
        wos = c.get_list("Work Order", filters=[["production_item", "=", pk], ["sales_order", "=", so_name]],
                         fields=["name", "production_item", "qty", "produced_qty", "status", "docstatus",
                                 "production_plan", "production_plan_item", "fg_warehouse"],
                         limit_page_length=0)
        for w in wos:
            res["step2_work_orders"].append(w)
            print(f"   皮壳工单 {w['name']} qty={w['qty']} produced={w['produced_qty']} {w['status']} "
                  f"ds={w['docstatus']} pp={w['production_plan']} ppi={w['production_plan_item']} fg={w['fg_warehouse']}")
            if w["production_plan"] and w["production_plan_item"]:
                pp = c.get_doc("Production Plan", w["production_plan"])
                po = next((x for x in pp.get("po_items", []) if x["name"] == w["production_plan_item"]), None)
                if po:
                    fg_item = c.get_doc("Item", fg)
                    res["step2_pp_rows"].append({
                        "pp": pp["name"], "po_row_name": po["name"], "docstatus": pp.get("docstatus"),
                        "item_code": [po.get("item_code"), fg],
                        "item_name": [po.get("item_name"), fg_item.get("item_name")],
                        "planned_qty": po.get("planned_qty"), "sales_order": po.get("sales_order"),
                        "sales_order_item": po.get("sales_order_item")})
                    print(f"      → PP {pp['name']}(ds={pp.get('docstatus')}) po_item {po['name']}: "
                          f"{po.get('item_code')} → {fg}  planned={po.get('planned_qty')} "
                          f"so_row={po.get('sales_order_item')}")

    # ── 3) 成品工单 & BOM ───────────────────────────────────────────
    print("\n[3] 拟新建成品工单 / 成品默认 BOM")
    res["step3_fg_wo"] = []
    for pk, fg in pairs.items():
        boms = c.get_list("BOM", filters=[["item", "=", fg], ["docstatus", "=", 1], ["is_default", "=", 1]],
                          fields=["name", "quantity"], limit_page_length=0)
        fg_item = c.get_doc("Item", fg)
        item = {"fg": fg, "bom": boms[0]["name"] if boms else None,
                "fg_warehouse": WH_FG, "wip_warehouse": WH_WIP, "stock_uom": fg_item.get("stock_uom")}
        res["step3_fg_wo"].append(item)
        print(f"   {fg}: 默认BOM={item['bom'] or '⚠ 无（需先建）'} uom={item['stock_uom']} "
              f"fg={WH_FG} wip={WH_WIP}")

    # ── 4) 菲号 ─────────────────────────────────────────────────────
    print("\n[4] Tracking Number（so_materials / finished_product_work_order）")
    res["step4_tns"] = []
    for pk, fg in pairs.items():
        pk_wos = [w["name"] for w in res["step2_work_orders"] if w.get("production_item") == pk]
        tns = c.get_list("Tracking Number", filters=[["work_order", "in", pk_wos or ["__none__"]]],
                         fields=["name", "work_order", "qty", "item_code", "so_materials",
                                 "finished_product_work_order"], limit_page_length=0)
        print(f"   {pk} 名下菲号 {len(tns)} 个，合计 {sum(float(t['qty'] or 0) for t in tns):.0f}")
        for t in sorted(tns, key=lambda x: x["name"]):
            res["step4_tns"].append({"tn": t["name"], "work_order": t["work_order"], "qty": t["qty"],
                                     "so_materials": [t["so_materials"], fg],
                                     "fp_wo": [t["finished_product_work_order"], "NEW_FG_WO"]})

    # ── 5) 皮壳库存 / 移仓 ──────────────────────────────────────────
    print(f"\n[5] 皮壳库存移仓 {WH_SEMI_PACK} → {WH_FG_PACK}")
    res["step5_stock"] = []
    for pk, fg in pairs.items():
        b = c.get_list("Bin", filters=[["item_code", "=", pk]], fields=["warehouse", "actual_qty"],
                       limit_page_length=0)
        wh = {x["warehouse"]: x["actual_qty"] for x in b if x["actual_qty"]}
        res["step5_stock"].append({"item": pk, "by_warehouse": wh, "move_from_pack_semi": wh.get(WH_SEMI_PACK, 0)})
        print(f"   {pk}: {wh}  → 拟移 {wh.get(WH_SEMI_PACK, 0)}")

    # ── 6) 风险 ─────────────────────────────────────────────────────
    print("\n[6] 风险点")
    res["step6_risk"] = []
    for w in res["step2_work_orders"]:
        gap = float(w["qty"] or 0) - float(w["produced_qty"] or 0)
        note = []
        if gap > 0:
            note.append(f"产出缺口 {gap:.0f}")
        if w["status"] not in ("Completed",):
            note.append(f"工单未收尾({w['status']})")
        if w["fg_warehouse"] != WH_FG_PACK:
            note.append(f"皮壳收货仓={w['fg_warehouse']}（正常样板为 {WH_FG_PACK}）")
        res["step6_risk"].append({"wo": w["name"], "notes": note})
        print(f"   {w['name']}: {note or '无'}")
    return res


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("action", choices=("dry-run",))
    ap.add_argument("--site", choices=("prod", "test"), default="prod")
    ap.add_argument("--so", required=True)
    ap.add_argument("--pairs", required=True, help='如 "PK#A=KSA,PK#B=KSB"')
    ap.add_argument("--out-dir", type=Path, default=Path(__file__).resolve().parent / "out")
    args = ap.parse_args()

    key, sec = load_env(args.site)
    if not key or not sec:
        print(f"✗ 缺 {ENV_KEYS[args.site]} 凭证")
        return 1
    c = ErpnextClient(ENV_URLS[args.site], key, sec)
    res = dry_run(c, args.so, parse_pairs(args.pairs))
    args.out_dir.mkdir(parents=True, exist_ok=True)
    p = args.out_dir / f"pk_to_fg_dryrun_{args.site}_{args.so}.json"
    p.write_text(json.dumps(res, ensure_ascii=False, indent=1, default=str), encoding="utf-8")
    print(f"\n落盘: {p}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
