---
okf: v0.1
type: Reference
title: Phase 3 写回演练（本地，不写 GS；Phase 3.2）
description: 以现有写回表 166 列为合同模板，Phase1 合并明细作行集合、Phase2 单位成本填四列并补齐派生列；阻断/跳过留空；缺列按 (order_common,平台SKU) 映射；血缘与差异归因
date: 2026-11-04
module: tongtool_order_cost
tags: [cost, writeback, phase3, rehearsal, lineage, unit-cost]
---

# Phase 3 写回演练

> 落地：`tongtool_order_cost/tongtu_cost_engine/domain/writeback_rehearsal.py`；
> CLI：`uv run python -m tongtool_order_cost.tongtu_cost_engine.cli writeback-rehearsal ...`。
> **本地文件，不写 GS/EN。**

## 1. 输入与输出

- 模板：现有写回表 166 列（`out/writeback_YYYYMM.csv` 表头；输出 166 列 + 13 个血缘/标注列）。
- 行集合：Phase1 合并明细（合并组 1 行 + 透传原行），行数 = `rows_detail`。
- **四列为单位成本**：
  - 合并行 `per_unit = Phase2 组总成本 / pieces`；合并行 `发货数量 = pieces`；
  - 透传行 `per_unit = Phase2 行成本 / qty`；
  - 断言 `per_unit × cost_qty ≈ Phase2 合计`（容差 0.01）。
- 输出：`writeback_new_YYYYMM.csv/.xlsx/.md`（xlsx：汇总/写回行/差异归因/映射缺口/断言/阻断清单）。

## 2. 派生列（按合同补齐）

- `皮壳成本*数量`、`头程运费*数量`、`二次加工成本*数量`、`绍兴二次加工成本*数量` = 单位成本 × `cost_qty`。
- `1件产品成本` = 皮壳 + 绍兴二次 + 二次（**不含头程**，单位值）。
- `产品成本*数量` = `1件产品成本` × `cost_qty`。
- `订单总成本` = (四列单位成本 + `运费`单位成本) × `cost_qty`；`运费`不可得 → 留空并写 `订单总成本:运费未映射`。
- `订单利润` = 源行 `收入(人民币)` 之和 − `订单总成本`；收入/总成本不可得 → 留空并写 reason。
- 其余旧派生列（`*系数`、`1件产品成本*系数`、`海外仓成本`、`EN绍兴包装*成本` 等）仍留空，避免与 Phase2 口径打架。

## 3. 留空与映射

- `cost_status != ok` → **四列及派生列留空**，`cost_reason` / `derived_reason` 写原因；不沿用旧值、不填 0。
- 非成本列：优先原始订单（**同组任一源行有值即带出**）；缺列**按 `(order_common, 平台SKU_统一)`**
  从旧写回映射，冲突时回退精确 `(订单号, 通途SKU)`；产品级属性（产品发售日期/当月是否新品/件套）
  再按 `品类尺寸面料编码` 兜底。候选值唯一才填；仍冲突/无来源 → 留空并标注 `列:conflict|no_source`。
- **是否皮壳**：皮壳行 = `皮壳`，非皮壳行 = `否`（合同要求非空）。
- **method 兜底**：EN `shipping_method` 为空时，按 `SKU→Item→item_group→branch`（`item_group_branch.tsv`，branch 空则向上找祖先）取 `皮壳/半成品/成品`，标 `method_source=item_group_fallback`；无分支保持 pending。
- **非商品配件**：`BUTTONKIT*`、`PP<n>LB`、`DLZYFX001`、`COTTON-EU` → 四列显式 **0** + reason，不进入待审成本。
- **TJ# 套件（Phase 3.5 固化）**：
  - Product Bundle 带版本：`bundle_version = Product Bundle modified/creation + 子件 sha256前12`；缺版本 → pending。
  - `kit_method`：所有子件 BOM method 非空且完全一致 → 该 method；混合/空 → pending，不猜。
  - 计价仍按子件 BOM 求和（不新增成本列），`method_source=kit_bundle`。
  - 用 `bom_cost_product_with_kits.csv` 的套件行（cost_fg/cost_sxbzbcp/cost_sxbzcp/sx_cost_all/valuation）对账，
    任一差 >0.01 → `kit_report_mismatch` 阻断。
  - 同订单同时出现 TJ# 与子件行 → `kit_child_double_count` 双向阻断，禁止静默去重。
- **多件不同变体**：同产品多个整件/皮壳 SKU（如不同颜色）→ `split_products`，逐件计价，不强行合并。
- **同订单锚定（Phase 1）**：`-COVER` 别名同时命中 PPCotton/Foam 两条线时，用同订单组件行
  （`Curve-Pillow-50-PPCotton`→KS0340、`Curve-Pillow-50-Foam`→KS0342）锁定；两条线都在时按平台 SKU
  材质词/颜色词再区分，仍不唯一才阻断；Cover 与填充行 method 不一致时以非 Cover 行为准。
  202608 锚定 9 行、Phase3 阻断/跳过/空白 = **0/0/0**（非商品配件 14 行零成本除外）。
- **组件吸收**：通用海绵/PP棉行若同订单皮壳/成品行已定价且数量匹配 → `component_absorbed`，四列显式 0
  （成本已含在成品 BOM 内，避免重复计）。
