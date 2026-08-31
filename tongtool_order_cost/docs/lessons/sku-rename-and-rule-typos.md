---
okf: v0.1
type: Lesson
title: 通途主档改名与规则笔误
description: 精确匹配会被 SKU 改名打断；像旧名的 SKU 先查主档再决定是否替换
tags: [lesson, sku, tongtool]
timestamp: 2026-08-14
---

# 通途主档改名与规则笔误

1. **井维护新名，订单保留导出时的旧名。** 不要把规则改回旧名来迁就导出。
2. **「搜不到」不一定是笔误。** `BNFBAvelvetgray60` 在通途主档真实存在（60CM），与 `…gray-100` 不是同一货。替换前用 goodsQuery。
3. **同系列编号也不一定是同一货。** `FoamFBA…BLACK-97` 是规则填错；`CENKZ…BLACK-97` 是 CEN 自发货，不要一起改。
4. **同一 workbook 里 SKU 列名可能不同**（`SKU` vs `通途SKU`）。只改那一列，不动 MSKU。
5. **写回前 dry-run 计数**，写回后旧名必须清零，例外 SKU 计数不变。
