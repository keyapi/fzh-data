# -*- coding: utf-8 -*-
"""Web 图片上传管理工具 — FastAPI 后端。

启动方式:
  uv run python image_upload_app.py
  uv run python image_upload_app.py --port 8080

浏览器自动打开后:
  1. 拖拽/选择图片 → 缩略图预览
  2. 拖拽缩略图调整顺序（第1张=主图）
  3. 点击"上传到ERPNext" → 生成Excel下载
"""

from __future__ import annotations

import argparse
import io
import json
import os
import sys
import time
import webbrowser
from datetime import datetime
from pathlib import Path
from typing import Any

import pandas as pd
import requests
import uvicorn
from fastapi import FastAPI, File, Form, UploadFile
from fastapi.responses import HTMLResponse, Response
from fastapi.staticfiles import StaticFiles
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

_MIME_MAP = {
    ".jpg": "image/jpeg", ".jpeg": "image/jpeg",
    ".png": "image/png", ".gif": "image/gif", ".webp": "image/webp",
}


# ── HTTP 适配器 ──────────────────────────────────────
class _NoExpectAdapter(HTTPAdapter):
    def send(self, request, **kwargs):
        request.headers.pop("Expect", None)
        return super().send(request, **kwargs)


# ── 图片压缩 ────────────────────────────────────────
def compress_image(
    data: bytes,
    max_size: int = 1500,
    quality: int = 85,
) -> bytes:
    """压缩图片: 缩放到 max_size 最大边长, 输出 JPEG 字节。"""
    import io as _io
    from PIL import Image

    img = Image.open(_io.BytesIO(data))
    w, h = img.size
    if max(w, h) > max_size:
        ratio = max_size / max(w, h)
        img = img.resize((int(w * ratio), int(h * ratio)), Image.LANCZOS)

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
    result = buf.getvalue()
    # Don't let compression increase file size
    if len(result) >= len(data):
        return data
    return result


# ── ERPNext 客户端 ───────────────────────────────────
class ErpnextClient:
    def __init__(self, base_url: str, api_key: str, api_secret: str) -> None:
        self.base_url = base_url.rstrip("/")
        self.session = requests.Session()
        self.session.headers["Authorization"] = f"token {api_key}:{api_secret}"
        self.session.mount("https://", _NoExpectAdapter())
        self.session.mount("http://", _NoExpectAdapter())

    def upload_file(self, filename: str, file_bytes: bytes) -> str:
        ext = Path(filename).suffix.lower()
        mime = _MIME_MAP.get(ext, "application/octet-stream")
        url = f"{self.base_url}/api/method/upload_file"
        resp = self._request("POST", url,
            files={"file": (filename, file_bytes, mime)},
            data={"is_private": "0"},
        )
        return resp.json()["message"]["file_url"]

    def _request(self, method: str, url: str, *, retries: int = 2, retry_delay: float = 3.0, **kwargs) -> requests.Response:
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


# ── FastAPI 应用 ─────────────────────────────────────
app = FastAPI(title="图片上传到 ERPNext")


@app.get("/", response_class=HTMLResponse)
async def index():
    html_path = _DIR / "static" / "index.html"
    if html_path.is_file():
        return html_path.read_text(encoding="utf-8")
    return HTMLResponse("<h1>static/index.html not found</h1>", status_code=404)


@app.post("/api/upload-images")
async def upload_images(
    files: list[UploadFile] = File(..., description="图片文件列表（顺序即用户排列的顺序）"),
    env: str = Form("prod", description="目标环境"),
    compress: bool = Form(True, description="是否压缩图片"),
):
    api_key = os.getenv("ERP_API_KEY", "")
    api_secret = os.getenv("ERP_API_SECRET", "")
    base_url = os.getenv("ERP_URL") or _ENV_URLS.get(env, _ENV_URLS["prod"])

    client = ErpnextClient(base_url, api_key, api_secret)

    results: list[dict[str, str]] = []
    for idx, f in enumerate(files, 1):
        filename = f.filename or f"image_{idx}"
        content = await f.read()
        orig_size = len(content)

        # Apply compression
        if compress and Path(filename).suffix.lower() in _MIME_MAP:
            try:
                content = compress_image(content)
                filename = f"{Path(filename).stem}.jpg"
            except Exception as e:
                print(f"    compress warning: {e}, using original")

        comp_size = len(content)
        size_info = f"({orig_size/1024:.0f}KB" + (f" -> {comp_size/1024:.0f}KB)" if compress else ")")
        print(f"  [{idx}/{len(files)}] {filename} {size_info}")
        try:
            file_url = client.upload_file(filename, content)
            full_url = f"{base_url}{file_url}"
            results.append({
                "序号": idx,
                "文件名": filename,
                "file_url": file_url,
                "完整链接": full_url,
                "状态": "成功",
            })
            print(f"    OK -> {full_url}")
        except Exception as e:
            results.append({
                "序号": idx,
                "文件名": filename,
                "file_url": "",
                "完整链接": f"上传失败: {e}",
                "状态": "失败",
            })
            print(f"    FAIL: {e}")

    # 生成 Excel
    df = pd.DataFrame(results)
    ts = datetime.now().strftime("%Y%m%d_%H%M%S")
    excel_buf = io.BytesIO()
    with pd.ExcelWriter(excel_buf, engine="openpyxl") as writer:
        df.to_excel(writer, sheet_name="图片链接", index=False)
    excel_buf.seek(0)

    success = sum(1 for r in results if r["状态"] == "成功")
    return Response(
        content=excel_buf.getvalue(),
        media_type="application/vnd.openxmlformats-officedocument.spreadsheetml.sheet",
        headers={
            "Content-Disposition": f"attachment; filename*=UTF-8''%E5%9B%BE%E7%89%87%E4%B8%8A%E4%BC%A0%E9%93%BE%E6%8E%A5_{ts}.xlsx",
            "X-Upload-Result": json.dumps({"total": len(results), "success": success}),
        },
    )


# ── 主入口 ─────────────────────────────────────────
def main():
    ap = argparse.ArgumentParser(description="Web 图片上传管理工具")
    ap.add_argument("--port", "-p", type=int, default=8099,
                    help="服务端口 (默认 8099，被占则自动找下一个可用)")
    ap.add_argument("--no-browser", action="store_true", help="不自动打开浏览器")
    args = ap.parse_args()

    url = f"http://127.0.0.1:{args.port}"
    if not args.no_browser:
        webbrowser.open(url)

    print(f"\n{'='*60}")
    print(f"  图片上传管理工具")
    print(f"  启动中: {url}")
    print(f"  按 Ctrl+C 停止")
    print(f"{'='*60}")

    # uvicorn 会打印 "Uvicorn running on ..." 确认绑定成功
    try:
        uvicorn.run(app, host="127.0.0.1", port=args.port, log_level="info")
    except KeyboardInterrupt:
        print("\n已停止")


if __name__ == "__main__":
    main()
