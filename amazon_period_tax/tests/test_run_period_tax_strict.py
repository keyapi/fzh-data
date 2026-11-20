# -*- coding: utf-8 -*-
"""run_period_tax 的 --strict 失败清单：OUT-OF-PERIOD / SKIP-DUP / FAIL 任一 >0 即非空。"""
from __future__ import annotations

import importlib.util
from pathlib import Path

# 直接按文件加载，避免把 scripts/ 放进 sys.path 后遮蔽包内同名模块（verify_period 等）。
_PATH = Path(__file__).resolve().parents[1] / "scripts" / "run_period_tax.py"
_spec = importlib.util.spec_from_file_location("run_period_tax_module", _PATH)
assert _spec and _spec.loader
_mod = importlib.util.module_from_spec(_spec)
_spec.loader.exec_module(_mod)
collect_strict_failures = _mod.collect_strict_failures


def test_clean_run_has_no_failures():
    assert (
        collect_strict_failures(
            {"files_failed": 0, "rows_mismatch": 0},
            n_skip_dup=0,
            n_out_of_period=0,
            missing_fx=[],
            gsheet_rows=5,
            n_accounts=5,
        )
        == []
    )


def test_each_category_is_reported():
    failures = collect_strict_failures(
        {"files_failed": 1, "rows_mismatch": 2},
        n_skip_dup=3,
        n_out_of_period=4,
        missing_fx=["JPY"],
        gsheet_rows=4,
        n_accounts=5,
    )
    joined = ";".join(failures)
    for token in (
        "SKIP-DUP=3",
        "OUT-OF-PERIOD=4",
        "FAIL=1",
        "rows_mismatch=2",
        "missing_fx=",
        "gsheet_rows=4!=accounts=5",
    ):
        assert token in joined


def test_out_of_period_alone_fails():
    assert collect_strict_failures(
        {}, n_skip_dup=0, n_out_of_period=1, missing_fx=[], gsheet_rows=1, n_accounts=1
    ) == ["OUT-OF-PERIOD=1"]
