---
okf: v0.1
type: Guide
title: Tongtool ERP2.0 Agent Handoff
description: Operating rules and known facts for agents using Tongtool ERP2.0 direct open API (MCP not used for business queries).
tags: [tongtool, erp2, mcp, handoff]
timestamp: 2026-08-14
---

# Tongtool ERP2.0 Agent Handoff

## Scope

- Current system: Tongtool ERP2.0 only. Do not use ERP3.0 assumptions.
- **Preferred access（用户明确要求）：直连 Tongtool open API**，base `https://open.tongtool.com/api-service`；认证流程见下方 Sources 与 `tongtool_integration/api/client.py`。**Agent 不要用通途 MCP 查订单/库存/包裹**；MCP 仅保留历史安装记录作排错参考，不作为业务取数通道。
- Current automation interests: orders, merchant packages, inventory, purchasing, and related base data.
- Out of scope: the separate Logistics Platform permission family. It is not exposed by the observed MCP tool catalog.

## Before Any Call

1. Read docs/reference/mcp-setup.md and docs/reference/authentication-and-errors.md.
2. 业务取数一律走直连 open API（脚本/HTTP）。不要再为了查订单/库存去装或调用 MCP；MCP 403/524 是工具层问题，不能据此判断 App 权限。
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

## Sources

- Official onboarding: https://open.tongtool.com/guides.html#/ai-service-onboarding
- Official API docs: https://open.tongtool.com/apiDoc.html
- Private EN integration: https://github.com/keyapi/tongtool_integration
- Community Go SDK: https://github.com/hiscaler/tongtool

Detailed navigation is in docs/index.md.
