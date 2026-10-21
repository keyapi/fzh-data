#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""生产只读统一预算闸门（requests / 响应字节 / 墙钟秒）。

契约（决策 Codex 2026-10-21 先决条件，见
`control/reviews/2026-10-21-gate-task.md`）：

  * 三类预算任一先到即停；**发请求前**拒绝，拒绝不产生 HTTP 调用。
  * 账本是 JSON：跨进程 / 崩溃续跑累计 requests、bytes、seconds，启动读取、
    每次请求后原子写回，续跑不重置。
  * 串行 GET，默认最小间隔 ≥1 秒；`stream=True` 分块读，超出剩余字节立即停，
    同时按 Content-Encoding 限制解压后字节。
  * 超时计入请求数与失败；429 遵守 Retry-After、最多重试 2 次；
    401/403 立即停；连续 3 次网络错误/5xx 立即停。
  * `prod_budget.log` 每请求一行；账本与日志的请求数/字节必须一致（启动时核对）。

不传预算参数时调用方保持旧语义；只有显式启用闸门才创建账本与日志。
"""

from __future__ import annotations

import email.utils
import json
import os
import time
import zlib
from collections import Counter
from contextlib import contextmanager
from dataclasses import dataclass, field
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Callable, Iterator

import requests

SCHEMA = "prod_budget/1"
LOG_SCHEMA = "prod_budget_log/1"
CHUNK = 64 * 1024
STOP_REASONS = ("requests", "bytes", "seconds", "auth", "consecutive_failures",
                "retry_exhausted")


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
    """账本不可读 / schema 不符 / 与日志对账不一致。禁止静默重置。"""


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
        self.known = True
        self._zlib: Any = None
        if enc in ("gzip", "x-gzip"):
            self._zlib = zlib.decompressobj(16 + zlib.MAX_WBITS)
        elif enc == "deflate":
            self._zlib = zlib.decompressobj()
            self._deflate_raw = False
        elif enc in ("", "identity"):
            self._zlib = None
        else:
            # br / zstd 等未内置解码器：按传输字节计，显式标记 unknown
            self.known = False
            self._zlib = None

    def feed(self, chunk: bytes) -> bytes:
        if self._zlib is None:
            return chunk
        try:
            return self._zlib.decompress(chunk)
        except zlib.error:
            if getattr(self, "_deflate_raw", False):
                raise
            # 服务器发的是 raw deflate（无 zlib 头）
            self._deflate_raw = True
            self._zlib = zlib.decompressobj(-zlib.MAX_WBITS)
            return self._zlib.decompress(chunk)


def _iter_wire_chunks(resp: Any) -> Iterator[bytes]:
    """优先读未解压的传输字节；测试替身只需提供 raw.stream 或 raw.read。"""
    raw = getattr(resp, "raw", None)
    if raw is not None and hasattr(raw, "stream"):
        yield from raw.stream(CHUNK, decode_content=False)
        return
    if raw is not None and hasattr(raw, "read"):
        while True:
            try:
                chunk = raw.read(CHUNK, decode_content=False)
            except TypeError:
                chunk = raw.read(CHUNK)
            if not chunk:
                return
            yield chunk
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
                 sleep: Callable[[float], None] | None = None,
                 http_get: Callable[..., Any] | None = None):
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
        self.clock = clock or time.monotonic
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
        self._base_seconds = 0.0
        self._run_start = self.clock()
        self._started_at = _iso_now()
        self._runs: list[dict] = []
        self._closed = False
        self._log_handle = None

        self._load()
        self._reconcile_or_raise()
        if self.log_path is not None:
            self.log_path.parent.mkdir(parents=True, exist_ok=True)
            self._log_handle = open(self.log_path, "a", encoding="utf-8", newline="\n")

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
        # 上一次进程的停止原因只作历史；本进程从累计计数器继续（不重置）
        self.previous_stop_reason = data.get("stop_reason")
        self.stop_reason = None
        self.exhausted = False

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
        with open(self.log_path, encoding="utf-8") as f:
            for line in f:
                line = line.strip()
                if not line:
                    continue
                try:
                    r = json.loads(line)
                except ValueError:
                    rec["bad_lines"] += 1
                    continue
                rec["log_requests"] += 1
                rec["log_bytes"] += int(r.get("bytes") or 0)
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
    def remaining_seconds(self) -> float | None:
        if self.max_seconds is None:
            return None
        return max(0.0, self.max_seconds - self.used_seconds)

    # 旧字段名（HttpBudget）
    @property
    def limit(self) -> int | None:
        return self.max_requests

    def _stop(self, reason: str, detail: str = "") -> None:
        self.exhausted = True
        self.stop_reason = reason
        self._persist()

    def _refuse(self, reason: str, detail: str) -> None:
        """预检拒绝：不占用请求数、不产生 HTTP、不写请求日志。"""
        self.refused += 1
        self._stop(reason, detail)
        raise BudgetExhausted(reason, detail, used=self.used, limit=self.max_requests)

    def _preflight(self, kind: str) -> None:
        if self.max_requests is not None and self.used >= self.max_requests:
            self._refuse("requests", f"{kind}: request budget {self.max_requests} used up")
        if self.max_bytes is not None and self.used_bytes >= self.max_bytes:
            self._refuse("bytes", f"{kind}: byte budget {self.max_bytes} used up")
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
            self._log_handle.write(json.dumps(line, ensure_ascii=False) + "\n")
            self._log_handle.flush()
            try:
                os.fsync(self._log_handle.fileno())
            except OSError:
                pass
        self._persist()

    # ── 读流 ──────────────────────────────────────────
    def _read_body(self, resp: Any, headers: dict) -> _Body:
        body = _Body()
        decoder = _Decoder(str(headers.get("Content-Encoding") or ""))
        try:
            for chunk in _iter_wire_chunks(resp):
                if not chunk:
                    continue
                take = len(chunk)
                if self.max_bytes is not None:
                    take = min(take, max(0, self.max_bytes - self.used_bytes))
                self.used_bytes += take
                body.wire += take
                piece = chunk[:take]
                try:
                    out = decoder.feed(piece)
                except zlib.error:
                    # 压缩流被字节上限截断 / 编码损坏：按越界停止，不读完
                    body.oversized = True
                    return body
                d_take = len(out)
                if self.max_bytes is not None:
                    d_take = min(d_take, max(0, self.max_bytes - self.decoded_bytes))
                self.decoded_bytes += d_take
                body.decoded += d_take
                body.data += out[:d_take]
                if take < len(chunk) or d_take < len(out):
                    body.oversized = True
                    return body
                if (self.max_seconds is not None
                        and self.used_seconds >= self.max_seconds):
                    body.deadline = True
                    return body
        except requests.RequestException as e:  # 读流超时/断连：已计字节保留
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
            self.reserve(kind if attempt == 0 else "retry", path)
            self._last_request_at = self.clock()

            started = self.clock()
            try:
                get = self.http_get or requests.get
                resp = get(url, headers=headers, timeout=timeout, stream=True)
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

                body = self._read_body(resp, resp_headers)
                elapsed = self.clock() - started
                if body.oversized:
                    self._note(kind, path, "oversized", wire=body.wire,
                               decoded=body.decoded, elapsed=elapsed,
                               attempt=attempt, error="byte_budget_exceeded", failed=True)
                    self._stop("bytes", f"response exceeded remaining byte budget")
                    raise BudgetExhausted("bytes", "response exceeded byte budget",
                                          used=self.used, limit=self.max_requests)
                if body.deadline:
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
        if self._log_handle is not None:
            self._log_handle.flush()
            self._log_handle.close()
            self._log_handle = None

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


@contextmanager
def iss_budget(budget: ProductionBudget, module: Any):
    """把 EN_API.item_shipment_status 的所有 GET 接到统一账本。

    `iss.paginated_get` / `get_single` / 各 fetch_* 都只经 `api_get_status` 发请求，
    因此单点替换即可覆盖分页与逐单详情，退出时恢复原函数。
    """
    original = module.api_get_status

    def gated(path, base_url, key, secret, timeout=60):
        resp = budget.fetch("iss", path, base_url, key, secret, timeout=timeout)
        return resp.status, resp.body

    module.api_get_status = gated
    try:
        yield budget
    finally:
        module.api_get_status = original
