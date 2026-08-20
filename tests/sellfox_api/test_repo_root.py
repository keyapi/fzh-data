"""Tests for repo root discovery (Issue #188 shallow-path fix)."""
from __future__ import annotations

from pathlib import Path
import sys

ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT / "SELLFOX_API"))

from repo_root import find_main_root  # noqa: E402


def test_find_main_root_from_shallow_sellfox_api_dir(tmp_path: Path):
    """E:\\FZH-AI\\SELLFOX_API style layout: root is parent of SELLFOX_API."""
    repo = tmp_path / "FZH-AI"
    sellfox = repo / "SELLFOX_API"
    sellfox.mkdir(parents=True)
    (repo / ".env").write_text("X=1\n", encoding="utf-8")
    (repo / "EN_API").mkdir()
    (repo / "EN_API" / ".env").write_text("Y=2\n", encoding="utf-8")

    assert find_main_root(start=sellfox) == repo.resolve()


def test_find_main_root_from_worktree_depth(tmp_path: Path):
    repo = tmp_path / "fzh-data"
    deep = repo / ".claude" / "worktrees" / "wt" / "SELLFOX_API"
    deep.mkdir(parents=True)
    (repo / ".env").write_text("X=1\n", encoding="utf-8")
    (repo / "EN_API").mkdir()
    (repo / "EN_API" / ".env").write_text("Y=2\n", encoding="utf-8")

    assert find_main_root(start=deep) == repo.resolve()


def test_find_main_root_raises_with_checked_paths(tmp_path: Path):
    shallow = tmp_path / "orphan" / "SELLFOX_API"
    shallow.mkdir(parents=True)
    try:
        find_main_root(start=shallow)
    except FileNotFoundError as exc:
        msg = str(exc)
        assert "找不到项目根目录" in msg
        assert str(shallow.resolve()) in msg
    else:
        raise AssertionError("expected FileNotFoundError")
