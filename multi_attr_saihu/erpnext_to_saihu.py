# -*- coding: utf-8 -*-
"""
Convert ERPNext vertical item export to Saihu multi-attribute import template.

Input (sheet 物料): 物料编码, 物料组, ..., 物料名称, 属性(规格属性), 属性值(规格属性)。
未指定路径时只自动选择纵向多属性用导出：含「物料导出」且**不含**「产品 通途SKU」（与配对用通途导出区分；「不含通途SKU」类仍可选）。
Output (sheet 商品): same columns as template xlsx, attributes 1–3 ordered 面料 → 尺寸 → 颜色.
Rows are sorted ascending by *SKU only (plain string order, e.g. ...-200- before ...-60-).

Optional `EN物料属性*.xlsx` Sheet1: 款式ID (= *SPU), 在售 (1=在售), 还有库存 (仅「有」算有库存).
Outputs: 赛狐导入_在售_转换结果.xlsx; 不在售拆为 赛狐导入_不在售有库存_转换结果.xlsx 与
赛狐导入_不在售无库存_转换结果.xlsx (在售=0 且 还有库存≠「有」、及未映射款式，进无库存).
"""

from __future__ import annotations

import argparse
import glob
import os
import sys
from typing import Any

import pandas as pd

# Attribute slot order (left to right in template)
ATTR_ORDER = ("面料", "尺寸", "颜色")


def _norm(x: Any) -> str:
    if pd.isna(x):
        return ""
    return str(x).strip()


def _classify_attr(attr_name: str) -> str | None:
    """
    Map ERP attribute label to 面料 / 尺寸 / 颜色.

    Names are usually ``{物料组}{面料|尺寸|颜色}``. A plain substring search fails when
    物料组 itself contains 尺寸 (e.g. 大尺寸车载宠物窝): ``尺寸`` would match inside
    ``大尺寸`` and the ``…颜色`` row can be misclassified as ``尺寸``, overwriting the
    real size row. Prefer **suffix** match on 颜色 / 尺寸 / 面料 (longer suffixes first).
    """
    an = _norm(attr_name)
    if not an:
        return None
    if an.endswith("颜色"):
        return "颜色"
    if an.endswith("尺寸"):
        return "尺寸"
    if an.endswith("面料"):
        return "面料"
    for key in ATTR_ORDER:
        if key in an:
            return key
    return None


def _default_spu_from_sku(sku: str) -> str:
    """Use first segment before '-' as SPU (e.g. KS0001 from KS0001-HLR-...)."""
    sku = _norm(sku)
    if not sku:
        return ""
    parts = sku.split("-", 1)
    return parts[0] if parts else sku


def parse_erp_blocks(
    path: str, sheet: str | int = 0
) -> list[dict[str, Any]]:
    df = pd.read_excel(path, sheet_name=sheet, header=0)
    # Expected columns
    col_sku = "物料编码"
    col_group = "物料组"
    col_name = "物料名称"
    col_attr = "属性 (规格属性)"
    col_val = "属性值 (规格属性)"

    for c in (col_sku, col_group, col_name, col_attr, col_val):
        if c not in df.columns:
            raise ValueError(f"Missing column {c!r} in {path}. Found: {list(df.columns)}")

    blocks: list[dict[str, Any]] = []
    current: dict[str, Any] | None = None

    for _, row in df.iterrows():
        sku_cell = row[col_sku]
        if _norm(sku_cell):
            if current:
                blocks.append(current)
            current = {
                "物料编码": _norm(sku_cell),
                "物料组": _norm(row[col_group]),
                "物料名称": _norm(row[col_name]),
                "attrs": {},  # key: 面料|尺寸|颜色 -> {"name": str, "value": str}
            }

        if current is None:
            continue

        an = _norm(row[col_attr])
        av = _norm(row[col_val])
        kind = _classify_attr(an)
        if kind:
            current["attrs"][kind] = {"name": an, "value": av}

    if current:
        blocks.append(current)

    return blocks


def blocks_to_saihu_rows(
    blocks: list[dict[str, Any]],
    spu_fn,
) -> list[dict[str, Any]]:
    rows: list[dict[str, Any]] = []
    for b in blocks:
        sku = b["物料编码"]
        style = b["物料组"]
        pname = b["物料名称"]
        spu = spu_fn(sku, b)
        out: dict[str, Any] = {
            "*SPU": spu,
            "*款名": style,
            "*SKU": sku,
            "*品名": pname,
        }
        attrs = b["attrs"]
        for i, key in enumerate(ATTR_ORDER, start=1):
            slot = attrs.get(key, {})
            # Template uses * on attribute 1 name/value only
            if i == 1:
                out["*属性1"] = slot.get("name", "")
                out["*属性值(中)1"] = slot.get("value", "")
            else:
                out[f"属性{i}"] = slot.get("name", "")
                out[f"属性值(中){i}"] = slot.get("value", "")
        rows.append(out)
    return rows


