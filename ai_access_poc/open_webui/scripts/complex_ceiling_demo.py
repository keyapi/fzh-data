#!/usr/bin/env python3
"""Complex ceiling demo: audit + Tool pull/summary + Open Terminal xlsx deep dive + chat synthesis."""
from __future__ import annotations

import json
import os
import subprocess
import urllib.error
import urllib.request
from pathlib import Path

BASE = os.environ.get("OWUI_BASE", "http://127.0.0.1:3000").rstrip("/")
ROOT = Path(__file__).resolve().parents[1]


def call(method: str, path: str, body=None, token: str | None = None, timeout: int = 180):
    data = None if body is None else json.dumps(body).encode()
    headers = {"Content-Type": "application/json"}
    if token:
        headers["Authorization"] = f"Bearer {token}"
    req = urllib.request.Request(f"{BASE}{path}", data=data, headers=headers, method=method)
    try:
        with urllib.request.urlopen(req, timeout=timeout) as resp:
            raw = resp.read().decode("utf-8", errors="replace")
            if not raw.strip():
                return resp.status, None
            if raw.lstrip().startswith(("{", "[")):
                return resp.status, json.loads(raw)
            return resp.status, {"_raw": raw[:300]}
    except urllib.error.HTTPError as e:
        raw = e.read().decode("utf-8", errors="replace")
        try:
            return e.code, json.loads(raw) if raw.lstrip().startswith(("{", "[")) else {"_raw": raw[:400]}
        except json.JSONDecodeError:
            return e.code, {"_raw": raw[:400]}


def section(title: str) -> None:
    print("\n" + "=" * 60)
    print(title)
    print("=" * 60)


