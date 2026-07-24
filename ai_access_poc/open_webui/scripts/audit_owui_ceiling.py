#!/usr/bin/env python3
"""Audit OWUI capability ceiling (tools/skills/terminal/code interpreter)."""
from __future__ import annotations

import json
import os
import urllib.error
import urllib.request

BASE = os.environ.get("OWUI_BASE", "http://127.0.0.1:3000").rstrip("/")


def call(method: str, path: str, body=None, token: str | None = None):
    data = None if body is None else json.dumps(body).encode()
    headers = {"Content-Type": "application/json"}
    if token:
        headers["Authorization"] = f"Bearer {token}"
    req = urllib.request.Request(f"{BASE}{path}", data=data, headers=headers, method=method)
    try:
        with urllib.request.urlopen(req, timeout=60) as resp:
            raw = resp.read().decode("utf-8", errors="replace")
            if not raw.strip():
                return resp.status, None
            try:
                return resp.status, json.loads(raw)
            except json.JSONDecodeError:
                return resp.status, {"_raw": raw[:300]}
    except urllib.error.HTTPError as e:
        raw = e.read().decode("utf-8", errors="replace")
        try:
            return e.code, json.loads(raw) if raw.strip() else None
        except json.JSONDecodeError:
            return e.code, {"_raw": raw[:300]}


def main() -> None:
    pw = os.environ.get("OWUI_ADMIN_PASSWORD", "")
    if not pw:
        raise SystemExit("Set OWUI_ADMIN_PASSWORD")
    st, auth = call(
        "POST",
        "/api/v1/auths/signin",
        {"email": os.environ.get("OWUI_ADMIN_EMAIL", "poc-admin@vilavi.local"), "password": pw},
    )
    print("signin", st, auth.get("role") if isinstance(auth, dict) else auth)
    tok = auth["token"]

    st, tools = call("GET", "/api/v1/tools/", token=tok)
    print("tools", st, [(t.get("id"), t.get("name")) for t in (tools or [])] if isinstance(tools, list) else tools)

    for path in ("/api/v1/skills/", "/api/v1/skills", "/api/v1/skills/list"):
        st, skills = call("GET", path, token=tok)
        print("skills", path, st, type(skills).__name__)
        if isinstance(skills, list):
            for s in skills[:15]:
                print(
                    "  skill",
                    s.get("id"),
                    s.get("name") or (s.get("meta") or {}).get("name"),
                )
            break

    st, models = call("GET", "/api/v1/models/", token=tok)
    print("workspace_models", st, type(models).__name__)
    if isinstance(models, list):
        for m in models:
            mid = m.get("id")
            meta = m.get("meta") or {}
            params = m.get("params") or {}
            info = m.get("info") or {}
            print(
                "model",
                mid,
                "name=",
                m.get("name"),
                "toolIds=",
                meta.get("toolIds") or info.get("meta", {}).get("toolIds"),
                "skillIds=",
                meta.get("skillIds"),
                "capabilities=",
                meta.get("capabilities") or params.get("capabilities"),
            )
            # dump keys for one custom model
            if mid and "sellfox" in str(mid).lower() or (m.get("name") and "赛狐" in str(m.get("name"))):
                print("  keys", sorted(m.keys()))
                print("  meta", json.dumps(meta, ensure_ascii=False)[:800])
                print("  params", json.dumps(params, ensure_ascii=False)[:800])

    st, base_models = call("GET", "/api/models", token=tok)
    print("base_models", st)
    if isinstance(base_models, dict):
        data = base_models.get("data") or []
        print("base_count", len(data))
        for m in data[:8]:
            print("  base", m.get("id"))

    for path in (
        "/api/v1/terminals/",
        "/api/v1/terminals",
        "/api/config",
    ):
        st, data = call("GET", path, token=tok)
        snippet = data
        if isinstance(data, dict) and path == "/api/config":
            snippet = {
                k: data.get(k)
                for k in (
                    "features",
                    "code",
                    "code_interpreter",
                    "terminal",
                    "enable_code_interpreter",
                    "default_models",
                )
                if k in data
            }
            # also search nested
            feats = data.get("features") or {}
            snippet["features_subset"] = {
                k: feats.get(k)
                for k in feats
                if any(x in k.lower() for x in ("code", "terminal", "tool", "skill"))
            } if isinstance(feats, dict) else feats
        print("cfg", path, st, json.dumps(snippet, ensure_ascii=False)[:600] if snippet is not None else None)

    # Open Terminal health from OWUI network
    print("done")


if __name__ == "__main__":
    main()
