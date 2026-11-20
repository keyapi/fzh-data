#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""把 Tracy 的 Camping World 入驻邮件附件下载到仓库外目录。

凭据从父仓库 .env 读取（IMAP_USER / IMAP_PASS / IMAP_SERVER），不写入任何文件。

用法:
  uv run python camping_world/fetch_attachments.py
  uv run python camping_world/fetch_attachments.py --out "D:/path/to/dir"
  uv run python camping_world/fetch_attachments.py --list-only
"""
from __future__ import annotations

import argparse
import imaplib
import os
import re
import sys
from email import policy
from email.parser import BytesParser
from email.utils import parsedate_to_datetime
from pathlib import Path

DEFAULT_OUT = Path(r"D:\Work\美国\Tracy Miller\Camping World\2026-11-19 入驻包")
SENDER_HINT = "inventivesleep.com"
SUBJECT_HINT = "camping world"
SCAN_RECENT = 800


def find_env() -> Path:
    for base in [Path.cwd(), *Path.cwd().parents]:
        candidate = base / ".env"
        if candidate.is_file():
            return candidate
    raise SystemExit("找不到父仓库 .env")


def load_env(path: Path) -> dict[str, str]:
    values: dict[str, str] = {}
    for line in path.read_text(encoding="utf-8-sig").splitlines():
        line = line.strip()
        if not line or line.startswith("#") or "=" not in line:
            continue
        key, value = line.split("=", 1)
        key = key.strip()
        if key.startswith("IMAP"):
            values[key] = value.strip().strip('"').strip("'")
    return values


def connect(env: dict[str, str]) -> imaplib.IMAP4_SSL:
    imap = imaplib.IMAP4_SSL(env["IMAP_SERVER"], int(env.get("IMAP_PORT", "993")))
    imap.login(env["IMAP_USER"], env["IMAP_PASS"])
    imap.select("INBOX")
    return imap


def list_messages(imap: imaplib.IMAP4_SSL, limit: int = SCAN_RECENT) -> list[tuple[bytes, str, str, str]]:
    typ, data = imap.uid("search", None, "ALL")
    if typ != "OK" or not data or data[0] is None:
        return []
    uids = data[0].split()[-limit:]
    found: list[tuple[bytes, str, str, str]] = []
    for start in range(0, len(uids), 50):
        chunk = b",".join(uids[start : start + 50])
        typ, fetched = imap.uid("fetch", chunk, "(BODY.PEEK[HEADER.FIELDS (FROM SUBJECT DATE)])")
        if typ != "OK":
            continue
        for item in fetched:
            if not isinstance(item, tuple):
                continue
            match = re.search(rb"UID (\d+)", item[0])
            if not match:
                continue
            uid = match.group(1)
            msg = BytesParser(policy=policy.default).parsebytes(item[1])
            sender = str(msg.get("from", ""))
            subject = str(msg.get("subject", ""))
            date = str(msg.get("date", ""))
            if SENDER_HINT in sender.lower() and SUBJECT_HINT in subject.lower():
                found.append((uid, date, sender, subject))
    return found


def sanitize_name(name: str) -> str:
    name = name.replace("\\", "_").replace("/", "_").strip()
    return name or "attachment"


def download(imap: imaplib.IMAP4_SSL, uid: bytes, out_dir: Path) -> list[tuple[str, int]]:
    typ, data = imap.uid("fetch", uid, "(RFC822)")
    if typ != "OK" or not data or not isinstance(data[0], tuple):
        raise SystemExit(f"读取 UID {uid!r} 失败")
    msg = BytesParser(policy=policy.default).parsebytes(data[0][1])
    out_dir.mkdir(parents=True, exist_ok=True)
    written: list[tuple[str, int]] = []
    for part in msg.walk():
        filename = part.get_filename()
        if not filename:
            continue
        payload = part.get_payload(decode=True) or b""
        target = out_dir / sanitize_name(filename)
        target.write_bytes(payload)
        written.append((target.name, len(payload)))
    return written


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--out", type=Path, default=DEFAULT_OUT)
    parser.add_argument("--list-only", action="store_true")
    parser.add_argument("--uid", help="直接指定 IMAP UID")
    args = parser.parse_args()

    env = load_env(find_env())
    imap = connect(env)
    try:
        if args.uid:
            uid = args.uid.encode()
        else:
            hits = list_messages(imap)
            if not hits:
                print("没找到 Tracy 的 Camping World 邮件", file=sys.stderr)
                return 1
            for u, date, sender, subject in hits:
                print(f"命中 UID {u.decode()} | {date} | {sender} | {subject}")
            uid = hits[-1][0]
        if args.list_only:
            typ, data = imap.uid("fetch", uid, "(RFC822)")
            msg = BytesParser(policy=policy.default).parsebytes(data[0][1])
            for part in msg.walk():
                if part.get_filename():
                    print(f"  - {part.get_filename()}")
            return 0
        written = download(imap, uid, args.out)
    finally:
        imap.logout()

    total = sum(size for _, size in written)
    print(f"\n已写入 {len(written)} 个附件到 {args.out}（共 {total:,} 字节）")
    for name, size in written:
        print(f"  {name}  {size:,} bytes")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
