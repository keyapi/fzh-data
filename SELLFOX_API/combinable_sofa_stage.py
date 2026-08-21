# -*- coding: utf-8 -*-
"""可组合扶手沙发分阶段创建：双子件套件，合成通途SKU 镜像 TJ# 组成。

登记表 4 个组合（2扶手 / 2扶手+1靠背 / 2扶手+2靠背 / 3扶手+1靠背），
全部为“无捆绑SKU”。本脚本负责计划与记录；实际创建用 sellfox_combo_ops.py。
"""
from __future__ import annotations

import json
import re

import soft_wall_stage as sws

sws.configure("可组合扶手沙发")

ARM = "KS0245-DM-75-DEEPGREY"
BACK = "KS0246-DM-75-DEEPGREY"
ARM_REF = "TT0031091K0063443"
BACK_REF = "TT0031092K0063444"


def _parse_composition(spec: str) -> list[tuple[str, int]]:
    if "2扶手模块+2个靠背模块" in spec:
        return [(ARM, 2), (BACK, 2)]
    if "2扶手模块+1个靠背模块" in spec:
        return [(ARM, 2), (BACK, 1)]
    if "3扶手模块+1个靠背模块" in spec:
        return [(ARM, 3), (BACK, 1)]
    if "2扶手模块拼接" in spec:
        return [(ARM, 2)]
    return []


def _full_sku(children: list[tuple[str, int]]) -> str:
    refs = {ARM: ARM_REF, BACK: BACK_REF}
    return "_".join(f"{refs[code]}x{qty}" for code, qty in children)


def _item_label(children: list[tuple[str, int]]) -> str:
    return " + ".join(f"{code} x{qty}" for code, qty in children)


def build_plan_rows(*, full: bool = False) -> list[dict]:
    workbook = sws.load_workbook(sws.REGISTER, read_only=True, data_only=True)
    rows_data = list(workbook["Sheet1"].iter_rows(values_only=True))
    sellfox = json.loads(sws.latest_snapshot().read_text(encoding="utf-8")).get(
        "sellfox_by_sku"
    ) or {}
    rows: dict[str, dict] = {}
    for index, raw in enumerate(rows_data[1:], start=2):
        name = sws.normalize(raw[3])
        if not name or not name.startswith("可组合扶手沙发"):
            continue
        qty_raw = raw[4]
        if qty_raw in (None, ""):
            continue
        spec = sws.normalize(raw[5])
        children = _parse_composition(spec)
        if not children:
            continue
        qty = int(qty_raw)
        sku = _full_sku(children)
        row = rows.setdefault(
            sku,
            {
                "阶段": "全部",
                "通途SKU": sku,
                "数量": qty,
                "底层EN物料": _item_label(children),
                "赛狐底层SKU": " | ".join(code for code, _ in children),
                "赛狐底层ID": " | ".join(
                    str((sellfox.get(code) or {}).get("id") or "") for code, _ in children
                ),
                "底层赛狐存在": "是",
                "物料名称": name,
                "ASIN": [],
                "店铺": [],
                "预计TJ#": "",
                "EN套件名称": "",
                "阶段状态": "待创建",
                "EN结果": "",
                "客户物料号结果": "",
                "赛狐结果": "",
                "完成时间": "",
                "备注": spec,
            },
        )
        if sws.normalize(raw[0]):
            row["ASIN"].append(sws.normalize(raw[0]))
        if sws.normalize(raw[1]):
            row["店铺"].append(sws.normalize(raw[1]))
    for row in rows.values():
        row["ASIN"] = " | ".join(sorted(set(row["ASIN"])))
        row["店铺"] = " | ".join(sorted(set(row["店铺"])))
    return list(rows.values())


sws.build_plan_rows = build_plan_rows

if __name__ == "__main__":
    raise SystemExit(sws.main())
