---
okf: v0.1
type: Reference
title: 通途分公司国外加工成本：BOM 理论、财务系数与 GS 基础/系数列
description: 用固定 1104 BOM 计算 USNJ/USTX/PL 国外加工理论值，按分公司套 1.0/1.2/1.6 系数，并区分 GS 基础列与 *系数列
date: 2026-11-18
category: architecture-patterns
module: tongtool_order_cost
problem_type: architecture_pattern
component: tooling
severity: high
applies_when:
  - "老板/财务要求分公司实际费用与 BOM 理论国外加工成本对比"
  - "需要在 GS 订单表区分 BOM 理论列和乘系数后的定价列"
  - "新增美国本地采购/包装产品（如棉包）或整套/组件拆分产品"
tags: [tongtool, branch, processing-cost, coefficient, bom, gs, us-local]
related_components: [tongtool_order_cost, erpnext, google-sheets]
---

# 通途分公司国外加工成本：BOM 理论、财务系数与 GS 基础/系数列

## Context

2026-11 老板/财务要求用 **BOM 成本表**计算 USNJ（美东）、USTX（美中）、波兰三个分公司的「国外加工成本」理论值，与财务实际费用对比，并在一段时间内用固定系数调整，便于运营定价。

固定口径是 **2026-11-04 BOM 成本表**（`bom_cost_product_with_disabled.csv`，2,358 行）；只新增 KS0050 棉包 6 行，原行零修改。原始版与加棉包版都留档。

## Guidance

### 1. 理论值

```
分公司国外加工成本 = Σ（二次加工成本[元/件] × 发货数量）
```

- 分公司用 **`发货仓按销售汇总分类`** 拆：`USNJ分公司` / `USTX分公司` / `波兰分公司`；
- **不要**用 `成本来源编码` 或 `对应成本工作簿` 拆 USNJ/USTX——两者都是 `COST-US` / 美国公司；
- 美国海外仓（大件云仓）是第三方，零成本，不计入三个分公司；
- GS 里 `二次加工成本` 是单位成本，手工验证必须乘 `发货数量`（或 `发货数量` 已为组 pieces 的 merged 行）。

202607-202610 理论值（1104+棉包）：

| 月 | USNJ | USTX | 波兰 | 合计 |
|---|---:|---:|---:|---:|
| 07 | 774,863.19 | 463,126.77 | 122,626.00 | 1,360,615.96 |
| 08 | 738,919.45 | 573,826.90 | 167,617.98 | 1,480,364.33 |
| 09 | 407,885.27 | 309,834.82 | 155,674.84 | 873,394.93 |
| 10 | 394,097.39 | 293,100.92 | 190,844.37 | 878,042.68 |
| 合计 | 2,315,765.30 | 1,639,889.41 | 636,763.19 | 4,592,417.90 |

### 2. 财务系数

- 计算比例 = 实际 / 理论：USNJ 0.775581852、USTX 1.184762040、PL 1.902793322（仅留档，下一轮调整参考）；
- **本期执行系数（老板/ZJ 2026-11-17）**：USNJ **1.0**、USTX **1.2**、PL **1.6**，生效 202607-202610；
- 记录在 `config/branch_processing_coefficient_policy.csv`；原始实际/理论在 `config/branch_processing_coefficients.csv` 与 `docs/reference/branch-processing-coefficients-202607-202610.md`；
- 系数只改 `二次加工成本系数`；绍兴成本系数保持历史值，绍兴二次系数本期=1；FBA 行=1。

### 3. GS 列：基础 vs *系数

- **不带 `*系数`**：BOM 理论值，只作对账/审计，不乘系数；
- **3 个输入系数**：`绍兴成本系数`、`二次加工成本系数`、`绍兴二次加工成本系数`；
- **15 个 `*系数` 派生列**：由基础成本 × 对应系数计算；
- `订单总成本*系数/订单利润*系数` 是校准口径；尾程、头程、海外仓**不乘系数**。

### 4. 美国本地产品（棉包 KS0050）

- 产品物料**不建 BOM**（`cost_fg=0`）；`USNJBZCP#/USTXBZCP#KS0050-<尺寸>` BOM = PP 棉 kg × 美国采购价 + 5 分钟 × 16.607 元/h；
- 物料组 `棉包` 发货类型=成品；报告按 `custom_model_id + 尺寸` 取 valuation；
- 引擎例外：`成品 + cost_fg=0 + 绍兴=0 + 目的地 valuation>0 → 二次加工=valuation`；其他情况不改，避免把“缺失成本”误判为本地成本；
- 审计统计：`phase2_us_local_rows`。

### 5. 整套/组件（KS0405 含脚凳）

- `TT0312566K0064133-All` 是整套，KS0405 已含脚凳；同单出现 `TT0312566K0064133-2` 时登记在 `config/whole_component_relations.csv`；
- 组件行四列/头程=0，仅保留实际尾程；不改 `product_id`、不触发合并；
- 若将来脚凳单独销售，需单独处理（KS0530 BOM 仍缺）。

### 6. 已知未决

- 16 行皮壳商品的目的地 BOM 缺失、加工暂 0（星球/石头/圆滚/地板枕套装等）；系数仍应视为 provisional；
- 10 月源表新增 `补发费用` 列（24 行/5,832.70），仅保留展示，不计入成本。

## Why This Matters

- 同一份 GS 里同时存在理论口径和系数口径；混淆“二次加工成本单位列”和“金额”会直接算错系数；
- USNJ/USTX 在 `成本来源编码` 层面不可区分，用错列会把两个系数混在一起；
- 只有显式登记整套/组件、美国本地产品，才能避免“缺 BOM = 0”与“整套重复计头程”两类错误。

## When to Apply

- 财务/老板要求分公司成本系数或调整定价；
- 月度 GS 写回后，需要手工复核理论值；
- 新增美国本地采购/包装 SKU、整套拆分 SKU。

## Examples

7 月 GS merged 手工验证：

```
二次加工金额 = 二次加工成本 × 发货数量
=SUMPRODUCT(($G:$G="USTX分公司")*$X:$X*$S:$S)
→ 463,126.77
```

## Related

- `docs/reference/branch-processing-coefficients-202607-202610.md`
- `docs/reference/cost-engine-spec/32-phase2-bom-cost-policy.md`
- `docs/reference/build-order-tabs.md`
- `docs/solutions/workflow-issues/tongtu-multicolor-cover-shared-foam-attribution.md`
