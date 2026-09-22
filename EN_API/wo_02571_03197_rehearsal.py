# -*- coding: utf-8 -*-
"""WO-26-02571 改挂方案 B 的**测试环境演练**（硬锁 ensh.vilavi.cn）

目的：在碰生产之前，用与生产**同一套 Server Script 代码**（来自 wo_02571_03197_reassign.py
的 repoint_script / redo_script / fixqty_script）在测试环境跑通完整 7 步，验证：

  H1 取消已提交的 Manufacture（成品行、无消耗行）是否可行 / 是否被负库存拦
  H2 按物料开 Item.allow_negative_stock 能否放行
  H3 沙箱是否接受这三段脚本（禁下划线变量 / 禁 import / 禁 getattr / 禁 -=）
  H4 「只有成品行 + 手写单价」的 Manufacture 能否 insert + submit，单价是否保住
  H5 改挂后 SLE 归属是否按菲号迁移，总量守恒

**硬锁测试环境**，不提供 prod 分支。

  python EN_API/wo_02571_03197_rehearsal.py scout
  python EN_API/wo_02571_03197_rehearsal.py run --apply
  python EN_API/wo_02571_03197_rehearsal.py report
  python EN_API/wo_02571_03197_rehearsal.py cleanup --apply
"""

from __future__ import annotations

import argparse
import json
import sys
from datetime import date
from pathlib import Path

from wo_02571_03197_reassign import (
    ApiClient, fixqty_script, redo_script, repoint_script,
)

sys.stdout.reconfigure(encoding="utf-8")
sys.stderr.reconfigure(encoding="utf-8")

_DIR = Path(__file__).resolve().parent
OUT_DIR = _DIR / "out"
MANIFEST = OUT_DIR / "wo_02571_03197_rehearsal_manifest.json"

BASE = "https://ensh.vilavi.cn"      # 硬锁测试环境
COMPANY = "FZH"

SHELL = "ZZRS-SHELL"
RAW = "ZZRS-RAW"
WO_T = "WO-ZZRS-TGT"
WO_S = "WO-ZZRS-SRC"
BOM = "BOM-ZZRS-SHELL-001"

WH_HALF = "待包装半成品仓 - FZH"
WH_STAGE = "待包装成品仓 - FZH"
WH_WIP = "在制品仓 - FZH"

# 4 个源菲号（13/26/13/26=78），前三个要改挂，第四个留下
TN_S = {"ZZRS-TN-001": 13.0, "ZZRS-TN-002": 26.0, "ZZRS-TN-003": 13.0, "ZZRS-TN-004": 26.0}
# 目标工单既有的 2 个菲号
TN_T = {"ZZRS-TN-005": 39.0, "ZZRS-TN-006": 39.0}
MOVE = {"ZZRS-TN-001": 13.0, "ZZRS-TN-002": 26.0, "ZZRS-TN-003": 13.0}
KEEP = {"ZZRS-TN-004": 26.0}

RATE = 27.88
TGT_QTY, SRC_QTY = 130.0, 26.0


def log(step: str, ok, detail) -> None:
    mark = "·" if ok is None else ("✓" if ok else "✗")
    print(f"   {mark} {step}: {detail}")


def banner(t: str) -> None:
    print(f"\n{'═' * 70}\n{t}\n{'═' * 70}")


def mf():
    return json.loads(MANIFEST.read_text(encoding="utf-8")) if MANIFEST.is_file() else {"created": {}}


def save_m(m: dict) -> None:
    """合并写盘：调用方持有的是旧快照，直接覆盖会丢掉后写的键。"""
    OUT_DIR.mkdir(exist_ok=True)
    cur = mf()
    for k, v in m.items():
        if k == "created":
            cur.setdefault("created", {}).update(v or {})
        else:
            cur[k] = v
    MANIFEST.write_text(json.dumps(cur, ensure_ascii=False, indent=1), encoding="utf-8")


def bal(c: ApiClient, tns, wh) -> float:
    tot = 0.0
    for tn in tns:
        for r in c.sle_rows(tracking=tn, item_code=SHELL, warehouse=wh):
            tot += float(r["actual_qty"] or 0)
    return round(tot, 4)


