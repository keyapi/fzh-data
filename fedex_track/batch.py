"""FedEx 批量查询编排：读清单(txt/csv/xlsx) → 按 ≤30/请求分块查询 → 局部失败隔离/重试/断点续跑。

业务无关：只关心"输入一批跟踪号 → 得到每个号的 FdxTrackInfo 或错误"。文件形态由 cli.py 负责。
"""

from __future__ import annotations

import csv
import json
import threading
import time
from concurrent.futures import ThreadPoolExecutor, as_completed
from dataclasses import dataclass, field
from typing import Any, Callable, Sequence

from .client import FedexTrackError, MAX_NUMBERS_PER_REQUEST
from .models import FdxTrackInfo, parse_track_payload

_TRACK_SYNONYMS = {
    "trackingnumber", "tracking_number", "tracking", "trackno", "trackingno",
    "fedex", "fedex_tracking", "trace", "traceid", "inquiry",
    "tracking #", "tracking#", "快递单号", "运单号", "跟踪号", "单号",
}
_CARRIER_COL_HINTS = ("邮寄方式", "物流方式", "物流商", "承运", "carrier", "shippingmethod", "ship_method")


def _norm_number(s: str) -> str:
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
    """单号一次查询的结果（输入顺序保持）。FedEx 复用跟踪号时一个号可能有多票。"""

    number: str
    remark: str = ""
    ok: bool = False
    infos: list[Any] = field(default_factory=list)  # list[FdxTrackInfo]
    error: str | None = None
    attempts: int = 1

    @property
    def info(self) -> Any:
        return self.infos[0] if self.infos else None

    @property
    def multi(self) -> bool:
        return self.ok and len(self.infos) > 1

    def _num_disp(self, i: int, total: int) -> str:
        return f"{self.number}[{i + 1}]" if total > 1 else self.number

    def to_summary_rows(self) -> list[dict[str, Any]]:
        if not (self.ok and self.infos):
            return [self._row(None, 0, 1)]
        return [self._row(info, i, len(self.infos)) for i, info in enumerate(self.infos)]

    def _row(self, info: Any, i: int, total: int) -> dict[str, Any]:
        disp = self._num_disp(i, total)
        dup = str(len(self.infos)) if self.multi else ""
        if self.ok and info:
            return {
                "跟踪号": disp, "备注": self.remark, "成功": "是", "多票": dup,
                "已交付": "是" if info.delivered else "否",
                "已取消": "是" if info.cancelled else "否",
                "当前状态": "查无此号" if info.not_found else (info.current_status or ""),
                "状态码": info.current_status_code or "",
                "建标时间": _fmt_dt(info.label_created_dt),
                "站点收件时间": _fmt_dt(info.picked_up_dt),
                "交付时间": _fmt_dt(info.delivery_dt),
                "交付城市": info.delivery_city or "",
                "交付州": info.delivery_state or "",
                "最近节点时间": _fmt_dt(info.last_event_dt),
                "节点数": len(info.events),
                "错误": self.error or "",
                "尝试次数": self.attempts,
            }
        info = info or (self.infos[0] if self.infos else None)
        return {
            "跟踪号": disp, "备注": self.remark, "成功": "是" if self.ok else "否", "多票": dup,
            "已交付": ("是" if (info and info.delivered) else ("否" if info else "")),
            "已取消": ("是" if (info and info.cancelled) else ("否" if info else "")),
            "当前状态": ("查无此号" if (info and info.not_found) else (info.current_status if info else "")),
            "状态码": info.current_status_code if info else "",
            "建标时间": _fmt_dt(info.label_created_dt) if info else "",
            "站点收件时间": _fmt_dt(info.picked_up_dt) if info else "",
            "交付时间": _fmt_dt(info.delivery_dt) if info else "",
            "交付城市": info.delivery_city if info else "",
            "交付州": info.delivery_state if info else "",
            "最近节点时间": _fmt_dt(info.last_event_dt) if info else "",
            "节点数": len(info.events) if info else "",
            "错误": self.error or "",
            "尝试次数": self.attempts,
        }

    def timeline_rows(self) -> list[dict[str, Any]]:
        if not (self.ok and self.infos):
            return []
        total = len(self.infos)
        rows = []
        for i, info in enumerate(self.infos):
            disp = self._num_disp(i, total)
            for ev in info.events:
                rows.append({
                    "跟踪号": disp, "备注": self.remark,
                    "分票": str(total) if total > 1 else "",
                    "节点时间": _fmt_dt(ev.dt), "事件码": ev.event_type or "",
                    "描述": ev.description or "", "派生状态": ev.derived_status or "",
                    "城市": ev.city or "", "州": ev.state or "", "邮编": ev.postal or "",
                    "国家": ev.country or "",
                })
        return rows

    def to_raw_entry(self) -> dict[str, Any]:
        return {
            "tracking": self.number,
            "remark": self.remark,
            "ok": self.ok,
            "error": self.error,
            "raw": {"trackingNumber": self.number,
                   "trackResults": [i.raw for i in self.infos if i.raw]},
        }


