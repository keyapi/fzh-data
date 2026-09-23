#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""worker 按任务类型分发库存预检与履约出件。"""

from __future__ import annotations

import shutil

from web import storage, tasks
from web.config import get_settings
from web.repository import Repository


def test_worker_runs_stock_check_and_publishes_outputs(pb_env):
    settings = get_settings()
    repo = Repository(settings.db_path)
    job_id = "stock-check-1"
    input_dir = settings.inputs_dir / job_id
    input_dir.mkdir(parents=True)
    shutil.copy2(pb_env.csv, input_dir / storage.ORDER_NAME)
    repo.create_job(
        job_id=job_id,
        job_type="stock_check",
        created_by="tester",
        no_stock="STYLE-B",
        no_stock_note=None,
        validate_only=False,
        allow_unmatched=False,
        input_packslip="",
        input_order="raw-orders.csv",
        pipeline_version="test-version",
    )
    repo.mark_queued(job_id, "rq-stock")

    assert tasks.run_job(job_id)["status"] == "succeeded"
    job = repo.get_job(job_id)
    assert job["report"]["details"]["out_of_stock"] == 1
    assert job["report"]["no_stock_snapshot"] == ["STYLE-B"]

    artifacts = repo.list_artifacts(job_id)
    assert {artifact["kind"] for artifact in artifacts} == {
        "checked_order",
        "stock_operations",
    }
    for artifact in artifacts:
        assert storage.resolve_artifact_path(settings.artifacts_dir, artifact["rel_path"]).is_file()


def test_worker_stock_check_failure_has_no_artifacts(pb_env):
    settings = get_settings()
    repo = Repository(settings.db_path)
    job_id = "stock-check-bad"
    input_dir = settings.inputs_dir / job_id
    input_dir.mkdir(parents=True)
    (input_dir / storage.ORDER_NAME).write_text("wrong,column\n1,2\n", encoding="utf-8")
    repo.create_job(
        job_id=job_id,
        job_type="stock_check",
        created_by="tester",
        no_stock="",
        no_stock_note=None,
        validate_only=False,
        allow_unmatched=False,
        input_packslip="",
        input_order="bad.csv",
        pipeline_version="test-version",
    )
    repo.mark_queued(job_id, "rq-stock-bad")

    assert tasks.run_job(job_id)["status"] == "failed"
    job = repo.get_job(job_id)
    assert job["error"]["code"] == "missing_columns"
    assert repo.list_artifacts(job_id) == []
