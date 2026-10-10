# -*- coding: utf-8 -*-
"""把 DP 2610001 菲号 WO-26-02538-001 两行的 `original_qty` 从 13 修正为 35（只改这一个字段）。

为什么：扫码放行量 = original_qty − 本单已分配 − 其他计划占用。行上快照停在 13（陈旧），
现实时库存 35（SLE/Bin/TN.qty 均 35，生产代码实跑也返回 35）→ 只能加到 13。
**只改数据、不动代码**；`original_qty` 是子表只读字段，用 db.set_value 直写（不走 doc.save()，
避免重跑 validate → create_items_from_planned_qties / handle_over_delivery_items 追加超量行）。

流程：snapshot → dry-run → apply → verify（rollback 可回滚）。
临时 Server Script 一律 `zz_` 前缀，用完即删。

用法:
  python EN_API/dp_orig_qty_fix.py snapshot
  python EN_API/dp_orig_qty_fix.py dry-run
  python EN_API/dp_orig_qty_fix.py apply
  python EN_API/dp_orig_qty_fix.py verify
  python EN_API/dp_orig_qty_fix.py rollback
"""
from __future__ import annotations

import argparse
import json
import sys
from datetime import datetime
from pathlib import Path

sys.stdout.reconfigure(encoding="utf-8")

from bom_fabric_length_check import ENV_KEYS, ENV_URLS, ErpnextClient, load_env  # noqa: E402

SCRIPT_NAME = "zz_dp_origqty_fix"
API_METHOD = SCRIPT_NAME
OUT_DIR = Path(__file__).resolve().parent / "out"