- **运费**：旧写回映射优先；缺失时用原始订单 `包裹总运费 / cost_qty`（单位化）。
- **suffix**：原始订单/旧写回缺失时，从平台 SKU 数字尾号推导。
- 不伪造：`订单号_公共部分/平台SKU_统一/需要合并/包含包裹/merge_group/sku_base/通途SKU_公共部分` 由身份字段计算。

## 4. 血缘与断言

每行追加：`source_row/group_id/merged/cost_qty/pieces/method/source/cost_status/cost_reason/derived_reason/lineage_status/mapping_status/unmapped_columns`。

断言（三态）：

1. **166 列合同**；
2. **行集合=Phase1 合并明细**；
3. **100% 可追溯**：每个 Phase1 源行恰好被一行消费；合并行有 group_id；透传行 source_row 为单行；
4. **四列口径**：定价行四列齐全；阻断/跳过行四列留空（不填 0）；
5. **per_unit×数量=Phase2 合计**（容差 0.01）；
6. **1件成本=四列(除头程)之和**；
7. **关键列非空率**：是否皮壳全表非空、皮壳行=皮壳；定价行 运费 100%；
8. **派生列可算率**：定价行 `*数量/1件/产品成本/订单总成本` 100%；有收入的定价行 订单利润非空。

## 5. 差异归因

`差异归因` sheet 维度：**列 × method × 合并/透传 × disabled × status**。
另有 `未映射对比` sheet：旧写回非空 vs 新输出非空（按列）；`映射缺口` sheet：列 × reason 行数。
`disabled` 来自 `out/bom_disabled_items.txt`（EN `tabItem.disabled=1` 的 BOM item_fg 集合）。写回差异只对账，不采信。

## 6. 2026-11-04 演练结果

| 指标 | 202608 | 202609 |
|---|---:|---:|
| 输出行数 | 10,847 | 6,228 |
| 可定价 / 阻断 / 跳过 | **10,830 / 0 / 0** | **6,188 / 0 / 0** |
| 非商品配件 0 成本 / 组件吸收 0 成本 | 14 / 3 | 39 / 1 |
| 套件 priced / pending | 5 / 0 | 0 / 0 |
| kit_method 分布 | 成品 5 | — |
| 套件报表对账失败 / 双计阻断 | 0 / 0 | 0 / 0 |
| 四列空白行（阻断+跳过+待审） | **0** | **0** |
| 单位成本恒等失败行 | **0** | **0** |
| 1件成本恒等失败行 | **0** | **0** |
| 成本合计（皮壳/头程/二次/绍兴二次） | 571,444.99 / 122,712.29 / 1,492,383.46 / 66,300.78 | 352,574.98 / 88,479.46 / 884,415.98 / 48,541.83 |
| 派生列空值 | *数量/1件/产品成本 = 0；订单总成本/利润 = 17（仅 0 成本行） | 0；40（仅 0 成本行） |
| 派生列留空原因 | 非商品配件 14、组件吸收 3 | 非商品配件 39、组件吸收 1 |
| 关键列空白（是否皮壳/运费） | **0 / 0** | **0 / 0** |
| 关键列空白（suffix/件套/虚拟跟踪号/物流商单号/产品发售日期/当月是否新品） | 9090 / 10825 / 10813 / 9923 / 9709 / 10388 | 5216 / 6195 / 6213 / 4494 / 5244 / 5592 |
| 血缘失败 | 0 | 0 |

剩余阻断/跳过/待审：**0 / 0 / 0**（202608、202609）。
- `TT0031186K0063918-COVER`：用同订单 `FOAM/PPCotton` 锁定产品线（RSUS→KS0342-DM-50-DEEPBLUE；JYWM→KS0340-DM-50-DEEPBLUE）。
- YUS-112-5490993-8813056：TT0312681K0064361/4363 是两种颜色的整件成品 → `split_products` 分别计价（4 行）。
- ETSYUS-4137034553：3 个 Cover 已分别计价；PPCotton qty3 与 3 个 Cover 1:1 → `component_absorbed` 零成本。
- TJ# TT0031102-ZUHE-ALL：Product Bundle 展开 5 个子件，`kit_method=成品`，`bundle_version=2026-08-11 17:39:10.966269|628319d6f208`；与 show_kit_items 报表对账差 0；5 行计价。
- OSFD-479986021：3 个颜色皮壳 → split 逐件计价；共享海绵属另一产品 KS0428，独立计价。

**method 兜底结果**：202608 137 行、202609 125 行 `item_group_fallback`；铁架 `TT0312701K0064561` 96 行（202608）→ 成品；`TT0312687K0064377-COVER/-FOAM` 通过刷新后的 alias 命中 `KS0495-FHXWXNERSZSRB-143x84x88-DARKRED`（白日梦躺椅，半成品）。

**未映射列改善**（旧写回非空 → 新输出非空）：是否皮壳 99→10,854 / 84→6,230；suffix 17→1,757 / 1→1,012；
运费保持 100% 非空（旧表 10,870/6,246 → 新 10,854/6,230）。件套/虚拟跟踪号/物流商单号/产品发售日期等
在原始订单与旧写回中本身覆盖率低，无法唯一映射时留空并标注，未伪造。
