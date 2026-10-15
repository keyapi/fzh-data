---
okf: v0.1
type: Log
title: cost-engine-spec 变更日志
---
# 变更日志

## 2026-10-15
- **bundle 首次成型**：把散落在 Colab/SHEET/EN 三侧的「成本口径」逆向结果，收拢为**单一事实源**（入口 [01-overview-and-glossary.md](01-overview-and-glossary.md)）。本次补全 4 个缺失页 + 索引 + 本日志：
  - [01-overview-and-glossary.md](01-overview-and-glossary.md) —— 入口：系统上下文、范围/非目标、**数据时点**（快照 09-03 / 线上 10-15 / 剔除额 10-10）、实体与编码速查、用户惯用语对照、18 项「疑问→答案」总表。
  - [02-keys-and-entities.md](02-keys-and-entities.md) —— **键与实体**：三套键（`品类尺寸面料编码` = `品类尺寸编码 + "-" + 材料编码.replace("ML-","")`；`品类尺寸编码` = `品类编码 + "-" + 尺寸`；EN 等价键 `重量模板编号`→并入订单改名 `EN重量模板物料号`）、前缀实体（`PK#`/`SXBZBCP#`/`SXBZCP#`/`USNJBZCP#`/`USTXBZCP#`/`PLBZCP#`/`ZLMB#`/`ML-`）、分流字段（`custom_shipment_type_to_branch` 等，401 组分布 成品165/皮壳156/半成品62/空18）、**6 列去重键**（`运营人员+发货区域+通途SKU+渠道账号不含国家+渠道账号+发货仓按销售汇总分类`）、键的坑（同键歧义 7 月 3 个 / 空键 75 行 / 命名不一致 `ZLMB#KS0383-HLR- 140*50*24`）。
  - [03-data-sources.md](03-data-sources.md) —— **数据源清单**：GS 侧 5 个工作簿（`通途订单202607`/`和财务部共享`/`二次加工成本2022`/`财务部绍兴成本核算表单2023`/`头程运费成本`）逐 ws 的生成者·消费者·行数；EN 侧报表（BOM Cost List V1/V2 等）、Doctype（BOM/Item/Item Group/Workstation/Tongtu Shipping Warehouse/Tongtool Settings）、app（`work_order_task`/`key_test`/`tongtool_integration`/`delivery_plan`/`vilavi_pim`）；缺口指向 [../old-system-source-coverage-audit.md](../old-system-source-coverage-audit.md)。
  - [04-cost-decision-tables.md](04-cost-decision-tables.md) —— **核心决策表**：按 目的地 × 绍兴发货方式 的 皮壳/头程/目的地加工/绍兴侧加成 取值链；A/B1/B2/B3 四方案对照（7 月 ￥加权 526,225 / 752,854 / 791,137 / 717,678）；头程专项（A=B2 Δ=0）、二次加工专项（+225,982，占 85%）。
  - [colab-engine-cell-by-cell.md](colab-engine-cell-by-cell.md) —— 老引擎逐 cell 逆向（224 cell）：全流程骨架、每列取值链、13 开关、硬编码与清零/占位规则、已知坑。
  - [deduction-and-sxbzcp-adjustments.md](deduction-and-sxbzcp-adjustments.md) —— **剔除额**完整定义（`get_sxbzbcp_deduction` 只减不加）、受影响列、非 FBA 半成品发货成本**不受影响**、Jack commit `533ecad`/`cf0bbbd`(2026-10-10)、09-03 快照证实未扣。
  - [en-branching-and-warehouse-config.md](en-branching-and-warehouse-config.md) —— EN **39 个分流点**穷举（9 文件，路径:行号）+ `Tongtu Shipping Warehouse` **40 行**配置（FBA 19 行 `processing_cost_name` 全空，美国海外仓 2 行非空）+ 目的地加工成本/头程三列取值链。
  - [07-colab-vs-en.md](07-colab-vs-en.md) —— **替换进度表**：4 个 BOM 类成本列里 2 个已 EN（皮壳 Δ=0、头程 Δ=0）、2 个仍借用（二次加工 +225,982、绍兴二次加工 +38,930）。
  - [08-special-cases.md](08-special-cases.md) —— **特例**：`-COVER`/`-PPCOTTON`/`-FOAM`（含数字后缀 `-COVER1`/`-FOAM1`）、自采购、拆单多包裹系数、Product Bundle、FBA 强制清零、是否需尾程、`HEAD-SX→0`、品类白名单清零、灰区 `fillna(0)`（`大件云仓`/`主体骨架 沙发L形支架`）、`0.001` 占位（`注意-清零PL二次加工成本`）、星链海外仓→DANEEY 替换。
  - [09-known-issues-register.md](09-known-issues-register.md) —— **问题登记册**：A（EN 内部不一致 7 项）/B（时序错配 3 项）/C（数据缺口与脏数据 9 项）/D（命名坑 6 项）/E（待证实 8 项）。**全 bundle 的「未证实」均指向此页**。
  - [10-glossary.md](10-glossary.md) —— **术语表（字段级）**：实体与编码（前缀/成本来源编码/头程编码/SKU 后缀）与 字段与列名（EN 字段/GS 列名/Colab 开关/报表列）两张速查表。

> **时点声明**：本 bundle 的「线上事实」以 **2026-10-15** 为观测点；GS 快照另有明确时点（见 [01](01-overview-and-glossary.md) §4）。跨时点结论一律先声明时点。
