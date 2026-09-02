# -*- coding: utf-8 -*-
"""从 Google Sheet 权限台账读账号列表（唯一的账号数据源，避免在脚本里硬编码邮箱 PII）。

台账「账号主清单」worksheet 列：
  [0]状态  [1]账号  [2]识别/备注  [3]处理方式  [4]当前文件数
  状态 = 自己 / SA / 在职 / 离职 / 待确认
  处理方式 = 不取消 / 保留 / 已清理 / 已清(遗留)

供 audit / cleanup / build 脚本按需取「离职账号 / 在职账号 / 全部账号」。
"""
from __future__ import annotations

import gspread

SHEET_ID = "1TTVVHQOe5VCmdLZynGFAKXSPUVIvtlB6kOOqgszIqD0"
MASTER_WS = "账号主清单"


def load_accounts(gc: gspread.Client) -> list[dict]:
    """返回账号主清单所有行：{account, status, handling, note}。"""
    sh = gc.open_by_key(SHEET_ID)
    ws = sh.worksheet(MASTER_WS)
    rows = ws.get_all_values()
    if len(rows) < 2:
        return []
    out = []
    for r in rows[1:]:
        if len(r) < 2 or not r[1]:
            continue
        out.append({
            "account": r[1].strip(),
            "status": (r[0] if len(r) > 0 else "").strip(),
            "note": (r[2] if len(r) > 2 else "").strip(),
            "handling": (r[3] if len(r) > 3 else "").strip(),
        })
    return out


def removed_accounts(gc: gspread.Client) -> list[str]:
    """「处理方式」含 已清 或 状态=离职 的账号 → 用于 cleanup 移除。"""
    return [a["account"] for a in load_accounts(gc)
            if a["status"] == "离职" or a["handling"].startswith("已清")]


def kept_accounts(gc: gspread.Client) -> list[str]:
    """「处理方式=保留」或 状态=在职 的账号 → 用于 audit 关注列表等。"""
    return [a["account"] for a in load_accounts(gc)
            if a["status"] == "在职" or a["handling"] == "保留"]


def all_accounts(gc: gspread.Client) -> list[str]:
    """全部非自己/非SA账号。"""
    return [a["account"] for a in load_accounts(gc)
            if a["status"] not in ("自己", "SA")]
