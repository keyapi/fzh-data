---
okf: v0.1
type: Reference
title: 离线证据表 v2 · 4379 美中订单行的身份解析与成本来源状态（Codex §9.5 交付物）
description: 按 Codex 第三轮修订方案第 5 条交付的离线证据表 v2：逐行给出「命中原码/命中方式/候选/直连值/直连成本来源/旧路径值/旧路径成本来源/两路对比/处置分类」；含版本清单(manifest)；先做证据表、不先建表
date: 2026-10-16
module: tongtool_order_cost
tags: [cost, ustx, evidence, offline, codex, reference]
---

# 离线证据表 v2 · 4379 美中订单行

> **依据**：Codex 第三轮修订方案第 5 条（[20](20-codex-round3-corrections.md) §9）——
> **「先做离线证据表；先修登记冲突/明确别名、业务确认剩余语义，再对拍 8/9 月；不要求先建新表」**。
> v2 已落地该方案的 **T1–T4**（见 §3）。**这是给下一轮复核与业务确认的共同靶子。**

## 1. 产物

| 文件 | 说明 |
|---|---|
| `out/ustx_wage_sim/offline_evidence_ustx_rows_v2.csv` | **4379 行 × 17 列**（评审对象） |
| `out/ustx_wage_sim/offline_evidence_manifest.json` | **T4 版本清单**：输入 sha256 / 时点 / 别名规则版本 / 计数 |
| `out/ustx_wage_sim/build_evidence_table_v2.py` | 生成脚本（**只读**，可复跑核对） |

**列**：`源CSV物理行 / 订单号 / 通途SKU / 命中原码 / 命中方式 / 品类尺寸面料编码 / 旧路径重量模板 /
候选数 / 候选(产品编号|发货方式|USTX) / 直连值 / 直连成本来源 / 旧路径值 / 旧路径成本来源 / 两路对比 / 处置分类 / 发货仓库 / 发货数量`

## 2. 结果（4379 行）

### 2.1 处置分类（**给业务的工作清单**）

| 处置分类 | 行数 | 含义 |
|---|---:|---|
| `auto_ok` | **3975** | 两路一致、非歧义、非回退 0 —— **可直接采用** |
| `review_zero_source` | **331** | 直连值为 0 且**无 BOM**（回退 0）—— **需确认「真 0」还是「缺 BOM」** |
| `review_direct_only` | **41** | 只有直连有值（旧路径断链）—— 需确认直连值可用 |
| `review_value_diff` | **20** | 两路**都有值但不一致** —— 需业务判断 |
| `review_bundle` | **4** | **五件套**（Product Bundle）—— 需套件路径 |
| `review_ambiguous_customer_code` | **3** | 同一完整客户码指向多产品多值 —— **阻断，不取 max** |
| `business_exempt_zero` | **3** | 空 key 业务豁免（2 针线扣 + 1 棉包） |
| `review_alias_pending` | **2** | 靠去末尾 `-Cover` 才命中 —— **别名待确认** |
| **合计** | **4379** | |

> **业务只需看 405 行**（非 `auto_ok` 的全部）。

### 2.2 成本来源（**T1：把「0」拆开**）

| 直连成本来源 | 行数 | | 旧路径成本来源 | 行数 |
|---|---:|---|---|---:|
| `bom_cost`（有 active+default BOM） | 3981 | | `bom_cost` | 3965 |
| `fallback_zero`（无 BOM 且值=0） | 359 | | `fallback_zero` | 335 |
| `fallback_nonzero`（无 BOM，回退 `valuation_rate`≠0） | 29 | | `fallback_nonzero` | 31 |
| `no_customer_code` | 7 | | `no_weight_template` | 44 |
| `ambiguous_customer_code` | 3 | | `no_value` | 4 |

### 2.3 两路对比

| | 行数 |
|---|---:|
| `same` | **4308** |
| `direct_only` | **41** |
| `DIFF` | **20** |
| `neither` | 7 |
| `old_only` | **3**（= 客户码歧义那 3 行） |

## 3. 已落地的 T1–T4（Codex §9 的规范）

| # | 项 | 落地 |
|---|---|---|
| **T1** | **细分「0」** | 成本来源拆成 `bom_cost` / `fallback_zero` / `fallback_nonzero`；**「原始数值 0」与「来源」分列**，不自动批准 |
| **T2** | **身份 vs 代理分开** | `直连值/直连成本来源`（身份）与 `旧路径值/旧路径成本来源`（**历史成本代理**）**两列并列**，不因身份更精确就默默换费用政策 |
| **T3** | **登记冲突 / 明确别名** | 3 行 `ambiguous_customer_code` + 2 行 `review_alias_pending` **显式标出**（**不自动消歧**；修复需业务/EN 侧动作） |
| **T4** | **锁定计算版本** | `offline_evidence_manifest.json`：输入 sha256 / 快照时点 / **别名规则版本**（`v2: 仅 -Cover 去尾、标 pending、不自动消歧`）/ 计数 |

## 4. 怎么用

1. **业务/财务**：只看 `处置分类 != auto_ok` 的 **405 行**，按分类逐桶核对（`review_zero_source` 331 行是大头，多为「无 BOM 回退 0」）。
2. **下一轮评审**：见 [22-review-brief-for-cursor-grok.md](22-review-brief-for-cursor-grok.md)（**自足**，不依赖 Codex 上下文）。
3. **对拍 8/9 月**：**待语义确认后**再做（Codex 明确要求先确认语义）。

## 5. 未证实

- 405 行里各桶的**业务最终归属**（需通途商品主档 / 实物 / 财务）。
- **7 月当时的登记状态**（反例仍在：[20](20-codex-round3-corrections.md) §6）。
- `fallback_zero` 的 331 行：**「真 0」还是「缺 BOM」** 未定（表已分类，语义待业务）。

## 6. 与 v1 的差异

v1（`offline_evidence_ustx_rows.csv`）只有 6 类状态、无「处置分类」、无 manifest、且**曾有一个 bug**（`bom_cost` 判据拿 `产品编号` 比 `USTXBZCP#` 码 → 全被误判 `valuation_fallback`，已修）。**以 v2 为准。**
