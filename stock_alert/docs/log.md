---
okf: v0.1
type: Log
title: stock_alert 变更日志
description: stock_alert 模块的建立、口径调整与容错修复时间线
tags: [stock-alert, changelog, dingtalk, tongtool]
---

# 变更日志

## 2026-11-17

- 根据用户反馈调整样式：低库存由3条文字+独立附件改为1张分仓汇总卡，卡底同时下载新增18行/全量411行；采购入库按仓、名称、SKU、数量分段，过长时同卡下载完整明细，不拆条。当前65项测试通过。新版低库存1卡、入库1条已实推，均errcode=0；两个下载链接已核对，新增18行/全量411行。

- 用户确认后正式发送：3条低库存明细、1张新增Excel卡片、1条昨日入库提醒，服务端响应均为errcode=0；注册两项任务，自11月18日起每日09:23/09:47运行。

- 阶段2：低库存逐条按仓分片、名称缓存接线、仅新增 Excel，新增独立昨日采购入库任务（09:47）。
- 入库采用每条正增量，排除创建/无变化、负向事件；增加输入/采用/跳过原因对账。
- 历史接口触顶/错误响应拒绝使用；Excel 写入失败不阻断已发送文字。
- 实测13504个商品，首次刷新30.4分钟；新增非阻塞缓存锁，避免09:23/09:47两任务重叠刷新名称。
- 验收：69项单测通过；真实低库存411、新增18、昨日采购入库45件；3条分片均低于20000字节，Excel6/4/8行。库存回退分页约束100，触顶报错。
- Claude 中断时主要代码已写、尚未验收；Codex 接续补回归和真实数据只读预览。

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
- **2026-11-04** 迁移：通途 **MCP 网关自 2026-11-03 起对全部 app_key 返回 `524 unknown不在白名单`**。
  取数改为 **OpenAPI 直连**（`tongtool_api/openapi_client.py`：`devApp/appToken` →
  `partnerOpenInfo/getAppBuyerList` → `POST /openapi/tongtool/stocksQuery`），不再依赖 MCP；
  新增「524 失败告警附出口 IP + 排查提示」。
- **2026-11-04** 主数据源改为 **EN `Tongtool Stock Latest`**（EN 每日同步 14 仓、字段一致）：
  新增 `en_client.py` + **新鲜度门禁**（`Tongtool Stock Run` 最近 `job=stock_snapshot` 必须
  `Success`/`complete=1`，且 `snapshot_at` 为今天；否则只发「库存同步未完成」）；
  通途 OpenAPI 直连保留为**回退**（EN 不可达时启用）。
