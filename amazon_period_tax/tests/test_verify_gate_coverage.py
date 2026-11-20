# -*- coding: utf-8 -*-
"""E2.2 V01/V02：verify 覆盖面与 NaN/非有限值门禁。

覆盖 gate_remediation_plan_20261120.md U-E2 / E2.2：
- 五张主表（含两张比例表）+ Tax/附加费源表逐表缺失都 FAIL；
- 缺列 FAIL，不能靠「列不存在 → sum=0」蒙混；
- 非空非法 / NaN / Inf 单独 FAIL，NaN 差值不能当通过；
- 显式 --exchange-month 与桶账期月不一致拒绝；
- 每行账期月校验（不只桶账期月）；
- FBA 两表：声明适用必须成对，单缺/缺 FBA 都 FAIL。
"""
from __future__ import annotations

import pandas as pd
import pytest

import phase3_gsheet
import verify_period

BUCKET = "账期20260804-20260903"
PERIOD = "20260804-20260903"
YYYYMM = "202608"

MAIN = PERIOD
ORIG = f"{PERIOD}原始"
RMB = f"人民币{PERIOD}"
RATE_RECEIPT = f"{PERIOD}收款比例收款归属"
RATE_STAFF = f"{PERIOD}收款比例运营人员"
TAX = f"Tax{YYYYMM}"
SEP = f"附加费{YYYYMM}"
FBA_SUMMARY = f"{PERIOD}{verify_period.FBA_SUMMARY_SUFFIX}"
FBA_STAFF = f"{PERIOD}{verify_period.FBA_STAFF_SUFFIX}"


def _frames() -> dict[str, pd.DataFrame]:
    return {
        MAIN: pd.DataFrame(
            {
                "渠道账号": ["AMZA"],
                "应收金额_人民币": [100.0],
                "销售额_人民币": [200.0],
                "收款费用累加人民币": [0.0],
            }
        ),
        ORIG: pd.DataFrame(
            {
                "账期日期": ["2026-08-11"],
                "审批状态": ["完成"],
                "审批结果": ["同意"],
                "渠道账号": ["AMZA"],
                "汇率": [7.0],
                "应收金额": [14.285714],
                "销售额": [28.571429],
                "应收金额_人民币": [100.0],
                "销售额_人民币": [200.0],
                "渠道账号正确提交次数": [1],
            }
        ),
        RMB: pd.DataFrame(
            {
                "渠道账号": ["AMZA"],
                "应收金额_人民币": [100.0],
                "销售额_人民币": [200.0],
                "Tax amount人民币": [10.0],
                "附加费累加人民币": [2.0],
            }
        ),
        RATE_RECEIPT: pd.DataFrame(
            {"收款归属": ["X"], "应收金额_人民币": [100.0], "销售额_人民币": [200.0], "平均收款比例": [0.5]}
        ),
        RATE_STAFF: pd.DataFrame({"运营人员": ["Y"], "销售额_人民币": [200.0], "应收金额_人民币": [100.0]}),
        TAX: pd.DataFrame({"渠道账号": ["AMZA"], "Tax amount人民币": [10.0]}),
        SEP: pd.DataFrame({"渠道账号": ["AMZA"], "附加费累加人民币": [2.0]}),
    }


@pytest.fixture
def sheet_store(monkeypatch):
    """把 read_sheet_df 变成以 worksheet 名为键的假表；打开表用哨兵对象。"""
    store = _frames()
    monkeypatch.setattr(verify_period, "read_sheet_df", lambda gc, sh, name: store.get(name, pd.DataFrame()))
    monkeypatch.setattr(verify_period, "open_additional_fee_tax_spreadsheet", lambda gc: object())
    monkeypatch.setattr(phase3_gsheet, "open_phase3_spreadsheet", lambda gc: object())
    return store


def _failed(checks):
    return [c for c in checks if not c.ok]


def _names(checks):
    return " | ".join(c.name + ":" + c.detail for c in checks if not c.ok)


def _set_cell(store, sheet, column, value):
    """把某格改成任意类型（float 列直接赋字符串会触发 pandas 类型错误）。"""
    df = store[sheet].copy()
    df[column] = df[column].astype(object)
    df.loc[0, column] = value
    store[sheet] = df


def test_all_good_passes(sheet_store):
    checks = verify_period.check_phase3(object(), bucket=BUCKET)
    assert _failed(checks) == [], _names(checks)
    assert len(checks) >= 10


@pytest.mark.parametrize(
    "missing",
    [MAIN, ORIG, RMB, RATE_RECEIPT, RATE_STAFF, TAX, SEP],
    ids=["主表", "原始", "人民币", "比例收款归属", "比例运营人员", "Tax源表", "附加费源表"],
)
def test_each_required_sheet_missing_fails(sheet_store, missing):
    sheet_store.pop(missing)
    checks = verify_period.check_phase3(object(), bucket=BUCKET)
    failed = _failed(checks)
    assert failed, f"缺 {missing} 应该 FAIL"
    assert any("存在" in c.name for c in failed)


