# -*- coding: utf-8 -*-
"""FBA 读桶/B2 门禁（F03/F04，整改 U-B B2）。

- FBA 只消费 E1 同批源文件总账；failed/mismatch/no-date/out-of-period/needs-review/
  缺 FX/数值异常/未知账号 全部进 ``info["errors"]`` → 写前门禁阻断。
- 生成失败**不得**返回旧表/空表冒充成功；请求写 FBA 但没有效结果必须 FAIL。
"""
from __future__ import annotations

from pathlib import Path

import pandas as pd
import pytest


def _raw_fba() -> pd.DataFrame:
    return pd.DataFrame(
        {
            "父文件夹名": ["甲", "甲"],
            "子文件夹名": ["A", "B"],
            "渠道账号": ["AMZAUS", "AMZAUS"],
            "sku": ["SKU1", "SKU1"],
            "currency": ["USD", "USD"],
            "amount": [10.0, 20.0],
            "amount-description": ["FBAPerUnitFulfillmentFee", "Storage Fee"],
        }
    )


FX = pd.DataFrame({"收款币种": ["USD"], "汇率": [7.0]})
MASTER = pd.DataFrame({"渠道账号": ["AMZAUS"], "运营人员": ["甲"]})


def _rules(rows: list[dict]) -> pd.DataFrame:
    frame = pd.DataFrame(rows)
    frame["当月是否执行"] = "是"
    return frame


def _install(monkeypatch, *, raw, stats=None, rules=None):
    import fba_adjust
    import read_amz_txt

    stats = stats or {}
    captured = {}

    def fake_reader(bucket_dir, *, repair_dir=None, stats_out=None, write_repairs=True):
        captured["write_repairs"] = write_repairs
        if stats_out is not None:
            stats_out.update({"publish_blockers": [], "files_failed": 0, "rows_mismatch": 0})
            stats_out.update(stats)
        return (raw.copy() if raw is not None else pd.DataFrame()), ["OK fake"]

    monkeypatch.setattr(read_amz_txt, "read_bucket_amz_txts", fake_reader)
    monkeypatch.setattr(fba_adjust, "load_fba_rules", lambda gc, *, bucket_name, **kw: rules)
    return captured


def _build(monkeypatch, **kwargs):
    from phase3_merge import build_fba_summary

    _install(monkeypatch, **kwargs)
    return build_fba_summary(
        None,
        bucket="账期20260804-20260903",
        bucket_dir=Path("unused"),
        df_exchange_rate=FX,
        df_account=MASTER,
    )


# ------------------------------------------------------- 读桶异常 → errors


def test_files_failed_blocks(monkeypatch):
    summary, info = _build(
        monkeypatch,
        raw=_raw_fba(),
        stats={"files_failed": 1, "publish_blockers": ["FAIL=1"]},
        rules=_rules([{"渠道账号": "AMZAUS", "平台SKU": "SKU1"}]),
    )
    assert summary is None
    assert any("FAIL=1" in e for e in info["errors"])


def test_rows_mismatch_blocks(monkeypatch):
    summary, info = _build(
        monkeypatch,
        raw=_raw_fba(),
        stats={"rows_mismatch": 2, "publish_blockers": ["rows_mismatch=2"]},
        rules=_rules([{"渠道账号": "AMZAUS", "平台SKU": "SKU1"}]),
    )
    assert summary is None
    assert any("rows_mismatch" in e for e in info["errors"])


def test_needs_review_blocks(monkeypatch):
    summary, info = _build(
        monkeypatch,
        raw=_raw_fba(),
        stats={"files_needs_review": 1, "publish_blockers": ["NEEDS-REVIEW=1"]},
        rules=_rules([{"渠道账号": "AMZAUS", "平台SKU": "SKU1"}]),
    )
    assert summary is None
    assert any("NEEDS-REVIEW" in e for e in info["errors"])


def test_out_of_period_blocks(monkeypatch):
    summary, info = _build(
        monkeypatch,
        raw=_raw_fba(),
        stats={"publish_blockers": ["OUT-OF-PERIOD=1"]},
        rules=_rules([{"渠道账号": "AMZAUS", "平台SKU": "SKU1"}]),
    )
    assert summary is None
    assert any("OUT-OF-PERIOD" in e for e in info["errors"])


def test_no_period_date_blocks(monkeypatch):
    summary, info = _build(
        monkeypatch,
        raw=_raw_fba(),
        stats={"publish_blockers": ["NO-PERIOD-DATE=1"]},
        rules=_rules([{"渠道账号": "AMZAUS", "平台SKU": "SKU1"}]),
    )
    assert summary is None
    assert any("NO-PERIOD-DATE" in e for e in info["errors"])


def test_missing_fx_blocks(monkeypatch):
    raw = _raw_fba()
    raw["currency"] = ["JPY", "JPY"]  # 汇率表没有 JPY
    summary, info = _build(monkeypatch, raw=raw, rules=_rules([{"渠道账号": "AMZAUS", "平台SKU": "SKU1"}]))
    assert summary is None
    assert any("缺汇率" in e for e in info["errors"])


