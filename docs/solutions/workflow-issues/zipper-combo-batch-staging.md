---
okf: v0.1
type: Reference
title: 拉链款 EN 套件 / 赛狐组合商品批量创建（无捆绑SKU 合成客户物料号）
date: 2026-08-21
category: workflow-issues
module: SELLFOX_API
problem_type: workflow_issue
component: development_workflow
severity: high
applies_when:
  - "登记表里整批产品通途SKU 为“无捆绑SKU”，但需要提前建 EN 套件与赛狐组合"
  - "同一面料/颜色基码被 PP棉与海绵等多个成品共用，需要保证合成客户物料号唯一"
  - "需要按登记表名称自动匹配 EN 底层物料并分阶段创建"
tags: [sellfox, combo, product-bundle, tj, zipper, synthetic-sku, customer-items]
---

# 拉链款 EN 套件 / 赛狐组合商品批量创建

## Context

`未配对产品登记表0821.xlsx` 中 `拉链款` 共 41 行，通途SKU 全部是 `无捆绑SKU`。产品覆盖 `弧形海绵靠枕-拉链款`（KS0342）与 `弧形PP棉靠枕-拉链款`（KS0340）两类填充，面料为荷兰绒/涤麻，颜色 15 种，按 2/3/4 件装出售，去重后共 40 个唯一组合。

EN 底层变体和赛狐底层 SKU 都存在，但没有任何现成套件；同时多个颜色共用 `Curve-Pillow-50-PPCotton` 等通用基码，不能只靠“基码+数量”合成唯一客户物料号。

## Guidance

### 1. 登记表名称自动匹配 EN 底层物料

按 `填充(海绵/PP棉) + 面料(荷兰绒/涤麻) + 颜色 + 尺寸(50x22x55)` 解析登记表名称，与 EN 快照里的变体 `item_name` 匹配；只纳入 `variant_of` 非空且物料组不是配套物料的成品变体。

### 2. 合成通途SKU 必须唯一

推荐规则：

```text
{基码}-{EN物料码}-{数量}pcs
```

示例：

- `TT0031183K0063912-KS0342-HLR-50-COCOAHAZELNUT-2pcs`
- `Curve-Pillow-50-PPCotton-KS0340-DM-50-DEEPBLUE-3pcs`

加入 EN 物料码后，即使多个颜色共用 `Curve-Pillow-50-PPCotton`，也不会撞 SKU。

### 3. 基码来源必须记录

阶段表备注记录基码来源：

- `直接基码`：EN Item 已有非 `-Cover/-Foam` 客户码。
- `-Cover去尾`：EN Item 只有 `-Cover/-Foam` 码，去掉尾缀得到基码。
- `同款另一填充借用`：该变体没有基码，借用同面料/颜色/尺寸的另一填充成品基码。

### 4. 批量流程

```bash
cd SELLFOX_API
uv run --project .. python soft_wall_lookup.py --product 拉链款 --out 数据源/拉链款快照_20260821.json
uv run --project .. python zipper_stage.py plan
uv run --project .. python zipper_stage.py status
uv run --project .. python zipper_stage.py apply --only "SKU1,SKU2"   # dry-run
uv run --project .. python zipper_stage.py apply --apply              # 用户确认后
```

`apply` 每行仍走 EN Product Bundle → 客户物料号登记 → 赛狐组合创建 → 回读断言，并把结果写回 `拉链款阶段记录.xlsx`。

## Why This Matters

- 全部 `无捆绑SKU` 的批次若不合成唯一码，多个颜色/填充会共用同一个客户物料号，EN 全局唯一校验会拦截或导致订单导入错配。
- 合成规则里保留 EN 物料码，可以让后续拿到真实通途SKU 时按行精确替换，不需要反查整张表。
- 阶段记录 xlsx 是 40 行进度的唯一事实，断点续跑和多 Agent 交接都读同一份文件。

## When to Apply

- 登记表某产品族整批 `无捆绑SKU`，且底层 EN/赛狐成品已存在。
- 同一基码被多个成品共用，需要保证合成客户物料号唯一。
- 需要先测试 3 个、再全量创建的分阶段上线。

## Examples

2026-08-21 拉链款全量完成：

- 40 个 EN Product Bundle：`TJ#KS0342x2/3/4-001~004`、`TJ#KS0340x2-001~010`、`TJ#KS0340x3-001~009`、`TJ#KS0340x4-001~009`。
- 40 个合成通途SKU 全部登记到对应 EN 上层 Item `customer_items.ref_code`。
- 40 个赛狐组合商品全部创建并回读，`sync-combos` 结果 `input_en=40 / output_rows=40 / ok=40`，无 `unmatched`。
- 阶段记录 Excel：`拉链款阶段记录.xlsx`，40/40 完成。

## Related

- [软包墙围 EN 套件 / 赛狐组合商品批量分阶段创建](soft-wall-combo-batch-staging.md)
- [赛狐组合商品/套件 SKU 创建与配对工作流](../conventions/sellfox-combo-sku-create-pairing-workflow.md)
- [EN 套件 / 赛狐组合商品操作手册](../../../SELLFOX_API/docs/reference/combo-ops.md)
- [通途有库存 SKU 三方主线补齐惯例](../conventions/tongtu-en-sellfox-instock-sku-mainline.md)
