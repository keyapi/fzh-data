---
okf: v0.1
type: Reference
title: Phase 3.7 作废原单处理 + 95↔78 对账 + GS-ready 严格列输出（本地）
description: crosswalk_missing 的作废原单保留行与销售、清空成本及派生（含系数轨）并标 invalid_original；95↔78 按 SKU/数量/销售额/四列/系数/派生聚合恒等；验证 FBA 与非 FBA 无重叠；输出严格 166/95/78 列 GS-ready CSV
date: 2026-11-05
module: tongtool_order_cost
tags: [cost, phase3.7, invalid-original, reconciliation, gs-ready, fba]
---

# Phase 3.7 作废原单 + 95↔78 对账 + GS-ready

> 落地：`domain/phase36_fill.py`（`fill-tables` 内扩展）；只写本地文件，不写 GS/EN。

## 1. 作废原单（invalid_original）

- 对 `cost_status=crosswalk_missing` 且订单在 `order_flags.invalid=1` 的行：
  - **保留行**与销售/非成本字段（售价×汇率、数量、渠道、SKU 等）；
  - 成本块与全部成本派生列（含系数轨）**清空**（不写 0）；
  - 审计标记 `cost_status=invalid_original`，并列入 `blanks.csv`；
  - 模板旧成本值只写入 `invalid_original_backup.csv`（优先取旧写回同键行，其次模板行）。
- 非作废的 `crosswalk_missing` 保持留空 + 原因（本次 202608 仅 2 行，202609 0 行）。

## 2. 95↔78 粒度对账

- FBA 95 与 merged 78 的 FBA 子集按 `(站点/渠道账号, MSKU/平台SKU, SKU/通途SKU)` 聚合；
  指标：发货数量、售价*汇率、四列（皮壳/绍兴二次/二次/头程，含单位与 `*数量`）、
  1件产品成本、产品成本*数量、订单总成本、订单利润、3 个基础系数 + 12 个派生系数。
- 输出 `recon_95_78.csv`（仅差异键/指标）、`recon_95_78_totals.csv`（总量对比）。
- FBA 与非 FBA 重叠：订单号交集 + `站点|SKU` 交集 → `overlap_self_fba.csv`（应为空）。

## 3. GS-ready

- `gs_ready/` 目录：严格按模板列输出 **166 / 95 / 78** 列（剔除 `cost_status` / `cost_reason` 审计列）。
- 审计版仍保留在 `out/phase36/<month>/` 顶层（+2 审计列 + 全部填充列）。

## 4. 2026-11-05 结果

| 指标 | 202608 | 202609 |
|---|---:|---:|
| 作废原单（invalid_original） | 11 | 9 |
| 其他 crosswalk_missing | 2 | 0 |
| 空白清单合计 | 13 | 10（含 1 行 Phase3 skipped） |
| 95↔78 指标合计差异 / 键级差异 | **0 / 0** | **0 / 0** |
| FBA↔非FBA 重叠 | **0** | **0** |
| GS-ready 行数（self / FBA / merged） | **10,870 / 1,966 / 12,836** | **6,246 / 1,269 / 7,515** |
| GS-ready 列数 | 166 / 95 / 78 | 166 / 95 / 78 |
| 普通轨+系数轨恒等违例 | 0 / 0 / 0 | 0 / 0 / 0 |

## 5. 断言与测试

- 作废行成本/系数全空、销售保留、备份含旧值；
- GS-ready 列严格等于模板列且无审计列；
- 95↔78 聚合零差异、FBA/非FBA 零重叠；
- `tests/test_tongtu_cost_engine_phase36.py` 覆盖以上路径；全仓库测试通过。
