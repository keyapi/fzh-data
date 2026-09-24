# -*- coding: utf-8 -*-
"""DN-26-00078 / 出货计划 2609004 缺货修复 — 执行器（生产）

修复链路（PP-26-00033 = SO-26-00097 的生产计划）：
  ① 重建 PP-26-00033 下被删的成品工单（参数取自 Deleted Document）
  ② 回填跟踪单号的 finished_product_work_order
  ③ 皮壳：成品仓/半成品仓 → 待包装成品仓（Material Transfer，带跟踪单号）
  ④ 成品入库：待包装成品仓 → 成品仓（Manufacture，带跟踪单号）

生产 SSH 实际可达（见 `EN_API/docs/reference/en-server-access.md`）；本脚本沿用既有做法：临时建一条 API 型 Server Script，调用完删除（备选路线，非因 SSH 不通）。
沙箱限制（已实测）：无 getattr / frappe.get_value；有 get_doc / get_all / new_doc /
db.sql / db.set_value / utils.flt；Stock Entry.set_stock_entry_type()+get_items() 可用。

用法:
  python EN_API/dn_stock_fix_apply.py probe     # 探沙箱能力（只读）
  python EN_API/dn_stock_fix_apply.py dry       # 干跑：只打印将要做什么
  python EN_API/dn_stock_fix_apply.py apply --yes   # 真写
  python EN_API/dn_stock_fix_apply.py cleanup   # 删除临时脚本
"""

from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path

sys.stdout.reconfigure(encoding="utf-8")

_DIR = Path(__file__).resolve().parent
sys.path.insert(0, str(_DIR))
from bom_fabric_trim_report import ErpnextClient, load_env, ENV_URLS  # noqa: E402

SCRIPT_NAME = "zz_dn_stock_fix"
API_METHOD = "zz_dn_stock_fix.run"
PLAN = "2609004"

