#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""任务与产物的元数据存储（SQLite，标准库实现）。

用 sqlite3 而不是 ORM：这里的结构就是两张表、几个状态转换，引入 SQLAlchemy
只会多一层需要维护的映射。每次调用开一条连接（SQLite 开销极低），配 WAL
以允许 Web 与 worker 并发读写。

状态机：uploaded -> queued -> running -> succeeded / failed
"""

from __future__ import annotations

import json
import sqlite3
import uuid
from datetime import datetime
from pathlib import Path

SCHEMA = """
CREATE TABLE IF NOT EXISTS jobs (
    id               TEXT PRIMARY KEY,
    status           TEXT NOT NULL,
    created_by       TEXT NOT NULL DEFAULT '',
    created_at       TEXT NOT NULL,
    started_at       TEXT,
    finished_at      TEXT,
    no_stock         TEXT NOT NULL DEFAULT '',
    no_stock_note    TEXT,
    validate_only    INTEGER NOT NULL DEFAULT 0,
    allow_unmatched  INTEGER NOT NULL DEFAULT 0,
    input_packslip   TEXT NOT NULL DEFAULT '',
    input_order      TEXT NOT NULL DEFAULT '',
    progress_step    TEXT,
    progress_message TEXT,
    report_json      TEXT,
    error_json       TEXT,
    worker_job_id    TEXT,
    pipeline_version TEXT NOT NULL DEFAULT '',
    source_job_id    TEXT
);
CREATE INDEX IF NOT EXISTS idx_jobs_status ON jobs(status);
CREATE INDEX IF NOT EXISTS idx_jobs_created ON jobs(created_at DESC);

