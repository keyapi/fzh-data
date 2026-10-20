---
okf: v0.1
type: Reference
title: 供应链整合 — 项目内资产盘点（Claude 独立复核）
description: 截至 2026-10-20 核实的代码/文档/分支/PR/历史资料；区分可直接复用、需合并、历史资产与缺失项，并给出指标权威初判
date: 2026-10-20
status: checkpoint-1
tags: [supply-chain, research, assets, checkpoint]
---

# 01 — 项目内资产盘点

> 核实口径：路径与分支用 `git ls-tree` / `ls` / `gh pr view` 实查；业务规则引用现有文档原文。
> **重要：很多成果不在 main。** 只看 main 会漏掉预测脚本、履约实现、成本规格与拆包裹设计。

## 1. 结论摘要

1. **项目不是从零开始，但拼图分散在 4 类位置**：main 上的连接器与业务规则、未合并 PR 里的履约/成本/补货实现、个人 worktree 里未提交的预测脚本、本机与 Notion 里的历史决策产物。
2. **最关键的缺口已确认**：main 没有任何需求预测 / 安全库存 / 净需求 / 排产优化 / 审批引擎代码；只有方法论。
3. **需求预测并不空白**：2026-08-31 已有一轮数据可行性 + 方法选型 + PB 多方法脚本，现已由 PR #304 归档（未合并）。
4. **最接近本项目的架构是「履约阶段机 + 证据分层」**：蓝图在 main，实现（阶段 0–3）在 PR #291；它正好覆盖「下单 → 生产 → 出库」这段事实链。
5. **最大风险仍是口径**：销量、库存、在途在三套系统里都有，但定义不同；本文件 §6 给出初步权威矩阵，需业务确认。

---

## 2. 资产总表（按决策链）

| 环节 | 资产 | 位置 | 状态 | 可复用内容 |
|---|---|---|---|---|
| 数据接入 | 通途 MCP/API | `tongtool_api/mcp_http.py::McpClient` | main | 订单/包裹/库存/采购只读；共享 **5 次/分钟** 限流 |
| 数据接入 | ERPNext REST | `EN_API/item_shipment_status.py::api_get/paginated_get`；`EN_API/bom_fabric_length_check.py::ErpnextClient` | main | SO/PP/WO/Job Card/DN/BOM/Bin；子表需嵌套过滤 |
| 数据接入 | 赛狐客户端 | `SELLFOX_API/client.py::SellfoxClient` | main | 库存明细/结算；Retry-After 与限流策略 |
| 数据接入 | 钉钉表 | `dingtalk/dingtalk_sheet/client.py::read_sheet_all` | main | 头程两张表整表读（合并单元格需下填） |
| 数据接入 | Google Sheet | `tongtool_order_cost/tongtool_order_cost/gsheets.py::gsheet2df` | main | 月度订单表、BOM 成本、仓库成本来源 |
| 事实层 | 通途订单侧输入 | PR #294 `order_side_input.py` / `profitability_audit.py` | 未合并 | 订单/包裹/成品件/行 grain、皮壳件数规则、快照+闸门、17 表审计 |
| 事实层 | 履约阶段机 | PR #291 `EN_API/fulfillment/` | 未合并 | 阶段 0–3、数量恒等式、`FieldValue(kind=fact/derived/estimate/assertion)`、异常→责任→下一行动 |
| 事实层 | 履约蓝图 | `docs/solutions/architecture-patterns/en-end-to-end-supply-chain-fulfillment-visibility.md` | **main** | 阶段 0–9、数量分层、四组对账等式、V1–V4 路线 |
| 成本 | 成本引擎规格 | PR #295 `tongtool_order_cost/docs/reference/cost-engine-spec/`（00–31） | 未合并 | EN BOM 成本口径、直采自套 BOM、成本决策表 |
| 成本/拆包 | 合并拆包规则 | PR #295 `ustx_cost_compare.py::group_split_rows` + `30/31` 设计稿 | 未合并 | 五条「不重不漏」断言：守恒、件数=Σ皮壳行、键不退化、仅成品行对 BOM、歧义即阻断 |
| 补货 | 补货量方法 | PR #297 `docs/solutions/workflow-issues/pb-replenishment-sizing-from-sales.md` | 未合并 | `月需求率 × 覆盖期 − 可用 − 在途`；断货月剔除；6 个月覆盖；美中 Daneey 仓族 |
| 断货 | PB 断货闭环 | PR #297 `pb_orders/notion_stockout.py` + `stock_precheck.py` | 未合并 | 明细行级缺货判定、部分缺货保留 Header、Notion 19 列契约 |
| 预警 | 低库存扫描 | PR #298 `stock_alert/` | 未合并 | 通途分页（pageSize≤100、无 total）、526 退避、每仓一 sheet、钉钉 markdown/ActionCard |
| 预测 | PB 多方法脚本 | `pb_reconciliation/sku_forecast.py`（本机未跟踪，PR #304 归档） | 未合并 | M1 运行率 / M2 同比窗口 / M3 线性趋势 / M3b 季节平均；区间与备货上浮 |
| 预测 | demand_forecast 阶段 A | PR #304 三篇 `docs/research/2026-08-31-*` | 未合并 | 43 张月表、EN 映射、断货信号、方法选型（Croston/TSB/LightGBM/Conformal） |
| Agent 治理 | 受控办理 demo | PR #288 `ops_assistant_demo/` | 未合并 | 能力注册表、read-then-guard、prepare→确认→执行→独立回读、权限与限流 |
| Agent 治理 | 独立竞赛 demo | `D:/Work/web-ai-assistant-review-20261012`（分支 `feature/competition-controlled-agent`，commit `acb2dd8`） | 本机仓库 | 同上模式，2026-10-15 版；23 项测试 |
| 审批 | ERPNext Workflow | `docs/solutions/architecture-patterns/erpnext-workflow-configuration.md` | main | State→Action→Role→Workflow 四件套；每 DocType 仅一个 active workflow |
| 通知 | 钉钉机器人 | `dingtalk/dingtalk_robot/send_dingtalk.py`；`dingtalk_robot` skill | main | 文本/ActionCard；文件经 ERPNext 中转 |

