---
okf: v0.1
type: Log
title: Tongtool ERP2.0 Foundation Change Log
description: Change history for the Tongtool ERP2.0 documentation bundle.
tags: [tongtool, erp2]
timestamp: 2026-08-13
---

# Change Log

## 2026-10-26
- 实测采购入库查询的 warehousingDate、PO/SKU/仓与数量字段；新增有界只读适配器与合成测试，保留无稳定流水 ID、无单位、来源时区未证的限制。补录库存快照前后事件的防重复/防漏计契约，不启用自动入库。

## 2026-08-14
- Added Cursor MCP registration: `setup_cursor_mcp.py` writes user-level `~/.cursor/mcp.json`. Same-chat `erp2_product_goodsquery` returned business 200. Secondary with the same URL did not appear in Cursor Available servers. No Marketplace install prompt.
- HTTP `mcp_http.py` remains the CLI/script channel, not a silent substitute when Cursor MCP tools are missing.

## 2026-08-13 - Initial Foundation

- Added dual-App local credential pattern and Codex MCP setup guidance.
- Recorded official MCP behavior and ERP2 permission/error semantics.
- Cross-checked the private EN integration and public Go SDK.
- Added order/package guidance, tool-area catalog, lessons, and a rate-limit experiment record.
- Corrected rate-limit scope after a live dual-App MCP discriminator test: the two Apps share one five-calls-per-minute quota.
- Added a reproducible discriminator command with pre-initialization cool-down and aggregate-only JSON output.
