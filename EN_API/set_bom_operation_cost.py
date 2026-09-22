# -*- coding: utf-8 -*-
"""把指定 BOM 的工序改成统一工费率/工时/工费，并同步 BOM 主表成本。

默认目标（用户指定，不含 BOM-SXBZCP#KS0437-120x200x45-001 —— 该 BOM 没有工序，保持不变）：
  BOM-SXBZBCP#KS0437-120x200x45-001  已提交
  BOM-SXBZBCP#KS0437-120x200x45-002  已提交
  BOM-SXBZBCP#KS0437-120x200x45-003  已提交
  BOM-SXBZBCP#KS0437-120x200x45-004  已提交
  BOM-SXBZBCP#KS0437-120x200x45-005  草稿

改动内容（逐 BOM）：
  1. 工序行：hour_rate / base_hour_rate = 23.2；time_in_mins = 28；operating_cost /
     base_operating_cost / cost_per_unit / base_cost_per_unit = 10.827
  2. BOM 主表：operating_cost / base_operating_cost = Σ工序工费；total_cost /
     base_total_cost = 该值 + 原材料成本 − 废料成本；operating_cost_per_bom_quantity

已提交 BOM 不能走 REST 保存（且不需要重建工序行），所以用临时 API Server Script + frappe.db.set_value。
用法:
  python set_bom_operation_cost.py                 # dry-run，只读
  python set_bom_operation_cost.py --apply         # 执行
  python set_bom_operation_cost.py --verify
"""
from __future__ import annotations

import argparse
import json
from pathlib import Path

import requests

from sync_bom_ops_from_routing import ErpnextClient, _DIR, _load_dotenv, make_client

SCRIPT_NAME = "zz_set_bom_operation_cost"

TARGETS = [
    "BOM-SXBZBCP#KS0437-120x200x45-001",
    "BOM-SXBZBCP#KS0437-120x200x45-002",
    "BOM-SXBZBCP#KS0437-120x200x45-003",
    "BOM-SXBZBCP#KS0437-120x200x45-004",
    "BOM-SXBZBCP#KS0437-120x200x45-005",
]
RATE = 23.2
TIME = 28.0
COST = 10.827

SERVER_SCRIPT = '''names = json.loads(frappe.form_dict.get("names"))
rate = frappe.utils.flt(frappe.form_dict.get("rate"))
mins = frappe.utils.flt(frappe.form_dict.get("time"))
cost = frappe.utils.flt(frappe.form_dict.get("cost"))

done = []
bad = []
for bom_name in names:
    try:
        rows = frappe.get_all("BOM Operation",
            filters={"parenttype": "BOM", "parent": bom_name}, fields=["name"])
        total = 0
        for one in rows:
            frappe.db.set_value("BOM Operation", one["name"], {
                "hour_rate": rate, "base_hour_rate": rate,
                "time_in_mins": mins,
                "operating_cost": cost, "base_operating_cost": cost,
                "cost_per_unit": cost, "base_cost_per_unit": cost,
            }, update_modified=False)
            total = total + cost
        head = frappe.db.get_value("BOM", bom_name,
            ["raw_material_cost", "base_raw_material_cost",
             "scrap_material_cost", "base_scrap_material_cost", "quantity"], as_dict=True)
        qty = frappe.utils.flt(head.quantity or 1)
        if not qty:
            qty = 1
        frappe.db.set_value("BOM", bom_name, {
            "operating_cost": total,
            "base_operating_cost": total,
            "total_cost": total + frappe.utils.flt(head.raw_material_cost or 0)
                          - frappe.utils.flt(head.scrap_material_cost or 0),
            "base_total_cost": total + frappe.utils.flt(head.base_raw_material_cost or 0)
                               - frappe.utils.flt(head.base_scrap_material_cost or 0),
            "operating_cost_per_bom_quantity": total / qty,
        }, update_modified=False)
        done.append(bom_name + " | ops=" + str(len(rows)) + " | op_cost=" + str(total))
    except Exception as exc:
        bad.append(bom_name + " :: " + repr(exc)[:140])

frappe.db.commit()
frappe.response["data"] = {"processed": len(done), "failed": len(bad),
                           "detail": done, "errors": bad}
'''


