---
okf: v0.1
type: Research
title: 通途库存「当前记录 + 每日历史」放哪最好 —— EN、DuckDB、NAS 与云端可靠性调研
description: 实测 EN 测试/生产服务器规格与磁盘、确认 /mnt/nas 并非 NAS 挂载、核实 DFP S3（香港 OSS 桶仍在但跨区、生产 internal 端点超时、NAS MinIO 可达）、盘点现有浏览器导出/Windows API 备份/Jack PR #309 低库存/demand_forecast DuckDB；给出「当前进 EN、历史进上海云盘 + OSS 镜像 + DuckDB」的分层方案
tags: [tongtool, inventory, erpnext, duckdb, nas, backup, architecture, research]
timestamp: 2026-10-23
---

# 通途库存「当前记录 + 每日历史」放哪最好

> 问题：通途库存的**当前值**可以写进 EN；**每日历史**要不要也进 EN？还是外挂 DuckDB？
> 背景：NAS 在北京办公室、可能断电；Jack 的低库存任务跑在他本地电脑；本地电脑不如云端可靠。
> 结论：**当前值进 EN（只读最新快照），历史不进 EN；原始文件放 EN 上海云盘，并镜像到 OSS（现有香港桶已实测可写，跨区慢；要快就上上海桶），DuckDB 只做查询层，且不要跑在生产（2C4G）。**

- 日期：2026-10-23
- 调研范围：EN 测试/生产服务器、现有两条通途库存流水线、Jack 低库存实现、demand_forecast DuckDB
- 全程只读探测；未改任何服务器配置、未写通途数据；S3 探针写/删了 1.5MB 临时对象（put/stat/get/remove 后清理）

## 1. 一句话结论

| 数据 | 放哪 | 理由 |
|---|---|---|
| 当前库存（每仓×SKU 一行） | EN 只读 DocType `Tongtool Stock Latest` | 运营要在 EN 里看，量小（约 5k 行） |
| 每日历史原始文件 | EN 云盘（上海）+ 镜像到 OSS | 云端供电/网络比办公室 NAS/Windows 稳；文件很小 |
| 历史查询/预测 | DuckDB（测试站或分析机），**不在生产** | 分析型 as-of/窗口/join 是 DuckDB 强项；生产只有 3.5G 内存 |
| 备份副本 | 现有香港 OSS（已实测可写，跨区慢）/ 上海区 OSS（更快，需新建）/ NAS MinIO（快但断电） | 香港桶日增量可用（0.42/0.19 MB/s，年成本约 ¥0–10）；多年远读慢；NAS 不能当唯一副本 |
| 低库存告警 | 与库存抓取**同一次拉取**，在 EN 跑 | 避免第二次 API 拉取和 5 次/分钟争抢；摆脱 Jack 本地电脑 |

## 2. 实测事实（2026-10-23）

### 2.1 EN 服务器

| 项 | 测试站 `sh-erpnext-test-frappe` | 生产 `阿里云-FZH-ERPNext-frappe` |
|---|---|---|
| 主机 | `iZuf6cg60rfql8k8qbw87xZ` | `iZuf61samgos1urs5cvp2iZ` |
| CPU / 内存 | 4 vCPU / 7.1 GiB（可用 1.6 GiB） | 2 vCPU / 3.5 GiB（可用 1.2 GiB） |
| 根盘 | 118G，**51G 空闲** | 492G，**319G 空闲** |
| `/mnt/nas` | **不是挂载点**；`df` 显示同一块根盘 | 同样不是挂载点 |
| NAS 挂载 | `mount` 无 nfs/cifs/smb | 无 |
| DFP S3 配置 | 2 条记录：`aliyun-erpnext-hk`（OSS 香港，公开端点）+ `NASMinio`（`fzh.myds.me:9000`，`en.media`） | 同左；生产用的是香港 **internal** 端点，已超时 |
| S3 客户端 | `minio` 7.2.5（bench env）；无 `ossutil`/`oss2`/RAM 角色 | 同左 |
| DuckDB | 未安装 | 未安装 |
| `tongtool_integration` | 已装，分支 `feat/throttled-refresh` | 已装，分支 `main` |
| 长任务 worker | 4 个 `queue long,default,short` | 有 long 队列（历史记录） |
| 出网 `mcp.tongtool.com` | 通（无凭证 POST 返回 401） | 未单独复测，按同云同地域推断 |

