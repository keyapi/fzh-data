# -*- coding: utf-8 -*-
"""D01：导出 N→M 守恒与读取阶段不丢行。

覆盖 gate_remediation_plan_20261120.md U-E2 / E2.1：
- 6 行 fixture（保留 / 其他月 / 无效日期 / 状态排除 / 迟交排除 / 读取失败）
  各自恰好 1 类，N=6 且分区和=6；
- 缺日期但有金额的行不得在读取阶段消失，进入 invalid 并阻断正式定稿；
- 读取失败的 sheet 逐条保留，不能被其它 sheet 成功掩盖；
- 21 位审批编号被浮点化时禁止伪恢复，直接阻断；
- 重复唯一键阻断。
"""
from __future__ import annotations

import pandas as pd
import pytest

from ding_xlsx import enrich, id_status, id_text, read_dingtalk_xlsx, read_dingtalk_xlsx_records
from export_lineage import (
    INVALID_MONTH,
    KEPT,
    OTHER_MONTH,
    READ_FAILED,
    build_export_lineage,
    duplicate_keys,
)

COLUMNS = ["审批编号", "账期日期", "发起时间", "审批状态", "审批结果", "选择平台", "AMZCTRD账户", "销售额"]


def _row(pid, date, status="完成", result="同意", amount=10):
    return {
        "审批编号": pid,
        "账期日期": date,
        "发起时间": "2026-11-05 10:00:00",
        "审批状态": status,
        "审批结果": result,
        "选择平台": "亚马逊",
        "AMZCTRD账户": "AMZCTRDUS",
        "销售额": amount,
    }


def _write(path, sheets):
    with pd.ExcelWriter(path, engine="openpyxl") as xw:
        for name, df in sheets.items():
            df.to_excel(xw, sheet_name=name, index=False)
    return path


def test_six_way_conservation(tmp_path):
    """6 行 fixture → 6 个互斥分区各 1 行，N=6。"""
    good = pd.DataFrame(
        [
            _row("A", "2026-11-01", amount=10),                 # 保留
            _row("B", "2026-10-09", amount=20),                 # 其他月
            _row("C", "not-a-date", amount=30),                 # 无效日期
            _row("D", "2026-11-02", status="已撤销", amount=40),  # 状态排除
            _row("E", "2026-11-03", amount=50),                 # 迟交排除（下面按 key 剔除）
        ]
    )
    notes = pd.DataFrame({"备注": ["这一页没有账期日期表头"]})  # 读取失败 1 行
    src = tmp_path / "export.xlsx"
    with pd.ExcelWriter(src, engine="openpyxl") as xw:
        good.to_excel(xw, sheet_name="核算", index=False)
        notes.to_excel(xw, sheet_name="说明", index=False, header=False)

    raw, report = read_dingtalk_xlsx_records(src)
    assert len(raw) == 5  # 缺/非法日期没有被读取阶段丢掉
    assert report["rows_failed"] == 1
    assert report["failed"][0]["sheet"] == "说明"

    en = enrich(raw)
    late_key = en.loc[en["审批编号"] == "E", "_key"].iloc[0]
    lineage = build_export_lineage(en, "2026-11", {late_key}, report)

    assert lineage.counts[KEPT] == 1
    assert lineage.counts[OTHER_MONTH] == 1
    assert lineage.counts[INVALID_MONTH] == 1
    assert lineage.counts["excluded_status"] == 1
    assert lineage.counts["excluded_late"] == 1
    assert lineage.counts[READ_FAILED] == 1
    assert lineage.n_total == 6
    # 显式把公式写死：N = 保留 + 其他月 + 无效 + 状态 + 迟交 + 读取失败
    assert lineage.n_total == (
        lineage.counts[KEPT]
        + lineage.counts[OTHER_MONTH]
        + lineage.counts[INVALID_MONTH]
        + lineage.counts["excluded_status"]
        + lineage.counts["excluded_late"]
        + lineage.counts[READ_FAILED]
    )
    assert lineage.assert_conserved() is lineage


def test_missing_date_amount_row_is_not_dropped_and_blocks(tmp_path):
    good = pd.DataFrame([_row("A", "2026-11-01", amount=10), _row("X", None, amount=99)])
    src = _write(tmp_path / "export.xlsx", {"核算": good})

    records, report = read_dingtalk_xlsx_records(src)
    legacy = read_dingtalk_xlsx(src)
    assert len(records) == 2  # 新读取器保留
    assert report["rows_failed"] == 0
    assert len(legacy) == 1  # 旧入口保持历史行为（只返回有日期的行）

    lineage = build_export_lineage(enrich(records), "2026-11", set(), report)
    assert lineage.counts[INVALID_MONTH] == 1
    assert lineage.n_invalid_with_amount == 1
    assert not lineage.is_publishable()
    assert any("有金额" in b for b in lineage.blockers())


def test_unreadable_sheet_not_masked_by_good_sheet(tmp_path):
    good = pd.DataFrame([_row("A", "2026-11-01")])
    bad = pd.DataFrame({"乱七八糟": ["a", "b"]})  # 2 行无表头
    src = _write(tmp_path / "export.xlsx", {"核算": good, "坏页": bad})

    raw, report = read_dingtalk_xlsx_records(src)
    assert len(raw) == 1
    assert report["rows_failed"] == 3  # 表头 + 2 数据行，全部算未分类
    lineage = build_export_lineage(enrich(raw), "2026-11", set(), report)
    assert lineage.counts[READ_FAILED] == 3
    assert not lineage.is_publishable()
    assert any("读取失败" in b for b in lineage.blockers())


def test_corrupted_float_id_is_blocked_and_not_faked(tmp_path):
    # Excel 把 21 位编号存成数字 → 读回是 float，精度已丢
    bad_id_value = 202607231544000528489.0
    df = pd.DataFrame([_row(bad_id_value, "2026-11-01")], columns=COLUMNS)
    src = _write(tmp_path / "export.xlsx", {"核算": df})

    raw, report = read_dingtalk_xlsx_records(src)
    value = raw["审批编号"].iloc[0]
    assert id_status(value) == "corrupted"
    assert report["corrupted_id_rows"] == 1
    # 禁止伪恢复成原 21 位数字
    assert id_text(value) != "202607231544000528489"

    lineage = build_export_lineage(enrich(raw), "2026-11", set(), report)
    assert not lineage.is_publishable()
    assert any("浮点化" in b for b in lineage.blockers())


def test_duplicate_unique_key_is_blocked():
    df = pd.DataFrame([_row("A", "2026-11-01", amount=10), _row("A", "2026-11-01", amount=10)])
    en = enrich(df)
    lineage = build_export_lineage(en, "2026-11", set(), {})
    assert lineage.counts[KEPT] == 2
    assert len(duplicate_keys(lineage.partitions[KEPT])) == 1
    assert not lineage.is_publishable()
    assert any("重复唯一键" in b for b in lineage.blockers())


def test_empty_key_is_not_a_duplicate():
    df = pd.DataFrame(
        [
            {"审批编号": "", "账期日期": "2026-11-01", "发起时间": None, "审批状态": "完成", "审批结果": "同意"},
            {"审批编号": "", "账期日期": "2026-11-01", "发起时间": None, "审批状态": "完成", "审批结果": "同意"},
        ]
    )
    en = enrich(df)
    assert duplicate_keys(en) == []


def test_lineage_rejects_unenriched_frame():
    with pytest.raises(ValueError, match="enrich"):
        build_export_lineage(pd.DataFrame({"x": [1]}), "2026-11", set(), {})
