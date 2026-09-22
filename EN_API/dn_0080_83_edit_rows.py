# -*- coding: utf-8 -*-
"""DN-26-00080 / DN-26-00083 改行：带菲号行按库存改数量，超出部分新增「无菲号」行

按用户确认的做法：
  · 带菲号行只保留「成品仓现有」的数量（不做投产）
  · 超出部分**新增**同物料的无菲号行（外箱号等字段照抄）——**不删行**
  · 数量跨界的那一行：改小原行数量 + 紧随其后插入一条无菲号行补差额

成本/重量字段不用手工算：Delivery Note 的 before_save 钩子
（update_bom_cost_info / update_dn_item_cost_info / update_incoming_cost_info）会自动重算。

用法:
  python EN_API/dn_0080_83_edit_rows.py plan            # 只读：打印逐行动作
  python EN_API/dn_0080_83_edit_rows.py edit            # dry：构建并给出改前/改后汇总
  python EN_API/dn_0080_83_edit_rows.py edit --apply    # 真写
"""

from __future__ import annotations

import argparse
import json
import sys
from collections import defaultdict
from pathlib import Path

sys.stdout.reconfigure(encoding="utf-8")
_DIR = Path(__file__).resolve().parent
sys.path.insert(0, str(_DIR))
from dp_perf_probe import Client  # noqa: E402
import dn_2600082_83_fix as F      # noqa: E402

OUT_DIR = _DIR / "out"
OPS_FILE = OUT_DIR / "dn_0080_83_edit_ops.json"

DNs = ["DN-26-00080", "DN-26-00083"]
# 菲号产能分配顺序：00080 优先（用户决定）
PRIORITY = ["DN-26-00080", "DN-26-00083"]

SCRIPT_NAME = "zz_dn_edit_rows"
METHOD = "zz_dn_edit_rows"

SERVER_BODY = '''
dn_name = frappe.form_dict.get("dn")
ops = json.loads(frappe.form_dict.get("ops") or "[]")
dry = frappe.form_dict.get("dry") == "1"

SKIP = ("name", "idx", "doctype", "creation", "modified", "modified_by", "owner", "docstatus")

dn = frappe.get_doc("Delivery Note", dn_name)
before = {"total": dn.total, "grand_total": dn.grand_total,
          "total_net_weight": dn.total_net_weight,
          "total_bom_cost": dn.get("total_bom_cost"),
          "rows": len(dn.items),
          "qty": sum(frappe.utils.flt(r.qty) for r in dn.items)}

report = []
for op in ops:
    pos = None
    for i in range(len(dn.items)):
        if int(dn.items[i].idx) == int(op["idx"]):
            pos = i
            break
    if pos is None:
        report.append(["MISS", op["idx"]])
        continue
    row = dn.items[pos]
    q = frappe.utils.flt(row.qty)
    if op["kind"] == "clear":
        row.stock_tracking_number = None
        row.to_stock_tracking_number = None
        report.append(["CLEAR", op["idx"], row.item_code, row.stock_tracking_number, q])
    else:
        keep = frappe.utils.flt(op["keep"])
        if keep >= q - 1e-6:
            report.append(["KEEP", op["idx"], row.item_code, "", q])
            continue
        new = {}
        for k, v in row.as_dict().items():
            if k in SKIP:
                continue
            new[k] = v
        new["qty"] = q - keep
        new["stock_tracking_number"] = None
        new["to_stock_tracking_number"] = None
        row.set("qty", keep)
        row.stock_tracking_number = None
        row.to_stock_tracking_number = None
        nr = frappe.new_doc("Delivery Note Item")
        for k, v in new.items():
            nr.set(k, v)
        dn.items.insert(pos + 1, nr)
        report.append(["SPLIT", op["idx"], row.item_code, "保留 " + str(keep), q - keep])

if dry != "1":
    dn.flags.ignore_mandatory = True
    dn.save(ignore_permissions=True)
    dn.reload()
after = {"total": dn.total, "grand_total": dn.grand_total,
         "total_net_weight": dn.total_net_weight,
         "total_bom_cost": dn.get("total_bom_cost"),
         "rows": len(dn.items),
         "qty": sum(frappe.utils.flt(r.qty) for r in dn.items)}
frappe.response["data"] = {"dn": dn_name, "dry": dry, "before": before, "after": after,
                           "report": report}
'''


def ensure_script(c: Client, name: str, method: str, body: str) -> None:
    try:
        c.delete("Server Script", name)
    except Exception:  # noqa: BLE001
        pass
    c.insert("Server Script", {"doctype": "Server Script", "name": name,
                               "script_type": "API", "api_method": method,
                               "script": body, "disabled": 0, "allow_guest": 0})


def dn_rows(c: Client, dn: str):
    d = c.get_doc("Delivery Note", dn)
    need: dict = defaultdict(float)
    rows: dict = defaultdict(list)
    for i in d.get("items") or []:
        tn = (i.get("stock_tracking_number") or "").strip() or None
        need[(i["item_code"], tn)] += float(i.get("qty") or 0)
        rows[(i["item_code"], tn)].append((int(i.get("idx")), float(i.get("qty") or 0)))
    return dict(need), {k: sorted(v) for k, v in rows.items()}, d