关键更正：**`/mnt/nas` 不是北京 NAS 的挂载**，只是云服务器本地目录。北京 NAS 目前没有挂到 EN 上；所以“写到 `/mnt/nas`”实际是写云盘，反而比 NAS 可靠。

### 2.2 数据体量（按 2026-10-22 实际产物）

- API 全量快照：14 个仓、**1.49 MB/天**（JSONL，未压缩）→ 约 **545 MB/年**。
- Parquet 压缩后通常 **50–100 MB/年**；DuckDB 表再加 **200–300 MB/年**。
- 现有订单 DuckDB：`D:\Work\fzh-order-store\order_store.duckdb` **222 MB**，45 个月 **407,898 行**（PR #290）。
- 结论：**测试站 51G 空闲对这个数据集完全够用**，不是瓶颈；真正的瓶颈是生产内存（3.5G），不是磁盘。

### 2.3 现有资产

| 资产 | 位置 | 现状 |
|---|---|---|
| 浏览器库存结存导出 | `web_automation/legacy-compatible/tongtu_auto_export.py`（02:17 Windows 任务） | 4 个有数据仓、约 4,575 行；含成本/状态/别名 |
| 浏览器销售及库存报表 | `tongtu_sales_report.py` | 约 1,954 行/8 仓；含 7/15/30/90 天销量，无故障品 |
| Windows API 全量备份 | `D:\Work\fzh-stock-backup\stock_daily_backup.py`（05:17） | JSONL + manifest + runs 封存；仓库外、非 git 管理；2026-10-23 修复后手工重跑 **complete=True**（64 次调用、14 仓） |
| 库存体检（两条 Windows 线） | PR #308 / `scripts/inventory_daily_health.py` | 07:17 体检 + 离线互证；API/Excel 失败告警；后续可改读 EN 产物 |
| Jack 低库存 | PR #309（`feat/stock-alert-low-stock-dingtalk`，open） | 3 仓、可用<5、过滤死库存；钉钉汇总；>10 个时 Excel 经 EN 文件上传发 ActionCard；跑 Jack 本地 Windows（任务 09:23）；33 tests 已通过 |
| demand_forecast DuckDB | PR #290 / 分支 `claude/affectionate-bell-93d3ec` | 45 个月订单 DuckDB + GSheet 原样 Parquet；已有 `tongtool_stock_snapshot.py` 写库存快照 |
| supply-chain 备份方案 | `docs/research/supply-chain/2026-10-20/claude/14-daily-inventory-backup.md` | 已建议 Parquet/DuckDB、禁写 EN Bin、测试站试点 |

Jack 的 Excel 上传**只是 EN 文件附件**（`send_file_card` → ERPNext 文件 + 钉钉卡片），**没有**在 EN 建库存记录；所以“EN 里能看当前库存”目前还不存在，需要新建只读 DocType。

### 2.4 DFP S3 / OSS 实测

`dfp_external_storage` 已装在测试与生产，配置了两条 S3 Compatible 存储：

| 记录 | 类型 | endpoint | bucket | 状态 |
|---|---|---|---|---|
| `DFP.ES.bainaimgs.240418.01` | 阿里云 OSS 香港 | 测试 `oss-cn-hongkong.aliyuncs.com`；生产 `oss-cn-hongkong-internal.aliyuncs.com` | `erpnext-hk` | 桶存在（公开端点 403）；**生产 internal 端点从上海连超时** |
| `DFP.ES.en.media.240418.02` | NAS MinIO | `fzh.myds.me:9000` | `en.media` | 当前可达（200）；办公室断电风险 |

