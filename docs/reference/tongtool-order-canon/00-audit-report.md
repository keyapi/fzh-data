---
okf: v0.1
type: Reference
title: 通途订单规则库 · 全局审计报告（源清单 / 规则对照 / 冲突 / 缺口）
description: 并行盘点旧 Colab+Google Sheet、EN 生产源码、本地成本引擎、文档与 PR 决策史；按主题对照三层口径并给出一致性与证据；登记 15 条冲突（3 条严重）与 12 项缺口/未证实
date: 2026-11-06
module: tongtool_order_cost
tags: [tongtool, order, audit, conflict, evidence, canon]
---

# 通途订单规则库 · 全局审计报告

> 本文只做盘点和判定，不改业务代码、不写 GS/EN、不提交 PR。
> 配套方案：[01-proposed-structure.md](01-proposed-structure.md)。

## 0. 摘要

- **四路并行**：旧 Colab+GS、EN 生产源码、本地引擎、文档与 PR 决策史。
- **规则主题 24 个**，其中 **2 个三层口径完全一致**、**9 个部分一致**、**6 个存在实质冲突**、**7 个仅一方有定义**。
- **冲突 15 条**，按严重度：**严重 3 条**、高 6 条、中 5 条、低 1 条。
- **缺口/未证实 12 项**，其中 2 项已由 2026-11-06 生产库只读元数据证实，1 项需财务拍板。

**最严重的 3 条**：

1. **拆单多包裹系数在通途订单同步链路恒为 1**（`order_sync.py:3033`；子表无 `warehouse_name` 字段），只在 Cost Review/Excel 链路生效。文档却写「✅ 在用」。
2. **同一 SKU 后缀在五条链路得到五种成本**：`order_sync` 成品 `-FOAM` 判错列且漏乘系数、不 clamp；`cost_review` 用 `max(0)` 且乘系数；`doc_event` 完全不认后缀；`delivery_note_filling_cost` 不认后缀；本地引擎按文档矩阵实现并把负值判为阻断。
3. **FBA 至少三套判据**：仓库分类含 `FBA`（订单同步/BOM 报表）、客户名含 FBA 关键字（送货单报表）、`order_type=FBA` + 渠道/账号短路（历史尾程），同一订单可能在不同链路被当成不同履约类型。

## 1. 范围、方法与证据等级

### 1.1 范围

「通途订单」从**进入计算**到**写回成本**的全链路口径：

- 订单身份：原始订单、作废原单、拆分子单、FBA、退货/补发。
- 分组合并：什么算同一件成品、件数、产品归属、歧义阻断。
- 计价：皮壳、头程、目的地加工、绍兴侧加成、后缀特例、自采购、套件。
- 旁路：尾程、有效重量、非商品配件、白名单、别名登记。
- 特殊规则 1.7.0、SKU 改名、月度写回。

**非目标**：售价/退款/税费口径；赛狐打单；EN 工单/生产；Colab 迁移实施。

### 1.2 方法

| 路 | 对象 | 方式 |
|---|---|---|
| 1 | 旧 Colab + Google Sheet | 只读文档逐页；notebook/表 id 取自文档，不联网执行 |
| 2 | EN 生产源码 | SSH 只读 `grep -n` / `sed -n`；2026-11-06 另做生产库 `information_schema` 只读元数据查询（仅确认列/字段是否存在）；**未执行 bench、未查业务数据、未调用 API** |
| 3 | 本地引擎 `tongtu_cost_engine` | 只读源码；未运行 |
| 4 | 文档、`docs/solutions`、PR | `grep`、`gh pr list/view`、`git log` |

### 1.3 证据等级

| 级 | 含义 |
|---|---|
| **A** | 本次直接读到的源码/数据（附文件:行号） |
| **B** | 文档中的代码引用，本次未回源 |
| **C** | 文档结论或转述，未见原始证据 |
| **D** | 未证实（标注「未证实」） |

> **行号时效**：EN 行号为 **2026-11-06** 观测。已有漂移实证：`08-special-cases.md:35` 引自采购 `bom_cost_list_v2.py:1496-1530`，实际在 **`:1725-1734`**（本次 A 级复核）。因此行号只能进「实现映射」，不能进规范正文。

## 2. 源清单

### 2.1 文档（worktree 内）

