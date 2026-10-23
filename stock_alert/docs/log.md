---
okf: v0.1
type: Log
title: stock_alert 变更日志
description: stock_alert 模块的建立、口径调整与容错修复时间线
tags: [stock-alert, changelog, dingtalk, tongtool]
---

# 变更日志

- **2026-10-13** 初版：整仓扫描（`erp2_stocks_stocksquery`）+ 可用<5 汇总 +
  按仓库分 sheet 的 Excel + 钉钉推送；`send_dingtalk`/`send_file_card` 增加可选 `webhook`/`secret`。
- **2026-10-13** 实测：只给 `warehouseName` 即可整仓列举；`pageSize` 上限 100，`datas.array` 无 total。
- **2026-10-14** 上线：正式推送成功（ActionCard + Excel 上传 ERPNext）。
- **2026-10-14** 口径收紧：排除「可用=0 且 在途=0」的死库存，不再统计。
- **2026-10-15** 定时：注册 `FZH-StockAlert-daily`，每日 09:23。
- **2026-10-19** 容错：通途 MCP 网关返回 `502 Bad Gateway` 导致整跑失败 →
  对 HTTP 5xx / 网络错误加指数退避重试（4xx 仍直接抛）。
- **2026-10-20** 容错：`tools/call` 返回 HTTP 400 `Server not initialized`（服务端丢会话）→
  `McpClient` 检测到后**重建会话再重试一次**，并纳入瞬时可重试分类。
