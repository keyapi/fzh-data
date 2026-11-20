# -*- coding: utf-8 -*-
"""把一次采集的结果写成可追溯的对账报告。"""
from __future__ import annotations

import datetime as _dt
from pathlib import Path
from typing import Iterable

from .harvest import GroupReport
from .paths import HARVEST_ROOT


def render_report(reports: Iterable[GroupReport], *, run_id: str) -> str:
    reports = list(reports)
    lines = [
        f"# 钉钉群采集对账 · {run_id}",
        "",
        f"生成时间：{_dt.datetime.now().astimezone().strftime('%Y-%m-%d %H:%M:%S %z')}",
        "",
        "| 群 | 群 ID | 窗口 | 消息拉取 | 新增 | 文件发现 | 已归档 | 跳过 | 失败 | 文档链接 | 已导出 |",
        "|---|---|---|---|---|---|---|---|---|---|---|",
    ]
    for r in reports:
        lines.append(
            f"| {r.group} | `{r.group_id}` | {r.window_start} → {r.window_end} "
            f"| {r.messages_fetched} | {r.messages_new} | {r.files_found} "
            f"| {r.files_archived} | {r.files_skipped} | {r.files_failed} "
            f"| {r.doc_links} | {r.docs_exported} |"
        )
    total = {
        "messages": sum(r.messages_fetched for r in reports),
        "new": sum(r.messages_new for r in reports),
        "files": sum(r.files_found for r in reports),
        "archived": sum(r.files_archived for r in reports),
        "failed": sum(r.files_failed for r in reports),
        "doc_failed": sum(r.doc_failures for r in reports),
    }
    lines += [
        "",
        "## 汇总",
        "",
        f"- 消息拉取 {total['messages']} 条，新增归档 {total['new']} 条",
        f"- 文件发现 {total['files']} 个，归档 {total['archived']} 个，失败 {total['failed']} 个",
        f"- 是否全部完整：{'是' if all(r.complete for r in reports) else '否'}",
        "",
    ]
    problems = [r for r in reports if r.failures or r.notes or not r.complete]
    if problems:
        lines += ["## 失败与提示", ""]
        for r in problems:
            lines.append(f"### {r.group}")
            for item in r.failures:
                lines.append(f"- ❌ {item}")
            for item in r.notes:
                lines.append(f"- ⚠️ {item}")
            lines.append("")
    return "\n".join(lines)


def write_report(reports: Iterable[GroupReport], *, root: Path = HARVEST_ROOT) -> Path:
    run_id = _dt.datetime.now().strftime("%Y%m%d-%H%M%S")
    path = root / "reports" / f"{run_id}.md"
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(render_report(reports, run_id=run_id), encoding="utf-8")
    return path
