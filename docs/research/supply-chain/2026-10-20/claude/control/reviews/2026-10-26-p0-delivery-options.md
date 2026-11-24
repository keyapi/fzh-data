---
okf: v0.1
type: Review
title: P0 供应时间线交付形态：现状、选项与抉择（待 Codex 审）
date: 2026-10-26
owner: claude-foreman
status: 待审；未派工
---

# P0 供应时间线交付形态

> **一句话**：P0 不是“再写一个脚本”，而是决定 **供应时间线快照在哪算、存哪、谁看、谁运维**。
> 当前 W1 v0 是本地 Python 原型；EN `key_test` 已在生产；SO 表单/报表是**订单视角**，不是供应计划表。
> 请 Codex 审：**A 本地脚本 / B EN 原生 / C 混合 / D 外部服务 / E 本地+独立网页** 哪条做主路线。

## 1. 现状

### 1.1 数据源与已有资产

| 资产 | 现状 | 约束 |
|---|---|---|
| 通途库存 | 每日 **05:17** 备份到 `D:\Work\库存备份\YYYY-MM-DD\*.jsonl + manifest.json`；14 仓，完整日约 5,314 行 | 本机 Windows 任务；不完整批要标 unknown |
| 通途 PO | API/MCP；`tongtool_po` 524 行 / 未结 248；`will_arrive_date` 全空 | 5 次/分钟共享限流；与 EN 01:00/02:45/04:30 同步要错峰 |
| EN 单据 | SO / WO / Job Card / DN / Shipment / Stock Entry；生产 REST 只读 | 生产只读闸门：300 请求 / 32 MiB / 900 秒/批 |
| W1 v0 | #312；9 SKU；233 行；B_min 1,212 / B_max 2,762+433；本地 Python，输出 CSV/JSON | 未调度、未入 EN；冻结基准 10-22 |
| #291 履约入口 | `EN_API/fulfillment_query.py`，SO→生产→出库，JSON 权威 | 本地 CLI，不是 EN 服务 |
| `key_test` app | SO 表单嵌入 + `SO Chain Overview` 报表；**生产已部署**（用户 2026-10-26 确认） | 仓库旧 `key_test/AGENT_HANDOFF.md` 仍写“生产未部署”，**已过时，待更正** |
| SC14 契约 | 7 阶段、21/21；D33 已清关（公开仓库无行级数量 JSON） | 代码在 #312，待合并 |

### 1.2 使用者与所需形态

| 使用者 | 问题 | 合适形态 |
|---|---|---|
| 技术/分析/补货引擎 | 某 SKU×仓未来每周可用多少、可追溯 | Parquet/JSON + manifest；稳定 schema |
| 计划/供应链 | 哪些 SKU×仓会缺/积压、何时到 | EN 原生报表（SKU×仓×阶段）或独立网页 |
| 销售/客服/业务 | 这一张 SO 每行走到哪、卡在哪 | SO 表单嵌入 / SO Chain Overview（SO 行） |
| 老板/负责人 | 阶段压了多少、例外谁负责 | KPI/例外看板，不是原始表 |

### 1.3 硬约束

