---
okf: v0.1
type: Research
title: 供应链决策系统 — 开源方案分层评估与最小参考栈
description: 面向 5 人技术团队的编排/存储/BI/预测/优化/计划层/Agent 七层选型；含许可证、维护活跃度、Windows 与中国网络适配、TCO 与不引入清单
date: 2026-10-20
status: final
tags: [supply-chain, research, open-source, tco, forecasting, or-tools, metabase]
---

# 04 — 开源方案分层评估与最小参考栈

> 时间基准 **2026-10-20**。许可证、版本、最近提交用 GitHub API 实查；Python 版本、依赖数、Windows wheel 用 PyPI JSON 实查；能力断言引用官方文档；价格引用公开定价页。证据号 `S4-xxx` 见 §8。

## 0. 范围与假设

- 团队 5 人、无专职数据工程；Python + uv；Windows 开发、Linux 生产；GitHub + PR；ERPNext 已在产。
- 数据量：约 15k SKU、43 个月订单表、低百万行级；**批处理**（周/月），不要求实时。
- 目标链：销量事实 → 需求预测 → 库存/在途 → 补货建议 → 排产 → 老板审批。
- 汇率假设 **1 USD = 7.1 CNY**；服务器与人力为区间估算，不是供应商报价。
- 本文是选型与 TCO 判断，不替代 E1（预测基线）与 E2（补货 LP）实验；模型效果以 `experiments/` 为准。

## 1. 结论先行

1. **本季度推荐组合**：`Windows 任务计划/cron + uv/Python → DuckDB（计算）→ SQLite（服务层）→ Metabase OSS → StatsForecast + HierarchicalForecast → OR-Tools → ERPNext（事实源 + 审批）→ MCP 只读工具`。Claude Agent SDK 只做内部分析师，不进入自动执行链。
2. **不要上 Airflow、Dagster、Kubernetes、dbt、Superset、深度学习预测**。当前只有 4–8 个月度/周度任务、一个兼职工程师；复杂度是首要风险，不是能力不足。
3. **编排毕业路径只选 Prefect**（Windows 可直接装、Python 原生、本地 server 简单）；Dagster 仅在“资产血缘是硬需求”时再评估；Airflow 因 Windows 不原生支持、依赖 251 个，直接排除。
4. **BI 选 Metabase + SQLite 服务层**：Metabase 官方支持 SQLite，但官方数据库列表**不含 DuckDB**；若坚持 DuckDB 直连则改用 Superset，代价是 Postgres + Redis + Celery 四服务栈。
5. **预测的瓶颈是口径不是模型**：断货删失、SKU 映射、层级定义决定上限。StatsForecast 已覆盖稀疏需求（Croston/TSB/ADIDA/IMAPA）、滚动回测与分层调和；深度模型在基线被稳定击败前不引入。

## 2. 判据与淘汰线

| 判据 | 要求 | 淘汰/降级线 |
|---|---|---|
| 单人可运维 | 一条命令跑完，失败可重跑，有日志 | 需要 K8s、专职运维、多服务编排 → 淘汰 |
| Windows 开发 | 开发机可安装、可调试 | 只能 WSL2/容器 → 降级为生产专用 |
| Linux 生产 | systemd/Docker 任选，备份简单 | 只能托管云 → 评估数据出境 |
| 中国网络 | PyPI 镜像可装，GitHub Release 可获取 | 只能 Docker Hub `latest` → 降级（见 §6） |
| 许可证 | 内部使用无额外义务；修改后分发需合规 | AGPL/GPL 可内部用，但不能闭源分发修改版 |
| Python 兼容 | 3.10–3.13；建议统一 3.12 | 只支持 3.11+ 的库要确认运行时 |
| 集成 | Python SDK/REST/Sheets/钉钉 | 无 Python 接口或需浏览器自动化 → 降级 |

## 3. 分层评估

> 依赖数 = PyPI `requires_dist` 声明数（不含间接依赖），仅作“重量”相对信号；“最近提交”为默认分支最后提交日。

### 3.1 编排：cron + Python vs Dagster vs Prefect vs Airflow

| 候选 | 许可证 | 最近发布 / 最近提交 | 维护信号 | Windows / Linux | 依赖重量 | 结论 | 理由与风险 |
|---|---|---|---|---|---|---|---|
| cron / 任务计划 + Python | 自建 | — | 无上游风险 | 原生 / 原生 | 0 | **首选（本季度）** | 4–8 个批任务，最少代码；风险是无重试/UI/血缘，需自建 `run_log` + 钉钉告警 |
| Prefect 3.8.8 | Apache-2.0 | 2026-10-06 / 10-19 | 24k stars；904 open；近 90 天关闭 issue 中位 1.7 天 | **官方安装文档支持 Windows PowerShell/CMD/conda** / 原生 | 83 | **毕业首选** | Python 原生、本地 server、重试/UI 够用；风险是 3.x 迭代快、Windows 服务化需 NSSM/任务计划 |
| Dagster 1.13.26 | Apache-2.0 | 2026-10-09 / 10-19 | 16k stars；2.6k open；近期关单中位被老 backlog 拉高 | 安装文档有 Windows 步骤；生产需 3 个常驻服务 | 100 | **暂缓** | asset 血缘最适合“可审计产出”，但 webserver+daemon+code location 三服务、概念重；团队 >2 名数据人员再评估 |
| Airflow 3.3.2 | Apache-2.0 | 2026-09-17 / 10-20 | 47k stars；极度活跃 | **Windows 只能 WSL2 或 Linux 容器** / 原生 | 251 | **不引入** | 调度器+webserver+元数据库，运维量远超收益；Windows 不原生支持是硬伤 |

**判断**：先用任务计划 + Python，把 `run_log`（输入哈希、行数、输出路径、状态）和钉钉失败告警做出来。任务数超过 10 个、或出现第二个运营同事要触发/看状态时，迁 Prefect；不要在第一个月就上编排平台。

