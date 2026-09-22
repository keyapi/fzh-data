#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""Web / worker 的配置：全部来自环境变量，带安全的本地默认值。

容器里通过环境变量指向挂载的持久卷；本机直接跑则落到 `pb_orders/runtime/`。
"""

from __future__ import annotations

import os
import subprocess
from dataclasses import dataclass, field
from pathlib import Path

PB_DIR = Path(__file__).resolve().parent.parent
REPO_ROOT = PB_DIR.parent


def _load_dotenv() -> None:
    """读 pb_orders/.env（本机开发用）。已存在的环境变量优先，容器里不覆盖。"""
    try:
        from dotenv import load_dotenv
    except ImportError:  # 容器里没装 dotenv 也能跑，配置全走环境变量
        return
    load_dotenv(PB_DIR / ".env", override=False)


_load_dotenv()


def _env_path(name: str, default: Path) -> Path:
    raw = os.environ.get(name, "").strip()
    return Path(raw).expanduser().resolve() if raw else default


def _env_int(name: str, default: int) -> int:
    raw = os.environ.get(name, "").strip()
    try:
        return int(raw) if raw else default
    except ValueError:
        return default


def _pipeline_version() -> str:
    env = os.environ.get("PB_ORDERS_PIPELINE_VERSION", "").strip()
    if env:
        return env
    try:
        out = subprocess.run(
            ["git", "rev-parse", "--short", "HEAD"],
            cwd=REPO_ROOT, capture_output=True, text=True, timeout=5,
        )
        if out.returncode == 0 and out.stdout.strip():
            return out.stdout.strip()
    except Exception:  # noqa: BLE001 - 拿不到版本不影响出件
        pass
    return "unknown"


def _env_csv(name: str) -> tuple[str, ...]:
    raw = os.environ.get(name, "").strip()
    return tuple(s.strip() for s in raw.split(",") if s.strip())


def _normalize_prefix(raw: str) -> str:
    """URL 前缀：'' 或 '/pb'（无尾斜杠）。"""
    value = (raw or "").strip().rstrip("/")
    if not value:
        return ""
    return value if value.startswith("/") else f"/{value}"


@dataclass(frozen=True)
class Settings:
    runtime_dir: Path = field(default_factory=lambda: _env_path("PB_ORDERS_RUNTIME_DIR", PB_DIR / "runtime"))
    data_dir: Path = field(default_factory=lambda: _env_path("PB_ORDERS_DATA_DIR", PB_DIR / "data"))
    redis_url: str = field(default_factory=lambda: os.environ.get("PB_ORDERS_REDIS_URL", "redis://127.0.0.1:6379/0"))
    queue_name: str = field(default_factory=lambda: os.environ.get("PB_ORDERS_QUEUE", "pb-orders"))
    max_upload_mb: int = field(default_factory=lambda: _env_int("PB_ORDERS_MAX_UPLOAD_MB", 64))
    job_timeout: int = field(default_factory=lambda: _env_int("PB_ORDERS_JOB_TIMEOUT", 1800))
    retention_days: int = field(default_factory=lambda: _env_int("PB_ORDERS_RETENTION_DAYS", 90))
    pipeline_version: str = field(default_factory=_pipeline_version)
    # 挂在反代路径下时用（如 /pb）。空 = 挂在根路径。
    url_prefix: str = field(default_factory=lambda: _normalize_prefix(os.environ.get("PB_ORDERS_URL_PREFIX", "")))
    # 新建任务页预填的无货 SKU；做成配置项，断货情况变了改 .env 即可，不用改代码
    default_no_stock: tuple[str, ...] = field(default_factory=lambda: _env_csv("PB_ORDERS_DEFAULT_NO_STOCK"))
    # 钉钉 OIDC（复用公司桥）。issuer 为空即关闭认证。
    oidc_issuer: str = field(default_factory=lambda: os.environ.get("PB_ORDERS_OIDC_ISSUER", "").rstrip("/"))
    oidc_client_id: str = field(default_factory=lambda: os.environ.get("PB_ORDERS_OIDC_CLIENT_ID", "pb-orders"))
    oidc_client_secret: str = field(default_factory=lambda: os.environ.get("PB_ORDERS_OIDC_CLIENT_SECRET", ""))
    oidc_redirect_uri: str = field(default_factory=lambda: os.environ.get("PB_ORDERS_OIDC_REDIRECT_URI", ""))
    session_secret: str = field(default_factory=lambda: os.environ.get("PB_ORDERS_SESSION_SECRET", ""))
    # 允许登录的钉钉用户（显示名或 sub，逗号分隔）。留空 = 任何钉钉用户都能进（会告警）。
    allowed_users: tuple[str, ...] = field(default_factory=lambda: _env_csv("PB_ORDERS_ALLOWED_USERS"))

    @property
    def auth_enabled(self) -> bool:
        return bool(self.oidc_issuer)

    def __post_init__(self) -> None:
        if self.auth_enabled:
            missing = [
                name for name, value in (
                    ("PB_ORDERS_OIDC_REDIRECT_URI", self.oidc_redirect_uri),
                    ("PB_ORDERS_SESSION_SECRET", self.session_secret),
                ) if not value
            ]
            if missing:
                raise RuntimeError(f"已配置 OIDC_ISSUER 但缺少：{', '.join(missing)}")


    @property
    def db_path(self) -> Path:
        return self.runtime_dir / "jobs.sqlite"

    @property
    def inputs_dir(self) -> Path:
        return self.runtime_dir / "inputs"

    @property
    def work_dir(self) -> Path:
        return self.runtime_dir / "work"

    @property
    def artifacts_dir(self) -> Path:
        return self.runtime_dir / "artifacts"

    @property
    def sku_cache_path(self) -> Path:
        return self.data_dir / "us_sku_name_cache.csv"

    @property
    def nltk_dir(self) -> Path:
        return self.data_dir / "nltk_data"

    @property
    def max_upload_bytes(self) -> int:
        return self.max_upload_mb * 1024 * 1024

    def ensure_dirs(self) -> None:
        for path in (self.runtime_dir, self.inputs_dir, self.work_dir, self.artifacts_dir):
            path.mkdir(parents=True, exist_ok=True)


_settings: Settings | None = None


def get_settings() -> Settings:
    """进程内单例；测试可调用 `reset_settings()` 后重新读环境变量。"""
    global _settings
    if _settings is None:
        _settings = Settings()
    return _settings


def reset_settings() -> None:
    global _settings
    _settings = None
