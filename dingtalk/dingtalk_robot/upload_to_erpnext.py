"""
上传文件到 ERPNext，返回公开访问 URL。

用法:
    cd dingtalk/dingtalk_robot && python upload_to_erpnext.py report.xlsx

环境变量:
    ERP_API_KEY    — ERPNext API Key
    ERP_API_SECRET — ERPNext API Secret
    ERP_URL        — ERPNext 服务器地址 (默认 https://erpnext.vilavi.cn)
"""

import os
import sys
import time
from pathlib import Path

import requests
from requests.adapters import HTTPAdapter


class NoExpectAdapter(HTTPAdapter):
    def send(self, request, **kwargs):
        request.headers.pop("Expect", None)
        return super().send(request, **kwargs)


_MIME_MAP = {
    ".xlsx": "application/vnd.openxmlformats-officedocument.spreadsheetml.sheet",
    ".xls": "application/vnd.ms-excel",
    ".csv": "text/csv",
    ".pdf": "application/pdf",
    ".png": "image/png",
    ".jpg": "image/jpeg",
    ".jpeg": "image/jpeg",
    ".txt": "text/plain",
    ".zip": "application/zip",
}


def upload_file_to_erpnext(
    file_path: str | Path,
    base_url: str | None = None,
    api_key: str | None = None,
    api_secret: str | None = None,
    is_private: bool = False,
) -> str:
    """上传文件到 ERPNext，返回完整下载 URL。

    Args:
        file_path:   本地文件路径
        base_url:    ERPNext 地址，默认从 ERP_URL 环境变量读取
        api_key:     API Key，默认从 ERP_API_KEY 环境变量读取
        api_secret:  API Secret，默认从 ERP_API_SECRET 环境变量读取
        is_private:  是否私密文件 (默认公开，方便钉钉链接下载)

    Returns:
        完整文件 URL，如 https://erpnext.vilavi.cn/files/abc123.xlsx
    """
    base_url = (base_url or os.environ.get("ERP_URL", "https://erpnext.vilavi.cn")).rstrip("/")
    api_key = api_key or os.environ["ERP_API_KEY"]
    api_secret = api_secret or os.environ["ERP_API_SECRET"]

    path = Path(file_path)
    if not path.is_file():
        raise FileNotFoundError(f"文件不存在: {file_path}")

    filename = path.name
    ext = path.suffix.lower()
    mime = _MIME_MAP.get(ext, "application/octet-stream")

    session = requests.Session()
    session.headers["Authorization"] = f"token {api_key}:{api_secret}"
    session.mount("https://", NoExpectAdapter())
    session.mount("http://", NoExpectAdapter())

    url = f"{base_url}/api/method/upload_file"
    resp = session.post(url,
        files={"file": (filename, path.read_bytes(), mime)},
        data={"is_private": "1" if is_private else "0"},
        timeout=(30, 120),
    )
    resp.raise_for_status()
    result = resp.json()

    file_url = result["message"]["file_url"]  # e.g. /files/abc123.xlsx
    return f"{base_url}{file_url}"


# ── CLI 测试 ─────────────────────────────────────────────
if __name__ == "__main__":
    if len(sys.argv) < 2:
        print(f"用法: python {Path(__file__).name} <文件路径>")
        sys.exit(1)

    full_url = upload_file_to_erpnext(sys.argv[1])
    print(full_url)
