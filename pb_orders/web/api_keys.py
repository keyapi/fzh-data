#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""PB JSON API Key 管理 CLI。

用法（容器内）：
  python -m web.api_keys create --name agent --scopes check,fulfill,read
  python -m web.api_keys list
  python -m web.api_keys revoke <key_id>
"""

from __future__ import annotations

import argparse
import sys

from web.config import get_settings
from web.repository import Repository


def _repo() -> Repository:
    settings = get_settings()
    settings.ensure_dirs()
    return Repository(settings.db_path)


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(prog="python -m web.api_keys")
    sub = parser.add_subparsers(dest="command", required=True)

    create = sub.add_parser("create", help="创建 API Key（明文只显示一次）")
    create.add_argument("--name", required=True)
    create.add_argument("--scopes", default="check,fulfill,read")
    create.add_argument("--created-by", default="cli")

    sub.add_parser("list", help="列出 Key（不含明文）")

    revoke = sub.add_parser("revoke", help="吊销 Key")
    revoke.add_argument("key_id")

    args = parser.parse_args(argv)
    repo = _repo()

    if args.command == "create":
        result = repo.create_api_key(args.name, args.scopes, args.created_by)
        print(f"id:     {result['id']}")
        print(f"name:   {result['name']}")
        print(f"prefix: {result['key_prefix']}")
        print(f"scopes: {result['scopes']}")
        print(f"key:    {result['key']}")
        print("⚠️ 明文只显示这一次，请立即保存。")
        return 0

    if args.command == "list":
        for row in repo.list_api_keys():
            state = "active" if row["is_active"] else "revoked"
            print(f"{row['id']}  {state:7}  {row['name']}  {row['key_prefix']}…  "
                  f"scopes={row['scopes']}  last_used={row['last_used_at'] or '-'}")
        return 0

    if args.command == "revoke":
        ok = repo.revoke_api_key(args.key_id)
        print("revoked" if ok else "not found")
        return 0 if ok else 1

    return 2


if __name__ == "__main__":
    sys.exit(main())
