# -*- coding: utf-8 -*-
"""ERPNext REST session for production Channel Account writes."""
from __future__ import annotations

import json
from pathlib import Path
from urllib.parse import quote

import requests

REPO_ROOT = Path(__file__).resolve().parents[1]


class NoExpect(requests.adapters.HTTPAdapter):
    def send(self, request, **kwargs):
        request.headers.pop("Expect", None)
        return super().send(request, **kwargs)


def load_env() -> dict[str, str]:
    values: dict[str, str] = {}
    for path in (REPO_ROOT / "EN_API" / ".env", REPO_ROOT / ".env"):
        if not path.exists():
            continue
        for line in path.read_text(encoding="utf-8").splitlines():
            line = line.strip()
            if line and not line.startswith("#") and "=" in line:
                key, value = line.split("=", 1)
                values[key.strip()] = value.strip().strip("'\"")
    return values


def session() -> tuple[requests.Session, str]:
    env = load_env()
    key = env.get("PROD_ERP_API_KEY") or env.get("ERP_API_KEY") or ""
    secret = env.get("PROD_ERP_API_SECRET") or env.get("ERP_API_SECRET") or ""
    if not key or not secret:
        raise SystemExit("MISSING_CREDENTIALS")
    url = (env.get("ERP_URL") or "https://erpnext.vilavi.cn").rstrip("/")
    s = requests.Session()
    s.headers.update(
        {
            "Authorization": f"token {key}:{secret}",
            "Accept": "application/json",
            "Content-Type": "application/json",
        }
    )
    s.mount("https://", NoExpect())
    s.mount("http://", NoExpect())
    return s, url


def enc(name: str) -> str:
    return quote(name, safe="")


def get_doc(s: requests.Session, url: str, doctype: str, name: str) -> requests.Response:
    return s.get(f"{url}/api/resource/{doctype}/{enc(name)}", timeout=60)


def put_doc(
    s: requests.Session, url: str, doctype: str, name: str, payload: dict
) -> requests.Response:
    return s.put(f"{url}/api/resource/{doctype}/{enc(name)}", json=payload, timeout=60)


def post_doc(s: requests.Session, url: str, doctype: str, payload: dict) -> requests.Response:
    return s.post(f"{url}/api/resource/{doctype}", json=payload, timeout=60)


def get_all(
    s: requests.Session, url: str, doctype: str, fields: list[str]
) -> list[dict]:
    all_data, offset = [], 0
    while True:
        params = {
            "fields": json.dumps(fields),
            "limit_start": offset,
            "limit_page_length": 200,
        }
        r = s.get(f"{url}/api/resource/{doctype}", params=params, timeout=60)
        r.raise_for_status()
        data = r.json().get("data") or []
        if not data:
            break
        all_data.extend(data)
        if len(data) < 200:
            break
        offset += 200
    return all_data
