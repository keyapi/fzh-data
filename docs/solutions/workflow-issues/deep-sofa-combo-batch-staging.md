---
okf: v0.1
type: Reference
title: 深卧单人沙发椅双色组合套件批量创建
date: 2026-08-21
category: workflow-issues
module: SELLFOX_API
problem_type: workflow_issue
component: development_workflow
severity: medium
applies_when:
  - "同一 SPU 多个颜色变体按双色组合成销售"
  - "通途SKU 已存在，但需要按颜色映射 EN 底层变体"
tags: [sellfox, combo, product-bundle, tj, deep-sofa, two-color, customer-items]
---

# 深卧单人沙发椅双色组合套件批量创建

## Context

`未配对产品登记表0821.xlsx` 中 `深卧单人沙发椅` 有 3 个组合，通途SKU 已存在：

- `JONYHBBChair-WWhite+RRed` → 暖白 + 茜红
- `JONYHBBChair-RRed+DBlue` → 茜红 + 深蓝
- `JONYHBBChair-WWhite+DBlue` → 暖白 + 深蓝

EN 底层变体：

- `KS0483-FHXYR-80x85x67-WARMWHITE`（基码 `TT0312681K0064363`，赛狐 ID `3702354`）
- `KS0483-FHXYR-80x85x67-ALIZARINRED`（基码 `TT0312681K0064361`，赛狐 ID `3702352`）
- `KS0483-FHXYR-80x85x67-DEEPBLUE`（基码 `TT0312681K0064362`，赛狐 ID `3702353`）

## Guidance

### 1. 通途SKU 已有，直接作为客户物料号

这类批次不需要合成 `TT` 新码；把登记表的完整通途SKU（如 `JONYHBBChair-WWhite+RRed`）登记到 EN 上层 Item `customer_items.ref_code`。

### 2. 登记表颜色列映射 EN 变体

登记表“套件”列 `白色，红色` 对应暖白 + 茜红各 1 件；创建 EN Product Bundle 时传两个 child：

```bash
uv run --project .. python sellfox_combo_ops.py en-create \
  --child "KS0483-FHXYR-80x85x67-WARMWHITE:1" \
  --child "KS0483-FHXYR-80x85x67-ALIZARINRED:1" \
  --apply
```

### 3. 同 SPU 同数量不同颜色用序号区分

EN 生成的 TJ# 会折叠为 `TJ#KS0483x1_KS0483x1-001/002/003`，名称中区分颜色；实际编号以创建前 preview 为准。

### 4. 阶段记录

`deep_sofa_stage.py plan / status / record` 生成 `深卧单人沙发椅阶段记录.xlsx`。

## Why This Matters

双色组合是“同 SPU 多变体”的另一形态：不能只按基码建一个套件，必须按登记表颜色列逐一映射 EN 变体，并确保客户物料号使用真实通途SKU。

## When to Apply

- 登记表已有通途SKU，但需要双色/多色组合。
- 需要按颜色中文名映射 EN 变体并记录阶段。

## Examples

2026-08-21 深卧单人沙发椅全量完成：

- 3 个 EN Product Bundle：`TJ#KS0483x1_KS0483x1-001/002/003`。
- 3 个真实通途SKU 全部登记到 EN 上层 Item `customer_items.ref_code`。
- 3 个赛狐组合商品全部创建并回读，`sync-combos` 结果 `input_en=3 / output_rows=3 / ok=3`。
- 阶段记录 Excel：`深卧单人沙发椅阶段记录.xlsx`，3/3 完成。

## Related

- [软包墙围 EN 套件 / 赛狐组合商品批量分阶段创建](soft-wall-combo-batch-staging.md)
- [可组合扶手沙发双子件套件批量创建](combinable-sofa-combo-batch-staging.md)
- [EN 套件 / 赛狐组合商品操作手册](../../../SELLFOX_API/docs/reference/combo-ops.md)
