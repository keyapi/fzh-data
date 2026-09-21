"""Tests for the shared Playwright browser launcher (env-driven channel / headless)."""

from __future__ import annotations

import sys
from pathlib import Path

LEGACY = Path(__file__).resolve().parents[2] / "web_automation" / "legacy-compatible"
sys.path.insert(0, str(LEGACY))

from browser_launch import (  # noqa: E402
    ENV_CHANNEL,
    ENV_HEADLESS,
    browser_channel,
    headless_override,
    launch_persistent,
    resolve_kwargs,
)


class _StubChromium:
    def __init__(self) -> None:
        self.calls: list[dict] = []

    def launch_persistent_context(self, **kwargs):
        self.calls.append(kwargs)
        return "context"


class _StubPlaywright:
    def __init__(self) -> None:
        self.chromium = _StubChromium()


def test_no_env_leaves_caller_values_untouched(monkeypatch):
    monkeypatch.delenv(ENV_CHANNEL, raising=False)
    monkeypatch.delenv(ENV_HEADLESS, raising=False)

    resolved = resolve_kwargs(headless=False, accept_downloads=True)

    assert resolved["headless"] is False
    assert resolved["accept_downloads"] is True
    assert "channel" not in resolved
    assert browser_channel() is None
    assert headless_override() is None


def test_channel_env_adds_channel(monkeypatch):
    monkeypatch.setenv(ENV_CHANNEL, "chrome")
    monkeypatch.delenv(ENV_HEADLESS, raising=False)

    resolved = resolve_kwargs(headless=False)

    assert resolved["channel"] == "chrome"
    assert resolved["headless"] is False


def test_headless_env_forces_true(monkeypatch):
    monkeypatch.delenv(ENV_CHANNEL, raising=False)
    monkeypatch.setenv(ENV_HEADLESS, "1")

    assert resolve_kwargs(headless=False)["headless"] is True


def test_headless_env_forces_false_overriding_caller(monkeypatch):
    monkeypatch.setenv(ENV_HEADLESS, "0")

    assert resolve_kwargs(headless=True)["headless"] is False


def test_unrecognised_headless_value_is_ignored(monkeypatch):
    monkeypatch.setenv(ENV_HEADLESS, "maybe")

    assert headless_override() is None
    assert resolve_kwargs(headless=True)["headless"] is True


def test_launch_persistent_stringifies_user_data_dir_and_forwards(monkeypatch):
    monkeypatch.setenv(ENV_CHANNEL, "chrome")
    monkeypatch.setenv(ENV_HEADLESS, "0")
    p = _StubPlaywright()

    launch_persistent(p, Path("chrome-profile"), headless=True, accept_downloads=True)

    assert p.chromium.calls == [
        {
            "user_data_dir": "chrome-profile",
            "accept_downloads": True,
            "headless": False,
            "channel": "chrome",
        }
    ]
