---
okf: v0.1
type: Reference
title: EN 通途库存同步与读取接口（05:17 全量 / 12:00 波兰 / 18:00 美国）
description: EN（ERPNext）tongtool_integration 四个库存同步任务的 cron、覆盖仓、产出文件，以及三个只读查询接口的用法与口径边界
date: 2026-11-27
category: reference
module: en_api
tags: [erpnext, tongtool, stock, inventory, sync, cron, api, poland, us, intraday]
related_components: [demand_collaboration, supply_copilot, tongtool_integration]
---

# EN 通途库存同步与读取接口

> 同步代码不在本仓库，在独立 ERPNext app `keyapi/tongtool_integration`
> （生产 `/home/frappe/frappe-bench/apps/tongtool_integration/`）。
> 本页记录**现状事实**（2026-11-27 核实），改动请回 app 仓库走 PR。

## 一、同步模式

不是 Webhook，是 Frappe 定时任务（`hooks.py` → `scheduler_events` → `Scheduled Job Type`），
cron 用**服务器本地时间 = 北京时间（CST）**。任务内部用通途 OpenAPI
（`/openapi/tongtool/stocksQuery`、`stocksChangeDetailQuery`）分页拉取，pace≈13s、每页 100：

- 只写三样东西：**当前视图 DocType**（`Tongtool Stock Latest`）、**parquet 历史文件**、**Run 日志**（`Tongtool Stock Run`）；
- **不写 Bin / Stock Ledger / 账务**，不改 ERPNext 自己的库存台账。

| 任务（Scheduled Job Type） | cron | 覆盖仓 | 产出 |
|---|---|---|---|
| `stock_sync.sync_daily_stock_snapshot` | `17 5 * * *` | 14 个活跃仓（全量，~5,385 行） | `Tongtool Stock Latest`（整体替换）+ `stock.parquet` |
| `stock_sync.retry_stock_snapshot_0617` / `_if_needed` | `17 6 * * *` / `17 7 * * *` | 同上 | 失败补跑 |
| `stock_change_sync.sync_daily_stock_change` | `47 5 * * *` | 14 仓（变动明细） | `stock_change.parquet` + Run 日志 |
| `stock_intraday.sync_intraday_eu` | `0 12 * * *` | **波兰-FZHPoland-covers**（1 仓，~1,374 行） | `stock_intraday.parquet`，`slot=eu` |
| `stock_intraday.sync_intraday_us` | `0 18 * * *` | **美东-CENTRADE + 美中-FZH-DANEEY**（~3,133 行） | 同一 parquet，`slot=us` |

数据目录（`Tongtool Settings.stock_snapshot_dir`，默认 `/home/frappe/fzh-inventory/`）：
`stock.parquet`、`stock_change.parquet`、`stock_intraday.parquet`，各自带 `.prev.parquet` 上一版备份。

**intraday 去重方式**：按 `(snapshot_date, slot)` 先删后写，eu 与 us 共存于同一文件，不会互相覆盖
（2026-11-27 实测 eu 保留 30 天、us 29 天）。

### 时间点容易记混的地方

- 库存的午/晚任务**从上线起就是 12:00 / 18:00**（2026-10-27 提交 `9b7d459`），app 历史中不存在 `0 13` / `0 19`。
- `40 5,13,21 * * *` 是 `daneey_sync.sync_daneey_products`（独立站**产品链接**同步）；
  `30 5,13,21 * * *` 是 `item_group_nas_path.update_item_group_nas_path`（NAS 物料组路径）——都不是库存。
- 「会卡/延迟」的机制：两个 intraday 任务都是 `enqueue(queue="long", timeout=3600)`，
  **12:00 / 18:00 只是入队时间**，long 队列被占（备份、订单重扫）就晚开始；
  另有 `.stock_intraday.lock`，并发的那一次直接 skip。实测 11-26：12:00:42→12:03:34、18:00:29→18:07:12。

## 二、对外读取接口（只读，Token 认证）

三个都属于 app，鉴权头统一 `Authorization: token <api_key>:<api_secret>`。

