# -*- coding: utf-8 -*-
"""drive_folder_ops — 在共享 Google Drive 文件夹里读写 Markdown / Google Sheet。

背景
----
「FZH运营知识中心」由 mxdeals1023@gmail.com 拥有，已共享给现有服务账号
colab-gsheets@gsheets-351101.iam.gserviceaccount.com（writer）。本机日常只靠
服务账号，不需要用户 OAuth，也不需要新建凭证。

关键约束
--------
1. 服务账号只能看到显式共享给它的文件；本工具所有写入都被限制在 ROOT_FOLDER_ID 之下。
2. 服务账号没有 My Drive 存储配额，**新建普通 Markdown 文件可能返回 403
   storageQuotaExceeded**。先跑 `smoke-test --apply` 确认；被拦时明确报错，
   绝不静默改写成 Google Doc。
3. 本机解析 Google IPv6 但 IPv6 不通，且 www.googleapis.com 偶发 SSL EOF。
   因此强制 IPv4，并在重试后切换到 content.googleapis.com。
"""

from __future__ import annotations

import argparse
import hashlib
import json
import os
import pathlib
import random
import re
import socket
import sys
import time
import uuid
from typing import Any
from urllib.parse import quote

ROOT_FOLDER_ID = os.environ.get(
    "FZH_KNOWLEDGE_ROOT_ID", "1RGSCHVGlCFQz7cAdMtdL66VU45758ntp"
)
ROOT_FOLDER_NAME = "FZH运营知识中心"
DEFAULT_BACKUP_DIR = pathlib.Path.home() / ".claude" / "backups" / "drive_folder_ops"

DRIVE_BASE = "https://www.googleapis.com/drive/v3"
UPLOAD_BASE = "https://www.googleapis.com/upload/drive/v3"
SHEETS_BASE = "https://sheets.googleapis.com/v4"
FALLBACK_HOST = "https://content.googleapis.com"

SCOPES = [
    "https://www.googleapis.com/auth/drive",
    "https://www.googleapis.com/auth/spreadsheets",
]
FOLDER_MIME = "application/vnd.google-apps.folder"
SHEET_MIME = "application/vnd.google-apps.spreadsheet"
DOC_MIME = "application/vnd.google-apps.document"
MARKDOWN_MIME = "text/markdown"

META_FIELDS = (
    "id,name,mimeType,modifiedTime,size,webViewLink,parents,"
    "owners(emailAddress),"
    "permissions(id,type,role,emailAddress),"
    "capabilities(canEdit,canAddChildren,canListChildren,canShare,canTrash)"
)
RETRIES = 6


# ─────────────────────────── 基础工具 ───────────────────────────


class PathError(RuntimeError):
    """路径不存在、歧义或越界。"""


class ApiError(RuntimeError):
    def __init__(self, status: int, body: str, url: str):
        super().__init__(f"HTTP {status}: {body[:400]}")
        self.status = status
        self.body = body
        self.url = url


def _stdout_utf8() -> None:
    """Windows 控制台默认 GBK，中文输出会炸。"""
    for stream in (sys.stdout, sys.stderr):
        try:
            stream.reconfigure(encoding="utf-8")  # type: ignore[union-attr]
        except Exception:
            pass


def install_ipv4_only() -> None:
    """本机 IPv6 路由不通；强制 urllib3 只解析 IPv4。"""
    import urllib3.util.connection as u3conn

    u3conn.allowed_gai_family = lambda: socket.AF_INET


def credentials_path() -> pathlib.Path:
    """优先 GSPREAD_SERVICE_ACCOUNT_FILE，否则从脚本位置向上找父仓库 secrets/。"""
    raw = os.environ.get("GSPREAD_SERVICE_ACCOUNT_FILE", "").strip()
    if raw:
        p = pathlib.Path(raw)
        if not p.is_absolute():
            p = pathlib.Path.cwd() / p
        if not p.is_file():
            raise SystemExit(f"GSPREAD_SERVICE_ACCOUNT_FILE 指向的文件不存在: {p}")
        return p
    here = pathlib.Path(__file__).resolve()
    for parent in here.parents:  # worktree 里凭证在父仓库
        candidate = parent / "secrets" / "gsheets-service-account.json"
        if candidate.is_file():
            return candidate
    raise SystemExit(
        "找不到服务账号私钥。设置 GSPREAD_SERVICE_ACCOUNT_FILE，"
        "或把它放到仓库的 secrets/gsheets-service-account.json。"
    )


