---
okf: v0.1
type: Log
title: 供应链整合 — Claude 独立调研过程日志
description: 每个阶段做了什么、用了哪些检索命令、失败与放弃的方向
date: 2026-10-20
tags: [supply-chain, research, log]
---

# 过程日志

## 2026-10-20 — Phase 0 脚手架

- 用户确认 4 项范围决策：历史记录挖掘优先；分阶段汇报；允许装包 + 只读拉数；验证切片 = PB 楔形枕 × 美中 Daneey。
- 新建独立 worktree `D:/Work/赛狐/Cursor/.claude/worktrees/supply-chain-claude`，
  分支 `research/supply-chain-claude`，基线 `origin/main` @ `e5d07c9d`。
- 交接包参考：`origin/docs/supply-chain-integration-handoff` @ `de899f4b`（PR #300，未合并）。
- 建立目录与 `index.md` / `00-plan.md` / `sources.md` / `log.md` / `experiments/`。

### Phase 0 已核实的事实（与交接包的差异）

| 事项 | 交接包说法 | 本次复核 |
|---|---|---|
| 端到端履约蓝图 | 未合并分支 | 蓝图**已在 main**（`docs/solutions/architecture-patterns/en-end-to-end-supply-chain-fulfillment-visibility.md`）；未合入的是实现 `EN_API/fulfillment/`（PR #291） |
| 网页 Agent demo | 未定位 | 找到 `ops_assistant_demo/`（PR #288，银行竞赛演示，治理模式可迁移） |
| 实时库存预警 | 未列 | PR #298 已含 `stock_alert/`（通途库存快照 + 阈值 + 钉钉通知，27 测试） |
| 多方法销量预估 | 未定位 | 本机有输出 `D:/Work/美国/Tracy Miller/PB orders/sales_forecast/`；生成脚本 `pb_reconciliation/sku_forecast.py` **未入库** |
| demand_forecast 子项目 | 未定位 | 继续挖（Cursor 对话库 / Notion / 本机目录） |

## 2026-10-20 — Phase 1 项目内资产与历史资料

- 三路并行：历史记录挖掘、仓库/PR 代码级复核、外部数据源侦察（只读）。
- 产出 `01-existing-assets.md` 与 `sources.md` 的 S1-001–S1-015、N-001–N-005。

### 关键发现

- **PR #304（2026-10-20 新建，keyapi）**：已归档 demand_forecast 阶段 A 三篇调研 +
  `pb_reconciliation/sku_forecast.py` + 口径文档。原会话转录已被 30 天清理。
- `demand_forecast/` 代码目录确认不存在于任何 ref；只有文档与 PB 脚本。
- 「上周网页 Agent demo」更可能是 `D:/Work/web-ai-assistant-review-20261012`（2026-10-15，`acb2dd8`），
  不是 PR #288（2026-10-11）。
- 通途×EN BOM 成本切换确实存在，集中在 PR #295/#294/#280，未进 main。
- PB 10-16 决策包（楔形枕补货 257 件）可作为 E1/E2 对拍基准。

### 副作用说明

- 历史挖掘子 Agent 早期误用 `uv run python`，在本 worktree 生成 `.venv` 并安装 101 个包；
  未跟踪、已 gitignore，不影响提交。后续实验可直接复用该环境。

### 检查点 1 后的用户更正（2026-10-20）

- `demand_forecast`：已由用户另一会话恢复到 PR #304；阶段 A 完成，阶段 B 未启动、未建目录。
- 多方法对比：实现 `pb_reconciliation/sku_forecast.py`，输出在本机 PB 目录，不入库。
- PR #304 纪要更正：`practical-paths.md` 创建于 2026-09-02 17:35，不是「9/2 没有产出」。
- 已写入 `01-existing-assets.md` §10；#300 的 §6 由维护者后续同步，本 PR 不改。

## 2026-10-20 — Phase 2 三条调研线

- 三个子 Agent 并行：业界实践（02）、AI/Agent SOTA（03）、开源方案（04）；各自只写自己的文件。
- 证据量：02 = 24 条（S2），03 = 35 条（S3），04 = 51 条（S4）；未找到项 N-201–207 / N-301–308 / N-401–408。
- URL 可达性抽检：110 个唯一 URL，96 个 200；其余为 403/429/Cloudflare（付费墙或反爬），非死链。
- 关键来源人工复核：
  - arXiv 2609.13840（Accuracy Is Not Service, 2026-09-12）：确认 Spearman −0.555、77.5%→92.0%。
  - Quartz/Reuters（2026-05-22）：确认 Starbucks 约 9 个月后撤下 AI 盘点工具。
  - accesson.kr（Quick-Commerce TSFM）：确认 TimesFM 汇总第一但优势集中于高周转，间歇段最佳模型随指标变。
  - claude.com/pricing：确认 Sonnet 5.5 定价 $2/$10 per MTok。
- 修正：03 的 frontmatter `okf_version` → `okf: v0.1`；证据计数 33→35。

