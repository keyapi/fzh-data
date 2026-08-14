# -*- coding: utf-8 -*-
"""Register Tongtool ERP2 MCP servers in Cursor user-level mcp.json.

Cursor project `.cursor/` is gitignored, so clone cannot ship MCP config.
This writes ~/.cursor/mcp.json (same credential source as Codex: tongtool_api/.env).
Never prints key/secret values.
"""
from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parents[1]
if str(REPO_ROOT) not in sys.path:
    sys.path.insert(0, str(REPO_ROOT))

from tongtool_api.mcp_http import ENV_PATH, load_env

MCP_URL = "https://mcp.tongtool.com/mcp"
PRIMARY_NAME = "tongtool_erp2_primary"
SECONDARY_NAME = "tongtool_erp2_secondary"
HEADER_KEY = "x-tongtool-access-key"
HEADER_SECRET = "x-tongtool-secret-key"


def default_mcp_json_path() -> Path:
    return Path.home() / ".cursor" / "mcp.json"


def _pair(env: dict[str, str], key_name: str, secret_name: str) -> tuple[str, str] | None:
    key = env.get(key_name, "").strip()
    secret = env.get(secret_name, "").strip()
    if (key and not secret) or (secret and not key):
        raise ValueError(f"{key_name} and {secret_name} must be configured together.")
    if not key:
        return None
    return key, secret


def credential_servers(env: dict[str, str]) -> dict[str, dict]:
    servers: dict[str, dict] = {}
    primary = _pair(env, "TONGTOOL_ERP2_PRIMARY_KEY", "TONGTOOL_ERP2_PRIMARY_SECRET")
    secondary = _pair(env, "TONGTOOL_ERP2_SECONDARY_KEY", "TONGTOOL_ERP2_SECONDARY_SECRET")
    if primary:
        servers[PRIMARY_NAME] = {
            "url": MCP_URL,
            "headers": {HEADER_KEY: primary[0], HEADER_SECRET: primary[1]},
        }
    if secondary:
        servers[SECONDARY_NAME] = {
            "url": MCP_URL,
            "headers": {HEADER_KEY: secondary[0], HEADER_SECRET: secondary[1]},
        }
    if not servers:
        raise ValueError("No Tongtool ERP2 credentials configured.")
    return servers


def merge_mcp_config(existing: dict, servers: dict[str, dict]) -> dict:
    merged = dict(existing)
    current = dict(merged.get("mcpServers") or {})
    current.update(servers)
    merged["mcpServers"] = current
    return merged


def read_existing(path: Path) -> dict:
    if not path.exists():
        return {}
    raw = path.read_text(encoding="utf-8").strip()
    if not raw:
        return {}
    data = json.loads(raw)
    if not isinstance(data, dict):
        raise ValueError(f"{path} is not a JSON object.")
    return data


def write_mcp_json(path: Path, data: dict) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    text = json.dumps(data, ensure_ascii=False, indent=2) + "\n"
    path.write_text(text, encoding="utf-8")


def register(env_path: Path = ENV_PATH, mcp_json_path: Path | None = None) -> tuple[Path, list[str]]:
    target = mcp_json_path or default_mcp_json_path()
    if not env_path.exists():
        raise FileNotFoundError(
            f"Missing {env_path}. Copy tongtool_api/.env.example to tongtool_api/.env."
        )
    servers = credential_servers(load_env(env_path))
    merged = merge_mcp_config(read_existing(target), servers)
    write_mcp_json(target, merged)
    return target, list(servers)


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description="Register Tongtool ERP2 MCP in Cursor user mcp.json")
    parser.add_argument("--env-file", type=Path, default=ENV_PATH)
    parser.add_argument("--mcp-json", type=Path, default=None)
    args = parser.parse_args(argv)
    try:
        target, names = register(env_path=args.env_file, mcp_json_path=args.mcp_json)
    except (FileNotFoundError, ValueError, json.JSONDecodeError) as exc:
        print(f"ERROR: {exc}", file=sys.stderr)
        return 1
    print(f"Registered {len(names)} Tongtool ERP2 MCP server(s) in {target}: {', '.join(names)}")
    print("Enable them in Cursor Customize → MCP. If tools do not appear, reload the window.")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
