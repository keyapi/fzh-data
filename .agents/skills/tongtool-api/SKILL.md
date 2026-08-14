---
name: tongtool-api
description: >
  通途 ERP2.0 API 与官方 MCP 接入。用户提到通途API、Tongtool API、通途 MCP、
  Tongtool MCP、ERP2.0、通途订单、通途包裹、P号、通途库存、通途采购、
  ordersquery、packagesquery、通途限流时触发。用于查询、调研、自动化设计和排错。
  不要用于 ERP3.0 或独立的“物流平台”API权限族。
metadata:
  module: tongtool_api
  docs: tongtool_api/docs/index.md
  compatibility: Codex remote MCP; credentials stay in local user configuration
  updated: 2026-08-13
---

# 通途 ERP2.0 API / MCP

## 必须先做

1. 阅读 tongtool_api/AGENT_HANDOFF.md。
2. 按 tongtool_api/docs/reference/mcp-setup.md 检查 MCP 和本机凭证状态。
3. 先用基础数据解析账号、仓库等代码，再做订单、包裹、库存或采购查询。
4. 默认只读、小日期窗口、小页数；订单与包裹结果不得原样写入 git。
5. 创建、更新、发货、入库、出库等写操作必须让用户确认对象和范围。

## 判断错误

- 200: 成功。
- 524: App 未授权该接口或权限族。
- 525: 参数不完整或不合法，通常说明认证和权限已通过。
- 526: 服务端超频，停止密集重试并退避。
- MCP -32602: 工具输入未通过 MCP schema。

当前按同一商户合计最多 5 次 ERP2 业务调用/分钟限流；2026-08-13 已通过双 App MCP 判别实验确认：主 App 的 5 次成功后，第二 App 第 1 次即触发 526。MCP 不会绕开通途 API 限额。完整证据见 tongtool_api/docs/research/2026-08-13-rate-limit-experiment.md。

**Cursor 当前未注册通途 MCP。** Codex 可用 `tongtool_api/setup_codex_mcp.ps1` 写入 `~/.codex/config.toml`。在 Cursor 里查货品/订单：用 `tongtool_api/.env` + `tongtool_api/mcp_http.py`（或 `tongtool_order_cost/scripts/lookup_tongtool_sku.py`）。把 MCP 装进 Cursor 是后续独立 PR；触发词：「给 Cursor 安装通途 MCP」「Cursor 没有 tongtool MCP」。
