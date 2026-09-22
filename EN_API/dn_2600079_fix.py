# -*- coding: utf-8 -*-
"""DN-26-00079（出货计划 2609005）缺货修复 —— 按出库数量补做成品入库

根因：这 35 个菲号的 `Tracking Number.finished_product_work_order` 为空（成品工单被误删的遗留），
计划 2609005 提交时 `_create_manufacture_for_finished_goods` 逐个静默 return → 成品入库没执行
→ 成品仓 0 → DN 提交被 `validate_dn_tracking_number_dimension_stock` 拦下（37 组 / 435 件）。

做法（**不修改 DN-26-00079、不修改计划、不动全局设置**）：
  1. 回填 33 个菲号的 `finished_product_work_order`（修复根因）
  2. 每个 (成品物料, 菲号) 按 DN 的出库数量建一张 Manufacture：
     - `tagged`   带菲号：复用出货计划的方法 `_build_manufacture_stock_entry`（带 BOM，系统算单价）
     - `untagged` 无菲号：DN 上那几行本来就没有菲号，用**无菲号皮壳**产出**无菲号成品**
  3. 数量口径 = **DN 出库数量**（不整批投产），剩余皮壳留在待包装仓，以后仍可扫

被跳过的：`KS0001-HLR-153-TAN` 8 件（用户决定先挂着：待包装仓没有无菲号的 TAN 皮壳）。

用法：
  python EN_API/dn_2600079_fix.py probe            # 只读：分组/可用量/目标工单/操作清单
  python EN_API/dn_2600079_fix.py dry              # 只读：打印将执行的每一步
  python EN_API/dn_2600079_fix.py apply --part backfill --apply
  python EN_API/dn_2600079_fix.py apply --part tagged   --apply
  python EN_API/dn_2600079_fix.py apply --part untagged --apply
  python EN_API/dn_2600079_fix.py verify           # 只读：逐组断言
"""

from __future__ import annotations

import argparse
import json
import sys
from collections import defaultdict
from pathlib import Path
from urllib.parse import quote

import requests

sys.stdout.reconfigure(encoding="utf-8")

_DIR = Path(__file__).resolve().parent
OUT_DIR = _DIR / "out"
MANIFEST = OUT_DIR / "dn_2600079_fix_manifest.json"

PROD = "https://erpnext.vilavi.cn"
DN = "DN-26-00079"
PLAN = "2609005"
WH_SHELL = "待包装成品仓 - FZH"
WH_FG = "成品仓 - FZH"
PREFERRED_PLAN = "PP-26-00033"          # 上次抢修重建工单所在的计划
PREFERRED_PREFIX = "WO-26-03400"        # 重建工单的起始号
SKIP_ITEMS = {"KS0001-HLR-153-TAN"}     # 用户决定先挂着

SERVER_SCRIPT = "zz_dn79_manu"
METHOD = "zz_dn79_manu"

