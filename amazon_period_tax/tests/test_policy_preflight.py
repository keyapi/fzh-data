# -*- coding: utf-8 -*-
"""F 批：修正策略（T1 自动 / T2 窄通道）+ manifest hash + 写前门禁。

对应 ``gate_remediation_plan_20261120.md`` U-F 与 ``correction_policy_20261120.md``。
覆盖：政策结构/生效期/TTL、T1 自动、T2 各项硬条件与上限、批次上限、已关账、
政策过期、proposal/policy hash 变化、preview 不写、授权命中放行、T3/T4 阻断、
preflight 与 enforce_write_gate 接入、manifest 字段与旧 PASS 失效。
"""
from __future__ import annotations

import copy
import importlib.util
import json
from datetime import datetime, timedelta, timezone
from decimal import Decimal
from pathlib import Path

import openpyxl
import pandas as pd
import pytest

from correction_policy import (
    PolicyError,
    STATUS_AUTO_ALLOWED,
    STATUS_BLOCKED,
    STATUS_APPROVED,
    STATUS_PREVIEW,
    build_proposals,
    digest,
    evaluate_batch,
    evaluate_proposal,
    load_policy,
    manifest_policy_fields,
    parse_policy,
    policy_errors,
    proposal_batch_hash,
    stale_pass_problems,
    write_gate_errors,
)
from remediation import RemediationError, apply_corrections, md5_file

PERIOD = "202607"
BUCKET = "账期20260704-20260803"
APPROVAL = "202608071439000120006"
NOW = datetime(2026, 11, 20, 12, tzinfo=timezone(timedelta(hours=8)))

ROW = {
    "审批编号": APPROVAL,
    "账期日期": "2026-07-22",
    "币种": "SEK",
    "AMZJohna账户": "AMZJohnaSE",
    "账期收款额": 5684,
    "销售额": 19920,
    "佣金": 14236,
}


# --------------------------------------------------------------- 政策工厂


def _policy_data(**overrides) -> dict:
    data = {
        "schema_version": 1,
        "policy_id": "amz-correction-2026Q4",
        "version": "1",
        "authorized_by": "财务账期负责人（测试）",
        "created_at": "2026-11-01T00:00:00+08:00",
        "effective_from": "2026-11-01T00:00:00+08:00",
        "effective_to": "2026-12-31T00:00:00+08:00",
        "ttl_hours": 24 * 45,
        "auto_apply_t1": True,
        "t2": {
            "enabled": True,
            "allowed_categories": ["amount_100x"],
            "allowed_platforms": ["Amazon"],
            "allowed_fields": ["账期收款额", "销售额", "佣金"],
            "closed_periods": [],
            "max_single_record_impact": "50000",
            "max_batch_impact": "100000",
        },
    }
    data.update(overrides)
    return data


def _policy(**overrides):
    return parse_policy(_policy_data(**overrides))


# --------------------------------------------------------------- 凭据工厂


def _evidence_file(tmp_path: Path) -> tuple[Path, str]:
    evidence = tmp_path / "evidence"
    evidence.mkdir(exist_ok=True)
    att = evidence / "att.txt"
    att.write_text("official settlement attachment", encoding="utf-8")
    return evidence, md5_file(att)


def _t1_correction(evidence_dir: Path, **overrides) -> dict:
    item = {
        "correction_id": "T1-202607-currency",
        "kind": "currency_representation",
        "scope": {"period": PERIOD, "bucket": BUCKET, "table": "核算行"},
        "approval_id": APPROVAL,
        "source_row_key": {"账期日期": "2026-07-22", "AMZJohna账户": "AMZJohnaSE"},
        "field_changes": {"币种": ["ＳＥＫ", "SEK"]},
        "evidence": {"rule": "currency-normalize-v1", "evidence_hash": "a" * 64},
    }
    item.update(overrides)
    return item


def _t1_row() -> dict:
    return {**ROW, "币种": "ＳＥＫ"}


