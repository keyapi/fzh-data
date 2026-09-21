#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""步骤 4：给 SPS 合并 PDF 叠加 SKUxQTY，再一页裁成两页（打包单 + UPS 标签）。

流程（照搬 Colab notebook cell 24 + cell 27）：
1. 生成叠加页 SKUxQTY_only.pdf：A4 竖版，每页把该页的 SKUxQTY 文字转 90° 画两次
   （上半页标注 + 下半页标注），另加裁切箭头 '---→' / '←---'、剪刀 '✂' 与时间戳
2. 逐页把叠加页 merge_page 到原 PDF 上 -> packlist_SKUxQTY.pdf
3. 每页复制两份并裁切/旋转：
   ① 上半页（10,435)-(590,830)  -> 打包单，rotate(90) 后按 0.732 缩放
   ② 下半页（98,77)-(530,367)   -> UPS 标签，rotate(90)
   50 页输入 -> 100 页输出，顺序为 单_0, 标签_0, 单_1, 标签_1 ...

坐标沿用 pypdf/PyPDF2 的左下角原点，**不要**换成 PyMuPDF（原点左上），否则打印件会错位。
缩放等价于 notebook 的 `page.scale_by(0.732)`，但改成了自己缩放各 box + 内容前置 cm 矩阵
（原因见 `_prepend_scale_matrix` 注释）。

用法：
    uv run python pb_label_pdf.py "Packslip 美中 x50 20260921.pdf" skus.csv