### 3.2 存储/转换：SQLite vs DuckDB vs Postgres；dbt 是否值得

| 候选 | 许可证 | 最近发布 | 维护信号 | Windows / Linux | 依赖重量 | 结论 | 理由与风险 |
|---|---|---|---|---|---|---|---|
| SQLite | Public Domain | 随 Python 标准库 | 极稳定 | 原生 / 原生 | 0 | **首选：BI 服务层** | 单文件、零运维、Metabase 官方驱动；风险是**单写者**，不能放 NAS/Synology Drive，不能多进程写 |
| DuckDB 1.5.6 | MIT | 2026-09-28 | 42k stars；周级提交 | win_amd64 wheel / 原生 | 6 | **首选：计算与仓库** | 进程内列式 OLAP、直接读 Parquet/CSV、单文件；风险是同一时刻只允许一个写进程，网络盘需谨慎 |
| PostgreSQL | PostgreSQL License（宽松） | 持续 | 极稳定 | 原生 / 原生 | 服务端 | **暂缓** | 多写并发、行级安全、Superset 元数据库才需要；现在引入只增加备份/升级/调优负担 |
| dbt-core 1.12.6 + dbt-duckdb 1.11.0 | Apache-2.0 | 2026-10-14 / 10-20 | 14k stars；活跃 | 原生 / 原生 | 25（core） | **暂缓** | 模型、测试、文档、血缘有价值；但一人团队用“SQL 文件 + Python 断言 + run_log”更直接。模型 >30 个或 2 人以上协作再引入；dbt Cloud Starter 为 $100/用户/月 |

**落地细节**：原始层落 Parquet 快照（保留输入指纹）；DuckDB 做 staging/marts；发布时写 `serve.sqlite.tmp` 再原子重命名，Metabase 只读该文件。所有中间表带 `run_id`、`as_of_date`、`source`。

### 3.3 BI/看板：Metabase vs Superset vs Grafana vs FastAPI

| 候选 | 许可证 | 最近发布 / 最近提交 | 维护信号 | Windows / Linux | 依赖重量 | 结论 | 理由与风险 |
|---|---|---|---|---|---|---|---|
| Metabase v0.64.1 | AGPL-3.0（`enterprise/` 为商业许可） | 2026-10-07 / 10-20 | 49k stars；4.5k open；近 90 天关单中位 4.5 天 | JAR 需 Java 25，Win/Linux 均可 | JVM，中等 | **首选** | 非技术同事自助查询/图表最省心；官方支持 SQLite，**不支持 DuckDB**；风险是 AGPL（内部用无分发义务，修改后对外提供需开源） |
| Superset 6.1.0 | Apache-2.0 | 2026-05-13 / 10-20 | 75k stars；632 open；发布节奏较慢但提交活跃 | Docker/Linux 为主；Win 需 Docker/WSL | 4 服务栈 | **备选** | 官方支持 DuckDB（`duckdb-engine`）、SQL Lab 强；代价是 Postgres 元数据库 + Redis + Celery worker/beat，最低建议 4C8G |
| Grafana 13.2.4 | AGPL-3.0 | 2026-10-13 / 10-20 | 77k stars；活跃 | 原生 / 原生 | 中等 | **不用于业务 BI** | 强在 metrics/logs/traces 与告警，不是业务语义层；给老板看补货建议不合适 |
| FastAPI/Streamlit + 简单前端 | Apache-2.0 | 持续 | 活跃 | 原生 / 原生 | Streamlit 33 | **首选：老板一页纸** | 完全可控、可嵌入门户与钉钉；风险是自维护 UI/权限，不能替代自助探索，所以与 Metabase 并存 |

**判断**：Metabase 负责“运营自己查”，FastAPI/Streamlit 负责“老板一页纸”。一页纸固定 6 块：未来 3 个月需求 P50/P90、可用+在途、覆盖天数、建议补货量与金额、缺货风险 Top 20、需老板拍板的例外（超预算/MOQ/新 SKU/加急）。每块都显示数据截止日与置信度。

### 3.4 预测：StatsForecast vs sktime vs Darts vs GluonTS vs PyTorch Forecasting vs Prophet

| 候选 | 许可证 | 最近发布 | 维护信号 | Python / Windows | 依赖重量 | 结论 | 理由与风险 |
|---|---|---|---|---|---|---|---|
| StatsForecast 2.1.1 | Apache-2.0 | 2026-07-16 | 4.9k stars；提交活跃；近 90 天关单中位 48.5 天（样本 10） | >=3.10；win_amd64 wheel | 10 | **首选** | 原生 Croston/TSB/ADIDA/IMAPA，`cross_validation` 滚动回测，15k 序列速度快；风险是删失需求需自建校正，API 变动需锁版本 |
| HierarchicalForecast 1.5.3 | Apache-2.0 | 2026-09-24 | 762 stars；活跃 | >=3.10 | 轻 | **首选配套** | MinTrace/ERM/BottomUp/TopDown 分层调和；风险是文档标注 WIP，按示例驱动 |
| sktime 1.2.0 | BSD-3-Clause | 2026-09-22 | 10k stars；161 个近期关闭 issue | >=3.10；原生 | 111 | **暂缓：实验用** | 统一 API、模型最全、回测工具好；抽象重、15k 序列生产运行慢，依赖多 |
| Darts 0.48.1 | Apache-2.0 | 2026-10-16 | 9.5k stars；活跃；近 90 天关单中位 24.3 天 | **>=3.11**；universal wheel | 31 | **备选** | 全局/深度模型 API 友好；内存与训练成本高，深度模型未必赢简单基线 |
| GluonTS 0.17.0 | Apache-2.0 | 2026-07-31 | 5.2k stars；活跃 | >=3.10；原生 | 93 | **不引入** | 深度概率预测，数据量与团队能力不匹配；依赖极重 |
| PyTorch Forecasting 1.8.0 | MIT | 2026-06-24 | 5.0k stars；活跃 | PyTorch/Lightning | 重 | **暂缓** | 需要训练栈、GPU/调参；先证明基线不够 |
| Prophet 1.5.0 | MIT | 2026-10-05 | 20k stars；活跃 | >=3.10；win_amd64 wheel | 17 | **仅基准** | 可解释、节假日方便；逐 SKU 拟合在 15k 规模慢，稀疏/间歇需求表现差 |

