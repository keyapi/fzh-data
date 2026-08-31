"""Locate fzh-data repo root from any script under SELLFOX_API or worktrees."""
from __future__ import annotations

from pathlib import Path

SECRET_KEYS = {"ERP_API_SECRET", "PROD_ERP_API_SECRET"}
CREDENTIAL_KEYS = {
    "ERP_API_KEY",
    "ERP_API_SECRET",
    "PROD_ERP_API_KEY",
    "PROD_ERP_API_SECRET",
}


def _has_en_credentials(env_file: Path) -> bool:
    try:
        lines = env_file.read_text(encoding="utf-8").splitlines()
    except OSError:
        return False
    keys = {
        line.split("=", 1)[0].strip()
        for line in lines
        if line.strip() and not line.lstrip().startswith("#") and "=" in line
    }
    return bool(keys & SECRET_KEYS and keys & CREDENTIAL_KEYS)


def find_main_root(*, start: Path | None = None) -> Path:
    """Return the repo root containing usable EN credentials.

    Accepts either ``EN_API/.env`` beside ``.env``, or a combined root
    ``.env`` that already carries EN API keys.
    """
    start_path = (start or Path(__file__).resolve().parent).resolve()
    checked: list[str] = []
    for candidate in (start_path, *start_path.parents):
        checked.append(str(candidate))
        root_env = candidate / ".env"
        if root_env.is_file() and (
            (candidate / "EN_API" / ".env").is_file()
            or _has_en_credentials(root_env)
        ):
            return candidate
    raise FileNotFoundError(
        "找不到项目根目录（需 .env 含 EN 凭证，或同时存在 EN_API/.env）。已检查: "
        + "; ".join(checked)
    )
