---
okf: v0.1
type: Reference
title: 术语表（字段级 · 实体前缀 / 编码 / 字段 / 开关 / 后缀 / 列名）
description: 本 bundle 全部专有名词的字段级释义，分「实体与编码」与「字段与列名」两表；含实体前缀、成本来源编码、头程编码、SKU 后缀、EN 字段、GS 列名、Colab 开关
date: 2026-10-15
module: tongtool_order_cost
tags: [cost, glossary, field-level, reference]
---

# 术语表（字段级）

> 全 bundle 专有名词速查。排序：数字/字母开头者按字符序在前，中文按拼音。
> 概念性与用户惯用语对照见 [01-overview-and-glossary.md](01-overview-and-glossary.md) §5/§6。

## 表 1 · 实体与编码

| 名称 | 释义 |
|---|---|
| `2CJG-PL` | `二次加工成本来源编码` 取值：波兰 |
| `2CJG-SX` | 同：**绍兴**。7 月美中 USTX 行仍写此值（历史上「借绍兴拟合」） |
| `2CJG-US` | 同：美东 USNJ |
| `2CJG-USNJ-TEST` / `2CJG-USTX-TEST` | 同：美东/美中测试态（`if_use_test_cost` 时改用） |
| `-COVER` | SKU 后缀：皮壳件（头程一律皮壳头程、加工成本清零） |
| `-COVER1` | SKU 数字后缀：仅改有效重量口径 |
| `-FOAM` | SKU 后缀：头程取差额（成品头程−皮壳头程；半成品则 半成品头程−皮壳头程） |
| `-FOAM1` | SKU 数字后缀：仅改有效重量口径 |
| `-PPCOTTON` | SKU 后缀：头程与发货成本双侧清零 |
| `HEAD-CAHWC` | 头程来源编码：加拿大海外仓 |
| `HEAD-EUFBA` | 头程来源编码：欧洲 FBA |
| `HEAD-EUHWC` | 头程来源编码：欧洲海外仓 |
| `HEAD-JPFBA` | 头程来源编码：日本 FBA |
| `HEAD-PL` | 头程来源编码：波兰 PL |
| `HEAD-SX` | 头程来源编码：绍兴自发货 → **头程 = 0** |
| `HEAD-UKFBA` | 头程来源编码：英国 FBA |
| `HEAD-US` | 头程来源编码：美东 USNJ |
| `HEAD-USFBA` | 头程来源编码：美国 FBA |
| `HEAD-USHWC` | 头程来源编码：美国海外仓 |
| `HEAD-USTX` | 头程来源编码：美中 USTX，**按物料发货方式**（成品/半成品/皮壳）落列 |
| `HEAD-USTX-PK` | 头程来源编码：美中 USTX，**固定用皮壳头程** |
| `ML-` | 材料编码前缀；构成 `品类尺寸面料编码` 时剥掉 |
| `ND#` | 内胆物料前缀（`doc_event` → `cost_nd`） |
| `PK#` | 皮壳物料前缀（`doc_event` → `cost_pk`） |
| `PL` | 波兰分公司（目的地） |
| `PLBZCP#` | 波兰包装成品物料前缀 |
| `SXBZBCP#` | 绍兴包装**半成品**物料前缀 |
| `SXBZCP#` | 绍兴包装**成品**物料前缀 |
| `USNJ` | 美东分公司（目的地） |
| `USNJBZCP#` | 美东包装成品物料前缀 |
| `USTX` | 美中分公司（目的地） |
| `USTXBZCP#` | 美中包装成品物料前缀 |
| `ZLMB#` | 重量模板物料前缀（= EN `重量模板编号`） |
| `重量模板编号` | EN 侧等价键；并入通途订单时改名 `EN重量模板物料号` |
| `美东 USNJ` / `美中 USTX` / `波兰 PL` | 三个**分公司**目的地 |
| `FBA` | 目的地类型：美/欧/日/英（`warehouse_classification` 含 `FBA` → FBA 分支，加工成本恒 0） |
| `海外仓` | 目的地类型：美国海外仓（**复用美中加工成本**，走非 FBA 分支）、欧洲/加拿大海外仓（**无配置行**） |
| `绍兴自发货` | 目的地类型：分类选项有、**无配置行**（`HEAD-SX→0`） |

## 表 2 · 字段与列名

