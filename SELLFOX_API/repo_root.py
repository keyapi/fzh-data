"""Locate fzh-data repo root from any script under SELLFOX_API or worktrees."""
from __future__ import annotations

from pathlib import Path


def find_main_root(*, start: Path | None = None) -> Path:
    """Return directory containing both ``.env`` and ``EN_API/.env``.

    Walks ``start`` and every ancestor until filesystem root. Raises
    ``FileNotFoundError`` with the checked paths when not found.
    """
    start_path = (start or Path(__file__).resolve().parent).resolve()
    checked: list[str] = []
    for candidate in (start_path, *start_path.parents):
        checked.append(str(candidate))
        if (candidate / ".env").is_file() and (candidate / "EN_API" / ".env").is_file():
            return candidate
    raise FileNotFoundError(
        "找不到项目根目录（需同时存在 .env 与 EN_API/.env）。已检查: "
        + "; ".join(checked)
    )
