# -*- coding: utf-8 -*-
"""方案① 生产执行脚本 —— 修正菲号 WO-26-02796-002 的「多投产」

问题：出货计划 2609004 只需要 4 件，但抢修时把整批 36 件皮壳一次性投产成成品
（STE-26-15219）。DN-26-00078 出掉 4 件后，成品仓剩 32、待包装仓皮壳 0 ——
扫码取的是「待包装仓皮壳」口径，所以下一张计划扫这个菲号报「无库存」。

做法：取消 STE-26-15219 → 重做一张 4 件的 Manufacture。
终态：成品仓 0 / 待包装成品仓皮壳 32（= 36 产 − 4 出）。
已出库的 DN-26-00078 全程不动。

依据：EN_API/out/manufacture_rollback_verify_<ts>.md（测试环境实测通过：
H1 取消被负库存拦；H2a 按物料开关放行；H3 终态成品0/皮壳32；H4 出库流水未动）

**默认 dry-run。所有写操作必须 --apply，且按 step 逐步执行，每步之间先 verify。**

  python EN_API/wo_02796_revert.py probe                 # 只读：前置条件 + 当前账面
  python EN_API/wo_02796_revert.py dry                   # 只读：打印完整执行计划（含 Server Script 正文）
  python EN_API/wo_02796_revert.py apply --apply --step open-gate
  python EN_API/wo_02796_revert.py apply --apply --step cancel
  python EN_API/wo_02796_revert.py apply --apply --step redo
  python EN_API/wo_02796_revert.py apply --apply --step close-gate
  python EN_API/wo_02796_revert.py verify                # 只读：终态断言

⚠️ 未在生产验证过的部分（见文件末尾「已知风险」）：step redo 依赖临时 API Server Script。
"""

from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path
from urllib.parse import quote

import requests

sys.stdout.reconfigure(encoding="utf-8")

_DIR = Path(__file__).resolve().parent

PROD = "https://erpnext.vilavi.cn"

# ── 目标单据 / 口径 ─────────────────────────────────────────
PLAN = "2609004"              # STE-26-15219 的 delivery_plan
TN = "WO-26-02796-002"        # 菲号（追踪维度取值）
SE_CANCEL = "STE-26-15219"    # 要取消的那张 36 件 Manufacture
DN_KEEP = "DN-26-00078"       # 已出库，全程不动
QTY_REDO = 4                  # 重做的数量（= 2609004 实际出库量）
N_TOTAL, M_SHIPPED = 36, 4

IC_FG = "KS0001-HLR-153-TAN"          # 成品（SLE 的 tracking 维度挂在它上面）
IC_SHELL = "PK#KS0001-HLR-153-TAN"    # 皮壳（扫码口径看的就是它）
WH_SHELL = "待包装成品仓 - FZH"
WH_FG = "成品仓 - FZH"

WO_FG = "WO-26-03463"         # 菲号回填的成品工单（重做要挂它）
WO_OLD = "WO-26-02502"        # STE-26-15219 实际挂的工单，取消后会从 Completed 回退

SERVER_SCRIPT = "zz_wo02796_redo"     # 临时 Server Script，用完即删
PREFLIGHT_SCRIPT = "zz_wo02796_preflight"
# API 型 Server Script 的调用路径是 /api/method/<api_method>（不是 docname）
REDO_METHOD = "zz_wo02796_redo"
PREFLIGHT_METHOD = "zz_wo02796_preflight"

# ── 期望账面（修正前 / 修正后） ──────────────────────────────
BASE_SHELL, BASE_FG = 0.0, 32.0
DONE_SHELL, DONE_FG = 32.0, 0.0

# 重做用的服务端脚本：走出货计划自己的方法，让系统按 BOM 算成品单价
REDO_BODY = '''plan = frappe.get_doc("Delivery Plan", "{plan}")
tn = frappe.get_doc("Tracking Number", "{tn}")
fp_wo = frappe.get_doc("Work Order", tn.finished_product_work_order)
se = plan.run_method("_build_manufacture_stock_entry", fp_wo, {qty}, "{tn}")
for d in se.items:
    d.stock_tracking_number = "{tn}"
se.insert()
se.submit()
frappe.response["data"] = {{
    "stock_entry": se.name,
    "fg_completed_qty": se.fg_completed_qty,
    "work_order": se.work_order,
    "items": [d.item_code for d in se.items],
}}
'''.format(plan=PLAN, tn=TN, qty=QTY_REDO)

