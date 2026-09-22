# -*- coding: utf-8 -*-
"""WO-26-02571 / WO-26-03197 完工归属更正 —— 生产执行脚本

背景：SO-26-00101 的皮壳工单 WO-26-02571 计划 130 只入库 78；
      SO-26-00106 的皮壳子工单 WO-26-03197 计划 25 却入库 78。
      两工单产的是同一个物料 PK#KS0001-HLR-100-BLACK，但落在不同仓：
      02571 → 待包装半成品仓 - FZH；03197 → 待包装成品仓 - FZH。
      用户希望把 03197 多出的部分改挂到 02571。

**默认 dry-run。所有写操作必须 --apply，且按 step 逐步执行，每步之间先 verify。**

  python EN_API/wo_02571_03197_reassign.py probe      # 只读：全账面落盘 out/
  python EN_API/wo_02571_03197_reassign.py verify     # 只读：终态断言
"""

from __future__ import annotations

import argparse
import json
import sys
from concurrent.futures import ThreadPoolExecutor
from datetime import datetime
from pathlib import Path
from urllib.parse import quote

import requests
from requests.adapters import HTTPAdapter

sys.stdout.reconfigure(encoding="utf-8")
sys.stderr.reconfigure(encoding="utf-8")

_DIR = Path(__file__).resolve().parent
OUT_DIR = _DIR / "out"

PROD = "https://erpnext.vilavi.cn"

# ── 目标对象 ────────────────────────────────────────────────
WO_TARGET = "WO-26-02571"       # 应归属的目标工单（SO-26-00101 皮壳 130）
WO_SOURCE = "WO-26-03197"       # 被错挂的工单（SO-26-00106 皮壳 25）
SO_TARGET = "SO-26-00101"
SO_SOURCE = "SO-26-00106"
PP_TARGET = "PP-26-00033"
PP_SOURCE = "PP-26-00035"
WO_FG_SOURCE = "WO-26-03047"    # SO-26-00106 的成品工单（03197 的菲号指向它）
ITEM_SHELL = "PK#KS0001-HLR-100-BLACK"
ITEM_FG = "KS0001-HLR-100-BLACK"

WH_HALF = "待包装半成品仓 - FZH"
WH_FG_STAGE = "待包装成品仓 - FZH"
WH_FG = "成品仓 - FZH"

VIRTUAL_EMP = "HR-EMP-00001"    # 一键完工用的虚拟员工

# 承载本批菲号开料分配的开料工单（probe 已全量扫描 2026-09-01 起 62 张，只有它命中）。
# `Woker Order Allocation` 是子表，REST list 会 403 → 只能从父单据里读。
INITIAL_WO = "753"

# ── 本次更正口径（用户 2026-09-21 确认）────────────────────
# 03197 名下 4 个菲号 13/26/13/26 = 78；53 无法由整菲号组合得出，
# 取 52（三个整菲号）→ 02571 = 78 + 52 = 130（正好），03197 剩 26。
MOVE_TNS = {
    "WO-26-03197-001": 14.0,   # 二次更正：13→14（超量 1 件归到 02571）
    "WO-26-03197-002": 26.0,
    "WO-26-03197-003": 13.0,
}
KEEP_TNS = {"WO-26-03197-004": 25.0}   # 二次更正：26→25
# 目标工单既有的两个菲号（留在待包装半成品仓，本次不动）
HOLD_TNS = {"WO-26-02571-001": 39.0, "WO-26-02571-002": 39.0}
ALL_TNS = list(MOVE_TNS) + list(KEEP_TNS) + list(HOLD_TNS)
MOVE_QTY = 52.0

# 各步的预期账面（本批菲号皮壳结余）
EXPECT = {
    "initial":     {WH_HALF: 78.0, WH_FG_STAGE: 78.0},
    "after_cancel": {WH_HALF: 78.0, WH_FG_STAGE: 26.0},
    "final":        {WH_HALF: 131.0, WH_FG_STAGE: 25.0},
}

# 终态
FINAL_PRODUCED = {WO_TARGET: 131.0, WO_SOURCE: 25.0}
FINAL_OPEN_MATERIAL = {WO_TARGET: 131.0, WO_SOURCE: 25.0}

# ── 临时 API Server Script 正文 ─────────────────────────────
# 沙箱约束：不许以下划线开头的变量/属性名、不许 import/getattr/lambda、AST 禁 -=；
# 可用 frappe.get_doc / get_all / new_doc / db.set_value / db.commit / utils.flt。
# 返回值走 frappe.response["data"]。用完即删。
_MOVE_LIST = "[" + ", ".join(f'"{t}"' for t in MOVE_TNS) + "]"
_MOVE_QTY_MAP = "{" + ", ".join(f'"{t}": {q}' for t, q in MOVE_TNS.items()) + "}"

_SCRIPT_TRANSFER = f'''# 把改挂的菲号对应的皮壳，从「{WH_FG_STAGE}」调拨到「{WH_HALF}」
TNS = {_MOVE_LIST}
QTYS = {_MOVE_QTY_MAP}
ITEM = "{ITEM_SHELL}"
SRC = "{WH_FG_STAGE}"
DST = "{WH_HALF}"
se = frappe.new_doc("Stock Entry")
se.purpose = "Material Transfer"
se.stock_entry_type = "Material Transfer"
se.company = "FZH"
se.from_warehouse = SRC
se.to_warehouse = DST
for tn in TNS:
    row = se.append("items", {{}})
    row.item_code = ITEM
    row.qty = QTYS[tn]
    row.s_warehouse = SRC
    row.t_warehouse = DST
    row.stock_tracking_number = tn
se.insert()
se.submit()
frappe.response["data"] = {{"stock_entry": se.name, "rows": len(se.items)}}
'''


def repoint_script(tns: list[str], wo_target: str, wo_source: str, item_shell: str) -> str:
    """把 52 件身上挂的**五层**记录一起改挂到目标工单：
       ① 菲号归属 ② 完工/耗用凭证 ③ 报工(Job Card) ④ 开料分配行 ⑤ 菲号 movements 子表。
    全部走 db.set_value（只改归属，不动库存流水、不动报工工时与员工）。"""
    return f'''# 改挂：菲号 + 完工/耗用凭证 + 报工 + 开料分配行（只改归属）
TNS = {json.dumps(tns, ensure_ascii=False)}
WOT = "{wo_target}"
ITEM = "{item_shell}"

# ① 菲号归属
for tn in TNS:
    frappe.db.set_value("Tracking Number", tn, "work_order", WOT)
    frappe.db.set_value("Tracking Number", tn, "finished_product_work_order", WOT)
    frappe.db.set_value("Tracking Number", tn, "so_materials", ITEM)

# ② 完工入库 + 加工耗用 凭证
se_names = frappe.get_all("Stock Entry",
    filters={{"tracking_number": ["in", TNS],
              "purpose": ["in", ["Manufacture", "Material Consumption for Manufacture"]]}},
    pluck="name")
for name in se_names:
    frappe.db.set_value("Stock Entry", name, "work_order", WOT)

# ③ 报工（保留真实员工与工时，只改工单归属）
jc_names = frappe.get_all("Job Card",
    filters={{"tracking_number": ["in", TNS], "docstatus": 1}}, pluck="name")
for name in jc_names:
    frappe.db.set_value("Job Card", name, "work_order", WOT)

# ④ 开料分配行（open_material_qty 的源头）
alloc_names = frappe.get_all("Woker Order Allocation",
    filters={{"tracking_number": ["in", TNS]}}, pluck="name")
for name in alloc_names:
    frappe.db.set_value("Woker Order Allocation", name, "work_order", WOT)

frappe.db.commit()
frappe.response["data"] = {{"tracking_numbers": TNS, "stock_entries": se_names,
                           "job_cards": jc_names, "allocations": alloc_names}}
'''


def fixqty_script(wo_target: str, target_qty: float, wo_source: str, source_qty: float,
                  target_status: str = "Completed") -> str:
    return f'''# 修正两个工单的已产/已开料数量与状态（根因字段）
WO1 = "{wo_target}"
WO2 = "{wo_source}"
frappe.db.set_value("Work Order", WO1, "produced_qty", {target_qty})
frappe.db.set_value("Work Order", WO1, "open_material_qty", {target_qty})
frappe.db.set_value("Work Order", WO1, "status", "{target_status}")
frappe.db.set_value("Work Order", WO2, "produced_qty", {source_qty})
frappe.db.set_value("Work Order", WO2, "open_material_qty", {source_qty})
frappe.db.commit()
frappe.response["data"] = {{"ok": 1}}
'''

# redo：在目标工单下按同样的菲号重做 Manufacture，产出进 dst。
# 单价从**原（已取消）凭证**抄，保证估值与原始完全一致，避免手搓凭证落成 0 成本。
def redo_script(mapping: list[tuple[str, float, str]], wo_target: str, item_shell: str,
                dst: str) -> str:
    """mapping: [(tracking_number, qty, 原凭证名), ...]"""
    plan = json.dumps([list(x) for x in mapping], ensure_ascii=False)
    return f'''# 在 {wo_target} 下按菲号重做 Manufacture（单价抄原凭证）
PLAN = {plan}
WOT = "{wo_target}"
ITEM = "{item_shell}"
DST = "{dst}"
wo = frappe.get_doc("Work Order", WOT)
out = []
for pair in PLAN:
    tn = pair[0]
    qty = pair[1]
    src = frappe.get_doc("Stock Entry", pair[2])
    rate = src.items[0].basic_rate
    se = frappe.new_doc("Stock Entry")
    se.purpose = "Manufacture"
    se.stock_entry_type = "Manufacture"
    se.company = wo.company
    se.work_order = wo.name
    # 必须 from_bom=1：erpnext stock_entry.py:229 `if not self.from_bom: self.fg_completed_qty = 0.0`
    # （生产上那批凭证也都是 from_bom=1 / bom_no 空）
    se.from_bom = 1
    se.use_multi_level_bom = 1
    se.fg_completed_qty = qty
    se.tracking_number = tn
    row = se.append("items", {{}})
    row.item_code = ITEM
    row.qty = qty
    row.t_warehouse = DST
    row.is_finished_item = 1
    row.stock_tracking_number = tn
    row.basic_rate = rate
    row.valuation_rate = rate
    # 不加这行：erpnext set_basic_rate 会按「工单历史 outgoing 值」重算成品单价（无消耗行时算成 0）
    row.set_basic_rate_manually = 1
    se.insert()
    se.submit()
    out.append({{"name": se.name, "tn": tn, "qty": qty, "rate": rate}})
frappe.db.commit()
frappe.response["data"] = out
'''

