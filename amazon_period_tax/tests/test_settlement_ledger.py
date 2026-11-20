# -*- coding: utf-8 -*-
"""结算台账：同一结算副本出现在两个账期桶 → 跨桶重复清单（只报告）。"""
from __future__ import annotations

from pathlib import Path

from settlement_ledger import find_duplicates, format_report, scan_buckets

HEADER = "settlement-id\tsettlement-end-date\tcurrency\tamount\tamount-description\tamount-type\tsku\n"


def _txt(sid: str, end: str) -> str:
    return (
        HEADER
        + f"{sid}\t{end}\tUSD\t100.00\t\t\t\n"
        + f"{sid}\t\t\t50.00\tTax\tItemPrice\tSKU1\n"
    )


def _make_root(tmp_path: Path) -> Path:
    root = tmp_path / "账期资料"
    july = root / "账期20260704-20260803"
    aug = root / "账期20260804-20260903"
    (july / "卢天姿").mkdir(parents=True)
    (aug / "卢天姿").mkdir(parents=True)
    same = _txt("27080868331", "2026-07-28 01:03:22 UTC")
    (july / "卢天姿" / "AMZJohnaUS-7.29.txt").write_text(same, encoding="utf-8")
    (aug / "卢天姿" / "AMZJohnaUS-8.11.txt").write_text(same, encoding="utf-8")
    (aug / "卢天姿" / "AMZJohnaUS-8.20.txt").write_text(
        _txt("999", "2026-08-20 00:00:00 UTC"), encoding="utf-8"
    )
    return root


def test_scan_and_find_cross_bucket_duplicate(tmp_path):
    root = _make_root(tmp_path)
    records = scan_buckets(root)
    assert len(records) == 3
    dups = find_duplicates(records)
    assert len(dups) == 1
    d = dups[0]
    assert d["type"] == "settlement-id"
    assert d["key"] == "27080868331"
    assert d["cross_bucket"] is True
    assert d["buckets"] == ["账期20260704-20260803", "账期20260804-20260903"]
    assert len(d["files"]) == 2


def test_out_of_window_flagged_in_report(tmp_path):
    root = _make_root(tmp_path)
    records = scan_buckets(root)
    aug_copy = next(r for r in records if r["bucket"].endswith("20260903"))
    assert aug_copy["in_bucket_window"] is False
    lines = format_report(records, find_duplicates(records))
    assert any("OUT-OF-PERIOD" in line for line in lines)
    assert any("跨桶" in line for line in lines)


def test_scan_ignores_hidden_and_non_txt(tmp_path):
    root = tmp_path / "账期资料"
    bucket = root / "账期20260804-20260903"
    (bucket / ".cache").mkdir(parents=True)
    (bucket / ".cache" / "AMZHiddenUS-8.1.txt").write_text(_txt("1", "2026-08-01 00:00:00 UTC"), encoding="utf-8")
    (bucket / "说明.txt").write_text("not amz", encoding="utf-8")
    assert scan_buckets(root) == []
