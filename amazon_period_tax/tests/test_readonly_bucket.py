# -*- coding: utf-8 -*-
"""R05 只读解析：dry-run/verify 不落缓存，tab 修复不移动列/金额/结算号。"""
from __future__ import annotations

import hashlib
from pathlib import Path

import pytest

import read_amz_txt
from read_amz_txt import fix_issues_in_txt, read_amz_txt_file, read_bucket_amz_txts

HEADER = (
    "settlement-id\tsettlement-end-date\tcurrency\tamount\tamount-description\tamount-type\tsku\n"
)


@pytest.fixture(autouse=True)
def _identity_account(monkeypatch):
    import channel_canonical

    monkeypatch.setattr(read_amz_txt, "canonical_account", lambda s: s)
    monkeypatch.setattr(channel_canonical, "canonical_account", lambda s: s)


def _bucket(tmp_path: Path) -> Path:
    b = tmp_path / "账期20261004-20261103"
    (b / "甲").mkdir(parents=True)
    return b


def _hashes(root: Path) -> dict[str, str]:
    return {
        str(p.relative_to(root)): hashlib.sha256(p.read_bytes()).hexdigest()
        for p in sorted(root.rglob("*"))
        if p.is_file()
    }


def _bad_file(bucket: Path) -> Path:
    # 行尾多一个 tab（pandas 会把 sku+EXTRA 拼成一个字段）
    text = HEADER + "1\t2026-10-05 00:00:00 UTC\tUSD\t10.00\tTax\tItemPrice\tSKU1\tEXTRA\n"
    path = bucket / "甲" / "AMZBadUS-2026-10-05.txt"
    path.write_text(text, encoding="utf-8")
    return path


def test_read_only_does_not_write_repair_cache(tmp_path):
    bucket = _bucket(tmp_path)
    _bad_file(bucket)
    before = _hashes(tmp_path)
    df, reports = read_bucket_amz_txts(bucket, write_repairs=False)
    after = _hashes(tmp_path)
    assert before == after  # 不创建任何文件（含 .repair_cache_*）
    assert not list(tmp_path.glob(".repair_cache*"))
    assert len(df) == 1
    assert df.attrs.get("repaired_in_memory") is True or any("内存修复" in r for r in reports)


def test_dry_run_toggle_is_read_only(tmp_path):
    """run_period_tax 的 --dry-run 传 write_repairs=False；等价入口必须只读。"""
    bucket = _bucket(tmp_path)
    _bad_file(bucket)
    before = _hashes(tmp_path)
    read_bucket_amz_txts(bucket, write_repairs=False)
    assert _hashes(tmp_path) == before


def test_explicit_repair_writes_cache_outside_bucket(tmp_path):
    bucket = _bucket(tmp_path)
    _bad_file(bucket)
    df, _ = read_bucket_amz_txts(bucket, write_repairs=True)
    assert len(df) == 1
    cache = tmp_path / f".repair_cache_{bucket.name}"
    assert cache.is_dir()
    assert not (bucket / ".repair_cache").exists()
    # 桶内原始文件未被修改
    assert (bucket / "甲" / "AMZBadUS-2026-10-05.txt").read_text(encoding="utf-8").endswith("EXTRA\n")


def test_tab_repair_does_not_move_columns_or_change_amount(tmp_path):
    """修复前后：列数一致、金额/结算号/描述不变（不能只靠行数证明）。"""
    bucket = _bucket(tmp_path)
    path = _bad_file(bucket)

    good = read_amz_txt_file(path, write_repairs=False)
    assert good is not None
    # 用同一行「无多余 tab」的干净文件做参照
    clean = bucket / "甲" / "AMZCleanUS-2026-10-05.txt"
    clean.write_text(
        HEADER + "1\t2026-10-05 00:00:00 UTC\tUSD\t10.00\tTax\tItemPrice\tSKU1\n",
        encoding="utf-8",
    )
    ref = read_amz_txt_file(clean, write_repairs=False)
    assert list(good.columns) == list(ref.columns)
    assert good["amount"].tolist() == ref["amount"].tolist()
    assert good["amount-description"].tolist() == ref["amount-description"].tolist()
    assert good["amount-type"].tolist() == ref["amount-type"].tolist()


def test_fix_issues_preserves_header_and_deletes_tabs(tmp_path):
    lines = [
        HEADER,
        "1\t2026-10-05 00:00:00 UTC\tUSD\t10.00\tTax\tItemPrice\tSKU1\tEXTRA\n",
    ]
    fixed = fix_issues_in_txt(lines)
    assert fixed[0] == lines[0]
    assert fixed[1].count("\t") == lines[0].count("\t")


def test_repair_mismatch_still_blocks_like_parse_failure(tmp_path):
    """修复后仍有非法金额 → FAIL（不能因为写缓存就放行）。"""
    bucket = _bucket(tmp_path)
    text = HEADER + "1\t2026-10-05 00:00:00 UTC\tUSD\tnot-a-number\tTax\tItemPrice\tSKU1\tEXTRA\n"
    (bucket / "甲" / "AMZBadUS-2026-10-05.txt").write_text(text, encoding="utf-8")
    stats: dict = {}
    df, reports = read_bucket_amz_txts(bucket, stats_out=stats, write_repairs=False)
    assert df.empty
    assert stats["files_failed"] == 1
