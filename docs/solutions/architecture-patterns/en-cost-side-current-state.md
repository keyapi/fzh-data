---
okf: v0.1
type: Reference
title: EN 成本侧现状（BOM Cost List / 客户码与配套物料 / 借用规则）
date: 2026-10-08
last_updated: 2026-10-08
category: architecture-patterns
module: en_api
problem_type: architecture_pattern
component: en-cost-side-current-state
severity: medium
applies_when:
  - "要把旧 Colab 的成本/匹配口径收口到 EN，先确认 EN 侧到底提供了什么"
  - "需要按通途 SKU / 客户物料号匹配 EN BOM 成本，或判断共享部件如何归属成品"
  - "有人把 engine_170.py 或本地文件当成 EN Tongtool Cost Review 的实现"
tags: [erpnext, bom-cost-list, customer-code, supporting-material, borrow, tongtool-cost-review, boundary]
related_components: [missing_products, warehouse_restock, item_cost_sx, tongtool_order_cost]
---

# EN 成本侧现状

> **维护约定：本档案随改动同步更新。** EN 侧字段/配套物料/报表 filters 变化时更新本文件。
> 配套：[Colab 逐段现状](colab-cost-pipeline-current-state.md) · [GS 清单](colab-gsheet-inventory.md) · [数据流关系图](colab-cost-pipeline-data-flow.md)。
> 证据等级：引用仓库既有文档的为**文档既有**；实测数字为**实测**；EN 内部实现为**无法确认**。

## 1. 权威口径：`docs/bom_cost_explanation.md`

来源：EN 自定义报表 **`BOM Cost List`**。仓库别名：美东 USNJ = `CENTRADE`、美中 USTX = `DANEEY`、波兰 PL = `POLAND`。

**三条交付形态规则（业务不变量）**

| 绍兴发货方式 | 绍兴发货成本 | 头程 | 国外加工成本 |
|---|---|---|---|
| 皮壳 | `皮壳成本` | 头程皮壳运费 | 对应仓库加工成本 |
| 半成品 | `皮壳成本` + `绍兴包装半成品成本` | 头程半成品运费 | 对应仓库加工成本 |
| 成品 | `绍兴总成本` | 头程成品运费 | **0** |

- **§5 借用（缺失补值）**：按 `重量模板` 分组 → 组内取非 0 **最大值**补缺；组内无非 0 值则保持缺失。
- **§7 表头标准化**：表头可能含真实换行 / `<br>` / 空格 / `-`；统一（去空格 → 换行转 `<br>` → `-` 视为换行分隔）。
- **§6 明确范围外**：通途 SKU 尾缀（`-Cover`/`-Foam`/`-PPCotton`/`-1`）造成的成本拆分、**拆分多包裹成本系数**、尾程派送费/平台费/交易费/广告费、FBA（本报表只处理 USNJ/USTX/PL）。

## 2. EN `Tongtool Cost Review`（`CONCEPTS.md:301-308`）

- EN（测试与生产）侧订单成本核算。依据 **通途完整 SKU 后缀**（至少 `-Cover`/`-Foam`/`-1`/`-2`）**+ 销售订单「皮壳/成品/半成品」交付形态**，从 BOM 选**局部**成本。
- **完整选路源码不在本仓库，Agent 不得用本地文件杜撰公式。**
- 与 `tongtool_order_cost/tongtool_order_cost/engine_170.py`（本地落地 Jeck Google Sheet 特殊规则）**是两套东西**，不得混用（`CONCEPTS.md:305-308`、`sellfox-cover-shared-inventory-transition.md:190-193`）。
- 赛狐组合商品扣子件批次**不能**复现该逻辑；赛狐「采购成本」的三层含义与 Cost Review 的皮壳切片不是同一件事（`CONCEPTS.md:280`）。

## 3. 生成与读取 BOM Cost List 的路径

- 六个 filters：`item_group=产品`、`show_disabled=1`、`show_ref_code=1`、`sum_columns_at_end=1`、`pllc_sfg_missing_use_cover=0`、`simplified_column_view=0`。
- 本地工具：`EN_API/bom_cost_list_excel.py`（生成）、`EN_API/compare_bom_cost_list.py`（比对）；`missing_products/audit_three_systems.py::load_bom()` 读 `warehouse_restock/数据源` 下最新 `EN产品BOM成本列表*.xlsx`。
- GS 侧快照 ws：`财务部绍兴成本核算表单2023`/`EN产品BOM成本列表20260202`（及 20+ 历史副本，见 GS 清单）。

## 4. 客户码 / 配套物料体系