COL_STOCK = "还有库存"


def load_spu_status_maps(
    path: str, sheet_name: str = "Sheet1"
) -> tuple[dict[str, int], dict[str, bool]]:
    """
    Read Sheet1: 款式ID -> (在售 1|0, 是否还有库存).
    还有库存: 仅当单元格规范化后等于「有」时为 True；「无」、空、其它均为 False。
    缺省列「还有库存」时，全部为 False。
    Duplicate 款式ID: last row wins.
    """
    df = pd.read_excel(path, sheet_name=sheet_name, header=0)
    id_col, sale_col = "款式ID", "在售"
    for c in (id_col, sale_col):
        if c not in df.columns:
            raise ValueError(
                f"Missing column {c!r} in {path} sheet {sheet_name!r}. Found: {list(df.columns)}"
            )
    has_stock_col = COL_STOCK in df.columns

    on_sale: dict[str, int] = {}
    stock_yes: dict[str, bool] = {}
    for _, row in df.iterrows():
        kid = _norm(row[id_col])
        if not kid:
            continue
        v = row[sale_col]
        if pd.isna(v):
            iv = 0
        else:
            try:
                iv = int(float(v))
            except (TypeError, ValueError):
                iv = 0
        on_sale[kid] = 1 if iv == 1 else 0
        if has_stock_col:
            stock_yes[kid] = _norm(row[COL_STOCK]) == "有"
        else:
            stock_yes[kid] = False
    return on_sale, stock_yes


def load_spu_onsale_map(path: str, sheet_name: str = "Sheet1") -> dict[str, int]:
    """Map 款式ID -> 在售 only (for erp_tongtu_bridge etc.)."""
    on_sale, _ = load_spu_status_maps(path, sheet_name)
    return on_sale


def split_rows_by_onsale_and_stock(
    rows: list[dict[str, Any]],
    spu_onsale: dict[str, int],
    spu_stock_yes: dict[str, bool],
) -> tuple[
    list[dict[str, Any]],
    list[dict[str, Any]],
    list[dict[str, Any]],
    int,
]:
    """
    Returns (on_sale_rows, off_sale_has_stock_rows, off_sale_no_stock_rows, count_spu_not_in_map).
    未出现在物料属性表中的 *SPU -> 无库存文件。
    """
    on_sale: list[dict[str, Any]] = []
    off_has: list[dict[str, Any]] = []
    off_no: list[dict[str, Any]] = []
    missing = 0
    for r in rows:
        spu = _norm(r.get("*SPU"))
        status = spu_onsale.get(spu)
        if status is None:
            missing += 1
            off_no.append(r)
        elif status == 1:
            on_sale.append(r)
        else:
            if spu_stock_yes.get(spu, False):
                off_has.append(r)
            else:
                off_no.append(r)
    return on_sale, off_has, off_no, missing


def sort_saihu_rows(rows: list[dict[str, Any]]) -> list[dict[str, Any]]:
    """Sort for Saihu prep: *SKU ascending (Unicode string order)."""

    def key(r: dict[str, Any]) -> str:
        return _norm(r.get("*SKU"))

    return sorted(rows, key=key)


def write_with_template_simple(
    template_path: str,
    out_path: str,
    data_rows: list[dict[str, Any]],
    sheet_name: str = "商品",
):
    """Copy template then overwrite sheet with pd.ExcelWriter(mode='a')."""
    import shutil

    Path(out_path).parent.mkdir(parents=True, exist_ok=True)
    shutil.copy(template_path, out_path)

    # 读取模板表头
    template_cols = pd.read_excel(template_path, sheet_name=sheet_name, nrows=0).columns.tolist()
    df = pd.DataFrame(data_rows)
    for c in template_cols:
        if c not in df.columns:
            df[c] = None
    df = df[template_cols]

    with pd.ExcelWriter(out_path, engine='openpyxl', mode='a', if_sheet_exists='replace') as writer:
        df.to_excel(writer, sheet_name=sheet_name, index=False)


