# -*- coding: utf-8 -*-
"""R01–R09 源文件总账：范围/ schema / 守恒 / 去重 / 结算唯一 / 跨期 / 终态分区。"""
from __future__ import annotations

import hashlib
from pathlib import Path

import pytest

import read_amz_txt
from source_ledger import (
    KIND_NON_AMZ_TXT,
    SCOPE_EXCLUDED_FOLDER,
    STATE_APPROVED_EXCLUDED,
    STATE_DUP,
    STATE_FAILED,
    STATE_NEEDS_REVIEW,
    STATE_OUT_OF_PERIOD,
    STATE_USED,
    SourceLedger,
    cross_bucket_settlement_conflicts,
)

V2_HEADER = (
    "settlement-id\tsettlement-end-date\tdeposit-date\tcurrency\tamount\t"
    "amount-description\tamount-type\tsku\n"
)
V1_COLS = (
    "settlement-id",
    "settlement-end-date",
    "currency",
    "transaction-type",
    "sku",
    "price-type",
    "price-amount",
    "item-related-fee-type",
    "item-related-fee-amount",
    "promotion-type",
    "promotion-amount",
)
V1_HEADER = "\t".join(V1_COLS) + "\n"


@pytest.fixture(autouse=True)
def _identity_account(monkeypatch):
    """文件名 → 渠道账号不做本机快照映射（测试不依赖 gitignored 快照）。"""
    import channel_canonical

    monkeypatch.setattr(read_amz_txt, "canonical_account", lambda s: s)
    monkeypatch.setattr(channel_canonical, "canonical_account", lambda s: s)


def _v2(sid: str, end: str = "2026-10-05 00:00:00 UTC", deposit: str = "", amount: str = "50.00") -> str:
    return (
        V2_HEADER
        + f"{sid}\t{end}\t{deposit}\tUSD\t100.00\t\t\t\n"
        + f"{sid}\t\t\t\t{amount}\tTax\tItemPrice\tSKU1\n"
    )


def _v1(sid: str, end: str = "2026-10-05 00:00:00 UTC") -> str:
    rows = [
        [sid, end, "USD", "TransactionTotalAmount", "", "", "", "", "", "", ""],
        [sid, "", "", "Order", "SKU1", "Principal", "100", "Commission", "-15", "Principal", "-5"],
    ]
    return V1_HEADER + "".join("\t".join(r) + "\n" for r in rows)


def _bucket(tmp_path: Path, name: str = "账期20261004-20261103") -> Path:
    b = tmp_path / name
    (b / "甲").mkdir(parents=True)
    return b


def _read(bucket: Path, **kwargs):
    ledger = SourceLedger(bucket.name)
    stats: dict = {}
    df, reports = read_amz_txt.read_bucket_amz_txts(
        bucket, stats_out=stats, ledger_out=ledger, **kwargs
    )
    return df, reports, stats, ledger


# ------------------------------------------------------------------ R01 范围


def test_inventory_covers_non_amz_non_txt_hidden_and_excluded(tmp_path):
    bucket = _bucket(tmp_path)
    (bucket / "甲" / "AMZGoodUS-2026-10-05.txt").write_text(_v2("100"), encoding="utf-8")
    (bucket / "甲" / "说明.txt").write_text("not a settlement", encoding="utf-8")
    (bucket / "甲" / "图片.png").write_bytes(b"\x89PNG\x00\x00binary")
    (bucket / ".cache").mkdir()
    (bucket / ".cache" / "AMZHiddenUS-2026-10-05.txt").write_text(_v2("9"), encoding="utf-8")
    (bucket / "杨鹏瑶").mkdir()
    (bucket / "杨鹏瑶" / "AMZExcludedUS-2026-10-05.txt").write_text(_v2("8"), encoding="utf-8")
    (bucket / "notes.md").write_text("hello", encoding="utf-8")

    df, reports, stats, ledger = _read(bucket)
    assert stats["files_total"] == 1 and len(df) == 2
    assert ledger.partition()[STATE_USED] == 1
    inv = {(r.rel, r.kind) for r in ledger.inventory}
    assert ("甲/说明.txt", KIND_NON_AMZ_TXT) in inv
    assert ("甲/图片.png", "non_txt") in inv
    assert ("杨鹏瑶/AMZExcludedUS-2026-10-05.txt", KIND_NON_AMZ_TXT) in inv
    assert any(r.scope == SCOPE_EXCLUDED_FOLDER for r in ledger.inventory)
    assert all(r.state == "not_applicable" for r in ledger.inventory)
    assert any(line.startswith("INVENTORY") for line in reports)


