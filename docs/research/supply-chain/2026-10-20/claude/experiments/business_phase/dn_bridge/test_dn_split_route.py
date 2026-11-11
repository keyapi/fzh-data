#!/usr/bin/env python
# -*- coding: utf-8 -*-
"""dn_split.route_state_of 回归测试（空状态串 bug）。

Run:  uv run python docs/research/supply-chain/2026-10-20/claude/experiments/business_phase/dn_bridge/test_dn_split_route.py
或:   uv run python -m pytest <本文件> -q

核心断言：**空串 / None / 缺失状态 => 未知**，绝不落回"已签收/已入仓"。
"""
from __future__ import annotations

import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))

import dn_split as D          # noqa: E402

CASES = [
    # (输入状态列表, 期望, 说明)
    ([""], "未知", "空串（DN-26-00112 的真实情况）"),
    ([], "未知", "完全没有号"),
    ([None], "未知", "None"),
    (["   "], "未知", "纯空白"),
    (["已签收", ""], "未知", "一真一空：缺一个号的状态就不能判整单签收"),
    (["已签收"], "已签收/已入仓", "正常签收"),
    (["已入仓", "已上传POD"], "已签收/已入仓", "多号全签收"),
    (["已签收", "已离港"], "部分签收", "真·部分签收"),
    (["已离港", "已订舱"], "在途", "全在途"),
    (["已离港", ""], "未知", "在途 + 空串 => 未知"),
    (["某种没见过的状态"], "未知", "未知枚举值"),
]


def test_empty_status_is_unknown():
    """回归断言（301/SC04 发现的 bug）：空状态串必须是 unknown。"""
    assert D.route_state_of([""]) == "未知"


def test_all_cases():
    for statuses, want, why in CASES:
        got = D.route_state_of(statuses)
        assert got == want, f"{statuses} -> {got}，期望 {want}（{why}）"


def main() -> int:
    test_empty_status_is_unknown()
    test_all_cases()
    for statuses, want, why in CASES:
        print(f"PASS {str(statuses):32s} -> {want:8s}  ({why})")
    print(f"ALL PASS ({len(CASES) + 1} assertions)")
    return 0


if __name__ == "__main__":
    try:
        sys.exit(main())
    except AssertionError as exc:
        print(f"FAIL: {exc}")
        sys.exit(1)
