# -*- coding: utf-8 -*-
"""A 组 P0 门禁（gate_audit_20261120.md A1–A6）的回归测试。

A1 账号判空 / A2 别名先查后去重 / A3 Tax 账号主数据 / A4 strict 写前生效 /
A5 金额严格解析 / A6 FX 校验与币种唯一。
"""
from __future__ import annotations

import importlib.util
from pathlib import Path

import pandas as pd
import pytest

from amounts import infer_decimal_format, is_blank, parse_amount_strict
from exchange_rate import normalize_currency_label, unique_rates_by_key
from tax_aggregate import enrich_with_fx

# ---------------------------------------------------------------- fake gspread


class _FakeWS:
    def __init__(self, rows, title="ws"):
        self._rows = rows
        self.title = title

    def get_all_values(self):
        return self._rows


class _FakeSh:
    def __init__(self, rows, title="ws"):
        self._ws = _FakeWS(rows, title)

    def worksheets(self):
        return [self._ws]

    def worksheet(self, name):
        return self._ws


class _FakeGc:
    def __init__(self, rows, title="ws"):
        self._rows = rows
        self._title = title

    def open_by_key(self, _id):
        return _FakeSh(self._rows, self._title)


@pytest.fixture(autouse=True)
def _identity_canonical(monkeypatch):
    """不依赖本机 gitignored 渠道账号快照。"""
    import channel_canonical

    monkeypatch.setattr(channel_canonical, "canonical_account", lambda s: s)


# ------------------------------------------------------------------ A1 判空


def test_is_blank_covers_na_sentinels():
    s = pd.Series([None, pd.NA, float("nan"), "", "  ", "nan", "None", "<NA>", "AMZUS"])
    assert is_blank(s).tolist() == [True, True, True, True, True, True, True, True, False]


def test_blank_dimension_problems_only_amount_rows():
    from phase3_merge import blank_dimension_problems

    df = pd.DataFrame(
        {
            "审批编号": ["A1", "A2"],
            "销售账户": ["AMZA", pd.NA],
            "渠道账号": ["AMZA", pd.NA],
            "运营人员": ["甲", "乙"],
            "收款归属": ["P卡", "P卡"],
            "选择平台": ["亚马逊", "亚马逊"],
            "应收金额": [0.0, 100.0],
            "销售额": [0.0, 200.0],
        }
    )
    problems = blank_dimension_problems(df)
    assert len(problems) == 2  # 销售账户 + 渠道账号，且只针对 A1 那条有金额行
    assert all("1 行" in p for p in problems)
    assert any(p.startswith("销售账户") for p in problems)
    assert any(p.startswith("渠道账号") for p in problems)


def test_blank_dimension_problems_zero_amount_rows_exempt():
    from phase3_merge import blank_dimension_problems

    df = pd.DataFrame(
        {
            "审批编号": ["A1"],
            "销售账户": [pd.NA],
            "渠道账号": [pd.NA],
            "运营人员": [pd.NA],
            "收款归属": [pd.NA],
            "选择平台": [pd.NA],
            "应收金额": [0.0],
            "销售额": [0.0],
        }
    )
    assert blank_dimension_problems(df) == []


# ------------------------------------------------------- A2 别名冲突先查后去重


def _channel_rows(rows):
    header = ["渠道", "渠道账号", "渠道账号别名", "运营人员202610"]
    return [header] + rows


def test_alias_shared_by_two_accounts_raises():
    from phase3_merge import load_channel_accounts

    rows = _channel_rows(
        [
            ["Amazon", "AMZA", "same", "甲"],
            ["Amazon", "AMZB", "same", "乙"],
        ]
    )
    with pytest.raises(ValueError, match="别名冲突"):
        load_channel_accounts(
            _FakeGc(rows, title="渠道账号（20260521起在此维护）"), "202610"
        )


def test_alias_case_only_conflict_kept_first(capsys):
    from phase3_merge import load_channel_accounts

    rows = _channel_rows(
        [
            ["Amazon", "AMZUS", "foo", "甲"],
            ["Amazon", "amzus", "FOO", "乙"],
        ]
    )
    acct_view, explode = load_channel_accounts(
        _FakeGc(rows, title="渠道账号（20260521起在此维护）"), "202610"
    )
    assert len(acct_view) == 2  # 大小写不同的同一账号不拦
    assert set(explode["渠道账号"]) == {"AMZUS", "amzus"}
    assert "仅大小写不同" in capsys.readouterr().err