def test_root_level_amz_txt_needs_review(tmp_path):
    bucket = _bucket(tmp_path)
    (bucket / "AMZRootUS-2026-10-05.txt").write_text(_v2("101"), encoding="utf-8")
    df, reports, stats, ledger = _read(bucket)
    assert df.empty
    assert stats["files_total"] == 1
    assert ledger.partition()[STATE_NEEDS_REVIEW] == 1
    assert any(r.startswith("NEEDS-REVIEW") and "根目录" in r for r in reports)
    assert ledger.publish_blockers()


def test_nested_amz_txt_needs_review(tmp_path):
    bucket = _bucket(tmp_path)
    deep = bucket / "甲" / "sub"
    deep.mkdir()
    (deep / "AMZDeepUS-2026-10-05.txt").write_text(_v2("102"), encoding="utf-8")
    df, reports, stats, ledger = _read(bucket)
    assert df.empty
    assert ledger.partition()[STATE_NEEDS_REVIEW] == 1
    assert any("深层目录" in (r.reason or "") for r in ledger.candidates)


def test_misnamed_settlement_csv_needs_review(tmp_path):
    bucket = _bucket(tmp_path)
    csv_text = "settlement-id,currency,amount,amount-type,amount-description\n1,USD,10,ItemPrice,Tax\n"
    (bucket / "甲" / "settlement_2026-10.csv").write_text(csv_text, encoding="utf-8")
    df, reports, stats, ledger = _read(bucket)
    assert df.empty
    assert ledger.partition()[STATE_NEEDS_REVIEW] == 1


def test_amz_content_txt_without_amz_prefix_needs_review(tmp_path):
    bucket = _bucket(tmp_path)
    (bucket / "甲" / "settlement_export.txt").write_text(_v2("103"), encoding="utf-8")
    df, reports, stats, ledger = _read(bucket)
    assert df.empty
    assert ledger.partition()[STATE_NEEDS_REVIEW] == 1
    assert any("命名不符" in (r.reason or "") for r in ledger.candidates)


# ------------------------------------------------------------------ R02 schema


def test_xml_rejected(tmp_path):
    bucket = _bucket(tmp_path)
    (bucket / "甲" / "AMZBadUS-2026-10-05.txt").write_text("<?xml version='1.0'?><x/>", encoding="utf-8")
    df, reports, stats, ledger = _read(bucket)
    assert df.empty and stats["files_failed"] == 1
    assert "SCHEMA-XML" in (ledger.candidates[0].reason or "")


def test_unknown_schema_rejected(tmp_path):
    bucket = _bucket(tmp_path)
    (bucket / "甲" / "AMZBadUS-2026-10-05.txt").write_text("foo\tbar\n1\t2\n", encoding="utf-8")
    df, reports, stats, ledger = _read(bucket)
    assert df.empty and stats["files_failed"] == 1
    assert "SCHEMA-UNKNOWN" in (ledger.candidates[0].reason or "")


def test_missing_required_column_rejected(tmp_path):
    bucket = _bucket(tmp_path)
    header = "settlement-id\tamount\tamount-description\tamount-type\n"
    (bucket / "甲" / "AMZBadUS-2026-10-05.txt").write_text(header + "1\t10\tTax\tItemPrice\n", encoding="utf-8")
    df, reports, stats, ledger = _read(bucket)
    assert df.empty and stats["files_failed"] == 1
    assert "currency" in (ledger.candidates[0].reason or "")


def test_empty_file_failed(tmp_path):
    bucket = _bucket(tmp_path)
    (bucket / "甲" / "AMZEmptyUS-2026-10-05.txt").write_bytes(b"")
    df, reports, stats, ledger = _read(bucket)
    assert df.empty and stats["files_failed"] == 1
    assert ledger.candidates[0].reason == "EMPTY-FILE"
    assert stats["files_total"] == stats["files_failed"] == 1


def test_header_only_file_failed(tmp_path):
    bucket = _bucket(tmp_path)
    (bucket / "甲" / "AMZHeaderUS-2026-10-05.txt").write_text(V2_HEADER, encoding="utf-8")
    df, reports, stats, ledger = _read(bucket)
    assert df.empty and stats["files_failed"] == 1
    assert ledger.candidates[0].reason == "NO-DATA-ROWS"


# ------------------------------------------------------------------ R03 V1


