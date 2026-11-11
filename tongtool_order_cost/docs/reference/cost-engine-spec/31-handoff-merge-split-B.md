---
okf: v0.1
type: Guide
title: 交接书 B — 拆包裹/合并 → 合成一件成品再对 BOM（不重不漏）
description: 给新对话/子Agent 的执行交接：起点=设计稿30 + group_split_rows
date: 2026-10-17
module: tongtool_order_cost
tags: [cost, ustx, order-merge, split-package, handoff]
---

# 交接书 B：拆包裹合并 → 合成一件再对 BOM

> **新对话/子Agent 直接执行本页。**

## 起点（已完成，别重造）
- **设计稿**：`30-design-merge-split-no-double-count.md`（落点/算法/5 条不重不漏断言/待拍板）。
- **第 1 片已落地**（`tongtool_order_cost/tongtool_order_cost/ustx_cost_compare.py`）：
  - `order_common_part(order_no)` —— 只剥末尾 1–2 位数字后缀。
  - `group_split_rows(records, *, require_multi_sku=True)` —— 按 `(订单号公共部分, 平台SKU)` 分组，出「行数≥2 且 通途SKU>1」的**拆包裹候选**，附 `skus/key_set/qty_sum/cost_sum`；**不合并、不改原行**。
  - `order_row_to_record` 已带 `order_no / platform_sku / tongtool_sku / sku`。
  - 约束：**主比较表必须保留全部 writeback 行**（所以合并是"附加视图"，不是替换）。

## 要做的
1. **聚合**：组内 `售价/售价*汇率/运费/发货数量` → `sum`（同 Colab `cell_077` 口径；注意 `order_row_to_record` 目前只带 4 项成本 + qty，**需要的列要补**）。
2. **选"成品行"**：优先 EN `shipping_method` / `custom_shipment_type_to_branch`；无 EN 回落 `是否皮壳=='皮壳'`→按成品。
3. **只有成品行对 BOM**；其余行成本置 0/并入 ⇒ **"不重"的关键**。
4. **A/B 对拍**：合并前 vs 合并后，逐项验 **断言1（守恒）/断言2（件数=Σ皮壳行）**，并**量化"当前重复计了多少成本"**。
5. 全部走**纯函数 + 测试**；不动 Colab（生产）。

## 权威源（不要靠"产品名含包裹"）
- EN `Tongtool Order`：**原始单 + 拆分子单**都在；`order_items` 带 `erp_item_code / quantity / shipping_method / split_package_cost_factor`。
- 判据：按 `通途SKU → EN ref_code → 同一 EN 产品` ⇒ 该合并；不同 ⇒ 不合并。
- **歧义即阻断**，不取 first/max。

## 相关
- `18-sku-direct-impact-on-order-merge.md`（影响评估 + 待拍板 Q1–Q7）
- `docs/solutions/conventions/tongtu-order-suffix-and-merge-criteria.md`（在分支 `docs/colab-cost-current-state`/PR#280）
