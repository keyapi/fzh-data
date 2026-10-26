# stock_alert —— 通途低库存汇总推送钉钉

按仓库查询通途 ERP2 库存（`erp2_stocks_stocksquery`），筛出**可用库存 < 5** 的 SKU，
按仓汇总后推送钉钉；数量多时附一张**按仓库分 sheet 的 Excel**。

## 口径

- **计入**：`availableStockQuantity`（可用库存）< 5，**且**排除「可用=0 且 在途=0」的死库存。
- **仓库**：`美中-FZH-DANEEY`、`美东-CENTRADE`、`波兰-FZHPoland-covers`。
- **范围**：整仓全量（按仓库分页拉取，不是固定清单）。

## 投递

- **正文**：每仓「N 个 SKU 可用<5（在途合计 M 件）」。
- **总数 ≤ 10**：明细直接写进正文；**> 10**：生成 Excel（每仓一 sheet：`SKU / 可用库存 / 在途库存`）
  上传 ERPNext，发 ActionCard 下载卡片。

## 运行

```bash
uv run python -m stock_alert.cli run --mock --dry-run     # 离线，不调 API / 不发群
uv run python -m stock_alert.cli run --dry-run            # 真查通途，只出正文
uv run python -m stock_alert.cli run --notify             # 真查 + 真推
uv run pytest stock_alert/tests -q
```

## 配置（敏感值只放 `.env`，已 gitignore）

| 用途 | 位置 | 键 |
|---|---|---|
| 通途 ERP2 | `tongtool_api/.env` | `TONGTOOL_ERP2_PRIMARY_KEY` / `TONGTOOL_ERP2_PRIMARY_SECRET` |
| 钉钉（默认复用原群） | 仓库根 `.env` | `DINGTALK_WEBHOOK` / `DINGTALK_SECRET` |
| 钉钉专用群（可选覆盖） | 仓库根 `.env` | `DINGTALK_WEBHOOK_STOCK` / `DINGTALK_SECRET_STOCK` |
| 发 Excel（上传 ERPNext） | 仓库根 `.env` | `ERP_API_KEY` / `ERP_API_SECRET` |

## 定时（Windows）

任务 `FZH-StockAlert-daily`，每日 **09:23**（避开尾程 `FZH-ParcelTrack-daily` 的 09:07）。

```powershell
powershell -ExecutionPolicy Bypass -File stock_alert\scripts\install_stock_alert_schedule.ps1 -AtTime "09:23"
powershell -ExecutionPolicy Bypass -File stock_alert\scripts\install_stock_alert_schedule.ps1 -Remove
```

日志：`stock_alert_output/logs/stock_alert-daily.log`（不入库）。

完整说明见 [docs/index.md](docs/index.md)、[docs/reference/low-stock-alert.md](docs/reference/low-stock-alert.md)。
