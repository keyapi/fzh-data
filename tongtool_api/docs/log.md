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
- 复核 PO021704：PO 头 10-14，实际 38 行 10-14 + 12 行 10-19；窄窗口漏 12/50。新增 `receipt_collector.py`（重叠窗口 + 仓库外缓存 + 弱键显式去重）与 6 项测试；对账增加 `not_collected`、弱身份标记。本地 83 项测试通过。
- 新增 `collect_receipts_cli.py`；跑 09-01–10-26（14 天窗/2 天重叠）：166 输入 → 150 唯一 + 16 重叠重复；12 PO / 113 SKU；无截断。8 项采集/对账新增测试，共 84 项本地测试通过。
- 新增 `supply_chain_visibility/receipt_coverage.py` 并接 `--coverage-out`：150 条唯一行全部 `unknown`（`missing_stable_id`），全部无 UOM/时区；未自动抵扣。共 86 项本地测试通过。

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
