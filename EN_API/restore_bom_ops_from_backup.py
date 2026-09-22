# -*- coding: utf-8 -*-
"""把「引用 包装工艺路线 的 BOM」按备份恢复回按钮执行前的状态。

背景：有人给 包装工艺路线 加了 source_items 并点了「根据来源物料更新BOM」，
      该按钮会把所有引用这条工艺路线的 BOM 的工序子表删掉重建 -> 费率/工作站/工时
      全被替换成工艺路线那一条，1,570 个 BOM 的 operating_cost 全变成 10.827。
备份：out/bom_ops_backup_prod_YYYYmmdd_HHMMSS.json（按钮执行前 13 分钟抓的完整快照）。

恢复内容（逐 BOM）：
  1. 删掉现在的工序行，按备份重建（含原行 name / docstatus）
  2. 写回 BOM 主表字段 operating_cost / base_operating_cost / total_cost /
     base_total_cost / raw_material_cost / base_raw_material_cost /
     scrap_material_cost / base_scrap_material_cost / exploded_operating_cost_qty /
     with_operations / routing

用法:
  python restore_bom_ops_from_backup.py --env prod probe            # 验证沙箱里 json 可用
  python restore_bom_ops_from_backup.py --env prod deploy
  python restore_bom_ops_from_backup.py --env prod run --page 20 --start 0 --max-pages 1   # 先小批试
  python restore_bom_ops_from_backup.py --env prod run --page 20    # 全量
  python restore_bom_ops_from_backup.py --env prod verify
  python restore_bom_ops_from_backup.py --env prod cleanup
"""
from __future__ import annotations

import argparse
import glob
import json
import sys
from pathlib import Path

import requests

from sync_bom_ops_from_routing import ErpnextClient, _DIR, _load_dotenv, make_client

SCRIPT_NAME = "zz_restore_bom_ops_from_backup"

BOM_FIELDS = [
    "operating_cost", "base_operating_cost", "total_cost", "base_total_cost",
    "raw_material_cost", "base_raw_material_cost", "scrap_material_cost",
    "base_scrap_material_cost", "exploded_operating_cost_qty",
    "with_operations", "routing",
]

OP_FIELDS = [
    "name", "idx", "sequence_id", "operation", "workstation", "workstation_type",
    "description", "time_in_mins", "hour_rate", "operating_cost", "batch_size",
    "fixed_time", "set_cost_based_on_bom_qty", "hour_rate_labour", "operation_labour",
    "hour_rate_manage", "operation_manage_cost", "base_hour_rate", "base_operating_cost",
    "cost_per_unit", "base_cost_per_unit", "custom_service_price",
    "custom_is_subcontracting", "custom_enable_wip_receipt", "custom_tax_rate",
    "custom_service_price_with_tax", "custom_labour_cost", "custom_subcontracting_cost",
    "docstatus",
]

EXOP_FIELDS = [
    "name", "idx", "item_code", "item_name", "bom_no",
    "operating_cost", "operating_cost_qty", "docstatus",
]

SERVER_SCRIPT = '''def restore_one(entry):
    bom_name = entry["name"]
    olds = frappe.get_all("BOM Operation",
        filters={"parenttype": "BOM", "parent": bom_name}, fields=["name"])
    for one in olds:
        frappe.delete_doc("BOM Operation", one["name"],
            force=True, ignore_permissions=True, ignore_on_trash=True)
    for op in entry["ops"]:
        data = {"doctype": "BOM Operation", "parent": bom_name,
                "parentfield": "operations", "parenttype": "BOM"}
        for key in entry["opkeys"]:
            if op.get(key) is not None:
                data[key] = op[key]
        status = op.get("docstatus")
        if "docstatus" in data:
            data.pop("docstatus")
        child = frappe.get_doc(data)
        child.insert(ignore_permissions=True)
        if status:
            frappe.db.set_value("BOM Operation", child.name, "docstatus", status,
                                update_modified=False)

    if entry.get("has_exops"):
        old_rows = frappe.get_all("Exploded Operation Cost Item",
            filters={"parent": bom_name}, fields=["name"])
        for one in old_rows:
            frappe.delete_doc("Exploded Operation Cost Item", one["name"],
                force=True, ignore_permissions=True, ignore_on_trash=True)
        for xr in entry["exops"]:
            data = {"doctype": "Exploded Operation Cost Item", "parent": bom_name,
                    "parentfield": "exploded_operation_cost_items", "parenttype": "BOM"}
            for key in entry["exkeys"]:
                if xr.get(key) is not None:
                    data[key] = xr[key]
            if "docstatus" in data:
                data.pop("docstatus")
            frappe.get_doc(data).insert(ignore_permissions=True)

    frappe.db.set_value("BOM", bom_name, entry["fields"], update_modified=False)


items = json.loads(frappe.form_dict.get("payload"))
done = []
bad = []
for entry in items:
    try:
        restore_one(entry)
        done.append(entry["name"])
    except Exception as exc:
        bad.append(entry["name"] + " :: " + repr(exc)[:140])

frappe.db.commit()
frappe.response["data"] = {
    "processed": len(done),
    "failed": len(bad),
    "names": done,
    "errors": bad[:20],
}
'''

