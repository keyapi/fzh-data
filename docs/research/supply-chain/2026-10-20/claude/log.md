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
- **G1 范围核对（2026-10-20 只读）**：2026-04..09 月表均存在且日期覆盖整月，2026-10 不存在；
  2026-09「三角」品类 3,963 行 / 4,111 件，主要仓为美东-CENTRADE 1,631、美中-DANEEY 1,586；
  GSheet 品类实际为「自产-三角靠枕-<面料>」，SKU 前缀多样，不能直接等同 KS0001+KS0248。
  已把 Daneey 降为候选仓、窗口改为候选（2026-07..09 或 2026-04..06），不再称「最近 3 个完整月」。
- **G1 范围确认（用户 2026-10-20）**：三角靠枕 family × **两仓（美中 Daneey + 美东 CENTRADE）** ×
  **2026-04..09（6 个月）**；6 个月只做契约回放，不做季节性。G2/G3 用 2023-01..2026-07（43 个月，PR #304），
  可扩到 2026-09；节假日/促销作为结构化日历事件。
- 新增 `13-g1-data-sources.md`（替代原导出请求清单）：默认用现有 GSheet + 本地成本文件 + 权威映射；
  业务导出只作最后兜底。
- **现有记录复用（2026-10-20）**：PR #304 是服务账号直读 GSheet 43 个月，不是业务导出；
  本地 `D:/Work/王忠于/成本核算/2026年{4..9}月订单_order_cost_*.xlsx` 已有订单/成本/品类列；
  PR #303（`40309079`）已有 `EN_API/query_customer_items_suffix.py`；
  权威映射记录见 `docs/solutions/integration-issues/tongtu-en-item-mapping-and-gsheet-source-fix.md`（10-17）
  与 `dce9769a/7f837046/83c05e8a`。G1 映射优先级改为
  **P1 通途SKU → EN 客户物料号（Tongtool Order 明细 / EN BOM 成本表 / ref_code）→
  P2 GSheet 写回品类仅参考 → P3 Colab 4.2 兜底**。
- 库存不是 6 个月序列：G1 用 `stock_alert`（PR #298，`FZH-StockAlert-daily`）或
  `erp2_stocks_stocksquery` 拉 cutoff 快照；EN 单据用 EN API（`item_shipment_status.py` /
  #291 `fulfillment_query.py` / `erpnext/scripts/fetch.py`），本地缓存。
- **库存历史核实（2026-10-20）**：通途只给当前库存；项目没有连续历史归档。
  `stock_alert` 每日任务只写低库存行，不是全量；`web_automation tongtu.stock.export` 可定时
  导出 6 仓库存，但本机无历史输出；本地仅有 `20260514`、`20260807` 稀疏结存。
  **G1 不需要历史库存**，只用 cutoff 当前快照；断货删失是 G2/G3 预测任务，
  用 Notion/邮件/check0stock/SPS 等信号 + 敏感性；每日全量快照是独立任务，不卡 G1。
- **本地映射补充（2026-10-20）**：`en_bom_cost_list/EN产品BOM成本列表_*.xlsx` 有 `产品编号`+`客户物料号`；
  `en_tongtool_cost_review/...` 有 `Tongtool SKU`+`ERPNext物料号`；G1 映射首选本地文件，无需 EN API。
- **PB 断货记录限制**：PB 只覆盖约 30 个涤麻 SKU，仓从美中 Daneey 到美东 Centrade 有过切换；
  只能作部分标注样本，不能当全 family 真值；非 PB SKU 用 raw vs censored 敏感性。
- **映射文件确认（2026-10-20）**：`D:/Work/王忠于/成本核算/EN产品BOM成本列表20261016.xlsx`
  有 3,700 行，KS0001/KS0248 共 1,739 行；列 `产品编号`+`客户物料号`+`产品名称`。
  G1 映射首选此文件；空客户码/`已删除`/`-Cover`/多物料歧义分别标记。
- **EN 单据环境**：测试环境没有真实 SO/PP/WO/JC/SE/DN，G1 用 **EN 生产 API 只读**，不写生产。
- `13-g1-data-sources.md` 替代原导出请求清单；业务导出只作最后兜底。
- 基线标签：`supply-chain-g0-baseline-20261020`（#300 提交 `b23c319a`）。
- #300 与 #301 分别审核合并；不把 #301 并入 #300；不写生产。

## 2026-10-20 — G1a 本地映射覆盖率

- 用 `EN产品BOM成本列表20261016.xlsx` + 本地 `2026年{4..9}月订单_order_cost_*.xlsx`，
  只读跑三角靠枕两仓完成品口径。
