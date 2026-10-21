#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""生产只读统一预算闸门离线单测（全部 mock，不访问生产）。

覆盖任务书 2026-10-21-gate-task.md 的验收项：
  零预算 / 精确边界（请求、字节）/ 超大响应中途停 / 超时连续失败 /
  429 Retry-After 与重试上限 / 401 立即停 / 崩溃续跑 / 日志对账 /
  解压后字节上限 / 最小间隔 / 两工具接入 / 离线默认不变。
"""

from __future__ import annotations

import gzip
import json
import sys
import tempfile
import unittest
from pathlib import Path
from unittest import mock

BASE = Path(__file__).resolve().parent
if str(BASE) not in sys.path:
    sys.path.insert(0, str(BASE))

import prod_budget as pb  # noqa: E402
import g1b_dn_wo_jc_se as dn  # noqa: E402
import g1b_en_extract as ex  # noqa: E402
import EN_API.item_shipment_status as iss  # noqa: E402


# ── 测试替身 ──────────────────────────────────────────
class FakeRaw:
    def __init__(self, chunks, tick=None):
        self.chunks = list(chunks)
        self.tick = tick
        self.chunks_yielded = 0
        self.bytes_yielded = 0

    def stream(self, amt, decode_content=False):
        for c in self.chunks:
            if self.tick:
                self.tick()
            self.chunks_yielded += 1
            self.bytes_yielded += len(c)
            yield c


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

    def __init__(self, responses, clock=None):
        self.responses = list(responses)
        self.served: list[FakeResponse] = []
        self.calls: list[str] = []
        self.starts: list[float] = []
        self.clock = clock

    def __call__(self, url, headers=None, timeout=None, stream=False):
        self.calls.append(url)
        if self.clock is not None:
            self.starts.append(self.clock())
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


def make(tmp: str, http, *, clock=None, **kw) -> pb.ProductionBudget:
    d = Path(tmp)
    return pb.ProductionBudget(
        ledger_path=d / "prod_budget.json", log_path=d / "prod_budget.log",
        http_get=http, clock=clock, sleep=clock.sleep if clock else None, **kw)


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

    def test_oversized_response_stops_mid_stream(self):
        chunks = [b"12345678", b"ABCDEFGH", b"ZZZZZZZZ"]
        http = FakeHTTP([FakeResponse(chunks=chunks)])
        with tempfile.TemporaryDirectory(ignore_cleanup_errors=True) as d:
            b = make(d, http, max_bytes=10)
            with self.assertRaises(pb.BudgetExhausted) as ctx:
                fetch(b)
            self.assertStopped(ctx, "bytes")
            self.assertEqual(b.used_bytes, 10)            # 不越界
            self.assertEqual(http.served[0].raw.bytes_yielded, 16)
            self.assertEqual(http.served[0].raw.chunks_yielded, 2)  # 第三块没读完
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


# ── 超时 / 429 / 401 ─────────────────────────────────
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

    def test_5xx_stops_after_three(self):
        http = FakeHTTP([FakeResponse(status=500, chunks=[b"err"]) for _ in range(5)])
        with tempfile.TemporaryDirectory(ignore_cleanup_errors=True) as d:
            b = make(d, http)
            with self.assertRaises(pb.BudgetExhausted) as ctx:
                fetch(b)
            self.assertStopped(ctx, "consecutive_failures")
            self.assertEqual(len(http.calls), 3)
            b.close()


# ── 崩溃续跑 / 日志对账 ──────────────────────────────
class ResumeAndReconcileTests(BudgetExhaustedAssertions):
    def test_resume_after_crash_does_not_reset(self):
        http = FakeHTTP([FakeResponse(chunks=[b'{"data": [1]}']),
                         FakeResponse(chunks=[b'{"data": [2]}'])])
        with tempfile.TemporaryDirectory(ignore_cleanup_errors=True) as d:
            b1 = make(d, http, max_requests=5)
            fetch(b1)                    # 模拟进程崩溃：不调用 close()
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
            b2 = make(d, http, max_requests=5)
            self.assertEqual(b2.used, 1)
            self.assertEqual(b2.used_bytes, len(b'{"data": [1]}'))
            b2.close()
            self.assertTrue(b2.reconcile()["ok"])

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
                 mock.patch.object(pb.requests, "get",
                                   side_effect=AssertionError("must not touch HTTP")):
                rc = ex.main(["--customer-code", "C-TEST", "--max-requests", "0",
                              "--budget-file", str(ledger_p),
                              "--out", str(Path(d) / "out.json")])
            self.assertEqual(rc, 1)
            led = json.loads(ledger_p.read_text(encoding="utf-8"))
            self.assertEqual(led["used"]["requests"], 0)
            self.assertEqual(led["stop_reason"], "requests")

    def test_extract_gate_counts_all_gets(self):
        with tempfile.TemporaryDirectory(ignore_cleanup_errors=True) as d:
            ledger_p = Path(d) / "prod_budget.json"
            http = FakeHTTP([FakeResponse(chunks=[b'{"data": []}'])])
            with mock.patch.object(ex.iss, "load_credentials", return_value=("k", "s")), \
                 mock.patch.object(pb.requests, "get", http):
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
                 mock.patch.object(pb.requests, "get",
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


if __name__ == "__main__":
    unittest.main(verbosity=2)
