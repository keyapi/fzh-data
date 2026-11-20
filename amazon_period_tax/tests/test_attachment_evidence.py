# -*- coding: utf-8 -*-
"""非 Amazon 最小证据：CSV/XLSX 金额出现性（不 substring）、签字清单、例外失效。"""
from __future__ import annotations

from datetime import date
from decimal import Decimal

from attachment_evidence import (
    AmountFormat,
    PENDING,
    SIGNED,
    build_entry,
    find_amount_occurrences,
    history_anomaly_hint,
    sha256_file,
    sign_entry,
    worklist_summary,
)


def _write_csv(tmp_path, name: str, text: str) -> str:
    p = tmp_path / name
    p.write_text(text, encoding="utf-8-sig")
    return str(p)


def _write_xlsx(tmp_path, name: str, rows: list[list]) -> str:
    from openpyxl import Workbook

    p = tmp_path / name
    wb = Workbook()
    ws = wb.active
    ws.title = "明细"
    for row in rows:
        ws.append(row)
    wb.save(p)
    wb.close()
    return str(p)


def test_csv_single_amount_occurrence(tmp_path):
    path = _write_csv(tmp_path, "a.csv", "账户,应收,销售额\nWFUS,123.45,999.00\n")
    result = find_amount_occurrences(path, Decimal("123.45"))
    assert result.kind == "csv"
    assert result.status == "occurrence_only"
    assert len(result.occurrences) == 1
    occ = result.occurrences[0]
    assert (occ.row, occ.col, occ.header) == (2, 2, "应收")
    assert occ.value == Decimal("123.45")


def test_xlsx_single_amount_occurrence_with_sheet_location(tmp_path):
    path = _write_xlsx(tmp_path, "a.xlsx", [["账户", "应收"], ["WFUS", 123.45]])
    result = find_amount_occurrences(path, Decimal("123.45"))
    assert result.kind == "xlsx"
    assert result.status == "occurrence_only"
    assert result.occurrences[0].sheet == "明细"
    assert result.occurrences[0].cell == "B2"


def test_multiple_occurrences_are_ambiguous(tmp_path):
    path = _write_csv(tmp_path, "a.csv", "a,b\n100.00,\n100.00,\n")
    result = find_amount_occurrences(path, Decimal("100.00"))
    assert result.status == "ambiguous"
    assert len(result.occurrences) == 2


def test_hundred_never_matches_thousand(tmp_path):
    path = _write_csv(tmp_path, "a.csv", "a\n1000\n1000.00\n")
    result = find_amount_occurrences(path, Decimal("100"))
    assert result.status == "mismatch"


def test_positive_ten_never_matches_negative_ten(tmp_path):
    path = _write_csv(tmp_path, "a.csv", "a\n-10\n")
    result = find_amount_occurrences(path, Decimal("10"))
    assert result.status == "mismatch"


def test_ambiguous_comma_is_not_guessed_as_integer(tmp_path):
    path = _write_csv(tmp_path, "a.csv", "a\n1,23\n")
    strict = find_amount_occurrences(path, Decimal("123"), fmt=AmountFormat(delimiter=";"))
    assert strict.status == "mismatch"
    auto = find_amount_occurrences(
        path, Decimal("1.23"), fmt=AmountFormat(delimiter=";", decimal_separator="auto")
    )
    assert auto.status == "occurrence_only"
    assert auto.occurrences[0].value == Decimal("1.23")


def test_long_numeric_id_is_not_treated_as_amount(tmp_path):
    path = _write_csv(tmp_path, "a.csv", "id,amount\n202607091719000391680,\n")
    result = find_amount_occurrences(path, Decimal("202607091719000391680"))
    assert result.status == "mismatch"


def test_declared_semicolon_and_thousands_format(tmp_path):
    path = _write_csv(tmp_path, "a.csv", '账户;应收\nWFUS;1234,56\n')
    result = find_amount_occurrences(
        path, Decimal("1234.56"), fmt=AmountFormat(delimiter=";", decimal_separator="auto")
    )
    assert result.status == "occurrence_only"


def test_unsupported_pdf_goes_to_manual_not_dropped(tmp_path):
    p = tmp_path / "a.pdf"
    p.write_bytes(b"%PDF-1.4 fake")
    result = find_amount_occurrences(str(p), Decimal("100"))
    assert result.status == "unsupported"
    entry = build_entry(
        row_id="R1",
        platform="Walmart",
        account="WFUS",
        currency="USD",
        oa_amount=Decimal("100"),
        attachment_name=p.name,
        attachment_sha256=result.sha256,
        result=result,
    )
    assert entry.status == PENDING
    assert entry.reason == "unsupported_format:.pdf"