- 结构：底层值表（`Item Attribute Value All Fabric/Color`，`FAB-*`/`CLR-*`）→ 物料属性 → 模板（`has_variants=1`）→ 变体（`variant_of`）；面料/颜色引用底层表，尺寸独立定义。
- 变体命名：`{模板}-{面料abbr}-{尺寸abbr}-{颜色abbr}`（如 `KS0013-HLR-80-COFFEE`）。
- **客户码全局唯一**：一个客户物料号只能登记在一个 EN 物料（自定义 app 校验「客户物料号已存在于其他物料」）；移动/重建须先移除旧码再登记新物料（`erpnext-item-variant-creation-convention.md:205`）。另有约束：客户物料号只能加到「产品/套件#」物料组，否则 REST 返 **HTTP 417**（`tongtu-en-sellfox-instock-sku-mainline.md:150`）。
- **9 类配套物料**（属性组合）：皮壳#(面料+尺寸+颜色)、内胆#(尺寸+内胆面料/颜色)、绍兴包装皮壳#/成品#/半成品#(尺寸)、波兰PL/美东USNJ/美中USTX包装成品#(尺寸)、重量模板#(面料+尺寸)。
- 一键创建：EN UI「物料 一键创建配套物料及变体」→ `key_test.add_item_semi.create_supporting_items_and_variants`（**不自动补颜色属性值**）。
- 配套物料客户码调查**已封存**：`PK#` 0 条客户码；`HM1510` 75 条原始子表行、大量带"删除"前缀；结论前**不得迁移/删除/重定义**（`missing_products/AGENT_HANDOFF.md:83,302`、`tongtu-en-sellfox-instock-sku-mainline.md:170-176`）。

## 5. 客户码索引的正确做法（收口的关键）

- **BOM Cost List 的「客户物料号」列只可能显示一个码** ⇒ 直接用它做索引会漏掉同一产品 `customer_items` 子表里的其他完整码。**必须回读 EN Item 的 `customer_items[].ref_code` 重建 `客户码 → 产品[]`**（`tongtu-en-sellfox-instock-sku-mainline.md:53,162`；实现见 `missing_products/audit_three_systems.py` 的 `fetch_en_items()` 与索引构建）。
- 匹配两阶段：**完整码精确匹配**；**基码（去后缀）仅作候选**；三态 `已精确登记 / 仅基码匹配 / 真正未登记`。

## 6. 实测：EN BOM 客户码形态（`EN产品BOM成本列表20260202`，**实测**）

- **1977 产品 / 3315 客户码**；**一码多产品仅 7 个**（含 `TT0031177K0063900-Cover`→2、`TT0031178K0063902-Cover`→2、`Curve-Pillow-50-Foam`→3、`Curve-Pillow-50-PPCotton`→3 等共享芯/共用皮壳）。
- **多客户码产品 730 个**（2 码 453、3 码 155、5 码 35、4 码 30、6 码 20…最多 11 码）。
- 形态签名 top：`(TT,BASE)+(TT,Cover)` 132；`(其他,BASE)+(其他,Cover)` 76；`(FBA名,BASE)+(TT,BASE)` 55；`(CEN,N)+(TT,BASE)` 41。
- **两条决定性证据**：① **26 个产品**是"两个后缀皆 BASE 的 TT 码"（如 `TT0000759K0062943` + `TT0000759K0063275`）；② 同有 Cover 与 Foam 的产品里 **同 base 仅 4、跨 base 26**（如 `KS0428-LSR-55x55x40-REDBRICKS` 的 `TT0312597K0064195-Cover` 配 `TT0312589K0064187-Foam`）。
  ⇒ **任何"后缀/编号"规则都会漏，只有 EN 产品编号能连**；而 EN 产品编号又因"共享部件只登记一处"（**29 个 Foam 码里 28 个只登记在 1 个产品下**）会漏 ⇒ **必须叠加订单侧信号**（见 [关系图](colab-cost-pipeline-data-flow.md) 与 Phase B 设计）。
- 该点已由文档既有立场印证：共用皮壳的可解释一对多**先保留并报告**（`tongtu-en-sellfox-instock-sku-mainline.md:165`）。

## 7. 借用（borrow）实现对照

| 口径 | 位置 | 分组键 |
|---|---|---|
| **按重量模板取非 0 最大**（与 EN §5 一致） | `warehouse_restock/build_saihu_warehouse_restock.py::borrow_costs`、`stock_init/build_saihu_stock_init.py::_borrow_costs` | `重量模板` |
| 同前缀借用（**口径不同，勿用于本链**） | `item_cost_sx/bom_cost_to_saihu_item_cost.py::_apply_sku_borrow`（`item_cost_sx/AGENT_HANDOFF.md §4.2`：≥4 个 `-` 段取前 3；来源记 `成本借用自(产品编号)`） | SKU 前缀 |
| Colab 侧 | `cell 99` `groupby(重量模板编号).agg(['max','nonzero_mean'])` | `重量模板编号` |

## 8. 无法确认（必须留白，不得杜撰）
- `Tongtool Cost Review` 的**后缀优先级**、**多包裹成本拆分/分摊公式**、**"共享部件归属哪个成品"** 的判定实现 —— 源码不在本仓库（`CONCEPTS.md:302`、`pb_orders/docs/reference/server-deployment-architecture.md:53`）。
- EN 是否已把「SPU/包裹级拆分」落到订单行 —— 未核实。
- EN 是否已有"部件↔成品"的显式关系（本方案的长期方案 B）—— 未核实。
- ⇒ 后续 Phase B/G 只基于**现状证据**给方向与代价，**不假设 EN 公式**。
