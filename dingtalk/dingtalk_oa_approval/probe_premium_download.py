# -*- coding: utf-8 -*-
"""对照实验：专享下载接口能否给离职发起人出链。只打印是否有 downloadUri，不 GET 文件。"""
from __future__ import annotations

import json
import sys
from pathlib import Path

_HERE = Path(__file__).resolve().parent
if str(_HERE) not in sys.path:
    sys.path.insert(0, str(_HERE))

from client import get_access_token, http_json, load_env
from paths import OA_DATA

MANIFEST = OA_DATA / "manifest.jsonl"
PREMIUM = "https://api.dingtalk.com/v1.0/workflow/premium/processInstances/spaces/files/urls/download"
STANDARD = "https://api.dingtalk.com/v1.0/workflow/processInstances/spaces/files/urls/download"


def first_user_not_exist() -> tuple[str, str, str]:
    by = {}
    for line in MANIFEST.read_text(encoding="utf-8").splitlines():
        rec = json.loads(line)
        pid = rec.get("processInstanceId")
        if pid:
            by[pid] = rec
    for rec in by.values():
        for e in rec.get("errors") or []:
            reason = str(e.get("reason") or "")
            if "userNotExist" not in reason:
                continue
            fid = e.get("fileId") or ""
            if rec.get("processInstanceId") and fid:
                return rec["processInstanceId"], fid, rec.get("originator") or ""
    raise SystemExit("manifest 里没有 userNotExist 样本")


def summarize(payload) -> dict:
    if not isinstance(payload, dict):
        return {"raw": str(payload)[:200]}
    result = payload.get("result") if isinstance(payload.get("result"), dict) else {}
    uri = result.get("downloadUri") or ""
    return {
        "success": payload.get("success"),
        "code": payload.get("code") or payload.get("errorCode"),
        "message": (payload.get("message") or payload.get("errorMsg") or "")[:180],
        "has_downloadUri": bool(uri and str(uri).startswith("http")),
    }


def main() -> None:
    sys.stdout.reconfigure(encoding="utf-8")
    env = load_env()
    token = get_access_token(env)
    pid, fid, who = first_user_not_exist()
    body = {"processInstanceId": pid, "fileId": fid, "withCommentAttatchment": False}
    print(f"sample originator={who} processInstanceId={pid} fileId={fid}")
    c1, p1 = http_json("POST", PREMIUM, token=token, body=body)
    print("premium", c1, summarize(p1))
    c2, p2 = http_json("POST", STANDARD, token=token, body={"processInstanceId": pid, "fileId": fid})
    print("standard", c2, summarize(p2))


if __name__ == "__main__":
    main()
