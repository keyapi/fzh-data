# -*- coding: utf-8 -*-
"""BACKLOG-TIMESTAMPS 用例。

重点验证**不许发生的事**：改状态、覆盖已有值、把猜的时间写进去、证据冲突时乱填。
"""

from __future__ import annotations

import importlib.util
import json
import sys
from pathlib import Path

import pytest

ROOT = Path(__file__).resolve().parents[2]
_SPEC = importlib.util.spec_from_file_location("fzh_backlog_ts", ROOT / "scripts" / "backlog_timestamps.py")
assert _SPEC and _SPEC.loader
bt = importlib.util.module_from_spec(_SPEC)
sys.modules[_SPEC.name] = bt
_SPEC.loader.exec_module(bt)


def make_repo(tmp_path: Path, tasks: list[dict], reviews: dict[str, str],
              manifests: dict[str, str]) -> Path:
    agent = tmp_path / "agent-ops"
    (agent / "reviews").mkdir(parents=True)
    store = tmp_path / "en-demand-v1"
    store.mkdir()
    for name, body in reviews.items():
        (agent / "reviews" / name).write_text(body, encoding="utf-8")
    for rel, generated_at in manifests.items():
        path = store / rel
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_text(json.dumps({"generated_at": generated_at}), encoding="utf-8")
    backlog = agent / "PROJECT_BACKLOG.json"
    backlog.write_text(json.dumps({"updated_at": "t0", "tasks": tasks},
                                  ensure_ascii=False, indent=1), encoding="utf-8")
    return backlog


@pytest.fixture(autouse=True)
def patch_paths(tmp_path, monkeypatch):
    monkeypatch.setattr(bt, "AGENT_OPS", tmp_path / "agent-ops")
    monkeypatch.setattr(bt, "ORDER_STORE", tmp_path / "en-demand-v1")


def test_attempt_id_parses_dispatch_time():
    assert bt.parse_attempt_ts("att-20261028-0356-promo").isoformat() == "2026-10-28T03:56:00+08:00"
    assert bt.parse_attempt_ts("att-20261028-0510-po").isoformat() == "2026-10-28T05:10:00+08:00"
    assert bt.parse_attempt_ts("nonsense") is None
    assert bt.parse_attempt_ts(None) is None


def test_fills_started_at_from_attempt_id(tmp_path):
    backlog = make_repo(tmp_path,
                        [dict(id="T1", state="done", attempt_id="att-20261028-0430-x")],
                        reviews={}, manifests={})
    out = bt.run(backlog, write=False)
    assert [(p["task_id"], p["field"], p["value"]) for p in out["proposals"]] == [
        ("T1", "started_at", "2026-10-28T04:30:00+08:00")]


def test_never_overwrites_existing_timestamp(tmp_path):
    backlog = make_repo(tmp_path, [dict(
        id="T1", state="done", attempt_id="att-20261028-0430-x",
        started_at="2026-10-28T01:00:00+08:00")], reviews={}, manifests={})
    out = bt.run(backlog, write=False)
    assert out["proposals"] == []


def test_finished_at_from_manifest_and_review(tmp_path):
    monkeypatch_target = bt.ARTIFACT_FOR_FINISH
    monkeypatch_target.clear()
    monkeypatch_target["DEV"] = "en-demand-v1/out/manifest.json"
    bt.REVIEW_FOR_FINISH.clear()
    bt.REVIEW_FOR_FINISH["DEV-REVIEW"] = "reviews/dev-review.md"
    backlog = make_repo(tmp_path,
                        [dict(id="DEV", state="done"), dict(id="DEV-REVIEW", state="done")],
                        reviews={"dev-review.md": "---\nverdict: reject\n---\n"},
                        manifests={"out/manifest.json": "2026-10-28T03:00:00+08:00"})
    out = bt.run(backlog, write=False)
    got = {p["task_id"]: p for p in out["proposals"]}
    assert got["DEV"]["value"] == "2026-10-28T03:00:00+08:00"
    assert got["DEV"]["evidence"] == "manifest.generated_at"
    assert got["DEV-REVIEW"]["value"].startswith("20")     # 文件 mtime
    assert got["DEV-REVIEW"]["evidence"].startswith("审核文档 mtime")


def test_no_finished_at_for_open_states(tmp_path):
    bt.ARTIFACT_FOR_FINISH.clear()
    bt.ARTIFACT_FOR_FINISH["OPEN"] = "en-demand-v1/out/manifest.json"
    backlog = make_repo(tmp_path, [dict(id="OPEN", state="running")], reviews={},
                        manifests={"out/manifest.json": "2026-10-28T03:00:00+08:00"})
    out = bt.run(backlog, write=False)
    assert out["proposals"] == []
    assert any("与状态矛盾" in s["reason"] for s in out["skipped"])