PROBE_SCRIPT = '''raw = frappe.form_dict.get("payload")
parsed = json.loads(raw)
frappe.response["data"] = {"len": len(parsed), "keys": sorted(parsed[0].keys())}
'''


def load_backup(env: str) -> dict:
    files = sorted(glob.glob(str(_DIR / "out" / f"bom_ops_backup_{env}_*.json")))
    if not files:
        raise SystemExit(f"找不到 {env} 的备份文件")
    path = Path(files[-1])
    print(f"备份文件: {path.name}")
    return json.loads(path.read_text(encoding="utf-8"))


def build_entries(backup: dict, exops_only: bool = False) -> list[dict]:
    ops_by_bom: dict[str, list[dict]] = {}
    for op in backup["operations"]:
        ops_by_bom.setdefault(op["parent"], []).append(op)
    entries = []
    for bom in backup["boms"]:
        exops = bom.get("exploded_operation_cost_items") or []
        if exops_only and not exops:
            continue
        entries.append({
            "name": bom["name"],
            "opkeys": OP_FIELDS,
            "exkeys": EXOP_FIELDS,
            "has_exops": bool(exops),
            "fields": {k: bom.get(k) for k in BOM_FIELDS},
            "ops": [{k: o.get(k) for k in OP_FIELDS} for o in ops_by_bom.get(bom["name"], [])],
            "exops": [{k: x.get(k) for k in EXOP_FIELDS} for x in exops],
        })
    return entries


def cmd_probe(client: ErpnextClient, entries: list[dict]) -> None:
    _delete_script(client)
    body = {"name": SCRIPT_NAME, "script_type": "API", "api_method": SCRIPT_NAME,
            "script": PROBE_SCRIPT, "allow_guest": 0, "disabled": 0}
    client._request("POST", "/api/resource/Server Script", json=body, timeout=60)
    try:
        res = client.call(SCRIPT_NAME, payload=json.dumps(entries[:1]))
        print("probe 结果:", res)
    finally:
        _delete_script(client)


def _delete_script(client: ErpnextClient) -> None:
    try:
        client._request("DELETE", f"/api/resource/Server Script/{SCRIPT_NAME}",
                        timeout=60, retries=0)
    except requests.HTTPError:
        pass


def cmd_deploy(client: ErpnextClient) -> None:
    _delete_script(client)
    body = {"name": SCRIPT_NAME, "script_type": "API", "api_method": SCRIPT_NAME,
            "script": SERVER_SCRIPT, "allow_guest": 0, "disabled": 0}
    r = client._request("POST", "/api/resource/Server Script", json=body,
                        timeout=60).json()["data"]
    print(f"已部署 Server Script: {r['name']}")


def cmd_run(client: ErpnextClient, entries: list[dict], page: int, start: int,
            max_pages: int | None) -> None:
    total_ok = total_bad = 0
    pages = 0
    while start < len(entries):
        chunk = entries[start:start + page]
        res = client.call(SCRIPT_NAME, payload=json.dumps(chunk, ensure_ascii=False))
        if not isinstance(res, dict):
            print("返回异常:", res)
            return
        print(f"  start={start:<5} 恢复 {res['processed']} 失败 {res['failed']}")
        for err in res.get("errors") or []:
            print("     ERR", err)
        total_ok += res["processed"]
        total_bad += res["failed"]
        pages += 1
        start += page
        if max_pages and pages >= max_pages:
            print(f"  达到 --max-pages={max_pages}，停下（下次用 --start {start} 继续）")
            break
    print(f"累计：恢复 {total_ok}，失败 {total_bad}")


