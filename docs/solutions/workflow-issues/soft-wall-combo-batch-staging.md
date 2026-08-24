---
okf: v0.1
type: Reference
title: 软包墙围 EN 套件 / 赛狐组合商品批量分阶段创建
date: 2026-08-21
category: workflow-issues
module: SELLFOX_API
problem_type: workflow_issue
component: development_workflow
severity: high
applies_when:
  - "登记表里大量同类产品需要分阶段创建 EN Product Bundle 与赛狐组合商品"
  - "同一底层 SPU 有多个面料/颜色/尺寸变体且每种数量档都要组合"
  - "需要记录每批 EN/客户物料号/赛狐的完成进度和回读结果"
tags: [sellfox, combo, product-bundle, tj, batch, staging, customer-items]
---

# 软包墙围 EN 套件 / 赛狐组合商品批量分阶段创建

## Context

`未配对产品登记表0821.xlsx` 里 `软包墙围` 有 6 个底层成品变体，每个变体可能按 4/6/9/12 件装出售。业务希望先测试创建 3 个，再批量补齐，并且每一行的 EN 套件、完整通途SKU 客户物料号、赛狐组合商品都要能回读验证、可续跑、可追溯。

EN 侧之前已有单条套件工作流（`sellfox_combo_ops.py en-create` + `sync-combos`），但没有“从登记表生成计划、分阶段批量执行、写阶段记录、客户物料号登记”的闭环；`create_support_pad_kits.py` 只覆盖固定两个垫子套件，不能复用。

## Guidance

### 1. 以“完整通途SKU”为批次主键

登记表里同一 ASIN 会跨店铺/国家重复出现，必须按完整通途 SKU 去重；`-pcs` 后缀大小写不统一时按小写 `pcs` 归一（如 `TT0031084K0063340-12PCS` 与 `-12pcs` 视为同一个客户物料号）。

### 2. 先建 6×4 全量计划，再分阶段 apply

`soft_wall_stage.py plan --full` 会生成 6 底层物料 × 4 数量 = 24 行阶段记录，并把登记表已有行与合成补齐行合并：

```bash
cd SELLFOX_API
uv run --project .. python soft_wall_stage.py plan --full
uv run --project .. python soft_wall_stage.py status
```

### 3. 每行固定三步写入

1. `en-create --child "KS0211-...:12" --apply`：EN Product Bundle，body 只传 `items`，服务端生成 `TJ#KS0211x12-NNN`。
2. `register-customer-code --sku TJ#... --ref-code TT... --apply`：把完整通途SKU 登记到上层 Item `customer_items.ref_code`，只追加，写入后回读。
3. `sync-combos --sku TJ#... --apply`：创建赛狐组合 SKU（`fullCid=428697-`，`isGroup=1`），创建后回读 `childSkus`。

批量版把三步串成一条命令：

```bash
uv run --project .. python soft_wall_stage.py apply --only "SKU1,SKU2" --apply
```

不传 `--apply` 时是 dry-run，只预览 EN 编号并写“已预览”。

### 4. 序号不是固定值

同一 `KS0211` 同数量下，不同面料/颜色/尺寸变体会被分配从 `-001` 到 `-006` 的序号。批量前统一预览会出现多个 `-001`，这是正常现象；`apply` 会在每行创建前重新预览，实际按创建顺序生成真实序号，并把编号写回阶段表。

### 5. 阶段记录 Excel 是唯一进度事实

`SELLFOX_API/数据源/软包墙围阶段记录.xlsx` 每行记录：通途SKU、数量、底层EN物料、赛狐底层ID、预计/实际 TJ#、EN结果、客户物料号结果、赛狐结果、完成时间、备注。`status` 命令按该文件汇总，不要把登记表源文件当成进度。

### 6. 大小写边界

EN 历史上有“先区分大小写、后改不区分”的演进，不确定所有匹配路径是否都已改完。因此新登记统一用小写 `pcs`；已存在的历史大写登记保留。上线后应做一次只读审计，验证销售订单导入/PIM 映射对大小写不敏感，必要时把历史大写统一规范。

## Why This Matters

- 以登记表源文件当进度会丢状态；阶段记录 xlsx + `status` 让断点续跑和多人/多 Agent 交接都只看一份事实。
- 客户物料号不登记在 EN 上层 Item 上，通途订单导入就找不到套件，最终会退回错误配对。
- 序号按创建顺序分配，若批量 apply 前把预览编号当最终编号写死，会污染阶段表和后续对账。

## When to Apply

- 登记表里“一个 SPU、多种数量档、多个变体”的套件批量创建。
- 需要先测试几个、再全量补齐的分阶段上线。
- 需要给技术同事或后续 Agent 一份可续跑的进度记录。

## Examples

2026-08-21 软包墙围全量 24 个组合完成：

- EN Product Bundle：`TJ#KS0211x4/6/9/12-001~006`，共 24 个。
- 每个 EN 上层 Item 均登记完整通途SKU 客户物料号（新补齐统一小写 `pcs`）。
- 赛狐组合商品 24 个全部创建并回读，`sync-combos` 结果 `input_en=24 / output_rows=24 / ok=24`，无 `unmatched`。
- 阶段记录 Excel 24/24 完成。

## Related

- [赛狐组合商品/套件 SKU 创建与配对工作流](../conventions/sellfox-combo-sku-create-pairing-workflow.md)
- [EN 套件 / 赛狐组合商品操作手册](../../../SELLFOX_API/docs/reference/combo-ops.md)
- [通途有库存 SKU 三方主线补齐惯例](../conventions/tongtu-en-sellfox-instock-sku-mainline.md)
- [SELLFOX_API Agent 交接](../../../SELLFOX_API/AGENT_HANDOFF.md)
