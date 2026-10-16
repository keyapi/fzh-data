#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""把「SPS库存检查操作表」里的缺货明细算成 Notion 待追加行（半自动）。

**只读 xlsx、只产出 JSON —— 不连 Notion。** 真正的写入走交互式 Notion MCP：
现有 Notion 工具的 OAuth 凭证只对 MCP 服务器有效，脚本复用不了
（实测把缓存的 token 打 REST API 返回 401），所以分工是「脚本算、Agent 推」。

用法::

    cd pb_orders
    uv run python notion_stockout.py \
        --xlsx "D:\\Work\\美国\\Tracy Miller\\PB orders\\20261012\\SPS库存检查操作表-order x24 20261012_0102_199800.xlsx" \
        --out rows_to_add.json

产出的 JSON 里 ``parent`` / ``pages`` 可直接传给 ``notion-create-pages``；
``summary`` 记录总数 / 新增 / 已存在跳过 / 未映射，任何一项都不会被静默丢掉。

推完之后，把新 PO 追加进 ``data/notion_pb_nostock_pos.json``（下次跑就不会重复推）。
"""

from __future__ import annotations

import argparse
import json
import re
import sys
from pathlib import Path
from typing import Any

import pandas as pd

SHEET_OVERVIEW = "操作总览"
SHEET_NO_STOCK = "缺货明细"
SHEET_FULLY_NO_STOCK = "全部缺货PO"

COL_PO = "PO Number"
COL_LINE = "PO Line #"
COL_VENDOR = "Vendor Style"
COL_BUYER = "Buyers Catalog or Stock Keeping #"
COL_PO_STATUS = "PO 库存状态"

PO_STATUS_PARTIAL = "部分缺货"
PO_STATUS_FULL = "全部缺货"

# Notion「打单」列的取值（未打单 / 已打单 / 部分）—— 注意与 PO 库存状态的「部分缺货」不同字
NOTION_FIELD_SHIPPED_PARTIAL = "部分"

# Notion「PB 无货未发（一行一个 PO）」库（与 data/notion_pb_nostock_pos.json 一致）
NOTION_DATA_SOURCE_ID = "collection://fa2f272d-289a-4a88-88eb-9ef39be00e43"

DATA_DIR = Path(__file__).resolve().parent / "data"
DEFAULT_SKU_MAP = DATA_DIR / "notion_sku_map.json"
DEFAULT_KNOWN_POS = DATA_DIR / "notion_pb_nostock_pos.json"

# xlsx 文件名里的 8 位日期（= SPS 操作日期）
DATE_TOKEN = re.compile(r"(?<!\d)(20\d{6})(?!\d)")

DEFAULT_REMARK = "库存预检自动登记；SPS 未打单"


class NotionStockoutError(Exception):
    """输入或映射有问题 —— 不产出半成品。"""


def _s(value: Any) -> str:
    """Excel 单元格 → 去空白字符串；NaN / None / 空 → ""。"""
    if value is None:
        return ""
    text = str(value).strip()
    return "" if text.lower() in ("nan", "none") else text


def norm_vendor(value: Any) -> str:
    """Vendor Style 归一化：去所有空白 + 大写（SPS 导出大小写/空格不稳定）。"""
    return re.sub(r"\s+", "", _s(value)).upper()


def load_sku_map(path: Path) -> dict[str, dict]:
    raw = json.loads(Path(path).read_text(encoding="utf-8"))
    mapping = {k: v for k, v in raw.items() if not k.startswith("_")}
    if not mapping:
        raise NotionStockoutError(f"SKU 映射表是空的：{path}")
    for key, entry in mapping.items():
        for field in ("sku", "tongtu_sku"):
            if not _s(entry.get(field)):
                raise NotionStockoutError(f"SKU 映射表 {path} 里 {key} 缺 {field}")
    return mapping


def load_known_pos(path: Path | None) -> set[str]:
    if path is None:
        return set()
    if not Path(path).exists():
        return set()
    raw = json.loads(Path(path).read_text(encoding="utf-8"))
    pos = raw.get("pos") if isinstance(raw, dict) else raw
    return {_s(p) for p in (pos or []) if _s(p)}


def _read_sheets(xlsx: Path) -> tuple[pd.DataFrame, pd.DataFrame, pd.DataFrame]:
    try:
        no_stock = pd.read_excel(xlsx, sheet_name=SHEET_NO_STOCK, dtype=str)
        fully = pd.read_excel(xlsx, sheet_name=SHEET_FULLY_NO_STOCK, dtype=str)
        overview = pd.read_excel(xlsx, sheet_name=SHEET_OVERVIEW, dtype=str)
    except ValueError as exc:  # sheet 不存在
        raise NotionStockoutError(
            f"{xlsx} 读不到预期的 sheet（{SHEET_OVERVIEW} / {SHEET_NO_STOCK} / "
            f"{SHEET_FULLY_NO_STOCK}）；这看着不像「SPS库存检查操作表」。原始错误：{exc}"
        ) from exc
    return no_stock, fully, overview


def _require_columns(df: pd.DataFrame, columns: list[str], sheet: str) -> None:
    missing = [c for c in columns if c not in df.columns]
    if missing:
        raise NotionStockoutError(
            f"sheet「{sheet}」缺列：{missing}；实际列：{list(df.columns)}"
        )


def _line_keys(df: pd.DataFrame) -> set[tuple[str, str]]:
    return {(_s(r[COL_PO]), _s(r[COL_LINE])) for _, r in df.iterrows()}


def _cross_check(no_stock: pd.DataFrame, fully: pd.DataFrame) -> None:
    """「缺货明细」里标 全部缺货 的行 必须与「全部缺货PO」sheet 完全一致。"""
    expected = {
        (_s(r[COL_PO]), _s(r[COL_LINE]))
        for _, r in no_stock.iterrows()
        if _s(r[COL_PO_STATUS]) == PO_STATUS_FULL
    }
    actual = _line_keys(fully)
    if expected != actual:
        raise NotionStockoutError(
            "「缺货明细」里 全部缺货 的行 与「全部缺货PO」sheet 对不上："
            f"只在缺货明细 {sorted(expected - actual)}；只在全部缺货PO {sorted(actual - expected)}"
        )


def _sps_date(stem: str, override: str | None) -> str:
    if override:
        return override
    match = DATE_TOKEN.search(stem)
    if not match:
        raise NotionStockoutError(
            f"文件名 {stem!r} 里找不到 8 位日期（YYYYMMDD），请用 --sps-date 指定 SPS 操作日期"
        )
    raw = match.group(1)
    return f"{raw[:4]}-{raw[4:6]}-{raw[6:]}"


def _original_po_count(overview: pd.DataFrame) -> str | None:
    if "项目" not in overview.columns or "数量" not in overview.columns:
        return None
    hit = overview[overview["项目"].map(_s) == "原始 PO"]
    if hit.empty:
        return None
    return _s(hit.iloc[0]["数量"]) or None


def _batch_label(xlsx: Path, sps_date: str, overview: pd.DataFrame) -> str:
    date_compact = sps_date.replace("-", "")
    count = _original_po_count(overview)
    mark = f"check0stock x{count}" if count else "check0stock"
    return f"{date_compact} {mark}（{xlsx.name}）"


def _properties(row: pd.Series, entry: dict, sps_date: str, batch: str) -> dict[str, Any]:
    props: dict[str, Any] = {
        "PO": _s(row[COL_PO]),
        "SKU": _s(entry["sku"]),
        "通途SKU": _s(entry["tongtu_sku"]),
        "对方SKU": _s(row[COL_BUYER]),
        "date:SPS操作日期:start": sps_date,
        "检出批次": batch,
        "打单": NOTION_FIELD_SHIPPED_PARTIAL
        if _s(row[COL_PO_STATUS]) == PO_STATUS_PARTIAL
        else "未打单",
        "通途建单": "__NO__",
        "invoice": "不适用",
        "顾客": "正常",
        "状态": "待到货",
        "备注": DEFAULT_REMARK,
    }
    eta = _s(entry.get("eta"))
    if eta:
        props["date:到货日期:start"] = eta
    return props


def build_payload(
    xlsx: Path,
    sku_map: dict[str, dict],
    known_pos: set[str] | None = None,
    sps_date: str | None = None,
    batch: str | None = None,
) -> dict[str, Any]:
    xlsx = Path(xlsx)
    if not xlsx.exists():
        raise NotionStockoutError(f"找不到 xlsx：{xlsx}")

    no_stock, fully, overview = _read_sheets(xlsx)
    _require_columns(no_stock, [COL_PO, COL_LINE, COL_VENDOR, COL_BUYER, COL_PO_STATUS], SHEET_NO_STOCK)
    _require_columns(fully, [COL_PO, COL_LINE], SHEET_FULLY_NO_STOCK)
    _cross_check(no_stock, fully)

    known_pos = known_pos or set()
    resolved_date = _sps_date(xlsx.stem, sps_date)
    label = batch or _batch_label(xlsx, resolved_date, overview)

    pages: list[dict[str, Any]] = []
    skipped: list[str] = []
    unmapped: list[str] = []
    no_eta: list[str] = []
    multi_line: list[str] = []
    seen_po: set[str] = set()

    for _, row in no_stock.iterrows():
        po = _s(row[COL_PO])
        entry = sku_map.get(norm_vendor(row[COL_VENDOR]))
        if entry is None:
            unmapped.append(f"{po} / {_s(row[COL_VENDOR])}")
            continue
        if po in known_pos:
            if po not in skipped:
                skipped.append(po)
            continue
        # 本表「一行一个 PO」：同一 PO 有多条缺货明细时只记一行，另在报告里点出来（不静默丢）。
        if po in seen_po:
            if po not in multi_line:
                multi_line.append(po)
            continue
        seen_po.add(po)
        if not _s(entry.get("eta")):
            no_eta.append(po)
        pages.append({"properties": _properties(row, entry, resolved_date, label)})

    return {
        "parent": {"type": "data_source_id", "data_source_id": NOTION_DATA_SOURCE_ID},
        "pages": pages,
        "summary": {
            "源文件": xlsx.name,
            "SPS操作日期": resolved_date,
            "检出批次": label,
            "缺货明细": int(len(no_stock)),
            "新增": len(pages),
            "已存在跳过": skipped,
            "未映射": unmapped,
            "无到货日期": no_eta,
            "同一PO多缺货行": multi_line,
        },
    }


def _print_report(payload: dict[str, Any], stream) -> None:
    s = payload["summary"]
    print(f"源文件      : {s['源文件']}", file=stream)
    print(f"SPS操作日期 : {s['SPS操作日期']}", file=stream)
    print(f"缺货明细    : {s['缺货明细']} 行", file=stream)
    print(f"新增        : {s['新增']}", file=stream)
    print(f"已存在跳过  : {s['已存在跳过'] or '（无）'}", file=stream)
    print(f"未映射      : {s['未映射'] or '（无）'}", file=stream)
    if s["无到货日期"]:
        print(f"无到货日期  : {s['无到货日期']}（到货日期留空，需人工补）", file=stream)
    if s["同一PO多缺货行"]:
        print(f"同一PO多缺货行: {s['同一PO多缺货行']}（只记一行，备注请人工补全）", file=stream)


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    parser.add_argument("--xlsx", required=True, help="SPS库存检查操作表-*.xlsx")
    parser.add_argument("--sku-map", default=str(DEFAULT_SKU_MAP), help="Vendor Style → Notion 取值映射表")
    parser.add_argument("--known-pos", default=str(DEFAULT_KNOWN_POS),
                        help="Notion 已有的 PO 快照（用于去重）；传 '' 关闭去重")
    parser.add_argument("--sps-date", default=None, help="覆盖 SPS 操作日期（YYYY-MM-DD）")
    parser.add_argument("--batch", default=None, help="覆盖「检出批次」文案")
    parser.add_argument("--out", default=None, help="输出 JSON 路径；缺省打到 stdout")
    args = parser.parse_args(argv)

    try:
        sku_map = load_sku_map(Path(args.sku_map))
        known_pos = load_known_pos(Path(args.known_pos) if args.known_pos else None)
        payload = build_payload(
            Path(args.xlsx), sku_map, known_pos,
            sps_date=args.sps_date, batch=args.batch,
        )
    except NotionStockoutError as exc:
        print(f"[错误] {exc}", file=sys.stderr)
        return 2

    _print_report(payload, sys.stderr)

    if payload["summary"]["未映射"]:
        print("[错误] 有 Vendor Style 不在映射表里，不产出结果 —— 先补 data/notion_sku_map.json",
              file=sys.stderr)
        return 2

    text = json.dumps(payload, ensure_ascii=False, indent=2)
    if args.out:
        Path(args.out).write_text(text + "\n", encoding="utf-8")
        print(f"[完成] 已写 {args.out}（{payload['summary']['新增']} 行待推）", file=sys.stderr)
    else:
        print(text)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
