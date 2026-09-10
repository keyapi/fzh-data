# -*- coding: utf-8 -*-
"""用 NAS 管理员 fzh.nas 连 FileStation（密码来自 NAS_API/.env 的 NAS_SSH_PASSWORD，不写入本模块）。"""
from __future__ import annotations

import os
import sys
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


def nas_admin() -> SynologyNAS:
    _load_dotenv([NAS_ENV])
    user = os.getenv("NAS_ADMIN_USER") or "fzh.nas"
    pwd = os.getenv("NAS_SSH_PASSWORD") or ""
    url = os.getenv("NAS_URL") or ""
    if not pwd:
        raise RuntimeError("NAS_API/.env 缺少 NAS_SSH_PASSWORD")
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
