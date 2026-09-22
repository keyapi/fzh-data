#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""启动时的三件 housekeeping：收回被杀掉的 running、捡回丢掉的队列任务、删掉过期成品。

queued 默认不动。那条任务还在 Redis 里，worker 拉起来之后会继续跑。
只把 status 仍是 running 的行标失败，避免盖掉已经成功的结果。
但 Redis 也可能把队列整个丢掉（快照间隔内重启、flush、清库），
那时数据库里的 queued 就再也没人管了 —— 由 `reconcile_queued` 兜住。
"""

from __future__ import annotations

import logging
from datetime import datetime, timedelta
from typing import Callable

from web import storage
from web.repository import Repository

log = logging.getLogger("pb_orders.housekeeping")


def recover_running(repo: Repository) -> int:
    n = repo.recover_interrupted()
    if n:
        log.warning("把 %d 个仍处于 running 的任务标为中断", n)
    return n


def reconcile_queued(repo: Repository, is_still_queued: Callable[[str], bool]) -> int:
    """把「数据库里还在排队、Redis 里已经没了」的任务标为失败。

    `is_still_queued` 由调用方提供（worker 用 rq 查，测试传简单函数）。
    查不到说明既没在排队也没在执行，不标失败就会永远停在「处理中」。
    输入文件保留，所以标失败之后仍可「用相同输入重新处理」。
    """
    stranded = [
        j["id"]
        for j in repo.queued_jobs()
        if not j["worker_job_id"] or not is_still_queued(j["worker_job_id"])
    ]
    for job_id in stranded:
        repo.mark_failed(job_id, {
            "code": "queue_lost",
            "message": "任务在队列中丢失（Redis 未持久化或被清空）",
            "hint": "可点击「用相同输入重新处理」重新排队。",
        })
    if stranded:
        log.warning("队列中已不存在 %d 个仍标记为排队中的任务，已标为失败", len(stranded))
    return len(stranded)


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
