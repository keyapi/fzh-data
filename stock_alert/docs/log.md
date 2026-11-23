---
okf: v0.1
type: Log
title: stock_alert 变更日志
description: stock_alert 模块的建立、口径调整与容错修复时间线
tags: [stock-alert, changelog, dingtalk, tongtool]
---

# 变更日志

## 2026-11-18

- 低库存卡片不再显示低库存总数，只保留今日新增；今日无新增时不推送（不生成图片/Excel）。当前 93 项测试通过。

- 采购入库按仓拆分推送：**只为有入库的仓发卡片**（最多 3 张），每张卡只含该仓明细和该仓 Excel；
  空仓不推送，三个仓都为 0 时整次不推送。当前 93 项测试通过。

- 卡片布局微调：低库存总数/今日新增移入标题下方并去掉统计框；入库去掉顶部统计框和
  「分仓明细」标题，直接进入各仓明细。

- 采购入库改为白天 **10:00 / 14:00 / 17:00** 三次实时检查：EN `stock_change` 每天约 05:53 才同步一次，
  改为直连通途 `/openapi/tongtool/stocksChangeDetailQuery`；按「上次成功检查 → 本次运行」的增量窗口查询，
  只取采购单 `relatedVoucherType=02` 且 `availableStockIncrease > 0`；窗口状态存
  `stock_alert_output/inbound_state.json`，dry-run/发送失败不推进。当前 89 项测试通过。

- 低库存图片卡片改为按仓列出**今日新增 SKU**（SKU、产品名称、当前库存），
  去掉「分仓明细」标题和在途合计；新增条数不设上限。某仓昨日基线缺失时提示
  「无法判断今日新增」，不把该仓全量低库存当成新增。
- 采购入库图片卡片取消「每仓 6 条 / 总计 18 条」上限，有多少显示多少；
  文本回退仍保留 20000 字节保护，超限时退为分仓汇总 + Excel。
- 当前 82 项测试通过。

## 2026-11-17

- 新增**图片卡片模式**（默认 `STOCK_ALERT_CARD_MODE=image`）：`card_image.py` 用 Pillow 渲染
  蓝底居中标题、统计框、分仓明细的 PNG，上传后由现有群机器人发图 + 原生下载按钮，无需企业内部应用。
  单按钮 ActionCard 改为独立跳转（`single_jump=False`），点图片不再触发下载；采购入库数量单位改为「个」。
  当前 80 项测试通过。

- 新增可选互动卡片发送层 `card.py`：配置企业内部应用 + 两个已发布模板后，低库存/入库可做居中标题、蓝底头部、统计框和通栏按钮；配置缺失或发送失败自动回退。新增 `test_card.py`，当时 75 项测试通过。

- 根据用户反馈调整样式：低库存由3条文字+独立附件改为1张分仓汇总卡，卡底同时下载新增18行/全量411行；采购入库按仓、名称、SKU、数量分段，有入库即同卡下载完整明细，不拆条。当前65项测试通过。新版低库存1卡、入库1条已实推，均errcode=0；两个下载链接已核对，新增18行/全量411行。

- 用户确认后正式发送：3条低库存明细、1张新增Excel卡片、1条昨日入库提醒，服务端响应均为errcode=0；注册两项任务，自11月18日起每日09:23/09:47运行。

- 阶段2：低库存逐条按仓分片、名称缓存接线、仅新增 Excel，新增独立昨日采购入库任务（09:47）。
- 入库采用每条正增量，排除创建/无变化、负向事件；增加输入/采用/跳过原因对账。
- 历史接口触顶/错误响应拒绝使用；Excel 写入失败不阻断已发送文字。
- 实测13504个商品，首次刷新30.4分钟；新增非阻塞缓存锁，避免09:23/09:47两任务重叠刷新名称。
- 阶段2首版验收：69项单测通过；真实低库存411、新增18、昨日采购入库45件；3条分片均低于20000字节，Excel6/4/8行。库存回退分页约束100，触顶报错。
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
