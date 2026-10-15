---
okf: v0.1
type: Reference
title: 特例清单（后缀 / 自采购 / 拆单 / 清零 / 占位 / 替换）
description: 成本引擎里所有旁路规则的逐条登记：SKU 后缀（-COVER/-PPCOTTON/-FOAM 及数字后缀）、自采购、拆单多包裹系数、Product Bundle、FBA 强制清零、是否需尾程、HEAD-SX→0、品类白名单清零、灰区 fillna(0)、0.001 占位、星链海外仓替换；每条给触发/效果/落点/是否在用
date: 2026-10-15
module: tongtool_order_cost
tags: [cost, special-cases, suffix, hardcode, reference]
---

# 特例清单

> 「正常决策表之外」的所有旁路规则。每条：**触发 → 效果 → 落点 → 是否在用**。
> 主决策表见 [04-cost-decision-tables.md](04-cost-decision-tables.md)；未证实项一律指向 [09](09-known-issues-register.md)。

## 1. SKU 后缀

| 后缀 | 触发 | 效果 | 落点 | 在用 |
|---|---|---|---|---|
| **`-COVER`** | SKU 含 `-COVER` | 头程一律取**皮壳头程**；加工成本清 0（成品/半成品分支） | `order_sync.py:2947/2964/2989`；`cost_review.py:1068/1091` | ✅ 在用（order_sync + cost_review） |
| **`-PPCOTTON`** | SKU 含 `-PPCOTTON` | 头程与发货成本**双侧清 0** | `order_sync.py:2941`；`cost_review.py:1062` | ✅ 在用 |
| **`-FOAM`** | SKU 含 `-FOAM`（成品/半成品分支） | 头程 = **`成品头程 − 皮壳头程`**（半成品则 `半成品头程 − 皮壳头程`） | `order_sync.py:2972/2997`；`cost_review.py:1100/…` | ✅ 在用，但**口径漂移**：`order_sync` **不 clamp**（可负），`cost_review` 用 `max(0, …)`（见 [09](09-known-issues-register.md) A3） |
| **数字后缀 `-COVER1` / `-FOAM1`** | SKU 带数字后缀 | 仅**改有效重量口径**（历史预估尾程计费用），不改无后缀 `-COVER/-FOAM` 逻辑 | `order_sync.py:4484`（`_calculate_effective_weight_for_hist_fee`）；`cost_review.py:741-830` | ✅ 在用 |

> ⚠️ **认后缀的范围不一致**：**只有 `order_sync` 与 `cost_review` 认后缀**；`doc_event`、`delivery_note_filling_cost` **完全不认后缀**（[09](09-known-issues-register.md) A3）。

## 2. 自采购（皮壳 BOM 自引用主物料）

| 项 | 内容 |
|---|---|
| **触发** | 成品 + `cost_fg≠0` + `cost_sxbzcp==0` + 该物料 BOM **自引用主物料** |
| **效果** | `sx_cost_all = cost_fg`（= 皮壳成本），不走「皮壳 + 绍兴包装成品成本」 |
| **落点** | `bom_cost_list_v2.py:1496-1530`（报表）；订单同步 `sx_cost_all` 同源 |
| **在用** | ✅ 在报表；**`doc_event` / `delivery_note_filling_cost` 无此规则**（漂移点）。存量触发笔数**未统计**（[09](09-known-issues-register.md) A3） |

## 3. 拆单 / 多包裹

| 项 | 内容 |
|---|---|
| **触发** | 订单行有 `erp_item_code` 且物料 `Item.custom_split_package_cost_factor` 非 1 |
| **效果** | 绍兴发货成本与**三列头程**统一 × `quantity × split_package_cost_factor` |
| **落点** | `order_sync.py:2907-2917`、`_fill_split_package_cost_factor_for_order:3120` |
| **在用** | ✅ 在用 |

## 4. Product Bundle（套件）

| 项 | 内容 |
|---|---|
| **触发** | 物料组 `套件#`（`BUNDLE_ITEM_GROUP="套件#"`）、`BUNDLE_UOM="套"` |
| **效果** | 套件拆解影响**订单行粒度**，进而影响按行的成本聚合 |
| **落点** | `product_bundle_lifecycle.py` |
| **在用** | ⚠️ 对「按行成本聚合」的确切影响路径**未逐行核实**（[09](09-known-issues-register.md) E / [en-branching-and-warehouse-config.md](en-branching-and-warehouse-config.md) §未证实） |

## 5. FBA 强制清零

| 项 | 内容 |
|---|---|
| **触发** | 仓库分类含 `FBA`（`warehouse_classification`） |
| **效果** | 加工成本 = 0；`valuation_rate / hist_predict_fee / needs_last_leg / final_last_leg_fee` **一律固定 0**；`sx_shipping_cost = sx_cost_all`、`first_freight = cp_first_freight` |
| **落点** | `excel_tongtool_order.py:535-555`、`cost_review.py:2146+`（`process_fba_order_excel`）、`order_sync.py:2921`、`doc_event.py:1652` |
| **在用** | ✅ 在用。**配置侧佐证**：19 行 FBA 仓库 `processing_cost_name` 全空（[en-branching-and-warehouse-config.md](en-branching-and-warehouse-config.md)） |

> ⚠️ FBA 分支**无视发货方式与 `-COVER`/`-FOAM` 特例**（一律取绍兴总成本 + 成品头程）——带后缀的 FBA 件可能取错口径（[09](09-known-issues-register.md) A4，是否有此类订单未确认）。
> ⚠️ 另有**按客户名判 FBA** 的旁路：`delivery_note_filling_cost.py:327 _contains_fba_keyword`（`:381/:414` 强制按成品、`:618` 强制纳入 `sxbzcp`）——判据与仓库分类**不同源**。