- DFP 不是 POSIX 挂载，而是 Frappe 的 S3/MinIO 文件存储后端；`doc.client` 是 `MinioConnection`，有 `put_object` / `list_objects` / `stat_object` / `remove_object`。可以直接用它写库存 JSONL，不必建 Frappe File 记录。
- 阿里云 OSS 桶 `erpnext-hk` **还在**（未授权 403 = 桶存在），但它是**香港区**；EN 已迁到上海，跨区日增量（约 1.5MB/天）可接受，但不适合把多年历史反复远读。生产配置的 `-internal` 端点在迁移后已不可达，需要改成公开端点或迁到上海桶。
- NAS MinIO `en.media` 当前从测试/生产都能访问，但仍受北京办公室供电影响，只能做副本。
- 凭证在 `DFP External Storage` DocType 内（`access_key` / 加密的 `secret_key`），运行时用 Frappe 读取；**不要把凭证复制到仓库或脚本**。
- 写探针已完成：在 EN 测试站用 `bench console` + 显式 `Minio(secure=True)` 对香港桶做了 1.5MB put/stat/get/remove，全部成功；NAS MinIO 同样成功。速度与成本见 §2.5。
- 注意：DFP 记录里香港 OSS 的 `secure=0`（HTTP）；探针用的是 HTTPS。正式写入建议把该字段改为 1，或用显式 `Minio(secure=True)`。

### 2.5 香港 OSS 速度与成本实测（EN 上海测试站 → 香港）

2026-10-23 实测（1.5MB 随机文件，put → stat → get → delete）：

| 目标 | 上传 | 下载 | 小对象 RTT |
|---|---|---|---|
| 香港 OSS `erpnext-hk`（HTTPS） | 3.61s（**0.42 MB/s**） | 8.00s（**0.19 MB/s**） | ~0.33s |
| NAS MinIO `en.media`（HTTP） | 0.66s（**2.27 MB/s**） | 0.21s（**7.21 MB/s**） | 0.07–0.17s |

- 每日全量约 **1.5MB**（14 个 JSONL）：香港桶上传约 4 秒、下载约 8 秒，**日增量镜像可用**；但按 0.19 MB/s 算，1GB 历史下载要 ~1.5 小时，**不适合多年历史反复远读**。
- NAS MinIO 快一个数量级，但办公室断电/断网就不可用；适合做**本地缓存/第二副本**，不能当唯一。
- 建议把一天的文件**打包成 1 个 tar.gz 或 1 个 Parquet** 再上传，减少 14 次小请求与 RTT。

成本（按 2026 年公开价，具体以官网为准）：

- **创建存储桶本身免费**；OSS 按存储量、请求数、外网下行流量计费，没有固定月费。
- 香港标准存储约 **¥0.136/GB/月**（部分价目表首 5GB 免费）或国际站约 **$0.0173/GB/月**；外网下行约 **$0.076/GB**；PUT/GET 有较大免费额度。
- 本项目体量：1.5MB/天 ≈ **0.55GB/年**，2 年 <2GB；每天约 14 次 PUT、少量 GET，远低于免费额度；即使算上行下载，年成本约 **¥0–10**。**主要代价是跨区速度，不是钱。**
- 上海区新桶与香港桶的价格同一量级；同区可走内网端点、免外网下行，速度也快。开新桶的“成本”主要是配置/凭证/运维，而不是账单。

**结论**：现有香港桶可以直接用，加 `fzh-inventory/` 前缀即可，无需新建桶；每日镜像完全可行。若以后要频繁做 DuckDB 分析/回填，建议上海区新桶或本地/NAS 缓存，不要每次都跨区读。

## 3. 方案对比

| 方案 | 当前库存 | 历史 | 可靠性 | 结论 |
|---|---|---|---|---|
| A. 全部进 EN（含历史表） | EN | EN | 云端稳 | ❌ 事务库膨胀、备份/迁移变重、易和 Bin 混淆 |
| B. 当前进 EN，历史放 EN 云盘 + DuckDB | EN | 云盘 + DuckDB | 云端稳 | ✅ **推荐** |
| C. 当前进 EN，历史放北京 NAS | EN | NAS | NAS 当前可达，但办公室会断电 | ⚠️ 只能做副本，不能当唯一 |
| D. 当前进 EN，历史放现有香港 OSS | EN | OSS 香港 | 桶存在，但上海跨区 | ⚠️ 日增量可用；多年远读不划算 |
| D2. 当前进 EN，历史放**上海区 OSS** | EN | OSS 上海 | 同区、最稳 | ✅ 若能开通，作为首选主副本 |
| E. 维持 Windows + Jack 本地 | 无 | Windows | 最差 | ❌ 停电/关机即断 |
| F. DuckDB 放生产 | — | 生产 | 2C4G、1.2G 可用 | ❌ PR #290 已记录批量回填 OOM 压死机器 |

