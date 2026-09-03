"""Gitignore guards: web_automation runtime state stays untracked, uv.lock is tracked."""

from __future__ import annotations

import subprocess
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]


def _ignored(rel: str) -> bool:
    cp = subprocess.run(
        ["git", "check-ignore", "-q", "--", rel],
        cwd=ROOT,
        stdout=subprocess.PIPE,
        stderr=subprocess.PIPE,
    )
    return cp.returncode == 0


def test_runtime_state_is_ignored():
    ignored = [
        "web_automation/.venv/x",
        "web_automation/profiles/x",
        "web_automation/chrome-profile/x",
        "web_automation/sellfox-profile/x",
        "web_automation/downloads/a.xlsx",
        "web_automation/output/a.xlsx",
        "web_automation/mcp_cookies.json",
        "web_automation/sellfox_cookies.json",
        "web_automation/.env",
        "web_automation/debug_page.json",
        "web_automation/screenshot.png",
    ]
    not_ignored = [rel for rel in ignored if not _ignored(rel)]
    assert not not_ignored, f"should be ignored: {not_ignored}"


def test_child_lockfile_is_tracked():
    assert not _ignored("web_automation/uv.lock"), "uv.lock must be tracked"


def test_child_code_files_are_tracked():
    assert not _ignored("web_automation/pyproject.toml")
    assert not _ignored("web_automation/capabilities.yaml")
    assert not _ignored("web_automation/scripts/dispatch.py")
