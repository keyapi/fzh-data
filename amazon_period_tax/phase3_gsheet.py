# -*- coding: utf-8 -*-
"""Phase3 目标 GSheet 读写与 tab 排序。"""
from __future__ import annotations

import re
from datetime import date, datetime

import numpy as np
import pandas as pd

from phase3_constants import PHASE3_SPREADSHEET_ID

# 这些列必须当文本写：21 位审批编号被当成数字会变科学计数法/丢位
ID_TEXT_COLS = ("审批编号", "关联审批单", "发起人工号", "数据id")


def open_phase3_spreadsheet(gc):
    return gc.open_by_key(PHASE3_SPREADSHEET_ID)


def worksheet_values_to_df(rows: list[list]) -> pd.DataFrame:
    if not rows:
        return pd.DataFrame()
    header = rows[0]
    return pd.DataFrame(rows[1:], columns=header).replace("", pd.NA)


def _gsheet_cell(value, column: str):
    """RAW 写入用的单元格值：保留数字原生类型，空值写空串，ID 列强制文本。

    之前 ``df.fillna("").astype(str)`` 把所有数字变成字符串，再配合 USER_ENTERED 被 Sheets
    重新解析（审批编号会变科学计数法，公式样字符串还会被当公式）。改 RAW 后数字要以原生
    Python 标量写出，格式（``_人民币``/``_比例``）才不会被当成文本。
    """
    if value is None:
        return ""
    try:
        if pd.isna(value):
            return ""
    except (TypeError, ValueError):
        pass  # list/array 之类，走 str()
    if column in ID_TEXT_COLS:
        if isinstance(value, float) and value.is_integer():
            return str(int(value))
        return str(value).strip()
    if isinstance(value, (np.integer, np.floating, np.bool_)):
        return value.item()
    if isinstance(value, (pd.Timestamp, datetime)):
        if getattr(value, "hour", 0) or getattr(value, "minute", 0) or getattr(value, "second", 0):
            return value.strftime("%Y-%m-%d %H:%M:%S")
        return value.strftime("%Y-%m-%d")
    if isinstance(value, date):
        return value.isoformat()
    if isinstance(value, (int, float, bool)):
        return value
    return str(value)


def df_to_gsheet_rows(df: pd.DataFrame) -> list[list]:
    header = df.columns.astype(str).tolist()
    body = [[_gsheet_cell(v, str(c)) for v, c in zip(row, df.columns)] for row in df.itertuples(index=False, name=None)]
    return [header] + body


def write_worksheet_df(
    gc,
    df: pd.DataFrame,
    *,
    worksheet: str,
    clear: bool = True,
    value_input_option: str = "RAW",
) -> None:
    import gspread

    sh = open_phase3_spreadsheet(gc)
    try:
        ws = sh.worksheet(worksheet)
    except gspread.exceptions.WorksheetNotFound:
        ws = sh.add_worksheet(
            title=worksheet,
            rows=max(len(df) + 5, 50),
            cols=max(len(df.columns) + 2, 20),
        )
    if clear:
        ws.clear()
    ws.update(df_to_gsheet_rows(df), value_input_option=value_input_option)


def phase3_spreadsheet_available(gc) -> bool:
    try:
        open_phase3_spreadsheet(gc)
        return True
    except Exception:
        return False


def read_worksheet_df(gc, worksheet: str) -> pd.DataFrame:
    import gspread

    if not phase3_spreadsheet_available(gc):
        return pd.DataFrame()
    sh = open_phase3_spreadsheet(gc)
    try:
        ws = sh.worksheet(worksheet)
    except gspread.exceptions.WorksheetNotFound:
        return pd.DataFrame()
    return worksheet_values_to_df(ws.get_all_values())


def complete_year(date_part: str) -> str:
    if len(date_part) == 9:
        return date_part[:5] + "20" + date_part[5:]
    return date_part


def phase3_tab_sort_key(title: str) -> tuple:
    prefix_order = ["人民币", ""]
    suffix_order = [
        "FBA费用扣减后收款比例运营人员",
        "FBA费用扣减后分类汇总",
        "收款比例收款归属",
        "收款比例运营人员",
        "",
        "原始",
    ]
    s = title
    prefix = ""
    for pre in prefix_order:
        if pre and s.startswith(pre):
            prefix = pre
            s = s[len(pre) :]
            break
    date_match = re.search(r"\d{8}-\d{4,8}", s)
    if date_match:
        date_range = complete_year(date_match.group(0))
        start_date = date_range.split("-")[0]
        suffix = s[len(date_match.group(0)) :]
    else:
        start_date = "00000000"
        suffix = s
    prefix_index = prefix_order.index(prefix) if prefix in prefix_order else len(prefix_order)
    suffix_index = suffix_order.index(suffix) if suffix in suffix_order else len(suffix_order)
    return (-int(start_date), prefix_index, suffix_index)


def sort_phase3_tabs(gc, *, pin_worksheet: str | None = None) -> None:
    sh = open_phase3_spreadsheet(gc)
    sheets = sh.worksheets()
    pattern = re.compile(r"\d{8}-\d{4,8}")
    variable_titles = sorted(
        {s.title for s in sheets if pattern.search(s.title)},
        key=phase3_tab_sort_key,
    )
    ordered: list[str] = []
    seen: set[str] = set()
    if pin_worksheet:
        ordered.append(pin_worksheet)
        seen.add(pin_worksheet)
    for t in variable_titles:
        if t not in seen:
            ordered.append(t)
            seen.add(t)
    for s in sheets:
        if s.title not in seen:
            ordered.append(s.title)
            seen.add(s.title)
    title_to_sheet = {s.title: s for s in sheets}
    sorted_sheets = [title_to_sheet[t] for t in ordered if t in title_to_sheet]
    requests = []
    for i, sheet in enumerate(sorted_sheets):
        requests.append(
            {
                "updateSheetProperties": {
                    "properties": {"sheetId": sheet.id, "index": i},
                    "fields": "index",
                }
            }
        )
    if requests:
        sh.batch_update({"requests": requests})
