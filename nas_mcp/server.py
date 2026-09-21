#!/usr/bin/env python3
"""NAS MCP server — 只读地暴露群晖 NAS 的若干目录给 MCP 客户端（含 ChatGPT）。

设计要点（**安全优先**）：
  1. **只读** —— 只暴露 `list / info / read_text / health`。创建、移动、**删除一律不暴露**。
  2. **路径锁死** —— 所有路径必须落在 `NAS_ROOT_FOLDER` 之内，`..` 与软链逃逸一律拒绝。
  3. **不吐大文件** —— `nas_read_text` 有硬上限；二进制/超大文件只返回元数据。
  4. **Bearer 鉴权** —— 与 ChatGPT「访问令牌/持有者」路线一致（2026-09-21 已实测可用）。

复用了仓库里已验证的 DSM 客户端 `NAS_API/synology.py`（认证 + 范围限制）。
传输层是 stdlib 最小实现，形状与 2026-09-21 实测被 ChatGPT 成功调用的探测服务一致。

环境变量：
  NAS_URL / NAS_USERNAME / NAS_PASSWORD / NAS_ROOT_FOLDER   —— 同 NAS_API（复用其约定）
  NAS_MCP_TOKEN    必填，Bearer 令牌（**不要写进文件**）
  NAS_MCP_PORT     默认 8402
  NAS_MCP_BIND     默认 127.0.0.1（只允许本机反代访问）
"""
from __future__ import annotations

import json
import os
import posixpath
import sys
from datetime import datetime, timezone
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path

# 让 server.py 在容器里也能 import 到仓库根下的 NAS_API
sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from NAS_API.synology import get_nas  # noqa: E402

PORT = int(os.environ.get("NAS_MCP_PORT", "8402"))
BIND = os.environ.get("NAS_MCP_BIND", "127.0.0.1")
TOKEN = os.environ.get("NAS_MCP_TOKEN", "")
ROOT = (os.environ.get("NAS_ROOT_FOLDER") or "/FZH共享文件夹").rstrip("/")
PROTOCOL = "2025-06-18"
MAX_TEXT_BYTES = 256 * 1024          # nas_read_text 硬上限 256 KiB
LOG = os.environ.get("NAS_MCP_LOG", "")


def log(line: str) -> None:
    ts = datetime.now(timezone.utc).strftime("%Y-%m-%d %H:%M:%SZ")
    out = f"[{ts}] {line}"
    print(out, flush=True)
    if LOG:
        try:
            with open(LOG, "a", encoding="utf-8") as f:
                f.write(out + "\n")
        except Exception:
            pass


# ── 路径护栏 ────────────────────────────────────────────────

class PathDenied(Exception):
    pass


def safe_path(raw: str) -> str:
    """把请求路径规范化，并强制落在 ROOT 之内。拒绝 .. 与软链逃逸。"""
    p = (raw or "").strip()
    if not p:
        return ROOT
    p = p.replace("\\", "/")
    if not p.startswith("/"):
        p = posixpath.join(ROOT, p)
    p = posixpath.normpath(p)
    if not (p == ROOT or p.startswith(ROOT + "/")):
        raise PathDenied(f"路径越界：仅允许 {ROOT} 之内")
    return p


# ── 工具定义 ────────────────────────────────────────────────