def _t2_correction(att_md5: str, **overrides) -> dict:
    item = {
        "correction_id": "T2-202607-JohnaSE-100x",
        "kind": "amount_100x",
        "platform": "Amazon",
        "scope": {"period": PERIOD, "bucket": BUCKET, "table": "核算行"},
        "approval_id": APPROVAL,
        "source_row_key": {
            "账期日期": "2026-07-22",
            "AMZJohna账户": "AMZJohnaSE",
            "销售额": "19920",
        },
        "settlement_id": "25909392482",
        "field_changes": {
            "账期收款额": ["5684", "56.84"],
            "销售额": ["19920", "199.20"],
            "佣金": ["14236", "142.36"],
        },
        "evidence": {
            "attachment": "att.txt",
            "attachment_md5": att_md5,
            "settlement_id": "25909392482",
            "identity_unique": True,
        },
    }
    item.update(overrides)
    return item


def _corrections(src: Path, items: list[dict], *, status: str = "approved") -> dict:
    payload = {
        "schema_version": 1,
        "revision": "v1",
        "created_at": "2026-11-19T16:20:00+08:00",
        "source_files": {PERIOD: {"path": str(src), "md5": md5_file(src)}},
        "corrections": items,
    }
    if status:
        payload["status"] = status
    return payload


def _write_src(tmp_path: Path, rows=None) -> Path:
    src = tmp_path / "src.xlsx"
    pd.DataFrame(rows or [ROW]).to_excel(src, sheet_name="核算行", index=False)
    return src


def _apply(src, corrections, evidence, out, **kw):
    return apply_corrections(
        src=src,
        corrections=corrections,
        period=kw.pop("period", PERIOD),
        out=out,
        evidence_root=evidence,
        **kw,
    )


# =============================================================== 政策结构/有效期


def test_policy_parse_and_hash_is_order_insensitive():
    a = _policy_data()
    b = dict(reversed(list(_policy_data().items())))
    assert parse_policy(a).hash == parse_policy(b).hash
    assert parse_policy(a).policy_id == "amz-correction-2026Q4"


@pytest.mark.parametrize(
    "payload, match",
    [
        ({"schema_version": 99}, "schema_version"),
        ({k: v for k, v in _policy_data().items() if k != "authorized_by"}, "authorized_by"),
        (_policy_data(effective_from="2026-12-01T00:00:00+08:00", effective_to="2026-11-01T00:00:00+08:00"), "effective_to"),
    ],
)
def test_policy_structural_errors_reject(payload, match):
    with pytest.raises(PolicyError, match=match):
        parse_policy(payload)


def test_policy_missing_file_and_bad_json_reject(tmp_path):
    with pytest.raises(PolicyError, match="不存在"):
        load_policy(tmp_path / "nope.json")
    bad = tmp_path / "bad.json"
    bad.write_text("{not json", encoding="utf-8")
    with pytest.raises(PolicyError, match="合法 JSON"):
        load_policy(bad)


def test_expired_policy_blocks_everything(tmp_path):
    policy = _policy(effective_to="2026-11-19T00:00:00+08:00")
    assert policy_errors(policy, now=NOW)
    ev, md5 = _evidence_file(tmp_path)
    proposal = build_proposals(_corrections(_write_src(tmp_path), [_t2_correction(md5)]), period=PERIOD)[0]
    result = evaluate_proposal(proposal, policy, now=NOW)
    assert result.status == STATUS_BLOCKED
    assert any("已过期" in r for r in result.reasons)
    errors = write_gate_errors(period=PERIOD, policy=policy, proposals=[proposal], now=NOW)
    assert errors and "POLICY" in errors[0]


def test_ttl_expiry_rejects_policy():
    policy = _policy(ttl_hours=1)
    assert any("TTL" in p for p in policy_errors(policy, now=NOW))


def test_not_yet_effective_policy_rejects():
    policy = _policy(effective_from="2026-12-01T00:00:00+08:00")
    assert any("尚未生效" in p for p in policy_errors(policy, now=NOW))


# =============================================================== T1 自动


def test_t1_auto_allowed_with_rule_receipt(tmp_path):
    ev, _ = _evidence_file(tmp_path)
    payload = _corrections(_write_src(tmp_path, [_t1_row()]), [_t1_correction(ev)])
    proposal = build_proposals(payload, period=PERIOD)[0]
    result = evaluate_proposal(proposal, _policy(), now=NOW)
    assert result.status == STATUS_AUTO_ALLOWED
    assert write_gate_errors(period=PERIOD, policy=_policy(), proposals=[proposal], now=NOW) == []