def normalize_rel_path(path: str | None) -> list[str]:
    """把 CLI 路径转为段列表；拒绝绝对路径、..、反斜杠、空段。

    `.` 表示根目录：Windows Git Bash 会把单独 `/` 转成盘符路径，所以文档统一用 `.`。
    """
    if not path:
        return []
    raw = path.strip()
    if raw in ("", "/", ".", "./"):
        return []
    if "\\" in raw:
        raise PathError("路径请用 / 分隔，不支持反斜杠")
    if re.match(r"^[A-Za-z]:", raw):
        raise PathError("不支持盘符路径")
    raw = raw.strip("/")
    if not raw:
        return []
    parts = raw.split("/")
    for part in parts:
        if part in ("", ".", ".."):
            raise PathError("路径不能包含空段、. 或 ..")
    return parts


def escape_drive_query(value: str) -> str:
    """Drive query 字符串转义。"""
    return value.replace("\\", "\\\\").replace("'", "\\'")


def sha256(raw: bytes) -> str:
    return hashlib.sha256(raw).hexdigest()


def _is_quota_error(exc: ApiError) -> bool:
    return exc.status == 403 and "storageQuotaExceeded" in exc.body


def _sleep(attempt: int, retry_after: str | None = None) -> None:
    if retry_after:
        try:
            base = min(float(retry_after), 30.0)
        except ValueError:
            base = min(0.5 * (2**attempt), 8.0)
    else:
        base = min(0.5 * (2**attempt), 8.0)
    time.sleep(base + random.uniform(0, 0.3))


# ─────────────────────────── Drive 客户端 ───────────────────────────


