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
  * **禁用 requests 的隐式预读**：会话强制 `stream=True` 且关闭跳转预判
    （`Session.send` 在 `allow_redirects=False` 时仍会 `next(resolve_redirects(...))`
    预读跳转响应体）。因此**每一个响应体**（含 3xx/401/403/429）都只经
    `_read_body` 有界读取并记账，不存在“库读走、账本没有”的字节。
  * 禁止自动重定向（`allow_redirects=False`）；3xx 直接停，不逐跳绕过计数。
  * **可中断执行边界**：整个 HTTP 调用（建连 → 等响应头 → 读体）都在工作线程里，
    主线程只等到截止时刻；到点即放弃本次尝试、记 `deadline` 并持久停机，
    不会被对端的阻塞读无限期卡住。socket 超时同时绑定剩余墙钟。
    **主线程到点绝不调用 `close()`**（关连接可能同步阻塞，把 80ms 预算拖成数百 ms）；
    响应由被放弃的工作线程在自己的 `finally` 里关闭，线程本身是 daemon 且以
    socket 超时为收敛上界。若需要连网络活动都立即硬停，只能用可终止的进程边界。
  * **在途读取预占**：每次阻塞读**之前**按本次读取额度（≤`CHUNK`，且不越过字节
    预算）预占 wire 与解压后字节；正常返回即结算为实际字节，并释放多余预占。
    边界放弃（取消）后工作线程不再改账本，预占值作为**保守上界留在账本里**——
    已从 socket 读走但来不及结算的字节不会丢账（复审反例：实读 16 字节、账本 0）。
  * **绝对截止**：`deadline=`（epoch 秒 / datetime / `"22:30"`）与相对墙钟预算
    取**更早**者；越过绝对截止后任何请求都在发请求前拒绝。
  * 429 遵守 Retry-After、最多重试 2 次；401/403 立即停；连续 3 次网络错误/5xx 立即停。
  * **终止态原子落盘**：日志行（含 `stop_reason`，fsync）先写，随后**一次**账本写
    同时清 `pending` 并写 `stop_reason`/`exhausted`；崩溃在两者之间时，
    续跑从日志重建停机状态，不会续跑打生产。
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


class BudgetAccountingError(RuntimeError):
    """有字节绕过了有界读取器（隐式预读）：无法记账，立即停手。"""


class _Cancelled(Exception):
    """执行边界已放弃本次尝试（截止到点）：此后不得再改账本。"""


# ── 传输层：关掉 requests 的两条隐式预读路径 ──────────
class _GateSession(requests.Session):
    """响应体只能经 `_read_body` 消费，库不得自行读走任何字节。

    requests 2.x 有两条会绕过闸门的隐式读取：

    1. `Session.send` 里 `if not stream: r.content`——整包读进内存；
    2. `Session.send` 里 `if not allow_redirects: r._next = next(self
       .resolve_redirects(..., yield_requests=True))`——`resolve_redirects`
       循环开头就是 `resp.content`（注释写的是 “Consume socket so it can be
       released”），**即使禁止跳转也会把跳转响应体整包读走**，无长度上限。

    离线复现（`test_requests_by_itself_prereads_redirect_body`）：
    302 + 16 字节体 → 原生会话读走 16 字节，闸门记账 0。两条路径都会让
    字节预算与日志对账失真，因此在会话层直接关闭。
    """

    def send(self, request, **kwargs):
        kwargs["stream"] = True                 # 关掉 `r.content` 预读
        kwargs["allow_redirects"] = False       # 关掉跳转解析
        return super().send(request, **kwargs)

    def resolve_redirects(self, *args, **kwargs):
        # `Session.send` 的 `next(...)` 只会拿到 StopIteration，不碰响应体
        return iter(())


_SESSION_LOCK = threading.Lock()
_SESSION: _GateSession | None = None
_NETWORK_BLOCKED = False


