# -*- coding: utf-8 -*-
"""用 NAS 管理员账号连 FileStation。账号/密码/URL 只从 .env 读，不要写进 git。"""
from __future__ import annotations

import os
import sys
import warnings
from pathlib import Path

_REPO = Path(__file__).resolve().parents[2]
if str(_REPO) not in sys.path:
    sys.path.insert(0, str(_REPO))
_HERE = Path(__file__).resolve().parent
if str(_HERE) not in sys.path:
    sys.path.insert(0, str(_HERE))

from NAS_API.synology import SynologyNAS, _load_dotenv
from paths import finance_candidates, finance_root, finance_period_roots

NAS_ENV = _REPO / "NAS_API" / ".env"


class _LazyRoot:
    def __str__(self) -> str:
        return finance_root()

    def __add__(self, other):
        return finance_root() + other


class _LazyCandidates:
    def __iter__(self):
        return iter(finance_candidates())

    def __getitem__(self, i):
        return finance_candidates()[i]

    def __bool__(self):
        return bool(finance_period_roots())


FINANCE_CANDIDATES = _LazyCandidates()
ROOT = _LazyRoot()


_USER_KEYS = ("NAS_ADMIN_USER", "NAS_SSH_USER", "NAS_USERNAME")


def nas_credentials() -> tuple[str, str, str]:
    """返回 (url, username, password)。账号不要写进代码。

    账号取 `NAS_ADMIN_USER` → `NAS_SSH_USER` → `NAS_USERNAME`。前两个是管理员；
    `NAS_USERNAME` 通常是只做 API 的账号（如 fzh.test）——**有时权限就够用**，
    所以仍允许，但会发一条警告：它可能看不见「财务部」共享，那时在
    `NAS_API/.env` 设 `NAS_ADMIN_USER=<管理员账号>` 即可，不需要改代码。
    """
    _load_dotenv([NAS_ENV])
    user, source = "", ""
    for key in _USER_KEYS:
        value = (os.getenv(key) or "").strip()
        if value:
            user, source = value, key
            break
    pwd = (os.getenv("NAS_SSH_PASSWORD") or os.getenv("NAS_PASSWORD") or "").strip()
    url = (os.getenv("NAS_URL") or "").strip()
    if not user:
        raise RuntimeError(
            "NAS_API/.env 缺少 NAS_ADMIN_USER（或 NAS_SSH_USER / NAS_USERNAME）。"
            "账号只写进 .env，不要写进 git。"
        )
    if not pwd:
        raise RuntimeError("NAS_API/.env 缺少 NAS_SSH_PASSWORD（或 NAS_PASSWORD）")
    if not url:
        raise RuntimeError("NAS_API/.env 缺少 NAS_URL")
    if source == "NAS_USERNAME":
        warnings.warn(
            f"NAS FileStation 用 NAS_USERNAME={user} 登录。该账号可能看不见「财务部」共享；"
            "需要管理员权限时，在 NAS_API/.env 加 NAS_ADMIN_USER=<管理员账号>（不用改代码）。",
            stacklevel=2,
        )
    return url, user, pwd


def nas_admin() -> SynologyNAS:
    url, user, pwd = nas_credentials()
    return SynologyNAS(base_url=url, username=user, password=pwd, root_folder="/")


def list_shares(nas: SynologyNAS) -> list[dict]:
    out = []
    if not nas._fl:
        return out
    sh = nas._fl.get_list_share()
    files = []
    if isinstance(sh, dict) and sh.get("success"):
        files = (sh.get("data") or {}).get("shares") or (sh.get("data") or {}).get("files") or []
    for f in files:
        out.append({"name": f.get("name"), "path": f.get("path"), "isdir": f.get("isdir")})
    return out
