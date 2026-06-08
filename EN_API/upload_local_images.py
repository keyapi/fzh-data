# -*- coding: utf-8 -*-
"""上传本地图片到 ERPNext，返回 Excel 含完整图片 URL。

扫描指定目录下的图片文件 (.jpg/.jpeg/.png/.gif/.webp)，
通过 ERPNext REST API upload_file 上传为公开文件，
输出 Excel 包含 filename / file_url / 完整链接。

使用:
  uv run python upload_local_images.py                       # 默认 prod + D:/EN上传图片
  uv run python upload_local_images.py --env test            # 开发测试环境
  uv run python upload_local_images.py --input-dir <path>    # 自定义输入目录
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


# ── ERPNext 客户端 ───────────────────────────────────
class ErpnextClient:
    """ERPNext REST API 客户端（精简版，仅上传文件）。"""

    def __init__(self, base_url: str, api_key: str, api_secret: str) -> None:
        self.base_url = base_url.rstrip("/")
        self.session = requests.Session()
        self.session.headers["Authorization"] = f"token {api_key}:{api_secret}"
        self.session.mount("https://", _NoExpectAdapter())
        self.session.mount("http://", _NoExpectAdapter())

    def upload_local_file(self, file_path: str) -> str:
        """上传本地文件到 ERPNext，返回 file_url（如 /files/xxx.jpg）。"""
        path = Path(file_path)
        filename = path.name
        mime = _MIME_MAP.get(path.suffix.lower(), "application/octet-stream")

        url = f"{self.base_url}/api/method/upload_file"
        with open(path, "rb") as f:
            resp = self._request("POST", url,
                files={"file": (filename, f, mime)},
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

    print(f"找到 {len(image_files)} 个图片文件:")
    for f in image_files:
        print(f"  {f.name} ({f.stat().st_size / 1024:.0f} KB)")

    client = ErpnextClient(base_url, api_key, api_secret)

    rows: list[dict[str, str]] = []
    for f in image_files:
        print(f"\n上传: {f.name} ...", end=" ")
        try:
            file_url = client.upload_local_file(str(f))
            full_url = f"{base_url}{file_url}"
            print(f"OK -> {full_url}")
            rows.append({
                "文件名": f.name,
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
