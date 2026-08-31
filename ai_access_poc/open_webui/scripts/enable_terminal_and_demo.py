#!/usr/bin/env python3
"""Enable Open Terminal + update FZH model; run ceiling demos."""
from __future__ import annotations

import json
import os
import urllib.error
import urllib.request
from pathlib import Path

BASE = os.environ.get("OWUI_BASE", "http://127.0.0.1:3000").rstrip("/")
ROOT = Path(__file__).resolve().parents[1]
ENV = ROOT / ".env"
KEY_TMP = ROOT / "reports" / ".terminal_key.tmp"


def load_env() -> dict[str, str]:
    out: dict[str, str] = {}
    if ENV.exists():
        for line in ENV.read_text(encoding="utf-8").splitlines():
            line = line.strip()
            if line and not line.startswith("#") and "=" in line:
                k, v = line.split("=", 1)
                out[k.strip()] = v.strip()
    return out


def call(method: str, path: str, body=None, token: str | None = None):
    data = None if body is None else json.dumps(body).encode()
    headers = {"Content-Type": "application/json"}
    if token:
        headers["Authorization"] = f"Bearer {token}"
    req = urllib.request.Request(f"{BASE}{path}", data=data, headers=headers, method=method)
    try:
        with urllib.request.urlopen(req, timeout=180) as resp:
            raw = resp.read().decode("utf-8", errors="replace")
            if not raw.strip():
                return resp.status, None
            if raw.lstrip().startswith(("{", "[")):
                return resp.status, json.loads(raw)
            return resp.status, {"_raw": raw[:200]}
    except urllib.error.HTTPError as e:
        raw = e.read().decode("utf-8", errors="replace")
        try:
            return e.code, json.loads(raw) if raw.strip().startswith(("{", "[")) else {"_raw": raw[:400]}
        except json.JSONDecodeError:
            return e.code, {"_raw": raw[:400]}


