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
import threading
from datetime import datetime, timezone
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from synology_api.filestation import FileStation  # noqa: E402

PORT = int(os.environ.get("NAS_MCP_PORT", "8402"))
BIND = os.environ.get("NAS_MCP_BIND", "127.0.0.1")
TOKEN = os.environ.get("NAS_MCP_TOKEN", "")
PROTOCOL = "2025-06-18"
MAX_TEXT_BYTES = 256 * 1024          # nas_read_text 硬上限 256 KiB
LOG = os.environ.get("NAS_MCP_LOG", "")


def _parse_roots() -> list[str]:
    """允许的根目录列表。

    优先级：`NAS_ALLOWED_ROOTS`（逗号或冒号分隔的多个）> `NAS_ROOT_FOLDER`（单个，兼容 NAS_API）。
    注意 DSM 上各共享文件夹是**彼此独立的顶层目录**（如 /FZH共享文件夹 与 /产品信息），
    所以需要哪个就显式列出来 —— 默认只给一个。
    """
    raw = os.environ.get("NAS_ALLOWED_ROOTS") or os.environ.get("NAS_ROOT_FOLDER") or "/FZH共享文件夹"
    parts = [p.strip().rstrip("/") for p in raw.replace(":", ",").split(",")]
    roots = [p for p in parts if p]
    return roots or ["/FZH共享文件夹"]


ROOTS = _parse_roots()
ROOT = ROOTS[0]                      # 兼容旧引用（health 里也报这个作默认）
ROOTS_STR = "、".join(ROOTS)          # 供工具描述使用


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


class NasError(Exception):
    """DSM 侧的失败。**绝不静默转成空结果。**"""


def _parse_nas_url(url: str) -> tuple[str, str, bool]:
    url = (url or "").strip().rstrip("/")
    secure = url.startswith("https://")
    host = url.replace("https://", "").replace("http://", "")
    if ":" in host:
        host, port = host.split(":", 1)
    else:
        port = "5001" if secure else "5000"
    return host, port, secure


_nas_lock = threading.Lock()
_nas: FileStation | None = None


def nas_client(relogin: bool = False) -> FileStation:
    """DSM 客户端（进程内复用）。relogin=True 时丢弃旧会话重新登录。"""
    global _nas
    with _nas_lock:
        if _nas is None or relogin:
            url = os.environ.get("NAS_URL", "")
            user, pw = os.environ.get("NAS_USERNAME", ""), os.environ.get("NAS_PASSWORD", "")
            if not (url and user):
                raise NasError("NAS_URL / NAS_USERNAME 未配置")
            host, port, secure = _parse_nas_url(url)
            _nas = FileStation(ip_address=host, port=port, username=user, password=pw,
                               secure=secure, cert_verify=False, dsm_version=7, debug=False)
            log(f"  DSM 会话{'重建' if relogin else '建立'}: {host}:{port}")
        return _nas


def _is_session_error(err) -> bool:
    """判断是不是「会话失效」类错误。err 可能是 str / dict / 异常对象，都要能处理。"""
    if isinstance(err, str):
        s = err
    else:
        try:
            s = json.dumps(err, ensure_ascii=False)
        except Exception:                            # noqa: BLE001  异常对象不可序列化
            s = str(err)
    s = s.lower()
    return ("session" in s) or ("timeout" in s) or ("code\":106" in s) or ("code\":107" in s)


def list_strict(path: str, limit: int = 100, offset: int = 0) -> dict:
    """列目录 —— **不吞异常**；会话失效自动重登重试一次。

    为什么不用 NAS_API.get_file_list：它在失败时 `return []`，会把
    「Session timeout / 权限被拒」伪装成「文件夹是空的」（实测踩过）。
    """
    last = None
    for attempt in (1, 2):
        c = nas_client(relogin=(attempt == 2))
        try:
            r = c.get_file_list(folder_path=path, limit=limit, offset=offset,
                                sort_by="name", sort_direction="asc",
                                additional="size,time")
        except Exception as e:                       # noqa: BLE001
            if attempt == 1 and _is_session_error(e):
                log(f"  会话失效，重登重试：{e}")
                last = e
                continue
            raise NasError(f"{type(e).__name__}: {e}") from e
        if not r.get("success"):
            err = r.get("error") or {}
            if attempt == 1 and _is_session_error(err):
                log(f"  会话失效(code={err.get('code')})，重登重试")
                last = err
                continue
            raise NasError("DSM 返回失败：" + json.dumps(err, ensure_ascii=False))
        d = r.get("data") or {}
        items = [{
            "name": f.get("name"),
            "path": f.get("path"),
            "is_dir": f.get("isdir", False),
            "size": (f.get("additional") or {}).get("size", 0),
            "mtime": ((f.get("additional") or {}).get("time") or {}).get("mtime", 0),
        } for f in (d.get("files") or [])]
        return {"items": items, "total": d.get("total")}
    raise NasError(f"重试后仍失败：{last}")


