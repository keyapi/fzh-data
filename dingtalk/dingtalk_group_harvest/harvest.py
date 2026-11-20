# -*- coding: utf-8 -*-
"""采集主流程：解析群 → 拉增量消息 → 下载文件/导出文档 → 归档 → 推进水位。"""
from __future__ import annotations

import hashlib
import json
import shutil
import uuid
from collections import defaultdict
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any

from . import dws_client as dws
from . import normalize, state as state_mod
from .paths import CONFIG_PATH, EXAMPLE_CONFIG, HARVEST_ROOT


@dataclass
class GroupReport:
    group: str
    group_id: str = ""
    window_start: str = ""
    window_end: str = ""
    messages_fetched: int = 0
    messages_new: int = 0
    files_found: int = 0
    files_archived: int = 0
    files_skipped: int = 0
    files_failed: int = 0
    media_found: int = 0
    media_archived: int = 0
    doc_links: int = 0
    docs_exported: int = 0
    doc_failures: int = 0
    complete: bool = True
    failures: list[str] = field(default_factory=list)
    notes: list[str] = field(default_factory=list)


def load_config(path: Path = CONFIG_PATH) -> list[dict[str, Any]]:
    source = path if path.is_file() else EXAMPLE_CONFIG
    data = json.loads(source.read_text(encoding="utf-8"))
    return [g for g in data.get("groups", []) if g.get("enabled", True)]


def resolve_group(group_cfg: dict[str, Any]) -> str:
    existing = (group_cfg.get("openConversationId") or "").strip()
    if existing:
        return existing
    name = group_cfg["name"]
    data = dws.run_json(["chat", "+chat-search", "--query", name, "--page-all", "-f", "json"])
    chats = data.get("chats") or []
    exact = [c for c in chats if (c.get("name") or c.get("title")) == name]
    candidates = exact or chats
    if len(candidates) == 1:
        return candidates[0]["openConversationId"]
    names = [c.get("name") or c.get("title") for c in candidates]
    raise dws.DwsError(f"群名无法唯一解析：{name}；候选={names}")


def _ensure_dirs(root: Path, group: str) -> None:
    for sub in ("messages", "files", "media", "docs"):
        (root / group / sub).mkdir(parents=True, exist_ok=True)
    for sub in ("reports", "state", "logs", "tmp", "digests"):
        (root / sub).mkdir(parents=True, exist_ok=True)


def _fetch_messages(group_id: str, start: str, end: str, workdir: Path) -> dict[str, Any]:
    out_name = "messages.json"
    args = [
        "chat", "+chat-messages",
        "--group", group_id,
        "--start", start,
        "--end", end,
        "--order", "asc",
        "--page-all",
        "--page-limit", "100",
        "--page-delay", "200",
        "--output", out_name,
        "-f", "json",
    ]
    result = dws.run_dws(args, cwd=workdir, timeout=900)
    if result.returncode != 0:
        try:
            dws.parse_json(result.stdout, result.stderr)
        except dws.DwsError:
            raise dws.DwsError(
                f"DWS 拉取消息失败，退出码 {result.returncode}",
                argv=result.argv,
                stdout=result.stdout,
                stderr=result.stderr,
            )
    data = dws.read_output(workdir / out_name)
    dws.validate_complete(data, "chat +chat-messages")
    return data


