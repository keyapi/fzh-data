---
okf: v0.1
type: Research
title: 补货证据链、人工判断留痕与闭环评估 — 设计与差距（只读）
date: 2026-11-24
owner: keyapi
status: 设计稿；未改业务代码、未部署、未开 PR
scope: supply_copilot / demand_collaboration / supply_chain_visibility / D5·D6·E（W1）
tags: [evidence-chain, human-in-the-loop, fva, override, backtesting, lineage, supply-copilot]
---

# 补货证据链、人工判断留痕与闭环评估

> **本轮只做调研与设计。** 不改业务代码、不部署、不写生产。
> 事实与判断分开标注：**【事实】**= 有代码/官方文档/审计文件可指；**【推断】**= 基于事实的判断；
> **【未核实】**= 公开信息冲突或没有一手来源。
> 本仓库是 **PUBLIC**：本文只写口径、字段、路径与行号，**不写任何分行数量、SKU 级库存、客户名明细**；
> 11-13 抽查的具体数字见本地 `D:/Work/fzh-order-store/analysis/*_20261113.md`（不入库）。

---

## 0. 结论先行

1. **证据链的"字段清单"我们大体已经有了，缺的是三样东西**：①同一行里"预测/需求/供给/动作"四段能逐字段回溯到源行；②`未知` 在计算层与展示层的一致表达（现在是分散的 `None`/`"未接入"` 字符串/`qty_status`）；③"人改了哪里、为什么、谁批的"这条链。
2. **当前 `decide`（live 决策器）有 3 处口径问题会让"看起来有证据、其实是 0 或虚高"**：SO 键不匹配（很可能恒为 0）、`po_on_time` 等于"有 ETA"而非"按时到"、未履约 SO 直接叠加在预测上（双计风险）。这三条比"再接一个数据源"更紧急。
3. **人工判断目前只能作用于需求基准行，不能作用于补货建议行**；且身份是进程参数（`--actor` / `--role`），不是登录身份 —— 防自批只在字符串层面成立。
4. **闭环评估不需要新造指标**：`INVENTORY_EVALUATION.md`（D37/D39/D40）已经定了 β/α、分位、比较协议；本轮要补的是 **FVA（预测增值）/ override（人工调整）分析 / tracking signal / 成对显著性检验**，并把"纯自动 vs 自动+人工"落成可执行的三种实验设计。
5. 三个最值得复用的开源组件：**StatsForecast（已在用）做批量滚动回测**、**sktime `evaluate` 做统一切分对照**、**OpenLineage/Marquez 做来源侧血缘登记**。frePPLe 维持 2026-10-27 的结论：**借逻辑、不部署**。

---

## 1. 完整证据链定义（逐字段）

### 1.1 一个"建议行"的身份键

**【事实】** `demand_collaboration/recommendation.py:349` 已用

```
(sku, customer, warehouse, physical_form, uom, period_start, period_end) → row_id(digest)
```

`supply_copilot/decide.py:495-497` 用 `(product_id, 主仓, UOM)` —— **少了两维**：客户/形态与期间。
两套键不一致，是后面"SO 命中不了"的根因之一（见 §2 B2）。

**建议统一为 8 元组 + 2 个版本维度**：

| 维度 | 取值来源 | 缺失时的表达 |
|---|---|---|
| `sku_canonical` | `sku_map.tsv` / `self_fulfilled_demand.canonical` | 不猜；行标 `identity_unknown` |
| `customer` | EN 客户 / `SO_CUSTOMER_POOL` | `归属待确认`（不静默隐藏，见 11-13 UX 简报） |
| `warehouse_pool` | 仓角色映射（`resolve_warehouse_role`） | 不合并到主仓 |
| `physical_form` | 成品 / 半成品 / 皮壳（`sellfox` 分型口径） | 保留原值，不归并 |
| `uom` | `service_policy.csv` / D6 行 | `uom_unknown` → 数量 `None` |
| `period_start/end` | 预测窗口 / 建议期间 | 缺期间则不生成建议行 |
| `as_of`（快照时点，带时区） | `decide.parse_as_of` 强制时区 | 无时区 = 拒绝运行 |
| `pack_version` / `run_id` / `forecast_run_id` | manifest | 无 manifest 不进入"可执行" |

### 1.2 需求侧（D）

| # | 字段 | 口径定义（要能检查什么） | 现状 |
|---|---|---|---|
| D1 | `hist_series` + `hist_window` | 历史是按**发运量**还是**接单量**；是否已扣退货；是否含 FBA/其他渠道；窗口长度 | **部分**【事实】`D5_v6_8.xlsx` 提供预测，原始历史在 `pull-history` 快照（截止 2026-10-26），**CLI 不展示序列口径** |
| D2 | `censoring_flag` | 该 SKU×期间是否存在断货/清仓/零库存观测（需求被截断） | **无**【事实】分型文档要求"零库存月不是真实需求 0"，但 `decide` 输出无此字段 |
| D3 | `model_id` / `model_version` / `trained_until` | 用的是 AutoETS / naive / tree / combo；训练截止；是否本次重训 | **部分**【事实】`recommend.py:113` 输出 `模型` + `holdout_wape`；`rebuild` 产 `en-demand-forecast-v1`（`decide.py:59`） |
| D4 | `quantile` + `quantile_basis` | p50 / p90 / q95；**是"累计需求分位"还是"逐期分位"**；是否做过覆盖率回测 | **部分**【事实】`decide.py:451-453, 470` 明写"p90 为经验分位，未做覆盖率回测"；D6 仍 q95 → 同一报告里并存两档 |
| D5 | `demand_period_basis` | **整期总量** vs **剩余期**（as_of 之后的部分）；窗口 `lead_days` = 60/90/120 | **部分**【事实】`decide.py:60, 419` 取窗口 p50 合计；不逐桶摊派（module docstring 已声明） |
| D6 | `demand_evidence` 文案 | 一行能说清"这个数是窗口总量，不是某天" | **有**【事实】`decide.py:598-599` |
| D7 | `open_so`（分桶） | 近期 / 历史开放 / 创建日未知；每行 `so`、`so_line`、`qty`、`delivered`、`open_qty`、`status`、`docstatus`、`delivery_date`、`overdue_days`、`warehouse`、`stage` | **有**【事实】`so_evidence.py:184-198`，且 `so_lines` 全量保留不丢弃 |
| D8 | `so_in_forecast` | 这批 SO **是否已含在预测里** → 决定"冲减"还是"另加" | **无**【事实】`decide.py:555` 直接 `demand + so`；D39 §3 明确要求先分清源语义 |
| D9 | `so_effective_filter` | 已提交、有效开放、逐行 `max(qty-delivered,0)>0`；取消/被替代单排除；`Closed` 剩余留档 | **部分**【事实】`so_evidence.py:143-145` 已做 `Closed`/`docstatus` 过滤，但未区分"已改单作废"（`amended_from`） |

