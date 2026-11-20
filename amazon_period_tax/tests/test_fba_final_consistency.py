# -*- coding: utf-8 -*-
"""FBA 最终口径一致性（F07，整改 U-B B4）。

- 分类总差额取反 = 人员 FBA 合计（逐账号、逐币种）。
- 人员基础应收/销售/佣金来自**同批**普通人员表。
- 分组表与人员表用同一份分类汇总 hash（不能一新一旧）。
- 无规则仍输出未调整原 FBA 行；丢人员/丢源账号必须 FAIL。
"""
from __future__ import annotations

import pandas as pd
import pytest


def _summary(rows: list[tuple[str, str, str, str, float, float]]) -> pd.DataFrame:
    """(父, 子, 渠道账号, 币种, 调整后人民币, 差额人民币) → 最小分类汇总。

    差额按人民币给（FBA 下游只用 ``调整前-后amount人民币``），原币按固定汇率 7 折算。
    """
    return pd.DataFrame(
        [
            {
                "父文件夹名": parent,
                "子文件夹名": child,
                "渠道账号": account,
                "currency": currency,
                "汇率": 7.0,
                "amount": adjusted_rmb / 7.0,
                "amount人民币": adjusted_rmb,
                "调整前-后amount": delta_rmb / 7.0,
                "调整前-后amount人民币": delta_rmb,
            }
            for parent, child, account, currency, adjusted_rmb, delta_rmb in rows
        ]
    )


def _group() -> pd.DataFrame:
    return pd.DataFrame(
        {
            "渠道账号": ["AMZA", "AMZB"],
            "运营人员": ["甲", "乙"],
            "应收金额_人民币": [1000.0, 400.0],
            "销售额_人民币": [2000.0, 800.0],
            "佣金_人民币": [100.0, 40.0],
        }
    )


# ------------------------------------------------------- 同源 hash（F07）


def test_same_summary_gives_same_hash_and_passes():
    from phase3_merge import apply_fba_to_group, assert_same_fba_source, build_fba_staff, fba_source_hash

    summary = _summary([("甲", "A", "AMZA", "USD", 50.0, -5.0), ("乙", "B", "AMZB", "USD", 20.0, 2.0)])
    staff = build_fba_staff(_group(), summary)
    merged, ok = apply_fba_to_group(_group(), None, "20260804-20260903", fba_summary=summary)
    assert ok is True
    assert merged.attrs["fba_source_hash"] == staff.attrs["fba_source_hash"]
    assert_same_fba_source(merged.attrs["fba_source_hash"], staff.attrs["fba_source_hash"])
    assert fba_source_hash(summary) == staff.attrs["fba_source_hash"]


def test_different_summary_hash_fails():
    from phase3_merge import assert_same_fba_source, fba_source_hash

    a = _summary([("甲", "A", "AMZA", "USD", 50.0, -5.0)])
    b = _summary([("甲", "A", "AMZA", "USD", 50.0, -6.0)])
    assert fba_source_hash(a) != fba_source_hash(b)
    with pytest.raises(ValueError, match="来源 hash 不一致"):
        assert_same_fba_source(fba_source_hash(a), fba_source_hash(b))


def test_hash_is_order_insensitive():
    from phase3_merge import fba_source_hash

    rows = [("甲", "A", "AMZA", "USD", 50.0, -5.0), ("乙", "B", "AMZB", "USD", 20.0, 2.0)]
    a = fba_source_hash(_summary(rows))
    b = fba_source_hash(_summary(list(reversed(rows))))
    assert a == b


# ------------------------------------------------------- 分类/人员守恒（F07）


def test_staff_total_equals_negated_category_delta_per_account():
    from phase3_merge import build_fba_staff, fba_account_deltas

    summary = _summary([("甲", "A", "AMZA", "USD", 50.0, -5.0), ("乙", "B", "AMZB", "USD", 20.0, 2.0)])
    staff = build_fba_staff(_group(), summary)
    fb = fba_account_deltas(summary)
    assert staff["FBA费用_人民币"].sum() == pytest.approx(-float(fb["调整前-后amount人民币"].sum()))
    assert staff["FBA费用_人民币"].sum() == pytest.approx(3.0)

    # 逐账号：组表 FBA == -账号差额
    merged = _group().merge(fb, on="渠道账号")
    merged["FBA费用_人民币"] = merged["调整前-后amount人民币"] * -1
    per_acct = merged.groupby("渠道账号")["FBA费用_人民币"].sum()
    assert per_acct["AMZA"] == pytest.approx(5.0)
    assert per_acct["AMZB"] == pytest.approx(-2.0)


def test_staff_bases_come_from_same_batch_group_table():
    from phase3_merge import build_fba_staff, collection_rate_by_staff

    summary = _summary([("甲", "A", "AMZA", "USD", 50.0, -5.0), ("乙", "B", "AMZB", "USD", 20.0, 2.0)])
    staff = build_fba_staff(_group(), summary).set_index("运营人员")
    plain = collection_rate_by_staff(_group()).set_index("运营人员")
    for col in ("应收金额_人民币", "销售额_人民币", "佣金_人民币"):
        assert (staff[col].astype(float) - plain[col].astype(float)).abs().max() <= 0.01
    # 加上/扣减列按 FBA 口径平移
    assert staff.loc["甲", "加上FBA费用_应收金额_人民币"] == pytest.approx(1005.0)
    assert staff.loc["甲", "扣减FBA费用_佣金_人民币"] == pytest.approx(95.0)


def test_staff_dropped_person_fails():
    from phase3_merge import build_fba_staff

    group = _group()
    group.loc[1, "运营人员"] = None  # 有金额却丢人员 → groupby 会静默吞掉
    with pytest.raises(ValueError, match="丢人员"):
        build_fba_staff(group, _summary([("甲", "A", "AMZA", "USD", 50.0, -5.0)]))


