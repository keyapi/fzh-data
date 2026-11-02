# -*- coding: utf-8 -*-
"""OPS-METRICS (DORA-lite) 用例。

重点不是「数字跑出来」，而是**口径不许夸大**：
削掉冒充完成时间的删失值、不把无 verdict 的 review 塞进分母、不把审核等待算进 lead time、
且脚本只读（不改任务状态）。
"""

from __future__ import annotations

import hashlib
import importlib.util
import json
import sys
from datetime import datetime, timedelta, timezone
from pathlib import Path

import pytest

ROOT = Path(__file__).resolve().parents[2]
_SPEC = importlib.util.spec_from_file_location("fzh_ops_metrics", ROOT / "scripts" / "ops_metrics.py")
assert _SPEC and _SPEC.loader
ops_metrics = importlib.util.module_from_spec(_SPEC)
sys.modules[_SPEC.name] = ops_metrics
_SPEC.loader.exec_module(ops_metrics)

AS_OF = datetime(2026, 10, 28, 8, 0, tzinfo=timezone(timedelta(hours=8)))


# ------------------------------------------------------------------ 夹具

def board_payload() -> dict:
    return {"last_foreman_check": "2026-10-27T13:00:00+08:00", "tasks": [
        # 普通任务，完整时间戳：14:00 → 15:00 = 60 min
        dict(id="DEV-A", status="accepted", dispatched_at="2026-10-27T14:00:00+08:00",
             delivered_at="2026-10-27T15:00:00+08:00"),
        # 返工任务，完整时间戳：19:00 → 19:30 = 30 min
        dict(id="DEV-A-REWORK", status="accepted", dispatched_at="2026-10-27T19:00:00+08:00",
             delivered_at="2026-10-27T19:30:00+08:00"),
        # 进行中、未交付 → 删失，不能当完成
        dict(id="DEV-B", status="rework", dispatched_at="2026-10-27T20:00:00+08:00"),
        # 终态但缺 delivered_at → 缺元数据，不能当「还在跑」
        dict(id="DEV-C", status="accepted", dispatched_at="2026-10-27T21:00:00+08:00"),
        # 从未派发
        dict(id="DEV-D", status="accepted"),
        # 审核任务：18:00 → 18:10 = 10 min（算审核等待，不算 lead time）
        dict(id="DEV-A-REVIEW", status="accepted", dispatched_at="2026-10-27T18:00:00+08:00",
             delivered_at="2026-10-27T18:10:00+08:00", verdict="reject"),
        # 审核任务：18:20 → 18:25 = 5 min，accept-with-findings
        dict(id="DEV-A-REVIEW-2", status="accepted", dispatched_at="2026-10-27T18:20:00+08:00",
             delivered_at="2026-10-27T18:25:00+08:00", verdict="accept-with-findings"),
    ]}


def backlog_payload() -> dict:
    return {"updated_at": "2026-10-28T07:00:00+08:00", "tasks": [
        dict(id="T1", state="done"),
        dict(id="T2", state="review", started_at="2026-10-28T03:56:00+08:00"),
        dict(id="T3", state="running", started_at="2026-10-28T04:10:00+08:00"),
        dict(id="T4", state="blocked"),
    ]}


REVIEW_TEXTS = {
    "alpha-review-2026-10-27.md": "---\ntype: Review\ntitle: A\ndate: 2026-10-27\nverdict: reject\n---\n\n正文\n",
    "alpha-v2-review-2026-10-27.md": "---\ntype: Review\ntitle: A2\ndate: 2026-10-27\nverdict: accept\n---\n\n正文\n",
    "beta-review-2026-10-27.md": "---\ntype: Review\ndate: 2026-10-27\nverdict: accept-with-findings（1 个 major）\n---\n",
    "gamma-review-2026-10-27.md": "---\ntype: Review\ndate: 2026-10-27\nverdict: partial-accept-f5-unresolved\n---\n",
    "note-without-verdict.md": "---\ntype: Review\ndate: 2026-10-27\n---\n没有判定\n",
}


def write_inputs(tmp_path: Path) -> dict:
    board = tmp_path / "board.json"
    board.write_text(json.dumps(board_payload(), ensure_ascii=False), encoding="utf-8")
    backlog = tmp_path / "backlog.json"
    backlog.write_text(json.dumps(backlog_payload(), ensure_ascii=False), encoding="utf-8")
    reviews = tmp_path / "reviews"
    reviews.mkdir()
    for name, text in REVIEW_TEXTS.items():
        (reviews / name).write_text(text, encoding="utf-8")
    canonical = tmp_path / "canonical"
    canonical.mkdir()
    (canonical / "demand_netting.parquet").write_bytes(b"fake-parquet")
    (canonical / "identity_manifest.json").write_text(
        json.dumps({"generated_at": "2026-10-27T14:02:20+08:00"}), encoding="utf-8")
    (tmp_path / "manifest.json").write_text(
        json.dumps({"watermarks": {"last_success_run_at": "2026-10-27T12:59:35+08:00"}}),
        encoding="utf-8")
    return dict(board=board, backlog=backlog, reviews=reviews, canonical=canonical)


