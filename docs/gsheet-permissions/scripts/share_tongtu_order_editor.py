# -*- coding: utf-8 -*-
"""给 12 张月度通途订单表(通途订单202501-202512)添加指定邮箱的编辑(writer)权限。

用法: uv run python share_tongtu_order_editor.py [邮箱]
  不带邮箱时从 Google Sheet 台账「识别/备注」找"现任财务负责人"。
"""
from __future__ import annotations

import sys

from tongtool_order_cost.tongtool_order_cost.gsheets import client
from sheet_ledger import load_accounts

MONTHS = [f"通途订单2025{mm:02d}" for mm in range(1, 13)]
ROLE = "writer"


def _current_finance(gc) -> str:
    for a in load_accounts(gc):
        if "现任财务负责人" in a["note"]:
            return a["account"]
    raise RuntimeError("台账「账号主清单」找不到备注含「现任财务负责人」的账号")


def main() -> None:
    gc = client()
    if len(sys.argv) > 1:
        target = sys.argv[1]
    else:
        target = _current_finance(gc)
        print(f"未指定邮箱，从台账取现任财务负责人: {target}")
    for title in MONTHS:
        sh = gc.open(title)
        existing = [p for p in sh.list_permissions() if p.get("emailAddress") == target]
        if any(p.get("role") == ROLE for p in existing):
            print(f"[skip] {title} — 已有编辑权限")
        else:
            sh.share(target, perm_type="user", role=ROLE, notify=True)
            print(f"[ok]   {title} — 已授权 {target}")
    print("\n===== 清单 =====\n")
    for title in MONTHS:
        sh = gc.open(title)
        print(title)
        print(f"https://docs.google.com/spreadsheets/d/{sh.id}/")


if __name__ == "__main__":
    main()
