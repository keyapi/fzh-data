# -*- coding: utf-8 -*-
"""按周生成群记录：结构化摘要 + 可选 Claude Code 润色。"""
from __future__ import annotations

import datetime as _dt
import json
import os
import re
import shutil
import subprocess
from collections import Counter
from pathlib import Path
from typing import Any

from . import normalize
from .harvest import load_config
from .paths import DIGEST_PROMPT, HARVEST_ROOT
from .state import CST

KEYWORDS = {
    "决策": ("决定", "确定", "结论", "拍板", "统一", "最终", "采用"),
    "待办": ("待办", "需要", "下一步", "请", "负责", "跟进", "安排", "明天", "本周"),
    "问题": ("问题", "风险", "卡点", "疑问", "不确定", "冲突", "缺少"),
}


def week_range(week: str | None, now: _dt.datetime | None = None) -> tuple[_dt.datetime, _dt.datetime]:
    now = now or _dt.datetime.now(CST)
    if week:
        monday = _dt.datetime.strptime(week + "-1", "%G-W%V-%u").replace(tzinfo=CST)
    else:
        monday = (now - _dt.timedelta(days=now.isoweekday() + 6)).replace(
            hour=0, minute=0, second=0, microsecond=0
        )
    return monday, monday + _dt.timedelta(days=7)


def week_label(start: _dt.datetime) -> str:
    iso = start.isocalendar()
    return f"{iso.year}-W{iso.week:02d}"


def load_messages(root: Path, group: str, start: _dt.datetime, end: _dt.datetime) -> list[dict[str, Any]]:
    folder = root / group / "messages"
    if not folder.is_dir():
        return []
    messages: list[dict[str, Any]] = []
    for path in sorted(folder.glob("*.jsonl")):
        for line in path.read_text(encoding="utf-8").splitlines():
            if not line.strip():
                continue
            try:
                msg = json.loads(line)
            except json.JSONDecodeError:
                continue
            raw = msg.get("createTime") or ""
            try:
                when = _dt.datetime.strptime(raw, "%Y-%m-%d %H:%M:%S").replace(tzinfo=CST)
            except ValueError:
                continue
            if start <= when < end:
                messages.append(msg)
    messages.sort(key=lambda m: m.get("createTime", ""))
    return messages


def _short(text: str, limit: int = 600) -> str:
    text = re.sub(r"\s+", " ", (text or "")).strip()
    return text if len(text) <= limit else text[: limit - 1] + "…"


def build_structured(group: str, messages: list[dict[str, Any]], start: _dt.datetime, end: _dt.datetime) -> dict[str, Any]:
    speakers = Counter(m.get("sender") or "未知" for m in messages)
    files: list[dict[str, str]] = []
    for msg in messages:
        for item in msg.get("_archived_files") or []:
            files.append(
                {
                    "name": item.get("name", ""),
                    "path": item.get("path", ""),
                    "sender": msg.get("sender", ""),
                    "time": msg.get("createTime", ""),
                    "messageId": msg.get("messageId", ""),
                }
            )
    buckets: dict[str, list[dict[str, str]]] = {key: [] for key in KEYWORDS}
    for msg in messages:
        text = msg.get("text") or ""
        for label, words in KEYWORDS.items():
            if any(word in text for word in words):
                buckets[label].append(
                    {
                        "time": msg.get("createTime", ""),
                        "sender": msg.get("sender", ""),
                        "text": _short(text),
                        "messageId": msg.get("messageId", ""),
                    }
                )
    return {
        "group": group,
        "start": start.strftime("%Y-%m-%d"),
        "end": (end - _dt.timedelta(days=1)).strftime("%Y-%m-%d"),
        "message_count": len(messages),
        "speakers": speakers.most_common(),
        "files": files,
        "decisions": buckets["决策"],
        "todos": buckets["待办"],
        "issues": buckets["问题"],
        "messages": [
            {
                "time": m.get("createTime", ""),
                "sender": m.get("sender", ""),
                "text": _short(m.get("text") or ""),
                "messageId": m.get("messageId", ""),
            }
            for m in messages
        ],
    }