def main() -> None:
    pw = os.environ.get("OWUI_ADMIN_PASSWORD", "")
    if not pw:
        raise SystemExit("Set OWUI_ADMIN_PASSWORD")

    st, auth = call(
        "POST",
        "/api/v1/auths/signin",
        {
            "email": os.environ.get("OWUI_ADMIN_EMAIL", "poc-admin@vilavi.local"),
            "password": pw,
        },
    )
    tok = auth["token"]
    section("1) CAPABILITY AUDIT")

    st, cfg = call("GET", "/api/config", token=tok)
    feats = (cfg or {}).get("features") or {}
    print(
        "code_interpreter_feature=",
        feats.get("enable_code_interpreter") or feats.get("code_interpreter"),
        "code=",
        (cfg or {}).get("code"),
    )
    interesting = {
        k: feats.get(k)
        for k in sorted(feats)
        if any(x in k.lower() for x in ("code", "terminal", "tool", "skill"))
    }
    print("features_subset=", json.dumps(interesting, ensure_ascii=False))

    st, tools = call("GET", "/api/v1/tools/", token=tok)
    tool_ids = [t.get("id") for t in (tools or [])] if isinstance(tools, list) else []
    print("tools_ok=", st == 200, "ids=", tool_ids)

    skills = []
    for path in ("/api/v1/skills/", "/api/v1/skills"):
        st, skills = call("GET", path, token=tok)
        if isinstance(skills, list):
            break
    skill_ids = [s.get("id") for s in skills] if isinstance(skills, list) else []
    print("skills_ok=", isinstance(skills, list), "ids=", skill_ids)

    st, terminals = call("GET", "/api/v1/terminals/", token=tok)
    print("terminals_ok=", st == 200, "list=", terminals)

    st, model = call("GET", "/api/v1/models/model?id=fzh-sellfox-ops", token=tok)
    meta = (model or {}).get("meta") or {}
    params = (model or {}).get("params") or {}
    print(
        "model=",
        (model or {}).get("id"),
        "toolIds=",
        meta.get("toolIds"),
        "skillIds=",
        meta.get("skillIds"),
        "capabilities=",
        meta.get("capabilities"),
        "function_calling=",
        params.get("function_calling"),
    )

    section("2) OPEN TERMINAL DEEP XLSX (openpyxl, no pandas on slim)")
    r = subprocess.run(
        ["docker", "exec", "fzh-open-terminal", "python", "/data/sellfox_reports/_analyze_demo.py"],
        capture_output=True,
        text=True,
        encoding="utf-8",
        errors="replace",
    )
    print("exit=", r.returncode)
    print(r.stdout or r.stderr)

    section("3) TOOL PULL + SUMMARY (complex multi-metric)")
    # Load tool module with env from PoC .env
    env_path = ROOT / ".env"
    if env_path.exists():
        for line in env_path.read_text(encoding="utf-8").splitlines():
            line = line.strip()
            if line and not line.startswith("#") and "=" in line:
                k, v = line.split("=", 1)
                os.environ.setdefault(k.strip(), v.strip())

    import importlib.util

    spec = importlib.util.spec_from_file_location(
        "sellfox_tool", ROOT / "tools" / "sellfox_pull_sp_search_term.py"
    )
    mod = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(mod)
    tools_obj = mod.Tools()
    # Prefer summarize existing xlsx (fast); fall back to live pull if missing.
    existing = ROOT / "reports" / "SearchTerm_TOODDLY-Daneey-US_2026-07-17_2026-07-23.xlsx"
    container_path = f"/data/sellfox_reports/{existing.name}"
    if existing.exists():
        pull = tools_obj.sellfox_summarize_search_term_xlsx(str(existing))
        source = "summarize_existing"
    else:
        pull = tools_obj.sellfox_pull_sp_search_term(shop_name="TOODDLY-Daneey-US", days=7)
        source = "live_pull"
    pull_obj = json.loads(pull) if isinstance(pull, str) else pull
    print("source=", source, "ok=", (pull_obj or {}).get("ok"), "path=", container_path)
    summary = (pull_obj or {}).get("summary") or pull_obj or {}
    if "summary" in (pull_obj or {}):
        summary = pull_obj["summary"]
    print("summary.totals=", json.dumps(summary.get("totals"), ensure_ascii=False))
    top = summary.get("top_by_spend_csv") or summary.get("top_by_spend") or []
    print("top_spend_preview=", str(top)[:500])

    section("4) CHAT SYNTHESIS (model + bound tool ids, using summary facts)")
    facts = {
        "shop": "TOODDLY-Daneey-US",
        "days": 7,
        "totals": summary.get("totals"),
        "terminal_waste_and_efficient": (r.stdout or "")[-1200:],
    }
    prompt = (
        "你是赛狐只读分析助手。下面是已拉数 + Open Terminal 深挖结果（事实），"
        "请输出结构化中文结论，禁止否词/改出价，标明「只读建议」：\n"
        "A) 健康度一句话\n"
        "B) 浪费词 Top3（高花费零单）及处理建议类型（观察/人工复核）\n"
        "C) 高效词 Top3 及是否值得加预算（只谈方向）\n"
        "D) 本 PoC 能力边界：哪些靠 Tool summary、哪些靠 Terminal\n"
        f"FACTS_JSON:\n{json.dumps(facts, ensure_ascii=False)[:3500]}"
    )
    st, out = call(
        "POST",
        "/api/chat/completions",
        {
            "model": "fzh-sellfox-ops",
            "messages": [{"role": "user", "content": prompt}],
            "stream": False,
            "tool_ids": ["sellfox_sp_search_term_pull"],
        },
        tok,
        timeout=240,
    )
    print("chat_http=", st)
    if isinstance(out, dict):
        msg = (out.get("choices") or [{}])[0].get("message") or {}
        print("tool_calls=", len(msg.get("tool_calls") or []))
        print("content=\n", (msg.get("content") or "")[:2000])
    else:
        print("chat_fail=", out)

    section("5) CODE INTERPRETER vs OPEN TERMINAL")
    caps = meta.get("capabilities") or {}
    print(
        "model.code_interpreter_capability=",
        caps.get("code_interpreter"),
        "| admin feature enable_code_interpreter=",
        interesting.get("enable_code_interpreter") or interesting.get("code_interpreter"),
        "| note: OWUI mutually exclusive per chat — model prefers Terminal; CI is pyodide browser-side",
    )
    print("open_terminal_packages=openpyxl+stdlib (slim image; NO pandas/pip)")
    print("done")


if __name__ == "__main__":
    main()
