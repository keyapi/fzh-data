# -*- coding: utf-8 -*-
"""按 txt 内部 settlement-end-date 与桶窗口比对：跨期副本默认排除。"""
from __future__ import annotations

from pathlib import Path

from read_amz_txt import parse_settlement_meta, read_bucket_amz_txts, settlement_end_date

HEADER = "settlement-id\tsettlement-end-date\tcurrency\tamount\tamount-description\tamount-type\tsku\n"
HEADER_DEP = (
    "settlement-id\tsettlement-end-date\tdeposit-date\tcurrency\tamount\t"
    "amount-description\tamount-type\tsku\n"
)


def _txt_with_deposit(sid: str, end: str, deposit: str) -> str:
    return (
        HEADER_DEP
        + f"{sid}\t{end}\t{deposit}\tUSD\t100.00\t\t\t\n"
        + f"{sid}\t\t\t\t50.00\tTax\tItemPrice\tSKU1\n"
    )


def _txt(sid: str, end: str, detail_amount: str = "50.00") -> str:
    return (
        HEADER
        + f"{sid}\t{end}\tUSD\t100.00\t\t\t\n"
        + f"{sid}\t\t\t{detail_amount}\tTax\tItemPrice\tSKU1\n"
    )


def _bucket(tmp_path: Path) -> Path:
    bucket = tmp_path / "账期20260804-20260903"
    (bucket / "甲").mkdir(parents=True)
    (bucket / "甲" / "AMZInUS-8.11.txt").write_text(_txt("111", "2026-08-11 00:00:00 UTC"), encoding="utf-8")
    # 7 月结算副本错放到 8 月桶（历史上真实发生过）
    (bucket / "甲" / "AMZOutUS-7.29.txt").write_text(_txt("27080868331", "2026-07-28 01:03:22 UTC"), encoding="utf-8")
    return bucket


def test_parse_settlement_meta():
    sid, end = parse_settlement_meta(_txt("27080868331", "2026-07-28 01:03:22 UTC"))
    assert sid == "27080868331"
    assert end == "2026-07-28 01:03:22 UTC"


def test_settlement_end_date():
    assert settlement_end_date(_txt("1", "2026-07-28 01:03:22 UTC")).isoformat() == "2026-07-28"
    # 无该列 → None
    assert settlement_end_date("settlement-id\tcurrency\n1\tUSD\n") is None


def test_out_of_period_excluded_by_default(tmp_path):
    bucket = _bucket(tmp_path)
    stats: dict = {}
    df, reports = read_bucket_amz_txts(bucket, stats_out=stats)
    assert stats["files_total"] == 2
    assert stats["files_out_of_period"] == 1
    assert stats["files_used"] == 1
    assert set(df["文件名"]) == {"AMZInUS-8.11.txt"}
    assert any(r.startswith("OUT-OF-PERIOD") and "end=2026-07-28" in r for r in reports)


def test_allow_out_of_period_includes(tmp_path):
    bucket = _bucket(tmp_path)
    stats: dict = {}
    df, _ = read_bucket_amz_txts(bucket, stats_out=stats, allow_out_of_period=True)
    assert stats["files_out_of_period"] == 1
    assert stats["files_used"] == 2
    assert len(df) == 4


def test_file_without_internal_end_date_is_kept_and_reported(tmp_path):
    bucket = tmp_path / "账期20260804-20260903"
    (bucket / "甲").mkdir(parents=True)
    (bucket / "甲" / "AMZNoDateUS-8.11.txt").write_text(
        "settlement-id\tcurrency\tamount\tamount-description\tamount-type\tsku\n"
        "9\tUSD\t10.00\tTax\tItemPrice\tSKU9\n",
        encoding="utf-8",
    )
    stats: dict = {}
    df, reports = read_bucket_amz_txts(bucket, stats_out=stats)
    assert stats["files_no_period_date"] == 1
    assert len(df) == 1
    assert any(r.startswith("NO-PERIOD-DATE") for r in reports)


def test_deposit_date_is_window_key_not_settlement_end(tmp_path):
    """7/20–8/3 结算、8/5 打款 → 属于 8 月桶（账期日期 4 号→次月 3 号）。"""
    bucket = tmp_path / "账期20260804-20260903"
    (bucket / "甲").mkdir(parents=True)
    (bucket / "甲" / "AMZCTRDUS-2026-8-3.txt").write_text(
        _txt_with_deposit("27040460241", "2026-08-03 05:59:50 UTC", "2026-08-05 05:59:50 UTC"),
        encoding="utf-8",
    )
    stats: dict = {}
    df, reports = read_bucket_amz_txts(bucket, stats_out=stats)
    assert stats["files_out_of_period"] == 0
    assert len(df) == 2
    assert not any(r.startswith("OUT-OF-PERIOD") for r in reports)


def test_deposit_date_outside_window_excluded(tmp_path):
    """7 月结算副本（7/30 打款）放进 8 月桶 → 排除。"""
    bucket = tmp_path / "账期20260804-20260903"
    (bucket / "甲").mkdir(parents=True)
    (bucket / "甲" / "AMZJohnaUS-8.11.txt").write_text(
        _txt_with_deposit("27080868331", "2026-07-28 01:03:22 UTC", "2026-07-30 01:03:22 UTC"),
        encoding="utf-8",
    )
    stats: dict = {}
    df, reports = read_bucket_amz_txts(bucket, stats_out=stats)
    assert stats["files_out_of_period"] == 1
    assert df.empty
    assert any("deposit=2026-07-30" in r for r in reports)


def test_dmy_settlement_dates_parsed(tmp_path):
    """欧盟站导出日期为 DD.MM.YYYY（旧实现全部 NO-PERIOD-DATE）。"""
    bucket = tmp_path / "账期20260704-20260803"
    (bucket / "甲").mkdir(parents=True)
    (bucket / "甲" / "AMZBAINADE-2026-7-25.txt").write_text(
        HEADER
        + "27405507412\t25.07.2026 06:01:04 UTC\tEUR\t-45,37\t\t\t\n"
        + "27405507412\t\t\t\t-10,00\tTax\tItemPrice\tSKU1\n",
        encoding="utf-8",
    )
    stats: dict = {}
    df, reports = read_bucket_amz_txts(bucket, stats_out=stats)
    assert stats["files_no_period_date"] == 0
    assert stats["files_out_of_period"] == 0
    assert len(df) == 2
