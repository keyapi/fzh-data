#!/usr/bin/env python3
"""赛狐官方 MCP 探测脚本（新协议：sf_discover / sf_describe / sf_execute）。

端点：https://api-mcp.sellfox.com/mcp（streamable-http，**无状态**，不需要 mcp-session-id）

鉴权（从环境变量读，**不要写进命令行历史或文件**）：

    SF_MCP_KEY   赛狐子账号「MCP管理」生成的 key → 请求头 X-MCP-Key（路径 B，推荐）
    SF_ID/SF_SECRET  赛狐 API 账号 App ID/Secret → X-Sellfox-Client-Id/Secret（路径 A）

2026-09 时服务端暴露 23 个扁平工具；2026-11 起改为 3 个元工具 + 371 个业务工具的发现目录：

    sf_discover   按业务问句 / domain / operation 发现已发布 tool_id（不调业务接口）
    sf_describe   按 tool_id 取当前契约（大契约会被切成 contract_parts，需按 part_index 拼接并校验 SHA-256）
    sf_execute    执行一个 tool_id（必须带 sf_describe 拿到的 contract_version）

用法：

    uv run python sellfox_mcp/scripts/probe_mcp.py --list-tools
        列出 3 个元工具及其 schema

    uv run python sellfox_mcp/scripts/probe_mcp.py --catalog
        翻完整个业务工具目录（371 个），按名字粗分读/写

    uv run python sellfox_mcp/scripts/probe_mcp.py --discover "查询亚马逊利润报表" --operation read
        按业务问句发现 tool_id（limit 只能 5–20）

    uv run python sellfox_mcp/scripts/probe_mcp.py --describe get_shop_page_list
        取单个工具的当前契约（自动拼接 contract_parts）

    uv run python sellfox_mcp/scripts/probe_mcp.py --execute get_shop_page_list \
        --params '{"page_no":1,"page_size":5}'
        调用一个**只读**工具（contract_version 自动取）

    uv run python sellfox_mcp/scripts/probe_mcp.py --smoke-reads
        跑一组代表性只读工具，产出「通/不通」表格

    uv run python sellfox_mcp/scripts/probe_mcp.py --probe-writes
        对写工具做**不产生变更**的干探测：只发空参数（必填缺失 → schema 拒绝），
        证明「鉴权通 + 路由通 + 参数校验生效」，绝不发送真实修改载荷

安全护栏：

    写工具（edit_*/create_*/save_*/update_*/delete_*/close_*/confirm_*/audit_*/apply_* …）
    默认一律拒绝执行；只有 --execute 且显式 --allow-write 才放行。
    --probe-writes 只对「有必填字段」的工具发空对象，天然不可能改数据；无必填的工具直接跳过。
"""

from __future__ import annotations

import argparse
import datetime as _dt
import hashlib
import json
import os
import sys
import urllib.error
import urllib.parse
import urllib.request

MCP_URL = "https://api-mcp.sellfox.com/mcp"
TOKEN_URL = "https://openapi.sellfox.com/api/oauth/v2/token.json"
PROTOCOL = "2025-06-18"

META_TOOLS = {"sf_discover", "sf_describe", "sf_execute"}
WRITE_PREFIXES = ("edit_", "create_", "close_", "delete_", "update_", "remove_", "set_",
                  "save_", "confirm_", "audit_", "apply_", "cancel_", "upload_", "sync_",
                  "mark_", "product_update_", "allot_", "allocate_", "modify_", "batch_")

# 干探测默认样本：覆盖广告 / 订单 / 报表 / 库存 / 发货 / 商品 六个域
PROBE_WRITE_SAMPLES = [
    "edit_sp_campaign", "create_sp_campaign", "edit_sb_campaign",
    "save_fbm_package_remark", "update_fbm_package_detail",
    "update_custom_report_index", "delete_oversea_stock_order",
    "confirm_warehouse_in_orders", "create_fba_shipping_order",
    "apply_fbm_package_track_no", "product_update_local_info",
]


def _out(msg: str = "") -> None:
    try:
        sys.stdout.reconfigure(encoding="utf-8", errors="replace")
    except Exception:
        pass
    print(msg)