# ── 超量 1 件的二次更正（2026-09-21 用户第二轮确认）────────────
# 那 1 件实物属于 02571：把它加到 g1 的菲号上（13→14），并从 03197 的 -004 减回（26→25）。
# 终态：02571 = 131（超计划 1）、03197 = 25（正好等于计划）。
SPLIT_UP_TN, SPLIT_UP_OLD, SPLIT_UP_NEW = "WO-26-03197-001", 13.0, 14.0
SPLIT_DN_TN, SPLIT_DN_OLD, SPLIT_DN_NEW = "WO-26-03197-004", 26.0, 25.0
# 要取消 + 重做的完工入库凭证：tn → (原凭证, 新数量, 收料仓, 工单)
SPLIT_MFG = {
    SPLIT_UP_TN: ("STE-26-15626", 14.0, "待包装半成品仓 - FZH", "WO-26-02571"),
    SPLIT_DN_TN: ("STE-26-15203", 25.0, "待包装成品仓 - FZH", "WO-26-03197"),
}
# 要取消 + 重做的加工耗用凭证：tn → (原凭证, 新件数, 新面料米数)
# 面料按同比例缩放（g1/g4 同属批次 BN-26-01207，该批面料总量不变）
SPLIT_CONS = {
    SPLIT_UP_TN: ("STE-26-14851", 14.0, 19.03),
    SPLIT_DN_TN: ("STE-26-14855", 25.0, 33.97),
}
# 开料工单：g1 13→14、g4 26→25，并按升序重算 orig / exceed；面料按比例缩放
SPLIT_ALLOC_FIX = {
    1: {"group_split_qty": 14.0, "wo_origion_fill_numb": 130.0, "is_or_exceed": 0,
        "batch": {"actual_split_wo_qty": 14.0, "actual_usage": 19.03, "real_usage": 24.92},
        "fg_qty": 14.0},
    2: {"wo_origion_fill_numb": 116.0, "is_or_exceed": 0},
    3: {"wo_origion_fill_numb": 90.0, "is_or_exceed": 0},
    5: {"wo_origion_fill_numb": 77.0, "is_or_exceed": 0},
    6: {"wo_origion_fill_numb": 38.0, "is_or_exceed": 1},
    4: {"group_split_qty": 25.0, "wo_origion_fill_numb": 25.0, "is_or_exceed": 0,
        "batch": {"actual_split_wo_qty": 25.0, "actual_usage": 33.97, "real_usage": 44.5},
        "fg_qty": 25.0},
}
SPLIT_STEPS = ("split-tn", "split-wo-qty", "split-fix1", "split-cons", "split-iwo", "split-op")

# 纠偏：`SPLIT_MFG` 里 tn -001 的凭证号一度写错（写成了 -003 的 STE-26-15626），
# 导致 -003 的完工被误取消、-001 多出一张。本步把两者都复原：
#   取消 -001 的旧凭证 STE-26-15628(13)（新的 14 张 STE-26-15629 已在）
#   为 -003 重建一张 13 的 Manufacture（单价抄被误取消的 STE-26-15626）
SPLIT_FIX1 = ("STE-26-15628", "WO-26-03197-003", "STE-26-15626", 13.0,
              "待包装半成品仓 - FZH", "WO-26-02571")


def split_fix1_script() -> str:
    old_cancel, tn_restore, src_rate, qty, dst, wo = SPLIT_FIX1
    return f'''# 纠偏：取消多出的一张，恢复被误取消的那张
ITEM = "{ITEM_SHELL}"
CANCEL_ME = "{old_cancel}"
TNR = "{tn_restore}"
SRC = "{src_rate}"
QTY = {qty}
DST = "{dst}"
WOT = "{wo}"
se = frappe.get_doc("Stock Entry", CANCEL_ME)
se.cancel()
frappe.db.commit()
rate = frappe.get_doc("Stock Entry", SRC).items[0].basic_rate
wo = frappe.get_doc("Work Order", WOT)
new = frappe.new_doc("Stock Entry")
new.purpose = "Manufacture"
new.stock_entry_type = "Manufacture"
new.company = wo.company
new.work_order = wo.name
new.from_bom = 1
new.use_multi_level_bom = 1
new.fg_completed_qty = QTY
new.tracking_number = TNR
row = new.append("items", {{}})
row.item_code = ITEM
row.qty = QTY
row.t_warehouse = DST
row.is_finished_item = 1
row.stock_tracking_number = TNR
row.basic_rate = rate
row.valuation_rate = rate
row.set_basic_rate_manually = 1
new.insert()
new.submit()
frappe.db.commit()
frappe.response["data"] = {{"cancelled": CANCEL_ME, "restored_for": TNR,
                           "new": new.name, "qty": QTY, "rate": rate}}
'''


def split_cons_script() -> str:
    """加工耗用 ±1。取消「加工耗用」时 ERPNext 会校验工单状态
    （`stock_entry.validate_work_order_status`，仅对 Material Consumption for Manufacture 生效），
    所以先把两个工单状态临时降为 In Process，做完再置回 Completed。"""
    cons = "[" + ", ".join(
        '["%s", "%s", %s, %s, "%s"]' % (
            tn, se, q, m, WO_TARGET if tn != SPLIT_DN_TN else WO_SOURCE)
        for tn, (se, q, m) in SPLIT_CONS.items()) + "]"
    return f'''# 加工耗用 ±1（件数 + 面料按比例）；工单状态临时降到 In Process 以放行取消
FABRIC = "HLR1020-BLACK-150-280"
WIP = "在制品仓 - FZH"
CONS = {cons}
WOS = ["{WO_TARGET}", "{WO_SOURCE}"]
SS = "Stock Settings"
for w in WOS:
    frappe.db.set_value("Work Order", w, "status", "In Process")
# 布料是批次管理物料：出库需自动生成 Serial and Batch Bundle（用完即关回）
frappe.db.set_value(SS, SS, "auto_create_serial_and_batch_bundle_for_outward", 1)
frappe.db.commit()
out = []
# 先全部取消（否则同批次的可用量不够新单使用），再统一新建
stash = []
for pair in CONS:
    old = frappe.get_doc("Stock Entry", pair[1])
    src = old.items[0]
    stash.append({{"tn": pair[0], "pieces": pair[2], "fabric": pair[3], "wo": pair[4],
                   "src": src, "bom": old.bom_no, "mlb": old.use_multi_level_bom,
                   "qty_old": src.qty}})
    if old.docstatus == 1:
        old.cancel()
        frappe.db.commit()
for item in stash:
    src = item["src"]
    new = frappe.new_doc("Stock Entry")
    new.purpose = "Material Consumption for Manufacture"
    new.stock_entry_type = "Material Consumption for Manufacture"
    new.company = "FZH"
    new.work_order = item["wo"]
    # 必须 from_bom=1，否则 stock_entry.py:229 把 fg_completed_qty 清成 0
    new.from_bom = 1
    new.bom_no = item["bom"]
    new.use_multi_level_bom = item["mlb"]
    new.fg_completed_qty = item["pieces"]
    new.tracking_number = item["tn"]
    new.from_warehouse = src.s_warehouse
    row = new.append("items", {{}})
    row.item_code = src.item_code
    row.qty = item["fabric"]
    row.uom = src.uom
    row.stock_uom = src.stock_uom
    row.s_warehouse = src.s_warehouse
    row.batch_no = src.batch_no
    row.use_serial_batch_fields = 1
    row.whole_batch_transfer = 0
    row.basic_rate = src.basic_rate
    row.valuation_rate = src.valuation_rate
    row.cost_center = src.cost_center
    row.expense_account = src.expense_account
    row.custom_s_warehouse = src.custom_s_warehouse
    row.stock_tracking_number = item["tn"]
    new.insert()
    new.submit()
    frappe.db.commit()
    out.append({{"new": new.name, "tn": item["tn"], "pieces": item["pieces"],
                 "fabric_old": item["qty_old"], "fabric_new": item["fabric"]}})
for w in WOS:
    frappe.db.set_value("Work Order", w, "status", "Completed")
frappe.db.set_value(SS, SS, "auto_create_serial_and_batch_bundle_for_outward", 0)
frappe.db.commit()
frappe.response["data"] = {{"entries": out,
                           "gate_restored": frappe.db.get_single_value(SS, "auto_create_serial_and_batch_bundle_for_outward")}}
'''


def split_tn_script() -> str:
    return f'''# 菲号数量 ±1 + 对应报工行数量 ±1（员工/工时不动，只改数量）
PAIRS = [["{SPLIT_UP_TN}", {SPLIT_UP_OLD}, {SPLIT_UP_NEW}],
         ["{SPLIT_DN_TN}", {SPLIT_DN_OLD}, {SPLIT_DN_NEW}]]
out = []
for pair in PAIRS:
    tn = pair[0]
    frappe.db.set_value("Tracking Number", tn, "qty", pair[2])
    n = 0
    for name in frappe.get_all("Job Card", filters={{"tracking_number": tn, "docstatus": 1}}, pluck="name"):
        frappe.db.set_value("Job Card", name, "for_quantity", pair[2])
        frappe.db.set_value("Job Card", name, "total_completed_qty", pair[2])
        n = n + 1
    out.append({{"tracking_number": tn, "qty": pair[2], "job_cards": n}})
frappe.db.commit()
frappe.response["data"] = out
'''


def split_se_script() -> str:
    cons = "[" + ", ".join(
        '["%s", "%s", %s, %s]' % (tn, se, q, m) for tn, (se, q, m) in SPLIT_CONS.items()) + "]"
    mfg = "[" + ", ".join(
        '["%s", "%s", %s, "%s", "%s"]' % (tn, se, q, dst, wo)
        for tn, (se, q, dst, wo) in SPLIT_MFG.items()) + "]"
    return f'''# 取消并重做 完工入库 + 加工耗用（数量 ±1；完工单价抄原凭证；面料按比例缩放）
ITEM = "{ITEM_SHELL}"
FABRIC = "HLR1020-BLACK-150-280"
WIP = "在制品仓 - FZH"
MFG = {mfg}
CONS = {cons}
out = {{"manufacture": [], "consumption": []}}
for pair in MFG:
    tn = pair[0]
    old = frappe.get_doc("Stock Entry", pair[1])
    rate = old.items[0].basic_rate
    frappe.db.set_value("Stock Entry", pair[1], "work_order", pair[4])
    frappe.db.commit()
    se = frappe.get_doc("Stock Entry", pair[1])
    se.cancel()
    frappe.db.commit()
    wo = frappe.get_doc("Work Order", pair[4])
    new = frappe.new_doc("Stock Entry")
    new.purpose = "Manufacture"
    new.stock_entry_type = "Manufacture"
    new.company = wo.company
    new.work_order = wo.name
    new.from_bom = 1
    new.use_multi_level_bom = 1
    new.fg_completed_qty = pair[2]
    new.tracking_number = tn
    row = new.append("items", {{}})
    row.item_code = ITEM
    row.qty = pair[2]
    row.t_warehouse = pair[3]
    row.is_finished_item = 1
    row.stock_tracking_number = tn
    row.basic_rate = rate
    row.valuation_rate = rate
    row.set_basic_rate_manually = 1
    new.insert()
    new.submit()
    out["manufacture"].append({{"cancelled": pair[1], "new": new.name, "tn": tn,
                                "qty": pair[2], "rate": rate}})
    frappe.db.commit()
for pair in CONS:
    tn = pair[0]
    old = frappe.get_doc("Stock Entry", pair[1])
    qty_old = old.items[0].qty
    frappe.db.set_value("Stock Entry", pair[1], "work_order",
                        "{WO_TARGET}" if tn != "{SPLIT_DN_TN}" else "{WO_SOURCE}")
    frappe.db.commit()
    se = frappe.get_doc("Stock Entry", pair[1])
    se.cancel()
    frappe.db.commit()
    new = frappe.new_doc("Stock Entry")
    new.purpose = "Material Consumption for Manufacture"
    new.stock_entry_type = "Material Consumption for Manufacture"
    new.company = se.company
    new.work_order = se.work_order
    new.fg_completed_qty = pair[2]
    new.tracking_number = tn
    new.from_warehouse = WIP
    row = new.append("items", {{}})
    row.item_code = FABRIC
    row.qty = pair[3]
    row.s_warehouse = WIP
    row.t_warehouse = None
    row.stock_tracking_number = tn
    new.insert()
    new.submit()
    out["consumption"].append({{"cancelled": pair[1], "new": new.name, "tn": tn,
                                "pieces": pair[2], "fabric_old": qty_old, "fabric_new": pair[3]}})
    frappe.db.commit()
frappe.response["data"] = out
'''