def show(c: ApiClient, label: str) -> None:
    print(f"   [{label}] 本批壳@{WH_HALF}={bal(c, list(TN_S) + list(TN_T), WH_HALF)}  "
          f"壳@{WH_STAGE}={bal(c, list(TN_S) + list(TN_T), WH_STAGE)}")


# ── 场景搭建 ────────────────────────────────────────────────
def ensure_masters(c: ApiClient) -> None:
    for code, name in ((SHELL, "ZZRS 皮壳"), (RAW, "ZZRS 原料")):
        if not c.get_all("Item", [["name", "=", code]], ["name"], 1):
            c.insert_doc("Item", {"doctype": "Item", "item_code": code, "item_name": name,
                                  "item_group": "三角靠枕", "stock_uom": "个", "is_stock_item": 1})
            log(f"Item {code}", True, "已创建")
        else:
            log(f"Item {code}", None, "已存在")

    bom = c.get_all("BOM", [["name", "=", BOM]], ["name", "docstatus"], 1)
    if not bom:
        c.insert_doc("BOM", {"doctype": "BOM", "name": BOM, "item": SHELL, "quantity": 1,
                             "company": COMPANY, "uom": "个",
                             "items": [{"doctype": "BOM Item", "item_code": RAW, "qty": 1.0,
                                        "uom": "个", "stock_uom": "个", "rate": 10.0}]})
        c.submit_doc("BOM", BOM)
        log(f"BOM {BOM}", True, "已创建并提交")
    elif int(bom[0]["docstatus"]) == 0:
        c.submit_doc("BOM", BOM)
        log(f"BOM {BOM}", True, "补提交草稿")
    else:
        log(f"BOM {BOM}", None, "已提交")


def ensure_wo(c: ApiClient, qty: float, fg_wh: str, tag: str) -> str:
    """建工单并提交。Work Order 走自动序列命名，必须回读真实编号。"""
    m = mf()
    got = m.get("created", {}).get(tag)
    if got and c.get_all("Work Order", [["name", "=", got]], ["name"], 1):
        log(f"WO({tag})", None, f"已存在 {got}")
        return got
    doc = {"doctype": "Work Order", "production_item": SHELL, "bom_no": BOM, "qty": qty,
           "company": COMPANY, "fg_warehouse": fg_wh, "wip_warehouse": WH_WIP,
           "source_warehouse": WH_WIP, "use_multi_level_bom": 0,
           "transfer_material_against": "Work Order", "skip_transfer": 0,
           "stock_uom": "个"}
    name = c.insert_doc("Work Order", doc)["name"]
    c.submit_doc("Work Order", name)
    m.setdefault("created", {})[tag] = name
    save_m(m)
    log(f"WO({tag})", True, f"{name} ×{qty} → {fg_wh}")
    return name


def make_tns(c: ApiClient, tns: dict, wo: str) -> None:
    """菲号挂当前轮的工单（与生产一致）。残留菲号会被对齐，避免报告出现假失败。"""
    for t, q in tns.items():
        got = c.get_all("Tracking Number", [["name", "=", t]], ["name", "work_order"], 1)
        if got:
            if got[0].get("work_order") != wo:
                c._write("PUT", f"/api/resource/Tracking%20Number/{t}", {"work_order": wo})
                log(f"TN {t}", True, f"对齐 work_order={wo}（原 {got[0].get('work_order')}）")
            continue
        try:
            c.insert_doc("Tracking Number", {"doctype": "Tracking Number", "tracking_number": t,
                                             "qty": q, "item_code": SHELL, "work_order": wo})
        except Exception as e:  # noqa: BLE001
            log(f"TN {t}", False, f"创建失败：{str(e)[:160]}")