| 路径 | 角色 | 本次用途 |
|---|---|---|
| `AGENTS.md` | 项目总纲/路由 | 模块边界、纪律 |
| `CONCEPTS.md` | 共享术语 | `Tongtool Cost Review` 与 1.7.0 的区分（`:299-310`） |
| `tongtool_order_cost/AGENT_HANDOFF.md` | 模块交接 | 管道、6 列去重、后缀结论 |
| `tongtool_order_cost/docs/reference/cost-engine-spec/` | 38 文件成本规格 bundle | 规则与冲突主源 |
| `.../cost-engine-spec/04-cost-decision-tables.md` | 决策表 | 目的地×发货方式 |
| `.../08-special-cases.md` | 特例清单 | 后缀/自采购/拆单/清零 |
| `.../09-known-issues-register.md` | 问题登记册 | A1–A7/B/C/D/E |
| `.../30-design-merge-split-no-double-count.md` | 合并设计稿 | 分组/件数/断言 |
| `.../32`–`37` | Phase 2–4 实现规格 | 本地引擎口径 |
| `.../38-en-line-identity-and-single-item-suffix.md` | 行级身份/后缀 | 最新口径，含 202608 A/B |
| `.../colab-engine-cell-by-cell.md` | Colab 逐 cell | 旧引擎证据 |
| `.../en-branching-and-warehouse-config.md` | EN 39 个分流点/仓库配置 | EN 内部漂移 |
| `tongtool_order_cost/docs/reference/en-shaoxing-shipment-cost-logic-spec.md` | 绍兴成本核实 | 两套绍兴成本定义 |
| `tongtool_order_cost/docs/reference/colab-cost-engine-spec.md` | Colab 总规格 | 旧口径 |
| `.../monthly-tail-cost-pipeline.md`、`rule-columns.md`、`sku-remap.md` | 尾程/1.7.0/改名 | 旁路口径 |
| `docs/solutions/*`（6 篇 `module: tongtool_order_cost`） | 经验库 | 决策史与踩坑 |

`docs/solutions/` 六篇：`architecture-patterns/tongtu-cost-engine-local-migration.md`、`architecture-patterns/ustx-cost-caliber-comparison.md`、`integration-issues/tongtu-en-item-mapping-and-gsheet-source-fix.md`、`integration-issues/tongtu-fba-alias-normalization-registration.md`、`workflow-issues/tongtool-sku-rename-gsheet-remap.md`、`workflow-issues/tongtu-order-universe-invalid-split-fba.md`。

### 2.2 EN 生产源码（`/home/frappe/frappe-bench/apps/`）

| 别名 | 绝对路径 | 行数 | 角色 |
|---|---|---:|---|
| **OS** | `tongtool_integration/tongtool_integration/sync/order_sync.py` | 5,218 | 通途订单同步：四成本列、绍兴发货成本、头程、尾程 |
| **CR** | `.../doctype/tongtool_cost_review/tongtool_cost_review.py` | — | Cost Review 导入：按后缀重算 |
| **EX** | `.../doctype/excel_tongtool_order/excel_tongtool_order.py` | — | 订单 Excel 导入/FBA 清零 |
| **PKG** | `.../sync/package_sync.py` | — | 包裹费分摊 |
| **BOM** | `work_order_task/work_order_task/work_order_task/report/bom_cost_list_v2/bom_cost_list_v2.py` | — | 绍兴总成本、自采购、目的地加工 |
| **DN** | `delivery_plan/delivery_plan/doc_event.py` | — | 销售出库写 `custom_valuation_rate` |
| **DNF** | `work_order_task/.../report/delivery_note_filling_cost/delivery_note_filling_cost.py` | — | 送货单填充成本 |
| **SGP** | `tongtool_integration/.../report/sales_gross_profit/sales_gross_profit.py` | — | 销售毛利 |

### 2.3 本地引擎（worktree 内）

| 文件 | 行数 | 角色 |
|---|---:|---|
| `tongtool_order_cost/tongtool_order_cost/tongtu_cost_engine/domain/split_merge.py` | 2,375 | 订单全集、分组、合并、行级身份、锚定 |
| `.../domain/bom_cost.py` | 1,195 | BOM 成本、后缀矩阵、套件 |
| `.../domain/phase36_fill.py` | 632 | 166/95/78 三表填充、作废原单、GS-ready |
| `.../domain/fba_shadow.py` | 979 | FBA 影子、跨月桥接、白名单 |
| `.../domain/run_package.py` / `fba_run_package.py` | 509 / 632 | 写回 run 包/canary |
| `.../domain/writeback_rehearsal.py` | 895 | 写回演练 |
| `tongtool_order_cost/engine_170.py` | — | 特殊规则 1.7.0 本地引擎（**不是** Cost Review） |

