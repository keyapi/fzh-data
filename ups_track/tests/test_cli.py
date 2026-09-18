"""cli.py 冒烟：--mock 离线跑通三件套输出。"""

from __future__ import annotations

import csv
import json

from ups_track.cli import main


def _write_input(path, numbers):
    with open(path, "w", encoding="utf-8") as fh:
        fh.write("tracking,备注\n")
        for i, n in enumerate(numbers, 1):
            fh.write(f"{n},row{i}\n")


def test_cli_query_mock(tmp_path):
    inp = tmp_path / "numbers.csv"
    out = tmp_path / "result"
    _write_input(str(inp), ["1Z999AA10123456784", "1Z999AA10123456785"])

    rc = main([
        "query", "--input", str(inp), "--out", str(out),
        "--mock", "--workers", "2",
    ])
    assert rc == 0

    summary = f"{out}.summary.csv"
    timeline = f"{out}.timeline.csv"
    raw = f"{out}.raw.json"

    with open(summary, "r", encoding="utf-8-sig") as fh:
        rows = list(csv.DictReader(fh))
    assert len(rows) == 2
    assert rows[0]["成功"] == "是"
    assert rows[0]["备注"] == "备注=row1"

    with open(timeline, "r", encoding="utf-8-sig") as fh:
        trows = list(csv.DictReader(fh))
    assert len(trows) >= 6  # 2 号各 ≥3 节点
    assert {"跟踪号", "节点时间", "描述"} <= set(trows[0].keys())

    with open(raw, "r", encoding="utf-8") as fh:
        rawd = json.load(fh)
    assert set(rawd) == {"1Z999AA10123456784", "1Z999AA10123456785"}
    assert rawd["1Z999AA10123456784"]["ok"] is True


def test_cli_query_mock_no_creds_input_missing():
    rc = main(["query", "--input", "NONEXISTENT_xyz.txt", "--out", "x", "--mock"])
    assert rc == 2