### 1. 全量当前视图（等价于 05:17 口径）

```
GET /api/resource/Tongtool Stock Latest?filters=[["warehouse","=","波兰-FZHPoland-covers"]]&limit_page_length=0
```

字段：`sku / warehouse / warehouse_id / available / intransit / waiting_shipment / defects / avg_cost / snapshot_at / run_id`。
**只代表每日 05:17 全量快照**，不能当午间/晚间数据用。

### 2. 日快照历史（05:17 口径，读 `stock.parquet`）

```
GET /api/method/tongtool_integration.sync.stock_sync.get_stock_history
    ?sku=<通途SKU>&warehouse=<仓名>&start_date=YYYY-MM-DD&end_date=YYYY-MM-DD&limit=1000
```

默认近 30 天，`limit` 上限 5000。

### 3. 盘中快照（12:00 波兰 / 18:00 美国，读 `stock_intraday.parquet`）

```
GET /api/method/tongtool_integration.sync.stock_intraday.get_stock_intraday
    ?slot=eu|us&warehouse=<仓名>&warehouse_id=<通途仓ID>&sku=<通途SKU>
    &start_date=YYYY-MM-DD&end_date=YYYY-MM-DD&limit=5000
```

- `slot`：`eu` = 12:00 波兰；`us` = 18:00 美东+美中；**不传则两者都返回**，非法值报 `ValidationError`（HTTP 417）。
- `start_date` **默认今天**（含），`end_date` 含当天全天；`limit` 默认 5000、上限 5000（超限静默截断）。
- 按 `snapshot_date DESC, slot, warehouse_id, sku` 排序；日期/时间字段返回字符串。
- 返回字段：`snapshot_date / slot / snapshot_at / warehouse_id / warehouse_name / sku /
  available / intransit / waiting_shipment / defects / avg_cost / source / run_id / schema_version`。

示例：

```bash
# 当天中午波兰
curl -sG "https://erpnext.vilavi.cn/api/method/tongtool_integration.sync.stock_intraday.get_stock_intraday" \
  -H "Authorization: token $ERP_API_KEY:$ERP_API_SECRET" \
  --data-urlencode "slot=eu" --data-urlencode "start_date=2026-11-26"

# 当天晚上美国（美东 + 美中）
curl -sG ".../get_stock_intraday" -H "Authorization: token $ERP_API_KEY:$ERP_API_SECRET" \
  --data-urlencode "slot=us" --data-urlencode "start_date=2026-11-26"
```

### 4. 库存变动明细（05:47 口径）

```
GET /api/method/tongtool_integration.sync.stock_change_sync.get_stock_change
    ?sku=&warehouse=&voucher_number=&voucher_type=&operator=&start=&end=&limit=1000
```

默认近 30 天，上限 5000。

## 三、权限与取 Key

- `Tongtool Stock Latest` / `Tongtool Stock Run` 的 DocPerm：`System Manager` 全权，**`All` 只读**。
- 三个 whitelisted 方法内部只校验 `read` on `Tongtool Stock Latest`，所以**任意已登录账号**都能读。
- 取 Key：ERPNext 右上角头像 → My Settings → **API Access → Generate Keys**（记下 secret，只显示一次）。

## 四、口径纪律

1. 要「05:17 全量」→ 接口 1/2；要「12:00 波兰 / 18:00 美国」→ 只能接口 3 并带 `slot`。
2. `Tongtool Stock Latest` 被 `demand_collaboration/live_stock.py`、`supply_copilot/en_live.py` 消费，
   **绝不要把 intraday 写进 Latest**，否则这两个工作台的口径会被污染。
3. 行数对账基准（2026-11-26）：`eu` 1,374（波兰）；`us` 3,133（美东 2,105 + 美中 1,028）；合并 4,507。
4. 未知/缺仓不补 0：看 `Tongtool Stock Run` 的 `complete` / `missing_warehouses` / `error_summary`。

## 相关

- 服务器与 bench 重启用 [en-server-access.md](en-server-access.md)
- [`../../AGENT_HANDOFF.md`](../../AGENT_HANDOFF.md)