def make_mfg(c: ApiClient, wo: str, tns: dict, wh: str) -> list[str]:
    """生产形态的 Manufacture：只有成品行，无消耗行。"""
    out = []
    for t, q in tns.items():
        doc = {"doctype": "Stock Entry", "stock_entry_type": "Manufacture", "purpose": "Manufacture",
               "company": COMPANY, "posting_date": str(date.today()), "fg_completed_qty": q,
               "work_order": wo, "tracking_number": t, "from_bom": 1, "use_multi_level_bom": 1,
               "items": [{"doctype": "Stock Entry Detail", "item_code": SHELL, "qty": q,
                          "t_warehouse": wh, "stock_tracking_number": t, "uom": "个",
                          "is_finished_item": 1, "basic_rate": RATE,
                          "valuation_rate": RATE, "set_basic_rate_manually": 1}]}
        name = c.insert_doc("Stock Entry", doc)["name"]
        c.submit_doc("Stock Entry", name)
        out.append(name)
    log(f"Manufacture ×{len(out)}", True, f"{out} → {wh}")
    return out


def make_initial_wo(c: ApiClient, wo_t: str, wo_s: str) -> None:
    """开料工单：这是 open_material_qty=78 的来源，也是 Manufacture 提交时
    update_tracking_stock_entrys_on_submit 反查「Woker Order Allocation」的依靠。
    故意复刻生产的错误分配：源工单只要 26 却分了 78，目标工单要 130 只分 78。"""
    m = mf()
    if m.get("created", {}).get("initial_wo"):
        log("Initial Work Order", None, f"已存在 {m['created']['initial_wo']}")
        return
    alloc = [{"doctype": "Woker Order Allocation", "work_order": wo_s, "group_split_qty": q,
              "tracking_number": t, "label_qty": 1, "fg_item": SHELL,
              "group_number": i + 1, "is_or_exceed": 1 if q + sum(
                  list(TN_S.values())[:i]) >= SRC_QTY else 0}
             for i, (t, q) in enumerate(TN_S.items())]
    alloc += [{"doctype": "Woker Order Allocation", "work_order": wo_t, "group_split_qty": q,
               "tracking_number": t, "label_qty": 1, "fg_item": SHELL,
               "group_number": 10 + i, "is_or_exceed": 0}
              for i, (t, q) in enumerate(TN_T.items())]
    doc = {"doctype": "Initial Work Order", "company": COMPANY, "date": str(date.today()),
           "employee": c.get_all("Employee", [], ["name"], 1)[0]["name"],
           "workstation": c.get_all("Workstation", [], ["name"], 1)[0]["name"],
           "source_warehouse": WH_WIP, "manual_assign_wo": 1,
           "default_scrap_warehouse": "不良品仓 - FZH",
           "work_orders": [{"doctype": "Initial Work Order Item", "work_order": w, "work_order_qty": q,
                            "item_name": SHELL}
                           for w, q in ((wo_t, TGT_QTY), (wo_s, SRC_QTY))],
           "woker_order_allocations": alloc}
    name = c.insert_doc("Initial Work Order", doc)["name"]
    try:
        c.submit_doc("Initial Work Order", name)
        log("Initial Work Order", True, f"{name} 已提交（分配 源78 / 目标78）")
    except Exception as e:  # noqa: BLE001
        log("Initial Work Order 提交失败", False, str(e)[:300])
    m.setdefault("created", {})["initial_wo"] = name
    save_m(m)


def cmd_scout(c: ApiClient) -> None:
    banner("scout：测试环境现状（只读）")
    for code in (SHELL, RAW):
        log(f"Item {code}", None, "存在" if c.get_all("Item", [["name", "=", code]], ["name"], 1) else "缺失")
    log("BOM", None, "存在" if c.get_all("BOM", [["name", "=", BOM]], ["name"], 1) else "缺失")
    for w in (WO_T, WO_S):
        r = c.get_all("Work Order", [["name", "=", w]], ["name", "qty", "status"], 1)
        log(f"WO {w}", None, r[0] if r else "缺失")
    show(c, "当前")
    m = mf()
    log("manifest", None, f"created={ {k: v for k, v in m.get('created', {}).items() if v} }")


