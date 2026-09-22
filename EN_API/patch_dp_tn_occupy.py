# -*- coding: utf-8 -*-
"""给 delivery_plan app 打「扫菲号时跨单据校验占用」补丁（在测试机上运行）。

背景：出货计划扫跟踪单号时，可用量只在本单据内计算（delivery_plan.py:1032 / :219
与 delivery_plan.js:751），看不到其他出货计划（尤其未提交草稿）已占用的数量，
导致两张草稿单可以各占同一批菲号的全额。

本补丁（4 处，只改这个 app 的 1 个 .py + 1 个 .js）：
  1. delivery_plan.py 新增 `_dp_other_plans_occupied()` —— 一次 SQL 批量查其他单据占用
     （从 tabDelivery Plan 驱动，子表走 parent 索引，避免全表扫）
  2. `_validate_tracking_number_planned_qty` 保存兜底加入跨单占用（批量，1 条 SQL/次保存）
  3. `add_item_from_tracking_number` 扫码剩余量扣除跨单占用（1 条 SQL/次扫码），
     返回值带上 other_occupied 供前端用
  4. delivery_plan.js 即时校验扣除跨单占用（用 frm 级缓存，0 次新增请求）

口径：占用范围 = docstatus IN (0,1)（草稿 + 已提交），排除本单据自己。
冲突行为：剩余 > 0 自动截断；剩余 <= 0 报错提示。

用法（在测试机上）：
  python3 patch_dp_tn_occupy.py --check     # 只校验锚点能否命中，不改文件
  python3 patch_dp_tn_occupy.py --apply     # 备份后写入
  python3 patch_dp_tn_occupy.py --revert    # 从 /tmp/zz_bak_*.py|js 还原
"""

from __future__ import annotations

import argparse
import shutil
import sys
from pathlib import Path

BASE = Path("/home/frappe/frappe-bench/apps/delivery_plan/delivery_plan/delivery_plan/doctype/delivery_plan")
PY = BASE / "delivery_plan.py"
JS = BASE / "delivery_plan.js"
BAK_PY = Path("/tmp/zz_bak_delivery_plan.py")
BAK_JS = Path("/tmp/zz_bak_delivery_plan.js")


def read(path: Path) -> tuple[str, str]:
    """返回 (文本, 换行符)。保留原换行风格。"""
    with open(path, "r", encoding="utf-8", newline="") as f:
        raw = f.read()
    nl = "\r\n" if "\r\n" in raw[:8000] else "\n"
    return raw, nl


def write(path: Path, text: str) -> None:
    with open(path, "w", encoding="utf-8", newline="") as f:
        f.write(text)


def ana(lines: list[str], nl: str) -> str:
    return nl.join(lines)


# ── 1) 新增跨单据占用查询方法 ────────────────────────────────────────
NEW_METHOD = """\tdef _dp_other_plans_occupied(self, tracking_numbers):
\t\t\"\"\"其他出货计划（docstatus 0/1，排除本单据自己）中这些菲号的占用。

\t\t返回 {tracking_number: {"total": float, "by_plan": {单据名: 数量}}}

\t\t性能：**一次 SQL 查完传入的全部菲号**（从 tabDelivery Plan 驱动，子表走 parent 索引）。
\t\t严禁在调用方按菲号循环调用 —— 当初保存慢 18 秒就是「每行一次无缓存查询」造成的。
\t\t\"\"\"
\t\ttns = sorted({(t or "").strip() for t in (tracking_numbers or []) if (t or "").strip()})
\t\tif not tns:
\t\t\treturn {}

\t\trows = frappe.db.sql(
\t\t\t\"\"\"
\t\t\tSELECT iq.tracking_number AS tn, dp.name AS plan, SUM(iq.planned_delivery_qty) AS qty
\t\t\tFROM `tabDelivery Plan` dp
\t\t\tINNER JOIN `tabDelivery Plan Item Qty` iq ON iq.parent = dp.name
\t\t\tWHERE dp.docstatus IN (0, 1)
\t\t\t  AND dp.name <> %(self)s
\t\t\t  AND iq.tracking_number IN %(tns)s
\t\t\tGROUP BY iq.tracking_number, dp.name
\t\t\t\"\"\",
\t\t\t{"self": self.name or "", "tns": tns},
\t\t\tas_dict=True,
\t\t)

\t\tout = {}
\t\tfor r in rows:
\t\t\tslot = out.setdefault(r.tn, {"total": 0.0, "by_plan": {}})
\t\t\tqty = flt(r.qty)
\t\t\tslot["total"] += qty
\t\t\tslot["by_plan"][r.plan] = flt(slot["by_plan"].get(r.plan, 0)) + qty
\t\treturn out

\t@frappe.whitelist()
\tdef get_tn_other_plan_occupied(self, tracking_number):
\t\t\"\"\"供前端即时校验用：某菲号被其他出货计划占用的数量。\"\"\"
\t\tinfo = self._dp_other_plans_occupied([tracking_number]).get((tracking_number or "").strip()) or {}
\t\treturn {"total": flt(info.get("total")), "by_plan": info.get("by_plan") or {}}

"""