### 2.4 旧 Colab / Google Sheet

| 对象 | 标识 | 来源 |
|---|---|---|
| Colab notebook | `1T5hZYvnJhS8xzORb3tuYRoXXWn9uSzNl` | `colab-cost-engine-spec.md:7,14`；`cost-engine-spec/colab-engine-cell-by-cell.md:20` |
| 源成本表 | `15CjWsxoYt8fKtJaJIAdT-G_l6T6-2Np8hWtdh82vysk` | `cost-engine-spec/27-gsheet-source-root-cause.md:19` |
| 订单工作簿 | `通途订单202606` / `通途订单202606-特殊规则` | `AGENT_HANDOFF.md:68` |
| 1.7.0 规则 ws | `和财务部共享` → `Jeck特殊规则-订单改销售额成本` | `AGENT_HANDOFF.md:57` |
| 成本源 ws | `订单发货仓库对应成本来源`(47)、`import皮壳成本`(902)、`importBOMCostList`(3693)、`测算 美中USTX二次加工成本`(621，未启用) | `cost-engine-spec/03-data-sources.md:35-47` |
| 账期/写回 ws | `{月}年{月}订单`(raw)、`写回…`、`写回…FBA订单`、`写回…FBA订单和非FBA订单` | `03-data-sources.md:22-27` |

### 2.5 Skill 与 PR

- `.agents/skills/tongtool-order-cost/SKILL.md`：1.7.0 审计、GS SKU 改名、月度盈利审计。
- `.agents/skills/tongtool-order-shipping/SKILL.md`：订单→每包裹一行承运商导入 + 背贴。
- `.agents/skills/tongtool-api/SKILL.md`：ERP2 API/MCP。
- PR：#165（1.7.0 本地引擎，MERGED）、#171（FBA 尾程负数，MERGED）、#174（SKU 改名，MERGED）、#229（月度 ws 上传，MERGED）、#280（旧 Colab 档案，OPEN）、#294（订单侧输入+月度审计，OPEN）、#295（USTX 三方案，OPEN）、#307（报税透视，OPEN）。
- 当前分支 `keyapi/tongtool-knowledge-canon` **无对应 PR**。

## 3. 规则主题对照表

> 「一致?」判定：✅ 三层同义 / ◐ 部分一致或仅两方有定义 / ❌ 实质冲突 / ➖ 仅一方有定义。
> 旧 Colab 列中的 `cell_*` 均来自 `colab-engine-cell-by-cell.md`。

