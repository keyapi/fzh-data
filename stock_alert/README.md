---
type: Reference
title: stock_alert 通途库存提醒
---
# stock_alert

三仓低库存汇总卡片（同卡下载新增/全部明细），以及独立的昨日采购入库提醒。
默认仓库：美中-FZH-DANEEY、美东-CENTRADE、波兰-FZHPoland-covers。

## 低库存

每日 09:23，默认读 EN `Tongtool Stock Latest`，要求今日快照同步成功；
EN 不可达时回退通途 OpenAPI。可用库存 < 5，排除可用=0 且在途=0。
每次只发一张卡片：总览之后按三个仓库分别成段，显示低库存SKU数、今日新增数、在途件数。
卡片不堆叠全部SKU；底部按钮直接下载“今日新增明细”和“全部低库存明细”。

新增Excel的判定：昨日可用 >= 阈值，或昨日无此 SKU。另提供全部低库存Excel。
某仓昨日基线整体缺失时，该仓按全量低库存导出，并明确提示，不能视作已证新增。
未获取基线（`--no-baseline` 或缺 EN 凭证）时不生成新增 Excel。
两份Excel都按仓分sheet，列为SKU、产品名称、可用库存、在途库存。
无新增时只保留“全部低库存”按钮；没有低库存时不生成文件。

## 采购入库

每日 09:47 独立任务，统计昨日全天：`get_stock_change` 的采购单 `voucher_type=02`，
仅汇总每条 `available_increase > 0` 的事件，按仓、SKU 合并。
零增量是创建/无变化事件，负增量也不计入；它们不能证明真实入库。
每次只发一条，按仓标题分段；每个产品的名称、SKU、入库件数分别成段，零入库仓明确显示。
明细过长则只展示分仓汇总，并在同一卡片下载完整入库Excel，始终不拆条。
昨日没有采购入库也会发消息。此提醒描述已同步的库存事件，不代表采购单全部到货。

## 运行（仓库根目录）

```powershell
uv run python -m stock_alert.cli run --mock --dry-run
uv run python -m stock_alert.cli run --dry-run
uv run python -m stock_alert.cli inbound --dry-run --date 2026-11-16
uv run python -m stock_alert.cli run --notify
uv run python -m stock_alert.cli inbound --notify
uv run pytest stock_alert/tests -q
```

`--dry-run` 只读 API、更新本地名称缓存并生成本地 Excel，不发群、不上传文件。
名称取通途 `goodsQuery.productName`；缓存每周全量重建、日常补缺，失败用已有缓存/SKU。
首次刷新实测约30分钟（13504个商品），通途商户共享 5 次/分钟限流，名称刷新带非阻塞缓存锁，任务重叠时另一任务直接用缓存/SKU，不争抢名称查询额度。

## 配置与定时

生产 EN 凭证在根 `.env`：`ERP_API_KEY` / `ERP_API_SECRET`，`ERP_URL` 默认生产。
通途凭证在 `tongtool_api/.env`：`TONGTOOL_ERP2_PRIMARY_KEY` / `TONGTOOL_ERP2_PRIMARY_SECRET`。
钉钉默认复用 `DINGTALK_WEBHOOK` / `DINGTALK_SECRET`；可用 `*_STOCK` 覆盖。

```powershell
powershell -ExecutionPolicy Bypass -File stock_alert/scripts/install_stock_alert_schedule.ps1 -AtTime "09:23" -InboundAtTime "09:47"
```

注册 `FZH-StockAlert-daily` / `FZH-StockInbound-daily`；脚本支持 `-SkipInbound`、`-Remove`。
日志分别为 `stock_alert_output/logs/stock_alert-daily.log`、`stock_inbound-daily.log`。
注册不会立即发送消息，任务到点会自动推送；首次发群前先审阅 dry-run。

详细接口边界与排障见 [参考](docs/reference/low-stock-alert.md)。
