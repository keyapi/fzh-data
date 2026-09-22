# -*- coding: utf-8 -*-
"""验证「扫菲号跨单据校验占用」补丁 —— 只读探针（内存调用后 rollback，不写任何数据）。

用法:
  python EN_API/dp_tn_occupy_probe.py survey   --site test
  python EN_API/dp_tn_occupy_probe.py scan     --site test --plan 2609009 --tn WO-26-02791-002
  python EN_API/dp_tn_occupy_probe.py residue  --site test

survey : 列出被 >1 张未取消出货计划占用的菲号（占用明细）
scan   : 在指定计划上模拟扫某个菲号，看后端算出的 other_occupied 与截断/提示结果
"""
from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path

sys.stdout.reconfigure(encoding="utf-8")

from bom_fabric_length_check import ENV_KEYS, ENV_URLS, ErpnextClient, load_env  # noqa: E402

SCRIPT_NAME = "zz_dp_tn_occupy_probe"
API_METHOD = SCRIPT_NAME

SERVER_SCRIPT = '''mode = frappe.form_dict.get("mode")


def now_stamp():
    """沙箱里没有 import time，用 frappe 的 datetime。"""
    return frappe.utils.now_datetime()


# 注意：Server Script 跑在 RestrictedPython 沙箱里 —— 不能访问 _ 开头的属性、
# 不能用 s["k"] += v 这种增强赋值。所以这里只用纯 SQL + 公开方法。

if mode == "ocsql":
    # 单独量「本补丁新增的那条跨单占用 SQL」的耗时（保存路径新增成本就是它）
    plan_name = frappe.form_dict.get("plan")
    doc = frappe.get_doc("Delivery Plan", plan_name)
    tns = []
    for r in (doc.item_qties or []):
        t = (r.tracking_number or "").strip()
        if t and t not in tns:
            tns.append(t)

    def run_once():
        return frappe.db.sql("""
            SELECT iq.tracking_number AS tn, dp.name AS plan, SUM(iq.planned_delivery_qty) AS qty
            FROM `tabDelivery Plan` dp
            INNER JOIN `tabDelivery Plan Item Qty` iq ON iq.parent = dp.name
            WHERE dp.docstatus IN (0, 1) AND dp.name <> %(self)s AND iq.tracking_number IN %(tns)s
            GROUP BY iq.tracking_number, dp.name
        """, {"self": plan_name, "tns": tns}, as_dict=True)

    times = []
    out = []
    for i in range(5):
        a = now_stamp()
        out = run_once()
        b = now_stamp()
        times.append((b - a).total_seconds() * 1000.0)
    frappe.response["data"] = {
        "plan": plan_name, "item_qty_rows": len(doc.item_qties or []), "tn_count": len(tns),
        "runs_ms": times, "avg_ms": sum(times) / len(times), "rows_returned": len(out),
    }

elif mode == "ocsqln":
    # 最坏情况：用一个 450 个菲号的 IN 列表量同一条 SQL（模拟大单据）
    n = frappe.utils.cint(frappe.form_dict.get("n") or 450)
    plan_name = frappe.form_dict.get("plan") or ""
    tns = []
    for i in range(n):
        tns.append("ZZZAKE-TN-" + frappe.utils.cstr(i))

    def run_once_n():
        return frappe.db.sql("""
            SELECT iq.tracking_number AS tn, dp.name AS plan, SUM(iq.planned_delivery_qty) AS qty
            FROM `tabDelivery Plan` dp
            INNER JOIN `tabDelivery Plan Item Qty` iq ON iq.parent = dp.name
            WHERE dp.docstatus IN (0, 1) AND dp.name <> %(self)s AND iq.tracking_number IN %(tns)s
            GROUP BY iq.tracking_number, dp.name
        """, {"self": plan_name, "tns": tns}, as_dict=True)

    times_n = []
    for i in range(5):
        a = now_stamp()
        run_once_n()
        b = now_stamp()
        times_n.append((b - a).total_seconds() * 1000.0)
    frappe.response["data"] = {"n_tns": n, "runs_ms": times_n,
                               "avg_ms": sum(times_n) / len(times_n)}

elif mode == "scantwice":
    # 同一单据内对同一菲号连扫两次：验证剩余量递减（含跨单占用）
    plan_name = frappe.form_dict.get("plan")
    tn = frappe.form_dict.get("tn")
    doc = frappe.get_doc("Delivery Plan", plan_name)
    scans = []
    for i in range(2):
        try:
            res = doc.add_item_from_tracking_number(tn)
            scans.append({"ok": True, "added_qty": res.get("added_qty"),
                          "original_qty": res.get("original_qty"),
                          "other_occupied": res.get("other_occupied")})
        except Exception as exc:
            scans.append({"ok": False, "error": str(exc)[:300]})
    frappe.db.rollback()
    frappe.response["data"] = {"plan": plan_name, "tn": tn, "scans": scans}

elif mode == "validate":
    # 端到端验证保存兜底：直接跑 doc.validate()（含 _validate_tracking_number_planned_qty）
    plan_name = frappe.form_dict.get("plan")
    doc = frappe.get_doc("Delivery Plan", plan_name)
    out = {"plan": plan_name, "docstatus": doc.docstatus}
    try:
        doc.validate()
        out["result"] = {"ok": True}
    except Exception as exc:
        out["result"] = {"ok": False, "error": str(exc)[:600]}
    frappe.db.rollback()
    frappe.response["data"] = out

elif mode == "survey":
    rows = frappe.db.sql("""
        SELECT iq.tracking_number AS tn, dp.name AS plan, dp.docstatus AS ds,
               SUM(iq.planned_delivery_qty) AS qty
        FROM `tabDelivery Plan` dp
        INNER JOIN `tabDelivery Plan Item Qty` iq ON iq.parent = dp.name
        WHERE dp.docstatus IN (0, 1)
          AND iq.tracking_number IS NOT NULL AND iq.tracking_number != ''
        GROUP BY iq.tracking_number, dp.name, dp.docstatus
    """, as_dict=True)
    by = {}
    for r in rows:
        s = by.setdefault(r.tn, {"total": 0.0, "plans": []})
        s["total"] = s["total"] + frappe.utils.flt(r.qty)
        s["plans"].append({"plan": r.plan, "docstatus": r.ds, "qty": frappe.utils.flt(r.qty)})
    multi = {k: v for k, v in by.items() if len(v["plans"]) > 1}
    ordered = sorted(multi.items(), key=lambda kv: -len(kv[1]["plans"]))
    frappe.response["data"] = {
        "tn_total": len(by),
        "multi_plan_tns": len(multi),
        "top": [{"tn": k, "plan_count": len(v["plans"]), "total": v["total"], "plans": v["plans"]}
                for k, v in ordered[:15]],
    }

elif mode == "scan":
    plan_name = frappe.form_dict.get("plan")
    tn = frappe.form_dict.get("tn")
    doc = frappe.get_doc("Delivery Plan", plan_name)
    info = {"plan": plan_name, "tn": tn, "docstatus": doc.docstatus,
            "is_strict_so_source": frappe.utils.cint(doc.is_strict_so_source)}
    # 跨单占用用纯 SQL 独立算一遍（作为对补丁内部算法的交叉验证）
    occ_rows = frappe.db.sql("""
        SELECT dp.name AS plan, dp.docstatus AS ds, SUM(iq.planned_delivery_qty) AS qty
        FROM `tabDelivery Plan` dp
        INNER JOIN `tabDelivery Plan Item Qty` iq ON iq.parent = dp.name
        WHERE dp.docstatus IN (0, 1) AND dp.name != %(self)s AND iq.tracking_number = %(tn)s
        GROUP BY dp.name, dp.docstatus
    """, {"self": plan_name, "tn": tn}, as_dict=True)
    info["sql_by_plan"] = [{"plan": r.plan, "docstatus": r.ds, "qty": frappe.utils.flt(r.qty)}
                           for r in occ_rows]
    info["sql_occupied_total"] = sum(frappe.utils.flt(r.qty) for r in occ_rows)
    existing = [r for r in (doc.item_qties or []) if (r.tracking_number or "").strip() == tn]
    info["this_doc_rows"] = len(existing)
    info["this_doc_planned_sum"] = sum(frappe.utils.flt(r.planned_delivery_qty) for r in existing)
    try:
        res = doc.add_item_from_tracking_number(tn)
        info["scan"] = {"ok": True, "added_qty": res.get("added_qty"),
                        "original_qty": res.get("original_qty"),
                        "other_occupied_returned": res.get("other_occupied")}
    except Exception as exc:
        info["scan"] = {"ok": False, "error": str(exc)[:400]}
    frappe.db.rollback()
    frappe.response["data"] = info
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
    print(f"[{client.base_url}] 已部署临时 Server Script {SCRIPT_NAME}")


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
    ap.add_argument("action", choices=("survey", "scan", "scantwice", "validate", "ocsql", "ocsqln", "residue"))
    ap.add_argument("--site", choices=("prod", "test"), default="test")
    ap.add_argument("--plan", default=None)
    ap.add_argument("--tn", default=None)
    ap.add_argument("--n", type=int, default=450)
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
        if args.action == "survey":
            res = call(client, mode="survey")
            print(json.dumps(res, ensure_ascii=False, indent=1)[:4000])
            args.out_dir.mkdir(parents=True, exist_ok=True)
            p = args.out_dir / "dp_tn_occupy_survey.json"
            p.write_text(json.dumps(res, ensure_ascii=False, indent=1), encoding="utf-8")
            print(f"\n落盘: {p}")
        elif args.action == "ocsql":
            if not args.plan:
                raise SystemExit("✗ ocsql 需要 --plan")
            res = call(client, mode="ocsql", plan=args.plan)
            print(json.dumps(res, ensure_ascii=False, indent=1))
        elif args.action == "ocsqln":
            res = call(client, mode="ocsqln", plan=args.plan or "", n=args.n)
            print(json.dumps(res, ensure_ascii=False, indent=1))
        elif args.action == "validate":
            if not args.plan:
                raise SystemExit("✗ validate 需要 --plan")
            res = call(client, mode="validate", plan=args.plan)
            print(json.dumps(res, ensure_ascii=False, indent=1))
        else:
            if not args.plan or not args.tn:
                raise SystemExit("✗ scan / scantwice 需要 --plan 与 --tn")
            res = call(client, mode=args.action, plan=args.plan, tn=args.tn)
            print(json.dumps(res, ensure_ascii=False, indent=1))
    finally:
        drop_script(client)
    return 0


if __name__ == "__main__":
    sys.exit(main())