# 预检：只「构建」不「提交」，用来确认行/仓库/菲号/单价都正确，不产生任何单据
PREFLIGHT_BODY = '''plan = frappe.get_doc("Delivery Plan", "{plan}")
tn = frappe.get_doc("Tracking Number", "{tn}")
fp_wo = frappe.get_doc("Work Order", tn.finished_product_work_order)
se = plan.run_method("_build_manufacture_stock_entry", fp_wo, {qty}, "{tn}")
for d in se.items:
    d.stock_tracking_number = "{tn}"
rows = []
for d in se.items:
    rows.append({{
        "item_code": d.item_code,
        "qty": d.qty,
        "s_warehouse": d.s_warehouse,
        "t_warehouse": d.t_warehouse,
        "is_finished_item": d.is_finished_item,
        "stock_tracking_number": d.stock_tracking_number,
        "basic_rate": d.basic_rate,
    }})
frappe.response["data"] = {{
    "row_count": len(rows),
    "rows": rows,
    "parent_tracking_number": se.tracking_number,
    "fg_completed_qty": se.fg_completed_qty,
    "from_warehouse": se.from_warehouse,
    "to_warehouse": se.to_warehouse,
    "work_order": se.work_order,
    "docstatus": se.docstatus,
}}
'''.format(plan=PLAN, tn=TN, qty=QTY_REDO)


def load_env() -> tuple[str, str]:
    vals: dict[str, str] = {}
    for p in (_DIR / ".env", _DIR.parent / ".env"):
        if not p.is_file():
            continue
        for line in p.read_text(encoding="utf-8", errors="ignore").splitlines():
            line = line.strip()
            if not line or line.startswith("#") or "=" not in line:
                continue
            k, _, v = line.partition("=")
            v = v.strip()
            if len(v) >= 2 and v[0] == v[-1] and v[0] in ('"', "'"):
                v = v[1:-1]
            vals.setdefault(k.strip(), v)
    return vals.get("PROD_ERP_API_KEY", ""), vals.get("PROD_ERP_API_SECRET", "")


class ProdClient:
    def __init__(self) -> None:
        key, sec = load_env()
        if not key or not sec:
            raise SystemExit("✗ 缺少 PROD_ERP_API_KEY / PROD_ERP_API_SECRET（EN_API/.env）")
        self.s = requests.Session()
        self.s.headers["Authorization"] = f"token {key}:{sec}"

    def _req(self, method, path, **kw):
        kw.setdefault("timeout", (30, 300))
        return self.s.request(method, f"{PROD}{path}", **kw)

    def get_list(self, dt, filters=None, fields=None, limit=0):
        pr: dict[str, str] = {"limit_page_length": str(limit)}
        if filters is not None:
            pr["filters"] = json.dumps(filters)
        if fields is not None:
            pr["fields"] = json.dumps(fields)
        r = self._req("GET", f"/api/resource/{quote(dt, safe='')}", params=pr)
        r.raise_for_status()
        return r.json()["data"]

    def get_doc(self, dt, name):
        r = self._req("GET", f"/api/resource/{quote(dt, safe='')}/{quote(name, safe='')}")
        r.raise_for_status()
        return r.json()["data"]

    def sle_sum(self, item_code, warehouse, tracking) -> float:
        rows = self.get_list(
            "Stock Ledger Entry",
            [["item_code", "=", item_code], ["warehouse", "=", warehouse],
             ["tracking_number", "=", tracking], ["is_cancelled", "=", 0]],
            ["actual_qty"], 0)
        return round(sum(float(r["actual_qty"] or 0) for r in rows), 4)

    # ── 写操作 ──
    def _write(self, method, path, payload=None):
        kw = {"headers": {"Content-Type": "application/json"}}
        if payload is not None:
            kw["data"] = json.dumps(payload)
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
        return r.json().get("data") if r.text else None

    def set_item_flag(self, value: int):
        """按物料开关（比全局 Stock Settings 影响面小）。"""
        return self._write("POST", "/api/method/frappe.client.set_value",
                           {"doctype": "Item", "name": IC_FG,
                            "fieldname": "allow_negative_stock", "value": value})

    def cancel(self, dt, name):
        return self._write("POST", "/api/method/frappe.client.cancel",
                           {"doctype": dt, "name": name})

    def insert(self, dt, doc):
        return self._write("POST", f"/api/resource/{quote(dt, safe='')}", doc)

    def delete(self, dt, name):
        return self._write("DELETE", f"/api/resource/{quote(dt, safe='')}/{quote(name, safe='')}")

    def call_method(self, method, payload=None):
        return self._write("POST", f"/api/method/{method}", payload or {})


