# -*- coding: utf-8 -*-
"""仓库配置覆盖审计：Tongtu Shipping Warehouse 42 行覆盖情况。"""
from __future__ import annotations

from pathlib import Path


def audit_warehouse_map(wh_tsv: Path) -> str:
    """输入 `name<TAB>warehouse_classification`，输出 Markdown 审计。"""
    rows: list[tuple[str, str]] = []
    for line in Path(wh_tsv).read_text(encoding="utf-8-sig", errors="ignore").splitlines():
        if not line.strip():
            continue
        parts = line.split("\t")
        if len(parts) < 2:
            continue
        name, cls = parts[0].strip(), parts[1].strip()
        if name == "name" and cls == "warehouse_classification":
            continue
        rows.append((name, cls))

    by_cls: dict[str, list[str]] = {}
    for name, cls in rows:
        by_cls.setdefault(cls, []).append(name)

    lines = ["# 仓库配置覆盖审计", "", f"- 配置行数：{len(rows)}", ""]
    lines += ["| 分类 | 仓库数 | 代表仓库 |", "|---|---:|---|"]
    for cls, names in sorted(by_cls.items()):
        lines.append(f"| {cls} | {len(names)} | {', '.join(sorted(names)[:3])} |")

    known = set(by_cls)
    expected = {"美国FBA", "欧洲FBA", "日本FBA", "英国FBA", "美国海外仓",
                "USNJ美东分公司", "USTX美中分公司", "PL波兰分公司"}
    missing = sorted(expected - known)
    lines += ["", "## 缺口/待确认", ""]
    lines.append(f"- 预期分类缺失：{missing or '无'}")
    lines.append("- 欧洲/加拿大海外仓、绍兴自发货：报告无对应配置行（未证实），切成本前需业务确认。")
    lines.append("- FBA 仓加工成本应为 0（processing_cost_name=NULL）；海外仓复用美中 USTX。")
    return "\n".join(lines) + "\n"
