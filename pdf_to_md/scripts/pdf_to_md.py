"""
pdf_to_md.py — PDF → Markdown（兼容入口，thin wrapper）

推荐使用独立引擎脚本：
  uv run python pdf_to_md/easyocr_md.py <pdf_path>
  uv run python pdf_to_md/paddleocr_md.py <pdf_path>
"""
import sys
from pathlib import Path

# 确保 pdf_to_md 包在 sys.path 中
_pkg = Path(__file__).resolve().parent.parent
if str(_pkg) not in sys.path:
    sys.path.insert(0, str(_pkg))


def main():
    # 尝试 PaddleOCR，不可用则回退 easyocr
    try:
        from pdf_to_md.paddleocr_md import main as _main
    except ImportError:
        from pdf_to_md.easyocr_md import main as _main
    _main()


if __name__ == "__main__":
    main()
