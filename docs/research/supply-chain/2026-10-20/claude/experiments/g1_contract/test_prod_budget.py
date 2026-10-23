#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""生产只读统一预算闸门离线单测（全部 mock，不访问生产）。

覆盖任务书 2026-10-21-gate-task.md 的验收项，以及 2026-10-21 两轮复审 FAIL 的
全部反例：

  零预算 / 精确边界（请求、字节）/ 按剩余额度读取（不是先读后裁）/
  解压后字节硬限 / 重定向不跟随 / 墙钟绑定剩余时间与空响应越时 /
  403 后 fetch 不再发请求 / 停止状态跨进程持久 / 崩溃途中保守恢复 /
  独占运行锁 / 最小间隔跨进程 / 重叠上下文禁止 / 离线输出与父版本逐字节一致。

第二轮复审（`control/reviews/2026-10-21-gate-review2-fail.md`）三个反例各有专属类：

  * `ImplicitPreReadTests`——requests 在禁止跳转时仍整包预读跳转响应体
    （离线复现：读走 16 字节、闸门记账 0）；会话层关闭预读，且**每一个**
    响应体都经有界读取器记账。
  * `ExecutionBoundaryTests`——watchdog 原在收到响应头后才启动；改为覆盖整次
    HTTP 的可中断执行边界 + 绝对截止（含等头阶段与阻塞读体）。
  * `AtomicStopTests`——403 终止态与清 pending 一次原子落盘；崩溃在两写之间时
    从日志重建停机状态，续跑不会放行。

第三轮复审（`control/reviews/2026-10-22-gate-review3.md`）两个阻断反例：

  * 取消后丢弃已读块（实读 16 字节、账本 0）：阻塞读**之前**预占读取额度，
    取消后工作线程不再结算、预占作为保守上界保留（绝不清除未结算字节）；
    正常完成 / EOF / 读流异常分别结算为实际字节 / 0 / 保留预占
    （读流异常可能是“socket 已读走部分字节后再抛超时”，无法证明未消耗）。
  * 截止返回路径同步 `close()`（80ms 预算实测 437ms）：主线程到点不再关闭
    响应，交给工作线程的 `finally`；回归用例用会阻塞 1 秒的 close 证明主线程
    立即返回且不是它调用 close。