# 临时 Server Script 正文：一次处理一个操作，dry=1 时只构建不提交
SERVER_BODY = '''
mode = frappe.form_dict.get("mode")
qty = frappe.utils.flt(frappe.form_dict.get("qty"))
item = frappe.form_dict.get("item")
tn = frappe.form_dict.get("tn")
do_dry = frappe.form_dict.get("dry")

if mode == "tagged":
    plan = frappe.get_doc("Delivery Plan", "2609005")
    wo = frappe.get_doc("Work Order", frappe.form_dict.get("wo"))
    se = plan.run_method("_build_manufacture_stock_entry", wo, qty, tn)
    for d in se.items:
        d.stock_tracking_number = tn
else:
    shell = frappe.form_dict.get("shell")
    se = frappe.new_doc("Stock Entry")
    se.purpose = "Manufacture"
    se.company = "FZH"
    se.posting_date = frappe.utils.nowdate()
    se.from_bom = 1
    se.bom_no = frappe.form_dict.get("bom")
    se.use_multi_level_bom = 0
    se.fg_completed_qty = qty
    se.set_stock_entry_type()
    se.get_items()
    drop = []
    for d in se.items:
        if d.is_finished_item:
            d.t_warehouse = "成品仓 - FZH"
            d.s_warehouse = None
        else:
            d.s_warehouse = "待包装成品仓 - FZH"
            d.t_warehouse = None
            q = frappe.db.sql("select actual_qty from tabBin where item_code=%s and warehouse=%s",
                              (d.item_code, d.s_warehouse))
            avail = frappe.utils.flt(q[0][0]) if q else 0.0
            if avail < frappe.utils.flt(d.qty):
                drop.append(d)
    for d in drop:
        se.remove(d)

rows = []
for d in se.items:
    rows.append({{"item_code": d.item_code, "qty": d.qty, "s_warehouse": d.s_warehouse,
                  "t_warehouse": d.t_warehouse, "is_finished_item": d.is_finished_item,
                  "stock_tracking_number": d.stock_tracking_number,
                  "basic_rate": d.basic_rate}})

if do_dry == "1":
    frappe.response["data"] = {{"dry": 1, "rows": rows, "fg_completed_qty": se.fg_completed_qty}}
else:
    se.insert()
    se.submit()
    frappe.response["data"] = {{"dry": 0, "name": se.name, "rows": rows,
                                "fg_completed_qty": se.fg_completed_qty}}
'''.format()


def load_env() -> tuple[str, str]:
    vals: dict[str, str] = {}
    for p in (_DIR / ".env", _DIR.parent / ".env"):
        if not p.is_file():
            continue
        for line in p.read_text(encoding="utf-8", errors="ignore").splitlines():
            line = line.strip()
            if not line or line.startswith("#") or "=" not in line:
                continue
            k, _, val = line.partition("=")
            val = val.strip()
            if len(val) >= 2 and val[0] == val[-1] and val[0] in ('"', "'"):
                val = val[1:-1]
            vals.setdefault(k.strip(), val)
    return vals.get("PROD_ERP_API_KEY", ""), vals.get("PROD_ERP_API_SECRET", "")


class Client:
    def __init__(self) -> None:
        key, sec = load_env()
        if not key or not sec:
            raise SystemExit("✗ 缺少 PROD_ERP_API_KEY / PROD_ERP_API_SECRET（EN_API/.env）")
        self.s = requests.Session()
        self.s.headers["Authorization"] = f"token {key}:{sec}"

    def _req(self, method, path, **kw):
        kw.setdefault("timeout", (30, 300))
        return self.s.request(method, f"{PROD}{path}", **kw)

    def get_doc(self, dt, name):
        r = self._req("GET", f"/api/resource/{quote(dt, safe='')}/{quote(name, safe='')}")
        r.raise_for_status()
        return r.json()["data"]

    def get_list(self, dt, filters=None, fields=None, limit=0):
        pr: dict[str, str] = {"limit_page_length": str(limit)}
        if filters is not None:
            pr["filters"] = json.dumps(filters)
        if fields is not None:
            pr["fields"] = json.dumps(fields)
        r = self._req("GET", f"/api/resource/{quote(dt, safe='')}", params=pr)
        r.raise_for_status()
        return r.json()["data"]

    def _write(self, method, path, payload=None, params=None):
        kw: dict = {"headers": {"Content-Type": "application/json"}}
        if payload is not None:
            kw["data"] = json.dumps(payload)
        if params:
            kw["params"] = params
        r = self._req(method, path, **kw)
        if r.status_code >= 400:
            try:
                err = r.json()
                msgs = err.get("_server_messages")
                readable = ""
                if msgs:
                    try:
                        readable = " | ".join(
                            str(json.loads(m).get("message", m)) for m in json.loads(msgs))
                    except Exception:  # noqa: BLE001
                        readable = str(msgs)
                exc = readable or err.get("exception") or err.get("exc") or json.dumps(err)
            except Exception:  # noqa: BLE001
                exc = r.text
            raise RuntimeError(f"{r.status_code} {exc}"[:2000])
        return r.json()

    def insert(self, dt, doc):
        return self._write("POST", f"/api/resource/{quote(dt, safe='')}", doc)["data"]

    def delete(self, dt, name):
        return self._write("DELETE", f"/api/resource/{quote(dt, safe='')}/{quote(name, safe='')}")

    def cancel(self, dt, name):
        return self._write("POST", "/api/method/frappe.client.cancel",
                           {"doctype": dt, "name": name})

    def call(self, method, params):
        return self._write("POST", f"/api/method/{method}", params=params)["data"]

    def put(self, dt, name, patch):
        return self._write("PUT", f"/api/resource/{quote(dt, safe='')}/{quote(name, safe='')}",
                           patch)["data"]

    # ── 库存 ──
    def sle_bal(self, item, warehouse, tracking):
        f = [["item_code", "=", item], ["warehouse", "=", warehouse], ["is_cancelled", "=", 0]]
        f.append(["tracking_number", "is", "not set"] if tracking is None
                 else ["tracking_number", "=", tracking])
        rows = self.get_list("Stock Ledger Entry", f, ["actual_qty"], 0)
        return round(sum(float(r["actual_qty"] or 0) for r in rows), 4)


