"""
pdf_to_md.py — PDF → Markdown 转换（含图片 OCR + 版面分析 + 代码块检测）

将 PDF 文件转换为结构化的 Markdown 文档：
- 纯文本页 → 直接提取 + 代码块/列表格式修复
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
    --dpi       OCR 渲染分辨率（默认 300）
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
    from PIL import Image, ImageEnhance
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
from PIL import Image, ImageEnhance, ImageOps, ImageFilter
import numpy as np

# PaddleOCR（可选，通过 ONNX Runtime 运行）
_has_paddleocr = False
try:
    from paddleocr import PaddleOCR as _PaddleOCR
    _has_paddleocr = True
except ImportError:
    pass


# ---------------------------------------------------------------------------
# OCR 引擎（延迟初始化）
# ---------------------------------------------------------------------------

_reader = None        # easyocr
_paddle_reader = None  # paddleocr + onnxruntime


def _get_reader(lang: str):
    global _reader
    if _reader is None:
        print(f"[OCR] 初始化 easyocr（语言: {lang}）...")
        _reader = easyocr.Reader(lang.split(","), gpu=False)
    return _reader


def _get_paddle_reader(lang: str = "ch"):
    global _paddle_reader
    if _paddle_reader is None:
        lang_map = {"ch_sim,en": "ch", "ch_sim": "ch", "en": "en"}
        plang = lang_map.get(lang, "ch")
        print(f"[OCR] 初始化 PaddleOCR ONNX（语言: {plang}）...")
        _paddle_reader = _PaddleOCR(engine="onnxruntime", lang=plang)
    return _paddle_reader


# ---------------------------------------------------------------------------
# 版面分析 — 表格 / 列表 / 段落重建
# ---------------------------------------------------------------------------

_Y_TOLERANCE = 15


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
    """判断是否为表格：列数相对一致，多列行占比高。"""
    if len(rows) < 3:
        return False
    col_counts = [len(r["cells"]) for r in rows]
    multi = sum(1 for c in col_counts if c >= 2)
    if multi < len(rows) * 0.4:
        return False
    main_cols = Counter(col_counts).most_common(1)[0][0]
    consistent = sum(1 for c in col_counts if abs(c - main_cols) <= 1)
    return consistent >= len(rows) * 0.5


def _format_table(rows):
    """将分组行输出为 Markdown 表格。"""
    ncols = max(len(r["cells"]) for r in rows)
    if ncols < 2:
        return "\n".join(r["cells"][0][1] for r in rows)

    lines = []
    first = rows[0]
    h_cells = [first["cells"][c][1] if c < len(first["cells"]) else "" for c in range(ncols)]
    # 跳过仅含单一空值的表头列
    clean_header = [h if h.strip() else " " for h in h_cells]
    lines.append(f"| {' | '.join(clean_header)} |")
    lines.append(f"|{'|'.join('---' for _ in range(ncols))}|")
    for row in rows[1:]:
        cells = [row["cells"][c][1] if c < len(row["cells"]) else "" for c in range(ncols)]
        lines.append(f"| {' | '.join(cells)} |")
    return "\n".join(lines)


def _build_paragraph_text(rows):
    """将非表格页面分组行重组为连续段落文本（合并相邻短行）。"""
    texts = [r["cells"][0][1] for r in rows]
    if not texts:
        return ""

    merged = []
    buffer = ""
    for t in texts:
        stripped = t.strip()
        if not stripped:
            if buffer:
                merged.append(buffer)
                buffer = ""
            merged.append("")
            continue
        # 如果 buffer 已存在且当前行像是一个新段落（开头大写/数字/符号），先 flush
        if buffer and (
            re.match(r"^[一二三四五六七八九十]+[、.]", stripped)
            or re.match(r"^[A-Z][a-z]{2,}", stripped)
            or re.match(r"^[\[【].+[\]】]", stripped)
            or stripped.startswith(("•", "-", "*", "·", "▪", "►", "→", "✅", "🔧", "⛔"))
            or re.match(r"^\d+[\.\)、]", stripped)
        ):
            merged.append(buffer)
            buffer = stripped
        elif buffer:
            # 尝试判断是否是上一行的续文（上一行不以标点结尾，或当前行以小写开头）
            if buffer[-1] not in "。，.；;：:！!？?、—-" and not stripped[0].isupper():
                buffer += stripped
            else:
                buffer += " " + stripped
        else:
            buffer = stripped
    if buffer:
        merged.append(buffer)

    return "\n".join(merged)


# ---------------------------------------------------------------------------
# 代码块 / 列表格式修复（文本层后处理）
# ---------------------------------------------------------------------------

def _fix_code_blocks(text: str, carry_in_code: bool = False):
    """检测文本层中的「代码块」标记并套上 ``` 围栏。
    返回 (fixed_text, in_code_at_end) 以支持跨页代码块追踪。"""
    # 清理零宽字符
    text = text.replace("​", "").replace("﻿", "")
    lines = text.split("\n")
    result = []
    in_code = carry_in_code
    code_buf = []
    code_end_markers = re.compile(
        r"^(STEP\s*\d|[一二三四五六七八九十]+[、.]|✅)"
    )

    for line in lines:
        stripped = line.strip()
        if stripped == "代码块" or stripped == "```":
            if in_code and code_buf:
                result.append("```")
                result.extend(code_buf)
                result.append("```")
                code_buf = []
                in_code = False
            else:
                in_code = True
                code_buf = []
            continue

        if in_code:
            if stripped and code_end_markers.match(stripped):
                if code_buf:
                    result.append("```")
                    result.extend(code_buf)
                    result.append("```")
                    code_buf = []
                    in_code = False
                result.append(line)
            else:
                code_buf.append(line)
        else:
            result.append(line)

    return "\n".join(result), in_code


