# -*- coding: utf-8 -*-
"""drive_folder_ops 的纯函数单测（不碰网络）。

网络命令（info/list/smoke-test/write）用真实文件夹手测，见 AGENT_HANDOFF.md；
这里只锁住路径解析、查询转义、祖先链守卫这些写错很难发现的逻辑。
"""

from __future__ import annotations

import pathlib
import sys

import pytest

sys.path.insert(0, str(pathlib.Path(__file__).resolve().parents[2]))

from drive_folder_ops import drive_folder_ops as dfo  # noqa: E402


# ── 路径规范化 ────────────────────────────────────────────


@pytest.mark.parametrize("raw", ["", "/", "///", ".", "./"])
def test_root_paths(raw):
    assert dfo.normalize_rel_path(raw) == []


def test_normal_path_keeps_order():
    assert dfo.normalize_rel_path("/00_候选与修正/文档.md") == ["00_候选与修正", "文档.md"]


@pytest.mark.parametrize(
    "raw",
    [
        "a/../b",
        "../a",
        "a/./b",
        "a//b",
        "C:/a",
        "a\\b",
        "a/..",
    ],
)
def test_rejects_unsafe_paths(raw):
    with pytest.raises(dfo.PathError):
        dfo.normalize_rel_path(raw)


# ── Drive query 转义 ──────────────────────────────────────


def test_escape_drive_query_quotes_and_backslashes():
    assert dfo.escape_drive_query("O'Brien") == "O\\'Brien"
    assert dfo.escape_drive_query("a\\b") == "a\\\\b"
    assert dfo.escape_drive_query("运营知识") == "运营知识"


# ── 祖先链守卫 ────────────────────────────────────────────


class FakeClient:
    def __init__(self, parents: dict[str, list[str]]):
        self.parents = parents
        self.calls: list[str] = []

    def get_meta(self, file_id: str) -> dict:
        self.calls.append(file_id)
        return {"id": file_id, "name": file_id, "parents": self.parents.get(file_id, [])}


def test_assert_under_root_walks_up():
    client = FakeClient({"file": ["sub"], "sub": [dfo.ROOT_FOLDER_ID]})
    dfo.DriveClient.assert_under_root(client, "file")  # 不抛即通过


def test_assert_under_root_rejects_orphan():
    client = FakeClient({"file": ["sub"], "sub": ["other-root"]})
    with pytest.raises(dfo.PathError):
        dfo.DriveClient.assert_under_root(client, "file")


def test_assert_under_root_rejects_cycle():
    client = FakeClient({"a": ["b"], "b": ["a"]})
    with pytest.raises(dfo.PathError):
        dfo.DriveClient.assert_under_root(client, "a")


def test_assert_under_root_allows_root_itself():
    client = FakeClient({})
    dfo.DriveClient.assert_under_root(client, dfo.ROOT_FOLDER_ID)
    assert client.calls == []


# ── 配额识别 ──────────────────────────────────────────────


def test_quota_error_detection():
    quota = dfo.ApiError(403, '{"error":{"errors":[{"reason":"storageQuotaExceeded"}]}}', "u")
    other = dfo.ApiError(403, '{"error":{"errors":[{"reason":"forbidden"}]}}', "u")
    assert dfo._is_quota_error(quota)
    assert not dfo._is_quota_error(other)


# ── 凭证路径 ──────────────────────────────────────────────


def test_credentials_path_honors_env(tmp_path, monkeypatch):
    key = tmp_path / "sa.json"
    key.write_text("{}", encoding="utf-8")
    monkeypatch.setenv("GSPREAD_SERVICE_ACCOUNT_FILE", str(key))
    assert dfo.credentials_path() == key


def test_credentials_path_rejects_missing_env(tmp_path, monkeypatch):
    missing = tmp_path / "nope.json"
    monkeypatch.setenv("GSPREAD_SERVICE_ACCOUNT_FILE", str(missing))
    with pytest.raises(SystemExit):
        dfo.credentials_path()
