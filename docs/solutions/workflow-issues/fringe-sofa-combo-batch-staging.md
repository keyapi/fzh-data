---
okf: v0.1
type: Reference
title: 弧形流苏沙发单件整沙发组合创建
date: 2026-08-21
category: workflow-issues
module: SELLFOX_API
problem_type: workflow_issue
component: development_workflow
severity: low
applies_when:
  - "登记表通途SKU 带 -ALL 后缀但 EN 只有整沙发成品，没有可拆成品模块"
  - "单件整沙发也需要在赛狐以组合商品形式存在以便配对"
tags: [sellfox, combo, product-bundle, tj, fringe-sofa, single-item, customer-items]
---

# 弧形流苏沙发单件整沙发组合创建

## Context

`未配对产品登记表0821.xlsx` 中 `弧形流苏沙发` 只有 1 个唯一通途SKU：

- `TT0031255K0064131-ALL`
- 名称：弧形流苏沙发 科艺绒 蓝色 193*108*80cm

EN 底层只有整沙发成品 `KS0402-KYR-193x108x80-BLUE`（基码 `TT0031255K0064131`，赛狐 ID `3701950`）；没有可拆分的成品模块，因此组合为单件 child。

## Guidance

### 1. -ALL 不一定等于多模块

先拉快照确认 EN 是否只有一个整沙发成品；如果只有单件成品，就按 child x1 创建，不要强行拆模块。

### 2. 单 child 创建

```bash
uv run --project .. python sellfox_combo_ops.py en-create \
  --child "KS0402-KYR-193x108x80-BLUE:1" \
  --apply
uv run --project .. python sellfox_combo_ops.py register-customer-code \
  --sku "TJ#KS0402x1-001" \
  --ref-code "TT0031255K0064131-ALL" \
  --apply
uv run --project .. python sellfox_combo_ops.py sync-combos --sku "TJ#KS0402x1-001" --apply
```

### 3. 阶段记录

`fringe_sofa_stage.py plan / status / record` 生成 `弧形流苏沙发阶段记录.xlsx`。

## Why This Matters

“套件/组合商品”不一定都是多模块；当 EN 只有整沙发时，单 child 组合是赛狐配对和订单归因的最小可用对象。备注里记录“整沙发单件”避免后续误拆。

## When to Apply

- `-ALL` 通途SKU 对应 EN 整件成品。
- 赛狐需要组合商品对象用于配对，但底层没有多个可拆模块。

## Examples

2026-08-21 弧形流苏沙发完成：

- EN Product Bundle：`TJ#KS0402x1-001`。
- 客户物料号：`TT0031255K0064131-ALL`，已登记并回读。
- 赛狐组合 ID：`3923064`，`sync-combos` 结果 `ok=1`。
- 阶段记录 Excel：`弧形流苏沙发阶段记录.xlsx`，1/1 完成。

## Related

- [沙发支撑垫存量 EN 套件补齐](support-pad-combo-reconcile.md)
- [复古造型大体量沙发四模块组合套件创建](retro-sofa-combo-batch-staging.md)
- [EN 套件 / 赛狐组合商品操作手册](../../../SELLFOX_API/docs/reference/combo-ops.md)