class DriveClient:
    def __init__(self) -> None:
        install_ipv4_only()
        from google.auth.transport.requests import Request
        from google.oauth2 import service_account
        import requests

        self._Request = Request
        self._requests = requests
        self.creds = service_account.Credentials.from_service_account_file(
            str(credentials_path()), scopes=SCOPES
        )
        self.creds.refresh(Request())
        self.session = requests.Session()

    def _token(self, force: bool = False) -> str:
        if force or not self.creds.token or self.creds.expired:
            self.creds.refresh(self._Request())
        return self.creds.token

    def request(
        self,
        method: str,
        url: str,
        *,
        params: dict | None = None,
        json_body: dict | None = None,
        data: bytes | None = None,
        headers: dict | None = None,
        expect: tuple[int, ...] | None = (200,),
    ):
        last: Exception | None = None
        for attempt in range(RETRIES):
            target = url
            if attempt >= RETRIES // 2:
                target = url.replace("https://www.googleapis.com", FALLBACK_HOST)
            req_headers = {"Authorization": f"Bearer {self._token()}"}
            if headers:
                req_headers.update(headers)
            try:
                resp = self.session.request(
                    method,
                    target,
                    params=params,
                    json=json_body,
                    data=data,
                    headers=req_headers,
                    timeout=60,
                )
            except (
                self._requests.exceptions.SSLError,
                self._requests.exceptions.ConnectionError,
                self._requests.exceptions.Timeout,
            ) as exc:
                last = exc
                _sleep(attempt)
                continue

            if resp.status_code == 401 and attempt == 0:
                self._token(force=True)
                continue
            if resp.status_code in (429, 500, 502, 503, 504) and attempt < RETRIES - 1:
                last = ApiError(resp.status_code, resp.text, target)
                _sleep(attempt, resp.headers.get("Retry-After"))
                continue
            if expect is not None and resp.status_code not in expect:
                raise ApiError(resp.status_code, resp.text, target)
            return resp
        raise ApiError(-1, f"network failure: {last}", url)

    # ── 读取 ──────────────────────────────────────────────

    def get_meta(self, file_id: str) -> dict:
        resp = self.request(
            "GET",
            f"{DRIVE_BASE}/files/{file_id}",
            params={"fields": META_FIELDS, "supportsAllDrives": "true"},
        )
        return resp.json()

    def find_child(self, parent_id: str, name: str) -> dict | None:
        q = (
            f"name = '{escape_drive_query(name)}' and "
            f"'{parent_id}' in parents and trashed=false"
        )
        resp = self.request(
            "GET",
            f"{DRIVE_BASE}/files",
            params={
                "q": q,
                "fields": f"files({META_FIELDS})",
                "supportsAllDrives": "true",
                "includeItemsFromAllDrives": "true",
                "pageSize": 100,
            },
        )
        files = resp.json().get("files", [])
        if len(files) > 1:
            lines = "\n".join(
                f"  - {f['name']} ({f['id']}) mime={f['mimeType']}" for f in files
            )
            raise PathError(f"同名项不唯一，拒绝猜测：\n{lines}")
        return files[0] if files else None

    def list_children(self, parent_id: str) -> list[dict]:
        out: list[dict] = []
        page: str | None = None
        while True:
            params: dict[str, Any] = {
                "q": f"'{parent_id}' in parents and trashed=false",
                "fields": f"nextPageToken,files({META_FIELDS})",
                "supportsAllDrives": "true",
                "includeItemsFromAllDrives": "true",
                "pageSize": 200,
            }
            if page:
                params["pageToken"] = page
            data = self.request("GET", f"{DRIVE_BASE}/files", params=params).json()
            out.extend(data.get("files", []))
            page = data.get("nextPageToken")
            if not page:
                break
        return out

    def resolve(self, parts: list[str]) -> dict:
        current = self.get_meta(ROOT_FOLDER_ID)
        if current.get("name") != ROOT_FOLDER_NAME:
            print(
                f"⚠️ 根文件夹名称是 {current.get('name')!r}，"
                f"与预期的 {ROOT_FOLDER_NAME!r} 不同；按 ID 继续。",
                file=sys.stderr,
            )
        for part in parts:
            if current["mimeType"] != FOLDER_MIME:
                raise PathError(f"路径中的 {current['name']!r} 不是文件夹")
            nxt = self.find_child(current["id"], part)
            if not nxt:
                raise PathError(f"路径不存在: {'/'.join(parts)}（缺少 {part!r}）")
            current = nxt
        return current

    def assert_under_root(self, file_id: str) -> None:
        """沿 parents 上溯，必须到达 ROOT_FOLDER_ID。"""
        if file_id == ROOT_FOLDER_ID:
            return
        seen: set[str] = set()
        current = file_id
        while current != ROOT_FOLDER_ID:
            if current in seen:
                raise PathError(f"父目录链出现循环: {file_id}")
            seen.add(current)
            meta = self.get_meta(current)
            parents = meta.get("parents") or []
            if not parents:
                raise PathError(
                    f"文件 {current}（{meta.get('name')!r}）不在 {ROOT_FOLDER_NAME} 下，拒绝写入"
                )
            current = parents[0]

    def download(self, file_id: str) -> bytes:
        resp = self.request(
            "GET",
            f"{DRIVE_BASE}/files/{file_id}",
            params={"alt": "media", "supportsAllDrives": "true"},
        )
        return resp.content

    # ── 创建 / 更新 ────────────────────────────────────────

    def create_native(self, parent_id: str, name: str, mime: str) -> dict:
        resp = self.request(
            "POST",
            f"{DRIVE_BASE}/files",
            params={"supportsAllDrives": "true", "fields": META_FIELDS},
            json_body={"name": name, "mimeType": mime, "parents": [parent_id]},
            expect=(200, 201),
        )
        return resp.json()

    def create_folder(self, parent_id: str, name: str) -> dict:
        return self.create_native(parent_id, name, FOLDER_MIME)

    def _multipart(self, metadata: dict, content: bytes, mime: str) -> tuple[bytes, str]:
        boundary = "drive_folder_ops_" + uuid.uuid4().hex
        head = (
            f"--{boundary}\r\n"
            "Content-Type: application/json; charset=UTF-8\r\n\r\n"
        ).encode("utf-8")
        mid = f"\r\n--{boundary}\r\nContent-Type: {mime}\r\n\r\n".encode("utf-8")
        tail = f"\r\n--{boundary}--\r\n".encode("utf-8")
        body = head + json.dumps(metadata, ensure_ascii=False).encode("utf-8") + mid + content + tail
        return body, f"multipart/related; boundary={boundary}"

    def create_text(self, parent_id: str, name: str, content: bytes, mime: str = MARKDOWN_MIME) -> dict:
        body, ctype = self._multipart(
            {"name": name, "mimeType": mime, "parents": [parent_id]}, content, mime
        )
        resp = self.request(
            "POST",
            f"{UPLOAD_BASE}/files",
            params={
                "uploadType": "multipart",
                "supportsAllDrives": "true",
                "fields": META_FIELDS,
            },
            data=body,
            headers={"Content-Type": ctype},
            expect=(200, 201),
        )
        return resp.json()

    def update_text(self, file_id: str, content: bytes, mime: str = MARKDOWN_MIME) -> dict:
        resp = self.request(
            "PATCH",
            f"{UPLOAD_BASE}/files/{file_id}",
            params={
                "uploadType": "media",
                "supportsAllDrives": "true",
                "fields": META_FIELDS,
            },
            data=content,
            headers={"Content-Type": mime},
            expect=(200, 201),
        )
        return resp.json()

    def trash(self, file_id: str) -> dict:
        resp = self.request(
            "PATCH",
            f"{DRIVE_BASE}/files/{file_id}",
            params={"supportsAllDrives": "true", "fields": "id,name,trashed"},
            json_body={"trashed": True},
            expect=(200,),
        )
        return resp.json()

    def export_doc(self, file_id: str) -> bytes:
        for mime in ("text/markdown", "text/plain"):
            try:
                resp = self.request(
                    "GET",
                    f"{DRIVE_BASE}/files/{file_id}/export",
                    params={"mimeType": mime},
                )
                return resp.content
            except ApiError as exc:
                if exc.status == 400 and mime != "text/plain":
                    continue
                raise
        raise ApiError(400, "无法导出 Google Doc", file_id)

    # ── Sheets ────────────────────────────────────────────

    def sheet_values(self, sheet_id: str, range_: str) -> list[list[str]]:
        resp = self.request(
            "GET",
            f"{SHEETS_BASE}/spreadsheets/{sheet_id}/values/{quote(range_, safe='')}",
        )
        return resp.json().get("values", [])

    def sheet_update(self, sheet_id: str, range_: str, values: list[list[Any]]) -> dict:
        resp = self.request(
            "PUT",
            f"{SHEETS_BASE}/spreadsheets/{sheet_id}/values/{quote(range_, safe='')}",
            params={"valueInputOption": "RAW"},
            json_body={"values": values},
        )
        return resp.json()

    def sheet_tabs(self, sheet_id: str) -> list[dict]:
        resp = self.request(
            "GET",
            f"{SHEETS_BASE}/spreadsheets/{sheet_id}",
            params={"fields": "sheets.properties"},
        )
        return [s.get("properties", {}) for s in resp.json().get("sheets", [])]


