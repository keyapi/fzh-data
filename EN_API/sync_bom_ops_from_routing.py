# -*- coding: utf-8 -*-
"""按工艺路线同步「引用该工艺路线的 BOM」的工序子表（复刻 work_order_task 的按钮逻辑）。

按钮 `key_test/work_order_task/js/routing.js` -> `根据来源物料更新BOM`
-> `work_order_task.work_order_task.utils.routing.update_bom_by_source_item(source_item, routing_name)`
里那一段「凡 BOM.routing == routing_name 的也纳入」的 referrer 分支：
  已提交 BOM: db.set_value(with_operations/routing) + 删掉工序子表 -> 按工艺路线重建 + 重算成本 + 版本记录
  草稿 BOM:   doc.routing = routing_name; doc.get_routing(); doc.save()

为什么用临时 Server Script 而不是直接调那个接口：
  * 那个接口要求 source_item 是「内胆#/重量模板#」物料，包装工艺路线没有来源物料 -> 接口直接返回失败；
  * `batch_update_selected_routings` 对没有 source_items 的路线显式 skip；
  * 已提交 BOM 必须走服务端（REST 不能改已提交单据，且要直接删子表行）；
  * 1,570 个 BOM 放一个 HTTP 请求里必然超时，所以需要服务端侧分批 + 断点续跑。
生产机 SSH 不通，于是在生产上临时建一条 API 型 Server Script，跑完即删。

Server Script 沙箱限制（frappe.utils.safe_exec，已实测）：
  * 任何以 `_` 开头的变量名/属性名都被拒绝 -> 不能 import 那个私有函数 `_update_bom_operations_from_routing`
  * 没有 frappe.db.delete；frappe.db.sql 只允许 SELECT
  * 可用：frappe.get_all / get_doc / new_doc / delete_doc / db.set_value / db.commit / frappe.utils.flt
  * 不能写 lambda / 海象表达式

用法:
  python sync_bom_ops_from_routing.py --env test count
  python sync_bom_ops_from_routing.py --env test deploy
  python sync_bom_ops_from_routing.py --env test run --page 20
  python sync_bom_ops_from_routing.py --env test cleanup
  python sync_bom_ops_from_routing.py --env test report
"""
from __future__ import annotations

import argparse
import json
import os
import time
from pathlib import Path
from typing import Any
from urllib.parse import quote

import requests
from requests.adapters import HTTPAdapter

_DIR = Path(__file__).resolve().parent
_ENV_URLS = {"prod": "https://erpnext.vilavi.cn", "test": "https://ensh.vilavi.cn"}
_ENV_KEYS = {
    "prod": ("PROD_ERP_API_KEY", "PROD_ERP_API_SECRET"),
    "test": ("TEST_ERP_API_KEY", "TEST_ERP_API_SECRET"),
}
SCRIPT_NAME = "zz_sync_bom_ops_from_routing"
DEFAULT_ROUTING = "包装工艺路线"


def _load_dotenv(candidates: list[Path]) -> None:
    for p in candidates:
        if not p.is_file():
            continue
        for line in p.read_text(encoding="utf-8").splitlines():
            line = line.strip()
            if not line or line.startswith("#") or "=" not in line:
                continue
            k, _, v = line.partition("=")
            k, v = k.strip(), v.strip()
            if len(v) >= 2 and v[0] == v[-1] and v[0] in ('"', "'"):
                v = v[1:-1]
            os.environ.setdefault(k, v)


class _NoExpectAdapter(HTTPAdapter):
    def send(self, request, **kwargs):
        request.headers.pop("Expect", None)
        return super().send(request, **kwargs)


