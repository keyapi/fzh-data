---
okf: v0.1
type: Index
title: cost-engine-spec 索引
description: EN/Colab 成本引擎的逐列与逐 cell 逆向规格 —— 成本口径的单一事实源
tags: [reference, index, cost-engine]
---
# cost-engine-spec

> 本 bundle 是**成本口径的单一事实源**：任何成本列怎么来、为什么两套系统不一样、缺哪些数，先查这里。

| 文档 | 说明 |
|------|------|
| [01-overview-and-glossary.md](01-overview-and-glossary.md) | **入口**：系统上下文、范围/非目标、数据时点、实体与编码速查、用户惯用语对照、「疑问→答案」总表 |
| [02-keys-and-entities.md](02-keys-and-entities.md) | **键与实体**：三套键（`品类尺寸面料编码`/`品类尺寸编码`/`重量模板编号`）、前缀实体、分流字段、6 列去重键、键的坑 |
| [03-data-sources.md](03-data-sources.md) | **数据源清单**：GS 工作簿/ws（谁写谁读多少行）+ EN 报表/Doctype/app；缺口指向覆盖率审计 |
| [04-cost-decision-tables.md](04-cost-decision-tables.md) | **核心**：按 目的地 × 绍兴发货方式 的各分项取值决策表（皮壳/头程/目的地加工/绍兴侧加成）+ A/B1/B2/B3 四方案对照 |
| [colab-engine-cell-by-cell.md](colab-engine-cell-by-cell.md) | 老成本引擎逐 cell 逆向（Colab notebook + Google Sheet）：全流程骨架、每列取值链、与 EN 对照、13 开关 |
| [deduction-and-sxbzcp-adjustments.md](deduction-and-sxbzcp-adjustments.md) | 「剔除额」完整定义（`get_sxbzbcp_deduction` 只减不加）· 受影响列清单 · 半成品发货成本是否受影响（非 FBA=不影响）· Jack commit `533ecad`/`cf0bbbd`(2026-10-10) · 09-03 快照证实未扣 |
| [en-branching-and-warehouse-config.md](en-branching-and-warehouse-config.md) | EN 39 个分流点穷举（9 文件，路径:行号）+ `Tongtu Shipping Warehouse` 40 行配置 + 目的地加工成本/头程三列取值链 |
| [07-colab-vs-en.md](07-colab-vs-en.md) | **替换进度表**：逐成本列标「A 现状取数 / EN 取数 / 是否已切 / 7 月差额」（皮壳✅Δ=0、头程✅Δ=0、二次加工❌+225,982、绍兴二次加工❌+38,930） |
| [08-special-cases.md](08-special-cases.md) | **特例**：`-COVER`/`-PPCOTTON`/`-FOAM`（含数字后缀）、自采购、拆单系数、Product Bundle、FBA 清零、是否需尾程、`HEAD-SX→0`、品类白名单清零、灰区 `fillna(0)`、`0.001` 占位、星链替换 |
| [09-known-issues-register.md](09-known-issues-register.md) | **问题登记册**：EN 内部不一致（A）、时序错配（B）、数据缺口/脏数据（C）、命名坑（D）、待证实（E）。所有「未证实」指向此页 |
| [10-glossary.md](10-glossary.md) | **术语表（字段级）**：实体前缀/成本来源编码/头程编码/SKU 后缀/EN 字段/GS 列名/Colab 开关两表速查 |

## 疑问 → 答案位置

（完整 18 项见 [01](01-overview-and-glossary.md) §8；此处为高频入口）

| 疑问 | 去哪 |
|---|---|
| A/B1/B2/B3 各用了哪些成本？ | [04](04-cost-decision-tables.md) §5 + [07](07-colab-vs-en.md) |
| 某成本列到底怎么算？ | [04](04-cost-decision-tables.md)（决策表）+ [colab-engine-cell-by-cell.md](colab-engine-cell-by-cell.md)（老引擎逐 cell） |
| 头程 `HEAD-USTX` / `HEAD-USTX-PK` 有何区别？ | [04](04-cost-decision-tables.md) §2.2；[08](08-special-cases.md) §7 |
| 「二次加工」用绍兴包装成品还是美中包装成品？ | [04](04-cost-decision-tables.md) §6；[07](07-colab-vs-en.md) |
| 某个键/前缀代表什么物料？ | [02](02-keys-and-entities.md) §2；[10](10-glossary.md) |
| 某张表谁写谁读、多少行？ | [03](03-data-sources.md) |
| 老系统哪些表会缺行？缺多少？ | [03](03-data-sources.md) §3；[../old-system-source-coverage-audit.md](../old-system-source-coverage-audit.md) |
| `-COVER` / `-PPCOTTON` / `-FOAM` 是什么？ | [08](08-special-cases.md) §1 |
| 剔除额是什么？影响半成品发货成本吗？ | [deduction-and-sxbzcp-adjustments.md](deduction-and-sxbzcp-adjustments.md)；[04](04-cost-decision-tables.md) §4 |
| EN 内部自己一致吗？ | [en-branching-and-warehouse-config.md](en-branching-and-warehouse-config.md)；[09](09-known-issues-register.md) |

## 相邻文档（不在本 bundle）

- 专项调查：[../en-ustx-no-bom-items-spec.md](../en-ustx-no-bom-items-spec.md)、[../en-pl-finished-processing-nonzero-spec.md](../en-pl-finished-processing-nonzero-spec.md)、[../en-material-request-type-spec.md](../en-material-request-type-spec.md)、[../en-shaoxing-shipment-cost-logic-spec.md](../en-shaoxing-shipment-cost-logic-spec.md)、[../en-shaoxing-ship-method-taxonomy-spec.md](../en-shaoxing-ship-method-taxonomy-spec.md)
- 美中 USTX 方案对比：[../monthly-profitability-audit.md](../monthly-profitability-audit.md)、[../ustx-cost-caliber-note.md](../ustx-cost-caliber-note.md)、[../en-ustx-bom-wage-rate-spec.md](../en-ustx-bom-wage-rate-spec.md)
- 覆盖率审计：[../old-system-source-coverage-audit.md](../old-system-source-coverage-audit.md)
- Colab 引擎总规格：[../colab-cost-engine-spec.md](../colab-cost-engine-spec.md)