# ─────────────────────────── 命令 ───────────────────────────


def _client() -> DriveClient:
    return DriveClient()


def _describe(meta: dict) -> str:
    parts = [meta.get("mimeType", "?")]
    if meta.get("modifiedTime"):
        parts.append(f"modified={meta['modifiedTime']}")
    if meta.get("size"):
        parts.append(f"size={meta['size']}")
    return " ".join(parts)


def cmd_info(args) -> int:
    client = _client()
    parts = normalize_rel_path(args.path)
    meta = client.resolve(parts)
    print(f"名称   : {meta.get('name')}")
    print(f"ID     : {meta.get('id')}")
    print(f"类型   : {meta.get('mimeType')}")
    print(f"属主   : {[o.get('emailAddress') for o in meta.get('owners', [])]}")
    print(f"修改   : {meta.get('modifiedTime')}")
    print(f"链接   : {meta.get('webViewLink', '')}")
    print("权限   :")
    for perm in meta.get("permissions", []):
        print(f"  - {perm.get('role'):8} {perm.get('type'):8} {perm.get('emailAddress', '')}")
    print(f"能力   : {meta.get('capabilities')}")
    return 0


def cmd_list(args) -> int:
    client = _client()
    parts = normalize_rel_path(args.path)
    meta = client.resolve(parts)
    if meta["mimeType"] != FOLDER_MIME:
        print(f"[{meta.get('mimeType')}] {meta['name']} ({meta['id']})")
        return 0

    total = 0
    counts: dict[str, int] = {}
    queue: list[tuple[int, dict]] = [(0, meta)]
    while queue and total < 2000:
        depth, folder = queue.pop(0)
        try:
            children = client.list_children(folder["id"])
        except ApiError as exc:
            print(f"  [读取失败] {folder['name']}: {exc}", file=sys.stderr)
            continue
        if not children and depth == 0:
            print("(空文件夹)")
        for child in children:
            total += 1
            mime = child["mimeType"]
            counts[mime] = counts.get(mime, 0) + 1
            label = "FOLDER" if mime == FOLDER_MIME else mime.split(".")[-1]
            print(f"{'  ' * depth}[{label}] {child['name']} ({child['id']})")
            if args.recursive and mime == FOLDER_MIME and depth < 8:
                queue.append((depth + 1, child))
    print(f"\n共 {total} 项" + ("（已截断）" if total >= 2000 else ""))
    for mime, n in sorted(counts.items(), key=lambda x: -x[1]):
        print(f"  {n:5d}  {mime}")
    return 0