"""

from __future__ import annotations

import gzip
import importlib.util
import json
import subprocess
import sys
import tempfile
import threading
import time
import unittest
from datetime import datetime, timedelta, timezone
from pathlib import Path
from unittest import mock

BASE = Path(__file__).resolve().parent
if str(BASE) not in sys.path:
    sys.path.insert(0, str(BASE))

import prod_budget as pb  # noqa: E402
import g1b_dn_wo_jc_se as dn  # noqa: E402
import g1b_en_extract as ex  # noqa: E402
import EN_API.item_shipment_status as iss  # noqa: E402

# 离线保险：任何一条测试若漏注入 http_get 就立刻失败，不得真实访问生产
pb.block_default_transport()

PARENT_COMMIT = "be37645b^"
DN_RELPATH = ("docs/research/supply-chain/2026-10-20/claude/experiments/"
              "g1_contract/g1b_dn_wo_jc_se.py")
EX_RELPATH = ("docs/research/supply-chain/2026-10-20/claude/experiments/"
              "g1_contract/g1b_en_extract.py")


# ── 测试替身 ──────────────────────────────────────────
class FakeRaw:
    """按 `read(amt)` 每次交付一个源块（最多 amt 字节），模拟 urllib3 流式读取。"""

    def __init__(self, chunks, tick=None):
        self.chunks = list(chunks)
        self.tick = tick
        self.chunks_yielded = 0
        self.bytes_yielded = 0
        self.reads: list[int] = []
        self.eof = not self.chunks
        self.closed = False

    def read(self, amt, decode_content=False):
        if self.tick:
            self.tick()
        if not self.chunks:
            self.eof = True
            return b""
        item = self.chunks[0]
        if isinstance(item, BaseException):
            self.chunks.pop(0)
            raise item
        self.reads.append(amt)
        take = item[:amt]
        if len(take) < len(item):
            self.chunks[0] = item[amt:]
        else:
            self.chunks.pop(0)
        self.chunks_yielded += 1
        self.bytes_yielded += len(take)
        if not self.chunks:
            self.eof = True
        return take

    def stream(self, amt, decode_content=False):
        while True:
            chunk = self.read(amt, decode_content=decode_content)
            if not chunk:
                return
            yield chunk

    def isclosed(self):
        return self.eof and not self.chunks

    def close(self):
        self.closed = True


class FakeResponse:
    def __init__(self, status=200, chunks=(b'{"data": []}',), headers=None, tick=None):
        self.status_code = status
        self.headers = headers or {}
        self.raw = FakeRaw(chunks, tick=tick)
        self.closed = False

    def close(self):
        self.closed = True


class FakeHTTP:
    """按顺序返回响应；元素为 Exception 时抛出。用尽即断言（零额外请求）。"""

    def __init__(self, responses, clock=None, call_tick=0.0):
        self.responses = list(responses)
        self.served: list[FakeResponse] = []
        self.calls: list[str] = []
        self.starts: list[float] = []
        self.timeouts: list[float] = []
        self.allow_redirects: list[bool] = []
        self.clock = clock
        self.call_tick = call_tick

    def __call__(self, url, headers=None, timeout=None, stream=False,
                 allow_redirects=None):
        self.calls.append(url)
        self.timeouts.append(timeout)
        self.allow_redirects.append(allow_redirects)
        if self.clock is not None:
            self.starts.append(self.clock())
            if self.call_tick:
                self.clock.t += self.call_tick
        if not self.responses:
            raise AssertionError(f"unexpected extra HTTP call: {url}")
        item = self.responses.pop(0)
        if isinstance(item, Exception):
            raise item
        self.served.append(item)
        return item


class FakeClock:
    def __init__(self):
        self.t = 0.0
        self.sleeps: list[float] = []

    def __call__(self):
        return self.t

    def sleep(self, s):
        self.sleeps.append(s)
        self.t += s


def make(tmp: str, http, *, clock=None, wall=None, **kw) -> pb.ProductionBudget:
    d = Path(tmp)
    return pb.ProductionBudget(
        ledger_path=d / "prod_budget.json", log_path=d / "prod_budget.log",
        http_get=http, clock=clock, wall_clock=wall if wall is not None else clock,
        sleep=clock.sleep if clock else None, **kw)


def crash(b: pb.ProductionBudget) -> None:
    """模拟进程死亡：OS 释放锁与日志句柄，但不写收尾账本。"""
    if b._log_handle is not None:
        b._log_handle.flush()
        b._log_handle.close()
        b._log_handle = None
    if b._lock is not None:
        b._lock.release()
        b._lock = None
    b._closed = True


def ledger(tmp: str) -> dict:
    return json.loads((Path(tmp) / "prod_budget.json").read_text(encoding="utf-8"))


def log_lines(tmp: str) -> list[dict]:
    p = Path(tmp) / "prod_budget.log"
    if not p.exists():
        return []
    return [json.loads(x) for x in p.read_text(encoding="utf-8").splitlines() if x.strip()]


def fetch(b: pb.ProductionBudget):
    return b.fetch("iss", "/api/resource/Sales%20Order", "http://en", "k", "s")


class BudgetExhaustedAssertions(unittest.TestCase):
    def assertStopped(self, ctx, reason):
        self.assertIsInstance(ctx.exception, pb.BudgetExhausted)
        self.assertEqual(ctx.exception.reason, reason)


# ── 零预算 / 精确边界 ─────────────────────────────────
class ZeroAndBoundaryTests(BudgetExhaustedAssertions):
    def test_zero_request_budget_refuses_before_http(self):
        http = FakeHTTP([])
        with tempfile.TemporaryDirectory(ignore_cleanup_errors=True) as d:
            b = make(d, http, max_requests=0)
            with self.assertRaises(pb.BudgetExhausted) as ctx:
                fetch(b)
            self.assertStopped(ctx, "requests")
            self.assertEqual(http.calls, [])
            self.assertEqual(b.used, 0)
            self.assertEqual(b.refused, 1)
            b.close()
            led = ledger(d)
            self.assertEqual(led["used"]["requests"], 0)
            self.assertEqual(led["refused"], 1)
            self.assertEqual(log_lines(d), [])
            self.assertTrue(b.reconcile()["ok"])

    def test_zero_byte_budget_refuses_before_http(self):
        http = FakeHTTP([])
        with tempfile.TemporaryDirectory(ignore_cleanup_errors=True) as d:
            b = make(d, http, max_bytes=0)
            with self.assertRaises(pb.BudgetExhausted) as ctx:
                fetch(b)
            self.assertStopped(ctx, "bytes")
            self.assertEqual(http.calls, [])
            b.close()

    def test_zero_second_budget_refuses_before_http(self):
        http = FakeHTTP([])
        with tempfile.TemporaryDirectory(ignore_cleanup_errors=True) as d:
            b = make(d, http, max_seconds=0)
            with self.assertRaises(pb.BudgetExhausted) as ctx:
                fetch(b)
            self.assertStopped(ctx, "seconds")
            self.assertEqual(http.calls, [])
            b.close()

    def test_exact_request_boundary(self):
        http = FakeHTTP([FakeResponse(chunks=[b'{"data": [1]}'])])
        with tempfile.TemporaryDirectory(ignore_cleanup_errors=True) as d:
            b = make(d, http, max_requests=1)
            r = fetch(b)
            self.assertEqual(r.status, 200)
            self.assertEqual(r.body, {"data": [1]})
            with self.assertRaises(pb.BudgetExhausted) as ctx:
                fetch(b)
            self.assertStopped(ctx, "requests")
            self.assertEqual(len(http.calls), 1)          # 第二次没有 HTTP
            b.close()
            self.assertEqual(ledger(d)["used"]["requests"], 1)
            self.assertEqual(len(log_lines(d)), 1)
            self.assertTrue(b.reconcile()["ok"])

    def test_exact_byte_boundary(self):
        body = b'{"data": [1]}'
        http = FakeHTTP([FakeResponse(chunks=[body])])
        with tempfile.TemporaryDirectory(ignore_cleanup_errors=True) as d:
            b = make(d, http, max_bytes=len(body))
            fetch(b)
            self.assertEqual(b.used_bytes, len(body))
            with self.assertRaises(pb.BudgetExhausted) as ctx:
                fetch(b)
            self.assertStopped(ctx, "bytes")
            self.assertEqual(len(http.calls), 1)
            b.close()
            self.assertEqual(ledger(d)["used"]["bytes"], len(body))

    def test_read_amount_never_exceeds_remaining(self):
        """复审反例：曾经实读 16、只记 10；现在读之前就按剩余额度封顶。"""
        chunks = [b"12345678", b"ABCDEFGH", b"ZZZZZZZZ"]
        http = FakeHTTP([FakeResponse(chunks=chunks)])
        with tempfile.TemporaryDirectory(ignore_cleanup_errors=True) as d:
            b = make(d, http, max_bytes=10)
            with self.assertRaises(pb.BudgetExhausted) as ctx:
                fetch(b)
            self.assertStopped(ctx, "bytes")
            raw = http.served[0].raw
            self.assertEqual(raw.reads, [10, 2])          # 第二次只请求剩余 2 字节
            self.assertEqual(raw.bytes_yielded, 10)       # 不再实读 16
            self.assertEqual(raw.chunks_yielded, 2)
            self.assertEqual(b.used_bytes, 10)            # 不越界
            b.close()
            lines = log_lines(d)
            self.assertEqual(len(lines), 1)
            self.assertEqual(lines[0]["status"], "oversized")
            self.assertEqual(lines[0]["bytes"], 10)
            self.assertEqual(ledger(d)["used"]["bytes"], 10)
            self.assertTrue(b.reconcile()["ok"])

    def test_decompressed_bytes_are_capped(self):
        plain = b"\0" * 100000
        wire = gzip.compress(plain)
        http = FakeHTTP([FakeResponse(chunks=[wire], headers={"Content-Encoding": "gzip"})])
        with tempfile.TemporaryDirectory(ignore_cleanup_errors=True) as d:
            b = make(d, http, max_bytes=1000)
            with self.assertRaises(pb.BudgetExhausted) as ctx:
                fetch(b)
            self.assertStopped(ctx, "bytes")
            self.assertLessEqual(b.used_bytes, 1000)
            self.assertEqual(b.decoded_bytes, 1000)
            b.close()

    def test_decoded_budget_reached_refuses_next_request(self):
        plain = b"\0" * 1000
        wire = gzip.compress(plain)
        http = FakeHTTP([FakeResponse(chunks=[wire], headers={"Content-Encoding": "gzip"})])
        with tempfile.TemporaryDirectory(ignore_cleanup_errors=True) as d:
            b = make(d, http, max_bytes=1000)
            r = fetch(b)                              # 传输字节远小于上限，解压恰好用满
            self.assertEqual(r.status, 200)
            self.assertEqual(b.decoded_bytes, 1000)
            with self.assertRaises(pb.BudgetExhausted) as ctx:
                fetch(b)
            self.assertStopped(ctx, "bytes")          # 解压额度已满：下一次请求前拒绝
            self.assertEqual(len(http.calls), 1)
            b.close()

    def test_gzip_body_is_decoded_and_counted(self):
        plain = b'{"data": [1, 2]}'
        wire = gzip.compress(plain)
        http = FakeHTTP([FakeResponse(chunks=[wire], headers={"Content-Encoding": "gzip"})])
        with tempfile.TemporaryDirectory(ignore_cleanup_errors=True) as d:
            b = make(d, http)
            r = fetch(b)
            self.assertEqual(r.body, {"data": [1, 2]})
            self.assertEqual(b.used_bytes, len(wire))
            self.assertEqual(b.decoded_bytes, len(plain))
            b.close()


# ── 超时 / 重定向 / 429 / 401 ────────────────────────
class StopConditionTests(BudgetExhaustedAssertions):
    def test_timeout_counts_as_request_and_stops_after_three(self):
        http = FakeHTTP([pb.requests.Timeout("t")] * 10)
        with tempfile.TemporaryDirectory(ignore_cleanup_errors=True) as d:
            b = make(d, http, max_requests=10)
            with self.assertRaises(pb.BudgetExhausted) as ctx:
                fetch(b)
            self.assertStopped(ctx, "consecutive_failures")
            self.assertEqual(len(http.calls), 3)
            self.assertEqual(b.used, 3)
            self.assertEqual(b.used_failures, 3)
            b.close()
            lines = log_lines(d)
            self.assertEqual([x["status"] for x in lines], ["timeout"] * 3)
            self.assertEqual(ledger(d)["used"]["requests"], 3)
            self.assertEqual(ledger(d)["used"]["failures"], 3)
            self.assertTrue(b.reconcile()["ok"])

    def test_429_honors_retry_after_then_succeeds(self):
        clk = FakeClock()
        http = FakeHTTP([FakeResponse(status=429, chunks=[], headers={"Retry-After": "2"}),
                         FakeResponse(chunks=[b'{"data": []}'])], clock=clk)
        with tempfile.TemporaryDirectory(ignore_cleanup_errors=True) as d:
            b = make(d, http, clock=clk)
            r = fetch(b)
            self.assertEqual(r.status, 200)
            self.assertEqual(r.attempts, 2)
            self.assertEqual(clk.sleeps, [2.0])
            self.assertEqual(b.used, 2)
            self.assertEqual(b.by_kind["retry"], 1)
            b.close()
            self.assertEqual([x["status"] for x in log_lines(d)], [429, 200])
            self.assertTrue(b.reconcile()["ok"])

    def test_429_stops_after_two_retries(self):
        clk = FakeClock()
        http = FakeHTTP([FakeResponse(status=429, chunks=[], headers={"Retry-After": "1"})
                         for _ in range(5)], clock=clk)
        with tempfile.TemporaryDirectory(ignore_cleanup_errors=True) as d:
            b = make(d, http, clock=clk)
            with self.assertRaises(pb.BudgetExhausted) as ctx:
                fetch(b)
            self.assertStopped(ctx, "retry_exhausted")
            self.assertEqual(len(http.calls), 3)          # 首次 + 2 次重试
            self.assertEqual(clk.sleeps, [1.0, 1.0])
            b.close()
            self.assertEqual(len(log_lines(d)), 3)
            self.assertEqual(ledger(d)["stop_reason"], "retry_exhausted")

    def test_403_stops_immediately(self):
        http = FakeHTTP([FakeResponse(status=403, chunks=[])])
        with tempfile.TemporaryDirectory(ignore_cleanup_errors=True) as d:
            b = make(d, http)
            with self.assertRaises(pb.BudgetExhausted) as ctx:
                fetch(b)
            self.assertStopped(ctx, "auth")
            self.assertEqual(len(http.calls), 1)
            b.close()
            self.assertEqual(ledger(d)["stop_reason"], "auth")

    def test_403_then_fetch_never_sends(self):
        """复审反例：403 后再次 fetch 仍然发请求。"""
        http = FakeHTTP([FakeResponse(status=403, chunks=[])])
        with tempfile.TemporaryDirectory(ignore_cleanup_errors=True) as d:
            b = make(d, http)
            with self.assertRaises(pb.BudgetExhausted) as ctx:
                fetch(b)
            self.assertStopped(ctx, "auth")
            with self.assertRaises(pb.BudgetExhausted) as ctx2:
                fetch(b)
            self.assertStopped(ctx2, "auth")
            self.assertEqual(len(http.calls), 1)          # 第二次没有 HTTP
            b.close()

    def test_stop_is_persistent_across_processes(self):
        http = FakeHTTP([FakeResponse(status=403, chunks=[])])
        with tempfile.TemporaryDirectory(ignore_cleanup_errors=True) as d:
            b1 = make(d, http)
            with self.assertRaises(pb.BudgetExhausted):
                fetch(b1)
            b1.close()
            b2 = make(d, http)                            # 新进程：停止状态不得清除
            self.assertTrue(b2.exhausted)
            self.assertEqual(b2.stop_reason, "auth")
            with self.assertRaises(pb.BudgetExhausted) as ctx:
                fetch(b2)
            self.assertStopped(ctx, "auth")
            self.assertEqual(len(http.calls), 1)
            b2.close()

    def test_5xx_stops_after_three(self):
        http = FakeHTTP([FakeResponse(status=500, chunks=[b"err"]) for _ in range(5)])
        with tempfile.TemporaryDirectory(ignore_cleanup_errors=True) as d:
            b = make(d, http)
            with self.assertRaises(pb.BudgetExhausted) as ctx:
                fetch(b)
            self.assertStopped(ctx, "consecutive_failures")
            self.assertEqual(len(http.calls), 3)
            b.close()


# ── 重定向 / 墙钟 ────────────────────────────────────
class RedirectAndDeadlineTests(BudgetExhaustedAssertions):
    def test_redirect_is_refused_not_followed(self):
        """复审反例：requests 默认自动跟随重定向，跳转绕过计数/字节/间隔。"""
        http = FakeHTTP([FakeResponse(status=302, chunks=[],
                                      headers={"Location": "http://elsewhere/"})])
        with tempfile.TemporaryDirectory(ignore_cleanup_errors=True) as d:
            b = make(d, http)
            with self.assertRaises(pb.BudgetExhausted) as ctx:
                fetch(b)
            self.assertStopped(ctx, "redirect")
            self.assertEqual(len(http.calls), 1)
            self.assertEqual(http.allow_redirects, [False])
            with self.assertRaises(pb.BudgetExhausted) as ctx2:
                fetch(b)
            self.assertStopped(ctx2, "redirect")
            self.assertEqual(len(http.calls), 1)
            b.close()
            self.assertEqual(ledger(d)["stop_reason"], "redirect")

    def test_timeout_is_bounded_by_remaining_wall_clock(self):
        clk = FakeClock()
        http = FakeHTTP([FakeResponse(chunks=[b'{"data": []}'])], clock=clk)
        with tempfile.TemporaryDirectory(ignore_cleanup_errors=True) as d:
            b = make(d, http, clock=clk, max_seconds=10.0)
            clk.t = 3.0                                   # 已用 3 秒，剩 7 秒
            fetch(b)
            self.assertLessEqual(http.timeouts[0], 7.0)
            self.assertGreater(http.timeouts[0], 0)
            b.close()

    def test_empty_response_past_deadline_does_not_succeed(self):
        """复审反例：空响应在截止后仍返回成功。"""
        clk = FakeClock()
        http = FakeHTTP([FakeResponse(chunks=[])], clock=clk, call_tick=2.0)
        with tempfile.TemporaryDirectory(ignore_cleanup_errors=True) as d:
            b = make(d, http, clock=clk, max_seconds=1.0)
            with self.assertRaises(pb.BudgetExhausted) as ctx:
                fetch(b)
            self.assertStopped(ctx, "seconds")
            self.assertEqual(log_lines(d)[0]["status"], "deadline")
            b.close()

    def test_wall_budget_stops_mid_response(self):
        clk = FakeClock()

        def tick():
            clk.t += 0.6

        http = FakeHTTP([FakeResponse(chunks=[b"chunk1", b"chunk2", b"chunk3"],
                                      tick=tick)], clock=clk)
        with tempfile.TemporaryDirectory(ignore_cleanup_errors=True) as d:
            b = make(d, http, clock=clk, max_seconds=1.0)
            with self.assertRaises(pb.BudgetExhausted) as ctx:
                fetch(b)
            self.assertStopped(ctx, "seconds")
            self.assertEqual(http.served[0].raw.chunks_yielded, 2)
            self.assertEqual(log_lines(d)[0]["status"], "deadline")
            b.close()


# ── 第二轮复审 ①②：隐式预读 / 整次 HTTP 有界 ─────────
class _FakeAdapter(pb.requests.adapters.BaseAdapter):
    """真实 requests 会话的传输替身：原样返回预置响应并记录调用参数。"""

    def __init__(self, resp):
        self.resp = resp
        self.seen: dict = {}

    def send(self, request, stream=False, timeout=None, verify=True, cert=None,
             proxies=None):
        self.seen = {"stream": stream, "timeout": timeout}
        return self.resp

    def close(self):
        pass


def _raw_response(status, body=b"", headers=None, url="http://en/api"):
    """用**真实** requests.Response 包一个可计数的传输流，复现库层行为。"""
    resp = pb.requests.Response()
    resp.status_code = status
    # 真实响应头是大小写不敏感映射；用普通 dict 会让 is_redirect 判不出来
    resp.headers = pb.requests.structures.CaseInsensitiveDict(headers or {})
    resp.url = url
    resp.raw = FakeRaw([body] if body else [])
    resp.request = pb.requests.Request("GET", url).prepare()
    return resp


def _join_http_thread(timeout: float = 2.0) -> None:
    """等被放弃的工作线程收敛，避免它落到别的测试里。"""
    for t in threading.enumerate():
        if t.name == "prod-budget-http":
            t.join(timeout)


class ImplicitPreReadTests(BudgetExhaustedAssertions):
    """复审反例 ①②：库预读 16 字节、闸门记账 0。"""

    BODY = b"0123456789abcdef"                       # 16 字节

    def _redirect_response(self):
        return _raw_response(302, self.BODY,
                             {"Location": "http://elsewhere/",
                              "Content-Length": str(len(self.BODY))})

    def _send_via(self, session):
        adapter = _FakeAdapter(self._redirect_response())
        session.mount("http://", adapter)
        resp = session.get("http://en/api/resource/Sales%20Order",
                           stream=True, allow_redirects=False)
        return resp, adapter

    def test_requests_by_itself_prereads_redirect_body(self):
        """反例复现：原生会话即使 allow_redirects=False 也把跳转体读走。"""
        resp, adapter = self._send_via(pb.requests.Session())
        self.assertEqual(adapter.seen["stream"], True)
        self.assertEqual(resp.raw.bytes_yielded, 16)  # 库读走 16，闸门无从记账
        self.assertTrue(resp._content_consumed)

    def test_gate_session_never_prereads(self):
        """修复：会话层关闭两条隐式预读路径 → 一个字节都不自行读。"""
        resp, adapter = self._send_via(pb._GateSession())
        self.assertEqual(resp.raw.bytes_yielded, 0)
        self.assertFalse(resp._content_consumed)

    def test_gate_session_forces_safe_stream_flags(self):
        session = pb._GateSession()
        adapter = _FakeAdapter(self._redirect_response())
        session.mount("http://", adapter)
        # 调用方即使传 stream=False / allow_redirects=True 也必须被强制成安全值
        session.get("http://en/api/x", stream=False, allow_redirects=True)
        self.assertEqual(adapter.seen["stream"], True)

    def test_gated_get_refuses_real_network_in_offline_suite(self):
        with self.assertRaises(AssertionError):
            pb.gated_get("http://en/api/x")

    def test_redirect_bytes_are_accounted_by_gate(self):
        http = FakeHTTP([FakeResponse(status=302, chunks=[self.BODY],
                                      headers={"Location": "http://elsewhere/",
                                               "Content-Length": "16"})])
        with tempfile.TemporaryDirectory(ignore_cleanup_errors=True) as d:
            b = make(d, http)
            with self.assertRaises(pb.BudgetExhausted) as ctx:
                fetch(b)
            self.assertStopped(ctx, "redirect")
            self.assertEqual(http.served[0].raw.bytes_yielded, 16)  # 经有界读取器
            self.assertEqual(b.used_bytes, 16)                      # 且记了账
            b.close()
            line = log_lines(d)[0]
            self.assertEqual(line["status"], 302)
            self.assertEqual(line["bytes"], 16)
            self.assertEqual(line["stop_reason"], "redirect")
            self.assertEqual(ledger(d)["used"]["bytes"], 16)
            self.assertTrue(b.reconcile()["ok"])

    def test_forbidden_bytes_are_accounted_by_gate(self):
        body = b'{"exc_type": "PermissionError"}'
        http = FakeHTTP([FakeResponse(status=403, chunks=[body])])
        with tempfile.TemporaryDirectory(ignore_cleanup_errors=True) as d:
            b = make(d, http)
            with self.assertRaises(pb.BudgetExhausted) as ctx:
                fetch(b)
            self.assertStopped(ctx, "auth")
            self.assertEqual(b.used_bytes, len(body))
            b.close()
            self.assertEqual(log_lines(d)[0]["bytes"], len(body))
            self.assertEqual(ledger(d)["used"]["bytes"], len(body))
            self.assertTrue(b.reconcile()["ok"])

    def test_rate_limited_body_is_accounted(self):
        body = b'{"error": "slow down"}'
        clk = FakeClock()
        http = FakeHTTP([FakeResponse(status=429, chunks=[body],
                                      headers={"Retry-After": "1"}),
                         FakeResponse(chunks=[b'{"data": []}'])], clock=clk)
        with tempfile.TemporaryDirectory(ignore_cleanup_errors=True) as d:
            b = make(d, http, clock=clk)
            self.assertEqual(fetch(b).status, 200)
            b.close()
            self.assertEqual(log_lines(d)[0]["bytes"], len(body))
            self.assertTrue(b.reconcile()["ok"])


class ExecutionBoundaryTests(BudgetExhaustedAssertions):
    """复审反例 ②：watchdog 只在收到响应头后才启动、等头阻塞不可打断、无绝对截止。"""

    @staticmethod
    def _blocked_get(gate: threading.Event, body: bytes = b'{"data": []}'):
        def blocked(url, headers=None, timeout=None, stream=False,
                    allow_redirects=None):
            gate.wait(10)                     # 模拟对端一个字节都不发
            return FakeResponse(chunks=[body] if body else [])
        return blocked

    def test_absolute_deadline_cuts_off_blocking_wait_for_headers(self):
        gate = threading.Event()
        with tempfile.TemporaryDirectory(ignore_cleanup_errors=True) as d:
            b = make(d, self._blocked_get(gate),
                     deadline=time.time() + 0.3, max_seconds=3600.0)
            started = time.time()
            try:
                with self.assertRaises(pb.BudgetExhausted) as ctx:
                    fetch(b)
            finally:
                elapsed = time.time() - started
                gate.set()
                _join_http_thread()
            self.assertStopped(ctx, "seconds")
            self.assertLess(elapsed, 3.0)      # 没有等满 10 秒的阻塞读
            b.close()
            self.assertEqual(ledger(d)["stop_reason"], "seconds")
            self.assertEqual(log_lines(d)[-1]["status"], "deadline")
            self.assertEqual(log_lines(d)[-1]["stop_reason"], "seconds")

    def test_relative_wall_budget_also_covers_wait_for_headers(self):
        gate = threading.Event()
        with tempfile.TemporaryDirectory(ignore_cleanup_errors=True) as d:
            b = make(d, self._blocked_get(gate), max_seconds=0.3)
            started = time.time()
            try:
                with self.assertRaises(pb.BudgetExhausted) as ctx:
                    fetch(b)
            finally:
                elapsed = time.time() - started
                gate.set()
                _join_http_thread()
            self.assertStopped(ctx, "seconds")
            self.assertLess(elapsed, 3.0)
            b.close()

    def test_blocking_body_read_is_cut_off(self):
        gate = threading.Event()

        class BlockingRaw(FakeRaw):
            def read(self, amt, decode_content=False):
                gate.wait(10)
                return b"0123456789abcdef"

        resp = FakeResponse(chunks=[])
        resp.raw = BlockingRaw([])
        http = FakeHTTP([resp])
        with tempfile.TemporaryDirectory(ignore_cleanup_errors=True) as d:
            b = make(d, http, deadline=time.time() + 0.3)
            started = time.time()
            try:
                with self.assertRaises(pb.BudgetExhausted) as ctx:
                    fetch(b)
            finally:
                elapsed = time.time() - started
                gate.set()
                _join_http_thread()
            self.assertStopped(ctx, "seconds")
            self.assertLess(elapsed, 3.0)
            # 复审反例：实际读出 16 字节，账本 0。阻塞读**之前**已预占读取额度；
            # 边界放弃后工作线程不得再结算 → 预占作为保守上界留在账本里。
            self.assertEqual(b.used_bytes, pb.CHUNK)
            self.assertEqual(b.decoded_bytes, pb.CHUNK)
            b.close()
            self.assertEqual(ledger(d)["used"]["bytes"], pb.CHUNK)
            self.assertEqual(log_lines(d)[-1]["bytes"], pb.CHUNK)
            self.assertTrue(b.reconcile()["ok"])

    def test_cancelled_inflight_read_keeps_reserved_quota(self):
        """复审反例（P:1026）：取消后丢弃已读块 → 实读 16 字节、账本 0。

        读取额度在阻塞读**之前**预占；取消后工作线程不得结算，预占作为
        保守上界一直保留到日志、账本与续跑（绝不清除未结算字节）。
        """
        gate = threading.Event()

        class BlockingRaw(FakeRaw):
            def read(self, amt, decode_content=False):
                gate.wait(10)
                return b"0123456789abcdef"      # 实际从 socket 读出 16 字节

        resp = FakeResponse(chunks=[])
        resp.raw = BlockingRaw([])
        http = FakeHTTP([resp])
        with tempfile.TemporaryDirectory(ignore_cleanup_errors=True) as d:
            b = make(d, http, max_bytes=1000, deadline=time.time() + 0.2)
            with self.assertRaises(pb.BudgetExhausted) as ctx:
                fetch(b)
            self.assertStopped(ctx, "seconds")
            # 预占 = min(CHUNK, 剩余字节额度) = 1000；实读的 16 字节在其中
            self.assertEqual(b.used_bytes, 1000)
            self.assertEqual(b.decoded_bytes, 1000)
            gate.set()
            _join_http_thread()
            self.assertEqual(b.used_bytes, 1000)    # 工作线程返回后也不清除
            b.close()
            self.assertEqual(ledger(d)["used"]["bytes"], 1000)
            self.assertEqual(log_lines(d)[-1]["bytes"], 1000)
            self.assertEqual(log_lines(d)[-1]["stop_reason"], "seconds")
            self.assertTrue(b.reconcile()["ok"])

            # 续跑：账本/日志一致、停机状态持久，不会再发 HTTP
            b2 = make(d, http, max_bytes=1000)
            self.assertTrue(b2.exhausted)
            self.assertEqual(b2.stop_reason, "seconds")
            self.assertEqual(b2.used_bytes, 1000)
            with self.assertRaises(pb.BudgetExhausted) as ctx2:
                fetch(b2)
            self.assertStopped(ctx2, "seconds")
            self.assertEqual(len(http.calls), 1)
            b2.close()

    def test_completed_read_settles_reservation_to_actual_bytes(self):
        """正常完成必须把预占结算为实际字节，不能长期占着整块额度。"""
        body = b'{"data": [1]}'
        http = FakeHTTP([FakeResponse(chunks=[body])])
        with tempfile.TemporaryDirectory(ignore_cleanup_errors=True) as d:
            b = make(d, http)
            fetch(b)
            self.assertEqual(b.used_bytes, len(body))
            self.assertEqual(b.decoded_bytes, len(body))
            b.close()
            self.assertEqual(ledger(d)["used"]["bytes"], len(body))
            self.assertTrue(b.reconcile()["ok"])

    def test_partial_read_then_timeout_keeps_reserved_bytes_across_retry_and_resume(self):
        """复审反例（P:1157）：读流异常整笔释放预占 → 实读 16 字节、账本/日志 0。

        真实 http.client/urllib3 的 `read(amt)` 可能先把部分字节读进缓冲区、再在
        等剩余数据时抛超时：调用方拿到异常而非字节，但 socket 上那 16 字节已经
        消耗。异常无法证明本次读未消耗，因此预占必须保留并并入 body 计数，让
        日志 `bytes`、账本 `cum_bytes`、重试与续跑口径一致（绝不归 0）。
        """
        class PartialThenTimeoutRaw(FakeRaw):
            """第一次 read 已从 socket 读走 16 字节，随后抛超时（交付 0 字节）。"""

            def __init__(self):
                super().__init__([])
                self.internal_bytes_read = 0
                self.raised = False

            def read(self, amt, decode_content=False):
                if not self.raised:
                    self.raised = True
                    self.internal_bytes_read = 16   # 已读走，但随异常丢弃
                    raise pb.requests.Timeout("read timed out")
                return super().read(amt, decode_content=decode_content)

        resp = FakeResponse(chunks=[])
        resp.raw = PartialThenTimeoutRaw()
        body = b'{"data": [{"name": "SO-1"}]}'
        http = FakeHTTP([resp, FakeResponse(chunks=[body])])
        with tempfile.TemporaryDirectory(ignore_cleanup_errors=True) as d:
            b = make(d, http)                       # 无字节上限：预占 = CHUNK
            out = fetch(b)                          # 第 1 次超时 → 第 2 次成功
            self.assertEqual(resp.raw.internal_bytes_read, 16)
            self.assertEqual(out.body, {"data": [{"name": "SO-1"}]})
            self.assertEqual(len(http.calls), 2)    # 保留预占没有吃掉重试
            self.assertEqual(b.used_bytes, pb.CHUNK + len(body))
            self.assertEqual(b.used_failures, 1)
            lines = log_lines(d)
            self.assertEqual([x["status"] for x in lines], ["read_error", 200])
            self.assertEqual(lines[0]["bytes"], pb.CHUNK)   # 不是 0
            self.assertEqual(lines[1]["bytes"], len(body))
            b.close()
            led = ledger(d)
            self.assertEqual(led["used"]["bytes"], pb.CHUNK + len(body))
            self.assertIsNone(led["pending"])
            self.assertTrue(b.reconcile()["ok"])

            # 续跑：新进程从同一账本继续，已消耗字节不会被当 0 重置
            b2 = make(d, FakeHTTP([FakeResponse(chunks=[b'{"data": []}'])]))
            self.assertEqual(b2.used_bytes, pb.CHUNK + len(body))
            self.assertFalse(b2.exhausted)
            fetch(b2)
            self.assertEqual(b2.used_bytes, pb.CHUNK + len(body) + len(b'{"data": []}'))
            self.assertTrue(b2.reconcile()["ok"])
            b2.close()

    def test_partial_read_timeout_never_undercounts_capped_byte_budget(self):
        """有字节上限时同样不得把已消耗字节清 0：宁可保守停，不可少记。"""
        class PartialThenTimeoutRaw(FakeRaw):
            def read(self, amt, decode_content=False):
                raise pb.requests.Timeout("read timed out")

        resp = FakeResponse(chunks=[])
        resp.raw = PartialThenTimeoutRaw([])
        http = FakeHTTP([resp])
        with tempfile.TemporaryDirectory(ignore_cleanup_errors=True) as d:
            b = make(d, http, max_bytes=1000)
            with self.assertRaises(pb.BudgetExhausted) as ctx:
                fetch(b)
            # 预占 = min(CHUNK, 剩余字节) = 1000，保留后预算用尽 → 下一次请求前拒绝
            self.assertStopped(ctx, "bytes")
            self.assertEqual(len(http.calls), 1)
            self.assertEqual(b.used_bytes, 1000)
            self.assertEqual(log_lines(d)[-1]["bytes"], 1000)
            b.close()
            self.assertEqual(ledger(d)["used"]["bytes"], 1000)
            self.assertTrue(b.reconcile()["ok"])

            b2 = make(d, http, max_bytes=1000)      # 持久停：续跑不静默少记后放行
            self.assertTrue(b2.exhausted)
            self.assertEqual(b2.used_bytes, 1000)
            b2.close()

    def test_deadline_return_never_calls_blocking_close(self):
        """复审反例（P:1138）：主线程同步 close() → 80ms 预算实测 437ms。

        截止返回路径不得调用任何可能阻塞的关闭；由被放弃的工作线程在
        自己的 finally 里关闭（daemon + socket 超时 = 有界收敛）。
        """
        gate = threading.Event()
        closed_by: list[int] = []
        main_ident = threading.get_ident()

        class BlockingRaw(FakeRaw):
            def read(self, amt, decode_content=False):
                gate.wait(10)
                return b"0123456789abcdef"

        class SlowCloseResponse(FakeResponse):
            def close(self):
                closed_by.append(threading.get_ident())
                time.sleep(1.0)                 # 模拟真实关连接被阻塞
                super().close()

        resp = SlowCloseResponse(chunks=[])
        resp.raw = BlockingRaw([])
        http = FakeHTTP([resp])
        with tempfile.TemporaryDirectory(ignore_cleanup_errors=True) as d:
            b = make(d, http, max_seconds=0.08)
            started = time.time()
            try:
                with self.assertRaises(pb.BudgetExhausted) as ctx:
                    fetch(b)
                elapsed = time.time() - started
                # 主线程立即返回：close() 还没被调用（否则这里会是 1.0s+）
                self.assertEqual(closed_by, [])
                self.assertLess(elapsed, 0.6)
            finally:
                gate.set()
                _join_http_thread()
            self.assertStopped(ctx, "seconds")
            self.assertEqual(len(closed_by), 1)     # 工作线程退出时才关闭
            self.assertNotEqual(closed_by[0], main_ident)
            b.close()

    def test_abandoned_attempt_never_charges_bytes(self):
        gate = threading.Event()
        with tempfile.TemporaryDirectory(ignore_cleanup_errors=True) as d:
            b = make(d, self._blocked_get(gate, b"0123456789abcdef"),
                     deadline=time.time() + 0.2)
            with self.assertRaises(pb.BudgetExhausted):
                fetch(b)
            gate.set()
            _join_http_thread()
            self.assertEqual(b.used_bytes, 0)
            self.assertEqual(b.decoded_bytes, 0)
            self.assertEqual(ledger(d)["used"]["bytes"], 0)
            self.assertEqual(len(log_lines(d)), 1)     # 只有 deadline 一行
            b.close()

    def test_absolute_deadline_in_the_past_refuses_before_http(self):
        http = FakeHTTP([])
        with tempfile.TemporaryDirectory(ignore_cleanup_errors=True) as d:
            b = make(d, http, deadline=time.time() - 1)
            with self.assertRaises(pb.BudgetExhausted) as ctx:
                fetch(b)
            self.assertStopped(ctx, "seconds")
            self.assertEqual(http.calls, [])
            self.assertEqual(b.refused, 1)
            b.close()
            self.assertEqual(ledger(d)["stop_reason"], "seconds")

    def test_socket_timeout_is_bound_by_absolute_deadline(self):
        http = FakeHTTP([FakeResponse(chunks=[b'{"data": []}'])])
        with tempfile.TemporaryDirectory(ignore_cleanup_errors=True) as d:
            b = make(d, http, deadline=time.time() + 5.0, timeout=60.0)
            fetch(b)
            self.assertLessEqual(http.timeouts[0], 5.0)
            self.assertGreater(http.timeouts[0], 0)
            b.close()

    def test_coerce_deadline_forms(self):
        self.assertIsNone(pb.coerce_deadline(None))
        self.assertEqual(pb.coerce_deadline(1700000000), 1700000000.0)
        local = datetime(2026, 10, 21, 22, 30)
        self.assertAlmostEqual(pb.coerce_deadline(local), local.timestamp(), places=3)
        hhmm = pb.coerce_deadline("22:30")
        stamp = datetime.fromtimestamp(hhmm)
        self.assertEqual((stamp.hour, stamp.minute), (22, 30))
        self.assertEqual(stamp.date(), datetime.now().date())
        with self.assertRaises(ValueError):
            pb.coerce_deadline("not-a-time")


# ── 第二轮复审 ③：终止态原子落盘 / 从日志重建 ────────
class AtomicStopTests(BudgetExhaustedAssertions):
    def test_stop_and_pending_clear_land_in_one_ledger_write(self):
        """反例：先清 pending、再落 stop，两次写之间的崩溃可续跑。"""
        http = FakeHTTP([FakeResponse(status=403, chunks=[])])
        with tempfile.TemporaryDirectory(ignore_cleanup_errors=True) as d:
            b = make(d, http)
            seen: list[dict] = []
            real_persist = b._persist

            def spy():
                real_persist()
                seen.append(json.loads((Path(d) / "prod_budget.json")
                                       .read_text(encoding="utf-8")))

            with mock.patch.object(b, "_persist", spy):
                with self.assertRaises(pb.BudgetExhausted):
                    fetch(b)
            cleared = [p for p in seen if p["pending"] is None]
            self.assertTrue(cleared)
            for payload in cleared:          # 不存在“停了但账本没记”的中间态
                self.assertTrue(payload["exhausted"])
                self.assertEqual(payload["stop_reason"], "auth")
            b.close()

    def test_crash_after_log_before_ledger_rebuilds_terminal_stop(self):
        http = FakeHTTP([FakeResponse(status=403, chunks=[])])
        with tempfile.TemporaryDirectory(ignore_cleanup_errors=True) as d:
            b1 = make(d, http)
            with mock.patch.object(b1, "_persist", lambda: None):
                with self.assertRaises(pb.BudgetExhausted):
                    fetch(b1)                        # 日志落盘、账本没写
            self.assertFalse((Path(d) / "prod_budget.json").exists())
            self.assertEqual(log_lines(d)[0]["stop_reason"], "auth")
            crash(b1)

            b2 = make(d, http)                        # 新进程：从日志重建停机
            self.assertTrue(b2.exhausted)
            self.assertEqual(b2.stop_reason, "auth")
            with self.assertRaises(pb.BudgetExhausted) as ctx:
                fetch(b2)
            self.assertStopped(ctx, "auth")
            self.assertEqual(len(http.calls), 1)      # 没有第二次 HTTP
            b2.close()
            self.assertEqual(ledger(d)["stop_reason"], "auth")

    def test_log_tail_stop_is_adopted_when_ledger_lags(self):
        body = b'{"data": []}'
        http = FakeHTTP([FakeResponse(chunks=[body]),
                         FakeResponse(status=403, chunks=[])])
        with tempfile.TemporaryDirectory(ignore_cleanup_errors=True) as d:
            b1 = make(d, http)
            fetch(b1)
            with mock.patch.object(b1, "_persist", lambda: None):
                with self.assertRaises(pb.BudgetExhausted):
                    fetch(b1)                        # 403 只进了日志
            crash(b1)

            b2 = make(d, http)
            self.assertEqual(b2.used, 2)
            self.assertTrue(b2.exhausted)
            self.assertEqual(b2.stop_reason, "auth")
            with self.assertRaises(pb.BudgetExhausted):
                fetch(b2)
            self.assertEqual(len(http.calls), 2)
            b2.close()
            self.assertTrue(b2.reconcile()["ok"])

    def test_ledger_stop_survives_when_log_has_no_stop_field(self):
        """旧账本（无 stop 字段的日志）仍以账本为准，不误判为可续跑。"""
        http = FakeHTTP([FakeResponse(status=403, chunks=[])])
        with tempfile.TemporaryDirectory(ignore_cleanup_errors=True) as d:
            b1 = make(d, http)
            with self.assertRaises(pb.BudgetExhausted):
                fetch(b1)
            b1.close()
            b2 = make(d, http)
            self.assertEqual(b2.stop_reason, "auth")
            b2.close()


# ── 崩溃续跑 / 日志对账 / 并发 ───────────────────────
class ResumeAndReconcileTests(BudgetExhaustedAssertions):
    def test_resume_after_crash_does_not_reset(self):
        http = FakeHTTP([FakeResponse(chunks=[b'{"data": [1]}']),
                         FakeResponse(chunks=[b'{"data": [2]}'])])
        with tempfile.TemporaryDirectory(ignore_cleanup_errors=True) as d:
            b1 = make(d, http, max_requests=5)
            fetch(b1)
            crash(b1)                    # 模拟进程崩溃：不调用 close()
            b2 = make(d, http, max_requests=5)
            self.assertEqual(b2.used, 1)  # 从账本继续，不重置
            fetch(b2)
            b2.close()
            lines = log_lines(d)
            self.assertEqual([x["cum_requests"] for x in lines], [1, 2])
            b3 = make(d, http, max_requests=5)
            self.assertEqual(b3.used, 2)
            self.assertEqual(b3.used_bytes, ledger(d)["used"]["bytes"])
            self.assertTrue(b3.reconcile()["ok"])
            b3.close()

    def test_crash_between_log_and_ledger_recovers_tail(self):
        http = FakeHTTP([FakeResponse(chunks=[b'{"data": [1]}'])])
        with tempfile.TemporaryDirectory(ignore_cleanup_errors=True) as d:
            b1 = make(d, http, max_requests=5)
            with mock.patch.object(b1, "_persist", lambda: None):
                fetch(b1)                # 日志已写、账本未写
            self.assertFalse((Path(d) / "prod_budget.json").exists())
            crash(b1)
            b2 = make(d, http, max_requests=5)
            self.assertEqual(b2.used, 1)
            self.assertEqual(b2.used_bytes, len(b'{"data": [1]}'))
            b2.close()
            self.assertTrue(b2.reconcile()["ok"])

    def test_tail_recovery_restores_elapsed_seconds(self):
        """复审反例：尾恢复只补请求/字节，不补耗时。"""
        clk = FakeClock()
        http = FakeHTTP([FakeResponse(chunks=[b'{"data": [1]}'])], clock=clk)
        with tempfile.TemporaryDirectory(ignore_cleanup_errors=True) as d:
            b1 = make(d, http, clock=clk, max_seconds=100.0)
            clk.t = 5.0
            with mock.patch.object(b1, "_persist", lambda: None):
                fetch(b1)                # 日志 cum_seconds≈5，账本未写
            crash(b1)
            b2 = make(d, http, clock=clk, max_seconds=100.0)
            self.assertGreaterEqual(b2.used_seconds, 5.0)
            b2.close()
            self.assertTrue(b2.reconcile()["ok"])

    def test_crash_mid_request_is_counted_and_recovered_conservatively(self):
        """复审反例：HTTP 途中崩溃丢请求/字节/耗时。"""
        clk = FakeClock()
        http = FakeHTTP([FakeResponse(chunks=[b"12345678",
                                              KeyboardInterrupt("boom")])], clock=clk)
        with tempfile.TemporaryDirectory(ignore_cleanup_errors=True) as d:
            b1 = make(d, http, clock=clk, max_requests=5, max_bytes=100,
                      max_seconds=600.0, timeout=30.0)
            with self.assertRaises(KeyboardInterrupt):
                fetch(b1)
            led = ledger(d)
            self.assertEqual(led["used"]["requests"], 1)   # 发请求前已持久预占
            self.assertIsNotNone(led["pending"])
            crash(b1)

            b2 = make(d, http, clock=clk, max_requests=5, max_bytes=100,
                      max_seconds=600.0, timeout=30.0)
            self.assertEqual(b2.used, 1)
            self.assertGreaterEqual(b2.used_bytes, 8)
            self.assertGreaterEqual(b2.used_seconds, 30.0)  # 至少补一个 timeout
            self.assertTrue(b2.reconcile()["ok"])
            # 保守恢复把字节额度记满：下一次请求在发请求前拒绝
            with self.assertRaises(pb.BudgetExhausted) as ctx:
                fetch(b2)
            self.assertStopped(ctx, "bytes")
            self.assertEqual(len(http.calls), 1)
            b2.close()

    def test_pending_with_matching_log_adopts_exact_values(self):
        """崩溃发生在日志写后、账本写前：直接采用日志精确值，不再加保守上界。"""
        http = FakeHTTP([FakeResponse(chunks=[b'{"data": [1]}'])])
        with tempfile.TemporaryDirectory(ignore_cleanup_errors=True) as d:
            b1 = make(d, http)
            fetch(b1)
            b1.close()
            led = ledger(d)
            led["pending"] = {"seq": 1, "kind": "iss", "path": "/x",
                              "timeout_seconds": 60, "wire_bytes": 0,
                              "decoded_bytes": 0, "content_encoding": ""}
            (Path(d) / "prod_budget.json").write_text(json.dumps(led), encoding="utf-8")
            b2 = make(d, http)
            self.assertEqual(b2.used_bytes, len(b'{"data": [1]}'))
            self.assertLess(b2.used_seconds, 1.0)     # 采用日志精确值，未加 60s 保守上界
            self.assertTrue(b2.reconcile()["ok"])
            b2.close()

    def test_exclusive_run_lock_rejects_second_live_budget(self):
        http = FakeHTTP([])
        with tempfile.TemporaryDirectory(ignore_cleanup_errors=True) as d:
            b1 = make(d, http)
            with self.assertRaises(pb.BudgetLedgerError):
                make(d, http)
            b1.close()
            b2 = make(d, http)                # 关闭后可重新获取
            b2.close()

    def test_log_reconciles_with_ledger(self):
        http = FakeHTTP([FakeResponse(chunks=[b'{"data": [1]}']),
                         FakeResponse(chunks=[b'{"data": [2]}']),
                         FakeResponse(chunks=[b'{"data": [3]}'])])
        with tempfile.TemporaryDirectory(ignore_cleanup_errors=True) as d:
            b = make(d, http)
            for _ in range(3):
                fetch(b)
            b.close()
            rec = b.reconcile()
            self.assertTrue(rec["ok"])
            self.assertEqual(rec["log_requests"], 3)
            self.assertEqual(rec["log_bytes"], ledger(d)["used"]["bytes"])
            self.assertEqual(rec["ledger_requests"], 3)
            self.assertEqual(len(log_lines(d)), 3)

    def test_tampered_log_refuses_resume(self):
        http = FakeHTTP([FakeResponse(chunks=[b'{"data": [1]}']),
                         FakeResponse(chunks=[b'{"data": [2]}'])])
        with tempfile.TemporaryDirectory(ignore_cleanup_errors=True) as d:
            b = make(d, http)
            fetch(b)
            fetch(b)
            b.close()
            p = Path(d) / "prod_budget.log"
            kept = p.read_text(encoding="utf-8").splitlines()[:1]
            p.write_text("\n".join(kept) + "\n", encoding="utf-8")
            with self.assertRaises(pb.BudgetLedgerError):
                make(d, http)

    def test_min_interval_is_enforced(self):
        clk = FakeClock()
        http = FakeHTTP([FakeResponse(chunks=[b'{"data": []}']),
                         FakeResponse(chunks=[b'{"data": []}'])], clock=clk)
        with tempfile.TemporaryDirectory(ignore_cleanup_errors=True) as d:
            b = make(d, http, clock=clk, min_interval=1.0)
            fetch(b)
            fetch(b)
            self.assertEqual(http.starts, [0.0, 1.0])
            b.close()

    def test_min_interval_survives_resume(self):
        """复审反例：续跑重置最小间隔。"""
        clk, wall = FakeClock(), FakeClock()
        http = FakeHTTP([FakeResponse(chunks=[b'{"data": []}']),
                         FakeResponse(chunks=[b'{"data": []}'])], clock=clk)
        with tempfile.TemporaryDirectory(ignore_cleanup_errors=True) as d:
            b1 = make(d, http, clock=clk, wall=wall, min_interval=1.0)
            fetch(b1)
            crash(b1)
            wall.t += 0.2                     # 距上次请求只过了 0.2 秒
            b2 = make(d, http, clock=clk, wall=wall, min_interval=1.0)
            fetch(b2)
            self.assertEqual(http.starts, [0.0, 1.0])   # 仍等满 1 秒
            b2.close()

    def test_interval_wait_beyond_wall_budget_refuses(self):
        clk = FakeClock()
        http = FakeHTTP([FakeResponse(chunks=[b'{"data": []}'])], clock=clk)
        with tempfile.TemporaryDirectory(ignore_cleanup_errors=True) as d:
            b = make(d, http, clock=clk, min_interval=10.0, max_seconds=5.0)
            clk.t = 4.0
            b._last_request_at = 0.0
            with self.assertRaises(pb.BudgetExhausted) as ctx:
                fetch(b)
            self.assertStopped(ctx, "seconds")
            self.assertEqual(http.calls, [])
            b.close()

    def test_overlapping_iss_contexts_are_forbidden(self):
        """复审反例：交错上下文会串预算、还原错误函数。"""
        http = FakeHTTP([])
        with tempfile.TemporaryDirectory(ignore_cleanup_errors=True) as d:
            b1 = make(d, http)
            b2 = make(str(Path(d) / "second"), http)
            original = iss.api_get_status
            with pb.iss_budget(b1, iss):
                with self.assertRaises(pb.BudgetContextError):
                    with pb.iss_budget(b2, iss):
                        pass
                self.assertIsNot(iss.api_get_status, original)
            self.assertIs(iss.api_get_status, original)
            with pb.iss_budget(b2, iss):      # 前一个退出后可正常进入
                self.assertIsNot(iss.api_get_status, original)
            self.assertIs(iss.api_get_status, original)
            b1.close()
            b2.close()


# ── 工具接入 ─────────────────────────────────────────
class ToolWiringTests(unittest.TestCase):
    def test_iss_budget_wraps_pagination_and_restores(self):
        original = iss.api_get_status
        http = FakeHTTP([FakeResponse(chunks=[b'{"data": []}'])])
        with tempfile.TemporaryDirectory(ignore_cleanup_errors=True) as d:
            b = pb.ProductionBudget(max_requests=1, ledger_path=Path(d) / "l.json",
                                    http_get=http)
            with pb.iss_budget(b, iss):
                self.assertIsNot(iss.api_get_status, original)
                self.assertEqual(iss.paginated_get("Sales Order", "http://en", "k", "s",
                                                   [], ["name"]), [])
                with self.assertRaises(pb.BudgetExhausted):
                    iss.get_single("Sales Order", "SO-1", "http://en", "k", "s")
            self.assertIs(iss.api_get_status, original)
            self.assertEqual(len(http.calls), 1)
            b.close()

    def test_extract_zero_budget_makes_no_http(self):
        with tempfile.TemporaryDirectory(ignore_cleanup_errors=True) as d:
            ledger_p = Path(d) / "prod_budget.json"
            with mock.patch.object(ex.iss, "load_credentials", return_value=("k", "s")), \
                 mock.patch.object(pb, "gated_get",
                                   side_effect=AssertionError("must not touch HTTP")):
                rc = ex.main(["--customer-code", "C-TEST", "--max-requests", "0",
                              "--budget-file", str(ledger_p),
                              "--out", str(Path(d) / "out.json")])
            self.assertEqual(rc, 1)
            led = json.loads(ledger_p.read_text(encoding="utf-8"))
            self.assertEqual(led["used"]["requests"], 0)
            self.assertEqual(led["stop_reason"], "requests")

    def test_extract_deadline_flag_enables_gate_and_refuses_after_it(self):
        """绝对截止可经 CLI 生效：已过期 → 发请求前就拒绝。"""
        past = (datetime.now(timezone.utc) - timedelta(minutes=1)).isoformat()
        with tempfile.TemporaryDirectory(ignore_cleanup_errors=True) as d:
            ledger_p = Path(d) / "prod_budget.json"
            with mock.patch.object(ex.iss, "load_credentials", return_value=("k", "s")), \
                 mock.patch.object(pb, "gated_get",
                                   side_effect=AssertionError("must not touch HTTP")):
                rc = ex.main(["--customer-code", "C-TEST", "--deadline", past,
                              "--budget-file", str(ledger_p),
                              "--out", str(Path(d) / "out.json")])
            self.assertEqual(rc, 1)
            led = json.loads(ledger_p.read_text(encoding="utf-8"))
            self.assertEqual(led["used"]["requests"], 0)
            self.assertEqual(led["stop_reason"], "seconds")
            self.assertIsNotNone(led["limits"]["deadline_epoch"])

    def test_extract_gate_counts_all_gets(self):
        with tempfile.TemporaryDirectory(ignore_cleanup_errors=True) as d:
            ledger_p = Path(d) / "prod_budget.json"
            http = FakeHTTP([FakeResponse(chunks=[b'{"data": []}'])])
            with mock.patch.object(ex.iss, "load_credentials", return_value=("k", "s")), \
                 mock.patch.object(pb, "gated_get", http):
                rc = ex.main(["--customer-code", "C-TEST", "--max-requests", "5",
                              "--budget-file", str(ledger_p),
                              "--min-interval", "0",
                              "--out", str(Path(d) / "out.json")])
            self.assertEqual(rc, 0)                    # 无匹配 SO
            led = json.loads(ledger_p.read_text(encoding="utf-8"))
            self.assertEqual(led["used"]["requests"], 1)
            self.assertEqual(len(http.calls), 1)

    def _snapshot(self, path: Path) -> None:
        snap = {
            "query": {"customer_code": "C-TEST", "item": None},
            "generated_at": "2026-10-20T18:00:00",
            "so_rows": [], "dn_rows": [], "wos": [], "jc_summary": {},
            "se_rows": [{"se": "SE-1", "work_order": None, "docstatus": 1,
                         "posting_date": "2026-05-01", "finished_qty": 10,
                         "finished_lines": 1}],
        }
        path.write_text(json.dumps(snap), encoding="utf-8")

    def test_dn_enrich_zero_budget_makes_no_http(self):
        with tempfile.TemporaryDirectory(ignore_cleanup_errors=True) as d:
            snap = Path(d) / "snap.json"
            self._snapshot(snap)
            out = Path(d) / "out"
            ledger_p = Path(d) / "prod_budget.json"
            with mock.patch.object(dn.iss, "load_credentials", return_value=("k", "s")), \
                 mock.patch.object(pb, "gated_get",
                                   side_effect=AssertionError("must not touch HTTP")):
                rc = dn.main(["--snapshot", str(snap), "--out-dir", str(out),
                              "--enrich-se", "--max-requests", "0",
                              "--budget-file", str(ledger_p), "--env-file", "x.env"])
            self.assertEqual(rc, 1)
            led = json.loads(ledger_p.read_text(encoding="utf-8"))
            self.assertEqual(led["used"]["requests"], 0)
            details = json.loads((out / "se_details.json").read_text(encoding="utf-8"))
            self.assertTrue(details["log"]["budget_exceeded"])
            self.assertEqual(details["log"]["stop_reason"], "requests")
            self.assertEqual(details["log"]["not_requested"], ["SE-1"])

    def test_dn_offline_default_unchanged_when_no_budget_flags(self):
        with tempfile.TemporaryDirectory(ignore_cleanup_errors=True) as d:
            snap = Path(d) / "snap.json"
            self._snapshot(snap)
            out = Path(d) / "out"
            rc = dn.main(["--snapshot", str(snap), "--out-dir", str(out)])
            self.assertEqual(rc, 1)                    # SE 明细缺失 → partial（与旧版一致）
            man = json.loads((out / "association_manifest.json").read_text(encoding="utf-8"))
            self.assertEqual(set(man["http_budget"]),
                             {"limit", "used", "remaining", "by_kind", "exhausted",
                              "events", "events_truncated", "note"})
            self.assertEqual(man["http_budget"]["limit"], 500)
            self.assertFalse((out / "prod_budget.json").exists())
            self.assertFalse((out / "prod_budget.log").exists())


class LegacyHttpBudgetTests(unittest.TestCase):
    def test_http_budget_keeps_old_interface(self):
        b = dn.HttpBudget(2)
        self.assertEqual(b.remaining, 2)
        b.spend("enrich")
        b.spend("probe")
        with self.assertRaises(pb.BudgetExhausted):
            b.spend("probe")
        self.assertTrue(b.exhausted)
        self.assertEqual(b.by_kind, {"enrich": 1, "probe": 1})
        log = b.as_log()
        self.assertEqual(set(log), {"limit", "used", "remaining", "by_kind",
                                    "exhausted", "events", "events_truncated", "note"})
        self.assertEqual(log["limit"], 2)
        self.assertEqual(log["used"], 2)
        self.assertEqual(log["events"],
                         [{"n": 1, "kind": "enrich", "detail": ""},
                          {"n": 2, "kind": "probe", "detail": ""}])


# ── 离线输出与父版本逐字节对照 ───────────────────────
_FIXED_NAIVE = datetime(2026, 10, 20, 18, 0, 0)
_FIXED_UTC = datetime(2026, 10, 20, 10, 0, 0, tzinfo=timezone.utc)


class _FixedDateTime(datetime):
    @classmethod
    def now(cls, tz=None):
        return _FIXED_UTC if tz is not None else _FIXED_NAIVE


def _repo_root() -> Path:
    for p in Path(__file__).resolve().parents:
        if (p / ".git").exists():
            return p
    raise unittest.SkipTest("找不到仓库根（无法做父版本对照）")


def _git_show(relpath: str) -> str:
    repo = _repo_root()
    try:
        out = subprocess.run(["git", "show", f"{PARENT_COMMIT}:{relpath}"],
                             cwd=repo, capture_output=True, check=True)
    except FileNotFoundError as e:
        raise unittest.SkipTest(f"git 不可用，无法做父版本对照: {e}")
    except subprocess.CalledProcessError as e:
        raise AssertionError(
            f"无法读取父版本 {PARENT_COMMIT}:{relpath}: "
            f"{e.stderr.decode('utf-8', 'replace')[:300]}") from e
    return out.stdout.decode("utf-8")


def _load_source(source: str, filename: str, name: str, tmpdir: str):
    # 父版本用 `Path(__file__).resolve().parents[7]` 作为 `next()` 的默认值；
    # 该默认值会被**立即求值**，所以源码必须放在至少 8 层深的路径下。
    # 同时路径要在仓库根之下，`next()` 才能找到 `EN_API/item_shipment_status.py`。
    deep = Path(tmpdir)
    for part in ("a", "b", "c", "d", "e", "f"):
        deep = deep / part
    deep.mkdir(parents=True, exist_ok=True)
    path = deep / filename
    path.write_text(source, encoding="utf-8")
    spec = importlib.util.spec_from_file_location(name, path)
    mod = importlib.util.module_from_spec(spec)
    sys.modules[name] = mod
    spec.loader.exec_module(mod)
    return mod


class ParentVersionParityTests(unittest.TestCase):
    """复审要求：离线分析输出必须与父版本逐字节一致，而不只是字段集合。"""

    def _dn_snapshot(self, path: Path) -> None:
        snap = {
            "query": {"customer_code": "C-TEST", "item": None},
            "generated_at": "2026-10-20T18:00:00",
            "so_rows": [], "dn_rows": [], "wos": [], "jc_summary": {},
            "se_rows": [{"se": "SE-1", "work_order": None, "docstatus": 1,
                         "posting_date": "2026-05-01", "finished_qty": 10,
                         "finished_lines": 1}],
        }
        path.write_text(json.dumps(snap), encoding="utf-8")

    def test_dn_offline_outputs_match_parent_byte_for_byte(self):
        with tempfile.TemporaryDirectory(dir=_repo_root(), prefix=".parity-dn-") as moddir:
            parent = _load_source(_git_show(DN_RELPATH), "dn_parent.py",
                                  "g1b_dn_wo_jc_se_parent", moddir)
            with tempfile.TemporaryDirectory(ignore_cleanup_errors=True) as d:
                snap = Path(d) / "snap.json"
                self._dn_snapshot(snap)
                out_cur, out_par = Path(d) / "cur", Path(d) / "par"
                argv = ["--snapshot", str(snap), "--run-id", "FIXED"]
                with mock.patch.object(dn, "datetime", _FixedDateTime):
                    rc_cur = dn.main(argv + ["--out-dir", str(out_cur)])
                parent_argv = ["dn_parent.py"] + argv + ["--out-dir", str(out_par)]
                with mock.patch.object(parent, "datetime", _FixedDateTime), \
                     mock.patch.object(sys, "argv", parent_argv):
                    rc_par = parent.main()
                self.assertEqual(rc_cur, rc_par)
                for name in ("association_manifest.json", "line_dispositions.jsonl",
                             "snapshots_manifest.json", "run.log"):
                    self.assertEqual((out_cur / name).read_bytes(),
                                     (out_par / name).read_bytes(), name)
                self.assertFalse((out_cur / "prod_budget.json").exists())

    def test_en_extract_offline_output_matches_parent_byte_for_byte(self):
        with tempfile.TemporaryDirectory(dir=_repo_root(), prefix=".parity-en-") as moddir:
            parent = _load_source(_git_show(EX_RELPATH), "en_parent.py",
                                  "g1b_en_extract_parent", moddir)
            ctx = {
                "so_rows": [{
                    "so": "SO-1", "so_status": "To Deliver and Bill", "so_docstatus": 1,
                    "transaction_date": "2026-05-01", "so_delivery_date": "2026-06-01",
                    "line_id": "SO-1-1", "item_code": "KS0001",
                    "customer_item_code": "C1", "warehouse": "W", "uom": "Nos",
                    "qty": 10, "delivered_qty": 0, "shipped_dn": [], "draft_dn": [],
                    "open_qty": 10, "anomalies": [], "wos": [{"name": "WO-1"}],
                    "pps": [],
                }],
                "dn_rows": [], "pp_rows": [],
                "wos": [{"name": "WO-1", "status": "In Process", "docstatus": 1,
                         "sales_order": "SO-1", "production_item": "KS0001", "qty": 10,
                         "produced_qty": 0, "planned_start_date": "2026-05-01",
                         "planned_end_date": "2026-05-02", "bom_no": "BOM-1"}],
                "jc_map": {}, "item_codes": ["KS0001"],
                "master_items": [{"name": "KS0001", "item_name": "X",
                                  "item_group": "G"}],
                "totals": {"open_qty": 10}, "anomalies": [],
            }
            with tempfile.TemporaryDirectory(ignore_cleanup_errors=True) as d:
                out_cur, out_par = Path(d) / "cur.json", Path(d) / "par.json"
                with mock.patch.object(ex.iss, "load_credentials",
                                       return_value=("k", "s")), \
                     mock.patch.object(ex.iss, "build_context", return_value=ctx), \
                     mock.patch.object(ex, "fetch_manufacture_stock_entries",
                                       return_value=([], None)), \
                     mock.patch.object(parent, "fetch_manufacture_stock_entries",
                                       return_value=([], None)), \
                     mock.patch.object(ex, "datetime", _FixedDateTime):
                    rc_cur = ex.main(["--customer-code", "C-TEST", "--sleep", "0",
                                      "--out", str(out_cur)])
                argv = ["en_parent.py", "--customer-code", "C-TEST",
                        "--sleep", "0", "--out", str(out_par)]
                with mock.patch.object(ex.iss, "load_credentials",
                                       return_value=("k", "s")), \
                     mock.patch.object(ex.iss, "build_context", return_value=ctx), \
                     mock.patch.object(parent, "fetch_manufacture_stock_entries",
                                       return_value=([], None)), \
                     mock.patch.object(parent, "datetime", _FixedDateTime), \
                     mock.patch.object(sys, "argv", argv):
                    rc_par = parent.main()
                self.assertEqual(rc_cur, rc_par)
                self.assertEqual(out_cur.read_bytes(), out_par.read_bytes())


if __name__ == "__main__":
    unittest.main(verbosity=2)
