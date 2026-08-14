# -*- coding: utf-8 -*-
"""Dry-run / apply old→new Tongtool SKU remap on Google Sheet tabs. SKU column only."""
from __future__ import annotations

import argparse
import sys
from pathlib import Path

import gspread
import pandas as pd
from gspread.utils import rowcol_to_a1

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))

from tongtool_order_cost.gsheets import client
from tongtool_order_cost.sku_map import DO_NOT_TOUCH, OLD_TO_NEW, sku_col

DEFAULT_TABS = [
    "2026年6月FBA订单",
    "写回2026年6月FBA订单",
    "写回2026年6月FBA订单和非FBA订单",
]


def col_index(header: list[str], name: str) -> int:
    names = [str(c).strip() for c in header]
    return names.index(name) + 1


def count_map(values: list[str]) -> dict[str, int]:
    keys = list(OLD_TO_NEW) + list(OLD_TO_NEW.values()) + sorted(DO_NOT_TOUCH)
    return {k: sum(1 for v in values if v == k) for k in keys}


def remap_tab(ws: gspread.Worksheet, apply: bool) -> dict:
    rows = ws.get_all_values()
    if not rows:
        raise RuntimeError(f"empty worksheet {ws.title}")
    header = rows[0]
    sku_name = sku_col(pd.DataFrame(columns=header))
    idx = col_index(header, sku_name)
    col_vals = [r[idx - 1].strip() if idx - 1 < len(r) else "" for r in rows]
    before = count_map(col_vals[1:])
    gray60_before = before.get("BNFBAvelvetgray60", 0)
    cells: list[gspread.Cell] = []
    for row_i, val in enumerate(col_vals[1:], start=2):
        if val in DO_NOT_TOUCH:
            continue
        new = OLD_TO_NEW.get(val)
        if new:
            cells.append(gspread.Cell(row_i, idx, new))
    result = {
        "工作表": ws.title,
        "SKU列": sku_name,
        "a1": rowcol_to_a1(1, idx),
        "改写单元格": len(cells),
        "before": before,
        "applied": False,
    }
    if apply and cells:
        ws.update_cells(cells, value_input_option="RAW")
        rows2 = ws.get_all_values()
        col_vals2 = [r[idx - 1].strip() if idx - 1 < len(r) else "" for r in rows2]
        after = count_map(col_vals2[1:])
        leftover = {k: after[k] for k in OLD_TO_NEW if after[k]}
        if leftover:
            raise RuntimeError(f"{ws.title} still has old SKUs: {leftover}")
        if after.get("BNFBAvelvetgray60", 0) != gray60_before:
            raise RuntimeError("BNFBAvelvetgray60 count changed")
        result["after"] = after
        result["applied"] = True
    return result


def main() -> None:
    p = argparse.ArgumentParser(description="Remap old Tongtool SKUs in Google Sheet tabs")
    p.add_argument("--sheet", required=True, help="Google spreadsheet title")
    p.add_argument("--tabs", nargs="+", default=DEFAULT_TABS)
    p.add_argument("--apply", action="store_true", help="Write SKU cells. Default is dry-run.")
    args = p.parse_args()

    gc = client()
    sh = gc.open(args.sheet)
    print("spreadsheet", sh.title, "apply", args.apply)
    for tab in args.tabs:
        ws = sh.worksheet(tab)
        report = remap_tab(ws, apply=args.apply)
        print(report)


if __name__ == "__main__":
    main()