def test_accepted_at_only_for_strict_accept(tmp_path):
    bt.ACCEPTING_REVIEWS.clear()
    bt.ACCEPTING_REVIEWS["A"] = "reviews/a.md"
    bt.ACCEPTING_REVIEWS["B"] = "reviews/b.md"
    backlog = make_repo(tmp_path, [dict(id="A", state="done"), dict(id="B", state="done")],
                        reviews={"a.md": "---\nverdict: accept\n---\n",
                                 "b.md": "---\nverdict: accept-with-findings\n---\n"},
                        manifests={})
    out = bt.run(backlog, write=False)
    filled = {p["task_id"] for p in out["proposals"] if p["field"] == "accepted_at"}
    assert filled == {"A"}                                  # accept-with-findings 不算通过
    assert any(s["task_id"] == "B" and "不是严格 accept" in s["reason"] for s in out["skipped"])


def test_attempt_later_than_artifact_drops_only_started_at(tmp_path):
    """attempt_id 晚于产物完成 = 二次派发，不能当任务起点；finished_at 仍要保留。"""
    bt.ARTIFACT_FOR_FINISH.clear()
    bt.ARTIFACT_FOR_FINISH["T1"] = "en-demand-v1/out/manifest.json"
    backlog = make_repo(tmp_path,
                        [dict(id="T1", state="done", attempt_id="att-20261028-0510-x")],
                        reviews={}, manifests={"out/manifest.json": "2026-10-28T03:24:15+08:00"})
    out = bt.run(backlog, write=False)
    fields = {p["field"] for p in out["proposals"]}
    assert fields == {"finished_at"}                        # started_at 被剔除
    assert any(s["field"] == "started_at" and "疑似二次派发" in s["reason"]
               for s in out["skipped"])


def test_shared_evidence_is_not_attributed(tmp_path):
    """同一份文件被两个任务认领 → 两个都不填，不硬分。"""
    bt.ARTIFACT_FOR_FINISH.clear()
    bt.ARTIFACT_FOR_FINISH["T1"] = "en-demand-v1/out/manifest.json"
    bt.ARTIFACT_FOR_FINISH["T2"] = "en-demand-v1/out/manifest.json"
    backlog = make_repo(tmp_path, [dict(id="T1", state="done"), dict(id="T2", state="done")],
                        reviews={}, manifests={"out/manifest.json": "2026-10-28T03:00:00+08:00"})
    out = bt.run(backlog, write=False)
    assert out["proposals"] == []
    assert len(out["conflicts"]) == 1


def test_missing_evidence_file_is_skipped_not_guessed(tmp_path):
    bt.ARTIFACT_FOR_FINISH.clear()
    bt.ARTIFACT_FOR_FINISH["T1"] = "en-demand-v1/nope/manifest.json"
    backlog = make_repo(tmp_path, [dict(id="T1", state="done")], reviews={}, manifests={})
    out = bt.run(backlog, write=False)
    assert out["proposals"] == []
    assert any("证据文件不存在" in s["reason"] for s in out["skipped"])


def test_write_preserves_state_and_creates_backup(tmp_path):
    backlog = make_repo(tmp_path, [dict(
        id="T1", state="review", priority="P1", note="keep me",
        attempt_id="att-20261028-0430-x")], reviews={}, manifests={})
    before = json.loads(backlog.read_text(encoding="utf-8"))

    out = bt.run(backlog, write=True)
    assert out["written"] is True
    assert out["backup"] and Path(out["backup"]).exists()

    after = json.loads(backlog.read_text(encoding="utf-8"))
    assert after["tasks"][0]["state"] == "review"           # 状态没动
    assert after["tasks"][0]["priority"] == "P1"
    assert after["tasks"][0]["note"] == "keep me"
    assert after["tasks"][0]["started_at"] == "2026-10-28T04:30:00+08:00"
    assert after["updated_at"] == before["updated_at"]      # 不碰 updated_at
    assert bt.diff_guard(before, after) == []


def test_diff_guard_catches_state_change():
    before = {"updated_at": "t0", "tasks": [dict(id="T1", state="done")]}
    after = {"updated_at": "t0", "tasks": [dict(id="T1", state="running")]}
    problems = bt.diff_guard(before, after)
    assert any("state 被改动" in p for p in problems)


def test_diff_guard_catches_unauthorised_new_field():
    before = {"updated_at": "t0", "tasks": [dict(id="T1", state="done")]}
    after = {"updated_at": "t0", "tasks": [dict(id="T1", state="done", priority="P0")]}
    problems = bt.diff_guard(before, after)
    assert any("非白名单字段 priority" in p for p in problems)


def test_provenance_csv_records_every_decision(tmp_path):
    bt.ARTIFACT_FOR_FINISH.clear()
    bt.ARTIFACT_FOR_FINISH["T1"] = "en-demand-v1/out/manifest.json"
    backlog = make_repo(tmp_path, [dict(id="T1", state="done"), dict(id="T2", state="done")],
                        reviews={}, manifests={"out/manifest.json": "2026-10-28T03:00:00+08:00"})
    prov = tmp_path / "prov.csv"
    bt.run(backlog, write=False, provenance_path=prov)

    import csv
    rows = list(csv.DictReader(open(prov, encoding="utf-8-sig")))
    assert {r["status"] for r in rows} <= {"filled", "skipped", "rejected"}
    filled = [r for r in rows if r["status"] == "filled"]
    assert filled[0]["source"].endswith("manifest.json")
    assert filled[0]["evidence"]