def main() -> None:
    pw = os.environ.get("OWUI_ADMIN_PASSWORD", "")
    if not pw:
        raise SystemExit("Set OWUI_ADMIN_PASSWORD")
    env = load_env()
    key = ""
    if KEY_TMP.exists():
        key = KEY_TMP.read_text(encoding="ascii").strip()
    key = key or env.get("OPEN_TERMINAL_API_KEY", "")
    if not key or "replace" in key:
        raise SystemExit("OPEN_TERMINAL_API_KEY missing")

    st, auth = call(
        "POST",
        "/api/v1/auths/signin",
        {
            "email": os.environ.get("OWUI_ADMIN_EMAIL", "poc-admin@vilavi.local"),
            "password": pw,
        },
    )
    print("signin", st)
    tok = auth["token"]

    # 1) Configure Open Terminal (admin)
    conn = {
        "id": "fzh-open-terminal",
        "name": "FZH Open Terminal",
        "enabled": True,
        "url": "http://open-terminal:8000",
        "path": "/openapi.json",
        "key": key,
        "auth_type": "bearer",
    }
    st, verify = call("POST", "/api/v1/configs/terminal_servers/verify", conn, tok)
    print("verify", st, verify)
    st, saved = call(
        "POST",
        "/api/v1/configs/terminal_servers",
        {"TERMINAL_SERVER_CONNECTIONS": [conn]},
        tok,
    )
    print("save_terminal", st, "count=", len((saved or {}).get("TERMINAL_SERVER_CONNECTIONS") or []))

    st, listed = call("GET", "/api/v1/terminals/", token=tok)
    print("terminals_visible", st, listed)

    # 2) Refresh model: keep tools+skills; enable native function calling + code interpreter caps
    st, model = call("GET", "/api/v1/models/model?id=fzh-sellfox-ops", token=tok)
    print("model_get", st, model.get("id") if isinstance(model, dict) else model)
    meta = dict(model.get("meta") or {})
    params = dict(model.get("params") or {})
    meta["toolIds"] = ["sellfox_sp_search_term_pull"]
    meta["skillIds"] = ["sellfox-search-term-pull"]
    # capabilities used by OWUI UI toggles
    caps = dict(meta.get("capabilities") or {})
    caps.update(
        {
            "code_interpreter": False,  # mutually exclusive with Open Terminal
            "web_search": False,
            "image_generation": False,
            "usage": True,
        }
    )
    meta["capabilities"] = caps
    params["function_calling"] = "native"
    params["system"] = (
        "你是 FZH 赛狐只读分析助手。"
        "优先调用 Sellfox tools 拉数；分析时优先用返回的 summary。"
        "若需要更深分析，可用 Open Terminal 对 /data/sellfox_reports 下的 xlsx 运行 Python（pandas/openpyxl）。"
        "禁止自动否词或改广告；结论须标明只读建议。"
    )
    update = {
        "id": model["id"],
        "base_model_id": model.get("base_model_id") or "deepseek-v4-flash",
        "name": model.get("name") or "FZH 赛狐只读分析 (DeepSeek Flash)",
        "meta": meta,
        "params": params,
        "access_grants": model.get("access_grants") or [],
    }
    st, updated = call("POST", "/api/v1/models/model/update", update, tok)
    if st >= 400:
        st, updated = call("POST", "/api/v1/models/update", update, tok)
    print("model_update", st, (updated or {}).get("id") if isinstance(updated, dict) else updated)

    # 3) Ceiling demos via chat completions + tool_ids
    demos = [
        (
            "shops",
            "用 sellfox_list_shops。只回复 COUNT=<n>",
        ),
        (
            "week_summary",
            "对店铺 TOODDLY-Daneey-US 拉近 7 天 SP 搜索词，并基于 summary 给出："
            "1) 总花费/销售额/ACOS 2) Top3 高花费词 3) 是否有高花费零转化词。"
            "不要说无法读 xlsx。不要否词。",
        ),
    ]
    for name, prompt in demos:
        body = {
            "model": "fzh-sellfox-ops",
            "messages": [{"role": "user", "content": prompt}],
            "stream": False,
            "tool_ids": ["sellfox_sp_search_term_pull"],
        }
        st, out = call("POST", "/api/chat/completions", body, tok)
        print("demo", name, "http", st)
        if not isinstance(out, dict):
            print("  fail", out)
            continue
        msg = (out.get("choices") or [{}])[0].get("message") or {}
        tcs = msg.get("tool_calls") or []
        print("  tool_calls", len(tcs), [((t.get("function") or {}).get("name")) for t in tcs])
        print("  content", repr((msg.get("content") or "")[:400]))
        # If tool call, execute local tool and second round for shops demo
        if name == "shops" and tcs:
            import importlib.util

            for k, v in env.items():
                os.environ.setdefault(k, v)
            spec = importlib.util.spec_from_file_location(
                "sellfox_tool", ROOT / "tools" / "sellfox_pull_sp_search_term.py"
            )
            mod = importlib.util.module_from_spec(spec)
            spec.loader.exec_module(mod)
            result = mod.Tools().sellfox_list_shops()
            msgs = [{"role": "user", "content": prompt}, msg]
            for tc in tcs:
                msgs.append(
                    {
                        "role": "tool",
                        "tool_call_id": tc.get("id"),
                        "name": (tc.get("function") or {}).get("name"),
                        "content": result,
                    }
                )
            st2, out2 = call(
                "POST",
                "/api/chat/completions",
                {
                    "model": "fzh-sellfox-ops",
                    "messages": msgs,
                    "stream": False,
                    "tool_ids": ["sellfox_sp_search_term_pull"],
                },
                tok,
            )
            msg2 = (out2.get("choices") or [{}])[0].get("message") or {}
            print("  round2", st2, repr((msg2.get("content") or "")[:200]))

    # cleanup temp key file
    try:
        KEY_TMP.unlink(missing_ok=True)
    except Exception:
        pass
    print("done")


if __name__ == "__main__":
    main()