# ---------------------------------------------------------------------------
# 后处理 — 表格列合并 / 页码清理 / 文本修复
# ---------------------------------------------------------------------------

_SPLIT_WORD_PATTERN = re.compile(r"^[a-z]{2,8}$", re.IGNORECASE)
_PAGE_NUM_PATTERN = re.compile(r"^\d{1,3}$")


def _looks_split(a: str, b: str) -> bool:
    """判断两个单元格是否像是被 OCR 拆开的单词片段。"""
    # 都是纯英文，且合并后长度合理
    if not (_SPLIT_WORD_PATTERN.match(a) and _SPLIT_WORD_PATTERN.match(b)):
        return False
    combined = a + b
    return 4 <= len(combined) <= 20


def _merge_table_columns(md_table: str) -> str:
    """检测并合并表格中被 OCR 拆分的单词列（如 foldng | char → folding char）。"""
    lines = md_table.split("\n")
    result = []
    for line in lines:
        if not line.startswith("|"):
            result.append(line)
            continue
        # 解析单元格
        raw = line.strip().strip("|")
        cells = [c.strip() for c in raw.split("|")]
        if len(cells) < 2:
            result.append(line)
            continue

        merged = []
        i = 0
        while i < len(cells):
            if i + 1 < len(cells) and _looks_split(cells[i], cells[i + 1]):
                merged.append(f"{cells[i]} {cells[i + 1]}")
                i += 2
            else:
                merged.append(cells[i])
                i += 1
        result.append("| " + " | ".join(merged) + " |")
    return "\n".join(result)


def _clean_page_numbers(text: str) -> str:
    """移除文本中的页码脚注数字（单独成行的 1-3 位数字）。"""
    lines = text.split("\n")
    # 收集连续数字行的范围
    cleaned = []
    i = 0
    while i < len(lines):
        stripped = lines[i].strip()
        if _PAGE_NUM_PATTERN.match(stripped):
            # 检查上下文是否也是数字行（连续页码）
            prev_is_num = i > 0 and _PAGE_NUM_PATTERN.match(lines[i-1].strip())
            next_is_num = i + 1 < len(lines) and _PAGE_NUM_PATTERN.match(lines[i+1].strip())
            if prev_is_num or next_is_num:
                i += 1
                continue
        cleaned.append(lines[i])
        i += 1
    return "\n".join(cleaned)


def _postprocess_ocr_text(text: str) -> str:
    """OCR 后处理流水线。"""
    text = _clean_page_numbers(text)
    # 表格页做列合并
    if text.strip().startswith("|"):
        text = _merge_table_columns(text)
    return text


def has_text_layer(page) -> bool:
    """判断页面是否有可提取的文本。"""
    text = page.get_text().strip()
    return len(text) > 50


def ocr_page_easyocr(page, reader, dpi=300) -> str:
    """easyocr → 版面分析 → Markdown。"""
    pix = page.get_pixmap(dpi=dpi)
    img = Image.frombytes("RGB", [pix.width, pix.height], pix.samples)

    # 预处理：灰度 + 对比度增强（保守）
    img_gray = img.convert("L")
    enhancer = ImageEnhance.Contrast(img_gray)
    img_enhanced = enhancer.enhance(2.0)
    img_array = np.array(img_enhanced)

    results = reader.readtext(img_array, detail=1, paragraph=False,
                              text_threshold=0.4, low_text=0.2)

    if not results:
        return ""

    rows = _group_rows(results)

    if _is_table(rows):
        output = _format_table(rows)
    else:
        output = _build_paragraph_text(rows)

    return _postprocess_ocr_text(output)


