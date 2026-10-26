---
okf: v0.1
type: Reference
title: 通途库存 EN 每日同步 — 配置、日志、数据与历史查询操作手册
description: EN 生产/测试上的通途库存每日快照：Tongtool Settings 配置、Tongtool Stock Run 运行日志、Tongtool Stock Latest 当前库存、Parquet/DuckDB 历史与外部 API 查询
date: 2026-10-23
tags: [tongtool, inventory, erpnext, operations, runbook, duckdb, parquet]
---

# 通途库存 EN 每日同步 — 操作手册

> 一句话：**当前库存看 `Tongtool Stock Latest`；运行状态看 `Tongtool Stock Run`；历史在 Parquet 文件里，不在 EN 数据库；外部查询走 API 或直接读 Parquet。**

## 0. 一页速查

| 想做什么 | 去哪里 |
|---|---|
| 看今天同步成没成 | Desk → **Tongtool Stock Run**，按 `snapshot_date` = 今天过滤 |
| 看最新库存 | Desk → **Tongtool Stock Latest**（每仓×SKU 一行） |
| 改开关/目录/仓库/页大小 | Desk → **Tongtool Settings** → Stock Sync |
| 看异常堆栈 | Desk → **Error Log**；或 `/home/frappe/frappe-bench/logs/` |
| 看调度记录 | Desk → **Scheduled Job Log** |
| 手动补跑 | `bench --site erpnext.vilavi.cn execute ...run_stock_snapshot --kwargs '{"source":"manual"}'` |
| 查库存变动（退货/盘点/调拨） | `/home/frappe/fzh-inventory/stock_change.parquet`；`Tongtool Stock Run` 里 `job = stock_change` |
| 手动补跑变动 | `...run_stock_change --kwargs '{"source":"manual","lookback_days":3}'` |
| 查历史（外部） | `GET /api/method/tongtool_integration.sync.stock_sync.get_stock_history` |
| 拿全量历史文件 | SFTP/SSH `/home/frappe/fzh-inventory/stock.parquet`，用 DuckDB 读 |

生产 Desk：`https://erpnext.vilavi.cn/app/...`；测试站通过 SSH/bench 操作。

## 1. 系统构成

| 部分 | 在哪 | 作用 |
|---|---|---|
| 每日任务 | EN 生产，`tongtool_integration` app，05:17 | 抓 14 个启用仓，写当前表/运行日志/Parquet |
| 库存变动 | EN（app PR #8 合并后），同一 app，05:47 | 抓 14 仓的库存变动明细（退货/盘点/调拨/包裹），写 `stock_change.parquet` |
| 失败重试 | 06:17 / 07:17（快照）；变动靠 7 天窗口自愈 | 当天 Run 不 complete 才重跑；文件锁防并发 |
| 当前视图 | MariaDB DocType `Tongtool Stock Latest` | 每仓×SKU 一行，约 5.3k 行 |
| 运行日志 | MariaDB DocType `Tongtool Stock Run` | 每次运行一行；`job` 区分 `stock_snapshot` / `stock_change` |
| 历史 | `/home/frappe/fzh-inventory/stock.parquet` | 单个 Parquet；不写 EN 数据库 |
| 库存变动 | `/home/frappe/fzh-inventory/stock_change.parquet` | 单个 Parquet；事件级，按事件去重；保留 7 天内可补 |
| 外部查询 | Frappe REST + whitelist history API | 当前/运行走 REST；历史走 DuckDB 读 Parquet |

**EN 数据库里没有“每日历史表”**。当前/运行是 MariaDB；历史是 Parquet。DuckDB 只是读 Parquet 的查询引擎（bench env 里的 Python 包），不是独立服务。

Windows 侧：浏览器库存结存导出 02:17 仍保留；原 Windows API 全量任务 `FZH-TongtuStockApiDaily` 已禁用（手动回退）。测试站同步定时已关闭，只保留手动/复制备份。

## 2. 配置：Tongtool Settings