> 关于 `per_delivered`：**【事实】** 11-13 审计指出它是**整单**指标，不能代替行余额；`so_evidence` 用的是行级 `qty - delivered_qty`，方向正确，**但未证明未交量属于哪一张 SO 的哪一行**（这正是 11-13 §1 的核心结论）。

### 1.3 供给侧（C / E）

| # | 字段 | 口径定义 | 现状 |
|---|---|---|---|
| S1 | `c_available`（期初可发） | 哪个仓、是否已扣占用、`snapshot_at`、是否含次品、是否含退货仓 | **有（弱）**【事实】`decide.py:212-262` 按仓前缀汇总；无批次去重、无 FBA 排除、无退货净额 |
| S2 | `en_shipped` / `intransit` | 已发运未到 vs 在途在库 | **有**【事实】`_supply_facts` 的 `intransit`；`refresh._live_stock` 另给 `waiting_shipment`/`defects` |
| S3 | `waiting_observed` | 未对单的"待发观察量"，**不计入供给**，只作观察 | **部分**【事实】只在 `refresh.py:36-40` 与 UI 出现；**`decide` 不消费**，也不进可执行性判据 |
| S4 | `po_open` | 每张 PO：`document_key`、`qty`、`in_quantity`、`status`、`willArriveDate`、目的仓、SKU 映射 | **有（弱）**【事实】`decide.py:265-332`；tsv 路径无 ETA（`eta=False`），JSONL 才带 ETA |
| S5 | `po_on_time` | **ETA ≤ 需要日** 的量 | **错**【事实】`decide.py:291-295, 333-334`：`bucket = "po_on_time" if eta else ...`，`eta=bool(eta)` —— 只要有 ETA 字段就算"按时" |
| S6 | `wo_progress` | 工单：第一道工序完成量、状态是否回写、是否 0 工序卡 | **无**【事实】UI `index.html` 节点写死 `'未接入'`；`supply_chain_visibility` 阶段 3 独立屏未做 |
| S7 | `dn_lines` | DN 行 ↔ SO 行（`so_detail`）；数量守恒；部分签收 | **无**【事实】同上，节点 `'未接入'` |
| S8 | `shipment` / 头程 | 批次号、离港/到港/入仓、目的仓、可售日 | **无**【事实】`supply_chain_visibility/AGENT_HANDOFF.md` §4 边界：阶段 4–8 外置，**暂缓接入** |
| S9 | `cg_buffer` | WayfairCG = **下游缓冲，不可回拨** | **有但语义打架**【事实】`decide.py:240-243` 注释写"跨分公司可调"；`min(live_cg, d6_cg)` 只是把 D6 当上限（`decide.py:527-531`） |
| S10 | `stage_dedup` | 同一批供应只在**一个**阶段计一次；进入 C 后退出未来到货；PO 与 shipment 不叠加 | **无**【事实】`decide.py:25-31` module docstring 明写未接入批次去重/跨阶段同批/FBA 分配 |
| S11 | `lead_time` | 路线实测交期（采购+生产+头程+清关+上架） | **无（伪）**【事实】`decide.py:774-786` 用 `D6 需要日 − 下单日` 反推，且 `lead_by_sku` 只用于重排下单日 |

### 1.4 计算侧

| # | 字段 | 当前公式 / 规则 | 需要能检查什么 |
|---|---|---|---|
| K1 | `net_demand` | `max(0, ceil((demand + so) − (opening + intransit + po + cg)))`（`decide.py:555-559`） | 每一项的符号与量级；为什么 SO 是加不是减 |
| K2 | `supply_proven` | `opening + po_on_time + cg`（`decide.py:558`） | "已证按时"到底证了什么（当前=有 ETA） |
| K3 | `worst_case` | `max(0, ceil((demand+so) − supply_proven))` | 在途/无 ETA 迟到时的上界 |
| K4 | `service_level` | D6 q95（历史包）/ live p90 | 依据是什么；是否已批准 |
| K5 | `coverage_days` | 源表 `覆盖` 列 | **基准不明**：45 是"到某天"还是"45 天量"？【事实】UI 自己标 `title="源覆盖天数，基准待核"` |
| K6 | `action` | `补 / 不补 / 待核`（`decide.py:568-576`） | 缺 **催已有**（`expedite_qty` 直接抄 D6，`decide.py:593`）与 **观察** |
| K7 | `qty_status` | `measured / replay / unknown_<缺什么>` | 可接受；但 `unknown_*` 是拼接字符串，**不是结构化字段** |
| K8 | `confidence` | 源表"置信度"文本 → low/medium/high | **无计算依据**【事实】`recommendation.py:192-212` 只做文本归一 |
| K9 | `date_source` | `d6_pack` / `d6_need_minus_d6_lead` | 已有，可接受，但要在 UI 上明示 |

### 1.5 来源侧（每个数字的"身份证"）