### Phase 2 核心结论（供 05 使用）

- 先轻量 S&OP + 例外队列，不上 APS；补货用 DDMRP-lite，MEIO 只做两级。
- TSFM 做挑战者而非主模型；稀疏需求先做 TSB/Croston + 偏差校正 + 分层选模。
- LLM 不做最终数字；做编排、解释、归因、语义层问答，关键数字由确定性内核计算。
- 推荐轻量栈：cron/uv/Python → DuckDB（算）→ SQLite（服务）→ Metabase → StatsForecast + HierarchicalForecast → OR-Tools → ERPNext 审批 → MCP 只读。
- 明确不引入：Airflow/Dagster（当前）、K8s、dbt、Superset、深度预测、多 Agent 框架。

## 2026-10-20 — Phase 3 最小验证（E1/E2/E3）

- **E1**：从 43 张通途月表拉取 8 个楔形枕 SKU（1370 行，2023-07–2026-07），滚动原点 h=3（23 个原点）。
  - 修复两处实现错误：M3b 使用了预测月真实值（数据泄漏）；排名按方法名而非 WAPE 排序。
  - 结果：组合法 `ens5` 聚合 WAPE 0.441 vs naive 0.562（−21.5%）；但无单一方法稳定领先
    （最好单一方法仅 26% 原点排第一）。判定：**有效性通过、稳定性证伪 → 用组合法 + 月度回测**。
- **E2**：OR-Tools CP-SAT，8 SKU × 12 月、B=257/180、MOQ 约束、±25% 敏感性与独立仿真回读。
  - 结果：全部 OPTIMAL（≤0.04s），预算/MOQ/回读通过；固定预算下总缺货结构性不变，
    仅持有成本（−1.1%~−2.5%）与到货后服务时点改善。判定：**机制通过、主假设证伪**。
- **E3**：确定性路由 + 8 个只读工具 + 指标注册表 + prepare→confirm→execute→readback。
  - 结果：可作答 10/10、歧义澄清 2/2、写意图拒绝 1/1、越界/错误前提各 1/1、0 次写；歧义率 13.3%。判定：**PASS**。
- 数据合规：E1 原始 CSV 不入库（`.gitignore`），仅保留拉取日志、脚本与聚合结果 JSON。
- 依赖副作用：安装 `ortools==9.15.6755` 时 `protobuf` 由 7.36.1 降至 6.33.6（项目 venv）。

### 三实验共同结论

- 确定性内核 + 简单统计基线 + 语义层 + 人工审批足够支撑 V1；复杂度不是瓶颈。
- 真正的杠杆是：口径统一、断货标签、预算/服务水平决策，而不是更复杂的模型或优化器。

## 2026-10-20 — Phase 4 综合与开放问题

- 写 `05-synthesis.md`：
  - 指标权威矩阵（销量/金额/库存/在途/生产/出库/头程/成本/渠道 + 派生指标）。
  - 三个候选架构：A 轻量决策链（推荐 V1）、B 标准数据平台（毕业路径）、C Agent 控制塔（只做薄层）。
  - 推荐 A + 薄 C；给出 90 天路线、成本区间、10 项风险与失败条件。
- 写 `06-open-questions.md`：A 业务 10 题、B 口径 9 题、C 外部依赖 4 题、D 系统流程 7 题、E 实验后续 5 题；
  附「最小可开工假设」。
- `sources.md` 合并 S2/S3/S4 共 110 条证据；修正引用格式与表头列数。
- `index.md` 状态更新为 Phase 0–4 完成。

## 2026-10-20 — 用户补充：库存数据架构与评审包

- 用户确认：目前只有通途库存可用（不一定准确，但无更好替代）；EN 未同步通途库存；
  通途 SKU ↔ EN 映射复杂；拆包裹/合并在 #294/#295 有记录；
  测试阶段先别碰 EN 生产。
- `05-synthesis.md` 新增 **§4.4 库存数据架构**：
  - 不把通途库存写进 EN Bin/Stock Ledger（会污染账务/双计）；
  - V1 用独立 DuckDB mart（Parquet 快照 + sku_map + 质量标记）；
  - EN 只读 Snapshot DocType 仅在 EN 是硬性 UI 要求时采用；
  - 历史库存备份（如有）只作一次性回填源，新链路用 API/受控导出；
  - 测试分三阶段：本地 → EN 测试 `ensh.vilavi.cn` → 生产只读，禁止写生产库存账。
- `06-open-questions.md` 新增 B10–B15、C5、D8–D9，并更新最小可开工假设。
- 新增 `07-review-guide.md`：用户审核顺序 + 给 Codex 的只读评审 brief。
- **更正（同日）**：Plentymarkets FTP 是用户多年前在别的公司的方法，与当前项目无关，
  已从 05/06/07/sources 中移除；历史库存备份仅作为「如有则一次性回填」处理。
- PR 归属澄清：#300 交接包、#301 Codex、#302 Claude；用户决定**合并到 #300**。

