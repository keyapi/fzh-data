"""batch：resume+limit、并行 delay。"""

from __future__ import annotations

import json
import time

from fedex_track.batch import BatchItem, merge_resumed_done, run_batch
from fedex_track.models import FdxTrackInfo


def _ok(number: str) -> dict[str, list[FdxTrackInfo]]:
    return {number: [FdxTrackInfo(tracking_number=number, delivered=True)]}


class _Fake:
    def __init__(self):
        self.calls: list[list[str]] = []

    def track_many(self, numbers: list[str]) -> dict[str, list[FdxTrackInfo]]:
        self.calls.append(list(numbers))
        out = {}
        for n in numbers:
            out.update(_ok(n))
        return out


def test_resume_limit_advances_past_done(tmp_path):
    raw = tmp_path / "r.raw.json"
    raw.write_text(json.dumps({
        "A": {"ok": True, "remark": "", "raw": {"trackingNumber": "A", "trackResults": []}},
    }), encoding="utf-8")
    fc = _Fake()
    items = [BatchItem("A"), BatchItem("B"), BatchItem("C")]
    out = run_batch(fc.track_many, items, workers=1, retries=0, resume_from=str(raw), limit=1)
    queried = [n for chunk in fc.calls for n in chunk]
    assert "A" not in queried
    assert queried == ["B"]  # 跳过已完成，limit 作用在 pending
    merged = merge_resumed_done(out, str(raw))
    assert {r.number for r in merged} >= {"A", "B"}


def test_delay_applied_on_parallel_path(monkeypatch):
    sleeps: list[float] = []
    monkeypatch.setattr(time, "sleep", lambda s: sleeps.append(s))
    fc = _Fake()
    items = [BatchItem("1"), BatchItem("2")]
    run_batch(fc.track_many, items, workers=2, chunk=1, retries=0, delay=0.25)
    assert 0.25 in sleeps