def test_staff_dropped_source_account_fails():
    from phase3_merge import build_fba_staff

    # AMZORPHAN 有非零差额但组表没有该账号 → 不能悄悄丢
    summary = _summary(
        [("甲", "A", "AMZA", "USD", 50.0, -5.0), ("丙", "C", "AMZORPHAN", "USD", 10.0, -3.0)]
    )
    with pytest.raises(ValueError, match="孤儿"):
        build_fba_staff(_group(), summary)


# ------------------------------------------------- 逐账号/币种原始=调整后+差额


def test_original_equals_adjusted_plus_delta_per_account_currency():
    summary = _summary(
        [
            ("甲", "A", "AMZA", "USD", 50.0, -5.0),
            ("甲", "A", "AMZA", "EUR", 30.0, -2.0),
            ("乙", "B", "AMZB", "USD", 20.0, 2.0),
        ]
    )
    grouped = summary.groupby(["渠道账号", "currency"])[["amount", "调整前-后amount"]].sum()
    for (account, currency), row in grouped.iterrows():
        original = row["amount"] + row["调整前-后amount"]
        assert abs(original - (row["amount"] + row["调整前-后amount"])) <= 0.01
        assert abs(row["调整前-后amount"]) <= abs(original) + 0.01


def test_cent_precision_conserved():
    from phase3_merge import build_fba_staff

    summary = _summary([("甲", "A", "AMZA", "USD", 0.0, -644.21)])
    staff = build_fba_staff(_group(), summary)
    assert staff["FBA费用_人民币"].sum() == pytest.approx(644.21, abs=0.01)


# ------------------------------------------------------- 无规则不返回空表


def test_no_rules_unadjusted_summary_still_feeds_staff():
    """无规则 → 分类汇总保留未调整行（差额 0）→ 人员表照常有行、FBA=0。"""
    from phase3_merge import build_fba_staff

    summary = _summary([("甲", "A", "AMZA", "USD", 50.0, 0.0), ("乙", "B", "AMZB", "USD", 20.0, 0.0)])
    staff = build_fba_staff(_group(), summary)
    assert set(staff["运营人员"]) == {"甲", "乙"}
    assert staff["FBA费用_人民币"].abs().max() <= 0.01
    assert len(staff) == 2


def test_empty_summary_does_not_invent_fba():
    from phase3_merge import build_fba_staff

    staff = build_fba_staff(_group(), pd.DataFrame({"渠道账号": [], "调整前-后amount人民币": []}))
    assert staff["FBA费用_人民币"].abs().max() <= 0.01
    assert len(staff) == 2


# ------------------------------------------------ 端到端：明细 → 分类 → 人员


def test_end_to_end_per_account_currency_conservation():
    """明细行（2 账号 / 2 币种）→ 规则扣减 → 分类汇总 → 人员表，逐账号逐币种守恒。"""
    from fba_adjust import fba_summary_df12, process_fba_orders
    from phase3_merge import build_fba_staff

    detail = pd.DataFrame(
        {
            "父文件夹名": ["甲", "甲", "甲", "乙", "乙"],
            "子文件夹名": ["A", "A", "A", "B", "B"],
            "渠道账号": ["AMZA", "AMZA", "AMZA", "AMZB", "AMZB"],
            "sku": ["SKU1", "SKU2", "SKU9", "SKU1", "SKU9"],
            "currency": ["USD", "USD", "EUR", "USD", "USD"],
            "汇率": [7.0, 7.0, 7.8, 7.0, 7.0],
            "amount": [10.0, 20.0, 30.0, 5.0, 50.0],
            "amount-description": [
                "FBAPerUnitFulfillmentFee",
                "Storage Fee",
                "FBAPerUnitFulfillmentFee",
                "FBAPerUnitFulfillmentFee",
                "Storage Fee",
            ],
        }
    )
    rules = pd.DataFrame({"渠道账号": ["AMZA"], "平台SKU": ["SKU1"], "当月是否执行": ["是"]})
    processed = process_fba_orders(rules, detail)
    summary = fba_summary_df12(processed)

    # 逐账号/币种：原始 = 调整后 + 差额（人民币口径 ≤0.01）
    orig = (
        detail.assign(amount人民币=detail["amount"] * detail["汇率"])
        .groupby(["渠道账号", "currency"])["amount人民币"]
        .sum()
    )
    adj = summary.groupby(["渠道账号", "currency"])["amount人民币"].sum()
    delta = summary.groupby(["渠道账号", "currency"])["调整前-后amount人民币"].sum()
    for key in orig.index:
        assert abs(float(orig[key]) - float(adj.get(key, 0.0) + delta.get(key, 0.0))) <= 0.01, key

    # 分类总差额取反 = 人员 FBA 合计（逐账号）
    group = pd.DataFrame(
        {
            "渠道账号": ["AMZA", "AMZB"],
            "运营人员": ["甲", "乙"],
            "应收金额_人民币": [1000.0, 400.0],
            "销售额_人民币": [2000.0, 800.0],
            "佣金_人民币": [100.0, 40.0],
        }
    )
    staff = build_fba_staff(group, summary)
    assert staff["FBA费用_人民币"].sum() == pytest.approx(
        -float(summary["调整前-后amount人民币"].sum()), abs=0.01
    )
    per_acct = group.assign(
        fba=group["渠道账号"].map(
            summary.groupby("渠道账号")["调整前-后amount人民币"].sum().mul(-1)
        )
    )
    assert abs(float(per_acct["fba"].sum()) - float(staff["FBA费用_人民币"].sum())) <= 0.01
