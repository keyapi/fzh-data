# -*- coding: utf-8 -*-
"""通途仓库归一规则（GS 历史仓名 → 当前仓）

依据用户 2026-10-21 说明：
- FZH-DANEEY-成品仓 / -半成品仓 / -皮壳仓库 / 美中-FZH-DANEEY-皮壳仓库 都属「美中 DANEEY 仓」；
- FZHPoland-finished 属「波兰仓」；
- 北美之路 / 枫筝海外仓 / 休斯顿 / 海外仓美西/美中备用仓 = 海外仓，但目前不用；
- 海外仓美中仓库备用仓 可能算美中 Daneey（不确定，标 pending）。
"""
from __future__ import annotations

EXPLICIT = {
    "FZH-DANEEY-成品仓": ("美中-FZH-DANEEY", "component->main"),
    "FZH-DANEEY-半成品仓": ("美中-FZH-DANEEY", "component->main"),
    "FZH-DANEEY-皮壳仓库": ("美中-FZH-DANEEY", "component->main"),
    "美中-FZH-DANEEY-皮壳仓库": ("美中-FZH-DANEEY", "component->main"),
    "FZHPoland-finished": ("波兰-FZHPoland-covers", "finished->main"),
}

UNUSED = {
    "北美之路-LA01", "北美之路-NJ02",
    "枫筝海外仓-多伦多-代发仓", "枫筝海外仓-温哥华-代发仓",
    "休斯顿1号仓", "休斯顿1号备用仓库",
    "海外仓美西仓库备用仓",
}

PENDING = {"海外仓美中仓库备用仓", "扬州仓库"}

PREFIXES = ("美东-", "美中-", "波兰-")


def classify(name: str, current_set: set[str]) -> tuple[str | None, str]:
    """返回 (当前仓名 or None, 分类)。"""
    if not name:
        return (None, "empty")
    if name in EXPLICIT:
        return EXPLICIT[name]
    if name in UNUSED:
        return (None, "unused")
    if name in current_set:
        return (name, "current")
    for p in PREFIXES:
        if p + name in current_set:
            return (p + name, "renamed")
    if name in PENDING:
        return (None, "pending")
    return (None, "unknown")
