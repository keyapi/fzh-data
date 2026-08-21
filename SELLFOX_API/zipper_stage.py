# -*- coding: utf-8 -*-
"""拉链款分阶段创建：登记表 → EN/赛狐快照 → 合成通途SKU → 阶段记录。

基于 soft_wall_stage.py 的通用框架，只覆盖 build_plan_rows：
登记表里拉链款全部是“无捆绑SKU”，按 EN 底层物料 + 数量合成唯一通途SKU。
"""
from __future__ import annotations

import json
import re
from pathlib import Path

import soft_wall_stage as sws

sws.configure("拉链款")

SUPPORT_GROUPS = (
    "皮壳#",
    "内胆#",
    "重量模板#",
    "套件#",
    "绍兴",
    "波兰",
    "美东",
    "美中",
    "包装",
)


def _norm_size(value: str) -> str:
    match = re.search(r"(\d+)\s*[*x×]\s*(\d+)\s*[*x×]\s*(\d+)", value)
    if match:
        return f"{match.group(1)}x{match.group(2)}x{match.group(3)}"
    return re.sub(r"[^0-9]", "", value)


def _color_norm(value: str) -> str:
    value = str(value or "").strip().replace("色", "").replace(" ", "").lower()
    aliases = {
        "米白": "白",
        "象牙白": "象牙白",
        "可可榛子": "可可榛子",
        "无烟煤灰": "无烟煤灰",
        "腮红": "腮红",
        "草绿": "草绿",
        "深蓝": "深蓝",
        "姜黄": "黄",
        "灰": "灰",
        "黑": "黑",
    }
    return aliases.get(value, value)


def _parse_register_name(name: str) -> dict | None:
    tokens = [token for token in name.replace("拉链款", "").split(" ") if token]
    if not tokens:
        return None
    fill = "海绵" if "海绵" in tokens[0] else "PP棉"
    fabric = next((token for token in tokens if token in ("荷兰绒", "涤麻")), "")
    color_raw = ""
    size = ""
    for index, token in enumerate(tokens):
        if "*" in token or "x" in token.lower() or "×" in token:
            size = _norm_size(token)
            if index > 0 and not color_raw:
                color_raw = tokens[index - 1]
    return {
        "fill": fill,
        "fabric": fabric,
        "color": _color_norm(color_raw),
        "size": size,
    }


def _snapshot_base_items() -> tuple[list[dict], dict[str, dict]]:
    snapshot = json.loads(sws.latest_snapshot().read_text(encoding="utf-8"))
    items: list[dict] = []
    for item in snapshot.get("en_items") or []:
        group = str(item.get("item_group") or "")
        name = str(item.get("item_name") or "")
        if group.startswith(SUPPORT_GROUPS):
            continue
        if not item.get("variant_of"):
            continue
        if sws.KEYWORD not in name or "50x22x55" not in name:
            continue
        parts = name.split("-")
        if len(parts) < 5:
            continue
        items.append(
            {
                "item_code": str(item.get("item_code") or ""),
                "item_name": name,
                "fill": "海绵" if "海绵" in name else "PP棉",
                "fabric": parts[2],
                "color": _color_norm(parts[-1]),
                "size": _norm_size(parts[3]),
                "refs": [
                    str(c.get("ref_code") or "")
                    for c in (item.get("customer_items") or [])
                ],
                "disabled": item.get("disabled"),
            }
        )
    sellfox = snapshot.get("sellfox_by_sku") or {}
    return items, sellfox


def _base_ref(item: dict, items: list[dict]) -> tuple[str, str]:
    plain = [
        ref
        for ref in item["refs"]
        if ref and not re.search(r"-(?i:cover|foam)$", ref)
    ]
    if plain:
        return plain[0], "直接基码"
    stripped = next(
        (
            re.sub(r"-(?i:cover|foam)$", "", ref)
            for ref in item["refs"]
            if ref and re.search(r"-(?i:cover|foam)$", ref)
        ),
        "",
    )
    if stripped:
        return stripped, "-Cover去尾"
    for other in items:
        if other["item_code"] == item["item_code"]:
            continue
        if (
            other["fabric"] == item["fabric"]
            and other["color"] == item["color"]
            and other["size"] == item["size"]
        ):
            ref, how = _base_ref(other, items)
            if ref:
                return ref, "同款另一填充借用"
    return "", "缺基码"


def _fill_tag(item_code: str) -> str:
    if item_code.startswith("KS0340"):
        return "PP"
    if item_code.startswith("KS0342"):
        return "FOAM"
    return ""


def build_plan_rows(*, full: bool = False) -> list[dict]:
    items, sellfox = _snapshot_base_items()
    rows: dict[str, dict] = {}
    for index, asin, shop, sku, name, qty in sws.read_register_rows():
        if not name or sws.KEYWORD not in name:
            continue
        try:
            qty_int = int(qty)
        except (TypeError, ValueError):
            continue
        parsed = _parse_register_name(name)
        if not parsed:
            continue
        matched = [
            item
            for item in items
            if item["fill"] == parsed["fill"]
            and item["fabric"] == parsed["fabric"]
            and item["color"] == parsed["color"]
            and item["size"] == parsed["size"]
        ]
        if not matched:
            continue
        item = matched[0]
        base_ref, how = _base_ref(item, items)
        tag = _fill_tag(item["item_code"])
        if not base_ref or not tag:
            continue
        full_sku = f"{base_ref}-{item['item_code']}-{qty_int}pcs"
        row = rows.setdefault(
            full_sku,
            {
                "阶段": "测试",
                "通途SKU": full_sku,
                "数量": qty_int,
                "底层EN物料": item["item_code"],
                "赛狐底层SKU": item["item_code"],
                "赛狐底层ID": str((sellfox.get(item["item_code"]) or {}).get("id") or ""),
                "底层赛狐存在": "是" if sellfox.get(item["item_code"]) else "否",
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
                "备注": how,
            },
        )
        row["ASIN"].append(asin)
        row["店铺"].append(shop)
    for row in rows.values():
        row["ASIN"] = " | ".join(sorted(set(row["ASIN"])))
        row["店铺"] = " | ".join(sorted(set(row["店铺"])))
    return list(rows.values())


sws.build_plan_rows = build_plan_rows

if __name__ == "__main__":
    raise SystemExit(sws.main())
