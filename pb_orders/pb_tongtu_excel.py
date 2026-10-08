#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""步骤 3：SPS 订单 CSV -> 通途导入 xlsx。

流程（照搬 Colab notebook 步骤 3，仅修 pandas 3.0 不兼容点）：
1. 读 CSV（PO Number / Zip 等强制为字符串，日期列 parse_dates）
2. 按 PO Number 分组组内前向填充（订单头 H 行的地址等字段下发给 D 行）
3. 只保留 Record Type == 'D' 的订单行
4. 按 (PO Number, PO Line # 倒序) 排序
5. 若 Qty Ordered > 1，拆成多行（每行 1 件），便于一页一包裹
6. 派生 Line # / Line Count / PO Number-Line / x Qty Ordered / SKUxQTY
7. 删掉通途不认的固定列，再按需从右往左删空列，保证不超过 100 列
8. 无货 SKU（--no-stock）从可导入集合中剔除，并单独出「无库存」文件

输出（与历史文件命名一致，产物落当天文件夹）：
    无 no-stock：  PB_0_导入_原始_{csv_stem}_on_{ts}.xlsx
    有 no-stock：  PB_0_不可导入_原始_... + PB_1_不可导入_无库存_... + PB_2_导入_库存有货_...

用法：
    uv run python pb_tongtu_excel.py "checked0stock order x40 20260921_0159_334423.csv"

    # 重复建单（补发）给订单号加后缀，后缀扫历史导入 xlsx 自动算：
    uv run python pb_tongtu_excel.py "checked0stock …csv" \
        --reorder 137974027 --history-dir "...\\PB orders"
"""

import argparse
import csv
import io
import os
import re
import sys
from collections.abc import Iterable
from datetime import datetime
from pathlib import Path

import numpy as np
import pandas as pd

# 通途导入列数上限（超出会导入失败）
MAX_COLS = 100

# 强制为字符串的列：PO Number / Zip 等若被 pandas 推断成数字会丢前导 0 或变成科学计数法
DTYPE_STR = {
    "PO Number": str,
    "PO Line #": str,
    "Retailers PO": str,
    "Customer Order #": str,
    "Buyers Catalog or Stock Keeping #": str,
    "Contact Phone": str,
    "Ship to Zip": str,
    "Ship To Zip": str,
    "Ship To Contact": str,
    "Bill To Zip": str,
    "Buying Party Zip": str,
}
DATE_COLS = ["PO Date", "Requested Delivery Date", "Ship Dates"]

# 固定删除的 31 列（通途导入模板不需要；原始 130 列 -> 99 列）
COLS_TO_DROP = [
    "Payment Terms %", "Payment Terms Disc Due Date", "Payment Terms Disc Days Due",
    "Payment Terms Net Due Date", "Payment Terms Net Days", "Payment Terms Disc Amt",
    "Payment Terms Desc", "PO Total Weight ", "PO Total UOM ", "Shipping account number",
    "Mark for Name", "Mark for Address 1", "Mark for Address 2", "Mark for City",
    "Mark for State", "Mark for Postal", "Mark for Country", "Shipping Container Code",
    "National Drug Code", "Expiration Date", "Dist", "Scheduled Quantity",
    "Scheduled Qty UOM", "Required By Date", "Must Arrive By", "Entire Shipment",
    "Agreement Number", "Additional Vendor Part #", "Buyer Part Number",
    "Carrier Details Special Handling", "Restrictions/Conditions",
]

COL_PO = "PO Number"
COL_PO_LINE = "PO Number-Line"
COL_RECORD_TYPE = "Record Type"
COL_QTY = "Qty Ordered"
COL_VENDOR_STYLE = "Vendor Style"
COL_SKUxQTY = "SKUxQTY"

# build_order_df/导出真正会读到的列。缺了会以 `KeyError: 'Ship To Country'` 这种
# 形式炸在深处，页面只能给一句「输入数据有问题」；先检查一遍，把缺哪几列说清楚。
REQUIRED_COLUMNS = [
    COL_PO, "PO Line #", COL_RECORD_TYPE, COL_QTY, COL_VENDOR_STYLE,
    "Buyers Catalog or Stock Keeping #", "Ship To Country", "Unit Price",
]


def _timestamp(fmt="%Y-%m-%d_%H-%M-%S"):
    return datetime.now().strftime(fmt)


class CsvSourceError(ValueError):
    """SPS 订单 CSV 读不了：编码不对，或行结构与表头对不上。

    两种情况都得把**具体原因**说出来 —— 早先只抛一句「无法读取 SPS 订单 CSV」，
    把 pandas 的 `Expected 147 fields in line 3, saw 148` 吞掉了，用户根本没法自查。
    """


def read_text_lines(path) -> list[str]:
    """读 CSV 文本行（UTF-8，容 BOM），去掉末尾空行。"""
    try:
        text = Path(path).read_text(encoding="utf-8-sig")
    except UnicodeDecodeError as exc:
        raise CsvSourceError(
            f"CSV 不是 UTF-8 文本（第 {exc.start} 字节处解码失败）。"
            "用 Excel 另存过的话请选「CSV UTF-8」，或从 SPS 重新导出。"
        ) from exc
    except OSError as exc:
        raise CsvSourceError(f"读不到 CSV：{exc}") from exc
    lines = text.splitlines()
    while lines and not lines[-1].strip():
        lines.pop()
    return lines


def strip_trailing_empty_fields(lines: list[str]) -> tuple[list[str], str]:
    """削掉数据行末尾多出来的**空**字段，返回 (处理后行, 给用户看的说明)。

    实测 20260924 批次：表头 147 字段、H 行 146、**D 行 148** —— D 行在所有列
    之后多一个空字段（SPS 自己导出就这样，Excel 另存也常见）。pandas 遇到
    「比表头多」的行会直接 `ParserError: Expected 147 fields in line 3, saw 148`，
    于是整批读不进来。

    这些字段在所有列之后且为空，削掉不影响任何一列的对齐；
    但只要多出来的部分**有非空值**，就说明列可能真的错位 —— 直接拒绝：
    宁可让人回 SPS 重导，也不能拿错位的数据去发货。
    """
    width = len(next(csv.reader([lines[0]])))
    out: list[str] = []
    dropped = 0
    for no, line in enumerate(lines, start=1):
        if no == 1 or not line.strip():
            out.append(line)
            continue
        cells = next(csv.reader([line]))
        extra = len(cells) - width
        if extra <= 0:
            out.append(line)
            continue
        if any(cell != "" for cell in cells[width:]):
            raise CsvSourceError(
                f"第 {no} 行比表头多 {extra} 个字段，其中有非空值：{cells[width:][:3]}"
                " —— 列可能整体错位。请从 SPS 重新导出这一批。"
            )
        trimmed = line.rstrip()
        if '"' in trimmed or not trimmed.endswith("," * extra):
            raise CsvSourceError(
                f"第 {no} 行比表头多 {extra} 个字段（含引号或结尾形状异常），无法安全处理。"
                "请从 SPS 重新导出这一批。"
            )
        trimmed = trimmed[:-extra]
        if len(next(csv.reader([trimmed]))) != width:
            raise CsvSourceError(
                f"第 {no} 行规范后仍与表头宽度不符。请从 SPS 重新导出这一批。"
            )
        out.append(trimmed)
        dropped += 1
    note = ""
    if dropped:
        note = (
            f"输入有 {dropped} 行在末尾多出空字段（SPS 导出 / Excel 另存常见）："
            "读取时按空字段忽略，不影响列对齐；checked CSV 仍逐行照搬原文，原样保留"
        )
    return out, note


def read_order_csv_lines(path) -> list[str]:
    """读订单 CSV 的文本行，容忍末尾多出的空字段。"""
    lines = read_text_lines(path)
    lines, _note = strip_trailing_empty_fields(lines)
    return lines


def load_order_csv(path):
    """读订单 CSV：dtype / parse_dates 只对实际存在的列生效。

    走 `read_order_csv_lines`，否则被 Excel 另存/手工合并过的文件会因为
    「数据行比表头多一个空字段」被 pandas 整批拒绝。
    """
    text = "\n".join(read_order_csv_lines(path))
    header = pd.read_csv(io.StringIO(text), nrows=0).columns
    dtype = {k: v for k, v in DTYPE_STR.items() if k in header}
    usecols_dates = [c for c in DATE_COLS if c in header]
    return pd.read_csv(io.StringIO(text), dtype=dtype, parse_dates=usecols_dates or None)


def drop_extra_empty_columns(df, max_cols=MAX_COLS):
    """列数 > max_cols 时，从右往左删整列空值列，直到 <= max_cols。"""
    if df.shape[1] <= max_cols:
        return df
    d = df.replace("", np.nan)
    empty = [c for c in list(d.columns)[::-1] if d[c].isna().all()]
    return df.drop(columns=empty[: df.shape[1] - max_cols])


def build_order_df(path, *, order_suffixes=None):
    """订单 CSV -> 通途导入用 DataFrame（拆行后）。

    `order_suffixes`（可选）：{PO: "-N"}，给「重复建单」的 PO 加订单号后缀。
    通途不允许重复订单号，同一 PO 分两次建单时第二次要换号（见
    `docs/reference/workflow.md` §10）。后缀加在 `PO Number` 上、在 `Line #`
    派生**之前** —— 与历史人工做法一致（改 H/D 两行的 PO Number），所以
    单行时得到 `{PO}-{N}`、同批多行时得到 `{PO}-{N}-{Line#}`。
    join 侧 `sps_pb_pdf.join_pages_with_orders` 会按 `-` 截断，不影响 PDF 关联。
    """
    df = load_order_csv(path)

    missing = [c for c in REQUIRED_COLUMNS if c not in df.columns]
    if missing:
        # 这里是纯文本错误信息，别写 markdown 记号（页面会原样显示 **）
        raise ValueError(
            "订单 CSV 缺少必需列：" + "、".join(missing)
            + "。出件要的是 SPS 导出的完整订单 CSV（checked0stock …），不是只有几列的摘要。"
        )

    # 组内前向填充：pandas 3.0 的 groupby.ffill() 会丢掉分组键，且 include_groups=True 已禁用
    # 用 concat 把 PO Number 拼回首位（直接赋值会往碎片化的宽表里 insert，触发 PerformanceWarning）
    po_keys = df[COL_PO]
    ffilled = df.groupby(COL_PO, group_keys=False).ffill()
    df = pd.concat([po_keys, ffilled], axis=1)

    df = df.loc[df[COL_RECORD_TYPE] == "D"].copy()

    if order_suffixes:
        po = df[COL_PO].astype(str).str.strip()
        df[COL_PO] = po + po.map(order_suffixes).fillna("")

    # 按 (PO Number, PO Line # 倒序) 排序。PO Line # 保持 CSV 读进来的字符串类型、
    # 按字典序比较 —— 与 notebook 一致；转成数字会改变导出列的值（'1' -> 1）。
    df = df.sort_values(
        by=[COL_PO, "PO Line #"], ascending=[True, False], ignore_index=True
    )

    # 数量 > 1 的拆成多行，每行 1 件（PDF 一页一包裹）
    qty = pd.to_numeric(df[COL_QTY], errors="coerce")
    if qty.isna().any():
        bad = df.loc[qty.isna(), COL_PO].tolist()
        raise ValueError(f"{COL_QTY} 存在空值/非数字，无法拆行。PO: {bad[:5]}")
    df = df.loc[df.index.repeat(qty.astype(int))].reset_index(drop=True)
    df.loc[pd.to_numeric(df[COL_QTY]) > 1, COL_QTY] = 1

    df["Line #"] = (df.groupby(COL_PO).cumcount(ascending=False) + 1).astype(str)
    df["Line Count"] = df.groupby(COL_PO)[COL_PO].transform("count")
    df["PO Number-Line"] = np.where(
        df["Line Count"] == 1, df[COL_PO], df[COL_PO] + "-" + df["Line #"]
    )

    if "PO Date" in df.columns:
        df["PO Date"] = df["PO Date"].dt.strftime("%Y-%m-%d %H:%M:%S")
    df["Ship To Country"] = df["Ship To Country"].str.replace("USA", "US")

    df["Unit Price x Qty Ordered"] = df["Unit Price"] * df[COL_QTY]

    df["x Qty Ordered"] = df[COL_QTY].astype("Int64").astype(str)
    multi = df["x Qty Ordered"] != "1"
    df.loc[multi, "x Qty Ordered"] = df.loc[multi, "x Qty Ordered"] + " ! ! !"
    df[COL_SKUxQTY] = df[COL_VENDOR_STYLE] + " x" + df["x Qty Ordered"]

    df = df.drop(columns=COLS_TO_DROP, errors="ignore")
    return drop_extra_empty_columns(df).reset_index(drop=True)


def split_no_stock(df, no_stock_skus):
    """按无货 SKU 拆分（大小写不敏感）。no_stock_skus 为空则全部可导入。

    注：Colab 里这段是死代码（参数是字符串，for 遍历的是单个字符，isin 永不命中），
    本版做成真正可用；默认不传 = 不过滤，与当前 Colab 行为等价。
    """
    if not no_stock_skus:
        return df, df.iloc[0:0].copy()
    wanted = {s.strip().lower() for s in no_stock_skus if s.strip()}
    mask = df[COL_VENDOR_STYLE].astype(str).str.strip().str.lower().isin(wanted)
    return df.loc[~mask].copy(), df.loc[mask].copy()


# ---------- 重复建单加后缀（workflow.md §10）--------------------------------
# 通途不允许重复订单号。同一 PO 分两次建单（典型：部分缺货，有货先发、缺货到货后补发）
# 时，第二次要换一个没用过的订单号。历史「通途导入」xlsx（本模块 export 出的
# PB_*_导入_*.xlsx）的 `PO Number-Line` 列就是历次用过的号，可离线查「用到哪了」。
_HISTORY_GLOB = "**/PB_*导入*.xlsx"
_SUFFIX_RE = re.compile(r"-(\d+)$")


def parse_reorder_spec(items: Iterable[str]) -> tuple[list[str], dict[str, str]]:
    """解析 `--reorder` 取值，返回 `(要自动算后缀的 PO 列表, {PO: "-N"} 显式映射)`。

    两种写法（可混用、逗号分隔）：
    - `137974027`     → 自动：扫历史算出下一个可用后缀；
    - `137974027=-2`  → 显式：直接用这个后缀（`=2` 也接受，自动补 `-`）。
    """
    auto: list[str] = []
    explicit: dict[str, str] = {}
    for raw in items:
        for chunk in str(raw).split(","):
            token = chunk.strip()
            if not token:
                continue
            if "=" in token:
                po, val = (part.strip() for part in token.split("=", 1))
                if not po:
                    continue
                explicit[po] = val if val.startswith("-") else f"-{val}"
            else:
                auto.append(token)
    return auto, explicit


def scan_used_order_numbers(
    dirs: Iterable[Path],
) -> tuple[dict[str, set[str]], list[str], int]:
    """扫历史「通途导入」xlsx，收集每个 PO 已经用过的订单号。

    返回 `(映射, 警告, 扫描到的文件数)`，映射为 `{基础PO: {完整订单号, …}}`。
    取 `PO Number-Line` 列（缺列回落 `PO Number`），以值里第一个 `-` 之前为键。
    坏文件 / 缺列文件**跳过并计数** —— 一个读不了的旧文件不该让整批后缀算不出来。
    跳过 Excel 的 `~$` 临时文件（与 `service.pick_newest` 同规则）。
    """
    used: dict[str, set[str]] = {}
    unreadable: list[str] = []
    files = 0
    for d in dirs:
        for path in sorted(Path(d).glob(_HISTORY_GLOB)):
            if path.name.startswith("~$") or not path.is_file():
                continue
            files += 1
            try:
                df = pd.read_excel(path, dtype=str)
            except Exception as exc:  # noqa: BLE001 - 坏文件只记名，不中断整批
                unreadable.append(f"{path.name}（{type(exc).__name__}）")
                continue
            col = COL_PO_LINE if COL_PO_LINE in df.columns else (
                COL_PO if COL_PO in df.columns else None
            )
            if col is None:
                unreadable.append(f"{path.name}（无 {COL_PO_LINE}/{COL_PO} 列）")
                continue
            for value in df[col].dropna().astype(str):
                value = value.strip()
                if not value or value.lower() == "nan":
                    continue
                used.setdefault(value.split("-")[0], set()).add(value)
    warnings: list[str] = []
    if unreadable:
        warnings.append(
            f"{len(unreadable)} 个历史导入文件读不了/缺列，已跳过（不影响其它）："
            + "、".join(unreadable[:5])
            + ("…" if len(unreadable) > 5 else "")
        )
    return used, warnings, files


def next_reorder_suffixes(
    pos: Iterable[str], history_dirs: Iterable[Path]
) -> tuple[dict[str, str], list[str], int]:
    """给出这些 PO 的下一个可用订单号后缀。

    规则（workflow.md §10）：后缀 = 该 PO 已用过的**最大 `-N` + 1**；从未用过带后缀的
    （只见过裸号、或历史里查无）→ `-2`。`-N` 与同批多行的 `Line#` 后缀是**同一命名空间**，
    所以必须按 max 递增，不能固定写 `-2`。

    返回 `(映射 {PO: "-N"}, 警告, 扫描到的文件数)`。查无历史的 PO 会警告 ——
    多半是 `history_dirs` 没盖全批次，不是真的没建过单。
    """
    used, warnings, files = scan_used_order_numbers(history_dirs)
    suffixes: dict[str, str] = {}
    for raw in pos:
        po = str(raw).strip()
        if not po:
            continue
        numbers = used.get(po, set())
        ns = [int(m.group(1)) for n in numbers if (m := _SUFFIX_RE.search(n))]
        if ns:
            suffixes[po] = f"-{max(ns) + 1}"
        else:
            suffixes[po] = "-2"
            if not numbers:
                warnings.append(
                    f"{po}：历史导入文件里没扫到该 PO，按 -2 处理；"
                    "若不符请用 --history-dir 指定 PB orders 根目录（覆盖所有历史批次）"
                )
    return suffixes, warnings, files


def export(df_all, df_importable, df_no_stock, out_dir, csv_stem, ts=None):
    """写导入文件，返回 {标签: 路径}。无 no-stock 命中时只写 PB_0。"""
    ts = ts or _timestamp()
    out_dir = Path(out_dir)
    out_dir.mkdir(parents=True, exist_ok=True)
    written = {}

    def _write(prefix, df):
        name = f"{prefix}_{csv_stem}_on_{ts}.xlsx"
        p = out_dir / name
        df.to_excel(p, index=False)
        written[prefix] = p
        return p

    if df_no_stock.empty:
        _write("PB_0_导入_原始", df_all)
    else:
        _write("PB_0_不可导入_原始", df_all)
        _write("PB_1_不可导入_无库存", df_no_stock)
        _write("PB_2_导入_库存有货", df_importable)
    return written


def main():
    ap = argparse.ArgumentParser(description="步骤 3：SPS 订单 CSV -> 通途导入 xlsx")
    ap.add_argument("csv", help="checked0stock order CSV 路径")
    ap.add_argument("--out", default=None, help="输出目录，默认与 CSV 同目录")
    ap.add_argument("--no-stock", default="", help="无货 SKU，逗号分隔")
    ap.add_argument(
        "--reorder", action="append", default=[], metavar="PO[=N]",
        help="给「重复建单」的 PO 加订单号后缀；`PO` 自动算，`PO=-2` 显式。可重复/逗号分隔",
    )
    ap.add_argument(
        "--history-dir", action="append", default=[], metavar="DIR",
        help="扫历史导入 xlsx 的目录（可重复）；默认 = 输入 CSV 所在目录",
    )
    args = ap.parse_args()

    src = Path(args.csv).resolve()
    if not src.is_file():
        sys.exit(f"文件不存在: {src}")
    out = Path(args.out).resolve() if args.out else src.parent

    auto_pos, suffixes = parse_reorder_spec(args.reorder)
    if auto_pos:
        history_dirs = [Path(d) for d in args.history_dir] or [src.parent]
        auto_map, warns, files = next_reorder_suffixes(auto_pos, history_dirs)
        suffixes.update(auto_map)
        print(f"扫历史导入文件 {files} 个（目录：{'、'.join(str(d) for d in history_dirs)}）")
        for w in warns:
            print(f"  [警告] {w}")
    if suffixes:
        print("已加后缀: " + "、".join(f"{p}{s}" for p, s in sorted(suffixes.items())))

    df = build_order_df(src, order_suffixes=suffixes)
    skus = [s for s in args.no_stock.split(",") if s.strip()]
    importable, no_stock = split_no_stock(df, skus)

    print(f"拆行后总行数: {len(df)} | 列数: {df.shape[1]}")
    print(f"可导入: {len(importable)} | 无库存: {len(no_stock)}")
    if df.shape[1] > MAX_COLS:
        print(f"警告：列数 {df.shape[1]} 超过通途上限 {MAX_COLS}")
    written = export(df, importable, no_stock, out, src.stem)
    for k, v in written.items():
        print(f"  {k}: {os.path.relpath(v, out)}")


if __name__ == "__main__":
    main()
