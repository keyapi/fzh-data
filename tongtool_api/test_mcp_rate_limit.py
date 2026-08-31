"""Run a minimal read-only Tongtool MCP connectivity/rate-limit audit."""

from __future__ import annotations

import argparse
import json
import time
import urllib.error
import urllib.request
from pathlib import Path


MCP_URL = "https://mcp.tongtool.com/mcp"
TOOL_NAME = "erp2_basedata_warehousequery"


def load_env(path: Path) -> dict[str, str]:
    values: dict[str, str] = {}
    for raw_line in path.read_text(encoding="utf-8").splitlines():
        line = raw_line.strip()
        if not line or line.startswith("#") or "=" not in line:
            continue
        key, value = line.split("=", 1)
        values[key.strip()] = value.strip()
    return values


def parse_sse(body: str) -> dict:
    for line in body.splitlines():
        if line.startswith("data:"):
            return json.loads(line[5:].strip())
    return json.loads(body)


class McpClient:
    def __init__(self, key: str, secret: str) -> None:
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
                    "clientInfo": {"name": "fzh-rate-audit", "version": "1.0"},
                },
            }
        )
        if "result" not in response:
            raise RuntimeError(f"MCP initialize failed: {response.get('error', response)}")
        self.session_id = headers.get("mcp-session-id", "")
        if not self.session_id:
            raise RuntimeError("MCP initialize response did not include a session id")
        self._post(
            {"jsonrpc": "2.0", "method": "notifications/initialized", "params": {}}
        )

    def _post(self, payload: dict) -> tuple[dict, dict[str, str]]:
        headers = dict(self.headers)
        if self.session_id:
            headers["Mcp-Session-Id"] = self.session_id
        request = urllib.request.Request(
            MCP_URL,
            data=json.dumps(payload).encode("utf-8"),
            headers=headers,
            method="POST",
        )
        try:
            with urllib.request.urlopen(request, timeout=60) as response:
                body = response.read().decode("utf-8")
                response_headers = {key.lower(): value for key, value in response.headers.items()}
                return parse_sse(body) if body.strip() else {}, response_headers
        except urllib.error.HTTPError as error:
            detail = error.read().decode("utf-8", errors="replace")
            raise RuntimeError(f"MCP HTTP {error.code}: {detail}") from error

    def call(self) -> dict:
        schema = self.tool_schema()
        properties = schema.get("properties", {})
        arguments = (
            {"pageNo": 1, "pageSize": 1}
            if {"pageNo", "pageSize"}.issubset(properties)
            else {"request": {}}
            if "request" in properties
            else {}
        )
        response, _ = self._post(
            {
                "jsonrpc": "2.0",
                "id": self.next_id(),
                "method": "tools/call",
                "params": {"name": TOOL_NAME, "arguments": arguments},
            }
        )
        return response

    def tool_schema(self) -> dict:
        response, _ = self._post(
            {"jsonrpc": "2.0", "id": self.next_id(), "method": "tools/list", "params": {}}
        )
        for tool in response.get("result", {}).get("tools", []):
            if tool.get("name") == TOOL_NAME:
                return tool.get("inputSchema", {})
        raise RuntimeError(f"MCP tool not found: {TOOL_NAME}")

    def next_id(self) -> int:
        self.request_id += 1
        return self.request_id


def summarize(response: dict) -> tuple[str, str]:
    if "error" in response:
        return "mcp_error", str(response["error"].get("code", "unknown"))
    result = response.get("result", {})
    text = " ".join(
        item.get("text", "") for item in result.get("content", []) if item.get("type") == "text"
    )
    for code in (200, 519, 523, 524, 525, 526, 527, 599):
        if f'"code":{code}' in text.replace(" ", ""):
            return "business", str(code)
    return "result", "unclassified"


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument(
        "--mode", choices=("connectivity", "burst", "alternate", "discriminate"), default="connectivity"
    )
    parser.add_argument("--count", type=int, default=6)
    parser.add_argument(
        "--cooldown-seconds",
        type=float,
        default=0,
        help="Wait before initializing MCP or making calls, for a clean rate-limit window.",
    )
    args = parser.parse_args()
    if args.cooldown_seconds < 0:
        parser.error("--cooldown-seconds must be zero or greater")

    if args.cooldown_seconds:
        print(
            json.dumps(
                {"event": "cooldown", "seconds": args.cooldown_seconds}, ensure_ascii=True
            )
        )
        time.sleep(args.cooldown_seconds)

    values = load_env(Path(__file__).with_name(".env"))
    credentials = {
        "primary": (
            values["TONGTOOL_ERP2_PRIMARY_KEY"],
            values["TONGTOOL_ERP2_PRIMARY_SECRET"],
        ),
        "secondary": (
            values["TONGTOOL_ERP2_SECONDARY_KEY"],
            values["TONGTOOL_ERP2_SECONDARY_SECRET"],
        ),
    }
    clients = {name: McpClient(*pair) for name, pair in credentials.items()}
    sequence = list(clients) if args.mode == "connectivity" else ["primary"] * args.count
    if args.mode == "alternate":
        sequence = ["primary" if index % 2 == 0 else "secondary" for index in range(args.count)]
    if args.mode == "discriminate":
        sequence = ["primary"] * 5 + ["secondary"]
    summary: dict[str, int] = {
        "total": 0,
        "success": 0,
        "unauthorized": 0,
        "rate_limited": 0,
        "other": 0,
    }
    for index, name in enumerate(sequence, start=1):
        started = time.time()
        kind, code = summarize(clients[name].call())
        summary["total"] += 1
        if code == "200":
            summary["success"] += 1
        elif code == "524":
            summary["unauthorized"] += 1
        elif code == "526":
            summary["rate_limited"] += 1
        else:
            summary["other"] += 1
        print(
            json.dumps(
                {"request": index, "app": name, "time": round(started, 3), "kind": kind, "code": code},
                ensure_ascii=True,
            )
        )
    print(json.dumps({"event": "summary", **summary}, ensure_ascii=True))


if __name__ == "__main__":
    main()