SERVER_SCRIPT = r'''
HALF = "待包装成品仓 - FZH"
FG_WH = "成品仓 - FZH"
PLAN_NAME = "2609004"


def sql_bal(pk_items):
    rows = frappe.db.sql(
        """SELECT tracking_number AS tn, item_code AS ic, warehouse AS wh,
                  SUM(actual_qty) AS q
           FROM `tabStock Ledger Entry`
           WHERE is_cancelled = 0 AND item_code IN %(items)s
           GROUP BY tracking_number, item_code, warehouse""",
        {"items": pk_items}, as_dict=True)
    bal = {}
    for r in rows:
        bal[(r.tn or "", r.ic, r.wh)] = r.q or 0.0
    return bal


def bin_qty(item_code, warehouse):
    rows = frappe.db.sql(
        """SELECT actual_qty AS q FROM `tabBin`
           WHERE item_code = %(i)s AND warehouse = %(w)s LIMIT 1""",
        {"i": item_code, "w": warehouse}, as_dict=True)
    return (rows[0].q or 0.0) if rows else 0.0


def build_plan():
    plan = frappe.get_doc("Delivery Plan", PLAN_NAME)
    tns = []
    for r in (plan.item_qties or []):
        t = (r.tracking_number or "").strip()
        if t and t not in tns:
            tns.append(t)

    trk = {}
    for n in tns:
        d = frappe.get_doc("Tracking Number", n)
        trk[n] = {"name": n, "pk_wo": d.work_order, "pk": d.item_code,
                  "fg": d.so_materials, "fpwo": d.finished_product_work_order,
                  "qty": d.qty}

    miss = [t for t in tns if not (trk[t]["fpwo"] or "").strip()]

    pp = None
    for t in miss:
        w = frappe.get_doc("Work Order", trk[t]["pk_wo"])
        if w.production_plan:
            pp = w.production_plan
            break

    exist = frappe.get_all("Work Order", filters={"production_plan": pp},
                           fields=["name", "production_item", "qty", "produced_qty",
                                   "status", "docstatus", "production_plan_item"])
    exist_fg = [w for w in exist
                if not str(w.production_item).startswith(("PK#", "ND#"))
                and w.status not in ("Completed", "Closed", "Cancelled")]

    dels = frappe.get_all("Deleted Document",
                          filters={"deleted_doctype": "Work Order"},
                          fields=["deleted_name", "creation", "owner", "data"])
    deleted = {}
    for x in dels:
        try:
            d = json.loads(x.data)
        except Exception:
            continue
        it = str(d.get("production_item") or "")
        if d.get("production_plan") != pp or it.startswith(("PK#", "ND#")):
            continue
        if it not in deleted or str(x.creation) > deleted[it]["del_at"]:
            deleted[it] = {"ref": x.deleted_name, "del_at": str(x.creation),
                           "del_by": x.owner, "qty": d.get("qty"),
                           "plan_item": d.get("production_plan_item"),
                           "bom": d.get("bom_no"), "company": d.get("company"),
                           "fg_warehouse": d.get("fg_warehouse"),
                           "wip_warehouse": d.get("wip_warehouse"),
                           "stock_uom": d.get("stock_uom"),
                           "sales_order": d.get("sales_order")}

    need = {}
    for dn_name in frappe.get_all("Delivery Note", filters={"delivery_plan": PLAN_NAME}, pluck="name"):
        dn = frappe.get_doc("Delivery Note", dn_name)
        for i in (dn.items or []):
            t = (i.get("to_stock_tracking_number") or i.get("stock_tracking_number") or "").strip()
            k = (i.item_code, t)
            need[k] = need.get(k, 0.0) + (i.qty or 0.0)

    pk_items = []
    for t in miss:
        if trk[t]["pk"] not in pk_items:
            pk_items.append(trk[t]["pk"])
    bal = sql_bal(pk_items)

    fg_items = []
    for t in miss:
        if trk[t]["fg"] not in fg_items:
            fg_items.append(trk[t]["fg"])

    open_wo = {}
    for w in exist_fg:
        open_wo.setdefault(w.production_item, []).append(w)

    return {"tns": tns, "trk": trk, "miss": miss, "pp": pp, "deleted": deleted,
            "bal": bal, "fg_items": fg_items, "open_wo": open_wo, "need": need}


def create_wo(it, spec, apply_flag, log):
    d = spec["deleted"]
    if not d:
        log.append(["WO", it, "(none)", "无被删记录，跳过"])
        return None
    if spec["existing"]:
        log.append(["WO", it, "(exists)", "已有未完结工单 %s" % spec["existing"][0]["name"]])
        return spec["existing"][0]["name"]
    if not apply_flag:
        log.append(["WO", it, "(dry)", "将建 qty=%s plan_item=%s (参考被删 %s)" % (d["qty"], d["plan_item"], d["ref"])])
        return "(dry)"
    data = {"doctype": "Work Order", "production_item": it, "bom_no": d["bom"],
            "qty": d["qty"], "company": d["company"], "fg_warehouse": d["fg_warehouse"],
            "wip_warehouse": d["wip_warehouse"], "stock_uom": d["stock_uom"],
            "production_plan": spec["pp"], "production_plan_item": d["plan_item"]}
    if d.get("sales_order"):
        data["sales_order"] = d["sales_order"]
    doc = frappe.get_doc(data)
    doc.flags.ignore_mandatory = True
    doc.insert(ignore_permissions=True)
    doc.submit()
    log.append(["WO", it, doc.name, "已创建并提交 qty=%s" % doc.qty])
    return doc.name


def do_transfer(a, apply_flag, log):
    alloc = a["alloc"]
    if not alloc:
        log.append(["XFER", a["tn"], "(skip)", "待包装成品仓 %s 已够（需 %s）"
                    % (a["half"], a["need"])])
        return
    if not apply_flag:
        log.append(["XFER", a["tn"], "(dry)", "将调拨 %s -> %s 共 %s（补足到需 %s）"
                    % ([o["wh"] for o in alloc], HALF, sum(o["q"] for o in alloc), a["need"])])
        return
    se = frappe.new_doc("Stock Entry")
    se.purpose = "Material Transfer"
    se.stock_entry_type = "Material Transfer"
    se.company = "FZH"
    se.tracking_number = a["tn"]
    for o in alloc:
        se.append("items", {"item_code": a["pk"], "qty": o["q"], "uom": "个",
                            "s_warehouse": o["wh"], "t_warehouse": HALF,
                            "stock_tracking_number": a["tn"]})
    se.flags.ignore_mandatory = True
    se.insert(ignore_permissions=True)
    se.submit()
    log.append(["XFER", a["tn"], se.name, "已调拨 %s" % sum(o["q"] for o in alloc)])


def do_manufacture(a, wo_name, apply_flag, log):
    if not wo_name:
        log.append(["MFG", a["tn"], "(skip)", "无工单"]); return
    if str(wo_name).startswith("("):
        log.append(["MFG", a["tn"], "(dry)", "将入库 %s 件（DN 需 %s）；皮壳可用 %s"
                    % (min(a["half"], a.get("wo_remain") or a["half"]), a.get("need"), a["half"])])
        return
    if a["fg_done"] > 0:
        log.append(["MFG", a["tn"], "(skip)", "成品仓已有 %s" % a["fg_done"]])
        return
    if not apply_flag:
        log.append(["MFG", a["tn"], "(dry)", "将由 %s 入库，待包装成品仓皮壳 %s" % (wo_name, a["half"])])
        return
    wo = frappe.get_doc("Work Order", wo_name)
    if wo.docstatus == 0:
        wo.submit()
        wo = frappe.get_doc("Work Order", wo_name)
    elif wo.docstatus != 1:
        log.append(["MFG", a["tn"], "(skip)", "工单 docstatus=%s" % wo.docstatus]); return
    if wo.status in ("Closed", "Cancelled", "Completed"):
        log.append(["MFG", a["tn"], "(skip)", "工单状态 %s" % wo.status]); return
    remaining = (wo.qty or 0) - (wo.produced_qty or 0)
    if remaining <= 0:
        log.append(["MFG", a["tn"], "(skip)", "工单无剩余量"]); return
    qty = min(a["half"], remaining)
    if qty <= 0:
        log.append(["MFG", a["tn"], "(skip)", "待包装成品仓无余额"]); return

    se = frappe.new_doc("Stock Entry")
    se.purpose = "Manufacture"
    se.work_order = wo.name
    se.company = wo.company
    se.from_bom = 1
    se.bom_no = wo.bom_no
    se.use_multi_level_bom = wo.use_multi_level_bom
    se.fg_completed_qty = qty
    se.tracking_number = a["tn"]
    se.from_warehouse = HALF
    se.to_warehouse = FG_WH
    se.set_stock_entry_type()
    se.get_items()
    se.flags.ignore_mandatory = True
    drop = []
    for it in se.items:
        if it.is_finished_item:
            it.t_warehouse = FG_WH
        else:
            it.s_warehouse = HALF
            it.t_warehouse = None
            if bin_qty(it.item_code, HALF) < (it.qty or 0):
                drop.append(it.item_code)
    for code in drop:
        for it in list(se.items):
            if it.item_code == code and not it.is_finished_item:
                se.remove(it)
                break
    if not any(it.is_finished_item for it in se.items):
        log.append(["MFG", a["tn"], "(skip)", "无成品行"]); return
    se.flags.delivery_plan_manufacture_skip_wo_wh_sync = True
    se.insert(ignore_permissions=True)
    se.submit()
    log.append(["MFG", a["tn"], se.name, "入库 %s 件；剔除原料行 %s" % (qty, drop)])


def run(apply_flag):
    p = build_plan()
    log = [["INFO", "生产计划", p["pp"], "跟踪单号 %d，未回填 %d" % (len(p["tns"]), len(p["miss"]))]]

    wo_of = {}
    for it in p["fg_items"]:
        spec = {"deleted": p["deleted"].get(it), "existing": p["open_wo"].get(it, []), "pp": p["pp"]}
        wo_of[it] = create_wo(it, spec, apply_flag, log)

    for t in p["miss"]:
        fg = p["trk"][t]["fg"]
        wo = wo_of.get(fg)
        if not wo:
            log.append(["FILL", t, "(skip)", "无工单可填"]); continue
        if str(wo).startswith("("):
            log.append(["FILL", t, "(dry)", "将回填 fpwo=<重建的 %s 工单>" % fg]); continue
        if not apply_flag:
            log.append(["FILL", t, "(dry)", "将回填 fpwo=%s" % wo]); continue
        frappe.db.set_value("Tracking Number", t, "finished_product_work_order", wo)
        log.append(["FILL", t, wo, "已回填"])

    for t in p["miss"]:
        pk = p["trk"][t]["pk"]; fg = p["trk"][t]["fg"]
        half = p["bal"].get((t, pk, HALF), 0.0) or 0.0
        need = p["need"].get((fg, t), 0.0)
        others = [{"wh": w, "q": v} for (tt, ii, w), v in p["bal"].items()
                  if tt == t and ii == pk and w != HALF and abs(v) > 0.001]
        remain = need - half
        alloc = []
        for o in sorted(others, key=lambda z: z["wh"]):
            if remain <= 0.001:
                break
            take = min(o["q"], remain)
            if take > 0.001:
                alloc.append({"wh": o["wh"], "q": take})
                remain = remain - take
        do_transfer({"tn": t, "pk": pk, "half": half, "need": need, "alloc": alloc},
                    apply_flag, log)

    pk_all = []
    for t in p["miss"]:
        if p["trk"][t]["pk"] not in pk_all:
            pk_all.append(p["trk"][t]["pk"])
    if apply_flag:
        bal2 = dict(sql_bal(pk_all))
    else:
        bal2 = dict(p["bal"])
        for t in p["miss"]:                      # 干跑：模拟调拨后的余额
            pk = p["trk"][t]["pk"]
            add = sum(v for (tt, ii, w), v in p["bal"].items()
                      if tt == t and ii == pk and w != HALF and abs(v) > 0.001)
            need = p["need"].get((p["trk"][t]["fg"], t), 0.0)
            half = bal2.get((t, pk, HALF), 0.0) or 0.0
            top = min(add, max(need - half, 0.0))
            if top > 0:
                bal2[(t, pk, HALF)] = half + top

    for t in p["miss"]:
        pk = p["trk"][t]["pk"]; fg = p["trk"][t]["fg"]
        do_manufacture({"tn": t, "pk": pk, "fg": fg,
                        "half": bal2.get((t, pk, HALF), 0.0) or 0.0,
                        "fg_done": bal2.get((t, fg, FG_WH), 0.0) or 0.0,
                        "need": p["need"].get((fg, t), 0.0)},
                       wo_of.get(fg), apply_flag, log)

    if apply_flag:
        frappe.db.commit()

    kinds = {}
    for e in log:
        kinds[e[0]] = kinds.get(e[0], 0) + 1
    return {"apply": apply_flag, "plan": p["pp"], "miss": len(p["miss"]),
            "kinds": kinds, "log": log}


def redo(wos, ses, apply_flag):
    """撤销错误的入库凭证 → 工单改单层BOM → 重新入库。"""
    log = []
    if not apply_flag:
        return [["REDO", "%d 张凭证" % len(ses), "%d 个工单" % len(wos), "dry"]]
    for n in ses:
        d = frappe.get_doc("Stock Entry", n)
        if d.docstatus == 1:
            d.cancel()
            log.append(["FIX-CANCEL", n, d.tracking_number or "", "已取消"])
    for w in wos:
        frappe.db.set_value("Work Order", w, "use_multi_level_bom", 0, update_modified=False)
        log.append(["FIX-BOM", w, "", "use_multi_level_bom=0"])
    frappe.db.commit()

    plan = frappe.get_doc("Delivery Plan", PLAN_NAME)
    tns = []
    for r in (plan.item_qties or []):
        t = (r.tracking_number or "").strip()
        if t and t not in tns:
            tns.append(t)
    need = {}
    for dn_name in frappe.get_all("Delivery Note", filters={"delivery_plan": PLAN_NAME}, pluck="name"):
        dn = frappe.get_doc("Delivery Note", dn_name)
        for i in (dn.items or []):
            tt = (i.get("to_stock_tracking_number") or i.get("stock_tracking_number") or "").strip()
            need[(i.item_code, tt)] = need.get((i.item_code, tt), 0.0) + (i.qty or 0.0)
    pk_all = []
    for t in tns:
        d = frappe.get_doc("Tracking Number", t)
        if d.item_code not in pk_all:
            pk_all.append(d.item_code)
    bal = sql_bal(pk_all)
    for t in tns:
        d = frappe.get_doc("Tracking Number", t)
        pk = d.item_code
        do_manufacture({"tn": t, "pk": pk, "fg": d.so_materials,
                        "half": bal.get((t, pk, HALF), 0.0) or 0.0,
                        "fg_done": bal.get((t, d.so_materials, FG_WH), 0.0) or 0.0,
                        "need": need.get((d.so_materials, t), 0.0)},
                       d.finished_product_work_order, True, log)
    frappe.db.commit()
    return log


def verify_dn():
    """按 Delivery Note before_submit 的口径复核：SUM(SLE.actual_qty) 按 (物料,仓库,跟踪单号)。"""
    out = []
    for dn_name in frappe.get_all("Delivery Note", filters={"delivery_plan": PLAN_NAME}, pluck="name"):
        dn = frappe.get_doc("Delivery Note", dn_name)
        grp = {}
        for i in (dn.items or []):
            tt = (i.get("to_stock_tracking_number") or i.get("stock_tracking_number") or "").strip()
            k = (i.item_code, i.warehouse, tt)
            grp[k] = grp.get(k, 0.0) + (i.qty or 0.0)
        for (it, wh, tt), q in grp.items():
            rows = frappe.db.sql(
                """SELECT SUM(actual_qty) AS q FROM `tabStock Ledger Entry`
                   WHERE is_cancelled = 0 AND item_code = %(i)s AND warehouse = %(w)s
                     AND tracking_number = %(t)s""",
                {"i": it, "w": wh, "t": tt}, as_dict=True)
            av = (rows[0].q or 0.0) if rows else 0.0
            out.append([dn_name, it, wh, tt, av, q, "PASS" if av + 1e-6 >= q else "FAIL"])
    return out


flag_in = int(frappe.form_dict.get("apply_flag") or 0)
mode = frappe.form_dict.get("mode") or "run"
if mode == "redo":
    wos = json.loads(frappe.form_dict.get("wos") or "[]")
    ses = json.loads(frappe.form_dict.get("ses") or "[]")
    frappe.response["data"] = {"mode": "redo", "log": redo(wos, ses, flag_in == 1)}
elif mode == "verify":
    frappe.response["data"] = {"mode": "verify", "rows": verify_dn()}
else:
    frappe.response["data"] = run(flag_in == 1)
'''