class ErpnextClient:
    def __init__(self, base_url: str, api_key: str, api_secret: str) -> None:
        self.base_url = base_url.rstrip("/")
        self.session = requests.Session()
        self.session.headers["Authorization"] = f"token {api_key}:{api_secret}"
        self.session.mount("https://", _NoExpectAdapter())
        self.session.mount("http://", _NoExpectAdapter())

    def _request(self, method: str, path: str, *, retries: int = 1,
                 retry_delay: float = 3.0, **kwargs: Any) -> requests.Response:
        timeout = kwargs.pop("timeout", (30, 600))
        url = f"{self.base_url}{path}"
        last: Exception | None = None
        for attempt in range(retries + 1):
            try:
                r = self.session.request(method, url, timeout=timeout, **kwargs)
                r.raise_for_status()
                return r
            except requests.RequestException as exc:
                last = exc
                if attempt < retries:
                    time.sleep(retry_delay)
        assert last is not None
        raise last

    def get_list(self, doctype: str, filters: list | None = None,
                 fields: list[str] | None = None) -> list[dict]:
        params: dict[str, str] = {"limit_page_length": "0"}
        if filters is not None:
            params["filters"] = json.dumps(filters)
        if fields is not None:
            params["fields"] = json.dumps(fields)
        return self._request("GET", f"/api/resource/{quote(doctype, safe='')}",
                             params=params).json()["data"]

    def call(self, method: str, **params) -> Any:
        r = self._request("POST", f"/api/method/{method}", data=params)
        body = r.json()
        return body.get("data") if "data" in body else body.get("message")


# ── 部署到目标环境的 Server Script（沙箱内运行，注意不能出现 `_` 开头的名字）──
SERVER_SCRIPT = '''start = int(frappe.form_dict.get("start") or 0)
page = int(frappe.form_dict.get("page") or 20)
routing_name = frappe.form_dict.get("routing_name") or "包装工艺路线"

def rebuild_operations(bom_name, routing_ops, conversion_rate):
    olds = frappe.get_all("BOM Operation",
        filters={"parenttype": "BOM", "parent": bom_name},
        fields=["name"])
    for one in olds:
        frappe.delete_doc("BOM Operation", one["name"],
            force=True, ignore_permissions=True, ignore_on_trash=True)
    for position, src in enumerate(routing_ops, start=1):
        data = {
            "doctype": "BOM Operation",
            "parent": bom_name,
            "parentfield": "operations",
            "parenttype": "BOM",
            "idx": src["idx"] or position,
            "sequence_id": src["sequence_id"],
            "operation": src["operation"],
            "workstation": src["workstation"],
            "workstation_type": src["workstation_type"],
            "description": src["description"],
            "time_in_mins": src["time_in_mins"],
            "batch_size": src["batch_size"] or 1,
            "fixed_time": src["fixed_time"] or 0,
            "set_cost_based_on_bom_qty": src["set_cost_based_on_bom_qty"] or 0,
        }
        hour_rate = frappe.utils.flt(src["hour_rate"])
        if hour_rate and conversion_rate:
            data["hour_rate"] = hour_rate / frappe.utils.flt(conversion_rate)
        else:
            data["hour_rate"] = hour_rate
        for extra in ("hour_rate_labour", "operation_labour",
                      "hour_rate_manage", "operation_manage_cost"):
            if src.get(extra):
                data[extra] = src[extra]
        child = frappe.get_doc(data)
        child.insert(ignore_permissions=True)

    bom_doc = frappe.get_doc("BOM", bom_name)
    quantity = frappe.utils.flt(bom_doc.quantity or 1)
    new_rows = frappe.get_all("BOM Operation",
        filters={"parenttype": "BOM", "parent": bom_name},
        fields=["name", "hour_rate", "time_in_mins", "batch_size",
                "operating_cost", "set_cost_based_on_bom_qty"])
    for doc_row in new_rows:
        if not doc_row.hour_rate or not doc_row.time_in_mins:
            continue
        cost = frappe.utils.flt(doc_row.hour_rate) * frappe.utils.flt(doc_row.time_in_mins) / 60.0
        base_cost = cost * frappe.utils.flt(conversion_rate) if conversion_rate else cost
        batch = frappe.utils.flt(doc_row.batch_size or 1)
        per_unit = cost / batch if batch > 0 else 0
        base_per_unit = base_cost / batch if batch > 0 else 0
        if doc_row.set_cost_based_on_bom_qty:
            cost = per_unit * quantity
            base_cost = base_per_unit * quantity
        frappe.db.set_value("BOM Operation", doc_row.name, {
            "operating_cost": cost,
            "base_operating_cost": base_cost,
            "base_hour_rate": frappe.utils.flt(doc_row.hour_rate) * frappe.utils.flt(conversion_rate)
                if conversion_rate else doc_row.hour_rate,
            "cost_per_unit": per_unit,
            "base_cost_per_unit": base_per_unit,
        }, update_modified=False)

    total = 0
    base_total = 0
    after = frappe.get_all("BOM Operation",
        filters={"parenttype": "BOM", "parent": bom_name},
        fields=["operating_cost", "base_operating_cost"])
    for item_row in after:
        total = total + frappe.utils.flt(item_row.operating_cost or 0)
        base_total = base_total + frappe.utils.flt(item_row.base_operating_cost or 0)

    material = frappe.db.get_value("BOM", bom_name,
        ["raw_material_cost", "base_raw_material_cost",
         "scrap_material_cost", "base_scrap_material_cost"], as_dict=True)
    raw = frappe.utils.flt(material.raw_material_cost or 0)
    base_raw = frappe.utils.flt(material.base_raw_material_cost or 0)
    scrap = frappe.utils.flt(material.scrap_material_cost or 0)
    base_scrap = frappe.utils.flt(material.base_scrap_material_cost or 0)

    frappe.db.set_value("BOM", bom_name, {
        "operating_cost": total,
        "base_operating_cost": base_total,
        "total_cost": total + raw - scrap,
        "base_total_cost": base_total + base_raw - base_scrap,
    }, update_modified=False)


def process(bom_row, routing_ops):
    bom_name = bom_row["name"]
    if bom_row["docstatus"] == 1:
        if not bom_row["with_operations"]:
            frappe.db.set_value("BOM", bom_name, "with_operations", 1)
        frappe.db.set_value("BOM", bom_name, "routing", routing_name)
        rebuild_operations(bom_name, routing_ops, bom_row["conversion_rate"])
    else:
        draft = frappe.get_doc("BOM", bom_name)
        draft.with_operations = 1
        draft.routing = routing_name
        draft.get_routing()
        draft.save(ignore_permissions=True)


routing_ops = frappe.get_all("BOM Operation",
    filters={"parenttype": "Routing", "parent": routing_name},
    fields=["sequence_id", "operation", "workstation", "workstation_type", "description",
            "time_in_mins", "batch_size", "operating_cost", "idx", "hour_rate",
            "set_cost_based_on_bom_qty", "fixed_time",
            "hour_rate_labour", "operation_labour", "hour_rate_manage", "operation_manage_cost"],
    order_by="sequence_id, idx")

targets = frappe.get_all("BOM",
    filters={"routing": routing_name, "docstatus": ["<", 2]},
    fields=["name", "docstatus", "with_operations", "conversion_rate"],
    order_by="name", limit_start=start, limit_page_length=page)

ok = []
bad = []
for target in targets:
    try:
        process(target, routing_ops)
        ok.append(target["name"])
    except Exception as exc:
        bad.append(target["name"] + " :: " + repr(exc)[:140])

if frappe.form_dict.get("no_commit"):
    pass
else:
    frappe.db.commit()

frappe.response["data"] = {
    "routing": routing_name,
    "start": start,
    "page": page,
    "routing_ops": len(routing_ops),
    "processed": len(ok),
    "failed": len(bad),
    "names": ok,
    "errors": bad[:20],
}
'''