def test_bad_amount_blocks(monkeypatch):
    raw = _raw_fba()
    raw["amount"] = raw["amount"].astype(object)
    raw.loc[0, "amount"] = "tbd"
    summary, info = _build(monkeypatch, raw=raw, rules=_rules([{"渠道账号": "AMZAUS", "平台SKU": "SKU1"}]))
    assert summary is None
    assert any(("非数值" in e) or ("金额非法" in e) for e in info["errors"])


def test_unknown_account_blocks(monkeypatch):
    raw = _raw_fba()
    raw["渠道账号"] = ["AMZUNKNOWN", "AMZUNKNOWN"]
    summary, info = _build(monkeypatch, raw=raw, rules=_rules([{"渠道账号": "AMZUNKNOWN", "平台SKU": "SKU1"}]))
    assert summary is None
    assert any("不在当期主表" in e for e in info["errors"])


def test_empty_source_blocks(monkeypatch):
    summary, info = _build(monkeypatch, raw=None, rules=pd.DataFrame())
    assert summary is None
    assert any("源 txt 为空" in e for e in info["errors"])


# ------------------------------------------------------- 正常/边界


def test_no_fba_rows_is_empty_not_error(monkeypatch):
    raw = _raw_fba()
    raw["amount-description"] = ["Tax", "Tax"]
    summary, info = _build(monkeypatch, raw=raw, rules=pd.DataFrame())
    assert isinstance(summary, pd.DataFrame) and summary.empty
    assert info["reason"] == "no-fba-rows"
    assert info["errors"] == []


def test_no_rules_returns_unadjusted_rows(monkeypatch):
    summary, info = _build(monkeypatch, raw=_raw_fba(), rules=_rules([]))
    assert summary is not None and not summary.empty
    assert info["rule_rows"] == 0
    assert (summary["调整前-后amount"].abs() < 1e-9).all()
    assert info["errors"] == []


def test_zero_hit_rule_requires_finance_review(monkeypatch):
    summary, info = _build(
        monkeypatch, raw=_raw_fba(), rules=_rules([{"渠道账号": "AMZAUS", "平台SKU": "SKU404"}])
    )
    # 结果仍然给出（诊断用），但错误必须阻断发布
    assert summary is not None
    assert any("0 命中" in e for e in info["errors"])


def test_bad_rule_blocks(monkeypatch):
    summary, info = _build(
        monkeypatch, raw=_raw_fba(), rules=_rules([{"渠道账号": "AMZAUS", "平台SKU": None}])
    )
    assert summary is None
    assert any("空 SKU" in e for e in info["errors"])


def test_rule_hits_and_conservation_numbers(monkeypatch):
    summary, info = _build(
        monkeypatch, raw=_raw_fba(), rules=_rules([{"渠道账号": "AMZAUS", "平台SKU": "SKU1"}])
    )
    assert summary is not None
    assert info["errors"] == []
    # 命中规则 → 该账号 FBA 全清零；逐账号 `原始 = 调整后 + 差额`（口径内 ≤0.01）。
    assert abs(float(summary["amount"].sum())) <= 0.01
    assert abs(float(summary["调整前-后amount"].sum()) - 30.0) <= 0.01
    assert abs(
        float(summary["amount"].sum() + summary["调整前-后amount"].sum())
        - float(_raw_fba()["amount"].sum())
    ) <= 0.01


# ------------------------------------------------------- 写前门禁汇总


def _preflight(**kw):
    from phase3_merge import preflight_write_errors

    df = pd.DataFrame(
        {
            "审批编号": ["A1"],
            "销售账户": ["AMZAUS"],
            "渠道账号": ["AMZAUS"],
            "运营人员": ["甲"],
            "收款归属": ["平台"],
            "选择平台": ["亚马逊"],
            "应收金额": [100.0],
            "销售额": [200.0],
            "应收金额_人民币": [700.0],
            "销售额_人民币": [1400.0],
            "汇率": [7.0],
        }
    )
    return preflight_write_errors(
        df,
        df_group=pd.DataFrame(
            {"渠道账号": ["AMZAUS"], "应收金额_人民币": [700.0], "销售额_人民币": [1400.0], "收款费用累加人民币": [0.0]}
        ),
        df_merged=pd.DataFrame({"渠道账号": ["AMZAUS"], "Tax amount人民币": [0.0]}),
        df_tax=pd.DataFrame({"渠道账号": ["AMZAUS"], "Tax amount人民币": [0.0]}),
        df_sep=pd.DataFrame(),
        df_account=MASTER,
        approval_filter=pd.Series([True]),
        **kw,
    )


def test_preflight_surfaces_fba_errors():
    assert _preflight() == []
    problems = _preflight(fba_errors=["源文件总账未闭合: FAIL=1"])
    assert any("FBA" in p and "FAIL=1" in p for p in problems)


# ------------------------------------------------------- run_phase3 writer=0


