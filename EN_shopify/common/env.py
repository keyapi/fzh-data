# -*- coding: utf-8 -*-
"""环境配置：.env 加载 + 环境映射。

可扫描的 .env 位置（按优先级）：
  - .env (当前目录)
  - ../.env
  - ../../.env
"""

from __future__ import annotations

import os
from pathlib import Path
from typing import Literal

# ── 环境 URL 映射 ─────────────────────────────────────
ENV_URLS: dict[str, str] = {
    "test": "https://ensh.vilavi.cn",
    "prod": "https://erpnext.vilavi.cn",
}

ENV_KEY_MAP: dict[str, tuple[str, str]] = {
    "test": ("TEST_ERP_API_KEY", "TEST_ERP_API_SECRET"),
    "prod": ("PROD_ERP_API_KEY", "PROD_ERP_API_SECRET"),
}

ShopifyEnv = Literal["test", "prod"]


def load_dotenv(candidates: list[Path] | None = None) -> None:
    """加载 .env 文件到环境变量（仅 setdefault，不覆盖已有值）。"""
    if candidates is None:
        _dir = Path(__file__).resolve().parent.parent  # EN_独立站/
        candidates = [
            _dir / ".env",                          # EN_独立站/.env
            _dir.parent / ".env",                   # fzh-data/.env
            _dir.parent.parent / ".env",            # Claude Demo/.env
            _dir / ".." / "EN_API" / ".env",        # EN_API/.env (凭证实际位置)
        ]
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


def get_erpnext_url(env: str = "test") -> str:
    """获取指定环境的 ERPNext URL。"""
    return ENV_URLS.get(env, ENV_URLS["test"])


def get_erpnext_credentials(env: str = "test") -> tuple[str, str]:
    """获取指定环境的 API 凭证 (api_key, api_secret)。"""
    key_var, secret_var = ENV_KEY_MAP.get(env, ENV_KEY_MAP["test"])
    return os.getenv(key_var, ""), os.getenv(secret_var, "")


# ── 默认加载 ──────────────────────────────────────────
load_dotenv()