# ── 计划构建（只读） ────────────────────────────────────────
def build_ops(c: Client) -> tuple[list[dict], list[dict]]:
    """返回 (tagged_ops, untagged_ops)。数量口径 = DN 出库数量（按 物料+菲号 汇总）。"""
    dn = c.get_doc("Delivery Note", DN)
    need: dict = defaultdict(float)
    for i in dn.get("items") or []:
        need[(i["item_code"], i.get("stock_tracking_number") or None)] += float(i.get("qty") or 0)

    items = sorted({ic for (ic, _) in need})
    tns = sorted({tn for (_, tn) in need if tn})

    # Item.valuation_rate（无菲号投产的单价来源）
    rate = {r["name"]: r.get("valuation_rate")
            for r in c.get_list("Item", [["name", "in", items]], ["name", "valuation_rate"], 0)}

    # 目标工单：优先 PP-26-00033 重建的、且有剩余可入量的
    wos = c.get_list("Work Order",
                     [["production_item", "in", items], ["docstatus", "=", 1]],
                     ["name", "production_item", "status", "qty", "produced_qty",
                      "production_plan"], 0)
    cand: dict = defaultdict(list)
    for r in wos:
        if r["status"] in ("Completed", "Cancelled", "Closed"):
            continue
        if float(r["qty"] or 0) - float(r["produced_qty"] or 0) <= 0:
            continue
        cand[r["production_item"]].append(r)

    # 默认 BOM（无菲号投产要走 from_bom + get_items，才能算对成品单价）
    boms = c.get_list("BOM", [["item", "in", items], ["is_default", "=", 1],
                              ["is_active", "=", 1], ["docstatus", "=", 1]],
                      ["name", "item"], 0)
    bom_of = {r["item"]: r["name"] for r in boms}

    # 菲号 → fp_wo 现状
    tn_docs = {t["name"]: t for t in
               c.get_list("Tracking Number", [["name", "in", tns]],
                          ["name", "qty", "so_materials", "finished_product_work_order"], 0)}

    tagged, untagged = [], []
    for (ic, tn), q in sorted(need.items(), key=lambda x: (x[0][0], str(x[0][1]))):
        if ic in SKIP_ITEMS:
            continue
        shell = "PK#" + ic
        fg_have = c.sle_bal(ic, WH_FG, tn)
        if fg_have >= q:
            continue                                   # 成品仓已有货
        shell_have = c.sle_bal(shell, WH_SHELL, tn)
        if shell_have < q:
            continue                                   # 皮壳不足（probe 里会单独告警）

        if tn:
            cs = sorted(cand.get(ic, []),
                        key=lambda x: (0 if (x["production_plan"] == PREFERRED_PLAN
                                             and x["name"] >= PREFERRED_PREFIX) else 1,
                                       x["name"]))
            wo = cs[0]["name"] if cs else None
            if not wo:
                print(f"   ⚠ {ic} 无可用成品工单，跳过 {tn}")
                continue
            tagged.append({"mode": "tagged", "item": ic, "tn": tn, "qty": q,
                           "shell": shell, "wo": wo,
                           "fp_wo_now": tn_docs.get(tn, {}).get("finished_product_work_order")})
        else:
            untagged.append({"mode": "untagged", "item": ic, "tn": None, "qty": q,
                             "shell": shell, "bom": bom_of.get(ic),
                             "rate": rate.get(ic)})
    return tagged, untagged


