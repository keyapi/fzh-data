# -*- coding: utf-8 -*-
"""沙发支撑垫阶段记录：复用 soft_wall_stage 框架，SKU 统一小写 pcs。

EN 已存在 TJ#KS0156x2-001 / x3-001 / x3-002，本脚本只负责计划与记录；
实际补客户物料号和赛狐组合用 sellfox_combo_ops.py 现有命令。
"""
from __future__ import annotations

import soft_wall_stage as sws

sws.configure("沙发支撑垫")
_orig_build_plan_rows = sws.build_plan_rows


def build_plan_rows(*, full: bool = False) -> list[dict]:
    rows = _orig_build_plan_rows(full=full)
    canonical: dict[str, dict] = {}
    for row in rows:
        row["通途SKU"] = sws.canonical_ref_code(row["通途SKU"])
        canonical.setdefault(row["通途SKU"], row)
    return list(canonical.values())


sws.build_plan_rows = build_plan_rows

if __name__ == "__main__":
    raise SystemExit(sws.main())
