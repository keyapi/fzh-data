---
okf: v0.1
type: Reference
title: 通途订单成本引擎：Colab 迁移本地包的四列口径与合并/BOM 架构
date: 2026-11-05
category: architecture-patterns
module: tongtool_order_cost
problem_type: architecture_pattern
component: tooling
severity: high
applies_when:
  - "要重跑某月通途订单成本、写回 写回YYYYMM 表"
  - "要改 Colab 成本逻辑或把某列切到 EN BOM"
  - "拆包裹/合并、套件、FBA 与自发货合并成本出现重复或缺失"
tags: [cost-engine, colab-migration, bom-cost, split-merge, fba, canary]
---

# 通途订单成本引擎：Colab 迁移本地包的四列口径与合并/BOM 架构

## Context

月度通途订单成本长期由 Colab notebook（Drive id `1T5hZYvnJhS8xzORb3tuYRoXXWn9uSzNl`，224 cells）生产。历史问题：

- 拆包裹/合并按 `订单号_公共部分 + 平台SKU` 分组，身份字段取 `first()`；实测 8/9 月 114 组中 52 组首行不是成品，行相加与"一件成品"口径差约 30%。
- 四列成本中只有皮壳、头程已用 EN；「二次加工成本」借绍兴包装成品成本（7 月高估 +225,982），「绍兴二次加工成本」整列 0（少计 +38,930）。
- EN 订单行存储的 `cost_fg/valuation_rate/sx_shipping_cost` 是**同步时点值**，会陈旧（CENTRADE 皮壳行存储 `valuation_rate=0`，当前 BOM 报表为 165.128），不能作为可复现主源。

因此目标是把引擎迁成本地 Python 包，Colab 只做薄调用；按"合并成一件成品 + 月末 BOM 单位成本 × 件数"计价。

## Guidance

### 1. 主路径：合并 + BOM，而不是行级存储字段

- 订单全集：EN `Tongtool Order` 有效单（`invalid=0`）；GS 原始 `2026年X月订单` 只作业务骨架。
- 拆包合并：按 EN 产品身份（`通途SKU → customer_code 别名 → Item/产品`）分组；成品/半成品/皮壳按 EN `shipping_method` 判定，不取 first。
- 件数：成品取成品载体数量；半成品 Cover+Foam 取 Cover 数量，不把组件行 qty 相加；多件按数量。
- 成本：**月末 BOM Cost List 产品单位成本 × 件数**；EN 订单行存储成本只作对账/兜底，并标注 `source/freshness`。

### 2. 四列语义（列名不变）

```
皮壳成本        = BOM cost_fg（单位）
头程运费金额    = BOM 头程列（按 method；-COVER 皮壳、-FOAM 差额、FBA 对应 FBA 成品头程）
二次加工成本    = 目的地加工（USNJ/USTX/PL 的 valuation_rate；FBA=0；美国海外仓复用 USTX）
绍兴二次加工成本 = 皮壳→0；半成品→绍兴包装半成品成本；成品/FBA→绍兴包装成品成本（已含半成品）
```

恒等式：`皮壳 + 绍兴二次 + 二次 = EN 1件产品成本`（同月快照、同 method）。FBA 的绍兴二次按 `sx_cost_all − cost_fg`，不能为 0（除非直采成品 `cost_fg==sx_cost_all`，标 `direct_purchase_zero`）。

### 3. 套件

- 优先 Product Bundle 字段（`derived_shipping_method` / `method_status` / `bundle_version`）；当前无字段时，按**全子件 method 一致**派生，混合/空则待审。
- 订单只有 TJ# 时，套件行是唯一成本载体；子件只用于展开/审计，不能与套件行同时计价。
- 可对照 BOM Cost List V2 的 `show_kit_items` 套件行（Σ子件×qty）做对账，差异 >0.01 阻断。

### 4. FBA 与自发货

- FBA 成本用 **EN FBA 订单明细**；GS FBA 销量报表只作 78 列输出骨架与业务对账；通途 FBA 导出作覆盖校验。
- 合并 shadow 必须带 `fulfillment` 与唯一键；FBA 与自发货禁止按 SKU 直接 union/去重。

### 5. Canary

- 旧值必须取**目标写回表**（如 `写回YYYYMM订单`/merged 写回），不能取上游 FBA 销量报表的「成本/头程费用」；后者是报表汇总口径，会造成假差异。
- 写前备份 + hash、单写锁、只写四列目标行；写后回读行数/键/四列/非目标列零变化；不一致用备份整体回滚。

## Why This Matters

- 存储字段陈旧会导致同一月份不同日期重跑结果不同，且无法审计。
- 行级相加在拆单场景会双计（同一产品多行完整成本），只取载体又会漏组件成本。
- 四列语义固定后，下游透视/财务无感，且每列可回溯源表、BOM 版本与件数。

## When to Apply

- 重跑某月成本、生成 `写回YYYYMM` 或 FBA/合并 shadow。
- 切换成本列、改拆合规则、处理套件/FBA。
- 做任何 GS 写回前的 canary 与差异解释。

## Examples

- CENTRADE 皮壳行存储 `valuation_rate=0`，当前 BOM 报 `usnj_valuation_rate=165.128` → 必须用 BOM 快照。
- `OS-477799069` 拆成 `_1/_2`，两行同产品各 sx=1788.49；行级相加=3577 双计，合并成一件只计一次。
- 8/9 月 FBA 覆盖：EN 明细 + GS 骨架 + 33 个 SKU 别名登记后，priced 覆盖 100% / 99.92%（1 件 `no_en_fba_rows` 待审）。

## Related

- `docs/reference/cost-engine-spec/04-cost-decision-tables.md`
- `07-colab-vs-en.md`、`30-design-merge-split-no-double-count.md`
- `32-phase2-bom-cost-policy.md`、`33-phase3-writeback-rehearsal.md`、`34-phase4-run-package-canary.md`、`35-phase4-fba-shadow.md`
- 代码：`tongtool_order_cost/tongtu_cost_engine/`（split_merge / bom_cost / writeback_rehearsal / fba_shadow / run_package）
