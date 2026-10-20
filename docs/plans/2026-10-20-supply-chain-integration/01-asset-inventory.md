---
okf: v0.1
type: Reference
title: 供应链整合 — 仓库现有资产盘点
description: 截至 2026-10-20 在本仓库（含未合并分支）核实到的、与供应链整合相关的代码、文档、数据入口；区分「已核实 / 未合并 / 外部 / 待确认」
date: 2026-10-20
---

# 01 — 现有资产盘点

> **核实口径**：路径存在性与所在分支用 `git ls-tree` / `ls` 实查过（2026-10-20）。
> 业务结论没有逐条重跑；标「待复核」的仍需新对话验证。
> **重要：很多东西不在 `main` 上。** 新对话必须 `git fetch --all` 后按分支查，
> 不要只在 main 上 grep 就下「没有」的结论。

## 0. 三条主线的现状（先看这个）

| 主线 | 状态 | 在哪 |
|---|---|---|
| **端到端履约可视化（SO → 生产 → 出库 → 头程 → 上架）** | 蓝图 + 实现都在**未合并分支** | `origin/claude/frosty-hellman-58de7a` |
| **成本引擎 / 拆包裹合并 / EN BOM 成本** | 规范与代码在**未合并分支** | `origin/feature/ustx-cost-compare` |
| **PB 断货闭环 / 补货量估算** | 已提交在 **PR #297 分支**，待合并 | `claude/vigorous-lehmann-889bf7` |

---

## 1. 端到端履约（最接近本项目的现有架构）

### 1.1 蓝图文档（**未合并，必读**）

`origin/claude/frosty-hellman-58de7a`：
`docs/solutions/architecture-patterns/en-end-to-end-supply-chain-fulfillment-visibility.md`

它已经定义了：

- **阶段状态机 0–9**：销售需求 → 待计划 → 生产中 → 工厂待出库 → 待头程 → 头程在途 →
  到港清关 → 国外仓收货 → 加工上架 → 下游履约；
- **数量分层**：`ordered → planned → produced → shipped → allocated → loaded → arrived →
  received → shelved`，并给出四组核心对账等式；
- **事实 / 推导 / 估算 / 人工判断**四层证据模型（每个日期带来源与置信度）；
- **头程真实入口**：EN `Sales Order.name` × 钉钉表（`2026年下单表` / `发货信息总表`），
  **不是** EN 的 `po_no`（那是离职同事自编的内部流转号，待废弃）；
- **V1–V4 路线**：V1 只覆盖 EN 可证的 0–3 阶段；V2 接钉钉头程；V3 接承运人/海外仓；V4 接尾程。

**它没有覆盖**：需求预测、补货/下单建议、排产建议、资金约束、老板审批视图 —— 正是本项目要补的前半段。

### 1.2 实现（**未合并**）

同分支：

- `EN_API/fulfillment_query.py` —— 统一履约查询入口（多输入 / 阶段 0–3 / 异常）
- `EN_API/fulfillment/` —— `model.py` / `assemble.py` / `quantities.py` / `stages.py` /
  `rules.py` / `evidence.py` / `render.py` / `report.py` / `kit.py` / `cli.py`
- `EN_API/tests/test_fulfillment.py`
- `docs/solutions/architecture-patterns/en-end-to-end-supply-chain-fulfillment-visibility.md`

> **决策记录**：该分支 §5.2 写明「头程**暂时不接入**统一履约入口」，等评估智美通/钉钉头程
> 如何移植到 EN。**本项目若要补头程，先读这一节，避免重复决策。**

---

## 2. 成本与拆包裹合并（**未合并**）

分支 `origin/feature/ustx-cost-compare`：

- `tongtool_order_cost/docs/reference/cost-engine-spec/`（00–31 共 30+ 篇）
  - `01-overview-and-glossary.md` / `02-keys-and-entities.md` / `03-data-sources.md`
  - `04-cost-decision-tables.md` / `07-colab-vs-en.md` / `08-special-cases.md`
  - `11-plan-new-ustx-processing-table.md` / `16-customer-sku-direct-path.md`
  - `18-sku-direct-impact-on-order-merge.md`
  - `30-design-merge-split-no-double-count.md` —— 拆包裹合并「合成一件再对 BOM」设计稿
  - `31-handoff-merge-split-B.md` —— 交接书