**判断**：第一版只做“基线 + 稀疏模型”：`SeasonalNaive`、`AutoETS`、`Croston/TSB`，按 ABC/流速分层；用滚动 6–12 个月回测，指标 WAPE + bias。分层调和先在“SKU → 叶子物料组 → 渠道”三层做，不要一次对 15k SKU 全量调和。

**删失需求没有库能自动解决**：必须把“断货月/低库存月”标成 `censored=true`，在回测与拟合中剔除或做校正；否则模型会把“没货”学成“没需求”。这是数据契约，不是模型选型。

### 3.5 优化：OR-Tools vs Pyomo vs CVXPY

| 候选 | 许可证 | 最近发布 | 维护信号 | Windows / Linux | 依赖重量 | 结论 | 理由与风险 |
|---|---|---|---|---|---|---|---|
| OR-Tools 9.15 | Apache-2.0 | 2026-01-12 | 14k stars；稳定维护；近 90 天关单中位 4.2 天 | win_amd64 wheel / 原生 | 6 | **首选** | 一套库覆盖 LP（GLOP/PDLP）、MILP、CP-SAT 排产；依赖最轻；风险是不可行诊断与约束调试，需要 fallback 启发式 |
| Pyomo 6.10.1 | BSD-3-Clause | 2026-06-04 | 2.5k stars；活跃 | 原生 / 原生 | 36 + 外部 solver | **备选** | 代数建模、可换 HiGHS/CBC/SCIP，模型可读性好；部署多一步 solver，团队需学建模语言 |
| CVXPY 1.9.3 | Apache-2.0 | 2026-09-19 | 6.4k stars；活跃 | **>=3.11**；win_amd64 wheel | 39 | **不用于补货/排产主流** | 以凸优化为主（1.9 增加 DNLP），整数/MOQ/换型约束表达不便；适合凸松弛或资金分配子问题 |

**判断**：补货先做连续量 LP（GLOP）：最小化持有 + 缺货惩罚，约束 MOQ、交期、在途、预算；需要整箱/整托时再上 CP-SAT 或 MILP。排产用 CP-SAT 的 interval + no-overlap；不要用 CVXPY 硬凑整数排产。每次优化必须与现有启发式对比，改进 <5% 或解不稳定就先用启发式。

### 3.6 计划层：ERPNext vs Odoo vs OpenBoxes

| 候选 | 许可证 | 最近发布 | 维护信号 | Windows / Linux | 依赖重量 | 结论 | 理由与风险 |
|---|---|---|---|---|---|---|---|
| ERPNext v16.51.1 | GPL-3.0 | 2026-10-15 | 40k stars；932 个近期关闭 issue；关单中位 0.7 天 | 已在产（Linux） | 既有 | **唯一事实源** | Production Plan、Reorder Level 自动 MR、Workflow 审批都在；风险是它**不是优化器**，Planning 能力有限，GPL 内部使用无分发义务 |
| Odoo | LGPL-3（Community）；Enterprise 付费 | 无 GitHub release；按版本分支 | 55k stars；极活跃 | Linux/Docker 为主 | 重 | **不引入** | MPS 仍是手工网格，官方明确不能与 reordering rules 混用；与 EN 重复，迁移/双写成本高 |
| OpenBoxes v0.9.8 | EPL-1.0 | 2026-08-14 | 915 stars；活动低；关单中位约 400 天（样本 9） | Java/Postgres | 重 | **不引入** | 定位是 WMS/库存管理，不是需求预测或排产；生态小 |

**判断**：ERPNext 只做“事实源 + 执行 + 审批”，不指望它算最优补货。把建议写成 **草稿** Material Request / Production Plan，走现有 Workflow；人确认后提交。任何“自动提交”都不做。

### 3.7 Agent 框架：Claude Agent SDK、MCP、LangGraph、PydanticAI、OpenAI Agents SDK

| 候选 | 许可证 | 最近发布 | 维护信号 | Windows / Linux | 依赖重量 | 结论 | 理由与风险 |
|---|---|---|---|---|---|---|---|
| MCP Python SDK 2.3.0 | MIT | 2026-10-02 | 24.6k stars；361 open；活跃 | 原生 / 原生 | 轻 | **首选：工具契约** | 把通途/EN/赛狐包成只读工具，客户端可换；风险是它只是协议，不是 Agent，需配客户端 |
| Claude Agent SDK 0.2.168 | 仓库 MIT；使用受 Anthropic Commercial Terms 约束 | 2026-10-15 | 8.3k stars；571 open；活跃 | 原生 / 原生 | 中 | **首选：内部分析师（若用 Claude）** | 复用 Claude Code 的 agent loop、权限、hooks、MCP；风险是绑定 Anthropic API key，token 成本随使用增长 |
| PydanticAI 2.57.0 | MIT | 2026-10-16 | 20.7k stars；1.5k open；关单中位 1.7 天 | 原生 / 原生 | 中 | **备选：模型无关** | 类型化输出、OTel 原生、MCP 一等公民、多模型可换；风险是生态较新，UI/会话要自己搭 |
| LangGraph | MIT | 2026-10-19 | 43k stars；493 open；关单中位 42.7 天 | 原生 / 原生 | 中 | **暂缓** | 状态图/持久化/HITL 适合复杂多步；单人团队易过度设计，LangSmith 为商业服务 |
| OpenAI Agents SDK 0.24.0 | MIT | 2026-10-15 | 30k stars；280 个近期关闭 issue；关单中位 1.0 天 | 原生 / 原生 | 中 | **暂缓：OpenAI 主模型时** | 内置 tracing（默认开启）、MCP 多传输、handoffs；非 OpenAI 模型需额外配置 tracing key |