def snapshot(c: ProdClient) -> dict:
    item = c.get_doc("Item", IC_FG)
    se = c.get_doc("Stock Entry", SE_CANCEL)
    dn = c.get_doc("Delivery Note", DN_KEEP)
    return {
        "皮壳@待包装成品仓": c.sle_sum(IC_SHELL, WH_SHELL, TN),
        "成品@成品仓": c.sle_sum(IC_FG, WH_FG, TN),
        "Item.allow_negative_stock": item.get("allow_negative_stock"),
        f"{SE_CANCEL}.docstatus": se.get("docstatus"),
        f"{DN_KEEP}.docstatus": dn.get("docstatus"),
    }


def show(s: dict, label: str) -> None:
    print(f"\n[{label}]")
    for k, v in s.items():
        print(f"   {k:<32} = {v}")


def check_step(s: dict, step: str) -> None:
    """逐步前置校验：不满足就中止，避免误操作 / 重复执行。

    注意各步的账面基准不同 —— cancel 之后是中间态（皮壳 36 / 成品 -4），
    cancel 这一步本身要求闸门是**开**的。
    """
    def need(cond: bool, msg: str) -> None:
        if not cond:
            raise SystemExit(f"✗ 前置不满足（step {step}）：{msg}")

    flag = int(s["Item.allow_negative_stock"] or 0)
    se_doc = int(s[f"{SE_CANCEL}.docstatus"])
    shell, fg = s["皮壳@待包装成品仓"], s["成品@成品仓"]

    if step in ("preflight", "open-gate", "cancel"):
        need(abs(shell - BASE_SHELL) < 1e-6, f"皮壳@待包装={shell}，期望 {BASE_SHELL}")
        need(abs(fg - BASE_FG) < 1e-6, f"成品@成品仓={fg}，期望 {BASE_FG}")
        need(se_doc == 1, f"{SE_CANCEL}.docstatus={se_doc}，应为 1（已提交）")
        if step == "cancel":
            need(flag == 1, "闸门未开，取消会被负库存拦下（先跑 step open-gate）")
        else:
            need(flag == 0, f"闸门应为关闭，实际 {flag}")
    elif step == "redo":
        need(se_doc == 2, f"{SE_CANCEL}.docstatus={se_doc}，应为 2（已取消）")
        need(abs(shell - N_TOTAL) < 1e-6, f"皮壳@待包装={shell}，期望 {N_TOTAL}")
        need(abs(fg - (BASE_FG - N_TOTAL)) < 1e-6,
             f"成品@成品仓={fg}，期望 {BASE_FG - N_TOTAL}")
    elif step == "close-gate":
        if flag != 1:
            print(f"   注意：闸门已是 {flag}，仍会再置 0（幂等，保证不会漏关）")


# ── 子命令 ─────────────────────────────────────────────────
def cmd_probe(c: ProdClient) -> None:
    print(f"环境: {PROD}（只读）")
    show(snapshot(c), "当前账面")
    tn = c.get_doc("Tracking Number", TN)
    wo_fg = c.get_doc("Work Order", WO_FG)
    wo_old = c.get_doc("Work Order", WO_OLD)
    print("\n[对象]")
    print(f"   菲号 {TN}: qty={tn.get('qty')} so_materials={tn.get('so_materials')} "
          f"fp_wo={tn.get('finished_product_work_order')} 皮壳={tn.get('item_code')}")
    print(f"   重做要挂的工单 {WO_FG}: status={wo_fg.get('status')} qty={wo_fg.get('qty')} "
          f"produced={wo_fg.get('produced_qty')} bom={wo_fg.get('bom_no')} "
          f"fg_warehouse={wo_fg.get('fg_warehouse')}")
    print(f"   现挂产工单 {WO_OLD}: status={wo_old.get('status')} "
          f"produced={wo_old.get('produced_qty')}（取消后会回退）")
    print("\n[基线校验]")
    s = snapshot(c)
    ok = (abs(s["皮壳@待包装成品仓"] - BASE_SHELL) < 1e-6
          and abs(s["成品@成品仓"] - BASE_FG) < 1e-6
          and int(s["Item.allow_negative_stock"] or 0) == 0
          and int(s[f"{SE_CANCEL}.docstatus"]) == 1)
    print("   " + ("✓ 与预期基线一致，可以执行" if ok else "✗ 与预期基线不一致 —— 先查清再动"))


