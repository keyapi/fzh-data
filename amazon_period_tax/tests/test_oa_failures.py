# -*- coding: utf-8 -*-
"""OA Excel sheet 读失败必须可见（默认 warnings，--strict 走 rep.warnings 非 0）。"""
from __future__ import annotations

import pandas as pd
import pytest


def _make_xlsx(path) -> None:
    with pd.ExcelWriter(path, engine="openpyxl") as w:
        pd.DataFrame({"新平台销售账户": ["A"], "选择平台": ["亚马逊"], "账期日期": ["2026-08-01"]}).to_excel(
            w, sheet_name="Good", index=False
        )
        pd.DataFrame({"x": [1]}).to_excel(w, sheet_name="Bad", index=False)


def test_sheet_failure_reported_not_silent(tmp_path, monkeypatch):
    import phase3_merge

    path = tmp_path / "oa.xlsx"
    _make_xlsx(path)
    good = pd.DataFrame({"新平台销售账户": ["A"], "选择平台": ["亚马逊"], "账期日期": ["2026-08-01"]})

    def fake_read(_path, sheet_name, _dtype):
        if sheet_name == "Bad":
            raise RuntimeError("boom")
        return good.copy(), 0

    monkeypatch.setattr(phase3_merge, "read_dingtalk_oa_sheet", fake_read)
    failures: list[str] = []
    df = phase3_merge.load_oa_dataframe(path, failures_out=failures)
    assert len(df) == 1
    assert any(f.startswith("FAIL-SHEET Bad") for f in failures)


def test_all_sheets_fail_raises(tmp_path, monkeypatch):
    import phase3_merge

    path = tmp_path / "oa2.xlsx"
    _make_xlsx(path)

    def fake_read(_path, _sheet_name, _dtype):
        raise RuntimeError("boom")

    monkeypatch.setattr(phase3_merge, "read_dingtalk_oa_sheet", fake_read)
    failures: list[str] = []
    with pytest.raises(ValueError, match="无法读取 OA Excel"):
        phase3_merge.load_oa_dataframe(path, failures_out=failures)
    assert len(failures) == 2


def test_hesuan_sheet_short_circuits(tmp_path):
    import phase3_merge

    path = tmp_path / "oa3.xlsx"
    with pd.ExcelWriter(path, engine="openpyxl") as w:
        pd.DataFrame({"新平台销售账户": ["A"]}).to_excel(w, sheet_name="核算行", index=False)
        pd.DataFrame({"x": [1]}).to_excel(w, sheet_name="Bad", index=False)
    failures: list[str] = []
    df = phase3_merge.load_oa_dataframe(path, failures_out=failures)
    assert len(df) == 1
    assert failures == []
