---
okf: v0.1
type: Reference
title: 业务操作清单 · 502 行按桶（谁确认什么、怎么确认）
description: 把离线证据表 v3 的 502 个非 auto_ok 行按 8 个桶整理成可执行清单；含每桶「要谁确认/确认什么」与涉及物料；并说明其中 474 行已因三时点验证大幅降级
date: 2026-10-16
module: tongtool_order_cost
tags: [cost, ustx, checklist, business, reference]
---

# 业务操作清单 · 502 行

> 产物：`out/ustx_wage_sim/business_checklist.csv`（502 行，含物理行号/订单号/SKU/两路值与来源/两路对比）。
> **前提**：机制已被三重证明（见 [23](23-en-report-rest-fetch-and-timepoints.md)）——
> **同一时点上 `美中加工成本 ≡ 该时点 active+default BOM 的 total_cost`（0 例外）**。

## 各桶：要谁确认什么

| 桶 | 行数 | 涉及物料 | **要谁 / 确认什么** |
|---|---:|---|---|
| `review_source_unverified` | **474** | KS0455-92-FHXWXNE(65)、RD-YM-pillow-015-60-WGMSRKQCLG(65)、SX-ZTCQX-194-KQC(31)… | **财务/你**：**确认是否接受「9/3 的值来自当时 BOM」**。机制已三重证明；9/3→10/16 仅 **9 个产品漂移（0.4%）**。**多数行是覆盖差异（disabled 件），不是值可疑** → **可批量接受，不必逐行核** |
| `review_value_diff` | 11 | RD-YM-pet-006-45-WGMSR(9)、SX-STH-SET6-YLR(2) | **业务**：两条路径值不同，**确认以哪条为准**（建议客户码=件级，但**需抽验实物/Listing**） |
| `review_bundle` | 4 | RD-YM-kid-001-SET5-KJB(4) | **业务/主数据**：五件套的**套件身份与成本规则**（**不要为套件硬造 BOM**） |
| `review_ambiguous_customer_code` | 3 | LM-HS-001-FOAM-50-DM(2)、…-HLR(1) | **主数据**：同一完整客户码指向**多个产品且成本不同**（PP 件 85.75843 / 海绵件 0）→ **确认应挂哪个产品** |
| `business_exempt_zero` | 3 | Buttonkit(2)、CEN-PPCotton-5lb(1) | **业务**：确认**维持归零**（售后针线扣 / 棉包） |
| `review_ambiguous_weight_template` | 3 | KS0423-153-XNEOSTH(3) | **主数据**：旧路径同键指两个重量模板（KS0364 vs KS0423）→ **确认应选哪个**（Codex §5.1 认为当前对象支持 KS0423） |
| `review_alias_pending` | 2 | XZH-HS-007-98-HLR(1)、SX-KZPT-100-DL(1) | **主数据**：靠去 `-Cover` 才命中 → **确认该别名成立** |
| `review_direct_only` | 2 | SX-KZSJ-194-MYJ(1)、SX-KZSJ-194-PPTM(1) | **主数据**：只有直连有值 → **确认该值可用** |

## 建议的确认顺序（按投入产出）

1. **先批量处理 474 行**（`review_source_unverified`）：**一看「9 个漂移产品」清单**（[23](23-en-report-rest-fetch-and-timepoints.md) §2），
   确认「7 月核算该用 9/3 值还是 10/16 值」；**其余按覆盖差异接受**。
2. **再看 28 行**（其余 7 个桶）：这些是**真正需要逐条判断**的。
3. **9 个漂移产品单独决策**：`KS0437`(177→271.29)、`KS0455`(206.479→90.306)、`KS0481`(**0→104.04**)。

## 附：9/3 → 10/16 漂移产品（唯一需要「选时点」的地方）

| 产品（族） | 9/3 值 | 10/16 值 |
|---|---:|---:|
| `KS0437-…-120x200x45-*` | 177.0 | **271.285333333** |
| `KS0455-FHXWXNE-92x56x75-*` | 206.479 | **90.306** |
| `KS0481-CTTM-45x45-*` | 0.0 | **104.035333333** |

> **要你拍板的只有一句**：**7 月订单核算，用 9/3 的 BOM 状态，还是用当前（10/16）的？**
> 这决定上面 3 个族在 7 月账上取哪个值。**其余 496 行不受影响。**