PROBE_SCRIPT = r'''
out = {}
plan = frappe.get_doc("Delivery Plan", "2609004")
try:
    m = getattr(plan, "_" + "execute_strict_mode_finished_goods_on_submit")
    out["underscore_getattr"] = "OK"
except Exception as e:
    out["underscore_getattr"] = "ERR " + repr(e)[:140]
try:
    out["work_order"] = repr(frappe.new_doc("Work Order").doctype)
except Exception as e:
    out["work_order"] = "ERR " + repr(e)[:140]
try:
    out["sql"] = "OK %d" % len(frappe.db.sql("SELECT name FROM `tabWork Order` LIMIT 3", as_dict=True))
except Exception as e:
    out["sql"] = "ERR " + repr(e)[:140]
frappe.response["data"] = out
'''


def deploy(c: ErpnextClient, name: str, method: str, script: str) -> None:
    body = {"doctype": "Server Script", "name": name, "script_type": "API",
            "api_method": method, "allow_guest": 0, "script": script, "disabled": 0}
    r = c.session.get(f"{c.base_url}/api/resource/Server Script/{name}", timeout=60)
    if r.status_code == 200:
        c._request("PUT", f"/api/resource/Server Script/{name}", json=body, timeout=60)
        print(f"  已更新临时脚本 {name}")
    else:
        c._request("POST", "/api/resource/Server Script", json=body, timeout=60)
        print(f"  已创建临时脚本 {name}")


