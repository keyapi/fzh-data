"""Tests for nas_product_visuals/nas_env.py — NAS SSH 凭据只从 .env / 环境变量来。"""

from __future__ import annotations

import importlib.util
import sys
from pathlib import Path

import pytest

ROOT = Path(__file__).resolve().parents[2]
_SPEC = importlib.util.spec_from_file_location(
    "fzh_nas_env", ROOT / "nas_product_visuals" / "nas_env.py"
)
assert _SPEC and _SPEC.loader
nas_env = importlib.util.module_from_spec(_SPEC)
sys.modules[_SPEC.name] = nas_env
_SPEC.loader.exec_module(nas_env)

KEYS = (
    "NAS_SSH_HOST",
    "NAS_HOST",
    "NAS_SSH_PORT",
    "NAS_PORT",
    "NAS_SSH_USER",
    "NAS_ADMIN_USER",
    "NAS_SSH_PASSWORD",
    "NAS_PASSWORD",
)


@pytest.fixture
def clean_env(monkeypatch, tmp_path):
    for k in KEYS:
        monkeypatch.delenv(k, raising=False)
    # 别去读真实的 NAS_API/.env
    monkeypatch.setattr(nas_env, "ENV_FILES", (tmp_path / ".env",))
    return tmp_path


def test_reads_all_four_from_env_file(clean_env):
    (clean_env / ".env").write_text(
        "NAS_SSH_HOST=nas.example\nNAS_SSH_PORT=31022\n"
        "NAS_SSH_USER=someadmin\nNAS_SSH_PASSWORD=pw123\n",
        encoding="utf-8",
    )
    cfg = nas_env.nas_ssh()
    assert (cfg.host, cfg.port, cfg.user, cfg.password) == ("nas.example", 31022, "someadmin", "pw123")


def test_port_defaults_to_22(clean_env):
    (clean_env / ".env").write_text(
        "NAS_SSH_HOST=nas.example\nNAS_SSH_USER=u\nNAS_SSH_PASSWORD=p\n", encoding="utf-8"
    )
    assert nas_env.nas_ssh().port == 22


def test_missing_user_raises_and_does_not_default(clean_env):
    """没有账号时必须报错——不能偷偷用某个默认账号连上去。"""
    (clean_env / ".env").write_text(
        "NAS_SSH_HOST=nas.example\nNAS_SSH_PASSWORD=pw123\n", encoding="utf-8"
    )
    with pytest.raises(RuntimeError, match="NAS_SSH_USER"):
        nas_env.nas_ssh()


def test_missing_password_raises(clean_env):
    (clean_env / ".env").write_text(
        "NAS_SSH_HOST=nas.example\nNAS_SSH_USER=u\n", encoding="utf-8"
    )
    with pytest.raises(RuntimeError, match="NAS_SSH_PASSWORD"):
        nas_env.nas_ssh()


def test_bad_port_raises(clean_env):
    (clean_env / ".env").write_text(
        "NAS_SSH_HOST=nas.example\nNAS_SSH_PORT=not-a-port\n"
        "NAS_SSH_USER=u\nNAS_SSH_PASSWORD=p\n",
        encoding="utf-8",
    )
    with pytest.raises(RuntimeError, match="NAS_SSH_PORT"):
        nas_env.nas_ssh()


def test_module_source_has_no_literal_password():
    """回归：这个模块（和调用它的两个脚本）里不许再出现明文密码。"""
    module_dir = ROOT / "nas_product_visuals"
    bad = []
    for name in ("nas_env.py", "nas_cmd.py", "nas_test_acl.py"):
        text = (module_dir / name).read_text(encoding="utf-8")
        for line in text.splitlines():
            if "PASSWORD" in line and "=" in line and "os.environ" not in line and "getenv" not in line:
                if any(q in line for q in ('"', "'")) and "_KEYS" not in line and "NAS_SSH_PASSWORD=" not in line:
                    bad.append(f"{name}: {line.strip()[:60]}")
    assert not bad, bad
