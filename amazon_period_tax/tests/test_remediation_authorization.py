# -*- coding: utf-8 -*-
"""E2.3 C02：corrections 凭据/授权/证据/字段校验。

覆盖 gate_remediation_plan_20261120.md U-E2 / E2.3：
- 只有 approved + confirmed_by 的修正可应用；pending/rejected/preview 一律拒绝；
- 源 xlsx md5 与附件 md5 都必须与凭据一致；缺 evidence_root 拒绝；
- scope.period / bucket 必须是目标期，空 period 集合不产出 corrected 副本；
- field_changes 必须是 [before, after]，文本列/金额列类型分别校验；
- 行指纹唯一命中、before 必须一致、同格不能重复修正、src≠out、schema_version 受控。
"""
from __future__ import annotations

import copy
from pathlib import Path

import openpyxl
import pandas as pd
import pytest

from remediation import RemediationError, apply_corrections, md5_file

APPROVAL = "202608071439000120006"
PERIOD = "202607"
BUCKET = "账期20260704-20260803"

ROW = {
    "审批编号": APPROVAL,
    "账期日期": "2026-07-22",
    "AMZJohna账户": "AMZJohnaSE",
    "账期收款额": 5684,
    "销售额": 19920,
    "佣金": 14236,
}


def _write_src(tmp_path: Path, rows=None) -> Path:
    src = tmp_path / "src.xlsx"
    pd.DataFrame(rows or [ROW]).to_excel(src, sheet_name="核算行", index=False)
    return src


def _case(tmp_path: Path, rows=None):
    src = _write_src(tmp_path, rows)
    evidence = tmp_path / "evidence"
    evidence.mkdir(exist_ok=True)
    att = evidence / "att.txt"
    att.write_text("attachment evidence", encoding="utf-8")
    corrections = {
        "schema_version": 1,
        "revision": "v1",
        "created_at": "2026-11-19T16:20:00+08:00",
        "source_files": {PERIOD: {"path": str(src), "md5": md5_file(src)}},
        "corrections": [
            {
                "correction_id": "B1-202607-JohnaSE-100x",
                "reason": "OA 定稿把 SEK 金额放大 100 倍",
                "scope": {"period": PERIOD, "bucket": BUCKET, "table": "核算行"},
                "approval_id": APPROVAL,
                "source_row_key": {
                    "账期日期": "2026-07-22",
                    "AMZJohna账户": "AMZJohnaSE",
                    "销售额": "19920",
                },
                "settlement_id": "25909392482",
                "currency": "SEK",
                "account_before": "AMZJohnaSE",
                "account_after": "AMZJohnaSE",
                "field_changes": {
                    "账期收款额": ["5684", "56.84"],
                    "销售额": ["19920", "199.20"],
                    "佣金": ["14236", "142.36"],
                },
                "evidence": {"attachment": "att.txt", "attachment_md5": md5_file(att)},
                "confirmed_by": "用户授权（工程侧按附件修正）",
                "status": "approved",
            }
        ],
    }
    return src, corrections, evidence


def _apply(src, corrections, evidence, tmp_path, **kw):
    return apply_corrections(
        src=src,
        corrections=corrections,
        period=kw.pop("period", PERIOD),
        out=kw.pop("out", tmp_path / "out" / "corrected.xlsx"),
        evidence_root=evidence,
        **kw,
    )


# ---------------------------------------------------------------- 有效路径


