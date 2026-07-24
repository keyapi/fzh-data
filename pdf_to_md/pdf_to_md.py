"""
pdf_to_md.py — PDF → Markdown（智能选择最优引擎）

自动选择: qwen-vl-ocr > PaddleOCR > EasyOCR

用法:
    uv run python pdf_to_md/pdf_to_md.py <pdf_path> [--engine auto|qwen|paddle|easyocr]

引擎说明:
    auto    自动选择（有 API key → qwen-vl，有 PaddleOCR → paddle，fallback easyocr）
    qwen    阿里云百炼 qwen-vl-ocr API（精度最高，需 DASHSCOPE_API_KEY）
    paddle  本地 PaddleOCR ONNX（精度高，需 ~200MB 模型）
    easyocr EasyOCR（轻量离线，无需额外依赖）
"""
import sys
import os
import argparse
from pathlib import Path

sys.stdout.reconfigure(encoding="utf-8")

# 确保包路径
_pkg = Path(__file__).resolve().parent
if str(_pkg) not in sys.path:
    sys.path.insert(0, str(_pkg))


def _detect_best_engine() -> str:
    """检测可用的最优引擎。"""
    # qwen-vl: 有 API key
    try:
        from dotenv import load_dotenv
        for env_file in [".env", ".env.local"]:
            env_path = _pkg.parent / env_file
            if env_path.exists():
                load_dotenv(env_path)
        if os.environ.get("DASHSCOPE_API_KEY"):
            return "qwen"
    except Exception:
        pass
    # paddleocr: 可 import
    try:
        from paddleocr import PaddleOCR  # noqa: F401
        return "paddle"
    except ImportError:
        pass
    # fallback
    return "easyocr"


def main():
    parser = argparse.ArgumentParser(description="PDF → Markdown（智能引擎）")
    parser.add_argument("pdf_path", help="PDF 文件路径")
    parser.add_argument("--engine", default="auto",
                        choices=["auto", "qwen", "paddle", "easyocr"],
                        help="OCR 引擎（默认 auto：自动选最优）")
    parser.add_argument("--dpi", type=int, default=200, help="渲染分辨率")
    parser.add_argument("--ocr-only", action="store_true", help="强制全部 OCR")
    args = parser.parse_args()

    engine = args.engine
    if engine == "auto":
        engine = _detect_best_engine()

    print(f"[引擎] {engine}")

    if engine == "qwen":
        from qwen_vl_md import convert_vl
        convert_vl(args.pdf_path, dpi=args.dpi)
    elif engine == "paddle":
        from paddleocr_md import _get_reader, ocr_page
        _get_reader()
        from _shared import convert
        convert(args.pdf_path, ocr_page, ocr_only=args.ocr_only,
                dpi=args.dpi, engine_label="PaddleOCR")
    else:
        from easyocr_md import _get_reader, ocr_page
        _get_reader()
        from _shared import convert
        convert(args.pdf_path, ocr_page, ocr_only=args.ocr_only,
                dpi=args.dpi, engine_label="EasyOCR")


if __name__ == "__main__":
    main()
