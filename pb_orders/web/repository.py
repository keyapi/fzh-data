#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""任务与产物的元数据存储（SQLite，标准库实现）。

用 sqlite3 而不是 ORM：这里的结构就是两张表、几个状态转换，引入 SQLAlchemy
只会多一层需要维护的映射。每次调用开一条连接（SQLite 开销极低），配 WAL
以允许 Web 与 worker 并发读写。

状态机：uploaded -> queued -> running -> succeeded / failed
"""

from __future__ import annotations

import hashlib
import json
import logging
import secrets
import sqlite3
import uuid
from datetime import datetime, timedelta
from pathlib import Path

log = logging.getLogger("pb_orders.web")

SCHEMA = """
CREATE TABLE IF NOT EXISTS jobs (
    id               TEXT PRIMARY KEY,
    job_type         TEXT NOT NULL DEFAULT 'fulfillment',
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

CREATE TABLE IF NOT EXISTS app_settings (
    key        TEXT PRIMARY KEY,
    value      TEXT NOT NULL DEFAULT '',
    updated_at TEXT NOT NULL,
    updated_by TEXT NOT NULL DEFAULT ''
);

-- API Key：只存 sha256 与前缀，明文只在创建时显示一次。
CREATE TABLE IF NOT EXISTS api_keys (
    id           TEXT PRIMARY KEY,
    name         TEXT NOT NULL,
    key_prefix   TEXT NOT NULL,
    key_hash     TEXT NOT NULL UNIQUE,
    scopes       TEXT NOT NULL DEFAULT '',
    is_active    INTEGER NOT NULL DEFAULT 1,
    created_at   TEXT NOT NULL,
    last_used_at TEXT,
    created_by   TEXT NOT NULL DEFAULT ''
);

-- 幂等键：同一 principal + operation + key 只对应一个任务/响应。
CREATE TABLE IF NOT EXISTS idempotency_keys (
    principal      TEXT NOT NULL,
    operation      TEXT NOT NULL,
    key            TEXT NOT NULL,
    request_sha256 TEXT NOT NULL,
    job_id         TEXT,
    response_json  TEXT,
    created_at     TEXT NOT NULL,
    expires_at     TEXT NOT NULL,
    PRIMARY KEY (principal, operation, key)
);

-- 通途订单号占用登记：补发时按 po_base 找下一个 -N，避免重复导入。
CREATE TABLE IF NOT EXISTS order_number_usage (
    full_number TEXT PRIMARY KEY,
    po_base     TEXT NOT NULL,
    job_id      TEXT,
    source      TEXT NOT NULL DEFAULT '',
    created_at  TEXT NOT NULL
);
CREATE INDEX IF NOT EXISTS idx_order_number_usage_base ON order_number_usage(po_base);
"""

# 断货 SKU 列表存这里（页面可改）；从没设置过时回落到 .env 的初始值
NO_STOCK_KEY = "default_no_stock"

ARTIFACT_KINDS = (
    "input_packslip", "input_order",
    "checked_order", "stock_operations",
    "tongtool", "tongtool_no_stock", "tongtool_importable",
    "label", "back_label", "label_no_stock", "back_label_no_stock",
)

# 产物类型的中文名（页面展示用）
ARTIFACT_LABELS = {
    "input_packslip": "Packslip PDF",
    "input_order": "SPS 订单 CSV",
    "checked_order": "checked0stock CSV",
    "stock_operations": "SPS 库存检查操作表",
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


class OrderNumberConflict(RuntimeError):
    """补发订单号已被占用（并发或历史登记冲突）。"""


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
            columns = {row[1] for row in conn.execute("PRAGMA table_info(jobs)")}
            for column, ddl in (
                ("job_type", "TEXT NOT NULL DEFAULT 'fulfillment'"),
                ("input_sha256", "TEXT"),
                ("reorder_json", "TEXT"),
                ("api_key_id", "TEXT"),
            ):
                if column in columns:
                    continue
                try:
                    conn.execute(f"ALTER TABLE jobs ADD COLUMN {column} {ddl}")
                except sqlite3.OperationalError as exc:
                    # Web 与 worker 会同时启动、同时看到旧库缺这一列，其中一个必然
                    # 撞上 duplicate column name。SQLite 没有 ADD COLUMN IF NOT EXISTS，
                    # 而那一刻「列已经在了」正是我们想要的结果，所以这里放行。
                    if "duplicate column name" not in str(exc).lower():
                        raise
                    log.info("%s 列已由另一个进程迁移完成，跳过", column)

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
        job_type: str = "fulfillment",
        input_sha256: str | None = None,
        reorder: list[str] | None = None,
        api_key_id: str | None = None,
    ) -> str:
        with self.connect() as conn:
            conn.execute(
                """INSERT INTO jobs (id, job_type, status, created_by, created_at, no_stock, no_stock_note,
                       validate_only, allow_unmatched, input_packslip, input_order,
                       progress_step, progress_message, pipeline_version, source_job_id,
                       input_sha256, reorder_json, api_key_id)
                   VALUES (?, ?, 'uploaded', ?, ?, ?, ?, ?, ?, ?, ?, 'uploaded', '已接收上传文件',
                       ?, ?, ?, ?, ?)""",
                (
                    job_id, job_type, created_by, now_iso(), no_stock, no_stock_note,
                    int(validate_only), int(allow_unmatched), input_packslip, input_order,
                    pipeline_version, source_job_id, input_sha256,
                    json.dumps(reorder or [], ensure_ascii=False), api_key_id,
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

    def queued_jobs(self) -> list[dict]:
        """仍在排队中的任务，带 Redis 侧的 `worker_job_id`，供启动时对账。"""
        with self.connect() as conn:
            rows = conn.execute(
                "SELECT id, worker_job_id FROM jobs WHERE status = 'queued'"
            ).fetchall()
        return [{"id": r[0], "worker_job_id": r[1] or ""} for r in rows]

    # ---------- 应用设置（页面上自己维护，不必再改服务器 .env）----------

    def get_setting(self, key: str) -> dict | None:
        with self.connect() as conn:
            row = conn.execute(
                "SELECT value, updated_at, updated_by FROM app_settings WHERE key = ?", (key,)
            ).fetchone()
        return dict(row) if row else None

    def set_setting(self, key: str, value: str, actor: str = "") -> None:
        with self.connect() as conn:
            conn.execute(
                """INSERT INTO app_settings(key, value, updated_at, updated_by)
                   VALUES (?, ?, ?, ?)
                   ON CONFLICT(key) DO UPDATE SET
                       value      = excluded.value,
                       updated_at = excluded.updated_at,
                       updated_by = excluded.updated_by""",
                (key, value, now_iso(), actor),
            )
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

    def artifacts_by_kind(self, kinds: tuple[str, ...] | list[str]) -> list[dict]:
        """按产物类型取全部行（回填订单号等一次性维护用）。"""
        kinds = tuple(kinds)
        if not kinds:
            return []
        marks = ", ".join("?" for _ in kinds)
        with self.connect() as conn:
            rows = conn.execute(
                f"SELECT * FROM artifacts WHERE kind IN ({marks}) ORDER BY created_at", kinds
            ).fetchall()
        return [dict(r) for r in rows]

    # ---------- API keys ----------

    def create_api_key(self, name: str, scopes: str, created_by: str = "") -> dict:
        """创建 API Key。返回明文只有这一次；库里只存 sha256 与前缀。"""
        key_id = new_id("key")
        plaintext = "sk-" + secrets.token_urlsafe(32)
        key_hash = hashlib.sha256(plaintext.encode("utf-8")).hexdigest()
        prefix = plaintext[:12]
        with self.connect() as conn:
            conn.execute(
                """INSERT INTO api_keys (id, name, key_prefix, key_hash, scopes, is_active,
                       created_at, created_by)
                   VALUES (?, ?, ?, ?, ?, 1, ?, ?)""",
                (key_id, name, prefix, key_hash, scopes, now_iso(), created_by),
            )
        return {"id": key_id, "name": name, "key": plaintext, "key_prefix": prefix, "scopes": scopes}

    def lookup_api_key(self, key_hash: str) -> dict | None:
        with self.connect() as conn:
            row = conn.execute(
                "SELECT * FROM api_keys WHERE key_hash = ? AND is_active = 1", (key_hash,)
            ).fetchone()
        return dict(row) if row else None

    def touch_api_key(self, key_id: str) -> None:
        with self.connect() as conn:
            conn.execute("UPDATE api_keys SET last_used_at = ? WHERE id = ?", (now_iso(), key_id))

    def list_api_keys(self) -> list[dict]:
        with self.connect() as conn:
            rows = conn.execute(
                "SELECT id, name, key_prefix, scopes, is_active, created_at, last_used_at, created_by "
                "FROM api_keys ORDER BY created_at DESC"
            ).fetchall()
        return [dict(r) for r in rows]

    def revoke_api_key(self, key_id: str) -> bool:
        with self.connect() as conn:
            cur = conn.execute("UPDATE api_keys SET is_active = 0 WHERE id = ?", (key_id,))
        return cur.rowcount == 1

    # ---------- idempotency ----------

    def lookup_idempotency(self, principal: str, operation: str, key: str) -> dict | None:
        with self.connect() as conn:
            row = conn.execute(
                """SELECT * FROM idempotency_keys
                   WHERE principal = ? AND operation = ? AND key = ? AND expires_at > ?""",
                (principal, operation, key, now_iso()),
            ).fetchone()
        return dict(row) if row else None

    def store_idempotency(
        self, principal: str, operation: str, key: str, request_sha256: str,
        job_id: str, response_json: str, ttl_minutes: int,
    ) -> None:
        expires = (datetime.now().astimezone() + timedelta(minutes=ttl_minutes)).isoformat(timespec="seconds")
        with self.connect() as conn:
            conn.execute(
                """INSERT INTO idempotency_keys
                       (principal, operation, key, request_sha256, job_id, response_json, created_at, expires_at)
                   VALUES (?, ?, ?, ?, ?, ?, ?, ?)
                   ON CONFLICT(principal, operation, key) DO UPDATE SET
                       request_sha256 = excluded.request_sha256,
                       job_id = excluded.job_id,
                       response_json = excluded.response_json,
                       created_at = excluded.created_at,
                       expires_at = excluded.expires_at""",
                (principal, operation, key, request_sha256, job_id, response_json, now_iso(), expires),
            )

    def purge_expired_idempotency(self) -> int:
        with self.connect() as conn:
            cur = conn.execute("DELETE FROM idempotency_keys WHERE expires_at <= ?", (now_iso(),))
        return cur.rowcount

    def find_recent_job(self, input_sha256: str, minutes: int) -> str | None:
        cutoff = (datetime.now().astimezone() - timedelta(minutes=minutes)).isoformat(timespec="seconds")
        with self.connect() as conn:
            row = conn.execute(
                """SELECT id FROM jobs
                   WHERE input_sha256 = ? AND created_at >= ? AND status != 'failed'
                   ORDER BY created_at DESC, rowid DESC LIMIT 1""",
                (input_sha256, cutoff),
            ).fetchone()
        return row[0] if row else None

    # ---------- Tongtool order number registry ----------

    def record_order_numbers(self, job_id: str, mapping: dict[str, str], source: str = "worker") -> None:
        """记录已写入 xlsx 的订单号（含裸号与 -N）。重复写入忽略。"""
        if not mapping:
            return
        numbers = [f"{po}{suffix}" if suffix else po for po, suffix in mapping.items()]
        self.record_full_numbers(numbers, job_id, source)

    def record_full_numbers(self, numbers: list[str], job_id: str, source: str = "worker") -> None:
        if not numbers:
            return
        with self.connect() as conn:
            for full in numbers:
                full = str(full).strip()
                if not full:
                    continue
                base = full.split("-", 1)[0]
                conn.execute(
                    """INSERT OR IGNORE INTO order_number_usage
                           (full_number, po_base, job_id, source, created_at)
                       VALUES (?, ?, ?, ?, ?)""",
                    (full, base, job_id, source, now_iso()),
                )

    def reserve_order_numbers(
        self, po_bases: list[str], job_id: str, explicit: dict[str, str] | None = None,
    ) -> dict[str, str]:
        """为补发 PO 预留 -N 后缀，返回 {PO: "-N"}。

        explicit 里的后缀直接采信；其余按该 PO 已登记的最大 -N + 1。
        用 BEGIN IMMEDIATE 把「读最大号 + 插入」放在同一把写锁里。
        """
        explicit = {str(k): str(v) for k, v in (explicit or {}).items()}
        result: dict[str, str] = {}
        with self.connect() as conn:
            conn.execute("BEGIN IMMEDIATE")
            try:
                for po in po_bases:
                    if po in explicit:
                        suffix = explicit[po].strip()
                        if suffix and not suffix.startswith("-"):
                            suffix = "-" + suffix
                    else:
                        rows = conn.execute(
                            "SELECT full_number FROM order_number_usage WHERE po_base = ?", (po,)
                        ).fetchall()
                        max_n = 0
                        for (full,) in rows:
                            if full == po:
                                max_n = max(max_n, 1)
                            elif full.startswith(po + "-"):
                                try:
                                    max_n = max(max_n, int(full[len(po) + 1:]))
                                except ValueError:
                                    pass
                        suffix = f"-{max(max_n + 1, 2)}"
                    full = f"{po}{suffix}"
                    try:
                        conn.execute(
                            """INSERT INTO order_number_usage
                                   (full_number, po_base, job_id, source, created_at)
                               VALUES (?, ?, ?, 'reserved', ?)""",
                            (full, po, job_id, now_iso()),
                        )
                    except sqlite3.IntegrityError as exc:
                        raise OrderNumberConflict(f"{po}{suffix} 已被占用") from exc
                    result[po] = suffix
                conn.commit()
            except BaseException:
                conn.rollback()
                raise
        return result

    # ---------- helpers ----------

    @staticmethod
    def _job_dict(row: sqlite3.Row) -> dict:
        job = dict(row)
        job["report"] = json.loads(job["report_json"]) if job["report_json"] else None
        job["error"] = json.loads(job["error_json"]) if job["error_json"] else None
        job["validate_only"] = bool(job["validate_only"])
        job["allow_unmatched"] = bool(job["allow_unmatched"])
        job["no_stock_list"] = [s for s in (job["no_stock"] or "").split(",") if s.strip()]
        job["reorder_list"] = json.loads(job["reorder_json"]) if job.get("reorder_json") else []
        return job
