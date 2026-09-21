#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""步骤 4.2：生成 PB 背贴 PDF（4×2 英寸，含包裹号 + 条形码 + 中/西品名）。

流程（照搬 Colab notebook cell 29，去掉明文私钥，改为读父仓库 secrets/）：
1. 读 Google Sheet `US SKU Name` -> 工作表 `SKUName`（列：通途SKU / 中文名称 / 西班牙语名称）
   - 网络抖动会重试；读取成功落本地 CSV 缓存，失败时回退缓存
   - 重复的通途SKU 去重（否则 merge 会多出页，页数对不上）
2. 中文名去掉尾部英文词（nltk words 词表；词表不可用则告警跳过）
   西班牙语名若含中文则清空（原 notebook 规则）
3. 与 PDF⋈订单 的结果按 Vendor Style 关联出中文/西语名
4. 每行一页：`PO: {PO}-{Line #}` + Code128 条形码 + 品名表

输出：`{MM.DD} PotteryBarn 背贴-中文西班牙语.pdf`

用法：
    uv run python pb_back_label_pdf.py <pdf_join.xlsx>  # 或由 run_pb_orders.py 调用
"""

import argparse
import os
import sys
import time
from datetime import datetime
from pathlib import Path

import pandas as pd
from reportlab.graphics.barcode import code128
from reportlab.lib import colors
from reportlab.lib.styles import ParagraphStyle, getSampleStyleSheet
from reportlab.lib.units import cm
from reportlab.pdfbase import pdfmetrics
from reportlab.pdfbase.cidfonts import UnicodeCIDFont
from reportlab.pdfgen import canvas
from reportlab.platypus import Paragraph, Table, TableStyle

from sellfox_shipping.sku_label.pdf_generator import build_mixed_xml, is_chinese
from tongtool_order_cost.tongtool_order_cost.gsheets import (
    client,
    gsheet2df,
    service_account_path,
)

SHEET_NAME = "US SKU Name"
WORKSHEET_NAME = "SKUName"
SA_FILENAME = "gsheets-service-account.json"
COL_SKU, COL_CN, COL_ES = "通途SKU", "中文名称", "西班牙语名称"

PAGE_W, PAGE_H = 288, 144
MARGIN_L, MARGIN_R, MARGIN_TOP = 5, 5, 10
LEADING = 9
COL_WIDTHS = [0.4 * cm, 2.35 * cm, 0.7 * cm, 3.25 * cm, 3.35 * cm]
HEADERS = ["#", "SKU", "QTY", "Name Chinese", "Nombres en español"]

BACK_LABEL_PDF_NAME = "{mmdd} PotteryBarn 背贴-中文西班牙语.pdf"
DATA_DIR = Path(__file__).resolve().parent / "data"
CACHE_CSV = DATA_DIR / "us_sku_name_cache.csv"
NLTK_DATA_DIR = DATA_DIR / "nltk_data"
SHEET_RETRIES = 5


def _retry(fn, tries=SHEET_RETRIES, delay=3):
    last = None
    for attempt in range(tries):
        try:
            return fn()
        except Exception as exc:  # noqa: BLE001 - 网络抖动需重试任意异常
            last = exc
            if attempt < tries - 1:
                time.sleep(delay)
    raise last


def _find_service_account():
    """从模块目录逐级向上找 secrets/gsheets-service-account.json。

    worktree 场景下 gitignore 的 secrets/ 只存在于父仓库（见 CONCEPTS.md
    「凭证在父仓库不在 worktree」），所以不能只看仓库根。
    """
    for base in [Path(__file__).resolve().parent, *Path(__file__).resolve().parent.parents]:
        candidate = base / "secrets" / SA_FILENAME
        if candidate.is_file():
            return candidate
    return None


def ensure_service_account_env():
    """把找到的凭证路径写进 GSPREAD_SERVICE_ACCOUNT_FILE，供共享 gsheets helper 使用。

    用户已显式设置环境变量时不覆盖；仓库根就有凭证时也不动。
    """
    if os.environ.get("GSPREAD_SERVICE_ACCOUNT_FILE", "").strip():
        return
    try:
        if service_account_path().is_file():
            return
    except Exception:  # noqa: BLE001 - 找不到就走父仓库回退
        pass
    found = _find_service_account()
    if found:
        os.environ["GSPREAD_SERVICE_ACCOUNT_FILE"] = str(found)


def load_sku_name(cache_path=CACHE_CSV, use_cache_only=False):
    """读 `US SKU Name` 表；成功则落缓存，失败回退缓存。返回 (df, 来源说明)。"""
    cache_path = Path(cache_path)
    if not use_cache_only:
        try:
            ensure_service_account_env()
            gc = _retry(client)
            df = _retry(lambda: gsheet2df(gc, SHEET_NAME, WORKSHEET_NAME))
            cache_path.parent.mkdir(parents=True, exist_ok=True)
            df.to_csv(cache_path, index=False)
            return df, f"Google Sheet（已缓存到 {cache_path.name}）"
        except Exception as exc:  # noqa: BLE001
            print(f"警告：读取 {SHEET_NAME} 失败（{type(exc).__name__}: {exc}）")
    if cache_path.is_file():
        return pd.read_csv(cache_path), f"本地缓存 {cache_path.name}"
    raise FileNotFoundError(
        f"无法读取 {SHEET_NAME}，且无本地缓存 {cache_path}。"
        "请确认 secrets/gsheets-service-account.json 存在且网络可用。"
    )


_english_words = None


def load_english_words(nltk_dir=NLTK_DATA_DIR):
    """加载 nltk 英文词表（本地缓存优先）；不可用返回 None 并告警。"""
    global _english_words
    if _english_words is not None:
        return _english_words
    try:
        import nltk

        nltk.data.path.insert(0, str(nltk_dir))
        try:
            from nltk.corpus import words
        except LookupError:
            nltk.download("words", download_dir=str(nltk_dir), quiet=True)
            from nltk.corpus import words
        _english_words = {w.lower() for w in words.words()}
    except Exception as exc:  # noqa: BLE001
        print(
            f"警告：nltk 英文词表不可用（{type(exc).__name__}），"
            "本次跳过中文名英文后缀清理（输出可能与 Colab 略有差异）"
        )
        _english_words = None
    return _english_words


def remove_english_suffix(text, english_words=None):
    """去掉中文名里第一个英文单词及其之后的内容；词表不可用则原样返回。"""
    if pd.isna(text):
        return ""
    words_set = english_words if english_words is not None else _english_words
    if not words_set:
        return str(text)
    kept = []
    for part in str(text).split():
        if part.lower() in words_set:
            break
        kept.append(part)
    return " ".join(kept)


def prepare_name_table(df, cache_path=CACHE_CSV, use_cache_only=False):
    """整理名称表：清洗 + 去重（返回 (df, 来源说明, 重复键列表)）。"""
    df, source = load_sku_name(cache_path, use_cache_only)
    if df.empty:
        raise ValueError(f"{SHEET_NAME}/{WORKSHEET_NAME} 无数据")

    english_words = load_english_words()
    df[COL_CN] = df[COL_CN].fillna("").apply(lambda x: remove_english_suffix(x, english_words))
    df[COL_ES] = df[COL_ES].fillna("").apply(
        lambda x: "" if any(is_chinese(c) for c in str(x)) else str(x)
    )
    df["_key"] = df[COL_SKU].astype(str).str.strip().str.upper()

    dupes = sorted(df.loc[df["_key"].duplicated(keep=False), "_key"].unique())
    if dupes:
        print(f"警告：名称表有重复 {COL_SKU} {len(dupes)} 个，保留最后一行: {dupes[:5]}")
        df = df.drop_duplicates(subset=["_key"], keep="last")
    return df, source, dupes


def attach_names(df_rows, df_names):
    """按 Vendor Style 关联中文/西语名。返回 (df, 未匹配的 SKU 列表)。"""
    out = df_rows.copy()
    out["_key"] = out["Vendor Style"].astype(str).str.strip().str.upper()
    # Qty Ordered 读进来常带 NaN 而是 float，转 int 再转 str，否则背贴会印成 1.0
    out["_qty"] = out["Qty Ordered"].astype(float).astype(int).astype(str)
    out = out.merge(df_names[["_key", COL_CN, COL_ES]], on="_key", how="left")
    out[COL_CN] = out[COL_CN].fillna("")
    out[COL_ES] = out[COL_ES].fillna("")
    missing = sorted(out.loc[out[COL_CN].eq("") & out[COL_ES].eq(""), "Vendor Style"].unique())
    return out, missing


def _write_pdf(df, out_path, timestamp):
    pdfmetrics.registerFont(UnicodeCIDFont("STSong-Light"))
    c = canvas.Canvas(str(out_path), pagesize=(PAGE_W, PAGE_H))
    total = len(df)
    styles = getSampleStyleSheet()
    cell_style = ParagraphStyle(
        name="PBCell", parent=styles["BodyText"], fontSize=10, leading=LEADING
    )
    table_style = TableStyle([
        ("BACKGROUND", (0, 0), (-1, 0), colors.grey),
        ("TEXTCOLOR", (0, 0), (-1, 0), colors.whitesmoke),
        ("FONTNAME", (0, 0), (-1, 0), "Helvetica"),
        ("FONTSIZE", (0, 0), (-1, 0), 8),
        ("FONTSIZE", (0, 1), (-1, -1), 10),
        ("ALIGN", (0, 0), (-1, -1), "LEFT"),
        ("BACKGROUND", (0, 1), (-1, -1), colors.white),
        ("GRID", (0, 0), (-1, -1), 1, colors.black),
        ("VALIGN", (0, 0), (-1, -1), "MIDDLE"),
    ])

    for idx, (_, row) in enumerate(df.iterrows(), 1):
        y = PAGE_H - MARGIN_TOP
        pack_id = f"{row['PO Number']}-{row['Line #']}"
        c.setFont("Helvetica", 8)
        c.drawString(MARGIN_L, y, f"PO: {pack_id}")
        y -= LEADING
        code128.Code128(pack_id, barHeight=8, fontSize=6, barWidth=0.65).drawOn(
            c, MARGIN_L + 100, y + 5
        )
        y -= 5

        data = [[
            "#", "SKU", "QTY", "Name Chinese", "Nombres en español",
        ], [
            "1",
            Paragraph(str(row["Vendor Style"]), cell_style),
            str(row["_qty"]),
            Paragraph(build_mixed_xml(str(row[COL_CN])), cell_style),
            Paragraph(build_mixed_xml(str(row[COL_ES])), cell_style),
        ]]
        table = Table(data, colWidths=COL_WIDTHS)
        table.setStyle(table_style)
        table.wrapOn(c, PAGE_W - MARGIN_L - MARGIN_R, y)
        table.drawOn(c, MARGIN_L - 3, y - table._height)

        c.setFont("STSong-Light", 5)
        c.drawRightString(PAGE_W - MARGIN_R - 10, PAGE_H - MARGIN_TOP + 3, timestamp)
        c.drawRightString(PAGE_W - MARGIN_R - 10, PAGE_H - MARGIN_TOP - 3, f"{idx} / {total}")
        c.showPage()

    c.save()
    return Path(out_path)


def build_back_label_pdf(df_rows, out_dir, ts_mmdd=None, cache_path=CACHE_CSV,
                         use_cache_only=False):
    """产出背贴 PDF，返回 (路径, 页数, 未匹配 SKU 列表)。"""
    ts_mmdd = ts_mmdd or datetime.now().strftime("%m.%d")
    df_names, source, _ = prepare_name_table(df_rows, cache_path, use_cache_only)
    df, missing = attach_names(df_rows, df_names)
    if missing:
        print(f"警告：{len(missing)} 个 SKU 在名称表里没有中/西语名，背贴对应格留空: {missing[:8]}")

    out_dir = Path(out_dir)
    out_dir.mkdir(parents=True, exist_ok=True)
    out_path = out_dir / BACK_LABEL_PDF_NAME.format(mmdd=ts_mmdd)
    _write_pdf(df, out_path, ts_mmdd)
    print(f"名称来源: {source}")
    return out_path, len(df), missing


def main():
    ap = argparse.ArgumentParser(description="步骤 4.2：生成 PB 背贴 PDF")
    ap.add_argument("rows_table", help="PDF⋈订单 的 xlsx/csv（含 PO Number/Line #/Vendor Style/Qty Ordered）")
    ap.add_argument("--out", default=None, help="输出目录，默认与输入同目录")
    ap.add_argument("--cache-only", action="store_true", help="只用本地缓存，不联网")
    args = ap.parse_args()

    src = Path(args.rows_table).resolve()
    if not src.is_file():
        sys.exit(f"文件不存在: {src}")
    df = pd.read_excel(src) if src.suffix.lower() in (".xlsx", ".xls") else pd.read_csv(src)
    out = Path(args.out).resolve() if args.out else src.parent

    path, pages, missing = build_back_label_pdf(df, out, use_cache_only=args.cache_only)
    print(f"背贴页数: {pages} | 未匹配名称 SKU: {len(missing)}")
    print(f"已生成: {path}")


if __name__ == "__main__":
    main()
