# -*- coding: utf-8 -*-
"""弧形流苏沙发分阶段创建：单件整沙发组合。

登记表 1 个唯一通途SKU TT0031255K0064131-ALL，
EN 底层只有整沙发 KS0402-KYR-193x108x80-BLUE，赛狐 ID 3701950。
"""
from __future__ import annotations

import json

import soft_wall_stage as sws

sws.configure("弧形流苏沙发")

BASE_ITEM = "KS0402-KYR-193x108x80-BLUE"
BASE_REF = "TT0031255K0064131"


def build_plan_rows(*, full: bool = False) -> list[dict]:
    workbook = sws.load_workbook(sws.REGISTER, read_only=True, data_only=True)
    rows_data = list(workbook["Sheet1"].iter_rows(values_only=True))
    sellfox = json.loads(sws.latest_snapshot().read_text(encoding="utf-8")).get(
        "sellfox_by_sku"
    ) or {}
    rows: dict[str, dict] = {}
    for index, raw in enumerate(rows_data[1:], start=2):
        name = sws.normalize(raw[3])
        if not name or not name.startswith("弧形流苏沙发"):
            continue
        sku = sws.normalize(raw[2])
        if not sku:
            continue
        row = rows.setdefault(
            sku,
            {
                "阶段": "全部",
                "通途SKU": sku,
                "数量": 1,
                "底层EN物料": f"{BASE_ITEM} x1",
                "赛狐底层SKU": BASE_ITEM,
                "赛狐底层ID": str((sellfox.get(BASE_ITEM) or {}).get("id") or ""),
                "底层赛狐存在": "是" if sellfox.get(BASE_ITEM) else "否",
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
                "备注": f"整沙发单件；基码 {BASE_REF}",
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
