---
okf: v0.1
type: Reference
title: 可组合扶手沙发双子件套件批量创建
date: 2026-08-21
category: workflow-issues
module: SELLFOX_API
problem_type: workflow_issue
component: development_workflow
severity: high
applies_when:
  - "组合商品由多个不同底层模块组成，需要按组成生成唯一通途SKU"
  - "登记表“无捆绑SKU”但套件列描述了扶手/靠背模块数量"
tags: [sellfox, combo, product-bundle, tj, modular-sofa, synthetic-sku, customer-items]
---

# 可组合扶手沙发双子件套件批量创建

## Context

`未配对产品登记表0821.xlsx` 中 `可组合扶手沙发` 有 4 个有效组合，全部为“无捆绑SKU”：

- 2 扶手模块拼接
- 2 扶手模块 + 1 靠背模块
- 2 扶手模块 + 2 靠背模块
- 3 扶手模块 + 1 靠背模块

EN 底层物料：

- 扶手模块 `KS0245-DM-75-DEEPGREY`（基码 `TT0031091K0063443`，赛狐 ID `3702373`）
- 靠背模块 `KS0246-DM-75-DEEPGREY`（基码 `TT0031092K0063444`，赛狐 ID `3702681`）

## Guidance

### 1. 双子件合成通途SKU

镜像 TJ# 组成命名：

```text
{扶手基码}x{数量}_{靠背基码}x{数量}
```

示例：

- `TT0031091K0063443x2`
- `TT0031091K0063443x2_TT0031092K0063444x1`
- `TT0031091K0063443x2_TT0031092K0063444x2`
- `TT0031091K0063443x3_TT0031092K0063444x1`

### 2. 创建命令用多 child

```bash
cd SELLFOX_API
uv run --project .. python sellfox_combo_ops.py en-create \
  --child "KS0245-DM-75-DEEPGREY:2" \
  --child "KS0246-DM-75-DEEPGREY:1" \
  --apply
uv run --project .. python sellfox_combo_ops.py register-customer-code \
  --sku "TJ#KS0245x2_KS0246x1-001" \
  --ref-code "TT0031091K0063443x2_TT0031092K0063444x1" \
  --apply
uv run --project .. python sellfox_combo_ops.py sync-combos --sku "TJ#KS0245x2_KS0246x1-001" --apply
```

### 3. 阶段记录

`combinable_sofa_stage.py plan / status / record` 生成 `可组合扶手沙发阶段记录.xlsx`，备注保留登记表“套件”列原始组成描述。

## Why This Matters

多模块组合不能沿用单底层 `基码-EN物料码-Npcs` 规则；按 `基码x数量_基码x数量` 合成才能唯一表达组成，并且与 EN 生成的 TJ# 组成一一对应，后续拿到真实通途SKU 也能按行替换。

## When to Apply

- 组合由多个不同 EN 成品模块组成。
- 登记表“套件”列已描述模块数量，但通途SKU 缺失。

## Examples

2026-08-21 可组合扶手沙发全量完成：

- 4 个 EN Product Bundle：`TJ#KS0245x2-001`、`TJ#KS0245x2_KS0246x1-001`、`TJ#KS0245x2_KS0246x2-001`、`TJ#KS0245x3_KS0246x1-001`。
- 4 个合成通途SKU 全部登记到 EN 上层 Item `customer_items.ref_code`。
- 4 个赛狐组合商品全部创建并回读，`sync-combos` 结果 `input_en=4 / output_rows=4 / ok=4`。
- 阶段记录 Excel：`可组合扶手沙发阶段记录.xlsx`，4/4 完成。

## Related

- [软包墙围 EN 套件 / 赛狐组合商品批量分阶段创建](soft-wall-combo-batch-staging.md)
- [拉链款 EN 套件 / 赛狐组合商品批量创建](zipper-combo-batch-staging.md)
- [灵活拼接床头板 EN 套件 / 赛狐组合商品批量创建](flex-headboard-combo-batch-staging.md)
- [沙发支撑垫存量 EN 套件补齐](support-pad-combo-reconcile.md)
- [EN 套件 / 赛狐组合商品操作手册](../../../SELLFOX_API/docs/reference/combo-ops.md)