def ocr_page_paddleocr(page, reader, dpi=300) -> str:
    """PaddleOCR (ONNX Runtime) → 版面分析 → Markdown。"""
    pix = page.get_pixmap(dpi=dpi)
    img = Image.frombytes("RGB", [pix.width, pix.height], pix.samples)
    img_array = np.array(img)

    raw = list(reader.predict(img_array))
    if not raw:
        return ""

    # PaddleOCR 3.7 output: OCRResult dict with rec_texts, rec_scores, rec_polys
    ocr_result = raw[0]
    texts = ocr_result.get("rec_texts", []) or []
    scores = ocr_result.get("rec_scores", []) or []
    bboxes = ocr_result.get("rec_polys", []) or []

    if not texts:
        return ""

    # 转换为 easyocr 兼容的 (bbox, text, conf) 格式
    results = []
    for i, text in enumerate(texts):
        poly = bboxes[i] if i < len(bboxes) else [[0, 0], [0, 0], [0, 0], [0, 0]]
        # poly 是 numpy array → 转为 list of lists
        if hasattr(poly, "tolist"):
            poly = poly.tolist()
        score = float(scores[i]) if i < len(scores) else 0.5
        results.append((poly, text, score))

    rows = _group_rows(results, y_tol=30)  # PaddleOCR 词级检测需更大容差

    if _is_table(rows):
        output = _format_table(rows)
    else:
        output = _build_paragraph_text(rows)

    return _postprocess_ocr_text(output)


def ocr_page(page, reader, engine="easyocr", dpi=300) -> str:
    """OCR 页面 → 版面分析 → Markdown（调度 easyocr / paddleocr）。"""
    if engine == "paddleocr":
        return ocr_page_paddleocr(page, reader, dpi=dpi)
    return ocr_page_easyocr(page, reader, dpi=dpi)


def convert(pdf_path: str, lang: str = "ch_sim,en", ocr_only: bool = False,
            dpi: int = 300, engine: str = "easyocr"):
    """将 PDF 转换为 Markdown。"""
    pdf = Path(pdf_path).resolve()
    if not pdf.exists():
        print(f"错误: 文件不存在 — {pdf}")
        sys.exit(1)

    md_path = pdf.with_suffix(".md")
    if engine == "paddleocr":
        if not _has_paddleocr:
            print("错误: PaddleOCR 未安装，请运行: uv pip install paddleocr onnxruntime")
            sys.exit(1)
        reader = _get_paddle_reader(lang)
    elif not ocr_only:
        reader = _get_reader(lang)
    else:
        reader = None

    doc = fitz.open(str(pdf))
    total = doc.page_count
    print(f"[PDF] {pdf.name} ({total} 页)")

    md_lines = []

    # Phase 1: 提取所有页面原始文本，标记类型
    page_meta = []  # (is_text_layer, raw_text_or_None)
    for page in doc:
        if ocr_only:
            page_meta.append((False, None))
        elif has_text_layer(page):
            page_meta.append((True, page.get_text()))
        else:
            page_meta.append((False, None))

    # Phase 2: 合并所有文本层页面，统一处理代码块跨页
    PAGE_MARKER = "\n<!--PB-->\n"
    combined_text = PAGE_MARKER.join(
        t for is_text, t in page_meta if is_text
    )
    fixed_combined, _ = _fix_code_blocks(combined_text)
    fixed_pages = fixed_combined.split(PAGE_MARKER) if fixed_combined.strip() else []

    # Phase 3: 输出页面
    text_idx = 0
    for i, (is_text, _) in enumerate(page_meta):
        page_num = i + 1
        # MD 文件不分页，不输出页标记

        if is_text:
            if text_idx < len(fixed_pages):
                md_lines.append(_clean_page_numbers(fixed_pages[text_idx].strip()))
            text_idx += 1
        else:
            print(f"  [OCR] 第 {page_num} 页 → 截图识别 ({engine})")
            text = ocr_page(doc[i], reader, engine=engine, dpi=dpi)
            md_lines.append(text)

    doc.close()

    content = "\n".join(md_lines)
    md_path.write_text(content, encoding="utf-8")
    print(f"[完成] → {md_path} ({md_path.stat().st_size:,} bytes)")


# ---------------------------------------------------------------------------
# CLI
# ---------------------------------------------------------------------------

def main():
    parser = argparse.ArgumentParser(description="PDF → Markdown（含 OCR + 版面分析 + 代码块检测）")
    parser.add_argument("pdf_path", help="PDF 文件路径")
    parser.add_argument("--lang", default="ch_sim,en", help="OCR 语言（默认: ch_sim,en）")
    parser.add_argument("--ocr-only", action="store_true", help="强制所有页均使用 OCR")
    parser.add_argument("--dpi", type=int, default=300, help="OCR 渲染分辨率（默认 300）")
    parser.add_argument("--engine", default="paddleocr" if _has_paddleocr else "easyocr",
                        choices=["easyocr", "paddleocr"],
                        help="OCR 引擎（默认: paddleocr）")
    args = parser.parse_args()

    convert(args.pdf_path, lang=args.lang, ocr_only=args.ocr_only, dpi=args.dpi,
            engine=args.engine)


if __name__ == "__main__":
    main()
