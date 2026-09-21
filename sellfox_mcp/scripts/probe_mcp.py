#!/usr/bin/env python3
"""赛狐官方 MCP 探测脚本（只读）。

用途：对 https://api-mcp.sellfox.com/mcp 做可复现的连通性 / 工具清单 / 只读调用验证。
只用标准库，不装依赖。

凭据（按需，从环境变量读，**不要写进命令行历史或文件**）：

    SF_ID / SF_SECRET      赛狐 API 账号的 App ID / App Secret
                           → 走「路径 A」鉴权头 X-Sellfox-Client-Id / X-Sellfox-Client-Secret
    SF_MCP_KEY             赛狐后台「业务设置 → 全局 → MCP管理」生成的 key
                           → 走「路径 B」鉴权头 X-MCP-Key

用法：

    uv run python sellfox_mcp/scripts/probe_mcp.py --check-token
        验证凭据有效性 + IP 白名单（直连公开 OpenAPI 取 token，不发 MCP 请求）

    uv run python sellfox_mcp/scripts/probe_mcp.py --list-tools
        建立 MCP 会话并列出全部工具（含 schema 摘要）

    uv run python sellfox_mcp/scripts/probe_mcp.py --call get_shop_page_list --args '{"page_no":"1","page_size":"5"}'
        调一个**只读**工具

    uv run python sellfox_mcp/scripts/probe_mcp.py --list-tools --auth mcp-key
        强制用路径 B（X-MCP-Key）而不是路径 A

安全护栏：

    本脚本**拒绝调用任何写工具**（edit_* / create_* / close_* / delete_* / update_*），
    除非显式加 --allow-write。赛狐 MCP 暴露的写工具会改**线上广告**，默认不碰。
    加 --allow-write 之前请确认你确实知道自己在做什么，并已在隔离店铺上验证过。
"""

from __future__ import annotations

import argparse
import json
import os
import sys
import urllib.error
import urllib.parse
import urllib.request

MCP_URL = "https://api-mcp.sellfox.com/mcp"
TOKEN_URL = "https://openapi.sellfox.com/api/oauth/v2/token.json"
PROTOCOL = "2025-06-18"

# 写工具前缀 —— 命中即拒绝，除非 --allow-write
WRITE_PREFIXES = ("edit_", "create_", "close_", "delete_", "update_", "remove_", "set_")

# 已知的只读工具白名单（用于把 --call 的默认风险降到最低）
KNOWN_READ_TOOLS = {
    "get_order_detail", "get_order_page_list", "get_shop_page_list",
    "get_custom_report_page_list", "get_online_product_page_list",
    "get_ad_download_task_page_list", "get_sp_ad_product_list",
    "get_sp_campaign_list", "get_sp_ad_group_list", "get_sp_keyword_list",
    "get_sp_product_targeting_list", "get_sp_negative_keyword_list",
    "get_sp_negative_product_targeting_list",
}

# create_ad_download_task 只建「报表下载任务」，不改广告数据；但仍归写侧，默认拒绝。
BENIGN_WRITES = {"create_ad_download_task"}


def _out(msg: str = "") -> None:
    try:
        sys.stdout.reconfigure(encoding="utf-8", errors="replace")
    except Exception:
        pass
    print(msg)


def is_write_tool(name: str) -> bool:
    return name.startswith(WRITE_PREFIXES) and name not in BENIGN_WRITES


def resolve_auth(mode: str) -> tuple[dict, str]:
    """返回 (headers, 说明)。mode: auto | api-creds | mcp-key | none"""
    cid, secret = os.environ.get("SF_ID", ""), os.environ.get("SF_SECRET", "")
    key = os.environ.get("SF_MCP_KEY", "")

    if mode == "api-creds" or (mode == "auto" and cid and secret):
        if not (cid and secret):
            raise SystemExit("需要 SF_ID / SF_SECRET 环境变量")
        return ({"X-Sellfox-Client-Id": cid, "X-Sellfox-Client-Secret": secret},
                "路径 A：X-Sellfox-Client-Id / X-Sellfox-Client-Secret（API 账号凭证）")
    if mode == "mcp-key" or (mode == "auto" and key):
        if not key:
            raise SystemExit("需要 SF_MCP_KEY 环境变量")
        return ({"X-MCP-Key": key}, "路径 B：X-MCP-Key（后台 MCP管理页）")
    return ({}, "无凭据")