| 名称 | 位置 | 释义 |
|---|---|---|
| `custom_model_id` | Item Group | KS 码映射；用于解析绍兴发货方式 |
| `custom_shipment_type_to_branch` | Item Group | **绍兴发货方式**（`皮壳`/`成品`/`半成品`；label `Shipment Type To Branch`） |
| `custom_split_package_cost_factor` | Item | 拆单多包裹成本系数 |
| `custom_valuation_rate` | Delivery Note Item | `doc_event` 写的成本列（**非**原生 `valuation_rate`） |
| `default_material_request_type` | Item | **不是业务标记**（多为默认 `Purchase`；残留 `Phantom` 选项来自已卸载 `zelin_pp`） |
| `EN重量模板物料号` | GS 列 | EN 重量模板物料号（`import皮壳成本` 等表内，与 `品类尺寸面料编码` 并存） |
| `hour_rate_labour` / `hour_rate_manage` | Workstation | 工资率（`美中USTX包装`：167.8 / 34.24） |
| `is_active` / `is_default` | BOM | 取 BOM `total_cost` 需 `is_active=1 且 is_default=1` |
| `needs_last_leg` | 订单/成本复核 | 是否需尾程（FBA/多渠道/云仓/对方付 → 0） |
| `operating_cost` / `raw_material_cost` / `scrap_material_cost` | BOM | 三费；`total_cost = 三者之和` |
| `processing_cost_name` | Tongtu Shipping Warehouse | 目的地加工成本列名（FBA 全空、美国海外仓非空） |
| `total_cost` | BOM | BOM 总成本；目的地加工成本与绍兴成本的主取值 |
| `valuation_rate` | Item | 物料估值；**无 BOM → 回退用它** |
| `warehouse_classification` | Tongtu Shipping Warehouse | 仓库分类（含 `FBA` → FBA 分支） |
| `bcp_first_freight` | 订单行 | 头程半成品运费（= BOM 列 × 数量 × 拆单系数） |
| `cp_first_freight` | 订单行 | 头程成品运费 |
| `pk_first_freight` | 订单行 | 头程皮壳运费 |
| `cost_fg` | 订单行/报表 | 成品成本（= 物料当前 active+default BOM 三费之和） |
| `cost_nd` | 订单行 | 内胆成本（`ND#`） |
| `cost_pk` | 订单行 | 皮壳成本（`PK#`） |
| `cost_sxbzbcp` | 订单行 | 绍兴包装半成品成本 |
| `cost_sxbzcp` | 订单行 | 绍兴包装成品成本 |
| `destination_processing_cost` | 报表 | 目的地加工成本（按仓库 code 选 USNJ/USTX/PL；FBA/HWC 恒 0） |
| `first_freight` | 订单行 | 头程运费（按发货方式/后缀落列） |
| `pllc_cover` | 报表列 | 「发皮壳/发半成品」兼用之列 |
| `pllc_fg` | 报表列 | 发成品尾程前成本 |
| `sx_cost_all` | 报表列 | **绍兴总成本** = 皮壳 + 绍兴包装成品成本（半成品只减剔除、不加半成品） |
| `sx_shipping_cost` | 订单同步字段 | **绍兴发货成本**：按发货方式三档组合（皮壳／皮壳+半成品／绍兴总成本） |
| `usnj_valuation_rate` / `ustx_valuation_rate` / `pl_valuation_rate` | 报表列 | 美东/美中/波兰目的地加工成本 |
| `二次加工成本*系数` | GS 列 | 二次加工成本 × 系数（缺列时 = 主列） |
| `二次加工成本来源编码` | 订单/GS | 见 `2CJG-*` |
| `头程运费来源编码` | 订单/GS | 见 `HEAD-*` |
| `品类尺寸编码` | GS 列 | = `品类编码 + "-" + 尺寸` |
| `品类尺寸面料编码` | GS 列 | = `品类尺寸编码 + "-" + 材料编码.replace("ML-","")`（材料码空则退化为 `品类尺寸编码`） |
| `绍兴二次加工成本` | GS 列 | 绍兴侧二次加工（**美中当前借此项**） |
| `绍兴包装半成品成本` / `绍兴包装成品成本` | GS 列 | 绍兴侧加成源（半成品/成品档） |
| `绍兴总成本` | 报表列 | = `sx_cost_all`（≠ 三段相加） |
| `美中加工成本, USTX` / `美东加工成本` / `波兰加工成本` | GS 列 | 目的地加工成本（= 目的地包装成品 BOM `total_cost`） |
| `剔除额` | 报表 | Jack 2026-10-10 引入的「只减不加」修正（`get_sxbzbcp_deduction`） |
| `皮壳成本` / `皮壳含包装成本` / `皮壳不含包装成本` | GS 列/口径 | 皮壳成本两种口径；按发货方式/来源编码选（见 [04](04-cost-decision-tables.md) §3） |
| `发成品尾程前成本` | 报表 | 受剔除额影响的列之一 |
| `运营人员` / `发货区域` / `通途SKU` / `渠道账号` / `渠道账号不含国家` / `发货仓按销售汇总分类` | 订单/规则 | **6 列去重键**组成（`渠道账号不含国家` = `渠道账号.str[:-2]`） |
| `发货仓库` / `发货数量` / `售价*汇率` | 订单 | 订单行基础列 |
| `if_0_PL_cost` | Colab 开关 | `注意-清零PL二次加工成本` → PL 成品二次加工成本 → 0.001 |
| `if_clear_all` | Colab 开关 | 写回前整表 clear |
| `if_del_special_order` | Colab 开关 | 按 `处理方式=='删除'` 剔订单 |
| `if_drop_row_empty_staff` | Colab 开关 | 是否 drop 运营人员为空行 |
| `if_replace_xinglianhwc_to_ustx` | Colab 开关 | `是-替换星链海外仓为DANEEY` → 星链海外仓 ⇒ `FZH-DANEEY-半成品仓` |
| `if_use_EN_cost_sxbzbcp` | Colab 开关 | 半成品行绍兴二次加工成本取 EN 半成品成本 |
| `if_use_EN_cost_sxbzcp` | Colab 开关 | 成品行绍兴二次加工成本取 EN 成品成本 |
| `if_use_test_cost` | Colab 开关 | 用测算成本时改 USNJ/USTX 来源编码 |
| `if_wedge_reduce_new_fabric_since_202403` | Colab 开关 | 202403 起三角新面料改写 |
| `option_head_source` | Colab 开关 | 头程用「头程运费合并」替换 EN / GS 原始版 |
| `mask_cost_fillna_zero` | Colab（cell_125） | 灰区（`大件云仓` / 产品名含「主体骨架 沙发L形支架」）15 列 `fillna(0)` |
| `ambiguous_shell_key` | 对比产出 | 同键指向不同重量模板时的排除标记 |

## 证据清单

- 见各页证据段：[02](02-keys-and-entities.md) §6、[03-data-sources.md](03-data-sources.md) §4、[04-cost-decision-tables.md](04-cost-decision-tables.md)、[08-special-cases.md](08-special-cases.md) §13、[en-branching-and-warehouse-config.md](en-branching-and-warehouse-config.md)
