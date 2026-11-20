# -*- coding: utf-8 -*-
"""FBA 规则范围门禁（F01/F02，整改 U-B B1）。

- 默认 ``scope=sku``：账号与 SKU 必填，空 SKU 不再隐式变成"整账号"。
- 账号级规则必须显式 ``规则范围=account`` + ``approve_account_scope=True``。
- 缺筛选列 / 空账号 / 非法日期 / 冲突规则 / 重叠规则 一律 FAIL。
"""
from __future__ import annotations

import pandas as pd
import pytest

from fba_adjust import (
    FbaRuleError,
    load_fba_rules,
    process_fba_orders,
    rule_hits_frame,
    validate_fba_rules,
)


def _fba_df() -> pd.DataFrame:
    return pd.DataFrame(
        {
            "渠道账号": ["AMZAUS", "AMZAUS", "AMZAUS", "AMZBUS", "AMZBUS"],
            "sku": ["SKU1", "SKU2", "SKU3", "SKU1", "SKU9"],
            "amount-description": ["FBAPerUnitFulfillmentFee"] * 5,
            "amount": [10.0, 20.0, 30.0, 40.0, 50.0],
            "汇率": [7.0] * 5,
        }
    )


class _FakeWS:
    def __init__(self, rows):
        self._rows = rows

    def get_all_values(self):
        return self._rows


class _FakeSh:
    def __init__(self, rows):
        self._rows = rows

    def worksheet(self, _name):
        return _FakeWS(self._rows)


class _FakeGc:
    def __init__(self, rows):
        self._rows = rows

    def open_by_key(self, _id):
        return _FakeSh(self._rows)


RULE_HEADER = ["渠道账号", "平台SKU", "执行开始时间", "执行结束时间", "规则范围"]


def _rules_gc(rows: list[list[str]]) -> _FakeGc:
    return _FakeGc([RULE_HEADER, *rows])


# ---------------------------------------------------------------- 正常路径


def test_rule_matches_only_listed_sku():
    rules = pd.DataFrame({"渠道账号": ["AMZAUS"], "平台SKU": ["SKU1"], "当月是否执行": ["是"]})
    out = process_fba_orders(rules, _fba_df())
    by = {(a, s): v for a, s, v in zip(out["渠道账号"], out["sku"], out["amount"])}
    assert by[("AMZAUS", "SKU1")] == 0.0  # 命中规则
    assert by[("AMZAUS", "SKU2")] == 20.0  # 同账号其它 SKU 不受影响
    assert by[("AMZAUS", "SKU3")] == 30.0
    assert by[("AMZBUS", "SKU9")] == 50.0
    assert (out["调整前-后amount"] > 0).sum() == 1


def test_rule_sku_whitespace_insensitive():
    rules = pd.DataFrame({"渠道账号": ["AMZAUS"], "平台SKU": ["SKU 2"], "当月是否执行": ["是"]})
    out = process_fba_orders(rules, _fba_df())
    by = {(a, s): v for a, s, v in zip(out["渠道账号"], out["sku"], out["amount"])}
    assert by[("AMZAUS", "SKU2")] == 0.0
    assert by[("AMZAUS", "SKU1")] == 10.0


def test_empty_rules_keep_unadjusted_rows():
    """无规则 → 输出未调整原 FBA 行，绝不返回空表冒充"没有 FBA"。"""
    out = process_fba_orders(pd.DataFrame(), _fba_df())
    assert len(out) == 5
    assert (out["调整前-后amount"] == 0).all()
    assert out["amount"].tolist() == [10.0, 20.0, 30.0, 40.0, 50.0]


# ---------------------------------------------------------- 账号级规则（显式）


def test_account_level_rule_requires_explicit_scope_and_approval():
    rules = pd.DataFrame({"渠道账号": ["AMZBUS"], "平台SKU": [None], "当月是否执行": ["是"]})
    with pytest.raises(FbaRuleError, match="空 SKU 不得隐式按账号匹配"):
        process_fba_orders(rules, _fba_df())


def test_account_scope_without_finance_approval_fails():
    rules = pd.DataFrame(
        {"渠道账号": ["AMZBUS"], "平台SKU": [""], "规则范围": ["account"], "当月是否执行": ["是"]}
    )
    with pytest.raises(FbaRuleError, match="未获财务批准"):
        process_fba_orders(rules, _fba_df())


def test_account_scope_with_approval_hits_only_that_account():
    rules = pd.DataFrame(
        {"渠道账号": ["AMZBUS"], "平台SKU": [""], "规则范围": ["account"], "当月是否执行": ["是"]}
    )
    out = process_fba_orders(rules, _fba_df(), approve_account_scope=True)
    b = out[out["渠道账号"] == "AMZBUS"]
    assert (b["amount"] == 0).all()
    a = out[out["渠道账号"] == "AMZAUS"]
    assert (a["amount"] > 0).all()  # 只有批准的 A 口径账号被清零，不碰别的账号


def test_account_scope_with_sku_fails():
    rules = pd.DataFrame(
        {"渠道账号": ["AMZBUS"], "平台SKU": ["SKU9"], "规则范围": ["account"], "当月是否执行": ["是"]}
    )
    problems = validate_fba_rules(rules, approve_account_scope=True)
    assert any("账号级规则不能带 SKU" in p for p in problems)


# ---------------------------------------------------------------- 空值/缺列


def test_blank_account_rule_fails():
    rules = pd.DataFrame({"渠道账号": [""], "平台SKU": ["SKU1"], "当月是否执行": ["是"]})
    with pytest.raises(FbaRuleError, match="渠道账号 为空"):
        process_fba_orders(rules, _fba_df())