def is_write_tool(name: str) -> bool:
    return name.startswith(WRITE_PREFIXES)


def resolve_auth(mode: str) -> tuple[dict, str]:
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
        return ({"X-MCP-Key": key}, "路径 B：X-MCP-Key（子账号 MCP Key）")
    return ({}, "无凭据")


class MCP:
    def __init__(self, auth: dict):
        self.auth = auth
        self._inited = False

    def _post(self, payload: dict, session: str | None = None) -> tuple[int, dict, str]:
        headers = {"Content-Type": "application/json",
                   "Accept": "application/json, text/event-stream"}
        headers.update(self.auth)
        if session:
            headers["mcp-session-id"] = session
        req = urllib.request.Request(MCP_URL, data=json.dumps(payload).encode(),
                                     headers=headers, method="POST")
        try:
            with urllib.request.urlopen(req, timeout=90) as r:
                return r.status, dict(r.headers), r.read().decode("utf-8", "replace")
        except urllib.error.HTTPError as e:
            return e.code, dict(e.headers), e.read().decode("utf-8", "replace")

    @staticmethod
    def _messages(body: str) -> list[dict]:
        out = []
        for line in body.splitlines():
            if line.startswith("data:"):
                try:
                    out.append(json.loads(line[5:].strip()))
                except Exception:
                    pass
        if not out:
            try:
                out = [json.loads(body)]
            except Exception:
                pass
        return out

    def init(self) -> None:
        if self._inited:
            return
        st, hdrs, body = self._post({"jsonrpc": "2.0", "id": 1, "method": "initialize",
                                     "params": {"protocolVersion": PROTOCOL, "capabilities": {},
                                                "clientInfo": {"name": "sellfox-mcp-probe",
                                                               "version": "2.0.0"}}})
        sid = hdrs.get("mcp-session-id")
        if sid:
            self._post({"jsonrpc": "2.0", "method": "notifications/initialized"}, sid)
        if st != 200:
            raise SystemExit(f"initialize 失败：HTTP {st} {body[:200]}")
        self._inited = True
        self.session = sid

    def tool(self, name: str, args: dict, rid: int = 2) -> dict:
        self.init()
        st, _, body = self._post({"jsonrpc": "2.0", "id": rid, "method": "tools/call",
                                  "params": {"name": name, "arguments": args}},
                                 getattr(self, "session", None))
        for m in self._messages(body):
            if "error" in m:
                return {"_rpc_error": m["error"], "_http": st}
            for item in (m.get("result") or {}).get("content", []):
                text = item.get("text")
                if text:
                    try:
                        return json.loads(text)
                    except Exception:
                        return {"_text": text[:4000]}
        return {"_http": st}

    # ---- 业务封装 ----
    def discover(self, query: str, **kw) -> dict:
        args = {"query": query, "include_schema": False, "limit": 20,
                "original_user_input": query}
        args.update({k: v for k, v in kw.items() if v is not None})
        return self.tool("sf_discover", args)

    def catalog(self) -> dict[str, str]:
        """翻完全部业务工具目录，返回 {tool_id: display_name}。"""
        ids: dict[str, str] = {}
        cursor, page = None, 0
        while page < 40:
            args = {"query": "列出全部已发布能力", "include_schema": False, "limit": 20,
                    "original_user_input": "列出全部已发布能力"}
            if cursor:
                args["cursor"] = cursor
            d = self.tool("sf_discover", args, 10 + page)
            for c in d.get("candidates") or []:
                tid = c.get("tool_id")
                if tid:
                    ids[tid] = c.get("display_name", "")
            cursor = d.get("next_cursor")
            page += 1
            if not cursor:
                break
        return ids

    def describe(self, tool_id: str, detail: bool = False) -> dict:
        """取单个工具契约；自动按 part_index 拼接 contract_parts 并校验 SHA-256。"""
        parts: dict[tuple, dict] = {}
        cursor, page = None, 0
        while page < 20:
            args = {"tool_ids": [tool_id], "detail": detail}
            if cursor:
                args["cursor"] = cursor
            d = self.tool("sf_describe", args, 30 + page)
            if d.get("tools"):
                return d["tools"][0]
            for p in d.get("contract_parts") or []:
                parts[(p["contract_version"], p["sha256"], p["part_index"])] = p
            cursor = d.get("next_cursor")
            page += 1
            if not cursor:
                break
        groups: dict[tuple, dict] = {}
        for (ver, sha, idx), p in parts.items():
            groups.setdefault((ver, sha), {})[idx] = p
        if not groups:
            return {}
        (ver, sha), pmap = next(iter(groups.items()))
        concat = "".join(pmap[i]["json_fragment"] for i in sorted(pmap))
        ok = hashlib.sha256(concat.encode()).hexdigest() == sha
        obj = json.loads(concat)
        schema = obj.get("inputSchema") or obj.get("input_schema") or obj
        return {"tool_id": tool_id, "contract_version": ver, "inputSchema": schema,
                "_assembled": True, "_parts": len(pmap), "_sha_ok": ok}

    def execute(self, tool_id: str, params: dict, contract_version: str | None = None) -> dict:
        if not contract_version:
            t = self.describe(tool_id)
            if not t:
                return {"status": "failed", "message": "无法取到契约（tool_id 可能未发布）"}
            contract_version = t.get("contract_version")
        return self.tool("sf_execute", {"tool_id": tool_id, "params": params,
                                         "contract_version": contract_version})