ANCHOR_METHOD = "\tdef _validate_tracking_number_planned_qty(self):"

# ── 2) 保存兜底加入跨单占用 ─────────────────────────────────────────
ANCHOR_VALIDATE = [
    "\t\t# 逐个检查超限情况",
    "\t\terrors = []",
    "\t\tfor tn, total_qty in tn_qty_map.items():",
    "\t\t\toriginal_qty = tn_original_qty.get(tn)",
    "\t\t\tif original_qty is not None and total_qty > original_qty:",
    "\t\t\t\texcess = total_qty - original_qty",
    "\t\t\t\terrors.append(",
    '\t\t\t\t\t_("跟踪单号 {0}：计划交货数量 {1} 超过原始库存 {2}（超出 {3}）")',
    "\t\t\t\t\t.format(tn, total_qty, original_qty, excess)",
    "\t\t\t\t)",
]

REPL_VALIDATE = [
    "\t\t# 跨单据占用：其他出货计划（草稿 + 已提交，排除本单据）已占用的数量",
    "\t\t# 一次批量查询；严禁改成按菲号循环（会让保存重新变慢）",
    "\t\tother_occ = self._dp_other_plans_occupied(list(tn_qty_map.keys()))",
    "",
    "\t\t# 逐个检查超限情况",
    "\t\terrors = []",
    "\t\tfor tn, total_qty in tn_qty_map.items():",
    "\t\t\toriginal_qty = tn_original_qty.get(tn)",
    "\t\t\tif original_qty is None:",
    "\t\t\t\tcontinue",
    "\t\t\t_occ = other_occ.get(tn) or {}",
    "\t\t\tother_qty = flt(_occ.get(\"total\"))",
    "\t\t\tif total_qty + other_qty > original_qty:",
    "\t\t\t\texcess = total_qty + other_qty - original_qty",
    "\t\t\t\t_detail = \"、\".join(",
    '\t\t\t\t\t"{0} 占 {1}".format(p, flt(q))',
    '\t\t\t\t\tfor p, q in sorted((_occ.get("by_plan") or {}).items())',
    "\t\t\t\t)",
    "\t\t\t\terrors.append(",
    '\t\t\t\t\t_("跟踪单号 {0}：本单计划 {1} + 其他出货计划已占用 {2} 超过原始库存 {3}（超出 {4}）{5}")',
    "\t\t\t\t\t.format(tn, total_qty, other_qty, original_qty, excess,",
    '\t\t\t\t\t        ("；其他单占用明细：{0}".format(_detail) if _detail else ""))',
    "\t\t\t\t)",
]

# ── 3) 扫码剩余量扣除跨单占用 ───────────────────────────────────────
ANCHOR_SCAN = [
    "\t\tremaining_qty = original_tn_qty - already_allocated",
    "",
    "\t\t# 如果剩余数量 <= 0，不允许再添加",
    "\t\tif remaining_qty <= 0:",
    "\t\t\tfrappe.throw(_(",
    '\t\t\t\t"跟踪单号 {0} 已无可用库存（原始数量: {1}，已分配: {2}）"',
    "\t\t\t).format(tracking_number, original_tn_qty, already_allocated))",
]

REPL_SCAN = [
    "\t\t# 跨单据占用：其他出货计划（草稿 + 已提交，排除本单据）已占用的数量（单次查询）",
    "\t\t_occ_info = self._dp_other_plans_occupied([tracking_number]).get(tracking_number) or {}",
    "\t\tother_occupied = flt(_occ_info.get(\"total\"))",
    "",
    "\t\tremaining_qty = original_tn_qty - already_allocated - other_occupied",
    "",
    "\t\t# 如果剩余数量 <= 0，不允许再添加（提示含占用来源）",
    "\t\tif remaining_qty <= 0:",
    "\t\t\t_occ_detail = \"、\".join(",
    '\t\t\t\t"{0} 占 {1}".format(p, flt(q))',
    '\t\t\t\tfor p, q in sorted((_occ_info.get("by_plan") or {}).items())',
    "\t\t\t)",
    "\t\t\tfrappe.throw(_(",
    '\t\t\t\t"跟踪单号 {0} 可用库存不足（原始数量: {1}，本单已分配: {2}，其他出货计划已占用: {3}）{4}"',
    "\t\t\t).format(tracking_number, original_tn_qty, already_allocated, other_occupied,",
    '\t\t\t         ("；占用明细：{0}".format(_occ_detail) if _occ_detail else "")))',
]

ANCHOR_RETURN = [
    '\t\t\t"added_qty": this_scan_qty,',
    '\t\t\t"original_qty": original_tn_qty,',
    '\t\t\t"remaining_after": 0  # 本次扫描后，该跟踪单号无剩余',
    "\t\t}",
]