def test_v1_expansion_rows_and_amount_conservation(tmp_path):
    bucket = _bucket(tmp_path)
    (bucket / "甲" / "AMZV1US-2026-10-05.txt").write_text(_v1("200"), encoding="utf-8")
    df, reports, stats, ledger = _read(bucket)
    assert stats["files_used"] == 1
    assert len(df) == 3  # Principal + Commission + Promotion
    assert stats["rows_mismatch"] == 0
    assert df["amount"].sum() == pytest.approx(100 - 15 - 5)
    assert ledger.candidates[0].rows_expected == 3


def test_v1_amount_without_type_failed(tmp_path):
    bucket = _bucket(tmp_path)
    header = "settlement-id\tcurrency\tprice-type\tprice-amount\n"
    (bucket / "甲" / "AMZV1BadUS-2026-10-05.txt").write_text(header + "1\tUSD\t\t100\n", encoding="utf-8")
    df, reports, stats, ledger = _read(bucket)
    assert df.empty and stats["files_failed"] == 1
    assert "有金额但缺 type" in (ledger.candidates[0].reason or "")


def test_unknown_amount_family_column_failed(tmp_path):
    bucket = _bucket(tmp_path)
    header = (
        "settlement-id\tcurrency\tamount\tamount-type\tamount-description\tvat-amount\n"
    )
    (bucket / "甲" / "AMZBadUS-2026-10-05.txt").write_text(header + "1\tUSD\t10\tItemPrice\tTax\t3\n", encoding="utf-8")
    df, reports, stats, ledger = _read(bucket)
    assert df.empty and stats["files_failed"] == 1
    assert "UNKNOWN-AMOUNT-COLS" in (ledger.candidates[0].reason or "")


def test_non_finite_amount_failed(tmp_path):
    bucket = _bucket(tmp_path)
    (bucket / "甲" / "AMZBadUS-2026-10-05.txt").write_text(_v2("300", amount="Inf"), encoding="utf-8")
    df, reports, stats, ledger = _read(bucket)
    assert df.empty and stats["files_failed"] == 1
    assert "金额解析失败" in (ledger.candidates[0].reason or "")


# ------------------------------------------------------------------ R06/R07


def test_three_identical_copies_used1_dup2(tmp_path):
    bucket = _bucket(tmp_path)
    (bucket / "乙").mkdir()
    (bucket / "丙").mkdir()
    content = _v2("400")
    for person in ("甲", "乙", "丙"):
        (bucket / person / f"AMZAAAUS-2026-10-0{len(person)}.txt").write_text(content, encoding="utf-8")
    df, reports, stats, ledger = _read(bucket)
    assert stats["files_total"] == 3
    assert stats["files_used"] == 1
    assert stats["files_dup"] == 2
    assert ledger.partition()[STATE_DUP] == 2
    assert len([r for r in reports if r.startswith("SKIP-DUP")]) == 2


def test_same_content_different_account_needs_review(tmp_path):
    bucket = _bucket(tmp_path)
    (bucket / "乙").mkdir()
    content = _v2("401")
    (bucket / "甲" / "AMZAAAUS-2026-10-05.txt").write_text(content, encoding="utf-8")
    (bucket / "乙" / "AMZBBBUS-2026-10-05.txt").write_text(content, encoding="utf-8")
    df, reports, stats, ledger = _read(bucket)
    assert stats["files_used"] == 1
    assert stats["files_needs_review"] == 1
    assert any("SAME-MD5-DIFFERENT-ACCOUNT" in (r.reason or "") for r in ledger.candidates)


def test_same_settlement_id_different_bytes_needs_review(tmp_path):
    bucket = _bucket(tmp_path)
    (bucket / "甲" / "AMZAAAUS-2026-10-05.txt").write_text(_v2("500", amount="50.00"), encoding="utf-8")
    (bucket / "甲" / "AMZAAAUS-2026-10-06.txt").write_text(_v2("500", amount="51.00"), encoding="utf-8")
    df, reports, stats, ledger = _read(bucket)
    assert stats["files_used"] == 1
    assert stats["files_needs_review"] == 1
    assert any("SID-MULTIPLE-VERSIONS" in (r.reason or "") for r in ledger.candidates)


def test_same_settlement_v1_v2_dual_needs_review(tmp_path):
    bucket = _bucket(tmp_path)
    (bucket / "甲" / "AMZAAAUS-2026-10-05.txt").write_text(_v1("600"), encoding="utf-8")
    (bucket / "甲" / "AMZAAAUS-2026-10-06.txt").write_text(_v2("600"), encoding="utf-8")
    df, reports, stats, ledger = _read(bucket)
    assert stats["files_used"] == 1
    assert stats["files_needs_review"] == 1
    assert any("V1+V2-DUAL" in (r.reason or "") for r in ledger.candidates)