def split_iwo_script(parent: str, fixes: dict) -> str:
    return f'''# 开料工单 {parent}：g1/g4 数量 ±1 + 全行 orig/exceed 重算 + 兄弟子表同步
PARENT = "{parent}"
FIXES = {json.dumps({str(k): v for k, v in fixes.items()}, ensure_ascii=False)}
iwo = frappe.get_doc("Initial Work Order", PARENT)
alloced = []
for row in iwo.woker_order_allocations:
    fix = FIXES.get(str(int(row.group_number)))
    if not fix:
        continue
    if "group_split_qty" in fix:
        frappe.db.set_value("Woker Order Allocation", row.name, "group_split_qty", fix["group_split_qty"])
    frappe.db.set_value("Woker Order Allocation", row.name,
                        {{"wo_origion_fill_numb": fix["wo_origion_fill_numb"],
                          "is_or_exceed": fix["is_or_exceed"]}})
    alloced.append({{"group": row.group_number, "tn": row.tracking_number, "qty": fix.get("group_split_qty"),
                     "orig": fix["wo_origion_fill_numb"], "exceed": fix["is_or_exceed"]}})
bq = 0
for row in iwo.work_order_batch_qtys or []:
    fix = FIXES.get(str(int(row.group_number)))
    if fix and "batch" in fix:
        frappe.db.set_value(row.doctype, row.name, fix["batch"])
        bq = bq + 1
fg = 0
for row in iwo.fg_qty_key_material_bns or []:
    fix = FIXES.get(str(int(row.group_number)))
    if fix and "fg_qty" in fix:
        frappe.db.set_value(row.doctype, row.name, "fg_qty", fix["fg_qty"])
        fg = fg + 1
frappe.db.commit()
frappe.response["data"] = {{"alloc": alloced, "batch_qtys": bq, "fg_qty_bns": fg}}
'''
_SCRIPT_FIXQTY = fixqty_script(WO_TARGET, FINAL_PRODUCED[WO_TARGET],
                               WO_SOURCE, FINAL_PRODUCED[WO_SOURCE])
_SCRIPT_REPOINT = repoint_script(list(MOVE_TNS), WO_TARGET, WO_SOURCE, ITEM_SHELL)

# 源工单的工序行名 → 目标工单同工序行名（按 `operation` 工序名对应）。
# 改挂后 Job Card.operation_id 仍指向源工单的工序行，必须一起换，
# 否则 `job_card.update_work_order()` 在目标工单上找不到工序行、completed_qty 永远不更新。
OP_ID_MAP = {
    "rf9ba32gq0": "opk4qn9vk5",   # 裁剪
    "gblco88t18": "00t6f8fit9",   # 皮壳整件
    "d87sikm5vc": "4h7senbti3",   # 锁扣眼
    "boaggdr4f9": "44qnlpu05d",   # 拷边
    "r0n768b43m": "r22jbs7h84",   # 翻面
    "ttfp912suq": "jadglhjlkc",   # 吸毛
    "77n2gmua96": "2puucd25re",   # 质检
}

# 开料工单 753 里 group1/2/3 的修正值（按源码 alloc 算法：组按 group_number 升序、
# wo_origion_fill_numb = 分配前工单剩余需求、超出并入该行并置 is_or_exceed=1）
ALLOC_FIX = {
    1: {"wo_origion_fill_numb": 130.0, "is_or_exceed": 0},
    2: {"wo_origion_fill_numb": 117.0, "is_or_exceed": 0},
    3: {"wo_origion_fill_numb": 91.0, "is_or_exceed": 0},
    5: {"wo_origion_fill_numb": 78.0, "is_or_exceed": 0},
    6: {"wo_origion_fill_numb": 39.0, "is_or_exceed": 0},
    4: {"wo_origion_fill_numb": 25.0, "is_or_exceed": 1},
}


def jc_opid_script(mapping: dict[str, str]) -> str:
    """把改挂过来的报工行的 operation_id 换到目标工单的同名工序行。"""
    return f'''# 报工行 operation_id → 目标工单同工序行
MAP = {json.dumps(mapping, ensure_ascii=False)}
TNS = {_MOVE_LIST}
fixed = []
for tn in TNS:
    for name in frappe.get_all("Job Card",
                               filters={{"tracking_number": tn, "docstatus": 1}}, pluck="name"):
        doc = frappe.get_doc("Job Card", name)
        new_id = MAP.get(doc.operation_id)
        if new_id and new_id != doc.operation_id:
            frappe.db.set_value("Job Card", name, "operation_id", new_id)
            fixed.append(name)
frappe.db.commit()
frappe.response["data"] = {{"fixed": len(fixed), "job_cards": fixed}}
'''


def recalc_op_script(wo_target: str, item_shell: str) -> str:
    """用系统自身的 job_card.update_work_order() 重算两个工单的工序 completed_qty。"""
    return f'''# 重算工序 completed_qty（走 job_card.update_work_order，聚合口径 (work_order, operation_id)）
WOT = "{wo_target}"
ITEM = "{item_shell}"
out = []
for wo_name in [WOT, frappe.db.get_value("Work Order", {{"production_item": ITEM, "name": ["!=", WOT]}}, "name")]:
    if not wo_name:
        continue
    wo = frappe.get_doc("Work Order", wo_name)
    done = []
    for op in wo.operations:
        jcs = frappe.get_all("Job Card",
                             filters={{"work_order": wo_name, "operation_id": op.name, "docstatus": 1}},
                             pluck="name", limit=1)
        if not jcs:
            continue
        jc = frappe.get_doc("Job Card", jcs[0])
        jc.run_method("update_work_order")
        done.append({{"operation": op.operation, "job_card": jcs[0]}})
    frappe.db.commit()
    wo = frappe.get_doc("Work Order", wo_name)
    out.append({{"work_order": wo_name,
                 "operations": [{{"operation": o.operation, "completed_qty": o.completed_qty,
                                  "status": o.status}} for o in wo.operations],
                 "updated_via": done}})
frappe.response["data"] = out
'''


def fix_initial_wo_script(parent: str, fixes: dict, to_target_groups: list[int],
                          wo_target: str) -> str:
    """开料工单：修正分配行的 wo_origion_fill_numb / is_or_exceed，
    并把兄弟子表的 group1/2/3 归属一并改到目标工单。
    沙箱禁「下标增强赋值」，所以计数器用普通变量、结果字典显式构造。"""
    return f'''# 开料工单 {parent}：分配行数量勾稽 + 兄弟子表归属
PARENT = "{parent}"
WOT = "{wo_target}"
FIXES = {json.dumps({str(k): v for k, v in fixes.items()}, ensure_ascii=False)}
GROUPS = {json.dumps(to_target_groups)}
iwo = frappe.get_doc("Initial Work Order", PARENT)
fixed_alloc = []
bq = 0
bns = 0
for row in iwo.woker_order_allocations:
    fix = FIXES.get(str(int(row.group_number)))
    if fix:
        frappe.db.set_value("Woker Order Allocation", row.name, fix)
        fixed_alloc.append({{"group": row.group_number, "tracking_number": row.tracking_number,
                             "wo_origion_fill_numb": fix.get("wo_origion_fill_numb"),
                             "is_or_exceed": fix.get("is_or_exceed")}})
for row in iwo.work_order_batch_qtys or []:
    if int(row.group_number) in GROUPS and row.work_order != WOT:
        frappe.db.set_value(row.doctype, row.name, "work_order", WOT)
        bq = bq + 1
for row in iwo.fg_qty_key_material_bns or []:
    if int(row.group_number) in GROUPS and row.work_order != WOT:
        frappe.db.set_value(row.doctype, row.name, "work_order", WOT)
        bns = bns + 1
frappe.db.commit()
frappe.response["data"] = {{"alloc": fixed_alloc, "batch_qtys": bq, "fg_qty_bns": bns}}
'''

WO_FIELDS = [
    "name", "status", "docstatus", "qty", "produced_qty", "open_material_qty",
    "production_item", "bom_no", "fg_warehouse", "wip_warehouse", "source_warehouse",
    "sales_order", "sales_order_item", "production_plan", "production_plan_item",
    "production_plan_sub_assembly_item", "company", "use_multi_level_bom",
    "transfer_material_against", "material_transferred_for_manufacturing",
    "skip_transfer", "from_wip_warehouse",
]

TN_FIELDS = [
    "name", "work_order", "finished_product_work_order", "item_code", "qty",
    "so_materials", "creation", "modified", "docstatus",
]

SE_FIELDS = [
    "name", "docstatus", "purpose", "work_order", "tracking_number",
    "delivery_plan", "fg_completed_qty", "posting_date", "creation",
    "total_amount", "from_warehouse", "to_warehouse", "stock_entry_type",
]


# ── 基础设施 ────────────────────────────────────────────────
class _NoExpect(HTTPAdapter):
    """nginx 对长 URL + 某些头返回 417；去掉 Expect 头即可。"""

    def add_headers(self, request, **kwargs):
        request.headers.pop("Expect", None)


def load_env() -> dict[str, str]:
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
    return vals