def cmd_read(args) -> int:
    client = _client()
    parts = normalize_rel_path(args.path)
    meta = client.resolve(parts)
    if meta["mimeType"] == FOLDER_MIME:
        raise PathError("目标是文件夹，不能 read")

    if meta["mimeType"] == SHEET_MIME:
        range_ = args.range or "A1:Z1000"
        values = client.sheet_values(meta["id"], range_)
        if args.out:
            pathlib.Path(args.out).write_text(
                json.dumps(values, ensure_ascii=False, indent=2), encoding="utf-8"
            )
            print(f"✅ 已写出 {len(values)} 行 → {args.out}")
        elif args.json:
            print(json.dumps(values, ensure_ascii=False, indent=2))
        else:
            for row in values:
                print("\t".join(str(cell) for cell in row))
        return 0

    if meta["mimeType"] == DOC_MIME:
        raw = client.export_doc(meta["id"])
    else:
        raw = client.download(meta["id"])

    if args.out:
        pathlib.Path(args.out).write_bytes(raw)
        print(f"✅ 已写出 {len(raw)} bytes → {args.out}")
    else:
        print(raw.decode("utf-8", errors="replace"), end="")
    return 0


def _ensure_parent(client: DriveClient, parts: list[str]) -> dict:
    """解析目标文件的父文件夹；父路径必须已存在。"""
    parent_parts = parts[:-1]
    parent = client.resolve(parent_parts)
    if parent["mimeType"] != FOLDER_MIME:
        raise PathError(f"父路径不是文件夹: {'/'.join(parent_parts)}")
    client.assert_under_root(parent["id"])
    return parent


def _resolve_target(client: DriveClient, path: str) -> tuple[list[str], dict | None, dict | None]:
    parts = normalize_rel_path(path)
    if not parts:
        raise PathError("目标路径不能是根目录")
    parent = _ensure_parent(client, parts)
    existing = client.find_child(parent["id"], parts[-1])
    return parts, parent, existing