def build_ops(c: Client) -> dict:
    data = {}
    for dn in DNs:
        need, rows, doc = dn_rows(c, dn)
        data[dn] = {"need": need, "rows": rows, "doc": doc}

    keys = sorted({k for dn in DNs for k in data[dn]["need"] if k[1]})
    pool = {k: F.sle_bal(c, k[0], "成品仓 - FZH", k[1]) for k in keys}
    alloc: dict = {}
    for dn in PRIORITY:
        for k in keys:
            q = data[dn]["need"].get(k, 0.0)
            if q <= 0:
                continue
            take = min(q, pool.get(k, 0.0))
            pool[k] = pool.get(k, 0.0) - take
            alloc[(dn, k)] = take

    plan = {}
    for dn in DNs:
        need, rows = data[dn]["need"], data[dn]["rows"]
        ops = []
        conv = 0.0
        for (ic, tn), q in sorted(need.items(), key=lambda x: (x[0][0], str(x[0][1]))):
            if not tn:
                continue
            keep = alloc.get((dn, (ic, tn)), 0.0)
            if keep + 1e-6 >= q:
                continue
            conv += q - keep
            rem = keep
            for idx, rq in rows[(ic, tn)]:
                if rem >= rq - 1e-6:
                    rem -= rq
                    continue
                if rem > 1e-6:
                    ops.append({"kind": "split", "idx": idx, "keep": rem,
                                "item": ic, "tn": tn, "qty": rq})
                    rem = 0.0
                else:
                    ops.append({"kind": "clear", "idx": idx, "item": ic, "tn": tn, "qty": rq})
        plan[dn] = {"ops": ops, "conv": conv}
    return plan


def cmd_plan(c: Client) -> None:
    plan = build_ops(c)
    OUT_DIR.mkdir(exist_ok=True)
    OPS_FILE.write_text(json.dumps(plan, ensure_ascii=False, indent=1), encoding="utf-8")
    for dn, p in plan.items():
        n80 = p["conv"]
        splits = [o for o in p["ops"] if o["kind"] == "split"]
        clears = [o for o in p["ops"] if o["kind"] == "clear"]
        print(f"\n=== {dn}：转无菲号 {n80:.0f} 件 —— 改动数量 {len(splits)} 行、清菲号 {len(clears)} 行 ===")
        for o in splits:
            print(f"   改数量 #{o['idx']:<4}{o['item']:<28}{o['tn']:<18}原 {o['qty']:.0f} → 保留 {o['keep']:.0f}"
                  f" + 新增无菲号 {o['qty']-o['keep']:.0f}")
        if clears:
            bytn: dict = defaultdict(lambda: [0, 0.0])
            for o in clears:
                bytn[(o["item"], o["tn"])][0] += 1
                bytn[(o["item"], o["tn"])][1] += o["qty"]
            print(f"   （清菲号明细按物料/菲号汇总，共 {len(bytn)} 组）")
            for (ic, tn), (n, q) in sorted(bytn.items()):
                print(f"       {ic:<28}{tn:<18}{n:>3} 行 / {q:>5.0f} 件 → 无菲号")
    print(f"\n指令已存 {OPS_FILE}")


def cmd_edit(c: Client, apply: bool) -> None:
    plan = build_ops(c)
    OUT_DIR.mkdir(exist_ok=True)
    OPS_FILE.write_text(json.dumps(plan, ensure_ascii=False, indent=1), encoding="utf-8")
    ensure_script(c, SCRIPT_NAME, METHOD, SERVER_BODY)
    try:
        for dn, p in plan.items():
            # 注意：ops 很长，必须放 POST body（放 query string 会被 nginx 414）
            r = c._req("POST", f"/api/method/{METHOD}",
                       data={"dn": dn, "ops": json.dumps(p["ops"]),
                             "dry": "0" if apply else "1"})
            res = c._check(r).json()["data"]
            b, a = res["before"], res["after"]
            tag = "改动后" if apply else "dry（未写）"
            print(f"\n=== {dn} {tag} ===")
            print(f"   行数 {b['rows']} → {a['rows']}   总件数 {b['qty']:.0f} → {a['qty']:.0f}")
            print(f"   total {b['total']} → {a['total']}")
            print(f"   grand_total {b['grand_total']} → {a['grand_total']}")
            print(f"   total_net_weight {b['total_net_weight']} → {a['total_net_weight']}")
            print(f"   total_bom_cost {b['total_bom_cost']} → {a['total_bom_cost']}")
            rp = res["report"]
            kinds = defaultdict(int)
            for r in rp:
                kinds[r[0]] += 1
            print(f"   动作：{dict(kinds)}")
            if not apply:
                print("   （dry：只构建未保存）")
    finally:
        try:
            c.delete("Server Script", SCRIPT_NAME)
            print(f"\n   ✓ 已删除临时脚本 {SCRIPT_NAME}")
        except Exception as e:  # noqa: BLE001
            print(f"   ✗ 删除失败：{str(e)[:120]}")
        print("   zz_ 残留：", [r["name"] for r in
                               c.get_list("Server Script", [["name", "like", "zz_%"]], ["name"], 0)])


def main() -> int:
    ap = argparse.ArgumentParser(description=__doc__,
                                 formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("cmd", choices=("plan", "edit"))
    ap.add_argument("--apply", action="store_true")
    args = ap.parse_args()
    c = Client("prod")
    if args.cmd == "plan":
        cmd_plan(c)
    else:
        cmd_edit(c, args.apply)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