def test_t1_applies_without_per_item_approval_and_keeps_receipt(tmp_path):
    ev, _ = _evidence_file(tmp_path)
    src = _write_src(tmp_path, [_t1_row()])
    payload = _corrections(src, [_t1_correction(ev)])
    out = tmp_path / "out" / "corrected.xlsx"
    result = _apply(src, payload, ev, out, policy=_policy(), now=NOW)
    assert Path(result["out"]).is_file()
    assert result["authorization"]["policy_hash"]
    ws = openpyxl.load_workbook(out)["核算行"]
    header = [c.value for c in ws[1]]
    col = {name: i + 1 for i, name in enumerate(header)}
    assert ws.cell(row=2, column=col["币种"]).value == "SEK"


def test_t1_without_rule_receipt_is_blocked(tmp_path):
    ev, _ = _evidence_file(tmp_path)
    payload = _corrections(
        _write_src(tmp_path, [_t1_row()]),
        [_t1_correction(ev, evidence={"evidence_hash": "a" * 64})],
    )
    proposal = build_proposals(payload, period=PERIOD)[0]
    result = evaluate_proposal(proposal, _policy(), now=NOW)
    assert result.status == STATUS_BLOCKED
    assert "rule" in ";".join(result.reasons)


def test_t1_auto_disabled_falls_back_to_preview(tmp_path):
    ev, _ = _evidence_file(tmp_path)
    payload = _corrections(_write_src(tmp_path, [_t1_row()]), [_t1_correction(ev)])
    proposal = build_proposals(payload, period=PERIOD)[0]
    result = evaluate_proposal(proposal, _policy(auto_apply_t1=False), now=NOW)
    assert result.status == STATUS_PREVIEW


# =============================================================== T2 窄通道


def test_t2_auto_allowed_when_all_conditions_hold(tmp_path):
    ev, md5 = _evidence_file(tmp_path)
    payload = _corrections(_write_src(tmp_path), [_t2_correction(md5)])
    proposal = build_proposals(payload, period=PERIOD)[0]
    result = evaluate_proposal(proposal, _policy(), now=NOW)
    assert result.status == STATUS_AUTO_ALLOWED, result.reasons
    assert write_gate_errors(period=PERIOD, policy=_policy(), proposals=[proposal], now=NOW) == []


def test_t2_over_single_limit_requires_manual_approval(tmp_path):
    ev, md5 = _evidence_file(tmp_path)
    payload = _corrections(_write_src(tmp_path), [_t2_correction(md5)])
    proposal = build_proposals(payload, period=PERIOD)[0]
    policy = parse_policy(
        _policy_data(
            t2={
                **_policy_data()["t2"],
                "max_single_record_impact": "1000",
            }
        )
    )
    result = evaluate_proposal(proposal, policy, now=NOW)
    assert result.status == STATUS_PREVIEW
    assert any("超过上限" in r for r in result.reasons)
    errors = write_gate_errors(period=PERIOD, policy=policy, proposals=[proposal], now=NOW)
    assert any("未获授权" in e for e in errors)


def test_t2_batch_limit_blocks_split_into_many(tmp_path):
    ev, md5 = _evidence_file(tmp_path)
    items = [_t2_correction(md5)]
    second = copy.deepcopy(items[0])
    second["correction_id"] = "T2-202607-second"
    second["source_row_key"] = {"账期日期": "2026-07-22", "AMZJohna账户": "AMZJohnaSE", "销售额": "1"}
    items.append(second)
    proposals = build_proposals(_corrections(_write_src(tmp_path), items), period=PERIOD)
    policy = parse_policy(
        _policy_data(t2={**_policy_data()["t2"], "max_single_record_impact": "40000", "max_batch_impact": "60000"})
    )
    batch = evaluate_batch(proposals, policy, now=NOW)
    assert batch.batch_impact > Decimal("60000")
    assert all(r.status == STATUS_PREVIEW for r in batch.results)
    assert any("批次影响" in ";".join(r.reasons) for r in batch.results)


def test_t2_closed_period_requires_restatement_approval(tmp_path):
    ev, md5 = _evidence_file(tmp_path)
    proposal = build_proposals(
        _corrections(_write_src(tmp_path), [_t2_correction(md5)]), period=PERIOD
    )[0]
    policy = parse_policy(
        _policy_data(t2={**_policy_data()["t2"], "closed_periods": [PERIOD]})
    )
    result = evaluate_proposal(proposal, policy, now=NOW)
    assert result.status == STATUS_PREVIEW
    assert any("已关账" in r for r in result.reasons)


