"""
pdf_to_md.py — PDF → Markdown 转换（含图片 OCR + 表格/列表重建）

将 PDF 文件转换为结构化的 Markdown 文档：
- 纯文本页 → 直接提取
- 图片/截图页 → OCR + 版面分析（表格/列表/段落）
- 输出文件与 PDF 同目录，文件名相同、扩展名为 .md

## 依赖

    pip install pymupdf easyocr pillow

## 用法

    python scripts/pdf_to_md.py <pdf_path> [--lang <lang>] [--ocr-only] [--dpi 300]

## 参数

    pdf_path   PDF 文件路径（含中文路径也可）
    --lang      OCR 语言，默认 "ch_sim,en"（中英文）
    --ocr-only  仅 OCR，跳过文本层的直接提取
    --dpi       OCR 渲染分辨率（默认 300，截图页建议 300+）
"""
import sys
import argparse
import re
from collections import Counter
from pathlib import Path

sys.stdout.reconfigure(encoding="utf-8")

# ---------------------------------------------------------------------------
# 可用性检查
# ---------------------------------------------------------------------------

_MISSING_DEPS = []
try:
    import fitz
except ImportError:
    _MISSING_DEPS.append("pymupdf (fitz)")
try:
    import easyocr
except ImportError:
    _MISSING_DEPS.append("easyocr")
try:
    from PIL import Image
except ImportError:
    _MISSING_DEPS.append("pillow")
try:
    import numpy as np
except ImportError:
    _MISSING_DEPS.append("numpy")

if _MISSING_DEPS:
    print("缺少依赖：" + ", ".join(_MISSING_DEPS))
    print("请运行: uv pip install pymupdf easyocr pillow numpy")
    sys.exit(1)

import fitz
import easyocr
from PIL import Image
import numpy as np


# ---------------------------------------------------------------------------
# OCR 引擎（延迟初始化）
# ---------------------------------------------------------------------------

_reader = None


def _get_reader(lang: str):
    global _reader
    if _reader is None:
        print(f"[OCR] 初始化 easyocr（语言: {lang}）...")
        _reader = easyocr.Reader(lang.split(","), gpu=False)
    return _reader


# ---------------------------------------------------------------------------
# 版面分析 — 表格 / 列表 / 段落重建
# ---------------------------------------------------------------------------

_Y_TOLERANCE = 15  # 同一行 Y 坐标容差（像素）


def _group_rows(results, y_tol=_Y_TOLERANCE):
    """将 OCR 结果按 Y 坐标分组为行，行内按 X 排序。"""
    rows = []
    for bbox, text, _conf in results:
        y_c = (bbox[0][1] + bbox[2][1]) / 2
        x_c = bbox[0][0]
        matched = False
        for row in rows:
            if abs(row["y"] - y_c) < y_tol:
                row["cells"].append((x_c, text))
                row["y"] = (row["y"] + y_c) / 2
                matched = True
                break
        if not matched:
            rows.append({"y": y_c, "cells": [(x_c, text)]})
    rows.sort(key=lambda r: r["y"])
    for r in rows:
        r["cells"].sort(key=lambda c: c[0])
    return rows


def _is_table(rows):
    """判断是否为表格：要求列数相对一致，且多列行占比高。"""
    if len(rows) < 3:
        return False
    col_counts = [len(r["cells"]) for r in rows]
    # 至少 40% 的行有 2 列以上
    multi = sum(1 for c in col_counts if c >= 2)
    if multi < len(rows) * 0.4:
        return False
    # 主要列数（众数）
    from collections import Counter
    main_cols = Counter(col_counts).most_common(1)[0][0]
    # 超过 50% 的行与主要列数一致
    consistent = sum(1 for c in col_counts if abs(c - main_cols) <= 1)
    return consistent >= len(rows) * 0.5


def _format_table(rows):
    """将分组行输出为 Markdown 表格。"""
    ncols = max(len(r["cells"]) for r in rows)
    if ncols < 2:
        return "\n".join(r["cells"][0][1] for r in rows)

    lines = []
    # 表头（第一行）
    first = rows[0]
    h_cells = []
    for c in range(ncols):
        h_cells.append(first["cells"][c][1] if c < len(first["cells"]) else "")
    lines.append(f"| {' | '.join(h_cells)} |")
    lines.append(f"|{'|'.join('---' for _ in range(ncols))}|")
    # 数据行
    for row in rows[1:]:
        cells = [row["cells"][c][1] if c < len(row["cells"]) else "" for c in range(ncols)]
        lines.append(f"| {' | '.join(cells)} |")
    return "\n".join(lines)


