#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""RQ worker：把一个 job 跑完，写进度、发布产物、记录结果。

worker 只接收 job id，其它信息（输入路径、选项）都从数据库读。
这样 Web 与 worker 之间没有隐式的内存状态，重启也不会丢任务。

普通任务一律 `cache_only=True`：出件过程绝不访问 Google，SKU 名称只读本地缓存。
"""

from __future__ import annotations

import shutil
import sys
import traceback
from pathlib import Path

_PB_DIR = Path(__file__).resolve().parent.parent
if str(_PB_DIR) not in sys.path:
    sys.path.insert(0, str(_PB_DIR))

import service  # noqa: E402
import stock_precheck  # noqa: E402
from web import housekeeping  # noqa: E402
from web import storage  # noqa: E402
from web.config import get_settings  # noqa: E402
from web.repository import Repository  # noqa: E402

_CACHE_HINT = (
    "出件只读本地 SKU 名称缓存。请管理员先把 us_sku_name_cache.csv "
    "放到数据目录（见 README 的「首次准备」）。"
)


def _friendly_error(exc: Exception) -> dict:
    """把异常翻译成面向用户的失败报告，不泄露服务器路径与堆栈。"""
    if isinstance(exc, service.PBJobError):
        return exc.to_dict()
    if isinstance(exc, stock_precheck.StockCheckError):
        return exc.to_dict()
    if isinstance(exc, FileNotFoundError):
        return {"code": "cache_missing", "message": "缺少本地 SKU 名称缓存", "hint": _CACHE_HINT}
    if isinstance(exc, (ValueError, KeyError)):
        return {"code": "data_error", "message": f"输入数据有问题：{exc}", "hint": "请核对上传的 PDF 与 CSV 是否属于同一批。"}
    return {
        "code": "internal_error",
        "message": "处理时发生内部错误",
        "hint": "已记录日志，请把任务编号反馈给维护者。",
    }


def _publish_artifacts(repo, settings, job_id: str, specs) -> None:
    """把产物按内容哈希发布到 artifacts 目录，再登记到数据库。"""
    for spec in specs:
        rel_path, size, content_hash = storage.publish_artifact(
            spec.path, settings.artifacts_dir, spec.download_name
        )
        repo.add_artifact(
            job_id=job_id, kind=spec.kind, original_name=spec.path.name,
            download_name=spec.download_name, rel_path=rel_path,
            content_hash=content_hash, size_bytes=size, mime_type=spec.mime_type,
        )


def _run_fulfillment(repo, job, settings, job_id, in_dir, work_dir):
    """出件：Packslip PDF + checked CSV -> 通途 xlsx + 标签/背贴 PDF。"""
    options = service.JobOptions(
        no_stock=job["no_stock_list"],
        no_stock_note=job["no_stock_note"],
        allow_unmatched=job["allow_unmatched"],
        cache_only=True,  # 普通任务绝不联网
        validate_only=job["validate_only"],
        sku_cache_path=settings.sku_cache_path,
        nltk_dir=settings.nltk_dir,
        # 磁盘名固定是 order.csv，拿它命名产物会变成 `..._order_on_...`；
        # 用页面上的原始文件名词干，产物才对得上批次。
        csv_stem=Path(job["input_order"] or "").stem,
    )
    result = service.run_job(
        # 磁盘名固定（见 storage 约定）。jobs.input_packslip/input_order
        # 只存用户原始文件名，仅用于页面展示，不能当路径用。
        in_dir / storage.PACKSLIP_NAME,
        in_dir / storage.ORDER_NAME,
        options,
        output_dir=work_dir,
        progress=lambda step, msg: repo.set_progress(job_id, step, msg),
    )
    return result.report, result.artifacts


def _run_stock_check(repo, job, settings, job_id, in_dir, work_dir):
    """库存预检：SPS 原始 New 订单 CSV -> checked CSV + 操作 Excel。"""
    result = stock_precheck.run_stock_check(
        in_dir / storage.ORDER_NAME,
        job["no_stock_list"],
        work_dir,
        progress=lambda step, msg: repo.set_progress(job_id, step, msg),
        name_stem=Path(job["input_order"] or "").stem,
    )
    specs = [
        service.ArtifactSpec(
            "checked_order", result.checked_csv, result.checked_csv.name, stock_precheck.MIME_CSV
        ),
        service.ArtifactSpec(
            "stock_operations", result.operations_xlsx, result.operations_xlsx.name,
            stock_precheck.MIME_XLSX,
        ),
    ]
    return result.report, specs


# 任务类型 -> 执行器。两种流程共用同一套「跑完发布产物」的外壳。
_RUNNERS = {
    "fulfillment": _run_fulfillment,
    "stock_check": _run_stock_check,
}


def run_job(job_id: str) -> dict:
    settings = get_settings()
    settings.ensure_dirs()
    repo = Repository(settings.db_path)
    job = repo.get_job(job_id)
    if job is None:
        return {"job_id": job_id, "status": "missing"}

    if job["status"] in ("succeeded", "failed"):
        return {"job_id": job_id, "status": job["status"], "skipped": True}

    job_type = job["job_type"] or "fulfillment"
    runner = _RUNNERS.get(job_type)
    if runner is None:
        repo.mark_failed(
            job_id,
            {"code": "unknown_job_type", "message": f"未知的任务类型：{job_type}", "hint": "请联系维护者。"},
        )
        return {"job_id": job_id, "status": "failed", "error": "unknown_job_type"}

    repo.mark_running(job_id)
    in_dir = settings.inputs_dir / job_id
    work_dir = settings.work_dir / job_id
    if work_dir.exists():
        shutil.rmtree(work_dir, ignore_errors=True)
    work_dir.mkdir(parents=True, exist_ok=True)

    try:
        report, specs = runner(repo, job, settings, job_id, in_dir, work_dir)
        report["pipeline_version"] = settings.pipeline_version
        _publish_artifacts(repo, settings, job_id, specs)
        repo.mark_succeeded(job_id, report)
        return {"job_id": job_id, "status": "succeeded"}
    except Exception as exc:  # noqa: BLE001 - 任何失败都要落库，页面才看得到原因
        repo.mark_failed(job_id, _friendly_error(exc))
        traceback.print_exc()
        return {"job_id": job_id, "status": "failed", "error": type(exc).__name__}
    finally:
        # 只清临时件；inputs 留着供「用相同输入重新处理」
        storage.remove_work_dir(settings.work_dir, job_id)


def main() -> None:
    """worker 容器入口：`python -m web.tasks`。"""
    import os

    from redis import Redis
    from rq import Queue, SimpleWorker, Worker
    from rq.exceptions import NoSuchJobError
    from rq.job import Job

    settings = get_settings()
    settings.ensure_dirs()
    repo = Repository(settings.db_path)
    # 只收回 running。queued 还在 Redis 里，下面的 work() 会继续跑。
    housekeeping.recover_running(repo)
    try:
        housekeeping.purge_expired(settings, repo)
    except Exception:  # noqa: BLE001 - 清理失败不应挡住 worker
        traceback.print_exc()

    conn = Redis.from_url(settings.redis_url)
    queue = Queue(settings.queue_name, connection=conn)

    def _still_queued(worker_job_id: str) -> bool:
        try:
            Job.fetch(worker_job_id, connection=conn)
            return True
        except NoSuchJobError:
            return False

    try:
        # Redis 若丢过队列，数据库里的 queued 就没人执行了，先标失败。
        housekeeping.reconcile_queued(repo, _still_queued)
    except Exception:  # noqa: BLE001 - 对账失败不应挡住 worker
        traceback.print_exc()

    housekeeping.start_queue_watch(repo, _still_queued, settings.queue_watch_seconds)

    # Windows 没有 fork()，RQ 的常规 Worker 会起不来；本机开发用 SimpleWorker，
    # 容器（Linux）仍用可并行 fork 的常规 Worker。
    worker_cls = SimpleWorker if os.name == "nt" else Worker
    worker_cls([queue], connection=conn).work(with_scheduler=False)


if __name__ == "__main__":
    main()
