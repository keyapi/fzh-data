#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""任务/产物元数据存储：状态转换、恢复中断任务、产物登记。"""

from __future__ import annotations

import pytest

from web.repository import Repository, new_id


@pytest.fixture
def repo(pb_env):
    return Repository(pb_env.runtime / "jobs.sqlite")


def _create(repo, job_id="job-test", **kw):
    kwargs = dict(
        job_id=job_id, created_by="tester", no_stock="", no_stock_note=None,
        validate_only=False, allow_unmatched=False, input_packslip="a.pdf",
        input_order="b.csv", pipeline_version="v1",
    )
    kwargs.update(kw)
    return repo.create_job(**kwargs)


def test_create_and_read_job(repo):
    _create(repo, no_stock="SKU-A,SKU-B")
    job = repo.get_job("job-test")
    assert job["status"] == "uploaded"
    assert job["created_by"] == "tester"
    assert job["no_stock_list"] == ["SKU-A", "SKU-B"]
    assert job["report"] is None and job["error"] is None


def test_status_transitions(repo):
    _create(repo)
    repo.mark_queued("job-test", "rq-1")
    assert repo.get_job("job-test")["status"] == "queued"
    assert repo.get_job("job-test")["worker_job_id"] == "rq-1"

    repo.mark_running("job-test")
    assert repo.get_job("job-test")["status"] == "running"
    assert repo.get_job("job-test")["started_at"]

    repo.mark_succeeded("job-test", {"pdf": {"pages": 3}})
    job = repo.get_job("job-test")
    assert job["status"] == "succeeded"
    assert job["report"]["pdf"]["pages"] == 3
    assert job["finished_at"]


def test_mark_failed_keeps_readable_error(repo):
    _create(repo)
    repo.mark_failed("job-test", {"code": "one_to_one_failed", "message": "页数不等", "hint": "检查导出"})
    job = repo.get_job("job-test")
    assert job["status"] == "failed"
    assert job["error"]["code"] == "one_to_one_failed"
    assert job["progress_message"] == "页数不等"


def test_update_rejects_unknown_field(repo):
    _create(repo)
    with pytest.raises(ValueError):
        repo.update_job("job-test", drop_table="x")


def test_recover_interrupted_only_marks_running(repo):
    _create(repo, job_id="job-a")
    repo.mark_queued("job-a", "rq-a")
    _create(repo, job_id="job-b")
    repo.mark_running("job-b")
    _create(repo, job_id="job-c")
    repo.mark_succeeded("job-c", {})

    assert repo.recover_interrupted() == 1
    assert repo.get_job("job-a")["status"] == "queued"
    assert repo.get_job("job-b")["status"] == "failed"
    assert repo.get_job("job-b")["error"]["code"] == "worker_interrupted"
    assert repo.get_job("job-c")["status"] == "succeeded"


def test_recover_interrupted_does_not_stop_at_one_page(repo):
    for i in range(101):
        job_id = f"run-{i:03d}"
        _create(repo, job_id=job_id)
        repo.mark_running(job_id)
    assert repo.recover_interrupted() == 101


def test_queued_jobs_lists_only_queued(repo):
    _create(repo, job_id="job-q")
    repo.mark_queued("job-q", "rq-q")
    _create(repo, job_id="job-r")
    repo.mark_running("job-r")
    _create(repo, job_id="job-s")
    repo.mark_succeeded("job-s", {})

    assert repo.queued_jobs() == [{"id": "job-q", "worker_job_id": "rq-q"}]


def test_reconcile_queued_marks_only_jobs_missing_from_queue(repo):
    from web import housekeeping

    _create(repo, job_id="still-there")
    repo.mark_queued("still-there", "rq-live")
    _create(repo, job_id="lost")
    repo.mark_queued("lost", "rq-gone")
    _create(repo, job_id="no-worker-id")
    repo.mark_queued("no-worker-id", "")
    _create(repo, job_id="running")
    repo.mark_running("running")

    alive = {"rq-live"}
    assert housekeeping.reconcile_queued(repo, lambda jid: jid in alive) == 2

    assert repo.get_job("still-there")["status"] == "queued"
    assert repo.get_job("lost")["status"] == "failed"
    assert repo.get_job("lost")["error"]["code"] == "queue_lost"
    assert repo.get_job("no-worker-id")["status"] == "failed"
    assert repo.get_job("running")["status"] == "running"


