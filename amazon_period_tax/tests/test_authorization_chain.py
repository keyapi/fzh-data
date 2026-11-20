# -*- coding: utf-8 -*-
"""R2 授权链与入口：approved 必须绑定 proposal hash / 依据 / 角色 / 时间 / scope。

验收（``reports/t2_hardening_20261120.md`` R2）：
- 伪 confirmed_by、preview 伪 approved、过期 policy、换证据、错期、
  空 proposal 但输入与批准源不符 → 拒绝且 writer=0；
- T3/T4 不可签字绕过；
- 硬身份/有效期/期间检查先于任何批准捷径。
"""
from __future__ import annotations

import copy
from datetime import datetime, timedelta, timezone
from pathlib import Path

import pandas as pd
import pytest

from correction_policy import (
    STATUS_APPROVED,
    STATUS_BLOCKED,
    build_proposals,
    evaluate_proposal,
    parse_policy,
    proposal_hash,
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
    "币种": "USD",
    "AMZJohna账户": "AMZJohnaUS",
    "账期收款额": 5000,
    "销售额": 1000,
    "佣金": 300,
}


def _policy(**overrides):
    data = {
        "schema_version": 1,
        "policy_id": "amz-r2",
        "version": "1",
        "authorized_by": "测试",
        "created_at": "2026-11-01T00:00:00+08:00",
        "effective_from": "2026-11-01T00:00:00+08:00",
        "effective_to": "2026-12-31T00:00:00+08:00",
        "ttl_hours": 24 * 45,
        "authorization": {"require_receipt": True, "allowed_roles": ["财务账期负责人", "工程验收"]},
        "t2": {
            "enabled": True,
            "allowed_categories": ["amount_value"],
            "allowed_platforms": ["Amazon"],
            "allowed_fields": ["销售额"],
            "closed_periods": [],
            "max_single_record_impact": "100000",
            "max_batch_impact": "200000",
        },
    }
    data.update(overrides)
    return parse_policy(data)


def _item(**overrides):
    item = {
        "correction_id": "T2-202607-JohnaUS",
        "kind": "amount_value",
        "platform": "Amazon",
        "scope": {"period": PERIOD, "bucket": BUCKET},
        "approval_id": APPROVAL,
        "source_row_key": {"审批编号": APPROVAL},
        "field_changes": {"销售额": ["1000", "1200"]},
        "evidence": {
            "attachment": "att.txt",
            "attachment_md5": "b" * 32,
            "settlement_id": "25909392482",
        },
        "currency": "USD",
        "status": "approved",
        "confirmed_by": "财务账期负责人",
    }
    item.update(overrides)
    return item


def _proposals(*items):
    return build_proposals(
        {"schema_version": 1, "revision": "v1",
         "source_files": {PERIOD: {"md5": "a" * 32}},
         "corrections": list(items)},
        period=PERIOD,
    )


def _receipt(proposal, **overrides):
    receipt = {
        "proposal_hash": proposal_hash(proposal),
        "authority_ref": "用户委托 2026-11-19 / 钉钉审批单 202608071439000120006",
        "role": "财务账期负责人",
        "decided_by": "财务账期负责人",
        "decided_at": "2026-11-19T16:20:00+08:00",
        "scope": {"period": PERIOD, "platform": "Amazon", "correction_ids": [proposal.correction_id]},
    }
    receipt.update(overrides)
    return receipt


def _approved(item_kwargs=None, *, receipt_overrides=None, fx_required=False):
    """构造一条带合法授权凭据的 approved 修正（proposal hash 先算出来再回填）。"""
    base = _item(**(item_kwargs or {}))
    proposal = _proposals(base)[0]
    base = copy.deepcopy(base)
    base["authorization"] = _receipt(proposal, **(receipt_overrides or {}))
    return build_proposals(
        {"schema_version": 1, "revision": "v1",
         "source_files": {PERIOD: {"md5": "a" * 32}},
         "corrections": [base]},
        period=PERIOD,
    )[0]


# --------------------------------------------------------------- 凭据本身


