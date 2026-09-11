# -*- coding: utf-8 -*-
"""NAS SSH 连接凭据：一律从 .env / 环境变量读，脚本里不要出现明文账号密码。

查找顺序：模块 `.env`（从 `.env.example` 复制）→ 仓库级 `NAS_API/.env` → 进程环境变量。
两处 `.env` 都已被 `.gitignore` 排除。
"""
from __future__ import annotations

import os
from dataclasses import dataclass
from pathlib import Path

MODULE_DIR = Path(__file__).resolve().parent
REPO_ROOT = MODULE_DIR.parent
ENV_FILES = (MODULE_DIR / ".env", REPO_ROOT / "NAS_API" / ".env")

_PASSWORD_KEYS = ("NAS_SSH_PASSWORD", "NAS_PASSWORD")
_USER_KEYS = ("NAS_SSH_USER", "NAS_ADMIN_USER")
_HOST_KEYS = ("NAS_SSH_HOST", "NAS_HOST")
_PORT_KEYS = ("NAS_SSH_PORT", "NAS_PORT")

HINT = (
    "把 nas_product_visuals/.env.example 复制为 nas_product_visuals/.env 并填好"
    "（或写进 NAS_API/.env）。不要把账号密码写进脚本、命令行参数或 git。"
)


def _load_dotenv(path: Path) -> None:
    if not path.is_file():
        return
    for raw in path.read_text(encoding="utf-8").splitlines():
        line = raw.strip()
        if not line or line.startswith("#") or "=" not in line:
            continue
        k, v = line.split("=", 1)
        os.environ.setdefault(k.strip(), v.strip().strip('"').strip("'"))


def _first(keys: tuple[str, ...]) -> str:
    for k in keys:
        v = os.environ.get(k, "").strip()
        if v:
            return v
    return ""


@dataclass(frozen=True)
class NasSsh:
    host: str
    port: int
    user: str
    password: str


def nas_ssh() -> NasSsh:
    """读 SSH 连接参数。缺任何一项都直接报错，不回退到别的账号或默认密码。"""
    for path in ENV_FILES:
        _load_dotenv(path)

    missing = []
    password = _first(_PASSWORD_KEYS)
    user = _first(_USER_KEYS)
    host = _first(_HOST_KEYS)
    if not password:
        missing.append("/".join(_PASSWORD_KEYS))
    if not user:
        missing.append("/".join(_USER_KEYS))
    if not host:
        missing.append(_HOST_KEYS[0])
    if missing:
        raise RuntimeError(f"缺少 {'、'.join(missing)}。{HINT}")

    port_raw = _first(_PORT_KEYS) or "22"
    try:
        port = int(port_raw)
    except ValueError:
        raise RuntimeError(f"NAS_SSH_PORT 不是数字：{port_raw!r}。{HINT}")
    return NasSsh(host=host, port=port, user=user, password=password)
