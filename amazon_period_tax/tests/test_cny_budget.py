# -*- coding: utf-8 -*-
"""R1 人民币预算：原币差 × 已确认目标月 FX；文本修正按受影响金额规模；累计防拆 run。

验收（``reports/t2_hardening_20261120.md`` R1）：
- 单条 1000 / 批次 5000 边界通过，1000.01 / 5000.01 转候选；
- 缺 FX 或币种未确认 → writer=0；
- 账号换人但金额没变不能 impact=0 PASS；
- 同一期间/同源版本累计，正负不抵消。
"""
from __future__ import annotations

import json
from datetime import datetime, timedelta, timezone
from decimal import Decimal
from pathlib import Path

import pandas as pd
import pytest

from correction_policy import (
    STATUS_AUTO_ALLOWED,
    STATUS_BLOCKED,
    STATUS_PREVIEW,
    build_proposals,
    cumulative_prior_impact,
    evaluate_batch,
    evaluate_proposal,
    fx_digest,
    fx_table_from_mapping,
    load_fx_table,
    manifest_policy_fields,
    parse_policy,
    resolve_impact_budget,
    stale_pass_problems,
)
from remediation import RemediationError, apply_corrections, md5_file

PERIOD = "202607"
BUCKET = "账期20260704-20260803"
APPROVAL = "202608071439000120006"
NOW = datetime(2026, 11, 20, 12, tzinfo=timezone(timedelta(hours=8)))
SRC_HASH = "a" * 32

ROW = {
    "审批编号": APPROVAL,
    "账期日期": "2026-07-22",
    "币种": "USD",
    "AMZJohna账户": "AMZJohnaUS",
    "账期收款额": 5000,
    "销售额": 1000,
    "佣金": 300,
}


def _policy(*, max_single="1000", max_batch="5000", require_fx=True, **t2_extra):
    data = {
        "schema_version": 1,
        "policy_id": "amz-r1",
        "version": "1",
        "authorized_by": "测试",
        "created_at": "2026-11-01T00:00:00+08:00",
        "effective_from": "2026-11-01T00:00:00+08:00",
        "effective_to": "2026-12-31T00:00:00+08:00",
        "ttl_hours": 24 * 45,
        "t2": {
            "enabled": True,
            "allowed_categories": ["amount_value", "account_attribution"],
            "allowed_platforms": ["Amazon"],
            "allowed_fields": ["销售额", "账期收款额", "佣金", "AMZJohna账户"],
            "closed_periods": [],
            "max_single_record_impact": max_single,
            "max_batch_impact": max_batch,
            "require_fx": require_fx,
            **t2_extra,
        },
    }
    return parse_policy(data)


def _fx(rate="1", month=PERIOD):
    return fx_table_from_mapping({"USD": rate}, month=month, source="<test>", source_hash="f" * 32)


def _item(*, delta="1000", cid="T2-1", kind="amount_value", currency="USD", field="销售额", **extra):
    decimal = Decimal(str(delta))
    item = {
        "correction_id": cid,
        "kind": kind,
        "platform": "Amazon",
        "scope": {"period": PERIOD, "bucket": BUCKET},
        "approval_id": APPROVAL,
        "source_row_key": {"审批编号": APPROVAL},
        "field_changes": {field: ["0", str(decimal)]},
        "evidence": {
            "attachment": "att.txt",
            "attachment_md5": "b" * 32,
            "settlement_id": "25909392482",
            "identity_unique": True,
        },
        "currency": currency,
    }
    item.update(extra)
    return item


def _text_item(*, affected="1000", cid="T2-account", **extra):
    item = _item(cid=cid, kind="account_attribution", field="AMZJohna账户")
    item["field_changes"] = {"AMZJohna账户": ["AMZJohnaUS", "AMZJohnaUS2"]}
    if affected is not None:
        item["affected_amount"] = affected
    item.update(extra)
    return item


def _proposals(*items):
    return build_proposals(
        {"schema_version": 1, "revision": "v1", "source_files": {PERIOD: {"md5": SRC_HASH}},
         "corrections": list(items)},
        period=PERIOD,
    )


def _proposal(item):
    return _proposals(item)[0]


# --------------------------------------------------------------- 单条边界


def test_single_impact_boundary_1000_passes():
    policy = _policy()
    result = evaluate_proposal(_proposal(_item(delta="1000")), policy, now=NOW, fx=_fx())
    assert result.status == STATUS_AUTO_ALLOWED, result.reasons
    assert result.impact_cny == Decimal("1000.00")
    assert result.budget_basis == "amount_delta"


def test_single_impact_1000_01_becomes_candidate():
    policy = _policy()
    result = evaluate_proposal(_proposal(_item(delta="1000.01")), policy, now=NOW, fx=_fx())
    assert result.status == STATUS_PREVIEW
    assert any("超过上限" in r for r in result.reasons)