def render_markdown(structured: dict[str, Any]) -> str:
    lines = [
        f"# {structured['group']} · {structured['start']} ~ {structured['end']}",
        "",
        f"- 消息数：{structured['message_count']}",
        f"- 活跃成员：{len(structured['speakers'])}",
        f"- 文件数：{len(structured['files'])}",
        "",
        "## 文件清单",
        "",
    ]
    if structured["files"]:
        lines += ["| 时间 | 发送人 | 文件名 | 本地路径 |", "|---|---|---|---|"]
        for f in structured["files"]:
            lines.append(
                f"| {f['time']} | {f['sender']} | {f['name']} | `{f['path']}` |"
            )
    else:
        lines.append("本周无文件。")
    for label, key in (("决策候选", "decisions"), ("待办候选", "todos"), ("问题/风险候选", "issues")):
        lines += ["", f"## {label}", ""]
        if structured[key]:
            for item in structured[key][:30]:
                lines.append(f"- {item['time']} {item['sender']}：{item['text']}")
        else:
            lines.append("无（仅按关键词粗筛，建议人工复核）。")
    lines += ["", "## 讨论原文", ""]
    for msg in structured["messages"][:200]:
        lines.append(f"- `{msg['messageId']}` {msg['time']} {msg['sender']}：{msg['text']}")
    lines += ["", "> 本文件由 DWS 采集的群消息生成；关键词候选仅供检索，事实以原文为准。", ""]
    return "\n".join(lines)


def _claude_cli() -> str | None:
    raw = os.environ.get("CLAUDE_CLI", "").strip()
    if raw:
        return raw
    return shutil.which("claude")


def polish_with_claude(markdown: str, structured: dict[str, Any]) -> str:
    cli = _claude_cli()
    if not cli:
        return markdown + "\n> 未找到 claude CLI，已输出结构化版本。\n"
    template = DIGEST_PROMPT.read_text(encoding="utf-8") if DIGEST_PROMPT.is_file() else ""
    payload_obj = dict(structured)
    payload_obj["files"] = structured["files"][:300]
    payload_obj["messages"] = structured["messages"][:300]
    for key in ("decisions", "todos", "issues"):
        payload_obj[key] = structured[key][:150]
    payload = json.dumps(payload_obj, ensure_ascii=False)
    prompt = f"{template}\n\n以下是本周结构化数据（JSON）：\n{payload}\n\n已生成的结构化初稿：\n{markdown}"
    try:
        proc = subprocess.run(
            [cli, "-p"],
            input=prompt,
            capture_output=True,
            text=True,
            encoding="utf-8",
            errors="replace",
            timeout=600,
        )
    except (OSError, subprocess.TimeoutExpired):
        return markdown + "\n> Claude Code 调用失败，已输出结构化版本。\n"
    if proc.returncode != 0 or not proc.stdout.strip():
        return markdown + f"\n> Claude Code 返回失败（{proc.returncode}），已输出结构化版本。\n"
    return proc.stdout.strip() + "\n"


def build_digest(
    group: str,
    *,
    week: str | None = None,
    root: Path = HARVEST_ROOT,
    use_llm: bool = True,
) -> Path:
    start, end = week_range(week)
    messages = load_messages(root, group, start, end)
    structured = build_structured(group, messages, start, end)
    markdown = render_markdown(structured)
    if use_llm:
        markdown = polish_with_claude(markdown, structured)
    out_dir = root / "digests" / group
    out_dir.mkdir(parents=True, exist_ok=True)
    label = week_label(start)
    md_path = out_dir / f"{label}.md"
    md_path.write_text(markdown, encoding="utf-8")
    (out_dir / f"{label}.json").write_text(
        json.dumps(structured, ensure_ascii=False, indent=2) + "\n", encoding="utf-8"
    )
    return md_path


def digest_all(
    *,
    week: str | None = None,
    root: Path = HARVEST_ROOT,
    only: list[str] | None = None,
    use_llm: bool = True,
) -> list[Path]:
    paths: list[Path] = []
    for cfg in load_config():
        if only and cfg["name"] not in only:
            continue
        paths.append(build_digest(cfg["name"], week=week, root=root, use_llm=use_llm))
    return paths
