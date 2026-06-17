"""
_shared.py — PDF→MD 共享工具（引擎无关）

版面分析 / 代码块修复 / 后处理 / pipeline。
所有函数不依赖任何 OCR 引擎。
"""
import sys
import re
from collections import Counter
from pathlib import Path

sys.stdout.reconfigure(encoding="utf-8")

# ---------------------------------------------------------------------------
# pymupdf 依赖检查
# ---------------------------------------------------------------------------
try:
    import fitz
except ImportError:
    print("缺少依赖：pymupdf (fitz)")
    print("请运行: uv pip install pymupdf")
    sys.exit(1)

# ---------------------------------------------------------------------------
# 版面分析 — 表格 / 列表 / 段落重建
# ---------------------------------------------------------------------------

_Y_TOLERANCE = 15

_SPLIT_WORD_PATTERN = re.compile(r"^[a-z]{2,8}$", re.IGNORECASE)
_PAGE_NUM_PATTERN = re.compile(r"^\d{1,3}$")


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
# 后处理 — 表格列合并 / 页码清理
# ---------------------------------------------------------------------------

def _looks_split(a: str, b: str) -> bool:
    """判断两个单元格是否像是被 OCR 拆开的单词片段。"""
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
    cleaned = []
    i = 0
    while i < len(lines):
        stripped = lines[i].strip()
        if _PAGE_NUM_PATTERN.match(stripped):
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
    if text.strip().startswith("|"):
        text = _merge_table_columns(text)
    return text


# ---------------------------------------------------------------------------
# 文本层 MD 格式修复 — 标题 / 列表 / 代码块
# ---------------------------------------------------------------------------

def _detect_heading(line: str):
    """检测文本行是否为标题。返回带 Markdown 标记的行，或 None。"""
    s = line.strip()
    if not s:
        return None
    if re.match(r"^#{1,6}\s", s):
        return s
    # 中文序号标题
    if re.match(r"^[一二三四五六七八九十]+[、]", s):
        return f"## {s}"
    # STEP 标题
    if re.match(r"^STEP\s+\d+", s, re.IGNORECASE):
        return f"### {s}"
    # emoji 标记行
    if re.match(r"^[✅🔧⛔📌⭐💡]", s):
        return f"#### {s}"
    # 副标题
    if s.startswith("——") or s.startswith("--"):
        return f"## {s}"
    return None


def _format_text_line(line: str) -> str:
    """将单行格式化为 MD 列表/段落。"""
    s = line.strip()
    if not s:
        return ""
    if s.startswith("•") or s.startswith("·"):
        return f"- {s.lstrip('•· ')}"
    return s


def _format_text_layer(text: str) -> str:
    """对文本层页面做 MD 格式修复：标题检测、列表、数字行过滤。"""
    raw_lines = text.split("\n")

    lines = []
    for line in raw_lines:
        stripped = line.strip()
        if stripped.isdigit():  # 过滤页码/行号
            continue
        heading = _detect_heading(line)
        if heading:
            lines.append(heading)
        else:
            lines.append(_format_text_line(line))

    # 文档标题检测：非标题行 后紧跟 —— → 升级为 H1
    result = []
    i = 0
    while i < len(lines):
        cur = lines[i]
        if (not re.match(r"^#{1,6}\s", cur)
                and i + 1 < len(lines)
                and re.match(r"^##\s+——", lines[i + 1])):
            result.append(f"# {cur.strip()}")
        else:
            result.append(cur)
        i += 1

    return "\n".join(result)


# ---------------------------------------------------------------------------
# Pipeline
# ---------------------------------------------------------------------------

def has_text_layer(page) -> bool:
    """判断页面是否有可提取的文本。"""
    text = page.get_text().strip()
    return len(text) > 50


def convert(pdf_path: str, ocr_page_fn, *, lang: str = "ch_sim,en",
            ocr_only: bool = False, dpi: int = 300, engine_label: str = "OCR"):
    """通用 PDF→MD pipeline。

    ocr_page_fn(page, dpi) → str  — OCR 单页的函数。
    """
    pdf = Path(pdf_path).resolve()
    if not pdf.exists():
        print(f"错误: 文件不存在 — {pdf}")
        sys.exit(1)

    out_dir = Path(__file__).parent / "out"
    out_dir.mkdir(parents=True, exist_ok=True)
    md_path = out_dir / f"{pdf.stem}.md"
    doc = fitz.open(str(pdf))
    total = doc.page_count
    print(f"[PDF] {pdf.name} ({total} 页)")

    md_lines = []

    # Phase 1: 提取所有页面原始文本，标记类型
    page_meta = []
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

    # Phase 3: 输出页面（MD 不分页，不输出页标记）
    text_idx = 0
    for i, (is_text, _) in enumerate(page_meta):
        page_num = i + 1

        if is_text:
            if text_idx < len(fixed_pages):
                raw = _clean_page_numbers(fixed_pages[text_idx].strip())
                md_lines.append(_format_text_layer(raw))
            text_idx += 1
        else:
            print(f"  [{engine_label}] 第 {page_num} 页 → 截图识别")
            text = ocr_page_fn(doc[i], dpi=dpi)
            md_lines.append(text)

    doc.close()

    content = "\n".join(md_lines)
    md_path.write_text(content, encoding="utf-8")
    print(f"[完成] → {md_path} ({md_path.stat().st_size:,} bytes)")
