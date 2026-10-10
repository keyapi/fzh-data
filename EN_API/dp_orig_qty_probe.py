# -*- coding: utf-8 -*-
"""定位 DP 2610001 菲号 WO-26-02538-001「原始数量 13 vs 实际库存 35」的**只读**探针。

背景：出货计划扫码时 `remaining = original_tn_qty - already_allocated - other_occupied`，
其中 `original_tn_qty` 取行上存下来的 `original_qty`（首扫写一次、之后不重读）。
2610001 两行快照都是 13，而该菲号实时库存是 35（SLE/Bin/TN.qty 全 35）。

本探针在**生产**上部署一个临时只读 Server Script，直接跑生产自己的代码，回答：
  * 生产 `get_strict_so_warehouse_and_stock()` / `get_strict_tracking_sle_balance()` 现在返回几？
  * 若把 2610001 的 item_qties 清空后「首扫」该菲号，生产会算出几？
全程不写库（末尾 frappe.db.rollback()）。用完立即删除并复查残留。

用法:
  python EN_API/dp_orig_qty_probe.py stock      --plan 2610001 --tn WO-26-02538-001
  python EN_API/dp_orig_qty_probe.py scan_first --plan 2610001 --tn WO-26-02538-001
  python EN_API/dp_orig_qty_probe.py residue
"""
from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path

sys.stdout.reconfigure(encoding="utf-8")

from bom_fabric_length_check import ENV_KEYS, ENV_URLS, ErpnextClient, load_env  # noqa: E402

SCRIPT_NAME = "zz_dp_origqty_probe"
API_METHOD = SCRIPT_NAME