def block_default_transport() -> None:
    """离线测试保险：默认传输一旦被调用立即失败，绝不发真实请求。

    单测若忘了注入 `http_get`（或补丁打在了旧入口上），就会静默走真实网络——
    这在本模块里等于未经授权的生产访问。测试模块导入时调用本函数即可封死。
    """
    global _NETWORK_BLOCKED
    _NETWORK_BLOCKED = True


def gate_session() -> _GateSession:
    """进程内复用一个已关闭隐式预读的会话（连接池保留）。"""
    global _SESSION
    with _SESSION_LOCK:
        if _SESSION is None:
            _SESSION = _GateSession()
        return _SESSION


def gated_get(url: str, headers: dict | None = None, timeout: Any = None,
              stream: bool = True, allow_redirects: bool = False) -> Any:
    """默认 HTTP 出口。`stream`/`allow_redirects` 只接受安全值，被强制覆盖。"""
    if _NETWORK_BLOCKED:
        raise AssertionError(
            f"默认传输被调用但离线测试已封网（应注入 http_get）: {url}")
    return gate_session().get(url, headers=headers, timeout=timeout,
                              stream=True, allow_redirects=False)


def coerce_deadline(value: Any) -> float | None:
    """绝对截止时刻 → epoch 秒。

    接受 epoch 秒（int/float）、`datetime`（naive 按本机时区）、
    `"HH:MM"` / `"HH:MM:SS"`（本机时区**今天**该时刻；已过即视为已到点）、
    ISO 8601 字符串。空值 → None（不启用绝对截止）。
    """
    if value is None or value == "":
        return None
    if isinstance(value, datetime):
        return float(value.timestamp())
    if isinstance(value, (int, float)) and not isinstance(value, bool):
        return float(value)
    text = str(value).strip()
    for fmt in ("%H:%M:%S", "%H:%M"):
        try:
            clock_time = datetime.strptime(text, fmt).time()
        except ValueError:
            continue
        return float(datetime.combine(datetime.now().date(), clock_time).timestamp())
    try:
        stamp = datetime.fromisoformat(text.replace("Z", "+00:00"))
    except ValueError as e:
        raise ValueError(f"无法解析绝对截止时刻: {value!r}") from e
    return float(stamp.timestamp())


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


class _Reservation:
    """一次在途阻塞读的额度预占。

    预占在真正 `read()` 之前完成；正常返回后结算为实际字节，取消时**保留**
    （工作线程不得再改账本，预占即保守上界，绝不把未结算字节清成 0）。
    """

    __slots__ = ("wire", "decoded")

    def __init__(self) -> None:
        self.wire = 0
        self.decoded = 0


class _Attempt:
    """一次 HTTP 尝试在可中断边界里的载体（工作线程写，主线程读）。"""

    def __init__(self) -> None:
        self.done = threading.Event()
        self.cancel = threading.Event()
        self.wire = 0                  # 已结算的传输字节
        self.decoded = 0               # 已结算的解压后字节
        self.reservation = _Reservation()  # 在途读预占（未结算）
        self.status: int | None = None
        self.headers: dict = {}
        self.body: _Body | None = None
        self.error: BaseException | None = None
        self.cancelled = False


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


