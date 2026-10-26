from __future__ import annotations

import json
from datetime import date
from pathlib import Path

import pytest

from tongtool_api.receipt_collector import (
    CollectedRow,
    CollectionResult,
    CollectionWindow,
    build_summary,
    collect_receipts,
    split_windows,
)


def mcp_response(rows: list[dict], page_no: int, page_size: int) -> dict:
    return {
        "result": {
            "content": [
                {
                    "type": "text",
                    "text": json.dumps({
                        "code": 200,
                        "datas": {"pageNo": page_no, "pageSize": page_size, "array": rows},
                    }),
                }
            ]
        }
    }


def caller_for(pages: list[list[dict]]):
    calls = []

    def caller(tool: str, arguments: dict) -> dict:
        calls.append(dict(arguments))
        page = int(arguments.get("pageNo", 1))
        index = min(page - 1, len(pages) - 1)
        return mcp_response(pages[index], page, int(arguments.get("pageSize", 100)))

    return caller, calls


def test_split_windows_uses_overlap() -> None:
    windows = split_windows("2026-10-01", "2026-10-26", window_days=7, overlap_days=1)
    assert windows[0] == CollectionWindow(date(2026, 10, 1), date(2026, 10, 7))
    assert windows[1] == CollectionWindow(date(2026, 10, 7), date(2026, 10, 13))
    assert windows[-1] == CollectionWindow(date(2026, 10, 25), date(2026, 10, 26))


def test_overlap_replay_is_dropped_with_flag() -> None:
    row = {"purchaseOrderCode": "PO1", "goodsDetailId": "G1", "warehousingNum": 2}
    caller, calls = caller_for([[row]])
    result = collect_receipts(
        caller, "2026-10-01", "2026-10-13",
        window_days=7, overlap_days=1, sleep=lambda _: None,
    )
    assert len(calls) == 2
    assert result.input_count == 2
    assert result.unique_count == 1
    assert result.overlap_duplicate_count == 1
    assert result.rows[1].overlap_duplicate is True
    assert result.rows[0].weak_event_key == result.rows[1].weak_event_key


def test_same_window_duplicates_are_kept_and_flagged() -> None:
    row = {"purchaseOrderCode": "PO1", "goodsDetailId": "G1", "warehousingNum": 2}
    caller, _ = caller_for([[row, dict(row)]])
    result = collect_receipts(
        caller, "2026-10-01", "2026-10-01", sleep=lambda _: None,
    )
    assert result.input_count == 2
    assert result.unique_count == 2
    assert result.possible_duplicate_count == 2
    assert result.overlap_duplicate_count == 0


def test_cache_reuse_avoids_second_fetch(tmp_path: Path) -> None:
    row = {"purchaseOrderCode": "PO1", "goodsDetailId": "G1", "warehousingNum": 2}
    caller, calls = caller_for([[row]])
    first = collect_receipts(
        caller, "2026-10-01", "2026-10-01", cache_dir=tmp_path, sleep=lambda _: None,
    )
    second = collect_receipts(
        caller, "2026-10-01", "2026-10-01", cache_dir=tmp_path, sleep=lambda _: None,
    )
    assert len(calls) == 1
    assert first.cache_hits == 0
    assert second.cache_hits == 1
    assert second.unique_count == 1


def test_truncated_window_is_reported() -> None:
    row = {"purchaseOrderCode": "PO1", "goodsDetailId": "G1", "warehousingNum": 2}
    caller, _ = caller_for([[row]])
    result = collect_receipts(
        caller, "2026-10-01", "2026-10-01",
        page_size=1, max_pages=1, sleep=lambda _: None,
    )
    assert result.truncated_windows == (CollectionWindow(date(2026, 10, 1), date(2026, 10, 1)),)


def test_cache_inside_repo_is_rejected() -> None:
    caller, calls = caller_for([[{"purchaseOrderCode": "PO1"}]])
    with pytest.raises(ValueError):
        collect_receipts(
            caller, "2026-10-01", "2026-10-01",
            cache_dir=Path(__file__).resolve().parent, sleep=lambda _: None,
        )
    assert calls == []


def test_summary_is_aggregate_only() -> None:
    window = CollectionWindow(date(2026, 10, 1), date(2026, 10, 7))
    rows = (
        CollectedRow(0, window, {"purchaseOrderCode": "PO1", "sku": "S1",
                                 "warehousingDate": "2026-10-01 08:00:00"}, ("k1",), False, False),
        CollectedRow(1, window, {"purchaseOrderCode": "PO1", "sku": "S2",
                                 "warehousingDate": "2026-10-02 09:00:00"}, ("k2",), False, True),
        CollectedRow(2, window, {"purchaseOrderCode": "PO2", "sku": "S1",
                                 "warehousingDate": "2026-10-02 10:00:00"}, ("k3",), True, False),
    )
    result = CollectionResult(
        rows=rows, windows=(window,), input_count=3, unique_count=2,
        overlap_duplicate_count=1, possible_duplicate_count=1,
        truncated_windows=(), cache_hits=0,
    )
    summary = build_summary(result)
    assert summary["distinct_po"] == 1
    assert summary["distinct_sku"] == 2
    assert summary["day_counts"] == {"2026-10-01": 1, "2026-10-02": 1}
    assert summary["possible_duplicate_count"] == 1
    assert "rows" not in summary
