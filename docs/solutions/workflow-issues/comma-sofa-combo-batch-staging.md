---
okf: v0.1
type: Reference
title: 逗号组合沙发三模块组合套件批量创建
date: 2026-08-22
category: workflow-issues
module: SELLFOX_API
problem_type: workflow_issue
component: development_workflow
severity: medium
applies_when:
  - "登记表‘无捆绑SKU’但套件列描述左扶手/右扶手/靠背组合"
  - "多模块组合需要按 EN 预览规范化顺序合成唯一通途SKU"
tags: [sellfox, combo, product-bundle, tj, comma-sofa, modular-sofa, synthetic-sku, customer-items]
---

# 逗号组合沙发三模块组合套件批量创建

## Context

`未配对产品登记表0821.xlsx` 中 `逗号组合沙发` 有 2 个组合，通途SKU 均为 `无捆绑SKU`：

- 逗号组合沙发-灰黄色
- 逗号组合沙发-蓝

套件列组成：`左扶手 + 右扶手 + 靠背`，各 1 个。

EN 底层模块：

- 右扶手：`KS0369-SZSRB-76x90x66-GRAYISHYELLOW` / `KS0369-MDR-76x90x66-BLUE`
- 靠背：`KS0378-SZSRB-76x90x66-GRAYISHYELLOW` / `KS0378-MDR-76x90x66-BLUE`
- 左扶手：`KS0379-SZSRB-76x90x66-GRAYISHYELLOW` / `KS0379-MDR-76x90x66-BLUE`

## Guidance

### 1. EN 预览会按右扶手、靠背、左扶手规范化编号

`en-preview` 返回 `TJ#KS0369x1_KS0378x1_KS0379x1-001/002`。创建命令按同一顺序传 child，阶段脚本 `comma_sofa_stage.py` 的合成通途SKU 也按此顺序生成。

### 2. 合成通途SKU

```text
{右扶手基码}x1_{靠背基码}x1_{左扶手基码}x1
```

示例：

- 灰黄：`TT0031230K0064049x1_TT0031230K0064052x1_TT0031230K0064055x1`
- 蓝：`TT0031230K0064047x1_TT0031230K0064050x1_TT0031230K0064053x1`

### 3. 批量流程

```bash
cd SELLFOX_API
uv run --project .. python soft_wall_lookup.py --product 逗号组合沙发 --out 数据源/逗号组合沙发快照_20260821.json
uv run --project .. python comma_sofa_stage.py plan
uv run --project .. python sellfox_combo_ops.py en-create --child ... --apply
uv run --project .. python sellfox_combo_ops.py register-customer-code --sku ... --ref-code ... --apply
uv run --project .. python sellfox_combo_ops.py sync-combos --sku ... --apply
uv run --project .. python comma_sofa_stage.py record --sku ... --complete
```

## Why This Matters

- EN 服务端会对多模块 child 顺序规范化，合成客户码若按登记表原始顺序，后续按 TJ# 反查会不一致。
- 无捆绑SKU 批次必须合成唯一客户码，拿到真实通途SKU 后按行替换。

## Examples

2026-08-22 逗号组合沙发完成：

- EN Product Bundle：`TJ#KS0369x1_KS0378x1_KS0379x1-001`（灰黄）、`-002`（蓝）。
- 客户物料号：两个合成通途SKU 均已登记并回读。
- 赛狐组合 ID：`3924081`、`3924082`，`sync-combos` 结果 `ok=2`。
- 阶段记录 Excel：`逗号组合沙发阶段记录.xlsx`，2/2 完成。

## Related

- [可组合扶手沙发双子件套件批量创建](combinable-sofa-combo-batch-staging.md)
- [拉链款 EN 套件 / 赛狐组合商品批量创建](zipper-combo-batch-staging.md)
- [EN 套件 / 赛狐组合商品操作手册](../../../SELLFOX_API/docs/reference/combo-ops.md)
