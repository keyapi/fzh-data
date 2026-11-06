# -*- coding: utf-8 -*-
"""透视表规格构造的单元测试（不访问网络）。"""
from __future__ import annotations

import sys
from pathlib import Path

import pytest

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))

from tongtool_order_cost.gsheets_pivot import (  # noqa: E402
    build_create_requests,
    build_pivot_spec,
    column_letter,
    estimated_grid_rows,
    expected_output_header,
    resolve_offsets,
)

HEADER_202607 = [
    "订单号", "平台SKU", "通途SKU", "品类orig", "品类", "品类统一名", "面料提取",
    "材料编码", "尺寸", "有无扣", "品类编码", "品类尺寸编码", "品类尺寸面料编码",
    "产品名称", "售价", "汇率", "售价*汇率", "发货数量", "是否皮壳", "皮壳含包装成本",
    "皮壳不含包装成本", "皮壳成本", "皮壳成本*数量", "当月给分公司发货类型",
    "绍兴二次加工成本", "绍兴二次加工成本*数量", "二次加工成本", "二次加工成本*数量",
    "1件产品成本", "产品成本*数量", "头程运费金额", "头程运费*数量", "海外仓成本",
    "海外仓成本*数量", "运费", "订单总成本", "订单利润", "渠道", "渠道账号",
    "发货仓库", "对应成本工作簿", "成本来源编码", "发货仓分类", "头程运费来源编码",
    "二次加工成本来源编码", "发货区域", "发货仓按销售汇总分类", "带*尺寸",
    "尺寸先大后小", "件套", "美版5尺寸", "材料名称", "品类别名", "绍兴成本系数",
    "皮壳含包装成本*系数", "皮壳不含包装成本*系数", "皮壳成本*系数",
    "皮壳成本*系数*数量", "绍兴二次加工成本系数", "绍兴二次加工成本*系数",
    "绍兴二次加工成本*系数*数量", "二次加工成本系数", "二次加工成本*系数",
    "二次加工成本*系数*数量", "1件产品成本*系数", "产品成本*系数*数量",
    "订单总成本*系数", "订单利润*系数", "当月是否新品", "运营部当月是否新品",
    "产品发售日期", "图片", "自定义费用", "产品名称去除品类", "EN绍兴包装半成品成本",
    "EN绍兴包装成品成本", "海外仓成本_USHWC", "平台SKU-渠道账号&实际运营人员",
]


def test_resolve_offsets_matches_202607_baseline():
    offsets = resolve_offsets(HEADER_202607)
    assert offsets == {
        "渠道账号": 38,
        "发货仓按销售汇总分类": 46,
        "通途SKU": 2,
        "发货数量": 17,
        "皮壳成本*系数*数量": 57,
        "绍兴二次加工成本*系数*数量": 60,
        "二次加工成本*系数*数量": 63,
        "头程运费*数量": 31,
        "运费": 34,
    }


def test_pivot_spec_equals_202607_golden():
    spec = build_pivot_spec(HEADER_202607, 801038373, 11233, 78)
    assert spec == {
        "source": {
            "sheetId": 801038373,
            "startRowIndex": 0,
            "endRowIndex": 11233,
            "startColumnIndex": 0,
            "endColumnIndex": 78,
        },
        "rows": [
            {
                "sourceColumnOffset": 38,
                "showTotals": True,
                "sortOrder": "ASCENDING",
                "repeatHeadings": True,
            },
            {
                "sourceColumnOffset": 46,
                "showTotals": True,
                "sortOrder": "ASCENDING",
                "repeatHeadings": True,
            },
            {
                "sourceColumnOffset": 2,
                "showTotals": True,
                "sortOrder": "ASCENDING",
            },
        ],
        "values": [
            {"sourceColumnOffset": 17, "summarizeFunction": "SUM"},
            {"sourceColumnOffset": 57, "summarizeFunction": "SUM"},
            {"sourceColumnOffset": 60, "summarizeFunction": "SUM"},
            {"sourceColumnOffset": 63, "summarizeFunction": "SUM"},
            {"sourceColumnOffset": 31, "summarizeFunction": "SUM"},
            {"sourceColumnOffset": 34, "summarizeFunction": "SUM"},
        ],
    }


def test_missing_column_raises():
    header = list(HEADER_202607)
    header[38] = "别的东西"
    with pytest.raises(ValueError, match="命中 0 次"):
        build_pivot_spec(header, 1, 10, 78)


def test_duplicate_column_raises():
    header = list(HEADER_202607) + ["运费"]
    with pytest.raises(ValueError, match="命中 2 次"):
        build_pivot_spec(header, 1, 10, 78)


def test_column_drift_raises():
    header = list(HEADER_202607)
    header[31], header[34] = header[34], header[31]
    with pytest.raises(ValueError, match="列顺序已变化"):
        build_pivot_spec(header, 1, 10, 78)


def test_column_letter():
    assert column_letter(1) == "A"
    assert column_letter(26) == "Z"
    assert column_letter(27) == "AA"
    assert column_letter(78) == "BZ"
    with pytest.raises(ValueError):
        column_letter(0)


def test_create_requests_are_atomic_pair():
    spec = build_pivot_spec(HEADER_202607, 1, 100, 78)
    reqs = build_create_requests(123, "数据透视表-报税成本202608", 5, 900, spec)
    assert len(reqs) == 2
    assert reqs[0]["addSheet"]["properties"]["sheetId"] == 123
    assert reqs[0]["addSheet"]["properties"]["index"] == 5
    assert reqs[0]["addSheet"]["properties"]["gridProperties"] == {
        "rowCount": 900,
        "columnCount": 51,
        "hideGridlines": True,
    }
    assert reqs[1]["updateCells"]["start"] == {
        "sheetId": 123,
        "rowIndex": 0,
        "columnIndex": 0,
    }
    assert reqs[1]["updateCells"]["fields"] == "pivotTable"
    assert reqs[1]["updateCells"]["rows"][0]["values"][0]["pivotTable"] == spec


def test_estimated_grid_rows_and_header():
    assert estimated_grid_rows(2170, 40, 70) == 2170 + 40 + 70 + 2 + 200
    assert expected_output_header() == [
        "渠道账号",
        "发货仓按销售汇总分类",
        "通途SKU",
        "用于“发货数量”的 SUM",
        "用于“皮壳成本*系数*数量”的 SUM",
        "用于“绍兴二次加工成本*系数*数量”的 SUM",
        "用于“二次加工成本*系数*数量”的 SUM",
        "用于“头程运费*数量”的 SUM",
        "用于“运费”的 SUM",
    ]
