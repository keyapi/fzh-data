# -*- coding: utf-8 -*-
"""钉钉 OA 审批只读客户端（accessToken + 实例 + 附件下载）。"""
from __future__ import annotations

import json
import os
import time
import urllib.error
import urllib.request
from pathlib import Path

MODULE_DIR = Path(__file__).resolve().parent
DEFAULT_PROCESS_CODE = "PROC-FB234439-0642-451E-A514-20FBEF4A4241"


def load_env(path: Path | None = None) -> dict[str, str]:
    vals: dict[str, str] = {}
    extra = os.environ.get("DINGTALK_OA_ENV", "").strip()
    candidates = []
    if path:
        candidates.append(path)
    if extra:
        candidates.append(Path(extra))
    candidates.append(MODULE_DIR / ".env")
    for p in candidates:
        if not p.is_file():
            continue
        for raw in p.read_text(encoding="utf-8").splitlines():
            line = raw.strip()
            if not line or line.startswith("#") or "=" not in line:
                continue
            k, v = line.split("=", 1)
            vals.setdefault(k.strip(), v.strip().strip('"').strip("'"))
    return vals


def http_json(method: str, url: str, token: str | None = None, body: dict | None = None, timeout: int = 45):
    data = None if body is None else json.dumps(body).encode("utf-8")
    headers = {"Content-Type": "application/json"}
    if token:
        headers["x-acs-dingtalk-access-token"] = token
    req = urllib.request.Request(url, data=data, headers=headers, method=method)
    try:
        with urllib.request.urlopen(req, timeout=timeout) as resp:
            raw = resp.read().decode("utf-8", errors="replace")
            try:
                return resp.status, json.loads(raw)
            except json.JSONDecodeError:
                return resp.status, raw
    except urllib.error.HTTPError as e:
        raw = e.read().decode("utf-8", errors="replace")
        try:
            parsed = json.loads(raw)
        except json.JSONDecodeError:
            parsed = raw
        return e.code, parsed


def get_access_token(env: dict | None = None) -> str:
    env = env or load_env()
    app_key = env.get("DINGTALK_CLIENT_ID") or env.get("DINGTALK_APP_KEY")
    app_secret = env.get("DINGTALK_CLIENT_SECRET") or env.get("DINGTALK_APP_SECRET")
    if not app_key or not app_secret:
        raise RuntimeError("缺少 DINGTALK_CLIENT_ID / DINGTALK_CLIENT_SECRET")
    code, payload = http_json(
        "POST",
        "https://api.dingtalk.com/v1.0/oauth2/accessToken",
        body={"appKey": app_key, "appSecret": app_secret},
    )
    token = payload.get("accessToken") if isinstance(payload, dict) else None
    if not token:
        raise RuntimeError(f"accessToken 失败 http={code} body={payload}")
    return token


def list_instance_ids(token: str, process_code: str, start_ms: int, end_ms: int, sleep_s: float = 0.15) -> list[str]:
    ids: list[str] = []
    next_token: int | str = 0
    seen_ids: set[str] = set()
    seen_tokens: set[str] = set()
    for _ in range(500):
        code, payload = http_json(
            "POST",
            "https://api.dingtalk.com/v1.0/workflow/processes/instanceIds/query",
            token=token,
            body={
                "processCode": process_code,
                "startTime": start_ms,
                "endTime": end_ms,
                "nextToken": next_token,
                "maxResults": 20,
            },
        )
        if code != 200 or not isinstance(payload, dict) or not payload.get("success"):
            raise RuntimeError(f"listIds 失败 http={code} body={payload}")
        result = payload.get("result") or {}
        batch = result.get("list") or []
        for i in batch:
            if i not in seen_ids:
                seen_ids.add(i)
                ids.append(i)
        nxt = result.get("nextToken")
        if not batch:
            break
        if nxt in (None, "", 0, "0"):
            break
        token_key = str(nxt)
        if token_key in seen_tokens:
            break
        seen_tokens.add(token_key)
        next_token = int(nxt) if str(nxt).isdigit() else nxt
        time.sleep(sleep_s)
    return ids


def get_instance(token: str, process_instance_id: str) -> dict:
    code, payload = http_json(
        "GET",
        f"https://api.dingtalk.com/v1.0/workflow/processInstances?processInstanceId={process_instance_id}",
        token=token,
    )
    if code != 200 or not isinstance(payload, dict):
        raise RuntimeError(f"getInstance 失败 http={code} body={payload}")
    if payload.get("success") in (True, "true") and isinstance(payload.get("result"), dict):
        return payload["result"]
    raise RuntimeError(f"getInstance 业务失败 {payload}")


def grant_download(token: str, process_instance_id: str, file_id: str) -> dict:
    code, payload = http_json(
        "POST",
        "https://api.dingtalk.com/v1.0/workflow/processInstances/spaces/files/urls/download",
        token=token,
        body={"processInstanceId": process_instance_id, "fileId": file_id},
    )
    if code != 200 or not isinstance(payload, dict):
        raise RuntimeError(f"download 授权失败 http={code} body={payload}")
    return payload


def http_get_bytes(url: str, timeout: int = 90) -> bytes:
    req = urllib.request.Request(url, method="GET")
    with urllib.request.urlopen(req, timeout=timeout) as resp:
        return resp.read()