| # | 主题 | 旧 Colab / GS | EN 口径 | 本地引擎口径 | 一致? | 证据 |
|---|---|---|---|---|---|---|
| T01 | 订单全集 | raw `{月}订单` 与写回表；文档无 `invalid` 概念 | `Tongtool Order.invalid`；下游按 `invalid=0` 过滤 | `order_flags.invalid=1` → `aux_rows`，只校验不进计算 | ◐ | OS:305/399/479/560/997/1122；SGP:60；SM:659-672,690,780-783 |
| T02 | 原始订单/子单识别 | 分组用 `订单号_公共部分 + 平台SKU_统一`；剥尾部数字 | 本次未在 EN 源码/Doctype JSON 找到 `order_common`；`isDeliverGoods=="1"` **取反**写 `is_deliver_good=0`（1=未发货=被拆出）；FBA 恒 1 | `order_common_part` **只剥 `[_-]\d{1,2}$`**，`OS-474530280` 不剥；按 `order_common+平台SKU+product` 分组 | ◐ | `18:57-78`；OS:686,777；`ustx_cost_compare.py:819-830`；SM:1133-1256 |
| T03 | 拆单组合并 | 合并行；聚合 `first`；触发靠产品名含「包裹」 | **无合并**：逐行独立计价 | 合并成一件；载体行计价；组件行 0 | ➖ | `30:19-44`；SM:1056-1112,1133-1256 |
| T04 | 件数 | 未明确；多件/多包裹混 | 按行 `quantity` | 合并组件数 = Σ皮壳行数量 | ➖ | `30:39`；SM `_count_pieces`:1056-1112 |
| T05 | 产品归属 | `品类尺寸面料编码` + `first` | 行级 `erp_item_code`（EN 订单行实际物料） | EN 行身份优先；组内 Cover 让位填充行；**皮壳别名唯一时反向由皮壳定产品** | ❌ 文档只写单向 | `38:26-56`；SM:715-742,849-888；`AGENT_HANDOFF.md:145` |
| T06 | 单独卖 COVER/FOAM/PPCOTTON | Colab 无行级身份；后缀特例仅在 EN | 见 T07 矩阵；**仅非 FBA**；PPCOTTON 仅在「皮壳」档 | 按矩阵清零；负值 → `negative_cost` 阻断 | ◐ | OS:2941-3003；CR:1058-1183；BC:441-458 |
| T07 | 后缀 × 发货方式矩阵 | — | 皮壳/成品/半成品三档，各档 COVER/FOAM/PPCOTTON 分支不同 | 与文档 38 矩阵一致；合并组不套后缀 | ❌ 五链不一致（见 C2） | OS:2936-3017；CR:1058-1183；DN:1662-1700；DNF:无；BC:441-458 |
| T08 | 「绍兴总成本」vs「绍兴发货成本」 | 三段相加的旧设计；`sx_cost_all` 报表明细 | 报表 `sx_cost_all`=皮壳+绍兴包装成品（半成品只剔除不加）；订单 `sx_shipping_cost`=按发货方式三档；FBA 忽略发货方式 | 按 method 取：皮壳 0、半成品 `cost_sxbzbcp`、成品 `cost_sxbzcp`、FBA `sx_cost_all−皮壳` | ◐ 文档已解释，命名仍误导 | BOM:1715-1739；OS:2919-3013；`en-shaoxing-shipment-cost-logic-spec.md:19,31-93`；BC:428-439 |
| T09 | 头程 | 价目表 + GS；`HEAD-SX→0`；1:2:4 补缺 | 三列头程按发货方式三选一；`-COVER` 皮壳头程；`-FOAM` 差额；FBA 成品头程 | 皮壳/半成品/成品 + 差额；负值阻断 | ◐ | OS:2913-2917,2958,2978,3003,3013；BC:395-410 |
| T10 | 目的地加工成本 | 借绍兴包装成品成本 | 目的地包装成品 BOM `total_cost`；FBA=0；海外仓复用 USTX | `usnj/ustx/pl_valuation_rate`；FBA=0 | ✅ | BOM:541-567；OS:2911；BC:414-426 |
| T11 | 自采购 | 成品+cost_fg≠0+cost_sxbzcp=0+BOM 自引用 → 总成本=皮壳 | 仅在 BOM 报表 `sx_cost_all`；OS/CR 通过 `bom_row` 继承；DN 文档称缺 | 未单独实现；依赖 BOM 快照 | ◐ | BOM:1725-1734（**非文档写的 1496**）；`08:29-36`；`09:A3` |
| T12 | 套件 TJ# | notebook 无套件；五件套按子件 Σ | OS/CR/SGP **grep 无 bundle/套件** | Product Bundle 展开；子件 method 全一致才派生；TJ# 与子件不得双计 | ➖ EN 订单链无实现 | `33:45-51`；BC:168-229；`35:23,33`；agent 复核 OS/CR/SGP grep=0 |
| T13 | FBA | FBA 表；按站点映射仓库；`index.repeat`；运费 0；无视后缀 | 仓库分类含 FBA → `sx_shipping_cost=sx_cost_all`、`first_freight=成品头程`；加工照算，Excel 再清零 | 绕过全部后缀；FBA shadow 独立口径；`绍兴二次=sx_cost_all−皮壳` | ❌ 判据三套 | OS:2921-2931；CR:1045-1056；DN:1652；DNF:327/381/414；SGP:291-300；FBA:23-32 |
| T14 | 拆单系数 | 无（Colab） | 设计：`Item Customer Detail.custom_split_package_cost_factor`，三层匹配，`<=0→1`；**订单同步子表无 warehouse_name → 恒 1** | 未实现 | ❌ 文档说在用 | OS:3019-3148（`:3033` 短路、`:3136` 取子表仓库）；`tongtool_order_item.json` 无 `warehouse_name`；`tongtool_cost_review_item.json:55` 有 |
| T15 | 尾程 | 物流商运费>历史预估>通途运费；FBA=0 | OS：上传>carrier>设置项，跨项兜底被注释；CR：carrier>hist>tt；SGP：`needs_last_leg=0` 清零 | 未纳入本地四列（只写成本，不含尾程） | ❌ 三套优先级 | OS:4687-4758（`:4744-4756` 注释）；CR:1748-1772；SGP:295 |
| T16 | 有效重量/数字后缀 | 无 | `-cover1..5/-foam1..5` 改历史预估计费重量；1–5 公式相同；`-COVER6` 落通用分支 | 未实现 | ➖ | OS:4484-4558；CR:738-810 |
| T17 | 非商品/白名单 | 品类白名单清零/灰区 fillna(0) | 无统一白名单；`delivery_note` 有 FBA 客户关键字 | `BUTTONKIT*/PP<n>LB/DLZYFX001/COTTON-EU` → 四列 0；FBA 未登记 SKU 白名单仅建议 | ◐ 三套概念 | `08:86-103`；`33:44`；`35:50-68` |
| T18 | 特殊规则 1.7.0 | 6 列去重；系数/参考值；FBA 负数写运费 | **EN 无实现** | `engine_170.py` 本地实现 | ➖ | `CONCEPTS.md:305-308`；`AGENT_HANDOFF.md:82-91`；`rule-columns.md` |
| T19 | 作废原单写回 | 旧写回表含原单 | `invalid=1` | 保留行+销售，清空成本与系数轨，标 `invalid_original`，旧值进备份 | ➖ | `37:15-22`；P36 |
| T20 | 时点/BOM 版本 | 快照 2026-09-03；名称误导 | 月末版本；BOM 会变更 | run 包锁 `month_end` + `bundle_version` | ✅（机制） | `01:55-70`；`34:15-26` |
| T21 | 6 列去重/规则匹配 | `运营人员+发货区域+通途SKU+渠道账号不含国家+渠道账号+发货仓分类` | 无 | 1.7.0 引擎使用 | ➖ | `02:64-75`；`engine_170.py:33-40` |
| T22 | 仓库配置 | `订单发货仓库对应成本来源` 8 列 | `Tongtu Shipping Warehouse` 42 行（文档另处写 40） | `branch_map`/`item_group_branch.tsv` | ◐ 行数口径不一 | `en-shaoxing...:123`；`en-branching...:152`；OS:2193-2242 |
| T23 | 别名登记/改名 | 订单旧名→井新名；规则表不改 | `Item Customer Detail.ref_code` 精确匹配；Cost Review 可按 `-Cover` 补登 | `EnResolver` 别名归一化；歧义阻断 | ◐ | `sku-remap.md`；OS:1330-1352；CR:575-735；SM:321-333 |
| T24 | 退货/补发 | 无退货成本规则 | 补发单 `-M\d+$` + OSTK/WAYFAIR → `needs_last_leg=1`；退货仓仅仓库名 | 未实现退货 | ❌ 缺口 | CR:37-55；`monthly-profitability-audit.md:98-100` |