# 沙箱（RestrictedPython）限制：
#   * 变量名/属性名不能以 `_` 开头  → 所以**不能**直接调 doc._dp_other_plans_occupied()，
#     也不要在自己脚本里用 _xxx 变量。跨单占用改用等价的只读 SQL。
#   * 无 lambda / 海象 / frappe.db.delete。
SERVER_SCRIPT = '''mode = frappe.form_dict.get("mode")
plan = frappe.form_dict.get("plan")
tn_name = frappe.form_dict.get("tn")

TN_WH = "\\u5f85\\u5305\\u88c5\\u534a\\u6210\\u54c1\\u4ed3 - FZH"  # 待包装半成品仓 - FZH

out = {"mode": mode, "plan": plan, "tn": tn_name}

if mode == "stock":
    doc = frappe.get_doc("Delivery Plan", plan)
    out["is_strict_so_source"] = frappe.utils.cint(doc.is_strict_so_source)
    out["docstatus"] = doc.docstatus
    out["allow_over_qty"] = frappe.utils.cint(doc.allow_over_qty)

    tn = frappe.get_doc("Tracking Number", tn_name)
    out["tn_item_code"] = tn.item_code
    out["tn_so_materials"] = tn.so_materials
    out["tn_qty"] = frappe.utils.flt(tn.qty)
    out["tn_work_order"] = tn.work_order

    wo = frappe.get_doc("Work Order", tn.work_order)
    out["wo_production_item"] = wo.production_item
    out["wo_production_plan"] = wo.production_plan
    out["wo_production_plan_item"] = wo.production_plan_item
    out["wo_qty"] = frappe.utils.flt(wo.qty)
    out["wo_produced_qty"] = frappe.utils.flt(wo.produced_qty)
    out["wo_status"] = wo.status

    # 生产自己的两个口径
    try:
        info = doc.get_strict_so_warehouse_and_stock(tn_name)
        out["strict_so_warehouse_and_stock"] = info
    except Exception as exc:
        out["strict_so_warehouse_and_stock"] = {"error": str(exc)[:400]}

    item_code = tn.item_code
    try:
        out["strict_tracking_sle_balance"] = frappe.utils.flt(
            doc.get_strict_tracking_sle_balance(item_code, TN_WH, tn_name))
    except Exception as exc:
        out["strict_tracking_sle_balance"] = {"error": str(exc)[:400]}

    # 原始 SQL 复核：SLE 按 物料+仓+菲号
    rows = frappe.db.sql("""
        SELECT SUM(actual_qty) AS q, COUNT(*) AS n
        FROM `tabStock Ledger Entry`
        WHERE item_code = %(item)s AND warehouse = %(wh)s
          AND is_cancelled = 0 AND tracking_number = %(tn)s
    """, {"item": item_code, "wh": TN_WH, "tn": tn_name}, as_dict=True)
    out["sle_item_wh_tn"] = {"qty": frappe.utils.flt(rows[0].q) if rows else 0.0,
                             "rows": rows[0].n if rows else 0}

    # SLE 全部仓库（含菲号）
    rows2 = frappe.db.sql("""
        SELECT warehouse, SUM(actual_qty) AS q
        FROM `tabStock Ledger Entry`
        WHERE item_code = %(item)s AND is_cancelled = 0
        GROUP BY warehouse
    """, {"item": item_code}, as_dict=True)
    out["sle_by_warehouse"] = [{"warehouse": r.warehouse, "qty": frappe.utils.flt(r.q)} for r in rows2]

    # Bin
    rows3 = frappe.db.sql("""
        SELECT warehouse, actual_qty, reserved_qty, projected_qty
        FROM `tabBin` WHERE item_code = %(item)s
    """, {"item": item_code}, as_dict=True)
    out["bin"] = [{"warehouse": r.warehouse, "actual": frappe.utils.flt(r.actual_qty),
                   "reserved": frappe.utils.flt(r.reserved_qty),
                   "projected": frappe.utils.flt(r.projected_qty)} for r in rows3]

    # 跨单占用（等价 _dp_other_plans_occupied 的只读 SQL）
    rows4 = frappe.db.sql("""
        SELECT dp.name AS plan, SUM(iq.planned_delivery_qty) AS qty
        FROM `tabDelivery Plan` dp
        INNER JOIN `tabDelivery Plan Item Qty` iq ON iq.parent = dp.name
        WHERE dp.docstatus IN (0, 1) AND dp.name <> %(self)s
          AND iq.tracking_number = %(tn)s
        GROUP BY dp.name
    """, {"self": plan, "tn": tn_name}, as_dict=True)
    out["other_plans_occupied"] = [{"plan": r.plan, "qty": frappe.utils.flt(r.qty)} for r in rows4]

    # 本单现存 item_qties 行（原样）
    out["this_doc_rows"] = [{"idx": r.idx, "planned": frappe.utils.flt(r.planned_delivery_qty),
                             "staging": frappe.utils.flt(r.staging_qty),
                             "assigned": frappe.utils.flt(r.assigned_qty),
                             "actual": frappe.utils.flt(r.actual_qty),
                             "original": frappe.utils.flt(r.original_qty)}
                            for r in (doc.item_qties or []) if r.tracking_number == tn_name]

elif mode == "scan_first":
    # 把 2610001 读进内存、清空 item_qties，模拟「在一个干净单据上首扫该菲号」
    doc = frappe.get_doc("Delivery Plan", plan)
    doc.item_qties = []
    try:
        res = doc.add_item_from_tracking_number(tn_name)
        out["scan_result"] = {"ok": True, "added_qty": frappe.utils.flt(res.get("added_qty")),
                              "original_qty": frappe.utils.flt(res.get("original_qty")),
                              "other_occupied": frappe.utils.flt(res.get("other_occupied"))}
    except Exception as exc:
        out["scan_result"] = {"ok": False, "error": str(exc)[:500]}
    frappe.db.rollback()

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
                          "script": SERVER_SCRIPT, "allow_guest": 0, "disabled": 0},
                    timeout=60)
    print(f"[{client.base_url}] 已部署临时只读 Server Script {SCRIPT_NAME}")


def drop_script(client: ErpnextClient) -> None:
    try:
        client._request("DELETE", f"/api/resource/Server Script/{SCRIPT_NAME}", timeout=60, retries=0)
    except Exception:  # noqa: BLE001
        pass
    try:
        client._request("GET", f"/api/resource/Server Script/{SCRIPT_NAME}", timeout=60, retries=0)
        print(f"  ⚠ {SCRIPT_NAME} 删除后仍能读到，请复查")
    except Exception:  # noqa: BLE001
        print(f"已删除临时 Server Script {SCRIPT_NAME}（残留 0）")


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("action", choices=("stock", "scan_first", "residue"))
    ap.add_argument("--site", choices=("prod", "test"), default="prod")
    ap.add_argument("--plan", default="2610001")
    ap.add_argument("--tn", default="WO-26-02538-001")
    ap.add_argument("--out-dir", type=Path, default=Path(__file__).resolve().parent / "out")
    args = ap.parse_args()

    key, sec = load_env(args.site)
    if not key or not sec:
        print(f"✗ 缺 {ENV_KEYS[args.site]} 凭证")
        return 1
    client = ErpnextClient(ENV_URLS[args.site], key, sec)

    if args.action == "residue":
        lst = client.get_list("Server Script", filters=[["name", "like", "zz_%"]], fields=["name"])
        print("zz_* Server Script 残留:", lst)
        return 0 if not lst else 1

    ensure_script(client)
    try:
        res = call(client, mode=args.action, plan=args.plan, tn=args.tn)
        print(json.dumps(res, ensure_ascii=False, indent=1, default=str))
        args.out_dir.mkdir(parents=True, exist_ok=True)
        p = args.out_dir / f"dp_origqty_probe_{args.action}.json"
        p.write_text(json.dumps(res, ensure_ascii=False, indent=1, default=str), encoding="utf-8")
        print(f"\n落盘: {p}")
    finally:
        drop_script(client)
    return 0


if __name__ == "__main__":
    sys.exit(main())
