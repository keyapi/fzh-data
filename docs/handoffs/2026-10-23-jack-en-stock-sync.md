---
okf: v0.1
type: Handoff
title: 给 Jack：在 EN tongtool_integration 落地通途库存每日同步（v1）
description: 每日 05:17 拉通途库存 → EN 当前表 + 单个 Parquet 历史 + 结构化运行日志 + 低库存告警；测试站先行，不在生产跑 DuckDB
date: 2026-10-23
agent: Claude Agent（通途库存存储架构调研）
related_prs: [308, 309, 310]
---

# HAND_OFF：EN 通途库存每日同步（v1）

> 给 Jack：这份只做一件事——在现有 `tongtool_integration` 里把“每天抓一次通途库存”落地。
> 不新建 app、不上 DuckDB/Insights、不写 EN 库存账。按第 10 节 checklist 开工即可。

## 0. 一页结论

| 交付 | 形态 |
|---|---|
| 当前库存 | MariaDB DocType `Tongtool Stock Latest`（每仓×SKU 一行，只读） |
| 运行日志 | MariaDB DocType `Tongtool Stock Run`（每次运行一行，结构化 log） |
| 历史 | **单个 Parquet**：`/home/frappe/fzh-inventory/stock.parquet`，每天原子替换 |
| 告警 | 同一次抓取顺带算低库存，钉钉推送（复用 PR #309 规则） |
| 调度 | `17 5 * * *`，long 队列，14 个启用仓 |

**不做**：DuckDB/Insights、Bin/Stock Ledger、每日 S3、日/月 Parquet 分区、自动下单。

## 1. 背景与复用

- 通途库存目前有两条 Windows 线：浏览器导出（02:17）和 API 全量备份（05:17）。本次把 **API 抓取**搬到 EN；浏览器线保留（结存 + 成本模板 + 销售报表）。
- 现有代码：
  - `D:\Work\fzh-stock-backup\stock_daily_backup.py`：抓取/分页/JSONL/manifest/run state 的参考；逻辑可搬，**不要直接依赖这个目录**。
  - `stock_alert/`（PR #309，已 approve）：API 客户端、13 秒节流、526 退避、低库存过滤与钉钉投递；**复用其规则**。
- EN 测试站已有 `tongtool_integration`（分支 `feat/throttled-refresh`）；生产为 `main`。凭证在 `Tongtool Settings`，不要新建 `.env`。
- 现有 3 个凌晨任务：订单同步约 01:00、订单更新约 02:00、包裹同步约 04:00–04:30。库存任务放 **05:17**，避开这些窗口。

## 2. v1 范围

1. 每日 05:17 拉全部启用仓（当前 14 个）。
2. upsert `Tongtool Stock Latest`。
3. 追加到单个 Parquet `stock.parquet`（tmp + 原子替换）。
4. 写 `Tongtool Stock Run`（成功/失败/缺失仓/行数/耗时）。
5. 同批数据算低库存，推钉钉；稳定后停 Jack 本地 `FZH-StockAlert-daily`（09:23）。
6. 不写 EN `Bin` / `Stock Ledger` / 库存单据。

## 3. 数据契约

### 3.1 `Tongtool Stock Latest`（当前，只读）

| 字段 | 类型 | 说明 |
|---|---|---|
| name | Data（主键） | `{warehouse_id}:{sku}` |
| warehouse | Data | 仓库名，精确匹配 |
| warehouse_id | Data | 通途仓库 ID |
| sku | Data | `goodsSku` |
| available | Float | `availableStockQuantity` |
| intransit | Float | `intransitStockQuantity` |
| waiting_shipment | Float | `waitingShipmentStockQuantity` |
| defects | Float | `defectsStockQuantity` |
| avg_cost | Float | `goodsAvgCost` |
| snapshot_at | Datetime | 本次抓取完成时间 |
| source | Data | `tongtool_api` |
| run_id | Data | 关联 Run |
| schema_version | Int | 1 |

- 唯一键用主键或 `(warehouse_id, sku)` 唯一索引。
- 每天 bulk upsert（`INSERT ... ON DUPLICATE KEY UPDATE` 或删后插），约 5k 行。
- 权限：业务用户只读；只有 scheduler/系统用户可写。

### 3.2 `Tongtool Stock Run`（结构化运行日志，1 行/次）

`run_id`（主键）、`snapshot_date`、`snapshot_at`、`started_at`、`finished_at`、`status`、`complete`、`warehouse_count`、`row_count`、`missing_warehouses`（Text/JSON）、`error_summary`、`source`（scheduled/manual）、`schema_version`、`data_path`。

> 这就是“运行表”，本质是结构化 log；有了它，EN 页面/告警/审计不用去翻文件。若暂时不想建 DocType，可先把同样的字段写进一个 JSON 日志；但建议保留，1 行/天成本极低。

### 3.3 历史 Parquet（单个文件）