def test_cross_bucket_conflict_helper(tmp_path):
    aug = _bucket(tmp_path, "账期20260804-20260903")
    sep = tmp_path / "账期20260904-20261003"
    (sep / "甲").mkdir(parents=True)
    (aug / "甲" / "AMZAAAUS-2026-08-10.txt").write_text(_v2("700", "2026-08-10 00:00:00 UTC"), encoding="utf-8")
    (sep / "甲" / "AMZAAAUS-2026-08-10.txt").write_text(_v2("700", "2026-08-10 00:00:00 UTC"), encoding="utf-8")
    ledgers = {}
    for b in (aug, sep):
        ledger = SourceLedger(b.name)
        read_amz_txt.read_bucket_amz_txts(b, allow_out_of_period=True, ledger_out=ledger)
        ledgers[b.name] = ledger
    conflicts = cross_bucket_settlement_conflicts(ledgers)
    assert len(conflicts) == 1
    assert conflicts[0]["settlement_id"] == "700"


# ------------------------------------------------------------------ R08 跨期


def test_month_end_and_year_boundary(tmp_path):
    bucket = _bucket(tmp_path, "账期20261204-20270103")
    (bucket / "甲" / "AMZAAAUS-2026-12-31.txt").write_text(
        _v2("800", "2026-12-31 23:00:00 UTC", "2027-01-03 10:00:00 UTC"), encoding="utf-8"
    )
    (bucket / "甲" / "AMZBBBUS-2026-11-30.txt").write_text(
        _v2("801", "2026-11-30 10:00:00 UTC"), encoding="utf-8"
    )
    (bucket / "甲" / "AMZCCCUS-2027-01-02.txt").write_text(
        _v2("802", "2027-01-02 10:00:00 UTC"), encoding="utf-8"
    )
    df, reports, stats, ledger = _read(bucket)
    assert stats["files_used"] == 1 and len(df) == 2  # 12/31 结算仍属 202612
    assert stats["files_out_of_period"] == 2
    assert ledger.partition()[STATE_OUT_OF_PERIOD] == 2


def test_no_internal_date_kept_but_blocks_publish(tmp_path):
    bucket = _bucket(tmp_path)
    header = "settlement-id\tcurrency\tamount\tamount-description\tamount-type\tsku\n"
    (bucket / "甲" / "AMZNoDateUS-2026-10-05.txt").write_text(
        header + "1\tUSD\t10.00\tTax\tItemPrice\tSKU9\n", encoding="utf-8"
    )
    df, reports, stats, ledger = _read(bucket)
    assert len(df) == 1
    assert stats["files_no_period_date"] == 1
    assert any(b.startswith("NO-PERIOD-DATE") for b in ledger.publish_blockers())


def test_period_exception_hash_mismatch_needs_review(tmp_path):
    bucket = _bucket(tmp_path)
    (bucket / "甲" / "AMZOldUS-6.12.txt").write_text(
        _v2("900", "2026-06-12 09:00:00 UTC"), encoding="utf-8"
    )
    exc = tmp_path / "_period_exceptions"
    exc.mkdir()
    (exc / f"{bucket.name}.txt").write_text(
        "甲/AMZOldUS-6.12.txt#sha256=deadbeef\n", encoding="utf-8"
    )
    df, reports, stats, ledger = _read(bucket)
    assert df.empty
    assert ledger.partition()[STATE_NEEDS_REVIEW] == 1
    assert "HASH-MISMATCH" in (ledger.candidates[0].reason or "")


def test_period_exception_hash_match_includes(tmp_path):
    bucket = _bucket(tmp_path)
    path = bucket / "甲" / "AMZOldUS-6.12.txt"
    content = _v2("901", "2026-06-12 09:00:00 UTC")
    path.write_text(content, encoding="utf-8")
    digest = hashlib.sha256(path.read_bytes()).hexdigest()
    exc = tmp_path / "_period_exceptions"
    exc.mkdir()
    (exc / f"{bucket.name}.txt").write_text(
        f"甲/AMZOldUS-6.12.txt#sha256={digest}\n", encoding="utf-8"
    )
    df, reports, stats, ledger = _read(bucket)
    assert len(df) == 2
    assert ledger.partition()[STATE_USED] == 1
    assert ledger.candidates[0].approval.startswith("period_exception:include")
    assert any(r.startswith("OUT-OF-PERIOD-ALLOWED") for r in reports)


