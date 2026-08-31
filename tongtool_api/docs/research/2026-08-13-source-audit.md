---
okf: v0.1
type: Research
title: Tongtool ERP2 Source Audit 2026-08-13
description: Cross-check of official docs, MCP behavior, private EN integration, and public Go SDK.
tags: [tongtool, erp2, mcp, source-audit]
timestamp: 2026-08-13
---

# Source Audit - 2026-08-13

## Sources Compared

1. Official AI service onboarding and dynamic API documentation.
2. Live official MCP server and generated schemas.
3. Private keyapi/tongtool_integration ERPNext application.
4. Public hiscaler/tongtool Go SDK.

## Findings

- MCP is the simplest Agent access path: credentials are headers and no local signing client is required.
- Direct API implementations agree on token acquisition, merchant lookup, signing, merchantId injection, and the core 519/523/524/525/526/527 error model.
- The Go SDK has broader ERP2 domain coverage and explicit request models. It retries HTTP 429 or business code 526, optionally waiting until the next minute boundary. It does not declare a fixed 5/minute quota.
- The EN app defaults api_rate_limit to 5/minute and enforces it locally per instantiated client. The public Go SDK README independently says all Tongtool API calls are limited to five per minute. A live two-App MCP discriminator run confirms this merchant's quota is shared across Apps.
- Official docs are dynamic and have previously been incomplete or inconsistent. Generated MCP schemas and live 525 validation are valuable evidence, but observed behavior must still be documented with a date.
- Tool catalogs are global rather than permission-filtered. ERP3, Listing, WMS, and YMS calls tested with an ERP2 App returned 524.

## Confidence Rules

Use this evidence order for implementation decisions: successful minimal live call, current MCP schema, current official endpoint detail, two independent client implementations, then historical local assumptions. Preserve disagreements instead of silently choosing one.