def cmd_verify(client: ErpnextClient, entries: list[dict], sample: int = 0) -> None:
    targets = entries[:sample] if sample else entries
    bad = []
    renamed = 0
    for e in targets:
        r = client._request(
            "GET", f"/api/resource/BOM/{requests.utils.quote(e['name'], safe='')}",
            timeout=60).json()["data"]
        want = e["fields"]
        got = {k: r.get(k) for k in BOM_FIELDS}
        for k, v in want.items():
            got_v = got.get(k)
            if isinstance(v, (int, float)) or isinstance(got_v, (int, float)):
                if abs(float(v or 0) - float(got_v or 0)) > 1e-6:
                    bad.append(f"{e['name']}.{k}: 期望 {v} 实际 {got_v}")
            elif (v or "") != (got_v or ""):
                bad.append(f"{e['name']}.{k}: 期望 {v!r} 实际 {got_v!r}")
        ops_got = r.get("operations") or []
        if len(ops_got) != len(e["ops"]):
            bad.append(f"{e['name']}: 工序数 期望 {len(e['ops'])} 实际 {len(ops_got)}")
        else:
            for w, g in zip(e["ops"], ops_got):
                if w.get("name") and g.get("name") != w["name"]:
                    renamed += 1
                for k in ("workstation", "hour_rate", "time_in_mins", "operating_cost"):
                    if w.get(k) is not None:
                        av, bv = w.get(k), g.get(k)
                        if isinstance(av, (int, float)):
                            if abs(float(av) - float(bv or 0)) > 1e-6:
                                bad.append(f"{e['name']}.operations.{k}: 期望 {av} 实际 {bv}")
                        elif av != bv:
                            bad.append(f"{e['name']}.operations.{k}: 期望 {av} 实际 {bv}")
        if e.get("has_exops"):
            xr = r.get("exploded_operation_cost_items") or []
            if len(xr) != len(e["exops"]):
                bad.append(f"{e['name']}: exploded 行数 期望 {len(e['exops'])} 实际 {len(xr)}")
            else:
                for w, g in zip(sorted(e["exops"], key=lambda x: x.get("idx") or 0),
                                sorted(xr, key=lambda x: x.get("idx") or 0)):
                    for k in ("item_code", "bom_no"):
                        if (w.get(k) or "") != (g.get(k) or ""):
                            bad.append(f"{e['name']}.exploded.{k}: 期望 {w.get(k)!r} 实际 {g.get(k)!r}")
                    for k in ("operating_cost", "operating_cost_qty"):
                        if abs(float(w.get(k) or 0) - float(g.get(k) or 0)) > 1e-6:
                            bad.append(f"{e['name']}.exploded.{k}: 期望 {w.get(k)} 实际 {g.get(k)}")
    print(f"校验 {len(targets)} 个 BOM：{'全部一致' if not bad else str(len(bad)) + ' 处不一致'}"
          f"（工序行 name 因 Frappe 重建而变化的: {renamed}，业务字段不受影响）")
    for b in bad[:30]:
        print("   -", b)
    if len(bad) > 30:
        print(f"   ... 共 {len(bad)} 处")


def main() -> int:
    ap = argparse.ArgumentParser(description="按备份恢复报工/成本（临时 Server Script）")
    ap.add_argument("action", choices=["probe", "deploy", "run", "verify", "cleanup"])
    ap.add_argument("--env", choices=["test", "prod"], default="prod")
    ap.add_argument("--page", type=int, default=20)
    ap.add_argument("--start", type=int, default=0)
    ap.add_argument("--max-pages", type=int, default=None)
    ap.add_argument("--sample", type=int, default=0)
    ap.add_argument("--exops-only", action="store_true",
                    help="只处理备份里带 exploded_operation_cost_items 的 BOM")
    args = ap.parse_args()

    _load_dotenv([_DIR / ".env", _DIR.parent / ".env", _DIR.parent.parent / ".env"])
    client = make_client(args.env)
    print(f"环境: {args.env} ({client.base_url})")

    entries = build_entries(load_backup(args.env), args.exops_only)
    print(f"待恢复 BOM: {len(entries)}")

    if args.action == "probe":
        cmd_probe(client, entries)
    elif args.action == "deploy":
        cmd_deploy(client)
    elif args.action == "run":
        cmd_run(client, entries, args.page, args.start, args.max_pages)
    elif args.action == "verify":
        cmd_verify(client, entries, args.sample)
    elif args.action == "cleanup":
        _delete_script(client)
        print("已删除 Server Script")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
