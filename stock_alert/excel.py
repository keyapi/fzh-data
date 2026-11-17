# -*- coding: utf-8 -*-
"""库存提醒明细 Excel：低库存与采购入库均按仓库分 sheet。"""

from __future__ import annotations

from pathlib import Path

from .scan import ScanResult
from .inbound import InboundResult

# Excel sheet 名限制：≤31 字符，禁用 : \ / ? * [ ]
_INVALID = set(':\\/?*[]')


def _sheet_name(name: str) -> str:
    cleaned = "".join(c for c in (name or "") if c not in _INVALID)
    return (cleaned or "Sheet")[:31]


def _num(value: float):
    return int(value) if float(value).is_integer() else value


def write_low_stock_workbook(result: ScanResult, path: str | Path, *, newly_only: bool = True) -> Path:
    """写明细 Excel；`newly_only=True` 时只写「今日新增」低库存。"""
    from openpyxl import Workbook
    from openpyxl.styles import Font

    wb = Workbook()
    wb.remove(wb.active)  # 去掉默认空 sheet

    for wh in result.warehouses:
        ws = wb.create_sheet(_sheet_name(wh.warehouse))
        ws.append(["SKU", "产品名称", "可用库存", "在途库存"])
        for cell in ws[1]:
            cell.font = Font(bold=True)
        for item in wh.low:
            if newly_only and not item.is_new:
                continue
            ws.append([item.sku, item.name or item.sku, _num(item.available), _num(item.intransit)])
        ws.column_dimensions["A"].width = 42
        ws.column_dimensions["B"].width = 32
        ws.column_dimensions["C"].width = 12
        ws.column_dimensions["D"].width = 12

    if not wb.sheetnames:
        wb.create_sheet("空")

    out = Path(path)
    out.parent.mkdir(parents=True, exist_ok=True)
    wb.save(out)
    return out


def write_inbound_workbook(result: InboundResult, path: str | Path) -> Path:
    """入库正文过长时，完整明细通过同一张卡片下载。"""
    from openpyxl import Workbook
    from openpyxl.styles import Font

    wb = Workbook()
    wb.remove(wb.active)
    for wh in result.warehouses:
        ws = wb.create_sheet(_sheet_name(wh.warehouse))
        ws.append(["SKU", "产品名称", "入库数量"])
        for cell in ws[1]:
            cell.font = Font(bold=True)
        for item in wh.items:
            ws.append([item.sku, item.name or item.sku, _num(item.qty)])
        ws.column_dimensions["A"].width = 42
        ws.column_dimensions["B"].width = 40
        ws.column_dimensions["C"].width = 14
    if not wb.sheetnames:
        wb.create_sheet("空")
    out = Path(path)
    out.parent.mkdir(parents=True, exist_ok=True)
    wb.save(out)
    return out