- 代码：`order_common_part` / `group_split_rows`（纯函数 + 测试），
  提交 `32a54286`、`e9147a6e`。
- `tongtool_order_cost/docs/reference/colab-cost-engine-spec.md`

**为什么与供应链整合相关**：

1. **原始数据整理**：拆包裹订单如果合并口径不对，销量和 BOM 成本都会重复计；
   预测与补货的「销量」必须先过这一层。
2. **SKU ↔ EN 物料映射**：成本引擎里的 `通途SKU → 客户物料号 → EN 物料号` 直连路径，
   就是主数据地图的一半。
3. **EN BOM 成本**：下单建议要不要看成本/毛利、资金占用，都依赖这套口径。

---

## 3. 库存 / 补货 / 订单（主分支已有）

| 模块 | 能做什么 | 与本项目的关系 |
|---|---|---|
| `stock_init/` | 通途库存 + EN BOM → 赛狐库存初始值 | 库存口径样板 |
| `warehouse_restock/` | EN BOM Cost List → 三成本拆分 → 赛狐海外仓备货单导入模板 | **补货单生成**的现成起点 |
| `other_outbound/` | 赛狐库存明细 → 其他出库清零 | 库存调整参照 |
| `cost_adjust/` | 赛狐成本补录单（采购成本 + 头程） | 资金/成本侧 |
| `item_cost_sx/` | EN BOM 成本 → 赛狐采购成本 | 成本输入 |
| `item_weight_size/` | 重量模板匹配 → 商品重尺 | 头程运费/装载 |
| `pb_orders/` | SPS 订单预检 → 通途导入 + 标签背贴；网页版任务/产物 | **销售→出库**的落地样板 |
| `pb_reconciliation/` | PB 月度对账 / TM 佣金 / UPS 交付核查 | 销售与交付对账 |
| `sellfox_settlement/` | 赛狐结算中心 → Amazon 账期 | 真实销售额口径 |
| `platform_account_reconciliation/` | OSTKUS / Wayfair 账期费用级对账 | 渠道销售口径 |
| `erpnext/` | 工单排查（setup→fetch→report） | **生产进度**事实 |
| `EN_API/` | BOM 成本列表/刷新、`item_shipment_status.py`、服务器与凭证入口 | EN 事实源 |
| `tongtool_api/` | ERP2 API + MCP（订单/库存/采购） | 通途事实源 |
| `tongtool_order_cost/` | 订单特殊规则成本引擎 + Google Sheet 月度表 | 订单/成本 |
| `tongtool_order_shipping/` | 通途订单导出 → 每包裹一行 + 背贴 PDF（**代码在同事 Colab**） | 出库/拆包裹 |
| `dingtalk/dingtalk_sheet/` | 只读钉钉表（`2026年下单表` / `发货信息总表`） | **头程入口（已可机器读）** |
| `web_automation/` | 通途/赛狐/通用浏览器自动化能力舱 | 无 API 时的采集手段 |
| `ai_access_poc/` | Open WebUI 壳 + IvyeaOps 只读板（统一 AI 接入 PoC） | 交互层/Agent 载体候选 |
| `dam-prototype/` | DAM 数字资产管理原型 | 产品原型经验 |
| `colab_kit/` | Colab notebook 读写改工具 | 现有业务脚本多在 Colab |

---

## 4. 已有的方法论文档（按分支标注）

### 主分支已有

- `docs/company-context.md` —— 公司背景、供应链、三系统 SKU 定义。
- `CONCEPTS.md` —— 共享词汇（实体、流程、状态）。
- `docs/agent-guide.md` —— 数据管道报告规范（总行数/成功/跳过/失败）。
- `docs/research/web-agent-platform-comparison-2026.md` —— Agent 平台选型（Open WebUI 等）。
- `docs/research/framework-maturity-shipping-research.md` —— Python 框架成熟度调研方法样板。
- `docs/ai-for-amazon-ops-2026.md` —— AI 在运营侧的实践分享。
- `docs/enterprise-agent-knowledge-system.md` —— 多用户 Agent + 知识沉淀可行性。
- `docs/solutions/workflow-issues/pb-out-of-stock-notification-and-zero-stock-orders.md`
- `docs/solutions/workflow-issues/cargo-location-tracking-source-reliability.md` ——
  「货物到哪了」四源分级（与本项目头程可视化直接相关）。