| # | 字段 | 现状 |
|---|---|---|
| P1 | `source_file` + `sha256` | **有**：库存/SO/PO 都有文件级 sha256（`decide.py:107-111, 612-613`） |
| P2 | `source_row`（行号） | **无**（`supply_copilot`）；**有**（`demand_collaboration` 的 CSV：`recommendation.py:383`） |
| P3 | `row_hash` | **无**（同上，CSV 侧有 `source_hash`） |
| P4 | `imported_at` | **无**（`recommendation.py:537` 留了 `imported_at=None`） |
| P5 | `as_of` / `snapshot_at` / `fetched_at` / `stale` | **有**【事实】`live_stock.py:249-251, 407-417`：`ok` / `fallback_stale` 两态，UI 有"旧数据"徽标 |
| P6 | `input = accepted + rejected + skipped` 对账 | **有（仅 CSV 快照）**【事实】`recommendation.py:424-427`；`supply_copilot` 的 D6/D5/D3b 是 `pd.read_excel` 直读，**无对账报告** |
| P7 | 拒收/跳过原因 | **有（仅 CSV 快照）**：`rejected[]` / `skipped[]` 带 `reason` + `source_row` |

> **判断**：来源侧在"快照导入"这条路上已经做到了本次要求的 80%（`recommendation.py`）；缺的是
> 把它推广到 **D6/D5/D3b xlsx 与 live 库存/PO/SO** 三类输入，以及行级行号/哈希。

### 1.6 人工侧

| # | 字段 | 现状 |
|---|---|---|
| H1 | `judgment_type` | **部分**：`delta / total / percent / event_only`（`index.html` `kinds`）—— 缺 `ACCEPT`（接受自动值）、`REJECT`、`NEED_EVIDENCE`、`ADJUST_PERIOD` |
| H2 | `author` / `reviewer` | **有**：`core.py:300, 339` |
| H3 | `decided_at` / `revision` | **有**：`core.py:324-339`，带乐观锁 `revision_conflict` |
| H4 | `basis`（依据）/ `evidence`（证据链接） | **有**：表单两栏 |
| H5 | `affected_period`（起止） | **有**：`start` / `end` |
| H6 | `baseline_version`（绑定版本） | **有**：提交时带 `baseline_version`，发布时按版本过滤（`core.py:355`） |
| H7 | `before/after` 数值 | **弱**：`_adjust` 重算，但审计表只存 `reason` + `revision`（`core.py:341`） |
| H8 | 作用对象 | **只到需求基准行**：`row_id` 来自 `baseline.rows`；**补货建议行不可提交判断** |

---

## 2. 现状差距清单（对照 11-13 抽查）

分类：**A 数据未接** / **B 口径有误** / **C 留痕与治理缺失**。
每条给证据位置。"严重度"只针对本轮目标（可检查、可留痕、可闭环）。

### A. 数据未接

| # | 缺口 | 证据 | 后果 |
|---|---|---|---|
| A1 | 生产 / WO、DN、Shipment 三个节点恒为"未接入" | `index.html` `recChain()` 写死字符串；`supply_chain_visibility/AGENT_HANDOFF.md` §3–4 | 链条断在"SO 之后"，无法回答"这 8 件到底在哪" |
| A2 | 头程/海运/国外仓（阶段 4–8）外置 | 同上 §4 | ETA 只能靠 D6 包或 PO 字段 |
| A3 | 通途 PO 未按 `purchaseOrderQuery` 直连 | `supply_copilot/README.md:59-64` 明确列为"可执行性=否"的原因之一 | PO 多落物料仓/未映射 SKU → 供给按 0 计（`decide.py:803-809` 有警告） |
| A4 | CG 无 live 重算 | `decide.py:534` `cg_source="d6_pack"` | CG 抵扣沿用历史包，时点不一致 |
| A5 | 预测未做覆盖率回测 | `decide.py:452-453, 470` 自述 | p90 被当"90% 服务档"用，但没有校准证据 |
| A6 | 无日级库存历史 | `docs/solutions/workflow-issues/supply-sku-segmentation-and-stockout-evidence.md`（PJ 22 个日期、最大间隔 38 天） | 断货率/服务水平**无法真回放**，只能情景模拟 |
| A7 | D6/D5/D3b 无导入对账（接收/拒收/跳过） | `recommend.py:33-35` 直读 `read_excel` | "入 N 行→出 M 行"对不上时无法解释 |
| A8 | 无行级 `source_row` / `row_hash` | `decide.py` 全表只有文件级 sha256 | 技术负责人无法"点到一个数字看源行" |

### B. 口径有误（最紧急）

