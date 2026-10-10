# -*- coding: utf-8 -*-
"""给 delivery_plan app 修 `handle_over_delivery_items()` 的超量行菲号/数量口径（在测试机上运行）。

背景（2026-10-08 出货计划 2610001 实测）：
  原逻辑建超量行时，菲号取的是「该物料在 items 里的**第一行**」（for + break），
  并整行 deepcopy，于是：
    1) 超量件被挂到**已用满、无余量**的菲号上（例：挂到 -001，而唯一余量在 -006）；
    2) `allocated_actual_qty` / 外箱箱号 / 箱组 / 外箱尺寸被一并复制，
       导致该字段虚增（例：只带 1 件却继承 24），且箱号张冠李戴。

本补丁（只改 delivery_plan.py 一个方法）：
  * 超量行改为挂在**仍有余量的备货行**（item_qties 里 `staging_qty - assigned_qty > 0`）对应的菲号上；
    余量分散在多个菲号时按余量拆多行；**没有余量来源就不建**（宁可留空也不挂错）。
  * 只带超量数量：`planned_delivery_qty` 与 `allocated_actual_qty` 都设为该行实际承担的件数；
    `delivered_qty` / `actual_delivered_qty` / `returned_qty` 归零。
  * 箱号 / 箱组 / 外箱尺寸**跟随该备货行**（未装箱则为空/0），不再继承模板行。

时序依据：validate 里 `create_items_from_planned_qties()`（负责写 `assigned_qty`）先执行，
`handle_over_delivery_items()` 在其后，故此处读到的 `assigned_qty` 是本轮最新值。

用法（在测试机上）：
  python3 patch_dp_over_delivery_fix.py --check     # 只定位并打印将被替换的块，不写文件
  python3 patch_dp_over_delivery_fix.py --apply     # 备份到 /tmp 后写入
  python3 patch_dp_over_delivery_fix.py --revert    # 从备份还原
  改完需重启：cd /home/frappe/frappe-bench && sudo -u frappe bench restart
"""
from __future__ import annotations

import argparse
import shutil
from pathlib import Path

PY = Path("/home/frappe/frappe-bench/apps/delivery_plan/delivery_plan/"
          "delivery_plan/doctype/delivery_plan/delivery_plan.py")
BAK = Path("/tmp/zz_bak_delivery_plan_over_delivery.py")

ANCHOR_DEF = "\tdef handle_over_delivery_items(self):"
NEXT_DEF_PREFIX = "\tdef "