# ---------------- 命令实现 ----------------

def cmd_check_token(_a) -> int:
    cid, secret = os.environ.get("SF_ID", ""), os.environ.get("SF_SECRET", "")
    if not (cid and secret):
        raise SystemExit("需要 SF_ID / SF_SECRET 环境变量")
    q = urllib.parse.urlencode({"client_id": cid, "client_secret": secret,
                                "grant_type": "client_credentials"})
    _out("=== 验证凭据 + IP 白名单（直连公开 OpenAPI） ===")
    try:
        with urllib.request.urlopen(TOKEN_URL + "?" + q, timeout=30) as r:
            d = json.loads(r.read().decode("utf-8", "replace"))
        ok = bool(d.get("access_token") or (d.get("data") or {}).get("access_token"))
        _out(f"  HTTP 200 | code={d.get('code')} msg={d.get('msg')} | token: {ok}")
        return 0 if ok else 1
    except urllib.error.HTTPError as e:
        _out(f"  HTTP {e.code} | {e.read().decode('utf-8', 'replace')[:300]}")
        return 1


def cmd_list_tools(a) -> int:
    auth, label = resolve_auth(a.auth)
    m = MCP(auth)
    _out(f"=== MCP 元工具清单（鉴权：{label}） ===")
    m.init()
    st, _, body = m._post({"jsonrpc": "2.0", "id": 2, "method": "tools/list", "params": {}},
                          getattr(m, "session", None))
    tools = []
    for msg in m._messages(body):
        tools += (msg.get("result") or {}).get("tools", [])
    _out(f"  HTTP {st} | 工具数: {len(tools)}")
    for t in tools:
        sch = t.get("inputSchema") or {}
        _out(f"  - {t['name']} | required={sch.get('required')} props={list((sch.get('properties') or {}).keys())}")
        _out(f"      {(t.get('description') or '').splitlines()[0][:160]}")
    if a.json:
        _out(json.dumps(tools, ensure_ascii=False, indent=2))
    return 0


def cmd_catalog(a) -> int:
    auth, label = resolve_auth(a.auth)
    m = MCP(auth)
    _out(f"=== 业务工具目录（鉴权：{label}） ===")
    ids = m.catalog()
    writes = sorted(k for k in ids if is_write_tool(k))
    _out(f"  总计 {len(ids)} 个业务工具 | 读 {len(ids) - len(writes)} / 写 {len(writes)}")
    if a.json:
        _out(json.dumps(ids, ensure_ascii=False, indent=2))
    else:
        _out("\n  --- 写工具（会改业务数据） ---")
        for k in writes:
            _out(f"    {k} | {ids[k]}")
    return 0


