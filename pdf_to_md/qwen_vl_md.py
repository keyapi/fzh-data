"""
qwen_vl_md.py — PDF 截图页 → 通义千问 VL OCR → Markdown

使用阿里云百炼 DashScope API（OpenAI 兼容模式）。
仅处理截图页（无文本层的页面），文本层页面仍用 pymupdf 提取。

用法:
    uv run python pdf_to_md/qwen_vl_md.py <pdf_path> [--dpi 200]

依赖:
    pip install python-dotenv requests pymupdf pillow
"""
import sys
import os
import base64
import argparse
import io
from pathlib import Path

sys.stdout.reconfigure(encoding="utf-8")

# 加载 .env
try:
    from dotenv import load_dotenv
    _env_file = Path(__file__).resolve().parent.parent / ".env"
    load_dotenv(_env_file)
except ImportError:
    pass

API_KEY = os.environ.get("DASHSCOPE_API_KEY", "")
API_BASE = "https://dashscope.aliyuncs.com/compatible-mode/v1"
MODEL = "qwen-vl-ocr"

if not API_KEY:
    print("错误: 未设置 DASHSCOPE_API_KEY，请在 .env 文件中配置")
    sys.exit(1)

# 依赖检查
_MISSING = []
try:
    import fitz
except ImportError:
    _MISSING.append("pymupdf")
try:
    import requests
except ImportError:
    _MISSING.append("requests")
try:
    from PIL import Image
except ImportError:
    _MISSING.append("pillow")

if _MISSING:
    print("缺少依赖：" + ", ".join(_MISSING))
    print("请运行: uv pip install pymupdf requests pillow python-dotenv")
    sys.exit(1)

from PIL import Image
try:
    from ._shared import (
        has_text_layer, _fix_code_blocks, _clean_page_numbers, _format_text_layer,
    )
except ImportError:
    from _shared import (
        has_text_layer, _fix_code_blocks, _clean_page_numbers, _format_text_layer,
    )


# ---------------------------------------------------------------------------
# Qwen VL OCR API
# ---------------------------------------------------------------------------

def _image_to_base64(pil_image: Image.Image) -> str:
    """PIL Image → base64 data URL。"""
    buf = io.BytesIO()
    pil_image.save(buf, format="PNG")
    return base64.b64encode(buf.getvalue()).decode("utf-8")


def ocr_image_vl(pil_image: Image.Image) -> str:
    """调用 qwen-vl-ocr API，识别图片中的表格/文字，返回 Markdown。"""
    img_b64 = _image_to_base64(pil_image)

    payload = {
        "model": MODEL,
        "messages": [
            {
                "role": "user",
                "content": [
                    {
                        "type": "image_url",
                        "image_url": {"url": f"data:image/png;base64,{img_b64}"},
                    },
                    {
                        "type": "text",
                        "text": (
                            "请将这张图片中的所有内容完整提取为 Markdown 格式。"
                            "如果有表格，请用 Markdown 表格格式输出。"
                            "如果是文字段落，请保持原文格式。"
                            "如果是文件名/标签，请保留。"
                            "只输出提取的内容，不要加任何解释。"
                        ),
                    },
                ],
            }
        ],
        "temperature": 0.1,
        "max_tokens": 4096,
    }

    try:
        resp = requests.post(
            f"{API_BASE}/chat/completions",
            json=payload,
            headers={
                "Authorization": f"Bearer {API_KEY}",
                "Content-Type": "application/json",
            },
            timeout=120,
        )
        resp.raise_for_status()
        data = resp.json()
        content = data["choices"][0]["message"]["content"]
        return content.strip()
    except requests.exceptions.RequestException as e:
        print(f"  [VL API 错误] {e}")
        return ""
    except (KeyError, IndexError) as e:
        print(f"  [VL 解析错误] {e}, response: {resp.text[:200]}")
        return ""


def ocr_page_vl(page, dpi=200) -> str:
    """PDF 页面 → qwen-vl-ocr → Markdown。"""
    pix = page.get_pixmap(dpi=dpi)
    img = Image.frombytes("RGB", [pix.width, pix.height], pix.samples)
    return ocr_image_vl(img)


# ---------------------------------------------------------------------------
# Pipeline
# ---------------------------------------------------------------------------

def convert_vl(pdf_path: str, dpi: int = 200):
    """
    PDF → Markdown（文本层用 pymupdf，截图页用 qwen-vl-ocr）。
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

    # Phase 1: classify pages
    page_meta = [(has_text_layer(p), None) for p in doc]

    # Phase 2: fix code blocks across text pages
    PAGE_MARKER = "\n<!--PB-->\n"
    combined_text = PAGE_MARKER.join(
        doc[i].get_text() for i, (is_text, _) in enumerate(page_meta) if is_text
    )
    fixed_combined, _ = _fix_code_blocks(combined_text)
    fixed_pages = fixed_combined.split(PAGE_MARKER) if fixed_combined.strip() else []

    # Phase 3: output
    text_idx = 0
    for i, (is_text, _) in enumerate(page_meta):
        page_num = i + 1

        if is_text:
            if text_idx < len(fixed_pages):
                raw = _clean_page_numbers(fixed_pages[text_idx].strip())
                md_lines.append(_format_text_layer(raw))
            text_idx += 1
        else:
            print(f"  [Qwen VL OCR] 第 {page_num} 页 → API 识别")
            text = ocr_page_vl(doc[i], dpi=dpi)
            md_lines.append(text)

    doc.close()

    content = "\n".join(md_lines)
    md_path.write_text(content, encoding="utf-8")
    print(f"[完成] → {md_path} ({md_path.stat().st_size:,} bytes)")


# ---------------------------------------------------------------------------
# CLI
# ---------------------------------------------------------------------------

def main():
    parser = argparse.ArgumentParser(
        description="PDF → Markdown（文本 pymupdf + 截图 qwen-vl-ocr）"
    )
    parser.add_argument("pdf_path", help="PDF 文件路径")
    parser.add_argument("--dpi", type=int, default=200,
                        help="截图渲染分辨率（默认 200，越高越清晰但 token 消耗越大）")
    args = parser.parse_args()
    convert_vl(args.pdf_path, dpi=args.dpi)


if __name__ == "__main__":
    main()
