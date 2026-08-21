# -*- coding: utf-8 -*-
"""户外托盘垫分阶段创建：3 色 × 2 尺寸套装。

组成（用户确认）：
- 120x60 套装 = 坐垫 120x60 + 靠背 120x40 + 转角垫 40x40 + 装饰方靠枕 40x40
- 120x80 套装 = 坐垫 120x80 + 靠背 120x40 + 转角垫 60x40 + 装饰方靠枕 40x40
"""
from __future__ import annotations

import json

import soft_wall_stage as sws

sws.configure("户外托盘垫")

SEAT = {
    ("DEEPBLUE", "120x60"): "KS0459-KLM-120x60x16-DEEPBLUE",
    ("DEEPBLUE", "120x80"): "KS0459-KLM-120x80x16-DEEPBLUE",
    ("DEEPGREY", "120x60"): "KS0459-KLM-120x60x16-DEEPGREY",
    ("DEEPGREY", "120x80"): "KS0459-KLM-120x80x16-DEEPGREY",
    ("OFFWHITE", "120x60"): "KS0459-KLM-120x60x16-OFFWHITE",
    ("OFFWHITE", "120x80"): "KS0459-KLM-120x80x16-OFFWHITE",
}
BACK = {
    "DEEPBLUE": "KS0460-KLM-120x40x12-DEEPBLUE",
    "DEEPGREY": "KS0460-KLM-120x40x12-DEEPGREY",
    "OFFWHITE": "KS0460-KLM-120x40x12-OFFWHITE",
}
CORNER = {
    ("DEEPBLUE", "40x40"): "KS0461-KLM-40x40x12-DEEPBLUE",
    ("DEEPBLUE", "60x40"): "KS0461-KLM-60x40x12-DEEPBLUE",
    ("DEEPGREY", "40x40"): "KS0461-KLM-40x40x12-DEEPGREY",
    ("DEEPGREY", "60x40"): "KS0461-KLM-60x40x12-DEEPGREY",
    ("OFFWHITE", "40x40"): "KS0461-KLM-40x40x12-OFFWHITE",
    ("OFFWHITE", "60x40"): "KS0461-KLM-60x40x12-OFFWHITE",
}
PILLOW = {
    "DEEPBLUE": "KS0462-KLM-40x40x20-DEEPBLUE",
    "DEEPGREY": "KS0462-KLM-40x40x20-DEEPGREY",
    "OFFWHITE": "KS0462-KLM-40x40x20-OFFWHITE",
}

SKU_MAP = {
    "TT0312635K0064265-ALL": ("DEEPBLUE", "120x60"),
    "TT0312635K0064268-ALL": ("DEEPBLUE", "120x80"),
    "TT0312636K0064266-ALL": ("DEEPGREY", "120x60"),
    "TT0312636K0064269-ALL": ("DEEPGREY", "120x80"),
    "TT0312637K0064264-ALL": ("OFFWHITE", "120x60"),
    "TT0312637K0064267-ALL": ("OFFWHITE", "120x80"),
}


def _children_for(sku: str) -> list[tuple[str, int]]:
    color, size = SKU_MAP[sku]
    corner_size = "60x40" if size == "120x80" else "40x40"
    return [
        (SEAT[(color, size)], 1),
        (BACK[color], 1),
        (CORNER[(color, corner_size)], 1),
        (PILLOW[color], 1),
    ]


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
        if not name or not name.startswith("户外托盘垫"):
            continue
        sku = sws.normalize(raw[2])
        if sku not in SKU_MAP:
            continue
        children = _children_for(sku)
        row = rows.setdefault(
            sku,
            {
                "阶段": "全部",
                "通途SKU": sku,
                "数量": len(children),
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
                "备注": "套装组成已确认",
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