def cmd_write(args) -> int:
    client = _client()
    parts, parent, existing = _resolve_target(client, args.path)
    filename = parts[-1]
    content = pathlib.Path(args.file).read_bytes()
    try:
        text = content.decode("utf-8")
    except UnicodeDecodeError as exc:
        raise PathError(f"--from 文件不是 UTF-8 文本: {exc}") from exc
    content = text.encode("utf-8")

    if existing:
        if existing["mimeType"] == FOLDER_MIME:
            raise PathError(f"目标是文件夹: {args.path}")
        if existing["mimeType"] in (SHEET_MIME, DOC_MIME):
            raise PathError(
                f"目标是 Google 原生文件（{existing['mimeType']}），不能用 Markdown 覆盖；"
                "请用 sheet-write 或另选路径"
            )
        if not args.overwrite:
            print(
                f"目标已存在: {args.path}\n"
                f"  id={existing['id']} modified={existing.get('modifiedTime')}\n"
                "未加 --overwrite，退出（退出码 2）。",
                file=sys.stderr,
            )
            return 2
        if args.expect_mtime and existing.get("modifiedTime") != args.expect_mtime:
            print(
                f"并发守卫失败：期望 modifiedTime={args.expect_mtime}，"
                f"实际 {existing.get('modifiedTime')}",
                file=sys.stderr,
            )
            return 2

        mime = existing["mimeType"] if existing["mimeType"].startswith("text/") else MARKDOWN_MIME
        planned = f"覆盖写入 {args.path}（{existing['id']}）"
        if args.apply:
            backup = DEFAULT_BACKUP_DIR / f"{existing['id']}_{time.strftime('%Y%m%d_%H%M%S')}.bak"
            backup.parent.mkdir(parents=True, exist_ok=True)
            backup.write_bytes(client.download(existing["id"]))
            res = client.update_text(existing["id"], content, mime=mime)
            print(f"✅ {planned}")
            print(f"   备份 → {backup}")
            print(f"   modifiedTime={res.get('modifiedTime')} size={res.get('size')}")
            file_id = existing["id"]
        else:
            print(f"[dry-run] 将{planned}")
            print(f"   备份将写到 {DEFAULT_BACKUP_DIR}")
            print("   加 --apply 真正写入。")
            return 0
    else:
        if not args.apply:
            print(f"[dry-run] 将在 {args.path} 新建 Markdown（{len(content)} bytes）")
            print("   加 --apply 真正写入。")
            return 0
        try:
            res = client.create_text(parent["id"], filename, content)
        except ApiError as exc:
            if _is_quota_error(exc):
                print(
                    "❌ 服务账号新建普通文件被存储配额拦截（403 storageQuotaExceeded）。\n"
                    "   这不是权限问题：服务账号没有 My Drive 存储配额。\n"
                    "   可选：\n"
                    "   1) 由 mxdeals1023 手动建一个空 .md 占位文件，Agent 再覆盖内容；\n"
                    "   2) 与用户确认后改用 Google Doc；\n"
                    "   3) 重新评估用户 OAuth（你此前已排除）。",
                    file=sys.stderr,
                )
                return 3
            raise
        print(f"✅ 已创建 {args.path}")
        print(f"   id={res.get('id')} modifiedTime={res.get('modifiedTime')}")
        file_id = res["id"]

    remote = client.download(file_id)
    if sha256(remote) != sha256(content):
        print("❌ 回读哈希不一致：写入可能被转换或截断", file=sys.stderr)
        return 1
    print(f"✅ 回读校验通过（sha256={sha256(content)[:12]}…）")
    return 0


def cmd_mkdir(args) -> int:
    client = _client()
    parts = normalize_rel_path(args.path)
    if not parts:
        print("根目录已存在")
        return 0
    current = client.get_meta(ROOT_FOLDER_ID)
    for i, part in enumerate(parts):
        existing = client.find_child(current["id"], part)
        if existing:
            if existing["mimeType"] != FOLDER_MIME:
                raise PathError(f"{'/'.join(parts[: i + 1])} 已存在但不是文件夹")
            current = existing
            continue
        if not args.apply:
            print(f"[dry-run] 将创建文件夹 {'/'.join(parts)}（从 {part!r} 起）")
            print("   加 --apply 真正创建。")
            return 0
        current = client.create_folder(current["id"], part)
        print(f"✅ 已创建文件夹 {'/'.join(parts[: i + 1])} ({current['id']})")
    return 0


def cmd_sheet_new(args) -> int:
    client = _client()
    parts, parent, existing = _resolve_target(client, args.path)
    if existing:
        raise PathError(f"目标已存在: {args.path} ({existing['id']})")
    name = args.title or parts[-1]
    if not args.apply:
        print(f"[dry-run] 将在 {args.path} 新建 Google Sheet（标题 {name!r}）")
        print("   加 --apply 真正创建。")
        return 0
    res = client.create_native(parent["id"], name, SHEET_MIME)
    print(f"✅ 已创建 Google Sheet: {args.path}")
    print(f"   id={res.get('id')} modifiedTime={res.get('modifiedTime')}")
    print(f"   下一步: sheet-write {args.path} --range A1 --values-json data.json --apply")
    return 0


def cmd_sheet_read(args) -> int:
    client = _client()
    meta = client.resolve(normalize_rel_path(args.path))
    if meta["mimeType"] != SHEET_MIME:
        raise PathError(f"不是 Google Sheet: {args.path}（{meta['mimeType']}）")
    values = client.sheet_values(meta["id"], args.range)
    if args.json:
        print(json.dumps(values, ensure_ascii=False, indent=2))
    else:
        for row in values:
            print("\t".join(str(cell) for cell in row))
    return 0


