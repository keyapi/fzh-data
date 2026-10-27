# -*- coding: utf-8 -*-
"""政策对账用例：维度齐全、数字取自输入、memo 声称不矛盾且非承诺。"""

from __future__ import annotations

import pandas as pd

from supply_netting.policy_reconcile import (DIMENSIONS, STATUS, build, write_memo)


def policy_csv(tmp_path):
    frame = pd.DataFrame([
        dict(单位="个", 选项="保守（控库存）", 服务档=0.90, 目标倍数=1.0,
             fill_rate=0.7561, **{"CSL(需求加权)": 0.7628}, 平均库存=24062.8),
        dict(单位="个", 选项="均衡（推荐倾向）", 服务档=0.95, 目标倍数=1.5,
             fill_rate=0.9235, **{"CSL(需求加权)": 0.9063}, 平均库存=43403.6),
        dict(单位="个", 选项="服务优先", 服务档=0.98, 目标倍数=2.0,
             fill_rate=0.9635, **{"CSL(需求加权)": 0.9648}, 平均库存=65697.5),
        dict(单位="套", 选项="保守（控库存）", 服务档=0.90, 目标倍数=1.0,
             fill_rate=1.0, **{"CSL(需求加权)": 1.0}, 平均库存=24.8),
    ])
    path = tmp_path / "policy.csv"
    frame.to_csv(path, index=False, encoding="utf-8-sig")
    return path


def test_dimensions_cover_required_axes(tmp_path):
    table, _, _ = build(policy_csv(tmp_path))
    axes = set(table["口径维度"])
    for required in ("指标定义", "母集", "提前期", "目标口径", "基线", "库存分母", "样本差异（关键）"):
        assert required in axes
    assert len(table) == len(DIMENSIONS)


def test_numbers_come_from_input_and_only_piece_unit(tmp_path):
    _, numbers, meta = build(policy_csv(tmp_path))
    v2_rows = numbers[numbers["口径"].str.contains("保守|均衡|服务优先")]
    assert len(v2_rows) == 3                          # 只取「个」，不含套的单键行
    assert "0.9235" in v2_rows.iloc[1]["实际服务"]
    assert "43,404" in v2_rows.iloc[1]["库存代价"]
    assert meta["base_inventory"] == 24062.8


def test_memo_states_no_contradiction_and_no_commitment(tmp_path):
    table, numbers, meta = build(policy_csv(tmp_path))
    memo = tmp_path / "memo.md"
    write_memo(memo, numbers, meta, "2026-10-28T00:00:00+08:00",
               dict(policy="p.csv", policy_sha="abc"))
    text = memo.read_text(encoding="utf-8")
    assert "不矛盾" in text
    assert "预测误差" in text and "观测销售" in text
    assert "都不是 95% 承诺" in text
    assert "2.4–4.6×" in text and "8.8–40×" in text
    assert STATUS in text
    assert "不改 r6 / h180" in text