TOOLS = [
    {
        "name": "nas_health",
        "description": "检查 NAS 连通性与配置的根目录。只读。",
        "inputSchema": {"type": "object", "properties": {}, "required": []},
    },
    {
        "name": "nas_list_folder",
        "description": "列出 NAS 上某个文件夹的内容（目录/文件、大小、修改时间）。只读。",
        "inputSchema": {
            "type": "object",
            "properties": {
                "path": {"type": "string",
                         "description": f"文件夹路径，必须在 {ROOT} 之内。留空则列根目录。"},
                "limit": {"type": "integer", "description": "返回条数上限，默认 100，最大 1000"},
            },
            "required": [],
        },
    },
    {
        "name": "nas_file_info",
        "description": "查询 NAS 上单个文件/文件夹的元数据（大小、修改时间）。只读，不返回内容。",
        "inputSchema": {
            "type": "object",
            "properties": {"path": {"type": "string", "description": "文件或文件夹路径"}},
            "required": ["path"],
        },
    },
    {
        "name": "nas_read_text",
        "description": (
            f"读取 NAS 上一个小**文本**文件的内容（上限 {MAX_TEXT_BYTES // 1024} KiB）。"
            "只读。二进制或超限文件会被拒绝，只建议文件。"
        ),
        "inputSchema": {
            "type": "object",
            "properties": {
                "path": {"type": "string", "description": "文本文件路径"},
                "max_bytes": {"type": "integer",
                              "description": f"最多读取字节数，默认 {MAX_TEXT_BYTES}，上限 {MAX_TEXT_BYTES}"},
            },
            "required": ["path"],
        },
    },
]

TEXT_EXT = {".txt", ".md", ".csv", ".json", ".yaml", ".yml", ".log", ".ini",
            ".conf", ".xml", ".html", ".py", ".js", ".ts", ".sql", ".toml"}


# ── 工具实现 ────────────────────────────────────────────────

def tool_health(_a: dict) -> dict:
    nas = get_nas()
    return {"available": bool(nas.available), "root": ROOT,
            "host": os.environ.get("NAS_URL", "").split("//")[-1].split("/")[0],
            "read_only": True}


def tool_list(a: dict) -> dict:
    p = safe_path(a.get("path", ""))
    limit = max(1, min(int(a.get("limit") or 100), 1000))
    items = get_nas().get_file_list(p, limit=limit)
    return {"path": p, "count": len(items), "items": items}


def tool_info(a: dict) -> dict:
    raw = a.get("path") or ""
    if not raw:
        raise ValueError("path 必填")
    p = safe_path(raw)
    parent = posixpath.dirname(p)
    name = posixpath.basename(p)
    if parent == p:                      # 直接问 ROOT 本身
        parent, name = posixpath.dirname(ROOT), posixpath.basename(ROOT)
    for f in get_nas().get_file_list(parent, limit=1000):
        if f.get("name") == name:
            return f
    return {"not_found": True, "path": p}


def tool_read_text(a: dict) -> dict:
    raw = a.get("path") or ""
    if not raw:
        raise ValueError("path 必填")
    p = safe_path(raw)
    cap = max(1, min(int(a.get("max_bytes") or MAX_TEXT_BYTES), MAX_TEXT_BYTES))
    ext = posixpath.splitext(p)[1].lower()
    if ext and ext not in TEXT_EXT:
        raise ValueError(f"只允许读取文本类文件（{ext} 不在白名单）。二进制/大文件请取元数据。")

    # 先看大小，避免把大文件拉下来
    parent, name = posixpath.dirname(p), posixpath.basename(p)
    meta = next((f for f in get_nas().get_file_list(parent, limit=1000)
                 if f.get("name") == name), None)
    if meta is None:
        raise ValueError("文件不存在")
    if meta.get("is_dir"):
        raise ValueError("这是文件夹，请用 nas_list_folder")
    size = int(meta.get("size") or 0)
    if size > cap:
        raise ValueError(f"文件 {size} 字节，超过上限 {cap}，拒绝读取（只返回元数据）")

    data = get_nas().download_file(p)
    if data is None:
        raise ValueError("读取失败")
    if len(data) > cap:
        raise ValueError(f"实际大小 {len(data)} 超过上限 {cap}，拒绝")
    try:
        text = data.decode("utf-8")
    except UnicodeDecodeError:
        raise ValueError("不是 UTF-8 文本，拒绝（避免返回乱码）")
    return {"path": p, "size": len(data), "text": text}


TOOL_IMPL = {
    "nas_health": tool_health,
    "nas_list_folder": tool_list,
    "nas_file_info": tool_info,
    "nas_read_text": tool_read_text,
}


