---
okf: v0.1
type: Guide
title: 交接书 — 国外3家分公司 工时 / PP棉用量 逐月分析（7-9月）+ 国外包装BOM缺口
description: 财务 ZJ 需求的自足交接：给新对话/子Agent 直接执行
date: 2026-10-17
module: tongtool_order_cost
tags: [cost, bom, labor, ppcotton, overseas, handoff]
---

# 交接书：国外 3 家 工时 / PP棉用量 逐月（7-9月）

> **新对话/子Agent 直接执行本页**，无需其它上下文。

## 目标（财务 ZJ 要的）
1. **7-9 月逐月**：国外 3 家分公司（**美东 USNJ / 美中 USTX / 波兰 PL**）按 **EN 国外包装成品 BOM** 算出的 **①工序工时 ②PP棉用量**。
2. **查清"国外包装成品 BOM 缺失"**：是否落在 7-9 月？逐条列。缺的**能否用绍兴包装成品 BOM 复制**生成？**没有绍兴 BOM 意味着什么**（本就是成品？别的？）。→ 要**彻底报告**。
3. **可行性评估**：缺口能否填充？后续分析是否可行？

## 已确认口径（用户 2026-10-17）
- **PP棉用量：借绍兴**。
- **工时**：3 家**复制逻辑不同**，来自**生产设置**——**美东=1、波兰=1、美中=1.5**。
- 借用绍兴 BOM 的 PP棉用量与工时；当时国外就是"复制"出来的，**可能有缺失**。

## 已就位的项目记录（先读，别重造）
- `en-ustx-bom-wage-rate-spec.md` —— 美中 USTX 工资率链路：`operating_cost = Σ(工序分钟/60 × hour_rate)`；`hour_rate = labour(167.8) + manage(34.24)`，存放在 `Workstation「美中USTX包装」` 的 **`hour_rate_labour`/`hour_rate_manage`**（**非** ERPNext 标准字段；`tabHour Rate` 为空）。
- `en-ustx-no-bom-items-spec.md` —— **"缺国外包装 BOM"的现有专项**。
- `en-pl-finished-processing-nonzero-spec.md` —— 波兰成品非零加工。
- `en-shaoxing-shipment-cost-logic-spec.md` / `en-shaoxing-ship-method-taxonomy-spec.md`。
- `cost-engine-spec/`（03 数据源、12 重量模板映射）。

## 必做（用 Subagent 探 EN，只读）
1. **把「工时系数 1 / 1 / 1.5」落到字段级证据**：它在 EN 哪个字段/Doctype（`Workstation`? `Operation`? `BOM Operation.time_in_mins`? 自定义字段?）、3 家分别怎么取、**美中 1.5 在哪体现**。**若项目无记录 → 直接读 EN 代码（`work_order_task` / `key_test` / `tongtool_integration`）与库实况查清**，给路径:行号。
2. **PP棉用量**：在 BOM 里是什么物料/字段（`raw_material_cost` 的哪一行），绍兴 vs 国外如何一致/不一致。
3. **缺口**：对 7/8/9 月通途自发货订单，逐月统计「其国外包装成品 BOM 是否存在」；缺失者逐条列（SKU/月份/对应绍兴BOM有无）。

## 交付
- 一份报告（`docs/reference/` 下新建）+ 机器可读 CSV（`out/`）；每步给**可复现命令**。
- **只读 EN**：不建/改/删任何记录；`uv run python`；不打印凭证。

## 另附（拟合用）
财务给了 `D:\Work\王忠于\成本核算-9境外二次加工成本.xls`（3 家 × 3 月的**工钱 + PP棉用量**）——
目的可能是**核对当前工站工资率（167.8 / 拟 105）与管理费率（34.24）是否合理**。
⚠️ 该目录在**工作目录之外**：新对话需先取得 `D:\Work\王忠于\成本核算` 的目录授权才能读。