def cmd_run(c: ApiClient, apply: bool) -> None:
    banner("run：搭建等效场景并跑完整 7 步")
    if not apply:
        print("   dry-run：加 --apply 才真正写测试环境")
        return

    m = mf()
    cr = m.setdefault("created", {})

    banner("① 搭建")
    ensure_masters(c)
    wo_t = ensure_wo(c, TGT_QTY, WH_HALF, "wo_t")
    wo_s = ensure_wo(c, SRC_QTY, WH_STAGE, "wo_s")
    make_tns(c, TN_T, wo_t)
    make_tns(c, TN_S, wo_s)
    make_initial_wo(c, wo_t, wo_s)

    # 两个工单各自的完工入库（与生产同形：只有成品行、无消耗行）。
    # 目标工单 2 张 ×39 → 待包装半成品仓；源工单 4 张 13/26/13/26 → 待包装成品仓。
    if not cr.get("mfg_t"):
        cr["mfg_t"] = make_mfg(c, wo_t, TN_T, WH_HALF)
        save_m(m)
    else:
        log("目标工单 Manufacture", None, f"已存在 {cr['mfg_t']}")

    if not cr.get("mfg_s"):
        cr["mfg_s"] = make_mfg(c, wo_s, TN_S, WH_STAGE)
        save_m(m)
    else:
        log("源工单 Manufacture", None, f"已存在 {cr['mfg_s']}")
    show(c, "投产到位")

    banner("② step open-gate")
    c.set_item_flag(SHELL, 1)
    log(f"{SHELL}.allow_negative_stock", True, str(c.get_item_flag(SHELL)))

    banner("③ step cancel")
    cancelled = []
    for name in cr["mfg_s"]:
        tns = c.get_all("Stock Entry", [["name", "=", name]], ["tracking_number"], 1)
        tn = tns[0]["tracking_number"] if tns else None
        if tn in MOVE:                                  # 只取消要改挂的 3 张
            try:
                c.cancel_doc("Stock Entry", name)
                cancelled.append(name)
                log(f"取消 {name} ({tn})", True, "ok")
            except Exception as e:  # noqa: BLE001
                log(f"取消 {name} ({tn})", False, str(e)[:200])
    cr["cancelled"] = cancelled
    save_m(m)
    show(c, "取消后")

    banner("④ step repoint（五层）（走沙箱 Server Script）")
    body = repoint_script(list(MOVE), wo_t, wo_s, SHELL)
    try:
        c.insert_doc("Server Script", {"doctype": "Server Script", "name": "zz_zzrs_repoint",
                                       "script_type": "API", "api_method": "zz_zzrs_repoint",
                                       "script": body, "disabled": 0, "allow_guest": 0})
        log("建临时脚本", True, "zz_zzrs_repoint")
        res = c.call_method("zz_zzrs_repoint")
        log("执行 repoint", True, json.dumps(res, ensure_ascii=False))
    except Exception as e:  # noqa: BLE001
        log("repoint 失败", False, str(e)[:400])
        raise
    finally:
        try:
            c.delete_doc("Server Script", "zz_zzrs_repoint")
            log("删临时脚本", True, "ok")
        except Exception as e:  # noqa: BLE001
            log("删临时脚本", False, str(e)[:150])

    # 关键顺序：先把目标工单的 open_material_qty 抬到 130，否则 redo 提交时
    # work_order_override.update_work_order_qty 会用 completed_qty=open_material_qty=78
    # 判「入库量 91 > 78」并抛 StockOverProductionError。
    banner("⑤ step fix-wo-qty（走沙箱 Server Script；必须在 redo 之前）")
    body = fixqty_script(wo_t, TGT_QTY, wo_s, SRC_QTY)
    try:
        c.insert_doc("Server Script", {"doctype": "Server Script", "name": "zz_zzrs_fixqty",
                                       "script_type": "API", "api_method": "zz_zzrs_fixqty",
                                       "script": body, "disabled": 0, "allow_guest": 0})
        res = c.call_method("zz_zzrs_fixqty")
        log("执行 fixqty", True, json.dumps(res, ensure_ascii=False))
    except Exception as e:  # noqa: BLE001
        log("fixqty 失败", False, str(e)[:400])
        raise
    finally:
        try:
            c.delete_doc("Server Script", "zz_zzrs_fixqty")
        except Exception:  # noqa: BLE001
            pass

    banner("⑥ step redo（走沙箱 Server Script）")
    mapping = [(tn, q, cr["mfg_s"][i]) for i, (tn, q) in enumerate(TN_S.items()) if tn in MOVE]
    body = redo_script(mapping, wo_t, SHELL, WH_HALF)
    try:
        c.insert_doc("Server Script", {"doctype": "Server Script", "name": "zz_zzrs_redo",
                                       "script_type": "API", "api_method": "zz_zzrs_redo",
                                       "script": body, "disabled": 0, "allow_guest": 0})
        log("建临时脚本", True, "zz_zzrs_redo")
        res = c.call_method("zz_zzrs_redo")
        log("执行 redo", True, json.dumps(res, ensure_ascii=False))
        cr["redo"] = res
        save_m(m)
    except Exception as e:  # noqa: BLE001
        log("redo 失败", False, str(e)[:400])
        raise
    finally:
        try:
            c.delete_doc("Server Script", "zz_zzrs_redo")
            log("删临时脚本", True, "ok")
        except Exception as e:  # noqa: BLE001
            log("删临时脚本", False, str(e)[:150])

    banner("⑦ step close-gate")
    c.set_item_flag(SHELL, 0)
    log(f"{SHELL}.allow_negative_stock", True, str(c.get_item_flag(SHELL)))

    cmd_report(c)