## 6. 是否需尾程（needs_last_leg）

| 项 | 内容 |
|---|---|
| **触发** | 仓库名含 `FBA` / `多渠道仓库`、或渠道/账号对方付尾程 |
| **效果** | `needs_last_leg = 0` → 尾程费用置 0；否则 1 |
| **落点** | `cost_review.py:39-45`、`sales_gross_profit.py:295`（`needs_last_leg==0` 时 `last_leg_fee` 置 0） |
| **在用** | ✅ 在用 |

## 7. `HEAD-SX → 0`

| 项 | 内容 |
|---|---|
| **触发** | 头程来源编码 = `HEAD-SX`（绍兴自发货） |
| **效果** | 头程 = 0 |
| **落点** | `colab-engine-cell-by-cell.md` cell_106 L41-42；[04](04-cost-decision-tables.md) §2/§7 |
| **在用** | ✅ 在用（Colab 侧） |

## 8. 品类白名单清零

| 项 | 内容 |
|---|---|
| **触发** | `品类 ∈ {创意床品, 创意方抱枕, 异形沙包坐墩, 棉包, 售后针线扣}` |
| **效果（A）** | `二次加工成本 = 0` |
| **效果（B）** | `售后针线扣` / `棉包`：**连带** 皮壳（含/不含）、头程、`*系数` 列全 0，`绍兴成本系数`=`二次加工成本系数`=1.0 |
| **落点** | cell_125 L59-74（A）、L81-99 + 211 L38-46（B） |
| **在用** | ✅ 在用（Colab 侧） |

## 9. 灰区 `fillna(0)`

| 项 | 内容 |
|---|---|
| **触发** | `发货仓库 == '大件云仓'` **或** 产品名称含「主体骨架 沙发L形支架」 |
| **效果** | 15 个成本列 `fillna(0)` 并**重算全部下游** |
| **落点** | cell_125 L475-549（`mask_cost_fillna_zero`） |
| **在用** | ✅ 在用。**「灰区」**= 该行成本缺失时不报错、直接补 0（[04](04-cost-decision-tables.md) §7「灰区→`fillna(0)`」） |

## 10. `0.001` 占位

| 项 | 内容 |
|---|---|
| **触发** | 开关 `if_0_PL_cost == '注意-清零PL二次加工成本'` **且** `当月给分公司发货类型=='成品'` **且** 来源 `2CJG-PL` **且** 绍兴二次加工成本≠0 **且** 二次加工成本≠0 |
| **效果** | `二次加工成本 = 0.001`（占位，避免 0 被下游当缺失） |
| **落点** | cell_125 L246-259；开关默认 `125:202` |
| **在用** | ⚠️ 默认值即「清零」；生效与否取决于该开关当前取值（[colab-engine-cell-by-cell.md](colab-engine-cell-by-cell.md) §6） |

## 11. 星链海外仓 → DANEEY 替换

| 项 | 内容 |
|---|---|
| **触发** | 开关 `if_replace_xinglianhwc_to_ustx == '是-替换星链海外仓为DANEEY'` **且** `发货仓库=='星链海外仓'` |
| **效果** | `发货仓库 → 'FZH-DANEEY-半成品仓'`（借美中 USTX 配置） |
| **落点** | cell_056 L227-234；开关默认 `056:227` |
| **在用** | ⚠️ 默认值即「替换」；[colab-engine-cell-by-cell.md](colab-engine-cell-by-cell.md) §6 |

## 12. 其它零散清零 / 兜底

| 规则 | 落点 |
|---|---|
| `品类尺寸面料编码` 为空 → 皮壳/二次加工/头程 置 `nan` | cell_125 L51-54 |
| `发货仓分类 ∈ {FBA, 海外仓}` → 绍兴二次加工成本 / `*系数` = 0 | cell_125 L283-284 |
| `二次加工成本来源编码=='2CJG-SX'` → 绍兴二次加工成本 / `*系数` = 0 | cell_125 L287-288 |
| `当月给分公司发货类型` 列不存在 → 绍兴二次加工成本 / `*系数` 整列 0 | cell_125 L266-267 |
| FBA `订单数量>1` → `index.repeat` 拆行，每组首个保留 销量/销售额，其余清零 | cell_138 |
| FBA 无尾程 → `运费=0` | cell_195 / 211 L589-591 |
| 三角新面料（暗花绒/牧羊卷/泡泡兔毛/雕印兔毛/疙瘩绒）改写（202403 起） | cell_066:757 / 141:589（开关 `if_wedge_reduce_new_fabric_since_202403`） |

## 13. 证据清单

- Colab：`colab-engine-cell-by-cell.md`（cell_056/066/108/125/138/141/195/211；§6 开关表）
- EN 代码：`order_sync.py:2907-2917,2921,2941,2947,2964,2972,2989,2997,3120,4484`；`cost_review.py:39-45,741-830,1062,1068,1091,1100,2146+`；`bom_cost_list_v2.py:1496-1530`；`doc_event.py:1652`；`excel_tongtool_order.py:535-555`；`sales_gross_profit.py:295`；`delivery_note_filling_cost.py:327,381,414,618`
- 文档：[en-branching-and-warehouse-config.md](en-branching-and-warehouse-config.md) §其它影响成本的分支、[09](09-known-issues-register.md)