def _format_list(texts):
    """将文本行按列表检测并格式化。"""
    lines = []
    for t in texts:
        stripped = t.strip()
        # bullet / 编号
        if stripped.startswith(("•", "-", "*", "·", "▪", "►", "→")):
            lines.append(f"- {stripped.lstrip('•-*·▪►→ ')}")
        elif re.match(r"^\d+[\.\)、]", stripped):
            lines.append(f"- {stripped}")
        elif re.match(r"^[A-Z][a-z]", stripped) and len(stripped) < 40:
            lines.append(f"- {stripped}")
        elif re.match(r"^\[.+\]", stripped):
            lines.append(f"### {stripped}")
        elif re.match(r"^[一二三四五六七八九十]+[、.]", stripped):
            lines.append(f"### {stripped}")
        else:
            lines.append(stripped)
    return "\n".join(lines)


def _format_paragraphs(rows):
    """将分组行输出为段落文本（单列布局），检测列表和结构化内容。"""
    texts = [r["cells"][0][1] for r in rows]
    # 尝试检测列表（bullet / 编号 / 中文字题 / [xxx] 标签）
    patterns = [
        lambda t: t.strip().startswith(("•", "-", "*", "·", "▪", "►", "→")),
        lambda t: bool(re.match(r"^\d+[\.\)、]", t.strip())),
        lambda t: bool(re.match(r"^\[.+\]", t.strip())),
        lambda t: bool(re.match(r"^[一二三四五六七八九十]+[、.]", t.strip())),
    ]
    bullet_like = sum(
        1 for t in texts if any(p(t) for p in patterns)
    )
    if bullet_like >= len(texts) * 0.25 and len(texts) >= 3:
        return _format_list(texts)
    return "\n".join(texts)


# ---------------------------------------------------------------------------
# 核心逻辑
# ---------------------------------------------------------------------------


def has_text_layer(page) -> bool:
    """判断页面是否有可提取的文本。"""
    text = page.get_text().strip()
    return len(text) > 50


def extract_text_page(page) -> str:
    """从文本层提取页面内容。"""
    return page.get_text()


def ocr_page(page, reader, dpi=300) -> str:
    """OCR 页面 → 版面分析 → Markdown。"""
    pix = page.get_pixmap(dpi=dpi)
    img = Image.frombytes("RGB", [pix.width, pix.height], pix.samples)
    img_array = np.array(img)

    # paragraph=False 获得 bbox 坐标（用于版面分析）
    results = reader.readtext(img_array, detail=1, paragraph=False)

    if not results:
        return ""

    rows = _group_rows(results)

    if _is_table(rows):
        return _format_table(rows)
    else:
        return _format_paragraphs(rows)


def convert(pdf_path: str, lang: str = "ch_sim,en", ocr_only: bool = False, dpi: int = 300):
    """将 PDF 转换为 Markdown。"""
    pdf = Path(pdf_path).resolve()
    if not pdf.exists():
        print(f"错误: 文件不存在 — {pdf}")
        sys.exit(1)

    md_path = pdf.with_suffix(".md")
    reader = _get_reader(lang) if not ocr_only else None

    doc = fitz.open(str(pdf))
    total = doc.page_count
    print(f"[PDF] {pdf.name} ({total} 页)")

    md_lines = []

    for i, page in enumerate(doc):
        page_num = i + 1
        md_lines.append(f"\n---\n**第 {page_num} 页**\n---\n")

        if ocr_only:
            text = ocr_page(page, reader, dpi=dpi)
        else:
            if has_text_layer(page):
                text = extract_text_page(page)
            else:
                print(f"  [OCR] 第 {page_num} 页 → 截图识别")
                text = ocr_page(page, reader, dpi=dpi)

        md_lines.append(text)

    doc.close()

    content = "\n".join(md_lines)
    md_path.write_text(content, encoding="utf-8")
    print(f"[完成] → {md_path} ({md_path.stat().st_size:,} bytes)")


# ---------------------------------------------------------------------------
# CLI
# ---------------------------------------------------------------------------

def main():
    parser = argparse.ArgumentParser(description="PDF → Markdown（含 OCR + 版面分析）")
    parser.add_argument("pdf_path", help="PDF 文件路径")
    parser.add_argument("--lang", default="ch_sim,en", help="OCR 语言（默认: ch_sim,en）")
    parser.add_argument("--ocr-only", action="store_true", help="强制所有页均使用 OCR")
    parser.add_argument("--dpi", type=int, default=300, help="OCR 渲染分辨率（默认 300）")
    args = parser.parse_args()

    convert(args.pdf_path, lang=args.lang, ocr_only=args.ocr_only, dpi=args.dpi)


if __name__ == "__main__":
    main()