SERVER_SCRIPT = '''mode = frappe.form_dict.get("mode")
plan = frappe.form_dict.get("plan")
tn_name = frappe.form_dict.get("tn")
target = frappe.utils.flt(frappe.form_dict.get("target") or 0)

rows = frappe.db.sql("""
    SELECT name, idx, original_qty, planned_delivery_qty, staging_qty, actual_qty
    FROM `tabDelivery Plan Item Qty`
    WHERE parent = %(plan)s AND tracking_number = %(tn)s
    ORDER BY idx
""", {"plan": plan, "tn": tn_name}, as_dict=True)

before = []
for r in rows:
    before.append({"name": r.name, "idx": r.idx,
                   "original_qty": frappe.utils.flt(r.original_qty),
                   "planned": frappe.utils.flt(r.planned_delivery_qty),
                   "staging": frappe.utils.flt(r.staging_qty),
                   "actual": frappe.utils.flt(r.actual_qty)})

result = {"mode": mode, "plan": plan, "tn": tn_name, "row_count": len(rows),
          "before": before, "target": target, "applied": False}

# 动作与回报分开：先算好回报，再写库并显式 commit（避免后续查询异常把写入一起回滚）
if mode == "apply":
    if len(rows) != 2:
        result["error"] = "预期 2 行，实际 %d 行，已中止" % len(rows)
    else:
        for r in rows:
            frappe.db.set_value("Delivery Plan Item Qty", r.name, "original_qty", target)
        frappe.db.commit()
        result["applied"] = True

frappe.response["data"] = result
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


def read_rows(client: ErpnextClient, plan: str, tn: str) -> list[dict]:
    dp = client.get_doc("Delivery Plan", plan)
    out = []
    for r in dp.get("item_qties") or []:
        if (r.get("tracking_number") or "") == tn:
            out.append({"name": r["name"], "idx": r["idx"],
                        "original_qty": r.get("original_qty"), "planned": r.get("planned_delivery_qty"),
                        "staging": r.get("staging_qty"), "assigned": r.get("assigned_qty"),
                        "actual": r.get("actual_qty"), "carton_group": r.get("carton_group"),
                        "outer_carton_no": r.get("outer_carton_no")})
    return sorted(out, key=lambda x: x["idx"])


def snapshot_path(plan: str) -> Path:
    return OUT_DIR / f"dp_{plan}_orig_qty_snapshot.json"


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("action", choices=("snapshot", "dry-run", "apply", "verify", "rollback"))
    ap.add_argument("--site", choices=("prod", "test"), default="prod")
    ap.add_argument("--plan", default="2610001")
    ap.add_argument("--tn", default="WO-26-02538-001")
    ap.add_argument("--target", type=float, default=35.0)
    args = ap.parse_args()

    key, sec = load_env(args.site)
    if not key or not sec:
        print(f"✗ 缺 {ENV_KEYS[args.site]} 凭证")
        return 1
    client = ErpnextClient(ENV_URLS[args.site], key, sec)
    snap = snapshot_path(args.plan)
    OUT_DIR.mkdir(parents=True, exist_ok=True)

    if args.action == "snapshot":
        dp = client.get_doc("Delivery Plan", args.plan)
        payload = {"plan": args.plan, "tn": args.tn,
                   "taken_at": datetime.now().isoformat(timespec="seconds"),
                   "site": args.site, "doc": dp}
        snap.write_text(json.dumps(payload, ensure_ascii=False, indent=1, default=str), encoding="utf-8")
        print(f"写前快照已落盘: {snap}")
        for r in read_rows(client, args.plan, args.tn):
            print(f"   idx={r['idx']} name={r['name']} original_qty={r['original_qty']} "
                  f"planned={r['planned']} staging={r['staging']} assigned={r['assigned']} "
                  f"actual={r['actual']} carton={r['carton_group']} {r['outer_carton_no']}")
        return 0

    if args.action == "verify":
        if not snap.is_file():
            print(f"✗ 缺快照 {snap}")
            return 1
        old = json.loads(snap.read_text(encoding="utf-8"))
        old_rows = {}
        for r in old["doc"]["item_qties"]:
            if (r.get("tracking_number") or "") != args.tn:
                continue
            old_rows[r["name"]] = {
                "name": r["name"], "idx": r["idx"], "original_qty": r.get("original_qty"),
                "planned": r.get("planned_delivery_qty"), "staging": r.get("staging_qty"),
                "assigned": r.get("assigned_qty"), "actual": r.get("actual_qty"),
                "carton_group": r.get("carton_group"), "outer_carton_no": r.get("outer_carton_no")}
        now_rows = read_rows(client, args.plan, args.tn)
        ok = True
        for r in now_rows:
            o = old_rows.get(r["name"], {})
            changed = [k for k in ("planned", "staging", "assigned", "actual", "carton_group", "outer_carton_no")
                       if r.get(k) != o.get(k)]
            verdict = "✓" if not changed and float(r["original_qty"] or 0) == args.target else "✗"
            if verdict == "✗":
                ok = False
            print(f"   {verdict} idx={r['idx']} name={r['name']} original_qty={r['original_qty']} "
                  f"(期望 {args.target})  其它字段变化={changed or '无'}")
        print("回读结论:", "全部一致 ✓" if ok else "存在差异 ✗")
        return 0 if ok else 1

    target = args.target
    label = args.action
    if args.action == "rollback":
        if not snap.is_file():
            print(f"✗ 缺快照 {snap}")
            return 1
        old_rows = [r for r in json.loads(snap.read_text(encoding="utf-8"))["doc"]["item_qties"]
                    if (r.get("tracking_number") or "") == args.tn]
        target = float(old_rows[0].get("original_qty") or 0)
        label = f"rollback→{target}"

    mode = "preview" if args.action == "dry-run" else "apply"
    ensure_script(client)
    try:
        res = call(client, mode=mode, plan=args.plan, tn=args.tn, target=target)
        print(json.dumps(res, ensure_ascii=False, indent=1, default=str))
        print(f"\n[{label}] mode={mode} target={target} applied={res.get('applied')}")
        if args.action != "dry-run":
            print("\n写后回读:")
            for r in read_rows(client, args.plan, args.tn):
                print(f"   idx={r['idx']} name={r['name']} original_qty={r['original_qty']} "
                      f"planned={r['planned']} actual={r['actual']} carton={r['carton_group']}")
    finally:
        drop_script(client)
    return 0


if __name__ == "__main__":
    sys.exit(main())
