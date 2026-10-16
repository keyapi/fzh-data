---
okf: v0.1
type: Reference
title: 通途SKU↔EN物料 权威映射（ref_code / importBOMCostList.客户物料号）与 gsheet 源头修正
date: 2026-10-17
category: integration-issues
module: tongtool_order_cost
problem_type: integration_issue
component: tooling
severity: high
applies_when:
  - "要把通途订单的 SKU 对到 EN 物料/成本（尤其美中 USTX 二次加工）"
  - "订单解析出的 品类尺寸面料编码 与 EN 对不上，怀疑解析错或 gsheet 数据错"
  - "要改 gsheet 里的成本映射表（先确认它是源表还是 IMPORTRANGE 的显示层）"
  - "自己算了个覆盖率，准备据此下结论前"
tags: [tongtu, erpnext, en-item, customer-code, gsheet, importerange, coverage, ustx]
---

## Context

美中（USTX）订单成本要靠「订单 → EN 物料 → 重量模板 → 成本」这条链。旧法按通途产品名解析出 `品类尺寸面料编码` 再查表；但**通途产品名常与 EN 不一致**（历史/登记错/改 SKU 习惯），解析出的编码就会和 EN 对不上，取到错模板。本页沉淀 2026-10 排查 USTX 成本时确立的**权威映射**与两个通用坑。

## Guidance（本学习沉淀的做法）

### 1. 通途SKU → EN物料 的**权威桥**（两条，都不需要通途 API）

| 源 | 位置 | 说明 |
|---|---|---|
| **EN `Item Customer Detail.ref_code`** | EN DB 子表（`parent`=EN 物料名） | 通途SKU 的权威登记。**REST 查该字段会 403**，须 SSH 查 DB：`SELECT ref_code,parent FROM \`tabItem Customer Detail\` WHERE ref_code IN (...)` |
| **`importBOMCostList.客户物料号`** | gsheet 成本导入表 | 通途SKU→EN `产品编号` 的**现成列**；**不必 SSH、不必通途 API** |

- 由 EN 物料名派生重量模板：**去掉最后一个 `-` 段（颜色/变体）再加前缀 `ZLMB#`**
  （`KS0423-XNEOSTH-153x65x23-OFFWHITE` → `ZLMB#KS0423-XNEOSTH-153x65x23`）。
- **口径**：**直连优先、旧键兜底** —— 能按 `通途SKU` 直连就用（最准），否则回落 `品类尺寸面料编码`。
- 实测（2026-07 美中 4379 行）：**直连覆盖 4367/4372 = 99.9%**；相对走旧键：**B2 匹配 4328→4372、未匹配 51→7、ΔB2 264,912→268,610**。

### 2. 改 gsheet 成本映射前，**先分清「源表」与「显示层」**

- `二次加工成本2022 / import皮壳成本` 的 A/B 两列是 **`=IMPORTRANGE("<源工作簿id>", "<源ws>!E:F")`** —— **改它无效**（下次刷新被覆盖）。
- **唯一可改点是源工作簿**：`财务部绍兴成本核算表单2023` 的 `皮壳成本平均…`（键 + `EN重量模板物料号`）、`品类使用面料`（品类→品类编码）、`材料价格明细`（面料名→材料编码）。
- **键的坑**：`品类使用面料` 里**两个品类共用同一品类编码** → 键撞车 → 下游 `drop_duplicates(键)` **静默取首行**，取到谁取决于行序。修法：给各款回归 EN 真码，**源表+成本表成对改**（只改一边会丢成本）。

### 3. 覆盖率/结论前**必做反证**（本页最贵的教训）

- 我先算出「直连覆盖率 11%」并差点据此下结论 —— **实际是我的解析脚本 `f[0].startswith("TT")` 把 `CE*`/`SX*`/`PP*` 前缀的客户码全丢了**；真值是 **99.9%**。
- 教训：①**筛选/前缀判断前先统计分布**，别让"顺手的前缀过滤"静默丢数据；②大批量 SSH 分块查询会**输出回显异常**（本条症状），小分块更稳；③**任何覆盖率数字，先抽查几条原始记录**。

## Why This Matters

- 通途↔EN 的 SKU 口径不一致是**系统性**的（改名习惯 + 历史登记），靠"解析产品名"必然踩坑；有权威桥就能把"猜"变成"查"。
- gsheet 是**财务主表**且层层 IMPORTRANGE，改错一边就静默错成本；分清源/显示层是动手前提。
- 覆盖率这类"自己算出来的数字"最容易变成错误结论的支点（本次差点冤枉系统）。

## When to Apply

- 任何 USTX/美东/波兰成本取数、`品类尺寸面料编码` 对不上、或要动 gsheet 成本映射时。
- 写"筛选/过滤后统计"的脚本时（前缀、后缀、白名单）。
- 准备用"覆盖率/命中率"支撑结论之前。

## Examples

- 权威桥实测（2026-10-17）：
  `TT0312588K0064179-Foam → KS0396-FHXRBFJPR-100x60x10-…`（**绗缝方格**扣子床头板）；
  同批 SKU 在订单键里却是 `KS0397-*`（**菱形**）—— 证明"解析键"会指错、直连才对。
- 撞车实伤：`KS0423-153-XNEOSTH` 曾被「床头靠枕」与「大靠背」共用 → `ZLMB#KS0364-…`(203) 与 `ZLMB#KS0423-…`(119) 谁先取到谁算数。
- `ZLMB#KS0396`(方格) vs `ZLMB#KS0397`(菱形) 同面料同尺寸差 **≈1.5 元/件**。

## Related

- 口径单一事实源（本主题的细账全在这）：[`tongtool_order_cost/docs/reference/cost-engine-spec/`](../../../tongtool_order_cost/docs/reference/cost-engine-spec/index.md)
  —— 尤其 [16 客户物料号直连](../../../tongtool_order_cost/docs/reference/cost-engine-spec/16-customer-sku-direct-path.md)、[27 gsheet 源头根因](../../../tongtool_order_cost/docs/reference/cost-engine-spec/27-gsheet-source-root-cause.md)、[28 解析 vs EN 体检](../../../tongtool_order_cost/docs/reference/cost-engine-spec/28-parse-vs-en-7to9.md)
- 通途订单号后缀与合并判据：`docs/solutions/conventions/tongtu-order-suffix-and-merge-criteria.md`（在分支 `docs/colab-cost-current-state` / PR #280，本分支未含）
- 通途订单→EN 精确串匹配：[`project_tongtool_sku_match_exact`]（记忆条：ref_code 等值、无后缀容错）
