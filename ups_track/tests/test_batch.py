"""batch.py 单测：输入解析、局部失败隔离、顺序保持、resume。"""

from __future__ import annotations

import json

from ups_track.batch import (
    BatchItem,
    load_input_file,
    merge_resumed_done,
    run_batch,
)
from ups_track.client import UpsTrackError
from ups_track.models import parse_track_payload

from _payloads import delivered_payload, empty_payload


class _FakeClient:
    """可控的假查询器：_fail 集合里的号抛错，其余返回 payload 解析结果。"""

    def __init__(self, payloads=None, fail=(), retriable_fail=False):
        self.payloads = payloads or {}
        self.fail = set(fail)
        self.calls: list[str] = []
        self.retriable_fail = retriable_fail

    def track(self, number: str):
        self.calls.append(number)
        if number in self.fail:
            raise UpsTrackError(f"UPS track {number} 失败", category="auth", retriable=self.retriable_fail)
        payload = self.payloads.get(number, delivered_payload(number))
        return parse_track_payload(number, payload)


def test_run_batch_partial_failure_keeps_order():
    fc = _FakeClient(fail={"2"})
    items = [BatchItem("2"), BatchItem("1"), BatchItem("3")]
    out = run_batch(fc.track, items, workers=2, retries=0)
    assert [r.number for r in out] == ["2", "1", "3"]
    assert [r.ok for r in out] == [False, True, True]
    assert out[0].error and "失败" in out[0].error
    assert out[0].attempts == 1


def test_run_batch_retries_retriable_then_gives_up():
    fc = _FakeClient(fail={"9"}, retriable_fail=True)
    out = run_batch(fc.track, [BatchItem("9")], workers=1, retries=2)
    rec = out[0]
    assert rec.ok is False
    assert rec.attempts == 3  # 1 原始 + 2 重试


def test_load_txt():
    import pathlib
    p = pathlib.Path("_tmp_batch_txt.txt")
    p.write_text(
        "# comment\n"
        "1Z999AA10123456784\n"
        "1Z999AA10123456785 ORD-备注\n",
        encoding="utf-8",
    )
    try:
        items = load_input_file(str(p))
    finally:
        p.unlink()
    assert len(items) == 2
    assert items[0].number == "1Z999AA10123456784"
    assert items[0].remark == ""
    assert items[1].number == "1Z999AA10123456785"
    assert items[1].remark == "ORD-备注"


def test_load_csv_header_and_remark():
    import pathlib
    p = pathlib.Path("_tmp_batch_csv.csv")
    p.write_text(
        "tracking,订单号\n1Z999AA10123456784,ORD-1\n1Z999AA10123456785,ORD-2\n",
        encoding="utf-8",
    )
    try:
        items = load_input_file(str(p))
    finally:
        p.unlink()
    assert len(items) == 2
    assert items[0].number == "1Z999AA10123456784"
    assert "订单号=ORD-1" in items[0].remark


def test_resume_skips_done_and_merges_back(tmp_path):
    raw = tmp_path / "r.raw.json"
    raw.write_text(json.dumps({"1ZOK": {"ok": True, "remark": "旧", "raw": delivered_payload("1ZOK")}}), encoding="utf-8")

    fc = _FakeClient()  # 若被调用 1ZOK 也会成功，但应被跳过
    out = run_batch(fc.track, [BatchItem("1ZOK"), BatchItem("1ZNEW")], workers=1, resume_from=str(raw))
    assert "1ZOK" not in fc.calls  # 已成功 → 跳过
    assert "1ZNEW" in fc.calls
    merged = merge_resumed_done(out, str(raw))
    nums = [r.number for r in merged]
    assert nums == ["1ZNEW", "1ZOK"]  # 旧的成功号并回（保持首次出现顺序）
    assert merged[1].ok is True
    assert merged[1].info is not None
