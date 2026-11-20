# -*- coding: utf-8 -*-
"""R4 依赖 hash 失效与幂等。

验收（``reports/t2_hardening_20261120.md`` R4）：
- 发布调用强制复验 input/master/FX/FBA/例外/evidence/policy/proposal 与目标基线；
- 任一依赖变化旧 PASS 失效；
- 相同 correction 重复运行经济应用次数=1；
- 旧 auto_allowed 结果遇 T2=false 必须拒绝。
"""
from __future__ import annotations

import copy
from datetime import datetime, timedelta, timezone
from decimal import Decimal
from pathlib import Path

import openpyxl
import pandas as pd
import pytest

from correction_policy import (
    fx_digest as _fx_digest,
    STATUS_AUTO_ALLOWED,
    STATUS_PREVIEW,
    build_proposals,
    digest,
    evaluate_batch,
    fx_table_from_mapping,
    manifest_policy_fields,
    parse_policy,
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
    "币种": "USD",
    "AMZJohna账户": "AMZJohnaUS",
    "账期收款额": 5000,
    "销售额": 1000,
    "佣金": 300,
}


def _policy(*, t2_enabled=True, **t2_extra):
    data = {
        "schema_version": 1,
        "policy_id": "amz-r4",
        "version": "1",
        "authorized_by": "测试",
        "created_at": "2026-11-01T00:00:00+08:00",
        "effective_from": "2026-11-01T00:00:00+08:00",
        "effective_to": "2026-12-31T00:00:00+08:00",
        "ttl_hours": 24 * 45,
        "t2": {
            "enabled": t2_enabled,
            "allowed_categories": ["amount_value"],
            "allowed_platforms": ["Amazon"],
            "allowed_fields": ["销售额"],
            "closed_periods": [],
            "max_single_record_impact": "100000",
            "max_batch_impact": "200000",
            **t2_extra,
        },
    }
    return parse_policy(data)


def _item(**overrides):
    item = {
        "correction_id": "T2-202607-1",
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
            "identity_unique": True,
        },
        "currency": "USD",
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


def _fx():
    return fx_table_from_mapping({"USD": "7.1"}, month=PERIOD, source="<test>", source_hash="f" * 32)


# --------------------------------------------------------------- 旧 auto_allowed 遇 T2=false


def test_old_auto_allowed_rejected_when_t2_disabled():
    proposals = _proposals(_item())
    enabled = _policy()
    old = list(evaluate_batch(proposals, enabled, now=NOW, fx=_fx(), require_fx=True).results)
    assert old[0].status == STATUS_AUTO_ALLOWED, old[0].reasons

    disabled = _policy(t2_enabled=False)
    errors = write_gate_errors(
        period=PERIOD,
        policy=disabled,
        proposals=proposals,
        results=old,
        now=NOW,
        fx=_fx(),
        require_fx=True,
    )
    assert errors
    joined = "; ".join(errors)
    assert "POLICY-HASH 变化" in joined
    assert "不再成立" in joined


def test_same_policy_hash_but_t2_turned_off_is_caught_by_rejudge():
    """即使凭据的 policy_hash 被手工改成当前 hash，重判仍会拒绝。"""
    proposals = _proposals(_item())
    enabled = _policy()
    old = list(evaluate_batch(proposals, enabled, now=NOW, fx=_fx(), require_fx=True).results)
    disabled = _policy(t2_enabled=False)
    forged = [type(old[0])(**{**old[0].__dict__, "policy_hash": disabled.hash})]
    errors = write_gate_errors(
        period=PERIOD,
        policy=disabled,
        proposals=proposals,
        results=forged,
        now=NOW,
        fx=_fx(),
        require_fx=True,
    )
    assert any("旧授权按当前政策重判" in e for e in errors)


def test_old_auto_allowed_rejected_when_fx_missing_now():
    proposals = _proposals(_item())
    policy = _policy()
    old = list(evaluate_batch(proposals, policy, now=NOW, fx=_fx(), require_fx=True).results)
    errors = write_gate_errors(
        period=PERIOD, policy=policy, proposals=proposals, results=old, now=NOW, require_fx=True
    )
    assert any("FX" in e for e in errors)


