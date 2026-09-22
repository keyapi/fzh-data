#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""启动时的两件 housekeeping：收回被杀掉的 running，删掉过期成品。

queued 不动。那条任务还在 Redis 里，worker 拉起来之后会继续跑。
只把 status 仍是 running 的行标失败，避免盖掉已经成功的结果。
"""

from __future__ import annotations

import logging
from datetime import datetime, timedelta

from web import storage
from web.repository import Repository

log = logging.getLogger("pb_orders.housekeeping")


def recover_running(repo: Repository) -> int:
    n = repo.recover_interrupted()
    if n:
        log.warning("把 %d 个仍处于 running 的任务标为中断", n)
    return n


def purge_expired(settings, repo: Repository) -> int:
    """删除完成时间早于保留期的任务，以及不再被引用的产物文件。"""
    days = settings.retention_days
    if days < 0:
        return 0
    cutoff = (datetime.now().astimezone() - timedelta(days=days)).isoformat(timespec="seconds")
    removed = 0
    for job_id in repo.expired_finished_ids(cutoff):
        rel_paths = [a["rel_path"] for a in repo.list_artifacts(job_id)]
        if not repo.delete_finished_job(job_id):
            continue
        storage.remove_job_dirs(settings.inputs_dir, settings.work_dir, job_id)
        for rel in rel_paths:
            if repo.rel_path_referenced(rel):
                continue
            try:
                storage.resolve_artifact_path(settings.artifacts_dir, rel).unlink(missing_ok=True)
            except storage.StoredPathError:
                continue
        removed += 1
    if removed:
        log.info("清理了 %d 个超过 %d 天的已完成任务", removed, days)
    return removed