def run(tmp_path: Path) -> dict:
    paths = write_inputs(tmp_path)
    return ops_metrics.build(paths["backlog"], paths["board"], paths["reviews"],
                             paths["canonical"], tmp_path / "out", "2026-10-28",
                             as_of=AS_OF)


# ------------------------------------------------------------------ 判定归桶

def test_verdict_buckets_are_prefix_based_and_conservative():
    assert ops_metrics.bucket_verdict("reject") == "reject"
    assert ops_metrics.bucket_verdict("reject-for-m2-validation") == "reject"
    assert ops_metrics.bucket_verdict("accept") == "accept"
    assert ops_metrics.bucket_verdict("accept-with-findings（1 个 major）") == "accept-with-findings"
    assert ops_metrics.bucket_verdict("accept-with-restrictions") == "accept-with-findings"
    # 认不出的一律 other，不硬塞 accept/reject
    assert ops_metrics.bucket_verdict("partial-accept-f5-unresolved") == "other"
    assert ops_metrics.bucket_verdict("revise-before-adoption") == "other"
    assert ops_metrics.bucket_verdict("") == "other"


def test_verdict_rate_excludes_reviews_without_verdict(tmp_path):
    metrics = run(tmp_path)
    vr = metrics["verdict_rates"]
    assert vr["total_reviews"] == 5
    assert vr["with_verdict"] == 4          # 无 verdict 的那份不进分母
    assert vr["no_verdict"] == 1
    assert vr["counts"] == {"reject": 1, "accept-with-findings": 1, "accept": 1, "other": 1}
    assert vr["rates"]["reject"] == 25.0


# ------------------------------------------------------------------ 时长口径

def test_lead_time_excludes_review_tasks(tmp_path):
    metrics = run(tmp_path)
    lt = metrics["lead_times"]
    ids = {r["id"] for r in lt["rows"]}
    assert ids == {"DEV-A", "DEV-A-REWORK"}
    assert lt["n"] == 2
    assert lt["median_minutes"] == 45.0     # (60 + 30) / 2
    # 审核任务的 10 min 不能混进 lead time
    assert all("REVIEW" not in i for i in ids)


def test_review_wait_only_counts_review_tasks(tmp_path):
    metrics = run(tmp_path)
    rw = metrics["review_waits"]
    assert {r["id"] for r in rw["rows"]} == {"DEV-A-REVIEW", "DEV-A-REVIEW-2"}
    assert rw["n"] == 2
    assert rw["median_minutes"] == 7.5      # (10 + 5) / 2


def test_censored_vs_missing_timestamp_are_not_conflated(tmp_path):
    """进行中 → 删失下限；终态缺时间戳 → 不可算。两者都不能当完成时间。"""
    metrics = run(tmp_path)
    lt = metrics["lead_times"]
    censored = {c["id"] for c in lt["censored"]}
    missing = {m["id"] for m in lt["missing_timestamp"]}
    assert censored == {"DEV-B"}
    assert missing == {"DEV-C"}
    assert censored.isdisjoint(missing)
    # 终态任务即使到冻结时刻有间隔，也不能算成「已耗时」
    assert all(c["id"] != "DEV-C" for c in lt["censored"])
    assert lt["unmeasurable"] == 2
    assert lt["no_dispatch"] == 1


def test_rework_counts_reject_then_next_verdict_only(tmp_path):
    metrics = run(tmp_path)
    rw = metrics["rework"]
    # DEV-A-REVIEW(reject@18:10) → DEV-A-REVIEW-2(submit 18:20, verdict 18:25) = 1 轮
    assert rw["total_rounds"] == 1
    cycle = rw["cycles"][0]
    assert cycle["after"] == "DEV-A-REVIEW" and cycle["until"] == "DEV-A-REVIEW-2"
    # 返工耗时只算 reject → 下轮提交（10 min），不与审核等待重复计数
    assert cycle["rework_minutes"] == pytest.approx(10.0)
    # 到下轮 verdict 的合计（10 返工 + 5 复审）
    assert cycle["minutes"] == pytest.approx(15.0)
    assert cycle["rework_includes_review"] is False
    assert rw["median_minutes"] == pytest.approx(10.0)


def test_rework_time_falls_back_and_says_so_when_next_submit_missing(tmp_path):
    """缺下一轮 dispatched_at 时只能退回「到下轮 verdict」，必须打标记，不能假装纯返工。"""
    board = {"tasks": [
        dict(id="X-REVIEW", status="accepted", dispatched_at="2026-10-27T10:00:00+08:00",
             delivered_at="2026-10-27T10:10:00+08:00", verdict="reject"),
        dict(id="X-REVIEW-2", status="accepted",
             delivered_at="2026-10-27T10:40:00+08:00", verdict="accept"),
    ]}
    for t in board["tasks"]:
        t.setdefault("dispatched_at", None)
        t.update(_dispatched=ops_metrics._parse(t.get("dispatched_at")),
                 _delivered=ops_metrics._parse(t.get("delivered_at")),
                 _family="X", _is_review=True,
                 _verdict_bucket=ops_metrics.bucket_verdict(t["verdict"]))
    rw = ops_metrics.rework(board)
    assert rw["total_rounds"] == 1
    cycle = rw["cycles"][0]
    assert cycle["next_submitted_at"] is None
    assert cycle["rework_includes_review"] is True
    assert cycle["rework_minutes"] == pytest.approx(30.0)