def test_valid_receipt_is_approved():
    proposal = _approved()
    result = evaluate_proposal(proposal, _policy(), now=NOW, require_receipt=True)
    assert result.status == STATUS_APPROVED, result.reasons


def test_fake_confirmed_by_without_receipt_is_blocked():
    proposal = _proposals(_item())[0]  # approved + confirmed_by，但没有 authorization
    result = evaluate_proposal(proposal, _policy(), now=NOW, require_receipt=True)
    assert result.status == STATUS_BLOCKED
    assert any("授权凭据" in r for r in result.reasons)


def test_preview_with_confirmed_by_cannot_pass_as_approved():
    proposal = _proposals(_item(status="preview"))[0]
    result = evaluate_proposal(proposal, _policy(), now=NOW, require_receipt=True)
    assert result.status == STATUS_BLOCKED
    assert any("不能当 approved" in r for r in result.reasons)


def test_receipt_bound_to_other_proposal_is_rejected_after_evidence_change():
    proposal = _approved()
    tampered = _item()
    tampered["field_changes"] = {"销售额": ["1000", "1200"]}
    tampered["evidence"] = {**tampered["evidence"], "attachment_md5": "c" * 32}  # 换证据
    tampered["authorization"] = proposal.authorization  # 复用旧凭据
    result = evaluate_proposal(_proposals(tampered)[0], _policy(), now=NOW, require_receipt=True)
    assert result.status == STATUS_BLOCKED
    assert any("别的 proposal" in r for r in result.reasons)


def test_receipt_wrong_scope_period_rejected():
    proposal = _approved(receipt_overrides={"scope": {"period": "202608"}})
    result = evaluate_proposal(proposal, _policy(), now=NOW, require_receipt=True)
    assert result.status == STATUS_BLOCKED
    assert any("scope.period" in r for r in result.reasons)


def test_receipt_role_outside_policy_rejected():
    proposal = _approved(receipt_overrides={"role": "运营"})
    result = evaluate_proposal(proposal, _policy(), now=NOW, require_receipt=True)
    assert result.status == STATUS_BLOCKED
    assert any("角色" in r for r in result.reasons)


def test_receipt_future_timestamp_rejected():
    future = (NOW + timedelta(days=3)).isoformat()
    proposal = _approved(receipt_overrides={"decided_at": future})
    result = evaluate_proposal(proposal, _policy(), now=NOW, require_receipt=True)
    assert result.status == STATUS_BLOCKED
    assert any("未来" in r for r in result.reasons)


def test_receipt_outside_policy_validity_rejected():
    old = "2026-10-01T00:00:00+08:00"  # 早于 effective_from
    proposal = _approved(receipt_overrides={"decided_at": old})
    result = evaluate_proposal(proposal, _policy(), now=NOW, require_receipt=True)
    assert result.status == STATUS_BLOCKED
    assert any("早于政策生效期" in r for r in result.reasons)


def test_receipt_decided_by_mismatch_with_confirmed_by_rejected():
    proposal = _approved(receipt_overrides={"decided_by": "别人"})
    result = evaluate_proposal(proposal, _policy(), now=NOW, require_receipt=True)
    assert result.status == STATUS_BLOCKED
    assert any("decided_by" in r for r in result.reasons)


# --------------------------------------------------------------- 硬检查先于批准


def test_wrong_period_is_blocked_before_approval_shortcut():
    proposal = _approved()
    result = evaluate_proposal(
        proposal, _policy(), now=NOW, require_receipt=True, expected_period="202608"
    )
    assert result.status == STATUS_BLOCKED
    assert any("目标期" in r for r in result.reasons)


def test_expired_policy_beats_approval_receipt():
    proposal = _approved()
    policy = _policy(effective_to="2026-11-19T00:00:00+08:00")
    result = evaluate_proposal(proposal, policy, now=NOW, require_receipt=True)
    assert result.status == STATUS_BLOCKED
    assert any("已过期" in r for r in result.reasons)