def test_t2_field_outside_policy_scope_is_preview(tmp_path):
    ev, md5 = _evidence_file(tmp_path)
    proposal = build_proposals(
        _corrections(_write_src(tmp_path), [_t2_correction(md5)]), period=PERIOD
    )[0]
    policy = parse_policy(
        _policy_data(t2={**_policy_data()["t2"], "allowed_fields": ["销售额"]})
    )
    result = evaluate_proposal(proposal, policy, now=NOW)
    assert result.status == STATUS_PREVIEW
    assert any("字段越界" in r for r in result.reasons)


def test_t2_platform_outside_policy_scope_is_preview(tmp_path):
    ev, md5 = _evidence_file(tmp_path)
    proposal = build_proposals(
        _corrections(_write_src(tmp_path), [_t2_correction(md5, platform="Wayfair")]), period=PERIOD
    )[0]
    result = evaluate_proposal(proposal, _policy(), now=NOW)
    assert result.status == STATUS_PREVIEW
    assert any("平台" in r for r in result.reasons)


def test_t2_missing_identity_unique_is_preview(tmp_path):
    ev, md5 = _evidence_file(tmp_path)
    correction = _t2_correction(md5)
    correction["evidence"] = {
        "attachment": "att.txt",
        "attachment_md5": md5,
        "settlement_id": "25909392482",
    }
    proposal = build_proposals(_corrections(_write_src(tmp_path), [correction]), period=PERIOD)[0]
    result = evaluate_proposal(proposal, _policy(), now=NOW)
    assert result.status == STATUS_PREVIEW
    assert any("identity_unique" in r for r in result.reasons)


def test_t2_without_policy_is_unauthorized(tmp_path):
    ev, md5 = _evidence_file(tmp_path)
    proposal = build_proposals(
        _corrections(_write_src(tmp_path), [_t2_correction(md5)]), period=PERIOD
    )[0]
    errors = write_gate_errors(period=PERIOD, policy=None, proposals=[proposal], now=NOW)
    assert errors and "未加载修正政策" in errors[0]


def test_human_approved_t2_passes_and_applies(tmp_path):
    ev, md5 = _evidence_file(tmp_path)
    src = _write_src(tmp_path)
    correction = _t2_correction(md5)
    correction.update({"status": "approved", "confirmed_by": "财务账期负责人"})
    payload = _corrections(src, [correction])
    proposal = build_proposals(payload, period=PERIOD)[0]
    result = evaluate_proposal(proposal, _policy(), now=NOW)
    assert result.status == STATUS_APPROVED
    out = tmp_path / "out" / "corrected.xlsx"
    applied = _apply(src, payload, ev, out, policy=_policy(), now=NOW)
    assert Path(applied["out"]).is_file()


def test_human_approval_waives_identity_unique_but_not_attachment(tmp_path):
    """人工签字可确认身份（不要求机器声明 identity_unique），但附件/hash 仍是硬条件。"""
    ev, md5 = _evidence_file(tmp_path)
    correction = _t2_correction(md5)
    correction["evidence"] = {
        "attachment": "att.txt",
        "attachment_md5": md5,
        "settlement_id": "25909392482",
    }
    correction.update({"status": "approved", "confirmed_by": "财务账期负责人"})
    proposal = build_proposals(_corrections(_write_src(tmp_path), [correction]), period=PERIOD)[0]
    assert evaluate_proposal(proposal, _policy(), now=NOW).status == STATUS_APPROVED

    no_attachment = copy.deepcopy(correction)
    no_attachment["evidence"] = {"settlement_id": "25909392482", "identity_unique": True}
    proposal = build_proposals(
        _corrections(_write_src(tmp_path), [no_attachment]), period=PERIOD
    )[0]
    assert evaluate_proposal(proposal, _policy(), now=NOW).status == STATUS_BLOCKED


def test_unclassified_kind_never_auto_allowed(tmp_path):
    ev, md5 = _evidence_file(tmp_path)
    unknown = _t2_correction(md5)
    unknown.pop("kind")
    proposal = build_proposals(_corrections(_write_src(tmp_path), [unknown]), period=PERIOD)[0]
    result = evaluate_proposal(proposal, _policy(), now=NOW)
    assert result.tier == "UNKNOWN"
    assert result.status == STATUS_PREVIEW