# ── MCP 传输 ────────────────────────────────────────────────

class Handler(BaseHTTPRequestHandler):
    protocol_version = "HTTP/1.1"

    def log_message(self, *a):
        pass

    def handle_one_request(self):
        try:
            super().handle_one_request()
        except Exception as e:                      # noqa: BLE001
            log(f"!! request error: {type(e).__name__}: {e}")
            self.close_connection = True

    def _read_body(self) -> bytes:
        n = self.headers.get("Content-Length")
        return self.rfile.read(int(n)) if n else b""

    def _auth_ok(self) -> bool:
        return bool(TOKEN) and self.headers.get("Authorization", "") == f"Bearer {TOKEN}"

    def _send(self, obj, code=200):
        body = json.dumps(obj, ensure_ascii=False).encode()
        self.send_response(code)
        self.send_header("Content-Type", "application/json")
        self.send_header("Content-Length", str(len(body)))
        self.end_headers()
        try:
            self.wfile.write(body)
        except Exception:                           # noqa: BLE001
            self.close_connection = True

    def _result(self, mid, result):
        self._send({"jsonrpc": "2.0", "id": mid, "result": result})

    def _error(self, mid, code, msg):
        self._send({"jsonrpc": "2.0", "id": mid, "error": {"code": code, "message": msg}})

    def do_POST(self):
        try:
            msg = json.loads(self._read_body().decode("utf-8", "replace") or "{}")
        except Exception:
            msg = {}
        method = msg.get("method") or "?"
        mid = msg.get("id")
        ua = self.headers.get("User-Agent", "-")
        log(f"<{method}> from {ua[:40]} auth={'ok' if self._auth_ok() else 'NO'}")

        if not self._auth_ok():
            self._send({"error": "unauthorized"}, 401)
            return

        if method == "initialize":
            self._result(mid, {
                "protocolVersion": PROTOCOL,
                "capabilities": {"tools": {}},
                "serverInfo": {"name": "nas-mcp", "version": "0.1.0"},
                "instructions": (
                    f"只读访问公司群晖 NAS。根目录 {ROOT}。"
                    "只提供列目录/查元数据/读小文本文件；无任何写入或删除能力。"
                ),
            })
        elif method.startswith("notifications/"):
            self.send_response(202)
            self.send_header("Content-Length", "0")
            self.end_headers()
        elif method == "tools/list":
            self._result(mid, {"tools": TOOLS})
        elif method == "tools/call":
            params = msg.get("params") or {}
            name = params.get("name")
            args = params.get("arguments") or {}
            fn = TOOL_IMPL.get(name)
            if fn is None:
                self._error(mid, -32602, f"未知工具 {name}")
                return
            try:
                out = fn(args)
                self._result(mid, {"content": [
                    {"type": "text", "text": json.dumps(out, ensure_ascii=False, indent=2)}],
                    "isError": False})
            except PathDenied as e:
                self._result(mid, {"content": [{"type": "text", "text": f"拒绝：{e}"}],
                                   "isError": True})
            except Exception as e:                  # noqa: BLE001
                log(f"!! tool {name} error: {type(e).__name__}: {e}")
                self._result(mid, {"content": [{"type": "text", "text": f"错误：{e}"}],
                                   "isError": True})
        else:
            self._error(mid, -32601, f"unknown method {method}")

    def do_GET(self):
        if not self._auth_ok():
            self._send({"error": "unauthorized"}, 401)
            return
        self._send({"status": "ok", "server": "nas-mcp", "root": ROOT,
                    "tools": [t["name"] for t in TOOLS], "read_only": True})


if __name__ == "__main__":
    if not TOKEN:
        raise SystemExit("必须设置 NAS_MCP_TOKEN")
    log(f"=== nas-mcp 启动于 {BIND}:{PORT}（只读，root={ROOT}） ===")
    ThreadingHTTPServer((BIND, PORT), Handler).serve_forever()
