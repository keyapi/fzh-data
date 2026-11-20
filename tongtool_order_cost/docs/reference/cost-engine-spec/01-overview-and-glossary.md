---
okf: v0.1
type: Reference
title: 通途订单成本引擎 · 总览与术语（Colab + Google Sheet + EN）
description: 本 bundle 的入口：系统上下文、范围与非目标、数据时点、实体与编码体系、术语表、以及「本次所有疑问 → 在哪一节被回答」的对照表
date: 2026-10-15
module: tongtool_order_cost
tags: [cost, tongtu, colab, gsheet, erpnext, reference, overview, glossary]
---

# 通途订单成本引擎 · 总览与术语

> 本 bundle 是**成本口径的单一事实源（single source of truth）**。凡「某成本列怎么来的 / 为什么两家算法不一样 / 缺哪些数」，
> 先查这里，再下钻到具体文档。
> 写作时间：**2026-10-15**。所含「线上事实」以该日为观测点；**数据快照**另有明确时点（见下）。

## 1. 这套系统在做什么

公司跨境电商，货从**绍兴**发出，去往：
- **分公司**：美东 USNJ、美中 USTX、波兰 PL（分公司负责当地加工/发货）
- **FBA**：美国/欧洲/日本/英国
- **海外仓**：美国海外仓、欧洲海外仓、加拿大海外仓
- **绍兴自发货**

需要对**每一笔通途订单行**算出它的产品成本与利润。成本由三块拼成（老架构的「**3 段论**」）：

```
1件产品成本 = 皮壳成本 + 绍兴二次加工成本 + 二次加工成本
订单总成本 = 产品成本*数量 + 头程运费*数量 + 运费 [+ 海外仓成本*数量]
订单利润   = 售价*汇率 − 订单总成本
```

## 2. 两套「谁算成本」的实现（本 bundle 的核心张力）

| | **老系统（Colab + Google Sheet）** | **EN（ERPNext）** |
|---|---|---|
| 形态 | Colab notebook 读 Google Sheet，算完写回共享表 | ERPNext app（`work_order_task` / `key_test` / `tongtool_integration`）在服务端算 |
| 成本主源 | 多张人工维护的 GS 表（**常需手工补行**） | 物料 BOM（`total_cost`）+ 价目表 |
| 键 | `品类尺寸面料编码`（= `品类尺寸编码 + "-" + 材料编码.replace("ML-","")`） | 等价键 = `重量模板编号`（并入订单时改名为 `EN重量模板物料号`） |
| 现状 | **补丁上落补丁**（13 个开关、17 处未启用/已知坑）；部分列已切到 EN，部分仍是借用/硬编码 | 相对确定；但**内部有 39 个按「发货方式/目的地类型」的分流点，口径互不一致** |
| 走向 | 用户方向：**逐步用 EN 的取值逻辑替换** Colab 的老逻辑 | — |

> **看当前「EN 化」进度** → [07-colab-vs-en.md](07-colab-vs-en.md)
> **看每个成本列到底怎么算** → [04-cost-decision-tables.md](04-cost-decision-tables.md)

## 3. 范围与非目标

**范围内**：成本口径（皮壳/头程/二次加工/绍兴二次加工/绍兴发货成本/目的地加工成本）、键与编码体系、数据源与血缘、分流转折、特例、缺口与已知问题。

**非目标**：
- 不评判「该不该这样算」（口径归属财务）；
- 不含售价/退款/税费口径（除与成本直接相关的汇率）；
- 不含「如何把 Colab 迁到服务器 / 换掉 Google Sheet」的方案（另题）。

## 4. 数据时点（**重要**）

| 对象 | 时点 | 说明 |
|---|---|---|
| GS「EN产品BOM成本列表20260202」快照 | **2026-09-03** 导出 | 名字里的日期是旧名，**不是** 2 月快照；**不是今天的 EN 状态** |
| 剔除额改动（Jack） | **2026-10-10** 提交 | 09-03 快照**尚未**含剔除额 |
| 海外加工成本优先 BOM 改动（Jack，V1+V2） | **2026-10-12** 提交 | `KS0455-DEEPBLUE` 的 `…-010` 主 BOM 同日上午创建 |
| 当前 Drive notebook（7067） | **2026-10-14** 最后修改 | 新增 `eval_delivery_en`（**保存代码 ≠ 已运行**） |
| 线上 EN 生产库 | **2026-10-16** 观测 | 与 09-03 快照**已有实质差异** |
| 7 月订单对账用快照 | `out/profitability_audit/2026年7月订单_ustx2/` | 上述各源的冻结副本 |