def _download_ref(
    ref: normalize.FileRef,
    *,
    workdir: Path,
    target_dir: Path,
    group_id: str,
    include_media: bool,
) -> tuple[str, Path | None, str]:
    """返回 (状态, 本地路径, 错误信息)。状态：archived / skipped / failed / ignored。"""
    is_file = ref.content_type == "file" or ref.resource_type == "fileId"
    if not is_file and not include_media:
        return "ignored", None, ""
    ext = Path(ref.name).suffix or (".bin" if is_file else ".dat")
    rel = Path("resources") / f"{hashlib.md5(ref.resource_id.encode()).hexdigest()}{ext}"
    rel.parent.mkdir(parents=True, exist_ok=True)
    args = [
        "chat", "+messages-resource-download",
        "--type", ref.resource_type,
        "--resource-id", ref.resource_id,
        "--output", rel.as_posix(),
        "-f", "json",
    ]
    if ref.resource_type == "mediaId":
        args += [
            "--message-id", ref.message_id,
            "--open-conversation-id", group_id,
        ]
    try:
        data = dws.run_json(args, cwd=workdir, timeout=600)
    except dws.DwsError as exc:
        return "failed", None, f"{ref.name}: {exc}"
    local = Path(data.get("localPath") or rel)
    if not local.is_absolute():
        local = workdir / local
    if not local.is_file() or local.stat().st_size == 0:
        return "failed", None, f"{ref.name}: 下载文件为空或不存在"
    target = target_dir / normalize.safe_filename(
        ref.name, sender=ref.sender, time=ref.time
    )
    if target.exists():
        return "skipped", target, ""
    target.parent.mkdir(parents=True, exist_ok=True)
    shutil.move(str(local), str(target))
    return "archived", target, ""


def _doc_title(url: str) -> str:
    try:
        data = dws.run_json(["doc", "info", "--node", url, "-f", "json"], timeout=120)
    except dws.DwsError:
        return ""
    for key in ("title", "name", "docTitle"):
        value = data.get(key)
        if isinstance(value, str) and value.strip():
            return value.strip()
    nested = data.get("data") or {}
    for key in ("title", "name", "docTitle"):
        value = nested.get(key)
        if isinstance(value, str) and value.strip():
            return value.strip()
    return ""


def _export_doc(
    url: str, workdir: Path, target_dir: Path, entry: dict[str, Any], root: Path
) -> tuple[bool, str]:
    key = hashlib.md5(url.encode("utf-8")).hexdigest()
    rel = Path("docs") / f"{key}.md"
    rel.parent.mkdir(parents=True, exist_ok=True)
    try:
        data = dws.run_json(
            [
                "doc", "export",
                "--node", url,
                "--export-format", "markdown",
                "--output", rel.as_posix(),
                "-f", "json",
            ],
            cwd=workdir,
            timeout=600,
        )
    except dws.DwsError as exc:
        return False, f"{url}: {exc}"
    local = Path(data.get("localPath") or rel)
    if not local.is_absolute():
        local = workdir / local
    if not local.is_file():
        return False, f"{url}: 导出文件不存在"
    title = _doc_title(url) or f"doc_{key[:8]}"
    target = target_dir / normalize.safe_filename(f"{title}.md")
    if target.exists():
        entry["docs"][url] = str(target.relative_to(root))
        return True, ""
    target.parent.mkdir(parents=True, exist_ok=True)
    shutil.move(str(local), str(target))
    entry["docs"][url] = str(target.relative_to(root))
    return True, ""


def _append_messages(
    root: Path, group: str, messages: list[dict[str, Any]], archived: dict[str, list[dict[str, str]]]
) -> int:
    by_date: dict[str, list[dict[str, Any]]] = defaultdict(list)
    for msg in messages:
        record = dict(msg)
        record["_archived_files"] = archived.get(msg.get("messageId", ""), [])
        by_date[normalize.date_part(msg.get("createTime", ""))].append(record)
    new_count = 0
    for day, records in by_date.items():
        path = root / group / "messages" / f"{day}.jsonl"
        seen: set[str] = set()
        if path.is_file():
            for line in path.read_text(encoding="utf-8").splitlines():
                if not line.strip():
                    continue
                try:
                    seen.add(json.loads(line).get("messageId", ""))
                except json.JSONDecodeError:
                    continue
        fresh = [r for r in records if r.get("messageId") not in seen]
        if fresh:
            with path.open("a", encoding="utf-8") as fh:
                for record in fresh:
                    fh.write(json.dumps(record, ensure_ascii=False) + "\n")
            new_count += len(fresh)
    return new_count


