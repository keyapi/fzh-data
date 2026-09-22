# -*- coding: utf-8 -*-
"""DN-26-00083 / DN-26-00082 缺货修复（计划 2609008 / 2609007-1，SO-26-00097）

形态与 DN-26-00078 / DN-26-00079 相同：菲号的 `finished_product_work_order`（fp_wo）为空
→ 计划提交时 `_create_manufacture_for_finished_goods` 静默 return → 成品仓没货。

**本次多一个问题**：两张 DN 重复占用同一批菲号，合计需求超过菲号产出的皮壳数（11 个菲号 / 126 件）。
经用户决定：**先跳过超量部分**（整枚菲号不碰，留给业务改挂），其余照做。

流水线（--part 分段执行，默认全部 dry-run）：
  fill      回填 fp_wo → 指向该物料现有、未完结、仍有剩余量的成品工单
  tagged    带菲号投产：走计划自己的 `_build_manufacture_stock_entry`（成本口径与系统一致）
  untagged  无菲号：待包装仓无菲号皮壳不足时先从「半成品仓」调拨，再 from_bom 投产无菲号成品

用法:
  python EN_API/dn_2600082_83_fix.py probe                     # 只读勘察
  python EN_API/dn_2600082_83_fix.py dry                       # 干跑：逐条动作，不写
  python EN_API/dn_2600082_83_fix.py apply --part fill    --apply
  python EN_API/dn_2600082_83_fix.py apply --part tagged  --apply
  python EN_API/dn_2600082_83_fix.py apply --part untagged --apply
  python EN_API/dn_2600082_83_fix.py verify                    # 只读：按 DN 校验口径复核
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

WH_SHELL = "待包装成品仓 - FZH"
WH_FG = "成品仓 - FZH"
WH_SEMI = "半成品仓 - FZH"          # 无菲号皮壳的允许调拨来源（其他仓库不自动动）

OUT_DIR = _DIR / "out"
MANIFEST = OUT_DIR / "dn_2600082_83_manifest.json"

TARGETS = {
    "DN-26-00083": "2609008",
    "DN-26-00082": "2609007-1",
}

# 两张 DN 重复占用同一批菲号，合计需求超过菲号产能时，按此顺序分配（用户决定：00082 优先）
PRIORITY = ["DN-26-00082", "DN-26-00083"]

SERVER_SCRIPT = "zz_dn8283"
METHOD = "zz_dn8283.run"

# 临时 Server Script：一次处理一个操作；dry=1 时只构建不提交。
# 与 dn_2600079_fix.py 同源（tagged 走计划自己的 builder；untagged 走 from_bom 显式行，保证单价正确）
SERVER_BODY = '''
mode = frappe.form_dict.get("mode")
plan_name = frappe.form_dict.get("plan")
qty = frappe.utils.flt(frappe.form_dict.get("qty"))
item = frappe.form_dict.get("item")
tn = frappe.form_dict.get("tn")
wo_name = frappe.form_dict.get("wo")
do_dry = frappe.form_dict.get("dry")

if mode == "fill":
    # 注意：必须遵守 dry —— 否则不带 --apply 也会真写生产
    if do_dry != "1":
        frappe.db.set_value("Tracking Number", tn, "finished_product_work_order", wo_name)
        frappe.db.commit()
    frappe.response["data"] = {"dry": 1 if do_dry == "1" else 0, "mode": "fill",
                               "tn": tn, "wo": wo_name}
else:
    if mode == "tagged":
        plan = frappe.get_doc("Delivery Plan", plan_name)
        wo = frappe.get_doc("Work Order", wo_name)
        se = plan.run_method("_build_manufacture_stock_entry", wo, qty, tn)
        for d in se.items:
            d.stock_tracking_number = tn
    elif mode == "xfer":
        src = frappe.form_dict.get("src")
        se = frappe.new_doc("Stock Entry")
        se.purpose = "Material Transfer"
        se.stock_entry_type = "Material Transfer"
        se.company = "FZH"
        se.append("items", {"item_code": item, "qty": qty, "uom": "个",
                            "s_warehouse": src, "t_warehouse": "待包装成品仓 - FZH"})
    else:
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
        rows.append({"item_code": d.item_code, "qty": d.qty, "s_warehouse": d.s_warehouse,
                     "t_warehouse": d.t_warehouse, "is_finished_item": d.is_finished_item,
                     "stock_tracking_number": d.stock_tracking_number,
                     "basic_rate": d.basic_rate})

    # 硬拦截：Manufacture 没有原料行 = 成品单价会算成 0（成本直接冲费用，之前踩过）
    has_raw = False
    for d in se.items:
        if not d.is_finished_item:
            has_raw = True
    if mode == "untagged" and not has_raw and do_dry != "1":
        frappe.throw("无原料行（待包装仓皮壳不足），拒绝提交以免成品单价为 0")

    if do_dry == "1":
        frappe.response["data"] = {"dry": 1, "mode": mode, "rows": rows,
                                   "fg_completed_qty": se.fg_completed_qty}
    else:
        se.flags.ignore_mandatory = True
        se.insert(ignore_permissions=True)
        se.submit()
        frappe.response["data"] = {"dry": 0, "mode": mode, "name": se.name, "rows": rows,
                                   "fg_completed_qty": se.fg_completed_qty}
'''


# ── 只读工具 ──────────────────────────────────────────────
def sle_bal(c: Client, item: str, warehouse: str, tracking: str | None) -> float:
    f = [["item_code", "=", item], ["warehouse", "=", warehouse], ["is_cancelled", "=", 0]]
    f.append(["tracking_number", "is", "not set"] if not tracking
             else ["tracking_number", "=", tracking])
    rows = c.get_list("Stock Ledger Entry", f, ["actual_qty"], 0)
    return round(sum(float(r["actual_qty"] or 0) for r in rows), 4)


def untagged_shell_sources(c: Client, shell_item: str) -> dict[str, float]:
    """无菲号皮壳在各仓库的结余（只看 >0 的）。"""
    rows = c.get_list("Stock Ledger Entry",
                      [["item_code", "=", shell_item], ["tracking_number", "is", "not set"],
                       ["is_cancelled", "=", 0]],
                      ["warehouse", "actual_qty"], 0)
    agg: dict[str, float] = defaultdict(float)
    for r in rows:
        agg[r["warehouse"]] += float(r["actual_qty"] or 0)
    return {w: round(q, 4) for w, q in agg.items() if q > 0.001}


def bin_bal(c: Client, item: str, warehouse: str) -> float:
    """仓库结余（Bin）。

    注意：**Bin 与 SLE 在本环境会不一致**（实测：某皮壳在半成品仓 SLE 有 51 件、Bin 却是 0）。
    ERPNext 的出入库校验认 **Bin**，所以判断「能不能领/能不能调」必须看 Bin；
    而 DN 提交前的库存维度校验看的是 **SLE 的跟踪单号维度**（见 sle_bal）。
    两个口径用途不同，别混用。
    """
    rows = c.get_list("Bin", [["item_code", "=", item], ["warehouse", "=", warehouse]],
                      ["actual_qty"], 0)
    return round(sum(float(r["actual_qty"] or 0) for r in rows), 4)


def dn_need(c: Client, dn_name: str) -> dict[tuple[str, str | None], float]:
    dn = c.get_doc("Delivery Note", dn_name)
    need: dict[tuple[str, str | None], float] = defaultdict(float)
    for i in dn.get("items") or []:
        tn = (i.get("stock_tracking_number") or "").strip() or None
        need[(i["item_code"], tn)] += float(i.get("qty") or 0)
    return dict(need)


def tn_caps(c: Client, tns: list[str]) -> dict[str, float]:
    if not tns:
        return {}
    rows = c.get_list("Tracking Number", [["name", "in", tns]], ["name", "qty"], 0)
    return {r["name"]: float(r["qty"] or 0) for r in rows}


def candidate_wos(c: Client, items: list[str]) -> dict[str, list[dict]]:
    wos = c.get_list("Work Order",
                     [["production_item", "in", items], ["docstatus", "=", 1]],
                     ["name", "production_item", "status", "qty", "produced_qty",
                      "production_plan", "bom_no"], 0)
    out: dict[str, list[dict]] = defaultdict(list)
    for w in wos:
        if w["status"] in ("Completed", "Cancelled", "Closed"):
            continue
        if float(w["qty"] or 0) - float(w["produced_qty"] or 0) <= 0:
            continue
        out[w["production_item"]].append(w)
    for k in out:
        out[k].sort(key=lambda w: w["name"])
    return dict(out)


# ── 计划构建（只读） ────────────────────────────────────────
def build_plan_all(c: Client) -> dict:
    """把两个 DN 的缺口算成逐条动作 + 跳过项。"""
    per_dn = {}
    for dn_name, plan_name in TARGETS.items():
        per_dn[dn_name] = {"plan": plan_name, "need": dn_need(c, dn_name)}

    combined: dict[tuple[str, str | None], float] = defaultdict(float)
    for d in per_dn.values():
        for k, v in d["need"].items():
            combined[k] += v
    tagged_keys = sorted({k for k in combined if k[1]})
    caps = tn_caps(c, [k[1] for k in tagged_keys])
    items = sorted({k[0] for k in combined})

    wos = candidate_wos(c, items)
    boms = c.get_list("BOM", [["item", "in", items], ["is_default", "=", 1],
                              ["is_active", "=", 1], ["docstatus", "=", 1]],
                      ["name", "item"], 0)
    bom_of = {r["item"]: r["name"] for r in boms}
    rates = {r["name"]: r.get("valuation_rate") for r in c.get_list(
        "Item", [["name", "in", items]], ["name", "valuation_rate"], 0)}

    # ── 菲号产能分配：成品仓现有 → 剩余靠生产；按 PRIORITY 贪心（00082 优先）──
    cap_eff: dict = {}
    fg_stock: dict = {}
    for (ic, tn) in tagged_keys:
        shell = sle_bal(c, "PK#" + ic, WH_SHELL, tn)
        shell_bin = bin_bal(c, "PK#" + ic, WH_SHELL)
        # 物理上限 = min(菲号数量, 待包装仓同菲号皮壳, 待包装仓 Bin 总量)
        cap_eff[(ic, tn)] = min(caps.get(tn, 0.0), shell, shell_bin)
        fg_stock[(ic, tn)] = sle_bal(c, ic, WH_FG, tn)

    stock_left = dict(fg_stock)
    prod_left = {k: max(cap_eff[k] - fg_stock[k], 0.0) for k in tagged_keys}
    alloc: dict = {}      # (dn, ic, tn) -> 本次要生产的量
    short: dict = {}      # (dn, ic, tn) -> 让出的量
    for dn_name in PRIORITY:
        d = per_dn.get(dn_name)
        if not d:
            continue
        for (ic, tn), q in d["need"].items():
            if not tn:
                continue
            key = (ic, tn)
            use_stock = min(q, stock_left.get(key, 0.0))
            stock_left[key] = stock_left.get(key, 0.0) - use_stock
            need_left = q - use_stock
            take = min(need_left, prod_left.get(key, 0.0))
            prod_left[key] = prod_left.get(key, 0.0) - take
            alloc[(dn_name, ic, tn)] = take
            short[(dn_name, ic, tn)] = need_left - take

    for dn_name, d in per_dn.items():
        fill, tagged, untagged, xfer, skip = [], [], [], [], []
        wo_load: dict[str, float] = defaultdict(float)

        for (ic, tn), q in sorted(d["need"].items(), key=lambda x: (x[0][0], str(x[0][1]))):
            if tn:
                take = alloc.get((dn_name, ic, tn), 0.0)
                if take <= 1e-6:
                    given = short.get((dn_name, ic, tn), 0.0)
                    if given > 1e-6:
                        skip.append(("让给 00082（超菲号产能）", ic, tn, q,
                                     cap_eff.get((ic, tn), 0.0), given))
                    continue
                cands = wos.get(ic, [])
                if not cands:
                    skip.append(("无成品工单", ic, tn, take, 0.0, 0.0))
                    continue
                picked = None
                for w in cands:
                    remain = float(w["qty"] or 0) - float(w["produced_qty"] or 0) - wo_load[w["name"]]
                    if remain + 1e-6 >= take:
                        picked = w
                        break
                if picked is None:
                    picked = cands[0]
                wo_load[picked["name"]] += take
                tagged.append({"item": ic, "tn": tn, "qty": take,
                               "shell_avail": sle_bal(c, "PK#" + ic, WH_SHELL, tn),
                               "wo": picked["name"],
                               "wo_remain": float(picked["qty"] or 0) - float(picked["produced_qty"] or 0)})
                fill.append({"tn": tn, "wo": picked["name"]})
                given = short.get((dn_name, ic, tn), 0.0)
                if given > 1e-6:      # 只能产一部分，缺口要照实列出来
                    skip.append(("让给 00082（超菲号产能）", ic, tn, q,
                                 cap_eff.get((ic, tn), 0.0), given))
            else:
                fg_have = sle_bal(c, ic, WH_FG, None)
                q_prod = q - fg_have                    # 已有无菲号成品先抵扣
                if q_prod <= 1e-6:
                    continue
                shell_half = sle_bal(c, "PK#" + ic, WH_SHELL, None)
                short_q = q_prod - shell_half
                if short_q <= 1e-6:
                    untagged.append({"item": ic, "qty": q_prod, "bom": bom_of.get(ic),
                                     "rate": rates.get(ic), "shell_avail": shell_half})
                else:
                    srcs = untagged_shell_sources(c, "PK#" + ic)
                    from_semi = srcs.get(WH_SEMI, 0.0)
                    if from_semi + 1e-6 >= short_q:
                        untagged.append({"item": ic, "qty": q_prod, "bom": bom_of.get(ic),
                                         "rate": rates.get(ic), "shell_avail": shell_half})
                        xfer.append({"item": "PK#" + ic, "qty": short_q, "src": WH_SEMI,
                                     "for_item": ic})
                    else:
                        skip.append(("无菲号皮壳来源不足", ic, None, q_prod,
                                     shell_half + from_semi, 0.0))

        d.update({"fill": fill, "tagged": tagged, "untagged": untagged,
                  "xfer": xfer, "skip": skip, "alloc": {k: v for k, v in alloc.items() if k[0] == dn_name}})
    return {"per_dn": per_dn, "combined": dict(combined), "caps": caps, "cap_eff": cap_eff,
            "wos": wos, "bom_of": bom_of, "rates": rates}


# ── 打印 ───────────────────────────────────────────────────
def print_plan(p: dict, dn_filter: list[str]) -> None:
    for dn_name, d in p["per_dn"].items():
        if dn_filter and dn_name not in dn_filter:
            continue
        print("=" * 104)
        print(f"{dn_name}  计划={d['plan']}  需求={sum(d['need'].values()):.0f}"
              f"  回填 {len(d['fill'])} ｜ 带菲号投产 {len(d['tagged'])}"
              f" ｜ 无菲号投产 {len(d['untagged'])} ｜ 调拨 {len(d['xfer'])} ｜ 跳过 {len(d['skip'])}")

        if d["fill"]:
            print(f"\n  [fill] 回填 finished_product_work_order（{len(d['fill'])} 条）")
            for o in d["fill"]:
                print(f"     {o['tn']:<18} → {o['wo']}")

        if d["tagged"]:
            print(f"\n  [tagged] 带菲号投产 Manufacture（{len(d['tagged'])} 张，"
                  f"{sum(o['qty'] for o in d['tagged']):.0f} 件）")
            for o in d["tagged"]:
                print(f"     {o['item']:<26}{o['tn']:<18}{o['qty']:>4.0f} 件"
                      f"  皮壳备 {o['shell_avail']:>5.0f}  → 工单 {o['wo']}（余 {o['wo_remain']:.0f}）")

        if d["xfer"]:
            print(f"\n  [xfer] 无菲号皮壳调拨 {WH_SEMI} → {WH_SHELL}（{len(d['xfer'])} 条）")
            for o in d["xfer"]:
                print(f"     {o['item']:<26}{o['qty']:>4.0f} 件  （供 {o['for_item']}）")

        if d["untagged"]:
            print(f"\n  [untagged] 无菲号投产（{len(d['untagged'])} 张，"
                  f"{sum(o['qty'] for o in d['untagged']):.0f} 件）")
            for o in d["untagged"]:
                print(f"     {o['item']:<26}{o['qty']:>4.0f} 件  皮壳 {o['shell_avail']:>5.0f}"
                      f"  单价 {o['rate']}  BOM {o['bom']}")

        if d["skip"]:
            print(f"\n  [skip] 跳过（{len(d['skip'])} 组）")
            for reason, ic, tn, q, have, extra in d["skip"]:
                if reason.startswith("让给"):
                    tail = f"需求 {q:>4.0f}，让出 {extra:>4.0f}（菲号产能 {have:.0f}）"
                elif reason == "无菲号皮壳来源不足":
                    tail = f"需 {q:>4.0f}，可凑 {have:.0f}"
                else:
                    tail = f"{q:.0f} 件"
                print(f"     {reason:<22}{ic:<26}{tn or '（无菲号）':<18}{tail}")

    print("\n" + "=" * 104)
    print("[不做的事] 不改 DN 任何行；不改计划；不动全局 allow_negative_stock；不改代码；不碰超量菲号")


def cmd_probe(c: Client, dn_filter: list[str]) -> None:
    p = build_plan_all(c)
    print_plan(p, dn_filter)


# ── 执行 ───────────────────────────────────────────────────
def ensure_script(c: Client) -> None:
    try:
        c.delete("Server Script", SERVER_SCRIPT)
    except Exception:  # noqa: BLE001
        pass
    c.insert("Server Script", {"doctype": "Server Script", "name": SERVER_SCRIPT,
                               "script_type": "API", "api_method": METHOD,
                               "script": SERVER_BODY, "disabled": 0, "allow_guest": 0})


def cmd_apply(c: Client, part: str, apply: bool, dn_filter: list[str]) -> None:
    p = build_plan_all(c)
    todo: list[dict] = []                   # {"dn","plan","ops":[(kind, op), ...]}
    for dn_name, d in p["per_dn"].items():
        if dn_filter and dn_name not in dn_filter:
            continue
        ops: list[tuple[str, dict]] = []
        if part == "fill":
            ops = [("fill", o) for o in d["fill"]]
        elif part == "tagged":
            ops = [("tagged", o) for o in d["tagged"]]
        elif part == "xfer":
            ops = [("xfer", o) for o in d["xfer"]]
        elif part == "untagged":
            ops = ([("xfer", o) for o in d["xfer"]]
                   + [("untagged", o) for o in d["untagged"]])
        if ops:
            todo.append({"dn": dn_name, "plan": d["plan"], "ops": ops})

    if not todo:
        print("无操作")
        return
    total = sum(len(t["ops"]) for t in todo)
    print(f"[{part}] {total} 个动作" + ("（dry-run，只构建不提交）" if not apply else "（真写）"))
    for k in ("xfer", "untagged", "tagged", "fill"):
        n = sum(1 for t in todo for kk, _ in t["ops"] if kk == k)
        if n:
            print(f"   {k}: {n}")

    m = json.loads(MANIFEST.read_text(encoding="utf-8")) if MANIFEST.is_file() else {}
    m.setdefault("done", {})
    ensure_script(c)
    done: list[dict] = []
    try:
        i = 0
        for t in todo:
            plan_name = t["plan"]
            for kind, o in t["ops"]:
                i += 1
                if kind == "fill":
                    params = {"mode": "fill", "plan": plan_name, "tn": o["tn"], "wo": o["wo"]}
                elif kind == "tagged":
                    params = {"mode": "tagged", "plan": plan_name, "item": o["item"],
                              "qty": o["qty"], "tn": o["tn"], "wo": o["wo"]}
                elif kind == "xfer":
                    params = {"mode": "xfer", "plan": plan_name, "item": o["item"],
                              "qty": o["qty"], "src": o["src"]}
                else:
                    params = {"mode": "untagged", "plan": plan_name, "item": o["item"],
                              "qty": o["qty"], "bom": o.get("bom") or ""}
                params["dry"] = "0" if apply else "1"
                label = o.get("tn") or o.get("for_item") or o["item"]
                try:
                    res = c.call(METHOD, params)
                    tag = res.get("name") or "构建 OK"
                    print(f"   [{i}/{total}] {t['dn']} {kind:<8}{str(label):<18}"
                          f"{o.get('qty', 0):>4.0f} → {tag}")
                    if not apply and res.get("rows"):
                        fin = [r for r in res["rows"] if r["is_finished_item"]]
                        src = [r for r in res["rows"] if not r["is_finished_item"]]
                        print("        成品行 " + str([(r["item_code"], r["qty"], r["basic_rate"]) for r in fin]))
                        print(f"        原料行 {len(src)} 条: "
                              + ", ".join(f"{r['item_code']}×{r['qty']:.0f}@" for r in src))
                    if apply:
                        done.append({"dn": t["dn"], "kind": kind, "label": label,
                                     "qty": o.get("qty"), "name": res.get("name")})
                except RuntimeError as e:
                    print(f"   [{i}/{total}] ✗ {t['dn']} {kind} {label} 失败：{str(e)[:300]}")
    finally:
        try:
            c.delete("Server Script", SERVER_SCRIPT)
            print(f"   ✓ 已删除临时 Server Script {SERVER_SCRIPT}")
        except Exception as e:  # noqa: BLE001
            print(f"   ✗ 临时脚本删除失败，请手工删除 {SERVER_SCRIPT}：{e}")

    if apply and done:
        m["done"].setdefault(part, []).extend(done)
        OUT_DIR.mkdir(exist_ok=True)
        MANIFEST.write_text(json.dumps(m, ensure_ascii=False, indent=1), encoding="utf-8")
        print(f"✓ {len(done)} 个动作已写库 → 清单 {MANIFEST}")


def cmd_verify(c: Client, dn_filter: list[str]) -> None:
    """按 DN before_submit 的口径复核：SUM(SLE.actual_qty) 按 (物料, 仓库, 菲号)。"""
    for dn_name, plan_name in TARGETS.items():
        if dn_filter and dn_name not in dn_filter:
            continue
        dn = c.get_doc("Delivery Note", dn_name) if True else None
        need = dn_need(c, dn_name)
        print(f"\n=== {dn_name}（计划 {plan_name}）docstatus={dn.get('docstatus')} ===")
        bad = []
        for (ic, tn), q in sorted(need.items(), key=lambda x: (x[0][0], str(x[0][1]))):
            have = sle_bal(c, ic, WH_FG, tn)
            ok = have + 1e-6 >= q
            if not ok:
                bad.append((ic, tn, q - have))
        print(f"   组数 {len(need)}，仍缺 {len(bad)} 组"
              f"（缺口合计 {sum(x[2] for x in bad):.0f} 件）")
        for ic, tn, gap in bad:
            print(f"     缺 {ic:<26}{tn or '（无菲号）':<18}{gap:>5.0f}")
    ss = c.get_list("Server Script", [["name", "like", "zz_%"]], ["name"], 0)
    print(f"\n临时脚本残留：{len(ss)} 个（应为 0）")


def main() -> int:
    ap = argparse.ArgumentParser(description=__doc__,
                                 formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("cmd", choices=("probe", "dry", "apply", "verify"))
    ap.add_argument("--part", choices=("fill", "tagged", "untagged", "xfer"))
    ap.add_argument("--apply", action="store_true", help="真正写生产（默认 dry-run）")
    ap.add_argument("--dn", nargs="*", default=[], help="只处理指定 DN")
    args = ap.parse_args()

    bad = [d for d in args.dn if d not in TARGETS]
    if bad:
        raise SystemExit(f"✗ 未知 DN: {bad}（可选 {list(TARGETS)}）")

    c = Client("prod")
    if args.cmd in ("probe", "dry"):
        cmd_probe(c, args.dn)
    elif args.cmd == "verify":
        cmd_verify(c, args.dn)
    else:
        if not args.part:
            raise SystemExit("✗ apply 必须带 --part fill|tagged|untagged|xfer")
        cmd_apply(c, args.part, args.apply, args.dn)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