def test_approved_exclude_requires_hash(tmp_path):
    bucket = _bucket(tmp_path)
    (bucket / "甲" / "AMZOldUS-6.12.txt").write_text(
        _v2("902", "2026-06-12 09:00:00 UTC"), encoding="utf-8"
    )
    exc = tmp_path / "_period_exceptions"
    exc.mkdir()
    (exc / f"{bucket.name}.txt").write_text("exclude:甲/AMZOldUS-6.12.txt\n", encoding="utf-8")
    df, reports, stats, ledger = _read(bucket)
    assert df.empty
    assert ledger.partition()[STATE_NEEDS_REVIEW] == 1
    assert "EXCLUDE-WITHOUT-HASH" in (ledger.candidates[0].reason or "")


def test_approved_exclude_with_hash_terminal_state(tmp_path):
    bucket = _bucket(tmp_path)
    path = bucket / "甲" / "AMZOldUS-6.12.txt"
    path.write_text(_v2("903", "2026-06-12 09:00:00 UTC"), encoding="utf-8")
    digest = hashlib.sha256(path.read_bytes()).hexdigest()
    exc = tmp_path / "_period_exceptions"
    exc.mkdir()
    (exc / f"{bucket.name}.txt").write_text(
        f"exclude:甲/AMZOldUS-6.12.txt#sha256={digest}\n", encoding="utf-8"
    )
    df, reports, stats, ledger = _read(bucket)
    assert df.empty
    assert ledger.partition()[STATE_APPROVED_EXCLUDED] == 1
    assert any(r.startswith("APPROVED-EXCLUDED") for r in reports)
    assert "OUT-OF-PERIOD" not in ";".join(ledger.publish_blockers())


# ------------------------------------------------------------------ R09 守恒


def test_six_file_mutually_exclusive_partition(tmp_path):
    bucket = _bucket(tmp_path)
    (bucket / "乙").mkdir()
    # used
    used = bucket / "甲" / "AMZUsedUS-2026-10-05.txt"
    used.write_text(_v2("1000"), encoding="utf-8")
    # dup（同内容同账号）
    (bucket / "乙" / "AMZUsedUS-2026-10-06.txt").write_text(_v2("1000"), encoding="utf-8")
    # failed（空文件）
    (bucket / "甲" / "AMZEmptyUS-2026-10-05.txt").write_bytes(b"")
    # out_of_period
    (bucket / "甲" / "AMZOutUS-2026-09-20.txt").write_text(
        _v2("1001", "2026-09-20 00:00:00 UTC"), encoding="utf-8"
    )
    # approved_excluded（跨期 + hash 绑定的排除）
    excl = bucket / "甲" / "AMZExclUS-2026-09-21.txt"
    excl.write_text(_v2("1002", "2026-09-21 00:00:00 UTC"), encoding="utf-8")
    # needs_review（根目录 AMZ 文件）
    (bucket / "AMZRootUS-2026-10-05.txt").write_text(_v2("1003"), encoding="utf-8")
    exc = tmp_path / "_period_exceptions"
    exc.mkdir()
    (exc / f"{bucket.name}.txt").write_text(
        f"exclude:甲/AMZExclUS-2026-09-21.txt#sha256={hashlib.sha256(excl.read_bytes()).hexdigest()}\n",
        encoding="utf-8",
    )

    df, reports, stats, ledger = _read(bucket)
    part = ledger.partition()
    assert stats["files_total"] == 6
    assert part == {
        STATE_USED: 1,
        STATE_DUP: 1,
        STATE_FAILED: 1,
        STATE_OUT_OF_PERIOD: 1,
        STATE_APPROVED_EXCLUDED: 1,
        STATE_NEEDS_REVIEW: 1,
    }
    assert sum(part.values()) == stats["files_total"] == 6
    assert ledger.assert_conservation() == 6
    assert len(df) == 2  # 只有 used 文件进入计算


def test_bucket_level_out_of_period_stats_keep_legacy_semantics(tmp_path):
    """--allow-out-of-period 时纳入计算，但 files_out_of_period 仍计数（兼容旧报告）。"""
    bucket = _bucket(tmp_path)
    (bucket / "甲" / "AMZOutUS-2026-09-20.txt").write_text(
        _v2("1100", "2026-09-20 00:00:00 UTC"), encoding="utf-8"
    )
    df, _, stats, ledger = _read(bucket, allow_out_of_period=True)
    assert stats["files_used"] == 1
    assert stats["files_out_of_period"] == 1
    assert ledger.partition()[STATE_USED] == 1
