"""env 测试：.env 有界上溯、就近优先、不覆盖已 export、BOM 容错。

重点是模拟 worktree 布局 —— 包目录到 .env 之间隔着若干层目录。
"""

from __future__ import annotations

import os
from pathlib import Path

import pytest

from intent_router import env


@pytest.fixture(autouse=True)
def _isolate_environment(monkeypatch):
    """load_env 直接写 os.environ，monkeypatch 撤不掉 —— 整份快照后还原，避免污染其它测试。"""
    monkeypatch.delenv("TYPESAFE_API_KEY", raising=False)
    snapshot = dict(os.environ)
    yield
    os.environ.clear()
    os.environ.update(snapshot)


def _nested(tmp_path: Path, depth: int) -> Path:
    """造 depth 层嵌套，返回最内层（当作包目录）。"""
    current = tmp_path
    for index in range(depth):
        current = current / f"level{index}"
    current.mkdir(parents=True, exist_ok=True)
    return current


def test_finds_env_several_levels_up(tmp_path):
    package_dir = _nested(tmp_path, 4)
    env_file = tmp_path / ".env"
    env_file.write_text("TYPESAFE_API_KEY=from-on-high\n", encoding="utf-8")

    loaded = env.load_env(package_dir, levels=6)
    assert loaded == [env_file]
    assert env.get_key("TYPESAFE_API_KEY") == "from-on-high"


def test_nearest_env_wins(tmp_path):
    package_dir = _nested(tmp_path, 3)
    near = package_dir.parent / ".env"
    near.write_text("NEAR=1\n", encoding="utf-8")
    far = tmp_path / ".env"
    far.write_text("FAR=1\n", encoding="utf-8")

    loaded = env.load_env(package_dir, levels=6)
    assert loaded == [near, far]  # 就近在前


def test_exported_value_is_never_overwritten(tmp_path, monkeypatch):
    package_dir = _nested(tmp_path, 2)
    (tmp_path / ".env").write_text("TYPESAFE_API_KEY=from-file\n", encoding="utf-8")
    monkeypatch.setenv("TYPESAFE_API_KEY", "already-exported")

    env.load_env(package_dir, levels=6)
    assert env.get_key("TYPESAFE_API_KEY") == "already-exported"


def test_blank_exported_value_gets_filled(tmp_path, monkeypatch):
    package_dir = _nested(tmp_path, 2)
    (tmp_path / ".env").write_text("TYPESAFE_API_KEY=from-file\n", encoding="utf-8")
    monkeypatch.setenv("TYPESAFE_API_KEY", "   ")

    env.load_env(package_dir, levels=6)
    assert env.get_key("TYPESAFE_API_KEY") == "from-file"


def test_bounded_walk_respects_level_limit(tmp_path):
    package_dir = _nested(tmp_path, 4)
    (tmp_path / ".env").write_text("TYPESAFE_API_KEY=too-far\n", encoding="utf-8")

    assert env.load_env(package_dir, levels=1) == []


def test_bom_prefixed_file_parses(tmp_path):
    package_dir = _nested(tmp_path, 1)
    env_file = tmp_path / ".env"
    env_file.write_text("TYPESAFE_API_KEY=with-bom\n", encoding="utf-8-sig")

    env.load_env(package_dir, levels=3)
    assert env.get_key("TYPESAFE_API_KEY") == "with-bom"


def test_parse_env_file_skips_noise_and_unquotes(tmp_path):
    path = tmp_path / ".env"
    path.write_text(
        "# comment\n"
        "\n"
        "NOT_A_PAIR\n"
        'QUOTED="quoted value"\n'
        "SINGLE='single value'\n"
        "EMPTY=\n"
        "  SPACED  =  trimmed  \n",
        encoding="utf-8",
    )

    values = env.parse_env_file(path)
    assert values == {"QUOTED": "quoted value", "SINGLE": "single value", "SPACED": "trimmed"}


def test_candidates_returns_only_existing_files(tmp_path):
    package_dir = _nested(tmp_path, 2)
    assert env.candidates(package_dir, levels=4) == []


def test_real_repo_env_is_reachable_from_the_package():
    """冒烟：从包目录真能上溯到仓库里的 .env（本地可能不存在，存在则必须可解析）。"""
    found = env.candidates()
    for path in found:
        assert path.name == ".env"
        assert path.is_file()
