# -*- coding: utf-8 -*-
"""AI auto-tagging pipeline — OpenRouter (free VL models) + Aliyun Bailian.

Usage:
    from ai_pipeline import run_ai_pipeline
    result = await run_ai_pipeline(image_path)

Providers (auto-detected from API key prefix):
  - sk-or-v1-... → OpenRouter (nvidia/nemotron-nano-12b-v2-vl:free)
  - sk-... (other) → Aliyun Bailian (qwen-vl-plus)
"""

from __future__ import annotations

import base64, os, json
from pathlib import Path

from openai import OpenAI

# ═══════════ Config — auto-detect provider ═══════════
_RAW_KEY = os.getenv("AI_API_KEY", os.getenv("DASHSCOPE_API_KEY", ""))

if _RAW_KEY.startswith("sk-or-v1-"):
    # OpenRouter
    BASE_URL = "https://openrouter.ai/api/v1"
    MODEL = os.getenv("AI_MODEL", "nvidia/nemotron-nano-12b-v2-vl:free")
    API_KEY = _RAW_KEY
    _EXTRA_HEADERS = {
        "HTTP-Referer": "https://dam.vilavi.cn",
        "X-Title": "Vilavi DAM",
    }
else:
    # Aliyun Bailian (fallback)
    BASE_URL = "https://dashscope.aliyuncs.com/compatible-mode/v1"
    MODEL = os.getenv("AI_MODEL", "qwen-vl-plus")
    API_KEY = _RAW_KEY
    _EXTRA_HEADERS = {}

# ═══════════ Prompts ═══════════

TAG_PROMPT = """Analyze this ecommerce product image for home textiles (pillows, cushions, sofa covers, bedding).
Return ONLY valid JSON, no other text, no markdown fences:

{
  "color": "red|blue|white|black|gray|beige|navy|green|brown|multi|other",
  "angle": "front|back|side|top|detail|45degree|lifestyle|packaging|other",
  "category": "pillow|cushion|sofa_cover|floor_pillow|other",
  "view_type": "studio_product|bedroom|living_room|outdoor|packaging|detail|other",
  "background": "pure_white|off_white|colored|scene|gradient",
  "has_text_overlay": false,
  "has_logo_watermark": false,
  "has_human": false,
  "product_fill_pct": 85,
  "alt_text": "concise SEO alt text in English",
  "tags": ["tag1","tag2","tag3"]
}

Tags should be lowercase English words describing: product type, color, view angle, scene, material appearance.
Example tags for a white pillow front view: ["pillow","white","front-view","studio-lighting"]
Example tags for a blue cushion lifestyle: ["cushion","blue","lifestyle","living-room"]
"""

COMPLIANCE_PROMPT = """Check if this image meets marketplace requirements.
Return ONLY valid JSON, no other text:

{
  "amazon_main_pass": true,
  "amazon_issues": [],
  "wayfair_main_pass": true,
  "wayfair_issues": [],
  "general_quality_pass": true,
  "general_issues": []
}

Amazon main image rules:
- Pure white background (RGB 255,255,255)
- Product fills >=85% of frame
- No text, logos, watermarks on main image
- sRGB color profile

Wayfair main image rules:
- Same as Amazon plus: no human models (including hands)
- No 3D renders without disclosure

General quality: blur, lighting, composition.
"""


# ═══════════ Core Functions ═══════════

def _image_to_data_url(path: str) -> str:
    """Convert image file to data:image/...;base64,... string."""
    ext = Path(path).suffix.lower().replace(".jpeg", ".jpg")
    mime_map = {".jpg": "image/jpeg", ".jpeg": "image/jpeg",
                ".png": "image/png", ".webp": "image/webp",
                ".gif": "image/gif"}
    mime = mime_map.get(ext, "image/jpeg")
    with open(path, "rb") as f:
        b64 = base64.b64encode(f.read()).decode()
    return f"data:{mime};base64,{b64}"


def _parse_json(content: str) -> dict:
    """Extract JSON from LLM response (may contain markdown fences)."""
    text = content.strip()
    if text.startswith("```"):
        lines = text.split("\n")
        lines = lines[1:] if lines[0].startswith("```") else lines
        if lines and lines[-1].startswith("```"):
            lines = lines[:-1]
        text = "\n".join(lines)
    return json.loads(text)


def _call_vision(image_path: str, prompt: str) -> dict:
    """Send image + prompt to Vision LLM, return parsed JSON."""
    client = OpenAI(api_key=API_KEY, base_url=BASE_URL, default_headers=_EXTRA_HEADERS)
    data_url = _image_to_data_url(image_path)

    resp = client.chat.completions.create(
        model=MODEL,
        messages=[{
            "role": "user",
            "content": [
                {"type": "image_url", "image_url": {"url": data_url}},
                {"type": "text", "text": prompt},
            ],
        }],
        max_tokens=500,
        temperature=0.1,
        extra_headers=_EXTRA_HEADERS if _EXTRA_HEADERS else None,
    )

    content = resp.choices[0].message.content
    return _parse_json(content)


async def run_ai_pipeline(image_path: str) -> dict:
    """Run full AI pipeline: tags + compliance.

    Returns dict suitable for storing in Asset.ai_metadata.
    """
    try:
        tags = _call_vision(image_path, TAG_PROMPT)
    except Exception as e:
        return {"error": f"tagging_failed: {e}", "tags": [], "compliance": {}}

    try:
        compliance = _call_vision(image_path, COMPLIANCE_PROMPT)
    except Exception as e:
        compliance = {"error": f"compliance_failed: {e}"}

    return {
        "tags": tags.get("tags", []),
        "color": tags.get("color"),
        "angle": tags.get("angle"),
        "category": tags.get("category"),
        "view_type": tags.get("view_type"),
        "background": tags.get("background"),
        "has_text_overlay": tags.get("has_text_overlay"),
        "has_logo_watermark": tags.get("has_logo_watermark"),
        "has_human": tags.get("has_human"),
        "product_fill_pct": tags.get("product_fill_pct"),
        "alt_text": tags.get("alt_text"),
        "compliance": compliance,
    }