## 4. 推荐架构

```text
                    每日 05:17（EN 测试站，long 队列）
通途 ERP2 API  ─────────────────────────────────────────────┐
 erp2_basedata_warehousequery                                │ 一次全量拉取
 erp2_stocks_stocksquery（pageSize=100，13s，502/526 重试）   │
                                                              ▼
                 ┌──────────────────────────────┬──────────────────────────────┐
                 │ EN 只读 DocType               │ EN 云盘原始层                  │
                 │ Tongtool Stock Latest         │ /home/frappe/fzh-inventory/    │
                 │ 每仓×SKU 一行，约 5k 行        │   YYYY-MM-DD/*.jsonl           │
                 │ 不写 Bin/Stock Ledger         │   manifest.json                │
                 └──────────────────────────────┴──────────────────────────────┘
                                                              │  异步镜像
                                                              ▼
                                              上海区 OSS（首选）/ 香港 OSS 公开端点
                                              prefix: fzh-inventory/YYYY-MM-DD/
                                                              │
                                                              ▼
                 ┌──────────────────────────────┬──────────────────────────────┐
                 │ 低库存告警（同一批内存行）      │ DuckDB（测试站或分析机）        │
                 │ 钉钉汇总 + 可选 Excel          │ inventory 视图 + order_store   │
                 └──────────────────────────────┴──────────────────────────────┘
                                                              │
                                                              ▼
                                              销量预测：断货剔除 / censored 标记
```

### 4.1 EN 当前快照 DocType

- 名称：`Tongtool Stock Latest`（独立表，只读）。
- 字段：`warehouse`、`warehouse_id`、`sku`、`available`、`intransit`、`waiting_shipment`、`defects`、`avg_cost`、`snapshot_at`、`source`、`run_id`。
- 唯一键：`name = f"{warehouse_id}:{sku}"`（或用 `sku + warehouse` 建唯一索引）。
- 更新：每天 `DELETE FROM` 后 bulk insert，或 MariaDB `INSERT ... ON DUPLICATE KEY UPDATE`；约 5k 行，秒级。
- 权限：所有业务用户只读；只有 scheduler 写。
- **不建子表历史、不写 Bin/Stock Ledger/单据**；历史在文件层。
- 可选：`Tongtool Stock Snapshot Run` 头表（run_id、snapshot_at、warehouse_count、row_count、complete、error_summary），用于健康检查。

### 4.2 历史原始层

- 路径：`/home/frappe/fzh-inventory/YYYY-MM-DD/warehouse=<id>_<name>.jsonl` + `manifest.json`。
- 镜像：异步上传到上海区 OSS（首选）；暂无上海桶时用现有香港桶的**公开端点**（`oss-cn-hongkong.aliyuncs.com`），不要用生产配置里的 `-internal` 端点（已超时）。NAS MinIO 只作第三副本。
- 保留：JSONL/Parquet 13–24 个月；DuckDB 视图可覆盖全部。
- 原子写 + manifest 记录 `complete`、每仓 pages/rows、文件 sha256；失败仓标 `complete=false`，不写 0。
- **原始文件是唯一事实源**；DuckDB 可随时从文件重建，不做唯一副本。

### 4.3 DuckDB 放哪

- **短期**：分析机（Windows）现有 `order_store.duckdb`（222MB）。EN 每天写原始文件，分析机按日同步后加载；与订单历史直接 join。
- **中期**：EN 测试站 4C/7G 可跑只读 DuckDB（1.6G 可用，数据量小）；但测试站是共享环境，建议单独目录/进程，不要塞进 Frappe worker。
- **生产**：**不要**跑 DuckDB（2C/3.5G、1.2G 可用；PR #290 已有 OOM 记录）。
- 如果将来需要多人共享查询，单独开一台小云主机/容器跑 DuckDB，挂只读文件，不碰 EN。