def test_impact_is_converted_with_target_month_fx():
    policy = _policy(max_single="1000")
    # 原币 100 USD × 7.1 = 710 CNY → 通过；101 USD × 7.1 = 717.1 → 也通过。
    ok = evaluate_proposal(_proposal(_item(delta="100")), policy, now=NOW, fx=_fx("7.1"))
    assert ok.status == STATUS_AUTO_ALLOWED
    assert ok.impact_cny == Decimal("710.00")
    # 原币 150 × 7.1 = 1065 CNY > 1000 → 候选（若按原币 150 会误通过）。
    over = evaluate_proposal(_proposal(_item(delta="150")), policy, now=NOW, fx=_fx("7.1"))
    assert over.status == STATUS_PREVIEW
    assert over.impact_cny == Decimal("1065.00")


# --------------------------------------------------------------- 批次边界 / 防拆


def _two(deltas, policy, *, prior_runs=(), source_hash=None):
    items = [_item(delta=d, cid=f"T2-{i}") for i, d in enumerate(deltas)]
    return evaluate_batch(
        _proposals(*items),
        policy,
        now=NOW,
        fx=_fx(),
        require_fx=True,
        prior_runs=prior_runs,
        source_hash=source_hash,
    )


def test_batch_boundary_5000_passes():
    batch = _two(["2500", "2500"], _policy(max_single="5000"))
    assert batch.batch_impact == Decimal("5000.00")
    assert all(r.status == STATUS_AUTO_ALLOWED for r in batch.results)


def test_batch_5000_01_becomes_candidate():
    batch = _two(["2500", "2500.01"], _policy(max_single="5000"))
    assert batch.batch_impact == Decimal("5000.01")
    assert all(r.status == STATUS_PREVIEW for r in batch.results)
    assert any("批次影响" in r for r in ";".join(";".join(r.reasons) for r in batch.results).split(";"))


def test_positive_and_negative_do_not_net_out():
    batch = _two(["3000", "-3000"], _policy(max_single="5000"))
    assert batch.batch_impact == Decimal("6000.00")  # 净额会是 0，必须按绝对值累加
    assert all(r.status == STATUS_PREVIEW for r in batch.results)


def test_split_runs_accumulate_for_same_period_and_source():
    prior = [
        {"period": PERIOD, "source_hash": SRC_HASH, "corrections": [{"impact_cny": "4000"}]}
    ]
    batch = _two(["2000"], _policy(max_single="5000"), prior_runs=prior, source_hash=SRC_HASH)
    assert batch.prior_impact == Decimal("4000")
    assert batch.cumulative_impact == Decimal("6000.00")
    assert batch.results[0].status == STATUS_PREVIEW
    assert any("同源历史" in r for r in batch.results[0].reasons)


def test_prior_run_of_other_source_is_not_accumulated():
    prior = [{"period": PERIOD, "source_hash": "c" * 32, "corrections": [{"impact_cny": "4000"}]}]
    batch = _two(["2000"], _policy(max_single="5000"), prior_runs=prior, source_hash=SRC_HASH)
    assert batch.prior_impact == Decimal("0")
    assert batch.results[0].status == STATUS_AUTO_ALLOWED


def test_cumulative_prior_impact_ignores_other_periods():
    prior = [{"period": "202608", "source_hash": SRC_HASH, "corrections": [{"impact_cny": "999"}]}]
    assert cumulative_prior_impact(prior, period=PERIOD, source_hash=SRC_HASH) == Decimal("0")


# --------------------------------------------------------------- 文本修正 / 账号换人


def test_account_swap_uses_affected_amount_not_zero():
    policy = _policy()
    result = evaluate_proposal(_proposal(_text_item(affected="1000")), policy, now=NOW, fx=_fx())
    assert result.status == STATUS_AUTO_ALLOWED, result.reasons
    assert result.impact_cny == Decimal("1000.00")
    assert result.budget_basis == "affected_amount"
    assert result.impact_cny > 0  # 金额没变也不能按 0 通过


def test_account_swap_over_limit_is_candidate():
    policy = _policy()
    result = evaluate_proposal(_proposal(_text_item(affected="1000.01")), policy, now=NOW, fx=_fx())
    assert result.status == STATUS_PREVIEW
    assert any("超过上限" in r for r in result.reasons)


def test_account_swap_without_affected_amount_is_blocked():
    policy = _policy()
    result = evaluate_proposal(_proposal(_text_item(affected=None)), policy, now=NOW, fx=_fx())
    assert result.status == STATUS_BLOCKED
    assert any("affected_amount" in r for r in result.reasons)


# --------------------------------------------------------------- 缺 FX / 币种未确认 → writer=0


def test_require_fx_without_table_blocks():
    policy = _policy()
    result = evaluate_proposal(_proposal(_item()), policy, now=NOW, require_fx=True)
    assert result.status == STATUS_BLOCKED
    assert any("FX" in r for r in result.reasons)


