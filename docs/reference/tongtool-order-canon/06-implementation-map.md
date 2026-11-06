---
okf: v0.1
type: Reference
title: 实现映射（规则 → EN / 本地 / Colab / GS）
description: 每条 canon 规则在当前 EN 生产代码、本地引擎、旧 Colab/GS 中的落点；只写文件与函数、观测日与 commit，不把行号当稳定键
date: 2026-11-06
module: tongtool_order_cost
tags: [tongtool, order, implementation, en, local, colab, mapping]
---

# 实现映射

> **状态：canon v0.1（2026-11-06 观测）。** 本页只描述「现在在哪」，不定义应然。
> 行号会漂移：只写文件/函数；如需精确定位，用函数名 grep，并记录观测日。

## 1. 订单身份与全集

| 规则 | EN 生产 | 本地引擎 | 旧 Colab / GS | 观测 |
|---|---|---|---|---|
| 有效单 `invalid=0` | `tongtool_integration/sync/order_sync.py`（订单头/明细） | `split_merge.load_orders` | raw `{月}订单` | 2026-11-06 |
| 作废原单只作锚 | 同上（`invalid=1` 仍在表内） | `split_merge.load_aux_original/_aux_validate` | 旧写回表含原单 | 2026-11-06 |
| 拆分子单 `_1/_2` 保留 | `order_sync.py`（子表） | `split_merge.load_orders` | 同 `order_common` 分组 | 2026-11-06 |
| 订单号只剥 1–2 位 | 无（本地派生键） | `ustx_cost_compare.order_common_part` | cell 070 `extract_order_prefix` | 2026-11-06 |
| GS 历史销售边界 | EN 2025-07 起基本完整 | `order_side_input`；DuckDB 在 demand_forecast | GS 2023-01 起为历史真源 | #290 |

## 2. 分组合并与产品归属

| 规则 | EN 生产 | 本地引擎 | 旧 Colab / GS | 观测 |
|---|---|---|---|---|
| 结构合并判据 | **无合并**（逐行） | `split_merge.find_groups/_pick_carrier/_count_pieces` | cell 072–092 | 2026-11-06 |
| 行级身份 `erp_item_code` | `order_sync.py`（订单明细） | `split_merge.load_en_line_map` + `bom_cost.item_for_detail` | 无 | 2026-11-06 |
| 共享皮壳→填充行定产品 | 无 | `split_merge._anchor_same_order` | cell 083（电话+sku_base） | 2026-11-06 |
| 共享填充物→皮壳定产品 | 无 | `split_merge._cover_product_precedence` | 无 | 2026-11-06 |
| 单独卖后缀不歧义 | `order_sync.py` 后缀特例 | `bom_cost._unit_costs` | 无行级身份 | 2026-11-06 |
| TikTok 跨前缀配对 | 无（手动建单） | `split_merge._pair_tiktok_cross_prefix`；`phase36_fill` body 兜底 | cell 082/083/085/089/090/092 | 2026-11-06 |

## 3. 计价矩阵

| 规则 | EN 生产 | 本地引擎 | 旧 Colab / GS | 观测 |
|---|---|---|---|---|
| 四列（皮壳/头程/目的地/绍兴二次） | `order_sync.py`；`bom_cost_list_v2.py` | `bom_cost._unit_costs` | cell 100–125 | 2026-11-06 |
| `-COVER/-FOAM/-PPCOTTON` | `order_sync.py`（仅非 FBA） | `bom_cost._unit_costs` 后缀矩阵 | 无 | 2026-11-06 |
| FBA 绕过/成品口径 | `order_sync.py` FBA 分支 | `fba_shadow.build_fba_shadow` | cell 138/148 | 2026-11-06 |
| 自采购 | `bom_cost_list_v2.py` | 依赖 BOM 快照 | cell 125 借成本 | 2026-11-06 |
| 套件 TJ# | **无实现**（grep bundle=0） | `bom_cost` Product Bundle | 无 | 2026-11-06 |
| 合并守恒（销售/运费） | 无合并 | `writeback_rehearsal._assert_conservation` | cell 077/090 求和 | 2026-11-06 |

## 4. 旁路

| 规则 | EN 生产 | 本地引擎 | 旧 Colab / GS | 观测 |
|---|---|---|---|---|
| 拆单系数 | `order_sync.py`（订单同步恒 1）/ `tongtool_cost_review.py`（生效） | 不乘（合并路线） | 无 | 2026-11-06 |
| 尾程 | `order_sync.py` / `tongtool_cost_review.py` / `sales_gross_profit.py` 三套 | 未纳入四列 | `monthly-tail-cost-pipeline.md` | 2026-11-06 |
| 90 天改单窗口 | 通途平台约束 | — | #282 实测 | 2026-11-06 |
| 非商品/白名单 | — | `split_merge.is_non_product_accessory` | cell 125 白名单 | 2026-11-06 |

## 5. 权威与迁移

- 成本口径权威：**本地 38 矩阵**（[ADR-0001](adr/0001-cost-authority-and-migration.md)）。
- EN 五链路对齐状态：见 [07-conflicts.md](07-conflicts.md) C2；C1（拆单系数）与 C3（FBA 判据）已有裁决，待实现。
- 任何实现与本页不一致 → 先判「代码 bug / 规范过期」，写进 07；不允许两边都算对。
