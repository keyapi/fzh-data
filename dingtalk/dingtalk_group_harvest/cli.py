# -*- coding: utf-8 -*-
"""命令行入口：resolve / harvest / digest / status。"""
from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path
from typing import Any

from . import dws_client as dws
from . import digest as digest_mod
from . import harvest as harvest_mod
from . import reconcile
from . import state as state_mod
from .paths import CONFIG_PATH, EXAMPLE_CONFIG, HARVEST_ROOT


def _raw_config() -> dict[str, Any]:
    source = CONFIG_PATH if CONFIG_PATH.is_file() else EXAMPLE_CONFIG
    return json.loads(source.read_text(encoding="utf-8"))


def _write_resolved(groups: list[dict[str, Any]]) -> None:
    CONFIG_PATH.parent.mkdir(parents=True, exist_ok=True)
    CONFIG_PATH.write_text(
        json.dumps({"groups": groups}, ensure_ascii=False, indent=2) + "\n",
        encoding="utf-8",
    )


def cmd_resolve(args: argparse.Namespace) -> int:
    raw = _raw_config()
    groups = raw.get("groups", [])
    changed = False
    for cfg in groups:
        try:
            gid = harvest_mod.resolve_group(cfg)
        except dws.DwsError as exc:
            print(f"❌ {cfg.get('name')}: {exc}")
            continue
        print(f"✅ {cfg.get('name')} -> {gid}")
        if gid != (cfg.get("openConversationId") or ""):
            cfg["openConversationId"] = gid
            changed = True
    if args.write and changed:
        _write_resolved(groups)
        print(f"已写入本地配置：{CONFIG_PATH}")
    return 0


def cmd_harvest(args: argparse.Namespace) -> int:
    dws.ensure_auth()
    only = args.group or None
    reports = harvest_mod.harvest_all(
        root=HARVEST_ROOT,
        only=only,
        backfill_days=args.backfill_days,
        dry_run=args.dry_run,
        include_media=args.include_media,
    )
    report_path = reconcile.write_report(reports, root=HARVEST_ROOT)
    for r in reports:
        flag = "✅" if r.complete else "❌"
        print(
            f"{flag} {r.group}: 消息 {r.messages_fetched}，新增 {r.messages_new}，"
            f"文件 {r.files_archived}/{r.files_found}，文档 {r.docs_exported}/{r.doc_links}"
        )
    print(f"对账报告：{report_path}")
    return 0 if all(r.complete for r in reports) else 3


def cmd_digest(args: argparse.Namespace) -> int:
    only = args.group or None
    paths = digest_mod.digest_all(
        week=args.week,
        root=HARVEST_ROOT,
        only=only,
        use_llm=not args.no_llm,
    )
    for path in paths:
        print(f"✅ {path}")
    return 0


def cmd_status(args: argparse.Namespace) -> int:
    status = dws.auth_status()
    print(json.dumps(status, ensure_ascii=False, indent=2))
    state = state_mod.load_state(HARVEST_ROOT)
    for name, entry in state.get("groups", {}).items():
        print(
            f"- {name}: 水位 {entry.get('last_message_time')}，"
            f"已归档文件 {len(entry.get('files', {}))} 个"
        )
    print(f"归档根：{HARVEST_ROOT}")
    return 0


def _parser() -> argparse.ArgumentParser:
    p = argparse.ArgumentParser(
        prog="dingtalk-group-harvest",
        description="钉钉 AI 项目群：群消息/文件增量采集与周报",
    )
    sub = p.add_subparsers(dest="command", required=True)

    r = sub.add_parser("resolve", help="把群名解析成 openConversationId")
    r.add_argument("--write", action="store_true", help="把解析结果写入 groups.local.json")
    r.set_defaults(func=cmd_resolve)

    h = sub.add_parser("harvest", help="拉取增量消息、下载文件、导出文档")
    h.add_argument("--group", action="append", help="只处理指定群，可重复")
    h.add_argument("--backfill-days", type=int, help="首次回溯天数，默认取配置")
    h.add_argument("--dry-run", action="store_true", help="只拉消息，不下载/不写状态")
    h.add_argument("--include-media", action="store_true", help="同时下载图片/视频")
    h.set_defaults(func=cmd_harvest)

    d = sub.add_parser("digest", help="生成周报")
    d.add_argument("--group", action="append", help="只处理指定群，可重复")
    d.add_argument("--week", help="ISO 周，如 2026-W45；默认上一周")
    d.add_argument("--no-llm", action="store_true", help="不调用 Claude Code，只输出结构化版本")
    d.set_defaults(func=cmd_digest)

    s = sub.add_parser("status", help="查看登录态与水位")
    s.set_defaults(func=cmd_status)
    return p


def main(argv: list[str] | None = None) -> int:
    args = _parser().parse_args(argv)
    try:
        return args.func(args)
    except dws.DwsAuthError as exc:
        print(f"❌ 登录态失效：{exc}", file=sys.stderr)
        return 4
    except dws.DwsError as exc:
        print(f"❌ DWS 调用失败：{exc}", file=sys.stderr)
        return 1


if __name__ == "__main__":
    raise SystemExit(main())