**判断**：先把 **MCP 只读工具层**做出来（销量、库存、在途、预测、补货建议、SKU 主数据、未结订单、异常），再决定是否要 Agent。没有工具层的 Agent 只会编数字。

**可观测性**：Claude Code 可导出 OTel metrics/logs/traces；PydanticAI OTel 原生；OpenAI Agents 默认 tracing；LangSmith/Logfire 都是可选商业后端。第一版用 `run_log` + 结构化 JSON 日志即可，不要先上观测平台。

**成本**：框架本身免费；成本在 token。按 Sonnet 5.5 公开价 $2 输入 / $10 输出每百万 token，月度批处理 200 次 × 20k token 约 400 万 token，量级在 **$10–50/月**，远小于工程时间。

### 3.8 分层汇总

| 层 | 首选 | 备选 | 暂缓/不引入 | 一句话 |
|---|---|---|---|---|
| 编排 | cron/任务计划 + Python | Prefect 3 | Dagster（暂缓）；Airflow（不引入） | 先简单，10 个任务后再毕业 |
| 存储 | DuckDB + SQLite | PostgreSQL（多写时） | dbt（暂缓） | DuckDB 算，SQLite 服务 |
| BI | Metabase OSS | Superset（DuckDB 直连） | Grafana（业务 BI） | 自助 + 一页纸分工 |
| 预测 | StatsForecast + HierarchicalForecast | sktime/Darts（实验） | GluonTS/PyTorch Forecasting（暂缓）；Prophet 仅基准 | 稀疏 + 回测 + 调和 |
| 优化 | OR-Tools | Pyomo | CVXPY（主流不用） | LP 先行，CP-SAT 排产 |
| 计划 | ERPNext | — | Odoo/OpenBoxes（不引入） | 事实源 + 审批，不做优化器 |
| Agent | MCP + Claude Agent SDK | PydanticAI | LangGraph/OpenAI Agents（暂缓） | 先工具，后 Agent |

## 4. 参考栈

### 4.1 轻量档（本季度推荐，一名工程师可跑）

```text
通途/EN/赛狐/GSheet/钉钉（只读）
        │  快照 + 指纹
        ▼
Parquet 原始层 ──► DuckDB（staging / marts / 回测）
        │                    │
        │                    ├─► StatsForecast 预测
        │                    ├─► OR-Tools 补货 LP
        │                    └─► 例外/风险表
        ▼
serve.sqlite（原子发布）──► Metabase（运营自助）
        │
        ├─► FastAPI/Streamlit 一页纸（老板）
        └─► 钉钉推送（周/月摘要 + 失败告警）
```

- **运行时**：Python 3.12 + uv；`duckdb 1.5.x`、`statsforecast 2.1.x`、`hierarchicalforecast 1.5.x`、`ortools 9.15.x`。
- **BI**：Metabase `v0.64.x` JAR + Java 25（Windows/Linux 均可），只读 `serve.sqlite`。
- **任务**：每日库存异常（复用 `stock_alert/`）、每周销量快照、每月预测 + 补货 + 回测、每月老板摘要。
- **可审计**：每次运行写 `run_log`（输入文件哈希、行数、输出路径、状态、耗时）；关键表做行数守恒/非负/求和断言。
- **验收**：E1 在高价值 SKU 聚合上 WAPE 比 naive 低 ≥10%；E2 5 分钟内可行且约束可解释；一页纸经老板试用一轮；全程只读。

### 4.2 标准档（触发条件满足后再升级）

- 编排 **Prefect 3**（Postgres 14.9+；本机 SQLite 仅单机）；存储 **DuckDB 计算 + Postgres 服务**；转换 **dbt-core + dbt-duckdb**（模型/测试/文档）；BI **Metabase Pro/Cloud 或 Superset**；预测/优化同轻量档，追加 MLforecast/LightGBM 全局模型。
- **升级触发**（满足任一）：任务 >10 个；2 名以上运营要触发/看状态；出现多写并发或行级权限；单表 >500 万行且 BI 查询变慢；审计要求“每个指标可追溯到资产血缘”；需要 DuckDB 直连 SQL Lab。
- 升级顺序：先 Prefect，再 Postgres，最后 dbt/Superset；不要一次性全换。

## 5. 明确「不引入」清单