def cmd_report(c: ApiClient) -> None:
    banner("report：结果断言")
    cr = mf().get("created", {})
    wo_t = cr.get("wo_t")
    wo_s = cr.get("wo_s")
    if not (wo_t and wo_s):
        print("   ✗ manifest 里没有工单编号，先跑 run")
        return
    checks = []

    half = bal(c, list(TN_S) + list(TN_T), WH_HALF)
    stage = bal(c, list(TN_S) + list(TN_T), WH_STAGE)
    checks.append((f"本批壳@{WH_HALF} == 130", abs(half - 130.0) < 1e-6, f"实际 {half}"))
    checks.append((f"本批壳@{WH_STAGE} == 26", abs(stage - 26.0) < 1e-6, f"实际 {stage}"))

    for tn in MOVE:
        row = c.get_all("Tracking Number", [["name", "=", tn]],
                        ["work_order", "finished_product_work_order", "so_materials"], 1)
        ok = bool(row) and row[0]["work_order"] == wo_t
        checks.append((f"菲号 {tn} 归属 {wo_t}", ok, str(row[0]) if row else "缺失"))

    for tn in KEEP:
        row = c.get_all("Tracking Number", [["name", "=", tn]], ["work_order"], 1)
        checks.append((f"菲号 {tn} 仍在 {wo_s}",
                       bool(row) and row[0]["work_order"] == wo_s,
                       str(row[0]) if row else "缺失"))

    for wo, want in ((wo_t, TGT_QTY), (wo_s, SRC_QTY)):
        d = c.get_doc("Work Order", wo)
        checks.append((f"{wo}.produced_qty == {want}",
                       abs(float(d.get("produced_qty") or 0) - want) < 1e-6,
                       f"实际 {d.get('produced_qty')}"))

    # 重做的凭证单价是否等于原单价（0 成本陷阱）
    for x in (mf().get("created", {}).get("redo") or []):
        se = c.get_doc("Stock Entry", x["name"])
        rate = float(se["items"][0].get("basic_rate") or 0)
        checks.append((f"{x['name']} 单价 == {RATE}",
                       abs(rate - RATE) < 1e-4, f"实际 {rate}"))

    left = c.get_all("Server Script", [["name", "like", "zz_zzrs%"]], ["name"], 0)
    checks.append(("临时脚本已清理", not left, f"残留 {[x['name'] for x in left]}"))
    checks.append((f"{SHELL}.allow_negative_stock 已归零",
                   not int(c.get_item_flag(SHELL) or 0), f"实际 {c.get_item_flag(SHELL)}"))

    print()
    for name, ok, detail in checks:
        print(f"   {'✓' if ok else '✗'} {name}（{detail}）")
    bad = [n for n, ok, _ in checks if not ok]
    print("\n" + ("✓ 全部通过，方案 B 在测试环境可行" if not bad else f"✗ 未通过 {len(bad)} 项：{bad}"))


