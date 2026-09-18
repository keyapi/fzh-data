"""批量查询编排：读清单 → 并发查号 → 局部失败隔离 / 有限重试 / 断点续跑。

业务无关：只关心"输入跟踪号 → 得到 UpsTrackInfo 或错误"。输入输出的文件形态由 cli.py 负责。
"""

from __future__ import annotations

import csv
import json
import threading
import time
from concurrent.futures import ThreadPoolExecutor, as_completed
from dataclasses import dataclass
from typing import Any, Callable, Sequence

from .client import UpsTrackError
from .models import parse_track_payload

_TRACK_SYNONYMS = {
    "trackingnumber", "tracking_number", "tracking", "trackno", "trackingno",
    "ups", "ups_tracking", "inquiry", "inquirynumber", "trace", "traceid",
    "tracking #", "tracking#", "快递单号", "运单号", "单号",
}


def _norm_number(s: str) -> str:
    """粗清洗：去空白，去常见分隔符，大写。"""
    s = (s or "").replace(" ", "").replace("\t", "").strip().upper()
    for ch in ("-", "_", ",", "，", "'"):
        s = s.replace(ch, "")
    return s


@dataclass
class BatchItem:
    number: str
    remark: str = ""


@dataclass
class Record:
    """单号一次查询的结果（输入顺序保持）。"""

    number: str
    remark: str = ""
    ok: bool = False
    info: Any = None  # UpsTrackInfo | None
    error: str | None = None
    attempts: int = 1

    def to_summary_row(self) -> dict[str, Any]:
        info = self.info
        status = ""
        if self.ok and info:
            status = "查无此号" if info.not_found else (info.current_status or "")
        return {
            "跟踪号": self.number,
            "备注": self.remark,
            "成功": "是" if self.ok else "否",
            "已交付": "是" if (self.ok and info and info.delivered) else ("否" if self.ok else ""),
            "当前状态": status,
            "交付日期": _fmt_dt(info.delivery_dt) if (self.ok and info) else "",
            "交付城市": info.delivery_city if (self.ok and info) else "",
            "交付州": info.delivery_state if (self.ok and info) else "",
            "签收人": info.delivery_signed_by if (self.ok and info) else "",
            "建标时间": _fmt_dt(info.label_created_dt) if (self.ok and info) else "",
            "实际发货时间": _fmt_dt(info.actual_ship_dt) if (self.ok and info) else "",
            "最近节点时间": _fmt_dt(info.last_event_dt) if (self.ok and info) else "",
            "错误": self.error or "",
            "尝试次数": self.attempts,
        }

    def timeline_rows(self) -> list[dict[str, Any]]:
        if not (self.ok and self.info):
            return []
        rows = []
        for ev in self.info.events:
            rows.append({
                "跟踪号": self.number,
                "备注": self.remark,
                "节点时间": _fmt_dt(ev.dt),
                "状态类型": ev.status_type or "",
                "状态码": ev.status_code or "",
                "描述": ev.description or "",
                "城市": ev.city or "",
                "州": ev.state or "",
                "邮编": ev.postal or "",
            })
        return rows

    def to_raw_entry(self) -> dict[str, Any]:
        return {
            "tracking": self.number,
            "remark": self.remark,
            "ok": self.ok,
            "error": self.error,
            "raw": self.info.raw if (self.ok and self.info) else None,
        }


def _fmt_dt(dt: Any) -> str:
    if dt is None:
        return ""
    return dt.strftime("%Y-%m-%d %H:%M:%S")


def load_input_file(path: str) -> list[BatchItem]:
    """读清单：txt 每行一个跟踪号；CSV 首列跟踪号，其余列作为备注列。

    CSV 若首行为表头（含 tracking/跟踪号 等词）会按列名定位，并把非跟踪列拼进备注。
    """
    lower = path.lower()
    if lower.endswith(".csv"):
        return _load_csv(path)
    return _load_txt(path)


def _load_txt(path: str) -> list[BatchItem]:
    items: list[BatchItem] = []
    with open(path, "r", encoding="utf-8-sig", errors="replace") as fh:
        for line in fh:
            line = line.strip()
            if not line or line.startswith("#"):
                continue
            if " " in line or "\t" in line:
                parts = line.split(None, 1)
                num, remark = parts[0], (parts[1] if len(parts) > 1 else "")
            else:
                num, remark = line, ""
            n = _norm_number(num)
            if n:
                items.append(BatchItem(number=n, remark=remark.strip()))
    return items


