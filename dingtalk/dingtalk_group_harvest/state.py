# -*- coding: utf-8 -*-
"""按群保存增量水位，原子写入，避免中断后重复或漏采。"""
from __future__ import annotations

import datetime as _dt
import json
import os
from pathlib import Path
from typing import Any

from .paths import HARVEST_ROOT

CST = _dt.timezone(_dt.timedelta(hours=8))
OVERLAP = _dt.timedelta(seconds=1)


def state_path(root: Path = HARVEST_ROOT) -> Path:
    return root / "state" / "watermarks.json"


def load_state(root: Path = HARVEST_ROOT) -> dict[str, Any]:
    path = state_path(root)
    if not path.is_file():
        return {"version": 1, "groups": {}}
    data = json.loads(path.read_text(encoding="utf-8"))
    data.setdefault("version", 1)
    data.setdefault("groups", {})
    return data


def save_state(state: dict[str, Any], root: Path = HARVEST_ROOT) -> None:
    path = state_path(root)
    path.parent.mkdir(parents=True, exist_ok=True)
    tmp = path.with_suffix(".tmp")
    tmp.write_text(
        json.dumps(state, ensure_ascii=False, indent=2) + "\n", encoding="utf-8"
    )
    os.replace(tmp, path)


def group_state(state: dict[str, Any], group: str) -> dict[str, Any]:
    groups = state.setdefault("groups", {})
    entry = groups.setdefault(
        group,
        {
            "last_message_time": None,
            "last_message_id": None,
            "files": {},
            "docs": {},
        },
    )
    entry.setdefault("files", {})
    entry.setdefault("docs", {})
    return entry


def parse_dt(raw: str) -> _dt.datetime:
    for fmt in ("%Y-%m-%d %H:%M:%S", "%Y-%m-%dT%H:%M:%S%z", "%Y-%m-%d"):
        try:
            value = _dt.datetime.strptime(raw, fmt)
            return value if value.tzinfo else value.replace(tzinfo=CST)
        except ValueError:
            continue
    raise ValueError(f"无法解析时间: {raw}")


def fmt_dt(value: _dt.datetime) -> str:
    return value.astimezone(CST).strftime("%Y-%m-%dT%H:%M:%S+08:00")


def window(
    entry: dict[str, Any],
    *,
    backfill_days: int,
    now: _dt.datetime | None = None,
) -> tuple[str, str]:
    now = now or _dt.datetime.now(CST)
    last = entry.get("last_message_time")
    if last:
        start = parse_dt(last) - OVERLAP
    else:
        start = now - _dt.timedelta(days=backfill_days)
    return fmt_dt(start), fmt_dt(now)


def advance(
    entry: dict[str, Any],
    messages: list[dict[str, Any]],
    *,
    window_end: str,
) -> None:
    if messages:
        newest = max(messages, key=lambda m: m.get("createTime", ""))
        entry["last_message_time"] = newest.get("createTime")
        entry["last_message_id"] = newest.get("messageId")
    else:
        entry["last_message_time"] = parse_dt(window_end).strftime("%Y-%m-%d %H:%M:%S")
