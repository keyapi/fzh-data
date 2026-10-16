---
okf: v0.1
type: Index
title: stock_alert 通途低库存汇总推送
description: 按仓库查通途库存，把可用库存低于阈值的 SKU 按仓汇总后推送到钉钉群机器人。
tags: [stock-alert, tongtool, erp2, dingtalk, inventory]
---

# stock_alert

按仓库查询通途 ERP2 库存（`erp2_stocks_stocksquery`），把**可用库存 < 阈值**（默认 5）
的 SKU 按仓汇总，用钉钉自定义机器人推送一条**仅汇总数量**的提醒。

## 口径（已与用户确认）

- **判断口径**：`availableStockQuantity`（可用库存）< 阈值，**且排除「可用=0 且 在途=0」的死库存**
  （既没货也无在途，一般是历史/停用 SKU）；正文**附带在途数量**提示。
- **监控仓库**：`美中-FZH-DANEEY`、`美东-CENTRADE`、`波兰-FZHPoland-covers`。
- **扫描范围**：整仓全量 SKU（按仓库分页拉取，不是固定清单）。
- **消息形式**：正文给每仓「N 个 SKU 可用<5（在途合计 M 件）」；**总数 > 10 时**另发一张
  **按仓库分 sheet 的 Excel**（ActionCard 下载卡片），≤10 时明细直接写进正文。

## 快速开始

```bash
# 离线全链路：不调 API、不发群，只看汇总正文
uv run python -m stock_alert.cli run --mock --dry-run

# 真查单仓（只出正文，不推送）
uv run python -m stock_alert.cli run --warehouses "美中-FZH-DANEEY"

# 三仓全量 → 真推
uv run python -m stock_alert.cli run --notify

# 单测
uv run pytest stock_alert/tests -q
```

## 目录

- `client.py` —— 通途 ERP2 库存客户端（分页 + 限流退避）
- `scan.py` —— 过滤 / 按仓聚合（纯函数，离线可测）
- `excel.py` —— 生成按仓库分 sheet 的低库存明细 Excel
- `notify.py` —— 生成正文 + 按数量分档推钉钉（正文明细 / Excel 卡片）
- `cli.py` —— `run` / `probe` 入口
- `scripts/run_stock_alert.py` —— 无人值守包装（失败告警兜底）
- `scripts/install_stock_alert_schedule.ps1` —— Windows 定时任务注册

详见 [reference/low-stock-alert.md](reference/low-stock-alert.md)。
