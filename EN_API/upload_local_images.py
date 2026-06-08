# -*- coding: utf-8 -*-
"""上传本地图片到 ERPNext，返回 Excel 含完整图片 URL。

扫描指定目录下的图片文件 (.jpg/.jpeg/.png/.gif/.webp)，
通过 ERPNext REST API upload_file 上传为公开文件，
输出 Excel 包含 filename / file_url / 完整链接。

使用:
  uv run python upload_local_images.py                       # 默认 prod + 自动压缩
  uv run python upload_local_images.py --no-compress         # 不压缩原图上传
  uv run python upload_local_images.py --max-size 2000       # 最大边长 2000px (默认 1500)
  uv run python upload_local_images.py --quality 90          # JPEG 质量 90 (默认 85)
"""

from __future__ import annotations

import json
import os
import sys
import time
from datetime import datetime
from pathlib import Path
from typing import Any

import pandas as pd
import requests
from requests.adapters import HTTPAdapter

_DIR = Path(__file__).resolve().parent
os.chdir(_DIR)


# ── .env 加载 ──────────────────────────────────────────
def _load_dotenv(candidates: list[Path]) -> None:
    for p in candidates:
        if not p.is_file():
            continue
        for line in p.read_text(encoding="utf-8").splitlines():
            line = line.strip()
            if not line or line.startswith("#") or "=" not in line:
                continue
            k, _, v = line.partition("=")
            k, v = k.strip(), v.strip()
            if len(v) >= 2 and v[0] == v[-1] and v[0] in ('"', "'"):
                v = v[1:-1]
            os.environ.setdefault(k, v)

_ROOT = _DIR.parent
_load_dotenv([_DIR / ".env", _ROOT / ".env"])


# ── 环境配置 ─────────────────────────────────────────
_ENV_URLS: dict[str, str] = {
    "test": "https://ensh.vilavi.cn",
    "prod": "https://erpnext.vilavi.cn",
}
_DEFAULT_ENV = "prod"

_IMAGE_EXTS = {".jpg", ".jpeg", ".png", ".gif", ".webp"}
_MIME_MAP = {
    ".jpg": "image/jpeg",
    ".jpeg": "image/jpeg",
    ".png": "image/png",
    ".gif": "image/gif",
    ".webp": "image/webp",
}


# ── HTTP 适配器 ──────────────────────────────────────
class _NoExpectAdapter(HTTPAdapter):
    def send(self, request, **kwargs):
        request.headers.pop("Expect", None)
        return super().send(request, **kwargs)


# ── 图片压缩 ────────────────────────────────────────
def compress_image(
    src: str | Path | bytes,
    max_size: int = 1500,
    quality: int = 85,
) -> tuple[bytes, int, int]:
    """压缩图片: 缩放到 max_size 最大边长, 输出 JPEG。

    返回 (压缩后字节, 原始大小, 压缩后大小)。
    """
    import io as _io
    from PIL import Image

    if isinstance(src, (str, Path)):
        orig_size = Path(src).stat().st_size
        img = Image.open(Path(src))
    else:
        orig_size = len(src)
        img = Image.open(_io.BytesIO(src))

    w, h = img.size
    if max(w, h) > max_size:
        ratio = max_size / max(w, h)
        img = img.resize((int(w * ratio), int(h * ratio)), Image.LANCZOS)

    # Convert to RGB (handle PNG/GIF alpha)
    if img.mode in ("RGBA", "P", "LA"):
        bg = Image.new("RGB", img.size, (255, 255, 255))
        if img.mode == "P":
            img = img.convert("RGBA")
        bg.paste(img, mask=img.split()[-1] if img.mode == "RGBA" else None)
        img = bg
    elif img.mode != "RGB":
        img = img.convert("RGB")

    buf = _io.BytesIO()
    img.save(buf, format="JPEG", quality=quality, optimize=True)
    compressed = buf.getvalue()
    # Don't let compression increase file size (happens with already-optimized JPEGs)
    if len(compressed) >= orig_size:
        return (src if isinstance(src, bytes) else Path(src).read_bytes()), orig_size, orig_size
    return compressed, orig_size, len(compressed)


# ── ERPNext 客户端 ───────────────────────────────────
class ErpnextClient:
    """ERPNext REST API 客户端（精简版，仅上传文件）。"""

    def __init__(self, base_url: str, api_key: str, api_secret: str) -> None:
        self.base_url = base_url.rstrip("/")
        self.session = requests.Session()
        self.session.headers["Authorization"] = f"token {api_key}:{api_secret}"
        self.session.mount("https://", _NoExpectAdapter())
        self.session.mount("http://", _NoExpectAdapter())

    def upload_local_file(self, file_path: str, file_bytes: bytes | None = None) -> str:
        """上传文件到 ERPNext，返回 file_url。file_bytes 为 None 则读盘。"""
        path = Path(file_path)
        filename = path.name
        # Use .jpg extension when we compress (always output JPEG)
        out_name = filename if file_bytes is None else f"{path.stem}.jpg"
        ext = Path(out_name).suffix.lower()
        mime = _MIME_MAP.get(ext, "application/octet-stream")

        url = f"{self.base_url}/api/method/upload_file"
        data = file_bytes if file_bytes is not None else path.read_bytes()
        resp = self._request("POST", url,
            files={"file": (out_name, data, mime)},
            data={"is_private": "0"},
        )
        return resp.json()["message"]["file_url"]

    def _request(
        self, method: str, url: str, *,
        retries: int = 2, retry_delay: float = 3.0,
        **kwargs: Any,
    ) -> requests.Response:
        timeout = kwargs.pop("timeout", (30, 120))
        last_exc = None
        for attempt in range(retries + 1):
            try:
                resp = self.session.request(method, url, timeout=timeout, **kwargs)
                resp.raise_for_status()
                return resp
            except requests.RequestException as e:
                last_exc = e
                if attempt < retries:
                    time.sleep(retry_delay)
        raise last_exc