Desk → **Tongtool Settings**（Single）→ **Stock Sync** 区：

| 字段 | 当前值 | 说明 |
|---|---|---|
| `enable_stock_sync` | 生产 **1**；测试 **0** | 关闭后 05:17/06:17/07:17 都不动作 |
| `stock_snapshot_dir` | `/home/frappe/fzh-inventory` | Parquet 目录；`stock.parquet` / `stock.prev.parquet` |
| `stock_sync_warehouses` | 空 | 空 = 全部启用仓；可逗号/换行限定 |
| `stock_low_threshold` | 默认 5 | 预留给低库存告警；v1 尚未并入 |
| `stock_snapshot_page_size` | 100 | 通途服务端上限 |
| `stock_snapshot_interval` | 13 | 每次 API 调用间隔秒数（商户级 5 次/分钟） |
| `enable_stock_change` | 默认 **1**（旧 Single 需手工设） | 05:47 是否抓库存变动明细 |
| `stock_change_lookback_days` | 默认 **3**（旧 Single 需手工设） | 首次/无成功记录时回看天数；有成功记录时从上次结束-1 天开始，最多 7 天 |

修改权限：`Tongtool Settings` 由 System Manager 维护。改完不需要重启；05:17 任务运行时会读最新值。

## 3. 每天怎么判断“正常”

按顺序看四处：

### 3.1 运行日志 `Tongtool Stock Run`（主要）

Desk → `Tongtool Stock Run`，按 `snapshot_date` = 今天过滤，或按 `creation` 倒序看最新：

- `status = Success` 且 `complete = 1`
- `warehouse_count = 14`
- `row_count` 约 **5,000–5,500**
- `missing_warehouses` 为空
- `error_summary` 为空
- `data_path = /home/frappe/fzh-inventory/stock.parquet`

失败/部分成功会显示 `Failed` / `Partial`，`error_summary` 写明仓库与异常。

### 3.2 当前库存 `Tongtool Stock Latest`

Desk → `Tongtool Stock Latest`：

- 总行数约 **5,300**
- `snapshot_at` / `run_id` 应是**今天**的最新 Run
- 可按 `warehouse` / `sku` 过滤

### 3.3 历史文件

SSH 到 EN：

```bash
ls -lh /home/frappe/fzh-inventory
```

- `stock.parquet` 修改时间应是今天
- `stock.prev.parquet` 是上一次的完整文件，用于回滚
- 现在约 64KB（4 天）；2 年约 100–200MB

### 3.4 异常日志

- Desk → **Error Log**：搜 `stock sync` / `Tongtool Stock`
- Desk → **Scheduled Job Log**：确认 05:17/06:17/07:17（快照）与 05:47（变动）是否入队
- 服务器：`ls /home/frappe/frappe-bench/logs/`；`grep -i "stock sync" logs/*.log`

### 3.5 库存变动 `stock_change.parquet`

- `Tongtool Stock Run` 过滤 `job = stock_change`，看今天是否 `Success`、`warehouse_count = 14`、`row_count > 0`
- `data_path = /home/frappe/fzh-inventory/stock_change.parquet`
- 变动是**事件级**：一行一次库存变动，含 `voucher_type_name`（包裹/拆包/采购单/报损/报溢/买家退货/调拨等）、`voucher_number`、`operator`、四个桶的 `*_increase`
- **7 天窗口**：通途只允许回看 7 天。任务每天跑，窗口从“上次成功结束 - 1 天”开始；漏跑 1–2 天会在下一次自动补回，超过 7 天无法补
- 同一事件重复抓取会按事件身份去重（仓+SKU+时间+凭证类型/单号+四桶增减），重跑不会翻倍

> 生产快照：2026-10-23 手动全量成功（14 仓 / 5,316 行）；10/24、10/25、10/26 05:17 定时连续 Success（14 仓 / 5,316 行 / `complete=1`）。

## 4. 查看最新库存