def new_method_lines() -> list[str]:
    L: list[str] = []
    a = L.append
    a("\tdef handle_over_delivery_items(self):")
    a('\t\t"""')
    a("\t\t处理超量交付的物料行")
    a("\t\t当允许超量交付且备货数量大于分配数量时，创建超量行。")
    a("\t\t超量行挂在「仍有余量的备货行」对应的跟踪单号上，且只带该行实际承担的件数；")
    a("\t\t箱号/箱组/外箱尺寸跟随该备货行，不继承模板行。")
    a('\t\t"""')
    a("\t\timport copy")
    a("\t\tif not self.allow_over_qty:")
    a("\t\t\treturn  # 如果不允许超量，直接返回")
    a("")
    a("\t\t# 每个物料号的备货数量合计")
    a("\t\tover_row_item_qties = {}")
    a("\t\tfor row in self.item_qties:")
    a("\t\t\tif row.item_code not in over_row_item_qties:")
    a("\t\t\t\tover_row_item_qties[row.item_code] = row.staging_qty")
    a("\t\t\telse:")
    a("\t\t\t\tover_row_item_qties[row.item_code] += row.staging_qty")
    a("")
    a("\t\t# 每个物料号在物料明细里已分配的计划交货数量合计")
    a("\t\titem_row_planned__qty = {}")
    a("\t\tfor item in self.items:")
    a("\t\t\tif item.item_code not in item_row_planned__qty:")
    a("\t\t\t\titem_row_planned__qty[item.item_code] = item.planned_delivery_qty")
    a("\t\t\telse:")
    a("\t\t\t\titem_row_planned__qty[item.item_code] += item.planned_delivery_qty")
    a("")
    a("\t\tover_delivery_items = []")
    a("\t\tfor material_code in over_row_item_qties:")
    a("\t\t\tif material_code not in item_row_planned__qty:")
    a("\t\t\t\tcontinue")
    a("\t\t\tplan_data_lack = flt(over_row_item_qties[material_code]) - flt(item_row_planned__qty[material_code])")
    a("\t\t\tif plan_data_lack <= 0:")
    a("\t\t\t\tcontinue")
    a("")
    a("\t\t\t# 该物料「仍有余量」的跟踪单号：按菲号汇总（备货数量 - 已分配数量 > 0），保持首次出现顺序")
    a("\t\t\tsurplus_order = []")
    a("\t\t\tsurplus_map = {}")
    a("\t\t\tfor qr in self.item_qties:")
    a("\t\t\t\tif qr.item_code != material_code:")
    a("\t\t\t\t\tcontinue")
    a("\t\t\t\tsurplus = flt(qr.staging_qty) - flt(qr.assigned_qty)")
    a("\t\t\t\tif surplus <= 0:")
    a("\t\t\t\t\tcontinue")
    a("\t\t\t\ttn = qr.tracking_number or \"\"")
    a("\t\t\t\tif tn not in surplus_map:")
    a("\t\t\t\t\tsurplus_map[tn] = {\"surplus\": surplus, \"qr\": qr}")
    a("\t\t\t\t\tsurplus_order.append(tn)")
    a("\t\t\t\telse:")
    a("\t\t\t\t\tsurplus_map[tn][\"surplus\"] += surplus")
    a("")
    a("\t\t\t# 没有余量来源就不建超量行（宁可留空，也不把超量挂到已用满的菲号上）")
    a("\t\t\tif not surplus_order:")
    a("\t\t\t\tcontinue")
    a("")
    a("\t\t\tremaining = plan_data_lack")
    a("\t\t\tfor tn in surplus_order:")
    a("\t\t\t\tif remaining <= 0:")
    a("\t\t\t\t\tbreak")
    a("\t\t\t\tqr = surplus_map[tn][\"qr\"]")
    a("\t\t\t\tsurplus = surplus_map[tn][\"surplus\"]")
    a("\t\t\t\ttake = surplus if surplus <= remaining else remaining")
    a("")
    a("\t\t\t\t# 模板：优先取同物料、同跟踪单号的明细行，取不到再退化为该物料第一行")
    a("\t\t\t\ttemplate = None")
    a("\t\t\t\tfor item in self.items:")
    a("\t\t\t\t\tif item.item_code == material_code and (item.tracking_number or \"\") == tn:")
    a("\t\t\t\t\t\ttemplate = item")
    a("\t\t\t\t\t\tbreak")
    a("\t\t\t\tif not template:")
    a("\t\t\t\t\tfor item in self.items:")
    a("\t\t\t\t\t\tif item.item_code == material_code:")
    a("\t\t\t\t\t\t\ttemplate = item")
    a("\t\t\t\t\t\t\tbreak")
    a("\t\t\t\tif not template:")
    a("\t\t\t\t\tcontinue")
    a("")
    a("\t\t\t\tnew_item_row = vars(copy.deepcopy(template))")
    a("\t\t\t\tnew_item_row[\"tracking_number\"] = tn")
    a("\t\t\t\tnew_item_row[\"planned_delivery_qty\"] = take")
    a("\t\t\t\tnew_item_row[\"allocated_actual_qty\"] = take")
    a("\t\t\t\tnew_item_row[\"over_qty\"] = True")
    a("\t\t\t\tnew_item_row[\"delivered_qty\"] = 0")
    a("\t\t\t\tnew_item_row[\"actual_delivered_qty\"] = 0")
    a("\t\t\t\tnew_item_row[\"returned_qty\"] = 0")
    a("\t\t\t\t# 箱号/箱组/外箱尺寸跟随该备货行（未装箱则为空/0），不继承模板行")
    a("\t\t\t\tnew_item_row[\"outer_carton_no\"] = qr.outer_carton_no")
    a("\t\t\t\tnew_item_row[\"carton_group\"] = qr.carton_group")
    a("\t\t\t\tnew_item_row[\"outer_carton_length\"] = qr.outer_carton_length or 0")
    a("\t\t\t\tnew_item_row[\"outer_carton_width\"] = qr.outer_carton_width or 0")
    a("\t\t\t\tnew_item_row[\"outer_carton_height\"] = qr.outer_carton_height or 0")
    a("\t\t\t\tnew_item_row[\"outer_carton_weight\"] = qr.outer_carton_weight or 0")
    a("\t\t\t\tnew_item_row[\"outer_carton_volume\"] = qr.outer_carton_volume or 0")
    a("\t\t\t\tnew_item_row.pop(\"idx\", None)  # 删除序号，避免重复")
    a("\t\t\t\tover_delivery_items.append(new_item_row)")
    a("\t\t\t\tremaining -= take")
    a("")
    a("\t\t# 将超量行追加到 items 子表末尾")
    a("\t\tfor over_item_data in over_delivery_items:")
    a("\t\t\tself.append('items', over_item_data)")
    return L


