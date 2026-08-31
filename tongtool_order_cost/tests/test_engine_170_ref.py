# -*- coding: utf-8 -*-
"""1.7.0 ref 模式与 FBA 尾程跳过的单元测试。"""
from __future__ import annotations

import sys
from pathlib import Path

import pandas as pd

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))

from tongtool_order_cost.engine_170 import apply_special_rules
from tongtool_order_cost.io_loaders import load_fx_table


def _sample_orders() -> pd.DataFrame:
    return pd.DataFrame(
        [
            {
                "订单号": "A1",
                "通途SKU": "SKU-1",
                "渠道账号": "AMZBAINAUS",
                "发货区域": "美国",
                "发货仓按销售汇总分类": "USNJ分公司",
                "发货仓库": "CENTRADE",
                "发货数量": 2,
                "皮壳成本": 30.0,
                "皮壳含包装成本": 30.0,
                "皮壳不含包装成本": 28.0,
                "皮壳成本*系数": 30.0,
                "皮壳成本*数量": 60.0,
                "皮壳成本*系数*数量": 60.0,
                "绍兴二次加工成本": 0.0,
                "绍兴二次加工成本*系数": 0.0,
                "绍兴二次加工成本*数量": 0.0,
                "绍兴二次加工成本*系数*数量": 0.0,
                "二次加工成本": 40.0,
                "二次加工成本*系数": 40.0,
                "二次加工成本*数量": 80.0,
                "二次加工成本*系数*数量": 80.0,
                "头程运费金额": 5.0,
                "头程运费*数量": 10.0,
                "海外仓成本": 0.0,
                "海外仓成本*数量": 0.0,
                "运费": 12.0,
                "产品成本*系数*数量": 140.0,
                "订单总成本*系数": 162.0,
                "售价*汇率": 200.0,
                "订单利润*系数": 38.0,
                "汇率": 7.0,
            },
            {
                "订单号": "B1",
                "通途SKU": "SKU-1",
                "渠道账号": "AMZBAINAUS",
                "发货区域": "美国",
                "发货仓按销售汇总分类": "FBA-US",
                "发货仓库": "FBA",
                "发货数量": 1,
                "皮壳成本": 30.0,
                "皮壳含包装成本": 30.0,
                "皮壳不含包装成本": 28.0,
                "皮壳成本*系数": 30.0,
                "皮壳成本*数量": 30.0,
                "皮壳成本*系数*数量": 30.0,
                "绍兴二次加工成本": 0.0,
                "绍兴二次加工成本*系数": 0.0,
                "绍兴二次加工成本*数量": 0.0,
                "绍兴二次加工成本*系数*数量": 0.0,
                "二次加工成本": 40.0,
                "二次加工成本*系数": 40.0,
                "二次加工成本*数量": 40.0,
                "二次加工成本*系数*数量": 40.0,
                "头程运费金额": 5.0,
                "头程运费*数量": 5.0,
                "海外仓成本": 0.0,
                "海外仓成本*数量": 0.0,
                "运费": 9.0,
                "产品成本*系数*数量": 70.0,
                "订单总成本*系数": 84.0,
                "售价*汇率": 100.0,
                "订单利润*系数": 16.0,
                "汇率": 7.0,
            },
        ]
    )


def _sample_rules() -> pd.DataFrame:
    return pd.DataFrame(
        [
            {
                "运营人员": None,
                "发货仓按销售汇总分类": None,
                "发货区域": None,
                "渠道账号不含国家": None,
                "渠道账号": "AMZBAINAUS",
                "通途SKU": "SKU-1",
                "销售额系数": None,
                "皮壳成本系数": None,
                "绍兴二次加工成本系数": None,
                "二次加工成本系数": None,
                "头程运费系数": None,
                "海外仓成本系数": None,
                "尾程运费系数": None,
                "执行开始时间": "2026-06-01",
                "执行结束时间": None,
                "收款币种": "USD",
                "发货数量1皮壳成本*系数参考值": 8.0,
                "发货数量1绍兴二次加工成本*系数参考值": 0.0,
                "发货数量1二次加工成本*系数参考值": 0.0,
                "发货数量1头程运费参考值": 2.7,
                "发货数量1海外仓成本参考值": 0.0,
                "发货数量1订单尾程运费": 9.0,
                "excel_row": 2,
            }
        ]
    )