def test_queue_watch_marks_lost_jobs_while_worker_stays_up(repo):
    """FLUSHALL 不断开连接：worker 不退出，必须靠定期对账，不能等下次启动。"""
    import time
    from web import housekeeping

    _create(repo, job_id="lost")
    repo.mark_queued("lost", "rq-gone")
    _create(repo, job_id="keep")
    repo.mark_queued("keep", "rq-live")
    alive = {"rq-live"}
    stop = housekeeping.start_queue_watch(repo, lambda jid: jid in alive, 0.05)
    deadline = time.time() + 3
    while time.time() < deadline and repo.get_job("lost")["status"] != "failed":
        time.sleep(0.05)
    stop.set()
    assert repo.get_job("lost")["status"] == "failed"
    assert repo.get_job("lost")["error"]["code"] == "queue_lost"
    assert repo.get_job("keep")["status"] == "queued"


def test_queue_watch_off_when_interval_is_zero(repo):
    from web import housekeeping

    _create(repo, job_id="lost")
    repo.mark_queued("lost", "rq-gone")
    stop = housekeeping.start_queue_watch(repo, lambda jid: False, 0)
    stop.set()
    assert repo.get_job("lost")["status"] == "queued"


def test_purge_expired_drops_old_finished_jobs_only(repo, pb_env):
    from web import housekeeping
    from web.config import get_settings

    settings = get_settings()
    _create(repo, job_id="old")
    repo.mark_succeeded("old", {})
    repo.update_job("old", finished_at="2000-01-01T00:00:00+00:00")
    old_input = settings.inputs_dir / "old"
    old_input.mkdir(parents=True)
    (old_input / "packslip.pdf").write_bytes(b"pdf")

    shared_dir = settings.artifacts_dir / "ab"
    shared_dir.mkdir(parents=True)
    shared = shared_dir / "abcdef0123456789.pdf"
    shared.write_bytes(b"same")
    only = shared_dir / "ffffffffffffffff.pdf"
    only.write_bytes(b"gone")
    repo.add_artifact(
        "old", "label", "a.pdf", "a.pdf", "ab/abcdef0123456789.pdf", "abc", 4, "application/pdf"
    )
    repo.add_artifact(
        "old", "back_label", "b.pdf", "b.pdf", "ab/ffffffffffffffff.pdf", "fff", 4, "application/pdf"
    )

    _create(repo, job_id="new")
    repo.mark_succeeded("new", {})
    repo.add_artifact(
        "new", "label", "a.pdf", "a.pdf", "ab/abcdef0123456789.pdf", "abc", 4, "application/pdf"
    )
    _create(repo, job_id="live")
    repo.mark_running("live")

    assert housekeeping.purge_expired(settings, repo) == 1
    assert repo.get_job("old") is None
    assert repo.get_job("new")["status"] == "succeeded"
    assert repo.get_job("live")["status"] == "running"
    assert not old_input.exists()
    assert shared.is_file()
    assert not only.exists()


def test_list_jobs_filters_and_orders(repo):
    for i in range(3):
        _create(repo, job_id=f"job-{i}")
    repo.mark_failed("job-1", {"code": "x", "message": "y", "hint": ""})
    assert len(repo.list_jobs()) == 3
    assert [j["id"] for j in repo.list_jobs(status="failed")] == ["job-1"]


def test_artifacts_are_listed_per_job(repo):
    _create(repo, job_id="job-a")
    _create(repo, job_id="job-b")
    repo.add_artifact("job-a", "label", "l.pdf", "09.21 label.pdf", "ab/hash.pdf", "abc123", 10, "application/pdf")
    repo.add_artifact("job-b", "label", "l.pdf", "09.21 label.pdf", "ab/hash.pdf", "abc123", 10, "application/pdf")

    arts = repo.list_artifacts("job-a")
    assert len(arts) == 1
    assert arts[0]["download_name"] == "09.21 label.pdf"
    assert repo.get_artifact(arts[0]["id"])["kind"] == "label"
    assert repo.get_artifact("nope") is None


def test_new_id_is_filename_safe(repo):
    job_id = new_id("job")
    assert job_id.startswith("job-")
    assert job_id.replace("-", "").isalnum()
    assert len(job_id) < 40