def test_valid_approved_applies_only_authorized_cells(tmp_path):
    src, corrections, evidence = _case(tmp_path)
    result = _apply(src, corrections, evidence, tmp_path)
    assert result["applied"][0]["excel_row"] == 2
    assert result["source_md5"] == md5_file(src)

    out = Path(result["out"])
    assert out.is_file()
    ws = openpyxl.load_workbook(out)["核算行"]
    header = [c.value for c in ws[1]]
    col = {name: i + 1 for i, name in enumerate(header)}
    assert ws.cell(row=2, column=col["账期收款额"]).value == pytest.approx(56.84)
    assert ws.cell(row=2, column=col["销售额"]).value == pytest.approx(199.2)
    assert ws.cell(row=2, column=col["佣金"]).value == pytest.approx(142.36)
    # 未授权列保持原值
    assert ws.cell(row=2, column=col["AMZJohna账户"]).value == "AMZJohnaSE"
    # 原件不被改动
    src_ws = openpyxl.load_workbook(src)["核算行"]
    assert src_ws.cell(row=2, column=col["销售额"]).value == 19920


def test_preview_does_not_write(tmp_path):
    src, corrections, evidence = _case(tmp_path)
    out = tmp_path / "out" / "corrected.xlsx"
    result = _apply(src, corrections, evidence, tmp_path, out=out, preview=True)
    assert result["preview"] is True and result["out"] is None
    assert not out.exists()
    assert result["applied"][0]["diffs"]


# ---------------------------------------------------------------- 授权状态


@pytest.mark.parametrize("status", ["pending", "rejected", "draft", "revoked", ""])
def test_unapproved_status_never_applied(tmp_path, status):
    src, corrections, evidence = _case(tmp_path)
    corrections["corrections"][0]["status"] = status
    out = tmp_path / "out" / "corrected.xlsx"
    with pytest.raises(RemediationError, match="未获批准"):
        _apply(src, corrections, evidence, tmp_path, out=out)
    assert not out.exists()


def test_missing_confirmed_by_rejected(tmp_path):
    src, corrections, evidence = _case(tmp_path)
    corrections["corrections"][0]["confirmed_by"] = ""
    with pytest.raises(RemediationError, match="confirmed_by"):
        _apply(src, corrections, evidence, tmp_path)


@pytest.mark.parametrize("marker", ["preview", "draft", "pending"])
def test_preview_top_level_rejected_by_write_entry(tmp_path, marker):
    src, corrections, evidence = _case(tmp_path)
    corrections["status"] = marker
    with pytest.raises(RemediationError, match="preview/draft"):
        _apply(src, corrections, evidence, tmp_path)


# ---------------------------------------------------------------- 期 / hash


def test_empty_period_set_produces_no_corrected_copy(tmp_path):
    src, corrections, evidence = _case(tmp_path)
    out = tmp_path / "out" / "corrected.xlsx"
    with pytest.raises(RemediationError, match="没有任何 corrections"):
        _apply(src, corrections, evidence, tmp_path, period="202608", out=out)
    assert not out.exists()


def test_source_hash_mismatch_rejected(tmp_path):
    src, corrections, evidence = _case(tmp_path)
    corrections["source_files"][PERIOD]["md5"] = "0" * 32
    with pytest.raises(RemediationError, match="源文件 md5 不符"):
        _apply(src, corrections, evidence, tmp_path)


def test_attachment_hash_mismatch_rejected(tmp_path):
    src, corrections, evidence = _case(tmp_path)
    corrections["corrections"][0]["evidence"]["attachment_md5"] = "0" * 32
    with pytest.raises(RemediationError, match="附件 md5 不符"):
        _apply(src, corrections, evidence, tmp_path)


def test_attachment_missing_rejected(tmp_path):
    src, corrections, evidence = _case(tmp_path)
    corrections["corrections"][0]["evidence"]["attachment"] = "nope.txt"
    with pytest.raises(RemediationError, match="附件不存在"):
        _apply(src, corrections, evidence, tmp_path)


def test_missing_evidence_root_rejected(tmp_path):
    src, corrections, evidence = _case(tmp_path)
    with pytest.raises(RemediationError, match="evidence_root"):
        apply_corrections(
            src=src, corrections=corrections, period=PERIOD, out=tmp_path / "o.xlsx", evidence_root=None
        )


