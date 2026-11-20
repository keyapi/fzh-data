# -*- coding: utf-8 -*-
"""写回 附加费&Tax / Tax{YYYYMM}。"""
from __future__ import annotations

import re

import pandas as pd

# 「附加费&Tax」— 用 id 打开，避免 Drive 按标题搜索
ADDITIONAL_FEE_TAX_SPREADSHEET_ID = "1nvBj05EfktUX5kgAkB_gQGlKn9IU1M55fuJGhyC7bI4"


def open_additional_fee_tax_spreadsheet(gc):
    return gc.open_by_key(ADDITIONAL_FEE_TAX_SPREADSHEET_ID)


def tax_worksheet_name(bucket_name: str) -> str:
    m = re.search(r"\d{8}-\d{8}", bucket_name)
    if not m:
        raise ValueError(f"桶名无日期区间: {bucket_name}")
    return f"Tax{m.group(0)[:6]}"


def additional_fee_worksheet_name(bucket_name: str) -> str:
    m = re.search(r"\d{8}-\d{8}", bucket_name)
    if not m:
        raise ValueError(f"桶名无日期区间: {bucket_name}")
    return f"附加费{m.group(0)[:6]}"


def additional_fee_worksheet_name_from_yyyymm(yyyymm: str) -> str:
    yyyymm = str(yyyymm).strip()
    if not re.fullmatch(r"\d{6}", yyyymm):
        raise ValueError(f"exchange-month 须为 YYYYMM，收到 {yyyymm!r}")
    return f"附加费{yyyymm}"


def ensure_zero_additional_fee_worksheet(
    gc,
    *,
    yyyymm: str,
    channel_accounts: list[str] | None = None,
    template_worksheet: str | None = None,
) -> dict:
    """缺失则新建「附加费{YYYYMM}」：表头同模板月，数值列填 0（Phase3 合并时按 0 算）。"""
    import gspread

    target = additional_fee_worksheet_name_from_yyyymm(yyyymm)
    sh = open_additional_fee_tax_spreadsheet(gc)
    try:
        sh.worksheet(target)
        return {"worksheet": target, "created": False, "rows": None, "message": "已存在，未覆盖"}
    except gspread.exceptions.WorksheetNotFound:
        pass

    tmpl_name = template_worksheet
    if not tmpl_name:
        prev = int(yyyymm)
        if prev % 100 == 1:
            tmpl_name = f"附加费{prev // 100 - 1}12"
        else:
            tmpl_name = f"附加费{prev - 1}"
    tmpl = sh.worksheet(tmpl_name)
    header = tmpl.row_values(1)
    if not header or not str(header[0]).strip():
        raise ValueError(f"模板 ws {tmpl_name!r} 无表头")

    zero_cols = {
        "附加费累加人民币",
        "账号单独费用",
        "账号销售费用附加费",
        "账号头程运费附加费",
        "账号尾程运费附加费",
    }
    rows_out: list[list] = [header]
    accounts = [str(a).strip() for a in (channel_accounts or []) if str(a).strip()]
    if not accounts:
        rows_out.append([""] * len(header))
    else:
        for acct in sorted(set(accounts)):
            row = [""] * len(header)
            row[0] = acct
            for i, col in enumerate(header):
                if col in zero_cols:
                    row[i] = "0"
                elif col == "汇率" and i + 1 < len(header):
                    pass
            rows_out.append(row)

    ws = sh.add_worksheet(
        title=target,
        rows=max(len(rows_out) + 5, 50),
        cols=max(len(header) + 2, 12),
    )
    ws.update(rows_out, value_input_option="USER_ENTERED")
    sort_additional_fee_tax_tabs(gc, pin_worksheet=target)
    return {
        "worksheet": target,
        "created": True,
        "rows": len(rows_out) - 1,
        "template": tmpl_name,
        "message": "已新建并排序（pin 到附加费/Tax 区最前）",
    }


def write_df_to_gsheet(
    df: pd.DataFrame,
    gc,
    *,
    spreadsheet: str = "附加费&Tax",
    worksheet: str,
    clear_all: bool = True,
) -> None:
    import gspread

    try:
        sh = (
            open_additional_fee_tax_spreadsheet(gc)
            if spreadsheet == "附加费&Tax"
            else gc.open(spreadsheet)
        )
    except gspread.exceptions.SpreadsheetNotFound as e:
        raise FileNotFoundError(spreadsheet) from e
    try:
        ws = sh.worksheet(worksheet)
    except gspread.exceptions.WorksheetNotFound:
        ws = sh.add_worksheet(title=worksheet, rows=max(len(df) + 5, 100), cols=max(len(df.columns) + 2, 20))
    if clear_all:
        ws.clear()
    data = [df.columns.astype(str).tolist()] + df.fillna("").astype(str).values.tolist()
    ws.update(data, value_input_option="USER_ENTERED")


def sort_additional_fee_tax_tabs(
    gc,
    *,
    spreadsheet: str = "附加费&Tax",
    pin_worksheet: str | None = None,
) -> None:
    """Colab cell 25：附加费/Tax{YYYYMM} 按月份降序，同月附加费在 Tax 前；其余 sheet 保持相对顺序。"""
    sh = open_additional_fee_tax_spreadsheet(gc) if spreadsheet == "附加费&Tax" else gc.open(spreadsheet)
    sheets = sh.worksheets()
    prefix_order = ["附加费", "Tax"]
    pattern = re.compile(r"\d{6}")

    def custom_sort_key(title: str):
        for prefix in prefix_order:
            if title.startswith(prefix):
                date_part = title[len(prefix) :]
                m = pattern.search(date_part)
                if m:
                    return (-int(m.group(0)), prefix_order.index(prefix))
                return (0, prefix_order.index(prefix))
        return (0, len(prefix_order))

    variable_titles = sorted(
        {s.title for s in sheets if pattern.search(s.title)},
        key=custom_sort_key,
    )
    ordered_titles: list[str] = []
    seen: set[str] = set()
    if pin_worksheet:
        ordered_titles.append(pin_worksheet)
        seen.add(pin_worksheet)
    for t in variable_titles:
        if t not in seen:
            ordered_titles.append(t)
            seen.add(t)
    for s in sheets:
        if s.title not in seen:
            ordered_titles.append(s.title)
            seen.add(s.title)
    title_to_sheet = {s.title: s for s in sheets}
    sorted_sheets = [title_to_sheet[t] for t in ordered_titles if t in title_to_sheet]

    requests = []
    for i, sheet in enumerate(sorted_sheets):
        if i >= len(sheets):
            print(f"跳过无效索引: {i}，工作表: {sheet.title}")
            continue
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