@pytest.mark.parametrize("kind", ["missing_attachment", "unknown_account"])
def test_t3_t4_cannot_be_signed_off(kind):
    base = _item(kind=kind)
    proposal = _proposals(base)[0]
    base["authorization"] = _receipt(proposal)
    result = evaluate_proposal(
        _proposals(base)[0], _policy(), now=NOW, require_receipt=True
    )
    assert result.status == STATUS_BLOCKED
    assert any("先修来源" in r for r in result.reasons)


# --------------------------------------------------------------- 空 proposal / 批准源


def test_empty_proposal_with_mismatched_approved_source_is_rejected():
    errors = write_gate_errors(
        period=PERIOD,
        policy=_policy(),
        proposals=[],
        input_md5="a" * 32,
        approved_input_md5="b" * 32,
    )
    assert errors and "输入与批准源不符" in errors[0]


def test_empty_proposal_with_matching_approved_source_passes():
    assert write_gate_errors(
        period=PERIOD,
        policy=_policy(),
        proposals=[],
        input_md5="a" * 32,
        approved_input_md5="a" * 32,
    ) == []


def test_require_proposals_rejects_empty_declaration():
    errors = write_gate_errors(period=PERIOD, policy=_policy(), proposals=[], require_proposals=True)
    assert errors and "空 proposal" in errors[0]


# --------------------------------------------------------------- writer=0


def _case(tmp_path: Path, *, item=None):
    src = tmp_path / "src.xlsx"
    pd.DataFrame([ROW]).to_excel(src, sheet_name="核算行", index=False)
    evidence = tmp_path / "evidence"
    evidence.mkdir(exist_ok=True)
    att = evidence / "att.txt"
    att.write_text("attachment", encoding="utf-8")
    if item is None:
        item = _item()
    item = copy.deepcopy(item)
    item.setdefault("evidence", {})
    item["evidence"]["attachment"] = "att.txt"
    item["evidence"]["attachment_md5"] = md5_file(att)
    payload = {
        "schema_version": 1,
        "revision": "v1",
        "created_at": "2026-11-19T16:20:00+08:00",
        "source_files": {PERIOD: {"md5": md5_file(src)}},
        "corrections": [item],
    }
    return src, evidence, payload


def _attach_receipt(payload):
    """按当前 proposal hash 生成合法授权凭据（模拟「批准的就是这份输入」）。"""
    proposals = build_proposals(payload, period=PERIOD)
    for item, proposal in zip(payload["corrections"], proposals):
        item["authorization"] = _receipt(proposal)
    return payload


def test_fake_approval_writes_nothing(tmp_path):
    src, evidence, payload = _case(tmp_path, item=_item())  # approved+confirmed_by，无凭据
    out = tmp_path / "out" / "corrected.xlsx"
    with pytest.raises(RemediationError, match="授权门禁未通过"):
        apply_corrections(
            src=src,
            corrections=payload,
            period=PERIOD,
            out=out,
            evidence_root=evidence,
            policy=_policy(),
            require_receipt=True,
            now=NOW,
        )
    assert not out.exists()


def test_valid_receipt_writes_corrected_copy(tmp_path):
    src, evidence, payload = _case(tmp_path)
    payload = _attach_receipt(payload)
    out = tmp_path / "out" / "corrected.xlsx"
    result = apply_corrections(
        src=src,
        corrections=payload,
        period=PERIOD,
        out=out,
        evidence_root=evidence,
        policy=_policy(),
        require_receipt=True,
        now=NOW,
        src_md5=md5_file(src),
    )
    assert out.is_file()
    assert result["economic_applications"] == 1


def test_approval_for_other_source_is_rejected(tmp_path):
    src, evidence, payload = _case(tmp_path)
    payload = _attach_receipt(payload)
    out = tmp_path / "out" / "corrected.xlsx"
    with pytest.raises(RemediationError, match="输入与批准源不符"):
        apply_corrections(
            src=src,
            corrections=payload,
            period=PERIOD,
            out=out,
            evidence_root=evidence,
            policy=_policy(),
            require_receipt=True,
            approved_input_md5="f" * 32,
            now=NOW,
        )
    assert not out.exists()