def cmd_discover(a) -> int:
    auth, label = resolve_auth(a.auth)
    m = MCP(auth)
    _out(f"=== sf_discover（鉴权：{label}） ===")
    d = m.discover(a.discover, domain=a.domain, operation=a.operation, limit=a.limit)
    _out(f"  status={d.get('status')} matched={d.get('matched_count')} "
         f"returned={d.get('returned_count')} mode={d.get('retrieval_mode')}")
    for c in d.get("candidates") or []:
        _out(f"    {c.get('tool_id')} | {c.get('display_name')}")
    if a.json:
        _out(json.dumps(d, ensure_ascii=False, indent=2)[:20000])
    return 0


def cmd_describe(a) -> int:
    auth, label = resolve_auth(a.auth)
    m = MCP(auth)
    _out(f"=== sf_describe {a.describe}（鉴权：{label}） ===")
    t = m.describe(a.describe, detail=a.detail)
    if not t:
        _out("  未取到契约：该 tool_id 可能不在当前目录，或契约分片不完整。")
        return 1
    sch = t.get("inputSchema") or {}
    _out(f"  contract_version={t.get('contract_version')}")
    _out(f"  required={sch.get('required')}")
    _out(f"  properties={list((sch.get('properties') or {}).keys())}")
    if a.json:
        _out(json.dumps(t, ensure_ascii=False, indent=2)[:20000])
    return 0


def cmd_execute(a) -> int:
    name = a.execute
    if is_write_tool(name) and not a.allow_write:
        _out(f"拒绝：'{name}' 是写工具（会改业务数据）。")
        _out("如确需调用，加 --allow-write —— 但请先确认范围并备份。")
        return 2
    params = json.loads(a.params) if a.params else {}
    auth, label = resolve_auth(a.auth)
    m = MCP(auth)
    _out(f"=== sf_execute {name}（鉴权：{label}） ===")
    _out(f"  参数：{json.dumps(params, ensure_ascii=False)[:400]}")
    d = m.execute(name, params, a.contract_version)
    if "_rpc_error" in d:
        _out("  RPC_ERROR: " + json.dumps(d["_rpc_error"], ensure_ascii=False)[:400])
        return 1
    _out(f"  status={d.get('status')} error_code={d.get('error_code')} "
         f"message={(d.get('message') or '')[:200]}")
    data = d.get("data")
    if isinstance(data, dict):
        rows = next((data[k] for k in ("rows", "list", "records", "items") if isinstance(data.get(k), list)), None)
        if rows is not None:
            _out(f"  rows={len(rows)} total={data.get('total_count')} "
                 f"row_keys={list(rows[0].keys())[:12] if rows else []}")
    return 0 if d.get("status") == "complete" else 1


def cmd_smoke_reads(a) -> int:
    auth, label = resolve_auth(a.auth)
    m = MCP(auth)
    end = _dt.date.today()
    begin = end - _dt.timedelta(days=30)
    _out(f"=== 只读冒烟（鉴权：{label}） ===")

    shops = m.execute("get_shop_page_list", {"page_no": 1, "page_size": 5})
    rows = (shops.get("data") or {}).get("rows") or []
    _out(f"  店铺           status={shops.get('status')} rows={len(rows)} "
         f"total={(shops.get('data') or {}).get('total_count')}")
    shop_id = (rows[0].get("id") if rows else None) or ""

    cases = [
        ("订单", "get_order_page_list", {"page_no": 1, "page_size": 20,
                                        "date_start": f"{begin} 00:00:00",
                                        "date_end": f"{end} 23:59:59"}),
        ("利润", "get_profit_report_by_order", {"begin": str(begin), "end": str(end),
                                               "page_no": 1, "page_size": 20}),
        ("库存", "query_platform_warehouse_full_inventory", {"page_no": 1, "page_size": 20}),
    ]
    if shop_id:
        cases.append(("SP广告活动", "get_sp_campaign_list",
                      {"shop_id": shop_id, "page_size": 20}))
    for tag, tid, params in cases:
        d = m.execute(tid, params)
        rows = (d.get("data") or {}).get("rows") or []
        _out(f"  {tag:<8s} status={d.get('status')} rows={len(rows)} "
             f"total={(d.get('data') or {}).get('total_count')} "
             f"msg={(d.get('message') or '')[:80]}")
    return 0


