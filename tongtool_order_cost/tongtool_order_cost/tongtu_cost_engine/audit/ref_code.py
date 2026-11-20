# -*- coding: utf-8 -*-
"""SKU / ref_code 解析审计（Phase 0）。

只做**只读统计**：订单行覆盖、作废单、缺 EN 物料、缺物料组、
ref_code 是否一对一（若提供 Item.ref_code 快照）。不做任何合并决策。
"""
from __future__ import annotations

from pathlib import Path
from typing import Optional

import pandas as pd

SUFFIX_CATS = ("-COVER", "-FOAM", "-PPCOTTON")


def _suffix_cat(sku: str) -> str:
    s = str(sku).upper()
    for c in SUFFIX_CATS:
        if c in s:
            return c.strip("-").title()
    if s.startswith("TJ#"):
        return "套件"
    return "普通"


def audit_skus(
    items_csv: Path,
    flags_csv: Path,
    groups_csv: Path,
    ref_map_csv: Optional[Path] = None,
    month: Optional[str] = None,
) -> str:
    d = pd.read_csv(items_csv, dtype=str, low_memory=False)
    flags = pd.read_csv(flags_csv, dtype=str, low_memory=False)
    groups = pd.read_csv(groups_csv, dtype=str, low_memory=False)

    if month:
        mm = str(month).replace('-', '')[:6]
        ym = f'{mm[:4]}-{mm[4:]}'
        d = d[d['despatch_complete_time'].astype(str).str.slice(0, 7) == ym].copy()
    d = d.merge(flags[["order_id_code", "invalid", "suspended"]], on="order_id_code", how="left")
    d["invalid"] = d["invalid"].fillna("0")
    gmap = dict(zip(groups["name"], groups["item_group"]))
    d["item_group"] = d["erp_item_code"].map(gmap)

    total_lines = len(d)
    invalid_lines = int((d["invalid"] == "1").sum())
    valid = d[d["invalid"] != "1"]
    no_item = int(valid["erp_item_code"].isna().sum())
    no_group = int(valid["erp_item_code"].notna().sum() - valid["item_group"].notna().sum())

    lines = ["# SKU / ref_code 解析审计", ""]
    lines.append(f"- 订单行：{total_lines}（作废 {invalid_lines}，有效 {len(valid)}）")
    lines.append(f"- 有效行缺 EN 物料：{no_item}")
    lines.append(f"- 有效行缺物料组：{no_group}")
    lines.append(f"- 有效物料数：{valid['erp_item_code'].nunique()}")
    lines.append("")

    cat = valid["tongtool_sku"].map(_suffix_cat).value_counts()
    lines += ["## SKU 后缀分布（有效行）", "", "| 类别 | 行数 |", "|---|---:|"]
    for k, v in cat.items():
        lines.append(f"| {k} | {int(v)} |")

    if ref_map_csv is not None and Path(ref_map_csv).exists():
        ref = pd.read_csv(ref_map_csv, dtype=str, low_memory=False)
        # 约定列：name / ref_code
        ref = ref.dropna(subset=["name"])
        dup = ref[ref.duplicated("name", keep=False)]
        one_to_many = (
            ref.groupby("name")["ref_code"].nunique().loc[lambda s: s > 1]
            if "ref_code" in ref.columns else pd.Series(dtype=int)
        )
        unmapped = valid[~valid["erp_item_code"].isin(set(ref["name"]))]["erp_item_code"].dropna().unique()
        lines += ["", "## ref_code 解析", ""]
        lines.append(f"- 重复 Item 行：{len(dup)}")
        lines.append(f"- 一对多 ref_code 的 Item：{len(one_to_many)}")
        lines.append(f"- 未映射到的有效物料：{len(unmapped)}")
        if len(one_to_many):
            lines.append(f"- 一对多样例：{list(one_to_many.index[:10])}")
        if len(unmapped):
            lines.append(f"- 未映射样例：{list(unmapped[:10])}")
    else:
        lines += ["", "## ref_code 解析", "", "- 未提供 Item.ref_code 快照（Phase 1 接入 EN 后补齐）"]

    lines.append("")
    lines.append("> 本报告只统计，不做合并；歧义项在 Phase 1 一律阻断。")
    return "\n".join(lines) + "\n"