@pytest.mark.parametrize("kind", ["missing_attachment", "unknown_account", "alias_conflict"])
def test_t3_t4_blocked_even_with_approval(tmp_path, kind):
    ev, md5 = _evidence_file(tmp_path)
    correction = _t2_correction(md5, kind=kind)
    correction.update({"status": "approved", "confirmed_by": "财务"})
    proposal = build_proposals(_corrections(_write_src(tmp_path), [correction]), period=PERIOD)[0]
    result = evaluate_proposal(proposal, _policy(), now=NOW)
    assert result.status == STATUS_BLOCKED
    assert "先修来源" in ";".join(result.reasons)


# =============================================================== hash 绑定


def test_proposal_hash_change_invalidates_authorization(tmp_path):
    ev, md5 = _evidence_file(tmp_path)
    src = _write_src(tmp_path)
    payload = _corrections(src, [_t2_correction(md5)])
    proposals = build_proposals(payload, period=PERIOD)
    authorized = list(evaluate_batch(proposals, _policy(), now=NOW).results)

    tampered = copy.deepcopy(payload)
    tampered["corrections"][0]["field_changes"]["销售额"] = ["19920", "199.21"]
    new_proposals = build_proposals(tampered, period=PERIOD)
    errors = write_gate_errors(
        period=PERIOD, policy=_policy(), proposals=new_proposals, results=authorized, now=NOW
    )
    assert any("PROPOSAL-HASH 变化" in e for e in errors)


def test_policy_hash_change_invalidates_old_pass(tmp_path):
    ev, md5 = _evidence_file(tmp_path)
    proposals = build_proposals(
        _corrections(_write_src(tmp_path), [_t2_correction(md5)]), period=PERIOD
    )
    old_policy = _policy()
    authorized = list(evaluate_batch(proposals, old_policy, now=NOW).results)
    new_policy = parse_policy(_policy_data(version="2"))
    errors = write_gate_errors(
        period=PERIOD, policy=new_policy, proposals=proposals, results=authorized, now=NOW
    )
    assert any("POLICY-HASH 变化" in e for e in errors)


def test_authorization_results_with_hash_match_allow_write(tmp_path):
    ev, md5 = _evidence_file(tmp_path)
    src = _write_src(tmp_path)
    payload = _corrections(src, [_t2_correction(md5)])
    proposals = build_proposals(payload, period=PERIOD)
    batch = evaluate_batch(proposals, _policy(), now=NOW)
    assert batch.publishable
    out = tmp_path / "out" / "corrected.xlsx"
    result = _apply(
        src, payload, ev, out, policy=_policy(), authorization=list(batch.results), now=NOW
    )
    assert Path(result["out"]).is_file()


def test_unknown_correction_id_in_authorization_rejected(tmp_path):
    ev, md5 = _evidence_file(tmp_path)
    proposals = build_proposals(
        _corrections(_write_src(tmp_path), [_t2_correction(md5)]), period=PERIOD
    )
    results = list(evaluate_batch(proposals, _policy(), now=NOW).results)
    results[0] = type(results[0])(
        **{**results[0].__dict__, "correction_id": "other-id"}
    )
    errors = write_gate_errors(
        period=PERIOD, policy=_policy(), proposals=proposals, results=results, now=NOW
    )
    assert any("未知 correction_id" in e for e in errors)


# =============================================================== 写入口


def test_preview_with_policy_writes_nothing(tmp_path):
    ev, _ = _evidence_file(tmp_path)
    src = _write_src(tmp_path, [_t1_row()])
    payload = _corrections(src, [_t1_correction(ev)])
    out = tmp_path / "out" / "corrected.xlsx"
    result = _apply(src, payload, ev, out, policy=_policy(), preview=True, now=NOW)
    assert result["preview"] is True and result["out"] is None
    assert not out.exists()


def test_expired_policy_apply_fails_before_touching_workbook(tmp_path):
    ev, md5 = _evidence_file(tmp_path)
    src = _write_src(tmp_path)
    payload = _corrections(src, [_t2_correction(md5)])
    out = tmp_path / "out" / "corrected.xlsx"
    with pytest.raises(RemediationError, match="授权门禁未通过"):
        _apply(src, payload, ev, out, policy=_policy(effective_to="2026-11-19T00:00:00+08:00"), now=NOW)
    assert not out.exists()


