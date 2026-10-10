# -*- coding: utf-8 -*-
"""只读盘点：出库单（Delivery Note）里「无菲号 / 未挂销售订单」的行有多少、长什么样。

背景：下单同事定期对账 SO→生产→出库；出库行若无菲号又未挂 SO，链条断裂、只能人肉发现。
本探针用只读 SQL 聚合，回答「这类裸行是偶发漏扫还是常态（赠品/备件/无菲号投产）」，
为「要不要禁止无菲号出库」提供事实依据。

全程只读（无写库）；临时 Server Script 用 zz_ 前缀，用完即删。

用法:
  python EN_API/dn_untracked_report.py --from 2026-01-01
  python EN_API/dn_untracked_report.py --from 2026-07-01 --site prod
"""
from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path

sys.stdout.reconfigure(encoding="utf-8")

from bom_fabric_length_check import ENV_KEYS, ENV_URLS, ErpnextClient, load_env  # noqa: E402

SCRIPT_NAME = "zz_dn_untracked_report"
API_METHOD = SCRIPT_NAME

# 沙箱限制：变量/属性不以 `_` 开头、无 lambda/海象/frappe.db.delete。
# 分类键一律用 ASCII，中文在客户端映射。
SERVER_SCRIPT = '''fr = frappe.form_dict.get("from") or "2026-01-01"
out = {"from": fr}

BASE_WHERE = """
    dn.docstatus = 1 AND dn.is_return = 0 AND dn.posting_date >= %(fr)s
"""
CAT_EXPR = """
    CASE
      WHEN IFNULL(dni.stock_tracking_number, '') = '' AND IFNULL(dni.against_sales_order, '') = ''
        THEN 'bare'
      WHEN IFNULL(dni.stock_tracking_number, '') = '' THEN 'no_tn'
      WHEN IFNULL(dni.against_sales_order, '') = '' THEN 'no_so'
      ELSE 'ok'
    END
"""

# 沙箱里 `.format()` 属 unsafe attribute，一律用字符串拼接
SELFROM = (" FROM `tabDelivery Note Item` dni"
           " INNER JOIN `tabDelivery Note` dn ON dn.name = dni.parent"
           " WHERE " + BASE_WHERE)
BARE_WHERE = SELFROM + " AND " + CAT_EXPR + " = 'bare'"

# 1) 总览：四类各多少行/多少件/金额
rows = frappe.db.sql(
    "SELECT " + CAT_EXPR + " AS cat, COUNT(*) AS rows_cnt, SUM(dni.qty) AS qty, SUM(dni.amount) AS amt"
    + SELFROM + " GROUP BY cat", {"fr": fr}, as_dict=True)
out["overview"] = [{"cat": r.cat, "rows": r.rows_cnt, "qty": frappe.utils.flt(r.qty),
                    "amount": frappe.utils.flt(r.amt)} for r in rows]

# 2) 裸行(bare) 按 物料组
rows = frappe.db.sql(
    "SELECT IFNULL(dni.item_group, '(空)') AS grp, COUNT(*) AS rows_cnt, SUM(dni.qty) AS qty"
    + BARE_WHERE + " GROUP BY grp ORDER BY qty DESC", {"fr": fr}, as_dict=True)
out["bare_by_item_group"] = [{"item_group": r.grp, "rows": r.rows_cnt, "qty": frappe.utils.flt(r.qty)} for r in rows]

# 3) 裸行 按 客户
rows = frappe.db.sql(
    "SELECT IFNULL(dn.customer, '(空)') AS cust, COUNT(*) AS rows_cnt, SUM(dni.qty) AS qty"
    + BARE_WHERE + " GROUP BY cust ORDER BY qty DESC LIMIT 25", {"fr": fr}, as_dict=True)
out["bare_by_customer"] = [{"customer": r.cust, "rows": r.rows_cnt, "qty": frappe.utils.flt(r.qty)} for r in rows]

# 4) 裸行 按 仓库
rows = frappe.db.sql(
    "SELECT IFNULL(dni.warehouse, '(空)') AS wh, COUNT(*) AS rows_cnt, SUM(dni.qty) AS qty"
    + BARE_WHERE + " GROUP BY wh ORDER BY qty DESC", {"fr": fr}, as_dict=True)
out["bare_by_warehouse"] = [{"warehouse": r.wh, "rows": r.rows_cnt, "qty": frappe.utils.flt(r.qty)} for r in rows]

# 5) 裸行 按月
rows = frappe.db.sql(
    "SELECT SUBSTRING(dn.posting_date, 1, 7) AS ym, COUNT(*) AS rows_cnt, SUM(dni.qty) AS qty"
    + BARE_WHERE + " GROUP BY ym ORDER BY ym", {"fr": fr}, as_dict=True)
out["bare_by_month"] = [{"month": r.ym, "rows": r.rows_cnt, "qty": frappe.utils.flt(r.qty)} for r in rows]

# 6) 裸行明细 TOP（按数量）
rows = frappe.db.sql(
    "SELECT dn.name AS dn, dn.posting_date AS pd, dn.customer AS cust, dni.idx AS idx,"
    " dni.item_code AS item, IFNULL(dni.item_group,'') AS grp, dni.qty AS qty,"
    " dni.rate AS rate, IFNULL(dni.warehouse,'') AS wh"
    + BARE_WHERE + " ORDER BY dni.qty DESC LIMIT 40", {"fr": fr}, as_dict=True)
out["bare_top_rows"] = [{"dn": r.dn, "posting_date": str(r.pd), "customer": r.cust, "idx": r.idx,
                         "item_code": r.item, "item_group": r.grp, "qty": frappe.utils.flt(r.qty),
                         "rate": frappe.utils.flt(r.rate), "warehouse": r.wh} for r in rows]

# 7) 有菲号但未挂 SO 的 TOP（这类更容易被忽略）
rows = frappe.db.sql(
    "SELECT dn.name AS dn, dn.posting_date AS pd, dni.idx AS idx, dni.item_code AS item,"
    " dni.qty AS qty, dni.stock_tracking_number AS tn"
    + SELFROM + " AND " + CAT_EXPR + " = 'no_so' ORDER BY dni.qty DESC LIMIT 20",
    {"fr": fr}, as_dict=True)
out["no_so_top_rows"] = [{"dn": r.dn, "posting_date": str(r.pd), "idx": r.idx, "item_code": r.item,
                          "qty": frappe.utils.flt(r.qty), "tracking_number": r.tn} for r in rows]

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
    ap.add_argument("--from", dest="fr", default="2026-01-01")
    ap.add_argument("--site", choices=("prod", "test"), default="prod")
    ap.add_argument("--out-dir", type=Path, default=Path(__file__).resolve().parent / "out")
    args = ap.parse_args()

    key, sec = load_env(args.site)
    if not key or not sec:
        print(f"✗ 缺 {ENV_KEYS[args.site]} 凭证")
        return 1
    client = ErpnextClient(ENV_URLS[args.site], key, sec)

    ensure_script(client)
    try:
        res = call(client, **{"from": args.fr})
        CAT = {"bare": "裸行(无菲号+未挂SO)", "no_tn": "仅无菲号", "no_so": "仅未挂SO", "ok": "正常"}
        print(f"\n统计窗口：自 {res['from']} 起（已提交、非退货的出库单）")
        print("\n== 总览 ==")
        for r in res["overview"]:
            print(f"   {CAT.get(r['cat'], r['cat']):<22} 行数={r['rows']:>6}  件数={r['qty']:>9.0f}  金额={r['amount']:>14,.2f}")
        for key_, title in (("bare_by_item_group", "裸行·按物料组"), ("bare_by_warehouse", "裸行·按仓库"),
                            ("bare_by_month", "裸行·按月"), ("bare_by_customer", "裸行·按客户(TOP25)")):
            print(f"\n== {title} ==")
            for r in res.get(key_, []):
                k = r.get("item_group") or r.get("warehouse") or r.get("month") or r.get("customer")
                print(f"   {str(k):<34} 行数={r['rows']:>5}  件数={r['qty']:>8.0f}")
        print("\n== 裸行明细 TOP40（按数量） ==")
        for r in res.get("bare_top_rows", []):
            print(f"   {str(r['posting_date'])[:10]} {r['dn']:<16} idx={r['idx']:>4} {r['item_code'][:38]:<38} "
                  f"qty={r['qty']:>6.0f} rate={r['rate']:>9.2f} {r['warehouse'][:20]:<20} {r['item_group']}")
        print("\n== 有菲号但未挂SO TOP20 ==")
        for r in res.get("no_so_top_rows", []):
            print(f"   {str(r['posting_date'])[:10]} {r['dn']:<16} idx={r['idx']:>4} {r['item_code'][:38]:<38} "
                  f"qty={r['qty']:>6.0f} tn={r['tracking_number']}")
        args.out_dir.mkdir(parents=True, exist_ok=True)
        p = args.out_dir / f"dn_untracked_report_{args.fr}.json"
        p.write_text(json.dumps(res, ensure_ascii=False, indent=1, default=str), encoding="utf-8")
        print(f"\n落盘: {p}")
    finally:
        drop_script(client)
    return 0


if __name__ == "__main__":
    sys.exit(main())