def _delete_script(client: ErpnextClient) -> None:
    try:
        client._request("DELETE", f"/api/resource/Server Script/{SCRIPT_NAME}",
                        timeout=60, retries=0)
    except requests.HTTPError:
        pass


def show(client: ErpnextClient, names: list[str]) -> None:
    for n in names:
        d = client._request("GET", f"/api/resource/BOM/{requests.utils.quote(n, safe='')}",
                            timeout=60).json()["data"]
        ops = d.get("operations") or []
        print(f"■ {n}  docstatus={d['docstatus']}")
        print(f"   前: 工序 {len(ops)} 行 " + "; ".join(
            f"{o.get('operation')}/{o.get('workstation')} {o.get('hour_rate')}×{o.get('time_in_mins')}={o.get('operating_cost')}"
            for o in ops))
        print(f"   BOM 前: operating_cost={d.get('operating_cost')} total_cost={d.get('total_cost')} "
              f"raw={d.get('raw_material_cost')} scrap={d.get('scrap_material_cost')}")


def main() -> int:
    ap = argparse.ArgumentParser(description="把指定 BOM 的工序设为统一工费率/工时/工费")
    ap.add_argument("action", choices=["dry", "apply", "verify"], nargs="?", default="dry")
    ap.add_argument("--env", choices=["test", "prod"], default="prod")
    ap.add_argument("--boms", default=",".join(TARGETS))
    args = ap.parse_args()

    _load_dotenv([_DIR / ".env", _DIR.parent / ".env", _DIR.parent.parent / ".env"])
    client = make_client(args.env)
    names = [x.strip() for x in args.boms.split(",") if x.strip()]
    print(f"环境: {args.env} ({client.base_url})  目标 {len(names)} 个 BOM   "
          f"目标值 hour_rate={RATE} time_in_mins={TIME} operating_cost={COST}")

    if args.action == "dry":
        show(client, names)
        print("\n[dry-run] 将执行：临时 Server Script -> 每个 BOM 的工序行写 "
              f"{RATE}/{TIME}/{COST}，主表按新工费重算。加 --apply 才写入。")
        return 0

    if args.action == "verify":
        bad = 0
        for n in names:
            d = client._request("GET", f"/api/resource/BOM/{requests.utils.quote(n, safe='')}",
                                timeout=60).json()["data"]
            ops = d.get("operations") or []
            want_total = COST * len(ops)
            ok = all(abs(float(o.get("hour_rate") or 0) - RATE) < 1e-9
                     and abs(float(o.get("time_in_mins") or 0) - TIME) < 1e-9
                     and abs(float(o.get("operating_cost") or 0) - COST) < 1e-9 for o in ops)
            want_bom_total = want_total + float(d.get("raw_material_cost") or 0) - float(d.get("scrap_material_cost") or 0)
            ok = ok and abs(float(d.get("operating_cost") or 0) - want_total) < 1e-9 \
                 and abs(float(d.get("total_cost") or 0) - want_bom_total) < 1e-9
            print(f"  {'OK ' if ok else 'BAD'} {n}: ops={len(ops)} "
                  f"op_cost={d.get('operating_cost')} total_cost={d.get('total_cost')}")
            bad += 0 if ok else 1
        print(f"校验: {'全部一致' if not bad else str(bad) + ' 个不一致'}")
        return 1 if bad else 0

    _delete_script(client)
    r = client._request("POST", "/api/resource/Server Script",
                        json={"name": SCRIPT_NAME, "script_type": "API", "api_method": SCRIPT_NAME,
                              "script": SERVER_SCRIPT, "allow_guest": 0, "disabled": 0},
                        timeout=60).json()["data"]
    print(f"已部署 Server Script: {r['name']}")
    try:
        res = client.call(SCRIPT_NAME, names=json.dumps(names), rate=RATE, time=TIME, cost=COST)
        print("执行结果:", json.dumps(res, ensure_ascii=False, indent=1))
    finally:
        _delete_script(client)
        print("已删除 Server Script")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
