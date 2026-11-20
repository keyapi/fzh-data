---
okf: v0.1
type: Reference
title: Phase 3.6 成本+系数块补全（self 166 / FBA 95 / merged 78，本地）
description: 以三份写回模板为骨架，用 Phase3 结果与 FBA shadow 填完整成本块与系数块；系数从旧写回按行/crosswalk 继承，合并组取载体系数并阻断冲突；输出 crosswalk/填充率/空白清单与恒等断言
date: 2026-11-05
module: tongtool_order_cost
tags: [cost, coefficient, phase3.6, fill, writeback, fba, merged]
---

# Phase 3.6 成本 + 系数块补全

> 落地：`domain/phase36_fill.py`；CLI `fill-tables`。**只写本地文件，不写 GS/EN。**

## 1. 输入与输出

| 角色 | 文件 |
|---|---|
| self 模板（166） | `out/wb_fresh_<month>.csv` |
| FBA 模板（95） | `out/wb_fba_<month>.csv` |
| merged 模板（78） | `out/merged_<month>.csv`（= self 行 + FBA 行，按索引对齐） |
| self 成本源 | `out/writeback_rehearsal/<month>/writeback_new_<month>.csv`（Phase3） |
| FBA 成本源 | `out/fba_shadow/<month>/fba_shadow_<month>.csv` |
| 系数旧值 | `out/writeback_<month>.csv`（旧写回） |

输出目录 `out/phase36/<month>/`：`wb_fresh_<m>.csv`、`wb_fba_<m>.csv`、`merged_<m>.csv`、
`crosswalk_self.csv`、`crosswalk_fba.csv`、`fill_rates.csv`、`blanks.csv`、`summary.md`、`manifest.json`。

## 2. 公式（colab cell_125/168/169）

- `1件产品成本 = 皮壳成本 + 绍兴二次加工成本 + 二次加工成本`
- `产品成本*数量 = 1件产品成本 × 发货数量`
- `订单总成本 = 产品成本*数量 + 头程运费*数量 + 运费 + 海外仓成本*数量`
- `订单利润 = 售价*汇率 − 订单总成本`
- 系数轨同结构：`皮壳成本*系数 = 皮壳成本 × 绍兴成本系数`，`绍兴二次*系数 = 绍兴二次 × 绍兴二次加工成本系数`，
  `二次*系数 = 二次 × 二次加工成本系数`；`1件*系数 = 三者之和`；`产品成本*系数*数量 = 1件*系数 × qty`；
  `订单总成本*系数 = 产品成本*系数*数量 + 头程*数量 + 运费 + 海外仓*数量`；
  `订单利润*系数 = 售价*汇率 − 订单总成本*系数`。

## 3. 系数继承与阻断

- self：Phase3 行基础系数（已从旧写回继承）→ 旧写回同键行 → 模板行。
- 合并组：所有成员统一取**载体行**系数；成员旧写回非空系数与载体不一致 → `coef_conflict`（留空）。
- FBA：95 模板自带基础系数（0/1），原样保留后派生。
- 0 / 1 原样保留；空基础系数保持空，派生列按 1.0 计算（与 Colab 一致）。
- 皮壳含/不含包装成本：优先继承旧写回；缺失时回退为 `皮壳成本`（BOM 无包装拆分）。

## 4. Crosswalk

- self：`(订单号, 通途SKU)` → `(订单号, 平台SKU)` → 同订单唯一来源行 → raw 行号→Phase3 `source_row`。
- 被吸收的组件行（同组非载体）→ 成本显式 **0** + `component_absorbed`，系数取载体。
- 非商品配件 → 成本 **0** + `non_product_accessory`，不进入空白清单。
- 未匹配模板行 → 留空 + `crosswalk_missing`（列入 `blanks.csv`）。
- FBA：`(站点, MSKU, SKU)` 对 FBA shadow；0 数量行金额按 0 计算。

## 5. 断言

每行校验普通轨与系数轨恒等（1件/产品成本/总成本/利润），违例写 `summary`；
目标 **0** 违例。2026-11-05 实测两月三表均为 0。

## 6. 2026-11-05 结果

| 指标 | 202608 | 202609 |
|---|---:|---:|
| 行数 self / FBA / merged | 10,870 / 1,966 / 12,836 | 6,246 / 1,269 / 7,515 |
| 成本块填充率（self / FBA / merged） | 99.88% / 100% / 99.90% | 99.84% / 100% / 99.87% |
| 系数块填充率（self / FBA / merged） | 99.81% / 100% / 99.84% | 99.59% / 100% / 99.66% |
| 基础系数填充率（self / merged） | 99.52% / 99.59% | 98.59% / 98.82% |
| 阻断 / 空白 | `crosswalk_missing` 13 / 13 | `crosswalk_missing` 9、`source_skipped_ineligible` 1 / 10 |
| 恒等违例 | 0 / 0 / 0 | 0 / 0 / 0 |

空白均为模板中**不在 raw 快照**的旧行（无法确定成本源），不沿用旧值。