REPL_RETURN = [
    '\t\t\t"added_qty": this_scan_qty,',
    '\t\t\t"original_qty": original_tn_qty,',
    '\t\t\t"other_occupied": other_occupied,  # 其他出货计划已占用（供前端即时校验）',
    '\t\t\t"remaining_after": 0  # 本次扫描后，该跟踪单号无剩余',
    "\t\t}",
]

# ── 4) 前端即时校验扣除跨单占用 ─────────────────────────────────────
ANCHOR_JS_MAX = [
    "        let new_value = flt(row.planned_delivery_qty);",
    "        let max_allowed = original_qty - other_rows_sum;",
]

REPL_JS_MAX = [
    "        // 跨单据占用：扫码时后端算出并缓存到 frm 上（同一菲号只取一次，不新增请求）",
    "        let other_plan_occupied = flt((frm._dp_tn_occupied || {})[row.tracking_number]);",
    "",
    "        let new_value = flt(row.planned_delivery_qty);",
    "        let max_allowed = original_qty - other_rows_sum - other_plan_occupied;",
]

ANCHOR_JS_MSG = [
    "                message: __('跟踪单号 {0} 的最大可用数量为 {1}（原始库存 {2} - 其他行已分配 {3}）',",
    "                    [row.tracking_number, max_allowed, original_qty, other_rows_sum])",
]

REPL_JS_MSG = [
    "                message: __('跟踪单号 {0} 的最大可用数量为 {1}（原始库存 {2} - 其他行已分配 {3} - 其他出货计划已占用 {4}）',",
    "                    [row.tracking_number, max_allowed, original_qty, other_rows_sum, other_plan_occupied])",
]

ANCHOR_JS_SCAN = [
    '\t\t\t\t\tfrm.set_value("tracking_number", "");',
    '\t\t\t\t\tfrm.refresh_field("tracking_number");',
]

REPL_JS_SCAN = [
    '\t\t\t\t\tfrm.set_value("tracking_number", "");',
    '\t\t\t\t\tfrm.refresh_field("tracking_number");',
    "",
    "\t\t\t\t\t// 缓存后端算出的「其他出货计划已占用」，供同页 planned_delivery_qty 校验使用",
    "\t\t\t\t\tif (r.message && r.message.other_occupied !== undefined) {",
    "\t\t\t\t\t\tfrm._dp_tn_occupied = frm._dp_tn_occupied || {};",
    "\t\t\t\t\t\tfrm._dp_tn_occupied[tracking_no] = flt(r.message.other_occupied);",
    "\t\t\t\t\t}",
]

PATCHES_PY = [
    ("插入 _dp_other_plans_occupied 方法", [ANCHOR_METHOD], [ANCHOR_METHOD], "insert"),
    ("保存兜底加入跨单占用", ANCHOR_VALIDATE, REPL_VALIDATE, "replace"),
    ("扫码剩余量扣除跨单占用", ANCHOR_SCAN, REPL_SCAN, "replace"),
    ("扫码返回值带上 other_occupied", ANCHOR_RETURN, REPL_RETURN, "replace"),
]

PATCHES_JS = [
    ("前端即时校验扣除跨单占用", ANCHOR_JS_MAX, REPL_JS_MAX, "replace"),
    ("前端提示文案", ANCHOR_JS_MSG, REPL_JS_MSG, "replace"),
    ("扫码回调缓存占用值", ANCHOR_JS_SCAN, REPL_JS_SCAN, "replace"),
]


def apply_patches(text: str, nl: str, patches: list, label: str) -> str:
    for name, anchor_lines, repl_lines, mode in patches:
        anchor = ana(anchor_lines, nl)
        repl = ana(repl_lines, nl)
        cnt = text.count(anchor)
        if cnt != 1:
            raise SystemExit(f"✗ [{label}] 「{name}」锚点命中 {cnt} 次（应为 1），中止")
        if mode == "insert":
            text = text.replace(anchor, NEW_METHOD.replace("\n", nl) + nl + anchor)
        else:
            text = text.replace(anchor, repl)
        print(f"  ✓ [{label}] {name}")
    return text


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("action", choices=("check", "apply", "revert"))
    args = ap.parse_args()

    if args.action == "revert":
        shutil.copyfile(BAK_PY, PY)
        shutil.copyfile(BAK_JS, JS)
        print(f"已从 {BAK_PY} / {BAK_JS} 还原")
        return 0

    py_text, py_nl = read(PY)
    js_text, js_nl = read(JS)
    print(f"换行风格: py={py_nl!r} js={js_nl!r}")

    new_py = apply_patches(py_text, py_nl, PATCHES_PY, "py")
    new_js = apply_patches(js_text, js_nl, PATCHES_JS, "js")

    if args.action == "check":
        print("\n[check] 全部锚点命中，未写文件。加 --apply 才写入。")
        return 0

    if not BAK_PY.exists() or not BAK_JS.exists():
        raise SystemExit(f"✗ 缺备份 {BAK_PY} / {BAK_JS}，先做备份再 apply")
    write(PY, new_py)
    write(JS, new_js)
    print(f"\n已写入 {PY}\n已写入 {JS}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
