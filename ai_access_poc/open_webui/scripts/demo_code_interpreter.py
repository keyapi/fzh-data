#!/usr/bin/env python3
"""Demo Open WebUI Code Interpreter (Pyodide) path vs Open Terminal.

CI runs in the browser; this script:
1) Enables code_interpreter on fzh-sellfox-ops (and keeps native FC)
2) Builds a small CSV fixture CI can ingest (Pyodide has pandas, not openpyxl for Sellfox xlsx quirks)
3) Calls chat completions with features.code_interpreter=true and captures execute_code tool calls
4) Optionally locally evaluates the same analysis with host pandas (parity check)

Restore Terminal-preferred settings with --restore.
"""
from __future__ import annotations

import argparse
import csv
import json
import os
import urllib.error
import urllib.request
from pathlib import Path

BASE = os.environ.get("OWUI_BASE", "http://127.0.0.1:3000").rstrip("/")
ROOT = Path(__file__).resolve().parents[1]
FIXTURE = ROOT / "reports" / "ci_demo_search_terms.csv"
XLSX = ROOT / "reports" / "SearchTerm_TOODDLY-Daneey-US_2026-07-17_2026-07-23.xlsx"


def call(method: str, path: str, body=None, token: str | None = None, timeout: int = 240):
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
            return resp.status, {"_raw": raw[:400]}
    except urllib.error.HTTPError as e:
        raw = e.read().decode("utf-8", errors="replace")
        try:
            return e.code, json.loads(raw) if raw.lstrip().startswith(("{", "[")) else {"_raw": raw[:500]}
        except json.JSONDecodeError:
            return e.code, {"_raw": raw[:500]}


def signin() -> str:
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
    if st >= 400 or not isinstance(auth, dict):
        raise SystemExit(f"signin failed {st} {auth}")
    return auth["token"]


def update_model(tok: str, *, code_interpreter: bool) -> None:
    st, model = call("GET", "/api/v1/models/model?id=fzh-sellfox-ops", token=tok)
    meta = dict(model.get("meta") or {})
    params = dict(model.get("params") or {})
    caps = dict(meta.get("capabilities") or {})
    caps["code_interpreter"] = code_interpreter
    meta["capabilities"] = caps
    params["function_calling"] = "native"
    if code_interpreter:
        params["system"] = (
            "你是 FZH 赛狐只读分析助手。"
            "本会话使用 Code Interpreter (Pyodide)。"
            "请用 execute_code 跑 Python 完成计算；可用 pandas。"
            "不要调用 Open Terminal。不要自动否词。"
        )
    else:
        params["system"] = (
            "你是 FZH 赛狐只读分析助手。"
            "优先调用 Sellfox tools 拉数；分析时优先用返回的 summary。"
            "若需要更深分析，可用 Open Terminal 对 /data/sellfox_reports 下的 xlsx 运行 Python。"
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
    print("model_update", st, "code_interpreter=", code_interpreter, (updated or {}).get("id"))


def build_fixture() -> Path:
    import pandas as pd

    df = pd.read_excel(XLSX)
    g = (
        df.groupby("用户搜索词", as_index=False)
        .agg(
            spend=("广告花费", "sum"),
            sales=("广告销售额", "sum"),
            orders=("广告订单量", "sum"),
        )
        .sort_values("spend", ascending=False)
    )
    # Keep top spenders + some efficient terms so CI has enough to filter
    top = g.head(40)
    top.to_csv(FIXTURE, index=False, encoding="utf-8")
    print("fixture", FIXTURE, "rows", len(top))
    return FIXTURE


def local_parity(csv_path: Path) -> str:
    import pandas as pd

    df = pd.read_csv(csv_path)
    waste = df[(df.spend >= 20) & (df.orders == 0)].sort_values("spend", ascending=False).head(3)
    eff = df[df.orders >= 2].sort_values("sales", ascending=False).head(3)
    lines = ["LOCAL_PARITY"]
    lines.append("waste:\n" + waste.to_string(index=False))
    lines.append("efficient:\n" + eff.to_string(index=False))
    return "\n".join(lines)


def chat_ci(tok: str, csv_text: str) -> None:
    prompt = (
        "请启用 Code Interpreter，用 Python+pandas 分析下面 CSV 文本"
        "（列: 用户搜索词,spend,sales,orders）。\n"
        "输出：\n"
        "1) 浪费词 Top3：spend>=20 且 orders==0\n"
        "2) 高效词 Top3：orders>=2 按 sales 降序，并算 acos=spend/sales\n"
        "3) 标明引擎=Pyodide Code Interpreter，结论为只读建议\n"
        "不要说无法计算。必须调用 execute_code。\n"
        "CSV:\n"
        f"{csv_text}\n"
    )
    # Try several feature shapes used by OWUI versions
    bodies = [
        {
            "model": "fzh-sellfox-ops",
            "messages": [{"role": "user", "content": prompt}],
            "stream": False,
            "features": {"code_interpreter": True, "web_search": False},
            "tool_ids": [],
        },
        {
            "model": "fzh-sellfox-ops",
            "messages": [{"role": "user", "content": prompt}],
            "stream": False,
            "code_interpreter": True,
            "tool_ids": [],
        },
    ]
    for i, body in enumerate(bodies):
        st, out = call("POST", "/api/chat/completions", body, tok, timeout=300)
        print(f"\n--- chat attempt {i} http={st} ---")
        if not isinstance(out, dict):
            print(out)
            continue
        msg = (out.get("choices") or [{}])[0].get("message") or {}
        tcs = msg.get("tool_calls") or []
        print("tool_calls", len(tcs))
        for tc in tcs:
            fn = tc.get("function") or {}
            print("  name=", fn.get("name"))
            args = fn.get("arguments") or ""
            print("  args_preview=", args[:600])
        content = msg.get("content") or ""
        print("content_preview=\n", content[:1500])
        if tcs or content:
            return
    print("NOTE: API may only emit execute_code; actual Pyodide runs in the browser UI.")


def main() -> None:
    ap = argparse.ArgumentParser()
    ap.add_argument("--restore", action="store_true", help="Restore Terminal-preferred model caps")
    args = ap.parse_args()
    tok = signin()
    if args.restore:
        update_model(tok, code_interpreter=False)
        print("restored Terminal-preferred settings")
        return

    print("=" * 60)
    print("CI (Pyodide) DEMO")
    print("=" * 60)
    st, cfg = call("GET", "/api/config", token=tok)
    feats = (cfg or {}).get("features") or {}
    print(
        "admin_enable_code_interpreter=",
        feats.get("enable_code_interpreter"),
        "engine=",
        (cfg or {}).get("code"),
    )
    update_model(tok, code_interpreter=True)
    build_fixture()
    csv_text = FIXTURE.read_text(encoding="utf-8")
    print(local_parity(FIXTURE))
    chat_ci(tok, csv_text)
    print("\nUI steps: new chat → model FZH 赛狐 → enable Code Interpreter (NOT Terminal)")
    print(f"  attach or paste {FIXTURE.name} and ask same waste/efficient Top3")
    print("done")


if __name__ == "__main__":
    main()