### 4.4 低库存告警合并

- 目标：**一次 API 拉取**同时产出当前快照、历史文件、低库存告警；不要 Jack 本地任务再拉一遍。
- Jack 的 PR 还没提交，先不 fork。等他 PR 落地后：
  - 复用 `stock_alert/scan.py`（阈值/死库存过滤）与 `notify.py`（钉钉汇总/Excel）逻辑；
  - 在 EN 定时任务里直接调用这些规则（或把纯函数抽到共享模块）；
  - 停掉 Jack 本地 `FZH-StockAlert-daily`，避免双跑和重复 API 调用。
- 告警仍遵守“可用=0 ≠ 断货”的口径：过滤“可用=0 且在途=0”的死库存，正文注明登记层提醒。

### 4.5 断货剔除（销量预测）

- 历史快照与订单历史在 DuckDB join：`snapshot_date × warehouse × sku`。
- 候选断货日：`available=0 且 intransit=0 且无在途补货/采购单`；预测时剔除或做 censored-demand。
- **不能只看 available=0**：通途为标记发货会先报溢，美中长期显示 0（见 `cargo-location-tracking-source-reliability.md`）。候选需结合订单下降、在途、补货单与人工例外。

## 5. 限流与调度（关键）

- 商户级 **5 次/分钟**，多 App、多服务器共享；**放测试站也一样占用同一额度**，不会因为不是生产就更快。
- 全量 14 仓约 64 次调用、约 14 分钟（pageSize=100，13 秒/页）。
- 调度 **05:17**，避开现有 3 个凌晨同步任务（约 01:00 / 02:00 / 04:00–04:30）。用 **long 队列**，避免阻塞 default 队列。
- 2026-10-23 实测通途 MCP 对美东仓返回 **502 Bad Gateway**；必须做 502/503/504 重试（10s/20s），526 继续 60s 指数退避。
- 只允许**一个**调度器跑全量（EN 或 Windows 二选一），否则双倍调用必然 526。
- **S3 端点**：EN 测试用香港 OSS 公开端点可写；生产 DFP 配的 `oss-cn-hongkong-internal.aliyuncs.com` 在迁到上海后已超时，使用前必须改成公开端点或换上海桶。跨区只适合日增量小文件；DuckDB 查询前先把文件拉到本地。

## 6. 分阶段建议

| 阶段 | 做什么 | 验收 |
|---|---|---|
| P0 测试站试点 | `tongtool_integration` 加 `sync/stock_sync.py` + `17 5 * * *`；写云盘 JSONL/manifest；先不写 EN DocType | 连续 3–5 天 `complete=true`，14 仓齐全 |
| P1 当前快照进 EN | 加只读 `Tongtool Stock Latest` + run 头表；每日覆盖 | EN 里能看到当天库存；行数约 5k；无 Bin 变化 |
| P2 告警合并 | Jack PR 落地后接入低库存规则；钉钉；停本地任务 | 同一批数据同时出告警；只调用一次 API |
| P3 生产决策 | 评估把抓取放生产（轻量，主要是网络/写文件）还是留测试站；DuckDB 绝不进生产 | 502/526 可控；生产内存无明显增长 |
| P4 预测接入 | 原始文件 → DuckDB；与订单历史 join；断货 censored 标记 | 能回答“某 SKU 某日是否因断货缺销量” |

## 7. 明确不做

- 不把每日历史写进 EN 的事务表/DocType。
- 不写 EN `Bin` / `Stock Ledger Entry` / 库存单据。
- 不拿北京 NAS 当唯一/主存储（会断电、且目前根本没挂到 EN）。
- 不在生产 2C4G 上跑 DuckDB 或预测批量任务。
- 不让 Windows 和 EN 同时抓全量库存。
- 不为库存历史单独再写一个取数器；复用现有 `erp2_stocks_stocksquery` 客户端与 Jack 的规则。

## 8. 待确认

