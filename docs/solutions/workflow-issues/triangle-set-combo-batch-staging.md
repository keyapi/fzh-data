---
okf: v0.1
type: Reference
title: 三角有扣套装（三角靠枕 + 50cm 圆枕）组合批量创建
date: 2026-08-22
category: workflow-issues
module: SELLFOX_API
problem_type: workflow_issue
component: development_workflow
severity: medium
applies_when:
  - "登记表套装名称为‘三角有扣 … 靠枕 + N个50cm圆枕套装’"
  - "EN 底层是三角靠枕 KS0001-* 与三角带圆柱靠枕 KS0260-*-50-*"
tags: [sellfox, combo, product-bundle, tj, triangle-pillow, KS0001, KS0260, synthetic-sku, customer-items]
---

# 三角有扣套装（三角靠枕 + 50cm 圆枕）组合批量创建

## Context

`未配对产品登记表0821.xlsx` 中 `三角有扣` 套装共 13 行，均为 `三角靠枕 + 1/2 个 50cm 圆枕`：

- 8 行有真实通途SKU（如 `TT0001325K0010860-all-T50`）。
- 5 行为 `无捆绑SKU`，需合成客户码。

EN 底层命名与登记表不同：登记表 `三角有扣` 对应 EN `三角靠枕`（KS0001 模板），50cm 圆枕对应 `三角带圆柱靠枕-圆柱`（KS0260 模板）。

## Guidance

### 1. 名称映射

按 `面料（涤麻/全涤宽条绒/荷兰绒）+ 颜色（黄色/白色/桃色/米白色/草绿色）+ 尺寸cm + 圆枕数量` 解析登记表名称，与 EN 变体匹配：

- 三角靠枕：`KS0001-{面料}-{尺寸}-{颜色}`。
- 50cm 圆枕：`KS0260-{面料}-50-{颜色}`。

### 2. 已确认的近似规则

- 登记表 `138CM 草绿色`：EN 无 138cm，使用 `KS0001-DM-140-GRASSGREEN` 近似。
- 全涤宽条绒（白/桃）套装：EN 无全涤宽条绒 50cm 圆枕，使用同色条绒款 `KS0260-TR-50-OFFWHITE / PEACH`。

### 3. 无捆绑SKU 合成客户码

```text
{三角靠枕EN物料码}x1_{圆枕EN物料码}x{数量}
```

示例：`KS0001-DM-153-YELLOWx1_KS0260-DM-50-YELLOWx2`。拿到真实通途SKU 后按行替换。

### 4. 批量流程

```bash
cd SELLFOX_API
uv run --project .. python triangle_set_stage.py plan
uv run --project .. python triangle_set_apply.py            # dry-run 预览
uv run --project .. python triangle_set_apply.py --apply    # 用户确认后
```

`triangle_set_apply.py` 逐行执行 EN Product Bundle 创建 → 客户物料号登记 → 赛狐组合创建 → 回读断言，并把结果写回 `三角有扣阶段记录.xlsx`。

## Why This Matters

- 登记表产品名与 EN 物料名不一致，必须先做名称/变体映射，不能直接拿登记表名创建。
- 138cm 与圆枕面料近似是业务决定，阶段记录备注保留依据，避免后续误判。

## Examples

2026-08-22 三角有扣套装完成：

- 13 个 EN Product Bundle：`TJ#KS0001x1_KS0260x1-001~003`、`TJ#KS0001x1_KS0260x2-001~010`。
- 13 个客户物料号（8 真实 + 5 合成）全部登记并回读。
- 13 个赛狐组合全部创建并回读，ID `3924083` ~ `3924095`。
- 阶段记录 Excel：`三角有扣阶段记录.xlsx`，13/13 完成。

## Related

- [逗号组合沙发三模块组合套件批量创建](comma-sofa-combo-batch-staging.md)
- [软包墙围 EN 套件 / 赛狐组合商品批量分阶段创建](soft-wall-combo-batch-staging.md)
- [EN 套件 / 赛狐组合商品操作手册](../../../SELLFOX_API/docs/reference/combo-ops.md)