- **EN 服务器（阿里云）读不到本机 `D:\`**；本机可以访问 EN REST。
- 通途库存备份在本机；EN 侧没有同一份逐日库存历史。
- EN 生产发布链路：测试 → main → 生产 `pull` + `migrate` + `clear-cache` + `restart`；生产不跑 `bench setup requirements`，新 pip 依赖要手动装。
- 公开仓库不放行级数量数据（D33）；EN 内部数据需要权限。
- 本机 Windows 05:17 已在跑备份；06:30 是否在线/可靠需确认。
- W1 代码目前是**本地 Python**，不是 Frappe app；移植到 EN 是重写/封装，不是加个 cron。
- 数据量：9 SKU 233 行；Top50 约 1–2k 行；全目录可能 10k+ 行/日；历史 30–90 天。

## 2. 选项

### A. 本地/服务器脚本 + Parquet/JSON + manifest（当前形态）

- 计算/存储在本机或 NAS/Linux；06:30 Task Scheduler/cron；输出 Parquet/JSON + manifest。
- **优点**：复用 W1 代码；离数据源近；历史便宜；无 EN 负载；技术消费方便。
- **缺点**：本机需在线；运维/告警要自己做；EN 用户看不到；跨机访问需共享盘/VPN；Windows 任务静默失败风险。
- **适合**：技术/分析先行，EN 展示后置。

### B. EN 原生（custom app scheduler + DocType/DB + Script Report）

- 把 W1 逻辑移植进 `key_test`（或新 app），EN scheduler 06:30 跑，写 DocType/DB；Script Report/API 读。
- **优点**：EN 常在线；权限/报表/导出/订阅原生；一个入口；运维在 EN。
- **缺点**：W1 代码移植成本；EN 要访问通途 API/本地备份（网络/凭证/限流）；大表/历史会压 EN；部署/迁移/重启链路；生产 Python 依赖要手动装；失败影响 EN。
- **适合**：EN 是唯一常在线主机；用户主要在 EN；数据量可控（只存最新）。

### C. 混合（推荐候选）

- 本地/Linux/NAS 计算 + Parquet/JSON 历史 + manifest；**最新快照推入 EN**（DocType/子表或只读 API）；EN 原生报表读最新；程序读 Parquet/API。
- **优点**：复用 W1；历史不压 EN；EN 用户可见；程序稳定；故障隔离。
- **缺点**：多一段同步/推送；需要定义“最新快照”契约；推送失败要告警；两处一致性。
- **适合**：既要 EN 人用，又要机器消费/历史。

### D. 外部服务/DB + API

- 独立 Linux/VPS/容器 + Postgres/DuckDB + API；EN/程序都调 API。
- **优点**：最干净的服务化；多消费者；历史/权限/监控成熟。
- **缺点**：新增运维面/成本；网络/安全；谁维护；当前阶段过重。
- **适合**：W3 多系统集成/长期生产化。

### E. 本地脚本 + 独立 Web 报表（不推 EN）

- 本地计算 + 一个只读网页（LAN/NAS）给计划看；EN 只保留 SO 单票。
- **优点**：最快给计划看；不动 EN；历史便宜。
- **缺点**：多一个入口；权限/账号；不在 EN。
- **适合**：先给少数计划用户，不等 EN 发布。

## 3. 对比

| 维度 | A 本地 | B EN 原生 | C 混合 | D 外部服务 | E 本地+网页 |
|---|---|---|---|---|---|
| 开发成本 | 低 | 高 | 中 | 高 | 低 |
| 运维归属 | 本机 | EN | 本机+EN | 新服务 | 本机 |
| 可靠性 | 中（本机在线） | 高（EN 常在线） | 中高 | 高 | 中 |
| EN 用户可达 | 无 | 强 | 强 | 需集成 | 中（另一入口） |
| 程序消费 | 强 | 中（需 API） | 强 | 强 | 中 |
| 历史/数据量 | 强 | 弱（大表） | 强（历史在外） | 强 | 强 |
| 部署风险 | 低 | 高（EN 发布） | 中 | 高 | 低 |
| 未来 W3 | 中 | 中 | 强 | 强 | 中 |

> 没有“绝对优势”。选型取决于：**谁运维 06:30、EN 用户是否是主需求、历史数据放哪、W3 是否要多系统消费**。

## 4. 关键抉择

1. **计算放哪**：本地/NAS vs EN。判断：数据源可达性、机器在线率、运维归属。
2. **历史放哪**：Parquet/DB vs EN。判断：数据量、查询需求、EN 负载。
3. **人看哪里**：EN 原生报表 vs 独立网页。判断：用户是否已在 EN、权限/导出/订阅需求。
4. **最新快照如何进 EN**：DocType/子表 vs 只读 API。判断：行数、EN 网络可达性、发布成本。
5. **谁运维 06:30**：本机 Task Scheduler vs EN scheduler vs 外部 cron；失败告警/重跑。
6. **数据量边界**：EN 只存最新；历史 Parquet；全目录是否上 EN。

## 5. 推荐（待 Codex 挑战）

**默认 C：本地/Linux 计算 + Parquet/JSON 历史 + 最新快照推 EN（DocType/子表或只读 API）+ EN 原生报表。**

条件：

- 本机/NAS 06:30 在线率可保证；否则改用 EN scheduler 或外部 cron；
- 最新快照行数 ≤ 2k（Top50）；全目录只留聚合/例外在 EN，原始行留 Parquet；
- 推送失败/源不完整要告警；EN 报表必须带 `snapshot_id/as_of`；
- 先 9 SKU 3 天，再 Top50；不直接全量。

Fallback：

- 若 EN 无法读本地/API，且用户主要在 EN → **B（EN 原生）**，但只存最新，历史导出 Parquet。
- 若只想先给技术/分析 → **A**。
- 若 W3 要多系统 → **D**。
- 若先给少数计划用户、不等 EN 发布 → **E**。

## 6. 需要 Codex 审的问题

1. 是否同意“计算与历史在本地/NAS、EN 只存最新快照”的边界？
2. EN 最新快照用 **DocType/子表** 还是 **只读 API**？考虑行数、部署、权限、失败模式。
3. 06:30 调度归属：本机 Task Scheduler / EN scheduler / 外部 cron？谁负责告警/重跑？
4. 全目录扩样时，EN 是否只留聚合/例外？原始行是否只进 Parquet？
5. SO Chain Overview 是否应 join 最新快照显示供给风险？粒度/口径？
6. 是否把 W1 移植进 EN？移植成本 vs 复用本地脚本。
7. 历史保留 30/90/365 天？存储/备份/权限。
8. 安全：EN API 账号/只读权限/网络入口。
9. 失败模式：源不完整、推送失败、EN 报表读到旧快照，如何显式暴露？
10. 是否需要 P0 就做 W3 接口，还是先快照后接口？

## 7. 非目标

- 不下单、不写生产、不改主数据。
- 不做全量大屏/AI 自助查询。
- 不把 SO 子表当供应时间线存储。
- 不在公开仓库放行级数量数据。

## 8. 附：现状证据

- W1 v0：#312（`feature/jack-supply-timeline`，draft）；9 SKU / 233 行 / B_min 1,212 / B_max 2,762+433。
- #311 已合并；#291 履约入口已在 main。
- `supply_chain_visibility/docs/research/presentation-forms.md`：呈现形式调研与建议路线。
- `supply_chain_visibility/key_test/AGENT_HANDOFF.md`：SO 表单/报表落点与部署链路（**生产状态段已过时，待更正**）。
- `supply_chain_visibility/docs/reference/en-custom-apps-and-deploy.md`：EN app 拓扑与发布链路。
- 通途备份：`D:\Work\库存备份\YYYY-MM-DD\`；05:17。
- 本机 DuckDB：`D:/Work/fzh-order-store/order_store.duckdb`（只读；`stock_latest` / `stock_history` / `tongtool_po` / `sku_item` / `bom_exploded`）。
