---
okf: v0.1
type: Guide
title: Tongtool ERP2.0 Agent Handoff
description: Operating rules and known facts for agents using Tongtool ERP2.0 MCP and APIs.
tags: [tongtool, erp2, mcp, handoff]
timestamp: 2026-08-14
---

# Tongtool ERP2.0 Agent Handoff

## Scope

- Current system: Tongtool ERP2.0 only. Do not use ERP3.0 assumptions.
- Preferred access: official remote MCP at https://mcp.tongtool.com/mcp. Register separately for Codex (`setup_codex_mcp.ps1`) and Cursor (`setup_cursor_mcp.py`). Cursor tools appear as `user-tongtool_erp2_primary`.
- Current automation interests: orders, merchant packages, inventory, purchasing, and related base data.
- Out of scope: the separate Logistics Platform permission family. It is not exposed by the observed MCP tool catalog.

## Before Any Call

1. Read docs/reference/mcp-setup.md and docs/reference/authentication-and-errors.md.
2. If the host tool catalog has no Tongtool MCP, run the host setup script and stop silent HTTP fallback. CLI/scripts may keep using mcp_http.py.
3. Confirm the requested operation is read-only. For create/update/ship/stock-in/out actions, show scope and obtain explicit user confirmation.
4. Keep page sizes and date windows small during discovery. Do not log full order/package payloads because they contain PII.
5. Treat official docs as useful but fallible; cross-check tool schema, live validation, the EN private app, and hiscaler/tongtool.
6. Report input, success, skipped, failed, and reasons for any batch workflow. Never silently discard unmatched records.

## Stable Findings

- The MCP server identified itself as tongtool-openapi-mcp 0.1.0, protocol 2025-11-25, with 212 globally listed tools on 2026-08-13.
- Tool listing is not permission-filtered. Unauthorized families return Tongtool business code 524.
- Code 525 usually proves the endpoint passed authorization but request parameters were invalid or incomplete.
- Orders require a valid short accountCode such as RSUS; a display account name is not interchangeable.
- Merchant package query uses assign/despatch time fields observed in the MCP schema; the old EN wrapper's updateTimeFrom/To assumption should not be copied without retesting.
- A 2026-08-13 live MCP discriminator run proved that the two Apps share one 5-calls/minute bucket: after five primary-App calls returned 200, the secondary App's first call returned 526. MCP does not bypass the Tongtool API quota. Throttle the merchant-wide workload, not each App independently.
- A 2026-08-14 Cursor install wrote `~/.cursor/mcp.json` from `tongtool_api/.env`. Same chat loaded `user-tongtool_erp2_primary` as ready and `erp2_product_goodsquery` returned business code 200 for `BNFBAvelvetgray60`. Secondary with the same URL did not appear in Available servers. No Marketplace install prompt exists. Details: docs/research/2026-08-14-cursor-mcp-install.md.
- Reproduce the rate-limit discriminator only when needed: `uv run python tongtool_api/test_mcp_rate_limit.py --mode discriminate --cooldown-seconds 65`. It waits before any MCP initialization, queries only one warehouse page, emits aggregate JSON, and never prints credentials or returned warehouse records.
- **HTTP 500 with `NoSuchMethodError: com.ibiz.openapi.common.Context.getIsNewApp()` is a Tongtool-side gateway deployment fault**, not an App/permission/parameter problem. Signature: `appToken` / `getAppBuyerList` still return 200, invalid parameters still return code 525, wrong token returns 401/523, but any valid business request returns HTTP 500 (text/html) in 0.2–0.4s. Reproduced across 3 Apps / 2 merchants / 2 egress networks on 2026-11-24 (recovered before 18:00 the same day). Do not rotate keys; raise a ticket with the exception text and the three counter-checks. Details: `docs/solutions/integration-issues/tongtool-openapi-gateway-500-nosuchmethod.md`.
- **Do not diagnose through EN's `TongToolClient`**: it treats HTTP 500 as a network error and retries with `retry_delay_minutes=5` backoff (5/10/20 min, ~35 min per call). Use plain `requests` with `timeout=20` to inspect raw responses.
- Order-cost sync (`tongtool_integration`) must never let `NaN` reach decimal columns: the weight-template backfill leaked NaN (`NaN != 0` is true) and any valid BOM request then failed with `nan can not be used with MySQL`. See `docs/solutions/integration-issues/pandas-nan-frappe-decimal-order-cost.md` (fixed in PR keyapi/tongtool_integration#29).

## Sources

- Official onboarding: https://open.tongtool.com/guides.html#/ai-service-onboarding
- Official API docs: https://open.tongtool.com/apiDoc.html
- Private EN integration: https://github.com/keyapi/tongtool_integration
- Community Go SDK: https://github.com/hiscaler/tongtool

Detailed navigation is in docs/index.md.
