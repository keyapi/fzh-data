---
okf: v0.1
type: Reference
title: Colab（截至 4.8）→ 本地引擎：已移植范围与 build-order-tabs 缺口
date: 2026-11-09
last_updated: 2026-11-10
category: documentation-gaps
module: tongtool_order_cost
problem_type: documentation_gap
component: tooling
severity: high
applies_when:
  - "准备停用 20250409 合并EN成本 Colab notebook"
  - "判断通途订单成本/拆单合并逻辑是否已完整本地化"
  - "需要知道本地引擎为什么仍依赖 Colab 生成的 166/95/78 列模板"
tags: [tongtu, colab, parity, build-order-tabs, split-merge]
---

## Context

`20250409 合并en成本 测算成本核算20250110 … .ipynb`（live 快照 `out/colab_live_20261104.ipynb`）截至步骤 4.8 仍是订单成本表的实际生产者；本地 `tongtu_cost_engine` 已移植大部分成本/拆单合并逻辑，但仍**往 Colab 生成的模板里填成本**。本页记录完整对照结论，避免误以为可以立即停用 Colab。

完整逐步骤矩阵：`tongtool_order_cost/docs/research/2026-11-09-colab-local-parity-audit.md`。

## Guidance（本学习沉淀的做法）

### 已移植/已替代

- 皮壳/绍兴二次/二次加工/头程：BOM + `wh_map`（4.3–4.5.1）。
- 拆单合并：`split_merge` 结构判据、TikTok 数字主体配对、件数/产品族/守恒（4.2.2/4.2.3 的通用部分）。
- 订单+成本合并（4.6）、78 列 merged shadow（4.8 的通用部分）。
- EN 行级 `erp_item_code` + `customer_items.ref_code` 替代 Colab 的产品名称解析（4.2/4.7.2）。

### 旧 self 表的展示合并规则：**不采用**（2026-11-10 重审）

旧 Colab 的 `包含包裹=TRUE` 且公共单号 ≥2 → 23 组合并；通用填充物在单皮壳组删除 17 行。行/键可复现到 202608 10,870/10,870，但**语义审计不通过**：

- 被删的通用填充物行有多行**行级售价非 0**，旧表只留 Cover 行，行级 `售价*汇率` 丢失：
  - 202608：9 组，Lost 售价 254.79 / `售价*汇率` **1,729.98**
  - 202609：7 组，Lost 售价 188.27 / `售价*汇率` **1,278.13**
- 23 组按公共单号合并，**未限制平台SKU/产品**，且对 `运费` 直接求和（共享包裹时会重复）。

因此：`self 166` 用本地成熟算法的**合并组视图**，不复刻旧 Colab 的展示合并/删除；行数差异按“旧表销售额 bug 修正”记录。旧表行键一致只是历史展示口径，不是业务规则。

### 仍需本地补/明确不移植

- **build-order-tabs（已补，2026-11-10）**：CLI `build-order-tabs --month` 已能本地重建
  self 166 / FBA 95 / merged 78（`docs/reference/build-order-tabs.md`）。两月对拍
  （vs 已写回 GS 的 `phase36/gs_ready`）：FBA 全 0 差异；self/merged 成本与数量 0 差异；
  差额只有旧表丢失的销售额（+1,729.97 / +1,276.64）与 202609 尾程补齐（+304,541.93）。
- 特殊订单删除（4.1.0.1）：`scripts/fetch_special_orders.py`；构建器默认读
  `raw_<月>_filtered.csv`。
- 汇率（4.1.0）：`scripts/fetch_fx_rates.py`；不能用 raw 的 `售价(人民币)/售价` 替代（GBP 不一致）。
- 仓库映射：`scripts/check_warehouse_map.py`；仓库成本来源：`scripts/fetch_warehouse_cost_sources.py`。
- 不移植：4.1.1/4.1.2（尾程分区/州名）、4.3.0.2.9（麻将×3）、4.5.2（无海外仓）、4.5.3/4.5.4/4.9（运营人员，非成本）。

### 关键数字（202608）

- raw 10,912 → 删除特殊订单后 10,910 → Phase1 合并明细 **10,819**（未过滤时演练为 10,821）。
- Colab self 表 10,870 行：保留组件行/合并展示行，**不是**合并明细；build 不能只 concat。
- 本地 build：self 10,819；FBA 95 列 1,966；merged 78 列 12,785。

## Why This Matters

- `build-order-tabs` 已能本地出三表，但 **GS 写回链路仍走 `fill-tables` + Colab 模板**；
  在切换写回之前，停用 Colab 仍会断掉订单表生产。
- 旧表行数（10,870）与新成熟组视图（10,819）不同，是因为旧表把组件行和合并展示行都留下了；
  新表用「合并组 1 行」并保留全部销售额/运费，不能再用旧行数做验收基准。

## When to Apply

- 评估/实施 Colab 退场；
- 新增月份订单表生产流程；
- 对拍本地与 Colab 的行数/销售额/四列成本/29 列。

## Examples

202608：raw 10,912 → 特殊订单 55 条（删除清单）→ 10,910；合并吸收 91 → build self 10,819；
FBA 1,966；merged 12,785。旧 self 10,870 / merged 12,836。
202609：raw 6,268 → 6,267；合并吸收 46 → build self 6,221；FBA 1,269；merged 7,490。
旧 self 6,246 / merged 7,515。

## Related

- 构建器说明：`tongtool_order_cost/docs/reference/build-order-tabs.md`
- 完整矩阵：`tongtool_order_cost/docs/research/2026-11-09-colab-local-parity-audit.md`
- 拆单合并成本修复：`docs/solutions/workflow-issues/tongtu-split-merge-writeback-cost-rules.md`
- 拆单类型与拆单前 SKU：`docs/solutions/conventions/tongtu-split-types-and-presplit-sku.md`
- 模块：`tongtool_order_cost/AGENT_HANDOFF.md`