- Desk → **Tongtool Stock Latest**（只读）
- 常用过滤：`warehouse = 美中-FZH-DANEEY`、`sku = ...`
- 字段：仓库、仓库 ID、SKU、可用、在途、待发、故障品、平均成本、`snapshot_at`、`run_id`、`schema_version`
- 这是 **05:17 快照**；09:23 的实时数据看 Jack 的低库存任务或直接调通途 API。
- 权限：`All` 只读；`System Manager` 读写。`All` 没有导出权限；需要导出用 System Manager 或 API。

## 5. 运行日志与排查

### 5.1 `Tongtool Stock Run` 字段

`run_id`、`job`（`stock_snapshot` / `stock_change`）、`snapshot_date`、`snapshot_at`、`started_at`、`finished_at`、`status`（Success/Partial/Failed）、`complete`、`warehouse_count`、`row_count`、`missing_warehouses`、`error_summary`、`source`（scheduled/retry/manual）、`data_path`、`schema_version`。

### 5.2 其他日志

- **Error Log**：未捕获异常 / Run 写入失败
- **Scheduled Job Log**：定时是否触发
- **RQ Job**（如界面有）：long 队列任务状态
- **服务器日志**：`/home/frappe/frappe-bench/logs/`；app 的 `stock sync ...` 行在这里

### 5.3 手动 SQL（可选）

```bash
cd /home/frappe/frappe-bench
bench --site erpnext.vilavi.cn mariadb <<'SQL'
SELECT run_id,status,complete,warehouse_count,row_count,creation
FROM `tabTongtool Stock Run`
ORDER BY creation DESC LIMIT 5;
SQL
```

## 6. 历史库存：Parquet + DuckDB，不在 EN 数据库

- 历史是**单个 Parquet**：`/home/frappe/fzh-inventory/stock.parquet`
- 现在有 **7 天**：10/20 5,192、10/21 5,314、10/22 5,314、10/23–10/26 各 5,316（10/20 当天一个仓超时，属部分数据）
- 回填行的 `avg_cost=0`（Windows JSONL 不含成本），`source=backfill_windows`；live 行有成本
- 库存变动另存 `stock_change.parquet`（见 6.3），**不与日快照混在一张表**
- **DuckDB 不是独立服务**：它是 bench env 里的 Python 包，用来写/读 Parquet；API 的 history 方法内部用它
- **EN 目前没有计划把日历史做成 MariaDB 表**；当前/状态在 EN，原始历史在 Parquet。以后若需要 EN 内展示趋势，加一张“状态汇总”小表，完整历史仍留 Parquet

### 6.1 服务器上直接查 Parquet

```bash
/home/frappe/frappe-bench/env/bin/python - <<'PY'
import duckdb
print(duckdb.sql("""
  SELECT snapshot_date, count(*) AS rows, count(DISTINCT warehouse_id) AS whs,
         sum(available) AS available
  FROM read_parquet('/home/frappe/fzh-inventory/stock.parquet')
  GROUP BY 1 ORDER BY 1
""").fetchall())
PY
```

### 6.2 外部批量分析

- 用 SFTP/SSH 把 `stock.parquet` 拉到分析机，用 DuckDB/Pandas 读
- 或走下面的 history API（有行数上限）
- 不要把原始 Parquet 放到 web 目录；不要暴露 SQL 接口

### 6.3 库存变动 `stock_change.parquet`

列：

`operate_time`、`warehouse_name`、`goods_detail_id`、`sku`、`voucher_type`、`voucher_type_name`、`voucher_number`、`operator`、`available_increase`、`defects_increase`、`intransit_increase`、`waiting_shipment_increase`、`available_quantity`、`defects_quantity`、`intransit_quantity`、`waiting_quantity`、`captured_at`、`run_id`、`schema_version`

```bash
/home/frappe/frappe-bench/env/bin/python - <<'PY'
import duckdb
print(duckdb.sql("""
  SELECT date_trunc('day', operate_time) AS day,
         voucher_type_name, count(*) AS events, sum(available_increase) AS avail_delta
  FROM read_parquet('/home/frappe/fzh-inventory/stock_change.parquet')
  GROUP BY 1,2 ORDER BY 1 DESC, 3 DESC LIMIT 20
""").fetchall())
PY
```