class ApiClient:
    """通用 Frappe 客户端；base/key_env/sec_env 决定打生产还是测试。"""

    def __init__(self, base: str = PROD, key_env: str = "PROD_ERP_API_KEY",
                 sec_env: str = "PROD_ERP_API_SECRET") -> None:
        env = load_env()
        key, sec = env.get(key_env, ""), env.get(sec_env, "")
        if not key or not sec:
            raise SystemExit(f"✗ 缺少 {key_env} / {sec_env}（EN_API/.env）")
        self.base = base
        self.s = requests.Session()
        self.s.mount("https://", _NoExpect())
        self.s.headers["Authorization"] = f"token {key}:{sec}"

    def _req(self, method, path, **kw):
        kw.setdefault("timeout", (30, 300))
        return self.s.request(method, f"{self.base}{path}", **kw)

    def get_list(self, dt, filters=None, fields=None, limit=0):
        pr: dict[str, str] = {"limit_page_length": str(limit)}
        if filters is not None:
            pr["filters"] = json.dumps(filters)
        if fields is not None:
            pr["fields"] = json.dumps(fields)
        r = self._req("GET", f"/api/resource/{quote(dt, safe='')}", params=pr)
        r.raise_for_status()
        return r.json()["data"]

    def get_all(self, dt, filters=None, fields=None, limit=0):
        """容错版：失败返回 [] 并提示（子表 list 常 403）。"""
        try:
            return self.get_list(dt, filters, fields, limit)
        except Exception as e:  # noqa: BLE001
            msg = ""
            try:
                msg = json.loads(e.response.text).get("exception", "")
            except Exception:  # noqa: BLE001
                pass
            print(f"   ! 列 {dt} 失败：{type(e).__name__} {msg or e}")
            return []

    def get_doc(self, dt, name):
        r = self._req("GET", f"/api/resource/{quote(dt, safe='')}/{quote(name, safe='')}")
        r.raise_for_status()
        return r.json()["data"]

    def try_doc(self, dt, name):
        try:
            return self.get_doc(dt, name)
        except Exception as e:  # noqa: BLE001
            print(f"   ! 取 {dt}/{name} 失败：{e}")
            return None

    def sle_rows(self, tracking=None, item_code=None, warehouse=None):
        flt = [["is_cancelled", "=", 0]]
        if tracking:
            flt.append(["tracking_number", "=", tracking])
        if item_code:
            flt.append(["item_code", "=", item_code])
        if warehouse:
            flt.append(["warehouse", "=", warehouse])
        return self.get_all(
            "Stock Ledger Entry", flt,
            ["item_code", "warehouse", "actual_qty", "voucher_type", "voucher_no",
             "posting_date", "tracking_number"], 0)

    # ── 写操作（仅 --apply 时调用）──
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

    def cancel_doc(self, dt, name):
        return self._write("POST", "/api/method/frappe.client.cancel",
                           {"doctype": dt, "name": name})

    def submit_doc(self, dt, name):
        # frappe.client.submit(doc) 只收一个 doc 参数，且必须是**完整单据**：
        # 只传 {"doctype","name"} 会被当成新文档、字段为空（BOM 会报「请先选择一个公司」）。
        return self._write("POST", "/api/method/frappe.client.submit",
                           {"doc": self.get_doc(dt, name)})

    def set_item_flag(self, item_code, value):
        return self._write("POST", "/api/method/frappe.client.set_value",
                           {"doctype": "Item", "name": item_code,
                            "fieldname": "allow_negative_stock", "value": value})

    def get_item_flag(self, item_code):
        return self.get_doc("Item", item_code).get("allow_negative_stock")

    def insert_doc(self, dt, doc):
        return self._write("POST", f"/api/resource/{quote(dt, safe='')}", doc)

    def delete_doc(self, dt, name):
        return self._write("DELETE", f"/api/resource/{quote(dt, safe='')}/{quote(name, safe='')}")

    def call_method(self, method, payload=None):
        return self._write("POST", f"/api/method/{method}", payload or {})


def dump(name: str, payload) -> Path:
    OUT_DIR.mkdir(exist_ok=True)
    ts = datetime.now().strftime("%Y%m%d_%H%M%S")
    p = OUT_DIR / f"{name}_{ts}.json"
    p.write_text(json.dumps(payload, ensure_ascii=False, indent=2), encoding="utf-8")
    print(f"   → 已落盘 {p}")
    return p


def flt(v) -> float:
    return float(v or 0)


def hr(title: str) -> None:
    print(f"\n{'─' * 70}\n{title}\n{'─' * 70}")


# ── probe ───────────────────────────────────────────────────
def cmd_probe(c: ApiClient) -> None:
    print(f"环境: {PROD}（只读）")
    out: dict = {"_generated_at": datetime.now().isoformat()}

    # 1) 工单
    hr("[1] 工单")
    out["wos"] = {}
    for wo_name in (WO_TARGET, WO_SOURCE, WO_FG_SOURCE):
        wo = c.try_doc("Work Order", wo_name)
        if not wo:
            continue
        out["wos"][wo_name] = {k: wo.get(k) for k in WO_FIELDS}
        print(f"   {wo_name}: 计划={wo.get('qty')} 已产={wo.get('produced_qty')} "
              f"已开料={wo.get('open_material_qty')} 状态={wo.get('status')}")
        print(f"       物料={wo.get('production_item')} BOM={wo.get('bom_no')} "
              f"fg_wh={wo.get('fg_warehouse')}")
        print(f"       SO={wo.get('sales_order')} PP={wo.get('production_plan')} "
              f"pp_item={wo.get('production_plan_item')} "
              f"sub={wo.get('production_plan_sub_assembly_item')}")

    # 2) 菲号
    hr("[2] 菲号（Tracking Number）")
    tns: dict[str, dict] = {}
    for field in ("work_order", "finished_product_work_order"):
        for wo_name in (WO_TARGET, WO_SOURCE):
            for r in c.get_all("Tracking Number", [[field, "=", wo_name]], TN_FIELDS, 0):
                tns[r["name"]] = r
    out["tracking_numbers"] = sorted(tns.values(), key=lambda r: r["name"])
    tn_names = sorted(tns)
    tot_src = sum(float(t["qty"] or 0) for t in out["tracking_numbers"]
                  if t.get("work_order") == WO_SOURCE)
    tot_tgt = sum(float(t["qty"] or 0) for t in out["tracking_numbers"]
                  if t.get("work_order") == WO_TARGET)
    print(f"   共 {len(tns)} 个菲号；{WO_TARGET} 名下合计 {tot_tgt}，{WO_SOURCE} 名下合计 {tot_src}")
    for r in out["tracking_numbers"]:
        print(f"   {r['name']:<20} wo={r.get('work_order')} fp_wo={r.get('finished_product_work_order')} "
              f"item={r.get('item_code')} qty={r.get('qty')} so_mat={r.get('so_materials')}")

    # 3) 凭证
    hr("[3] Stock Entry")
    ses: dict[str, dict] = {}
    for flt in ([["work_order", "in", [WO_TARGET, WO_SOURCE]]],
                [["tracking_number", "in", tn_names]] if tn_names else None):
        if not flt:
            continue
        for r in c.get_all("Stock Entry", flt, SE_FIELDS, 0):
            ses[r["name"]] = r
    out["stock_entries"] = sorted(ses.values(), key=lambda r: r["name"])
    print(f"   共 {len(ses)} 张")
    for r in out["stock_entries"]:
        print(f"   {r['name']:<16} ds={r.get('docstatus')} {str(r.get('purpose') or r.get('stock_entry_type')):<38} "
              f"wo={r.get('work_order')} tn={r.get('tracking_number')} "
              f"qty={r.get('fg_completed_qty')} dp={r.get('delivery_plan')} {r.get('posting_date')}")

    # 4) SLE
    hr("[4] SLE（按菲号 × 物料 × 仓）")
    sle_rows = []
    for tn in tn_names:
        for r in c.sle_rows(tracking=tn):
            sle_rows.append(r)
    out["sle"] = sle_rows
    agg: dict[tuple, float] = {}
    for r in sle_rows:
        key = (r["tracking_number"], r["item_code"], r["warehouse"])
        agg[key] = agg.get(key, 0.0) + float(r["actual_qty"] or 0)
    out["sle_agg"] = [{"tracking_number": k[0], "item_code": k[1], "warehouse": k[2], "qty": round(v, 4)}
                      for k, v in sorted(agg.items()) if abs(v) > 1e-9]
    for r in out["sle_agg"]:
        print(f"   {r['tracking_number']:<20} {r['item_code']:<28} {r['warehouse']:<24} {r['qty']}")

    # 5) 报工
    hr("[5] Job Card（扫码报工）")
    jcs = []
    for wo_name in (WO_TARGET, WO_SOURCE):
        jcs += c.get_all("Job Card", [["work_order", "=", wo_name]],
                         ["name", "operation", "status", "total_completed_qty", "docstatus",
                          "work_order", "for_quantity"], 0)
    out["job_cards"] = jcs
    by_wo: dict[str, float] = {}
    for r in jcs:
        by_wo[r["work_order"]] = by_wo.get(r["work_order"], 0.0) + float(r.get("total_completed_qty") or 0)
    print(f"   共 {len(jcs)} 张")
    for wo_name, tot in sorted(by_wo.items()):
        print(f"   {wo_name}: 报工总次数口径合计 {tot}（同工单多工序会重复计）")

    # 5b) 是否合成报工（一键完工）
    print("\n   工序时间段员工占用：")
    emp_used: dict[str, set] = {}
    for r in jcs:
        jc = c.try_doc("Job Card", r["name"])
        for tl in (jc or {}).get("time_logs") or []:
            emp_used.setdefault(tl.get("employee") or "<空>", set()).add(r["name"])
    for emp, names in sorted(emp_used.items()):
        tag = "  ← 虚拟员工（一键完工）" if emp == VIRTUAL_EMP else ""
        print(f"     {emp}: {len(names)} 张{tag}")
    out["job_card_employees"] = {k: sorted(v) for k, v in emp_used.items()}

    # 6) 出货计划引用
    hr("[6] 引用这些菲号的出货计划行")
    plans = c.get_all("Delivery Plan", [["creation", ">=", "2026-09-01"]], ["name"], 0)
    print(f"   2026-09-01 之后创建的出货计划 {len(plans)} 张，逐张检查…")
    dp_hits = []

    def scan(plan_name):
        try:
            d = c.get_doc("Delivery Plan", plan_name)
        except Exception:  # noqa: BLE001
            return []
        hits = []
        for row in d.get("item_qties") or []:
            if row.get("tracking_number") in tn_names:
                hits.append({"parent": plan_name, "plan_status": d.get("status"),
                             "plan_docstatus": d.get("docstatus"),
                             "tracking_number": row.get("tracking_number"),
                             "item_code": row.get("item_code"),
                             "planned_delivery_qty": row.get("planned_delivery_qty"),
                             "actual_qty": row.get("actual_qty"),
                             "original_qty": row.get("original_qty")})
        return hits

    with ThreadPoolExecutor(max_workers=4) as ex:
        for hits in ex.map(scan, [p["name"] for p in plans]):
            dp_hits += hits
    out["delivery_plan_rows"] = dp_hits
    if dp_hits:
        for r in dp_hits:
            print(f"   {r['parent']:<12}({r['plan_status']},ds={r['plan_docstatus']}) "
                  f"{r['tracking_number']:<20} item={r['item_code']} "
                  f"计划={r['planned_delivery_qty']} 实际={r['actual_qty']} 原始={r['original_qty']}")
    else:
        print("   （无）")

    # 7) 开料分配
    hr("[7] 开料工单分配（核实 open_material_qty）")
    for wo_name in (WO_TARGET, WO_SOURCE):
        rows = c.get_all("Initial Work Order Item", [["work_order", "=", wo_name]],
                         ["parent", "work_order", "group_split_qty"], 0)
        total = sum(float(r.get("group_split_qty") or 0) for r in rows)
        print(f"   {wo_name}: 子表分配记录 {len(rows)} 条，合计 {total}")
        out.setdefault("initial_wo_alloc", {})[wo_name] = {"rows": rows, "total": total}
    iwos = c.get_all("Initial Work Order", [],
                     ["name", "status", "docstatus", "creation"], 0)
    print(f"   Initial Work Order 主表可见 {len(iwos)} 张")

    # 8) 相关生产计划 / 销售订单
    hr("[8] 生产计划与销售订单口径")
    out["ctx"] = {}
    for pp_name in (PP_TARGET, PP_SOURCE):
        pp = c.try_doc("Production Plan", pp_name)
        if not pp:
            continue
        out["ctx"][pp_name] = {
            "status": pp.get("status"),
            "sales_orders": [r.get("sales_order") for r in (pp.get("sales_orders") or [])],
            "po_items": [{"name": r.get("name"), "item_code": r.get("item_code"),
                          "sales_order": r.get("sales_order"),
                          "sales_order_item": r.get("sales_order_item"),
                          "planned_qty": r.get("planned_qty"), "work_order": r.get("work_order")}
                         for r in (pp.get("po_items") or [])],
            "sub_assembly_items": [{"name": r.get("name"), "item_code": r.get("item_code"),
                                    "qty": r.get("qty"), "work_order": r.get("work_order"),
                                    "production_plan_item": r.get("production_plan_item"),
                                    "sales_order": r.get("sales_order")}
                                   for r in (pp.get("sub_assembly_items") or [])],
        }
        print(f"   {pp_name}: SO={out['ctx'][pp_name]['sales_orders']}")
        for r in out["ctx"][pp_name]["po_items"]:
            if r["item_code"] in (ITEM_SHELL, ITEM_FG):
                print(f"     po  {r['name']} {r['item_code']} so={r['sales_order']} 计划={r['planned_qty']}")
        for r in out["ctx"][pp_name]["sub_assembly_items"]:
            if r["item_code"] in (ITEM_SHELL, ITEM_FG) or r["name"] == "b1dron2hv8":
                print(f"     sub {r['name']} {r['item_code']} qty={r['qty']} pp_item={r['production_plan_item']}")

    for so_name in (SO_TARGET, SO_SOURCE):
        so = c.try_doc("Sales Order", so_name)
        if not so:
            continue
        lines = [{"name": r.get("name"), "item_code": r.get("item_code"), "qty": r.get("qty"),
                  "delivered_qty": r.get("delivered_qty")}
                 for r in (so.get("items") or [])
                 if r.get("item_code") in (ITEM_SHELL, ITEM_FG)]
        out["ctx"][so_name] = {"status": so.get("status"), "customer": so.get("customer"),
                               "lines": lines}
        print(f"   {so_name}: status={so.get('status')} customer={so.get('customer')}")
        for r in lines:
            print(f"     行 {r['name']} {r['item_code']} 数量={r['qty']} 已发={r['delivered_qty']}")

    dump("wo_02571_03197_probe", out)


