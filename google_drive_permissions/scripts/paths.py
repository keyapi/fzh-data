# -*- coding: utf-8 -*-
"""Credential and ledger path helpers (no machine-specific D:\\ paths)."""
from __future__ import annotations

import os
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parents[2]


def user_oauth_path() -> Path:
    raw = os.environ.get("GSPREAD_USER_OAUTH_FILE", "").strip()
    if raw:
        p = Path(raw)
        if not p.is_absolute():
            p = REPO_ROOT / p
        return p
    return REPO_ROOT / "secrets" / "gsheets-user-oauth.json"
