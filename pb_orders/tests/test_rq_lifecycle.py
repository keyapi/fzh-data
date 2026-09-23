#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""用真 Redis 验证 RQ 2.12.0 的真实断连行为（不是只读源码里的 TimeoutError 分支）。

实测结论（见本文件用例）：
- Redis 重启触发的是 `ConnectionError`。`dequeue_job_and_maintain_ttl` 会指数退避重连，
  **worker 进程不退出**，因此 compose 的 `restart: unless-stopped` 不会被触发。
- `FLUSHALL` 同样不断开 worker。
- 两种情况都靠 `housekeeping.start_queue_watch` 把库里仍 `queued`、Redis 已无 job 的任务标失败。

默认跳过。要跑：先有 `redis:7-alpine` 镜像，再：

    $env:PB_ORDERS_RQ_DOCKER='1'; uv run pytest pb_orders/tests/test_rq_lifecycle.py -q
"""

from __future__ import annotations

import os
import shutil
import subprocess
import sys
import time
from pathlib import Path

import pytest

pytestmark = pytest.mark.skipif(
    os.environ.get("PB_ORDERS_RQ_DOCKER") != "1",
    reason="set PB_ORDERS_RQ_DOCKER=1 to run Redis/RQ lifecycle checks",
)

PORT = "16379"
REDIS_URL = f"redis://127.0.0.1:{PORT}/0"
NAME = "pb-rq-probe"
PB_DIR = Path(__file__).resolve().parent.parent


def _docker(*args: str) -> subprocess.CompletedProcess:
    return subprocess.run(
        ["docker", *args], capture_output=True, text=True, timeout=90
    )


def _wait_pong(seconds: float = 20) -> bool:
    deadline = time.time() + seconds
    while time.time() < deadline:
        ping = _docker("exec", NAME, "redis-cli", "ping")
        if ping.returncode == 0 and "PONG" in (ping.stdout or ""):
            return True
        time.sleep(0.3)
    return False


@pytest.fixture(scope="module")
def redis_url():
    if shutil.which("docker") is None:
        pytest.skip("docker not on PATH")
    _docker("rm", "-f", NAME)
    started = _docker(
        "run", "-d", "--name", NAME, "-p", f"{PORT}:6379",
        "redis:7-alpine",
        "redis-server", "--save", "", "--appendonly", "no",
    )
    if started.returncode != 0:
        pytest.skip(f"docker run failed: {started.stderr}")
    if not _wait_pong():
        _docker("rm", "-f", NAME)
        pytest.skip("redis never became ready")
    yield REDIS_URL
    _docker("rm", "-f", NAME)


def _worker_cmd(url: str) -> list[str]:
    return [
        sys.executable, "-c",
        "import logging; logging.basicConfig(level=logging.INFO);"
        "from redis import Redis; from rq import Queue, SimpleWorker;"
        f"c=Redis.from_url({url!r}); q=Queue('probe', connection=c);"
        "SimpleWorker([q], connection=c).work(with_scheduler=False)",
    ]


def _start_worker(url: str, log: Path) -> subprocess.Popen:
    env = {**os.environ, "PYTHONUNBUFFERED": "1"}
    proc = subprocess.Popen(
        _worker_cmd(url),
        cwd=str(PB_DIR),
        stdout=log.open("w", encoding="utf-8"),
        stderr=subprocess.STDOUT,
        env=env,
    )
    time.sleep(1.5)
    assert proc.poll() is None, log.read_text(encoding="utf-8", errors="replace")
    return proc


def test_rq_worker_reconnects_instead_of_quitting(redis_url, tmp_path):
    """Redis 重启：worker 打 retrying、进程还在。TimeoutError/quitting 那条路径没走到。"""
    log = tmp_path / "worker.log"
    proc = _start_worker(redis_url, log)
    restart = _docker("restart", NAME)
    assert restart.returncode == 0, restart.stderr
    assert _wait_pong(20)
    time.sleep(3)
    text = log.read_text(encoding="utf-8", errors="replace")
    still = proc.poll()
    if still is not None:
        pytest.fail(f"worker exited after redis restart (code={still}):\n{text}")
    assert "retrying in" in text
    assert "quitting" not in text.lower()
    proc.terminate()
    proc.wait(timeout=8)


def test_lost_queue_job_is_marked_failed_while_worker_stays(redis_url, tmp_path, pb_env):
    """FLUSHALL 后 worker 不退；定期对账把 SQLite 里仍 queued 的任务标失败。"""
    from redis import Redis
    from rq import Queue
    from rq.exceptions import NoSuchJobError
    from rq.job import Job

    from web import housekeeping
    from web.repository import Repository

    log = tmp_path / "flush.log"
    proc = _start_worker(redis_url, log)

    conn = Redis.from_url(redis_url)
    rq_job = Queue("other", connection=conn).enqueue("builtins.id", 1, job_timeout=60)
    repo = Repository(pb_env.runtime / "jobs.sqlite")
    repo.create_job(
        job_id="job-lost", created_by="probe", no_stock="", no_stock_note=None,
        validate_only=False, allow_unmatched=False, input_packslip="a.pdf",
        input_order="b.csv", pipeline_version="v1",
    )
    repo.mark_queued("job-lost", rq_job.id)

    flush = _docker("exec", NAME, "redis-cli", "FLUSHALL")
    assert flush.returncode == 0, flush.stderr
    time.sleep(1)
    assert proc.poll() is None, "FLUSHALL must not kill the worker"

    def still_queued(worker_job_id: str) -> bool:
        try:
            Job.fetch(worker_job_id, connection=Redis.from_url(redis_url))
            return True
        except NoSuchJobError:
            return False

    stop = housekeeping.start_queue_watch(repo, still_queued, 0.2)
    deadline = time.time() + 5
    while time.time() < deadline and repo.get_job("job-lost")["status"] != "failed":
        time.sleep(0.1)
    stop.set()
    assert repo.get_job("job-lost")["status"] == "failed"
    assert repo.get_job("job-lost")["error"]["code"] == "queue_lost"
    assert proc.poll() is None
    proc.terminate()
    proc.wait(timeout=8)