def _load_csv(path: str) -> list[BatchItem]:
    items: list[BatchItem] = []
    with open(path, "r", encoding="utf-8-sig", errors="replace", newline="") as fh:
        rows = list(csv.reader(fh))
    if not rows:
        return items
    header = None
    track_idx = 0
    first = [(c or "").strip().lower() for c in rows[0]]
    if any(c in _TRACK_SYNONYMS for c in first if c):
        header = rows[0]
        track_idx = first.index(next(c for c in first if c in _TRACK_SYNONYMS))
        data = rows[1:]
    else:
        data = rows
    for row in data:
        if not row or not (row[0] or "").strip():
            continue
        number = _norm_number(row[track_idx]) if track_idx < len(row) else ""
        if not number:
            continue
        remarks: list[str] = []
        for i, cell in enumerate(row):
            if i == track_idx or not (cell or "").strip():
                continue
            if header and i < len(header) and (header[i] or "").strip():
                remarks.append(f"{header[i].strip()}={cell.strip()}")
            else:
                remarks.append(cell.strip())
        items.append(BatchItem(number=number, remark=" | ".join(remarks)))
    return items


def _read_done(raw_path: str) -> set[str]:
    """从上次的 raw.json 读取已成功单号（供 --resume 跳过）。"""
    try:
        with open(raw_path, "r", encoding="utf-8") as fh:
            data = json.load(fh)
    except (OSError, ValueError):
        return set()
    if not isinstance(data, dict):
        return set()
    return {k for k, v in data.items() if isinstance(v, dict) and v.get("ok")}


def run_batch(
    query: Callable[[str], Any],
    items: Sequence[BatchItem],
    *,
    workers: int = 4,
    retries: int = 1,
    resume_from: str | None = None,
    delay: float = 0.0,
    on_progress: Callable[[int, int, BatchItem, bool], None] | None = None,
) -> list[Record]:
    """并发查询。单号失败不中断；``resume_from`` 传上次 raw.json 路径时跳过已成功号。

    ``query`` 形如 ``client.track``，只接受一个 tracking 号并返回 ``UpsTrackInfo``。
    返回按输入顺序排列的 ``Record`` 列表。
    """
    done: set[str] = set()
    if resume_from:
        done = _read_done(resume_from)

    pending: list[BatchItem] = []
    for item in items:
        if item.number in done:
            continue
        pending.append(item)

    total = len(pending)
    results_by_key: dict[str, Record] = {}
    progress_lock = threading.Lock()
    progress_done = [0]

    def run_one(item: BatchItem) -> Record:
        attempts = 0
        last_err: UpsTrackError | None = None
        while True:
            attempts += 1
            try:
                info = query(item.number)
                return Record(number=item.number, remark=item.remark, ok=True, info=info, attempts=attempts)
            except UpsTrackError as exc:
                last_err = exc
                if exc.retriable and attempts <= retries:
                    time.sleep(min(2 ** attempts, 8))
                    continue
                return Record(
                    number=item.number, remark=item.remark, ok=False,
                    error=str(exc), attempts=attempts,
                )
            except Exception as exc:  # 防御：非 UPS 异常也不中断批量
                return Record(
                    number=item.number, remark=item.remark, ok=False,
                    error=f"{type(exc).__name__}: {exc}", attempts=attempts,
                )

    def _track_progress(item: BatchItem) -> None:
        with progress_lock:
            progress_done[0] += 1
        if on_progress:
            on_progress(progress_done[0], total, item, True)

    if workers <= 1 or total <= 1:
        for item in pending:
            rec = run_one(item)
            results_by_key[item.number] = rec
            _track_progress(item)
            if delay:
                time.sleep(delay)
    else:
        with ThreadPoolExecutor(max_workers=workers) as pool:
            futs = {pool.submit(run_one, item): item for item in pending}
            for fut in as_completed(futs):
                item = futs[fut]
                rec = fut.result()
                results_by_key[item.number] = rec
                _track_progress(item)
                if delay:
                    time.sleep(delay)

    ordered: list[Record] = []
    seen: set[str] = set()
    for item in items:
        if item.number in seen:
            continue
        seen.add(item.number)
        rec = results_by_key.get(item.number)
        if rec is None:  # resume 跳过的已成功号
            continue
        ordered.append(rec)
    return ordered


def merge_resumed_done(ordered: list[Record], resume_from: str | None) -> list[Record]:
    """若 --resume 跳过了已成功单号，把它们合并回结果（从 raw.json 还原 info）。"""
    if not resume_from:
        return ordered
    try:
        with open(resume_from, "r", encoding="utf-8") as fh:
            data = json.load(fh)
    except (OSError, ValueError):
        return ordered
    if not isinstance(data, dict):
        return ordered
    keys = {r.number for r in ordered}
    for number, entry in data.items():
        if number in keys:
            continue
        if not (isinstance(entry, dict) and entry.get("ok")):
            continue
        raw = entry.get("raw")
        info = parse_track_payload(number, raw) if isinstance(raw, dict) else None
        ordered.append(
            Record(number=number, remark=entry.get("remark", ""), ok=True, info=info, attempts=0)
        )
    return ordered