def post_mcp(payload: dict, session: str | None, auth: dict) -> tuple[int, dict, str]:
    headers = {"Content-Type": "application/json",
               "Accept": "application/json, text/event-stream"}
    headers.update(auth)
    if session:
        headers["mcp-session-id"] = session
    req = urllib.request.Request(MCP_URL, data=json.dumps(payload).encode(),
                                 headers=headers, method="POST")
    try:
        with urllib.request.urlopen(req, timeout=40) as r:
            return r.status, dict(r.headers), r.read().decode("utf-8", "replace")
    except urllib.error.HTTPError as e:
        return e.code, dict(e.headers), e.read().decode("utf-8", "replace")


def parse_sse(body: str) -> list[dict]:
    out = []
    for line in body.splitlines():
        if line.startswith("data:"):
            try:
                out.append(json.loads(line[5:].strip()))
            except Exception:
                pass
    return out


def open_session(auth: dict) -> tuple[str | None, int]:
    st, hdrs, _ = post_mcp({"jsonrpc": "2.0", "id": 1, "method": "initialize",
                            "params": {"protocolVersion": PROTOCOL, "capabilities": {},
                                       "clientInfo": {"name": "sellfox-mcp-probe",
                                                      "version": "1.0.0"}}}, None, auth)
    sid = hdrs.get("mcp-session-id")
    if sid:
        post_mcp({"jsonrpc": "2.0", "method": "notifications/initialized"}, sid, auth)
    return sid, st


def cmd_check_token(_args) -> int:
    cid, secret = os.environ.get("SF_ID", ""), os.environ.get("SF_SECRET", "")
    if not (cid and secret):
        raise SystemExit("需要 SF_ID / SF_SECRET 环境变量")
    q = urllib.parse.urlencode({"client_id": cid, "client_secret": secret,
                                "grant_type": "client_credentials"})
    _out("=== 验证凭据 + IP 白名单（直连公开 OpenAPI） ===")
    _out(f"  GET {TOKEN_URL}?client_id={cid}&client_secret=…&grant_type=client_credentials")
    try:
        with urllib.request.urlopen(TOKEN_URL + "?" + q, timeout=30) as r:
            raw = r.read().decode("utf-8", "replace")
        d = json.loads(raw)
        ok = bool(d.get("access_token") or (d.get("data") or {}).get("access_token"))
        _out(f"  HTTP 200 | code={d.get('code')} msg={d.get('msg')}")
        _out(f"  取到 access_token: {ok}")
        if not ok:
            _out("  ⚠️ 凭据或 IP 白名单可能有问题，返回体：")
            _out("  " + raw[:400])
        return 0 if ok else 1
    except urllib.error.HTTPError as e:
        _out(f"  HTTP {e.code} | {e.read().decode('utf-8', 'replace')[:400]}")
        return 1
    except Exception as e:
        _out(f"  失败：{type(e).__name__}: {e}")
        return 1


