---
okf: v0.1
type: Reference
title: 沙发支撑垫存量 EN 套件补齐（客户物料号 + 赛狐组合）
date: 2026-08-21
category: workflow-issues
module: SELLFOX_API
problem_type: workflow_issue
component: development_workflow
severity: medium
applies_when:
  - "EN Product Bundle 已存在但上层 Item 缺少通途客户物料号"
  - "EN 套件已存在但赛狐组合商品缺失，需要只补赛狐"
  - "登记表名称与实际通途基码颜色不一致，需要按基码判定"
tags: [sellfox, combo, product-bundle, tj, support-pad, customer-items, reconcile]
---

# 沙发支撑垫存量 EN 套件补齐

## Context

`未配对产品登记表0821.xlsx` 中 `沙发支撑垫` 共 3 行，对应两个 EN 底层变体：

- `KS0156-NYBDSFH-52x52x5-BLACK`（基码 `TT0031038K0062927`）
- `KS0156-NYBDSFH-52x52x8-BLACK`（基码 `TT0031038K0064291`）

EN 套件 `TJ#KS0156x2-001`、`TJ#KS0156x3-001`、`TJ#KS0156x3-002` 已存在，但三个上层 Item 都没有客户物料号；其中 52x52x5 的两个赛狐组合缺失，52x52x8 x3 的赛狐组合已存在。

## Guidance

### 1. 先读现状，不要盲建

用 `soft_wall_lookup.py --product 沙发支撑垫` 拉快照，确认：

- EN 已有 Product Bundle 名称与组成；
- 赛狐已有组合 ID 与 `childSkus`；
- 上层 Item `customer_items` 是否为空。

### 2. 只补缺失环节

- EN 已存在：跳过 `en-create`，直接用 `register-customer-code --apply` 补客户物料号。
- 赛狐缺失：用 `sync-combos --sku TJ#... --apply` 只创建赛狐组合。
- 赛狐已存在：`sync-combos` 应返回 `ok`，不要重复创建。

### 3. 名称与基码冲突按基码为准

登记表 52x52x5 的 2 件行写“深灰色”，但通途SKU `TT0031038K0062927-2PCS` 对应 EN 黑色变体；EN 也没有活跃的深灰 52x52x5 成品。处理为黑色，并在阶段表备注记录差异。

### 4. 阶段记录

```bash
cd SELLFOX_API
uv run --project .. python support_pad_stage.py plan
uv run --project .. python support_pad_stage.py status
```

记录字段与软包墙围/拉链款一致，SKU 统一小写 `pcs`。

## Why This Matters

存量套件补齐最怕“以为没有就重建”：EN 已有套件再 `en-create` 会重复，或生成错误序号。正确顺序是先快照对账，再按 EN/客户物料号/赛狐三列缺口分别补。

## When to Apply

- 登记表里出现历史已有 EN 套件的产品族。
- 只需补赛狐组合或客户物料号，不需要新建 EN Bundle。

## Examples

2026-08-21 沙发支撑垫完成：

- `TJ#KS0156x2-001`：补客户物料号，新建赛狐组合 `3922967`。
- `TJ#KS0156x3-001`：补客户物料号，新建赛狐组合 `3922968`。
- `TJ#KS0156x3-002`：补客户物料号，赛狐已存在 `3913600` 且一致。
- `sync-combos` 结果 `input_en=3 / output_rows=3 / ok=3`。

## Related

- [软包墙围 EN 套件 / 赛狐组合商品批量分阶段创建](soft-wall-combo-batch-staging.md)
- [拉链款 EN 套件 / 赛狐组合商品批量创建](zipper-combo-batch-staging.md)
- [灵活拼接床头板 EN 套件 / 赛狐组合商品批量创建](flex-headboard-combo-batch-staging.md)
- [EN 套件 / 赛狐组合商品操作手册](../../../SELLFOX_API/docs/reference/combo-ops.md)