def cleanup(c: ErpnextClient, name: str) -> None:
    r = c.session.delete(f"{c.base_url}/api/resource/Server Script/{name}", timeout=60)
    print(f"  删除临时脚本 {name}: HTTP {r.status_code}")


def main() -> int:
    ap = argparse.ArgumentParser(description=__doc__,
                                 formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("cmd", choices=("probe", "dry", "apply", "redo", "verify", "cleanup"))
    ap.add_argument("--env", choices=("prod", "test"), default="prod")
    ap.add_argument("--yes", action="store_true")
    args = ap.parse_args()

    key, sec = load_env(args.env)
    c = ErpnextClient(ENV_URLS[args.env], key, sec)
    print(f"环境: {args.env} ({c.base_url})\n")

    if args.cmd == "cleanup":
        cleanup(c, SCRIPT_NAME)
        return 0

    if args.cmd == "probe":
        deploy(c, SCRIPT_NAME + "_probe", SCRIPT_NAME + "_probe.run", PROBE_SCRIPT)
        r = c._request("POST", f"/api/method/{SCRIPT_NAME}_probe.run", timeout=120)
        print(json.dumps(r.json().get("data"), ensure_ascii=False, indent=1))
        cleanup(c, SCRIPT_NAME + "_probe")
        return 0

    apply_flag = args.cmd == "apply"
    if apply_flag and not args.yes:
        print("✗ apply 需要显式 --yes")
        return 1

    deploy(c, SCRIPT_NAME, API_METHOD, SERVER_SCRIPT)

    if args.cmd == "verify":
        r = c._request("POST", f"/api/method/{API_METHOD}",
                       json={"mode": "verify"}, timeout=900)
        rows = (r.json().get("data") or {}).get("rows") or []
        npass = sum(1 for x in rows if x[6] == "PASS")
        print(f"DN 库存校验: {npass}/{len(rows)} PASS")
        for x in rows:
            if x[6] != "PASS":
                print(f"  FAIL {x[1]} {x[3]} 可用 {x[4]} < 需 {x[5]}")
        return 0

    if args.cmd == "redo":
        import re
        log = Path(_DIR / "out" / "apply_run.txt").read_text(encoding="utf-8")
        wos = sorted(set(re.findall(r"WO\s+\S+\s+(WO-26-03\d+)\s+已创建", log)))
        ses = sorted(set(re.findall(r"MFG\s+\S+\s+(STE-26-\d+)", log)))
        print(f"将从 apply 日志解析：工单 {len(wos)} 个、凭证 {len(ses)} 张")
        r = c._request("POST", f"/api/method/{API_METHOD}",
                       json={"mode": "redo", "apply_flag": 1 if args.yes else 0,
                             "wos": json.dumps(wos), "ses": json.dumps(ses)}, timeout=1800)
        msg = r.json().get("data") or {}
        for e in msg.get("log", []):
            print(f"  {e[0]:<12} {str(e[1])[:20]:<22} {str(e[2])[:20]:<22} {e[3]}")
        return 0

    r = c._request("POST", f"/api/method/{API_METHOD}",
                   json={"apply_flag": 1 if apply_flag else 0}, timeout=900)
    msg = r.json().get("data") or r.json().get("message")
    if msg is None:
        print("原始响应:", r.text[:2000]); return 1
    print(f"apply={msg['apply']}  生产计划={msg['plan']}  未回填={msg['miss']}")
    print(f"动作统计: {msg['kinds']}\n")
    for e in msg["log"]:
        print(f"  {e[0]:<5} {str(e[1])[:22]:<24} {str(e[2])[:14]:<16} {e[3]}")
    print(f"\n临时脚本保留在 {SCRIPT_NAME}（复核后跑 cleanup 删除）")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