def cmd_probe_writes(a) -> int:
    auth, label = resolve_auth(a.auth)
    m = MCP(auth)
    samples = [s.strip() for s in a.tools.split(",") if s.strip()] if a.tools else PROBE_WRITE_SAMPLES
    _out(f"=== 写工具干探测（鉴权：{label}） ===")
    _out("  规则：只对有必填字段的工具发空参数 → 必被 schema 拒绝；无必填的直接跳过。")
    ok = skipped = failed = 0
    for tid in samples:
        t = m.describe(tid)
        if not t:
            _out(f"  {tid:<34s} NO_CONTRACT（目录有但契约取不到）")
            failed += 1
            continue
        required = (t.get("inputSchema") or {}).get("required") or []
        if not required:
            _out(f"  {tid:<34s} SKIP（无必填字段，空参数不安全）")
            skipped += 1
            continue
        d = m.execute(tid, {}, t.get("contract_version"))
        ec = str(d.get("error_code"))
        blocked = ec in ("40027", "401", "403")
        verdict = ("AUTH_BLOCKED" if blocked
                   else "SCHEMA_VALIDATED_OK" if d.get("status") == "failed"
                   else f"UNEXPECTED({d.get('status')})")
        _out(f"  {tid:<34s} {verdict:<20s} ec={d.get('error_code')} required={required[:3]}")
        if blocked:
            failed += 1
        elif verdict == "SCHEMA_VALIDATED_OK":
            ok += 1
        else:
            failed += 1
    _out(f"\n  汇总：通 {ok} / 跳过 {skipped} / 异常 {failed}")
    return 0 if failed == 0 else 1


def main() -> int:
    p = argparse.ArgumentParser(description="赛狐官方 MCP 探测（sf_discover/describe/execute）")
    p.add_argument("--check-token", action="store_true", help="验证 API 账号凭据 + IP 白名单")
    p.add_argument("--list-tools", action="store_true", help="列出 3 个元工具")
    p.add_argument("--catalog", action="store_true", help="翻完业务工具目录并分类读写")
    p.add_argument("--discover", metavar="QUERY", help="按业务问句发现 tool_id")
    p.add_argument("--describe", metavar="TOOL_ID", help="取单个工具的当前契约")
    p.add_argument("--execute", metavar="TOOL_ID", help="执行一个工具（写工具需 --allow-write）")
    p.add_argument("--params", default="{}", help="--execute 的 JSON 参数")
    p.add_argument("--contract-version", default=None, help="--execute 显式指定契约版本")
    p.add_argument("--smoke-reads", action="store_true", help="跑一组代表性只读工具")
    p.add_argument("--probe-writes", action="store_true", help="写工具空参数干探测（不产生变更）")
    p.add_argument("--tools", default=None, help="--probe-writes 的自定义 tool_id 列表（逗号分隔）")
    p.add_argument("--domain", default=None, help="--discover 的 domain 收窄")
    p.add_argument("--operation", choices=("read", "write"), default=None,
                   help="--discover 的操作类型收窄")
    p.add_argument("--limit", type=int, default=20, help="--discover 返回条数（5–20）")
    p.add_argument("--detail", action="store_true", help="--describe 取字段说明")
    p.add_argument("--auth", choices=("auto", "api-creds", "mcp-key", "none"),
                   default="auto", help="鉴权路径（默认 auto）")
    p.add_argument("--json", action="store_true", help="输出原始 JSON")
    p.add_argument("--allow-write", action="store_true",
                   help="⚠️ 放行 --execute 的写工具，默认关闭")
    a = p.parse_args()

    if a.check_token:
        return cmd_check_token(a)
    if a.list_tools:
        return cmd_list_tools(a)
    if a.catalog:
        return cmd_catalog(a)
    if a.discover:
        return cmd_discover(a)
    if a.describe:
        return cmd_describe(a)
    if a.execute:
        return cmd_execute(a)
    if a.smoke_reads:
        return cmd_smoke_reads(a)
    if a.probe_writes:
        return cmd_probe_writes(a)
    p.print_help()
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
