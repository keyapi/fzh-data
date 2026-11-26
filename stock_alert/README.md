---
type: Reference
title: stock_alert 通途库存提醒
---
# stock_alert

三仓低库存汇总卡片（同卡下载新增/全部明细），以及独立的昨日采购入库提醒。
默认仓库：美中-FZH-DANEEY、美东-CENTRADE、波兰-FZHPoland-covers。

## 低库存预警

标题「低库存预警」。按地区两个任务：

- **波兰**：每日 14:00，仅 `波兰-FZHPoland-covers`；
- **美中 + 美东**：每日 20:00，共用一张卡片，只显示有新增的仓。

默认读 EN `Tongtool Stock Latest`，要求今日快照同步成功；
EN 不可达时回退通途 OpenAPI。可用库存 < 5，排除可用=0 且在途=0。
**只提醒今日新增的低库存 SKU**：今日快照 vs 昨日历史，昨日 ≥5 或昨日无记录才算新增；
同一 SKU 明天继续低不会重复提醒。某地区今日无新增则整次不推送。
卡片标题下方只显示今日新增数，不显示低库存总数；每仓显示「今日新增 N 个」+ 当天新增 SKU
（SKU、产品名称、当前库存），不限条数；**无新增的仓不显示**。
底部下载“今日新增明细”和“全部低库存明细”；不在卡片上显示在途合计，Excel 保留每个 SKU 的在途库存。

某仓昨日基线整体缺失时，卡片不把全量低库存当成新增，只提示“无法判断今日新增”并指向 Excel；
Excel 仍可导出该仓全量低库存。未获取基线（`--no-baseline` 或缺 EN 凭证）时不生成新增 Excel。
两份Excel都按仓分sheet，列为SKU、产品名称、可用库存、在途库存。
今日无新增（或没有低库存）时**不推送**，也不生成消息/Excel。

## 采购入库（每天 14:00 一张卡）

每日 **14:00** 一次，直连通途 OpenAPI `/openapi/tongtool/stocksChangeDetailQuery`
查今天 00:00 到运行时间的增量：
EN 的 `stock_change` 每天约 05:53 才同步一次，白天会滞后，所以不走 EN。
只保留采购单 `relatedVoucherType=02` 且 `availableStockIncrease > 0` 的事件，按仓、SKU 合并。
**所有有入库的仓合成一张卡片**；没有入库的仓不显示；三个仓都没有则整次不推送。
消息列出各仓全部入库 SKU（默认文字，可直接复制）；一个 Excel 按仓分 sheet，下载全部有入库的仓。
本次没有采购入库时**不推送**。此提醒描述已同步的库存事件，不代表采购单全部到货。
上次检查时间保存在 `stock_alert_output/inbound_state.json`，dry-run 不推进。
手动查历史某天：`inbound --date YYYY-MM-DD --source tongtool`；沿用 EN：`--source en`。

## 运行（仓库根目录）

```powershell
uv run python -m stock_alert.cli run --mock --dry-run
uv run python -m stock_alert.cli run --dry-run
uv run python -m stock_alert.cli inbound --dry-run --date 2026-11-16
uv run python -m stock_alert.cli inbound --dry-run --today --source tongtool
uv run python -m stock_alert.cli run --notify
uv run python -m stock_alert.cli inbound --notify
uv run pytest stock_alert/tests -q
```

`--dry-run` 只读 API、更新本地名称缓存并生成本地 Excel/文字卡片预览，不发群、不上传文件。
名称取通途 `goodsQuery.productName`；缓存每周全量重建、日常补缺，失败用已有缓存/SKU。
首次刷新实测约30分钟（13504个商品），通途商户共享 5 次/分钟限流，名称刷新带非阻塞缓存锁，任务重叠时另一任务直接用缓存/SKU，不争抢名称查询额度。

## 卡片样式

默认发送 **Markdown 文字卡片**（`STOCK_ALERT_CARD_MODE=text`）：低库存列出 SKU/产品名称/库存，
入库列出产品明细，**可直接复制粘贴**；有下载按钮时使用 ActionCard。图片卡片仍可选。

可选模式（环境变量 `STOCK_ALERT_CARD_MODE`）：

- `text`（默认）：纯文本/ActionCard，可直接复制；
- `image`：PNG 图片卡片（蓝底居中标题、低库存今日新增在标题下方、各仓明细）；
- `interactive` / `auto`：钉钉原生互动卡片（需按 [互动卡片接入](docs/reference/interactive-card.md)
  配置企业内部应用与两个已发布模板；未配置时回退文字卡片）。

## 配置与定时

生产 EN 凭证在根 `.env`：`ERP_API_KEY` / `ERP_API_SECRET`，`ERP_URL` 默认生产。
通途凭证在 `tongtool_api/.env`：`TONGTOOL_ERP2_PRIMARY_KEY` / `TONGTOOL_ERP2_PRIMARY_SECRET`。
钉钉默认复用 `DINGTALK_WEBHOOK` / `DINGTALK_SECRET`；可用 `*_STOCK` 覆盖。

```powershell
powershell -ExecutionPolicy Bypass -File stock_alert/scripts/install_stock_alert_schedule.ps1 -PolandAtTime "14:00" -UsAtTime "20:00" -InboundAtTime "14:00"
```

注册 `FZH-StockAlert-Poland`（14:00）/ `FZH-StockAlert-US`（20:00）/ `FZH-StockInbound-daily`（14:00）；
旧的 `FZH-StockAlert-daily` 会一并移除。脚本支持 `-SkipInbound`、`-Remove`。
日志分别为 `stock_alert_output/logs/stock_alert_poland-daily.log`、`stock_alert_us-daily.log`、`stock_inbound-daily.log`。
注册不会立即发送消息，任务到点会自动推送；首次发群前先审阅 dry-run。

**避免睡眠影响**：`powercfg /change standby-timeout-ac 0`（交流电永不休眠；屏幕仍可关闭），
这样只要电脑不关机，定时任务就能按时执行；任务本身仍保留 `StartWhenAvailable` / `WakeToRun` 兜底。
如果关机/注销登录，任务不会执行。

详细接口边界与排障见 [参考](docs/reference/low-stock-alert.md)。
