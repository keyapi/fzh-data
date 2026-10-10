# -*- coding: utf-8 -*-
"""只读分析：出库单里 `against_sales_order` 为空的行，能否反查它是哪个销售订单的货。

- 组成：这些行按物料组/仓库分布（判断有多少是"成品/皮壳/内胆"这类真该归因的，多少是辅料/包材）
- 头部线索可用性：DN.delivery_plan / dn.po_no / dni.so_detail / dni.stock_tracking_number 到底有多少非空
- 代理反查：对样品物料，用 `tabWork Order.sales_order`（该物料是为哪张 SO 生产的）看能否倒推出唯一 SO

只读；临时 Server Script 用 zz_ 前缀，用完即删。
"""
from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path

sys.stdout.reconfigure(encoding="utf-8")

from bom_fabric_length_check import ENV_KEYS, ENV_URLS, ErpnextClient, load_env  # noqa: E402

SCRIPT_NAME = "zz_dn_no_so_attr"
API_METHOD = SCRIPT_NAME

SERVER_SCRIPT = '''fr = frappe.form_dict.get("from") or "2020-01-01"
P = {"fr": fr}

BASE = (" FROM `tabDelivery Note Item` dni"
        " INNER JOIN `tabDelivery Note` dn ON dn.name = dni.parent"
        " WHERE dn.docstatus = 1 AND dn.is_return = 0"
        " AND dn.posting_date >= %(fr)s"
        " AND IFNULL(dni.against_sales_order, '') = ''")

out = {"from": fr}

# 1) 组成：按物料组
rows = frappe.db.sql("SELECT IFNULL(dni.item_group, '(空)') AS grp, COUNT(*) AS rows_cnt,"
                     " SUM(dni.qty) AS qty" + BASE +
                     " GROUP BY grp ORDER BY rows_cnt DESC LIMIT 30", P, as_dict=True)
out["by_item_group"] = [{"item_group": r.grp, "rows": r.rows_cnt, "qty": frappe.utils.flt(r.qty)} for r in rows]

# 2) 组成：按仓库
rows = frappe.db.sql("SELECT IFNULL(dni.warehouse, '(空)') AS wh, COUNT(*) AS rows_cnt,"
                     " SUM(dni.qty) AS qty" + BASE +
                     " GROUP BY wh ORDER BY rows_cnt DESC", P, as_dict=True)
out["by_warehouse"] = [{"warehouse": r.wh, "rows": r.rows_cnt, "qty": frappe.utils.flt(r.qty)} for r in rows]

# 3) 这些行上还有哪些"来源线索"可用
rows = frappe.db.sql("SELECT COUNT(*) AS total,"
                     " SUM(CASE WHEN IFNULL(dn.delivery_plan, '') != '' THEN 1 ELSE 0 END) AS has_plan,"
                     " SUM(CASE WHEN IFNULL(dn.po_no, '') != '' THEN 1 ELSE 0 END) AS has_po_no,"
                     " SUM(CASE WHEN IFNULL(dni.so_detail, '') != '' THEN 1 ELSE 0 END) AS has_so_detail,"
                     " SUM(CASE WHEN IFNULL(dni.stock_tracking_number, '') != '' THEN 1 ELSE 0 END) AS has_tracking,"
                     " SUM(CASE WHEN IFNULL(dn.customer, '') != '' THEN 1 ELSE 0 END) AS has_customer"
                     + BASE, P, as_dict=True)
r0 = rows[0]
out["signal_availability"] = {"total": r0.total, "has_delivery_plan": r0.has_plan, "has_po_no": r0.has_po_no,
                              "has_so_detail": r0.has_so_detail, "has_tracking": r0.has_tracking,
                              "has_customer": r0.has_customer}

# 4) 样品：按数量最大的 30 行
rows = frappe.db.sql("SELECT dn.name AS dn, dn.posting_date AS pd, dn.customer AS cust,"
                     " IFNULL(dn.delivery_plan, '') AS plan, dni.item_code AS item,"
                     " IFNULL(dni.item_group, '') AS grp, dni.qty AS qty,"
                     " IFNULL(dni.warehouse, '') AS wh" + BASE +
                     " ORDER BY dni.qty DESC LIMIT 30", P, as_dict=True)
out["sample"] = [{"dn": r.dn, "posting_date": str(r.pd), "customer": r.cust, "delivery_plan": r.plan,
                  "item_code": r.item, "item_group": r.grp, "qty": frappe.utils.flt(r.qty),
                  "warehouse": r.wh} for r in rows]

# 5) 代理反查：样品物料通过生产工单能倒出哪些 SO
codes = []
for r in out["sample"]:
    if r["item_code"] not in codes:
        codes.append(r["item_code"])
codes = codes[:12]
proxy = []
for it in codes:
    ws = frappe.db.sql("SELECT DISTINCT sales_order FROM `tabWork Order`"
                       " WHERE production_item = %(i)s AND docstatus = 1"
                       " AND IFNULL(sales_order, '') != ''", {"i": it}, as_dict=True)
    proxy.append({"item_code": it, "wo_sales_orders": [x.sales_order for x in ws]})
out["proxy_wo_sales_order"] = proxy

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
        print(f"  已删除临时 Server Script {SCRIPT_NAME}（残留 0）")


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--from", dest="fr", default="2020-01-01")
    ap.add_argument("--site", choices=("prod", "test"), default="prod")
    ap.add_argument("--out-dir", type=Path, default=Path(__file__).resolve().parent / "out")
    args = ap.parse_args()
    key, sec = load_env(args.site)
    client = ErpnextClient(ENV_URLS[args.site], key, sec)
    ensure_script(client)
    try:
        res = call(client, **{"from": args.fr})
        s = res["signal_availability"]
        print(f"\n窗口：自 {res['from']} 起，against_sales_order 为空的出库行（已提交、非退货），共 {s['total']} 行")
        print("\n== 这些行手上还有哪些来源线索 ==")
        print(f"   DN.delivery_plan 非空: {s['has_delivery_plan']}   dn.po_no 非空: {s['has_po_no']}")
        print(f"   dni.so_detail 非空:   {s['has_so_detail']}   dni.stock_tracking_number 非空: {s['has_tracking']}")
        print(f"   dn.customer 非空:     {s['has_customer']}")
        print("\n== 按物料组（TOP30） ==")
        for r in res["by_item_group"]:
            print(f"   {str(r['item_group']):<30} 行数={r['rows']:>5}  件数={r['qty']:>9.0f}")
        print("\n== 按仓库 ==")
        for r in res["by_warehouse"]:
            print(f"   {str(r['warehouse']):<28} 行数={r['rows']:>5}  件数={r['qty']:>9.0f}")
        print("\n== 代理反查：样品物料的工单 SO（看能否唯一倒推） ==")
        for p in res["proxy_wo_sales_order"]:
            print(f"   {p['item_code'][:40]:<40} 工单SO={p['wo_sales_orders']}")
        args.out_dir.mkdir(parents=True, exist_ok=True)
        p = args.out_dir / f"dn_no_so_attribution_{args.fr}.json"
        p.write_text(json.dumps(res, ensure_ascii=False, indent=1, default=str), encoding="utf-8")
        print(f"\n落盘: {p}")
    finally:
        drop_script(client)
    return 0


if __name__ == "__main__":
    sys.exit(main())