def test_ref_writes_rmb_unit_times_qty():
    orders = _sample_orders()
    rules = _sample_rules()
    fx, src = load_fx_table(fx_usd=7.0)
    result = apply_special_rules(
        orders, rules, "202606", fx, fx_source=src, verbose=False
    )
    df = result.orders
    # non-FBA row: qty=2, 皮壳 8*7=56, *qty=112
    assert abs(float(df.loc[0, "皮壳成本"]) - 56.0) < 1e-6
    assert abs(float(df.loc[0, "皮壳成本*系数*数量"]) - 112.0) < 1e-6
    assert abs(float(df.loc[0, "二次加工成本*系数*数量"]) - 0.0) < 1e-6
    assert abs(float(df.loc[0, "头程运费*数量"]) - 2.7 * 7 * 2) < 1e-6
    # 尾程仅非 FBA
    assert abs(float(df.loc[0, "运费"]) - 9.0 * 7 * 2) < 1e-6
    # FBA 行：皮壳/头程改了，运费保持 9
    assert abs(float(df.loc[1, "皮壳成本"]) - 56.0) < 1e-6
    assert abs(float(df.loc[1, "运费"]) - 9.0) < 1e-6
    assert result.meta["n_applied"] == 1
    assert result.meta["n_affected_rows"] == 2
    assert len(result.change_events) > 0
    # 手算事件：皮壳数量列 delta
    ev = result.change_events
    shell = ev[(ev["order_index"] == 0) & (ev["column"] == "皮壳成本*系数*数量")]
    assert len(shell) == 1
    assert abs(float(shell.iloc[0]["after"]) - 112.0) < 1e-6
    assert abs(float(shell.iloc[0]["before"]) - 60.0) < 1e-6


def test_unmatched_rule_recorded():
    orders = _sample_orders()
    rules = _sample_rules()
    rules.loc[0, "通途SKU"] = "NO-SUCH"
    fx, src = load_fx_table(fx_usd=7.0)
    result = apply_special_rules(
        orders, rules, "202606", fx, fx_source=src, verbose=False
    )
    assert result.meta["n_applied"] == 0
    assert result.meta["n_unmatched"] == 1


def test_fba_negative_lastmile_applies():
    """FBA 尾程参考值为负数时写入 运费 = ref × 汇率 × 数量。"""
    orders = _sample_orders()
    rules = _sample_rules()
    rules.loc[0, "发货数量1订单尾程运费"] = -5.59
    fx, src = load_fx_table(fx_usd=7.0)
    result = apply_special_rules(
        orders, rules, "202606", fx, fx_source=src, verbose=False
    )
    df = result.orders
    expected_fba = -5.59 * 7.0 * 1
    expected_non_fba = -5.59 * 7.0 * 2
    assert abs(float(df.loc[1, "运费"]) - expected_fba) < 1e-6
    assert abs(float(df.loc[0, "运费"]) - expected_non_fba) < 1e-6


def test_fba_zero_lastmile_still_skipped():
    """FBA 尾程参考值 0 仍跳过，不覆盖已有运费。"""
    orders = _sample_orders()
    rules = _sample_rules()
    rules.loc[0, "发货数量1订单尾程运费"] = 0.0
    fx, src = load_fx_table(fx_usd=7.0)
    result = apply_special_rules(
        orders, rules, "202606", fx, fx_source=src, verbose=False
    )
    df = result.orders
    assert abs(float(df.loc[1, "运费"]) - 9.0) < 1e-6
    assert abs(float(df.loc[0, "运费"]) - 0.0) < 1e-6