## 4. 冲突清单（按严重度）

> 每条给：现象 → 证据 → 影响 → 判定。「可判定」= 有明确证据可定谁对；「需业务」= 口径归属需财务/用户拍板。

| ID | 严重度 | 一句话 | 判定类型 |
|---|---|---|---|
| C1 | 严重 | 拆单系数在订单同步恒为 1 | 可判定（代码 + DB）；修复方式需产品 |
| C2 | 严重 | 后缀在五条链路五种成本 | 可判定；以谁为准需业务 |
| C3 | 严重 | FBA 三套判据 | 可判定；统一判据需业务 |
| C4 | 高 | 头程三列系数文档/代码相反 | 可判定（OS 缺陷或文档过期） |
| C5 | 高 | `doc_event` 注释声称支持后缀 | 可判定（注释错误） |
| C6 | 高 | 两套「绍兴成本」同名不同义 | 可判定；命名需固化 |
| C7 | 高 | 产品归属文档只写单向 | 可判定（文档滞后） |
| C8 | 高 | 套件在 EN 订单链无实现 | 可判定（口径归属） |
| C9 | 高 | 退货无成本口径 | 需业务 |
| C10 | 中 | 双 SSOT 声明 + 数字不一致 | 可判定；一项未证实 |
| C11 | 中 | 行号锚点漂移 | 可判定（结构性） |
| C12 | 中 | 拆单系数字段位置写错 | 可判定（DB 已证实） |
| C13 | 中 | 尾程优先级三套 | 可判定；利润口径需业务确认 |
| C14 | 中 | 本地负成本阻断 vs EN 可负 | 可判定；政策需业务 |
| C15 | 低 | 1:2:4 是否触发 | 未证实 |

