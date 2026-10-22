# -*- coding: utf-8 -*-
"""「数据透视表-报税成本」的规格构造（纯函数，不访问网络）。

口径来源：通途订单202607 的既有透视表，按表头名解析列偏移。
"""
from __future__ import annotations

ROW_FIELDS: tuple[dict, ...] = (
    {"name": "渠道账号", "repeat_headings": True},
    {"name": "发货仓按销售汇总分类", "repeat_headings": True},
    {"name": "通途SKU", "repeat_headings": False},
)

VALUE_FIELDS: tuple[str, ...] = (
    "发货数量",
    "皮壳成本*系数*数量",
    "绍兴二次加工成本*系数*数量",
    "二次加工成本*系数*数量",
    "头程运费*数量",
    "运费",
)

# 202607 实测基准；表头发生漂移时显式失败，避免静默生成错口径。
BASELINE_OFFSETS: dict[str, int] = {
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

TARGET_COLUMN_COUNT = 51
GRID_BUFFER_ROWS = 200


def column_letter(n: int) -> str:
    """1-based 列号 → A / Z / AA…"""
    if n < 1:
        raise ValueError(f"列号必须 >= 1: {n}")
    s = ""
    while n > 0:
        n, r = divmod(n - 1, 26)
        s = chr(65 + r) + s
    return s


def required_names() -> list[str]:
    return [f["name"] for f in ROW_FIELDS] + list(VALUE_FIELDS)


def resolve_offsets(header: list[str]) -> dict[str, int]:
    """表头名 → 0-based 列偏移；缺列、重名、与基准不一致均抛错。"""
    cleaned = [str(v).strip() for v in header]
    offsets: dict[str, int] = {}
    problems: list[str] = []
    for name in required_names():
        hits = [i for i, v in enumerate(cleaned) if v == name]
        if len(hits) != 1:
            problems.append(f"{name}: 命中 {len(hits)} 次")
            continue
        offsets[name] = hits[0]
    if problems:
        raise ValueError("源表表头不满足透视口径: " + "; ".join(problems))

    drifted = {
        name: (offsets[name], BASELINE_OFFSETS[name])
        for name in required_names()
        if offsets[name] != BASELINE_OFFSETS[name]
    }
    if drifted:
        detail = ", ".join(f"{k}: 实际 {a} ≠ 基准 {b}" for k, (a, b) in drifted.items())
        raise ValueError(f"源表列顺序已变化，请先复核口径: {detail}")
    return offsets


def build_pivot_spec(
    header: list[str],
    source_sheet_id: int,
    end_row: int,
    end_col: int,
) -> dict:
    """返回与 202607 逐字段一致的 pivotTable dict。"""
    offsets = resolve_offsets(header)
    rows = []
    for field in ROW_FIELDS:
        item = {
            "sourceColumnOffset": offsets[field["name"]],
            "showTotals": True,
            "sortOrder": "ASCENDING",
        }
        if field["repeat_headings"]:
            item["repeatHeadings"] = True
        rows.append(item)

    return {
        "source": {
            "sheetId": source_sheet_id,
            "startRowIndex": 0,
            "endRowIndex": end_row,
            "startColumnIndex": 0,
            "endColumnIndex": end_col,
        },
        "rows": rows,
        "values": [
            {"sourceColumnOffset": offsets[name], "summarizeFunction": "SUM"}
            for name in VALUE_FIELDS
        ],
    }


def estimated_grid_rows(
    group_count: int,
    account_count: int,
    account_warehouse_count: int,
) -> int:
    """明细 + 账号小计 + 账号×仓小计 + 总计 + 表头 + 缓冲。"""
    return group_count + account_count + account_warehouse_count + 2 + GRID_BUFFER_ROWS


def build_create_requests(
    sheet_id: int,
    title: str,
    index: int,
    row_count: int,
    spec: dict,
    column_count: int = TARGET_COLUMN_COUNT,
) -> list[dict]:
    """同一批 batchUpdate：addSheet + updateCells（失败则整体不落地）。"""
    return [
        {
            "addSheet": {
                "properties": {
                    "sheetId": sheet_id,
                    "title": title,
                    "index": index,
                    "gridProperties": {
                        "rowCount": row_count,
                        "columnCount": column_count,
                        "hideGridlines": True,
                    },
                }
            }
        },
        {
            "updateCells": {
                "start": {"sheetId": sheet_id, "rowIndex": 0, "columnIndex": 0},
                "rows": [{"values": [{"pivotTable": spec}]}],
                "fields": "pivotTable",
            }
        },
    ]


def expected_output_header() -> list[str]:
    return [f["name"] for f in ROW_FIELDS] + [f"用于“{v}”的 SUM" for v in VALUE_FIELDS]
