# -*- coding: utf-8 -*-
"""SO-26-00097「皮壳误下单 → 改成品」完整链路 DRY-RUN（只读，不写任何数据）。

五步：
  1) SO idx23/24 两行：皮壳码 → 成品码（+ 名称/组/单位/仓 + Item Price 价）
  2) 拟新建 2 张成品工单（模板 = 同计划下已存在、跑通的成品工单 WO-26-03483）
  3) 两张皮壳工单下的全部菲号：so_materials → 成品码；finished_product_work_order → 新成品工单
  4) 皮壳库存移仓：待包装半成品仓 → 待包装成品仓（否则改完 so_materials 后出货计划找不到货）
  5) 风险：产出不足 / 移仓影响面

用法: python EN_API/so2600097_fix_dryrun.py
"""
from __future__ import annotations

import json
import sys
from pathlib import Path

sys.stdout.reconfigure(encoding="utf-8")

from bom_fabric_length_check import load_env, ErpnextClient, ENV_URLS  # noqa: E402

SO = "SO-26-00097"
PK_ITEMS = ["PK#KS0195-DMNJB-58-GREY", "PK#KS0230-WGMSRKQCLG-60-WHITE"]
FG_OF = {
    "PK#KS0195-DMNJB-58-GREY": "KS0195-DMNJB-58-GREY",
    "PK#KS0230-WGMSRKQCLG-60-WHITE": "KS0230-WGMSRKQCLG-60-WHITE",
}
PK_WO = {"PK#KS0195-DMNJB-58-GREY": "WO-26-02880", "PK#KS0230-WGMSRKQCLG-60-WHITE": "WO-26-02877"}
TPL_WO = "WO-26-03483"          # 同计划里跑通的成品工单（模板）
WH_SEMI = "待包装半成品仓 - FZH"
WH_FG = "待包装成品仓 - FZH"


