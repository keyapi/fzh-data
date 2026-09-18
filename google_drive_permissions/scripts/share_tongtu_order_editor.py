# -*- coding: utf-8 -*-
"""给 12 张月度通途订单表(通途订单202501-202512)添加指定邮箱的编辑(writer)权限。

用法: uv run python share_tongtu_order_editor.py [--apply] [邮箱]
  默认 dry-run。不带邮箱时从台账「识别/备注」找「现任财务负责人」。
"""
from __future__ import annotations

import sys

from tongtool_order_cost.tongtool_order_cost.gsheets import client
from sheet_ledger import kept_accounts, load_accounts

MONTHS = [f"通途订单2025{mm:02d}" for mm in range(1, 13)]
ROLE = "writer"


def parse_argv(argv: list[str]) -> dict:
    apply = False
    email = None
    for arg in argv[1:]:
        if arg == "--apply":
            apply = True
        elif arg.startswith("-"):
            raise ValueError(f"unknown flag: {arg}")
        else:
            email = arg
    return {"apply": apply, "email": email}


def _current_finance(gc) -> str:
    for a in load_accounts(gc):
        if "现任财务负责人" in a["note"]:
            return a["account"]
    raise RuntimeError("台账「账号主清单」找不到备注含「现任财务负责人」的账号")


def main() -> None:
    parsed = parse_argv(sys.argv)
    gc = client()
    if parsed["email"]:
        target = parsed["email"]
        keep = set(kept_accounts(gc))
        finance = None
        try:
            finance = _current_finance(gc)
        except RuntimeError:
            pass
        if target not in keep and target != finance:
            raise SystemExit(f"拒绝授权: {target} 不在台账在职/保留名单，也不是现任财务负责人")
    else:
        target = _current_finance(gc)
        print(f"未指定邮箱，从台账取现任财务负责人: {target}")

    print(f"目标 {target} writer on {len(MONTHS)} 张通途订单表")
    if not parsed["apply"]:
        print(">>> dry-run，未修改。加 --apply 执行（不发邮件）。")
        return

    for title in MONTHS:
        sh = gc.open(title)
        existing = [p for p in sh.list_permissions() if p.get("emailAddress") == target]
        if any(p.get("role") == ROLE for p in existing):
            print(f"[skip] {title} — 已有编辑权限")
        else:
            sh.share(target, perm_type="user", role=ROLE, notify=False)
            print(f"[ok]   {title} — 已授权 {target}")
    print("\n===== 清单 =====\n")
    for title in MONTHS:
        sh = gc.open(title)
        print(title)
        print(f"https://docs.google.com/spreadsheets/d/{sh.id}/")


if __name__ == "__main__":
    main()
