#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""重复建单加后缀：扫历史导入 xlsx 算下一个可用 `-N`。

通途不允许重复订单号，同一 PO 分两次建单时第二次要换号（见
`docs/reference/workflow.md` §10）。这里覆盖：历史扫描、后缀规则、显式/自动解析，
以及后缀确实进了通途 xlsx 且不影响 PDF 关联。
"""

from __future__ import annotations

from pathlib import Path

import pandas as pd
import pytest

import pb_tongtu_excel as m
import service


def write_history_xlsx(path: Path, order_numbers) -> Path:
    """造一个与 export 产物同构的「历史导入」xlsx（含 `PO Number-Line` 列）。"""
    path.parent.mkdir(parents=True, exist_ok=True)
    pd.DataFrame(
        {"PO Number-Line": list(order_numbers), "Vendor Style": ["X"] * len(order_numbers)}
    ).to_excel(path, index=False)
    return path


def test_scan_collects_used_numbers_and_skips_bad_file(tmp_path):
    h = tmp_path / "hist"
    write_history_xlsx(
        h / "PB_0_导入_原始_a_on_2026-09-01_00-00-00.xlsx",
        ["137770200-1", "137770200-2", "137974027"],
    )
    write_history_xlsx(
        h / "PB_0_导入_原始_b_on_2026-09-02_00-00-00.xlsx",
        ["137974181-1", "137974181-2", "137974181-3", "137974027"],
    )
    (h / "PB_0_导入_原始_bad.xlsx").write_bytes(b"not an xlsx")
    # `~$` 临时文件不该被当历史
    write_history_xlsx(h / "~$PB_0_导入_原始_a.xlsx", ["999"])

    used, warnings, files = m.scan_used_order_numbers([h])
    assert used["137770200"] == {"137770200-1", "137770200-2"}
    assert used["137974027"] == {"137974027"}
    assert used["137974181"] == {"137974181-1", "137974181-2", "137974181-3"}
    assert "999" not in used  # `~$` 被跳过
    assert files == 3  # 三个真文件（坏的那个也算「扫到」）
    assert warnings and "读不了" in warnings[0]


def test_next_suffix_rule_max_plus_one(tmp_path):
    h = tmp_path / "hist"
    write_history_xlsx(
        h / "PB_0_导入_原始_a.xlsx",
        ["137770200-1", "137770200-2", "137974027",
         "137974181-1", "137974181-2", "137974181-3"],
    )
    sfx, warns, _ = m.next_reorder_suffixes(["137770200", "137974027", "137974181"], [h])
    # -1/-2 -> -3；只见过裸号 -> -2；-1..-3 -> -4
    assert sfx == {"137770200": "-3", "137974027": "-2", "137974181": "-4"}
    assert warns == []


def test_next_suffix_warns_when_po_absent(tmp_path):
    h = tmp_path / "hist"
    h.mkdir()
    sfx, warns, files = m.next_reorder_suffixes(["137999999"], [h])
    assert sfx == {"137999999": "-2"}
    assert files == 0
    assert any("没扫到" in w for w in warns)


def test_parse_reorder_spec_auto_and_explicit():
    auto, explicit = m.parse_reorder_spec(["137974027", "137887120=-2", "A=3", "B, C"])
    assert auto == ["137974027", "B", "C"]
    assert explicit == {"137887120": "-2", "A": "-3"}


def test_build_order_df_applies_suffix_to_order_number(pb_env):
    df = m.build_order_df(pb_env.csv, order_suffixes={"137943090": "-2"})
    # 137943090 是同一个 PO 的 2 行 -> 后缀 + 批内 Line#（后缀加在 PO Number 上）
    got = sorted(
        v for v in df["PO Number-Line"].unique() if str(v).startswith("137943090")
    )
    assert got == ["137943090-2-1", "137943090-2-2"]
    assert "137943090-2" in set(df["PO Number"].astype(str))
    # 没点名的 PO 不受影响
    assert "137943091" in set(df["PO Number-Line"].astype(str))


def test_build_order_df_without_suffix_is_unchanged(pb_env):
    df = m.build_order_df(pb_env.csv)
    assert set(df["PO Number"].astype(str)) == {"137943090", "137943091"}


def test_run_job_applies_reorder_suffix_and_still_joins(pb_env):
    hist = pb_env.tmp / "hist"
    # 该 PO 历史只建过裸号 -> 下一次 -2
    write_history_xlsx(hist / "PB_0_导入_原始_old.xlsx", ["137943090"])

    out = pb_env.tmp / "out-reorder"
    result = service.run_job(
        pb_env.pdf, pb_env.csv,
        service.JobOptions(
            reorder=["137943090"], history_dirs=[str(hist)],
            cache_only=True, sku_cache_path=pb_env.cache,
        ),
        out,
    )
    assert result.report["reorder"]["applied"] == {"137943090": "-2"}
    assert result.report["reorder"]["history_files"] == 1
    # 后缀进了产物，且 PDF 关联没断（1:1 / join 都在 run_job 里硬校验过）
    assert result.report["join"]["unmatched"] == 0
    tongtool = next(a for a in result.artifacts if a.kind == "tongtool")
    df = pd.read_excel(tongtool.path, dtype=str)
    assert "137943090-2" in set(df["PO Number"].astype(str))
    assert "137943091" in set(df["PO Number"].astype(str))


def test_run_job_explicit_suffix_overrides_history(pb_env):
    hist = pb_env.tmp / "hist"
    write_history_xlsx(hist / "PB_0_导入_原始_old.xlsx", ["137943090", "137943090-2"])
    result = service.run_job(
        pb_env.pdf, pb_env.csv,
        service.JobOptions(
            reorder=["137943090=-7"], history_dirs=[str(hist)], validate_only=True,
        ),
    )
    assert result.report["reorder"]["applied"] == {"137943090": "-7"}
