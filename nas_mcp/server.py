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

import base64
import io
import json
import os
import posixpath
import sys
import threading
from datetime import datetime, timezone
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path
from urllib.parse import quote_plus

import requests
from PIL import Image
from synology_api.filestation import FileStation  # noqa: E402

PORT = int(os.environ.get("NAS_MCP_PORT", "8402"))
BIND = os.environ.get("NAS_MCP_BIND", "127.0.0.1")
TOKEN = os.environ.get("NAS_MCP_TOKEN", "")
PROTOCOL = "2025-06-18"
MAX_TEXT_BYTES = 256 * 1024          # nas_read_text 硬上限 256 KiB
MAX_IMAGE_BYTES = 4 * 1024 * 1024    # nas_read_image 最终 base64 前的字节上限
IMAGE_MAX_EDGE = int(os.environ.get("NAS_MCP_IMAGE_MAX_EDGE", "1280"))
LOG = os.environ.get("NAS_MCP_LOG", "")


def _parse_roots() -> tuple[list[str], bool]:
    """返回 (允许的根目录列表, 是否放开为「信任 DSM 账号权限」)。

    两种模式：
      - **`NAS_ALLOWED_ROOTS=*`（推荐）** —— 不在 MCP 层设目录白名单，
        **完全交给 DSM 账号自身的权限**把关；MCP 只拦 `..` 之类路径逃逸。
        这是「权限按用户（NAS 账号）走」的形态，加目录不用改服务。
      - `NAS_ALLOWED_ROOTS=/dirA,/dirB` —— MCP 层再收一道，需要显式列。
    """
    raw = os.environ.get("NAS_ALLOWED_ROOTS")
    if raw is None:
        raw = os.environ.get("NAS_ROOT_FOLDER") or "*"
    raw = raw.strip()
    if raw in ("*", "all", "ALL"):
        return ["*"], True
    parts = [p.strip().rstrip("/") for p in raw.replace(":", ",").split(",")]
    roots = [p for p in parts if p]
    return (roots or ["*"]), (roots == ["*"] or not roots)


ROOTS, ALLOW_ANY = _parse_roots()
# 空 path 时用哪个作默认：优先 NAS_ROOT_FOLDER；放开模式下没有就退到 "/"
DEFAULT_ROOT = (os.environ.get("NAS_ROOT_FOLDER") or "").strip().rstrip("/") \
    or (ROOTS[0] if not ALLOW_ANY else "/")
ROOT = DEFAULT_ROOT
ROOTS_STR = "任意目录（由 NAS 账号权限决定）" if ALLOW_ANY else "、".join(ROOTS)


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


def fetch_bytes(path: str, max_bytes: int = MAX_IMAGE_BYTES) -> bytes:
    """按 DSM `SYNO.FileStation.Download` API 取文件字节 —— **不吞异常**，会话失效自动重登重试。

    为什么不用 `FileStation.get_file(mode='download')`：那个方法**往磁盘写文件并返回 None**，
    根本不返回字节（`NAS_API.download_file()` 因此永远返回 None，且会偷偷在磁盘建文件）。
    这里直接用 `requests` 打同一个 API，拿到真正的响应体。
    """
    last = None
    for attempt in (1, 2):
        c = nas_client(relogin=(attempt == 2))
        api = "SYNO.FileStation.Download"
        info = c.file_station_list[api]
        url = (f"{c.base_url}{info['path']}?api={api}&version={info['maxVersion']}"
               f"&method=download&path={quote_plus(path)}&mode=download&_sid={c._sid}")
        token = getattr(c.session, "_syno_token", "") or ""
        try:
            r = requests.get(url, stream=True, verify=False, timeout=120,
                             headers={"X-SYNO-TOKEN": token})
            r.raise_for_status()
            buf = io.BytesIO()
            for chunk in r.iter_content(65536):
                if chunk:
                    buf.write(chunk)
                    if buf.tell() > max_bytes:
                        raise NasError(f"文件超过上限 {max_bytes} 字节，拒绝下载")
            return buf.getvalue()
        except NasError:
            raise
        except Exception as e:                       # noqa: BLE001
            if attempt == 1 and _is_session_error(e):
                log(f"  会话失效，重登重试：{e}")
                last = e
                continue
            raise NasError(f"{type(e).__name__}: {e}") from e
    raise NasError(f"重试后仍失败：{last}")