def test_unauthorized_t2_apply_fails(tmp_path):
    ev, md5 = _evidence_file(tmp_path)
    src = _write_src(tmp_path)
    payload = _corrections(src, [_t2_correction(md5)])
    out = tmp_path / "out" / "corrected.xlsx"
    with pytest.raises(RemediationError, match="授权门禁未通过"):
        _apply(src, payload, ev, out, policy=None, authorization=[], now=NOW)
    assert not out.exists()


def test_prior_manifest_changed_input_invalidates_old_pass(tmp_path):
    ev, md5 = _evidence_file(tmp_path)
    src = _write_src(tmp_path)
    payload = _corrections(src, [_t2_correction(md5)])
    proposals = build_proposals(payload, period=PERIOD)
    manifest = {
        "input_md5": "f" * 32,
        "policy_hash": _policy().hash,
        "proposal_hash": proposal_batch_hash(proposals),
    }
    out = tmp_path / "out" / "corrected.xlsx"
    with pytest.raises(RemediationError, match="旧 PASS 已失效"):
        _apply(src, payload, ev, out, policy=_policy(), prior_manifest=manifest, now=NOW)
    assert not out.exists()


# =============================================================== manifest


def test_manifest_binds_policy_and_proposal_hashes(tmp_path):
    ev, md5 = _evidence_file(tmp_path)
    proposals = build_proposals(
        _corrections(_write_src(tmp_path), [_t2_correction(md5)]), period=PERIOD
    )
    policy = _policy()
    batch = evaluate_batch(proposals, policy, now=NOW)
    fields = manifest_policy_fields(policy=policy, proposals=proposals, results=batch.results)
    assert fields["policy_hash"] == policy.hash
    assert fields["proposal_hash"] == proposal_batch_hash(proposals)
    assert fields["corrections"][0]["correction_id"] == "T2-202607-JohnaSE-100x"
    assert fields["corrections"][0]["evidence_hash"] == md5
    assert fields["corrections"][0]["status"] == STATUS_AUTO_ALLOWED


def test_stale_pass_problems_detects_each_hash_change(tmp_path):
    ev, md5 = _evidence_file(tmp_path)
    payload = _corrections(_write_src(tmp_path), [_t2_correction(md5)])
    proposals = build_proposals(payload, period=PERIOD)
    policy = _policy()
    manifest = {
        "input_md5": md5_file(Path(payload["source_files"][PERIOD]["path"])),
        "policy_hash": policy.hash,
        "proposal_hash": proposal_batch_hash(proposals),
    }
    assert stale_pass_problems(
        manifest, input_md5=manifest["input_md5"], policy=policy, proposals=proposals
    ) == []
    assert stale_pass_problems(
        manifest, input_md5="0" * 32, policy=policy, proposals=proposals
    )
    assert stale_pass_problems(
        manifest, input_md5=manifest["input_md5"], policy=_policy(version="2"), proposals=proposals
    )
    tampered = build_proposals(
        {**payload, "corrections": [{**payload["corrections"][0], "impact": "1"}]},
        period=PERIOD,
    )
    assert stale_pass_problems(
        manifest, input_md5=manifest["input_md5"], policy=policy, proposals=tampered
    )


# =============================================================== preflight 接入


def _clean_frames():
    df = pd.DataFrame(
        {
            "审批编号": ["A1"],
            "销售账户": ["AMZA"],
            "渠道账号": ["AMZA"],
            "运营人员": ["甲"],
            "收款归属": ["P卡"],
            "选择平台": ["亚马逊"],
            "应收金额": [100.0],
            "销售额": [200.0],
            "应收金额_人民币": [700.0],
            "销售额_人民币": [1400.0],
        }
    )
    df_group = pd.DataFrame(
        {
            "渠道账号": ["AMZA"],
            "应收金额_人民币": [700.0],
            "销售额_人民币": [1400.0],
            "收款费用累加人民币": [0.0],
        }
    )
    df_account = pd.DataFrame(
        {"渠道": ["Amazon"], "渠道账号": ["AMZA"], "运营人员": ["甲"]}
    )
    return df, df_group, df_account