def make_client(env: str) -> ErpnextClient:
    key_name, secret_name = _ENV_KEYS[env]
    key, secret = os.getenv(key_name, ""), os.getenv(secret_name, "")
    if not key or not secret:
        raise SystemExit(f"缺少 {key_name} / {secret_name}")
    base = os.getenv("PROD_ERP_URL" if env == "prod" else "TEST_ERP_URL", _ENV_URLS[env])
    return ErpnextClient(base, key, secret)


def cmd_count(client: ErpnextClient, routing: str) -> None:
    rows = client.get_list("BOM", filters=[["routing", "=", routing], ["docstatus", "<", 2]],
                           fields=["name", "docstatus", "with_operations"])
    from collections import Counter
    print(f"引用 {routing} 的 BOM: {len(rows)}")
    print("  docstatus:", dict(Counter(r["docstatus"] for r in rows)))
    print("  with_operations:", dict(Counter(r["with_operations"] for r in rows)))


def cmd_deploy(client: ErpnextClient, routing: str) -> None:
    try:
        client._request("DELETE", f"/api/resource/Server Script/{SCRIPT_NAME}",
                        timeout=60, retries=0)
    except requests.HTTPError:
        pass
    body = {"name": SCRIPT_NAME, "script_type": "API", "api_method": SCRIPT_NAME,
            "script": SERVER_SCRIPT, "allow_guest": 0, "disabled": 0}
    r = client._request("POST", "/api/resource/Server Script", json=body,
                        timeout=60).json()["data"]
    print(f"已部署 Server Script: {r['name']} (api_method={r.get('api_method')})")