- 路径：`/home/frappe/fzh-inventory/stock.parquet`
- 列：`snapshot_date DATE`、`snapshot_at TIMESTAMP`、`warehouse_id`、`warehouse_name`、`sku`、`available`、`intransit`、`waiting_shipment`、`defects`、`avg_cost`、`source`、`run_id`、`schema_version`。
- 每天：读旧文件 + 当天新行 → 写 `stock.tmp.parquet` → `os.replace` 原子替换；成功前保留 `stock.prev.parquet` 用于回滚。
- 2 年约 112MB；**先不要按天/按月分区**（小文件问题）。
- JSONL 只作 7–30 天调试副本，不做长期存储。
- 幂等：同一天重跑时替换该天行，不追加重复行；Parquet 重写覆盖当天快照。

## 4. 实现细节

- 代码：`tongtool_integration/sync/stock_sync.py`。
- 调度：`hooks.py` 增加 `"17 5 * * *": ["tongtool_integration.sync.stock_sync.sync_daily_stock_snapshot"]`；方法内部 `frappe.enqueue(..., queue="long", timeout=7200)`，避免阻塞 default 队列。
- 仓库：`erp2_basedata_warehousequery` 取 `status=1` 的仓；当前 14 个。
- 库存：`erp2_stocks_stocksquery`，`warehouseName` 必填，`pageSize=100`（服务端上限），`pageNo` 翻到短页为止。
- 节流/重试：每次调用间隔 13 秒；HTTP 502/503/504 重试 10s/20s；业务码 526 60s 指数退避；4xx（524/525 等）直接报错。
- 写 Parquet：EN bench env 有 pandas 但**没有 pyarrow/duckdb**。给 app 加 `duckdb` 依赖（单 wheel），用：
  ```python
  con = duckdb.connect()
  con.register("df", df)
  con.execute("COPY df TO ? (FORMAT PARQUET)", [str(tmp_path)])
  ```
  测试站 `bench setup requirements`；**生产要手动在 bench env 安装**（生产不会自动跑 app 依赖）。
- 失败：单仓异常不阻断其他仓；`complete=false`、缺失仓写进 Run；Parquet 只在有行时重写，失败保留旧文件。
- 安全：不打印/不落库 SKU 级以外的敏感信息；凭证只用 `Tongtool Settings`。

## 5. 低库存告警

- 用同一批内存行计算，不再单独拉 API。
- 规则复用 PR #309：`available < 阈值` 且排除「可用=0 且在途=0」的死库存；正文注明“登记层提醒，不等于断货”。
- 先只监控 3 个主仓（美中/美东/波兰）；需要扩仓再改配置。
- 钉钉凭证沿用现有 `DINGTALK_WEBHOOK` / `DINGTALK_SECRET`（或 `*_STOCK` 覆盖键）。
- 稳定 3–5 天后停 Jack 本地 09:23 任务，避免双跑。

## 6. 测试与验收

在 **EN 测试站**（`sh-erpnext-test-frappe`，4C/7.1G）先跑：

1. 单元测试：分页、526/502 重试、upsert 幂等、Parquet 原子替换、同一天重跑不重复。
2. 手工跑一次：14 仓、约 5k 行、`Run.complete=true`、`missing_warehouses=[]`。
3. 回读：
   ```sql
   SELECT count(*), sum(available) FROM read_parquet('/home/frappe/fzh-inventory/stock.parquet');
   ```
   行数与 Latest 一致（按 snapshot_date 过滤）。
4. 连续 3–5 天定时跑：每天 `complete=true`，行数在预期范围（约 4.5k–5.5k）。
5. 与 Windows 的浏览器/API 产物抽查：同仓同 SKU 的 4 个数量字段一致；允许少量时间差。
6. 低库存：dry-run 正文 + 一次真实钉钉。
7. 确认无 `Bin` / `Stock Ledger` 写入。

## 7. 部署顺序

1. 测试站 `feature/stock-sync`（基于 `feat/throttled-refresh`）：已 migrate、已装 duckdb；跑 3–5 天。
2. 合并 app PR #5（`feature/stock-sync-main`，从 main 拉出）到 `main`；生产按现有链路 `pull → migrate → 装 duckdb → clear-cache → restart`。
3. 生产只跑抓取 + 当前表 + Run；**不要在生产跑 DuckDB/Insights/重分析**（2C/3.5G）。
4. 生产稳定后停 Windows `FZH-TongtuStockApiDaily`，只保留浏览器导出。

手动单仓测试命令（测试站）：

```bash
cd /home/frappe/frappe-bench
bench --site erpnext.vilavi.cn execute \
  tongtool_integration.sync.stock_sync.run_stock_snapshot \
  --kwargs '{"warehouses": "美中-FZH-DANEEY", "source": "manual"}'
```

### 7.1 目录与权限（先做）

测试站（Jack 有权限）和生产（你有权限）都先建同一目录：

