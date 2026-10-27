# -*- coding: utf-8 -*-
"""政策选项表用例：三档 × 单位分列、增量口径、UOM 不跨单位合计、memo 边界。"""

from __future__ import annotations

import pandas as pd
import pytest

from supply_netting.policy_options import (STATUS, TIERS, UOM_CONFIRMATION, build_options,
                                           write_memo)


def by_key_frame():
    rows = []
    cells = [(90, 0.90, 1.0, 0.6, 0.5), (90, 0.95, 1.5, 0.9, 0.8),
             (90, 0.98, 2.0, 0.97, 0.95), (60, 0.95, 1.5, 0.92, 0.85),
             (60, 0.98, 2.0, 0.975, 0.96)]
    for uom, keys in (("个", 3), ("套", 1)):
        for lead, level, mult, fill, csl in cells:
            for index in range(keys):
                demand = 100.0
                rows.append(dict(lead_days=lead, service_level=level, target_multiplier=mult,
                                 单位=uom, SKU=f"{uom}-S{index}", 仓库="W",
                                 窗口需求=demand, 满足=demand * fill,
                                 缺货量=demand * (1 - fill), 缺货天数=int(demand * (1 - fill)),
                                 平均库存=1000.0 * mult + index, CSL=csl, fill_rate=fill,
                                 补货周期数=13))
    return pd.DataFrame(rows)


def _write(tmp_path):
    path = tmp_path / "by_key.csv"
    by_key_frame().to_csv(path, index=False)
    return path


def build(tmp_path):
    return build_options(tmp_path / "unused.csv", _write(tmp_path))


def test_three_tiers_times_two_units(tmp_path):
    frame, meta = build(tmp_path)
    assert len(frame) == len(TIERS) * 2
    assert set(frame["单位"]) == {"个", "套"}
    assert set(frame["状态"]) == {STATUS}
    assert meta["status"] == STATUS


def test_no_cross_uom_sum_and_single_key_units_are_flagged(tmp_path):
    frame, _ = build(tmp_path)
    # 每个 (单位, 选项) 只有一行，且键数来自该单位自身，不是两单位相加
    grouped = frame.groupby(["单位", "选项"]).size()
    assert (grouped == 1).all()
    piece = frame[(frame["单位"] == "个") & (frame["选项"] == "保守（控库存）")].iloc[0]
    assert piece["涉及键数"] == 3
    single = frame[frame["单位"] == "套"].iloc[0]
    assert single["涉及键数"] == 1
    assert "单键样本" in single["UOM备注"]


def test_fill_rate_and_increment_per_unit(tmp_path):
    frame, _ = build(tmp_path)
    by = frame.set_index(["单位", "选项"])
    assert by.loc[("个", "保守（控库存）"), "fill_rate"] == pytest.approx(0.6)
    assert by.loc[("个", "均衡（推荐倾向）"), "fill_rate"] == pytest.approx(0.9)
    # 增量以同单位 1× 为基线：×1.5 的库存 (1500,1501,1502) - (1000,1001,1002) = 1,500
    assert by.loc[("个", "均衡（推荐倾向）"), "相对同交期同单位1倍的增量"] == pytest.approx(1500.0)


def test_lead_time_lever_is_per_unit(tmp_path):
    _, meta = build(tmp_path)
    units = {item["单位"] for item in meta["lead_time_lever"]}
    assert units == {"个", "套"}
    assert meta["uom_policy"]["confirmation"] == UOM_CONFIRMATION


def test_memo_states_uom_and_boundaries(tmp_path):
    frame, meta = build(tmp_path)
    memo = tmp_path / "memo.md"
    write_memo(memo, frame, meta, "2026-10-28T00:00:00+08:00",
               dict(sensitivity="a.csv", by_key="b.csv", sensitivity_sha="x", by_key_sha="y"))
    text = memo.read_text(encoding="utf-8")
    assert "观测销售路径模拟" in text and "不是承诺" in text and "不是采购量" in text
    assert UOM_CONFIRMATION in text
    assert "没有跨单位合计" in text
    assert STATUS in text and "不改 r6 / h180" in text
    # 必须与 frepple 对话知识清单对齐，不能给相反印象
    assert "与既有结论对齐" in text
    assert "8.8–40×" in text and "0.63–0.84" in text
    assert "POLICY-RECONCILE" in text