def read(path: Path) -> tuple[list[str], str, str]:
    with open(path, "r", encoding="utf-8", newline="") as f:
        raw = f.read()
    nl = "\r\n" if "\r\n" in raw[:8000] else "\n"
    return raw.split(nl), nl, raw


def find_block(lines: list[str]) -> tuple[int, int]:
    start = None
    for i, ln in enumerate(lines):
        if ln.startswith(ANCHOR_DEF):
            start = i
            break
    if start is None:
        raise SystemExit("找不到锚点 def handle_over_delivery_items")
    end = None
    for j in range(start + 1, len(lines)):
        if lines[j].startswith(NEXT_DEF_PREFIX):
            end = j
            break
    if end is None:
        raise SystemExit("找不到下一个 def 作为结束边界")
    return start, end


def main() -> None:
    ap = argparse.ArgumentParser()
    ap.add_argument("--check", action="store_true")
    ap.add_argument("--apply", action="store_true")
    ap.add_argument("--revert", action="store_true")
    args = ap.parse_args()

    if args.revert:
        if not BAK.is_file():
            raise SystemExit(f"备份不存在: {BAK}")
        shutil.copyfile(BAK, PY)
        print(f"已从 {BAK} 还原")
        return

    lines, nl, _raw = read(PY)
    start, end = find_block(lines)
    print(f"锚点命中：第 {start + 1} 行 — 下一个 def 在第 {end + 1} 行（将替换 {end - start} 行）")
    print(f"  首行: {lines[start]!r}")
    print(f"  末行: {lines[end - 1]!r}")
    print(f"  下一段首行: {lines[end]!r}")

    new_lines = new_method_lines() + [""]      # 末尾留一个空行，对齐原文件风格
    print(f"新方法 {len(new_lines)} 行")

    if args.check:
        print("\n--- 新方法预览 ---")
        for ln in new_lines[:12]:
            print(ln.replace("\t", "    "))
        print("    ...")
        print("\n--check 完成，未写入")
        return

    if args.apply:
        shutil.copyfile(PY, BAK)
        out = nl.join(lines[:start] + new_lines + lines[end:])
        with open(PY, "w", encoding="utf-8", newline="") as f:
            f.write(out)
        print(f"已写入（备份: {BAK}）")
        print("请重启：cd /home/frappe/frappe-bench && sudo -u frappe bench restart")
        return

    raise SystemExit("请指定 --check / --apply / --revert")


if __name__ == "__main__":
    main()