def test_channel_accounts_blank_rows_dropped_and_staff_na():
    from phase3_merge import load_channel_accounts

    rows = _channel_rows(
        [
            ["Amazon", "AMZA", "", "甲"],
            ["Amazon", "", "ghost", "乙"],
            ["Amazon", "AMZC", "", ""],
        ]
    )
    acct_view, _ = load_channel_accounts(
        _FakeGc(rows, title="渠道账号（20260521起在此维护）"), "202610"
    )
    assert acct_view["渠道账号"].tolist() == ["AMZA", "AMZC"]  # 空账号行被丢弃
    assert pd.isna(acct_view.loc[acct_view["渠道账号"] == "AMZC", "运营人员"].iloc[0])


# ------------------------------------------------- A3 Tax 账号/主数据/人员


def _master():
    return pd.DataFrame(
        {
            "渠道": ["Amazon", "Amazon", "Amazon"],
            "渠道账号": ["AMZA", "AMZB", "AMZC"],
            "运营人员": ["甲", pd.NA, "丙"],
        }
    )


def test_tax_unknown_account_and_blank_staff_reported():
    from phase3_merge import tax_account_problems

    df_tax = pd.DataFrame(
        {
            "渠道账号": ["AMZA", "AMZZZ", "AMZB"],
            "Tax amount人民币": [10.0, 5.0, 7.0],
        }
    )
    problems = tax_account_problems(df_tax, _master(), only_nonzero=True)
    joined = ";".join(problems)
    assert "不在渠道主表" in joined and "AMZZZ" in joined
    assert "运营人员为空" in joined and "AMZB" in joined


def test_tax_zero_amount_unknown_account_not_blocking_phase3():
    from phase3_merge import tax_account_problems

    df_tax = pd.DataFrame({"渠道账号": ["AMZZZ"], "Tax amount人民币": [0.0]})
    assert tax_account_problems(df_tax, _master(), only_nonzero=True) == []
    # 发布 df6_gsheet 时按全部账号校验（T03）
    assert tax_account_problems(df_tax, _master(), only_nonzero=False)


def test_tax_blank_account_reported():
    from phase3_merge import tax_account_problems

    df_tax = pd.DataFrame({"渠道账号": [pd.NA], "Tax amount人民币": [3.0]})
    assert any("空白渠道账号" in p for p in tax_account_problems(df_tax, _master()))


def test_blank_account_zero_amount_rows_dropped():
    from phase3_merge import _drop_blank_accounts

    raw = pd.DataFrame({"渠道账号": ["A", "null", ""], "Tax amount人民币": [1.0, 0.0, 0.0]})
    out = _drop_blank_accounts(raw, ["Tax amount人民币"], label="t")
    assert out["渠道账号"].tolist() == ["A"]


def test_blank_account_with_amount_raises():
    from phase3_merge import _drop_blank_accounts

    raw = pd.DataFrame({"渠道账号": ["null"], "Tax amount人民币": [5.0]})
    with pytest.raises(ValueError, match="渠道账号为空但金额非零"):
        _drop_blank_accounts(raw, ["Tax amount人民币"], label="t")


def test_preflight_composes_dimension_and_tax_checks():
    from phase3_merge import preflight_write_errors

    df = pd.DataFrame(
        {
            "审批编号": ["A1"],
            "销售账户": ["AMZZZ"],
            "渠道账号": [pd.NA],
            "运营人员": ["甲"],
            "收款归属": ["P卡"],
            "选择平台": ["亚马逊"],
            "应收金额": [100.0],
            "销售额": [200.0],
            "应收金额_人民币": [700.0],
            "销售额_人民币": [1400.0],
        }
    )
    df_group = df[["渠道账号", "应收金额_人民币", "销售额_人民币"]].assign(收款费用累加人民币=0.0)
    df_tax = pd.DataFrame({"渠道账号": ["AMZZZ"], "Tax amount人民币": [9.0]})
    problems = preflight_write_errors(
        df,
        df_group=df_group,
        df_merged=df_tax,
        df_tax=df_tax,
        df_sep=pd.DataFrame(),
        df_account=_master(),
        approval_filter=pd.Series([True], index=df.index),
    )
    joined = ";".join(problems)
    assert "渠道账号 有金额行判空" in joined
    assert "不在渠道主表" in joined


# ------------------------------------------------------- A4 strict 写前生效