def cmd_dry(c: ProdClient) -> None:
    print(f"环境: {PROD}（只读，不写）")
    show(snapshot(c), "当前账面")
    print("""
[执行计划] 逐步执行，每步之间建议跑 verify

  step open-gate   置 Item.allow_negative_stock = 1（只给 KS0001-HLR-153-TAN）
                   依据：stock_ledger.py:2193 —— 按物料开关即可放行，无需动全局 Stock Settings
  step cancel      取消 STE-26-15219（36 件 Manufacture）
                   中间态：成品仓 -4 / 待包装仓皮壳 36（这一步必须已开闸门）
  step redo        重做一张 4 件 Manufacture（走 _build_manufacture_stock_entry，带 BOM 由系统算成本）
                   终态：成品仓 0 / 待包装仓皮壳 32
  step close-gate  置 Item.allow_negative_stock = 0（务必执行；verify 会断言它已归零）

[不会做的事]
  - 不动 DN-26-00078（已提交的出库流水原样保留）
  - 不改全局 Stock Settings.allow_negative_stock
  - 不改代码、不建分支

[redo 将创建的临时 Server Script]""")
    print(f"   名称: {SERVER_SCRIPT}（script_type=API，执行完立即删除）")
    print("   正文:")
    for ln in REDO_BODY.rstrip().splitlines():
        print(f"     {ln}")
    print("""
[已知风险]
  1. step redo 依赖临时 API Server Script（script_type=API，调用路径 /api/method/<api_method>）。
     preflight 已验证「构建」可行；**insert()/submit() 仍属未经生产验证**，失败则改走 REST 手工建 SE。
  2. 成本口径：已用 preflight 实测 —— 成品行单价算出 41.63176，与原始凭证 STE-26-15219 **完全一致**
     （ERPNext 按物料现有估值取 FG 单价），此前担心的估值差**不成立**。
  3. WO-26-02502 由 Completed 回退（produced 40→4）；执行前确认无人依赖它。
  4. 问题会复发：下次提交同菲号的计划时 _create_manufacture_for_finished_goods 仍会
     按 min(皮壳余额, 工单剩余) 整批投产。要断根需改扫码口径或改成按需投产。
""")


def cmd_apply(c: ProdClient, step: str, apply: bool) -> None:
    s = snapshot(c)
    show(s, f"step {step}：执行前账面")
    check_step(s, step)
    if not apply:
        print(f"\ndry-run：step {step} 将执行（加 --apply 才真正写生产）")
        return

    if step == "open-gate":
        c.set_item_flag(1)
        print("   ✓ 已置 Item.allow_negative_stock = 1")
        print("     回读 =", c.get_doc("Item", IC_FG).get("allow_negative_stock"))

    elif step == "cancel":
        if int(s["Item.allow_negative_stock"] or 0) != 1:
            raise SystemExit("✗ 闸门未开（先跑 step open-gate），取消会被负库存拦下")
        c.cancel("Stock Entry", SE_CANCEL)
        print(f"   ✓ 已取消 {SE_CANCEL}")
        show(snapshot(c), "取消后")

    elif step == "preflight":
        try:
            c.insert("Server Script", {"doctype": "Server Script", "name": PREFLIGHT_SCRIPT,
                                       "script_type": "API", "api_method": PREFLIGHT_METHOD,
                                       "script": PREFLIGHT_BODY,
                                       "disabled": 0, "allow_guest": 0})
            print(f"   ✓ 已建临时 Server Script {PREFLIGHT_SCRIPT}（api_method={PREFLIGHT_METHOD}）")
            res = c.call_method(PREFLIGHT_METHOD)
            print("   ✓ 预检结果（未产生任何单据）:")
            print(json.dumps(res, ensure_ascii=False, indent=2))
        finally:
            try:
                c.delete("Server Script", PREFLIGHT_SCRIPT)
                print(f"   ✓ 已删除临时 Server Script {PREFLIGHT_SCRIPT}")
            except Exception as e:  # noqa: BLE001
                print(f"   ✗ 临时脚本删除失败，请手工删除 {PREFLIGHT_SCRIPT}：{e}")

    elif step == "redo":
        if int(c.get_doc("Stock Entry", SE_CANCEL).get("docstatus")) == 1:
            raise SystemExit(f"✗ {SE_CANCEL} 仍是已提交状态（先跑 step cancel）")
        try:
            c.insert("Server Script", {"doctype": "Server Script", "name": SERVER_SCRIPT,
                                       "script_type": "API", "api_method": REDO_METHOD,
                                       "script": REDO_BODY,
                                       "disabled": 0, "allow_guest": 0})
            print(f"   ✓ 已建临时 Server Script {SERVER_SCRIPT}（api_method={REDO_METHOD}）")
            res = c.call_method(REDO_METHOD)
            print("   ✓ 重做结果:", json.dumps(res, ensure_ascii=False))
        finally:
            try:
                c.delete("Server Script", SERVER_SCRIPT)
                print(f"   ✓ 已删除临时 Server Script {SERVER_SCRIPT}")
            except Exception as e:  # noqa: BLE001
                print(f"   ✗ 临时脚本删除失败，请手工删除 {SERVER_SCRIPT}：{e}")
        show(snapshot(c), "重做后")

    elif step == "close-gate":
        c.set_item_flag(0)
        print("   ✓ 已置 Item.allow_negative_stock = 0")
        print("     回读 =", c.get_doc("Item", IC_FG).get("allow_negative_stock"))

    else:
        raise SystemExit(f"✗ 未知 step: {step}")


