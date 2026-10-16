---
okf: v0.1
type: Reference
title: 离线证据表 · 4379 美中订单行的身份解析与成本来源状态（Codex §9.5 交付物）
description: 按 Codex 第三轮修订方案第 5 条交付的离线证据表：逐行给出「命中方式 / 候选 / 直连值 / 旧路径值 / 成本来源状态 / 两路对比」；先做证据表、不先建表
date: 2026-10-16
module: tongtool_order_cost
tags: [cost, ustx, evidence, offline, codex, reference]
---

# 离线证据表 · 4379 美中订单行

> **依据**：Codex 第三轮修订方案第 5 条（见 [20](20-codex-round3-corrections.md) §9）——
> **「先做离线证据表；先修登记冲突/明确别名、业务确认剩余语义，再对拍 8/9 月；不要求先建新表」**。
> **这是给第四轮 Codex 复核与业务确认的共同靶子。**

## 产物

`tongtool_order_cost/out/ustx_wage_sim/offline_evidence_ustx_rows.csv`（**4379 行**，`out/` 已 gitignore）。

列：`源CSV物理行 / 订单号 / 通途SKU / 命中方式 / 品类尺寸面料编码 / 旧路径重量模板 / 候选数 /
候选(产品编号|发货方式|USTX) / 直连值 / 旧路径值 / 成本来源状态 / 两路对比 / 发货仓库 / 发货数量`

生成脚本：`out/ustx_wage_sim/build_evidence_table.py`（**只读**，不改任何外部系统）。

## 成本来源状态（按 Codex §9.3「0 与异常分开」的口径）

| 状态 | 行数 | 含义 |
|---|---:|---|
| `bom_cost` | **3963** | 该 USTX 包装成品有 **active+default BOM** → 值 = `total_cost` |
| `zero_literal` | **377** | 值为 **0**（**未细分**「无 BOM 回退 0」与「批准的零成本」——见 §待办） |
| `valuation_fallback` | **29** | 无 BOM → 回退 `Item.valuation_rate`（非 0） |
| `bundle_pending` | **4** | **五件套**（`TT0031102-zuhe-all`）→ 需 Product Bundle 路径，**不硬造 BOM** |
| `ambiguous_customer_code` | **3** | 同一完整客户码指向 **多个产品且成本不同** → **阻断，不取 max** |
| `business_exempt_zero` | **3** | 空 key 的业务豁免（2 针线扣 + 1 棉包） |
| **合计** | **4379** | 无静默丢行 |

## 两路对比（直连 vs 旧路径）

| 两路对比 | 行数 |
|---|---:|
| `same`（一致） | **4308** |
| `DIFF`（**都有值但不一致**） | **20** |
| `direct_only`（只有直连有值） | **41** |
| `old_only`（只有旧路径有值） | **0** |
| `neither`（两边都没有） | **7** |

> 注意：**`DIFF` 20 + `ambiguous` 3 + 旧路径歧义 3 = 26**，与 Codex 说的「23 处差异 + 3 客户码歧义」口径**需按其拆解对齐**（见 [20](20-codex-round3-corrections.md) §3）。**本表不替业务选边。**

## 怎么用（建议）

1. **业务/财务**：只看 `成本来源状态 ∈ {ambiguous_customer_code, valuation_fallback, bundle_pending, business_exempt_zero}` 与 `两路对比 = DIFF` 的行 —— **共 ≤ 40 行**，逐行核对实物/登记。
2. **第四轮 Codex**：见 [00](00-review-brief.md) 的第三轮结果 + 本表作为**可复算的一手输入**。
3. **对拍 8/9 月**：待 §2 的语义确认后再做（Codex 明确要求「先确认语义、再对拍」）。

## 待办（按 Codex §9 的规范，尚未做）

| # | 项 | 说明 |
|---|---|---|
| T1 | **细分 `zero_literal`** | 现 377 行里混了「无 BOM 回退 0」与「可能的批准零成本」→ 应拆成**两个字段**（原始数值 0 / 批准的零成本） |
| T2 | **加「历史成本代理」列** | 与「实际身份」并列（Codex §9.2），不得因身份更精确就默默换费用政策 |
| T3 | **修登记冲突 / 明确别名** | 3 行客户码歧义 + 2 行 `-Cover` 待验证别名 |
| T4 | **锁定计算版本** | 每次产出冻结（原始 SKU / resolved Item / 映射快照日期 / 别名规则版本 / 成本来源与值 / 仓库规则 / 行身份）；**当前重估与历史复原分别命名** |
| T5 | **不改现有链路** | 本表是**离线证据**，**未动** Colab / GS / EN |

## 未证实

- 17 行差异的**业务最终归属**（Codex 明确保留：通途商品主档查询本轮超时）。
- **7 月当时的登记状态**（反例：五件套客户码 `creation=5/21` 但 Version 显示 `8/11` 才 added）。
- `zero_literal` 里哪些是「真 0」哪些是「回退 0」。
