# -*- coding: utf-8 -*-
"""Load gitignored Google service-account JSON and open Sheets (read/write)."""
from __future__ import annotations

import json
from pathlib import Path

import gspread
import pandas as pd

REPO_ROOT = Path(__file__).resolve().parents[2]
DEFAULT_SA = REPO_ROOT / "secrets" / "gsheets-service-account.json"
MODULE_ENV = Path(__file__).resolve().parents[1] / ".env"


def _parse_env(path: Path) -> dict[str, str]:
    values: dict[str, str] = {}
    if not path.exists():
        return values
    for raw in path.read_text(encoding="utf-8").splitlines():
        line = raw.strip()
        if not line or line.startswith("#") or "=" not in line:
            continue
        k, v = line.split("=", 1)
        values[k.strip()] = v.strip().strip('"').strip("'")
    return values


def service_account_path() -> Path:
    import os

    env = {**_parse_env(MODULE_ENV), **{k: v for k, v in os.environ.items() if v}}
    raw = env.get("GSPREAD_SERVICE_ACCOUNT_FILE", "").strip()
    if raw:
        p = Path(raw)
        if not p.is_absolute():
            p = REPO_ROOT / p
        return p
    return DEFAULT_SA


def load_credentials() -> dict:
    path = service_account_path()
    if not path.exists():
        raise FileNotFoundError(
            f"Google service account JSON not found: {path}\n"
            "Run: uv run python tongtool_order_cost/scripts/bootstrap_gsheets_credentials.py"
        )
    creds = json.loads(path.read_text(encoding="utf-8"))
    if creds.get("type") != "service_account":
        raise ValueError(f"{path} is not a service_account JSON")
    return creds


def client() -> gspread.Client:
    return gspread.service_account_from_dict(load_credentials())


def gsheet2df(
    gc: gspread.Client,
    gsheet_name: str,
    worksheet_name: str,
    header_row: int = 0,
) -> pd.DataFrame:
    """Match Colab notebook gsheet2df: first row is header."""
    sh = gc.open(gsheet_name)
    ws = sh.worksheet(worksheet_name)
    rows = ws.get_all_values()
    if not rows:
        return pd.DataFrame()
    header = rows[header_row]
    body = rows[header_row + 1 :]
    df = pd.DataFrame(body, columns=header)
    return df.replace("", pd.NA)