def test_missing_sku_column_fails():
    rules = pd.DataFrame({"渠道账号": ["AMZAUS"], "当月是否执行": ["是"]})
    problems = validate_fba_rules(rules)
    assert any("缺列" in p for p in problems)


def test_missing_detail_filter_column_fails():
    detail = _fba_df().drop(columns=["sku"])
    rules = pd.DataFrame({"渠道账号": ["AMZAUS"], "平台SKU": ["SKU1"], "当月是否执行": ["是"]})
    with pytest.raises(FbaRuleError, match="明细缺筛选列"):
        process_fba_orders(rules, detail)


# ---------------------------------------------------------------- 日期（F01）


def test_invalid_rule_date_fails():
    gc = _rules_gc([["AMZAUS", "SKU1", "待定", "", ""]])
    with pytest.raises(FbaRuleError, match="不是合法年月"):
        load_fba_rules(gc, bucket_name="账期20260804-20260903")


def test_rule_start_after_end_fails():
    gc = _rules_gc([["AMZAUS", "SKU1", "2026-09", "2026-08", ""]])
    with pytest.raises(FbaRuleError, match="晚于"):
        load_fba_rules(gc, bucket_name="账期20260804-20260903")


def test_rule_date_window_selects_execution():
    gc = _rules_gc(
        [
            ["AMZAUS", "SKU1", "2026-07", "2026-08", ""],
            ["AMZAUS", "SKU2", "2026-09", "", ""],
        ]
    )
    rules = load_fba_rules(gc, bucket_name="账期20260804-20260903")
    executed = rules.loc[rules["当月是否执行"] == "是", "平台SKU"].tolist()
    assert executed == ["SKU1"]


# ---------------------------------------------------------------- 冲突/重叠


def test_conflicting_duplicate_rules_fail_before_dedupe():
    gc = _rules_gc(
        [
            ["AMZAUS", "SKU1", "2026-08", "2026-09", ""],
            ["AMZAUS", "SKU1", "2026-07", "2026-09", ""],
        ]
    )
    with pytest.raises(FbaRuleError, match="规则冲突"):
        load_fba_rules(gc, bucket_name="账期20260804-20260903")


def test_identical_duplicate_rules_are_deduped():
    gc = _rules_gc(
        [
            ["AMZAUS", "SKU1", "2026-08", "2026-09", ""],
            ["AMZAUS", "SKU1", "2026-08", "2026-09", ""],
        ]
    )
    rules = load_fba_rules(gc, bucket_name="账期20260804-20260903")
    assert len(rules) == 1
    assert rules.attrs["deduped"] == 1


def test_account_and_sku_rules_overlap_fails():
    """同账号既有账号级又有 SKU 级规则 → 重复扣减口径不明，默认 FAIL。"""
    gc = _rules_gc(
        [
            ["AMZAUS", "", "2026-08", "2026-09", "account"],
            ["AMZAUS", "SKU1", "2026-08", "2026-09", "sku"],
        ]
    )
    with pytest.raises(FbaRuleError, match="规则重叠"):
        load_fba_rules(gc, bucket_name="账期20260804-20260903", approve_account_scope=True)


def test_overlap_allowed_only_by_whitelist():
    rules = pd.DataFrame(
        {
            "渠道账号": ["AMZAUS", "AMZAUS"],
            "平台SKU": ["", "SKU1"],
            "规则范围": ["account", "sku"],
            "当月是否执行": ["是", "是"],
        }
    )
    problems = validate_fba_rules(
        rules,
        approve_account_scope=True,
        allowed_overlaps={("AMZAUS", "SKU1")},
    )
    assert problems == []


# ---------------------------------------------------------------- 命中统计


def test_rule_hits_report_includes_zero_hit_rows():
    rules = pd.DataFrame(
        {
            "渠道账号": ["AMZAUS", "AMZAUS"],
            "平台SKU": ["SKU1", "SKU404"],
            "当月是否执行": ["是", "是"],
        }
    )
    hits = rule_hits_frame(
        rules.rename(columns={"平台SKU": "sku"}), _fba_df(), ["渠道账号", "sku"]
    )
    assert hits["hit_rows"].tolist() == [1, 0]
    assert hits.loc[hits["sku"] == "SKU404", "hit_rows"].iloc[0] == 0
    assert hits.loc[hits["sku"] == "SKU1", "hit_amount"].iloc[0] == 10.0


def test_process_orders_exposes_rule_hits():
    rules = pd.DataFrame({"渠道账号": ["AMZAUS"], "平台SKU": ["SKU1"], "当月是否执行": ["是"]})
    out = process_fba_orders(rules, _fba_df())
    hits = out.attrs["rule_hits"]
    assert hits["hit_rows"].tolist() == [1]


# ---------------------------------------------------------------- 数值/汇率


def test_bad_amount_fails_not_zeroed():
    detail = _fba_df()
    detail["amount"] = detail["amount"].astype(object)
    detail.loc[0, "amount"] = "abc"
    rules = pd.DataFrame({"渠道账号": ["AMZAUS"], "平台SKU": ["SKU1"], "当月是否执行": ["是"]})
    with pytest.raises(FbaRuleError, match="非数值"):
        process_fba_orders(rules, detail)


def test_missing_fx_fails_not_zeroed():
    detail = _fba_df()
    detail.loc[3, "汇率"] = None
    rules = pd.DataFrame({"渠道账号": ["AMZAUS"], "平台SKU": ["SKU1"], "当月是否执行": ["是"]})
    with pytest.raises(FbaRuleError, match="汇率"):
        process_fba_orders(rules, detail)