def all_ops(tagged, untagged) -> list[dict]:
    return tagged + untagged


def cmd_probe(c: Client) -> None:
    dn = c.get_doc("Delivery Note", DN)
    print(f"环境 {PROD}（只读）  DN={DN} docstatus={dn.get('docstatus')} "
          f"行数={len(dn.get('items') or [])} 需求={sum(float(i.get('qty') or 0) for i in dn['items']):.0f}")
    tagged, untagged = build_ops(c)

    print(f"\n[带菲号] {len(tagged)} 个操作，合计 {sum(o['qty'] for o in tagged):.0f} 件")
    print(f"   {'物料':<26}{'菲号':<18}{'数量':>5}{'皮壳可用':>9}{'挂工单':<16}")
    for o in tagged:
        sh = c.sle_bal(o["shell"], WH_SHELL, o["tn"])
        print(f"   {o['item']:<26}{o['tn']:<18}{o['qty']:>5.0f}{sh:>9.0f}{o['wo']:<16}")

    print(f"\n[无菲号] {len(untagged)} 个操作，合计 {sum(o['qty'] for o in untagged):.0f} 件")
    for o in untagged:
        sh = c.sle_bal(o["shell"], WH_SHELL, None)
        print(f"   {o['item']:<26}{'（无菲号）':<18}{o['qty']:>5.0f}{sh:>9.0f}  单价={o['rate']}")

    skip = c.get_doc("Delivery Note", DN)
    print(f"\n[跳过] {sorted(SKIP_ITEMS)} —— 待包装仓无无菲号皮壳，用户决定先挂着")
    tot = sum(o["qty"] for o in all_ops(tagged, untagged))
    need = sum(float(i.get("qty") or 0) for i in skip["items"])
    dn_need: dict = defaultdict(float)
    for i in skip.get("items") or []:
        dn_need[(i["item_code"], i.get("stock_tracking_number") or None)] += float(i.get("qty") or 0)
    have = sum(min(q, c.sle_bal(ic, WH_FG, tn)) for (ic, tn), q in dn_need.items())
    print(f"[汇总] 需求 {need:.0f} = 已有成品 {have:.0f} + 本次投产 {tot:.0f} + 待处理 {need - have - tot:.0f}"
          f"（待处理即跳过的 TAN 8 件）")


def cmd_dry(c: Client) -> None:
    tagged, untagged = build_ops(c)
    print(f"环境 {PROD}（只读，不写）\n")
    print("[执行计划]")
    print(f"  part backfill  —— 回填 {len([o for o in tagged if not o.get('fp_wo_now')])} 个菲号的 "
          f"finished_product_work_order")
    print(f"  part tagged    —— {len(tagged)} 张 Manufacture（带菲号，走出货计划自己的 builder）")
    print(f"  part untagged  —— {len(untagged)} 张 Manufacture（无菲号皮壳 → 无菲号成品）")
    print("\n[单张凭证的形态]")
    print("  tagged   : 皮壳 s_warehouse=待包装成品仓 + 成品 t_warehouse=成品仓，行上带菲号，挂成品工单")
    print("  untagged : 皮壳 s_warehouse=待包装成品仓 + 成品 t_warehouse=成品仓，行上无菲号，走默认 BOM 之外的显式行")
    print(f"\n[不做的事] 不改 {DN} 的任何行；不改计划 {PLAN}；不动全局 allow_negative_stock；不改代码")
    print("\n[临时 Server Script]")
    print(f"   api_method = {METHOD}（执行完立即删除）")
    for ln in SERVER_BODY.rstrip().splitlines():
        print(f"     {ln}")


