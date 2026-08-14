# -*- coding: utf-8 -*-
from __future__ import annotations

import json
from pathlib import Path

import pytest

from tongtool_api.setup_cursor_mcp import (
    MCP_URL,
    PRIMARY_NAME,
    SECONDARY_NAME,
    credential_servers,
    merge_mcp_config,
    register,
    write_mcp_json,
)


def test_merge_preserves_unrelated_servers() -> None:
    existing = {"mcpServers": {"other": {"command": "npx"}}}
    servers = {PRIMARY_NAME: {"url": MCP_URL, "headers": {"x-tongtool-access-key": "k"}}}
    merged = merge_mcp_config(existing, servers)
    assert merged["mcpServers"]["other"]["command"] == "npx"
    assert merged["mcpServers"][PRIMARY_NAME]["url"] == MCP_URL


def test_incomplete_pair_raises() -> None:
    with pytest.raises(ValueError, match="together"):
        credential_servers({"TONGTOOL_ERP2_PRIMARY_KEY": "only-key"})


def test_no_credentials_raises() -> None:
    with pytest.raises(ValueError, match="No Tongtool"):
        credential_servers({})


def test_register_writes_utf8_no_bom(tmp_path: Path) -> None:
    env_file = tmp_path / ".env"
    env_file.write_text(
        "TONGTOOL_ERP2_PRIMARY_KEY=pk\nTONGTOOL_ERP2_PRIMARY_SECRET=ps\n",
        encoding="utf-8",
    )
    mcp_json = tmp_path / ".cursor" / "mcp.json"
    target, names = register(env_path=env_file, mcp_json_path=mcp_json)
    raw = target.read_bytes()
    assert not raw.startswith(b"\xef\xbb\xbf")
    data = json.loads(raw.decode("utf-8"))
    assert names == [PRIMARY_NAME]
    headers = data["mcpServers"][PRIMARY_NAME]["headers"]
    assert headers["x-tongtool-access-key"] == "pk"
    assert headers["x-tongtool-secret-key"] == "ps"


def test_secondary_and_existing_merge(tmp_path: Path) -> None:
    env_file = tmp_path / ".env"
    env_file.write_text(
        "\n".join(
            [
                "TONGTOOL_ERP2_PRIMARY_KEY=pk",
                "TONGTOOL_ERP2_PRIMARY_SECRET=ps",
                "TONGTOOL_ERP2_SECONDARY_KEY=sk",
                "TONGTOOL_ERP2_SECONDARY_SECRET=ss",
            ]
        )
        + "\n",
        encoding="utf-8",
    )
    mcp_json = tmp_path / "mcp.json"
    write_mcp_json(mcp_json, {"mcpServers": {"keep-me": {"url": "https://example.invalid/mcp"}}})
    _, names = register(env_path=env_file, mcp_json_path=mcp_json)
    data = json.loads(mcp_json.read_text(encoding="utf-8"))
    assert PRIMARY_NAME in names
    assert SECONDARY_NAME in names
    assert "keep-me" in data["mcpServers"]
