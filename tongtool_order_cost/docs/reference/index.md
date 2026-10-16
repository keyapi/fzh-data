---
okf: v0.1
type: Index
title: reference 索引
description: 特殊规则列与模式参考
tags: [reference, index]
---
# reference

| 文档 | 说明 |
|------|------|
| [rule-columns.md](rule-columns.md) | 系数列 / 参考值列 / 目标订单列 |
| [gsheets-credentials.md](gsheets-credentials.md) | gspread 本地 SA JSON |
| [gsheet-monthly-sheet-upload.md](gsheet-monthly-sheet-upload.md) | 月度成品 xlsx → 固定 gsheet 月度 ws（patch 写入：复制/归档/只覆盖变化列） |
| [monthly-tail-cost-pipeline.md](monthly-tail-cost-pipeline.md) | 月度尾程补齐全链路（通途导出→EN 预估→键值合并→GSheet）+ 覆盖率口径 + 缺尾清单 |
| [colab-cost-engine-spec.md](colab-cost-engine-spec.md) | Colab 成本引擎逆向规格（皮壳/头程/二次加工/绍兴二次加工 + 仓库→来源编码 + 美中 USTX 不对称） |
| [monthly-profitability-audit.md](monthly-profitability-audit.md) | 月度盈利审计：只读冻结→口径矩阵→对账闸门→JSON/Excel/管理摘要（两阶段 CLI）；含美中 USTX 三方案对比 `ustx-compare` |
| [ustx-cost-caliber-note.md](ustx-cost-caliber-note.md) | 美中仓库二次加工成本口径变更说明（给财务/业务）：A/B1/B2 差额 + 分歧归因 + 待确认项 |
| [en-ustx-bom-wage-rate-spec.md](en-ustx-bom-wage-rate-spec.md) | EN「美中加工成本, USTX」成本链路逆向规格：公式、167.8 工资率存放记录、随动项、复制 BOM 机制、167.8→105 复算（含 `out/ustx_wage_sim/` 逐 BOM 结果） |
| [en-ustx-no-bom-items-spec.md](en-ustx-no-bom-items-spec.md) | EN 美中 USTX 无 BOM 物料画像（96 个）· 309 张 BOM 来源与时间分布 · 能否补齐 · PP棉→海绵 对自动复制链路的影响（只读调查） |
| [en-shaoxing-ship-method-taxonomy-spec.md](en-shaoxing-ship-method-taxonomy-spec.md) | 「绍兴发货方式」定义（Item Group 字段 `custom_shipment_type_to_branch`）· 36 个无 PP棉源的画像 · 「成品→国外加工=0」核实 · 三种发货情况能否区分（只读调查） |
| [en-material-request-type-spec.md](en-material-request-type-spec.md) | `Item.default_material_request_type` 调查：取值分布（Purchase 66.6% / Manufacture 33.4%）、谁读谁写、与「绍兴发货方式」正交不冲突、2025 起不再维护（只读调查） |
| [en-pl-finished-processing-nonzero-spec.md](en-pl-finished-processing-nonzero-spec.md) | PL 16 个「成品却带非零加工成本」逐条清单：来源=2025-02 建料批次人工残值（未被 BOM 回写覆盖）· 清零金额 1463.17 复核 · 影响 `pllc_cover` 不影响绍兴总成本（只读调查） |
| [overseas-bom-labor-ppcotton-findings.md](overseas-bom-labor-ppcotton-findings.md) | 国外 3 家分公司：工时系数 1/1/1.5 字段级落点（`Manufacturing Settings.foreign_branch_time_multipliers`→`Foreign Branch Time Multiplier.time_multiplier`，仅 `bom_batch_process.py` 复制时乘）· PP棉用量（单行 BOM、1:1 借绍兴）· 7-9 月国外包装成品 BOM 缺口逐月行数与要因分布（只读调查） |
| [en-shaoxing-shipment-cost-logic-spec.md](en-shaoxing-shipment-cost-logic-spec.md) | EN「绍兴发货成本」按发货方式的组合（皮壳→皮壳；半成品→皮壳+半成品；成品→绍兴总成本）· 是否区分 分公司/FBA/海外仓 · 头程与发货方式联动（只读核实） |
| [old-system-source-coverage-audit.md](old-system-source-coverage-audit.md) | 老系统各源表对 7 月订单的覆盖率与缺口：`测算 美中USTX二次加工成本` 缺 43.5%（最严重）· 头程 USTX 表多为「列未回填、可 rematch」· 缺口清单 `out/ustx_wage_sim/source_coverage_gaps.csv` |
| [sku-remap.md](sku-remap.md) | 订单旧 SKU → 井新名 |
| **[cost-engine-spec/](cost-engine-spec/index.md)** | **成本口径单一事实源（bundle）**：系统总览与术语 · 键与实体 · 数据源 · **按目的地×发货方式的决策表** · Colab 逐 cell · EN 39 个分流点+仓库配置 · 剔除额 · Colab↔EN 替换进度 · 特例 · 问题登记册 |
