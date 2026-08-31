---
okf: v0.1
type: Research
title: 2026-08-14 Cursor Tongtool MCP install
description: Live Cursor registration of Tongtool ERP2 MCP via user mcp.json and one goodsQuery.
tags: [tongtool, erp2, mcp, cursor]
timestamp: 2026-08-14
---

# 2026-08-14 Cursor Tongtool MCP install

## Setup

- Script: `uv run python tongtool_api/setup_cursor_mcp.py`
- Source: `tongtool_api/.env` (gitignored)
- Target: `~/.cursor/mcp.json` (user-level; not in this repo)
- Result printed: registered `tongtool_erp2_primary` and `tongtool_erp2_secondary`
- Header names present: `x-tongtool-access-key`, `x-tongtool-secret-key`; URL `https://mcp.tongtool.com/mcp`
- Unit tests: `uv run pytest tongtool_api/tests/test_setup_cursor_mcp.py -q` → 5 passed

## Cursor tool catalog (same chat, no window reload)

- `user-tongtool_erp2_primary` status: `ready`
- `erp2_product_goodsquery` listed
- `user-tongtool_erp2_secondary` **not** in Available servers after the write (primary + Cursor built-ins only)
- No Marketplace / “Add to Cursor” prompt appeared; writing `mcp.json` was the install

## Live call (1 ERP2 business request)

- Server: `user-tongtool_erp2_primary`
- Tool: `erp2_product_goodsquery`
- Args: `productType=0`, `pageNo=1`, `pageSize=5`, `skus=["BNFBAvelvetgray60"]`
- Tongtool business `code`: 200
- Returned `sku`: `BNFBAvelvetgray60`
- Returned `productName`: `三角无扣 60CM 灰色 荷兰绒 靠枕CEN`
- Returned alias `skuLabel`: `BNvelvetgray60fba`

Do not repeat this call to “double-check”; merchant quota is 5 ERP2 calls/minute shared across Apps.

## Conclusions

1. Cursor and Codex MCP registrations are independent. Codex setup does not install Cursor tools.
2. Repo `.cursor/` is gitignored, so project `mcp.json` cannot ship via git.
3. Cursor Agent has no MCP-install dialog tool. Skills must instruct `setup_cursor_mcp.py` instead of waiting for a prompt.
4. This session hot-loaded primary after the JSON write. If a later session does not, enable the server in Customize → MCP and reload.
5. Prefer the Cursor MCP tool in Agent chat once `ready`. Keep `mcp_http.py` for CLI/scripts.