def alloc_rows(c: ApiClient, tns: list[str]) -> list[dict]:
    """从开料工单父单据里读分配行（子表 REST list 会 403）。"""
    try:
        d = c.get_doc("Initial Work Order", INITIAL_WO)
    except Exception:  # noqa: BLE001
        return []
    out = []
    for r in d.get("woker_order_allocations") or []:
        if r.get("tracking_number") in tns:
            out.append({"name": r.get("name"), "parent": INITIAL_WO,
                        "work_order": r.get("work_order"),
                        "tracking_number": r.get("tracking_number"),
                        "group_split_qty": r.get("group_split_qty")})
    return out


def gather(c: ApiClient) -> dict:
    """实时抓一遍本次更正涉及的单据（只读）。"""
    g: dict = {"wos": {}, "tns": {}, "move_ses": [], "keep_ses": [],
               "job_cards": [], "cons_ses": [], "allocs": []}
    for wo_name in (WO_TARGET, WO_SOURCE):
        g["wos"][wo_name] = c.get_doc("Work Order", wo_name)

    for tn in list(MOVE_TNS) + list(KEEP_TNS):
        g["tns"][tn] = c.get_doc("Tracking Number", tn)

    move = list(MOVE_TNS)
    # Manufacture（完工入库）。redo 需要**已取消**的那 3 张作模板（取单价），
    # 而 repoint 已把这些凭证的 work_order 改到目标工单 → 只能按菲号查，不能按工单查。
    for r in c.get_list("Stock Entry",
                        [["purpose", "=", "Manufacture"],
                         ["tracking_number", "in", move + list(KEEP_TNS)]],
                        SE_FIELDS + ["from_bom", "bom_no", "company"], 0):
        full = c.get_doc("Stock Entry", r["name"])
        (g["keep_ses"] if r.get("tracking_number") in KEEP_TNS else g["move_ses"]).append(full)

    # 加工耗用（Material Consumption for Manufacture）
    for r in c.get_list("Stock Entry",
                        [["tracking_number", "in", move],
                         ["purpose", "=", "Material Consumption for Manufacture"]],
                        SE_FIELDS, 0):
        g["cons_ses"].append(r)

    # 报工（Job Card）
    for r in c.get_list("Job Card", [["tracking_number", "in", move]],
                        ["name", "work_order", "tracking_number", "operation",
                         "for_quantity", "total_completed_qty", "docstatus", "status"], 0):
        g["job_cards"].append(r)

    # 开料分配行（open_material_qty 的源头）
    g["allocs"] = alloc_rows(c, move)
    return g


def _se_line(se: dict) -> str:
    items = []
    for d in se.get("items") or []:
        if d.get("is_finished_item"):
            items.append(f"成品 {d.get('item_code')} {d.get('qty')} @{d.get('s_warehouse')}→{d.get('t_warehouse')}")
    return (f"{se['name']:<16} ds={se.get('docstatus')} wo={se.get('work_order')} "
            f"tn={se.get('tracking_number')} qty={se.get('fg_completed_qty')} | " + "; ".join(items))


def cmd_dry(c: ApiClient) -> None:
    print(f"环境: {PROD}（只读，不写任何数据）")
    g = gather(c)

    hr("[当前账面]")
    for name, wo in g["wos"].items():
        print(f"   {name}: 计划={wo.get('qty')} 已产={wo.get('produced_qty')} "
              f"已开料={wo.get('open_material_qty')} 状态={wo.get('status')} "
              f"fg_wh={wo.get('fg_warehouse')}")
    for tn, t in g["tns"].items():
        mark = "改挂" if tn in MOVE_TNS else "保留"
        print(f"   [{mark}] {tn:<20} wo={t.get('work_order')} fp_wo={t.get('finished_product_work_order')} "
              f"item={t.get('item_code')} qty={t.get('qty')} so_mat={t.get('so_materials')}")
    print("   待改挂的成品入库凭证：")
    for se in g["move_ses"]:
        print(f"     {_se_line(se)}")
    print("   保留在 03197 的成品入库凭证：")
    for se in g["keep_ses"]:
        print(f"     {_se_line(se)}")

    hr("[目标终态]")
    print(f"   {WO_TARGET}: 已产 {g['wos'][WO_TARGET].get('produced_qty')} → {FINAL_PRODUCED[WO_TARGET]}，"
          f"open_material_qty → {FINAL_OPEN_MATERIAL[WO_TARGET]}，皮壳应落在 {WH_HALF}")
    print(f"   {WO_SOURCE}: 已产 {g['wos'][WO_SOURCE].get('produced_qty')} → {FINAL_PRODUCED[WO_SOURCE]}，"
          f"open_material_qty → {FINAL_OPEN_MATERIAL[WO_SOURCE]}，皮壳留在 {WH_FG_STAGE}")
    print(f"   改挂菲号：{list(MOVE_TNS)}  →  {WO_TARGET}")

    hr("[方案 A] 调拨 + 改归属字段（改动小，不动已提交凭证的库存流水结构）")
    print(f"""   要点：3 张 Manufacture 凭证保持已提交不取消；库存靠一张带菲号的 Material Transfer
         把 {MOVE_QTY:.0f} 件皮壳从「{WH_FG_STAGE}」搬到「{WH_HALF}」；其余归属字段用 db.set_value 直接改。

   step transfer   Material Transfer: {MOVE_QTY:.0f} 件 {ITEM_SHELL}
                   {WH_FG_STAGE}  →  {WH_HALF}（按菲号分行，带 stock_tracking_number）
   step repoint-tn 3 个菲号：work_order/finished_product_work_order → {WO_TARGET}；
                   so_materials: {ITEM_FG} → {ITEM_SHELL}
   step repoint-se 3 张 Manufacture 凭证：work_order → {WO_TARGET}
   step fix-wo-qty {WO_TARGET} produced={FINAL_PRODUCED[WO_TARGET]} open_material={FINAL_OPEN_MATERIAL[WO_TARGET]}；
                   {WO_SOURCE} produced={FINAL_PRODUCED[WO_SOURCE]} open_material={FINAL_OPEN_MATERIAL[WO_SOURCE]}
                   ⚠️ 本步必须在 redo 之前

   优点：不取消任何已提交凭证；SLE 历史诚实（先入库到成品仓、再调拨到半成品仓）。
   代价：{WO_TARGET} 的 produced_qty={FINAL_PRODUCED[WO_TARGET]} 没有对应的本工单入库凭证
         （那 52 件是调拨进来的，不结转成本）→ 财务口径上工单产出与凭证不完全自洽。""")

    hr("[方案 B] 取消 + 重做 Manufacture（与 WO-26-02796 先例一致）")
    print(f"""   要点：取消挂在 {WO_SOURCE} 上的 3 张 Manufacture（{MOVE_QTY:.0f} 件），
         再在 {WO_TARGET} 下按同样的菲号重做 3 张 Manufacture，
         产出直接进 {WH_HALF}（= {WO_TARGET}.fg_warehouse），成本由 BOM 重算。

   step open-gate  按物料开 Item.allow_negative_stock=1（取消会被负库存拦）
   step cancel     取消 {', '.join(x['name'] for x in g['move_ses'])}
   step repoint-tn 3 个菲号改归属（同方案 A）
   step fix-wo-qty ⚠️ 必须在 redo **之前**：先把 {WO_TARGET}.open_material_qty 抬到
                   {FINAL_OPEN_MATERIAL[WO_TARGET]}，否则重做提交时 work_order_override
                   会用 completed_qty=78 判「91 > 78」并抛 StockOverProductionError
   step redo       按 {WO_TARGET} 重做 3 张 Manufacture（单价抄原凭证，产出进 {WH_HALF}）
   step close-gate 关回闸门

   优点：工单产出有自有凭证背书，成本由 BOM 重算，账证自洽。
   代价：动 3 张已提交凭证；需开负库存闸门。
   ✅ 已在测试环境 ensh.vilavi.cn 用同一套脚本代码演练通过（终态 130/26、单价一致）。""")

    hr("[不会做的事]")
    print("""   - 不动 WO-26-03047（SO-26-00106 的成品工单，仍为 Draft）
   - 不动任何 Delivery Note（本批从未生成）
   - 不改代码、不建分支、不动全局 Stock Settings""")

    hr("[将要写入的临时 Server Script]")
    for name, body in (("zz_wo02571_transfer", _SCRIPT_TRANSFER),
                       ("zz_wo02571_repoint", _SCRIPT_REPOINT),
                       ("zz_wo02571_fixqty", _SCRIPT_FIXQTY)):
        print(f"\n   名称: {name}")
        for ln in body.strip().splitlines():
            print(f"     {ln}")