- BOM：3,700 行；KS0001/KS0248 1,739 行；有效客户码 1,489；已删除 108；EN 物料 762；0 歧义。
- G1 两仓：18,863 行 / 19,267 件；映射 18,708 行（99.18%）/ 19,043 件（98.84%）；
  未匹配 155 行 / 224 件；0 歧义；0 仅删除别名。
- 仓库归一：CENTRADE 14,751 件；DANEEY 成品 4,516 件；`FZH-DANEEY-皮壳仓库` 10,371 件排除
  （组件/半成品，待业务确认）；波兰/WayfairCG/退货仓不计入 G1。
- 判定：**PASS**；未匹配单列，下一步逐条核。
- **未匹配归因（763 vs 155）**：763 是全仓三角口径，155 是 G1 两仓完成品口径，差额 608 来自
  皮壳/半成品 365、波兰 173、其他 66、退货 4。155 中 31 行可由 `-Cover`(30)/`-out`(1) 尾缀回退；
  124 行在 EN Cost Review 里映射到**非 family** EN 物料（KS0194/KS0003/KS0383/KS0419/KS0260 等）；
  **真正无法解释的 family 缺失为 0**。`-Cover` 按皮壳组件处理，不算完成品需求。
- 两条路径：P1 EN BOM 成本表 + P2 EN Tongtool Cost Review 足够；Colab 4.2 未介入 G1 family 映射。
- 产物：`experiments/g1_contract/`（脚本、聚合 JSON、results/README/index）；无 PII/原始行入库。

## 2026-10-20 — G1 匹配口径更正（待确认）

- 用户指出：不能用“品类/产品名含三角”做主筛选；应优先用 EN BOM 成本表客户物料号。
  EN Tongtool Cost Review 只借代码逻辑，不是数据源。`-Cover` 不是尾缀兜底，三角靠枕类只给分公司发皮壳。
- 核实 BOM：KS0001/KS0248 **1,739 行全部 `绍兴发货方式=皮壳`**；base 码 1,200、`-Cover` 287、`-out` 2、空 142、已删除 108。
- 只用客户码精确匹配重算 2026-04..09：base 32,634 行/33,452 件；`-Cover` 254 行/267 件；
  皮壳口径合计 32,888 行/33,719 件；`-out`/`-Foam` 0；品类文本未命中 763 行（仅诊断）。
- 仓库：CENTRADE 14,720；DANEEY 皮壳/半成品 10,537；DANEEY 成品 4,323；波兰 2,812；其他 1,162；退货 165。
- **公司架构对齐（2026-10-20）**：读 `docs/company-context.md:14-29`：绍兴生产皮壳/内胆/半成品 →
  USNJ(CENTRADE)、USTX(DANEEY)、波兰分公司填充/压缩/包装/发货；最终销售多数是成品。
  三角靠枕类绍兴只发皮壳，成品销售 1:1 消耗皮壳；`-Cover` 是只卖皮壳的例外。
- **皮壳仓不是皮壳产品仓**：`FZH-DANEEY-皮壳仓库` 的 family 销售行产品名是「三角有扣…靠枕」，
  渠道是亚马逊/Wayfair/OSTK 等；它是分公司仓，销量是需求，库存才是补货缓冲。
- 正确需求口径：family 销售（base 32,634 行/33,452 件 + `-Cover` 254 行/267 件）
  = **32,888 行 / 33,719 件 / 6 个月**；分公司皮壳库存/在途做净算；只剩 WayfairCG/3PL 是否计入待确认。
- G1a v1（品类筛选、两仓完成品 99.18%）口径作废；以 `mapping_process.md` 为准。
- **WayfairCG/3PL（2026-10-20）**：WayfairCG-Cranbury 是从美国分公司拿成品再发货的下游 3PL；
  family 销售 1,162 件/6 个月，计入总需求；分公司→3PL 转移不重复计，净算要算 3PL 库存/在途。
  其他 3PL 在 2026-04..09 没有 family 销售；海绵 `-Foam` 是另一条组件流，不是皮壳需求。
  只剩 WayfairCG 由 USNJ 还是 USTX 供货待确认。
- **WayfairCG 库存缺口（2026-10-20）**：Tongtool 库存可能不准；YTQ 做调拨但 Wayfair 实际收货会丢件；
  YTQ 补货时下载 Wayfair 后台库存。赛狐平台仓 API 只有 Temu/Mercado/Walmart WFS，**无 Wayfair**；
  G1 用 `source=wayfair_backend_manual`，Tongtool 调拨只算发出量，transfer vs receipt 对账；
  未知标 unknown + 安全缓冲。WayfairCG family 销售 1,162/33,719 = 3.4%；
  丢件率 r% → 总需求偏差约 3.4%×r，渠道库存偏差 r%。
