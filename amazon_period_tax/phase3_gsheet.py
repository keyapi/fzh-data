# -*- coding: utf-8 -*-
"""Phase3 目标 GSheet 读写与 tab 排序。"""
from __future__ import annotations

import re

import pandas as pd

from phase3_constants import PHASE3_SPREADSHEET_ID


def open_phase3_spreadsheet(gc):
    return gc.open_by_key(PHASE3_SPREADSHEET_ID)


def worksheet_values_to_df(rows: list[list]) -> pd.DataFrame:
    if not rows:
        return pd.DataFrame()
    header = rows[0]
    return pd.DataFrame(rows[1:], columns=header).replace("", pd.NA)


def df_to_gsheet_rows(df: pd.DataFrame) -> list[list]:
    header = df.columns.astype(str).tolist()
    body = [
        [vv if pd.notna(vv) else "" for vv in row]
        for row in df.fillna("").astype(str).values.tolist()
    ]
    return [header] + body


def write_worksheet_df(
    gc,
    df: pd.DataFrame,
    *,
    worksheet: str,
    clear: bool = True,
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
    ws.update(df_to_gsheet_rows(df), value_input_option="USER_ENTERED")


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