def cmd_verify(c: ProdClient) -> None:
    s = snapshot(c)
    show(s, "校验")
    checks: list[tuple[str, bool, str]] = []

    checks.append(("皮壳@待包装成品仓 == 32",
                   abs(s["皮壳@待包装成品仓"] - DONE_SHELL) < 1e-6,
                   f"实际 {s['皮壳@待包装成品仓']}"))
    checks.append(("成品@成品仓 == 0",
                   abs(s["成品@成品仓"] - DONE_FG) < 1e-6,
                   f"实际 {s['成品@成品仓']}"))
    checks.append(("Item.allow_negative_stock 已归零",
                   int(s["Item.allow_negative_stock"] or 0) == 0,
                   f"实际 {s['Item.allow_negative_stock']}"))

    dn_rows = c.get_list("Stock Ledger Entry",
                         [["item_code", "=", IC_FG], ["tracking_number", "=", TN],
                          ["voucher_type", "=", "Delivery Note"]],
                         ["voucher_no", "actual_qty", "is_cancelled"], 0)
    dn_ok = any(r["voucher_no"] == DN_KEEP and float(r["actual_qty"]) < 0
                and not r["is_cancelled"] for r in dn_rows)
    checks.append((f"{DN_KEEP} 出库流水仍在且未取消", dn_ok,
                   f"{len(dn_rows)} 条: "
                   + ", ".join(f"{r['voucher_no']}({r['actual_qty']})" for r in dn_rows)))

    se = c.get_doc("Stock Entry", SE_CANCEL)
    checks.append((f"{SE_CANCEL} 已取消", int(se.get("docstatus")) == 2,
                   f"docstatus={se.get('docstatus')}"))

    ss = c.get_list("Server Script", [["name", "=", SERVER_SCRIPT]], ["name"], 1)
    checks.append((f"临时脚本 {SERVER_SCRIPT} 已清理", not ss, f"残留 {len(ss)} 个"))

    print("\n[断言]")
    for name, ok, detail in checks:
        print(f"   {'✓' if ok else '✗'} {name}（{detail}）")
    bad = [n for n, ok, _ in checks if not ok]
    print("\n" + ("✓ 全部通过，修正完成" if not bad else f"✗ 未通过 {len(bad)} 项：{bad}"))
    if bad:
        raise SystemExit(1)


def main() -> int:
    ap = argparse.ArgumentParser(description=__doc__,
                                 formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("cmd", choices=("probe", "dry", "apply", "verify"))
    ap.add_argument("--step", choices=("preflight", "open-gate", "cancel", "redo", "close-gate"),
                    help="apply 用：要执行的单步")
    ap.add_argument("--apply", action="store_true", help="真正写生产（默认 dry-run）")
    args = ap.parse_args()

    c = ProdClient()
    if args.cmd == "probe":
        cmd_probe(c)
    elif args.cmd == "dry":
        cmd_dry(c)
    elif args.cmd == "verify":
        cmd_verify(c)
    else:
        if not args.step:
            raise SystemExit("✗ apply 必须带 --step open-gate|cancel|redo|close-gate")
        cmd_apply(c, args.step, args.apply)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