def main():
    ap = argparse.ArgumentParser(description="ERPNext export → Saihu spu_add_new_sku template")
    ap.add_argument(
        "erp_path",
        nargs="?",
        default=None,
        help="ERPNext 纵向物料导出（默认：含「物料导出」且非「产品 通途SKU」配对表）",
    )
    ap.add_argument(
        "template_path",
        nargs="?",
        default=None,
        help="Saihu template xlsx (default: auto-pick *spu_add_new_sku*.xlsx)",
    )
    ap.add_argument(
        "--spu-status",
        default=None,
        metavar="PATH",
        help="物料属性 xlsx with Sheet1 款式ID/在售 (default: newest *物料属性*.xlsx in cwd)",
    )
    ap.add_argument(
        "--out-onsale",
        default=None,
        help="Output path for 在售=1 rows (default: 赛狐导入_在售_转换结果.xlsx)",
    )
    ap.add_argument(
        "--out-offsale-stock",
        default=None,
        help="Output for 在售=0 且 还有库存=「有」 (default: 赛狐导入_不在售有库存_转换结果.xlsx)",
    )
    ap.add_argument(
        "--out-offsale-nostock",
        default=None,
        help="Output for 在售=0 且无库存 / 未映射 (default: 赛狐导入_不在售无库存_转换结果.xlsx)",
    )
    ap.add_argument(
        "--no-spu-split",
        action="store_true",
        help="Ignore 物料属性 file; write a single 赛狐导入_转换结果.xlsx (legacy)",
    )
    args = ap.parse_args()

    base = os.path.dirname(os.path.abspath(__file__))
    os.chdir(base)

    erp = args.erp_path
    if not erp:
        # 纵向多属性：含「物料导出」；排除「产品 通途SKU」配对导出（不能仅用「通途SKU」子串，否则「不含通途SKU」会被误伤）
        cands = [
            f
            for f in glob.glob("*.xlsx")
            if not f.startswith("~$")
            and "物料导出" in f
            and "产品 通途SKU" not in f
            and "spu_add" not in f.lower()
            and "转换结果" not in f
            and "物料属性" not in f
            and "配对" not in f
            and "炸开" not in f
        ]
        if not cands:
            print(
                "未找到 ERP 纵向导出（需含「物料导出」且非「产品 通途SKU」表）。请传入 erp_path。",
                file=sys.stderr,
            )
            sys.exit(1)
        erp = sorted(cands, key=os.path.getmtime)[-1]

    tpl = args.template_path
    if not tpl:
        cands = [f for f in glob.glob("*spu_add_new_sku*.xlsx") if not f.startswith("~$")]
        if not cands:
            print("No Saihu template *spu_add_new_sku*.xlsx found.", file=sys.stderr)
            sys.exit(1)
        tpl = cands[0]

    blocks = parse_erp_blocks(erp, sheet=0)
    rows = blocks_to_saihu_rows(blocks, spu_fn=lambda sku, b: _default_spu_from_sku(sku))
    rows = sort_saihu_rows(rows)

    if args.no_spu_split:
        out = os.path.join(base, "赛狐导入_转换结果.xlsx")
        write_with_template_simple(tpl, out, rows, sheet_name="商品")
        print(f"Wrote {len(rows)} rows to {out}")
        return

    spu_path = args.spu_status
    if not spu_path:
        cands = [f for f in glob.glob("*物料属性*.xlsx") if not f.startswith("~$")]
        if not cands:
            print(
                "No *物料属性*.xlsx found; use --spu-status PATH or --no-spu-split.",
                file=sys.stderr,
            )
            sys.exit(1)
        spu_path = sorted(cands, key=os.path.getmtime)[-1]

    spu_map, spu_stock = load_spu_status_maps(spu_path, sheet_name="Sheet1")
    on_rows, off_has, off_no, n_missing = split_rows_by_onsale_and_stock(
        rows, spu_map, spu_stock
    )

    out_on = args.out_onsale or os.path.join(base, "赛狐导入_在售_转换结果.xlsx")
    out_off_stock = args.out_offsale_stock or os.path.join(
        base, "赛狐导入_不在售有库存_转换结果.xlsx"
    )
    out_off_nostock = args.out_offsale_nostock or os.path.join(
        base, "赛狐导入_不在售无库存_转换结果.xlsx"
    )

    write_with_template_simple(tpl, out_on, on_rows, sheet_name="商品")
    write_with_template_simple(tpl, out_off_stock, off_has, sheet_name="商品")
    write_with_template_simple(tpl, out_off_nostock, off_no, sheet_name="商品")

    print(
        f"SPU status: {spu_path} ({len(spu_map)} unique 款式ID)\n"
        f"  在售: {len(on_rows)} -> {out_on}\n"
        f"  不在售有库存: {len(off_has)} -> {out_off_stock}\n"
        f"  不在售无库存(含未映射): {len(off_no)} -> {out_off_nostock}\n"
        f"  *SPU not in sheet: {n_missing} (进无库存文件)"
    )


if __name__ == "__main__":
    main()