| # | 问题 | 证据 | 后果（【推断】） |
|---|---|---|---|
| **B1** | `po_on_time` 的定义是"**有 ETA 字段**"，不是"ETA ≤ 需要日" | `decide.py:291-295`（`if eta: evidence["with_eta"]+=1`）、`:333-334`（`eta=bool(eta)`）→ `:294-295` 分桶 `po_on_time` / `po_conditional` | `supply_proven`（"已证按时供给"）**系统性高估**；`new_qty` 被低估；最坏情况列被当成"保守值"而实际是常态 |
| **B2** | SO 键未经 `sku_map` 归一，与主循环键不一致 | `decide.py:375-376` 用 `(raw item_code, 固定主仓, 原样 UOM)`，**不走 `lookup`**；对比 `_supply_facts`:232 与 `_po_facts`:277 都走了 `lookup.get(raw_sku)`；主循环 `:495-497` 用 `(canonical product_id, 主仓, D6 UOM)`；`:522` 源存在时"没行=0" | **【推断】** 只要 SO 导出的 `item_code` 不是 canonical 成品码（皮壳 `PK#`、通途 SKU、带后缀形态都算），未履约订单就会被**当成 0**。这是最危险的一种：**看起来有证据，实际是静默 0**，违反"未知不补 0" |
| **B3** | 未履约 SO 直接**加**在预测上 | `decide.py:555` `total_demand = demand_qty + (so_qty or 0.0)`；`meta.limits` 写"SO 按未完成量计入需求" | 若预测已含这些订单 → **双计**（D39 §3 要求先分清源语义再决定冲减/另加） |
| B4 | CG 语义写成"跨分公司可调拨" | `decide.py:240-243`；列名仍是 `CG可调拨抵扣`；UI 已改口径为"下游缓冲，不可回拨"（`index.html` `rec-grid`） | 代码与业务口径打架；下游缓冲被当成可回拨供给 |
| B5 | `waiting_shipment` 未进入决策 | 只在 `refresh.py:36-40`；`decide` 无该字段 | 11-13 的核心问题（"待发的 8/9 件算不算供给"）在决策器里**没有答案** |
| B6 | 阶段去重/批次守恒未接入 | `decide.py:25-31` docstring；`:812-813` warning | C 可发与净额引擎可能有差；同一批供应可能跨阶段重复 |
| B7 | 期间口径混用：需求是"窗口总量"，日期是"D6 计划" | `decide.py:868-869` limits；`:498-509` | 行内"整期缺多少"与"哪天要下单"来自两个时点的两套假设 |
| B8 | 分位混用：同一报告 D6 q95 与 live p90 并列 | `decide.py:510-517` + `demand_source` 逐行标注 | 可接受（有逐行标注），但汇总层没有"本报告用了几种档位"的计数 |
| B9 | 覆盖天数无基准 | `recommendation.py:215-223` 只解析数字+单位；UI 标"基准待核" | "覆盖 45" 无法被技术负责人复核 |
| B10 | `expedite`（催已有）不按 live 重算 | `decide.py:593` 直接抄 D6 `催已有量`；`action` 枚举无"催已有" | 建议动作缺一整类；与 11-13 首行"动作=催已有 但 PO/SO=0/0"的疑问直接相关 |

### C. 留痕与治理缺失

| # | 缺口 | 证据 |
|---|---|---|
| C1 | 身份是进程参数，不是登录身份 | `demand_collaboration/__main__.py:12-13`（`--actor` / `--role`）；`web.py:29-31`；UI 自述"身份由本地服务配置" |
| C2 | 防自批只在字符串层面 | `core.py:329-330` `if actor == p["author"]` —— 同一人用两个 `--actor` 标签即可绕过 |
| C3 | 无法记录"我同意自动值" | `kinds` 无 `ACCEPT`；只能 `event_only/delta/total/percent` |
| C4 | 补货建议行不可提交判断 | `row_id` 来自 `baseline.rows`；`recommendation.rows` 只读（`recommendation.py:5-7` 自述 READ_ONLY） |
| C5 | `decide` 输出无签名/无发布概念 | 只落 md/json；无 `snapshot_id`、无不可变存储 |
| C6 | 审计表无结构化 before/after | `core.py:341` 只存 `reason` + `revision` |
| C7 | 无"调整过期/失效"机制 | 提案的 `start/end` 是静态日期，跨周滚动时不会自动衰减 |

> 一句话：**A 是"没接"，B 是"接错了"，C 是"接了但记不下来"。** 优先级 B > C > A —— 因为 B 会让技术负责人**相信一个错的数**。

---

## 3. 人工判断与留痕模型

### 3.1 判断类型（enum，建议冻结）

| 类型 | 语义 | 对数量的影响 | 谁可提交 |
|---|---|---|---|
| `ACCEPT` | 认可系统建议（含"我核过了"） | 不变 | 运营 |
| `ADJUST_QTY` | 改量：`delta` / `total` / `percent` | 替换或增减 | 运营 |
| `ADJUST_PERIOD` | 改期间（提前/延后需要日、改覆盖窗口） | 不改量，改时序 | 运营 → 计划复核 |
| `EVENT_ONLY` | 报事件：促销 / 提价降价 / 活动 / 渠道变化 / 断货 / 交期变动 | 不直接改量，作为特征与解释 | 运营 |
| `REJECT` | 驳回系统建议（必须填理由 + 依据） | 建议不生效 | 复核/主管 |
| `NEED_EVIDENCE` | 暂不能判断（缺证据，指定缺什么） | 保持 `None`，不得补 0 | 任何角色 |

**关键设计**：`ACCEPT` 是本次新增的**最重要一条**。现在系统只能表达"我要改"，不能表达"我确认不改"——
没有它，就无法区分"没人看"和"人看过并认可"，FVA 也就无法归因到人。

### 3.2 谁能改、如何避免自批

现状：**【事实】** 只有 `operator` / `reviewer` 两个角色 + 字符串比较作者（`core.py:313-330`）。
问题：单机部署时，一个人可以 `--actor 张三 --role operator` 提交，另开 `--actor 李四 --role reviewer` 批准。

**建议（三层 + 硬约束）**：

1. **身份来自 EN 登录（OIDC / 公司 SSO）**，`actor = sub`，不从命令行传。进程只决定"这个服务以谁的身份对外"，
   不决定"这条记录是谁写的"。→ 与既有决定一致：*公司内部工具用公司 OIDC 登录即准入，不做逐人白名单*。
2. **提交与批准必须是不同 `sub`**（不是不同字符串标签），且**同一 `sub` 不得在同一建议行上既 `ADJUST` 又 `REJECT`**。
3. **高风险二级批准**：`|delta| / base > 阈值`（例如 >30%）或 `new_qty` 超过某绝对量，或"把不补改成补"且跨月，
   需要第二人（计划/主管）再批一次。阈值**不在本轮定**，由业务拍板（用户主权）。
4. **留痕不可编辑**：判断只能"追加 + 撤销（新增一条 `REVOKE` 指向原记录）"，不 UPDATE 原行。

### 3.3 版本与冻结