def cmd_sheet_write(args) -> int:
    client = _client()
    meta = client.resolve(normalize_rel_path(args.path))
    if meta["mimeType"] != SHEET_MIME:
        raise PathError(f"不是 Google Sheet: {args.path}（{meta['mimeType']}）")
    values = json.loads(pathlib.Path(args.values_json).read_text(encoding="utf-8"))
    if not isinstance(values, list) or not values:
        raise PathError("values JSON 必须是非空二维数组")
    if not isinstance(values[0], list):
        values = [values]
    if not args.apply:
        print(
            f"[dry-run] 将写 {meta['name']} 的 {args.range}: "
            f"{len(values)} 行 × {max(len(r) for r in values)} 列"
        )
        print("   加 --apply 真正写入。")
        return 0
    client.sheet_update(meta["id"], args.range, values)
    back = client.sheet_values(meta["id"], args.range)
    while len(back) < len(values):
        back.append([])
    ok = all(
        [str(c) for c in back[i][: len(row)]] == [str(c) for c in row]
        for i, row in enumerate(values)
    )
    if not ok:
        print("❌ 回读内容与写入不一致", file=sys.stderr)
        return 1
    print(f"✅ 已写入并回读校验通过: {meta['name']} {args.range}")
    return 0


def cmd_sheet_tabs(args) -> int:
    client = _client()
    meta = client.resolve(normalize_rel_path(args.path))
    if meta["mimeType"] != SHEET_MIME:
        raise PathError(f"不是 Google Sheet: {args.path}")
    for tab in client.sheet_tabs(meta["id"]):
        print(f"  [{tab.get('index')}] {tab.get('title')} (sheetId={tab.get('sheetId')})")
    return 0


def cmd_smoke(args) -> int:
    client = _client()
    stamp = time.strftime("%Y%m%d_%H%M%S")
    folder_name = f"_agent_smoke_{stamp}"
    print(f"将在根目录 {ROOT_FOLDER_NAME!r} 下创建临时文件夹 {folder_name!r}，测试后移入回收站。")
    print("测试项: Markdown 新建/回读、Google Sheet 新建/写读、Google Doc 新建。")
    if not args.apply:
        print("[dry-run] 加 --apply 真正执行写入烟囱测试。")
        return 0

    results: dict[str, str] = {}
    folder = client.create_folder(ROOT_FOLDER_ID, folder_name)
    print(f"✅ 临时文件夹: {folder['id']}")

    # 1. Markdown
    md_content = f"# smoke\n\ncreated={stamp}\n".encode("utf-8")
    try:
        md = client.create_text(folder["id"], "smoke.md", md_content)
        results["md_create"] = "OK"
        back = client.download(md["id"])
        results["md_readback"] = "OK" if sha256(back) == sha256(md_content) else "MISMATCH"
    except ApiError as exc:
        if _is_quota_error(exc):
            results["md_create"] = "QUOTA_BLOCKED"
        else:
            results["md_create"] = f"FAIL {exc.status}"
        results["md_readback"] = "-"

    # 2. Google Sheet
    try:
        sheet = client.create_native(folder["id"], "smoke_sheet", SHEET_MIME)
        results["sheet_create"] = "OK"
        client.sheet_update(sheet["id"], "A1", [["ping"]])
        back = client.sheet_values(sheet["id"], "A1")
        results["sheet_rw"] = "OK" if back and back[0][0] == "ping" else "MISMATCH"
    except ApiError as exc:
        results["sheet_create"] = f"FAIL {exc.status}"
        results["sheet_rw"] = "-"

    # 3. Google Doc
    try:
        client.create_native(folder["id"], "smoke_doc", DOC_MIME)
        results["doc_create"] = "OK"
    except ApiError as exc:
        results["doc_create"] = f"FAIL {exc.status}"

    # 4. 清理：回收站（非永久删除）
    try:
        client.trash(folder["id"])
        still = client.find_child(ROOT_FOLDER_ID, folder_name)
        results["cleanup"] = "OK" if still is None else "STILL_VISIBLE"
    except ApiError as exc:
        results["cleanup"] = f"FAIL {exc.status}"
        print(f"⚠️ 清理失败，请手动处理临时文件夹 {folder['id']}", file=sys.stderr)

    print("\n能力矩阵:")
    for key in ("md_create", "md_readback", "sheet_create", "sheet_rw", "doc_create", "cleanup"):
        print(f"  {key:14} {results.get(key, '-')}")

    ok = results.get("md_create") == "OK" and results.get("sheet_rw") == "OK" and results.get("cleanup") == "OK"
    if not ok:
        print(
            "\n⚠️ 未全部通过。md_create=QUOTA_BLOCKED 时，服务账号无法新建普通文件；"
            "可选：由账号属主建空 .md 占位、改用 Google Doc、或重新评估 OAuth。",
            file=sys.stderr,
        )
        return 3
    return 0


