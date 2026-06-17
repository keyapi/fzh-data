"""
pdf_to_md.py — PDF → Markdown 转换（含图片 OCR）

将 PDF 文件转换为结构化的 Markdown 文档：
- 纯文本页 → 直接提取
- 图片/截图页 → OCR 识别为文字（含表格数据）
- 输出文件与 PDF 同目录，文件名相同、扩展名为 .md

## 依赖

    pip install pymupdf easyocr pillow

## 用法

    python scripts/pdf_to_md.py <pdf_path> [--lang <lang>] [--ocr-only]

## 参数

    pdf_path   PDF 文件路径（含中文路径也可）
    --lang      OCR 语言，默认 "ch_sim,en"（中英文）
    --ocr-only  仅 OCR，跳过文本层的直接提取
"""
import sys
import argparse
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
from PIL import Image, ImageEnhance
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
# 核心逻辑
# ---------------------------------------------------------------------------


def has_text_layer(page) -> bool:
    """判断页面是否有可提取的文本。"""
    text = page.get_text().strip()
    return len(text) > 50  # 少于 50 字符视为纯图片页


def extract_text_page(page) -> str:
    """从文本层提取页面内容。"""
    return page.get_text()


def ocr_page(page, reader) -> str:
    """对页面图片内容做 OCR，返回识别文本。"""
    pix = page.get_pixmap(dpi=200)
    img = Image.frombytes("RGB", [pix.width, pix.height], pix.samples)

    # 图像预处理：灰度化 + 对比度增强，提升 OCR 准确率
    img_gray = img.convert("L")
    enhancer = ImageEnhance.Contrast(img_gray)
    img_enhanced = enhancer.enhance(2.0)
    img_array = np.array(img_enhanced)

    # text_threshold=0.3 低阈值捕获表格/截图文字
    # low_text=0.3 不丢弃低密度文本区域
    # detail=0 直接返回文本列表
    results = reader.readtext(
        img_array, detail=0, text_threshold=0.3, low_text=0.3
    )
    return "\n".join(results)


def convert(pdf_path: str, lang: str = "ch_sim,en", ocr_only: bool = False):
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
            # 强制 OCR
            text = ocr_page(page, reader)
        else:
            # 智能判断：有文本层则提取，否则 OCR
            if has_text_layer(page):
                text = extract_text_page(page)
                # 文本层非空 — 检视是否有图片需额外 OCR（跳过本次）
                # 纯文本优先
            else:
                print(f"  [OCR] 第 {page_num} 页 → 截图识别")
                text = ocr_page(page, reader)

        md_lines.append(text)

    doc.close()

    content = "\n".join(md_lines)
    md_path.write_text(content, encoding="utf-8")
    print(f"[完成] → {md_path} ({md_path.stat().st_size:,} bytes)")


# ---------------------------------------------------------------------------
# CLI
# ---------------------------------------------------------------------------

def main():
    parser = argparse.ArgumentParser(description="PDF → Markdown（含 OCR）")
    parser.add_argument("pdf_path", help="PDF 文件路径")
    parser.add_argument("--lang", default="ch_sim,en", help="OCR 语言（默认: ch_sim,en）")
    parser.add_argument("--ocr-only", action="store_true", help="强制所有页均使用 OCR")
    args = parser.parse_args()

    convert(args.pdf_path, lang=args.lang, ocr_only=args.ocr_only)


if __name__ == "__main__":
    main()