def _preflight(proposals=(), policy=None, results=None):
    from phase3_merge import preflight_write_errors

    df, df_group, df_account = _clean_frames()
    empty = pd.DataFrame(columns=["渠道账号", "Tax amount人民币"])
    return preflight_write_errors(
        df,
        df_group=df_group,
        df_merged=empty,
        df_tax=empty,
        df_sep=pd.DataFrame(),
        df_account=df_account,
        approval_filter=pd.Series([True], index=df.index),
        correction_policy=policy,
        correction_proposals=proposals,
        authorization_results=results,
        correction_period=PERIOD,
        now=NOW,
    )


def test_preflight_without_proposals_unchanged():
    assert _preflight() == []


def test_preflight_blocks_unauthorized_t2(tmp_path):
    ev, md5 = _evidence_file(tmp_path)
    proposals = build_proposals(
        _corrections(_write_src(tmp_path), [_t2_correction(md5)]), period=PERIOD
    )
    policy = parse_policy(
        _policy_data(t2={**_policy_data()["t2"], "max_single_record_impact": "1"})
    )
    problems = _preflight(proposals=proposals, policy=policy)
    assert any("未获授权" in p for p in problems)


def test_preflight_allows_authorized_t2(tmp_path):
    ev, md5 = _evidence_file(tmp_path)
    proposals = build_proposals(
        _corrections(_write_src(tmp_path), [_t2_correction(md5)]), period=PERIOD
    )
    assert _preflight(proposals=proposals, policy=_policy()) == []


def test_preflight_blocks_expired_policy(tmp_path):
    ev, md5 = _evidence_file(tmp_path)
    proposals = build_proposals(
        _corrections(_write_src(tmp_path), [_t2_correction(md5)]), period=PERIOD
    )
    problems = _preflight(
        proposals=proposals, policy=_policy(effective_to="2026-11-19T00:00:00+08:00")
    )
    assert any("POLICY" in p and "过期" in p for p in problems)


def test_preflight_blocks_hash_change(tmp_path):
    ev, md5 = _evidence_file(tmp_path)
    payload = _corrections(_write_src(tmp_path), [_t2_correction(md5)])
    proposals = build_proposals(payload, period=PERIOD)
    results = list(evaluate_batch(proposals, _policy(), now=NOW).results)
    tampered = copy.deepcopy(payload)
    tampered["corrections"][0]["field_changes"]["销售额"] = ["19920", "199.21"]
    problems = _preflight(
        proposals=build_proposals(tampered, period=PERIOD), policy=_policy(), results=results
    )
    assert any("PROPOSAL-HASH 变化" in p for p in problems)


def test_preflight_rejects_other_period_proposal(tmp_path):
    ev, md5 = _evidence_file(tmp_path)
    correction = _t2_correction(md5)
    correction["scope"] = {**correction["scope"], "period": "202608"}
    proposals = build_proposals(
        _corrections(_write_src(tmp_path), [correction]), period="202608"
    )
    problems = _preflight(proposals=proposals, policy=_policy())
    assert any("期间" in p for p in problems)


# =============================================================== CLI 门禁


_PATH = Path(__file__).resolve().parents[1] / "scripts" / "run_period_tax.py"
_spec = importlib.util.spec_from_file_location("run_period_tax_policy_gate", _PATH)
assert _spec and _spec.loader
_mod = importlib.util.module_from_spec(_spec)
_spec.loader.exec_module(_mod)
enforce_write_gate = _mod.enforce_write_gate


def test_enforce_write_gate_blocks_policy_problems_on_publish():
    with pytest.raises(SystemExit, match="修正政策未通过"):
        enforce_write_gate(
            strict=False,
            strict_failures=[],
            master_problems=[],
            publish_requested=True,
            publish_blockers=[],
            policy_problems=["POLICY: 政策已过期"],
        )


def test_enforce_write_gate_blocks_policy_problems_even_without_publish():
    """显式政策无效时连本地 xlsx 也不写：过早失败胜过写一半再报错。"""
    with pytest.raises(SystemExit, match="修正政策未通过"):
        enforce_write_gate(
            strict=False,
            strict_failures=[],
            master_problems=[],
            publish_requested=False,
            policy_problems=["POLICY: 政策已过期"],
        )


def test_enforce_write_gate_clean_policy_passes():
    enforce_write_gate(
        strict=False,
        strict_failures=[],
        master_problems=[],
        publish_requested=True,
        publish_blockers=[],
        policy_problems=[],
    )