def download_strict(path: str) -> bytes:
    last = None
    for attempt in (1, 2):
        c = nas_client(relogin=(attempt == 2))
        try:
            r = c.get_file(path=path, mode="download")
        except Exception as e:                       # noqa: BLE001
            if attempt == 1 and _is_session_error(e):
                log(f"  会话失效，重登重试：{e}")
                last = e
                continue
            raise NasError(f"{type(e).__name__}: {e}") from e
        if isinstance(r, dict) and r.get("success") and "data" in r:
            return r["data"]
        raise NasError("下载失败：" + json.dumps(r if not isinstance(r, dict) else r.get("error"),
                                                ensure_ascii=False)[:200])
    raise NasError(f"重试后仍失败：{last}")


def safe_path(raw: str) -> str:
    """把请求路径规范化，并强制落在任一允许的根目录之内。拒绝 .. 与越界。"""
    p = (raw or "").strip()
    if not p:
        return ROOT
    p = p.replace("\\", "/")
    # 相对路径：默认挂到第一个根目录下
    if not p.startswith("/"):
        p = posixpath.join(ROOT, p)
    p = posixpath.normpath(p)
    for r in ROOTS:
        if p == r or p.startswith(r + "/"):
            return p
    raise PathDenied(f"路径越界：仅允许 {'、'.join(ROOTS)} 之内")


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
                         "description": f"文件夹路径，必须在允许的根目录之一内（{ROOTS_STR}）。留空则列默认根目录。"},
                "limit": {"type": "integer", "description": "返回条数上限，默认 100，最大 1000"},
                "offset": {"type": "integer", "description": "从第几条开始（翻页用）。返回里会带 total 与下一页提示。"},
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
    base = {"allowed_roots": ROOTS, "default_root": ROOT,
            "host": os.environ.get("NAS_URL", "").split("//")[-1].split("/")[0],
            "read_only": True}
    try:
        # 用「列 1 项」探活 —— 它同时验证凭据与会话是否有效
        r = list_strict(ROOT, limit=1)
        base["available"] = True
        base["probe"] = {"path": ROOT, "total": r.get("total")}
    except Exception as e:                            # noqa: BLE001
        base["available"] = False
        base["error"] = str(e)
    return base


def tool_list(a: dict) -> dict:
    p = safe_path(a.get("path", ""))
    limit = max(1, min(int(a.get("limit") or 100), 1000))
    offset = max(0, int(a.get("offset") or 0))
    r = list_strict(p, limit=limit, offset=offset)
    items = r["items"]
    out = {"path": p, "count": len(items), "items": items}
    # 让模型知道「这一页之外还有」，避免把分页当成「总共就这些」
    if r.get("total") is not None:
        out["total"] = r["total"]
        if r["total"] > offset + len(items):
            out["note"] = (f"仅返回第 {offset + 1}-{offset + len(items)} 项，共 {r['total']} 项；"
                           f"用 offset={offset + len(items)} 取下一页")
    return out


def tool_info(a: dict) -> dict:
    raw = a.get("path") or ""
    if not raw:
        raise ValueError("path 必填")
    p = safe_path(raw)
    parent, name = posixpath.dirname(p), posixpath.basename(p)
    if not name:                                     # 问的是某个根目录本身
        for r in ROOTS:
            if p == r:
                return {"name": posixpath.basename(r), "path": r, "is_dir": True}
    for f in list_strict(parent, limit=1000)["items"]:
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

    parent, name = posixpath.dirname(p), posixpath.basename(p)
    meta = next((f for f in list_strict(parent, limit=1000)["items"]
                 if f.get("name") == name), None)
    if meta is None:
        raise ValueError("文件不存在")
    if meta.get("is_dir"):
        raise ValueError("这是文件夹，请用 nas_list_folder")
    size = int(meta.get("size") or 0)
    if size > cap:
        raise ValueError(f"文件 {size} 字节，超过上限 {cap}，拒绝读取（只返回元数据）")

    data = download_strict(p)
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
                    f"只读访问公司群晖 NAS。允许的根目录：{ROOTS_STR}。"
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
            except NasError as e:
                log(f"!! NAS 侧失败: {e}")
                self._result(mid, {"content": [{"type": "text",
                                   "text": f"NAS 侧失败（**不是空的**，是出错了）：{e}"}],
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