- **三层版本**：`pack_version`（数据包）→ `baseline_version`（需求基准）→ `decision_date`（决策日/发布快照）。
  已有 `baseline_version` 绑定（`core.py:355`）与 `publication` 快照，可直接扩展。
- **冻结规则**：发布 = 把"当时的建议 + 判断 + 输入哈希"打包成不可变快照（`snapshot_id = digest(body)`，
  参照 `recommendation.py:535-537`）。冻结后：
  - 事实变化（新库存/新 SO）**不覆盖**旧快照，只生成新版本并标 `supersedes`；
  - 判断过期（`end < as_of`）**不删除**，标 `expired`，在下一版重新评估。
- **`decide` 输出也应带 `snapshot_id`**（当前没有，见 C5）。

### 3.4 与"逐周调整"兼容

- 判断以 **(行, 事件, 期间)** 三元组存，不是"整表重填"。每周滚动时：
  - 未过期的调整**自动继承**，并显示"沿用上周判断（作者/日期）"；
  - 过期调整标 `expired`，需重新确认（可一键"沿用"）；
  - 新证据导致建议翻转时，**必须提示**"你的调整与本周系统建议方向相反"，不静默覆盖。
- 允许"只对剩余期生效"：`period_start = max(判断起点, as_of+1)`，避免把已过去的部分重复调整。

### 3.5 UI 上怎么让非技术人员看懂（不用行话）

**白话词典（页面直接用，不出现 C/D/E/q50 这些代号）**：

| 行话 | 页面说法 |
|---|---|
| C 可发供给 | 手上现在能发的 |
| EN 已发运/在途 | 已经从工厂发出、在路上 |
| PO 追加 | 已经下过单、还没到 |
| SO 已下 | 客户已经订了、还没交 |
| CG 抵扣 | 下游仓已备的（不能拉回来用） |
| q50 / q90 / q95 | 预计卖 / 偏保守的预计 / 很保守的预计 |
| 覆盖 45 | 现在这些货能撑到 **12/26** |
| 待核 / unknown | **不知道**（灰底斜体，绝不显示 0） |

**三个按钮**：`我同意` / `我要改` / `我知道一个情况`。
`我要改` 只问两个问题："改成多少" "因为什么（活动/促销/客户说要加/别的）"。

---

## 4. 闭环评估：SOTA 与开源方案

> 本节**不重造**指标定义：β/α、分位、Bias/WAPE、比较协议已在
> `docs/research/supply-chain/2026-10-20/claude/control/INVENTORY_EVALUATION.md`（D37/D39/D40）定过，
> 并与 SC08 任务书绑定。本节只补四件它没写的东西：**FVA、override 分析、tracking signal、成对显著性**。

### 4.1 预测价值增量（FVA）