def _iter_wire_chunks(resp: Any,
                      reserve_fn: Callable[[], int]) -> Iterator[tuple[int, bytes]]:
    """读未解压的传输字节；每次阻塞读**之前**调用 `reserve_fn()` 预占读取额度。

    `reserve_fn()` 返回本次允许读取的最大字节数（≤0 表示额度已尽，停止）。
    预占发生在真正 `read()` 之前，因此阻塞读期间被取消时，已从 socket 读走
    但来不及结算的字节仍按该额度留在账本里（保守上界，不会丢账）。

    每次交付 `(预占额度, 原始块)`；原始块可能大于额度（传输层无视 amt），
    由 `_read_body` 裁剪并保守判 `oversized`。
    """
    raw = getattr(resp, "raw", None)
    if raw is not None and hasattr(raw, "read"):
        while True:
            amt = reserve_fn()
            if amt <= 0:
                return
            try:
                chunk = raw.read(amt, decode_content=False)
            except TypeError:
                chunk = raw.read(amt)
            if not chunk:
                return
            yield amt, chunk
        return
    if raw is not None and hasattr(raw, "stream"):
        # 旧式替身 / 无 read 的传输层：无法在流中途缩小 amt，退化为固定块读取；
        # `_read_body` 仍会按预占额度裁剪并保守判超界。
        stream = raw.stream(CHUNK, decode_content=False)
        while True:
            amt = reserve_fn()
            if amt <= 0:
                return
            try:
                chunk = next(stream)
            except StopIteration:
                return
            if not chunk:
                return
            yield amt, chunk
        return
    # 没有 raw（如简单替身）：iter_content 已是解压后的字节，wire=decoded
    content = iter(resp.iter_content(CHUNK))
    while True:
        amt = reserve_fn()
        if amt <= 0:
            return
        try:
            chunk = next(content)
        except StopIteration:
            return
        if not chunk:
            continue
        yield amt, chunk


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
                 lock_path: str | os.PathLike | None = None,
                 deadline: Any = None):
        self.max_requests = None if max_requests is None else int(_nonneg(max_requests) or 0)
        self.max_bytes = None if max_bytes is None else int(_nonneg(max_bytes) or 0)
        self.max_seconds = _nonneg(max_seconds)
        self.deadline_epoch = coerce_deadline(deadline)
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
        # 账本写/读流记账互斥：HTTP 尝试在工作线程里记账，主线程到点只读快照
        self._io_lock = threading.RLock()

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
                       "deadline_epoch": self.deadline_epoch,
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
        with self._io_lock:               # 工作线程 checkpoint 与主线程写盘互斥
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

    def _scan_log(self) -> tuple[int, int, int, dict | None, str | None]:
        """返回 (行数, bytes 合计, 坏行数, 最后一行, 最后一行的 stop_reason)。"""
        if self.log_path is None or not self.log_path.exists():
            return 0, 0, 0, None, None
        requests_n = bytes_n = bad = 0
        last = None
        last_stop = None
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
                if r.get("stop_reason"):
                    last_stop = str(r["stop_reason"])
        return requests_n, bytes_n, bad, last, last_stop

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
        self._adopt_log_stop()

    def _adopt_log_stop(self) -> None:
        """从日志重建终止态：日志先落盘、账本后写，崩溃窗口内账本可能没有 stop。

        403/重定向/预算耗尽这些终止态一旦被记录到任意一行日志，续跑就不得放行。
        """
        if self.log_path is None:
            return
        _, _, bad, _, last_stop = self._scan_log()
        if bad or not last_stop or self.stop_reason is not None:
            return
        self.exhausted = True
        self.stop_reason = last_stop
        self._persist()

    def _recover_pending(self) -> None:
        """崩溃在 HTTP 途中：请求已持久预占，字节/耗时按保守上界补记。"""
        pending = self._pending or {}
        seq = int(pending.get("seq") or 0)
        log_n, log_bytes, bad, last, _ = self._scan_log()
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
        log_n, log_bytes, bad, _, _ = self._scan_log()
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
        """剩余墙钟 = min(相对累计预算, 绝对截止)，任一更早者先到。"""
        rel = None
        if self.max_seconds is not None:
            rel = self.max_seconds - self.used_seconds
        if self.deadline_epoch is not None:
            abs_left = self.deadline_epoch - self.wall_clock()
            rel = abs_left if rel is None else min(rel, abs_left)
        if rel is None:
            return None
        return max(0.0, rel)

    def _deadline_label(self) -> str:
        if self.deadline_epoch is None:
            return ""
        try:
            return datetime.fromtimestamp(self.deadline_epoch).isoformat(timespec="seconds")
        except (OverflowError, OSError, ValueError):
            return f"epoch={self.deadline_epoch}"

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
        if self.deadline_epoch is not None and self.wall_clock() >= self.deadline_epoch:
            self._refuse("seconds",
                         f"{kind}: absolute deadline {self._deadline_label()} passed")
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
              failed: bool = False, stop: str | None = None) -> None:
        """一次尝试落盘：日志行（含终止态）→ 账本（清 pending + 写 stop，单次原子替换）。

        终止态写在这一**次**账本写里，不再“先清 pending 再补 stop”：两次写之间的
        崩溃会让续跑看不到停机。日志行先 fsync，若随后崩溃，续跑按日志里的
        `stop_reason` 重建停机状态（`_adopt_log_stop`）。
        """
        if failed:
            self.used_failures += 1
        event = {"n": self._seq, "kind": kind, "detail": path[:120],
                 "status": status, "bytes": wire, "decoded_bytes": decoded,
                 "elapsed_ms": round(elapsed * 1000, 1), "attempt": attempt}
        if error:
            event["error"] = error[:200]
        if stop:
            event["stop_reason"] = stop
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
            if stop:
                line["stop_reason"] = stop
            self._append_log(line)
        self._pending = None
        if stop is not None and not self.exhausted:
            self.exhausted = True
            self.stop_reason = stop
        self._persist()

    def _failure_stop(self, attempt: int, detail: str) -> tuple[str, str] | None:
        """按连续失败/重试次数判定是否终止；返回 (reason, detail)。"""
        if self.consecutive_failures >= self.max_consecutive_failures:
            return ("consecutive_failures",
                    f"{detail}; max {self.max_consecutive_failures} consecutive")
        if attempt >= self.max_retries:
            return ("retry_exhausted", f"{detail}; {attempt} retries used")
        return None

    # ── 读流 ──────────────────────────────────────────
    def _reserve_read(self, call: "_Attempt | None", res: _Reservation,
                      expandable: bool) -> int:
        """阻塞读之前预占额度：wire 与解压后字节都先按本次读的上界记账。

        预占在真正 `read()` 之前完成（`_io_lock` 内），所以“已从 socket 读走、
        但取消后工作线程不再结算”的字节也有账可查。预占只存在于内存；崩溃
        恢复沿用 `_recover_pending` 的同一 CHUNK 上界，不会少记。
        """
        with self._io_lock:
            if call is not None and (call.cancelled or call.cancel.is_set()):
                raise _Cancelled()
            amt = self._wire_read_limit()
            if amt <= 0:
                return 0
            if self.max_bytes is None:
                dec = amt
            else:
                rem_dec = max(0, self.max_bytes - self.decoded_bytes)
                # 只有 gzip/deflate 会膨胀；其它编码按 1:1，最多 amt
                dec = rem_dec if expandable else min(rem_dec, amt)
            self.used_bytes += amt
            self.decoded_bytes += dec
            res.wire = amt
            res.decoded = dec
            return amt

    def _release_reservation(self, res: _Reservation) -> None:
        """释放未消费的预占（EOF / 结算前撤离解压预占）。调用方须持 `_io_lock`。"""
        self.used_bytes -= res.wire
        self.decoded_bytes -= res.decoded
        res.wire = 0
        res.decoded = 0

    def _read_body(self, resp: Any, headers: dict, started: float,
                   call: "_Attempt | None" = None) -> _Body:
        """有界读体：唯一消费响应体的路径（含 3xx/4xx）。

        `call` 非空时是执行边界内的尝试：每个阻塞读前后与每次记账前都检查
        取消标记。读取额度在**阻塞读之前**预占；一旦边界放弃本次尝试，工作
        线程不再改账本，预占额度（可能含已从 socket 读走但未结算的字节）
        作为保守上界保留，绝不清成 0。
        """
        body = _Body()
        decoder = _Decoder(str(headers.get("Content-Encoding") or ""))
        if self._pending is not None:
            with self._io_lock:
                if call is not None and call.cancel.is_set():
                    raise _Cancelled()
                self._pending["content_encoding"] = decoder.encoding
                self._persist()
        res = call.reservation if call is not None else _Reservation()
        chunks = _iter_wire_chunks(
            resp, lambda: self._reserve_read(call, res, decoder.compressed))

        def cancelled() -> bool:
            return call is not None and call.cancel.is_set()

        try:
            while True:
                if cancelled():
                    raise _Cancelled()
                # 截止优先于下一次 read：阻塞读开始前就拒绝继续
                if self._deadline_passed():
                    body.deadline = True
                    return body
                try:
                    amt, chunk = next(chunks)
                except StopIteration:
                    # EOF 是正常完成：本次空读的预占结算为 0 字节
                    with self._io_lock:
                        if call is not None and call.cancelled:
                            raise _Cancelled()
                        self._release_reservation(res)
                    break
                if cancelled():          # 阻塞读刚返回就可能已被放弃
                    raise _Cancelled()   # 预占留在账本：已读字节的保守上界
                with self._io_lock:
                    if call is not None and call.cancelled:
                        raise _Cancelled()
                    # 先撤掉解压预占，才能按剩余解压额度限制本次解压
                    self.decoded_bytes -= res.decoded
                    res.decoded = 0
                    over = len(chunk) > amt       # 传输层无视额度
                    take = min(len(chunk), amt)
                    self.used_bytes += take - res.wire   # 预占结算为实际字节
                    res.wire = 0
                    body.wire += take
                    if call is not None:
                        call.wire = body.wire
                    piece = chunk[:take]
                    try:
                        out = decoder.feed(piece, self._decoded_max_out())
                    except zlib.error:
                        # 压缩流被字节上限截断 / 编码损坏：按越界停止，不读完
                        self._checkpoint(body, started)
                        body.oversized = True
                        return body
                    remaining_decoded = self.remaining_decoded
                    if remaining_decoded is not None and len(out) > remaining_decoded:
                        out = out[:remaining_decoded]
                        over = True
                    self.decoded_bytes += len(out)
                    body.decoded += len(out)
                    body.data += out
                    if call is not None:
                        call.decoded = body.decoded
                    self._checkpoint(body, started)
                if over:
                    body.oversized = True
                    return body
            # 额度恰好用尽且流未结束：按超大响应处理（读之前已封顶，不会超额读）
            if (self.max_bytes is not None and self.used_bytes >= self.max_bytes
                    and not _stream_at_eof(resp, body.wire, headers)):
                body.oversized = True
        except (requests.RequestException, _Urllib3HTTPError, OSError) as e:
            # 读流超时/断连：已结算字节保留。本次阻塞读以异常结束、**没有交付
            # 任何块**，属于已结算而非“取消后未结算”，因此释放它的预占；
            # 否则一次瞬时超时就会吃掉剩余全部字节额度，重试也失去意义。
            with self._io_lock:
                if call is None or not call.cancelled:
                    self._release_reservation(res)
            body.error = e
        return body

    # ── 可中断执行边界 ────────────────────────────────
    def _run_attempt(self, url: str, headers: dict, timeout_bound: float,
                     started: float) -> "_Attempt":
        """把**整次** HTTP（建连 → 等响应头 → 读体）放进工作线程，主线程只等到截止。

        复审反例：watchdog 原在收到响应头后才启动，等头阶段的阻塞读无人可打断，
        也没有绝对截止。现在边界从**发请求之前**开始，覆盖整次调用：

          * 主线程最多等到 `remaining_seconds`（相对预算与绝对截止取更早者）；
          * 到点即：置取消标记 → 取**含在途预占**的字节快照 → 立刻返回；
          * **主线程绝不 `close()` 响应**：关闭可能同步阻塞（80ms 预算实测被拖到
            437ms）。关闭交给工作线程的 `finally`；被放弃的线程是 daemon，socket
            超时已绑定剩余墙钟，是有界收敛的；需要硬停网络活动只能用可终止进程边界；
          * 工作线程在每个阻塞调用前后与每次记账前查取消标记，放弃后不再改账本；
            在途读取的预占额度留在账本里（保守上界，绝不清除）。
        """
        call = _Attempt()

        def worker() -> None:
            resp = None
            try:
                get = self.http_get or gated_get
                resp = get(url, headers=headers, timeout=timeout_bound, stream=True,
                           allow_redirects=False)
                if call.cancel.is_set():
                    call.cancelled = True
                    return
                call.status = int(resp.status_code)
                call.headers = dict(getattr(resp, "headers", {}) or {})
                if getattr(resp, "_content_consumed", False):
                    # 兜底哨兵：字节已被别人整包读走，无法记账
                    raise BudgetAccountingError(
                        "响应体被隐式预读（requests 预读路径未被关闭），拒绝在无法"
                        "记账的情况下继续")
                # 所有状态码（含 3xx/401/403/429）都走同一有界读取器
                call.body = self._read_body(resp, call.headers, started, call)
            except _Cancelled:
                call.cancelled = True
            except BaseException as e:      # noqa: BLE001 - 交回主线程按类型分派
                call.error = e
            finally:
                close = getattr(resp, "close", None)
                if callable(close):
                    try:
                        close()
                    except Exception:       # noqa: BLE001 - 关连接失败不影响判定
                        pass
                call.done.set()

        thread = threading.Thread(target=worker, daemon=True,
                                  name="prod-budget-http")
        thread.start()
        wait_for = self.remaining_seconds
        if call.done.wait(None if wait_for is None else max(0.0, wait_for)):
            return call
        # 到点：先取消（工作线程不再记账），再在锁内取含预占的快照。
        # 不在这里 close()：关连接可能同步阻塞，会把截止返回路径拖长；响应由
        # 工作线程的 finally 关闭（daemon 线程 + socket 超时 = 有界收敛）。
        call.cancel.set()
        with self._io_lock:
            call.cancelled = True
            wire = call.wire + call.reservation.wire
            decoded = call.decoded + call.reservation.decoded
        call.wire, call.decoded = wire, decoded
        return call

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
            outcome = self._run_attempt(url, headers, timeout_bound, started)

            if outcome.cancelled:
                # 截止到点：整次 HTTP 被边界放弃（含等响应头阶段的阻塞读）
                self._note(kind, path, "deadline", wire=outcome.wire,
                           decoded=outcome.decoded, elapsed=self.clock() - started,
                           attempt=attempt,
                           error="wall_budget_exceeded_before_response",
                           failed=True, stop="seconds")
                raise BudgetExhausted(
                    "seconds", "wall-clock budget exceeded (execution boundary)",
                    used=self.used, limit=self.max_requests)

            if outcome.error is not None:
                err = outcome.error
                elapsed = self.clock() - started
                if isinstance(err, requests.Timeout):
                    self.consecutive_failures += 1
                    stop = self._failure_stop(
                        attempt, f"timeout ({self.consecutive_failures} consecutive)")
                    self._note(kind, path, "timeout", wire=0, decoded=0,
                               elapsed=elapsed, attempt=attempt,
                               error=f"Timeout: {err}", failed=True,
                               stop=stop[0] if stop else None)
                    if stop:
                        raise BudgetExhausted(stop[0], stop[1], used=self.used,
                                              limit=self.max_requests)
                    attempt += 1
                    continue
                if isinstance(err, requests.RequestException):
                    self.consecutive_failures += 1
                    stop = self._failure_stop(
                        attempt,
                        f"{type(err).__name__} ({self.consecutive_failures} consecutive)")
                    self._note(kind, path, "network_error", wire=0, decoded=0,
                               elapsed=elapsed, attempt=attempt,
                               error=f"{type(err).__name__}: {err}", failed=True,
                               stop=stop[0] if stop else None)
                    if stop:
                        raise BudgetExhausted(stop[0], stop[1], used=self.used,
                                              limit=self.max_requests)
                    attempt += 1
                    continue
                raise err                      # 其他异常原样抛出（不吞编程错误）

            status = int(outcome.status)
            resp_headers = outcome.headers
            body = outcome.body
            elapsed = self.clock() - started

            # 3xx / 401 / 403 是终止态：HTTP 语义优先于字节/耗时判定；
            # 响应体已经过有界读取并记账（不再有库预读的“黑洞字节”）。
            if 300 <= status < 400:
                loc = resp_headers.get("Location") or resp_headers.get("location") or ""
                self._note(kind, path, status, wire=body.wire, decoded=body.decoded,
                           elapsed=elapsed, attempt=attempt,
                           error="redirect_refused", failed=True, stop="redirect")
                raise BudgetExhausted(
                    "redirect",
                    f"HTTP {status} refused (allow_redirects=False) "
                    f"Location={str(loc)[:120]}",
                    used=self.used, limit=self.max_requests)
            if status in (401, 403):
                self._note(kind, path, status, wire=body.wire, decoded=body.decoded,
                           elapsed=elapsed, attempt=attempt,
                           error="auth_stop", failed=True, stop="auth")
                raise BudgetExhausted("auth", f"HTTP {status} on {path[:120]}",
                                      used=self.used, limit=self.max_requests)
            if body.deadline or self._deadline_passed():
                body.deadline = True
                self._note(kind, path, "deadline", wire=body.wire,
                           decoded=body.decoded, elapsed=elapsed,
                           attempt=attempt, error="wall_budget_exceeded",
                           failed=True, stop="seconds")
                raise BudgetExhausted("seconds", "wall-clock budget exceeded mid-response",
                                      used=self.used, limit=self.max_requests)
            if body.oversized:
                self._note(kind, path, "oversized", wire=body.wire,
                           decoded=body.decoded, elapsed=elapsed,
                           attempt=attempt, error="byte_budget_exceeded",
                           failed=True, stop="bytes")
                raise BudgetExhausted("bytes", "response exceeded byte budget",
                                      used=self.used, limit=self.max_requests)
            if status == 429:
                retry_after = parse_retry_after(resp_headers.get("Retry-After"))
                wait = 1.0 if retry_after is None else retry_after
                rem = self.remaining_seconds
                stop: tuple[str, str] | None = None
                if attempt >= self.max_retries:
                    stop = ("retry_exhausted", f"429 after {attempt} retries")
                elif rem is not None and wait >= rem:
                    stop = ("seconds",
                            f"Retry-After {wait:.1f}s exceeds remaining {rem:.1f}s")
                self._note(kind, path, status, wire=body.wire, decoded=body.decoded,
                           elapsed=elapsed, attempt=attempt, error="rate_limited",
                           failed=True, stop=stop[0] if stop else None)
                if stop:
                    raise BudgetExhausted(stop[0], stop[1], used=self.used,
                                          limit=self.max_requests)
                if wait > 0:
                    self.sleep(wait)
                attempt += 1
                continue
            if body.error is not None:
                self.consecutive_failures += 1
                stop = self._failure_stop(
                    attempt, f"read error ({self.consecutive_failures} consecutive)")
                self._note(kind, path, "read_error", wire=body.wire,
                           decoded=body.decoded, elapsed=elapsed, attempt=attempt,
                           error=f"{type(body.error).__name__}: {body.error}",
                           failed=True, stop=stop[0] if stop else None)
                if stop:
                    raise BudgetExhausted(stop[0], stop[1], used=self.used,
                                          limit=self.max_requests)
                attempt += 1
                continue
            if status >= 500:
                self.consecutive_failures += 1
                stop = self._failure_stop(
                    attempt, f"HTTP {status} ({self.consecutive_failures} consecutive)")
                self._note(kind, path, status, wire=body.wire, decoded=body.decoded,
                           elapsed=elapsed, attempt=attempt, failed=True,
                           stop=stop[0] if stop else None)
                if stop:
                    raise BudgetExhausted(stop[0], stop[1], used=self.used,
                                          limit=self.max_requests)
                attempt += 1
                continue

            self.consecutive_failures = 0
            self._note(kind, path, status, wire=body.wire, decoded=body.decoded,
                       elapsed=elapsed, attempt=attempt, failed=False)
            try:
                parsed = json.loads(body.data) if body.data else {}
            except ValueError:
                parsed = {}
            if not isinstance(parsed, dict):
                parsed = {}
            return BudgetResponse(status=status, body=parsed, bytes=body.wire,
                                  decoded_bytes=body.decoded, attempts=attempt + 1,
                                  headers=resp_headers)

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
                        else round(self.remaining_seconds, 3),
                        "absolute_deadline": self._deadline_label() or None},
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