| 不引入 | 原因 | 何时再评估 |
|---|---|---|
| Apache Airflow | Windows 只能 WSL2/容器；251 个声明依赖；调度器+webserver+元数据库，4–8 个任务严重过度 | 基本不再评估 |
| Dagster（本季度） | 三个常驻服务、100 个依赖、asset 概念学习成本；当前不需要资产血缘 | 审计要求“资产级血缘”或团队 >2 名数据人员 |
| Spark / Kafka / Flink | 数据量低百万行、批处理；引入后运维与人才成本远超收益 | 单日事件 >千万级或真实时 |
| Snowflake / BigQuery | 数据出境、成本不可控；DuckDB 单机足够 | 多地域团队共享、数据量 >TB |
| dbt（首期） | Jinja/adapter 学习成本；一人团队 SQL+断言更直接 | 模型 >30 个或 2 人以上协作 |
| Superset（首期） | Postgres+Redis+Celery 四服务，4C8G 起；Metabase 已够用 | 需要 DuckDB 直连/SQL Lab 或 Apache 许可硬约束 |
| Grafana（业务 BI） | 面向 metrics/logs/traces，不是业务语义层 | 仅用于基础设施监控时 |
| PostgreSQL（首期） | 单写批处理，SQLite/DuckDB 足够；多一个备份/升级对象 | 多写并发、行级权限、Superset 元数据库 |
| GluonTS / Darts / PyTorch Forecasting | 依赖重、训练栈复杂；无证据表明基线不够 | 基线被稳定击败 >10% 且数据量足够 |
| Prophet 全量 | 15k SKU 逐条拟合慢；稀疏/间歇需求弱 | 仅对少量高价值季节 SKU 做基准 |
| Odoo / OpenBoxes | Odoo 与 EN 重复且 MPS 仍手工；OpenBoxes 是 WMS，不做预测/排产 | 不再评估 |
| LangGraph / CrewAI 多 Agent | 单人团队过度设计；MCP + 单 Agent 已够 | 出现复杂多步、多角色、长事务编排 |
| Kubernetes / Docker Swarm | 一台 VM 足够；国内 Docker 拉取还有额外风险 | 多环境多租户、需要弹性伸缩 |
| 自研 React 前端 | Metabase + Streamlit/FastAPI 已覆盖自助与一页纸 | 有明确品牌/交互产品化需求 |
| LLM 自动写回业务系统 | 幻觉与越权风险；审批链不能省 | 只读运行 3–6 个月、准确率与权限审计达标后 |

## 6. 成本区间

**假设**：1 USD = 7.1 CNY；2C4G 云主机约 ¥1,800/年，4C8G 约 ¥4,200/年；工程师全成本 ¥300,000/年（0.1 FTE = ¥30,000/年）；不含一次性建设期机会成本。

| 方案 | 软件许可/年 | 服务器/年 | 人力/年 | 年度合计（估） | 说明 |
|---|---|---|---|---|---|
| A 轻量自建（推荐） | 0 | ¥0–1,800（现有机器） | 0.1 FTE ≈ ¥30,000 | **¥30k–32k** | 首年另计 4–6 人周建设 |
| B 标准 OSS（Prefect+PG+dbt+Metabase） | 0 | ¥4,200–8,000 | 0.2–0.3 FTE ≈ ¥60k–90k | **¥64k–98k** | 升级、备份、监控、故障处理 |
| C SaaS 编排+BI（Prefect Cloud Starter + Metabase Cloud Starter） | ¥16k（$2,280） | ¥0–1,800 | 0.15 FTE ≈ ¥45k | **¥61k–63k** | 仍需自建预测/优化；省的是运维不是建模 |
| D C + dbt Cloud Starter（5 席） | +¥42.6k（$6,000） | — | — | **+¥42.6k** | 一人团队性价比低 |
| E Odoo Enterprise（10 用户） | ¥24k–31k（$3,420–4,320） | 另计 | 实施 ¥100k–300k 一次性 | 首年 **¥124k–331k** | 与 EN 重复，不建议 |
| F Metabase Enterprise | 起 ¥142k（$20,000） | 云/自建另计 | — | — | 本阶段不需要 |

**结论**：许可证不是主要成本，**人力与数据口径治理才是**。C 方案看似便宜，但不会替你完成预测、补货、审批集成；A 方案现金最省、可控性最高，适合本季度。SaaS 补货工具（如 Inventory Planner）按库存量报价、无公开价，未计入；它能替代“补货建议”的一部分，但替代不了生产排产与 EN 审批链。

## 7. 与本仓库现有资产的衔接

| 现有资产 | 用法 | 边界 |
|---|---|---|
| `ai_access_poc/portal` | 内部门户 `/ops` 嵌入一页纸或 Metabase 链接；钉钉 OIDC 可选 | 不把 AGPL 的 IvyeaOps 整仓 vendoring 进本仓 |
| `ai_access_poc/open_webui` | 聊天入口，挂只读 MCP 工具 | 不开放写操作 |
| `web_automation` | API 缺字段时的只读导出兜底（赛狐/通途），走 `dispatch.py` 状态机 | 不做写回、不扩大范围 |
| `EN_API` REST 客户端 | 读 SO/PP/WO/DN/BOM/Bin；把建议写成草稿 MR/PP | 不自动 submit；审批走 Workflow |
| `SELLFOX_API/client.py` | 库存明细/结算；复用重试与限流 | 只读；注意 IP 白名单 |
| `tongtool_api/mcp_http.py` | 包成 MCP 只读工具；共享 5 次/分钟限流 | 缓存优先，批量任务错峰 |
| `stock_alert/`（PR #298） | 复用分页、526 退避、钉钉推送；做每日异常 | 不改成写操作 |
| `uv` | 锁 Python 3.12 与全部依赖；`uv run python -m ...`；离线缓存 | 生产机预热缓存，避免现场装包 |
| Google Sheets / 钉钉 | 作为输入源与输出通道；原始快照落 Parquet | BI 不实时查 Sheets |
| `docs/solutions/` | 动手前查口径/踩坑；新结论回写 | 不重复造轮子 |

**原则**：所有新代码只读；唯一的“写”是把建议写成 EN 草稿单据，由人确认提交。Agent 不直接调用通途/赛狐写 API。

## 8. 证据表

> 类型：`P` 论文 / `V` 厂商主张 / `I` 独立证据 / `C` 可复现代码或实验。强度：A 一手/官方；B 独立可复核；C 厂商文档；D 博客/轶事。

