#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""生产只读统一预算闸门（requests / 响应字节 / 墙钟秒）。

契约（决策 Codex 2026-10-21 先决条件，见
`control/reviews/2026-10-21-gate-task.md`）：

  * 三类预算任一先到即停；**发请求前**拒绝，拒绝不产生 HTTP 调用。
  * 账本是 JSON：跨进程 / 崩溃续跑累计 requests、bytes、seconds，启动读取、
    每次请求（及读流分块）后原子写回，续跑不重置，**也不清除停止状态**。
  * 串行 GET，默认最小间隔 ≥1 秒；`stream=True` 分块读，**按剩余字节额度读取**
    （不是先读后裁），同时按剩余解压额度限长解压；解压额度到达后拒绝下一请求。
  * 禁止自动重定向（`allow_redirects=False`）；3xx 直接停，不逐跳绕过计数。
  * 超时绑定剩余墙钟：阻塞读的 socket 超时不超过剩余预算，每个分块前后检查
    墙钟；空响应也不能越过截止时间。
  * 429 遵守 Retry-After、最多重试 2 次；401/403 立即停；连续 3 次网络错误/5xx 立即停。
  * 发请求前把请求/字节/耗时预占写入账本；独占运行锁防止并发进程；
    崩溃恢复按保守上界补记字节与耗时。
  * `prod_budget.log` 每请求一行；账本与日志的请求数/字节必须一致（启动时核对）。