"""

import argparse

import sys
import tempfile
from copy import copy
from datetime import datetime
from pathlib import Path

from pypdf import PdfReader, PdfWriter
from pypdf.generic import DecodedStreamObject, NameObject, RectangleObject
from reportlab.lib.pagesizes import A4
from reportlab.lib.units import mm
from reportlab.pdfgen import canvas

# 叠加页版式 —— 与 notebook cell 24 的变量一一对应，避免翻译时出错。
# ⚠️ reportlab 的单位是 point：`36 * mm` 已经算成 point，所以 notebook 里
# `x5 + 30`、`y5 + 140` 加的是 **30/140 point**，不是 30/140 mm。
# （曾把 TS_1 写成 (66mm, 215mm)，把时间戳画到了打包单区域，标签页反而没有时间戳。）
FONT_SIZE = 14
OVERLAY_FONT = "Helvetica-Bold"
X1, Y1 = 205 * mm, 190 * mm   # SKUxQTY 标注 1
X2, Y2 = 170 * mm, 50 * mm    # SKUxQTY 标注 2
X3, Y3 = 195 * mm, 165 * mm   # 箭头 '---→'
X4, Y4 = X3, 280 * mm         # 箭头 '---→'
X5, Y5 = 36 * mm, 75 * mm     # 箭头 '←---'
X6, Y6 = 20, 815              # 剪刀 '✂' + 时间戳（point）
X7, Y7 = 20, 440              # 剪刀 '✂'（point）
TS_1 = (X5 + 30, Y5 + 140)    # 落在**标签**页
TS_2 = (X6 + 400, Y6)         # 落在**打包单**页

# 裁切框（pypdf 左下角原点）
SLIP_LL, SLIP_UR = (10, 435), (590, 830)
LABEL_LL, LABEL_UR = (98, 77), (530, 367)
LABEL_CROP_LL, LABEL_CROP_UR = (97, 76), (529, 366)
SLIP_SCALE = 0.732

LABEL_PDF_NAME = "{mmdd} PotteryBarn label-FZH-DANEEY-Not Prime-第一天.pdf"
NO_STOCK_LABEL_PDF_NAME = "无货{note}-{mmdd} PotteryBarn label-FZH-DANEEY-Not Prime-第一天.pdf"


def _ts(fmt="%Y-%m-%d %H:%M:%S"):
    return datetime.now().strftime(fmt)


def make_sku_overlay_pdf(skus, out_path, timestamp, font_size=FONT_SIZE):
    """生成 SKUxQTY 叠加页（每行一页，A4 竖版，文字转 90°）。"""
    pdf = canvas.Canvas(str(out_path), pagesize=A4)
    pdf.setFont(OVERLAY_FONT, font_size)
    for sku in skus:
        pdf.drawString(X3, Y3, "---→")
        pdf.drawString(X4, Y4, "---→")
        pdf.drawString(X5, Y5, "←---")
        pdf.drawString(*TS_1, timestamp)
        pdf.drawString(*TS_2, timestamp)

        pdf.rotate(90)
        pdf.drawString(Y1, -X1, sku)
        pdf.drawString(Y2, -X2, sku)
        pdf.drawString(Y6, -X6, "✂")
        pdf.drawString(Y7, -X7, "✂")
        pdf.rotate(-90)

        pdf.showPage()
    pdf.save()
    return Path(out_path)


def merge_overlay(base_path, overlay_path, out_path):
    """逐页把叠加页合并到原 PDF。页数必须一致。"""
    base, overlay = PdfReader(str(base_path)), PdfReader(str(overlay_path))
    if len(base.pages) != len(overlay.pages):
        raise ValueError(
            f"合并失败：原 PDF {len(base.pages)} 页 != 叠加页 {len(overlay.pages)} 页"
        )
    _assert_no_shared_contents(base)
    writer = PdfWriter()
    for i, page in enumerate(base.pages):
        page.merge_page(overlay.pages[i])
        writer.add_page(page)
    with open(out_path, "wb") as fh:
        writer.write(fh)
    return Path(out_path)


def _assert_no_shared_contents(reader):
    """merge_page 是就地改写页的 /Contents，多页共用同一个 /Contents 时会被叠加多次。

    正常 SPS 导出每页独立；真遇到共用就直接报错，避免静默产出错件。
    """
    seen = {}
    for idx, page in enumerate(reader.pages):
        contents = page.get("/Contents")
        key = getattr(contents, "idnum", None) or id(contents)
        if key in seen:
            raise ValueError(
                f"第 {seen[key]} 页与第 {idx} 页共用 /Contents，无法逐页叠加，请先拆分该 PDF"
            )
        seen[key] = idx


def _set_boxes(page, ll, ur, crop_ll=None, crop_ur=None):
    for box, lo, hi in (
        (page.mediabox, ll, ur),
        (page.trimbox, ll, ur),
        (page.cropbox, crop_ll or ll, crop_ur or ur),
    ):
        box.lower_left = lo
        box.upper_right = hi


_PAGE_BOX_KEYS = ("/MediaBox", "/CropBox", "/TrimBox", "/ArtBox", "/BleedBox")


def _scale_boxes_about_origin(page, factor):
    """等价于 pypdf `scale_by` 的 box 部分：各 box 坐标乘 factor（关于原点缩放）。"""
    for key in _PAGE_BOX_KEYS:
        box = page.get(key)
        if box is None:
            continue
        box = box.get_object() if hasattr(box, "get_object") else box
        page[NameObject(key)] = RectangleObject([float(v) * factor for v in box])


def _prepend_scale_matrix(page, writer, factor):
    """给页内容前置一条缩放矩阵 cm，等价于 `scale_by` 的内容部分。

    不用 `page.scale_by()` 是因为它内部走 `replace_contents` -> `_replace_object`，
    只能改**归属该 reader 的对象**；这里页已经交给 writer，会报
    `Cannot update PdfReader with external object`。
    """
    data = f"{factor} 0 0 {factor} 0 0 cm\n".encode("ascii") + page.get_contents().get_data()
    stream = DecodedStreamObject()
    stream.set_data(data)
    page[NameObject("/Contents")] = writer._add_object(stream)


def crop_split_pdf(src_path, out_path, scale=SLIP_SCALE):
    """每页裁成两页：上半页打包单（旋转+缩放），下半页 UPS 标签（旋转）。

    输出顺序为 单_0, 标签_0, 单_1, 标签_1 ...（与 notebook 一致）。

    实现要点：**同一个 PdfReader 只读一遍**，两份拷贝只改页字典与 /Contents，
    图片等资源仍指向同一批对象（一张图只存一份）。
    若改成「两趟处理各写一个中间 PDF」，同一张图会各存一份，成品体积翻倍
    （实测 130 -> 260 个图片对象、12.8MB -> 24MB，邮件发不出去）。
    """
    reader, writer = PdfReader(str(src_path)), PdfWriter()
    for page in reader.pages:
        slip = copy(page)
        _set_boxes(slip, SLIP_LL, SLIP_UR)
        slip.rotate(90)
        writer.add_page(slip)
        if scale:
            slipped = writer.pages[-1]
            _scale_boxes_about_origin(slipped, scale)
            _prepend_scale_matrix(slipped, writer, scale)

        label = copy(page)
        _set_boxes(label, LABEL_LL, LABEL_UR, LABEL_CROP_LL, LABEL_CROP_UR)
        label.rotate(90)
        writer.add_page(label)

    with open(out_path, "wb") as fh:
        writer.write(fh)
    return Path(out_path)


def extract_pages(src_path, page_indices, out_path):
    """把 src 的第 page_indices（0 基，按给定顺序）页抽成一个新 PDF。"""
    reader, writer = PdfReader(str(src_path)), PdfWriter()
    for idx in page_indices:
        writer.add_page(reader.pages[idx])
    with open(out_path, "wb") as fh:
        writer.write(fh)
    return Path(out_path)


def build_label_pdf(base_pdf, skus, out_dir, ts_full=None, ts_mmdd=None,
                    filename=None, page_indices=None):
    """产出标签 PDF，返回 (路径, 输出页数)。

    page_indices 给定时，先从原 PDF 抽出这些页（用于「无货子集」），
    此时 skus 必须与所选页数一一对应。
    """
    base_pdf, out_dir = Path(base_pdf), Path(out_dir)
    ts_full = ts_full or _ts("%Y-%m-%d %H:%M:%S")
    ts_mmdd = ts_mmdd or _ts("%m.%d")
    out_dir.mkdir(parents=True, exist_ok=True)
    if page_indices is not None and len(page_indices) != len(skus):
        raise ValueError(f"抽页数 {len(page_indices)} != SKU 数 {len(skus)}")

    with tempfile.TemporaryDirectory(prefix="pb_orders_") as tmp:
        src = base_pdf
        if page_indices is not None:
            src = extract_pages(base_pdf, page_indices, Path(tmp) / "subset.pdf")
        overlay = make_sku_overlay_pdf(skus, Path(tmp) / "SKUxQTY_only.pdf", ts_full)
        merged = merge_overlay(src, overlay, Path(tmp) / "packlist_SKUxQTY.pdf")
        out_path = out_dir / (filename or LABEL_PDF_NAME.format(mmdd=ts_mmdd))
        crop_split_pdf(merged, out_path)

    return out_path, len(PdfReader(str(out_path)).pages)


def _read_skus_csv(path):
    import csv

    with open(path, newline="", encoding="utf-8-sig") as fh:
        rows = list(csv.reader(fh))
    return [r[0] for r in rows if r and r[0].strip()]


def main():
    ap = argparse.ArgumentParser(description="步骤 4：叠加 SKUxQTY 并裁切拆分标签 PDF")
    ap.add_argument("pdf", help="Packslip 原 PDF")
    ap.add_argument("skus_csv", help="SKUxQTY 列表 CSV（每行一个）")
    ap.add_argument("--out", default=None, help="输出目录，默认与原 PDF 同目录")
    args = ap.parse_args()

    pdf = Path(args.pdf).resolve()
    if not pdf.is_file():
        sys.exit(f"文件不存在: {pdf}")
    skus = _read_skus_csv(args.skus_csv)
    out = Path(args.out).resolve() if args.out else pdf.parent

    pages_in = len(PdfReader(str(pdf)).pages)
    if pages_in != len(skus):
        sys.exit(f"PDF {pages_in} 页 != SKU {len(skus)} 个，拒绝生成（会错件）")

    out_path, pages_out = build_label_pdf(pdf, skus, out)
    print(f"输入 {pages_in} 页 -> 输出 {pages_out} 页")
    print(f"已生成: {out_path}")


if __name__ == "__main__":
    main()
