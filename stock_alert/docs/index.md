---
okf: v0.1
type: Index
title: stock_alert 通途库存提醒
description: 低库存逐条明细、今日新增 Excel 和独立采购入库提醒。
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
- `excel.py`：按仓输出新增 SKU 与产品名称。
- `notify.py`：全部明细按字节分片，文字先发，新增 Excel 卡片后发。
- `cli.py`：`run` / `inbound` / `probe`。
- `scripts/run_stock_alert.py` / `run_stock_inbound.py`：两条独立任务包装及失败告警。
- `scripts/install_stock_alert_schedule.ps1`：09:23 / 09:47 Windows 任务。