- **WX 计划反馈（2026-10-20）**：产能时间不确定；美中新运营 2026-06/07/08 入职、第二个月才下单、
  首批刚回货，历史不可参考；美东稳定（2 个运营），历史可用。
  方法调整：美东用 ens5/TSB 回测；美中用短窗 run-rate + 运营/Listing cohort + ramp；
  产能/交期用区间/情景，不输出固定 3 个月到货日。08 增加 operator/listing/cohort 与 V19/V20；
  06 增加 A12/B27/E12；13 增加 §1.6 运营/产能数据。
- **Codex 复核意见处理（2026-10-20）**：33,719 只能叫「family 匹配毛量」，不是净需求；
  退货仓 165 件是正数出库销售（Amazon/Wayfair/OSTK，是否补发货=否），不是退货；
  family 补发 66 行/72 件待交易事件核实；订单文件 45,129 行/48,346 件**无负数行**；
  未匹配 text-tri 759/925 标 pending，不直接判非 family。
  全量去向：family 32,888 + 未匹配 759 + 非 family 退货仓 148 + out_of_scope 11,334 = 45,129 行；
  件数 33,719+925+152+13,550 = 48,346。G1b 继续暂停。
- **本步骤确认前不进入 G1b。**
- 新增 `experiments/g1_contract/codex-sync.md`：给 Codex 的同步块（皮壳 1:1、旧 v1 作废、C21–C25）。
  以后每次我方实质更新都在结尾附「给 Codex」同步块。

## 2026-10-20 — 补发/退货/3PL 供货归属澄清（用户口径）

- 用户明确：**补发/换货是出库消耗，补货必须计入**，不能只按会计“销量”净扣；
  退货是反向流，三角暂按 5% 假设，不确定退货是否在通途重新入库。
- 补发核对：全量 Mxxx 286 行/333 件（`是否补发货=是` 172 / 否 114）；
  family Mxxx 115 行/124 件（是 64 / 否 51）；family `是否补发货=是` 66/72。
  **M 后缀不是唯一判据**。family Mxxx 渠道：Amazon 52、manomano 47、Wayfair 7、Cdiscount 3、
  PotteryBarn 2、HOME24 1、Mirakl 1、allegro 1、Shopify 1。
- 退货：订单文件无负数行；5% 是**假设**（`confidence=low`），不是事实；
  `net = 33,719 − 33,647×5%×restock_share` ≈ 1,682×restock_share；
  输出 0/50/100% → 33,719 / 32,878 / 32,037；其他品类/新品不套 5%。
- WayfairCG 供货归属：不固定 USNJ/USTX，可能按 SKU 分流；用赛狐调拨单
  `POST /api/warehouseTransfer/pageList.json`（发货仓/收货仓/SKU/数量/状态/时间）或通途调拨单；
  新增 `3pl_supply_allocation`；无数据 unknown + 情景，不阻塞 family 总需求。
- 文档更新：mapping_process §3/§4、codex-sync、05/06/08/11/13/results、sources。
- G1b 状态：可在假设下启动；不再等补发交易事件；退货回库比例/调拨数据用于收紧。

## 2026-10-20 — G1b 首版与 Codex 852d7791

- Codex #301 `852d7791`：C26–C35 **35/35**；接受 G1b 带显式假设/unknown 启动；
  要求 ①退货已计入库存不得再次冲减 ②调拨完成≠Wayfair 实收、历史供货占比≠当前库存归属
  ③美中 new cohort run-rate 考虑上架/有货曝光/断货；交付 manifest/逐行去向/守恒/假设清单。
- **退货口径修正**：33,719 直接作为对照当前库存的需求基线；已回库退货已在 `available`，
  不再从需求扣（双扣）；未回库/报废也不冲减。5% 仅未来需求情景（约 1,682 件），
  未来可从 Amazon 结算 V2/退货报表配置化。
- **库存快照**：CENTRADE 478 family SKU（可用 9,877 / 在途 4,504 / 次品 80 / 待发 49）；
  DANEEY 337 SKU（8,492 / 5,071 / 4 / 54）；0 错误。旧 `FZH-DANEEY-皮壳仓库`
  当前不在活跃仓库列表，历史老名并入 `美中-FZH-DANEEY`；不再单列皮壳仓。
- **覆盖首版**：USNJ 5.86 个月、USTX 5.48 个月（gross run-rate）；但 450 个 SKU 有需求无供给、
  501 个 <2 个月。头部缺口如 `CENCord995-DKGrey-97` 784 件/0 供给、
  `CEN003-DPBLUE-100` 703/1、`C/Velvet-White-100-664-wow` 388/0。
- **EN 试点**：`C/Linen-Natural-194-688-wow` → 26 SO / 3,220 订单 / 2,084 已发 / 1,036 未发；
  死单 421、在产/待发 622；557 JC；SO 行用 `PK#` 包装码，必须用客户码或 KS→PK# 映射。