# ── 主入口 ─────────────────────────────────────────
def main() -> int:
    import argparse
    ap = argparse.ArgumentParser(description="上传本地图片到 ERPNext，返回完整链接 Excel")
    ap.add_argument("--env", "-e", choices=["test", "prod"], default=_DEFAULT_ENV,
                    help="目标环境 (默认 prod，开发测试用 --env test)")
    ap.add_argument("--input-dir", "-i", type=Path, default=Path("D:/EN上传图片"),
                    help="图片目录 (默认 D:/EN上传图片)")
    ap.add_argument("--no-compress", action="store_true",
                    help="不压缩，直接上传原图")
    ap.add_argument("--max-size", type=int, default=1500,
                    help="压缩后最大边长 px (默认 1500)")
    ap.add_argument("--quality", type=int, default=85,
                    help="JPEG 压缩质量 1-100 (默认 85)")
    args = ap.parse_args()

    api_key = os.getenv("ERP_API_KEY", "")
    api_secret = os.getenv("ERP_API_SECRET", "")
    if not api_key or not api_secret:
        print("错误: 请设置环境变量或创建 .env 文件")
        return 1

    base_url = os.getenv("ERP_URL") or _ENV_URLS[args.env]
    print(f"目标环境: {args.env} ({base_url})")

    img_dir = args.input_dir
    if not img_dir.is_dir():
        print(f"错误: 目录不存在 {img_dir}")
        return 1

    image_files = sorted([
        p for p in img_dir.iterdir()
        if p.is_file() and p.suffix.lower() in _IMAGE_EXTS
    ])
    if not image_files:
        print(f"错误: 目录 {img_dir} 中没有图片文件")
        return 1

    do_compress = not args.no_compress
    if do_compress:
        print(f"压缩: 最大 {args.max_size}px, JPEG quality {args.quality}")
    else:
        print("压缩: 已关闭 (原图上传)")

    print(f"找到 {len(image_files)} 个图片文件:")
    for f in image_files:
        print(f"  {f.name} ({f.stat().st_size / 1024:.0f} KB)")

    client = ErpnextClient(base_url, api_key, api_secret)

    total_orig = 0
    total_compressed = 0
    rows: list[dict[str, str]] = []
    for f in image_files:
        print(f"\n上传: {f.name} ...", end=" ")
        try:
            file_bytes = None
            if do_compress:
                compressed, orig_sz, comp_sz = compress_image(
                    str(f), max_size=args.max_size, quality=args.quality
                )
                file_bytes = compressed
                total_orig += orig_sz
                total_compressed += comp_sz
                print(f"({orig_sz/1024:.0f}KB -> {comp_sz/1024:.0f}KB)", end=" ")

            file_url = client.upload_local_file(str(f), file_bytes=file_bytes)
            full_url = f"{base_url}{file_url}"
            print(f"OK -> {full_url}")
            rows.append({
                "文件名": f.name if file_bytes is None else f"{f.stem}.jpg",
                "file_url": file_url,
                "完整链接": full_url,
            })
        except Exception as e:
            print(f"FAIL: {e}")
            rows.append({
                "文件名": f.name,
                "file_url": "",
                "完整链接": f"上传失败: {e}",
            })

    if do_compress and total_orig > 0:
        ratio = (1 - total_compressed / total_orig) * 100
        print(f"\n总计压缩: {total_orig/1024:.0f}KB -> {total_compressed/1024:.0f}KB (减小 {ratio:.0f}%)")

    out_dir = _DIR / "out"
    out_dir.mkdir(parents=True, exist_ok=True)
    ts = datetime.now().strftime("%Y%m%d_%H%M%S")
    out_path = out_dir / f"图片上传链接_{ts}.xlsx"

    df = pd.DataFrame(rows)
    with pd.ExcelWriter(out_path, engine="openpyxl") as writer:
        df.to_excel(writer, sheet_name="图片链接", index=False)

    print(f"\n{'='*50}")
    print(f"报告已生成: {out_path}")
    success = sum(1 for r in rows if r["完整链接"].startswith("http"))
    print(f"共上传 {success} / {len(rows)} 个文件")
    if success:
        print(f"\n完整链接:")
        for r in rows:
            if r["完整链接"].startswith("http"):
                print(f"  {r['文件名']}: {r['完整链接']}")
    print(f"{'='*50}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