**【事实】** FVA 的定义是"某一步骤/参与者对某个预测绩效指标带来**的变化量**"，以 **naive（朴素）预测作为
安慰剂/对照组**；FVA ≤ 0 表示这一步没有增加价值。
来源：[SAS《Forecast Value Added Analysis: Step by Step》](https://www.sas.com/content/dam/SAS/en_us/doc/whitepaper1/forecast-value-added-analysis-106186.pdf)（Michael Gilliland）、
[ISF 2019 讲义（naive as placebo）](https://isf.forecasters.org/wp-content/uploads/gravity_forms/2-dd30f7ae09136fa695c552259bdb3f99/2019/07/Gilliland_Michael_ISF2019.pdf)。

**本项目落法**（三步链，逐级相减）：

```
FVA_统计模型 = MAPE(naive)   − MAPE(统计预测)        # 模型有没有超过"照抄上周"
FVA_人工     = MAPE(统计预测) − MAPE(最终执行值)      # 人改完是变好还是变坏
FVA_流程     = MAPE(naive)   − MAPE(最终执行值)      # 整条流程的净增值
```

**必须同时报**：样本 SKU 数、销量覆盖、每档的中位数（不只均值）、以及"改坏的 SKU 占比"。
**【推断】** 如果只看均值，少数改对的高销量 SKU 会掩盖大量改坏的长尾。

### 4.2 Override（人工调整）效果分析

**【事实】** 2024 年 IJF 论文《Forecast value added in demand planning》做了系统梳理：已有研究结论**不一致**——
在有促销等**新信息**、且预测者专业度高、系统可信度低时，判断性调整能改善准确度；
但在一般情形下"准确度通常被降低"（引 Fildes & Goodwin 2007 等）。
来源：[ScienceDirect 摘要](https://www.sciencedirect.com/science/article/pii/S0169207024000736)。

**结论 → 设计**：不能一刀切"禁止改"或"鼓励改"，而要**按"有没有新信息"分层评估**：

| 分层 | 判据 | 期望 |
|---|---|---|
| L-A 有事件依据 | 填了 `EVENT_ONLY`（促销/提价/活动）且事件日期覆盖该期间 | 应改善 |
| L-B 无事件、纯凭经验 | 只填 `ADJUST_QTY`，无事件 | 常变差，需重点监控 |
| L-C 只改期间 | `ADJUST_PERIOD` | 评估"到货日误差"而非需求量误差 |

**必备报表**（每期滚动出一次）：
1. 每档 FVA、改坏占比、按 SKU 分型（正常/慢销/长尾/短史，见 `supply-sku-segmentation-and-stockout-evidence.md`）分组；
2. "调整幅度 vs 效果"散点（大改是否更差）；
3. 高频修改者的个人 FVA（**只给本人与主管，不进公开看板** —— 避免把工具变成考核）。

### 4.3 Bias / Tracking Signal

- **Bias**（已有定义）：`Σ(预测−实际)/Σ实际`，正=高估。
- **Tracking Signal**（本项目新引入）：`TS_t = Σ_{i≤t}(F_i − A_i) / MAD_t`，|TS| > 4 视为"系统性偏差"。
  **【推断/未核实】** 阈值 4 是行业经验规则，**不是本项目已批准的门槛**；先作为"告警信号"入库，
  由 D40 的回放分级决定是否升级为判据。
- **用在哪**：不是给老板看，而是给"预测维护者"看 —— 哪个 SKU 连续 4 周同一方向偏，说明模型或事件没被吸收。

### 4.4 回测与滚动评估（不自己写循环）

| 方案 | 官方入口 | 适用性判断 |
|---|---|---|
| **StatsForecast**（已在用 2.1.1） | [Cross validation 教程](https://nixtlaverse.nixtla.io/statsforecast/docs/tutorials/crossvalidation.html)、[端到端 walkthrough](https://nixtlaverse.nixtla.io/statsforecast/docs/getting-started/getting_started_complete.html) | **【推断】首选**：`StatsForecast.cross_validation` 一次跑完多 SKU、多切点；与现有 `rebuild` 同栈，零迁移成本 |
| **sktime** `evaluate` | [API 参考](https://www.sktime.net/docs/api-reference/sktimeforecastingmodel-evaluationevaluate) | **【推断】次选**：切分器（`ExpandingWindowSplitter` / 滑动窗）+ 多 scoring + `strategy=refit/update` 统一表达；适合做"换模型/换切分"的对照实验，不必自己写滚动循环 |
| **Darts** `historical_forecasts` / `backtest` | [官方文档](https://unit8co.github.io/darts/) | **【推断】可选**：封装最省事，但依赖重（torch），本项目不需要深度模型时不划算 |
| **frePPLe** | [GitHub（MIT 社区版）](https://github.com/frePPLe/frepple) | **维持既有结论：借逻辑、不部署**（见 `docs/solutions/tooling-decisions/frepple-evaluation-and-borrow-logic.md`）。可借的是 **forecast consumption**（gross forecast − open orders = net forecast）——正好对应 §2 B3 的双计问题 |

### 4.5 业务 KPI（直接引用，不新造）

| 指标 | 定义来源 | 本项目边界 |
|---|---|---|
| Fill rate β（主报） | `INVENTORY_EVALUATION.md` §3 + [Sobel 2004](https://pubsonline.informs.org/doi/pdf/10.1287/msom.1030.0027) | 缺潜在需求时只能报"已接订单满足率" |
| CSL α（辅报） | 同上 + [MIT 15.763 课程总结](https://ocw.mit.edu/courses/15-763j-manufacturing-system-and-supply-chain-design-spring-2005/e1800430fdccaf618b22bd551fc00fac_summary.pdf) | 周期不可定义 → 不可评 |
| 库存天数 / 资金占用 | 同上 §3 | 时间加权，不用期末余额 |
| 过剩 / 报废 | 同上 §3 | 阈值须事先声明 |
| 履约满足率 | 同上 §3 | 与 β 分开报，不混用 |
| 缺货持续 | 同上 §3 | 快照稀疏时只报"信号"，不报"连续断货天数" |

### 4.6 「纯自动 vs 自动+人工」怎么比

**三种设计，按证据强度排序**（命名遵循 D39/D40：评估用 `MODEL_ONLY` / `FULL_FLOW`，**不要再用 A/B**）：

| 设计 | 做法 | 证据强度 | 成本 |
|---|---|---|---|
| **① 同期间成对比较（paired）** | 同一 `(SKU×周)` 上，同时保存"系统建议值"与"最终执行值"，比较二者对实际的误差 | 中：观测性，有选择偏差（人只改他关心的行） | 低：加两个字段即可 |
| **② 反事实模拟** | 固定初始库存、同一需求真值路径、同一供给/提前期路径，只换政策：`MODEL_ONLY` vs `FULL_FLOW`（把人改的值喂回去） | 中高：可控，但需求真值在缺货段不可见 | 中：需仿真器（SC08 已有） |
| **③ 分群随机化（影子 A/B）** | 按 SKU 簇或周块随机分组，一组只走系统值，一组可人工改 | 高：可因果归因 | 高：有业务风险（可能故意让一组缺货），**必须业务授权** |

**统计怎么做（关键，且现在完全没做）**：

- **损失差分 + Diebold–Mariano 检验**：对每条 SKU 序列算两种方法的损失差 `d_t = L(系统)_t − L(人工)_t`，
  检验 `E[d_t] = 0`。DM 允许非二次、非对称损失，且允许误差自相关 —— 正好适合我们的场景
  （[Diebold & Mariano 1995, JBES 13(3):253-263](https://doi.org/10.1080/07350015.1995.10524599)）。
- **不要按 SKU 独立检验再数 p 值**：SKU 之间共享供应商/仓位/季节，必须**按 SKU 簇或时间块做 block bootstrap**
  （D40 §4 已要求"以 SKU 整簇/时间块的成对重采样保留依赖"）。
- **样本量与功效（必须事先算，不能事后挑）**：
  `n ≈ (z_{1−α/2} + z_{1−β})² · σ² / δ²`；断货率这类比例指标用 `σ² = p(1−p)`。
  例（**纯示例，非本项目参数**）：p=0.05、想检出 δ=1 个百分点、α=0.05、power=0.8 → 每组约 3,000 个 SKU×周观测。
  **【推断】** 这意味着"周级、单分公司、几百个 SKU"的样本**不足以**在断货率上做出统计显著结论，
  只能做"同服务水平下库存占用"这类连续指标（方差小得多）。
- **预先登记**（D40 §4 已定）：指标、最小可检测效应、退化容忍、切点、检验方法 —— 先写后跑。
- **不许**用 1−WAPE 当准确率，不许用"事后挑一个显著项"宣布成功（`INVENTORY_EVALUATION.md` §2/§6）。

### 4.7 来源侧：血缘与事件存储

| 方案 | 入口 | 适用性 |
|---|---|---|
| **OpenLineage 规范 + Marquez** | [openlineage.io](https://openlineage.io/docs/)、[MarquezProject/marquez](https://github.com/MarquezProject/marquez) | **【推断】推荐**：标准是 `job / dataset / run` facet，能把 `pack → rebuild → decide` 这条链登记成图；对本项目需自己写一个轻量 extractor（我们不是 Airflow/Spark），成本 1–2 天 |
| **MLflow** | [Evaluation 文档](https://mlflow.org/docs/latest/ml/evaluation/) | **【推断】可选**：把每次 `decide` 当一次 run，记 metrics + artifact（报告 md/json）+ 参数（pack 版本、阈值），天然带 run 对比 UI |
| **事件溯源 / 追加式审计** | 无需外部组件 | **【事实】** `demand_collaboration/core.py` 的 `_audit` 表已经是**弱事件流**；建议直接升级为 append-only（禁止 UPDATE），并给每条记录 `prev_hash` 形成哈希链，即可满足"不可篡改留痕"，不必引入 Kafka/EventStoreDB |
| **数据校验**（可选） | pandera / Great Expectations | 若要做"列验证全覆盖/缺列报错"（AGENTS 铁律②），pandera 的 schema 断言最轻 |

---

## 5. UI 方案：技术视图与非技术视图共存

### 5.1 四层展开（同一页面，默认层级不同）

| 层 | 内容 | 默认展开给 |
|---|---|---|
| **L0 一句话结论** | "美东 · KS…：未来 90 天**不缺**" / "**缺 320 件**，建议 **12/02 前**下单" | 所有人 |
| **L1 为什么（三行）** | ① 预计卖 X（区间 X–Y）② 手上+在途 Z ③ 差 W | 运营 |
| **L2 证据链时间线** | `SO → 生产 → DN → 在途 → 通途PO → 当前库存 → 下游CG`，每节点：数量 / 日期 / 状态 / **来源时点徽标** | 运营（可点开）、技术（默认） |
| **L3 证据原文** | 逐行表格（SO 行 / PO 行 / 库存行）+ `source_file` / `row` / `hash` / `as_of` + **可复制的 JSON** + **可复制的重跑命令** | 技术负责人 |

**【事实】** 现状已经做到 L2 的骨架（`index.html` `recChain()` / `recSOLines()` / `recLivePanel()`），
以及 L3 的一部分（`模型与来源` 折叠块：`source_row` / `source_hash` / `period_basis`）。
**缺的是**：L0 的"一句话"目前还是表格行；L3 的"重跑命令"没有。

### 5.2 未知/待核/不可用的统一标记（四个徽标，不许多造）

| 徽标 | 含义 | 视觉 |
|---|---|---|
| `实时` | 本次刷新读到 | 绿 |
| `旧 · N 小时` | 读到了但不是最新（`fallback_stale`） | 橙 |
| `未接入` | 系统里没有这个能力（生产/DN/头程） | 灰 |
| `待核` | 有源但这份数据不可信/口径未定（覆蓋天数、CG 规则） | 橙 |

**硬规则**：任何数字位置只允许出现"数字"或"未知"（灰底斜体），**不允许出现 0 代替未知**。
**【事实】** 这条已被写进代码纪律（`decide.py:33` "未知一律 None，绝不写 0"；`recommendation.py:26` `unknown_is_null_never_zero`），
但 B2 那个 bug 说明**代码纪律不等于结果纪律** —— 需要"未知率"作为报表字段暴露出来。

### 5.3 技术负责人的证据链检查清单（逐项打勾）

| # | 检查项 | 通过判据 |
|---|---|---|
| 1 | 时点一致 | 库存/SO/PO/预测四个源各有 `as_of`，最大时差 ≤ 阈值（建议 12h，`decide.py:827`） |
| 2 | 身份可追 | 每个数字能点到 `source_file` + 行号 + `row_hash` |
| 3 | 数量对账 | 每个源 `input = accepted + rejected + skipped`，差数为 0 或有解释 |
| 4 | 阶段互斥 | 同一供应不在两个阶段同时计数；进入 C 后退出未来到货 |
| 5 | SO 守恒 | 开放量按行余额；`Closed 未发` 单列为"死单"，不静默丢弃 |
| 6 | 未知不补 0 | 每个供给/需求字段的"未知率"有数；`qty_status != measured` 的行数被报出 |
| 7 | 按时 ≠ 有 ETA | "已证按时"必须带与需要日的比较（当前 B1 不通过） |
| 8 | 可复现 | 报告里带 `run_id` + 命令；同输入重跑结果哈希一致 |
| 9 | 人改留痕 | 每个被改的数有作者/时间/依据/版本，且能显示"改前→改后" |
| 10 | 冻结 | 发布快照有 `snapshot_id`，历史快照不被覆盖 |

### 5.4 非技术人员视图的三条禁忌

1. **不给小数**：`394.03` → `约 394 件`（11-13 UX 简报已点出）。
2. **不给代号**：不出现 `q95`、`C`、`E`。
3. **不隐藏"不知道"**：缺数据的行**必须出现**（标 `待确认` / `待核`），不能因为"看着乱"就过滤掉
   —— 11-13 里"5 行不在范围被静默隐藏"就是反例。

---

## 6. 下一步任务（按优先级）

| 优先级 | 任务 | 产物 | 验收 |
|---|---|---|---|
| **P0** | 修 `decide` 三处口径：B1（`po_on_time` 必须与需要日比较）、B2（SO 键改 canonical + 期间 + 客户）、B3（SO 是否已在预测内，做成显式开关而非硬编码相加） | 补丁 + 单测（合成样例：PO ETA 晚于需要日 → 不得进 `supply_proven`；SO 行必须命中） | 三条用例全绿；旧报告能复现差异；`unknown_*` 行数变化被记录 |
| **P1** | 证据字段补齐：`source_row` / `row_hash` / `imported_at` / `waiting_observed` / `stage_dedup` 标记 / `confidence_basis` | `decide` 输出 schema v2 + 报告模板 | 检查清单 §5.3 第 2/3/6/7 项通过 |
| **P2** | 补货建议行可提交判断：新增 `ACCEPT` / `REJECT` / `NEED_EVIDENCE` / `ADJUST_PERIOD`；`row_id` 同时支持 baseline 行与 recommendation 行 | 提案 schema v2 + UI 三个按钮 | 能对建议行"同意/改量/报事件"，且 `ACCEPT` 可查 |
| **P3** | 身份换成 EN 登录（OIDC），自批按 `sub` 判断；高风险二级批准（阈值待业务定） | 认证改造 + 审计表 append-only + `prev_hash` | 两个不同账号无法互相顶替；改历史记录会被拒绝 |
| **P4** | 闭环评估 v1：双轨保存"系统建议值 / 最终执行值"，出 FVA + override 分层报表 + DM 检验（block bootstrap） | 评估脚本 + 一期报表 | 能回答"人工调整让误差变大还是变小"，且带样本量与置信区间 |
| **P5** | 证据节点补生产/WO、DN（复用 `EN_API/fulfillment_query.py` 与 `item_shipment_status.py`，不重写查询） | 只读适配器 + UI 节点从"未接入"变"实时/旧" | 任一 SKU 的 SO → WO → DN 能串起来，数量守恒可核 |
| **P6** | 预测覆盖率回测：p90 校准（PIT/覆盖率曲线），决定 q95 还是 p90 作为默认服务档 | 回测报告 + 决策记录 | 覆盖率在 [0.85, 0.95] 内或有明确偏差解释；`decide` 的 `quantile_basis` 可引用该报告 |
| **P7** | 血缘登记：`pack → rebuild → decide` 的 OpenLineage 事件（或轻量 manifest） | 事件/清单 + 一个可视化页面 | 能从一个建议行反查到它消费的每一个文件版本 |

**建议顺序的理由**：P0 之前不接新数据源 —— 因为 B2 会让"新接的 SO"看起来接上了其实可能恒为 0，
先修键再扩源，否则会积累更多"假证据"。

---

## 7. 未核实与边界

| 项 | 状态 |
|---|---|
| Tracking signal 阈值 \|TS\|>4 | **【未核实】** 行业经验规则，非本项目批准门槛 |
| p90 ≈ "90% 服务水平" | **【未核实】** 累计需求分位 ≠ fill rate（D39 §3 已明确）；需 P6 回测 |
| 观测性成对比较的因果性 | **【推断】** 有选择偏差；严格因果归因需设计 ③（业务授权） |
| 各阶段去重后的"真实可发" | **【未核实】** 未接 `supply_netting.net_all` 的批次门禁，当前按仓前缀汇总 |
| CG 是否可跨分公司 | **【事实】** 业务口径为"不可回拨"（11-13 UX 简报），代码注释仍写"可调拨" —— 需产品确认后统一 |
| OpenLineage 在纯 pandas 脚本下的接入成本 | **【推断】** 需自写 extractor，估 1–2 天，未实测 |
| 样本量示例（3,000 SKU×周） | **【示例】** 仅演示算法，不含本项目真实参数 |

## 8. 主要来源

- 内部（**事实**）：
  `supply_copilot/decide.py`、`recommend.py`、`refresh.py`、`live_rules.py`、`README.md`；
  `demand_collaboration/recommendation.py`、`so_evidence.py`、`live_stock.py`、`core.py`、`web.py`、`static/index.html`；
  `supply_chain_visibility/AGENT_HANDOFF.md`；
  `docs/research/supply-chain/2026-10-20/claude/control/{PROJECT_ROADMAP,DECISIONS,INVENTORY_EVALUATION}.md`；
  `docs/solutions/workflow-issues/{supply-sku-segmentation-and-stockout-evidence,erpnext-so-closed-unshipped-and-unstarted-work-orders}.md`；
  `docs/solutions/tooling-decisions/frepple-evaluation-and-borrow-logic.md`；
  本地审计 `D:/Work/fzh-order-store/analysis/{USNJ_SO_CHAIN_REVIEW,WAITING_SO_PIPELINE_REVIEW,SYSTEM_ARCHITECTURE_DESIGN,USNJ_WORKBENCH_UX_DESIGN_BRIEF,SUPPLY_COPILOT_RELEASE_BRIEF}_20261113.md`（不入库）。
- 外部（**事实**）：
  - FVA：[SAS 白皮书](https://www.sas.com/content/dam/SAS/en_us/doc/whitepaper1/forecast-value-added-analysis-106186.pdf)、[ISF 2019](https://isf.forecasters.org/wp-content/uploads/gravity_forms/2-dd30f7ae09136fa695c552259bdb3f99/2019/07/Gilliland_Michael_ISF2019.pdf)
  - Override 研究综述：[Forecast value added in demand planning (IJF, 2024)](https://www.sciencedirect.com/science/article/pii/S0169207024000736)
  - 成对显著性：[Diebold & Mariano 1995](https://doi.org/10.1080/07350015.1995.10524599)
  - 回测：[StatsForecast CV](https://nixtlaverse.nixtla.io/statsforecast/docs/tutorials/crossvalidation.html)、[sktime evaluate](https://www.sktime.net/docs/api-reference/sktimeforecastingmodel-evaluationevaluate)、[Darts](https://unit8co.github.io/darts/)
  - 计划器：[frePPLe（MIT）](https://github.com/frePPLe/frepple)
  - 血缘：[OpenLineage](https://openlineage.io/docs/)、[Marquez](https://github.com/MarquezProject/marquez)
  - 实验管理：[MLflow Evaluation](https://mlflow.org/docs/latest/ml/evaluation/)
  - 服务指标：[Sobel 2004](https://pubsonline.informs.org/doi/pdf/10.1287/msom.1030.0027)、[MIT 15.763](https://ocw.mit.edu/courses/15-763j-manufacturing-system-and-supply-chain-design-spring-2005/e1800430fdccaf618b22bd551fc00fac_summary.pdf)