CREATE TABLE IF NOT EXISTS artifacts (
    id            TEXT PRIMARY KEY,
    job_id        TEXT NOT NULL,
    kind          TEXT NOT NULL,
    original_name TEXT NOT NULL,
    download_name TEXT NOT NULL,
    rel_path      TEXT NOT NULL,
    content_hash  TEXT NOT NULL,
    size_bytes    INTEGER NOT NULL,
    mime_type     TEXT NOT NULL,
    created_at    TEXT NOT NULL,
    FOREIGN KEY (job_id) REFERENCES jobs(id) ON DELETE CASCADE
);
CREATE INDEX IF NOT EXISTS idx_artifacts_job ON artifacts(job_id);
"""

ARTIFACT_KINDS = (
    "input_packslip", "input_order",
    "tongtool", "tongtool_no_stock", "tongtool_importable",
    "label", "back_label", "label_no_stock", "back_label_no_stock",
)

# 产物类型的中文名（页面展示用）
ARTIFACT_LABELS = {
    "input_packslip": "Packslip PDF",
    "input_order": "SPS 订单 CSV",
    "tongtool": "通途导入 xlsx",
    "tongtool_no_stock": "通途 无库存 xlsx",
    "tongtool_importable": "通途 有货 xlsx",
    "label": "标签 PDF",
    "back_label": "背贴 PDF",
    "label_no_stock": "无货 标签 PDF",
    "back_label_no_stock": "无货 背贴 PDF",
}


def now_iso() -> str:
    return datetime.now().astimezone().isoformat(timespec="seconds")


def new_id(prefix: str = "job") -> str:
    return f"{prefix}-{uuid.uuid4().hex[:12]}"


class Repository:
    def __init__(self, db_path):
        self.db_path = Path(db_path)
        self.db_path.parent.mkdir(parents=True, exist_ok=True)
        self.init_db()

    def connect(self) -> sqlite3.Connection:
        conn = sqlite3.connect(self.db_path, timeout=30)
        conn.row_factory = sqlite3.Row
        conn.execute("PRAGMA journal_mode=WAL")
        conn.execute("PRAGMA foreign_keys=ON")
        return conn

    def init_db(self) -> None:
        with self.connect() as conn:
            conn.executescript(SCHEMA)

    # ---------- jobs ----------

    def create_job(
        self,
        job_id: str,
        created_by: str,
        no_stock: str,
        no_stock_note: str | None,
        validate_only: bool,
        allow_unmatched: bool,
        input_packslip: str,
        input_order: str,
        pipeline_version: str,
        source_job_id: str | None = None,
    ) -> str:
        with self.connect() as conn:
            conn.execute(
                """INSERT INTO jobs (id, status, created_by, created_at, no_stock, no_stock_note,
                       validate_only, allow_unmatched, input_packslip, input_order,
                       progress_step, progress_message, pipeline_version, source_job_id)
                   VALUES (?, 'uploaded', ?, ?, ?, ?, ?, ?, ?, ?, 'uploaded', '已接收上传文件',
                       ?, ?)""",
                (
                    job_id, created_by, now_iso(), no_stock, no_stock_note,
                    int(validate_only), int(allow_unmatched), input_packslip, input_order,
                    pipeline_version, source_job_id,
                ),
            )
        return job_id

    def get_job(self, job_id: str) -> dict | None:
        with self.connect() as conn:
            row = conn.execute("SELECT * FROM jobs WHERE id = ?", (job_id,)).fetchone()
        return self._job_dict(row) if row else None

    def list_jobs(self, status: str | None = None, limit: int = 100) -> list[dict]:
        sql = "SELECT * FROM jobs"
        params: list = []
        if status:
            sql += " WHERE status = ?"
            params.append(status)
        sql += " ORDER BY created_at DESC, rowid DESC LIMIT ?"
        params.append(limit)
        with self.connect() as conn:
            rows = conn.execute(sql, params).fetchall()
        return [self._job_dict(r) for r in rows]

    def update_job(self, job_id: str, **fields) -> None:
        if not fields:
            return
        allowed = {
            "status", "started_at", "finished_at", "progress_step", "progress_message",
            "report_json", "error_json", "worker_job_id",
        }
        bad = set(fields) - allowed
        if bad:
            raise ValueError(f"不允许更新的字段: {sorted(bad)}")
        sets = ", ".join(f"{k} = ?" for k in fields)
        with self.connect() as conn:
            conn.execute(f"UPDATE jobs SET {sets} WHERE id = ?", (*fields.values(), job_id))

    def set_progress(self, job_id: str, step: str, message: str) -> None:
        self.update_job(job_id, progress_step=step, progress_message=message)

    def mark_queued(self, job_id: str, worker_job_id: str) -> None:
        self.update_job(
            job_id, status="queued", worker_job_id=worker_job_id,
            progress_step="queued", progress_message="已进入队列，等待处理",
        )

    def mark_running(self, job_id: str) -> None:
        self.update_job(
            job_id, status="running", started_at=now_iso(),
            progress_step="running", progress_message="开始处理",
        )

    def mark_succeeded(self, job_id: str, report: dict) -> None:
        self.update_job(
            job_id, status="succeeded", finished_at=now_iso(),
            progress_step="done", progress_message="处理完成",
            report_json=json.dumps(report, ensure_ascii=False),
        )

    def mark_failed(self, job_id: str, error: dict) -> None:
        self.update_job(
            job_id, status="failed", finished_at=now_iso(),
            progress_step="failed", progress_message=error.get("message", "处理失败"),
            error_json=json.dumps(error, ensure_ascii=False),
        )

    def recover_interrupted(self) -> int:
        """worker 启动时，只把仍是 running 的任务标为失败。

        queued 还在 Redis 里，留给新 worker 继续执行。
        条件更新避免把已经写成 succeeded 的任务盖回失败。
        """
        error = {
            "code": "worker_interrupted",
            "message": "worker 在处理中重启，任务被中断",
            "hint": "可点击「用相同输入重新处理」重新排队。",
        }
        with self.connect() as conn:
            cur = conn.execute(
                """UPDATE jobs
                   SET status = 'failed', finished_at = ?, progress_step = 'failed',
                       progress_message = ?, error_json = ?
                   WHERE status = 'running'""",
                (now_iso(), error["message"], json.dumps(error, ensure_ascii=False)),
            )
        return cur.rowcount

    def expired_finished_ids(self, cutoff_iso: str) -> list[str]:
        with self.connect() as conn:
            rows = conn.execute(
                """SELECT id FROM jobs
                   WHERE status IN ('succeeded', 'failed')
                     AND COALESCE(finished_at, created_at) < ?""",
                (cutoff_iso,),
            ).fetchall()
        return [r[0] for r in rows]

    def delete_finished_job(self, job_id: str) -> bool:
        """只删已结束的任务。产物行随外键级联删除。"""
        with self.connect() as conn:
            cur = conn.execute(
                "DELETE FROM jobs WHERE id = ? AND status IN ('succeeded', 'failed')",
                (job_id,),
            )
        return cur.rowcount == 1

    def rel_path_referenced(self, rel_path: str) -> bool:
        with self.connect() as conn:
            row = conn.execute(
                "SELECT 1 FROM artifacts WHERE rel_path = ? LIMIT 1",
                (rel_path,),
            ).fetchone()
        return row is not None

    # ---------- artifacts ----------

    def add_artifact(
        self, job_id: str, kind: str, original_name: str, download_name: str,
        rel_path: str, content_hash: str, size_bytes: int, mime_type: str,
    ) -> str:
        artifact_id = new_id("art")
        with self.connect() as conn:
            conn.execute(
                """INSERT INTO artifacts (id, job_id, kind, original_name, download_name,
                       rel_path, content_hash, size_bytes, mime_type, created_at)
                   VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?)""",
                (artifact_id, job_id, kind, original_name, download_name, rel_path,
                 content_hash, size_bytes, mime_type, now_iso()),
            )
        return artifact_id

    def list_artifacts(self, job_id: str) -> list[dict]:
        with self.connect() as conn:
            rows = conn.execute(
                "SELECT * FROM artifacts WHERE job_id = ? ORDER BY rowid", (job_id,)
            ).fetchall()
        return [dict(r) for r in rows]

    def get_artifact(self, artifact_id: str) -> dict | None:
        with self.connect() as conn:
            row = conn.execute("SELECT * FROM artifacts WHERE id = ?", (artifact_id,)).fetchone()
        return dict(row) if row else None

    # ---------- helpers ----------

    @staticmethod
    def _job_dict(row: sqlite3.Row) -> dict:
        job = dict(row)
        job["report"] = json.loads(job["report_json"]) if job["report_json"] else None
        job["error"] = json.loads(job["error_json"]) if job["error_json"] else None
        job["validate_only"] = bool(job["validate_only"])
        job["allow_unmatched"] = bool(job["allow_unmatched"])
        job["no_stock_list"] = [s for s in (job["no_stock"] or "").split(",") if s.strip()]
        return job
