# -*- coding: utf-8 -*-
"""逗号组合沙发分阶段创建：三模块组合套件，无捆绑SKU 合成通途SKU。

登记表 2 行（灰黄色 / 蓝色），组成 = 左扶手 + 右扶手 + 靠背，各 1 个。
合成通途SKU 镜像 TJ# 组成：{右扶手基码}x1_{靠背基码}x1_{左扶手基码}x1。
实际创建用 sellfox_combo_ops.py（en-create / register-customer-code / sync-combos）。
"""
from __future__ import annotations

import json

import soft_wall_stage as sws

sws.configure("逗号组合沙发")

COLOR_TO_MODULES = {
    "灰黄色": {
        "左扶手": "KS0379-SZSRB-76x90x66-GRAYISHYELLOW",
        "右扶手": "KS0369-SZSRB-76x90x66-GRAYISHYELLOW",
        "靠背": "KS0378-SZSRB-76x90x66-GRAYISHYELLOW",
    },
    "蓝": {
        "左扶手": "KS0379-MDR-76x90x66-BLUE",
        "右扶手": "KS0369-MDR-76x90x66-BLUE",
        "靠背": "KS0378-MDR-76x90x66-BLUE",
    },
}
ITEM_REF = {
    "KS0379-SZSRB-76x90x66-GRAYISHYELLOW": "TT0031230K0064055",
    "KS0369-SZSRB-76x90x66-GRAYISHYELLOW": "TT0031230K0064049",
    "KS0378-SZSRB-76x90x66-GRAYISHYELLOW": "TT0031230K0064052",
    "KS0379-MDR-76x90x66-BLUE": "TT0031230K0064053",
    "KS0369-MDR-76x90x66-BLUE": "TT0031230K0064047",
    "KS0378-MDR-76x90x66-BLUE": "TT0031230K0064050",
}


def _children_from_name(name: str, spec: str) -> list[tuple[str, int]]:
    color = ""
    for token in ("灰黄色", "蓝"):
        if token in name:
            color = token
            break
    modules = COLOR_TO_MODULES.get(color)
    if not modules:
        return []
    order = ("右扶手", "靠背", "左扶手")  # 与 EN 预览 TJ# 组成一致
    parts = [p.strip() for p in str(spec or "").split("+") if p.strip()]
    return [(modules[p], 1) for p in order if p in parts]


def _label(children: list[tuple[str, int]]) -> str:
    return " + ".join(f"{code} x{qty}" for code, qty in children)


def _full_sku(children: list[tuple[str, int]]) -> str:
    return "_".join(f"{ITEM_REF[code]}x{qty}" for code, qty in children)


def build_plan_rows(*, full: bool = False) -> list[dict]:
    workbook = sws.load_workbook(sws.REGISTER, read_only=True, data_only=True)
    rows_data = list(workbook["Sheet1"].iter_rows(values_only=True))
    sellfox = json.loads(sws.latest_snapshot().read_text(encoding="utf-8")).get(
        "sellfox_by_sku"
    ) or {}
    rows: dict[str, dict] = {}
    for index, raw in enumerate(rows_data[1:], start=2):
        name = sws.normalize(raw[3])
        if not name or not name.startswith("逗号组合沙发"):
            continue
        spec = sws.normalize(raw[5])
        children = _children_from_name(name, spec)
        if not children:
            continue
        sku = _full_sku(children)
        bottom_codes = [code for code, _ in children]
        bottom_ids = [str((sellfox.get(code) or {}).get("id") or "") for code in bottom_codes]
        row = rows.setdefault(
            sku,
            {
                "阶段": "全部",
                "通途SKU": sku,
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
                "备注": "无捆绑SKU，按模块基码合成；组成见套件列",
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