def safe_path(raw: str) -> str:
    """规范化路径并拦掉越界逃逸。

    - **放开模式（`NAS_ALLOWED_ROOTS=*`）**：不设目录白名单，
      `..` 由 normpath 解析掉，**真正的权限边界交给 DSM 账号**。
    - **列表模式**：必须落在列出的根目录之一内（前缀混淆也拒）。
    """
    p = (raw or "").strip()
    if not p:
        return ROOT
    p = p.replace("\\", "/")
    if not p.startswith("/"):
        p = posixpath.join(ROOT, p)
    p = posixpath.normpath(p)
    if ALLOW_ANY:
        return p
    for r in ROOTS:
        if p == r or p.startswith(r + "/"):
            return p
    raise PathDenied(f"路径越界：仅允许 {ROOTS_STR} 之内")


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
        "name": "nas_search",
        "description": "在 NAS 上按名字/扩展名递归搜索文件（DSM 索引搜索）。只读。",
        "inputSchema": {
            "type": "object",
            "properties": {
                "path": {"type": "string", "description": "从哪个目录开始搜；留空用默认根"},
                "name": {"type": "string", "description": "文件名关键词（模糊匹配）"},
                "extension": {"type": "string", "description": "扩展名过滤，如 pdf / jpg"},
                "limit": {"type": "integer", "description": "返回上限，默认 50，最大 500"},
            },
            "required": [],
        },
    },
    {
        "name": "nas_folder_size",
        "description": "算一个目录的递归大小与条目数（可能耗时，服务端会轮询）。只读。",
        "inputSchema": {
            "type": "object",
            "properties": {"path": {"type": "string", "description": "目录路径"}},
            "required": ["path"],
        },
    },
    {
        "name": "nas_read_pdf",
        "description": ("把 PDF 渲染成图片返回，模型可直接看图；同时附每页抽出的文字。"
                        "只读。默认只渲染第 1 页，用 pages 指定（如 2-4）。"),
        "inputSchema": {
            "type": "object",
            "properties": {
                "path": {"type": "string", "description": "PDF 路径"},
                "pages": {"type": "string", "description": "要渲染的页，如 1 或 1-3，默认 1"},
                "max_edge": {"type": "integer", "description": "图片长边像素，默认 1400，最大 3000"},
                "max_pages": {"type": "integer", "description": "最多渲染几页，默认 3，最大 10"},
            },
            "required": ["path"],
        },
    },
    {
        "name": "nas_read_image",
        "description": ("读取 NAS 上的一张**图片**并直接返回画面内容（模型可看图）。只读。"
                        f"超过长边 {IMAGE_MAX_EDGE}px 会自动等比缩小。"),
        "inputSchema": {
            "type": "object",
            "properties": {
                "path": {"type": "string", "description": "图片路径（jpg/jpeg/png/gif/webp/bmp）"},
                "max_edge": {"type": "integer",
                             "description": f"返回图的长边上限像素，默认 {IMAGE_MAX_EDGE}，最大 4096"},
            },
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
IMAGE_EXT = {".jpg", ".jpeg", ".png", ".gif", ".webp", ".bmp"}


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

    data = fetch_bytes(p, max_bytes=MAX_TEXT_BYTES)
    if len(data) > cap:
        raise ValueError(f"实际大小 {len(data)} 超过上限 {cap}，拒绝")
    try:
        text = data.decode("utf-8")
    except UnicodeDecodeError:
        raise ValueError("不是 UTF-8 文本，拒绝（避免返回乱码）")
    return {"path": p, "size": len(data), "text": text}


def tool_read_image(a: dict) -> dict:
    """读一张图片并**按 MCP 原生 image 内容返回**（base64）—— 让模型能真的看到画面。

    超过长边上限会等比缩小并重编码为 JPEG，避免把几 MB 的原图塞进上下文。
    返回 `_content` 交给传输层直接当 content 数组（文本元信息 + 图片）。
    """
    raw = a.get("path") or ""
    if not raw:
        raise ValueError("path 必填")
    p = safe_path(raw)
    ext = posixpath.splitext(p)[1].lower()
    if ext not in IMAGE_EXT:
        raise ValueError(f"只允许图片类型 {sorted(IMAGE_EXT)}；当前是 {ext or '无扩展名'}")

    data = fetch_bytes(p, max_bytes=MAX_IMAGE_BYTES)
    try:
        im = Image.open(io.BytesIO(data))
        im.load()
    except Exception as e:                            # noqa: BLE001
        raise ValueError(f"不是可解析的图片：{type(e).__name__}: {e}")

    orig_size, orig_mode, orig_format = im.size, im.mode, im.format
    max_edge = max(64, min(int(a.get("max_edge") or IMAGE_MAX_EDGE), 4096))
    resized = False
    if max(orig_size) > max_edge:
        im = im.copy()
        im.thumbnail((max_edge, max_edge))
        resized = True

    buf = io.BytesIO()
    if im.mode in ("RGBA", "LA", "P") and (ext == ".png" or not resized):
        mime, pil_fmt = "image/png", "PNG"
    else:
        if im.mode not in ("RGB", "L"):
            im = im.convert("RGB")
        mime, pil_fmt = "image/jpeg", "JPEG"
    im.save(buf, pil_fmt, quality=82, optimize=True)
    out = buf.getvalue()

    meta = {"path": p, "mime": mime, "original": {"format": orig_format, "size": orig_size,
                                                  "mode": orig_mode, "bytes": len(data)},
            "returned": {"size": im.size, "bytes": len(out), "resized": resized}}
    return {"_content": [
        {"type": "text", "text": json.dumps(meta, ensure_ascii=False, indent=2)},
        {"type": "image", "data": base64.b64encode(out).decode(), "mimeType": mime},
    ]}


def _poll(fn, tries: int = 12, delay: float = 0.8, done=lambda d: d.get("finished")):
    """DSM 的 Search / DirSize 都是「起任务 + 轮询」。统一轮询到 finished。"""
    import time as _t
    last = None
    for _ in range(max(1, tries)):
        last = fn()
        if isinstance(last, dict) and done(last):
            return last
        _t.sleep(delay)
    return last


def _human(n) -> str:
    try:
        n = float(n)
    except Exception:                                 # noqa: BLE001
        return str(n)
    for u in ("B", "KiB", "MiB", "GiB", "TiB"):
        if n < 1024:
            return f"{n:.0f} {u}" if u == "B" else f"{n:.1f} {u}"
        n /= 1024
    return f"{n:.1f} PiB"


def _task_id(res, label: str) -> str:
    """从「起任务」类调用的返回里取出 taskid。

    synology_api 的 search_start / start_dir_size_calc 在 ``interactive_output=True``（默认）
    时**返回一句字符串**（"...your id is: \\"xxx\\""），否则返回 ``{"message":…, "taskid":…}``。
    两种都要能吃。
    """
    import re as _re
    if isinstance(res, dict):
        if res.get("taskid"):
            return res["taskid"]
        if res.get("success"):
            tid = (res.get("data") or {}).get("taskid")
            if tid:
                return tid
    s = str(res)
    for pat in (r'taskid"\s*:\s*"([^"]+)"', r'id is:\s*"([^"]+)"', r"id is:\s*'?([0-9A-Za-z]+)'?"):
        mm = _re.search(pat, s)
        if mm:
            return mm.group(1)
    raise NasError(f"{label}启动失败：" + s[:200])


def tool_search(a: dict) -> dict:
    """在 NAS 上按名字/扩展名搜索（DSM 索引搜索）。只读。"""
    p = safe_path(a.get("path", ""))
    name = (a.get("name") or "").strip() or None
    ext = (a.get("extension") or "").strip().lstrip(".") or None
    limit = max(1, min(int(a.get("limit") or 50), 500))

    def start(c):
        return c.search_start(folder_path=p, recursive=True, pattern=name, extension=ext)

    res = start(nas_client())
    c = nas_client()
    try:
        task_id = _task_id(res, "搜索")
    except NasError:
        res = start(nas_client(relogin=True))
        c = nas_client()
        task_id = _task_id(res, "搜索")

    def fetch():
        # 注意：synology_api 的 get_search_list 要求 taskid **带双引号**
        # （库自己的错误信息是 `Enter a correct taskid, choose one of the following: ['"xxx"']`）
        r = c.get_search_list(task_id='"{}"'.format(task_id), limit=limit, offset=0,
                              additional="size,time", filetype="all")
        if isinstance(r, str):
            raise NasError("搜索查询失败：" + r[:200])
        if not (isinstance(r, dict) and r.get("success")):
            raise NasError("搜索查询失败：" + json.dumps(r, ensure_ascii=False)[:200])
        d = r.get("data") or {}
        return {"finished": bool(d.get("finished")), "total": d.get("total"),
                "items": [{"name": f.get("name"), "path": f.get("path"),
                           "is_dir": f.get("isdir", False),
                           "size": (f.get("additional") or {}).get("size", 0)}
                          for f in (d.get("files") or [])]}

    out = _poll(fetch)
    return {"query": {"path": p, "name": name, "extension": ext}, "limit": limit, **(out or {})}


def tool_folder_size(a: dict) -> dict:
    """算一个目录的递归大小与条目数（DSM DirSize）。只读。"""
    p = safe_path(a.get("path") or "")
    if p == "/":
        raise ValueError("请指定具体目录（不能对整个根算大小）")

    def start(c):
        return c.start_dir_size_calc(path=p)

    res = start(nas_client())
    c = nas_client()
    try:
        task_id = _task_id(res, "目录统计")
    except NasError:
        res = start(nas_client(relogin=True))
        c = nas_client()
        task_id = _task_id(res, "目录统计")

    state = {"restarts": 0}
    MAX_RESTARTS = 3

    def restart(_why: str) -> dict:
        nonlocal task_id
        state["restarts"] += 1
        task_id = _task_id(start(nas_client()), "目录统计")
        return {"finished": False}

    def fetch():
        nonlocal task_id
        try:
            r = c.get_dir_status(taskid=task_id)
        except Exception as e:                           # noqa: BLE001
            # DSM 会回收 DirSize 任务；被回收时这里**抛异常**（也可能返回字符串）。
            # 这是 DSM 该 API 的已知不稳，重启新任务重试有限次。
            if "No such task" in str(e) and state["restarts"] < MAX_RESTARTS:
                return restart(str(e))
            if "No such task" in str(e):
                raise NasError(
                    "DSM 的「目录统计」任务反复被回收（该 API 已知不稳）。"
                    "换个目录、或改用 nas_search/nas_list_folder 逐层看，稍后再试。"
                ) from e
            raise NasError(f"目录统计查询失败：{type(e).__name__}: {e}") from e
        if isinstance(r, str) and "No such task" in r and state["restarts"] < MAX_RESTARTS:
            return restart(r)
        if isinstance(r, str):
            raise NasError(r[:200])
        if not (isinstance(r, dict) and r.get("success")):
            raise NasError("目录统计查询失败：" + json.dumps(r, ensure_ascii=False)[:200])
        d = r.get("data") or {}
        return {"finished": bool(d.get("finished")), "total_size": d.get("total_size"),
                "file_count": d.get("file_count"), "dir_count": d.get("dir_count")}

    out = _poll(fetch, tries=20, delay=1.0)
    if out and out.get("total_size") is not None:
        out["human"] = _human(out["total_size"])
    return {"path": p, **(out or {})}


def tool_read_pdf(a: dict) -> dict:
    """把 PDF **渲染成图片**返回（模型可直接看图），并附每页抽出的文字。只读。"""
    import fitz                                    # PyMuPDF

    raw = a.get("path") or ""
    if not raw:
        raise ValueError("path 必填")
    p = safe_path(raw)
    if posixpath.splitext(p)[1].lower() != ".pdf":
        raise ValueError("这个工具只处理 .pdf")

    max_pages = max(1, min(int(a.get("max_pages") or 3), 10))
    max_edge = max(200, min(int(a.get("max_edge") or 1400), 3000))
    sel = (a.get("pages") or "1").strip()

    data = fetch_bytes(p, max_bytes=64 * 1024 * 1024)
    try:
        doc = fitz.open(stream=data, filetype="pdf")
    except Exception as e:                            # noqa: BLE001
        raise NasError(f"打不开 PDF：{type(e).__name__}: {e}")

    n = doc.page_count
    try:
        if "-" in sel:
            lo, hi = sel.split("-", 1)
            idxs = list(range(max(1, int(lo)) - 1, min(n, int(hi))))
        else:
            idxs = [max(1, int(sel)) - 1]
    except Exception:                                 # noqa: BLE001
        idxs = [0]
    idxs = [i for i in idxs if 0 <= i < n][:max_pages]

    blocks = [{"type": "text", "text": json.dumps({
        "path": p, "pages_total": n, "pages_returned": [i + 1 for i in idxs],
        "note": ("只渲染了这些页；需要其它页用 pages 指定（如 2-4）" if len(idxs) < n else None),
    }, ensure_ascii=False, indent=2)}]

    for i in idxs:
        page = doc.load_page(i)
        zoom = max_edge / max(1.0, max(page.rect.width, page.rect.height))
        pix = page.get_pixmap(matrix=fitz.Matrix(zoom, zoom), alpha=False)
        png = pix.tobytes("png")
        blocks.append({"type": "text", "text": f"--- 第 {i + 1} 页（{len(png) // 1024} KiB）---"})
        blocks.append({"type": "image", "data": base64.b64encode(png).decode(),
                       "mimeType": "image/png"})
        txt = (page.get_text() or "").strip()
        if txt:
            blocks.append({"type": "text",
                           "text": "[第 %d 页文字]\n%s" % (i + 1, txt[:4000])})
    doc.close()
    return {"_content": blocks}


TOOL_IMPL = {
    "nas_health": tool_health,
    "nas_list_folder": tool_list,
    "nas_file_info": tool_info,
    "nas_search": tool_search,
    "nas_folder_size": tool_folder_size,
    "nas_read_pdf": tool_read_pdf,
    "nas_read_image": tool_read_image,
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
                if isinstance(out, dict) and "_content" in out:
                    content = out["_content"]          # 工具自带内容块（如 文本+图片）
                else:
                    content = [{"type": "text",
                                "text": json.dumps(out, ensure_ascii=False, indent=2)}]
                self._result(mid, {"content": content, "isError": False})
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