常见用法：

- 退货：`voucher_type_name IN ('买家退货','退货')`
- 盘点/手工：`voucher_type_name IN ('报损','报溢','库存调整')`，有 `operator`
- 调拨：`voucher_type_name` 含“调拨”；仓间移动
- 发货：`voucher_type_name = '包裹'`；拆包为反向
- 采购入库：`voucher_type_name = '采购单'`

## 7. 外部查询 API

认证：`Authorization: token <api_key>:<api_secret>`；调用用户需要有 `Tongtool Stock Latest` 读权限（当前 `All` 已读）。

### 7.1 当前库存（MariaDB）

```http
GET /api/resource/Tongtool Stock Latest?limit_page_length=1000
```

可选过滤：`filters=[["warehouse","=","美中-FZH-DANEEY"]]`、`[["sku","=","..."]]`。
**没有 `snapshot_date`**：这张表本身就是“最新一份”。

### 7.2 运行日志（MariaDB）

```http
GET /api/resource/Tongtool Stock Run?order_by=creation desc&limit_page_length=1
```

查某天全部运行：`filters=[["snapshot_date","=","2026-10-23"]]`。
只看库存快照：`filters=[["job","=","stock_snapshot"]]`；只看库存变动：`filters=[["job","=","stock_change"]]`。

### 7.3 历史（Parquet + DuckDB）

```http
GET /api/method/tongtool_integration.sync.stock_sync.get_stock_history
  ?sku=TEST-1
  &warehouse=美东-CENTRADE
  &start_date=2026-10-20
  &end_date=2026-10-23
  &limit=1000
```

- 可选参数：`sku`、`warehouse`（仓库名）、`warehouse_id`、`start_date`、`end_date`、`limit`
- 默认最近 **30 天**；最多 **5,000 行**
- 返回 `{"message": [{...}, ...]}`；日期为字符串
- 已实测生产 HTTP 200
- 大批量/全量：用 6.2 的 Parquet，不要靠 API 硬扫

Python 示例：

```python
import requests
base = "https://erpnext.vilavi.cn"
headers = {"Authorization": f"token {api_key}:{api_secret}"}
r = requests.get(
    base + "/api/method/tongtool_integration.sync.stock_sync.get_stock_history",
    headers=headers,
    params={"sku": "TEST-1", "start_date": "2026-10-20", "end_date": "2026-10-23", "limit": 100},
    timeout=30,
)
print(r.status_code, len(r.json().get("message", [])))
```

## 8. 权限

生产 `Tongtool Stock Latest` / `Tongtool Stock Run` 的 DocPerm：

| 角色 | read | write | create | delete |
|---|---:|---:|---:|---:|
| All | 1 | 0 | 0 | 0 |
| System Manager | 1 | 1 | 1 | 1 |

- 所有登录用户可读；只有 System Manager 可写
- 外部 API key 对应的用户只要有 `All` 即可读（已实测）
- 如需收紧：新建 `Stock Viewer` 角色，把 `All` 的 read 去掉，只给该角色和 API 用户

## 9. 手动补跑

生产（一次只跑一路；避开 09:23 Jack 的低库存任务）：

```bash
cd /home/frappe/frappe-bench

# 单仓验证（约 2–3 分钟）
bench --site erpnext.vilavi.cn execute \
  tongtool_integration.sync.stock_sync.run_stock_snapshot \
  --kwargs '{"warehouses": "美中-FZH-DANEEY", "source": "manual"}'

# 全量 14 仓（约 14 分钟）
bench --site erpnext.vilavi.cn execute \
  tongtool_integration.sync.stock_sync.run_stock_snapshot \
  --kwargs '{"source": "manual"}'

# 库存变动：单仓 1 天（约 1–2 分钟）
bench --site erpnext.vilavi.cn execute \
  tongtool_integration.sync.stock_change_sync.run_stock_change \
  --kwargs '{"warehouses": "美东-CENTRADE", "source": "manual", "lookback_days": 1}'

# 库存变动：全量 14 仓 3 天（约 10–20 分钟）
bench --site erpnext.vilavi.cn execute \
  tongtool_integration.sync.stock_change_sync.run_stock_change \
  --kwargs '{"source": "manual", "lookback_days": 3}'
```

