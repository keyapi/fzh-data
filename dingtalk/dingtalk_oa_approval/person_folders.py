# -*- coding: utf-8 -*-
"""钉钉审批标题名 → NAS 人名文件夹。真名只放本地 json，不要进 git。"""
from __future__ import annotations

import json
from pathlib import Path

MODULE_DIR = Path(__file__).resolve().parent
LOCAL_MAP = MODULE_DIR / "person_folders.local.json"


def _load() -> dict:
    if not LOCAL_MAP.is_file():
        return {"originator_to_folder": {}, "initials_to_folder": {}}
    raw = json.loads(LOCAL_MAP.read_text(encoding="utf-8"))
    if not isinstance(raw, dict):
        return {"originator_to_folder": {}, "initials_to_folder": {}}
    orig = raw.get("originator_to_folder") or {}
    initials = raw.get("initials_to_folder") or {}
    return {
        "originator_to_folder": {str(k): str(v) for k, v in orig.items() if not str(k).startswith("_")},
        "initials_to_folder": {str(k).upper(): str(v) for k, v in initials.items() if not str(k).startswith("_")},
    }


_MAP = _load()
DINGTALK_TO_FOLDER = _MAP["originator_to_folder"]


def nas_person_folder(originator: str) -> str:
    n = (originator or "").strip()
    return DINGTALK_TO_FOLDER.get(n, n)


def folder_for_initials(initials: str) -> str:
    """拼音大写首字母 → NAS 文件夹真名。本地 json 缺失时返回空串。"""
    return _MAP["initials_to_folder"].get((initials or "").strip().upper(), "")


def mentions(initials: str, text: str) -> bool:
    """originator / 文件夹名是否对应该组首字母。"""
    t = text or ""
    folder = folder_for_initials(initials)
    if folder and folder in t:
        return True
    for alias, dest in DINGTALK_TO_FOLDER.items():
        if dest == folder and alias and alias in t:
            return True
    key = (initials or "").strip().upper()
    return bool(key) and key in t.upper()


def mapped_folder_names() -> list[str]:
    names = []
    for src, dest in DINGTALK_TO_FOLDER.items():
        names.extend([src, dest])
    names.extend(_MAP["initials_to_folder"].values())
    out = []
    seen = set()
    for n in names:
        if n and n not in seen:
            seen.add(n)
            out.append(n)
    return out