- `docs/solutions/integration-issues/...` 里的 SKU 映射、EN API、通途 API 经验。

### 仅在 PR #297 分支（待合并）

- `docs/solutions/workflow-issues/pb-replenishment-sizing-from-sales.md` ——
  **已跑通的补货量估算方法**：美中 Daneey 口径、仓名族、通途订单表读法、断货月剔除、
  在途只看通途采购单、EN Bin 不能当库存、Excel 结论打头。
- `docs/solutions/workflow-issues/sps-portal-ia-akn-operations.md`
- `docs/solutions/workflow-issues/pb-stockout-post-shipment-closed-loop.md`
- `pb_orders/docs/reference/notion-stockout.md`

### 仅在 `feature/ustx-cost-compare`

- `tongtool_order_cost/docs/reference/cost-engine-spec/*`（见 §2）。

### 仅在 `claude/frosty-hellman-58de7a`

- 端到端履约蓝图 + 实现（见 §1）。

---

## 5. 外部 / 待接入

| 来源 | 内容 | 现状 | 下一步 |
|---|---|---|---|
| **头程物流商 + WorkBuddy 大屏** | PJ 之前做过对接头程物流商的数据大屏；Jack 正在 PJ 的 WorkBuddy 上整理 | **代码不在本仓库** | 等 Jack 提 PR 到 Gitee 镜像 `gitee.com/keyapi/fzh-data`；先要数据结构与更新频率 |
| **钉钉两张表** | `2026年下单表`（年度订单明细、物流信息表）、`发货信息总表`（物流跟踪 Tracking、各仓明细） | 客户端已能只读 | 先做 V2.1 精确匹配 + 未匹配报告 |
| **智美通** | 货代/头程数据 | 未接入 | 评估 API/导出方式 |
| **海外仓 WMS** | 收货、加工、上架 | 无统一闭环 | V3/V4 |
| **船司/港口/AIS** | ETD/ETA/异常 | 无 | V3 |

---

## 6. 用户提到但仓库里**没找到**的（待确认）

> 这几项不要当成「不存在」，也不要当成「存在」—— 新对话第一件事是问用户要位置。

1. **`demand_forecast` 子项目**（记忆里：阶段 A 数据调研完成，通途订单月表 2023 至今 + EN 映射 +
   断货信号；阶段 B 待启动）。
   实查：`main` 与所有本地/远程分支均无 `demand_forecast/` 目录。
   → 可能在别的机器、未提交、或已删除。**要用户确认。**
2. **「之前做过简单的预估销量的多种方法对比」**。
   仓库里只找到 `pb-replenishment-sizing-from-sales.md`（方法），没找到多方法对比文档。
   → 可能在 Notion / 本地文件 / 别的仓库。
3. **「上周演示 demo 网页 Agent 的初步探索」**。
   候选是 `ai_access_poc/`（Open WebUI + 只读板，2026-07）或 `dam-prototype/`。
   → 需用户指认是哪一次、代码在哪。
4. **通途 SKU / Colab + GSheet 换用 EN BOM 成本表**的最近工作。
   相关分支是 `feature/ustx-cost-compare`，但「最近几天换用 EN BOM 成本表」的具体产出
   未在 main 上找到 → 需用户确认分支/路径。

---

## 7. 盘点结论

- **不是从零开始**：端到端履约蓝图 + 成本引擎 + 补货方法 + 三系统连接器都已存在，
  主要缺的是「**需求预测 + 补货/排产决策 + 审批视图**」这三块，以及把它们串成一条可复跑的链。
- **最大的风险不是技术，是口径与数据权威性**：库存/销量/在途在三套系统里都有，
  必须先把「谁是事实源」定下来。
- **第二风险是工作散落在未合并分支与个人手里**（Colab、WorkBuddy、Notion），
  新对话要先把这些收敛到 main 或明确的引用位置。