@pytest.mark.parametrize(
    "sheet, column",
    [
        (ORIG, "账期日期"),
        (RMB, "Tax amount人民币"),
        (MAIN, "销售额_人民币"),
        (RATE_RECEIPT, "平均收款比例"),
        (RATE_STAFF, "运营人员"),
        (TAX, "渠道账号"),
        (SEP, "渠道账号"),
    ],
)
def test_missing_columns_fail(sheet_store, sheet, column):
    sheet_store[sheet] = sheet_store[sheet].drop(columns=[column])
    checks = verify_period.check_phase3(object(), bucket=BUCKET)
    assert any("列齐全" in c.name for c in _failed(checks)), _names(checks)


def test_non_empty_invalid_value_fails(sheet_store):
    _set_cell(sheet_store, TAX, "Tax amount人民币", "abc")
    checks = verify_period.check_phase3(object(), bucket=BUCKET)
    assert any("非空非法" in c.name for c in _failed(checks)), _names(checks)


def test_nan_string_is_not_a_pass(sheet_store):
    # 「NaN」既不能解析成有限数，sum 也会变 NaN；旧实现 abs(nan)<=TOL → False 侥幸，
    # 但 0.0 兜底会把缺数据当 0。这里两侧都放 NaN 字符串，必须 FAIL。
    _set_cell(sheet_store, RMB, "Tax amount人民币", "NaN")
    _set_cell(sheet_store, TAX, "Tax amount人民币", "NaN")
    checks = verify_period.check_phase3(object(), bucket=BUCKET)
    assert any("非有限" in c.name or "非空非法" in c.name for c in _failed(checks)), _names(checks)


def test_inf_value_fails(sheet_store):
    _set_cell(sheet_store, RMB, "应收金额_人民币", "Inf")
    checks = verify_period.check_phase3(object(), bucket=BUCKET)
    assert any("非有限" in c.name or "非空非法" in c.name for c in _failed(checks)), _names(checks)


def test_per_row_period_month_mismatch_fails(sheet_store):
    sheet_store[ORIG].loc[0, "账期日期"] = "2026-09-01"  # 桶是 8 月账期
    checks = verify_period.check_phase3(object(), bucket=BUCKET)
    assert any("每行账期月" in c.name for c in _failed(checks)), _names(checks)


def test_ratio_table_sum_mismatch_fails(sheet_store):
    sheet_store[RATE_STAFF].loc[0, "销售额_人民币"] = 199.0
    checks = verify_period.check_phase3(object(), bucket=BUCKET)
    assert any("比例表" in c.name for c in _failed(checks)), _names(checks)


def test_fba_pair_missing_when_required_fails(sheet_store):
    checks = verify_period.check_phase3(object(), bucket=BUCKET, require_fba=True)
    assert any("FBA 两表成对" in c.name for c in _failed(checks)), _names(checks)


def test_fba_only_one_present_fails(sheet_store):
    sheet_store[FBA_SUMMARY] = pd.DataFrame({"渠道账号": ["AMZA"], verify_period.FBA_DELTA_RMB: [5.0]})
    checks = verify_period.check_phase3(object(), bucket=BUCKET)
    assert any("FBA 两表成对" in c.name for c in _failed(checks)), _names(checks)


def test_fba_both_present_and_valid_passes(sheet_store):
    sheet_store[FBA_SUMMARY] = pd.DataFrame({"渠道账号": ["AMZA"], verify_period.FBA_DELTA_RMB: [5.0]})
    sheet_store[FBA_STAFF] = pd.DataFrame({"运营人员": ["Y"], "FBA费用_人民币": [5.0]})
    checks = verify_period.check_phase3(object(), bucket=BUCKET, require_fba=True)
    assert _failed(checks) == [], _names(checks)


def test_fba_nonfinite_fails(sheet_store):
    sheet_store[FBA_SUMMARY] = pd.DataFrame({"渠道账号": ["AMZA"], verify_period.FBA_DELTA_RMB: ["NaN"]})
    sheet_store[FBA_STAFF] = pd.DataFrame({"运营人员": ["Y"], "FBA费用_人民币": [5.0]})
    checks = verify_period.check_phase3(object(), bucket=BUCKET, require_fba=True)
    assert any("FBA 两表列/数值" in c.name for c in _failed(checks)), _names(checks)


# ---------------------------------------------------------------- run_checks 级


def test_explicit_exchange_month_mismatch_rejected(sheet_store):
    checks = verify_period.run_checks(object(), bucket=BUCKET, do_tax=False, exchange_month="202607")
    failed = _failed(checks)
    assert failed and "exchange-month" in failed[0].name, _names(checks)


def test_exchange_month_default_from_bucket_ok(sheet_store):
    checks = verify_period.run_checks(object(), bucket=BUCKET, do_tax=False)
    assert _failed(checks) == [], _names(checks)


def test_tax_and_phase3_both_skipped_fails():
    checks = verify_period.run_checks(object(), bucket=BUCKET, do_tax=False, do_phase3=False)
    assert len(checks) == 1 and not checks[0].ok


def test_finite_close_rejects_nan_and_inf():
    assert verify_period.finite_close(1.0, 1.005)
    assert not verify_period.finite_close(float("nan"), float("nan"))
    assert not verify_period.finite_close(float("inf"), float("inf"))
    assert not verify_period.finite_close(None, 0.0)