---

## 3. 未合并 PR 台账（2026-10-20 实查）

| PR | 分支 | 状态 | 相关度 | 内容 | 合并风险 |
|---|---|---|---|---|---|
| [#291](https://github.com/keyapi/fzh-data/pull/291) | `claude/frosty-hellman-58de7a` | OPEN | 高 | EN 统一履约查询（阶段 0–3）+ 异常 + 证据分层 | 与 #294/#295/#297/#288 都改共享索引 |
| [#294](https://github.com/keyapi/fzh-data/pull/294) | `feature/en-order-side-input` | OPEN | 高 | 通途订单侧输入 + 月度盈利审计 | 与 #295 双向分叉，互不为祖先 |
| [#295](https://github.com/keyapi/fzh-data/pull/295) | `feature/ustx-cost-compare` | OPEN, CONFLICTING | 高 | USTX 成本 A/B1/B2 + 成本引擎规格 + 拆包合并 | 与 #294 重复且冲突；引用以 20 号更正页为准 |
| [#297](https://github.com/keyapi/fzh-data/pull/297) | `claude/vigorous-lehmann-889bf7` | OPEN | 高 | PB 断货闭环 + 补货量方法 | 仅方法论，无补货计算代码 |
| [#298](https://github.com/keyapi/fzh-data/pull/298) | `feature/en-api-ops` | OPEN | 高 | `stock_alert/` 低库存扫描 + 钉钉推送 | 标题只写重量模板，易被忽略 |
| [#288](https://github.com/keyapi/fzh-data/pull/288) | `claude/ce-okf-branch-param-desk` | OPEN, CONFLICTING | 中 | `ops_assistant_demo/` 受控办理演示 | 域无关，只迁移治理模式 |
| [#300](https://github.com/keyapi/fzh-data/pull/300) | `docs/supply-chain-integration-handoff` | OPEN | 高 | 交接包（00–04） | 与本调研共用 `docs/plans/` 索引 |
| [#301](https://github.com/keyapi/fzh-data/pull/301) | `feature/codex-supply-chain-research` | OPEN | 中 | Codex 调研计划（未产出结论） | **不读取其结论，保持独立性** |
| [#304](https://github.com/keyapi/fzh-data/pull/304) | `claude/gifted-ptolemy-bc923f` | OPEN | 高 | 归档 demand_forecast 阶段 A + `sku_forecast.py` | 纯归档，可直接作为资产引用 |
| [#280](https://github.com/keyapi/fzh-data/pull/280) | `docs/colab-cost-current-state` | OPEN, CONFLICTING | 中高 | 旧 Colab 成本链现状档案 | 已被 #295 部分取代 |
| [#232](https://github.com/keyapi/fzh-data/pull/232) | `feature/history-last-leg-v2` | CLOSED 未合并 | 高 | 历史尾程费率模型（V0–V4、Holdout、EN 导入契约） | 历史资产；含三个已修正口径错误 |
| [#234](https://github.com/keyapi/fzh-data/pull/234) | `claude/zen-torvalds-5b9c9d` | CLOSED 未合并 | 中 | AI ops 试点评估与 Workspace Agent 边界 | 纯文档，已过时 |
| [#278](https://github.com/keyapi/fzh-data/pull/278) | `docs/pb-orders-tongtool-reorder-suffix` | CLOSED 未合并 | 高 | 通途重复建单后缀 + UPS 取件才算真发 | 业务规则仍有效 |

其他低相关：`#290`（通途同步五类缺陷）、`#289`（Daneey 同步 429）、`#286`（成本账本）、`#283`（钉钉/Excel/赛狐核对）、`#282`（通途 90 天改单窗口）、`#287`（FedEx 账单）、`#205`（PB 供货价）、`#159/#146–148`（赛狐回写 outbox）。

---

## 4. 历史资料抢救结果

### 4.1 demand_forecast 子项目（阶段 A 已完成，阶段 B 未启动）

- 归档：PR #304 的 `docs/research/2026-08-31-demand-forecast-data-feasibility.md`、
  `-practical-paths.md`、`-ts-forecast-methods.md`。
- 文件名沿用 `2026-08-31`；其中 `practical-paths.md` 的实际创建时间是 **2026-09-02 17:35**，
  不是「9/2 没有产出」。此处以用户 2026-10-20 的更正为准。
- 数据可行性：通途订单 Google Sheet **202301–202607 连续 43 张月表**（逐日行，含发货日期/通途SKU/解析后SKU/数量/渠道/发货仓库）；
  EN 主数据 15,190 物料、410 个叶子物料组；断货信号用通途库存导出（可用 ≤0）。
- SKU 映射：EN `customer_items.ref_code` + 剥离 `-淘汰/-out/-Cover/-Foam`；`missing_products/audit_three_systems.py` 已跑通。
- 方法结论（2026-08-31）：**分段 + 全局 LightGBM + 分层调和 + Conformal 区间**；
  长尾用 Croston/TSB/ADIDA；断货=截断需求（Tobit/删失校正）；新品用物料组相似借力。
- 原会话转录 `fc0170d0` 已被 30 天清理；现存为归档文档与脚本。

### 4.2 多方法销量预估

- 脚本：`pb_reconciliation/sku_forecast.py`（约 19.6 KB，2026-08-31），PR #304 归档。
- 口径文档：`pb_reconciliation/docs/reference/sku-forecast.md`（PR #304）。
- 输出样例：`D:/Work/美国/<PB渠道>/PB orders/sales_forecast/…CENKZ1325-YELLOW-97_20260831_141542.{md,xlsx}`。
  **实际输出在仓库外，不入库**；仓库只归档脚本与口径文档（PR #304）。
- 方法：M1 运行率、M2 同比窗口、M3 线性趋势、M3b 季节平均；输出中间值/区间/备货建议（上浮约 20%）。
- 局限：销量取 PB 对账表 `Invoice to PB` 的 PO 下单量作代理；断货会低估需求；近 1–2 月数据滞后。

### 4.3 网页 Agent demo（两个，需区分）

1. PR #288 `ops_assistant_demo/`：2026-10-11，工单驱动受控渠道接入（银行竞赛场景）。
2. `D:/Work/web-ai-assistant-review-20261012`，分支 `feature/competition-controlled-agent`，commit `acb2dd8`（2026-10-15）：
   含 `server.py` / `agent_runtime.py` / `task UI`，23 项测试。**更可能是用户说的「上周 demo」**。
- 可迁移的是治理模式，不是业务逻辑：能力白名单、read-then-guard、不可变提案、确认后执行、独立回读、权限分级。

### 4.4 通途 SKU / Colab + GSheet → EN BOM 成本

- PR #295（`feature/ustx-cost-compare`）：成本引擎规格 00–31、A/B1/B2 对比、拆包合并设计。
- PR #294（`feature/en-order-side-input`）：订单侧输入 + 7 月盈利审计。
- PR #280：旧 Colab 成本链现状档案（10 月初快照）。
- 关键提交：`9ccf0c1f`（头程改用 EN BOM 成本列表，A 与 B2 同源）、`7f837046`/`dce9769a`/`430e268c`（通途 SKU↔EN 权威映射、精确匹配、GSheet 源头修正）、`e9e92e4f`（AKN 重发口径）。
- 结论：**EN 为成本权威源**的方向已在分支上验证，但尚未进 main。

### 4.5 PB 10-16 决策包（E1/E2 的对拍基准）

- `D:/Work/美国/<PB渠道>/PB orders/楔形枕 补货决策信息包 20261016.{md,xlsx}`
- `…/楔形枕 断货预警 20261016.xlsx`
- Notion「PB 断货处理 2026-10-16」记录 2 单断货、楔形枕补货 257 件。

---

## 5. 数据源可读性地图

| 系统 | 数据对象 | 访问 | 粒度 | 新鲜度 | 已知坑 |
|---|---|---|---|---|---|
| 钉钉 | `2026年下单表` | `read_table.py --list` / `--all` | 订单行/批次 | 人工维护，无时间戳 | 批次号仅首行，需下填；join key 是 EN 销售订单编号，不是 `po_no` |
| 钉钉 | `发货信息总表` | 同上（`DINGTALK_OPERATOR_SHIP`） | 包裹/行 | 同上 | operatorId 必须授权 unionId |
| GSheet | `通途订单YYYYMM` | `gsheet2df` | 订单行 | 月更，最新 202609 | tab 命名随月份变化，不能写死 |
| GSheet | BOM 成本/仓成本来源 | 同上 | SKU/BOM | 人工 | 成本表是某 workSheet，不是独立表 |
| ERPNext | SO/PP/WO/Job Card/DN/BOM/Bin | REST token | 单据/行 | 实时 | 子表需嵌套过滤；Bin ≠ 可用库存 |
| 通途 | 订单/包裹/库存/采购 | MCP | 单据/行 | 准实时 | 共享 5 次/分钟；订单查询必须带 accountCode |
| 赛狐 | 库存明细/结算 | OpenAPI | SKU/仓、交易 | 准实时/日更 | 直连需 IP 白名单；pageSize≤100 |
| Notion | 断货台账/成本笔记 | MCP | 页面 | 人工 | 无注册表；页面分散 |

**头程 ETA 缺口（最重要）**：钉钉表只有「工厂确认交期 / 包装完成日期」，没有离厂、到港、清关、入仓时间；
批次与订单多对多，无分配表；「订单日期 + 3 个月」是低置信估计。Jack/PJ 的 WorkBuddy 大屏尚未进仓库。

---

## 6. 指标权威矩阵（初判，待业务确认）

| 指标 | 候选来源 | 初步事实源 | 理由 / 已知偏差 |
|---|---|---|---|
| 销量/需求 | 通途订单月表 / 平台结算 / PB PO | **通途订单月表（发货口径）** | 逐日逐行、含渠道与仓库；PB 渠道需注意 PO 下单量 ≠ 实际需求 |
| 销售额/毛利 | 赛狐结算 / 平台账单 | **平台结算**（金额） | 通途订单表用于数量；金额以结算为准 |
| 可用库存 | 通途分仓库存 / EN Bin / 赛狐 | **通途分仓库存** | EN 不扣减通途；赛狐有安全冗余 |
| 采购在途 | 通途采购单 / EN PO | **通途采购单** | EN 侧采购执行链基本空白 |
| 生产进度 | EN PP / WO / Job Card | **EN（工序卡优先）** | WO 头状态不可信；`Closed` ≠ 已发完 |
| 工厂出库 | EN Delivery Note | **EN DN** | 部分出库/退货需净额 |
| 头程在途 | 钉钉两张表 / 智美通 / WorkBuddy | **钉钉表（暂定）** | 无结构化 ETA；待 Jack/PJ 数据接入后重评 |
| 成本 | EN BOM 成本 / Colab 成本引擎 / 赛狐批次成本 | **EN BOM 成本 + 成本引擎口径** | 赛狐 FIFO 批次成本不可反推；成本口径以 #295 规格为准 |
| 客户/渠道 | 平台 / EN Channel Account | **EN Channel Account** | Amazon 按国家站 |

> 本矩阵是**调研假设**，不是结论；Phase 4 会结合调研与实验修订。

---

## 7. 最值得复用的 8 项

1. **#291 履约阶段机与证据模型** → 订单→生产→出库的事实内核。
2. **#294 订单侧事实层** → 销量/件数/拆包/补发口径；可合并。
3. **#295 成本规格 + 拆包「不重不漏」断言** → 成本与原始数据整理。
4. **#297 补货量方法** → 唯一的成文补货公式；需代码化。
5. **#298 `stock_alert/`** → 现成的库存快照、分页、限流与钉钉推送。
6. **#304 demand_forecast 阶段 A + `sku_forecast.py`** → 预测的数据地基与基线实现。
7. **#288 / 独立 demo 的治理模式** → 建议审批流与「执行后回读」。
8. **main 上的业务铁律文档** → 口径与失败模式，避免重蹈覆辙。

---

## 8. 缺失与风险

- **缺失（仓库内确认不存在）**：需求预测代码、安全库存策略、净需求/补货计算、排产优化、供应链审批流、统一语义层、告警规范、头程 ETA 事件模型。
- **#294 与 #295 双向分叉**：都有订单侧输入与盈利审计，互不为祖先；不要假设能机械合并。
- **#295/#288/#280/#205/#159 当前 CONFLICTING**：引用其文档与设计，不依赖其可合并性。
- **共享索引冲突**：#291/#294/#295/#297/#288/#300/#301 都改根 `index.md` 或 `docs/plans/index.md`；
  本 PR #302 只写自己的目录，目前 MERGEABLE。
- **历史资料依赖个人 worktree**：PR #304 已归档，但后续应以 PR 为准，不引用未跟踪文件。

---

## 9. 检索命令附录

```bash
git fetch --all
gh pr list --state open --limit 300 --json number,title,headRefName,state,mergeable,url,updatedAt
gh pr list --state closed --limit 300 --json number,title,headRefName,mergedAt,url   # 过滤 mergedAt == null
git log --all --oneline --name-only -- '*demand_forecast*' '*sku_forecast*'
git rev-list --all --objects | grep -iE 'demand[_-]?forecast|sku[_-]?forecast'
git log --all --oneline --grep='BOM'
git ls-tree -r --name-only origin/<branch> | grep -E 'fulfillment|stock_alert|order_side_input|ustx_cost|ops_assistant'
find "D:/Work/美国" -maxdepth 5 -iname '*forecast*' -o -iname '*预估*'
```

> `sku_forecast.py` 在 git 对象中不存在；唯一命中是 PR #301 的计划文档。归档版本见 PR #304。

---

## 10. 对交接包 `01-asset-inventory.md` §6 的更正

交接包 §6「用户提到但仓库里没找到」有 4 项；Phase 1 已全部定位。**本文件是更正后的权威版本**，
#300 的原文由其维护者后续同步（本 PR 不修改 #300 的文件）。

| 交接包 §6 原项 | 更正后 |
|---|---|
| `demand_forecast` 子项目 | **已定位**（用户 2026-10-20 于另一会话恢复到 PR #304）：阶段 A 数据可行性完成；**阶段 B 未启动，未建 `demand_forecast/` 目录**；资产见 PR #304 三篇 `docs/research/2026-08-31-*` |
| 多方法销量预测对比 | **已定位**：PB 的 M1/M2/M3/M3b 实现在 `pb_reconciliation/sku_forecast.py`（PR #304 归档）；实际输出在仓库外 `D:\Work\美国\Tracy Miller\PB orders\sales_forecast\`，**不入库** |
| 网页 Agent demo | **已定位两个**：PR #288 `ops_assistant_demo/`（2026-10-11）与 `D:/Work/web-ai-assistant-review-20261012`（2026-10-15，更可能是「上周」那个） |
| 通途 SKU / Colab+GSheet 换 EN BOM 成本 | **已定位**：PR #295 / #294 / #280，核心提交 `9ccf0c1f`、`7f837046`、`dce9769a`、`430e268c`、`e9e92e4f`；未进 main |

另：PR #304 的检索纪要中「practical-paths.md 9/2 没有产出」应更正为
**该文件创建于 2026-09-02 17:35**（文件名仍保留 `2026-08-31` 前缀）。