- **每日库存备份**：本机此前未发现 `FZH-TongtuAutoExport-stock` / `FZH-StockAlert-daily` 任务，
  `web_automation/logs/export-stock.log` 不存在；`stock_alert` 只写低库存行，不是全量归档。
  **已注册 `FZH-TongtuAutoExport-stock`：每日 02:17** 跑 `tongtu.stock.export`，
  输出 `web_automation/output/`，日志 `web_automation/logs/export-stock.log`；首跑可能需登录。
  每日全量快照仍独立于 G1b。
- **平台库存 <=2 视为无货**：会造成人为断货/删失，分析时标 `censored/manual_low`，不补 0；
  若可得，记录平台库存快照与调整事件。
- 新增 `g1b_stock_snapshot.py` / `g1b_en_extract.py` / `g1b_coverage.py` / `g1b_pilot.md` /
  `g1b_results.md`；原始库存/单据 JSON 留在本地，不入库。

## 2026-10-20 — Codex d9a11557 G1b 复审修复

- Codex #301 `d9a11557` 判“首版抽取有进展、未通过 G1 契约验收”，列 G1B01–09；
  本轮只修适配器与报告，不扩 top10–20。
- **G1B01**：覆盖只对 `sampled_complete` 分支计缺口；PL 单列、WayfairCG unknown、
  退货仓 demand_only；旧 450/501 撤回。
- **G1B02–04**：订单必需列/缺月/坏数量/负数/非整数/缺 SKU/缺仓显式计数；
  库存分页截断/响应结构/坏值/重复/冲突显式标记；多快照同仓只取最新。
- **G1B05–07**：JC 按工序聚合、首道/末道分开；补 63 张 Manufacture SE；
  DN 增加 `dn_line_id`；未发互斥分解 `421+622+9-16=1,036`，差 7 = `+9-16`。
- **G1B08**：同客户码多 EN 物料 fail-closed；本批 ambiguous=0。
- **G1B09**：新增 `g1b_warehouse_evidence.md`；2026-09 仓名统一，
  旧皮壳仓并入美中主仓（用户确认 + `tongtu_auto_export.py` 注释）；
  旧仓 ID/余额转移仍待系统审计。
- **每日备份更正**：浏览器 `tongtu.stock.export` 的 `downloads/` 有原始库存结存，
  `output/` 有合并库存 + 派生成本模板；**它是有效库存备份**，不是只有成本模板。
  新增 `stock_daily_backup.py`（API 全仓 JSONL+manifest），
  冒烟测试 2 页/200 行通过；注册 `FZH-TongtuStockApiDaily` 每日 05:17。
- 全量 API 备份手工运行中；DANEEY 退货仓出现一次连接超时，按仓记录 error 并继续。
- 产物：`g1b_review_response.md`、`g1b_warehouse_evidence.md`、
  `14-daily-inventory-backup.md`、`stock_daily_backup.py`、`g1b_from_daily_backup.py`。
- **完整 API 备份（2026-10-20）**：CENTRADE 2,072 行/21 页、DANEEY 1,024/11、PL 1,369/14、
  WayfairCG-Cranbury 92/1，均 `complete=true`；DANEEY 退货仓一次连接超时，
  整体 manifest `complete=false`、exit 1。主仓完整，可用于覆盖。
- **完整快照覆盖**：USNJ 5.86 / USTX 5.48 / PL 10.24 个月（含在途名义）；
  131 个 branch×SKU 有需求无供给、194 个 <2 月、127 个 unknown（3PL/退货仓不计缺口）。
- **top10 EN 抽取 9/9 完成**：SO 15–42 张/SKU，SE 36–111 张；9 个 SKU 的未发互斥分解
  `difference=0`；死单/无计划/超发均按 SKU 显式列出。

## 2026-10-21 — 每日备份核对、自动登录与 WayfairCG 尝试

- **浏览器 02:17 首跑成功**：4/6 仓，2 个空退货仓跳过，合并 4,575 行；
  `downloads/` 原始库存结存，`output/` 合并库存 + 派生成本模板；日志 `status=READY reason=success`。
- **销售及库存报表**：`tongtu.sales.export` 导出 1,954 行/8 仓；family 568，
  含 7/15/30/90 天销量，但不是完整库存（库存结存 family 1,527）。结论：库存备份用库存结存，
  销量/周转用销售报表，二者都归档。
- **自动登录**：02:17 无弹窗，使用 `chrome-profile`；`TONGTU_USER/PASSWORD` 在
  `fzh-web-automation/.env`，`tongtu_auto_export.py` 与 `tongtu_sales_report.py` 已加载该路径；
  cookie 过期可走 ddddocr 自动登录（失败降级人工输码）。
