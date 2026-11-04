# -*- coding: utf-8 -*-
"""仓库外归档路径与 DWS 可执行文件定位。不要把本机私有路径写进 git。"""
from __future__ import annotations

import os
import shutil
from pathlib import Path

MODULE_DIR = Path(__file__).resolve().parent
_REPO = MODULE_DIR.parents[1]


def _load_dotenv(path: Path) -> None:
    if not path.is_file():
        return
    for raw in path.read_text(encoding="utf-8").splitlines():
        line = raw.strip()
        if not line or line.startswith("#") or "=" not in line:
            continue
        key, value = line.split("=", 1)
        os.environ.setdefault(key.strip(), value.strip().strip('"').strip("'"))


_load_dotenv(MODULE_DIR / ".env")
_load_dotenv(_REPO / ".env")


def _env_path(key: str, default: Path) -> Path:
    raw = os.environ.get(key, "").strip()
    return Path(raw) if raw else default


HARVEST_ROOT = _env_path("DINGTALK_HARVEST_ROOT", Path.home() / "dingtalk_harvest")
CONFIG_PATH = _env_path(
    "DINGTALK_HARVEST_CONFIG", MODULE_DIR / "config" / "groups.local.json"
)
EXAMPLE_CONFIG = MODULE_DIR / "config" / "groups.example.json"
DIGEST_PROMPT = MODULE_DIR / "docs" / "prompts" / "digest.md"


def dws_exe() -> str:
    raw = os.environ.get("DWS_EXE", "").strip()
    if raw:
        return raw
    found = shutil.which("dws")
    if found:
        return found
    name = "dws.exe" if os.name == "nt" else "dws"
    candidate = Path.home() / ".local" / "bin" / name
    if candidate.is_file():
        return str(candidate)
    raise RuntimeError(
        "找不到 dws。请安装钉钉 Workspace CLI，或在 .env 设置 DWS_EXE。"
    )


def ensure_group_dirs(group: str) -> None:
    for sub in ("messages", "files", "media", "docs"):
        (HARVEST_ROOT / group / sub).mkdir(parents=True, exist_ok=True)
    for sub in ("digests", "reports", "state", "logs", "tmp"):
        (HARVEST_ROOT / sub).mkdir(parents=True, exist_ok=True)
