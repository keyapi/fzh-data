# -*- coding: utf-8 -*-
"""
通途「普通商品」导出：按 SKU 与 SKU别名 炸开为多行（一对多）。

逻辑与原先 Colab 一致：先把主 SKU 并入别名串再按分号拆开、explode，
空别名时仅保留主 SKU 一行，避免 ``主SKU;`` 拆出空串。

输出仅三列：SKU、SKU别名、商品名称。
"""

from __future__ import annotations

import argparse
import os
import sys

import pandas as pd

DEFAULT_INPUT = "通途普通商品.xlsx"
DEFAULT_OUTPUT = "通途SKU别名炸开.xlsx"
COL_MAIN = "SKU"
COL_ALIAS = "SKU别名"
COL_NAME = "商品名称"
DELIMITER = ";"
OUTPUT_COLS = (COL_MAIN, COL_ALIAS, COL_NAME)


def explode_sku_aliases(
    df: pd.DataFrame,
    col_main: str = COL_MAIN,
    col_alias: str = COL_ALIAS,
    delimiter: str = DELIMITER,
) -> pd.DataFrame:
    for c in (col_main, col_alias, COL_NAME):
        if c not in df.columns:
            raise ValueError(
                f"需要列 {OUTPUT_COLS}，缺少 {c!r}。当前为: {list(df.columns)}"
            )

    def tokens_for_row(row: pd.Series) -> list[str]:
        main = str(row[col_main]).strip() if pd.notna(row[col_main]) else ""
        raw = row[col_alias]
        if pd.isna(raw) or str(raw).strip() == "":
            return [main] if main else []
        rest = str(raw).strip()
        combined = main + delimiter + rest
        parts = [p.strip() for p in combined.split(delimiter) if p.strip()]
        return parts if parts else ([main] if main else [])

    out = df.copy()
    out["_explode_tokens"] = out.apply(tokens_for_row, axis=1)
    out = out.explode("_explode_tokens", ignore_index=True)
    out[col_alias] = out["_explode_tokens"]
    out = out.drop(columns=["_explode_tokens"])

    # 与 Colab 一致：别名列空值用主 SKU 填（explode 后一般无 NaN，保留以防万一）
    out[col_alias] = out[col_alias].fillna(out[col_main])

    return out[list(OUTPUT_COLS)]


def main() -> None:
    ap = argparse.ArgumentParser(description="通途 SKU 别名按分号炸开")
    ap.add_argument(
        "input",
        nargs="?",
        default=None,
        help=f"输入 xlsx（默认: {DEFAULT_INPUT}）",
    )
    ap.add_argument(
        "-o",
        "--output",
        default=None,
        help=f"输出 xlsx（默认: {DEFAULT_OUTPUT}）",
    )
    ap.add_argument(
        "--sheet",
        default=0,
        help="工作表名或索引（默认 0）",
    )
    args = ap.parse_args()

    base = os.path.dirname(os.path.abspath(__file__))
    os.chdir(base)

    inp = args.input or DEFAULT_INPUT
    if not os.path.isfile(inp):
        print(f"找不到输入文件: {inp}", file=sys.stderr)
        sys.exit(1)

    out_path = args.output or os.path.join(base, DEFAULT_OUTPUT)

    # sheet: try int
    sheet: str | int = args.sheet
    if isinstance(sheet, str) and sheet.isdigit():
        sheet = int(sheet)

    df = pd.read_excel(inp, sheet_name=sheet, header=0)
    result = explode_sku_aliases(df)
    result.to_excel(out_path, index=False, engine="openpyxl")
    print(f"Wrote {len(result)} rows -> {out_path}")


if __name__ == "__main__":
    main()
