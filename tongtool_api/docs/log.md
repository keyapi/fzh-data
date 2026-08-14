---
okf: v0.1
type: Log
title: Tongtool ERP2.0 Foundation Change Log
description: Change history for the Tongtool ERP2.0 documentation bundle.
tags: [tongtool, erp2]
timestamp: 2026-08-13
---

# Change Log

## 2026-08-14
- Documented that Cursor does not yet register Tongtool MCP; agents should use `mcp_http.py` + `tongtool_api/.env`. Cursor MCP install is a separate PR.

## 2026-08-13 - Initial Foundation

- Added dual-App local credential pattern and Codex MCP setup guidance.
- Recorded official MCP behavior and ERP2 permission/error semantics.
- Cross-checked the private EN integration and public Go SDK.
- Added order/package guidance, tool-area catalog, lessons, and a rate-limit experiment record.
- Corrected rate-limit scope after a live dual-App MCP discriminator test: the two Apps share one five-calls-per-minute quota.
- Added a reproducible discriminator command with pre-initialization cool-down and aggregate-only JSON output.
