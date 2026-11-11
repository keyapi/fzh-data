# -*- coding: utf-8 -*-
"""audit_august_order_side 的失败隔离与数量对账测试（不联网）。"""
from __future__ import annotations

import importlib.util
import sys
from pathlib import Path

_ROOT = Path(__file__).resolve().parents[1]
if str(_ROOT) not in sys.path:
    sys.path.insert(0, str(_ROOT))

from tongtool_order_cost.order_side_input import OrderInput  # noqa: E402

_SCRIPT = _ROOT / "scripts" / "audit_august_order_side.py"
_spec = importlib.util.spec_from_file_location("audit_august_order_side", _SCRIPT)
m = importlib.util.module_from_spec(_spec)
_spec.loader.exec_module(m)


def test_chunked_splits_in_order():
    assert list(m.chunked(["a", "b", "c", "d", "e"], 2)) == [["a", "b"], ["c", "d"], ["e"]]
    assert list(m.chunked([], 3)) == []


def test_fetch_resilient_isolates_single_failure_via_bisect():
    calls: list[list[str]] = []

    def fetch(ids):
        calls.append(list(ids))
        if "BAD" in ids:
            raise RuntimeError("boom")
        return [{"name": i} for i in ids]

    failures: list[str] = []
    failed_ids: set[str] = set()

    rows = m.fetch_resilient(fetch, ["A", "BAD", "C"], failures, failed_ids, "order")

    assert rows == [{"name": "A"}, {"name": "C"}]
    assert failed_ids == {"BAD"}
    assert len(failures) == 1 and "order BAD: RuntimeError: boom" == failures[0]


def test_fetch_resilient_records_every_failed_id():
    def fetch(ids):
        if any(i.startswith("BAD") for i in ids):
            raise RuntimeError("boom")
        return [{"name": i} for i in ids]

    failures: list[str] = []
    failed_ids: set[str] = set()

    rows = m.fetch_resilient(fetch, ["A", "BAD1", "BAD2", "B"], failures, failed_ids, "items")

    assert {r["name"] for r in rows} == {"A", "B"}
    assert failed_ids == {"BAD1", "BAD2"}
    assert len(failures) == 2


def test_fetch_resilient_empty_input_makes_no_call():
    def fetch(ids):  # pragma: no cover - 不应被调用
        raise AssertionError("should not be called")

    assert m.fetch_resilient(fetch, [], [], set(), "order") == []


def test_build_report_separates_failed_from_missing():
    row = OrderInput(
        requested_order_id="A",
        order_id="A",
        base_order_id="A",
        platform_order_body="",
        is_child=False,
        original_order_exists=None,
        is_supplementary=False,
        warehouse_name="",
        piece_count=1,
        piece_rule="成品口径",
        shipping_methods=(),
        items=(),
        status="ok",
    )

    report = m.build_report(
        3,
        ["A", "B", "C"],
        [row],
        failures=("order B: RuntimeError: boom",),
        failed_ids=frozenset({"B"}),
    )

    assert report["reconciliation"]["requested_unique"] == 3
    assert report["reconciliation"]["fetched"] == 1
    assert report["reconciliation"]["failed"] == 1
    assert report["reconciliation"]["missing"] == 1
    assert report["missing_order_ids"] == ["C"]
    assert report["failed_order_ids"] == ["order B: RuntimeError: boom"]
