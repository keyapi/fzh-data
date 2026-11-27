---
okf: v0.1
type: Reference
title: EN 通途库存同步与读取接口（05:17 全量 / 13:00 波兰 / 19:00 美国）
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
| `stock_intraday.sync_intraday_eu` | `0 13 * * *` | **波兰-FZHPoland-covers**（1 仓，~1,374 行） | `stock_intraday.parquet`，`slot=eu` |
| `stock_intraday.sync_intraday_us` | `0 19 * * *` | **美东-CENTRADE + 美中-FZH-DANEEY**（~3,133 行） | 同一 parquet，`slot=us` |
| `stock_intraday.retry_intraday_*_1320/1340/1920/1940` | `20 13` / `40 13` / `20 19` / `40 19` | 同上 | 当天该 slot 无 `complete=1` 的 Run 才重跑 |

数据目录（`Tongtool Settings.stock_snapshot_dir`，默认 `/home/frappe/fzh-inventory/`）：
`stock.parquet`、`stock_change.parquet`、`stock_intraday.parquet`，各自带 `.prev.parquet` 上一版备份。

**intraday 去重方式**：按 `(snapshot_date, slot)` 先删后写，eu 与 us 共存于同一文件，不会互相覆盖
（2026-11-27 实测 eu 保留 30 天、us 29 天）。

### 时间点与「卡死」的真实历史（重要）

**当前生效值（2026-11-27 起）：欧洲 13:00 / 美国 19:00**，各带 2 次条件重试（13:20/13:40、19:20/19:40），对应 app PR #31。

调整原因与历史：

1. **2026-10-27（fzh-data `bac970ca`）**：上线时是 12:00 / 18:00；因周一美国操作量最重，记录过「周一 19:00」建议（`0 19 * * 1`），当时标注「暂不实施」。
2. **2026-11-18 停站事故**：18:02 在 18 点窗口执行 `bench restart`，RQ 优雅停机必须等 `run_stock_intraday(slot=us)` 跑完（等 6m33），期间 SSH 断连 → 站点全停 14 小时；当时计划（`en-graceful-micali.md`）建议美国改 19:30，未实施。
3. **2026-11-27 实施**：业务方要求 14:00 / 20:00 前能读到数据，最终定为 **欧洲 13:00、美国 19:00**（都在 `0 */6 * * *` 备份窗口结束后），并补条件重试。

配套的可靠性改动（同一 PR）：

- **超时 3600 → 1200 秒**：卡住的运行不会拖过 20:00，也给 19:20/19:40 重试让路。
- **部分成功不发布**：原先 partial 也整槽覆盖写 parquet，会删掉缺失仓的旧行（11-04 事故：18:00 的 partial 覆盖了 12:58 的完整结果）。现在只有 `complete`（无缺仓、无错误）才写文件，partial 只记 Run，等重试补。
- 重试闸门读 `Tongtool Stock Run`：当天该 slot 有 `complete=1` 就直接跳过；复用 `run_stock_intraday`，按 `(snapshot_date, slot)` 整槽替换，幂等。

「会卡/延迟」的机制：
- frappe crontab `0 */6 * * *` 备份（00 / 06 / 12 / 18 点，7.6GB，约 55 分钟）——13:00 / 19:00 已避开其起点；
- 两个 intraday 任务都是 `enqueue(queue="long")`，**整点只是入队时间**，long 队列被占（S3 上传、订单重扫）就晚开始；生产有 2 个 long worker，`Daily Long` 类任务集中在 00:0x；
- `.stock_intraday.lock` 使并发的那一次直接 skip；
- 在 13:00 / 19:00 附近做 `bench restart` 仍会等待长任务，重启请避开。

时间点容易记混的地方：
- `40 5,13,21 * * *` 是 `daneey_sync.sync_daneey_products`（独立站**产品链接**同步）；
- `30 5,13,21 * * *` 是 `item_group_nas_path.update_item_group_nas_path`（NAS 物料组路径）——都不是库存。

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

### 4. 最近一次完整槽（含新鲜度，推荐业务读取用这个）