| ID | 主张 | 来源 URL | 类型 | 日期 | 原文摘录 | 强度 |
|---|---|---|---|---|---|---|
| S4-001 | Airflow 生产只支持 Linux；Windows 需 WSL2 或容器 | https://airflow.apache.org/docs/apache-airflow/stable/installation/prerequisites.html | C | 2026-10-20 访问 | “On Windows you can run it via WSL2 (Windows Subsystem for Linux 2) or via Linux Containers.” | A |
| S4-002 | Airflow 3.3.2，Apache-2.0，声明依赖 251 个 | https://github.com/apache/airflow | C | 2026-10-20 访问 | tag 3.3.2；`requires_dist` 251；`requires_python !=3.15,>=3.10` | A |
| S4-003 | Dagster 生产需 3 个常驻服务；默认 SQLite run storage | https://dagster.io/docs/deployment/oss/oss-deployment-architecture | C | 2026-10-20 访问 | “Dagster requires three long-running services”；“by default Dagster uses SqliteRunStorage” | A |
| S4-004 | Dagster 安装文档含 Windows 步骤，推荐 Python 3.13 | https://dagster.io/docs/getting-started/installation | C | 2026-10-20 访问 | “Python 3.13 is recommended.”；安装分 Mac/Windows/Linux | A |
| S4-005 | Prefect 可在 Windows PowerShell/CMD/conda 安装运行 | https://docs.prefect.io/v3/get-started/install | C | 2026-10-20 访问 | “You can install and run Prefect via Windows PowerShell, the Windows Command Prompt, or conda.” | A |
| S4-006 | Prefect 多机部署需 Postgres 14.9+；SQLite 不支持多机同步 | https://docs.prefect.io/v3/advanced/self-hosted | C | 2026-10-20 访问 | “SQLite does not support multi-server synchronization”；“PostgreSQL version 14.9 or higher is required for multi-server deployments.” | A |
| S4-007 | Prefect Cloud Starter $100/月 | https://www.prefect.io/pricing | V | 2026-10-20 访问 | “Starter: $100/mo” | C |
| S4-008 | Dagster+ Solo $10/月 + $0.040/credit；Starter $100/月 | https://dagster.io/pricing | V | 2026-10-20 访问 | “$10 per month” plus “$0.040/credit”；“$100 per month” plus “$0.035/credit” | C |
| S4-009 | SQLite 公有领域，无需许可证 | https://www.sqlite.org/copyright.html | C | 2026-10-20 访问 | “SQLite is in the public domain and does not require a license.” | A |
| S4-010 | SQLite 单写者；多写应选客户端/服务器数据库 | https://www.sqlite.org/whentouse.html | C | 2026-10-20 访问 | “SQLite supports an unlimited number of simultaneous readers, but it will only allow one writer at any instant in time.” | A |
| S4-011 | DuckDB 进程内、无独立服务、面向 OLAP | https://duckdb.org/why_duckdb | C | 2026-10-20 访问 | “embedded within a host process”；“There is no DBMS server software to install, update and maintain.” | A |
| S4-012 | DuckDB 单写进程；只读可多进程 | https://duckdb.org/docs/current/connect/concurrency.html | C | 2026-10-20 访问 | “one process can both read and write”；“multiple processes can read from the database, but no processes can write” | A |
| S4-013 | DuckDB 1.5.6，MIT，声明依赖 6 个，有 Windows wheel | https://pypi.org/project/duckdb/ | C | 2026-10-20 访问 | `duckdb-1.5.6-cp312-cp312-win_amd64.whl` | A |
| S4-014 | PostgreSQL 宽松许可证 | https://raw.githubusercontent.com/postgres/postgres/master/COPYRIGHT | C | 2026-10-20 访问 | “Permission to use, copy, modify, and distribute this software and its documentation for any purpose, without fee…” | A |
| S4-015 | dbt-core 1.12.6 / dbt-duckdb 1.11.0，均 Apache-2.0 | https://pypi.org/project/dbt-duckdb/ | C | 2026-10-20 访问 | 版本 1.12.6 / 1.11.0；License Apache-2.0 | A |
| S4-016 | dbt Cloud Starter $100/用户/月，含 5 个开发者席位 | https://www.getdbt.com/pricing | V | 2026-10-20 访问 | “$100 per user/month”；“Five developer seats” | C |
| S4-017 | Metabase 核心 AGPL，`enterprise/` 为商业许可 | https://raw.githubusercontent.com/metabase/metabase/master/LICENSE.txt | C | 2026-10-20 访问 | “Outside of the top-level ‘enterprise’ directory… licensed under the AGPL.” | A |
| S4-018 | Metabase 官方数据库列表含 SQLite，不含 DuckDB | https://www.metabase.com/docs/latest/databases/connecting | C | 2026-10-20 访问 | “The databases listed below have official drivers maintained by the Metabase team.”；列表含 SQLite | B |
| S4-019 | Metabase Cloud 不提供 SQLite | https://www.metabase.com/docs/latest/databases/connections/sqlite | C | 2026-10-20 访问 | “SQLite isn’t available for Metabase Cloud.” | A |
| S4-020 | Metabase JAR 需 Java 25（早版本不支持） | https://www.metabase.com/docs/latest/installation-and-operation/running-the-metabase-jar-file | C | 2026-10-20 访问 | “We recommend version 25 of JRE from Eclipse Temurin”；“Earlier Java versions aren’t supported.” | A |
| S4-021 | Metabase Cloud Starter $100/月、$1,080/年；Enterprise 起 $20k/年 | https://www.metabase.com/pricing/ | V | 2026-10-20 访问 | “$100 / month”；“$1,080 / year”；“Price starts at $20,000 / year” | C |
| S4-022 | Superset 6.1.0，Apache-2.0 | https://github.com/apache/superset | C | 2026-10-20 访问 | tag 6.1.0，published 2026-05-13；SPDX Apache-2.0 | A |
| S4-023 | Superset 通过 `duckdb-engine` 支持 DuckDB | https://superset.apache.org/user-docs/6.1.0/databases/supported/duckdb/ | C | 2026-10-20 访问 | “Required packages: duckdb-engine”；`duckdb:////path/to/duck.db` | A |
| S4-024 | Superset Docker 栈含 Postgres、Redis、Celery worker/beat | https://superset.apache.org/user-docs/6.0.0/installation/installation-methods/ | C | 2026-10-20 访问 | “the Superset application, a Postgres metadata DB, Redis cache, Celery worker and beat” | A |
| S4-025 | Grafana AGPL-3.0，定位 metrics/logs/traces | https://grafana.com/docs/grafana/latest/introduction/ | C | 2026-10-20 访问 | “querying, visualizing, and alerting on your metrics, logs, and traces” | A |
| S4-026 | StatsForecast 2.1.1，Apache-2.0，依赖 10 个，有 Windows wheel | https://pypi.org/project/statsforecast/ | C | 2026-10-20 访问 | 版本 2.1.1；`statsforecast-2.1.1-cp312-cp312-win_amd64.whl` | A |
| S4-027 | StatsForecast 提供 Croston/TSB/IMAPA/ADIDA 与滚动交叉验证 | https://nixtlaverse.nixtla.io/statsforecast/docs/models/tsb.html | C | 2026-10-20 访问 | 模型页含 `CrostonClassic`、`TSB`、`IMAPA`、`ADIDA`；核心 API `cross_validation(h, df, n_windows=1, step_size=1, …)` | A |
| S4-028 | HierarchicalForecast 提供 MinTrace/ERM/BottomUp/TopDown 调和 | https://nixtlaverse.nixtla.io/hierarchicalforecast/index.html | C | 2026-10-20 访问 | MinTrace “minimizes the total forecast variance”；ERM “minimizing an L1 regularized objective” | A |
| S4-029 | sktime 1.2.0，BSD-3，依赖 111 个 | https://pypi.org/project/sktime/ | C | 2026-10-20 访问 | `requires_dist` 111；`requires_python <3.15,>=3.10` | A |
| S4-030 | Darts 0.48.1，Apache-2.0，Python >=3.11，依赖 31 个 | https://pypi.org/project/darts/ | C | 2026-10-20 访问 | `requires_python >=3.11`；`requires_dist` 31 | A |
| S4-031 | GluonTS 0.17.0，Apache-2.0，依赖 93 个 | https://pypi.org/project/gluonts/ | C | 2026-10-20 访问 | `requires_dist` 93；`requires_python <3.15,>=3.10` | A |
| S4-032 | Prophet 1.5.0，MIT，依赖 17 个，有 Windows wheel | https://pypi.org/project/prophet/ | C | 2026-10-20 访问 | `prophet-1.5.0-py3-none-win_amd64.whl` | A |
| S4-033 | PyTorch Forecasting 1.8.0，MIT | https://github.com/sktime/pytorch-forecasting | C | 2026-10-20 访问 | tag v1.8.0；SPDX MIT | A |
| S4-034 | OR-Tools 9.15，Apache-2.0，依赖 6 个，有 Windows wheel | https://pypi.org/project/ortools/ | C | 2026-10-20 访问 | `ortools-9.15.6755-cp312-cp312-win_amd64.whl` | A |
| S4-035 | CP-SAT 适合整数规划与作业车间排产，支持 no-overlap | https://developers.google.com/optimization/scheduling/job_shop | C | 2026-10-20 访问 | “The CP-SAT solver is designed for integer programming problems and is generally faster than MPSolver.”；`model.add_no_overlap(...)` | A |
| S4-036 | Pyomo 6.10.1，BSD-3，依赖 36 个 | https://pypi.org/project/pyomo/ | C | 2026-10-20 访问 | `requires_dist` 36；LICENSE.md 为 BSD 文本 | A |
| S4-037 | CVXPY 1.9.3，Apache-2.0，Python >=3.11；凸优化为主，1.9 扩展 DNLP | https://www.cvxpy.org/ | C | 2026-10-20 访问 | “a Python-embedded modeling language for convex optimization problems”；1.9 支持 “quasiconvex programming, and nonlinear programming” | A |
| S4-038 | ERPNext GPL-3.0；Production Plan 做生产/物料计划；Reorder Level 自动建 MR | https://docs.frappe.io/erpnext/auto-creation-of-material-request | C | 2026-10-20 访问 | “When item’s stock reaches reorder level, Material Request is auto-created automatically.”；“comparing the projected quantity… with the reorder level” | A |
| S4-039 | Odoo Community LGPLv3；Enterprise $28.50–36/用户/月；MPS 手工且不能与 reordering rules 混用 | https://www.odoo.com/documentation/19.0/applications/inventory_and_mrp/inventory/warehouses_storage/replenishment.html | C | 2026-10-20 访问 | MPS “should absolutely not be used alongside reordering rules” | A |
| S4-040 | OpenBoxes EPL-1.0，定位仓库/库存管理，非计划优化 | https://github.com/openboxes/openboxes | C | 2026-10-20 访问 | “An accessible, open-source warehouse and inventory management system.”；v0.9.8-hotfix1 | A |
| S4-041 | Claude Agent SDK 复用 Claude Code agent loop；使用受 Commercial Terms 约束；仓库 MIT | https://code.claude.com/docs/en/agent-sdk/overview | C | 2026-10-20 访问 | “the same tools, agent loop, and context management that power Claude Code, programmable in Python and TypeScript”；“governed by Anthropic’s Commercial Terms of Service” | A |
| S4-042 | MCP 是开放标准，用于连接 AI 应用与外部系统 | https://modelcontextprotocol.io/docs/getting-started/intro | C | 2026-10-20 访问 | “MCP (Model Context Protocol) is an open-source standard for connecting AI applications to external systems.” | A |
| S4-043 | LangGraph 是低层有状态编排；推荐 LangSmith 做可观测 | https://docs.langchain.com/oss/python/langgraph/overview | C | 2026-10-20 访问 | “a low-level orchestration framework and runtime for building, managing, and deploying long-running, stateful agents”；“Use LangSmith to trace requests…” | A |
| S4-044 | PydanticAI 模型无关、OTel 原生、MCP 一等公民 | https://pydantic.dev/docs/ai/overview/ | C | 2026-10-20 访问 | “every model a string swap away”；“OpenTelemetry-native”；“Core ships fundamentals like MCP” | A |
| S4-045 | OpenAI Agents SDK tracing 默认开启，支持多种 MCP 传输 | https://openai.github.io/openai-agents-python/tracing/ | C | 2026-10-20 访问 | Tracing is “enabled by default.”；“understands multiple MCP transports” | A |
| S4-046 | Claude Code 可导出 OTel metrics/logs/traces | https://code.claude.com/docs/en/monitoring-usage | C | 2026-10-20 访问 | “exports metrics as time series data… events via the logs/events protocol, and optionally distributed traces via OpenTelemetry” | A |
| S4-047 | 清华 TUNA 提供 PyPI 镜像 | https://mirrors.tuna.tsinghua.edu.cn/help/pypi/ | C | 2026-10-20 访问 | `pip install -i https://mirrors.tuna.tsinghua.edu.cn/pypi/web/simple some-package` | A |
| S4-048 | 阿里云 ACR 加速已停止同步最新镜像，建议 ACR 订阅或 GA | https://help.aliyun.com/zh/acr/user-guide/accelerate-the-pulls-of-docker-official-images | C | 2026-10-20 访问 | “ACR镜像加速目前已停止同步最新镜像” | A |
| S4-049 | uv 支持 `--offline` 与多读写者共享缓存 | https://docs.astral.sh/uv/concepts/cache/ | C | 2026-10-20 访问 | “With `--offline`, an affected entry is unavailable until it can be refreshed online.”；“uv’s cache supports multiple concurrent readers and writers” | A |
| S4-050 | 近 90 天关闭 issue 的创建→关闭天数中位数（维护信号代理） | https://api.github.com/search/issues?q=repo:PrefectHQ/prefect+is:issue+is:closed+closed:%3E=2026-07-20 | I | 2026-10-20 实测 | Prefect 1.7 / PydanticAI 1.7 / OpenAI Agents 1.0 / ERPNext 0.7 / OR-Tools 4.2 / Metabase 4.5 / Superset 3.9 / Airflow 3.2 / sktime 6.5 / Darts 24.3 / StatsForecast 48.5 / LangGraph 42.7 / Dagster 395 / OpenBoxes 400（天；受清 backlog 影响） | B |
| S4-051 | Claude Sonnet 5.5 公开 API 价 $2 输入 / $10 输出 每百万 token | https://claude.com/pricing | V | 2026-10-20 访问 | “Sonnet 5.5 — input $2; output $10” per million tokens | C |