_PATH = Path(__file__).resolve().parents[1] / "scripts" / "run_period_tax.py"
_spec = importlib.util.spec_from_file_location("run_period_tax_gate", _PATH)
assert _spec and _spec.loader
_mod = importlib.util.module_from_spec(_spec)
_spec.loader.exec_module(_mod)
enforce_write_gate = _mod.enforce_write_gate


def test_strict_failures_block_before_any_write():
    with pytest.raises(SystemExit) as e:
        enforce_write_gate(
            strict=True,
            strict_failures=["OUT-OF-PERIOD=1"],
            master_problems=[],
            publish_requested=True,
        )
    assert "OUT-OF-PERIOD=1" in str(e.value)


def test_non_strict_does_not_block_on_strict_failures():
    enforce_write_gate(
        strict=False, strict_failures=["SKIP-DUP=2"], master_problems=[], publish_requested=True
    )


def test_master_problems_block_publish_even_without_strict():
    with pytest.raises(SystemExit, match="主数据"):
        enforce_write_gate(
            strict=False,
            strict_failures=[],
            master_problems=["Tax 渠道账号不在渠道主表 1 个: ['AMZZZ']"],
            publish_requested=True,
        )
    # 只写本地 xlsx（不发布）时只报告不拦
    enforce_write_gate(
        strict=False,
        strict_failures=[],
        master_problems=["Tax 渠道账号不在渠道主表 1 个"],
        publish_requested=False,
    )


# --------------------------------------------------------- A5 金额严格解析


@pytest.mark.parametrize("raw", [None, "", "  ", float("nan"), pd.NA, "nan", "None", "<NA>"])
def test_parse_amount_strict_blank_is_none(raw):
    assert parse_amount_strict(raw) is None


@pytest.mark.parametrize(
    "raw,expected",
    [
        ("1,234", 1234.0),
        ("-12,345.6", -12345.6),
        ("1234.5", 1234.5),
        (1234.5, 1234.5),
        (10, 10.0),
        ("+7", 7.0),
    ],
)
def test_parse_amount_strict_ok(raw, expected):
    assert parse_amount_strict(raw) == pytest.approx(expected)


@pytest.mark.parametrize("raw", ["abc", "Inf", "-inf", "1,5", "1,23", "1,2345", "12,34.5"])
def test_parse_amount_strict_rejects(raw):
    with pytest.raises(ValueError):
        parse_amount_strict(raw)


def test_parse_amount_strict_nan_string_is_blank():
    """'NaN' 是 pandas 序列化出来的缺失值，按空处理；Inf 才是非法。"""
    assert parse_amount_strict("NaN") is None


def test_parse_amount_strict_auto_mode_mixed_file():
    """Amazon 欧洲站同一文件混用小数逗号与点小数：按单元格判定。"""
    assert parse_amount_strict("0,04", decimal_separator="auto") == pytest.approx(0.04)
    assert parse_amount_strict("109,24", decimal_separator="auto") == pytest.approx(109.24)
    assert parse_amount_strict("-16.64", decimal_separator="auto") == pytest.approx(-16.64)
    # 千分位口径优先（任务要求 1,234 → 1234，不是 1.234）
    assert parse_amount_strict("1,234", decimal_separator="auto") == pytest.approx(1234.0)
    assert parse_amount_strict("1,234.56", decimal_separator="auto") == pytest.approx(1234.56)
    with pytest.raises(ValueError):
        parse_amount_strict("1,5", decimal_separator="auto")  # 1 位小数逗号：歧义
    with pytest.raises(ValueError):
        parse_amount_strict("1,2345", decimal_separator="auto")  # 4 位小数逗号：歧义


def test_infer_decimal_format_labels():
    assert infer_decimal_format(["1,234"]) == "thousands"
    assert infer_decimal_format(["0,04", "12"]) == "comma+int"
    assert infer_decimal_format(["0,04", "-16.64"]) == "comma+dot"
    assert infer_decimal_format([1.0, 2]) == "dot"


def test_read_amz_txt_bad_amount_fails_file(tmp_path):
    from read_amz_txt import read_bucket_amz_txts

    bucket = tmp_path / "账期20261004-20261103"
    (bucket / "甲").mkdir(parents=True)
    header = "settlement-id\tcurrency\tamount\tamount-description\ttransaction-type\tamount-type\n"
    (bucket / "甲" / "AMZBadUS-2026-10-05.txt").write_text(
        header + "1\tUSD\tnot-a-number\tTax\tOrder\tItemPrice\n", encoding="utf-8"
    )
    stats: dict = {}
    df, reports = read_bucket_amz_txts(bucket, stats_out=stats)
    assert df.empty
    assert stats["files_failed"] == 1
    assert any(r.startswith("FAIL") and "金额解析失败" in r for r in reports)