```
GET /api/method/tongtool_integration.sync.stock_intraday.get_intraday_latest
    ?slot=eu|us&warehouse=&warehouse_id=&sku=&limit=5000&allow_stale=0
```

一次调用同时给数据和「这是不是当天的、完整不完整」：

| 字段 | 含义 |
|---|---|
| `data_complete` | 这份快照本身是否完整成功（`Success` 且 `complete=1`，且 parquet 的 `run_id` 与运行记录一致） |
| `is_today` | 是否当天槽 |
| `age_seconds` / `snapshot_at` / `finished_at` | 快照年龄与时间（带 `+08:00`） |
| `reason` | `no_complete_snapshot`（从未完整成功）/ `stale_snapshot`（旧数据被拦）/ `no_match`（过滤无命中）/ `null` |
| `row_count` / `returned_count` / `truncated` | 过滤后总数 / 实际返回 / 是否被 `limit` 截断 |
| `latest_attempt_today` | 当天最近一次尝试（含 `Partial`/`Failed`、`missing_warehouses`），用来解释为什么今天没数据 |
| `next_retry_at` | 当天未完成且仍有重试位时给出下一次重试时间 |

**旧快照默认不返回 `rows`**（`reason=stale_snapshot`），要取旧数据必须显式 `allow_stale=1`——避免静默拿到过期库存。`slot` 必填。

### 5. 库存变动明细（05:47 口径）

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

1. 要「05:17 全量」→ 接口 1/2；要「13:00 波兰 / 19:00 美国」→ 接口 3（按日期区间）或接口 4（最近完整槽 + 新鲜度）。
2. `Tongtool Stock Latest` 被 `demand_collaboration/live_stock.py`、`supply_copilot/en_live.py` 消费，
   **绝不要把 intraday 写进 Latest**，否则这两个工作台的口径会被污染。
3. 行数对账基准（2026-11-26）：`eu` 1,374（波兰）；`us` 3,133（美东 2,105 + 美中 1,028）；合并 4,507。
4. 未知/缺仓不补 0：看 `Tongtool Stock Run` 的 `complete` / `missing_warehouses` / `error_summary`。

## 五、给同事的读法（可直接转发）

**每天 14:00 读波兰、20:00 读美国**，推荐只用接口 4，不用自己拼 Run 查询：

```python
import os, requests

BASE = "https://erpnext.vilavi.cn/api/method/tongtool_integration.sync.stock_intraday.get_intraday_latest"
H = {"Authorization": f"token {os.environ['ERP_API_KEY']}:{os.environ['ERP_API_SECRET']}"}

def read_slot(slot: str):
    r = requests.get(BASE, params={"slot": slot, "limit": 5000}, headers=H, timeout=120)
    r.raise_for_status()
    data = r.json()["message"]
    if data["data_complete"] and data["is_today"]:
        return data["rows"], "ok"
    # 当天还没成功：先看有没有重试位，再决定是否用旧数据
    return None, data["reason"]
```

**失败时的处理顺序（兜底）**：

1. `data_complete=true` 且 `is_today=true` → 直接用，`snapshot_at` 就是数据时间。
2. 当天还没完成 → 看 `next_retry_at`，等到重试结束（最晚 13:45 / 19:45）再读一次。
3. 仍没有 → 两种降级，**都必须标注非当日**：
   - 旧槽：同一接口加 `allow_stale=1`（返回 `snapshot_date` 与 `age_seconds`，自己判断可接受性）；
   - 05:17 全量：`/api/resource/Tongtool Stock Latest`，它是当天开门基线，不是盘中数据。
4. **不建议直连通途 OpenAPI**：那是共享 app_key + 13 秒/请求的限流，多一个消费者会把 EN 自己的同步打出 526（历史上的失败多是这类限流/网关抖动）。只有 EN 完全不可用时才考虑，且必须单独申请 key、串行限速。

## 相关

- 服务器与 bench 重启用 [en-server-access.md](en-server-access.md)
- [`../../AGENT_HANDOFF.md`](../../AGENT_HANDOFF.md)