不传预算参数时调用方保持旧语义；只有显式启用闸门才创建账本与日志。
"""

from __future__ import annotations

import email.utils
import json
import os
import threading
import time
import zlib
from collections import Counter
from contextlib import contextmanager
from dataclasses import dataclass, field
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Callable, Iterator

import requests

try:                                  # requests 必然依赖 urllib3；read() 可能直接抛它
    from urllib3.exceptions import HTTPError as _Urllib3HTTPError
except ImportError:                   # pragma: no cover - 仅极端裁剪环境
    _Urllib3HTTPError = OSError

SCHEMA = "prod_budget/1"
LOG_SCHEMA = "prod_budget_log/1"
CHUNK = 64 * 1024
STOP_REASONS = ("requests", "bytes", "seconds", "auth", "redirect",
                "consecutive_failures", "retry_exhausted")
COMPRESSED_ENCODINGS = ("gzip", "x-gzip", "deflate")


class BudgetExhausted(RuntimeError):
    """闸门关闭：预算是枯竭 / 授权失败 / 连续失败 / 重试耗尽。

    调用方必须显式记录 partial，不得把已停止的运行当成完整证据。
    """

    def __init__(self, reason: str, detail: str = "", *, used: int | None = None,
                 limit: int | None = None):
        self.reason = reason
        self.detail = detail
        self.used = used
        self.limit = limit
        super().__init__(f"{reason}: {detail}" if detail else reason)


class BudgetLedgerError(RuntimeError):
    """账本不可读 / schema 不符 / 与日志对账不一致 / 并发运行。禁止静默重置。"""


class BudgetContextError(RuntimeError):
    """`iss_budget` 上下文重叠或退出时发现补丁被他人改写。"""


def parse_retry_after(value: Any) -> float | None:
    """Retry-After: 秒数或 HTTP-date。无法解析返回 None。"""
    if value is None or value == "":
        return None
    try:
        return max(0.0, float(str(value).strip()))
    except (TypeError, ValueError):
        pass
    try:
        dt = email.utils.parsedate_to_datetime(str(value))
    except (TypeError, ValueError):
        return None
    if dt is None:
        return None
    if dt.tzinfo is None:
        dt = dt.replace(tzinfo=timezone.utc)
    return max(0.0, (dt - datetime.now(timezone.utc)).total_seconds())


def _iso_now() -> str:
    return datetime.now(timezone.utc).isoformat(timespec="seconds")


def _nonneg(v: float | int | None) -> float | None:
    if v is None:
        return None
    v = float(v)
    return v if v >= 0 else 0.0


@dataclass
class BudgetResponse:
    status: int
    body: dict
    bytes: int
    decoded_bytes: int
    attempts: int
    headers: dict = field(default_factory=dict)


@dataclass
class _Body:
    wire: int = 0
    decoded: int = 0
    data: bytes = b""
    error: Exception | None = None
    oversized: bool = False
    deadline: bool = False


class _Decoder:
    """按 Content-Encoding 逐块解压并统计解压后字节；未知编码按 1:1 计。"""

    def __init__(self, content_encoding: str):
        enc = (content_encoding or "").strip().lower()
        self.encoding = enc
        self.compressed = enc in COMPRESSED_ENCODINGS
        self.known = self.compressed or enc in ("", "identity")
        self._deflate_raw = False
        self._zlib: Any = None
        if enc in ("gzip", "x-gzip"):
            self._zlib = zlib.decompressobj(16 + zlib.MAX_WBITS)
        elif enc == "deflate":
            self._zlib = zlib.decompressobj()
        elif enc in ("", "identity"):
            self._zlib = None
        else:
            # br / zstd 等未内置解码器：按传输字节计，显式标记 unknown
            self._zlib = None

    def feed(self, chunk: bytes, max_out: int = 0) -> bytes:
        """`max_out=0` 不限制；否则最多返回 max_out 字节（用于硬限解压额度）。"""
        if self._zlib is None:
            return chunk[:max_out] if max_out else chunk
        try:
            return (self._zlib.decompress(chunk, max_out) if max_out
                    else self._zlib.decompress(chunk))
        except zlib.error:
            if self.encoding != "deflate" or self._deflate_raw:
                raise
            # 服务器发的是 raw deflate（无 zlib 头）
            self._deflate_raw = True
            self._zlib = zlib.decompressobj(-zlib.MAX_WBITS)
            return (self._zlib.decompress(chunk, max_out) if max_out
                    else self._zlib.decompress(chunk))


class _RunLock:
    """跨进程独占运行锁；进程死亡时由操作系统自动释放（不是 O_EXCL 残留文件）。"""

    def __init__(self, path: Path):
        self.path = path
        self._fh = None

    def acquire(self) -> None:
        self.path.parent.mkdir(parents=True, exist_ok=True)
        fh = open(self.path, "a+b")
        try:
            if os.name == "nt":
                import msvcrt
                fh.seek(0, os.SEEK_END)
                if fh.tell() == 0:
                    fh.write(b"\0")
                    fh.flush()
                fh.seek(0)
                msvcrt.locking(fh.fileno(), msvcrt.LK_NBLCK, 1)
            else:
                import fcntl
                fcntl.flock(fh.fileno(), fcntl.LOCK_EX | fcntl.LOCK_NB)
        except OSError as e:
            fh.close()
            raise BudgetLedgerError(
                f"账本已被另一个运行占用（独占锁失败，禁止并发取数）: {self.path}: {e}"
            ) from e
        self._fh = fh

    def release(self) -> None:
        fh = self._fh
        self._fh = None
        if fh is None:
            return
        try:
            if os.name == "nt":
                import msvcrt
                fh.seek(0)
                try:
                    msvcrt.locking(fh.fileno(), msvcrt.LK_UNLCK, 1)
                except OSError:
                    pass
            else:
                import fcntl
                try:
                    fcntl.flock(fh.fileno(), fcntl.LOCK_UN)
                except OSError:
                    pass
        finally:
            fh.close()


def _stream_at_eof(resp: Any, wire: int, headers: dict) -> bool:
    """判断响应流是否已结束；无法证明时返回 False（保守按未结束处理）。"""
    raw = getattr(resp, "raw", None)
    if raw is not None:
        eof = getattr(raw, "eof", None)
        if eof is not None:
            return bool(eof)
        for attr in ("isclosed", "closed"):
            v = getattr(raw, attr, None)
            if callable(v):
                try:
                    if v():
                        return True
                except Exception:  # noqa: BLE001 - 传输层实现差异
                    pass
            elif v is not None and bool(v):
                return True
        remaining = getattr(raw, "length_remaining", None)
        if remaining is not None:
            try:
                return int(remaining) == 0
            except (TypeError, ValueError):
                pass
    length = headers.get("Content-Length") or headers.get("content-length")
    if length is not None:
        try:
            return int(length) == wire
        except (TypeError, ValueError):
            pass
    return False


def _iter_wire_chunks(resp: Any, limit_fn: Callable[[], int]) -> Iterator[bytes]:
    """优先读未解压的传输字节；`limit_fn()` 在**每次读之前**给出本次最大读取量。"""
    raw = getattr(resp, "raw", None)
    if raw is not None and hasattr(raw, "read"):
        while True:
            amt = limit_fn()
            if amt <= 0:
                return
            try:
                chunk = raw.read(amt, decode_content=False)
            except TypeError:
                chunk = raw.read(amt)
            if not chunk:
                return
            if len(chunk) > amt:
                # 传输层无视 amt：只交付额度内字节并停止，绝不继续超额读
                yield chunk[:amt]
                return
            yield chunk
        return
    if raw is not None and hasattr(raw, "stream"):
        # 旧式替身 / 无 read 的传输层：无法在流中途缩小 amt，退化为固定块读取；
        # `_read_body` 仍会按剩余额度裁剪并停止。
        yield from raw.stream(CHUNK, decode_content=False)
        return
    # 没有 raw（如简单替身）：iter_content 已是解压后的字节，wire=decoded
    yield from resp.iter_content(CHUNK)


class ProductionBudget:
    """统一账本。`HttpBudget(limit)` 是它的向后兼容包装（仅请求数上限）。"""

    def __init__(self, max_requests: int | None = None, max_bytes: int | None = None,
                 max_seconds: float | None = None, ledger_path: str | os.PathLike | None = None,
                 log_path: str | os.PathLike | None = None, min_interval: float = 0.0,
                 timeout: float = 60.0, max_retries: int = 2,
                 max_consecutive_failures: int = 3,
                 clock: Callable[[], float] | None = None,
                 wall_clock: Callable[[], float] | None = None,
                 sleep: Callable[[float], None] | None = None,
                 http_get: Callable[..., Any] | None = None,
                 lock_path: str | os.PathLike | None = None):
        self.max_requests = None if max_requests is None else int(_nonneg(max_requests) or 0)
        self.max_bytes = None if max_bytes is None else int(_nonneg(max_bytes) or 0)
        self.max_seconds = _nonneg(max_seconds)
        self.min_interval = max(0.0, float(min_interval or 0.0))
        self.timeout = float(timeout)
        self.max_retries = max(0, int(max_retries))
        self.max_consecutive_failures = max(1, int(max_consecutive_failures))
        self.ledger_path = Path(ledger_path) if ledger_path else None
        if log_path is not None:
            self.log_path = Path(log_path)
        elif self.ledger_path is not None:
            self.log_path = self.ledger_path.with_suffix(".log")
        else:
            self.log_path = None
        if lock_path is not None:
            self.lock_path = Path(lock_path)
        elif self.ledger_path is not None:
            self.lock_path = self.ledger_path.with_name(self.ledger_path.name + ".lock")
        else:
            self.lock_path = None
        self.clock = clock or time.monotonic
        self.wall_clock = wall_clock or time.time
        self.sleep = sleep or time.sleep
        self.http_get = http_get          # None → 调用时取 requests.get（便于测试打桩）

        self.used = 0
        self.used_bytes = 0
        self.decoded_bytes = 0
        self.used_failures = 0
        self.refused = 0
        self.by_kind: Counter = Counter()
        self.events: list[dict] = []
        self.exhausted = False
        self.stop_reason: str | None = None
        self.previous_stop_reason: str | None = None
        self.consecutive_failures = 0
        self._seq = 0
        self._last_request_at: float | None = None
        self._last_request_epoch: float | None = None
        self._pending: dict | None = None
        self._base_seconds = 0.0
        self._run_start = self.clock()
        self._started_at = _iso_now()
        self._runs: list[dict] = []
        self._closed = False
        self._log_handle = None
        self._lock: _RunLock | None = None

        try:
            if self.lock_path is not None:
                self._lock = _RunLock(self.lock_path)
                self._lock.acquire()
            self._load()
            if self.log_path is not None:
                self.log_path.parent.mkdir(parents=True, exist_ok=True)
                self._log_handle = open(self.log_path, "a", encoding="utf-8", newline="\n")
            self._recover_state_or_raise()
        except Exception:
            self._release_resources()
            raise

    def _release_resources(self) -> None:
        if self._log_handle is not None:
            try:
                self._log_handle.close()
            except OSError:
                pass
            self._log_handle = None
        if self._lock is not None:
            self._lock.release()
            self._lock = None

    # ── 账本读写 ──────────────────────────────────────
    def _load(self) -> None:
        if self.ledger_path is None or not self.ledger_path.exists():
            return
        try:
            data = json.loads(self.ledger_path.read_text(encoding="utf-8"))
        except (OSError, ValueError) as e:
            raise BudgetLedgerError(f"账本不可读: {self.ledger_path}: {e}") from e
        if not isinstance(data, dict) or data.get("schema") != SCHEMA:
            raise BudgetLedgerError(f"账本 schema 不符: {self.ledger_path}")
        used = data.get("used") or {}
        self.used = int(used.get("requests") or 0)
        self.used_bytes = int(used.get("bytes") or 0)
        self.decoded_bytes = int(used.get("decoded_bytes") or 0)
        self.used_failures = int(used.get("failures") or 0)
        self._base_seconds = float(used.get("seconds") or 0.0)
        self.refused = int(data.get("refused") or 0)
        self.by_kind = Counter(data.get("by_kind") or {})
        self._seq = self.used
        self._runs = list(data.get("runs") or [])
        # 停止状态是持久锁停：续跑不清除。要重新放行必须人工轮换账本。
        self.stop_reason = data.get("stop_reason")
        self.exhausted = bool(data.get("exhausted")) or self.stop_reason is not None
        self.previous_stop_reason = data.get("previous_stop_reason")
        pending = data.get("pending")
        self._pending = pending if isinstance(pending, dict) else None
        epoch = data.get("last_request_epoch")
        self._last_request_epoch = float(epoch) if epoch is not None else None
        if self.min_interval > 0 and self._last_request_epoch is not None:
            # 跨进程最小间隔：只要上次请求距今不足一个间隔（含时钟回拨），
            # 就从本进程当前时刻重新等满一个间隔——只会更慢，不会更短。
            if self.wall_clock() - self._last_request_epoch < self.min_interval:
                self._last_request_at = self.clock()

    def _payload(self) -> dict:
        return {
            "schema": SCHEMA,
            "updated_at": _iso_now(),
            "limits": {"max_requests": self.max_requests, "max_bytes": self.max_bytes,
                       "max_seconds": self.max_seconds,
                       "min_interval": self.min_interval},
            "used": {"requests": self.used, "bytes": self.used_bytes,
                     "decoded_bytes": self.decoded_bytes,
                     "seconds": round(self.used_seconds, 3),
                     "failures": self.used_failures},
            "refused": self.refused,
            "by_kind": dict(sorted(self.by_kind.items())),
            "exhausted": self.exhausted,
            "stop_reason": self.stop_reason,
            "previous_stop_reason": self.previous_stop_reason,
            "last_request_epoch": self._last_request_epoch,
            "pending": self._pending,
            "runs": self._runs,
        }

    def _persist(self) -> None:
        if self.ledger_path is None:
            return
        self.ledger_path.parent.mkdir(parents=True, exist_ok=True)
        tmp = self.ledger_path.with_name(f"{self.ledger_path.name}.tmp.{os.getpid()}")
        tmp.write_text(json.dumps(self._payload(), ensure_ascii=False, indent=1),
                       encoding="utf-8")
        # Windows 上 os.replace 会被杀软/索引器短暂占用目标文件（WinError 5），重试即可
        for delay in (0.0, 0.01, 0.02, 0.05):
            if delay:
                time.sleep(delay)
            try:
                os.replace(tmp, self.ledger_path)
                return
            except PermissionError:
                if delay == 0.05:
                    raise

    def _scan_log(self) -> tuple[int, int, int, dict | None]:
        """返回 (行数, bytes 合计, 坏行数, 最后一行)。"""
        if self.log_path is None or not self.log_path.exists():
            return 0, 0, 0, None
        requests_n = bytes_n = bad = 0
        last = None
        with open(self.log_path, encoding="utf-8") as f:
            for line in f:
                line = line.strip()
                if not line:
                    continue
                try:
                    r = json.loads(line)
                except ValueError:
                    bad += 1
                    continue
                requests_n += 1
                bytes_n += int(r.get("bytes") or 0)
                last = r
        return requests_n, bytes_n, bad, last

    def _append_log(self, line: dict) -> None:
        if self._log_handle is None:
            return
        self._log_handle.write(json.dumps(line, ensure_ascii=False) + "\n")
        self._log_handle.flush()
        try:
            os.fsync(self._log_handle.fileno())
        except OSError:
            pass

    def _recover_state_or_raise(self) -> None:
        if self._pending is not None:
            self._recover_pending()
        self._reconcile_or_raise()

    def _recover_pending(self) -> None:
        """崩溃在 HTTP 途中：请求已持久预占，字节/耗时按保守上界补记。"""
        pending = self._pending or {}
        seq = int(pending.get("seq") or 0)
        log_n, log_bytes, bad, last = self._scan_log()
        if bad:
            raise BudgetLedgerError(f"日志含 {bad} 个坏行，拒绝崩溃恢复")
        if seq > self.used:
            # 预占记录领先账本计数（理论上预占与计数同一次写盘）：补记请求
            self.used = seq
            self._seq = seq
            kind = pending.get("kind")
            if kind:
                self.by_kind[kind] += 1

        if last is not None and int(last.get("seq") or -1) == seq and log_n == self.used:
            # 日志已写、账本未写：日志是精确事实，直接采用（不再加保守上界）
            self.used_bytes = int(last.get("cum_bytes") or 0)
            self.decoded_bytes = int(last.get("cum_decoded") or 0)
            self._base_seconds = max(self._base_seconds,
                                     float(last.get("cum_seconds") or 0.0))
            status = last.get("status")
            if (isinstance(status, int) and status >= 500) or status in (
                    "timeout", "network_error", "read_error", "oversized", "deadline"):
                self.used_failures += 1
            self._pending = None
            self._persist()
            return

        if log_n not in (self.used - 1,):
            raise BudgetLedgerError(
                "崩溃预占与日志行数不一致，拒绝续跑（禁止静默重置）: "
                f"ledger requests={self.used}, log requests={log_n}, pending seq={seq}")

        # 保守恢复：最后一次落盘之后可能又读了一块（≤CHUNK 传输字节）、
        # 一次阻塞读可能耗掉本次请求的 timeout。压缩响应的一块可能解压到
        # 剩余额度上限，因此直接把解压额度记满。
        old_bytes, old_dec = self.used_bytes, self.decoded_bytes
        if self.max_bytes is None:
            self.used_bytes += CHUNK
            self.decoded_bytes += CHUNK
        else:
            self.used_bytes = min(self.max_bytes,
                                  self.used_bytes + min(CHUNK, max(
                                      0, self.max_bytes - self.used_bytes)))
            enc = str(pending.get("content_encoding") or "").strip().lower()
            if enc in COMPRESSED_ENCODINGS:
                self.decoded_bytes = self.max_bytes
            else:
                self.decoded_bytes = min(
                    self.max_bytes,
                    self.decoded_bytes + min(CHUNK, max(
                        0, self.max_bytes - self.decoded_bytes)))
        timeout_s = pending.get("timeout_seconds")
        elapsed_allow = max(0.0, float(
            self.timeout if timeout_s is None else timeout_s))
        self._base_seconds += elapsed_allow
        charged_wire = max(0, self.used_bytes - log_bytes)
        self._append_log({
            "schema": LOG_SCHEMA, "seq": seq, "ts": _iso_now(),
            "kind": pending.get("kind"), "path": str(pending.get("path") or "")[:300],
            "status": "recovered_crash", "bytes": charged_wire,
            "decoded_bytes": max(0, self.decoded_bytes - old_dec),
            "cum_requests": self.used, "cum_bytes": self.used_bytes,
            "cum_decoded": self.decoded_bytes,
            "cum_seconds": round(self.used_seconds, 3),
            "elapsed_ms": round(elapsed_allow * 1000, 1), "attempt": 0,
            "recovered": True,
            "note": "crash mid-request: conservative byte/time upper bound",
        })
        self.events.append({"n": seq, "kind": pending.get("kind"),
                            "detail": "recovered_crash",
                            "bytes": max(0, self.used_bytes - old_bytes),
                            "decoded_bytes": max(0, self.decoded_bytes - old_dec)})
        self._pending = None
        self._persist()

    def _reconcile_or_raise(self) -> None:
        if self.log_path is None or not self.log_path.exists():
            if self.used:
                raise BudgetLedgerError(
                    f"账本已有 {self.used} 次请求但日志缺失: {self.log_path}")
            return
        rec = self.reconcile()
        if rec["ok"]:
            return
        if self._recover_from_log_tail(rec):
            return
        raise BudgetLedgerError(
            "账本与日志不一致，拒绝续跑（禁止静默重置）: "
            f"ledger={rec['ledger_requests']} req/{rec['ledger_bytes']} B, "
            f"log={rec['log_requests']} req/{rec['log_bytes']} B")

    def _recover_from_log_tail(self, rec: dict) -> bool:
        """崩溃恢复：日志先落盘、账本后写；最多一条日志领先，按累计值补齐。"""
        if rec["log_requests"] != self.used + 1 or rec["bad_lines"]:
            return False
        last = None
        with open(self.log_path, encoding="utf-8") as f:
            for line in f:
                line = line.strip()
                if line:
                    last = line
        if last is None:
            return False
        try:
            tail = json.loads(last)
            cum_req = int(tail["cum_requests"])
            cum_bytes = int(tail["cum_bytes"])
        except (ValueError, KeyError, TypeError):
            return False
        if cum_req != self.used + 1 or cum_bytes != rec["log_bytes"]:
            return False
        self.used = cum_req
        self._seq = cum_req
        self.used_bytes = cum_bytes
        self.decoded_bytes = int(tail.get("cum_decoded") or self.decoded_bytes)
        # 尾恢复也要恢复耗时，否则跨进程墙钟会被少算
        self._base_seconds = max(self._base_seconds,
                                 float(tail.get("cum_seconds") or 0.0))
        status = tail.get("status")
        if (isinstance(status, int) and status >= 500) or status in (
                "timeout", "network_error", "read_error", "oversized", "deadline"):
            self.used_failures += 1
        kind = tail.get("kind")
        if kind in ("retry", "iss", "enrich", "probe"):
            self.by_kind[kind] += 1
        self.events.append({"n": self._seq, "kind": kind, "detail": "recovered_from_log",
                            "status": tail.get("status"), "bytes": tail.get("bytes", 0),
                            "decoded_bytes": tail.get("decoded_bytes", 0),
                            "elapsed_ms": tail.get("elapsed_ms", 0),
                            "attempt": tail.get("attempt", 0)})
        self._persist()
        return True

    def reconcile(self) -> dict:
        """账本 vs `prod_budget.log` 的请求数/字节对账。"""
        rec = {"ok": True, "log_exists": False, "log_requests": 0, "log_bytes": 0,
               "ledger_requests": self.used, "ledger_bytes": self.used_bytes,
               "bad_lines": 0, "mismatches": []}
        if self.log_path is None:
            return rec                    # 旧模式：未启用请求日志，无对账对象
        if not self.log_path.exists():
            if self.used:
                rec["ok"] = False
                rec["mismatches"].append("ledger_has_requests_but_no_log")
            return rec
        rec["log_exists"] = True
        log_n, log_bytes, bad, _ = self._scan_log()
        rec["log_requests"] = log_n
        rec["log_bytes"] = log_bytes
        rec["bad_lines"] = bad
        if rec["log_requests"] != self.used:
            rec["ok"] = False
            rec["mismatches"].append(
                f"requests ledger={self.used} log={rec['log_requests']}")
        if rec["log_bytes"] != self.used_bytes:
            rec["ok"] = False
            rec["mismatches"].append(
                f"bytes ledger={self.used_bytes} log={rec['log_bytes']}")
        if rec["bad_lines"]:
            rec["ok"] = False
            rec["mismatches"].append(f"bad_log_lines={rec['bad_lines']}")
        return rec

    # ── 预算读数 ──────────────────────────────────────
    @property
    def used_seconds(self) -> float:
        frozen = getattr(self, "_frozen_seconds", None)
        if frozen is not None:
            return frozen
        return self._base_seconds + max(0.0, self.clock() - self._run_start)

    @property
    def remaining(self) -> int | None:
        if self.max_requests is None:
            return None
        return max(0, self.max_requests - self.used)

    @property
    def remaining_bytes(self) -> int | None:
        if self.max_bytes is None:
            return None
        return max(0, self.max_bytes - self.used_bytes)

    @property
    def remaining_decoded(self) -> int | None:
        if self.max_bytes is None:
            return None
        return max(0, self.max_bytes - self.decoded_bytes)

    @property
    def remaining_seconds(self) -> float | None:
        if self.max_seconds is None:
            return None
        return max(0.0, self.max_seconds - self.used_seconds)

    # 旧字段名（HttpBudget）
    @property
    def limit(self) -> int | None:
        return self.max_requests

    def _stop(self, reason: str, detail: str = "") -> None:
        if not self.exhausted:
            self.exhausted = True
            self.stop_reason = reason
        self._persist()

    def _refuse(self, reason: str, detail: str) -> None:
        """预检拒绝：不占用请求数、不产生 HTTP、不写请求日志。"""
        self.refused += 1
        self._stop(reason, detail)
        raise BudgetExhausted(reason, detail, used=self.used, limit=self.max_requests)

    def _preflight(self, kind: str) -> None:
        # 持久停止优先：401/403/预算耗尽后，任何新请求都在这里被拦下
        if self.exhausted:
            self.refused += 1
            self._persist()
            raise BudgetExhausted(
                self.stop_reason or "stopped",
                f"{kind}: gate already stopped (persistent stop; rotate ledger to reset)",
                used=self.used, limit=self.max_requests)
        if self.max_requests is not None and self.used >= self.max_requests:
            self._refuse("requests", f"{kind}: request budget {self.max_requests} used up")
        if self.max_bytes is not None and self.used_bytes >= self.max_bytes:
            self._refuse("bytes", f"{kind}: byte budget {self.max_bytes} used up")
        if self.max_bytes is not None and self.decoded_bytes >= self.max_bytes:
            self._refuse("bytes",
                         f"{kind}: decoded byte budget {self.max_bytes} used up")
        if self.max_seconds is not None and self.used_seconds >= self.max_seconds:
            self._refuse("seconds", f"{kind}: wall-clock budget {self.max_seconds}s used up")

    def reserve(self, kind: str, detail: str = "") -> None:
        """预检并占用一次请求；旧 `spend()` 的语义。"""
        self._preflight(kind)
        self.used += 1
        self._seq += 1
        self.by_kind[kind] += 1
        if self.ledger_path is None:      # 旧模式：保持事件结构不变
            self.events.append({"n": self._seq, "kind": kind, "detail": detail})
        else:
            self._persist()

    # 旧字段名（HttpBudget）
    def spend(self, kind: str, detail: str = "") -> None:
        self.reserve(kind, detail)

    def _throttle(self) -> None:
        """串行上限：请求起点之间至少 min_interval 秒。"""
        if self.min_interval <= 0 or self._last_request_at is None:
            return
        wait = self._last_request_at + self.min_interval - self.clock()
        if wait <= 0:
            return
        rem = self.remaining_seconds
        if rem is not None and wait >= rem:
            self._refuse("seconds", f"min_interval wait {wait:.2f}s exceeds remaining {rem:.2f}s")
        self.sleep(wait)

    def _bounded_timeout(self, timeout: float) -> float:
        """socket 超时不超过剩余墙钟；剩余为 0 时预检已拒绝。"""
        rem = self.remaining_seconds
        if rem is None:
            return timeout
        return max(0.001, min(timeout, rem))

    def _deadline_passed(self) -> bool:
        rem = self.remaining_seconds
        return rem is not None and rem <= 0

    def _reserve_attempt(self, kind: str, path: str, timeout_bound: float) -> None:
        """发请求前持久预占：请求数、最后请求时刻、字节/耗时起点。"""
        self._preflight(kind)
        self.used += 1
        self._seq += 1
        self.by_kind[kind] += 1
        self._last_request_at = self.clock()
        self._last_request_epoch = self.wall_clock()
        if self.ledger_path is not None:
            self._pending = {
                "seq": self._seq, "kind": kind, "path": path[:300],
                "started_at": _iso_now(), "started_epoch": self._last_request_epoch,
                "timeout_seconds": round(timeout_bound, 3),
                "elapsed_seconds": 0.0, "wire_bytes": 0, "decoded_bytes": 0,
                "content_encoding": "",
            }
        self._persist()

    def _checkpoint(self, body: _Body, started: float) -> None:
        """读流分块后落盘：崩溃时最多只丢最后一块的计数。"""
        if self.ledger_path is None:
            return
        if self._pending is not None:
            self._pending.update({
                "wire_bytes": body.wire, "decoded_bytes": body.decoded,
                "elapsed_seconds": round(max(0.0, self.clock() - started), 3),
            })
        self._persist()

    def _wire_read_limit(self) -> int:
        if self.max_bytes is None:
            return CHUNK
        return min(CHUNK, max(0, self.max_bytes - self.used_bytes))

    def _decoded_max_out(self) -> int:
        if self.max_bytes is None:
            return 0
        return max(1, self.max_bytes - self.decoded_bytes + 1)

    def _note(self, kind: str, path: str, status: Any, *, wire: int, decoded: int,
              elapsed: float, attempt: int, error: str | None = None,
              failed: bool = False) -> None:
        if failed:
            self.used_failures += 1
        event = {"n": self._seq, "kind": kind, "detail": path[:120],
                 "status": status, "bytes": wire, "decoded_bytes": decoded,
                 "elapsed_ms": round(elapsed * 1000, 1), "attempt": attempt}
        if error:
            event["error"] = error[:200]
        if self.ledger_path is not None:   # 旧模式事件由 reserve() 保持原结构
            self.events.append(event)
        if self._log_handle is not None:
            line = {"schema": LOG_SCHEMA, "seq": self._seq, "ts": _iso_now(),
                    "kind": kind, "path": path[:300], "status": status,
                    "bytes": wire, "decoded_bytes": decoded,
                    "cum_requests": self.used, "cum_bytes": self.used_bytes,
                    "cum_decoded": self.decoded_bytes,
                    "cum_seconds": round(self.used_seconds, 3),
                    "elapsed_ms": round(elapsed * 1000, 1), "attempt": attempt}
            if error:
                line["error"] = error[:200]
            self._append_log(line)
        self._pending = None
        self._persist()

    # ── 读流 ──────────────────────────────────────────
    def _read_body(self, resp: Any, headers: dict, started: float) -> _Body:
        body = _Body()
        decoder = _Decoder(str(headers.get("Content-Encoding") or ""))
        if self._pending is not None:
            self._pending["content_encoding"] = decoder.encoding
            self._persist()
        chunks = _iter_wire_chunks(resp, self._wire_read_limit)
        try:
            while True:
                # 截止优先于下一次 read：阻塞读开始前就拒绝继续
                if self._deadline_passed():
                    body.deadline = True
                    return body
                try:
                    chunk = next(chunks)
                except StopIteration:
                    break
                if not chunk:
                    continue
                remaining_wire = self.remaining_bytes
                take = len(chunk)
                if remaining_wire is not None:
                    take = min(take, remaining_wire)
                if take <= 0:
                    body.oversized = True
                    return body
                self.used_bytes += take
                body.wire += take
                piece = chunk[:take]
                try:
                    out = decoder.feed(piece, self._decoded_max_out())
                except zlib.error:
                    # 压缩流被字节上限截断 / 编码损坏：按越界停止，不读完
                    self._checkpoint(body, started)
                    body.oversized = True
                    return body
                over = False
                remaining_decoded = self.remaining_decoded
                if remaining_decoded is not None and len(out) > remaining_decoded:
                    out = out[:remaining_decoded]
                    over = True
                self.decoded_bytes += len(out)
                body.decoded += len(out)
                body.data += out
                self._checkpoint(body, started)
                if over or take < len(chunk):
                    body.oversized = True
                    return body
            # 额度恰好用尽且流未结束：按超大响应处理（读之前已封顶，不会超额读）
            if (self.max_bytes is not None and self.used_bytes >= self.max_bytes
                    and not _stream_at_eof(resp, body.wire, headers)):
                body.oversized = True
        except (requests.RequestException, _Urllib3HTTPError, OSError) as e:
            # 读流超时/断连：已计字节保留
            body.error = e
        return body

    # ── 单次逻辑请求（含重试）────────────────────────
    def fetch(self, kind: str, path: str, base_url: str, key: str, secret: str, *,
              timeout: float | None = None, label: str = "") -> BudgetResponse:
        """串行 GET + 三类预算 + 重试策略；任何停止都抛 BudgetExhausted。"""
        url = f"{base_url}{path}"
        # 只接受可离线解码的编码：解压后字节上限才真正可执行
        headers = {"Authorization": f"token {key}:{secret}",
                   "Accept-Encoding": "gzip, deflate"}
        timeout = self.timeout if timeout is None else float(timeout)
        attempt = 0
        while True:
            # 预检 → 节流 → 再预检；全部在 HTTP 之前
            self._preflight(kind)
            self._throttle()
            self._preflight(kind)
            timeout_bound = self._bounded_timeout(timeout)
            self._reserve_attempt(kind if attempt == 0 else "retry", path, timeout_bound)
            started = self.clock()
            try:
                get = self.http_get or requests.get
                # 禁止自动重定向：跳转的每一跳都不会绕过计数/字节/间隔
                resp = get(url, headers=headers, timeout=timeout_bound, stream=True,
                           allow_redirects=False)
            except requests.Timeout as e:
                self.consecutive_failures += 1
                self._note(kind, path, "timeout", wire=0, decoded=0,
                           elapsed=self.clock() - started, attempt=attempt,
                           error=f"Timeout: {e}", failed=True)
                self._after_failure(attempt, "consecutive_failures",
                                    f"timeout ({self.consecutive_failures} consecutive)")
                attempt += 1
                continue
            except requests.RequestException as e:
                self.consecutive_failures += 1
                self._note(kind, path, "network_error", wire=0, decoded=0,
                           elapsed=self.clock() - started, attempt=attempt,
                           error=f"{type(e).__name__}: {e}", failed=True)
                self._after_failure(attempt, "consecutive_failures",
                                    f"{type(e).__name__} "
                                    f"({self.consecutive_failures} consecutive)")
                attempt += 1
                continue

            status = int(resp.status_code)
            resp_headers = dict(getattr(resp, "headers", {}) or {})
            try:
                if 300 <= status < 400:
                    self._note(kind, path, status, wire=0, decoded=0,
                               elapsed=self.clock() - started, attempt=attempt,
                               error="redirect_refused", failed=True)
                    loc = resp_headers.get("Location") or resp_headers.get("location") or ""
                    self._stop("redirect", f"HTTP {status} Location={str(loc)[:120]}")
                    raise BudgetExhausted(
                        "redirect", f"HTTP {status} refused (allow_redirects=False)",
                        used=self.used, limit=self.max_requests)
                if status in (401, 403):
                    self._note(kind, path, status, wire=0, decoded=0,
                               elapsed=self.clock() - started, attempt=attempt,
                               error="auth_stop", failed=True)
                    self._stop("auth", f"HTTP {status}")
                    raise BudgetExhausted("auth", f"HTTP {status} on {path[:120]}",
                                          used=self.used, limit=self.max_requests)
                if status == 429:
                    self._note(kind, path, status, wire=0, decoded=0,
                               elapsed=self.clock() - started, attempt=attempt,
                               error="rate_limited", failed=True)
                    retry_after = parse_retry_after(resp_headers.get("Retry-After"))
                    if attempt >= self.max_retries:
                        self._stop("retry_exhausted",
                                   f"429 after {attempt} retries")
                        raise BudgetExhausted("retry_exhausted",
                                              f"429 after {attempt} retries",
                                              used=self.used, limit=self.max_requests)
                    wait = 1.0 if retry_after is None else retry_after
                    rem = self.remaining_seconds
                    if rem is not None and wait >= rem:
                        self._stop("seconds",
                                   f"Retry-After {wait:.1f}s exceeds remaining {rem:.1f}s")
                        raise BudgetExhausted("seconds", "Retry-After exceeds wall budget",
                                              used=self.used, limit=self.max_requests)
                    if wait > 0:
                        self.sleep(wait)
                    attempt += 1
                    continue

                # 可中断截止：墙钟到点时从另一线程关闭响应，让阻塞 read 立即失败；
                # 正常读完则取消。这是 socket 超时之外的第二道截止保险。
                timer = None
                rem = self.remaining_seconds
                if rem is not None and rem > 0:
                    def _interrupt() -> None:
                        close = getattr(resp, "close", None)
                        if callable(close):
                            try:
                                close()
                            except Exception:  # noqa: BLE001 - 关连接失败不影响判定
                                pass
                    timer = threading.Timer(rem, _interrupt)
                    timer.daemon = True
                    timer.start()
                try:
                    body = self._read_body(resp, resp_headers, started)
                finally:
                    if timer is not None:
                        timer.cancel()
                elapsed = self.clock() - started
                if body.oversized:
                    self._note(kind, path, "oversized", wire=body.wire,
                               decoded=body.decoded, elapsed=elapsed,
                               attempt=attempt, error="byte_budget_exceeded", failed=True)
                    self._stop("bytes", f"response exceeded remaining byte budget")
                    raise BudgetExhausted("bytes", "response exceeded byte budget",
                                          used=self.used, limit=self.max_requests)
                if body.deadline or self._deadline_passed():
                    body.deadline = True
                    self._note(kind, path, "deadline", wire=body.wire,
                               decoded=body.decoded, elapsed=elapsed,
                               attempt=attempt, error="wall_budget_exceeded", failed=True)
                    self._stop("seconds", "wall-clock budget exceeded mid-response")
                    raise BudgetExhausted("seconds", "wall-clock budget exceeded mid-response",
                                          used=self.used, limit=self.max_requests)
                if body.error is not None:
                    self.consecutive_failures += 1
                    self._note(kind, path, "read_error", wire=body.wire,
                               decoded=body.decoded, elapsed=elapsed, attempt=attempt,
                               error=f"{type(body.error).__name__}: {body.error}",
                               failed=True)
                    self._after_failure(attempt, "consecutive_failures",
                                        f"read error ({self.consecutive_failures} consecutive)")
                    attempt += 1
                    continue
                self._note(kind, path, status, wire=body.wire, decoded=body.decoded,
                           elapsed=elapsed, attempt=attempt,
                           failed=status >= 500)
                if status >= 500:
                    self.consecutive_failures += 1
                    self._after_failure(attempt, "consecutive_failures",
                                        f"HTTP {status} ({self.consecutive_failures} consecutive)")
                    attempt += 1
                    continue
                self.consecutive_failures = 0
                try:
                    parsed = json.loads(body.data) if body.data else {}
                except ValueError:
                    parsed = {}
                if not isinstance(parsed, dict):
                    parsed = {}
                return BudgetResponse(status=status, body=parsed, bytes=body.wire,
                                      decoded_bytes=body.decoded, attempts=attempt + 1,
                                      headers=resp_headers)
            finally:
                close = getattr(resp, "close", None)
                if callable(close):
                    close()

    def _after_failure(self, attempt: int, reason: str, detail: str) -> None:
        if self.consecutive_failures >= self.max_consecutive_failures:
            self._stop(reason, f"{detail}; max {self.max_consecutive_failures} consecutive")
            raise BudgetExhausted(reason, detail, used=self.used,
                                  limit=self.max_requests)
        if attempt >= self.max_retries:
            self._stop("retry_exhausted", f"{detail}; {attempt} retries used")
            raise BudgetExhausted("retry_exhausted", detail, used=self.used,
                                  limit=self.max_requests)

    # ── 收尾 / 报告 ───────────────────────────────────
    def close(self) -> None:
        if self._closed:
            return
        self._closed = True
        final_seconds = self.used_seconds
        self._runs.append({
            "started_at": self._started_at, "ended_at": _iso_now(), "pid": os.getpid(),
            "requests": self.used, "bytes": self.used_bytes,
            "seconds": round(final_seconds, 3), "stop_reason": self.stop_reason,
        })
        self._frozen_seconds = final_seconds
        self._persist()
        self._release_resources()

    def __enter__(self) -> "ProductionBudget":
        return self

    def __exit__(self, *exc: Any) -> None:
        self.close()

    def as_log(self) -> dict:
        if self.ledger_path is None:
            # 未启用闸门：保持旧 manifest 字段逐字节不变（离线结果/哈希不变）
            return {"limit": self.max_requests, "used": self.used,
                    "remaining": self.remaining,
                    "by_kind": dict(sorted(self.by_kind.items())),
                    "exhausted": self.exhausted,
                    "events": self.events[:50],
                    "events_truncated": len(self.events) > 50,
                    "note": ("request-level budget shared by enrichment, probe pages "
                             "and retries")}
        rec = self.reconcile()
        return {
            "limit": self.max_requests,
            "used": self.used,
            "remaining": self.remaining,
            "by_kind": dict(sorted(self.by_kind.items())),
            "exhausted": self.exhausted,
            "stop_reason": self.stop_reason,
            "events": self.events[:50],
            "events_truncated": len(self.events) > 50,
            "note": ("unified gate: requests + response bytes + wall seconds shared by "
                     "pagination, retries, SE detail enrichment and probes"),
            "bytes": {"used": self.used_bytes, "limit": self.max_bytes,
                      "remaining": self.remaining_bytes,
                      "decoded": self.decoded_bytes},
            "seconds": {"used": round(self.used_seconds, 3), "limit": self.max_seconds,
                        "remaining": None if self.remaining_seconds is None
                        else round(self.remaining_seconds, 3)},
            "min_interval": self.min_interval,
            "failures": self.used_failures,
            "refused": self.refused,
            "ledger": str(self.ledger_path) if self.ledger_path else None,
            "log": str(self.log_path) if self.log_path else None,
            "log_reconciliation": rec,
        }


# 进程内只允许一个 `iss_budget` 上下文：交错/嵌套会让 monkey-patch 无法按 LIFO
# 还原，并把两个账本的预算串在一起。
_ACTIVE_GATES: dict[str, int] = {}
_ACTIVE_BUDGETS: set[int] = set()


@contextmanager
def iss_budget(budget: ProductionBudget, module: Any):
    """把 EN_API.item_shipment_status 的所有 GET 接到统一账本。

    `iss.paginated_get` / `get_single` / 各 fetch_* 都只经 `api_get_status` 发请求，
    因此单点替换即可覆盖分页与逐单详情，退出时恢复原函数。禁止重叠上下文。
    """
    key = getattr(module, "__name__", str(id(module)))
    budget_key = id(budget)
    if key in _ACTIVE_GATES or budget_key in _ACTIVE_BUDGETS:
        raise BudgetContextError(
            f"iss_budget 上下文重叠：module={key} budget={budget_key}；"
            "禁止嵌套/交错，避免账本串用与错误的函数还原")
    original = module.api_get_status

    def gated(path, base_url, key, secret, timeout=60):
        resp = budget.fetch("iss", path, base_url, key, secret, timeout=timeout)
        return resp.status, resp.body

    _ACTIVE_GATES[key] = budget_key
    _ACTIVE_BUDGETS.add(budget_key)
    module.api_get_status = gated
    try:
        yield budget
    finally:
        _ACTIVE_GATES.pop(key, None)
        _ACTIVE_BUDGETS.discard(budget_key)
        if module.api_get_status is not gated:
            raise BudgetContextError(
                f"iss_budget 退出时发现 {key}.api_get_status 已被他人改写；拒绝错误还原")
        module.api_get_status = original