def test_bucket_not_mapping_to_period_rejected(tmp_path):
    src, corrections, evidence = _case(tmp_path)
    corrections["corrections"][0]["scope"]["bucket"] = "账期20260804-20260903"
    with pytest.raises(RemediationError, match="映射月"):
        _apply(src, corrections, evidence, tmp_path)


# ---------------------------------------------------------------- 字段类型 / schema


def test_numeric_column_rejects_text_after(tmp_path):
    src, corrections, evidence = _case(tmp_path)
    corrections["corrections"][0]["field_changes"]["销售额"] = ["19920", "abc"]
    with pytest.raises(RemediationError, match="不是合法十进制"):
        _apply(src, corrections, evidence, tmp_path)


def test_numeric_column_rejects_nonfinite_after(tmp_path):
    src, corrections, evidence = _case(tmp_path)
    corrections["corrections"][0]["field_changes"]["销售额"] = ["19920", "NaN"]
    with pytest.raises(RemediationError, match="非有限"):
        _apply(src, corrections, evidence, tmp_path)


def test_text_column_requires_string_after(tmp_path):
    src, corrections, evidence = _case(tmp_path)
    corrections["corrections"][0]["field_changes"]["AMZJohna账户"] = ["AMZJohnaSE", 123]
    with pytest.raises(RemediationError, match="文本列 after"):
        _apply(src, corrections, evidence, tmp_path)


def test_field_change_must_be_pair(tmp_path):
    src, corrections, evidence = _case(tmp_path)
    corrections["corrections"][0]["field_changes"]["销售额"] = ["19920"]
    with pytest.raises(RemediationError, match="二元组"):
        _apply(src, corrections, evidence, tmp_path)


def test_unsupported_schema_version_rejected(tmp_path):
    src, corrections, evidence = _case(tmp_path)
    corrections["schema_version"] = 2
    with pytest.raises(RemediationError, match="schema_version"):
        _apply(src, corrections, evidence, tmp_path)


def test_duplicate_correction_id_rejected(tmp_path):
    src, corrections, evidence = _case(tmp_path)
    corrections["corrections"].append(copy.deepcopy(corrections["corrections"][0]))
    with pytest.raises(RemediationError, match="correction_id 重复"):
        _apply(src, corrections, evidence, tmp_path)


# ---------------------------------------------------------------- 行指纹


def test_duplicate_row_fingerprint_rejected(tmp_path):
    src, corrections, evidence = _case(tmp_path, rows=[ROW, ROW])
    with pytest.raises(RemediationError, match="恰好 1 行"):
        _apply(src, corrections, evidence, tmp_path)


def test_before_mismatch_rejected(tmp_path):
    src, corrections, evidence = _case(tmp_path)
    # 改一个**不在行指纹里**的列并同步源 md5，隔离出「before 不符」
    df = pd.read_excel(src, dtype=str)
    df.loc[0, "佣金"] = "14237"
    df.to_excel(src, sheet_name="核算行", index=False)
    corrections["source_files"][PERIOD]["md5"] = md5_file(src)
    with pytest.raises(RemediationError, match="before 不符"):
        _apply(src, corrections, evidence, tmp_path)


def test_same_cell_corrected_twice_rejected(tmp_path):
    src, corrections, evidence = _case(tmp_path)
    second = copy.deepcopy(corrections["corrections"][0])
    second["correction_id"] = "B1-202607-second"
    # 第一条改完后行指纹里的销售额已变成 199.2，第二条按新值定位到同一行
    second["source_row_key"] = {"账期日期": "2026-07-22", "AMZJohna账户": "AMZJohnaSE", "销售额": "199.2"}
    second["field_changes"] = {"销售额": ["199.2", "1.0"]}
    corrections["corrections"].append(second)
    with pytest.raises(RemediationError, match="重复修正"):
        _apply(src, corrections, evidence, tmp_path)


def test_src_equals_out_rejected(tmp_path):
    src, corrections, evidence = _case(tmp_path)
    with pytest.raises(RemediationError, match="同一个文件"):
        _apply(src, corrections, evidence, tmp_path, out=src)