## 2026-10-20 — Codex 评审响应（#300 @ 7181415c）

- Codex 给出 5 项意见；逐条处理结果见新增 `09-codex-review-response.md`。
- **E1 修正（接受，且实锤 TSB bug）**：
  - TSB 零需求期错误地衰减需求规模 d；修正为只衰减概率 z、d 不变。
  - 缺失≠0：新增 `data_status.json`（observed / zero_confirmed / pre_launch / missing）。
  - 日期按发货日期解析（多种格式）；最小训练 18 月；验证期选方法、测试期只报告。
  - 结果：测试期 TSB 0.511、ens5 0.520、naive 0.602（ens5 −13.6%）；验证期选中 MA3 测试 0.575。
  - **不能声称 ens5 被验证选中**；ens5 是稳健候选，不是稳定最优。
- **生产数量口径（接受）**：新增 `08-fact-contract.md`，定义首道 JC / 末道 JC / 已提交 Manufacture SE / 已提交 DN 四分法；
  指出 #291 文档与代码自相矛盾；给出守恒式与 10 项只读验证。
- **E2/E3 收窄（接受）**：E2 仅件数预算，不能外推金额；E3 未验证生产鉴权/并发/独立回读。
- **计划引擎（接受）**：05 §3 新增候选 D（ERPNext 原生 / FrePPLe / Odoo），附翻转条件；工期/成本标为假设。
- **PR 归属**：Claude 早期 #302 已关闭并合入 #300；Codex #301 保持独立，不合并。
- 未写任何生产系统；V1–V16 验证全部设计为只读。

## 2026-10-20 — Codex 第二轮定向复审（R01–R07）

- 读 Codex #301 `dd2551ef` 的 `claude-review.md`、`common-framework.md`、`semantic-examples.md`、`decisions.md`。
- 新增 `10-codex-round2-response.md`：R01–R07 逐条处理、D01–D05 契约对照、B01–B07 保留分支、C01–C13 样例对照。
- **R01 接受**：E1 验证/测试标签重叠；增加 label 可知时间与目标月交集断言。
- **R02 接受**：坏数量不再转 0；列长度对齐；坏行整格隔离。
- **R03–R06 接受**：08 补 DN 自身行 ID、收货行+revision+分摊桥、需求冲减/内部 SO、同 cutoff 互斥余额与退货规则。
- **R07 接受**：计划引擎对照不等 V1 完成，同快照先跑轻量与 EN 原生。
- **R01/R02 已修正并复跑**：
  - R01：验证 2024-12..2025-04（目标 2025-01..07），测试 2025-07..2026-02（目标 2025-08..2026-05）；
    交集空，`label_overlap_check.pass=true`；验证样本 34 个 SKU-原点。
  - R02：坏数量不转 0；列长度对齐；43 月 bad_qty=0、mismatch=0；闸门未被真实坏行触发。
  - 结果：验证选 Croston 0.448；测试 TSB 0.511 / ens5 0.520 / Croston 0.530 / naive 0.602；
    选择规则三种口径全部跑输 ens5。
- 实跑 Codex `contract_examples.py`：13/13 PASS（仅算例自洽）。
- 不访问 EN 生产、不写业务系统、不锁定数据库/计划引擎。

## 2026-10-20 — G0 基线冻结 / G1 准备

- 读 Codex #301 `5708609d` 的 `alignment-status.md` §3。
- 08 补准两处契约：
  - 供应余额改为**互斥状态表**：新收不与可用重复；采购/头程在途经 crosswalk 只保留一个余额；
    WIP 只含未完成部分；accepted ≠ available；无来源标 unknown。
  - 需求冲减区分 `forecast_qty / consumed_order_qty / open_order_qty / net_forecast`；
    **桶内已发订单继续冲减预测**，交付不使已冲减需求复活。
- 新增 `11-common-baseline.md`：冻结共同框架/事实契约/验收样例/决策表的版本清单 +
  G1 脱敏快照本地回放的输入、步骤、验收门槛。
- **G1 切片确认（用户 2026-10-20）**：三角靠枕 family（EN 叶子物料组 KS0001 三角靠枕 + KS0248 三角靠枕无扣），
  通途 GSheet 品类可能叫「三角」；规划层按 family 聚合，事实层保留 leaf group/SKU。
  已写入 11 §2.1、05 §5、06 A7/B21–B22。
- 新增 `12-codex-g1-instructions.md`：给 Codex 的 G1 执行清单（基线冻结、C14–C18 样例、08 定向复核、三角靠枕映射）；
  Claude 负责 G1 脱敏快照本地回放。
- 基线标签：`supply-chain-g0-baseline-20261020`（#300 提交 `b23c319a`）。
- #300 与 #301 分别审核合并；不把 #301 并入 #300；不写生产。

## 模板（后续阶段）

```text
## YYYY-MM-DD — Phase N
- 做了什么：
- 检索命令：
- 结果/发现：
- 失败或放弃的方向 + 原因：
```
