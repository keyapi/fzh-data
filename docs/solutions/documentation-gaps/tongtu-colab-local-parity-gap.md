---
okf: v0.1
type: Reference
title: Colab（截至 4.8）→ 本地引擎：已移植范围与 build-order-tabs 缺口
date: 2026-11-09
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

### 仍需本地补/明确不移植

- **build-order-tabs（必须）**：本地不生成 self 166 / FBA 95 / merged 78 的行集合与列结构；`fill-tables` 只填 29 个成本/系数列。
- 特殊订单删除（4.1.0.1）：已补 `scripts/fetch_special_orders.py`。
- 汇率（4.1.0）：已补 `scripts/fetch_fx_rates.py`；不能用 raw 的 `售价(人民币)/售价` 替代（GBP 不一致）。
- 仓库映射：`scripts/check_warehouse_map.py`；8/9 月 0 未覆盖。
- 不移植：4.1.1/4.1.2（尾程分区/州名）、4.3.0.2.9（麻将×3）、4.5.2（无海外仓）、4.5.3/4.5.4/4.9（运营人员，非成本）。

### 关键数字（202608）

- raw 10,912 → 删除特殊订单后 10,910 → Phase1 合并明细 10,821。
- Colab self 表 10,870 行：保留组件行/合并展示行，**不是**合并明细；build 不能只 concat。
- FBA 95 列 1,966；merged 78 列 12,836。

## Why This Matters

- 只要 self/FBA/merged 模板仍来自 Colab，停用 Colab 就会断掉订单表生产；成本引擎再准也无法落表。
- 行全集差异（10,870 vs 10,821）说明 build 不是简单合并，必须复刻 Colab 的行集合与列合同。

## When to Apply

- 评估/实施 Colab 退场；
- 新增月份订单表生产流程；
- 对拍本地与 Colab 的行数/销售额/四列成本/29 列。

## Examples

202608：raw 10,912 → 特殊订单 55 条（删除清单）→ 10,910；合并吸收 91 → 10,821；Colab self 10,870；FBA 1,966；merged 12,836。
202609：raw 6,268 → 6,267；合并吸收 46 → 6,222；Colab self 6,246；FBA 1,269；merged 7,515。

## Related

- 完整矩阵：`tongtool_order_cost/docs/research/2026-11-09-colab-local-parity-audit.md`
- 拆单合并成本修复：`docs/solutions/workflow-issues/tongtu-split-merge-writeback-cost-rules.md`
- 拆单类型与拆单前 SKU：`docs/solutions/conventions/tongtu-split-types-and-presplit-sku.md`
- 模块：`tongtool_order_cost/AGENT_HANDOFF.md`