def test_unconfirmed_currency_is_blocked():
    policy = _policy()
    result = evaluate_proposal(
        _proposal(_item(currency="JPY")), policy, now=NOW, fx=_fx(), require_fx=True
    )
    assert result.status == STATUS_BLOCKED
    assert any("JPY" in r for r in result.reasons)


def test_missing_currency_is_blocked():
    item = _item()
    item.pop("currency")
    result = evaluate_proposal(_proposal(item), _policy(), now=NOW, fx=_fx(), require_fx=True)
    assert result.status == STATUS_BLOCKED
    assert any("币种" in r for r in result.reasons)


def test_fx_month_mismatch_is_blocked():
    result = evaluate_proposal(
        _proposal(_item()), _policy(), now=NOW, fx=_fx(month="202608"), require_fx=True
    )
    assert result.status == STATUS_BLOCKED
    assert any("月份" in r for r in result.reasons)


def test_writer_zero_when_fx_missing(tmp_path):
    """缺 FX 时正式写入口不产生 corrected 副本（writer=0）。"""
    src = tmp_path / "src.xlsx"
    pd.DataFrame([ROW]).to_excel(src, sheet_name="核算行", index=False)
    evidence = tmp_path / "ev"
    evidence.mkdir()
    (evidence / "att.txt").write_text("x", encoding="utf-8")
    payload = {
        "schema_version": 1,
        "revision": "v1",
        "created_at": "2026-11-19T16:20:00+08:00",
        "source_files": {PERIOD: {"md5": md5_file(src)}},
        "corrections": [_item()],
    }
    out = tmp_path / "out" / "corrected.xlsx"
    with pytest.raises(RemediationError, match="授权门禁未通过"):
        apply_corrections(
            src=src,
            corrections=payload,
            period=PERIOD,
            out=out,
            evidence_root=evidence,
            policy=_policy(),
            require_fx=True,
            now=NOW,
        )
    assert not out.exists()


# --------------------------------------------------------------- FX 表加载 / hash


def test_load_fx_table_json_and_csv(tmp_path):
    j = tmp_path / "fx.json"
    j.write_text(json.dumps({"month": PERIOD, "rates": {"usd": "7.1"}}), encoding="utf-8")
    table = load_fx_table(j, month=PERIOD)
    assert table.rate("USD") == Decimal("7.1")

    c = tmp_path / "fx.csv"
    c.write_text("currency,rate,month\nUSD,7.2,202607\n", encoding="utf-8")
    table2 = load_fx_table(c, month=PERIOD)
    assert table2.rate("USD") == Decimal("7.2")


def test_load_fx_table_rejects_zero_and_month_mismatch(tmp_path):
    bad = tmp_path / "fx.json"
    bad.write_text(json.dumps({"month": PERIOD, "rates": {"USD": "0"}}), encoding="utf-8")
    with pytest.raises(Exception, match="汇率必须 > 0"):
        load_fx_table(bad, month=PERIOD)
    mismatch = tmp_path / "fx2.json"
    mismatch.write_text(json.dumps({"month": "202608", "rates": {"USD": "7"}}), encoding="utf-8")
    with pytest.raises(Exception, match="月份"):
        load_fx_table(mismatch, month=PERIOD)


def test_fx_change_invalidates_old_pass():
    proposals = _proposals(_item(delta="100"))
    policy = _policy()
    manifest = {
        "input_md5": SRC_HASH,
        "policy_hash": policy.hash,
        "proposal_hash": manifest_policy_fields(policy=policy, proposals=proposals)["proposal_hash"],
        "fx_hash": fx_digest(_fx("7.1")),
    }
    assert stale_pass_problems(
        manifest, input_md5=SRC_HASH, policy=policy, proposals=proposals, fx=_fx("7.1")
    ) == []
    problems = stale_pass_problems(
        manifest, input_md5=SRC_HASH, policy=policy, proposals=proposals, fx=_fx("7.2")
    )
    assert any("汇率 hash 变化" in p for p in problems)


def test_manifest_records_cny_impact_and_fx():
    proposals = _proposals(_item(delta="100"))
    policy = _policy()
    batch = evaluate_batch(proposals, policy, now=NOW, fx=_fx("7.1"), require_fx=True)
    fields = manifest_policy_fields(
        policy=policy, proposals=proposals, results=batch.results, fx=_fx("7.1"), batch=batch
    )
    assert fields["fx_hash"] == fx_digest(_fx("7.1"))
    assert Decimal(fields["corrections"][0]["impact_cny"]) == Decimal("710")
    assert fields["corrections"][0]["currency"] == "USD"
    assert Decimal(fields["cumulative_impact_cny"]) == Decimal("710.00")


def test_budget_api_is_available_for_reuse():
    proposal = _proposal(_item(delta="100"))
    budget = resolve_impact_budget(proposal, fx=_fx("7.1"), month=PERIOD, require_fx=True)
    assert budget.impact_cny == Decimal("710.00")
    assert budget.fx_rate == Decimal("7.1")
