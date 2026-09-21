"""有界上溯加载 .env —— 解决 worktree 里取不到父仓库凭证的问题。

背景：本仓库既有的 .env 加载器都假设「仓库根 = parents[1]」，但在 git worktree 里
(parents[1] = worktree 根) 没有 .env，真正的 .env 在父仓库根 (parents[4])。
这里改成从包目录逐级上溯、有界、就近优先，两种布局都能命中。
"""

from __future__ import annotations

import os
from pathlib import Path

_PKG_DIR = Path(__file__).resolve().parent

# 上溯层数上限：够到 worktree 的 parents[4]，又不至于吃到无关的上层目录
_ENV_LEVELS = 6


def parse_env_file(path: Path) -> dict[str, str]:
    """解析 key=value，跳过空行/注释/无 = 的行，去掉值两端引号。utf-8-sig 防 BOM。"""
    values: dict[str, str] = {}
    for raw in path.read_text(encoding="utf-8-sig").splitlines():
        line = raw.strip()
        if not line or line.startswith("#") or "=" not in line:
            continue
        key, _, value = line.partition("=")
        key = key.strip().lstrip("\ufeff")
        value = value.strip()
        if len(value) >= 2 and value[0] == value[-1] and value[0] in "'\"":
            value = value[1:-1].strip()
        if key and value:
            values[key] = value
    return values


def candidates(start: Path | None = None, *, levels: int = _ENV_LEVELS) -> list[Path]:
    """从 start（默认包目录）逐级上溯，返回存在的 .env 路径，就近在前。"""
    base = (start or _PKG_DIR).resolve()
    found: list[Path] = []
    for directory in [base, *base.parents[:levels]]:
        candidate = directory / ".env"
        if candidate.is_file():
            found.append(candidate)
    return found


def load_env(start: Path | None = None, *, levels: int = _ENV_LEVELS) -> list[Path]:
    """把上溯到的 .env 灌进 os.environ，只补缺失或为空的值（已 export 的永不覆盖）。

    返回实际加载的文件路径列表，供 --verbose 展示。
    """
    loaded = candidates(start, levels=levels)
    for path in loaded:
        for key, value in parse_env_file(path).items():
            if not (os.environ.get(key) or "").strip():
                os.environ[key] = value
    return loaded


def get_key(name: str) -> str | None:
    """先看已 export 的环境变量，再走上溯加载。"""
    value = (os.environ.get(name) or "").strip()
    if value:
        return value
    load_env()
    return (os.environ.get(name) or "").strip() or None