## 9. 未找到项

| ID | 目标 | 检索词 | 范围 | 日期 | 结论 |
|---|---|---|---|---|---|
| N-401 | Inventory Planner 公开价格 | “Inventory Planner pricing” | 官网定价页 + 公开搜索 | 2026-10-20 | 未公开；按库存量报价，需销售询价 |
| N-402 | Metabase 官方 DuckDB 驱动 | “Metabase DuckDB driver” | Metabase 官方文档/数据库列表 + GitHub | 2026-10-20 | 官方列表无 DuckDB；仅有社区驱动，未纳入官方支持 |
| N-403 | Dagster/Prefect 中国区托管与 SLA | “Dagster China region”“Prefect China” | 官网定价/部署文档 | 2026-10-20 | 未发现中国区官方托管；需自建或海外云，跨境网络需评估 |
| N-404 | OR-Tools 官方操作系统支持矩阵 | “OR-Tools supported platforms” | 官方文档 + PyPI | 2026-10-20 | 未找到正式 OS 支持声明；以 PyPI `win_amd64`/`manylinux` wheel 为准 |
| N-405 | 各项目官方 issue 首响时间/SLA | “issue response SLA” | 项目文档/治理页 | 2026-10-20 | 未找到公开 SLA；用 S4-050 关单中位数作代理，不能等同首响 |
| N-406 | ERPNext/Odoo 跨境场景需求预测准确率基准 | “ERPNext forecast accuracy benchmark” | 官方文档 + 公开搜索 | 2026-10-20 | 未发现独立可复现基准；厂商材料不作为独立证据 |
| N-407 | 开源端到端“预测+补货+排产+审批”一体化产品 | “open source supply chain planning” | GitHub + 公开搜索 | 2026-10-20 | 未发现成熟且可维护的一体化开源产品；多为 ERP 模块或 SaaS |
| N-408 | Docker Hub 中国大陆官方可用性声明 | “Docker Hub China availability” | Docker/Aliyun 官方文档 | 2026-10-20 | 未找到官方声明；找到阿里云 ACR 加速限制（S4-048），故推荐无 Docker 轻量栈 |

## 10. 90 天落地与复评

- **第 1–2 周**：数据契约与只读快照；断货月标记；SKU/仓/渠道映射；DuckDB 原始层。
- **第 3–4 周**：基线预测 + 滚动回测（E1）；先覆盖 Top 200 SKU + 叶子物料组，不追全量。
- **第 5–6 周**：OR-Tools 补货 LP（E2）；与现有启发式对比；输出约束松弛/不可行报告。
- **第 7–8 周**：SQLite 服务层 + Metabase + 一页纸 + 钉钉推送；老板试用一轮。
- **第 9–12 周**：PB 楔形枕试点；记录例外与人工修正；形成月度运行手册。
- **复评触发**：任务 >10 或 2 名运营 → Prefect；多写并发/行级权限 → Postgres；需要 DuckDB 直连 → Superset；需要资产血缘 → Dagster；基线被 ML 稳定击败 >10% → MLforecast/LightGBM；需要 Agent 写回 → 先做 3–6 个月只读审计。

---

> 本文件只回答“用什么开源组件、怎么拼、多少钱、先不做什么”。业务口径与指标权威仍以 `01-existing-assets.md` 与后续 `05-synthesis.md` 为准。