> ⚠️ **四种状态不能混用**（2026-10-16 Codex 独立复核确立，见 [13](13-codex-review-corrections.md) §1）。
> 本 bundle 里凡以「9/3 快照 = 现状」口吻写的句子，**一律按「9/3 时点」理解**。
> 反例：`KS0455-FHXWXNE-92x56x75-DEEPBLUE` 在 9/3 是「皮壳」、**当前已是「半成品」**，且主 BOM 于 10-12 新建。

→ **任何跨时点的结论都要先看这一节**：拿 09-03 的表去对 10-15 的线上，必错。

## 5. 实体与编码体系

详见 [02-keys-and-entities.md](02-keys-and-entities.md)。速查：

| 前缀/字段 | 含义 |
|---|---|
| `PK#` | 皮壳物料 |
| `SXBZBCP#` | 绍兴包装**半成品** |
| `SXBZCP#` | 绍兴包装**成品** |
| `USNJBZCP#` / `USTXBZCP#` / `PLBZCP#` | 美东 / 美中 / 波兰 **包装成品**（= 各目的地的"国外包装成品"） |
| `ZLMB#` | 重量模板（= EN 的 `重量模板编号`） |
| `custom_shipment_type_to_branch` | Item Group 自定义字段，Select：`皮壳`/`半成品`/`成品` —— 表达**绍兴给（国外）分公司的发货方式** |
| `二次加工成本来源编码` | `2CJG-US`(美东) / `2CJG-PL`(波兰) / `2CJG-SX`(绍兴) / `2CJG-USNJ-TEST` / `2CJG-USTX-TEST` |
| `头程运费来源编码` | `HEAD-US` / `HEAD-USTX` / **`HEAD-USTX-PK`** / `HEAD-PL` / `HEAD-USFBA` / `HEAD-USHWC` / … |

> ⚠️ **命名坑**：GS 表 `import皮壳成本` 的三列叫「绍兴/美国/波兰**二次加工成本**」，但**绍兴那一列装的其实是「绍兴包装成品成本」**（与 `importBOMCostList.绍兴包装成品成本` 在 4328/4331 行数值相同）。表名、列名、实际内容三者不一致。

## 6. 「术语」与用户惯用语对照

| 用户说法 | 实际对象 |
|---|---|
| 「国外包装成品」 | `USTXBZCP#` / `USNJBZCP#` / `PLBZCP#`（**不是**「国外加工成品」，用户已更正口径） |
| 「国外加工成本」 | 这些国外包装成品物料的 active+default BOM 的 `total_cost`（= GS 表的 `美中/美东/波兰加工成本` 列） |
| 「绍兴发货成本」 | EN **订单同步字段** `sx_shipping_cost`：按绍兴发货方式组合（皮壳／皮壳+半成品／绍兴总成本） |
| 「绍兴总成本」 | EN**报表列** `sx_cost_all`：皮壳+绍兴包装成品成本（**不含**半成品；见 [04](04-cost-decision-tables.md)） |
| 「三段简单相加」 | 用户 **Colab 侧老设计**的局限，**不是** EN 的行为（EN 的 `绍兴总成本` ≠ 三段相加） |
| 「剔除额」 | Jack 于 2026-10-10 引入的「只减不加」修正，见 [deduction-and-sxbzcp-adjustments.md](deduction-and-sxbzcp-adjustments.md) |

## 7. 导航：本 bundle 的文件

| 文件 | 内容 |
|---|---|
| [02-keys-and-entities.md](02-keys-and-entities.md) | 键与实体、编码体系、去重键 |
| [03-data-sources.md](03-data-sources.md) | 数据源清单（GS 工作簿/ws + EN 报表/Doctype），谁生成、谁消费 |
| [**04-cost-decision-tables.md**](04-cost-decision-tables.md) | **核心**：按 目的地 × 发货方式 的各分项取值决策表 |
| [05 … colab-engine-cell-by-cell.md](colab-engine-cell-by-cell.md) | Colab 老引擎逐 cell |
| [06 … en-branching-and-warehouse-config.md](en-branching-and-warehouse-config.md) | EN 39 个分流点 + `Tongtu Shipping Warehouse` 40 行配置 |
| [06 … deduction-and-sxbzcp-adjustments.md](deduction-and-sxbzcp-adjustments.md) | 剔除额与 Jack 的改动 |
| [07-colab-vs-en.md](07-colab-vs-en.md) | Colab ↔ EN 逐步替换进度 |
| [08-special-cases.md](08-special-cases.md) | 后缀特例 / 自采购 / 拆单 等 |
| [09-known-issues-register.md](09-known-issues-register.md) | **问题登记册**（缺口、冲突、口径漂移、未证实） |
| [10-glossary.md](10-glossary.md) | 术语表（含字段级） |

