---
okf: v0.1
type: Guide
title: Tongtool MCP Setup
description: Secure local setup for Tongtool ERP2.0 MCP in Codex and Cursor.
tags: [tongtool, mcp, cursor, codex, credentials]
timestamp: 2026-08-14
---

# Tongtool MCP Setup

## Architecture

The repository distributes instructions, the Skill, `.env.example`, and setup scripts. Real credentials remain local. A colleague who clones and trusts the project automatically receives the knowledge and Skill, but must obtain authorized App credentials and register them **per host**. Secrets cannot and should not propagate through git.

| Host | Config file | Setup command |
|------|-------------|----------------|
| Codex | `~/.codex/config.toml` | `powershell -ExecutionPolicy Bypass -File tongtool_api/setup_codex_mcp.ps1` |
| Cursor | `~/.cursor/mcp.json` | `uv run python tongtool_api/setup_cursor_mcp.py` |

Cursor project `.cursor/` is **gitignored**. Clone will not create a project `mcp.json`. There is no Cursor Marketplace listing and no Agent tool that pops an “install MCP” prompt. Writing the user-level file is the install.

## Local Setup (both hosts)

1. Copy `tongtool_api/.env.example` to `tongtool_api/.env`.
2. Fill at least the primary ERP2.0 App Key/Secret pair.
3. Run the host-specific command in the table above.
4. **Codex:** fully quit and restart. Opening a new task is not sufficient.
5. **Cursor:** check the Agent tool catalog for `user-tongtool_erp2_primary`. 2026-08-14 this machine hot-loaded in the same chat. If missing: Customize → MCP → enable `tongtool_erp2_primary`, then reload the window or start a new chat.
6. Verify with a single read-only call such as `erp2_product_goodsquery` (`productType` required). Stop after one success; quota is 5 ERP2 calls/minute merchant-wide.

Daily use: enable **primary only**. A second server with the same URL may not appear in Cursor’s Available servers (observed 2026-08-14). Keep secondary for Codex rate-limit experiments, not for routine Cursor queries.

## Transport

- URL: `https://mcp.tongtool.com/mcp`
- Transport: Streamable HTTP
- Headers: `x-tongtool-access-key` and `x-tongtool-secret-key`

Do not add real headers to committed project config. Cursor remote MCP does not load `envFile`; the setup script copies values from `tongtool_api/.env` into the user config.

## Agent host detection

1. If `user-tongtool_erp2_primary` or Codex `tongtool_erp2_primary` / `erp2_product_goodsquery` is already in the tool catalog → call MCP. Do not also call `mcp_http.py`.
2. If this is Cursor and those tools are missing → tell the user, run `setup_cursor_mcp.py`, re-check the catalog. Do not silently HTTP-fallback.
3. CLI, pytest, and CI use `tongtool_api/mcp_http.py` on purpose.

Cursor server ids use a `user-` prefix on the `mcp.json` key.
