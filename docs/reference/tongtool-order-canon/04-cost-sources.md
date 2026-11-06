---
okf: v0.1
type: Reference
title: 成本取值链（皮壳 / 头程 / 目的地加工 / 绍兴侧 / 自采购 / 套件）
description: 四列成本各自的取值来源与优先级，含 BOM 时点、自采购特例、套件的本地实现边界；不写订单分组（见 02）与矩阵（见 03）
date: 2026-11-06
module: tongtool_order_cost
tags: [tongtool, order, bom, cost-source, self-purchase, kit, canon]
---

# 成本取值链

> **状态：canon v0.1。** 矩阵怎么组合见 [03](03-price-matrix.md)；本页只回答「每一列的数值从哪来、优先级是什么」。

## 1. 时点：月末 BOM 快照

- 用**月末 BOM 快照**（BOM Cost List，含 disabled 物料与套件行）计价，不用 EN 订单行存储成本。
- 订单行存储的 `cost_fg/valuation_rate/sx_shipping_cost` 是**同步时点值**，会陈旧；只作对账/兜底。
- 每个 run 记录 BOM、Bundle、仓库映射、白名单的版本/hash。

## 2. 皮壳成本

| 口径 | 取值 |
|---|---|
| 默认 | BOM `cost_fg` |
| `皮壳含 / 不含包装` | 由 BOM 口径决定；Colab 的历史分支（`2CJG-SX` / `是否皮壳` / 分公司发货类型）只作证据 |
| 自采购 | 见 §6（`cost_fg == sx_cost_all` 且 `cost_sxbzcp == 0`） |
| 缺值 | 阻断并暴露，不静默补 0（灰区/白名单除外） |

## 3. 头程

- 来源：BOM Cost List 的头程列（按仓库分类 + 发货方式三选一：皮壳/半成品/成品）。
- `-COVER` → 皮壳头程；`-FOAM`（半成品/成品）→ 总额 − 皮壳头程。
- `HEAD-SX`（绍兴自发货）→ 0。
- FBA → 对应国家 FBA 成品头程。
- 美国海外仓：皮壳/半成品头程借 USTX，成品头程借 USFBA。

## 4. 目的地二次加工

- 目的地包装成品 BOM 的 `total_cost`：
  - 美东 USNJ / 美中 USTX / 波兰 PL → 各自包装成品 BOM；
  - 美国海外仓 → 复用 USTX；
  - FBA → 0（无加工成本配置）。
- 无 BOM → `Item.valuation_rate`；`disabled=1` → 空。

## 5. 绍兴二次加工

| 发货方式 | 取值 |
|---|---|
| 皮壳 | 0 |
| 半成品 | `cost_sxbzbcp`（绍兴包装半成品成本） |
| 成品 | `cost_sxbzcp`（绍兴包装成品成本） |
| FBA | `sx_cost_all − cost_fg` |

> 注意两套「绍兴成本」不同义：报表列 `sx_cost_all` 与订单字段 `sx_shipping_cost` 口径不同；本规范只用上述分解。

## 6. 自采购（皮壳 BOM 自引用主物料）

- 触发：成品 + `cost_fg ≠ 0` + `cost_sxbzcp == 0` + 该物料 BOM **自引用主物料**。
- 效果：`sx_cost_all = cost_fg`，不走「皮壳 + 绍兴包装成品」。
- 报表侧已有；订单同步/送货单侧是否一致未证实 → 合并/对账时标 `direct_purchase_zero`。
- FBA 直采：`cost_fg == sx_cost_all` 且 `cost_sxbzcp == 0` 时允许绍兴二次=0，不是缺值。

## 7. 套件（TJ#）

- **EN 订单成本链无实现**（OS/CR/SGP grep bundle=0）；当前权威是本地引擎。
- 规则：Product Bundle 子件 method 全一致才派生 `kit_method`；混合/空 → 待审。
- 订单只有 `TJ#` 时，套件行是唯一成本载体；子件只用于展开/审计，**不得与套件行双计**。
- 可用 BOM Cost List V2 `show_kit_items` 的套件行（Σ子件×qty）对账，差异 >0.01 阻断。

## 8. 证据

- [03-price-matrix.md](03-price-matrix.md)、[04-cost-decision-tables（历史）](../../../tongtool_order_cost/docs/reference/cost-engine-spec/04-cost-decision-tables.md)
- `bom_cost_list_v2.py`、`order_sync.py`（2026-11-06 观测）
- 本地：`bom_cost.py`、`fba_shadow.py`
- 冲突：C1/C2/C3/C6/C8 见 [07-conflicts.md](07-conflicts.md)
