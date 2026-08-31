# -*- coding: utf-8 -*-
"""复古造型大体量沙发分阶段创建：四模块组合套件。

登记表 1 行：TT0031241K0064076-ALL，组成 = 右扶手 + 无扶手 + 脚踏 + 左扶手带延长。
"""
from __future__ import annotations

import json

import soft_wall_stage as sws

sws.configure("复古造型大体量沙发")

MODULES = {
    "右扶手": "KS0387-MTXCTTM-100x100x85-BROWNLIGHTBEIGE",
    "无扶手": "KS0391-MTXCTTM-100x80x75-BROWNLIGHTBEIGE",
    "脚踏": "KS0393-MTXCTTM-80x80x45-BROWNLIGHTBEIGE",
    "左扶手带延长": "KS0392-MTXCTTM-120x180x85-BROWNLIGHTBEIGE",
}
REF = {
    "KS0387-MTXCTTM-100x100x85-BROWNLIGHTBEIGE": "TT0031241K0064076",
    "KS0391-MTXCTTM-100x80x75-BROWNLIGHTBEIGE": "TT0031241K0064077",
    "KS0393-MTXCTTM-80x80x45-BROWNLIGHTBEIGE": "TT0031241K0064079",
    "KS0392-MTXCTTM-120x180x85-BROWNLIGHTBEIGE": "TT0031241K0064078",
}


def _children_from_spec(spec: str) -> list[tuple[str, int]]:
    parts = [p.strip() for p in str(spec or "").replace("复古造型大体量沙发-", "").split("，") if p.strip()]
    return [(MODULES[p], 1) for p in parts if p in MODULES]


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
        if not name or not name.startswith("复古造型大体量沙发"):
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