def test_no_rework_round_without_a_verdict_following_reject():
    board = {"tasks": [
        dict(id="X-REVIEW", status="accepted", dispatched_at="2026-10-27T10:00:00+08:00",
             delivered_at="2026-10-27T10:10:00+08:00", verdict="reject"),
    ]}
    loaded = ops_metrics.load_board
    # 直接手工补内部字段，避免落盘
    for t in board["tasks"]:
        t.update(_dispatched=ops_metrics._parse(t["dispatched_at"]),
                 _delivered=ops_metrics._parse(t["delivered_at"]),
                 _family="X", _is_review=True,
                 _verdict_bucket=ops_metrics.bucket_verdict(t["verdict"]))
    assert loaded is not None
    assert ops_metrics.rework(board)["total_rounds"] == 0


# ------------------------------------------------------------------ 新鲜度

def test_freshness_uses_manifest_time_and_flags_missing(tmp_path):
    metrics = run(tmp_path)
    fr = metrics["freshness"]
    by_name = {r["artifact"]: r for r in fr["rows"]}
    netting = by_name["canonical/demand_netting.parquet"]
    assert netting["basis"] == "identity_manifest.json generated_at"
    assert netting["status"] == "fresh"                     # 约 0.75 天
    assert len(netting["sha256"]) == 16
    # 目录里没有这些文件 → missing，不是「新鲜」
    assert "canonical/demand_canonical.parquet" in fr["missing"]
    assert by_name["canonical/demand_canonical.parquet"]["status"] == "missing"
    watermark = by_name["en-demand-v1/manifest.json (watermark)"]
    assert watermark["basis"] == "watermarks.last_success_run_at"


def test_freshness_thresholds(tmp_path):
    canonical = tmp_path / "canonical"
    canonical.mkdir()
    old = canonical / "demand_netting.parquet"
    old.write_bytes(b"x")
    (canonical / "identity_manifest.json").write_text(
        json.dumps({"generated_at": "2026-10-10T00:00:00+08:00"}), encoding="utf-8")
    fr = ops_metrics.freshness(canonical, AS_OF)
    row = {r["artifact"]: r for r in fr["rows"]}["canonical/demand_netting.parquet"]
    assert row["status"] == "stale"                          # >7 天
    assert row["age_days"] > 7


# ------------------------------------------------------------------ 只读 + 产物

def test_script_does_not_modify_backlog_or_board(tmp_path):
    paths = write_inputs(tmp_path)
    before = {p: hashlib.sha256(Path(p).read_bytes()).hexdigest()
              for p in (paths["backlog"], paths["board"])}
    ops_metrics.build(paths["backlog"], paths["board"], paths["reviews"],
                      paths["canonical"], tmp_path / "out", "2026-10-28", as_of=AS_OF)
    after = {p: hashlib.sha256(Path(p).read_bytes()).hexdigest() for p in before}
    assert before == after


def test_outputs_are_one_page_md_plus_long_csv(tmp_path):
    metrics = run(tmp_path)
    out = tmp_path / "out"
    md = out / "ops-metrics-2026-10-28.md"
    csv_path = out / "ops-metrics-2026-10-28.csv"
    assert md.exists() and csv_path.exists()

    import csv as csvmod
    with open(csv_path, encoding="utf-8-sig", newline="") as fh:
        rows = list(csvmod.DictReader(fh))
    assert set(rows[0]) == {"metric", "item", "value", "unit", "evidence"}
    metrics_seen = {r["metric"] for r in rows}
    assert {"lead_time", "verdict_rate", "rework", "review_wait", "freshness"} <= metrics_seen
    assert metrics["csv_rows"] == len(rows)


def test_report_refuses_vanity_metrics_and_states_boundaries(tmp_path):
    run(tmp_path)
    text = (tmp_path / "out" / "ops-metrics-2026-10-28.md").read_text(encoding="utf-8")
    # 必须明确声明不用在线时长/提交数当进展
    assert "不用在线时长" in text or "不用的指标" in text
    assert "提交（commit）数" in text
    # 边界必须写清：backlog 时间戳覆盖不全 → 不可算，不估
    assert "`finished_at` 0 个" in text
    assert "不可算" in text
    assert "只读" in text


def test_review_families_group_versions_and_rereviews(tmp_path):
    metrics = run(tmp_path)
    fams = {f["family"]: f for f in metrics["review_families"]["families"]}
    # alpha-review / alpha-v2-review 归到同一族
    assert any(k.startswith("alpha") for k in fams)
    alpha = [f for k, f in fams.items() if k.startswith("alpha")][0]
    assert alpha["rounds"] == 2
    assert alpha["verdicts"] == ["reject", "accept"]
