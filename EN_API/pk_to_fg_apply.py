# -*- coding: utf-8 -*-
"""「皮壳→成品」修复的**写操作**执行器（payload 驱动，一步一 commit，只跑明确指定的动作）。

配合 pk_to_fg_fix.py（只读 dry-run）使用。所有写入都经一个临时 zz_ Server Script 执行，
动作与回报分离、每步显式 commit。先在 test 排练，再上 prod。

动作（--step）：
  snapshot   写前快照（SO / PP / WO / TN / Bin 落 JSON）
  so         Sales Order Item 行：改物料码/名称/组/单位/仓 + 重算单据合计
  pp         Production Plan po_item 行：改 item_code
  bom        新建成品默认 BOM（仅排练环境需要）
  fgwo       新建并提交成品工单
  tn         Tracking Number：so_materials / finished_product_work_order
  transfer   皮壳库存移仓 待包装半成品仓 → 待包装成品仓（带菲号）
  verify     回读比对

用法:
  python EN_API/pk_to_fg_apply.py snapshot --site test --job test
  python EN_API/pk_to_fg_apply.py apply --site test --job test --step bom
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

JOBS = {
    "test": {
        "so": "SO-26-00048",
        "pairs": {"PK#KS0002-DL-100-GREY": "KS0002-DL-100-GREY"},
        "company": "FZH",
        "set_price": False,          # 排练不改价
    },
    "prod": {
        "so": "SO-26-00097",
        "pairs": {"PK#KS0195-DMNJB-58-GREY": "KS0195-DMNJB-58-GREY",
                  "PK#KS0230-WGMSRKQCLG-60-WHITE": "KS0230-WGMSRKQCLG-60-WHITE"},
        "company": "FZH",
        "target_rate": {"KS0195-DMNJB-58-GREY": 0.0, "KS0230-WGMSRKQCLG-60-WHITE": 123.055},
        "set_price": True,
    },
}

SCRIPT_NAME = "zz_pk_to_fg_apply"
API_METHOD = SCRIPT_NAME

SERVER_SCRIPT = '''mode = frappe.form_dict.get("mode")
p = json.loads(frappe.form_dict.get("payload") or "{}")
out = {"mode": mode}

if mode == "set_values":
    for row in (p.get("rows") or []):
        frappe.db.set_value(row["dt"], row["name"], row["values"])
    frappe.db.commit()
    out["updated"] = len(p.get("rows") or [])

elif mode == "recalc_so":
    doc = frappe.get_doc("Sales Order", p["so"])
    doc.run_method("calculate_taxes_and_totals")
    heads = ["total", "net_total", "base_total", "base_net_total", "grand_total", "base_grand_total",
             "rounded_total", "base_rounded_total", "in_words", "base_in_words",
             "total_taxes_and_charges", "base_total_taxes_and_charges",
             "rounding_adjustment", "base_rounding_adjustment"]
    frappe.db.set_value("Sales Order", p["so"], {k: doc.get(k) for k in heads})
    frappe.db.commit()
    out["totals"] = {k: doc.get(k) for k in ("total", "net_total", "grand_total", "rounded_total")}

elif mode == "new_bom":
    bom = frappe.new_doc("BOM")
    bom.item = p["item"]
    bom.quantity = p.get("quantity") or 1
    bom.company = p.get("company") or "FZH"
    bom.is_active = 1
    bom.is_default = 1
    for r in (p.get("items") or []):
        bom.append("items", {"item_code": r["item_code"], "qty": r["qty"]})
    bom.insert(ignore_permissions=True)
    bom.submit()
    frappe.db.commit()
    out["bom"] = bom.name

elif mode == "new_wo":
    wo = frappe.new_doc("Work Order")
    for k, v in (p.get("wo") or {}).items():
        wo.set(k, v)
    wo.insert(ignore_permissions=True)
    wo.submit()
    frappe.db.commit()
    out["wo"] = wo.name
    out["wo_status"] = wo.status

elif mode == "new_se":
    se = frappe.new_doc("Stock Entry")
    se.purpose = p["purpose"]
    se.company = p.get("company") or "FZH"
    if p.get("tracking_number"):
        se.tracking_number = p["tracking_number"]
    for r in (p.get("rows") or []):
        se.append("items", {"item_code": r["item_code"], "qty": r["qty"],
                            "s_warehouse": r.get("s_warehouse"), "t_warehouse": r.get("t_warehouse"),
                            "stock_tracking_number": r.get("tracking_number"),
                            "to_stock_tracking_number": r.get("tracking_number"),
                            "tracking_number": r.get("tracking_number")})
    se.set_stock_entry_type()
    se.insert(ignore_permissions=True)
    se.submit()
    frappe.db.commit()
    out["se"] = se.name
    out["se_type"] = se.stock_entry_type

elif mode == "append_child":
    names = []
    for r in (p.get("rows") or []):
        d = frappe.get_doc(r)
        d.insert(ignore_permissions=True)
        if p.get("docstatus"):
            frappe.db.set_value(d.doctype, d.name, "docstatus", p["docstatus"])
        names.append(d.name)
    frappe.db.commit()
    out["names"] = names
    out["count"] = len(names)

elif mode == "delete_child":
    done = []
    for nm in (p.get("names") or []):
        dt = p["dt"]
        if frappe.db.exists(dt, nm):
            frappe.delete_doc(dt, nm, force=True, ignore_permissions=True)
            done.append(nm)
    frappe.db.commit()
    out["deleted"] = done

elif mode == "cancel_doc":
    done = []
    errs = []
    for nm in (p.get("names") or []):
        dt = p.get("dt") or "Stock Entry"
        try:
            d = frappe.get_doc(dt, nm)
            if d.docstatus == 1:
                d.cancel()
                done.append(nm)
            else:
                errs.append({"name": nm, "why": "docstatus=%s" % d.docstatus})
        except Exception as exc:
            errs.append({"name": nm, "why": str(exc)[:200]})
    frappe.db.commit()
    out["cancelled"] = done
    out["errors"] = errs

frappe.response["data"] = out
'''


def call(client: ErpnextClient, **data):
    r = client._request("POST", f"/api/method/{API_METHOD}", data=data, timeout=(30, 600))
    body = r.json()
    for k in ("message", "data"):
        if k in body:
            return body[k]
    return body


def ensure_script(client: ErpnextClient) -> None:
    try:
        client._request("DELETE", f"/api/resource/Server Script/{SCRIPT_NAME}", timeout=60, retries=0)
    except Exception:  # noqa: BLE001
        pass
    client._request("POST", "/api/resource/Server Script",
                    json={"name": SCRIPT_NAME, "script_type": "API", "api_method": API_METHOD,
                          "script": SERVER_SCRIPT, "allow_guest": 0, "disabled": 0}, timeout=60)


def drop_script(client: ErpnextClient) -> None:
    try:
        client._request("DELETE", f"/api/resource/Server Script/{SCRIPT_NAME}", timeout=60, retries=0)
    except Exception:  # noqa: BLE001
        pass
    try:
        client._request("GET", f"/api/resource/Server Script/{SCRIPT_NAME}", timeout=60, retries=0)
        print(f"  ⚠ {SCRIPT_NAME} 删除后仍能读到")
    except Exception:  # noqa: BLE001
        print(f"  已删除 {SCRIPT_NAME}（残留 0）")


def run(client: ErpnextClient, mode: str, payload: dict) -> dict:
    ensure_script(client)
    try:
        return call(client, mode=mode, payload=json.dumps(payload, ensure_ascii=False))
    finally:
        drop_script(client)


def build_context(client: ErpnextClient, job: dict) -> dict:
    """把一次修复所需的对象（SO 行 / PP po_item / 皮壳工单 / 菲号 / 成品 BOM）解析成 payload 片段。"""
    so_name = job["so"]
    so = client.get_doc("Sales Order", so_name)
    ctx: dict = {"so": so_name, "pairs": job["pairs"], "company": job.get("company") or "FZH"}

    so_rows = []
    for r in so["items"]:
        cur = r["item_code"]
        if cur in job["pairs"]:
            pk = cur
        else:
            pk = next((k for k, v in job["pairs"].items() if v == cur), None)
        if not pk:
            continue
        fg = job["pairs"][pk]
        fg_item = client.get_doc("Item", fg)
        vals = {"item_code": fg, "item_name": fg_item.get("item_name"),
                "description": fg_item.get("item_name"),
                "item_group": fg_item.get("item_group"), "uom": fg_item.get("stock_uom"),
                "stock_uom": fg_item.get("stock_uom"), "warehouse": WH_FG}
        boms = client.get_list("BOM", filters=[["item", "=", fg], ["docstatus", "=", 1],
                                               ["is_default", "=", 1]], fields=["name"], limit_page_length=0)
        if boms:
            vals["bom_no"] = boms[0]["name"]
        if job.get("set_price"):
            rate = (job.get("target_rate") or {}).get(fg)
            if rate is not None:
                vals.update({"price_list_rate": rate, "rate": rate, "net_rate": rate})
        so_rows.append({"row_name": r["name"], "idx": r["idx"], "pk": pk, "fg": fg,
                        "qty": float(r["qty"] or 0), "values": vals})
    ctx["so_rows"] = so_rows

    wos, pp_rows = [], []
    for pk in job["pairs"]:
        for w in client.get_list("Work Order",
                                 filters=[["production_item", "=", pk], ["sales_order", "=", so_name]],
                                 fields=["name", "production_item", "qty", "produced_qty", "status",
                                         "docstatus", "production_plan", "production_plan_item",
                                         "fg_warehouse", "wip_warehouse", "company", "bom_no",
                                         "stock_uom", "planned_start_date", "sales_order_item"],
                                 limit_page_length=0):
            wos.append(w)
            if w["production_plan"] and w["production_plan_item"]:
                pp = client.get_doc("Production Plan", w["production_plan"])
                po = next((x for x in (pp.get("po_items") or [])
                           if x["name"] == w["production_plan_item"]), None)
                if po:
                    fg = job["pairs"][pk]
                    fg_item = client.get_doc("Item", fg)
                    boms = client.get_list("BOM", filters=[["item", "=", fg], ["docstatus", "=", 1],
                                                           ["is_default", "=", 1]], fields=["name"],
                                           limit_page_length=0)
                    vals = {"item_code": fg,
                            "custom_item_name": fg_item.get("item_name"),
                            "description": "成品 " + (fg_item.get("item_name") or ""),
                            "warehouse": WH_FG}
                    if boms:
                        vals["bom_no"] = boms[0]["name"]
                    pp_rows.append({"pp": pp["name"], "row_name": po["name"], "pk": pk, "fg": fg,
                                    "values": vals})
    ctx["work_orders"] = wos
    ctx["pp_rows"] = pp_rows

    tns = []
    for w in wos:
        for t in client.get_list("Tracking Number", filters=[["work_order", "=", w["name"]]],
                                 fields=["name", "work_order", "qty", "so_materials",
                                         "finished_product_work_order"],
                                 limit_page_length=0):
            tns.append(t)
    ctx["tns"] = tns

    fg_wos = []
    for fg in job["pairs"].values():
        for w in client.get_list("Work Order", filters=[["production_item", "=", fg], ["sales_order", "=", so_name]],
                                 fields=["name", "production_item", "qty", "produced_qty", "status", "docstatus",
                                         "production_plan", "production_plan_item",
                                         "production_plan_sub_assembly_item"], limit_page_length=0):
            fg_wos.append(w)
    ctx["fg_wos"] = fg_wos
    return ctx


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("action", choices=("snapshot", "apply", "verify", "show"))
    ap.add_argument("--site", choices=("prod", "test"), default="test")
    ap.add_argument("--job", choices=tuple(JOBS), required=True)
    ap.add_argument("--step", choices=("so", "pp", "bom", "fgwo", "tn", "transfer", "subrows", "wolink"),
                    default=None)
    ap.add_argument("--fg-wo-map", default="", help='{"成品码":"成品工单名"} 供 tn 步骤用')
    ap.add_argument("--bom-map", default="", help='{"成品码":"BOM名"} 供 fgwo 步骤用（缺省取默认BOM）')
    ap.add_argument("--out-dir", type=Path, default=Path(__file__).resolve().parent / "out")
    args = ap.parse_args()

    key, sec = load_env(args.site)
    if not key or not sec:
        print(f"✗ 缺 {ENV_KEYS[args.site]} 凭证")
        return 1
    client = ErpnextClient(ENV_URLS[args.site], key, sec)
    job = JOBS[args.job]
    ctx = build_context(client, job)

    print(f"[{args.site}] job={args.job} SO={job['so']}")
    print(f"  SO 行: {[(r['idx'], r['pk'], '→', r['fg']) for r in ctx['so_rows']]}")
    print(f"  皮壳工单: {[(w['name'], w['status'], w['produced_qty']) for w in ctx['work_orders']]}")
    print(f"  PP po_item: {[(r['pp'], r['row_name'], r['pk'], '→', r['fg']) for r in ctx['pp_rows']]}")
    print(f"  菲号: {len(ctx['tns'])} 个, 合计 {sum(float(t['qty'] or 0) for t in ctx['tns']):.0f}")

    args.out_dir.mkdir(parents=True, exist_ok=True)
    stamp = datetime.now().strftime("%Y%m%d-%H%M%S")

    if args.action in ("snapshot", "show"):
        so_full = client.get_doc("Sales Order", job["so"])
        snap = {"site": args.site, "job": args.job, "taken_at": stamp, "context": ctx,
                "so_header": {k: so_full.get(k) for k in
                              ("name", "status", "docstatus", "customer", "customer_name", "net_total",
                               "total", "grand_total", "rounded_total", "total_taxes_and_charges",
                               "base_grand_total", "base_net_total", "per_delivered")},
                "so_row_docs": [r for r in so_full["items"]
                                if r["item_code"] in job["pairs"] or r["item_code"] in job["pairs"].values()],
                "pp_row_docs": [], "tn_docs": [], "bin": [], "wo_docs": []}
        for r in ctx["pp_rows"]:
            pp = client.get_doc("Production Plan", r["pp"])
            po = next((x for x in (pp.get("po_items") or []) if x["name"] == r["row_name"]), None)
            if po:
                snap["pp_row_docs"].append(po)
        for t in ctx["tns"]:
            snap["tn_docs"].append(client.get_doc("Tracking Number", t["name"]))
        for pk in job["pairs"]:
            snap["bin"] += client.get_list("Bin", filters=[["item_code", "=", pk]],
                                           fields=["warehouse", "actual_qty", "reserved_qty", "projected_qty"],
                                           limit_page_length=0)
        for w in ctx["work_orders"]:
            snap["wo_docs"].append(client.get_doc("Work Order", w["name"]))
        snap["fg_wo_docs"] = [client.get_doc("Work Order", w["name"]) for w in ctx["fg_wos"]]
        if ctx["pp_rows"]:
            _pp = client.get_doc("Production Plan", ctx["pp_rows"][0]["pp"])
            snap["pp_sub_rows_all"] = _pp.get("sub_assembly_items") or []
        p = args.out_dir / f"pk_to_fg_snapshot_{args.site}_{job['so']}_{stamp}.json"
        p.write_text(json.dumps(snap, ensure_ascii=False, indent=1, default=str), encoding="utf-8")
        print(f"  快照落盘: {p}")
        print(f"  含: SO行 {len(snap['so_row_docs'])} / PP po_item {len(snap['pp_row_docs'])} / "
              f"菲号 {len(snap['tn_docs'])} / 皮壳工单 {len(snap['wo_docs'])} / Bin {len(snap['bin'])}")
        return 0

    if args.action == "verify":
        so = client.get_doc("Sales Order", job["so"])
        for r in so["items"]:
            if r["item_code"] in tuple(job["pairs"].values()) or r["item_code"] in job["pairs"]:
                print(f"  SO行 idx={r['idx']} {r['item_code']} wh={r.get('warehouse')} rate={r.get('rate')} "
                      f"qty={r['qty']} 已交={r.get('delivered_qty')}")
        print(f"  SO 合计: net_total={so.get('net_total')} grand_total={so.get('grand_total')}")
        for pk in job["pairs"]:
            for w in client.get_list("Work Order", filters=[["production_item", "=", pk], ["sales_order", "=", job["so"]]],
                                     fields=["name", "status", "produced_qty"], limit_page_length=0):
                print(f"  皮壳工单 {w['name']} {w['status']} produced={w['produced_qty']}")
        newtns = [t for t in ctx["tns"]]
        print(f"  菲号 {len(newtns)} 个: {[(t['name'], t['so_materials'], t['finished_product_work_order']) for t in newtns[:3]]}")
        return 0

    # ── apply ────────────────────────────────────────────────────────
    step = args.step
    if step == "so":
        rows = [{"dt": "Sales Order Item", "name": r["row_name"], "values": r["values"]} for r in ctx["so_rows"]]
        print("  ", run(client, "set_values", {"rows": rows}))
        print("  ", run(client, "recalc_so", {"so": job["so"]}))
    elif step == "pp":
        rows = [{"dt": "Production Plan Item", "name": r["row_name"], "values": r["values"]} for r in ctx["pp_rows"]]
        print("  ", run(client, "set_values", {"rows": rows}))
    elif step == "bom":
        # 排练环境：给成品建默认 BOM = [皮壳 ×1]（照生产样板 BOM-KS0195-…-002）
        for pk, fg in job["pairs"].items():
            boms = client.get_list("BOM", filters=[["item", "=", fg], ["docstatus", "=", 1],
                                                   ["is_default", "=", 1]], fields=["name"], limit_page_length=0)
            if boms:
                print(f"  跳过 {fg}：已有默认 BOM {boms[0]['name']}")
                continue
            print(f"  给 {fg} 建默认 BOM = [{pk} ×1] …",
                  run(client, "new_bom", {"item": fg, "quantity": 1,
                                          "company": job.get("company") or "FZH",
                                          "items": [{"item_code": pk, "qty": 1}]}))
    elif step == "fgwo":
        wo_map = json.loads(args.fg_wo_map) if args.fg_wo_map else {}
        for pk, fg in job["pairs"].items():
            w = next((x for x in ctx["work_orders"] if x["production_item"] == pk), None)
            if not w:
                print(f"  跳过 {pk}：找不到皮壳工单")
                continue
            bom_map = json.loads(args.bom_map) if args.bom_map else {}
            bom = bom_map.get(fg)
            if not bom:
                boms = client.get_list("BOM", filters=[["item", "=", fg], ["docstatus", "=", 1],
                                                      ["is_default", "=", 1]], fields=["name"],
                                       limit_page_length=0)
                bom = boms[0]["name"] if boms else None
            if not bom:
                print(f"  跳过 {fg}：无默认 BOM")
                continue
            payload = {"wo": {"production_item": fg, "qty": w["qty"], "bom_no": bom,
                              "fg_warehouse": WH_FG, "wip_warehouse": w.get("wip_warehouse") or WH_WIP,
                              "company": w.get("company") or job.get("company") or "FZH",
                              "sales_order": job["so"], "production_plan": w["production_plan"],
                              "production_plan_item": w["production_plan_item"],
                              "stock_uom": "个", "use_multi_level_bom": 0, "skip_transfer": 1}}
            print(f"  建 {fg} 成品工单…", run(client, "new_wo", payload))
    elif step == "tn":
        wo_map = json.loads(args.fg_wo_map) if args.fg_wo_map else {}
        rows = []
        for t in ctx["tns"]:
            pk = next((p for p in job["pairs"] if t["qty"] is not None), None)
            # 菲号归属按其 work_order 对应物料
            pk_item = next((w["production_item"] for w in ctx["work_orders"] if w["name"] == t["work_order"]), None)
            fg = job["pairs"].get(pk_item)
            fgwo = wo_map.get(fg)
            if not fg or not fgwo:
                print(f"  跳过 {t['name']}：缺 fg/fgwo 映射（--fg-wo-map）")
                continue
            rows.append({"dt": "Tracking Number", "name": t["name"],
                         "values": {"so_materials": fg, "finished_product_work_order": fgwo}})
        print("  ", run(client, "set_values", {"rows": rows, "n": len(rows)}))
    elif step == "transfer":
        for pk, fg in job["pairs"].items():
            # 以 SLE 在该仓的**实际余额**为准（TN.qty 可能大于实存，如工单未产满）
            sle = client.get_list("Stock Ledger Entry",
                                  filters=[["item_code", "=", pk], ["warehouse", "=", WH_SEMI_PACK],
                                           ["is_cancelled", "=", 0]],
                                  fields=["tracking_number", "actual_qty"], limit_page_length=0)
            bal: dict[str, float] = {}
            for r in sle:
                if r["tracking_number"]:
                    bal[r["tracking_number"]] = bal.get(r["tracking_number"], 0) + float(r["actual_qty"] or 0)
            bal = {k: v for k, v in bal.items() if v > 0}
            if not bal:
                print(f"  跳过 {pk}：{WH_SEMI_PACK} 无 SLE 余额（可能已搬）")
                continue
            rows = [{"item_code": pk, "qty": v, "s_warehouse": WH_SEMI_PACK,
                     "t_warehouse": WH_FG_PACK, "tracking_number": k} for k, v in sorted(bal.items())]
            print(f"  移仓 {pk} 共 {sum(r['qty'] for r in rows):.0f}（{len(rows)} 个菲号）…",
                  run(client, "new_se", {"purpose": "Material Transfer",
                                         "company": job.get("company") or "FZH", "rows": rows}))
    elif step == "subrows":
        pp_name = ctx["pp_rows"][0]["pp"]
        pp = client.get_doc("Production Plan", pp_name)
        existing = pp.get("sub_assembly_items") or []
        max_idx = max([int(s.get("idx") or 0) for s in existing] or [0])
        payloads = []
        for pr in ctx["pp_rows"]:
            po = next((x for x in pp["po_items"] if x["name"] == pr["row_name"]), None)
            if not po or not po.get("bom_no"):
                continue
            bom = client.get_doc("BOM", po["bom_no"])
            for bi in bom.get("items", []):
                child = bi["item_code"]
                cb = client.get_list("BOM", filters=[["item", "=", child], ["docstatus", "=", 1],
                                                     ["is_default", "=", 1]], fields=["name"],
                                     limit_page_length=0)
                if not cb:            # 无 BOM 的原料 → 不是子装配
                    continue
                ci = client.get_doc("Item", child)
                max_idx += 1
                payloads.append({
                    "doctype": "Production Plan Sub Assembly Item",
                    "parent": pp_name, "parentfield": "sub_assembly_items", "parenttype": "Production Plan",
                    "idx": max_idx,
                    "production_item": child, "item_name": ci.get("item_name"),
                    "parent_item_code": pr["fg"],
                    "schedule_date": po.get("planned_start_date"),
                    "fg_sales_order": po.get("sales_order"), "fg_sales_order_item": po.get("sales_order_item"),
                    "custom_label_combination": po.get("custom_label_combination"),
                    "qty": float(bi.get("qty") or 0) * float(po.get("planned_qty") or 0),
                    "bom_no": cb[0]["name"], "bom_level": 0, "type_of_manufacturing": "In House",
                    "production_plan_item": po["name"], "description": child,
                    "stock_uom": ci.get("stock_uom"), "uom": ci.get("stock_uom"),
                })
        print("  待追加子装配行（production_plan_item | production_item | qty | bom）:")
        for x in payloads:
            print(f"     {x['production_plan_item']} | {x['production_item']} | {x['qty']:.0f} | {x['bom_no']}")
        print("  ", run(client, "append_child", {"rows": payloads, "docstatus": 1}))
    elif step == "wolink":
        pp_name = ctx["pp_rows"][0]["pp"]
        pp = client.get_doc("Production Plan", pp_name)
        sub = pp.get("sub_assembly_items") or []
        rows = []
        for pr in ctx["pp_rows"]:
            subrow = next((s for s in sub if s.get("production_plan_item") == pr["row_name"]
                           and s.get("production_item") == pr["pk"]), None)
            if not subrow:
                print(f"  未找到 {pr['pk']} 的子装配行，跳过")
                continue
            for w in ctx["work_orders"]:
                if w.get("production_item") == pr["pk"]:
                    rows.append({"dt": "Work Order", "name": w["name"],
                                 "values": {"production_plan_item": None,
                                            "production_plan_sub_assembly_item": subrow["name"]}})
            for w in ctx["fg_wos"]:
                if w.get("production_item") == pr["fg"]:
                    rows.append({"dt": "Work Order", "name": w["name"],
                                 "values": {"production_plan_sub_assembly_item": subrow["name"]}})
        print("  待重挂工单:")
        for r in rows:
            print(f"     {r['name']} → {r['values']}")
        print("  ", run(client, "set_values", {"rows": rows}))
    else:
        print("✗ apply 需要 --step so|pp|bom|fgwo|tn|transfer|subrows|wolink")
        return 1
    return 0


if __name__ == "__main__":
    sys.exit(main())