def _stub_run_phase3(monkeypatch, tmp_path, *, fba_result, writes):
    import phase3_gsheet
    import phase3_merge as m

    df_row = pd.DataFrame(
        {
            "审批编号": ["A1"],
            "销售账户": ["AMZAUS"],
            "渠道账号": ["AMZAUS"],
            "运营人员": ["甲"],
            "收款归属": ["平台"],
            "选择平台": ["亚马逊"],
            "应收金额": [100.0],
            "销售额": [200.0],
            "汇率": [7.0],
            "应收金额_人民币": [700.0],
            "销售额_人民币": [1400.0],
        }
    )
    df_group = pd.DataFrame(
        {
            "渠道账号": ["AMZAUS"],
            "运营人员": ["甲"],
            "收款归属": ["平台"],
            "应收金额_人民币": [700.0],
            "销售额_人民币": [1400.0],
            "佣金_人民币": [70.0],
            "收款费用累加人民币": [0.0],
        }
    )
    df_tax = pd.DataFrame({"渠道账号": ["AMZAUS"], "Tax amount人民币": [0.0]})
    df_merged = pd.DataFrame({"渠道账号": ["AMZAUS"], "Tax amount人民币": [0.0], "附加费累加人民币": [0.0]})

    monkeypatch.setattr(m, "load_oa_dataframe", lambda path, failures_out=None: pd.DataFrame({"x": [1]}))
    monkeypatch.setattr(m, "drop_april_resubmit_rows", lambda df, month: (df, 0))
    monkeypatch.setattr(m, "load_exchange_rate_table", lambda gc, month_col: (pd.DataFrame(), pd.DataFrame()))
    monkeypatch.setattr(m, "load_channel_accounts", lambda gc, month: (MASTER, pd.DataFrame()))
    monkeypatch.setattr(m, "build_row_level_df", lambda *a, **k: (df_row, pd.Series([True], index=df_row.index)))
    monkeypatch.setattr(m, "build_group_account_cost", lambda *a, **k: df_group)
    monkeypatch.setattr(m, "build_rmb_by_account", lambda df_group: df_group.copy())
    monkeypatch.setattr(m, "load_additional_fee_grouped", lambda *a, **k: (pd.DataFrame(), []))
    monkeypatch.setattr(m, "load_tax_grouped", lambda *a, **k: (df_tax, []))
    monkeypatch.setattr(m, "merge_rmb_tax_additional", lambda *a, **k: df_merged)
    monkeypatch.setattr(m, "phase3_spreadsheet_available", lambda gc: True)
    monkeypatch.setattr(m, "read_worksheet_df", lambda gc, name: pd.DataFrame())
    monkeypatch.setattr(m, "build_fba_summary", lambda *a, **k: fba_result)
    monkeypatch.setattr(m, "write_worksheet_df", lambda gc, df, worksheet: writes.append(worksheet))
    monkeypatch.setattr(phase3_gsheet, "sort_phase3_tabs", lambda gc, pin_worksheet: None)
    monkeypatch.setenv("PERIOD_WRITE_MANIFEST_DIR", str(tmp_path / "manifests"))


def test_run_phase3_fba_failure_blocks_all_writes(monkeypatch, tmp_path):
    from phase3_merge import run_phase3

    writes: list[str] = []
    _stub_run_phase3(
        monkeypatch,
        tmp_path,
        fba_result=(None, {"errors": ["源文件总账未闭合: FAIL=1"], "read_stats": {}}),
        writes=writes,
    )
    with pytest.raises(RuntimeError, match="写前门禁失败"):
        run_phase3(
            gc=None,
            input_xlsx=Path("x.xlsx"),
            bucket="账期20260804-20260903",
            exchange_month="202608",
            bucket_dir=tmp_path,
            write_gsheet=True,
        )
    assert writes == []  # 任何一张表都不能先写


def test_run_phase3_fba_failure_blocks_fba_write_too(monkeypatch, tmp_path):
    from phase3_merge import run_phase3

    writes: list[str] = []
    _stub_run_phase3(
        monkeypatch,
        tmp_path,
        fba_result=(None, {"errors": ["FBA 明细缺汇率 2 行"], "read_stats": {}}),
        writes=writes,
    )
    with pytest.raises(RuntimeError, match="写前门禁失败"):
        run_phase3(
            gc=None,
            input_xlsx=Path("x.xlsx"),
            bucket="账期20260804-20260903",
            exchange_month="202608",
            bucket_dir=tmp_path,
            write_gsheet_fba=True,
        )
    assert writes == []


def test_run_phase3_clean_run_writes(monkeypatch, tmp_path):
    """反证：没有 FBA 错误时写前门禁不误杀。"""
    from phase3_merge import run_phase3

    writes: list[str] = []
    _stub_run_phase3(
        monkeypatch,
        tmp_path,
        fba_result=(pd.DataFrame(), {"errors": [], "read_stats": {}}),
        writes=writes,
    )
    rep, frames = run_phase3(
        gc=None,
        input_xlsx=Path("x.xlsx"),
        bucket="账期20260804-20260903",
        exchange_month="202608",
        bucket_dir=tmp_path,
        write_gsheet=True,
    )
    assert len(writes) == 5
    assert "fba_staff" in frames
