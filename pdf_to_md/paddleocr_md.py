"""
paddleocr_md.py — PDF → Markdown（PaddleOCR ONNX 引擎）

高精度方案，需要 paddleocr + onnxruntime。
首次运行自动下载 ONNX 模型（~200MB）。

用法:
    uv run python pdf_to_md/paddleocr_md.py <pdf_path> [--dpi 300] [--ocr-only]
"""
import sys
import argparse

sys.stdout.reconfigure(encoding="utf-8")

# 依赖检查
_MISSING = []
try:
    import fitz
except ImportError:
    _MISSING.append("pymupdf")
try:
    from paddleocr import PaddleOCR
    _has_paddleocr = True
except ImportError:
    _MISSING.append("paddleocr")
    _has_paddleocr = False
try:
    from PIL import Image
except ImportError:
    _MISSING.append("pillow")
try:
    import numpy as np
except ImportError:
    _MISSING.append("numpy")

if _MISSING:
    print("缺少依赖：" + ", ".join(_MISSING))
    print("请运行: uv pip install paddleocr onnxruntime pillow numpy pymupdf")
    sys.exit(1)

from PIL import Image
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
# PaddleOCR 引擎（ONNX Runtime）
# ---------------------------------------------------------------------------

_reader = None


def _get_reader(lang: str = "ch"):
    global _reader
    if _reader is None:
        print(f"[PaddleOCR] 初始化 ONNX（语言: {lang}）...")
        _reader = PaddleOCR(engine="onnxruntime", lang=lang)
    return _reader


def ocr_page(page, dpi=300) -> str:
    """PaddleOCR (ONNX Runtime) → 版面分析 → Markdown。"""
    reader = _get_reader()
    pix = page.get_pixmap(dpi=dpi)
    img = Image.frombytes("RGB", [pix.width, pix.height], pix.samples)
    img_array = np.array(img)

    raw = list(reader.predict(img_array))
    if not raw:
        return ""

    ocr_result = raw[0]
    texts = ocr_result.get("rec_texts", []) or []
    scores = ocr_result.get("rec_scores", []) or []
    bboxes = ocr_result.get("rec_polys", []) or []

    if not texts:
        return ""

    results = []
    for i, text in enumerate(texts):
        poly = bboxes[i] if i < len(bboxes) else [[0, 0], [0, 0], [0, 0], [0, 0]]
        if hasattr(poly, "tolist"):
            poly = poly.tolist()
        score = float(scores[i]) if i < len(scores) else 0.5
        results.append((poly, text, score))

    rows = _group_rows(results, y_tol=30)

    if _is_table(rows):
        output = _format_table(rows)
    else:
        output = _build_paragraph_text(rows)

    return _postprocess_ocr_text(output)


# ---------------------------------------------------------------------------
# CLI
# ---------------------------------------------------------------------------

def main():
    parser = argparse.ArgumentParser(description="PDF → Markdown（PaddleOCR ONNX）")
    parser.add_argument("pdf_path", help="PDF 文件路径")
    parser.add_argument("--lang", default="ch", help="OCR 语言（ch / en）")
    parser.add_argument("--ocr-only", action="store_true", help="强制全部 OCR")
    parser.add_argument("--dpi", type=int, default=300, help="OCR 渲染分辨率")
    args = parser.parse_args()

    _get_reader(args.lang)
    convert(args.pdf_path, ocr_page, ocr_only=args.ocr_only,
            dpi=args.dpi, engine_label="PaddleOCR")


if __name__ == "__main__":
    main()