# --------------------------------------------------------------- 依赖 hash


def _manifest(proposals, policy, *, deps=None, baseline="t" * 64):
    manifest = {
        "input_md5": "a" * 32,
        "policy_hash": policy.hash,
        "proposal_hash": proposal_batch_hash(proposals),
        "fx_hash": __import__("correction_policy").fx_digest(_fx()),
        "target_baseline_hash": baseline,
        "dependencies": deps
        or {
            "input_md5": "a" * 32,
            "master_md5": "m" * 32,
            "fx_md5": "f" * 32,
            "fba_hash": "b" * 32,
            "exception_md5": "e" * 32,
        },
    }
    return manifest


@pytest.mark.parametrize(
    "key,new_value",
    [
        ("input_md5", "0" * 32),
        ("master_md5", "0" * 32),
        ("fx_md5", "0" * 32),
        ("fba_hash", "0" * 32),
        ("exception_md5", "0" * 32),
    ],
)
def test_any_dependency_change_invalidates_old_pass(key, new_value):
    proposals = _proposals(_item())
    policy = _policy()
    manifest = _manifest(proposals, policy)
    current = dict(manifest["dependencies"])
    current[key] = new_value
    problems = stale_pass_problems(
        manifest,
        input_md5="a" * 32,
        policy=policy,
        proposals=proposals,
        fx=_fx(),
        dependencies=current,
        target_baseline_hash="t" * 64,
    )
    assert problems
    assert any(key in p for p in problems)


def test_target_baseline_change_invalidates_old_pass():
    proposals = _proposals(_item())
    policy = _policy()
    manifest = _manifest(proposals, policy)
    problems = stale_pass_problems(
        manifest,
        input_md5="a" * 32,
        policy=policy,
        proposals=proposals,
        fx=_fx(),
        dependencies=manifest["dependencies"],
        target_baseline_hash="u" * 64,
    )
    assert any("目标表基线变化" in p for p in problems)


def test_clean_manifest_has_no_stale_problems():
    proposals = _proposals(_item())
    policy = _policy()
    manifest = _manifest(proposals, policy)
    assert stale_pass_problems(
        manifest,
        input_md5="a" * 32,
        policy=policy,
        proposals=proposals,
        fx=_fx(),
        dependencies=manifest["dependencies"],
        target_baseline_hash="t" * 64,
    ) == []


# --------------------------------------------------------------- 幂等


def _write_src(tmp_path: Path) -> Path:
    src = tmp_path / "src.xlsx"
    pd.DataFrame([ROW]).to_excel(src, sheet_name="核算行", index=False)
    return src


def test_same_correction_rerun_applies_economically_once(tmp_path):
    src = _write_src(tmp_path)
    evidence = tmp_path / "ev"
    evidence.mkdir()
    att = evidence / "att.txt"
    att.write_text("x", encoding="utf-8")
    item = _item()
    item["evidence"] = {
        "attachment": "att.txt",
        "attachment_md5": md5_file(att),
        "settlement_id": "25909392482",
        "identity_unique": True,
    }
    payload = {
        "schema_version": 1,
        "revision": "v1",
        "created_at": "2026-11-19T16:20:00+08:00",
        "source_files": {PERIOD: {"md5": md5_file(src)}},
        "corrections": [item],
    }

    out1 = tmp_path / "out1.xlsx"
    first = apply_corrections(
        src=src,
        corrections=payload,
        period=PERIOD,
        out=out1,
        evidence_root=evidence,
        policy=_policy(),
        fx=_fx(),
        require_fx=True,
        now=NOW,
        idempotent=True,
    )
    assert first["economic_applications"] == 1

    # 第二轮：以第一轮的输出为源（行指纹里的 销售额 已变成 after 值）
    payload2 = copy.deepcopy(payload)
    payload2["source_files"][PERIOD]["md5"] = md5_file(out1)
    out2 = tmp_path / "out2.xlsx"
    second = apply_corrections(
        src=out1,
        corrections=payload2,
        period=PERIOD,
        out=out2,
        evidence_root=evidence,
        policy=_policy(),
        fx=_fx(),
        require_fx=True,
        now=NOW,
        idempotent=True,
    )
    assert second["economic_applications"] == 0
    assert second["already_applied"] == ["T2-202607-1"]
    assert first["economic_applications"] + second["economic_applications"] == 1

    ws = openpyxl.load_workbook(out2)["核算行"]
    header = [c.value for c in ws[1]]
    col = {name: i + 1 for i, name in enumerate(header)}
    assert ws.cell(row=2, column=col["销售额"]).value == pytest.approx(1200)