def cmd_run(client: ErpnextClient, routing: str, page: int, start: int,
            max_pages: int | None) -> None:
    total_ok = total_bad = 0
    pages = 0
    while True:
        res = client.call(SCRIPT_NAME, routing_name=routing, start=start, page=page)
        if not isinstance(res, dict):
            print("返回异常:", res)
            return
        print(f"  start={start:<5} 处理 {res['processed']} 失败 {res['failed']} "
              f"(路线工序数 {res['routing_ops']})")
        for err in res.get("errors") or []:
            print("     ERR", err)
        total_ok += res["processed"]
        total_bad += res["failed"]
        pages += 1
        if res["processed"] == 0 and res["failed"] == 0:
            break
        start += page
        if max_pages and pages >= max_pages:
            print(f"  达到 --max-pages={max_pages}，停下")
            break
    print(f"累计：处理 {total_ok}，失败 {total_bad}")


def cmd_cleanup(client: ErpnextClient) -> None:
    try:
        client._request("DELETE", f"/api/resource/Server Script/{SCRIPT_NAME}",
                        timeout=60, retries=0)
        print("已删除 Server Script")
    except requests.HTTPError as exc:
        print("删除失败:", exc)


def cmd_report(client: ErpnextClient, routing: str) -> None:
    """对比备份与现状，打印前后变化。"""
    import glob
    from collections import Counter
    env_tag = "test" if "ensh" in client.base_url else "prod"
    files = sorted(glob.glob(str(_DIR / "out" / f"bom_ops_backup_{env_tag}_*.json")))
    if not files:
        raise SystemExit("找不到备份文件")
    before = json.loads(Path(files[-1]).read_text(encoding="utf-8"))
    b_ops = {}
    for op in before["operations"]:
        b_ops.setdefault(op["parent"], []).append(op)

    rows = client.get_list("BOM", filters=[["routing", "=", routing], ["docstatus", "<", 2]],
                           fields=["name", "docstatus", "operating_cost", "total_cost"])
    print(f"备份: {Path(files[-1]).name}   BOM {before['meta']['bom_count']} 个")
    print(f"现状: {len(rows)} 个 BOM")
    changed = stale = 0
    samples = []
    for r in rows:
        b = b_ops.get(r["name"], [])
        bcost = sum(float(o.get("operating_cost") or 0) for o in b)
        if abs(bcost - float(r.get("operating_cost") or 0)) > 0.001:
            changed += 1
            if len(samples) < 10:
                samples.append((r["name"], bcost, r.get("operating_cost")))
        else:
            stale += 1
    print(f"BOM.operating_cost 已变化: {changed}   未变: {stale}")
    for nm, old, new in samples:
        print(f"   {nm}: {old:.3f} -> {float(new or 0):.3f}")


def main() -> int:
    ap = argparse.ArgumentParser(description="按工艺路线同步引用它的 BOM 工序（临时 Server Script）")
    ap.add_argument("action", choices=["count", "deploy", "run", "cleanup", "report"])
    ap.add_argument("--env", choices=["test", "prod"], default="test")
    ap.add_argument("--routing", default=DEFAULT_ROUTING)
    ap.add_argument("--page", type=int, default=20)
    ap.add_argument("--start", type=int, default=0)
    ap.add_argument("--max-pages", type=int, default=None)
    args = ap.parse_args()

    _load_dotenv([_DIR / ".env", _DIR.parent / ".env", _DIR.parent.parent / ".env"])
    client = make_client(args.env)
    print(f"环境: {args.env} ({client.base_url})  工艺路线: {args.routing}")

    if args.action == "count":
        cmd_count(client, args.routing)
    elif args.action == "deploy":
        cmd_deploy(client, args.routing)
    elif args.action == "run":
        cmd_run(client, args.routing, args.page, args.start, args.max_pages)
    elif args.action == "cleanup":
        cmd_cleanup(client)
    elif args.action == "report":
        cmd_report(client, args.routing)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
