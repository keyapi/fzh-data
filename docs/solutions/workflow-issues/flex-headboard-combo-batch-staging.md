---
okf: v0.1
type: Reference
title: 灵活拼接床头板 EN 套件 / 赛狐组合商品批量创建
date: 2026-08-21
category: workflow-issues
module: SELLFOX_API
problem_type: workflow_issue
component: development_workflow
severity: medium
applies_when:
  - "登记表某产品族只有单一变体、多个数量档，且通途SKU 为“无捆绑SKU”"
  - "需要按既有合成规则提前登记客户物料号并批量创建组合"
tags: [sellfox, combo, product-bundle, tj, headboard, synthetic-sku, customer-items]
---

# 灵活拼接床头板 EN 套件 / 赛狐组合商品批量创建

## Context

`未配对产品登记表0821.xlsx` 中 `灵活拼接床头板` 共 12 行，全部为 `无捆绑SKU`，实际只有 1 个 EN 底层变体：

- `KS0453-OMR-60x30x20-WHITEMEDIUMGRAY`
- 基码 `TT0312608K0064211`（EN 直接登记）
- 赛狐底层 ID `3702320`

数量档为 3/4/5/6，去重后共 4 个唯一组合。

## Guidance

与拉链款相同，合成通途SKU 规则为：

```text
{基码}-{EN物料码}-{数量}pcs
```

示例：

- `TT0312608K0064211-KS0453-OMR-60x30x20-WHITEMEDIUMGRAY-3pcs`
- `TT0312608K0064211-KS0453-OMR-60x30x20-WHITEMEDIUMGRAY-6pcs`

批量流程复用阶段框架：

```bash
cd SELLFOX_API
uv run --project .. python soft_wall_lookup.py --product 灵活拼接床头板 --out 数据源/灵活拼接床头板快照_20260821.json
uv run --project .. python flex_headboard_stage.py plan
uv run --project .. python flex_headboard_stage.py status
uv run --project .. python flex_headboard_stage.py apply --apply
```

## Why This Matters

单一变体多数量档的批次不需要复杂的名称解析，但仍要保证合成客户物料号唯一、阶段记录可续跑，并沿用既有 `基码-EN物料码-Npcs` 规范，避免同类批次各自发明规则。

## When to Apply

- 登记表某个产品族只有 1-2 个变体、多个数量档。
- 通途SKU 缺失但用户已确认提前登记合成客户物料号。

## Examples

2026-08-21 灵活拼接床头板全量完成：

- 4 个 EN Product Bundle：`TJ#KS0453x3/4/5/6-001`。
- 4 个合成通途SKU 全部登记到 EN 上层 Item `customer_items.ref_code`。
- 4 个赛狐组合商品全部创建并回读，`sync-combos` 结果 `input_en=4 / output_rows=4 / ok=4`。
- 阶段记录 Excel：`灵活拼接床头板阶段记录.xlsx`，4/4 完成。

## Related

- [软包墙围 EN 套件 / 赛狐组合商品批量分阶段创建](soft-wall-combo-batch-staging.md)
- [拉链款 EN 套件 / 赛狐组合商品批量创建](zipper-combo-batch-staging.md)
- [EN 套件 / 赛狐组合商品操作手册](../../../SELLFOX_API/docs/reference/combo-ops.md)