```bash
sudo mkdir -p /home/frappe/fzh-inventory
sudo chown frappe:frappe /home/frappe/fzh-inventory
sudo chmod 750 /home/frappe/fzh-inventory
# 可选：备份/调试子目录
sudo -u frappe mkdir -p /home/frappe/fzh-inventory/backup /home/frappe/fzh-inventory/debug
# 写权限自检
sudo -u frappe touch /home/frappe/fzh-inventory/.write_test
sudo -u frappe rm /home/frappe/fzh-inventory/.write_test
df -h /home/frappe
```

- 测试站如果当前 SSH 用户就是 `frappe`，可省略 `sudo`。
- 目录在站点 `public` 之外，不会被 nginx 直接访问。
- 代码里仍要 `Path(dir).mkdir(parents=True, exist_ok=True)` 兜底，但预建能提前暴露权限问题。
- 生产顺序：**建目录 → 部署 app + 安装 `duckdb` → 手工跑一次 → 核对 Latest/Run/Parquet → 再开定时 → 最后停 Windows API 任务**。
- 生产装依赖：`/home/frappe/frappe-bench/env/bin/pip install duckdb`（生产不会自动跑 app 依赖）；测试站用 `bench setup requirements` 或同样 pip 安装。

## 8. 以后可加（现在不做）

- 数据 >1GB、重写 >2–3s、或需要历史不可变/局部恢复 → 拆成**一年一个 Parquet**（只重写当年），不要按天/按月。
- 需要历史趋势/预测 → 测试站或分析机用 DuckDB 读 `stock.parquet`；AI/外部服务也可直接读。
- 需要 EN 页面显示关键状态 → 加 `Tongtool Stock Status`（覆盖天数/断货风险）由后台任务写小表。
- 自动下单 → 先建议/草稿/审批，不自动 submit。
- BI 大屏不是当前需求；Insights 以后有真实自助分析需求再装，连只读 Parquet/快照。

## 9. 相关

- PR #309（stock_alert 低库存，已 approve）：`stock_alert/client.py`、`scan.py`、`notify.py`。
- PR #308（两条 Windows 线体检）：以后可改为读 EN 的 Run/Parquet。
- PR #310（调研）：`docs/research/2026-10-23-inventory-history-storage-architecture.md`。
- 参考脚本：`D:\Work\fzh-stock-backup\stock_daily_backup.py`（分页/重试/run state 逻辑）。

## 10. 实现进度（2026-10-23）

- **app PR**：https://github.com/keyapi/tongtool_integration/pull/5 已合并 main（`5a6d28e`）
- **测试站**：已切 main；单仓 1,024 行、全量 **5,316 行 / 14 仓 / complete=true / 64 次调用**；Parquet/Latest/Run 一致
- **生产**：已 pull main（`5a6d28e`）、装 `duckdb 1.5.6`、migrate、restart；单仓 1,024 行 + 全量 **5,316 行 / 14 仓 / complete=true / 64 次调用**；Parquet 5,316 行 / 10 个有数据仓、Latest 5,316 行、Run Success
- **生产已启用** `enable_stock_sync=1`（05:17）；只有生产这一路在跑
- **测试站定时已关闭**（`enable_stock_sync=0`），避免与生产重复抓取同一 5 次/分钟额度
- **Windows API 任务** `FZH-TongtuStockApiDaily` 已禁用（保留为手动回退，未删除）；浏览器导出 02:17 保留
- **历史起点**：EN Parquet 目前只有 2026-10-23；如需接上 10/20–10/22 的 Windows JSONL，做一次性 backfill 即可
- **低库存告警**：未并入 v1，Jack 后续按 §5 接入
- **体检脚本**（PR #308）：目前仍看 Windows 两条线；API 线迁 EN 后需改为读生产 Parquet/Run（后续）
- ⚠️ **安全**：`test_fix.py` 含硬编码 app_secret（已跟踪），请尽快轮换并清理；本实现不使用该文件

## 11. Jack 开工 checklist

- [x] 测试站建目录/权限（`/home/frappe/fzh-inventory`，`frappe:frappe`）。
- [x] 生产建目录/权限（你有权限，Jack 没有）。
- [x] 测试站拉 `feat/throttled-refresh`，确认 `Tongtool Settings` 凭证可用。
- [x] 新建 `Tongtool Stock Latest` / `Tongtool Stock Run` DocType（只读、无 Bin）。
- [x] 写 `sync/stock_sync.py`：14 仓抓取 + 13s 节流 + 502/526 重试。
- [x] 写单 Parquet：tmp + `os.replace`，保留 `stock.prev.parquet`。
- [x] 加 `duckdb` 依赖并在测试站安装。
- [x] `hooks.py` 注册 05:17、long 队列。
- [x] 合并 main、推生产并实测（14 仓 5,316 行，complete=true）。
- [x] Windows API 任务已禁用（保留手动回退）；浏览器导出 02:17 保留。
- [ ] 低库存告警复用 PR #309 规则；先 dry-run。
- [ ] 低库存并入 EN 后，停 Jack 本地 `FZH-StockAlert-daily`。
- [ ] 连续 3–5 天验收；体检脚本改为读生产 Parquet/Run。