# ─────────────────────────── CLI ───────────────────────────


def build_parser() -> argparse.ArgumentParser:
    p = argparse.ArgumentParser(
        prog="drive_folder_ops",
        description="在共享 Google Drive 文件夹里读写 Markdown / Google Sheet（服务账号）",
    )
    sub = p.add_subparsers(dest="cmd", required=True)

    s = sub.add_parser("info", help="查看路径的属主、权限与能力")
    s.add_argument("path", nargs="?", default="/")
    s.set_defaults(func=cmd_info)

    s = sub.add_parser("list", help="列目录")
    s.add_argument("path", nargs="?", default="/")
    s.add_argument("--recursive", action="store_true")
    s.set_defaults(func=cmd_list)

    s = sub.add_parser("read", help="读取文本/Markdown/Sheet/Doc")
    s.add_argument("path")
    s.add_argument("--out")
    s.add_argument("--range", help="Sheet 范围，默认 A1:Z1000")
    s.add_argument("--json", action="store_true")
    s.set_defaults(func=cmd_read)

    s = sub.add_parser("write", help="新建或覆盖 Markdown（默认 dry-run）")
    s.add_argument("path")
    s.add_argument("--from", dest="file", required=True)
    s.add_argument("--overwrite", action="store_true")
    s.add_argument("--expect-mtime")
    s.add_argument("--apply", action="store_true")
    s.set_defaults(func=cmd_write)

    s = sub.add_parser("mkdir", help="创建文件夹（幂等，默认 dry-run）")
    s.add_argument("path")
    s.add_argument("--apply", action="store_true")
    s.set_defaults(func=cmd_mkdir)

    s = sub.add_parser("sheet-new", help="新建 Google Sheet（默认 dry-run）")
    s.add_argument("path")
    s.add_argument("--title")
    s.add_argument("--apply", action="store_true")
    s.set_defaults(func=cmd_sheet_new)

    s = sub.add_parser("sheet-read", help="读取 Google Sheet")
    s.add_argument("path")
    s.add_argument("--range", default="A1:Z1000")
    s.add_argument("--json", action="store_true")
    s.set_defaults(func=cmd_sheet_read)

    s = sub.add_parser("sheet-write", help="写 Google Sheet（默认 dry-run）")
    s.add_argument("path")
    s.add_argument("--range", required=True)
    s.add_argument("--values-json", required=True)
    s.add_argument("--apply", action="store_true")
    s.set_defaults(func=cmd_sheet_write)

    s = sub.add_parser("sheet-tabs", help="列出 Google Sheet 的工作表")
    s.add_argument("path")
    s.set_defaults(func=cmd_sheet_tabs)

    s = sub.add_parser("smoke-test", help="写入能力烟囱测试（默认 dry-run）")
    s.add_argument("--apply", action="store_true")
    s.set_defaults(func=cmd_smoke)

    return p


def main(argv: list[str] | None = None) -> int:
    _stdout_utf8()
    args = build_parser().parse_args(argv)
    try:
        return args.func(args)
    except PathError as exc:
        print(f"❌ {exc}", file=sys.stderr)
        return 2
    except ApiError as exc:
        print(f"❌ {exc}", file=sys.stderr)
        if exc.status == 403 and "storageQuotaExceeded" in exc.body:
            print(
                "   服务账号没有 My Drive 存储配额；普通文件新建会被拦。"
                "详见 README 的「存储配额」一节。",
                file=sys.stderr,
            )
        return 1


if __name__ == "__main__":
    raise SystemExit(main())