def cmd_cleanup(c: ApiClient, apply: bool) -> None:
    banner("cleanup：清理 ZZRS 测试单据")
    if not apply:
        print("   dry-run：加 --apply 才真正删")
        return
    # 取消所有动过 SHELL 的未取消凭证，再删测试单据
    ses = c.get_all("Stock Entry", [["docstatus", "=", 1]], ["name"], 0)
    for s in ses:
        d = c.get_doc("Stock Entry", s["name"])
        if any(i.get("item_code") == SHELL for i in (d.get("items") or [])):
            try:
                c.cancel_doc("Stock Entry", s["name"])
                log(f"取消 {s['name']}", True, "ok")
            except Exception as e:  # noqa: BLE001
                log(f"取消 {s['name']}", False, str(e)[:120])
    for wo in (WO_T, WO_S):
        try:
            c._write("POST", "/api/method/frappe.client.cancel", {"doctype": "Work Order", "name": wo})
            c.delete_doc("Work Order", wo)
            log(f"删 {wo}", True, "ok")
        except Exception as e:  # noqa: BLE001
            log(f"删 {wo}", False, str(e)[:120])

    # 先删菲号（否则后面的步骤一旦报错，菲号会带着上一轮的 work_order 留下来）
    for t in list(TN_S) + list(TN_T):
        try:
            c.delete_doc("Tracking Number", t)
        except Exception:  # noqa: BLE001
            pass

    # 历轮演练累积的工单也一并清（否则菲号会挂在上一轮的工单上，报告出现假失败）
    for w in c.get_all("Work Order", [["production_item", "=", SHELL]], ["name", "docstatus"], 0):
        wn = str(w["name"])
        try:
            if int(w.get("docstatus") or 0) == 1:
                c._write("POST", "/api/method/frappe.client.cancel",
                         {"doctype": "Work Order", "name": wn})
            c.delete_doc("Work Order", wn)
            log(f"删遗留工单 {wn}", True, "ok")
        except Exception as e:  # noqa: BLE001
            log(f"删遗留工单 {wn}", False, str(e)[:100])

    for iwo in c.get_all("Initial Work Order", [], ["name", "docstatus"], 0):
        iname = str(iwo["name"])
        try:
            d = c.get_doc("Initial Work Order", iname)
            if any(r.get("fg_item") == SHELL for r in (d.get("woker_order_allocations") or [])):
                if int(iwo.get("docstatus") or 0) == 1:
                    c._write("POST", "/api/method/frappe.client.cancel",
                             {"doctype": "Initial Work Order", "name": iname})
                c.delete_doc("Initial Work Order", iname)
                log(f"删遗留开料工单 {iname}", True, "ok")
        except Exception as e:  # noqa: BLE001
            log(f"删遗留开料工单 {iname}", False, str(e)[:100])
    for x in c.get_all("Server Script", [["name", "like", "zz_zzrs%"]], ["name"], 0):
        c.delete_doc("Server Script", x["name"])
    c.set_item_flag(SHELL, 0)
    log("清理完成", True, "如需重建，删除 manifest 后重跑 run")