def test_rerun_with_prior_manifest_skips_already_applied(tmp_path):
    src = _write_src(tmp_path)
    evidence = tmp_path / "ev"
    evidence.mkdir()
    att = evidence / "att.txt"
    att.write_text("x", encoding="utf-8")
    item = _item()
    item["evidence"] = {
        "attachment": "att.txt",
        "attachment_md5": md5_file(att),
        "settlement_id": "25909392482",
        "identity_unique": True,
    }
    payload = {
        "schema_version": 1,
        "revision": "v1",
        "created_at": "2026-11-19T16:20:00+08:00",
        "source_files": {PERIOD: {"md5": md5_file(src)}},
        "corrections": [item],
    }
    proposals = build_proposals(payload, period=PERIOD)
    prior = {"corrections": [{"correction_id": item["correction_id"], "proposal_hash": proposals[0].hash}]}
    out = tmp_path / "out.xlsx"
    result = apply_corrections(
        src=src,
        corrections=payload,
        period=PERIOD,
        out=out,
        evidence_root=evidence,
        policy=_policy(),
        fx=_fx(),
        now=NOW,
        idempotent=True,
    )
    assert result["economic_applications"] == 1

    # 第二轮同源：manifest 已记录同 proposal hash → 整条跳过，不再经济应用。
    from remediation import apply_corrections as _apply

    result2 = _apply(
        src=src,
        corrections=payload,
        period=PERIOD,
        out=tmp_path / "out2.xlsx",
        evidence_root=evidence,
        policy=_policy(),
        fx=_fx(),
        now=NOW,
        idempotent=True,
        prior_manifest={
            **prior,
            "input_md5": md5_file(src),
            "policy_hash": _policy().hash,
            "proposal_hash": proposal_batch_hash(proposals),
            "fx_hash": _fx_digest(_fx()),
        },
    )
    assert result2["economic_applications"] == 0
    assert result2["already_applied"] == [item["correction_id"]]


def test_non_idempotent_rerun_still_rejects_double_apply(tmp_path):
    """默认（非幂等）仍把重复应用当错误，不静默双记。"""
    src = _write_src(tmp_path)
    evidence = tmp_path / "ev"
    evidence.mkdir()
    att = evidence / "att.txt"
    att.write_text("x", encoding="utf-8")
    item = _item()
    item["evidence"] = {
        "attachment": "att.txt",
        "attachment_md5": md5_file(att),
        "settlement_id": "25909392482",
        "identity_unique": True,
    }
    payload = {
        "schema_version": 1,
        "revision": "v1",
        "created_at": "2026-11-19T16:20:00+08:00",
        "source_files": {PERIOD: {"md5": md5_file(src)}},
        "corrections": [item],
    }
    out1 = tmp_path / "out1.xlsx"
    apply_corrections(
        src=src,
        corrections=payload,
        period=PERIOD,
        out=out1,
        evidence_root=evidence,
        policy=_policy(),
        fx=_fx(),
        now=NOW,
    )
    payload2 = copy.deepcopy(payload)
    payload2["source_files"][PERIOD]["md5"] = md5_file(out1)
    with pytest.raises(RemediationError, match="命中 0 行|before 不符"):
        apply_corrections(
            src=out1,
            corrections=payload2,
            period=PERIOD,
            out=tmp_path / "out2.xlsx",
            evidence_root=evidence,
            policy=_policy(),
            fx=_fx(),
            now=NOW,
        )
