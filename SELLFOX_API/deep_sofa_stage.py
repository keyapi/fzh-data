# -*- coding: utf-8 -*-
"""深卧单人沙发椅分阶段创建：双色组合套件，通途SKU 已存在。

登记表 3 个组合：
- JONYHBBChair-WWhite+RRed  → 暖白 + 茜红
- JONYHBBChair-RRed+DBlue   → 茜红 + 深蓝
- JONYHBBChair-WWhite+DBlue → 暖白 + 深蓝
"""
from __future__ import annotations

import json

import soft_wall_stage as sws

sws.configure("深卧单人沙发椅")

COLOR_TO_ITEM = {
    "白色": "KS0483-FHXYR-80x85x67-WARMWHITE",
    "红色": "KS0483-FHXYR-80x85x67-ALIZARINRED",
    "蓝色": "KS0483-FHXYR-80x85x67-DEEPBLUE",
}
ITEM_REF = {
    "KS0483-FHXYR-80x85x67-WARMWHITE": "TT0312681K0064363",
    "KS0483-FHXYR-80x85x67-ALIZARINRED": "TT0312681K0064361",
    "KS0483-FHXYR-80x85x67-DEEPBLUE": "TT0312681K0064362",
}


def _children_from_spec(spec: str) -> list[tuple[str, int]]:
    colors = [part.strip() for part in str(spec or "").split("，") if part.strip()]
    return [(COLOR_TO_ITEM[color], 1) for color in colors if color in COLOR_TO_ITEM]


def _label(children: list[tuple[str, int]]) -> str:
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
        if not name or not name.startswith("深卧单人沙发椅"):
            continue
        sku = sws.normalize(raw[2])
        if not sku:
            continue
        children = _children_from_spec(raw[5])
        if not children:
            continue
        row = rows.setdefault(
            sku,
            {
                "阶段": "全部",
                "通途SKU": sku,
                "数量": raw[4],
                "底层EN物料": _label(children),
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
                "备注": sws.normalize(raw[5]),
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
