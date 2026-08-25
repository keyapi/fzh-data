---
okf: v0.1
type: Reference
title: 复古造型大体量沙发四模块组合套件创建
date: 2026-08-21
category: workflow-issues
module: SELLFOX_API
problem_type: workflow_issue
component: development_workflow
severity: medium
applies_when:
  - "组合商品由四个不同 EN 成品模块组成"
  - "登记表通途SKU 已存在且带 -ALL 后缀"
tags: [sellfox, combo, product-bundle, tj, retro-sofa, multi-module, customer-items]
---

# 复古造型大体量沙发四模块组合套件创建

## Context

`未配对产品登记表0821.xlsx` 中 `复古造型大体量沙发` 只有 1 行：

- 通途SKU：`TT0031241K0064076-ALL`
- 数量：4
- 组成：右扶手 + 无扶手 + 脚踏 + 左扶手带延长

EN 底层变体：

- `KS0387-MTXCTTM-100x100x85-BROWNLIGHTBEIGE`（右扶手，赛狐 `3702040`）
- `KS0391-MTXCTTM-100x80x75-BROWNLIGHTBEIGE`（无扶手，赛狐 `3702147`）
- `KS0392-MTXCTTM-120x180x85-BROWNLIGHTBEIGE`（左扶手带延长，赛狐 `3702158`）
- `KS0393-MTXCTTM-80x80x45-BROWNLIGHTBEIGE`（脚踏，赛狐 `3702155`）

## Guidance

### 1. 四模块用四个 child

```bash
uv run --project .. python sellfox_combo_ops.py en-create \
  --child "KS0387-MTXCTTM-100x100x85-BROWNLIGHTBEIGE:1" \
  --child "KS0391-MTXCTTM-100x80x75-BROWNLIGHTBEIGE:1" \
  --child "KS0392-MTXCTTM-120x180x85-BROWNLIGHTBEIGE:1" \
  --child "KS0393-MTXCTTM-80x80x45-BROWNLIGHTBEIGE:1" \
  --apply
```

### 2. 通途SKU 已存在，直接登记

`TT0031241K0064076-ALL` 是登记表真实通途SKU，直接作为 EN 上层 Item `customer_items.ref_code`，不需要合成新码。

### 3. 阶段记录

`retro_sofa_stage.py plan / status / record` 生成 `复古造型大体量沙发阶段记录.xlsx`。

## Why This Matters

四模块组合的组成映射必须按登记表“套件”列逐项解析；EN TJ# 会按四个 SPU 前缀生成 `TJ#KS0387x1_KS0391x1_KS0392x1_KS0393x1-001`，与赛狐 `childSkus` 一一对应。

## When to Apply

- 组合由 3 个以上不同 EN 成品模块组成。
- 登记表通途SKU 已存在且不需要合成。

## Examples

2026-08-21 复古造型大体量沙发完成：

- EN Product Bundle：`TJ#KS0387x1_KS0391x1_KS0392x1_KS0393x1-001`。
- 客户物料号：`TT0031241K0064076-ALL`，已登记并回读。
- 赛狐组合 ID：`3923034`，`sync-combos` 结果 `ok=1`。
- 阶段记录 Excel：`复古造型大体量沙发阶段记录.xlsx`，1/1 完成。

## Related

- [可组合扶手沙发双子件套件批量创建](combinable-sofa-combo-batch-staging.md)
- [深卧单人沙发椅双色组合套件批量创建](deep-sofa-combo-batch-staging.md)
- [EN 套件 / 赛狐组合商品操作手册](../../../SELLFOX_API/docs/reference/combo-ops.md)
