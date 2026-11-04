# -*- coding: utf-8 -*-
"""消息归一化：识别文件、钉钉文档链接，并生成安全的归档文件名。"""
from __future__ import annotations

import hashlib
import re
from dataclasses import dataclass
from pathlib import Path
from typing import Any

URL_RE = re.compile(r"https?://[^\s<>()\[\]{}\"'，。；、]+")
DOC_MARKERS = (
    "alidocs.dingtalk.com",
    "docs.dingtalk.com",
    "dingtalk.com/doc",
    "dingtalk.com/i/nodes",
)
IGNORED_HOSTS = ("n.dingtalk.com", "static.dingtalk.com")
ILLEGAL = re.compile(r'[<>:"/\\|?*\x00-\x1f]')
TEXT_SUFFIXES = {".md", ".markdown", ".txt"}


@dataclass
class FileRef:
    message_id: str
    resource_id: str
    resource_type: str
    name: str
    sender: str
    time: str
    content_type: str


def extract_doc_links(text: str) -> list[str]:
    links: list[str] = []
    for url in URL_RE.findall(text or ""):
        if any(host in url for host in IGNORED_HOSTS):
            continue
        if any(marker in url for marker in DOC_MARKERS):
            if url not in links:
                links.append(url)
    return links


def message_files(message: dict[str, Any]) -> list[FileRef]:
    refs: list[FileRef] = []
    for ref in message.get("resourceRefs") or []:
        name = (ref.get("name") or "").strip()
        resource_id = ref.get("resourceId") or ""
        resource_type = ref.get("resourceIdType") or ref.get("type") or "fileId"
        content_type = (ref.get("contentType") or "").lower()
        is_file = content_type == "file" or (resource_type == "fileId" and bool(name))
        if not is_file or not resource_id:
            continue
        refs.append(
            FileRef(
                message_id=message.get("messageId", ""),
                resource_id=resource_id,
                resource_type=resource_type,
                name=name or f"file_{resource_id[-8:]}",
                sender=message.get("sender", ""),
                time=message.get("createTime", ""),
                content_type=content_type,
            )
        )
    return refs


def message_media(message: dict[str, Any]) -> list[FileRef]:
    refs: list[FileRef] = []
    for ref in message.get("resourceRefs") or []:
        resource_id = ref.get("resourceId") or ""
        if not resource_id:
            continue
        content_type = (ref.get("contentType") or "").lower()
        if content_type == "file" or ref.get("resourceIdType") == "fileId":
            continue
        media_type = ref.get("type") or ref.get("resourceIdType") or "mediaId"
        refs.append(
            FileRef(
                message_id=message.get("messageId", ""),
                resource_id=resource_id,
                resource_type=media_type,
                name=ref.get("name") or f"media_{hashlib.md5(resource_id.encode()).hexdigest()[:8]}",
                sender=message.get("sender", ""),
                time=message.get("createTime", ""),
                content_type=content_type or "media",
            )
        )
    return refs


def safe_filename(name: str, *, sender: str = "", time: str = "", max_len: int = 120) -> str:
    stem = ILLEGAL.sub("_", name or "file").strip().rstrip(".")
    if not stem:
        stem = "file"
    suffix = Path(stem).suffix
    base = stem[: max_len - len(suffix)] if len(stem) > max_len else stem
    if sender or time:
        stamp = time.replace("-", "").replace(":", "").replace(" ", "_")[:15]
        who = ILLEGAL.sub("_", sender or "unknown")[:20]
        base = f"{stamp}_{who}_{base}"
    return base


def is_text(name: str) -> bool:
    return Path(name).suffix.lower() in TEXT_SUFFIXES


def month_parts(time: str) -> tuple[str, str]:
    day = time[:10] if time else "1970-01-01"
    return day[:4], day[5:7]


def date_part(time: str) -> str:
    return time[:10] if time else "1970-01-01"
