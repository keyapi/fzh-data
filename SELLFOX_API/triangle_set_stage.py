# -*- coding: utf-8 -*-
"""三角有扣套装分阶段创建：三角靠枕 + 50cm 圆枕组合。

登记表 13 个套装：三角靠枕（涤麻/全涤宽条绒/荷兰绒）+ 1/2 个 50cm 圆枕。
EN 底层：三角靠枕 KS0001-*；50cm 圆枕 KS0260-*-50-*（三角带圆柱靠枕-圆柱）。
实际创建用 sellfox_combo_ops.py（en-create / register-customer-code / sync-combos）。
"""
from __future__ import annotations

import json
import re

import soft_wall_stage as sws

sws.configure("三角有扣")

TRIANGLE = {
    ("涤麻", "黄色", 100): "KS0001-DM-100-YELLOW",
    ("涤麻", "黄色", 140): "KS0001-DM-140-YELLOW",
    ("涤麻", "黄色", 153): "KS0001-DM-153-YELLOW",
    ("涤麻", "黄色", 200): "KS0001-DM-200-YELLOW",
    ("涤麻", "草绿色", 138): "KS0001-DM-140-GRASSGREEN",  # EN 无 138，用 140 近似
    ("涤麻", "草绿色", 153): "KS0001-DM-153-GRASSGREEN",
    ("涤麻", "草绿色", 194): "KS0001-DM-194-GRASSGREEN",
    ("全涤宽条绒", "白色", 153): "KS0001-QDKTR-153-WHITE",
    ("全涤宽条绒", "白色", 200): "KS0001-QDKTR-200-WHITE",
    ("全涤宽条绒", "桃色", 153): "KS0001-QDKTR-153-PEACH",
    ("全涤宽条绒", "桃色", 200): "KS0001-QDKTR-200-PEACH",
    ("荷兰绒", "米白色", 153): "KS0001-HLR-153-OFFWHITE",
    ("荷兰绒", "米白色", 200): "KS0001-HLR-200-OFFWHITE",
}
CYLINDER = {
    ("涤麻", "黄色"): "KS0260-DM-50-YELLOW",
    ("涤麻", "草绿色"): "KS0260-DM-50-GRASSGREEN",
    ("全涤宽条绒", "白色"): "KS0260-TR-50-OFFWHITE",  # EN 无全涤宽条绒 50 圆枕，用条绒同色
    ("全涤宽条绒", "桃色"): "KS0260-TR-50-PEACH",
    ("荷兰绒", "米白色"): "KS0260-HLR-50-OFFWHITE",
}

REAL_SKU = {
    "TT0001325K0010860-all-T50": ("涤麻", "黄色", 200, 2),
    "TT0001325K0010857-all-50": ("涤麻", "黄色", 100, 1),
    "TT0001325K0011165-all-100": ("涤麻", "黄色", 140, 1),
    "TT0000668K0063814-all-T50": ("全涤宽条绒", "白色", 200, 2),
    "TT0000669K0063813-all-T50": ("全涤宽条绒", "桃色", 200, 2),
    "TT0000671K0063724-all-T50": ("荷兰绒", "米白色", 153, 2),
    "TT0000671K0063728-all-T50": ("荷兰绒", "米白色", 200, 2),
    "CEN961NLinen-SageGreen-194-all-50": ("涤麻", "草绿色", 194, 2),
}


def _children_for(fabric: str, color: str, size: int, rounds: int) -> list[tuple[str, int]]:
    triangle = TRIANGLE[(fabric, color, size)]
    cylinder = CYLINDER[(fabric, color)]
    return [(triangle, 1), (cylinder, rounds)]


def _label(children: list[tuple[str, int]]) -> str:
    return " + ".join(f"{code} x{qty}" for code, qty in children)


def _synthetic_sku(children: list[tuple[str, int]]) -> str:
    return "_".join(f"{code}x{qty}" for code, qty in children)


def _parse_name(name: str) -> tuple[str, str, int, int] | None:
    fabric = next((f for f in ("全涤宽条绒", "荷兰绒", "涤麻") if f in name), "")
    color = next((c for c in ("草绿色", "米白色", "桃色", "黄色", "白色") if c in name), "")
    size_m = re.search(r"(\d+)\s*[cC][mM]", name)
    rounds_m = re.search(r"(\d+)\s*个50cm圆枕", name)
    if not (fabric and color and size_m and rounds_m):
        return None
    return fabric, color, int(size_m.group(1)), int(rounds_m.group(1))


def build_plan_rows(*, full: bool = False) -> list[dict]:
    workbook = sws.load_workbook(sws.REGISTER, read_only=True, data_only=True)
    rows_data = list(workbook["Sheet1"].iter_rows(values_only=True))
    sellfox = json.loads(sws.latest_snapshot().read_text(encoding="utf-8")).get(
        "sellfox_by_sku"
    ) or {}
    rows: dict[str, dict] = {}
    for index, raw in enumerate(rows_data[1:], start=2):
        name = sws.normalize(raw[3])
        if "三角有扣" not in name or "圆枕套装" not in name:
            continue
        sku = sws.normalize(raw[2])
        if sku in REAL_SKU:
            fabric, color, size, rounds = REAL_SKU[sku]
        else:
            parsed = _parse_name(name)
            if not parsed:
                continue
            fabric, color, size, rounds = parsed
        children = _children_for(fabric, color, size, rounds)
        if not children:
            continue
        full_sku = sku if sku != "无捆绑SKU" else _synthetic_sku(children)
        bottom_codes = [code for code, _ in children]
        bottom_ids = [str((sellfox.get(code) or {}).get("id") or "") for code in bottom_codes]
        note = "138cm 用 EN 140cm 近似" if size == 138 else ""
        if sku == "无捆绑SKU":
            note = (note + " | " if note else "") + "无捆绑SKU，按 EN 物料码合成客户码"
        row = rows.setdefault(
            full_sku,
            {
                "阶段": "全部",
                "通途SKU": full_sku,
                "数量": len(children),
                "底层EN物料": _label(children),
                "赛狐底层SKU": " | ".join(bottom_codes),
                "赛狐底层ID": " | ".join(bottom_ids),
                "底层赛狐存在": "是" if all(bottom_ids) else "否",
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
                "备注": note,
            },
        )
        row["ASIN"].append(sws.normalize(raw[0]))
        row["店铺"].append(sws.normalize(raw[1]))
    for row in rows.values():
        row["ASIN"] = " | ".join(sorted(set(row["ASIN"])))
        row["店铺"] = " | ".join(sorted(set(row["店铺"])))
    return list(rows.values())


sws.build_plan_rows = build_plan_rows

if __name__ == "__main__":
    raise SystemExit(sws.main())