def cmd_verify(c: ApiClient) -> None:
    print(f"环境: {PROD}（只读）\n")
    g = gather(c)
    checks: list[tuple[str, bool, str]] = []

    for wo_name, want in FINAL_PRODUCED.items():
        wo = g["wos"][wo_name]
        checks.append((f"{wo_name}.produced_qty == {want}",
                       abs(float(wo.get("produced_qty") or 0) - want) < 1e-6,
                       f"实际 {wo.get('produced_qty')}"))
    for wo_name, want in FINAL_OPEN_MATERIAL.items():
        wo = g["wos"][wo_name]
        checks.append((f"{wo_name}.open_material_qty == {want}",
                       abs(float(wo.get("open_material_qty") or 0) - want) < 1e-6,
                       f"实际 {wo.get('open_material_qty')}"))

    for tn in MOVE_TNS:
        t = g["tns"][tn]
        checks.append((f"菲号 {tn} 已改挂 {WO_TARGET}",
                       t.get("work_order") == WO_TARGET
                       and t.get("finished_product_work_order") == WO_TARGET
                       and t.get("so_materials") == ITEM_SHELL,
                       f"wo={t.get('work_order')} fp_wo={t.get('finished_product_work_order')} "
                       f"so_mat={t.get('so_materials')}"))

    # 报工层：本批 21 张 Job Card 全部改挂，且员工/工时记录未丢
    jcs = c.get_list("Job Card", [["tracking_number", "in", list(MOVE_TNS)]],
                     ["name", "work_order", "total_completed_qty", "docstatus"], 0)
    bad_jc = [x["name"] for x in jcs if x.get("work_order") != WO_TARGET]
    checks.append((f"本批 {len(jcs)} 张报工全部改挂 {WO_TARGET}", bool(jcs) and not bad_jc,
                   f"未改挂 {bad_jc}" if bad_jc else f"{len(jcs)} 张（docstatus=1 保留）"))
    checks.append(("报工记录仍为已提交（工时/员工未丢）",
                   all(int(x.get("docstatus") or 0) == 1 for x in jcs),
                   f"{[x['name'] for x in jcs if int(x.get('docstatus') or 0) != 1]}"))

    # 耗用层
    cons = c.get_list("Stock Entry",
                      [["tracking_number", "in", list(MOVE_TNS)],
                       ["purpose", "=", "Material Consumption for Manufacture"]], ["name"], 0)
    cons_bad = [x for x in c.get_list("Stock Entry",
                                      [["tracking_number", "in", list(MOVE_TNS)],
                                       ["purpose", "=", "Material Consumption for Manufacture"],
                                       ["work_order", "=", WO_SOURCE]], ["name"], 0)]
    checks.append((f"本批耗用凭证全部改挂 {WO_TARGET}",
                   bool(cons) and not cons_bad,
                   f"共 {len(cons)} 张，未改挂 {[x['name'] for x in cons_bad]}"))

    # 开料分配层
    alloc_bad = [r for r in alloc_rows(c, list(MOVE_TNS)) if r.get("work_order") == WO_SOURCE]
    alloc_all = alloc_rows(c, list(MOVE_TNS))
    checks.append((f"开料分配行全部改挂 {WO_TARGET}",
                   bool(alloc_all) and not alloc_bad,
                   f"共 {len(alloc_all)} 行，未改挂 {[x['name'] for x in alloc_bad]}"))

    # 皮壳落仓：每个改挂菲号在 待包装半成品仓 应有结余，在 待包装成品仓 应为 0
    for tn, qty in MOVE_TNS.items():
        half = c.sle_rows(tracking=tn, item_code=ITEM_SHELL, warehouse=WH_HALF)
        stage = c.sle_rows(tracking=tn, item_code=ITEM_SHELL, warehouse=WH_FG_STAGE)
        h = round(sum(float(r["actual_qty"] or 0) for r in half), 4)
        s = round(sum(float(r["actual_qty"] or 0) for r in stage), 4)
        checks.append((f"菲号 {tn} 皮壳在 {WH_HALF} == {qty}",
                       abs(h - qty) < 1e-6, f"实际 {h}"))
        checks.append((f"菲号 {tn} 皮壳在 {WH_FG_STAGE} == 0",
                       abs(s) < 1e-6, f"实际 {s}"))

    for tn, qty in KEEP_TNS.items():
        stage = c.sle_rows(tracking=tn, item_code=ITEM_SHELL, warehouse=WH_FG_STAGE)
        s = round(sum(float(r["actual_qty"] or 0) for r in stage), 4)
        checks.append((f"保留菲号 {tn} 皮壳仍在 {WH_FG_STAGE} == {qty}",
                       abs(s - qty) < 1e-6, f"实际 {s}"))

    # 目标工单名下应新增 3 张 Manufacture（重做的那批）
    tgt_ses = c.get_list("Stock Entry",
                         [["work_order", "=", WO_TARGET], ["purpose", "=", "Manufacture"],
                          ["docstatus", "=", 1]], ["name", "tracking_number", "fg_completed_qty"], 0)
    moved = [x for x in tgt_ses if x.get("tracking_number") in MOVE_TNS]
    checks.append((f"{WO_TARGET} 名下有 3 张重做的 Manufacture",
                   len(moved) == 3,
                   f"{[ (x['name'], x.get('tracking_number')) for x in moved ]}"))

    src_ses = c.get_list("Stock Entry",
                         [["work_order", "=", WO_SOURCE], ["purpose", "=", "Manufacture"],
                          ["docstatus", "=", 1]], ["name", "tracking_number"], 0)
    checks.append((f"{WO_SOURCE} 名下只剩 1 张 Manufacture（{next(iter(KEEP_TNS))}）",
                   len(src_ses) == 1 and src_ses[0].get("tracking_number") in KEEP_TNS,
                   f"{[(x['name'], x.get('tracking_number')) for x in src_ses]}"))

    # 工序层：7 道真实工序的 completed_qty 应与工单产出一致
    for wo_name, want in FINAL_PRODUCED.items():
        wo = g["wos"][wo_name]
        ops = [o for o in (wo.get("operations") or []) if flt(o.get("completed_qty"))]
        bad_op = [(o["operation"], o.get("completed_qty")) for o in ops
                  if abs(flt(o.get("completed_qty")) - want) > 1e-6]
        checks.append((f"{wo_name} 工序 completed_qty 全为 {want}",
                       bool(ops) and not bad_op,
                       f"{len(ops)} 道工序，异常 {bad_op}" if bad_op else f"{len(ops)} 道"))

    # 报工 operation_id 必须落在其 work_order 的工序行上（否则工序数量永远不会更新）
    bad_link = []
    for r in c.get_list("Job Card", [["tracking_number", "in", list(MOVE_TNS)], ["docstatus", "=", 1]],
                        ["name", "work_order", "operation_id"], 0):
        ids = {o.get("name") for o in (c.get_doc("Work Order", r["work_order"]).get("operations") or [])}
        if r.get("operation_id") not in ids:
            bad_link.append(r["name"])
    checks.append(("21 张报工的 operation_id 均落在本工单工序行上", not bad_link, f"异常 {bad_link}"))

    # 开料工单：分配行数量勾稽 + 兄弟子表归属
    try:
        iwo = c.get_doc("Initial Work Order", INITIAL_WO)
        alloc = iwo.get("woker_order_allocations") or []
        tgt_qty = sum(flt(r.get("group_split_qty")) for r in alloc if r.get("work_order") == WO_TARGET)
        tgt_exceed = [r.get("tracking_number") for r in alloc
                      if r.get("work_order") == WO_TARGET and int(r.get("is_or_exceed") or 0)]
        checks.append((f"开料工单分配行 {WO_TARGET} 合计 {FINAL_PRODUCED[WO_TARGET]}",
                       abs(tgt_qty - FINAL_PRODUCED[WO_TARGET]) < 1e-6, f"实际 {tgt_qty}"))
        checks.append((f"开料工单 {WO_TARGET} 有 1 行超量标记", len(tgt_exceed) == 1, f"超量 {tgt_exceed}"))
        src_exceed = [r.get("tracking_number") for r in alloc
                      if r.get("work_order") == WO_SOURCE and int(r.get("is_or_exceed") or 0)]
        checks.append((f"开料工单 {WO_SOURCE} 无超量行", not src_exceed, f"超量 {src_exceed}"))
        for ct in ("work_order_batch_qtys", "fg_qty_key_material_bns"):
            bad = [int(r.get("group_number")) for r in (iwo.get(ct) or [])
                   if r.get("work_order") != WO_TARGET and r.get("work_order") == WO_SOURCE
                   and int(r.get("group_number") or 0) in (1, 2, 3)]
            checks.append((f"开料工单 [{ct}] group1-3 已归属 {WO_TARGET}", not bad, f"未改 {bad}"))
    except Exception as e:  # noqa: BLE001
        checks.append(("开料工单校验", False, f"读取失败 {e}"))
    total = 0.0
    for tn in ALL_TNS:
        for wh in (WH_HALF, WH_FG_STAGE):
            total += sum(float(r["actual_qty"] or 0)
                         for r in c.sle_rows(tracking=tn, item_code=ITEM_SHELL, warehouse=wh))
    checks.append(("本批皮壳总量仍为 156", abs(round(total, 4) - 156.0) < 1e-6, f"实际 {round(total, 4)}"))

    ss = c.get_all("Server Script", [["name", "like", "zz_wo02571%"]], ["name"], 0)
    checks.append(("临时 Server Script 已清理", not ss, f"残留 {[x['name'] for x in ss]}"))

    print("[断言]")
    for name, ok, detail in checks:
        print(f"   {'✓' if ok else '✗'} {name}（{detail}）")
    bad = [n for n, ok, _ in checks if not ok]
    print("\n" + ("✓ 全部通过，更正完成" if not bad else f"✗ 未通过 {len(bad)} 项：{bad}"))
    if bad:
        raise SystemExit(1)


STEPS = ("preflight", "open-gate", "cancel", "repoint", "fix-wo-qty", "redo",
         "close-gate", "fix-jc-op", "recalc-op", "fix-initial-wo", "cleanup") + SPLIT_STEPS
SCRIPT_NAMES = {"repoint": "zz_wo02571_repoint",
                "redo": "zz_wo02571_redo",
                "fix-wo-qty": "zz_wo02571_fixqty",
                "fix-jc-op": "zz_wo02571_jcop",
                "recalc-op": "zz_wo02571_recalcop",
                "fix-initial-wo": "zz_wo02571_iwo",
                "split-tn": "zz_wo02571_splittn",
                "split-fix1": "zz_wo02571_splitfix1",
                "split-cons": "zz_wo02571_splitcons",
                "split-op": "zz_wo02571_splitop",
                "split-wo-qty": "zz_wo02571_splitwo",
                "split-se": "zz_wo02571_splitse",
                "split-iwo": "zz_wo02571_splitiwo"}
# close-gate 之后的三步是「工序层 + 开料工单数量勾稽」的补齐（2026-09-21 用户指出）
POST_STEPS = ("fix-jc-op", "recalc-op", "fix-initial-wo")