def test_read_amz_txt_comma_decimal_file_parsed(tmp_path):
    from read_amz_txt import read_bucket_amz_txts

    bucket = tmp_path / "账期20261004-20261103"
    (bucket / "甲").mkdir(parents=True)
    header = "settlement-id\tcurrency\tamount\tamount-description\ttransaction-type\tamount-type\n"
    (bucket / "甲" / "AMZDEUS-2026-10-05.txt").write_text(
        header + "1\tEUR\t0,04\tTax\tOrder\tItemPrice\n2\tEUR\t109,24\tTax\tOrder\tItemPrice\n",
        encoding="utf-8",
    )
    stats: dict = {}
    df, _ = read_bucket_amz_txts(bucket, stats_out=stats)
    assert stats["files_failed"] == 0
    assert df["amount"].tolist() == pytest.approx([0.04, 109.24])


def test_oa_invalid_amount_raises():
    from phase3_merge import build_row_level_df

    df = pd.DataFrame(
        {
            "亚马逊销售账户": ["A", "A"],
            "审批状态": ["完成", "完成"],
            "审批结果": ["同意", "同意"],
            "审批编号": ["1", "2"],
            "币种": ["USD", "USD"],
            "应收金额": [10, 20],
            "销售额": ["not-a-number", 30],
        }
    )
    df_rate_explode = pd.DataFrame({"货币中文名": ["USD"], "收款币种": ["USD"], "汇率": [7.0]})
    df_explode = pd.DataFrame(
        {"渠道账号": ["AMZA"], "渠道账号别名": ["A"], "运营人员": ["甲"]}
    )
    with pytest.raises(ValueError, match="金额解析失败"):
        build_row_level_df(
            df, df_exchange_rate=None, df_explode=df_explode, df_rate_explode=df_rate_explode
        )


# --------------------------------------------------- A6 FX 校验与币种唯一


def test_currency_label_ascii_uppercased():
    assert normalize_currency_label("usd") == "USD"
    assert normalize_currency_label("  eur ") == "EUR"
    assert normalize_currency_label("美元") == "美元"
    assert normalize_currency_label("匈牙利福林（HUF）") == "匈牙利福林(HUF)"


def test_enrich_with_fx_usd_lowercase_hits_uppercase():
    df = pd.DataFrame({"currency": ["usd"], "amount": [10.0]})
    rates = pd.DataFrame({"收款币种": ["USD"], "汇率": [7.0]})
    out = enrich_with_fx(df, rates)
    assert out["汇率"].iloc[0] == 7.0
    assert out["amount人民币"].iloc[0] == 70.0


def test_enrich_with_fx_duplicate_currency_different_rate_raises():
    df = pd.DataFrame({"currency": ["USD"], "amount": [10.0]})
    rates = pd.DataFrame({"收款币种": ["USD", "USD"], "汇率": [7.0, 7.2]})
    with pytest.raises(ValueError, match="多个汇率"):
        enrich_with_fx(df, rates)


def test_enrich_with_fx_blank_currency_raises():
    df = pd.DataFrame({"currency": [None], "amount": [10.0]})
    rates = pd.DataFrame({"收款币种": ["USD"], "汇率": [7.0]})
    with pytest.raises(ValueError, match="币种为空"):
        enrich_with_fx(df, rates)


def test_enrich_with_fx_non_positive_rate_raises():
    df = pd.DataFrame({"currency": ["USD"], "amount": [10.0]})
    rates = pd.DataFrame({"收款币种": ["USD"], "汇率": [0.0]})
    with pytest.raises(ValueError, match="有限且 >0"):
        enrich_with_fx(df, rates)


def test_unique_rates_many_to_one_validate():
    rates = pd.DataFrame(
        {"收款币种": ["USD", "EUR"], "货币中文名": ["美元", "欧元"], "汇率": [7.0, 8.0]}
    )
    out = unique_rates_by_key(rates, key="收款币种", used_keys=["usd"])
    assert out["收款币种"].tolist() == ["USD", "EUR"]
    # 用作 m:1 连接键时唯一
    left = pd.DataFrame({"收款币种": ["USD", "USD"]})
    assert len(left.merge(out, how="left", on="收款币种", validate="many_to_one")) == 2