### 严重

#### C1 拆单系数在订单同步链路恒为 1

- **现象**：`_fill_split_package_cost_factor_for_order` 用 `it.warehouse_name` 取仓库（OS:3136），但 `Tongtool Order Item` 的 JSON **没有 `warehouse_name` 字段**（本次 grep A 级）；`_get_split_factor_for_item` 在 `warehouse_name` 为空时直接 `return 1`（OS:3033）。而 `Tongtool Cost Review Item` 有该字段（`tongtool_cost_review_item.json:55`）。
- **证据**：OS:3019-3148；`tongtool_order_item.json` 字段清单（72–321）无 `warehouse_name`；CR 路径可正常取到。
- **影响**：定时订单同步的「拆单多包裹系数」**从未生效**；Cost Review/Excel 路径生效。两条链路同一订单成本不同。
- **判定**：**可判定（代码事实 + 2026-11-06 生产库只读元数据证实）**。是否为 bug 需产品决定：给 Order Item 加字段/从订单头带仓库，或明确「订单同步不乘系数」。
- **DB 证实（A 级，2026-11-06）**：`tabTongtool Order Item` **不存在** `warehouse_name` 列，也无同名 Custom Field；对照 `tabTongtool Cost Review Item.warehouse_name` 存在。

#### C2 同一 SKU 后缀在五条链路得到五种成本

- **现象**：

| 链路 | `-FOAM`（成品档） | `-COVER` | `-PPCOTTON` |
|---|---|---|---|
| OS（订单同步） | 判 `cost_sxbzbcp_field` 却读 `cost_sxbzcp_field`；**不乘 factor**；**不 clamp**（可负） | 皮壳成本+皮壳头程；加工 0 | 仅皮壳档：发货/头程 0；成品/半成品档落普通分支 |
| CR（Cost Review） | 读 `cost_sxbzcp_field`；乘 factor；`max(0, …)` | 同 OS；乘 factor | 仅皮壳档零；其余普通 |
| DN（销售出库） | **不认后缀**，按发货方式普通分支 | 同左 | 同左 |
| DNF（送货单） | **不认后缀** | 同左 | 同左 |
| 本地引擎 | 皮壳=0、绍兴二次=`cost_sxbzcp/bcp`、头程=总额−皮壳；负值 → `negative_cost` 阻断 | sx/processing=0 | 仅 method=皮壳：三项 0 |

- **证据**：OS:2960-2985（成品 `-FOAM` 分支 2972-2978）；CR:1090-1132（`max(0)` 在 1107）；DN:1662-1700（注释明写「不区分 SKU 后缀」）；DNF 全文件无 `-COVER/-FOAM/-PPCOTTON` 分支；BC:441-458。
- **影响**：同一通途订单在「订单同步 → 毛利报表 → 销售出库 → 送货单 → 本地引擎」可得到五个不同成本；带后缀的 FBA 件更绕过全部特例。
- **判定**：**可判定（代码事实）**；「以哪条链路为准」**需业务拍板**。建议以 Cost Review/本地矩阵为规范，逐条修 OS/DN/DNF。

#### C3 FBA 至少三套判据

- **现象**：
  1. 仓库分类含 `FBA`：OS:2921、BOM 报表、CR:1045。
  2. 客户名/客户码含 FBA 关键字：DNF `_contains_fba_keyword`（:327，用于 :381/:414/:588/:1063/:1262）。
  3. `order_type=FBA` + 渠道/账号/仓库名短路：OS:777、OS:4570-4600（历史尾程）。
  4. `needs_last_leg` 另有一套：SGP:291-300 只看 FBA/多渠道/平台/TikTok；CR:37-55 还看云仓/补发。
