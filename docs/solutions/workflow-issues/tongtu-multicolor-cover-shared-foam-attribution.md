---
okf: v0.1
type: Solution
title: 通途多颜色皮壳 + 共享海绵：填充行成本挂错产品族
description: 多色 Cover 共享一个 Foam SKU 时，Foam 默认登记到另一产品（红砖凳），导致绍兴二次少计、头程多计
date: 2026-11-18
category: workflow-issues
module: tongtool_order_cost
problem_type: workflow_issue
component: tooling
severity: high
symptoms:
  - "三色魔方凳 3 个 Cover 正确指向 KS0316，但 Foam 行取 KS0428（红砖凳）成本"
  - "绍兴二次加工少计、头程多计，国外加工不变"
  - "多颜色 Cover 的组被跳过产品归属，未纠正共享填充"
root_cause: logic_error
resolution_type: code_fix
tags: [tongtool, split-merge, cover, foam, product-attribution, cost]
related_components: [tongtool_order_cost]
---

# 通途多颜色皮壳 + 共享海绵：填充行成本挂错产品族

## Problem

一个订单有 3 种颜色的几何坐墩 Cover（KS0316），共享一行 `TT0312589K0064187-Foam`，数量 3。Cover 解析正确，但 Foam 的 EN 别名默认指向另一个产品 **KS0428 红砖凳**，导致 Foam 行用了 104.265 的绍兴二次成本，而正确应为 KS0316 的 139.57；头程也用了 KS0428 的值。

这是“多件不同变体 + 共享填充”的结构，不是一件成品的拆包，不能合并成一行。

## Symptoms

- 每件绍兴二次少计 35.305（139.57−104.265）；
- 头程方向相反，多计；
- 国外加工金额不变（两个产品目的地 valuation 都为 0），所以只查国外加工总额发现不了。

实测：8 个订单家族、27 件；绍兴二次补回 953.235、头程修正 1,129.95。

## What Didn't Work

- 直接按 `(order_common, platform_sku)` 合并：会把多颜色 Cover 当组件，触发 `multiple_cover_skus` 或错误合并；
- 用数字后缀合并：规则过宽，会误并其它 SKU。

## Solution

在 `_cover_product_precedence` 里，多颜色 Cover（多个不同 Cover SKU）**不合并**，但如果所有 Cover 都解析到同一产品：

- 仅把填充行（FOAM/PPCOTTON）的 **`_en_item` 成本物料**改成该产品的 Cover 物料；
- **不改 `product_id`**，不触发合并；
- 保留多行结构、尾程按各包裹求和；
- 记录 `_group_cover_override=产品` 供审计。

验证：`WFUS-CS665428834` 的 Foam 行从 KS0428 → `KS0316-HLR-55-PURPLE`，绍兴二次 139.57、头程 46.75。

## Why This Works

共享 Foam SKU 本身不带足够产品信息；同一订单的多颜色 Cover 才是产品锚点。只替换成本物料即可纠正成本，不会改变订单件数或合并结构。

## Prevention

- 共享填充 SKU（一个 Foam 对应多个产品）不能作为产品归属依据；
- 多颜色 Cover 订单按“多件”处理，不能合并；填充行用 Cover 同族物料计价；
- 回归/对账时同时看绍兴二次和头程，不能只看国外加工总额。

## Related

- `docs/solutions/architecture-patterns/tongtu-branch-processing-cost-and-coefficients.md`
- `docs/reference/cost-engine-spec/32-phase2-bom-cost-policy.md`
- `docs/solutions/workflow-issues/tongtu-split-merge-writeback-cost-rules.md`
