"""Load project-root .env into os.environ (setdefault, never override)."""

from __future__ import annotations

import os
from pathlib import Path

_ROOT = Path(__file__).resolve().parents[1]

# Shipping historically used SELLFOX_PROXY_API_KEY; proxy admin / skill often use SELLFOX_API_KEY.
_KEY_ALIASES = (
    ("SELLFOX_API_KEY", "SELLFOX_PROXY_API_KEY"),
    ("SAIFU_KEY", "SELLFOX_PROXY_API_KEY"),
)


def load_dotenv(path: Path | None = None) -> Path | None:
    env_path = path or (_ROOT / ".env")
    if not env_path.is_file():
        _apply_key_aliases()
        return None
    text = env_path.read_text(encoding="utf-8-sig")
    for raw in text.splitlines():
        line = raw.strip()
        if not line or line.startswith("#") or "=" not in line:
            continue
        key, value = line.split("=", 1)
        key = key.strip().lstrip("\ufeff")
        value = value.strip()
        if len(value) >= 2 and value[0] == value[-1] and value[0] in "'\"":
            value = value[1:-1]
        value = value.strip()
        if key:
            os.environ.setdefault(key, value)
    _apply_key_aliases()
    return env_path


def _apply_key_aliases() -> None:
    for source, target in _KEY_ALIASES:
        if os.environ.get(target):
            continue
        value = (os.environ.get(source) or "").strip()
        if value:
            os.environ[target] = value