def _stage(c: ApiClient) -> dict:
    """判定当前处于哪个 step 的中间态（用于前置校验）。"""
    wos = {w: c.get_doc("Work Order", w) for w in (WO_TARGET, WO_SOURCE)}
    tns = {t: c.get_doc("Tracking Number", t) for t in MOVE_TNS}
    ses = {se["name"]: se for se in
           c.get_list("Stock Entry", [["tracking_number", "in", list(MOVE_TNS)]],
                      ["name", "docstatus", "purpose"], 0)}
    cancelled = sum(1 for s in ses.values() if s["purpose"] == "Manufacture" and s["docstatus"] == 2)
    submitted = sum(1 for s in ses.values() if s["purpose"] == "Manufacture" and s["docstatus"] == 1)
    repointed = sum(1 for t in tns.values() if t.get("work_order") == WO_TARGET)
    move = list(MOVE_TNS)
    jc_left = len(c.get_list("Job Card", [["tracking_number", "in", move],
                                          ["work_order", "=", WO_SOURCE]], ["name"], 0))
    jc_all = len(c.get_list("Job Card", [["tracking_number", "in", move]], ["name"], 0))
    cons_left = len(c.get_list("Stock Entry",
                               [["tracking_number", "in", move],
                                ["purpose", "=", "Material Consumption for Manufacture"],
                                ["work_order", "=", WO_SOURCE]], ["name"], 0))
    alloc_left = sum(1 for r in alloc_rows(c, move) if r.get("work_order") == WO_SOURCE)

    # 只看本批菲号的结余（仓里还有别的菲号/别的工单的库存，不能用整仓余额判断）
    half = stage = 0.0
    for tn in ALL_TNS:
        half += sum(float(r["actual_qty"] or 0)
                    for r in c.sle_rows(tracking=tn, item_code=ITEM_SHELL, warehouse=WH_HALF))
        stage += sum(float(r["actual_qty"] or 0)
                     for r in c.sle_rows(tracking=tn, item_code=ITEM_SHELL, warehouse=WH_FG_STAGE))
    return {
        "wos": wos, "tns": tns, "ses": ses,
        "manufacture_cancelled": cancelled, "manufacture_submitted": submitted,
        "tn_repointed": repointed,
        "jc_all": jc_all, "jc_left": jc_left,
        "cons_left": cons_left, "alloc_left": alloc_left,
        "gate": int(c.get_item_flag(ITEM_SHELL) or 0),
        "half": round(half, 4), "stage": round(stage, 4),
    }


def check_step(c: ApiClient, step: str) -> None:
    s = _stage(c)

    def need(cond: bool, msg: str) -> None:
        if not cond:
            raise SystemExit(f"✗ 前置不满足（step {step}）：{msg}")

    print(f"   本批菲号结余：@{WH_HALF}={s['half']}  @{WH_FG_STAGE}={s['stage']}  "
          f"闸门={s['gate']}  完工凭证(已提交/已取消)={s['manufacture_submitted']}/{s['manufacture_cancelled']}  "
          f"菲号已改挂={s['tn_repointed']}/3  报工仍挂源工单={s['jc_left']}/{s['jc_all']}  "
          f"耗用仍挂源={s['cons_left']}  开料分配仍挂源={s['alloc_left']}")

    def need_bal(key: str) -> None:
        want = EXPECT[key]
        need(abs(s["half"] - want[WH_HALF]) < 1e-6,
             f"皮壳@{WH_HALF}={s['half']}，期望 {want[WH_HALF]}")
        need(abs(s["stage"] - want[WH_FG_STAGE]) < 1e-6,
             f"皮壳@{WH_FG_STAGE}={s['stage']}，期望 {want[WH_FG_STAGE]}")

    def need_repointed() -> None:
        need(s["tn_repointed"] == 3, f"菲号未改挂完（{s['tn_repointed']}/3）")
        need(s["jc_all"] > 0, "本批菲号上一张报工都没找到 —— 先查清再动")
        need(s["jc_left"] == 0, f"仍有 {s['jc_left']}/{s['jc_all']} 张报工挂在 {WO_SOURCE}")
        need(s["cons_left"] == 0, f"仍有 {s['cons_left']} 张耗用凭证挂在 {WO_SOURCE}")
        need(s["alloc_left"] == 0, f"仍有 {s['alloc_left']} 行开料分配挂在 {WO_SOURCE}")

    if step == "cleanup":
        return  # 清理幂等，不做账面校验

    if step in ("preflight", "open-gate"):
        need(s["manufacture_submitted"] == 3, f"应有 3 张已提交 Manufacture，实际 {s['manufacture_submitted']}")
        need(s["manufacture_cancelled"] == 0, "已存在被取消的凭证，可能重复执行过")
        need(s["tn_repointed"] == 0, "菲号已被改挂，可能重复执行过")
        need(s["jc_all"] > 0, "本批菲号上一张报工都没找到 —— 先查清再动")
        need(s["jc_left"] == s["jc_all"], "报工已被改挂，可能重复执行过")
        need_bal("initial")
        if step == "open-gate":
            need(s["gate"] == 0, f"闸门已是 {s['gate']}")
    elif step == "cancel":
        need(s["gate"] == 1, "闸门未开（先跑 step open-gate）")
        need_bal("initial")   # cancel 之前仍是初始账面
        need(s["manufacture_submitted"] == 3, f"应有 3 张已提交 Manufacture，实际 {s['manufacture_submitted']}")
    elif step == "repoint":
        need(s["gate"] == 1, "闸门未开")
        need_bal("after_cancel")
        need(s["manufacture_cancelled"] == 3, f"应先取消 3 张凭证，实际已取消 {s['manufacture_cancelled']}")
        need(s["tn_repointed"] == 0, "菲号已改挂过")
    elif step == "fix-wo-qty":
        need_repointed()
        need_bal("after_cancel")
    elif step == "redo":
        need_bal("after_cancel")
        need_repointed()
        # 关键守卫：目标工单的 open_material_qty 必须先抬到 130，否则本步提交 Manufacture 时
        # work_order_override.update_work_order_qty 会用 completed_qty=open_material_qty=78
        # 判「入库量 91 > 78」并抛 StockOverProductionError（测试机已实测）。
        omq = float(s["wos"][WO_TARGET].get("open_material_qty") or 0)
        need(abs(omq - FINAL_OPEN_MATERIAL[WO_TARGET]) < 1e-6,
             f"{WO_TARGET}.open_material_qty={omq}，应先跑 step fix-wo-qty 抬到 "
             f"{FINAL_OPEN_MATERIAL[WO_TARGET]}")
        new_ses = c.get_list("Stock Entry",
                             [["work_order", "=", WO_TARGET], ["purpose", "=", "Manufacture"],
                              ["docstatus", "=", 1]], ["name"], 0)
        need(len(new_ses) == 2, f"{WO_TARGET} 名下应只有原有 2 张 Manufacture，实际 {len(new_ses)}")
    elif step == "close-gate":
        need(s["gate"] == 1, f"闸门应为开，实际 {s['gate']}")
        need_repointed()
        need_bal("final")
    elif step in POST_STEPS:
        need(s["tn_repointed"] == 3, "菲号未改挂完")
        need_bal("final")
        jcop = op_and_alloc_state(c)
        if step == "fix-jc-op":
            need(len(jcop["jcop"]) > 0, "没有待换 operation_id 的报工行 —— 可能已执行过")
        elif step == "recalc-op":
            need(len(jcop["jcop"]) == 0, f"仍有 {len(jcop['jcop'])} 张报工 operation_id 未换")
    elif step in SPLIT_STEPS:
        wos = {w: c.get_doc("Work Order", w) for w in (WO_TARGET, WO_SOURCE)}
        up = c.get_doc("Tracking Number", SPLIT_UP_TN)
        dn = c.get_doc("Tracking Number", SPLIT_DN_TN)
        if step == "split-fix1":
            pass
        elif step == "split-cons":
            pass
        elif step == "split-tn":
            need(float(up["qty"]) == SPLIT_UP_OLD, f"{SPLIT_UP_TN}.qty={up['qty']}，应为 {SPLIT_UP_OLD}")
            need(float(dn["qty"]) == SPLIT_DN_OLD, f"{SPLIT_DN_TN}.qty={dn['qty']}，应为 {SPLIT_DN_OLD}")
        elif step == "split-wo-qty":
            need(float(up["qty"]) == SPLIT_UP_NEW, f"{SPLIT_UP_TN}.qty={up['qty']}，应先跑 split-tn")
        elif step in ("split-se", "split-iwo", "split-op"):
            need(float(up["qty"]) == SPLIT_UP_NEW, f"{SPLIT_UP_TN}.qty={up['qty']}，应先跑 split-tn")
            need(abs(float(wos[WO_TARGET]["open_material_qty"] or 0) - (SPLIT_UP_NEW + 117.0)) < 1e-6,
                 f"{WO_TARGET}.open_material_qty 应为 {SPLIT_UP_NEW + 117.0}，先跑 split-wo-qty")
            if step in ("split-iwo", "split-op"):
                done = [r for r in c.get_list("Stock Entry",
                                              [["tracking_number", "in", [SPLIT_UP_TN, SPLIT_DN_TN]],
                                               ["purpose", "=", "Manufacture"], ["docstatus", "=", 1]],
                                              ["name", "fg_completed_qty"], 0)]
                qtys = sorted(float(r["fg_completed_qty"]) for r in done)
                need(qtys == sorted([SPLIT_UP_NEW, SPLIT_DN_NEW]),
                     f"完工凭证数量应为 {sorted([SPLIT_UP_NEW, SPLIT_DN_NEW])}，实际 {qtys} —— 先跑 split-se")
    else:
        raise SystemExit(f"✗ 未知 step: {step}")


def _run_script(c: ApiClient, name: str, body: str) -> None:
    try:
        c.insert_doc("Server Script", {
            "doctype": "Server Script", "name": name, "script_type": "API",
            "api_method": name, "script": body, "disabled": 0, "allow_guest": 0,
        })
        print(f"   ✓ 已建临时 Server Script {name}")
        res = c.call_method(name)
        print(f"   ✓ 执行结果: {json.dumps(res, ensure_ascii=False)}")
    finally:
        try:
            c.delete_doc("Server Script", name)
            print(f"   ✓ 已删除临时 Server Script {name}")
        except Exception as e:  # noqa: BLE001
            print(f"   ✗ 临时脚本删除失败，请手工删除 {name}：{e}")


def op_and_alloc_state(c: ApiClient) -> dict:
    """工序层与开料工单的当前状态（供 dry 预览与前置校验）。"""
    st: dict = {"ops": {}, "alloc": []}
    for wo_name in (WO_TARGET, WO_SOURCE):
        wo = c.get_doc("Work Order", wo_name)
        st["ops"][wo_name] = [
            {"name": o.get("name"), "operation": o.get("operation"),
             "completed_qty": o.get("completed_qty"), "status": o.get("status")}
            for o in (wo.get("operations") or [])]
    st["jcop"] = [r for r in c.get_list(
        "Job Card", [["tracking_number", "in", list(MOVE_TNS)], ["docstatus", "=", 1]],
        ["name", "operation", "operation_id"], 0) if r.get("operation_id") in OP_ID_MAP]
    st["alloc"] = {}
    try:
        iwo = c.get_doc("Initial Work Order", INITIAL_WO)
        st["alloc"] = [{"name": r.get("name"), "group_number": r.get("group_number"),
                        "tracking_number": r.get("tracking_number"),
                        "group_split_qty": r.get("group_split_qty"),
                        "work_order": r.get("work_order"),
                        "wo_origion_fill_numb": r.get("wo_origion_fill_numb"),
                        "is_or_exceed": r.get("is_or_exceed")}
                       for r in (iwo.get("woker_order_allocations") or [])]
    except Exception:  # noqa: BLE001
        pass
    return st