def _fmt_dt(dt: Any) -> str:
    if dt is None:
        return ""
    return dt.strftime("%Y-%m-%d %H:%M:%S")


# ── 输入清单读取（txt / csv / xlsx）──────────────────────────
def load_input_file(path: str) -> list[BatchItem]:
    lower = path.lower()
    if lower.endswith(".csv"):
        return _load_csv(path)
    if lower.endswith((".xlsx", ".xlsm")):
        return _load_xlsx(path)
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
    return _rows_to_items(rows)


def _load_xlsx(path: str) -> list[BatchItem]:
    try:
        import openpyxl
    except ImportError as exc:  # pragma: no cover
        raise ValueError("读 xlsx 需要 openpyxl；请 uv pip install openpyxl") from exc
    wb = openpyxl.load_workbook(path, read_only=True, data_only=True)
    try:
        ws = wb.active
        rows = []
        for row in ws.iter_rows(values_only=True):
            rows.append(["" if c is None else str(c) for c in row])
    finally:
        wb.close()
    if not rows:
        return []
    return _rows_to_items(rows)


def _rows_to_items(rows: list[list[str]]) -> list[BatchItem]:
    if not rows:
        return []
    header: list[str] | None = None
    track_idx = 0
    first = [(c or "").strip().lower() for c in rows[0]]
    if any(c in _TRACK_SYNONYMS for c in first if c):
        header = rows[0]
        track_idx = first.index(next(c for c in first if c in _TRACK_SYNONYMS))
        data = rows[1:]
    else:
        data = rows
    # 承运/备注列：表头含 邮寄方式/物流商/承运/carrier
    carrier_idx = None
    if header:
        for i, h in enumerate(header):
            if h and any(k in h.lower() for k in _CARRIER_COL_HINTS):
                carrier_idx = i
                break
    items: list[BatchItem] = []
    for row in data:
        if not row or track_idx >= len(row) or not (row[track_idx] or "").strip():
            continue
        number = _norm_number(row[track_idx])
        if not number:
            continue
        parts: list[str] = []
        if carrier_idx is not None and carrier_idx < len(row) and (row[carrier_idx] or "").strip():
            parts.append(f"承运={row[carrier_idx].strip()}")
        # 其余非跟踪列并入备注（仅前 3 个，避免过长）
        extra = 0
        for i, cell in enumerate(row):
            if i == track_idx or i == carrier_idx or not (cell or "").strip():
                continue
            if header and i < len(header) and (header[i] or "").strip():
                parts.append(f"{header[i].strip()}={cell.strip()}")
            else:
                parts.append(cell.strip())
            extra += 1
            if extra >= 3:
                break
        items.append(BatchItem(number=number, remark=" | ".join(parts)))
    return items