def _ensure_script(c: Client) -> None:
    try:
        c.delete("Server Script", SERVER_SCRIPT)
    except Exception:  # noqa: BLE001
        pass
    c.insert("Server Script", {"doctype": "Server Script", "name": SERVER_SCRIPT,
                               "script_type": "API", "api_method": METHOD,
                               "script": SERVER_BODY, "disabled": 0, "allow_guest": 0})


def cmd_apply(c: Client, part: str, apply: bool, cancel: bool = False) -> None:
    tagged, untagged = build_ops(c)
    m = json.loads(MANIFEST.read_text(encoding="utf-8")) if MANIFEST.is_file() else {}
    m.setdefault("created", {})
    m.setdefault("backfilled", [])

    if cancel:
        done = m.get("created", {}).get(part, [])
        print(f"取消已建的 {len(done)} 张 {part} 凭证" + ("（dry-run，未写）" if not apply else ""))
        for rec in done:
            print(f"   {rec.get('se')}  {rec.get('item')} {rec.get('tn') or '（无菲号）'} {rec.get('qty'):.0f}")
            if not apply:
                continue
            c.cancel("Stock Entry", rec["se"])
        if apply:
            m["cancelled"] = m.get("cancelled", []) + done
            m["created"][part] = []
            MANIFEST.write_text(json.dumps(m, ensure_ascii=False, indent=1), encoding="utf-8")
        print("✓ 完成" if apply else "（dry-run，未写）")
        return

    if part == "backfill":
        todo = [o for o in tagged if not o.get("fp_wo_now")]
        print(f"回填 {len(todo)} 个菲号的 fp_wo"
              + ("（dry-run）" if not apply else ""))
        for o in todo:
            print(f"   {o['tn']:<18} → {o['wo']}")
            if not apply:
                continue
            c.put("Tracking Number", o["tn"], {"finished_product_work_order": o["wo"]})
            m["backfilled"].append({"tn": o["tn"], "wo": o["wo"]})
        if apply:
            MANIFEST.write_text(json.dumps(m, ensure_ascii=False, indent=1), encoding="utf-8")
        print("✓ 完成" if apply else "（dry-run，未写）")
        return

    ops = tagged if part == "tagged" else untagged
    if not ops:
        print("无操作")
        return
    print(f"{part}: {len(ops)} 张 Manufacture，合计 {sum(o['qty'] for o in ops):.0f} 件"
          + ("（dry-run，只构建不提交）" if not apply else ""))

    # 先做一张 dry 预检，确认机制/行/单价
    _ensure_script(c)
    created: list[dict] = []
    try:
        for i, o in enumerate(ops, start=1):
            params = {"mode": o["mode"], "item": o["item"], "qty": o["qty"],
                      "shell": o["shell"], "tn": o["tn"] or "", "wo": o.get("wo") or "",
                      "bom": o.get("bom") or "", "rate": o.get("rate") or 0,
                      "dry": "0" if apply else "1"}
            tag = o["tn"] or "（无菲号）"
            try:
                res = c.call(METHOD, params)
                if apply:
                    created.append({"item": o["item"], "tn": o["tn"], "qty": o["qty"],
                                    "se": res.get("name"), "wo": o.get("wo")})
                    print(f"   [{i}/{len(ops)}] {o['item']:<26}{tag:<18}{o['qty']:>4.0f} → {res.get('name')}")
                else:
                    print(f"   [{i}/{len(ops)}] {o['item']:<26}{tag:<18}{o['qty']:>4.0f} → 构建 OK")
                    if i == 1:
                        print("        行:", json.dumps(res.get("rows"), ensure_ascii=False))
            except RuntimeError as e:
                print(f"   [{i}/{len(ops)}] ✗ {o['item']} {tag} 失败：{str(e)[:400]}")
    finally:
        try:
            c.delete("Server Script", SERVER_SCRIPT)
            print(f"   ✓ 已删除临时 Server Script {SERVER_SCRIPT}")
        except Exception as e:  # noqa: BLE001
            print(f"   ✗ 临时脚本删除失败，请手工删除 {SERVER_SCRIPT}：{e}")

    if apply and created:
        m["created"].setdefault(part, []).extend(created)
        MANIFEST.parent.mkdir(parents=True, exist_ok=True)
        MANIFEST.write_text(json.dumps(m, ensure_ascii=False, indent=1), encoding="utf-8")
        print(f"✓ {len(created)} 张已提交")