def cmd_dry_post(c: ApiClient) -> None:
    """只读预览：工序层 + 开料工单三步的逐行 before → after。"""
    s = op_and_alloc_state(c)
    hr("[工序层] Work Order Operation.completed_qty")
    for wo_name, ops in s["ops"].items():
        want = FINAL_PRODUCED[wo_name]
        print(f"   {wo_name}（工单数量 {c.get_doc('Work Order', wo_name).get('qty')}）")
        for o in ops:
            if not flt(o["completed_qty"]) and o["status"] == "Pending":
                continue          # 未涉及的工序行（通用返工/质检发现问题）
            mark = "" if abs(flt(o["completed_qty"]) - want) < 1e-6 else f"  ← 应为 {want}"
            print(f"     {o['operation']:<12} completed={o['completed_qty']:<8} status={o['status']}{mark}")
    print(f"\n   待换 operation_id 的报工行：{len(s['jcop'])} 张")
    for r in sorted(s["jcop"], key=lambda x: (x["operation"], x["name"]))[:8]:
        print(f"     {r['name']:<16} {r['operation']:<8} {r['operation_id']} → {OP_ID_MAP[r['operation_id']]}")
    if len(s["jcop"]) > 8:
        print(f"     … 其余 {len(s['jcop']) - 8} 张同理")

    hr(f"[开料工单 {INITIAL_WO}] 分配行数量勾稽（6 行全列）")
    print(f"   {'group':<6}{'菲号':<20}{'数量':<7}{'归属':<14}{'wo_origion':<12}{'is_or_exceed':<12}→ 修正后")
    for r in sorted(s["alloc"], key=lambda x: x["group_number"]):
        g = int(r["group_number"])
        f = ALLOC_FIX.get(g, {})
        print(f"   {g:<6}{r['tracking_number']!s:<20}{r['group_split_qty']:<7}{r['work_order']!s:<14}"
              f"{r.get('wo_origion_fill_numb'):<12}{r.get('is_or_exceed'):<12}"
              f"→ wo_origion={f.get('wo_origion_fill_numb')} is_or_exceed={f.get('is_or_exceed')}")
    print(f"\n   兄弟子表 group1/2/3 归属 → {WO_TARGET}：work_order_batch_qtys、fg_qty_key_material_bns")


def cmd_dry_split(c: ApiClient) -> None:
    """只读预览：超量 1 件从 03197 挪到 02571 的逐行变更。"""
    hr("[1] 跟踪单号 + 报工数量")
    for tn, old, new in ((SPLIT_UP_TN, SPLIT_UP_OLD, SPLIT_UP_NEW),
                         (SPLIT_DN_TN, SPLIT_DN_OLD, SPLIT_DN_NEW)):
        t = c.get_doc("Tracking Number", tn)
        jcs = c.get_list("Job Card", [["tracking_number", "=", tn], ["docstatus", "=", 1]],
                         ["name", "for_quantity", "total_completed_qty"], 0)
        qtys = sorted({x["for_quantity"] for x in jcs})
        print(f"   {tn:<20} wo={t['work_order']:<14} qty {t['qty']} → {new}"
              f"   报工 {len(jcs)} 张 {qtys} → {new}")

    hr("[2] 工单数量（必须先于重做，否则超产校验会拦）")
    print(f"   {WO_TARGET}: produced/open_material → {SPLIT_UP_NEW + 117.0}")
    print(f"   {WO_SOURCE}: produced/open_material → {SPLIT_DN_NEW}")

    hr("[3] 取消 + 重做 完工入库 / 加工耗用")
    for tn, (se, q, dst, wo) in SPLIT_MFG.items():
        d = c.get_doc("Stock Entry", se)
        print(f"   完工 {se}({d['fg_completed_qty']}) → 取消，在 {wo} 下重做 {q} 进 {dst}"
              f"（单价抄原凭证 {d['items'][0].get('basic_rate')}）")
    for tn, (se, pieces, fabric) in SPLIT_CONS.items():
        d = c.get_doc("Stock Entry", se)
        print(f"   耗用 {se}(件数 {d['fg_completed_qty']} / 面料 {d['items'][0].get('qty')}m)"
              f" → 取消，重做 件数 {pieces} / 面料 {fabric}m")

    hr(f"[4] 开料工单 {INITIAL_WO}")
    print(f"   {'group':<6}{'菲号':<20}{'数量':<8}{'orig':<8}{'exceed':<8}（现值 → 修正后）")
    try:
        iwo = c.get_doc("Initial Work Order", INITIAL_WO)
        for r in sorted(iwo.get("woker_order_allocations") or [], key=lambda x: x.get("group_number")):
            g = int(r["group_number"])
            f = SPLIT_ALLOC_FIX.get(g, {})
            print(f"   {g:<6}{r['tracking_number']!s:<20}{r['group_split_qty']:<8}"
                  f"{r.get('wo_origion_fill_numb'):<8}{r.get('is_or_exceed'):<8}"
                  f"→ {f.get('group_split_qty', r['group_split_qty'])} / {f.get('wo_origion_fill_numb')} / {f.get('is_or_exceed')}")
        print(f"   兄弟子表 g1/g4：work_order_batch_qtys 的 split/usage/real_usage、fg_qty_key_material_bns 的 fg_qty")
    except Exception as e:  # noqa: BLE001
        print(f"   ! 读取失败 {e}")

    hr("[5] 工序 completed_qty")
    print(f"   {WO_TARGET} → {SPLIT_UP_NEW + 117.0}（7 道）；{WO_SOURCE} → {SPLIT_DN_NEW}（7 道）")


def cmd_apply(c: ApiClient, step: str, apply: bool) -> None:
    print(f"环境: {PROD}" + ("" if apply else "（dry-run，加 --apply 才真正写）"))

    if step in SPLIT_STEPS and not apply:
        cmd_dry_split(c)
        print(f"\ndry-run：step {step} 将执行")
        return

    if step in POST_STEPS and not apply:
        cmd_dry_post(c)
        print(f"\ndry-run：step {step} 将执行")
        return

    check_step(c, step)

    if not apply:
        print(f"\ndry-run：step {step} 将执行")
        return

    g = gather(c)

    if step == "preflight":
        p = dump("wo_02571_03197_before", {
            "wos": {k: {f: v.get(f) for f in WO_FIELDS} for k, v in g["wos"].items()},
            "tracking_numbers": {k: dict(v) for k, v in g["tns"].items()},
            "stock_entries": [{f: se.get(f) for f in SE_FIELDS} for se in g["move_ses"] + g["keep_ses"]],
            "manufacture_move": [se["name"] for se in g["move_ses"]],
            "material_consumption": g["cons_ses"],
            "job_cards": g["job_cards"],
            "woker_order_allocations": g["allocs"],
        })
        print(f"   ✓ 已备份改前账面（含报工/耗用/开料分配）→ {p}")

    elif step == "open-gate":
        c.set_item_flag(ITEM_SHELL, 1)
        print(f"   ✓ {ITEM_SHELL}.allow_negative_stock = {c.get_item_flag(ITEM_SHELL)}")

    elif step == "cancel":
        for se in sorted(g["move_ses"], key=lambda x: x["name"]):
            c.cancel_doc("Stock Entry", se["name"])
            print(f"   ✓ 已取消 {se['name']}（{se.get('tracking_number')} {se.get('fg_completed_qty')}）")

    elif step == "repoint":
        _run_script(c, SCRIPT_NAMES[step], _SCRIPT_REPOINT)
        print(f"      待改挂：报工 {len(g['job_cards'])} 张 / 耗用 {len(g['cons_ses'])} 张 / "
              f"开料分配 {len(g['allocs'])} 行")

    elif step == "redo":
        mapping = [(se.get("tracking_number"), float(se.get("fg_completed_qty") or 0), se["name"])
                   for se in sorted(g["move_ses"], key=lambda x: x["name"])]
        if len(mapping) != 3:
            raise SystemExit(f"✗ redo 的单价来源凭证应有 3 张，实际 {len(mapping)}："
                             f"{[m[2] for m in mapping]} —— 先查清再做，避免空跑")
        _run_script(c, SCRIPT_NAMES[step], redo_script(mapping, WO_TARGET, ITEM_SHELL, WH_HALF))

    elif step == "fix-wo-qty":
        _run_script(c, SCRIPT_NAMES[step], _SCRIPT_FIXQTY)

    elif step == "close-gate":
        c.set_item_flag(ITEM_SHELL, 0)
        print(f"   ✓ {ITEM_SHELL}.allow_negative_stock = {c.get_item_flag(ITEM_SHELL)}")

    elif step == "cleanup":
        for name in SCRIPT_NAMES.values():
            try:
                c.delete_doc("Server Script", name)
                print(f"   ✓ 已删除 {name}")
            except Exception as e:  # noqa: BLE001
                print(f"   · {name}: {e}")

    elif step == "fix-jc-op":
        _run_script(c, SCRIPT_NAMES[step], jc_opid_script(OP_ID_MAP))

    elif step == "recalc-op":
        _run_script(c, SCRIPT_NAMES[step], recalc_op_script(WO_TARGET, ITEM_SHELL))

    elif step == "fix-initial-wo":
        _run_script(c, SCRIPT_NAMES[step],
                    fix_initial_wo_script(INITIAL_WO, ALLOC_FIX, [1, 2, 3], WO_TARGET))

    elif step == "split-tn":
        _run_script(c, SCRIPT_NAMES[step], split_tn_script())

    elif step == "split-wo-qty":
        _run_script(c, SCRIPT_NAMES[step],
                    fixqty_script(WO_TARGET, SPLIT_UP_NEW + 117.0, WO_SOURCE, SPLIT_DN_NEW))

    elif step == "split-fix1":
        _run_script(c, SCRIPT_NAMES[step], split_fix1_script())

    elif step == "split-cons":
        _run_script(c, SCRIPT_NAMES[step], split_cons_script())

    elif step == "split-se":
        _run_script(c, SCRIPT_NAMES[step], split_se_script())

    elif step == "split-iwo":
        _run_script(c, SCRIPT_NAMES[step], split_iwo_script(INITIAL_WO, SPLIT_ALLOC_FIX))

    elif step == "split-op":
        _run_script(c, SCRIPT_NAMES[step], recalc_op_script(WO_TARGET, ITEM_SHELL))


def cmd_cleanup(c: ApiClient, apply: bool) -> None:
    left = c.get_all("Server Script", [["name", "like", "zz_wo02571%"]], ["name"], 0)
    if not left:
        print("✓ 无遗留临时 Server Script")
        return
    print(f"发现遗留：{[x['name'] for x in left]}")
    if not apply:
        print("（dry-run，加 --apply 才删）")
        return
    for x in left:
        c.delete_doc("Server Script", x["name"])
        print(f"   ✓ 已删除 {x['name']}")


def main() -> int:
    ap = argparse.ArgumentParser(description=__doc__,
                                 formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("cmd", choices=("probe", "dry", "apply", "verify", "cleanup"))
    ap.add_argument("--step", choices=STEPS, help="apply 用：要执行的单步")
    ap.add_argument("--apply", action="store_true", help="真正写生产（默认 dry-run）")
    args = ap.parse_args()

    c = ApiClient()
    if args.cmd == "probe":
        cmd_probe(c)
    elif args.cmd == "dry":
        cmd_dry(c)
    elif args.cmd == "verify":
        cmd_verify(c)
    elif args.cmd == "cleanup":
        cmd_cleanup(c, args.apply)
    else:
        if not args.step:
            raise SystemExit(f"✗ apply 必须带 --step {{{'|'.join(STEPS)}}}")
        cmd_apply(c, args.step, args.apply)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