**相邻文档（不在本 bundle，但强相关）**：
- 具体分支的专项调查：[en-ustx-no-bom-items-spec.md](../en-ustx-no-bom-items-spec.md)、[en-pl-finished-processing-nonzero-spec.md](../en-pl-finished-processing-nonzero-spec.md)、[en-material-request-type-spec.md](../en-material-request-type-spec.md)、[en-shaoxing-shipment-cost-logic-spec.md](../en-shaoxing-shipment-cost-logic-spec.md)、[en-shaoxing-ship-method-taxonomy-spec.md](../en-shaoxing-ship-method-taxonomy-spec.md)
- 美中 USTX 三/四方案对比（A/B1/B2/B3）：[monthly-profitability-audit.md](../monthly-profitability-audit.md)、[ustx-cost-caliber-note.md](../ustx-cost-caliber-note.md)、[en-ustx-bom-wage-rate-spec.md](../en-ustx-bom-wage-rate-spec.md)
- 源表覆盖率审计：[old-system-source-coverage-audit.md](../old-system-source-coverage-audit.md)

## 8. 「本次所有疑问 → 在哪被回答」对照表

| # | 疑问 | 答案位置 |
|---|---|---|
| 1 | A/B1/B2/B3 各用了哪些成本？ | [04](04-cost-decision-tables.md) §「四方案取数」 + [07](07-colab-vs-en.md) |
| 2 | 皮壳成本哪来的、会不会变？ | [04](04-cost-decision-tables.md) §皮壳；[05](colab-engine-cell-by-cell.md) |
| 3 | 头程 `HEAD-USTX` / `HEAD-USTX-PK` 有何区别？影响 7 月吗？ | [04](04-cost-decision-tables.md) §头程；[en-shaoxing-shipment-cost-logic-spec.md](../en-shaoxing-shipment-cost-logic-spec.md) |
| 4 | 为什么四个方案头程完全一样？ | [04](04-cost-decision-tables.md) §头程（A 已 = EN 按发货方式）；[07](07-colab-vs-en.md) |
| 5 | 「二次加工」用的是绍兴包装成品还是美中包装成品？ | [04](04-cost-decision-tables.md) §二次加工与绍兴侧 |
| 6 | 「成品 → 国外加工成本 = 0」成立吗？ | [04](04-cost-decision-tables.md) §目的地加工成本；[en-shaoxing-ship-method-taxonomy-spec.md](../en-shaoxing-ship-method-taxonomy-spec.md) |
| 7 | 96 个无 BOM 的美中物料是什么？ | [en-ustx-no-bom-items-spec.md](../en-ustx-no-bom-items-spec.md) |
| 8 | PL 那 16 个「成品却带非零加工成本」？ | [en-pl-finished-processing-nonzero-spec.md](../en-pl-finished-processing-nonzero-spec.md) |
| 9 | `default_material_request_type` 被用来当标记了吗？ | [en-material-request-type-spec.md](../en-material-request-type-spec.md) |
| 10 | 「绍兴发货方式」到底是什么、在哪？ | [en-shaoxing-ship-method-taxonomy-spec.md](../en-shaoxing-ship-method-taxonomy-spec.md)、[02](02-keys-and-entities.md) |
| 11 | 剔除额是什么？影响半成品发货成本吗？ | [deduction-and-sxbzcp-adjustments.md](deduction-and-sxbzcp-adjustments.md) |
| 12 | EN 内部自己一致吗？ | [06](en-branching-and-warehouse-config.md)、[07](07-colab-vs-en.md)、[09](09-known-issues-register.md) |
| 13 | 老系统哪些表会缺行？缺多少？ | [old-system-source-coverage-audit.md](../old-system-source-coverage-audit.md)、[09](09-known-issues-register.md) |
| 14 | 工资率 167.8→105 影响多少？ | [en-ustx-bom-wage-rate-spec.md](../en-ustx-bom-wage-rate-spec.md) |
| 15 | `-COVER` / `-PPCOTTON` / `-FOAM` 各是什么？ | [08-special-cases.md](08-special-cases.md) |
| 16 | Colab 有哪些开关、哪些没启用？ | [05](colab-engine-cell-by-cell.md) |
| 17 | 「3 段论」是什么？现在还成立吗？ | §1 本文 + [07](07-colab-vs-en.md) |
| 18 | 哪些列已经是 EN、哪些还是借用？ | [07-colab-vs-en.md](07-colab-vs-en.md) |