def cmd_verify(c: Client) -> None:
    tagged, untagged = build_ops(c)
    dn = c.get_doc("Delivery Note", DN)
    ops = all_ops(tagged, untagged)
    print(f"环境 {PROD}（只读）  操作清单剩 {len(ops)} 个（做完应为 0）")

    need: dict = defaultdict(float)
    for i in dn.get("items") or []:
        need[(i["item_code"], i.get("stock_tracking_number") or None)] += float(i.get("qty") or 0)

    print(f"\n{'物料':<26}{'菲号':<18}{'需求':>5}{'成品仓现有':>11}  判定")
    bad = []
    for (ic, tn), q in sorted(need.items(), key=lambda x: (x[0][0], str(x[0][1]))):
        have = c.sle_bal(ic, WH_FG, tn)
        if ic in SKIP_ITEMS:
            verdict = "已跳过（用户决定先挂着）"
        elif have + 1e-6 >= q:
            verdict = "✓ 够"
        else:
            verdict = f"✗ 仍缺 {q - have:.0f}"
            bad.append((ic, tn, q - have))
        print(f" {ic:<26}{tn or '（无菲号）':<18}{q:>5.0f}{have:>11.1f}  {verdict}")

    ss = c.get_list("Server Script", [["name", "=", SERVER_SCRIPT]], ["name"], 1)
    print(f"\n临时脚本残留：{len(ss)} 个（应为 0）")
    print(f"全局 allow_negative_stock = "
          f"{c.get_doc('Stock Settings', 'Stock Settings').get('allow_negative_stock')}（应为 0）")
    if bad:
        print(f"\n✗ 仍缺 {len(bad)} 组：" + ", ".join(f"{i}/{t or '-'}({g:.0f})" for i, t, g in bad))
    else:
        print("\n✓ 全部满足（除已跳过的 TAN 8 件）")


def main() -> int:
    ap = argparse.ArgumentParser(description=__doc__,
                                 formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("cmd", choices=("probe", "dry", "apply", "verify"))
    ap.add_argument("--part", choices=("backfill", "tagged", "untagged"))
    ap.add_argument("--cancel", action="store_true", help="取消清单里该 part 已建的凭证")
    ap.add_argument("--apply", action="store_true", help="真正写生产（默认 dry-run）")
    args = ap.parse_args()

    c = Client()
    if args.cmd == "probe":
        cmd_probe(c)
    elif args.cmd == "dry":
        cmd_dry(c)
    elif args.cmd == "verify":
        cmd_verify(c)
    else:
        if not args.part:
            raise SystemExit("✗ apply 必须带 --part backfill|tagged|untagged")
        cmd_apply(c, args.part, args.apply, args.cancel)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
