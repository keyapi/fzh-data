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


def test_recover_interrupted_marks_stuck_jobs_failed(repo):
    _create(repo, job_id="job-a")
    repo.mark_queued("job-a", "rq-a")
    _create(repo, job_id="job-b")
    repo.mark_running("job-b")
    _create(repo, job_id="job-c")
    repo.mark_succeeded("job-c", {})

    assert repo.recover_interrupted() == 2
    assert repo.get_job("job-a")["status"] == "failed"
    assert repo.get_job("job-a")["error"]["code"] == "worker_interrupted"
    assert repo.get_job("job-b")["status"] == "failed"
    assert repo.get_job("job-c")["status"] == "succeeded"


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