- **影响**：同一订单可能在订单同步里是 FBA（仓库维度）、在送货单里不是（客户维度）、在毛利里尾程又被清零（渠道维度）。
- **判定**：**可判定（代码事实）**；统一判据**需业务拍板**（建议以 `Tongtu Shipping Warehouse.warehouse_classification` 为唯一权威）。

### 高

#### C4 头程三列是否乘拆单系数：文档与代码相反

- 文档：`08-special-cases.md:43` 与 `en-branching-and-warehouse-config.md:72` 称「绍兴发货成本与三列头程统一 × 系数」。
- 代码：OS:2913-2917 三列头程 **只 × quantity，不 × factor**（注释仍写「× 拆分多包裹成本系数」）；CR:1195-1208 全部 × factor。
- **判定**：可判定；**代码与自身注释也不一致**，优先判定为 OS 缺陷或文档过期。

#### C5 `doc_event` 注释声称支持后缀，代码不认

- `doc_event.py:1530` docstring 写「支持 SKU 后缀特殊处理：-PPCOTTON / -COVER / -FOAM」。
- 实际 `:1662-1700` 明写「不区分 SKU 后缀，统一使用 else 分支逻辑」。
- **判定**：可判定（注释错误）。`09:A3` 的「doc_event 不认后缀」正确，docstring 应删。

#### C6 两套「绍兴成本」同名不同义，文档已解释但未固化

- 报表列 `sx_cost_all` = 皮壳 + 绍兴包装成品成本；半成品只被剔除、**从不加入**（BOM:1715-1739）。
- 订单字段 `sx_shipping_cost` = 按发货方式三档；FBA 忽略发货方式（OS:2919-3013）。
- **影响**：任何新实现若只看字段名，必选错。
- **判定**：可判定；需在规范中把「报表列」与「订单字段」拆成两个独立术语，禁止再用「绍兴总成本」一名指两物。

#### C7 合并组产品归属：文档只写单向，代码已双向

- `38:43-56` 写两条规则（Cover 让位填充行；皮壳别名唯一时反向覆盖）。
- `AGENT_HANDOFF.md:145` 只写「Cover 行不采信自身 EN 物料号，由填充行锚定」，**缺反向 override**。
- 代码：`_cover_product_precedence`（SM:849-888）实现反向。
- **判定**：可判定（文档滞后）。反向规则是用户 2026-11-06 明确口径，应进规范。

#### C8 套件在 EN 订单成本链路没有实现

- OS/CR/SGP 中 `bundle`/`套件` **grep 为 0**（子代理 A 级复核）。
- 本地引擎已实现 TJ# 展开、method 一致性、双计阻断（BC:168-229；`33:45-51`）。
- **判定**：可判定；这是「本地新增口径」，不能写成「EN 已有」。

#### C9 退货无成本口径

- 文档只出现仓库名「…-退货产品仓」（`en-branching...:156-158`；`monthly-profitability-audit.md:98-100`），**无退货成本规则**。
- 本地引擎有 `invalid`/退款 aux 校验，但**无退货计价**。
- **判定**：缺口；需业务定义（退货是否冲成本、按原单还是退货仓）。

### 中

#### C10 两处「单一事实源」声明 + 同一事实多个数字

- `cost-engine-spec/01:13` 与 `index.md:10` 自称成本口径唯一事实源；本 bundle 若成立会出现第二个。
- 同源冲突实例：
  - 仓库配置 **42 行**（`en-shaoxing...:123`）vs **40 行**（`en-branching...:152`）。
  - 直连覆盖 **99.9%（4367/4372）**（`AGENT_HANDOFF.md:128`）vs **唯一 4369**（`20:41-45`）。
  - 202608 皮壳 **547,909.37 / 总成本 2,924,215.75**（`38:74-79`）vs Phase3 记录 **571,328.45**（`cost-engine-spec/log.md:226-245`）——行集/范围未声明，**无法对账**。
- **判定**：可判定（文档治理）；第三项**未证实**（需同口径重跑）。

#### C11 行号锚点大面积漂移

- 自采购：文档 `bom_cost_list_v2.py:1496-1530`，实际 `:1725-1734`（本次 A 级）。
- 拆单系数：文档 `order_sync.py:2907-2917,3120`，实际函数起点 `:3019`、写值 `:3136`。
- **判定**：结构性缺陷；行号不能作为规范的稳定键，只能进「实现映射」并标注观测日。

