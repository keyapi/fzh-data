---
okf: v0.1
type: Reference
title: EN 行级身份与单品后缀（单独卖皮壳/海绵/PP棉）
description: 用 EN Tongtool Order 行的 erp_item_code 做行级身份；-COVER/-FOAM/-PPCOTTON 单独售卖时按 EN order_sync 后缀特例计价；拆单组内 Cover 让位填充行；非 FBA 生效、FBA 绕过
date: 2026-11-06
category: cost-engine-spec
module: tongtool_order_cost
tags: [cost, en-line, suffix, cover, foam, ppcotton, identity]
---

# EN 行级身份与单品后缀

> 起因：2026-11 把「单独卖皮壳」误判成 SKU 别名歧义而留空，并把 Cover 行按整件产品计价。
> 用户口径：**原始订单只卖皮壳时，直接取皮壳成本；一个皮壳可配 PP棉或海绵两种填充物，这是同一皮壳、不同填充物，不是两个皮壳。**

## 1. 两类订单必须先分开

| 类型 | 判据 | 处理 |
|---|---|---|
| **拆单 / 拆包裹** | 同一 `order_common` 下多行（Cover + Foam/PPCotton，或 `_1/_2`、`-M####` 子单），且属于同一 EN 产品 | **先合并成一件成品，再对整件 BOM 计价**；只有成品/载体行计成本，组件行 0 |
| **单独卖单品** | 原始订单只有一行（只有 Cover，或只有 Foam，或只有 PP棉） | **不合并**，按 EN 后缀特例逐行计价 |

判据不是「SKU 后缀」单独决定，而是「**同一原始订单内是否有配套行**」+ 后缀。

## 2. 行级身份：EN 订单行 `erp_item_code` 优先

- 引擎原先只用 `通途SKU → customer_code 别名 → Item → 产品`。共享皮壳（如 `TT0031187K0063920-Cover` 同时登记在 KS0340 PP棉 与 KS0342 海绵）天然歧义。
- EN `Tongtool Order` 明细行自带 `erp_item_code`，即**该行实际卖的物料**，是行级权威。
- 实测：20,804 条 EN 行中，`(order_id, 通途SKU)` 无任何 `erp_item_code` 冲突；694 行为空。
- 规则：
  1. 唯一非空、且能映射到 Item/产品 → 采用（`_anchor_source=en_line`，`raw._en_item`）；
  2. 多值冲突 → 不猜；
  3. 空值 / 字面 `NULL`/`NONE`/`-` → 回退别名解析；
  4. EN 物料不在 Item 表 → **不静默回退**（若别名也解不出唯一产品则阻断），计 `en_item_unmapped`；
  5. BOM 取数优先用 `raw._en_item`，否则会出现「产品换了但别名里没有该 Item」→ `bom_item_missing`。

### 例外：拆单组内的 Cover 行

共享 Cover 的 EN 行常被默认到另一条产品线。实测 4 例（`WFUS-CS673715383`、`JYWM-129123364445886`、`WFUS-CS671990569` 等）：
平台 SKU 写 PPCotton/FOAM，Cover 行的 EN 物料却是另一产品。

→ 同一 `order_common` 内已有 Foam/PPCotton 行时，**Cover 行不采信自身 EN 物料号**，
   由填充行解析出的产品锚定（`en_line_skipped_cover_in_group`）。

### 反向例外：皮壳别名唯一时，皮壳决定组内产品

共用填充物也会被单独登记到另一产品上。实测床头板族：
`TT0031249K0064104-Cover → KS0397（菱形）`，`TT0312588K0064179-Foam → KS0396（方格）`，
两者 `绍兴包装成品成本` 不同（105.80 vs 82.90）；若按填充行取产品，整件成本会对到方格 BOM。

→ 同一 `(order_common, 平台SKU)` 内，若**皮壳别名唯一**（且组内只有一个皮壳 SKU），
   皮壳产品覆盖填充行的产品（`group_cover_override`）。
   平台 SKU 含逗号（多商品）或多皮壳 SKU（多颜色多件）时不套用，避免误并。

两条规则合起来：**差异化的那个组件决定产品**——皮壳共用→填充行定；填充物共用→皮壳定。

## 3. 单品后缀计价矩阵（EN `order_sync.py:2941-3003`，仅非 FBA）

| 形态 | 皮壳成本 | 绍兴二次加工 | 二次加工（目的地） | 头程 |
|---|---|---|---|---|
| `-COVER` | `cost_fg` | **0** | **0** | 皮壳头程 |
| `-FOAM` | **0** | `cost_sxbzcp`（成品）/ `cost_sxbzbcp`（半成品） | 目的地 valuation | 总额 − 皮壳头程（半成品：`sfg − cover`） |
| `-PPCOTTON`（且 method=皮壳） | **0** | **0** | 目的地 valuation | **0** |

- **FBA 仓绕过**以上全部特例（仍取 `sx_cost_all` + 成品头程）。
- **合并组不套后缀**：合并行代表一件整成品，按 method 取整件成本。
- `1件产品成本 = 皮壳 + 绍兴二次 + 二次` 恒等式与上述矩阵同步计算；另加硬断言
  （Cover 的 sx/processing=0、Foam 的 shell=0、PPCotton 三项=0）防止两侧同错自洽。

## 4. 实测影响（202608，已写 GS）

| 指标 | 修正前 | 修正后 | Δ |
|---|---:|---:|---:|
| 皮壳成本 | 547,909.37 | 546,543.72 | −1,365.65 |
| 头程运费金额 | 111,681.30 | 111,689.42 | +8.12 |
| 二次加工成本 | 1,453,013.54 | 1,442,508.46 | −10,505.08 |
| 绍兴二次加工成本 | 52,526.88 | 46,790.43 | −5,736.44 |
| 订单总成本 | 2,924,215.75 | 2,906,175.12 | −18,040.63 |

变化行 110：独立 Cover 清绍兴二次/二次、独立 Foam 清皮壳、PPCotton 清头程；
`N/BXP2920-BlueButterfly-60` 3 行按 EN 行由 KS0248 改 KS0001（项目既定「有无扣优先 KS0001」）。
FBA 表逐字节不变。

202609：唯一歧义单 `MXXXLAT-5002609601599-A`（波兰 covers 仓、单独卖皮壳）由留空改为
皮壳 41.912 + 皮壳头程 5.2 = 订单总成本 47.112。

## 5. 代码落点

- `domain/split_merge.py`：`SHAPE_PPCOTTON`、`load_en_line_map`、`load_orders` 的 EN 行身份与
  Cover-in-group 让位、`_en_item` 透传。
- `domain/bom_cost.py`：`item_for_detail` 优先 `_en_item`；`_unit_costs` 后缀矩阵；
  恒等式 + `单品后缀成本口径` 断言。
- 测试：`tests/test_tongtu_cost_engine_phase2.py`（EN 消歧 / EN 覆盖 / 组内让位 / 单独 Foam /
  单独 PPCotton / FBA 绕过 / 不可映射不回退）。

## 6. 相关

- [04-cost-decision-tables.md](04-cost-decision-tables.md)
- [08-special-cases.md](08-special-cases.md)
- [30-design-merge-split-no-double-count.md](30-design-merge-split-no-double-count.md)
- `../en-shaoxing-shipment-cost-logic-spec.md`（EN 后缀特例表）