def test_missing_amount_goes_to_manual_with_reason(tmp_path):
    path = _write_csv(tmp_path, "a.csv", "a\n1.00\n")
    result = find_amount_occurrences(path, Decimal("2.00"))
    entry = build_entry(
        row_id="R1",
        platform="Walmart",
        account="WFUS",
        currency="USD",
        oa_amount=Decimal("2.00"),
        attachment_name="a.csv",
        attachment_sha256=result.sha256,
        result=result,
    )
    assert entry.status == PENDING
    assert entry.reason == "mismatch"


def _signed_entry(tmp_path, amount="100.00", valid_until="2026-12-31"):
    path = _write_csv(tmp_path, "s.csv", f"a\n{amount}\n")
    sha = sha256_file(path)
    return (
        build_entry(
            row_id="R1",
            platform="Walmart",
            account="WFUS",
            currency="USD",
            oa_amount=Decimal(amount),
            attachment_name="s.csv",
            attachment_sha256=sha,
        ),
        sha,
    )


def test_valid_signature_passes(tmp_path):
    entry, sha = _signed_entry(tmp_path)
    signed = sign_entry(
        entry,
        transcribed_value="100.00",
        checker="张三",
        finance_reviewer="李四",
        approved_at="2026-08-01",
        proposal_hash="p" * 64,
        valid_until="2026-12-31",
    )
    ok, why = signed.is_signed(today=date(2026, 8, 15), observed_sha256=sha)
    assert (ok, why) == (True, "signed")


def test_signature_hash_change_invalidates(tmp_path):
    entry, _ = _signed_entry(tmp_path)
    signed = sign_entry(
        entry,
        transcribed_value="100.00",
        checker="张三",
        finance_reviewer="李四",
        approved_at="2026-08-01",
        proposal_hash="p" * 64,
    )
    ok, why = signed.is_signed(today=date(2026, 8, 15), observed_sha256="0" * 64)
    assert (ok, why) == (False, "attachment_hash_changed")


def test_incomplete_signature_is_not_signed(tmp_path):
    entry, _ = _signed_entry(tmp_path)
    signed = sign_entry(
        entry,
        transcribed_value="100.00",
        checker="张三",
        finance_reviewer="",
        approved_at="2026-08-01",
        proposal_hash="p" * 64,
    )
    ok, why = signed.is_signed(today=date(2026, 8, 15))
    assert ok is False
    assert "signature_incomplete" in why


def test_expired_signature_is_invalid(tmp_path):
    entry, _ = _signed_entry(tmp_path)
    signed = sign_entry(
        entry,
        transcribed_value="100.00",
        checker="张三",
        finance_reviewer="李四",
        approved_at="2026-01-01",
        proposal_hash="p" * 64,
        valid_until="2026-02-01",
    )
    ok, why = signed.is_signed(today=date(2026, 8, 15))
    assert (ok, why) == (False, "signature_expired")


def test_transcribed_value_must_match_oa_amount(tmp_path):
    entry, _ = _signed_entry(tmp_path)
    signed = sign_entry(
        entry,
        transcribed_value="99.98",
        checker="张三",
        finance_reviewer="李四",
        approved_at="2026-08-01",
        proposal_hash="p" * 64,
    )
    ok, why = signed.is_signed(today=date(2026, 8, 15))
    assert (ok, why) == (False, "transcribed_amount_mismatch")


def test_same_approval_multiple_subrows_are_not_copied(tmp_path):
    e1, _ = _signed_entry(tmp_path, amount="100.00")
    e2 = build_entry(
        row_id="R2",
        platform="Walmart",
        account="WFUS",
        currency="USD",
        oa_amount=Decimal("50.00"),
        attachment_name="s.csv",
        attachment_sha256="x" * 64,
    )
    signed = sign_entry(
        e1,
        transcribed_value="100.00",
        checker="张三",
        finance_reviewer="李四",
        approved_at="2026-08-01",
        proposal_hash="p" * 64,
    )
    summary = worklist_summary([signed, e2], today=date(2026, 8, 15))
    assert summary["signed_valid"] == 1
    assert summary["pending"] == 1
    assert summary["pending_rows"] == ["R2"]


def test_history_hint_needs_three_samples_and_flags_10x():
    assert history_anomaly_hint(Decimal("100"), [Decimal("90"), Decimal("100")])["status"] == "insufficient_history"
    hint = history_anomaly_hint(Decimal("2000"), [Decimal("90"), Decimal("100"), Decimal("110")])
    assert hint["status"] == "high_10x"
    hint = history_anomaly_hint(Decimal("5"), [Decimal("90"), Decimal("100"), Decimal("110")])
    assert hint["status"] == "low_0.1x"
