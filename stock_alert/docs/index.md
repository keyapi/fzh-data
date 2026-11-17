---
okf: v0.1
type: Index
title: stock_alert 通途库存提醒
description: 单卡低库存汇总、同卡新增/全量下载及分段采购入库提醒。
---
# stock_alert 文档索引

| 需要 | 文档 |
|---|---|
| 操作与配置 | [README](../README.md) |
| 接口、口径与排障 | [参考](reference/low-stock-alert.md) |
| 变更历史 | [日志](log.md) |

## 代码入口

- `en_client.py`：EN 最新库存、新鲜度门禁、昨日基线、库存事件及截断保护。
- `client.py`：通途 OpenAPI 库存回退；认证与限流复用 `tongtool_api/openapi_client.py`。
- `names.py`：SKU 产品名称缓存，周更全量、日补缺失。
- `scan.py`：低库存扫描与今日新增标记。
- `inbound.py`：仅正向采购入库事件汇总及跳过原因计数。
- `excel.py`：分仓新增/全量低库存Excel，以及长入库消息的完整明细。
- `notify.py`：单卡分仓汇总、同卡下载按钮、独立分段入库；不拆消息。
- `cli.py`：`run` / `inbound` / `probe`。
- `scripts/run_stock_alert.py` / `run_stock_inbound.py`：两条独立任务包装及失败告警。
- `scripts/install_stock_alert_schedule.ps1`：09:23 / 09:47 Windows 任务。