def harvest_group(
    group_cfg: dict[str, Any],
    *,
    root: Path = HARVEST_ROOT,
    backfill_days: int | None = None,
    dry_run: bool = False,
    include_media: bool = False,
) -> GroupReport:
    group = group_cfg["name"]
    report = GroupReport(group=group)
    _ensure_dirs(root, group)
    try:
        group_id = resolve_group(group_cfg)
        report.group_id = group_id
    except dws.DwsError as exc:
        report.complete = False
        report.failures.append(str(exc))
        return report

    st = state_mod.load_state(root)
    entry = state_mod.group_state(st, group)
    days = backfill_days if backfill_days is not None else int(group_cfg.get("backfillDays", 60))
    start, end = state_mod.window(entry, backfill_days=days)
    report.window_start, report.window_end = start, end

    run_dir = root / "tmp" / f"{uuid.uuid4().hex[:10]}_{group}"
    run_dir.mkdir(parents=True, exist_ok=True)
    try:
        data = _fetch_messages(group_id, start, end, run_dir)
    except dws.DwsError as exc:
        report.complete = False
        report.failures.append(str(exc))
        return report

    messages = data.get("messages") or []
    report.messages_fetched = len(messages)
    archived: dict[str, list[dict[str, str]]] = defaultdict(list)

    for msg in messages:
        files = normalize.message_files(msg)
        media = normalize.message_media(msg) if include_media else []
        report.files_found += len(files)
        report.media_found += len(media)
        for ref in files + media:
            known = entry["files"].get(ref.resource_id)
            if known and (root / known).is_file():
                archived[ref.message_id].append(
                    {"name": ref.name, "path": known, "resourceId": ref.resource_id}
                )
                if ref in files:
                    report.files_skipped += 1
                continue
            date = normalize.month_parts(ref.time)
            base = root / group / ("files" if ref in files else "media") / date[0] / date[1]
            if dry_run:
                continue
            status, path, error = _download_ref(
                ref,
                workdir=run_dir,
                target_dir=base,
                group_id=group_id,
                include_media=include_media,
            )
            if status == "archived" and path:
                rel = str(path.relative_to(root))
                entry["files"][ref.resource_id] = rel
                archived[ref.message_id].append(
                    {"name": ref.name, "path": rel, "resourceId": ref.resource_id}
                )
                if ref in files:
                    report.files_archived += 1
                else:
                    report.media_archived += 1
            elif status == "skipped" and path:
                entry["files"][ref.resource_id] = str(path.relative_to(root))
                archived[ref.message_id].append(
                    {"name": ref.name, "path": str(path.relative_to(root)), "resourceId": ref.resource_id}
                )
                if ref in files:
                    report.files_skipped += 1
            elif status == "failed":
                report.files_failed += 1 if ref in files else 0
                report.failures.append(error or f"{ref.name}: 下载失败")

        for url in normalize.extract_doc_links(msg.get("text", "")):
            report.doc_links += 1
            if entry["docs"].get(url) and (root / entry["docs"][url]).is_file():
                continue
            if dry_run:
                continue
            target_dir = root / group / "docs" / normalize.month_parts(msg.get("createTime", ""))[0] / normalize.month_parts(msg.get("createTime", ""))[1]
            ok, error = _export_doc(url, run_dir, target_dir, entry, root)
            if ok:
                report.docs_exported += 1
            else:
                report.doc_failures += 1
                report.notes.append(error)

    if not dry_run:
        report.messages_new = _append_messages(root, group, messages, archived)

    if report.files_failed == 0 and report.complete:
        state_mod.advance(entry, messages, window_end=end)
        if not dry_run:
            state_mod.save_state(st, root)
    else:
        report.complete = False
        report.notes.append("存在文件下载失败，水位未推进，下次运行会重试")

    shutil.rmtree(run_dir, ignore_errors=True)
    return report


def harvest_all(
    *,
    root: Path = HARVEST_ROOT,
    only: list[str] | None = None,
    backfill_days: int | None = None,
    dry_run: bool = False,
    include_media: bool = False,
) -> list[GroupReport]:
    reports: list[GroupReport] = []
    for cfg in load_config():
        if only and cfg["name"] not in only:
            continue
        reports.append(
            harvest_group(
                cfg,
                root=root,
                backfill_days=backfill_days,
                dry_run=dry_run,
                include_media=include_media,
            )
        )
    return reports
