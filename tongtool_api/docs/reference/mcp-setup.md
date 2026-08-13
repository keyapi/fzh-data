---
okf: v0.1
type: Guide
title: Tongtool MCP Setup
description: Secure local and team setup for two Tongtool ERP2.0 MCP applications in Codex.
tags: [tongtool, mcp, codex, credentials]
timestamp: 2026-08-13
---

# Tongtool MCP Setup

## Architecture

The repository distributes instructions, the Skill, .env.example, and a setup script. Real credentials remain local. A colleague who clones and trusts the project automatically receives the knowledge and Skill, but must obtain authorized App credentials and register them on that machine. Secrets cannot and should not propagate through git.

## Local Setup

1. Copy tongtool_api/.env.example to tongtool_api/.env.
2. Fill one or both ERP2.0 App Key/Secret pairs.
3. Run: powershell -ExecutionPolicy Bypass -File tongtool_api/setup_codex_mcp.ps1
4. Fully quit and restart Codex. Opening a new task is not sufficient.
5. Verify tongtool_erp2_primary and, when configured, tongtool_erp2_secondary are available.

The script manages a marked block in user-level ~/.codex/config.toml. Credentials are written there because Codex must send two custom HTTP headers to the remote MCP endpoint. The local .env and user config are both outside git tracking.

## Transport

- URL: https://mcp.tongtool.com/mcp
- Transport: Streamable HTTP
- Headers: x-tongtool-access-key and x-tongtool-secret-key

Do not add real headers to project .codex/config.toml. Project config is committed and shared.
