---
okf: v0.1
type: Reference
title: 户外托盘垫套装组合批量创建
date: 2026-08-21
category: workflow-issues
module: SELLFOX_API
problem_type: workflow_issue
component: development_workflow
severity: high
applies_when:
  - "登记表名称带“套装”但套件列为空，需要按套装规格确认组成"
  - "四模块坐垫套装需要按 120x60 / 120x80 区分转角垫尺寸"
tags: [sellfox, combo, product-bundle, tj, outdoor-pad, four-module, customer-items]
---

# 户外托盘垫套装组合批量创建

## Context

`未配对产品登记表0821.xlsx` 中 `户外托盘垫` 有 6 个唯一套装（3 色 × 2 尺寸），通途SKU 已存在：

- 深蓝 120x60 / 120x80：`TT0312635K0064265-ALL` / `TT0312635K0064268-ALL`
- 深灰 120x60 / 120x80：`TT0312636K0064266-ALL` / `TT0312636K0064269-ALL`
- 米白 120x60 / 120x80：`TT0312637K0064264-ALL` / `TT0312637K0064267-ALL`

登记表“套件”列为空，名称只写 120x60 / 120x80；经用户确认，套装组成按坐垫尺寸区分：

- 120x60 套装 = 坐垫 120x60 + 靠背 120x40 + 转角垫 40x40 + 装饰方靠枕 40x40
- 120x80 套装 = 坐垫 120x80 + 靠背 120x40 + 转角垫 60x40 + 装饰方靠枕 40x40

## Guidance

### 1. 名称只给坐垫尺寸时，先确认转角垫规格

同一系列存在 `40x40` 与 `60x40` 两种转角垫；120x60 套装用 `40x40`，120x80 套装用 `60x40`。确认前不要盲建。

### 2. 四模块 child 固定顺序

```bash
uv run --project .. python sellfox_combo_ops.py en-create \
  --child "KS0459-KLM-120x60x16-DEEPBLUE:1" \
  --child "KS0460-KLM-120x40x12-DEEPBLUE:1" \
  --child "KS0461-KLM-40x40x12-DEEPBLUE:1" \
  --child "KS0462-KLM-40x40x20-DEEPBLUE:1" \
  --apply
```

### 3. 通途SKU 直接登记

`-ALL` 后缀的真实通途SKU 直接作为 EN 上层 Item `customer_items.ref_code`，不需要合成新码。

### 4. 阶段记录

`outdoor_pad_stage.py plan / status / record` 生成 `户外托盘垫阶段记录.xlsx`。

## Why This Matters

“套装”名称只反映坐垫尺寸，但转角垫有两种规格；如果不确认组成就创建，会出现转角垫尺寸错误且难以批量修正。阶段记录把确认后的组成写进备注，后续可按 SKU 追溯。

## When to Apply

- 登记表名称含“套装”但套件列空。
- 同一系列存在多个转角/靠背规格，需要按坐垫尺寸推断。

## Examples

2026-08-21 户外托盘垫全量完成：

- 6 个 EN Product Bundle：`TJ#KS0459x1_KS0460x1_KS0461x1_KS0462x1-001~006`。
- 6 个真实通途SKU（`-ALL`）全部登记到 EN 上层 Item `customer_items.ref_code`。
- 6 个赛狐组合商品全部创建并回读，`sync-combos` 结果 `input_en=6 / output_rows=6 / ok=6`。
- 阶段记录 Excel：`户外托盘垫阶段记录.xlsx`，6/6 完成。

## Related

- [复古造型大体量沙发四模块组合套件创建](retro-sofa-combo-batch-staging.md)
- [可组合扶手沙发双子件套件批量创建](combinable-sofa-combo-batch-staging.md)
- [EN 套件 / 赛狐组合商品操作手册](../../../SELLFOX_API/docs/reference/combo-ops.md)