def _read_done(raw_path: str) -> set[str]:
    try:
        with open(raw_path, "r", encoding="utf-8") as fh:
            data = json.load(fh)
    except (OSError, ValueError):
        return set()
    if not isinstance(data, dict):
        return set()
    return {k for k, v in data.items() if isinstance(v, dict) and v.get("ok")}


def run_batch(
    batch_query: Callable[[list[str]], dict[str, list[FdxTrackInfo]]],
    items: Sequence[BatchItem],
    *,
    chunk: int = MAX_NUMBERS_PER_REQUEST,
    workers: int = 4,
    retries: int = 1,
    resume_from: str | None = None,
    delay: float = 0.0,
    on_progress: Callable[[int, int, BatchItem, bool], None] | None = None,
) -> list[Record]:
    """按 ≤chunk 分块并发查询，返回按输入顺序的 Record 列表。单块失败不中断。

    ``batch_query`` 形如 ``client.track_many``（输入号列表 → {号: FdxTrackInfo}）。
    FedEx 每请求 ≤30 号。块内的号若响应缺该号则标记 not_found；块级 HTTP/限流错误则整块标记失败并可重试。
    """
    done: set[str] = set()
    if resume_from:
        done = _read_done(resume_from)
    pending = [i for i in items if i.number not in done]
    total = len(pending)
    if total == 0:
        return []

    # 按输入顺序切块
    chunks: list[list[BatchItem]] = []
    for i in range(0, total, chunk):
        chunks.append(pending[i:i + chunk])

    results: dict[str, Record] = {}
    lock = threading.Lock()
    progress_done = [0]

    def _run_chunk(chunk_items: list[BatchItem]) -> None:
        chunk_result: dict[str, Record] = {}
        attempts = 0
        last_err: FedexTrackError | None = None
        while True:
            attempts += 1
            try:
                info_map = batch_query([it.number for it in chunk_items])
                for it in chunk_items:
                    infos = info_map.get(it.number) or []
                    if not infos:
                        rec = Record(number=it.number, remark=it.remark, ok=False,
                                     error="未在响应中找到该号", attempts=attempts)
                    else:
                        rec = Record(number=it.number, remark=it.remark, ok=True, infos=infos, attempts=attempts)
                    chunk_result[it.number] = rec
                break
            except FedexTrackError as exc:
                last_err = exc
                if exc.retriable and attempts <= retries:
                    time.sleep(min(2 ** attempts, 8))
                    continue
                for it in chunk_items:
                    chunk_result[it.number] = Record(
                        number=it.number, remark=it.remark, ok=False, error=str(exc), attempts=attempts)
                break
            except Exception as exc:  # 防御
                for it in chunk_items:
                    chunk_result[it.number] = Record(
                        number=it.number, remark=it.remark, ok=False,
                        error=f"{type(exc).__name__}: {exc}", attempts=attempts)
                break
        with lock:
            results.update(chunk_result)
            progress_done[0] += len(chunk_items)
        if on_progress:
            for it in chunk_items:
                on_progress(progress_done[0], total, it, chunk_result.get(it.number, Record(number=it.number)).ok)

    if workers <= 1 or len(chunks) <= 1:
        for c in chunks:
            _run_chunk(c)
            if delay:
                time.sleep(delay)
    else:
        with ThreadPoolExecutor(max_workers=min(workers, len(chunks))) as pool:
            futs = [pool.submit(_run_chunk, c) for c in chunks]
            for f in as_completed(futs):
                f.result()

    # 按输入顺序输出（去重）
    ordered: list[Record] = []
    seen: set[str] = set()
    for item in items:
        if item.number in seen:
            continue
        seen.add(item.number)
        rec = results.get(item.number)
        if rec is None:
            continue
        ordered.append(rec)
    return ordered


def merge_resumed_done(ordered: list[Record], resume_from: str | None) -> list[Record]:
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
        infos = parse_track_payload(number, {"output": {"completeTrackResults": [raw]}}) if isinstance(raw, dict) else []
        ordered.append(Record(number=number, remark=entry.get("remark", ""), ok=True, infos=infos, attempts=0))
    return ordered
