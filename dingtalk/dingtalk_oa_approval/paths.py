# -*- coding: utf-8 -*-
"""仓库外缓存 / NAS 账期根路径。不要把本机人名目录写进 git。"""
from __future__ import annotations

import os
from pathlib import Path

MODULE_DIR = Path(__file__).resolve().parent
_REPO = MODULE_DIR.parents[1]


def _env_path(key: str, default: Path) -> Path:
    raw = os.environ.get(key, "").strip()
    return Path(raw) if raw else default


def _load_dotenv(path: Path) -> None:
    if not path.is_file():
        return
    for raw in path.read_text(encoding="utf-8").splitlines():
        line = raw.strip()
        if not line or line.startswith("#") or "=" not in line:
            continue
        k, v = line.split("=", 1)
        os.environ.setdefault(k.strip(), v.strip().strip('"').strip("'"))


_load_dotenv(MODULE_DIR / ".env")
_extra = os.environ.get("DINGTALK_OA_ENV", "").strip()
if _extra:
    _load_dotenv(Path(_extra))
_load_dotenv(_REPO / "NAS_API" / ".env")

OA_DATA = _env_path("DINGTALK_OA_DATA", MODULE_DIR / "data")
OA_REPORTS = OA_DATA / "reports"
OA_TOOLS = _env_path("DINGTALK_OA_TOOLS", MODULE_DIR)
OA_WORK = _env_path("DINGTALK_OA_WORK", OA_DATA.parent)
LOCAL_NAS_PERIOD = _env_path("LOCAL_NAS_PERIOD_ROOT", Path(r"D:\NAS与我共享\2023年度账期资料"))


def finance_period_roots() -> list[str]:
    raw = os.environ.get("NAS_FINANCE_PERIOD_ROOT", "").strip()
    if raw:
        return [p.strip() for p in raw.replace(",", ";").split(";") if p.strip()]
    return []


def finance_candidates() -> list[str]:
    roots = finance_period_roots()
    if not roots:
        raise RuntimeError(
            "未设置 NAS_FINANCE_PERIOD_ROOT。在模块 .env 或 NAS_API/.env 填 FileStation "
            "账期资料根路径（可用分号分隔多个候选）。不要把含人名的 NAS 路径写进 git。"
        )
    return roots


def finance_root() -> str:
    return finance_candidates()[0]
