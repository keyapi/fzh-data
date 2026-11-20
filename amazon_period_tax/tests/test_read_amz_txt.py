# -*- coding: utf-8 -*-
"""同内容 txt 去重 + 缓存目录不落在桶内 + 隐藏目录不扫。"""
from __future__ import annotations

from pathlib import Path

from read_amz_txt import read_bucket_amz_txts

HEADER = "settlement-id\tcurrency\tamount\tamount-description\ttransaction-type\tamount-type\tsku\n"


def _txt(rows: list[str]) -> str:
    return HEADER + "".join(r + "\n" for r in rows)


ROWS_A = ["1\tUSD\t10.0\tTax\tOrder\tItemPrice\tSKU1", "2\tUSD\t20.0\tTax\tOrder\tItemPrice\tSKU2"]


def _make_bucket(tmp_path: Path) -> Path:
    bucket = tmp_path / "账期20261004-20261103"
    (bucket / "甲").mkdir(parents=True)
    (bucket / "乙").mkdir()
    (bucket / "丙").mkdir()
    (bucket / "甲" / "AMZTestUS-2026-10-05.txt").write_text(_txt(ROWS_A), encoding="utf-8")
    # 同一内容、不同人名夹：必须只读一次
    (bucket / "乙" / "AMZTestUS-2026.10.05.txt").write_text(_txt(ROWS_A), encoding="utf-8")
    (bucket / "丙" / "AMZTestUS-2026-10-06.txt").write_text(
        _txt(["3\tUSD\t5.0\tTax\tOrder\tItemPrice\tSKU3"]), encoding="utf-8"
    )
    return bucket


def test_same_md5_read_once(tmp_path):
    bucket = _make_bucket(tmp_path)
    stats: dict = {}
    df, reports = read_bucket_amz_txts(bucket, stats_out=stats)
    assert len(df) == 3
    assert stats["files_total"] == 3
    assert stats["files_used"] == 2
    assert stats["files_dup"] == 1
    assert stats["files_failed"] == 0
    assert stats["rows_mismatch"] == 0
    dup_lines = [r for r in reports if r.startswith("SKIP-DUP")]
    assert len(dup_lines) == 1
    assert "AMZTestUS-2026" in dup_lines[0]


def test_hidden_dir_not_scanned(tmp_path):
    bucket = _make_bucket(tmp_path)
    hidden = bucket / ".repair_cache"
    hidden.mkdir()
    (hidden / "AMZHiddenUS-2026-10-05.txt").write_text(_txt(["9\tUSD\t1.0\tTax\tOrder\tItemPrice\tSKU9"]), encoding="utf-8")
    stats: dict = {}
    df, _ = read_bucket_amz_txts(bucket, stats_out=stats)
    assert stats["files_total"] == 3
    assert len(df) == 3


def test_repair_cache_outside_bucket(tmp_path):
    bucket = tmp_path / "账期20261004-20261103"
    (bucket / "甲").mkdir(parents=True)
    # 多一个 tab → 触发 tab 修复并写缓存
    bad = HEADER + "1\tUSD\t10.0\tTax\tOrder\tItemPrice\tSKU1\tEXTRA\n"
    (bucket / "甲" / "AMZBadUS-2026-10-05.txt").write_text(bad, encoding="utf-8")
    df, _ = read_bucket_amz_txts(bucket)
    assert len(df) == 1
    assert (tmp_path / ".repair_cache_账期20261004-20261103").is_dir()
    assert not (bucket / ".repair_cache").exists()


def test_parse_failure_reported(tmp_path):
    """解析失败时不能静默：必须落到 FAIL 报告里。"""
    bucket = tmp_path / "账期20261004-20261103"
    (bucket / "甲").mkdir(parents=True)
    # 第二条数据行坏掉（引号不闭合），pandas 会解析异常
    (bucket / "甲" / "AMZBadUS-2026-10-05.txt").write_text(
        HEADER + '1\tUSD\t10.0\tTax\tOrder\tItemPrice\t"SKU1\n', encoding="utf-8"
    )
    stats: dict = {}
    _df, reports = read_bucket_amz_txts(bucket, stats_out=stats)
    assert any(r.startswith("FAIL") for r in reports)