- 快照输出：`run_id / warehouses / rows / complete / data_path / requests`
- 变动输出：`run_id / status / window_from / warehouses / fetched_rows / parquet_rows / missing / errors`
- 同一天重跑会替换当天的 Parquet 行（快照）或按事件去重（变动），不重复累加
- 文件锁会阻止与定时任务并发（`.stock_sync.lock` / `.stock_change.lock`）

## 10. 常见问题

| 现象 | 处理 |
|---|---|
| 今天没有 `Tongtool Stock Run` | 检查 `enable_stock_sync`、Scheduled Job Log、scheduler 是否重启；手动跑一次 |
| `status=Failed` | 看 `error_summary` / Error Log；检查凭证、网络、通途 526；06:17/07:17 会自动重试 |
| `status=Partial` | 某个仓失败；看 `error_summary`；手动重跑全量 |
| `Latest` 是旧时间 | 看最新 Run；手动重跑；确认 `run_id` 一致 |
| `stock.parquet` 没更新 | 检查目录权限（`frappe:frappe`）、磁盘、`duckdb` 是否安装 |
| 没有 `job=stock_change` 的 Run | 检查 `enable_stock_change`、Scheduled Job Log 的 05:47；手动跑一次 |
| 变动 `row_count=0` | 可能是周末/无作业；看 3 天窗口是否有事件；`window_from` 是否过窄 |
| 变动漏了 1–2 天 | 下次运行自动从“上次成功 -1 天”补；**超过 7 天无法补**（通途 API 限制） |
| 526 限流 | 确认测试站定时关闭、Windows API 任务禁用；只保留生产；等退避 |
| API 403 | 调用用户缺少 `Tongtool Stock Latest` 读权限 |
| history API 空 | 日期范围不对（默认 30 天）或 Parquet 不存在 |
| 磁盘 | 2 年约 100–200MB；`df -h /home/frappe` |

## 11. 部署/变更

1. 在 `tongtool_integration` 测试站分支改代码，测试站先跑。
2. PR 合 main。
3. 生产：

```bash
cd /home/frappe/frappe-bench/apps/tongtool_integration
git fetch upstream && git checkout main && git pull upstream main

# 如新增 Python 依赖（duckdb 已装）：
/home/frappe/frappe-bench/env/bin/pip install 'duckdb>=1.0'

cd /home/frappe/frappe-bench
bench --site erpnext.vilavi.cn migrate      # 仅 DocType/字段变更时需要
bench --site erpnext.vilavi.cn clear-cache
bench restart
```

4. 确认只有**一个调度器**在跑：生产 `enable_stock_sync=1`，测试站 `0`，Windows `FZH-TongtuStockApiDaily` 禁用；浏览器 02:17 保留。

## 12. 明确不做

- 不写 EN `Bin` / `Stock Ledger` / 库存单据
- 不把每日 SKU 历史做成 MariaDB 表（历史在 Parquet）
- 不跑独立 DuckDB 服务 / Insights 大屏（当前不需要）
- 不自动提交采购单（以后先建议/草稿/审批）
- 不在 09:23 前后跑测试站全量（会占 Jack 的 API 额度）

## 13. 相关

- `docs/handoffs/2026-10-23-jack-en-stock-sync.md` — 实现/交接清单
- `docs/research/2026-10-23-inventory-history-storage-architecture.md` — 存储选型调研
- app PR #5（基础同步）、#6（重试 + 历史 API）
- 私有仓 `tongtool_integration` 的 `sync/stock_sync.py`