#### C12 拆单系数字段位置文档写错

- `08-special-cases.md:42` 写 `Item.custom_split_package_cost_factor`。
- 代码读 `Item Customer Detail.custom_split_package_cost_factor`（OS:3066-3096）。
- **判定**：**可判定（文档错 + 2026-11-06 生产库只读元数据证实）**。`tabItem` **不存在** `custom_split_package_cost_factor`；全库仅在 `tabItem Customer Detail.custom_split_package_cost_factor`。

#### C13 尾程优先级三套

- OS：上传值 > carrier > 设置项，跨项兜底被注释（:4744-4756）。
- CR：carrier > hist > tt（:1748-1772）。
- SGP：`needs_last_leg=0` 时直接 0（:295）。
- **判定**：可判定；需明确「哪条是利润口径」。

#### C14 本地引擎对负成本的处理与 EN 不同

- EN OS：`-FOAM` 头程差额可为负，照写。
- 本地：任一成本 < 0 → `negative_cost` 阻断（BC:457-458）。
- **判定**：可判定；需决定「负头程是业务允许还是数据错误」。

### 低

#### C15 1:2:4 倍数口径未证实是否触发

- `cell_049 fill_shipping_cost` docstring 有「半成品=2×皮壳，成品=2×半成品=4×皮壳」（`colab-engine-cell-by-cell.md:223-226`）。
- 但该函数**只更新已存在的发货方式行、不新建**；实测回放无变化（`09:E2`；`17:§5`）。
- **判定**：未证实；不应写进规范正文，只能进证据页。

## 5. 缺口与未证实

| # | 项 | 现状 | 需要什么 |
|---|---|---|---|
| G1 | 站点 DB 是否有 `Tongtool Order Item.warehouse_name` Custom Field | **已证实（2026-11-06 DB 只读）**：无该列、无同名 Custom Field | 无需再查；C1 结论坐实 |
| G2 | `Item` 是否有 `custom_split_package_cost_factor` | **已证实（2026-11-06 DB 只读）**：`tabItem` 无；仅在 `tabItem Customer Detail` | 无需再查；C12 结论坐实 |
| G3 | 退货/退款成本口径 | 文档与代码均无 | 业务定义 |
| G4 | 套件在 EN 订单成本的权威实现 | EN 无 | 明确「本地引擎即权威」或补 EN |
| G5 | 带后缀的 FBA 订单实际笔数 | 未统计 | 只读订单统计 |
| G6 | 三处 EN 口径漂移的月度金额 | 未量化 | 用订单快照重算 |
| G7 | 202608 皮壳 547,909 vs 571,328 差异 | 行集未声明 | 同口径重跑并给 manifest |
| G8 | 1:2:4 实际触发面 | 未证实 | 回放带缺失发货方式档的月份 |
| G9 | `HWC` 关键字设计意图 | 生产无对应价格表 | 原开发者确认 |
| G10 | 海外仓→USTX/USFBA 映射是否逐单成立 | 仅配置反查 | 抽样订单核对 |
| G11 | `order_common` 在 EN 源码/Doctype JSON 未找到，本地全靠订单号剥后缀 | 已确认源码层 | 查库确认是否有同名 Custom Field；规范中注明「本地派生键」 |
| G12 | `isDeliverGoods` 取反的语义 | 代码注释确认 | 写进规范，防后来者再踩 |

## 6. 对规范化的直接结论

1. **能立即写进规范（证据充分、三层可对齐）**：订单全集与 `invalid=1` 用法、`order_common_part` 剥后缀铁律、目的地加工成本、后缀矩阵（以 CR/本地为准）、作废原单写回、月末 BOM 版本机制。
2. **必须先裁决再写规范**：C1（拆单系数范围）、C2（哪条链路为准）、C3（FBA 判据）、C6（两套绍兴成本命名）、C9（退货）。
3. **只能进「实现映射/证据」不能进规范**：所有 EN 行号、Colab cell 号、Codex 复核过程、月度金额。
4. **规范必须显式区分三层**：`EN 现状` / `本地引擎新增` / `旧 Colab 历史`。本次审计中多处「一致」其实是「文档把本地新增写成了 EN 已有」（C8），这是后续最容易复发的一类错误。