- **API 05:17 首跑失败，补跑成功**：旧任务 action 的中文路径被 Task Scheduler 存成乱码；
  已把 wrapper/脚本/`tongtool_api`/`.env` 复制到 `D:\Work\fzh-stock-backup`（ASCII）并重注册。
  09:46 补跑 `complete=True`：CENTRADE 2,072/21、DANEEY 1,024/11、DANEEY 退货仓 522/6、
  PL 1,369/14、WayfairCG-Cranbury 92/1；数据 `D:\Work\库存备份\2026-10-21\`。
- **DANEEY 退货仓超时**：2026-10-20 18:06 跑，不在 QDY/通途 API 同步窗口；
  是到 `mcp.tongtool.com` 的 TCP 超时（WinError 10060）。2026-10-21 补跑成功，
  脚本已加 3 次网络重试（10/20s）。
- **WayfairCG 继续尝试**：Sellfox 调拨单 2025-01..2026-10 共 0 条；
  通途中转发货单对 5 个 WayfairCG 仓 2026-04..09 均 0 条；
  通途 WayfairCG 库存：Cranbury 92、Perris 4、Romeoville 2，其余 0。
  **供货归属仍 unknown**；需要业务导出通途 WMS 调拨单或 Wayfair 后台收货记录。

## 2026-10-21 — Codex fd1029b4 复审与全 family 方向修正

- Codex #301 `fd1029b4`：G1B06/07/08 关闭；RR01–RR08 未闭合，要求先修
  `daily backup → 转换 → coverage` 入口，再扩全 family。
- **RR01**：complete 绑定选中仓/文件；坏值/冲突降该仓 complete；branch 按
  CENTRADE/DANEEY/PL 全覆盖才 `sampled_complete`。
- **RR02**：转换器空/NaN/Inf/负数/分数→bad，不转 0；同仓同 SKU 异值 conflict 整键丢弃；
  缺文件/坏行/冲突→仓 incomplete；加 file hash。
- **RR03**：每日备份校验 datas/业务码/`truncated`；空仓清单不再 `all([])`；
  JSONL/manifest 原子写；加 run_id/script_version。
- **RR04**：首/末工序取路由首/末，无卡则 unknown，不用后道替代；补 JC ID/status；
  另给 `last_card_operation` 辅助。
- **RR05**：SE 保留行 ID/item/qty/UOM/成品标记；详情失败/无匹配/UOM 未知→unknown；
  不再把未知产量当 0。
- **RR06**：Wayfair API 只作参考，标 `unknown_authority`，不进入缺口。
- **RR07/08**：请求/读取/缺失仓、file hash、逐仓 complete；非整数/NaN 不纳入毛量；
  文本三角 pending 与 non_family 分开。
- **实跑**：4 仓转换 `complete=True`、bad=0、conflict=0；Wayfair `unknown_authority`；
  presence 重算：129 observed_zero / 2 missing / 192 <2 月 / 127 unknown；EN 试点 63 SE 全 `ok`，last_route 无卡→null。
- **方向修正**：逐客户码 1,486 次只适合试点；批量 SO 探针按
  `item_group in ("三角靠枕","三角靠枕无扣")` 返回 333 行/56 张 SO，证明可按物料组批量。
  新增 `15-full-family-etl.md`：ODS→staging→fact/dim→语义层、水位线、幂等键、manifest/hash。
- **自动登录**：`TONGTU_USER/PASSWORD` 在 `fzh-web-automation/.env`；
  `tongtu_auto_export.py` 与 `tongtu_sales_report.py` 已加载该路径，cookie 过期可走 ddddocr。
- **库存备份**：浏览器 02:17 成功 4/6 仓/4,575 行；API 05:17 因中文任务路径失败，
  迁 ASCII 后 09:46 补跑 `complete=True`；销售报表 1,954 行/family 568，不能替代库存结存。

## 2026-10-21 — Codex 93e6bd1f 第三轮（T01–T06 / E01–E04）

- Codex #301 `93e6bd1f`：接受批量 ETL；RR 大部分修复；T01–T06 仍待修。
- **T01**：`presence`/`quantity_status`；未返回 SKU 记 missing，不记 0；3PL/未知
  `available/intransit/supply=None`，只留 reference。重算 **129 observed_zero / 2 missing /
  192 <2月 / 127 unknown**；missing 为 `CENVel1612-Black-138-Cover`、`CEN003-DPBLUE-100-old` 各 1。
- **T02**：daily 改 `day/run=<run_id>/` 不可变目录，仓文件 tmp→replace，日 manifest 最后原子发布；
  转换器校验 manifest `file_sha256`，失配/缺失拒绝（旧 manifest 用 `--allow-missing-hash`）。
- **T03/T04**：请求仓保留、缺仓 `missing_requested` 失败；逐仓 complete 绑定
  `by_warehouse[wh].complete`，不再用 global 降级好仓。
- **T05**：SE `missing_doc` 保留 list 阶段 `work_order`；无法定位时 `se_error`，
  相关 WO 全部 unknown，不当 0。
- **T06**：headline 用 `window_complete + complete_branches`；缺月/partial 不混入无供给/低覆盖。
- **E01–E04**：写入 `15-full-family-etl.md`（family manifest、增量/tombstone、不可变键、守恒回归）。
- 负例：hash 全 0 → read=0/complete=false；请求不存在的仓 → requested=2/read=1/complete=false。
- 旧 131/194 被 presence 更新为 129/192 + 2 missing；仍只是 Claude 报告，不是 G1 验收。

## 2026-10-21 — Codex c6275051 / U01 / family PoC

- Codex #301 `c6275051`：T01–T04/T06 关闭；T05 只余 U01（混合 SE 失败仍可绕过 unknown）。
- **U01**：`build_four_way` 先过全局 SE 查询完整性闸门；`se_error` 时该 WO
  `se_status=query_incomplete, se_finished_qty=None`，成功量只留 `se_known_subtotal`。
  合成 WO-X（成功 5 + 未定位失败）已验证。
- **15 统一**：§2.1/2.2 改为不可变快照键、`modified` 与业务日期分离、父单重拉/tombstone、
  提交后推进水位；`--allow-missing-hash` 标 `integrity_mode=legacy_unverified`。
- **family SO PoC**：group-only 15 SO/135 行，10 个试点客户码只中 1 个；
  并集（group delivery/tx + item_code chunks + 10 个试点码）后 **96 SO / 380 family 行 /
  4,100 非 family 同行，10/10 试点命中**。仍缺页数、DN/WO/JC/SE、水位/tombstone 回归。
- 仍不宣称 G1 验收；Wayfair/旧仓迁移 pending。

## 2026-10-21 — Codex 862f77d1 family SO PoC 复审（S01–S04）

- **S01**：统一 `--date-basis delivery|transaction`，默认 delivery；group/item_code/pilot
  全部同窗口过滤，pilot 不再无日期混入。
- **S02**：family manifest 真正接入：969 KS item / 1,486 客户码 / 2,907 查询码（KS+PK#+ND#）；
  行角色 KS/PK/ND/group/customer；PK#/ND# 但 base 非 family 记 pending，不判 non-family。
- **S03**：candidate/selected/truncated/max_sos/status 入 manifest，超限 partial + exit 1。
- **S04**：detail_failed、line_dispositions、script/manifest/out sha、run_id；缺详情 partial。
- 同窗重跑（delivery_date）：**52 SO / 1,510 family 行 / 392 pending / 122 out_of_scope**；
  group 132 行/2 页、item_code 945 行/75 页、pilot 89 行/10 页；10/10 试点命中；status complete。
- 旧 96/380/4,100 是 pilot 无日期 + PK# 角色未修的口径，不作为同窗结果。
- 1,510 是 SO 行，不等同 33,719 终端出库件数；DN/WO/JC/SE、水位/tombstone、守恒仍未做。

## 2026-10-21 — Codex run_86b2a4645f21 S02/S04 复审

- Codex：S01/S03 verified；S02 partially（前缀接纳未证实 PK#/ND#）；S04 partially
  （只计数不存逐行 disposition；缺 items 静默零行并 complete）。
- **S02**：`classify_line()` 对 PK#/ND# 取消 KS 前缀规则，改为证据表门控；
  `--variant-manifest` 不传则变体一律 pending（`variant_manifest_absent`）。
- **提交前阻塞修复 + 证据设计对齐**（`reviews/2026-10-21-s02-evidence-design`）：
  PK=皮壳、ND=内胆；方向固定 KS 成品 BOM → PK/ND 组件，不反转、不要求 PK/ND 的 BOM 必有 KS。
  文件层 `schema_version/site/as_of/producer/rule_version/payload_sha256`
  + 重复 JSON key 拒绝；条目层 canonical KS/role/direction/有效期/Item+BOM 身份与 hash/
  `candidate_boms[]`（全 `eligible_at_evidence` 且比例一致，default/当前 active 不消解冲突）/
  组件 stock 累计 ÷ 输出 stock 数量 = 1/UOM 换算已知/历史窗口
  `historical_verified + historical_basis`；停用 Item 保留历史关系但
  `current_planning_eligible=false`；`evidence_ref` 由已验证 BOM 派生。
  结构证据只证明 family，不证明销量等价。
  行上分离 `family_membership` 与 `demand_role`（内胆独立销售不产生皮壳需求）；
  qty 缺/坏值记 None 不转 0。证据表 code 并入候选查询；
  离线单测 34 条全绿（不联网、不调 main）。
- **本地证据边界**：BOM xlsx 3,700 行无任何 PK#/ND# 单元格（包装列是 SXBZCP# 等），
  因此 variant→KS 证据只能由独立只读 EN Item/BOM 步骤生成；本补丁不访问生产。
- **S04**：新增 `<out>.audit.jsonl` 逐行 disposition；详情状态机
  `detail_ok/detail_none/items_missing/items_not_list/items_empty/detail_error`，
  失败一律 partial + exit 1；`so_audit`/`line_audit` 两条守恒 + `audit_ok`。
  `pilot_seen` 改为 disposition 前统计，另记 `pilot_seen_family`。
- `status` 只表示查询/详情完整性；逐行证据完成度单列 `adjudication`。
- 本轮**未跑真实回放**（按用户要求单列验收）；不发布新数字，不宣称 G1 验收。

## 2026-10-21 — bb25327b 复审后 P1/P2 修复

- Codex CONDITIONAL GO：S04/candidate union/34 tests VERIFIED；PK/ND/demand PARTIAL。
- 本轮按 `next-steps.md` 只修 P1/P2，不跑生产：
  - **E1** 同 UOM 强制 `qty≈stock_qty`、factor 若给出只能为 1，component/output 两侧；
  - **E2** schema/rule/source/site 白名单与当前 run 绑定，`version/source` 必填，
    manifest 记 `schema_decision`，未知值 exit 2；条目 schema 也白名单；
  - **E3** 坏 `docstatus`/validator 异常转 `variant_record_invalid` 并继续，
    结构错误标 partial（`variant_record_error`）；
  - **E4** 行 UOM 缺失 `variant_line_uom_missing`；disabled 与 eligible 矛盾
    `variant_planning_eligibility_conflict`；源 hash 明确为受信 producer 边界；
  - **行键** 缺失/重复 `line_key_invalid/duplicate` + partial，保留 `line_index`，
    改 `demand_event_candidate_id`，不再生成 `A:None`；
  - **demand** 角色改为 `*_candidate`，counting 一律 `event_unverified`，
    manifest 明确 `demand_quantity_available=false`、factor 不消费。
- R1/R2 有界只读回放（bb25327b，未用于验收）：52 SO / 2,024 行 / family 132 /
  pending 1,770 / out_of_scope 122；两次忽略 run_id 的 audit SHA 相同
  `4fec233b...`，`audit_ok=true`；五个详情失败状态真实数据未触发。
- 离线单测 44 条全绿（不联网、不调 main）；未提交 out/ 产物。

## 2026-10-21 — 有界 Item/BOM 证据 producer 首样本

- 新增 `en_variant_evidence.py`：从 d8 R1 audit 选 20 个 PK/ND 样本（14 PK、6 ND、
  6 个 base 不在 family），Item/BOM list 精确 `in` + 父单详情，单并发 0.2s，
  timeout 30s，预算 500 HTTP/900s。
- 结果：79 HTTP / 19.8s；14 PK `consistent/current_structure_only`（ratio=1，
  `ks_parent_variant_component`），6 ND `not_family`（base 不在 969 KS 清单，
  内胆是多个成品 BOM 的共享子件）。
- Consumer 校验：`fp.load_variant_evidence` 通过；本地分类 2,024 行中
  `variant_current_structure_only=119`、`variant_not_in_manifest=694`、
  `variant_base_not_family=956`；PK/ND family=0，family 仍 132 裸 KS。
- **历史边界**：当前 BOM 只证明抓取时结构；不凭 `modified/active/default/Version 空集`
  升级 Apr–Sep；项目存在 `update_modified=False`，`modified` 不可靠；
  `historical_verified` 需可信锚点 + 完整期段重建，或仅 event 绑定不可变版本。
  本 producer 不查 Version，历史关系保持 pending。
- **踩坑**：EN `is_active/is_default` 是 1/0 整数，`is True` 误判（v1 全 missing）；
  BOM Item 子表 list 403；BOM list 混入无关父单需先过滤；ND# 共享多父单；
  `qty=1` 不等于 1:1，需 stock 数量归一。
- 产物：`g1b_evidence_producer.md`；zip `evidence_d8c473fe_v3.zip`
  sha256 `69b679af…`；evidence `0f365b99…`。
- 离线单测 53 条全绿（consumer 44 + producer 9），不联网、不调 `main()`。

## 2026-10-21 — producer P1 修正与 20 样本 v5 回放

- Codex producer 复审 CONDITIONAL：反向 BOM 误判 consistent；共享 ND 被武断
  `not_family` 且丢失父边；字符串 `'0'` 被当 True。
- **修正**：反向方向只进 `excluded/unsupported_direction`，混合方向
  `conflict_mixed_direction`，current planning 仅 `consistent` 且正向可行；
  ND 改 `unresolved_canonical_mapping`，按 raw BOM 保留 `shared_parent_ks` 与父边，
  reason_code 区分多父/单父/样本内无父；`flag()` 严格解析 bool/int/`'0'/'1'/'true'/'false'`，
  其它 invalid；consumer 新增 `variant_unresolved_canonical_mapping`。
- v5：20 样本（14 PK / 6 ND）；14 `consistent/current_structure_only`；
  6 `unresolved`（2 多父 8/5、1 单父、3 无父）；79/500 HTTP、19.8/900s。
- v5 本地回放（复用 d8 R1 快照，无新 SO 查询）：pending 1,769
  （unresolved 537 / not_in_manifest 694 / base_not_family 419 /
  current_structure_only 119）；family 132 KS、PK/ND family 0；无 historical_verified；
  两次归一化 audit 相同。
- 离线单测 61 条全绿；文档更新 `g1b_evidence_producer.md`；
  evidence `1d6a7b33…`、producer zip `db44dadf…`、replay zip `a3b23cf1…`。

## 2026-10-21 — producer P2 flag 数值边界

- Codex v5：两个 P1 关闭，仅余 P2 flag 数值分支。
- `flag()` 收紧：只接受 bool、整数 0/1、浮点 0.0/1.0（显式等价）；
  `2/-1/0.5/NaN/Inf` 与未知字符串 → invalid；Item/BOM 共用。
- 补负例后 66 条单测全绿（consumer 45 + producer 21）。
- 复用 v5 raw（43 BOM 全 int1、37/6 default、34 Item disabled=0），严格解析全通过；
  evidence/replay hash 不变，无新增生产查询、无样本扩张。

## 2026-10-21 — 库存历史离线入库 dry-run（v4）

- 新增 `experiments/g1_contract/stock_history_ingest.py`：只读 run 目录 →
  确定性 run_id / SHA256 基线 / 三级完整性 / 稳定 ID 与别名 / 同日多 run 发布指针 /
  回滚 / 独占锁 / 版本化迁移；默认 `:memory:`，写模式必须显式 `--db`。
- 新增 `test_stock_history_ingest.py` 20 条离线测试（14 条验收 + 6 条补充）；
  真实两日只在本地存在时只读校验，不复制、不提交原始 JSONL。
- 两日 dry-run：10-20 5,192 行、13/14 仓、`run_complete=false`
  （退货仓 400 行部分批次）；10-21 5,314 行、14/14、`run_complete=true`。
- 固定 manifest 基线：10-20 `18649875…`、10-21 `4dd9bbfd…`；
  每个 JSONL 的 64 位 SHA256 见 `experiments/g1_contract/stock_history_ingest.md` §13。
- 未写 `order_store.duckdb`、未访问通途/EN、未改计划任务、未提交原始数据。

## 2026-10-22 — 库存入库代码复审修复（六项）

- Codex 复审 `2026-10-22-stock-code-review.md` 判 FAIL，六项逐一修复：
  ① 同 run_id 重导比对 `snapshot_date + manifest SHA + 每个 JSONL SHA`，变更即
  `reimport_changed_rejected` 并拒绝，不再先删后插；② `manifest.complete` 缺失
  判 unknown（`run_complete=false`），不再用 `scope_complete` 冒充；③ 跨 run
  别名冲突按同一总序裁决，低者 `reject`、高者发布，最终赢家与导入顺序无关；
  ④ `stock_id_history` 按日期正序从已发布 run 重建，反序导入不会出现
  `valid_to < valid_from`，回滚同步恢复；⑤ 0 行 previous run 按批次有效性
  （`run_complete`）判断可否回滚；⑥ 锁改为 OS 文件锁（Windows LockFile /
  POSIX flock），活进程超时不被抢，崩溃后内核自动释放。
- `test_stock_history_ingest.py` 增加 6 条回归（`test_r1`–`test_r6`），并改写
  `test_a12` 锁语义与跨 run 别名补充用例；共 26 条离线测试全绿。
- 两日 dry-run 重跑：10-20 5,192 行 / 13/14 仓 / `run_complete=false`；
  10-21 5,314 行 / 14/14 / `run_complete=true`；输出见 `control/` 与提交说明。
- 未访问通途/EN、未写 `order_store.duckdb`、未改计划任务。

## 模板（后续阶段）

```text
## YYYY-MM-DD — Phase N
- 做了什么：
- 检索命令：
- 结果/发现：
- 失败或放弃的方向 + 原因：
```
