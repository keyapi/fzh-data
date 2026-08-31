# -*- coding: utf-8 -*-
"""Minimal Tongtool official MCP HTTP client. Credentials stay in tongtool_api/.env."""
from __future__ import annotations

import json
import urllib.error
import urllib.request
from pathlib import Path

MCP_URL = "https://mcp.tongtool.com/mcp"
ENV_PATH = Path(__file__).resolve().parent / ".env"


def load_env(path: Path = ENV_PATH) -> dict[str, str]:
    values: dict[str, str] = {}
    if not path.exists():
        return values
    for raw in path.read_text(encoding="utf-8").splitlines():
        line = raw.strip()
        if not line or line.startswith("#") or "=" not in line:
            continue
        k, v = line.split("=", 1)
        values[k.strip()] = v.strip().strip('"').strip("'")
    return values


def primary_credentials() -> tuple[str, str]:
    env = load_env()
    key = env.get("TONGTOOL_ERP2_PRIMARY_KEY", "").strip()
    secret = env.get("TONGTOOL_ERP2_PRIMARY_SECRET", "").strip()
    if not key or not secret:
        raise FileNotFoundError(
            f"Missing TONGTOOL_ERP2_PRIMARY_KEY/SECRET in {ENV_PATH}. "
            "Copy tongtool_api/.env.example to tongtool_api/.env."
        )
    return key, secret


def parse_sse(body: str) -> dict:
    for line in body.splitlines():
        if line.startswith("data:"):
            return json.loads(line[5:].strip())
    return json.loads(body) if body.strip() else {}


class McpClient:
    """Streamable HTTP client for https://mcp.tongtool.com/mcp (ERP2)."""

    def __init__(self, key: str, secret: str, client_name: str = "fzh-tongtool-mcp") -> None:
        self.request_id = 1
        self.headers = {
            "Accept": "application/json, text/event-stream",
            "Content-Type": "application/json",
            "x-tongtool-access-key": key,
            "x-tongtool-secret-key": secret,
        }
        self.session_id = ""
        response, headers = self._post(
            {
                "jsonrpc": "2.0",
                "id": 1,
                "method": "initialize",
                "params": {
                    "protocolVersion": "2025-11-25",
                    "capabilities": {},
                    "clientInfo": {"name": client_name, "version": "1.0"},
                },
            }
        )
        if "error" in response:
            raise RuntimeError(f"MCP initialize error: {response['error']}")
        self.session_id = headers.get("mcp-session-id", "")
        if not self.session_id:
            raise RuntimeError("MCP initialize response did not include mcp-session-id")
        self._post({"jsonrpc": "2.0", "method": "notifications/initialized", "params": {}})

    def _post(self, payload: dict) -> tuple[dict, dict[str, str]]:
        headers = dict(self.headers)
        if self.session_id:
            headers["Mcp-Session-Id"] = self.session_id
        req = urllib.request.Request(
            MCP_URL,
            data=json.dumps(payload).encode("utf-8"),
            headers=headers,
            method="POST",
        )
        try:
            with urllib.request.urlopen(req, timeout=90) as resp:
                body = resp.read().decode("utf-8")
                rh = {k.lower(): v for k, v in resp.headers.items()}
                return parse_sse(body) if body.strip() else {}, rh
        except urllib.error.HTTPError as e:
            detail = e.read().decode("utf-8", errors="replace")[:400]
            raise RuntimeError(f"MCP HTTP {e.code}: {detail}") from e

    def next_id(self) -> int:
        self.request_id += 1
        return self.request_id

    def call(self, name: str, arguments: dict) -> dict:
        resp, _ = self._post(
            {
                "jsonrpc": "2.0",
                "id": self.next_id(),
                "method": "tools/call",
                "params": {"name": name, "arguments": arguments},
            }
        )
        return resp
