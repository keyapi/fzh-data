"""
easyocr_md.py — PDF → Markdown（EasyOCR 引擎）

轻量级方案，仅依赖 easyocr + pymupdf。

用法:
    uv run python pdf_to_md/easyocr_md.py <pdf_path> [--dpi 300] [--ocr-only]
"""
import sys
import re
import argparse

sys.stdout.reconfigure(encoding="utf-8")

# 依赖检查
_MISSING = []
try:
    import fitz
except ImportError:
    _MISSING.append("pymupdf")
try:
    import easyocr
except ImportError:
    _MISSING.append("easyocr")
try:
    from PIL import Image, ImageEnhance
except ImportError:
    _MISSING.append("pillow")
try:
    import numpy as np
except ImportError:
    _MISSING.append("numpy")

if _MISSING:
    print("缺少依赖：" + ", ".join(_MISSING))
    print("请运行: uv pip install pymupdf easyocr pillow numpy")
    sys.exit(1)

from PIL import Image, ImageEnhance
import numpy as np

# 从共享层导入（兼容 package 和 standalone 运行）
try:
    from ._shared import (
        _group_rows, _is_table, _format_table, _build_paragraph_text,
        _fix_code_blocks, _clean_page_numbers,
        _merge_table_columns, _looks_split, _postprocess_ocr_text,
        has_text_layer, convert,
    )
except ImportError:
    from _shared import (
        _group_rows, _is_table, _format_table, _build_paragraph_text,
        _fix_code_blocks, _clean_page_numbers,
        _merge_table_columns, _looks_split, _postprocess_ocr_text,
        has_text_layer, convert,
    )

# ---------------------------------------------------------------------------
# EasyOCR 引擎
# ---------------------------------------------------------------------------

_reader = None

# OCR 纠错词典（来源于 PR #18 同事 Jack 的积累）
_CHAR_FIX = str.maketrans({
    "穴": "文", "刍": "含", "趾": "逊", "珧": "现",
    "廿": "中", "迷": "述", "颈": "须", "倩": "信",
    "笫": "第", "狈": "须", "瓴": "须", "豳": "圈",
    "潸": "清", "眄": "的", "菅": "营", "掎": "椅",
    "枸": "椅", "晷": "营", "篁": "篮",
})

_WORD_FIX = {
    # 常见英文 OCR 错误
    "campng": "camping", "campig": "camping", "campg": "camping",
    "foldng": "folding", "foldig": "folding", "folng": "folding",
    "loldng": "folding", "Ioldng": "folding",
    "char": "chair", "chars": "chairs", "chav": "chair",
    "chays": "chairs", "chai": "chair",
    "heaw": "heavy", "heawy": "heavy",
    "duly": "duty", "dutr": "duty",
    "portab": "portable", "le": "",  # handled by _merge_table_columns
    "Iaw": "Lawn", "law": "lawn", "bam": "lawn",
    "adylis": "adults", "aduls": "adults", "adullis": "adults",
    "tor": "for", "lor": "for", "Ior": "for",
    "ouiside": "outside", "Gutsde": "Outside", "oulside": "outside",
    "Oversizcd": "Oversized", "Owersizcd": "Oversized",
    "comlortab": "comfortable", "comlortable": "comfortable",
    "flable": "foldable", "Ioldab": "Foldable", "foldab": "foldable",
    "b89ch": "beach", "b8ach": "beach",
    "roclng": "rocking", "rockig": "rocking", "reclnng": "reclining",
    "gcirocker": "gci rocker",
}


def _ocr_correct(text: str) -> str:
    """后处理纠错：中文字符映射 + 英文单词直查。"""
    text = text.translate(_CHAR_FIX)
    words = text.split()
    corrected = []
    for w in words:
        m = re.match(r"^([^a-zA-Z]*)([a-zA-Z'.]+)([^a-zA-Z]*)$", w)
        if not m:
            corrected.append(w)
            continue
        pre, core, post = m.groups()
        if core in _WORD_FIX:
            corrected.append(pre + _WORD_FIX[core] + post)
        else:
            corrected.append(w)
    return " ".join(corrected)


def _get_reader(lang: str = "ch_sim,en"):
    global _reader
    if _reader is None:
        print(f"[EasyOCR] 初始化（语言: {lang}）...")
        _reader = easyocr.Reader(lang.split(","), gpu=False)
    return _reader


def ocr_page(page, dpi=300) -> str:
    """EasyOCR → 版面分析 → Markdown。"""
    reader = _get_reader()
    pix = page.get_pixmap(dpi=dpi)
    img = Image.frombytes("RGB", [pix.width, pix.height], pix.samples)

    # 预处理：灰度 + 对比度增强
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

    output = _postprocess_ocr_text(output)
    return _ocr_correct(output)


# ---------------------------------------------------------------------------
# CLI
# ---------------------------------------------------------------------------

def main():
    parser = argparse.ArgumentParser(description="PDF → Markdown（EasyOCR）")
    parser.add_argument("pdf_path", help="PDF 文件路径")
    parser.add_argument("--lang", default="ch_sim,en", help="OCR 语言")
    parser.add_argument("--ocr-only", action="store_true", help="强制全部 OCR")
    parser.add_argument("--dpi", type=int, default=300, help="OCR 渲染分辨率")
    args = parser.parse_args()

    _get_reader(args.lang)  # 预初始化
    convert(args.pdf_path, ocr_page, ocr_only=args.ocr_only,
            dpi=args.dpi, engine_label="EasyOCR")


if __name__ == "__main__":
    main()