1. **抓取放测试站还是生产？** 建议先测试站；生产网络/磁盘更足但内存小，抓取本身轻，可作为 P3 决策。
2. **DuckDB 长期放哪？** 建议先分析机（已有 222MB 订单库）；要多人共享再上独立小云主机。
3. **云盘备份方式**：现有香港桶已实测可写（0.42/0.19 MB/s，年成本约 ¥0–10），可直接用 `fzh-inventory/` 前缀做日增量镜像；上海区新桶主要解决**速度**，不是省钱。生产 DFP 的 `-internal` 端点需要修或迁到上海桶。
4. **Jack PR 合并时间**：PR #309 已提交、33 tests 通过；合并后再接低库存规则，避免两套代码。
5. **EN 当前快照是否要映射 `item_code`**：先用通途 SKU；映射到 EN Item 作为下一步。
6. **S3 写入能力**：需在有权限的 frappe 进程里补一次 1 字节 put/stat/remove 探针（本次因 `/home/frappe/logs` 权限未完成）。

## 9. 证据命令（只读）

```bash
# 服务器规格 / 磁盘 / 挂载
ssh sh-erpnext-test-frappe "free -h; nproc; df -h / /mnt/nas; mount | grep -iE 'nas|nfs|cifs|smb'"
ssh 阿里云-FZH-ERPNext-frappe "free -h; nproc; df -h / /mnt/nas; mount | grep -iE 'nas|nfs|cifs|smb'"

# 出网
ssh sh-erpnext-test-frappe "curl -sS -m 10 -o /dev/null -w '%{http_code}' -X POST https://mcp.tongtool.com/mcp -H 'Content-Type: application/json' -d '{}'"

# 体量
du -sh D:/Work/库存备份/2026-10-22          # 1.49 MB, 14 files
ls -lh D:/Work/fzh-order-store/order_store.duckdb   # 222 MB

# DFP S3 桶是否还在（403=存在，404=不存在）
ssh sh-erpnext-test-frappe "curl -sS -m 8 -o /dev/null -w '%{http_code}' https://erpnext-hk.oss-cn-hongkong.aliyuncs.com/; echo"
ssh 阿里云-FZH-ERPNext-frappe "curl -sS -m 8 -o /dev/null -w '%{http_code}' https://erpnext-hk.oss-cn-hongkong.aliyuncs.com/; echo"
ssh sh-erpnext-test-frappe "curl -sS -m 8 -o /dev/null -w '%{http_code}' http://fzh.myds.me:9000/en.media/; echo"

# DFP 配置（不打印 access_key/secret_key）
ssh sh-erpnext-test-frappe "cd /home/frappe/frappe-bench && bench --site erpnext.vilavi.cn mariadb -e 'SELECT name,title,type,endpoint,secure,bucket_name,region,enabled FROM \`tabDFP External Storage\`;'"
```

## 10. 相关文档

- `docs/research/supply-chain/2026-10-20/claude/14-daily-inventory-backup.md` — 每日备份现状、DuckDB/Parquet、EN DocType 取舍
- `docs/solutions/workflow-issues/tongtool-inventory-daily-health.md` — 当前两条 Windows 线的体检（PR #308）
- `docs/solutions/architecture-patterns/order-history-duckdb-store.md` — 订单历史 DuckDB 分层（PR #290）
- `docs/solutions/workflow-issues/cargo-location-tracking-source-reliability.md` — 通途“可用 0”不可信
- `docs/solutions/integration-issues/en-tongtool-order-package-sync-failures.md` — EN 通途同步的 300s/526/重叠

## 11. 价格与测速来源

- 阿里云 OSS 计费概述: https://www.alibabacloud.com/help/zh/oss/billing-overview
- OSS 计费项（存储/请求/流量）: https://www.alibabacloud.com/help/en/oss/billable-item-overview
- 阿里云 OSS 价格详情: https://www.aliyun.com/price/detail/oss
- 2026 国际站 OSS 价格分析（含香港/海外参考）: https://sevencoloryun.com/blog/aliyun-oss-pricing-cost-comparison-2026/
- OSS 香港端点与用法: https://cloudinsight.cc/en/blog/alibaba-cloud-oss-guide

> 测速为 2026-10-23 从 EN 上海测试站到香港 OSS / NAS MinIO 的单文件 1.5MB put/stat/get/remove，网络状况会波动；价格以官网当期为准。
