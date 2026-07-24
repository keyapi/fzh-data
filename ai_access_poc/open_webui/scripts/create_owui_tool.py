#!/usr/bin/env python3
"""Create or update OWUI Workspace Tool from local sellfox tool source.

Requires env OWUI_ADMIN_PASSWORD (and optional OWUI_ADMIN_EMAIL / OWUI_BASE).
"""
from __future__ import annotations

import json
import os
import urllib.error
import urllib.request
from pathlib import Path

BASE = os.environ.get("OWUI_BASE", "http://127.0.0.1:3000").rstrip("/")
TOOL = Path(__file__).resolve().parents[1] / "tools" / "sellfox_pull_sp_search_term.py"
TOOL_ID = "sellfox_sp_search_term_pull"


def req(method: str, path: str, body: dict | None = None, token: str | None = None):
    data = None if body is None else json.dumps(body).encode("utf-8")
    headers = {"Content-Type": "application/json"}
    if token:
        headers["Authorization"] = f"Bearer {token}"
    request = urllib.request.Request(
        f"{BASE}{path}", data=data, headers=headers, method=method
    )
    try:
        with urllib.request.urlopen(request, timeout=120) as resp:
            raw = resp.read().decode("utf-8")
            return resp.status, json.loads(raw) if raw else None
    except urllib.error.HTTPError as e:
        raw = e.read().decode("utf-8", errors="replace")
        raise SystemExit(f"HTTP {e.code} {path}: {raw[:800]}") from e


def main() -> None:
    email = os.environ.get("OWUI_ADMIN_EMAIL", "poc-admin@vilavi.local")
    password = os.environ.get("OWUI_ADMIN_PASSWORD", "")
    if not password:
        raise SystemExit("Set OWUI_ADMIN_PASSWORD")
    _, auth = req("POST", "/api/v1/auths/signin", {"email": email, "password": password})
    token = auth["token"]
    content = TOOL.read_text(encoding="utf-8")
    payload = {
        "id": TOOL_ID,
        "name": "Sellfox SP Search Term Pull",
        "content": content,
        "meta": {
            "description": (
                "Read-only Sellfox SP search-term pull + text summary "
                "(proxy preferred)"
            ),
            "manifest": {},
        },
        "access_grants": [],
    }

    _, tools = req("GET", "/api/v1/tools/", token=token)
    exists = any(isinstance(t, dict) and t.get("id") == TOOL_ID for t in (tools or []))

    if exists:
        _, updated = req(
            "POST", f"/api/v1/tools/id/{TOOL_ID}/update", payload, token=token
        )
        print("updated", updated.get("id"), updated.get("name"))
    else:
        _, created = req("POST", "/api/v1/tools/create", payload, token=token)
        print("created", created.get("id"), created.get("name"))

    valves = {
        "SELLFOX_PROXY_API_KEY": os.environ.get("SELLFOX_PROXY_API_KEY", ""),
        "SELLFOX_PROXY_BASE_URL": os.environ.get(
            "SELLFOX_PROXY_BASE_URL", "https://api.vilavi.cn/sellfox"
        ),
        "SELLFOX_PROXY_ACCOUNT": os.environ.get("SELLFOX_PROXY_ACCOUNT", "sellfox-main"),
        "REPORT_DIR": "/data/sellfox_reports",
        "MAX_WAIT_S": 300,
        "DEFAULT_DAYS": 7,
        "SUMMARY_TOP_N": 20,
    }
    env_path = Path(__file__).resolve().parents[1] / ".env"
    if env_path.is_file():
        for line in env_path.read_text(encoding="utf-8").splitlines():
            line = line.strip()
            if line and not line.startswith("#") and "=" in line:
                k, v = line.split("=", 1)
                if k.strip() in valves and v.strip():
                    valves[k.strip()] = v.strip()
    _, vout = req(
        "POST",
        f"/api/v1/tools/id/{TOOL_ID}/valves/update",
        valves,
        token=token,
    )
    print(
        "valves_keys",
        sorted(vout.keys()) if isinstance(vout, dict) else type(vout).__name__,
    )


if __name__ == "__main__":
    main()