def main() -> int:
    key, sec = load_env("prod")
    c = ErpnextClient(ENV_URLS["prod"], key, sec)
    out: dict = {"so": SO}

    so = c.get_doc("Sales Order", SO)
    out["so_header"] = {"customer": so.get("customer_name"), "status": so.get("status"),
                        "docstatus": so.get("docstatus"), "selling_price_list": so.get("selling_price_list"),
                        "currency": so.get("currency"), "per_delivered": so.get("per_delivered")}
    print(f"== SO {SO} ==\n   customer={so.get('customer_name')} status={so.get('status')} "
          f"docstatus={so.get('docstatus')} price_list={so.get('selling_price_list')} "
          f"per_delivered={so.get('per_delivered')}")

    # ── Step 1：SO 两行 ───────────────────────────────────────────────
    print("\n== Step 1 · SO 两行（皮壳 → 成品） ==")
    # 参照：孪生单 SO-26-00104（同客户/同数量/成品码）——修复的权威目标值
    twin = c.get_doc("Sales Order", "SO-26-00104")
    twin_rows = {r["item_code"]: r for r in twin["items"] if r["item_code"] in FG_OF.values()}
    out["step1_twin_reference"] = {k: {"item_code": v["item_code"], "item_name": v.get("item_name"),
                                       "qty": v["qty"], "rate": v.get("rate"), "warehouse": v.get("warehouse"),
                                       "docstatus": twin["docstatus"], "status": twin["status"]}
                                   for k, v in twin_rows.items()}
    print(f"   参照单 SO-26-00104（{twin['status']}, docstatus={twin['docstatus']}）: "
          + "; ".join(f"{k} qty={v['qty']} rate={v.get('rate')} wh={v.get('warehouse')}" for k, v in twin_rows.items()))

    out["step1"] = []
    for r in so["items"]:
        if r["item_code"] not in PK_ITEMS:
            continue
        fg = FG_OF[r["item_code"]]
        fg_item = c.get_doc("Item", fg)
        prices = c.get_list("Item Price", filters=[["item_code", "=", fg]],
                            fields=["name", "price_list", "customer", "price_list_rate", "currency"],
                            limit_page_length=0)
        pick = next((p for p in prices if p.get("price_list") == so.get("selling_price_list")), None)
        t = twin_rows.get(fg, {})
        out["step1"].append({
            "row_name": r["name"], "idx": r["idx"],
            "item_code": {"now": r["item_code"], "to": fg},
            "item_name": {"now": r.get("item_name"), "to": fg_item.get("item_name")},
            "item_group": {"now": r.get("item_group"), "to": fg_item.get("item_group")},
            "uom": {"now": r.get("uom"), "to": fg_item.get("stock_uom")},
            "stock_uom": {"now": r.get("stock_uom"), "to": fg_item.get("stock_uom")},
            "warehouse": {"now": r.get("warehouse"), "to": "成品仓 - FZH"},
            "qty": r["qty"], "delivered_qty": r.get("delivered_qty"), "billed_amt": r.get("billed_amt"),
            "rate": {"now": r.get("rate"), "item_price": pick["price_list_rate"] if pick else None,
                     "twin_so2600104": t.get("rate")},
            "so_detail": r["name"],
        })
        print(f"   idx={r['idx']} {r['item_code']} → {fg}")
        print(f"      名称 {r.get('item_name')} → {fg_item.get('item_name')}   组 {r.get('item_group')} → {fg_item.get('item_group')}")
        print(f"      仓   {r.get('warehouse')} → 成品仓 - FZH   qty={r['qty']} 已交={r.get('delivered_qty')}")
        print(f"      价   皮壳价(现)={r.get('rate')}  |  Item Price(标准销售)={pick['price_list_rate'] if pick else '无'}  |  孪生单 SO-26-00104={t.get('rate')}")

    # ── Step 2：成品工单模板 ──────────────────────────────────────────
    print("\n== Step 2 · 拟新建成品工单（模板 = %s） ==" % TPL_WO)
    tpl = c.get_doc("Work Order", TPL_WO)
    tpl_keep = ["production_item", "qty", "bom_no", "fg_warehouse", "wip_warehouse", "company",
                "sales_order", "production_plan", "production_plan_item", "source_warehouse",
                "skip_transfer", "use_multi_level_bom", "stock_uom", "conversion_rate"]
    print("   模板字段:", {k: tpl.get(k) for k in tpl_keep})
    out["step2_template"] = {k: tpl.get(k) for k in tpl_keep}

    out["step2_planned"] = []
    for pk in PK_ITEMS:
        fg = FG_OF[pk]
        boms = c.get_list("BOM", filters=[["item", "=", fg], ["docstatus", "=", 1], ["is_default", "=", 1]],
                          fields=["name"], limit_page_length=0)
        pk_wo = c.get_doc("Work Order", PK_WO[pk])
        item = c.get_doc("Item", fg)
        out["step2_planned"].append({
            "production_item": fg, "qty": pk_wo["qty"], "bom_no": boms[0]["name"] if boms else None,
            "fg_warehouse": "成品仓 - FZH", "wip_warehouse": pk_wo.get("wip_warehouse") or "在制品仓 - FZH",
            "company": pk_wo.get("company"), "sales_order": SO,
            "production_plan": pk_wo.get("production_plan"),
            "production_plan_item": pk_wo.get("production_plan_item"),
            "stock_uom": item.get("stock_uom"),
        })
        print(f"   拟建: {fg}  qty={pk_wo['qty']}  bom={boms[0]['name'] if boms else '?'}  "
              f"fg=成品仓 wip={pk_wo.get('wip_warehouse')} SO={SO} PP={pk_wo.get('production_plan')} "
              f"ppi={pk_wo.get('production_plan_item')}")

    # ── Step 3：菲号 ────────────────────────────────────────────────
    print("\n== Step 3 · 菲号字段（so_materials / finished_product_work_order） ==")
    out["step3_tns"] = []
    for pk in PK_ITEMS:
        fg = FG_OF[pk]
        tns = c.get_list("Tracking Number", filters=[["work_order", "=", PK_WO[pk]]],
                         fields=["name", "qty", "so_materials", "finished_product_work_order"],
                         limit_page_length=0)
        tns.sort(key=lambda t: t["name"])
        tot = sum(float(t["qty"] or 0) for t in tns)
        print(f"   {PK_WO[pk]}（{pk}）: {len(tns)} 个菲号, 合计 {tot:.0f}")
        print(f"      so_materials: {pk} → {fg}    fp_wo: {PK_WO[pk]} → 「新成品工单」")
        for t in tns:
            out["step3_tns"].append({"tn": t["name"], "qty": t["qty"], "pk_wo": PK_WO[pk],
                                     "so_materials_now": t["so_materials"], "so_materials_to": fg,
                                     "fp_wo_now": t["finished_product_work_order"], "fp_wo_to": "NEW_FG_WO"})
    print(f"   合计菲号数: {len(out['step3_tns'])}")

    # ── Step 4：移仓清单 ────────────────────────────────────────────
    print(f"\n== Step 4 · 皮壳库存移仓 {WH_SEMI} → {WH_FG} ==")
    out["step4_stock"] = []
    for pk in PK_ITEMS:
        b = c.get_list("Bin", filters=[["item_code", "=", pk]], fields=["warehouse", "actual_qty"],
                       limit_page_length=0)
        wh = {x["warehouse"]: x["actual_qty"] for x in b if x["actual_qty"]}
        print(f"   {pk}: {wh}")
        out["step4_stock"].append({"item": pk, "by_warehouse": wh,
                                   "move_qty": wh.get(WH_SEMI, 0)})

    # ── Step 5：风险 ────────────────────────────────────────────────
    print("\n== Step 5 · 风险点 ==")
    for pk in PK_ITEMS:
        wo = c.get_doc("Work Order", PK_WO[pk])
        gap = float(wo["qty"] or 0) - float(wo["produced_qty"] or 0)
        print(f"   {PK_WO[pk]} 状态={wo['status']} 计划={wo['qty']} 已产={wo['produced_qty']} 缺口={gap:.0f}")
        out.setdefault("step5_risk", []).append(
            {"pk_wo": PK_WO[pk], "status": wo["status"], "qty": wo["qty"],
             "produced": wo["produced_qty"], "gap": gap})

    outp = Path(__file__).resolve().parent / "out" / "so2600097_fix_dryrun.json"
    outp.parent.mkdir(parents=True, exist_ok=True)
    outp.write_text(json.dumps(out, ensure_ascii=False, indent=1, default=str), encoding="utf-8")
    print(f"\n落盘: {outp}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