def cmd_list_tools(args) -> int:
    auth, label = resolve_auth(args.auth)
    _out(f"=== MCP 工具清单（鉴权：{label}） ===")
    sid, st = open_session(auth)
    _out(f"  initialize : HTTP {st} | session: {'有' if sid else '无'}")
    if not sid:
        _out("  ⚠️ 未拿到 session，后续请求会 400。")
        return 1
    st, _, body = post_mcp({"jsonrpc": "2.0", "id": 2, "method": "tools/list",
                            "params": {}}, sid, auth)
    tools: list[dict] = []
    for m in parse_sse(body):
        tools += (m.get("result") or {}).get("tools", [])
    _out(f"  tools/list : HTTP {st} | 工具数: {len(tools)}")
    # 三分类：只读 / 非破坏性写（如只建报表任务）/ 破坏性写
    benign = [t for t in tools if t["name"] in BENIGN_WRITES]
    destructive = [t for t in tools if is_write_tool(t["name"])]
    pure_read = [t for t in tools if t not in benign and t not in destructive]
    _out(f"  只读 {len(pure_read)} / 非破坏性写 {len(benign)} / 破坏性写 {len(destructive)}")
    _out()
    _out("  --- 只读 ---")
    for t in pure_read:
        _out(f"    {t['name']}")
    if benign:
        _out()
        _out("  --- 非破坏性写（不改业务数据，但仍是写侧，本脚本默认不调用） ---")
        for t in benign:
            _out(f"    {t['name']}")
    _out()
    _out("  --- 破坏性写（会改线上广告，本脚本不会调用） ---")
    for t in destructive:
        sch = t.get("inputSchema") or {}
        req = sch.get("required") or []
        props = list((sch.get("properties") or {}).keys())
        _out(f"    {t['name']}")
        _out(f"        required={req} props={props}")
    if args.json:
        _out()
        _out("  --- 原始 schema ---")
        _out(json.dumps(tools, ensure_ascii=False, indent=2))
    return 0


def cmd_call(args) -> int:
    name = args.call
    if is_write_tool(name) and not args.allow_write:
        _out(f"拒绝：'{name}' 是写工具（会改线上广告）。")
        _out("如确需调用，加 --allow-write —— 但请先在隔离店铺上验证过。")
        return 2
    if name not in KNOWN_READ_TOOLS and not args.allow_write:
        _out(f"拒绝：'{name}' 不在已知只读白名单内。加 --allow-write 才放行。")
        return 2

    auth, label = resolve_auth(args.auth)
    payload = json.loads(args.args) if args.args else {}
    _out(f"=== 调用工具 {name}（鉴权：{label}） ===")
    _out(f"  参数：{json.dumps(payload, ensure_ascii=False)}")
    sid, st = open_session(auth)
    if not sid:
        _out("  ⚠️ 未能建立 session。")
        return 1
    st, _, body = post_mcp({"jsonrpc": "2.0", "id": 3, "method": "tools/call",
                            "params": {"name": name, "arguments": payload}}, sid, auth)
    _out(f"  HTTP {st}")
    for m in parse_sse(body):
        if "error" in m:
            _out("  ERROR: " + json.dumps(m["error"], ensure_ascii=False)[:500])
        for c in (m.get("result") or {}).get("content", []):
            _out("  " + (c.get("text") or "")[:2000])
    return 0


def main() -> int:
    p = argparse.ArgumentParser(description="赛狐官方 MCP 只读探测")
    p.add_argument("--check-token", action="store_true",
                   help="验证凭据 + IP 白名单（直连公开 OpenAPI）")
    p.add_argument("--list-tools", action="store_true", help="列出 MCP 工具")
    p.add_argument("--call", metavar="TOOL", help="调用一个只读工具")
    p.add_argument("--args", default="{}", help="--call 的 JSON 参数")
    p.add_argument("--auth", choices=("auto", "api-creds", "mcp-key", "none"),
                   default="auto", help="用哪条鉴权路径（默认 auto）")
    p.add_argument("--json", action="store_true", help="--list-tools 时附原始 schema")
    p.add_argument("--allow-write", action="store_true",
                   help="⚠️ 放行写工具/白名单外工具，默认关闭")
    a = p.parse_args()

    if a.check_token:
        return cmd_check_token(a)
    if a.list_tools:
        return cmd_list_tools(a)
    if a.call:
        return cmd_call(a)
    p.print_help()
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
