---
name: tongtool-api
description: >
  通途 ERP2.0 **直连 open API**（不要用 MCP）。用户提到通途API、Tongtool API、ERP2.0、
  通途订单、通途包裹、P号、通途库存、通途采购、ordersQuery、packagesQuery、通途限流时触发。
  用于查询、调研、自动化设计和排错。
  不要用于 ERP3.0 或独立的“物流平台”API权限族。
metadata:
  module: tongtool_api
  docs: tongtool_api/docs/index.md
  compatibility: direct open API; credentials stay in local .env
  updated: 2026-08-14
---

# 通途 ERP2.0 直连 API（不用 MCP）

## 必须先做

1. 阅读 tongtool_api/AGENT_HANDOFF.md。
2. **一律走直连 open API**（`https://open.tongtool.com/api-service`，认证见 handoff 与 `tongtool_integration/api/client.py`）。
   **不要再调用通途 MCP 查业务数据**；MCP 403/524 是工具层问题，不能据此判断 App 权限。
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