PURGE_BODY = f'''# 彻底清掉 ZZRS 演练痕迹（逐条容错，依赖倒序：SE/报工 → 开料工单 → 工单 → 菲号 → BOM/物料）
ITEM = "{SHELL}"
RAWITEM = "{RAW}"
done = 0
for name in frappe.get_all("Stock Entry", filters={{"tracking_number": ["like", "ZZRS-%"]}}, pluck="name"):
    try:
        doc = frappe.get_doc("Stock Entry", name)
        if doc.docstatus == 1:
            doc.cancel()
        frappe.delete_doc("Stock Entry", name, force=True, ignore_permissions=True)
        done = done + 1
    except Exception:
        frappe.db.rollback()
for name in frappe.get_all("Stock Entry", filters={{"name": ["like", "STE-26-002%"]}}, pluck="name"):
    try:
        doc = frappe.get_doc("Stock Entry", name)
        if doc.docstatus == 1:
            doc.cancel()
        frappe.delete_doc("Stock Entry", name, force=True, ignore_permissions=True)
        done = done + 1
    except Exception:
        frappe.db.rollback()
for name in frappe.get_all("Job Card", filters={{"tracking_number": ["like", "ZZRS-%"]}}, pluck="name"):
    try:
        doc = frappe.get_doc("Job Card", name)
        if doc.docstatus == 1:
            doc.cancel()
        frappe.delete_doc("Job Card", name, force=True, ignore_permissions=True)
        done = done + 1
    except Exception:
        frappe.db.rollback()
for name in frappe.get_all("Initial Work Order", pluck="name"):
    try:
        doc = frappe.get_doc("Initial Work Order", name)
        if any(x.get("fg_item") == ITEM for x in (doc.woker_order_allocations or [])):
            if doc.docstatus == 1:
                doc.cancel()
            frappe.delete_doc("Initial Work Order", name, force=True, ignore_permissions=True)
            done = done + 1
    except Exception:
        frappe.db.rollback()
for name in frappe.get_all("Work Order", filters={{"production_item": ITEM}}, pluck="name"):
    try:
        doc = frappe.get_doc("Work Order", name)
        if doc.docstatus == 1:
            doc.cancel()
        frappe.delete_doc("Work Order", name, force=True, ignore_permissions=True)
        done = done + 1
    except Exception:
        frappe.db.rollback()
for name in frappe.get_all("Tracking Number", filters={{"name": ["like", "ZZRS-%"]}}, pluck="name"):
    try:
        frappe.delete_doc("Tracking Number", name, force=True, ignore_permissions=True)
        done = done + 1
    except Exception:
        frappe.db.rollback()
for name in frappe.get_all("BOM", filters={{"item": ITEM}}, pluck="name"):
    try:
        doc = frappe.get_doc("BOM", name)
        if doc.docstatus == 1:
            doc.cancel()
        frappe.delete_doc("BOM", name, force=True, ignore_permissions=True)
        done = done + 1
    except Exception:
        frappe.db.rollback()
for name in [ITEM, RAWITEM]:
    try:
        frappe.delete_doc("Item", name, force=True, ignore_permissions=True)
        done = done + 1
    except Exception:
        frappe.db.rollback()
frappe.db.commit()
frappe.response["data"] = {{"deleted": done}}
'''


def cmd_purge(c: ApiClient, apply: bool) -> None:
    banner("purge：彻底清掉测试环境的 ZZRS 演练痕迹")
    if not apply:
        print("   dry-run：加 --apply 才真正删")
        return
    name = "zz_zzrs_purge"
    try:
        c.insert_doc("Server Script", {"doctype": "Server Script", "name": name,
                                       "script_type": "API", "api_method": name,
                                       "script": PURGE_BODY, "disabled": 0, "allow_guest": 0})
        log("执行 purge", True, json.dumps(c.call_method(name), ensure_ascii=False))
    except Exception as e:  # noqa: BLE001
        log("purge 失败", False, str(e)[:400])
    finally:
        try:
            c.delete_doc("Server Script", name)
        except Exception:  # noqa: BLE001
            pass
    if MANIFEST.is_file():
        MANIFEST.unlink()
    log("manifest", True, "已删除，可干净重跑 run")


def main() -> int:
    ap = argparse.ArgumentParser(description=__doc__,
                                 formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("cmd", choices=("scout", "run", "report", "cleanup", "purge"))
    ap.add_argument("--apply", action="store_true")
    args = ap.parse_args()

    assert BASE.endswith("ensh.vilavi.cn"), "演练脚本硬锁测试环境"
    c = ApiClient(base=BASE, key_env="TEST_ERP_API_KEY", sec_env="TEST_ERP_API_SECRET")

    if args.cmd == "scout":
        cmd_scout(c)
    elif args.cmd == "run":
        cmd_run(c, args.apply)
    elif args.cmd == "report":
        cmd_report(c)
    elif args.cmd == "purge":
        cmd_purge(c, args.apply)
    else:
        cmd_cleanup(c, args.apply)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
